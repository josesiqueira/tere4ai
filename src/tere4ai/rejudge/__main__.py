"""Entry point: python -m tere4ai.rejudge norms --source SRC --out-dir NEW --name NAME --cost-stop USD

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

Card B173. A published build's generator output is judged again by the
judge the environment names, and written as a new build in NEW (named by
the rule of source.py, R11): layer1.json copied byte for byte,
norms_NAME.json, logs/ with the judge's event log (R8), build_records/
with the new record. `norms` judges every stored candidate norm again with
zero generator calls (Layer 2); every attempt is an execution rejudge_norms
covering LAYER2_STEP1 and LAYER2_STEP2, checkpointed per Article or Annex
(R7) and resumable as extract_norms is. The failure mechanics are the
sibling commands' (R12) plus the cost stop (R10, exit 5). The source folder
is only read.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tere4ai import parallel_calls
from tere4ai.act_parties import ACT_PARTIES_PATH
from tere4ai.extract_norms.actor_audit import addressee_counts, section_2_checks
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    USAGE_KEYS,
    AnthropicJudge,
    InferenceBackendUnavailable,
    declared_sampling,
)
from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    Heartbeat,
    RecordError,
    choose_record,
    create_chosen_record,
    existing_artefact_digest,
    live_run_refusal,
    published_artefact_owner,
    relative_to_dump_dir,
    signals_as_interrupt,
)
from tere4ai.graph_store.checkpoints import CheckpointError, prepare_resume, resume_command
from tere4ai.judge.config import (
    ConfigurationError,
    ModelConfigError,
    load_model_config,
    load_model_prices,
)
from tere4ai.rejudge.cost import CostStop, record_spend, usage_cost, usd
from tere4ai.rejudge.norms import (
    JUDGE_PROMPT_KIND,
    changed_verdicts,
    group_of,
    groups_in_order,
    merge_in_source_order,
    norms_refusal,
    recounted_stats,
    rejudge_group,
    rejudged_build_block,
    verdict_counts,
)
from tere4ai.rejudge.source import SourceError, name_refusal, read_source

PROGRAM = ".venv/bin/python -m tere4ai.rejudge"
NORMS_COMMAND = "rejudge_norms"
NORMS_RESULT_KEYS = ("norms", "judge_runs", "stats")
EXTRACTION_LOG = "rejudge_extraction_log.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _zero_usage() -> dict[str, int]:
    """The generator's usage at Layer 2: no generator client exists (R5)."""
    return dict.fromkeys(USAGE_KEYS, 0)


def _usage_of(client: object) -> dict:
    """Token counts the inference backend reported over this run; empty for a stub."""
    return dict(getattr(client, "usage", None) or {})


def _cost_stop(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not an amount in USD") from None
    if not value > 0:
        raise argparse.ArgumentTypeError("the cost stop must be above 0 USD")
    return value


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, required=True,
                        help="the published build folder to re-judge (read only, never written)")
    parser.add_argument("--out-dir", type=Path, required=True, help="the new build folder; its name must be --name")
    parser.add_argument("--name", required=True,
                        help="the new build's name: <date>-<source name without its date>-<judge model without "
                             "'claude-'>[-N]")
    parser.add_argument("--cost-stop", type=_cost_stop, required=True,
                        help="stop before the next group once the rejudge executions of the record have spent "
                             "this many USD at list price (a resume may raise it)")
    parser.add_argument("--resume", action="store_true", help="continue from the checkpoint of a stopped run")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tere4ai.rejudge",
        description="Judge a published build's stored generator output again and write a new build (B173).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    norms = commands.add_parser("norms", help="Layer 2: judge every stored candidate norm again, no generator call")
    _common_arguments(norms)
    parallel_calls.add_max_in_flight_argument(norms)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command with SIGTERM and SIGHUP raising KeyboardInterrupt, so a
    closed terminal ends the execution failed with its usage (final review A2 (a))."""
    with signals_as_interrupt():
        return _main(argv)


def _main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_argv = list(sys.argv[1:] if argv is None else argv)
    if args.command == "norms":
        return run_norms(args, run_argv)
    raise AssertionError(f"unknown subcommand {args.command!r}")  # argparse refuses it first


def _refuse(message: str, code: int) -> int:
    print(f"refusing to start: {message}", file=sys.stderr)
    return code


def run_norms(args: argparse.Namespace, run_argv: list[str]) -> int:
    """The Layer 2 flow: every refusal before any record is written, then one
    execution judging the groups not yet in the checkpoint."""
    try:
        source = read_source(args.source)
        source_payload = json.loads(source.norms_path.read_text(encoding="utf-8"))
    except SourceError as exc:
        return _refuse(str(exc), 2)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refuse(f"the source norms file cannot be read ({type(exc).__name__})", 2)
    try:
        cfg = load_model_config()
    except ModelConfigError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 4
    models = cfg.as_public_dict()
    refusal = norms_refusal(source_payload, models)
    if refusal:
        return _refuse(refusal, 2)
    judge_model = models["judge_model"]
    refusal = name_refusal(args.name, source.name, judge_model)
    if refusal is None and args.out_dir.name != args.name:
        refusal = f"the out-dir {args.out_dir} must be named {args.name}"
    if refusal:
        return _refuse(refusal, 2)
    try:
        prices = load_model_prices()
    except ConfigurationError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 4
    if judge_model not in prices:
        print(f"stopped: configuration error: config/model_prices.json has no price row for the judge "
              f"{judge_model!r}, so the cost stop cannot be kept", file=sys.stderr)
        return 4

    out_dir = args.out_dir
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    layer1_path = out_dir / "layer1.json"
    if layer1_path.exists():
        if sha256_of_file(layer1_path) != source.layer1_sha256:
            return _refuse(f"{layer1_path} is not the source's layer1.json (another sha256)", 2)
    else:
        shutil.copyfile(source.layer1_path, layer1_path)
    out_path = out_dir / f"norms_{args.name}.json"
    log_path = out_dir / "logs" / EXTRACTION_LOG
    store = BuildRecordStore(out_dir)
    # Nothing in a published build is edited in place (spec G Section 2).
    existing = existing_artefact_digest(out_path)
    owner = published_artefact_owner(store, out_dir, existing) if existing else None
    if owner:
        print(f"refusing to overwrite {out_path.name}: it is {owner}; choose another --name", file=sys.stderr)
        return 1
    out_path.touch()  # the zero-cost writability probe of extract_norms
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    dump = json.loads(layer1_path.read_text(encoding="utf-8"))
    source_build = source_payload["build"]
    prompt_version = source_build["prompt_version"]
    # R6: the judge runs keep the source's base build id
    build_id = source_build.get("build_id", "build-unknown")
    description = f"generator output of {source.name}, judged by {judge_model}"
    inputs = [
        {"input_kind": "layer1_dump", "file": relative_to_dump_dir(layer1_path, out_dir),
         "sha256": source.layer1_sha256},
        {"input_kind": "source_norms",
         "file": os.path.relpath(source.norms_path.resolve(), out_dir.resolve()), "sha256": source.norms_sha256},
        # the Act's parties the addressee counts read, as extract_norms records them
        {"input_kind": "act_parties",
         "file": os.path.relpath(ACT_PARTIES_PATH.resolve(), out_dir.resolve()),
         "sha256": sha256_of_file(ACT_PARTIES_PATH)},
    ]
    config = {"prompt_version": prompt_version, "max_in_flight": args.max_in_flight,
              "cost_stop_usd": args.cost_stop, "source_build": source.name, "source_record_id": source.record_id,
              "source_chain_id": source.chain_id, "judged_by": judge_model, "description": description}
    prompts = {"judge": prompt_sha256(load_prompt(JUDGE_PROMPT_KIND, prompt_version))}
    choice = choose_record(store, args.name, dump.get("build", {}).get("build_id"), source.layer1_sha256)
    refusal = live_run_refusal(store, choice.record_id, NORMS_COMMAND) if choice.record_id else None
    if refusal:
        return _refuse(refusal, 2)
    if choice.message and existing:
        print(f"refusing to overwrite {out_path.name}: {choice.message}, and the file belongs to the record it "
              "continues; choose another --name", file=sys.stderr)
        return 1
    try:
        plan = prepare_resume(checkpoint_path, "group", NORMS_RESULT_KEYS, resume=args.resume, accept_legacy=False,
                              store=store, record_id=choice.record_id, expected_config=config,
                              expected_inputs=inputs, expected_models=models, expected_prompt_sha256=prompts)
    except CheckpointError as exc:
        return _refuse(str(exc), 2)
    if plan.inherited_keys:
        print(f"resume: {len(plan.inherited_keys)} group(s) inherited from {plan.inherited_from}")

    # spec F D-F30: a terminal run with a checkpoint waits out an overload; no
    # generator client is built at Layer 2 (R5)
    judge = AnthropicJudge(cfg, retry_policy=TERMINAL_POLICY)
    record_id, message = create_chosen_record(store, choice)
    if message:
        print(message)
    source_norms: list[dict[str, Any]] = source_payload.get("norms") or []
    groups = groups_in_order(source_norms)
    run_id = store.start_execution(
        record_id, command=NORMS_COMMAND, covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"],
        argv=run_argv, inputs=inputs, config=config, expected_total=len(groups), work_unit="groups",
        checkpoint_file=relative_to_dump_dir(checkpoint_path, out_dir),
        resumes_run_id=plan.resumes_run_id, inherited_keys=plan.inherited_keys, inherited_from=plan.inherited_from,
        models=models, prompt_sha256=prompts, sampling=declared_sampling(None, judge),
    )

    print(f"calls in flight: at most {args.max_in_flight} (--max-in-flight)", flush=True)
    group_results: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
    completed: list[str] = []
    judge_price = prices[judge_model]

    def usage() -> dict:
        return {"generator": _zero_usage(), "judge": _usage_of(judge)}

    def spent() -> float:
        """R10: the record's other rejudge executions plus this run so far."""
        return (record_spend(store.read(record_id), prices, excluding=run_id)
                + usage_cost(_usage_of(judge), judge_price))

    def end_failed(error: str) -> None:
        # the original error is the one reported (B79 item 15)
        try:
            store.finish_execution(record_id, run_id, status="failed", usage=usage(), completed_keys=completed,
                                   sampling=declared_sampling(None, judge), error=error)
        except RecordError as record_exc:
            print(f"the failure could not be recorded: {record_exc}", file=sys.stderr)

    def print_resume(note: str = "") -> None:
        print(f"the checkpoint {checkpoint_path.name} is kept ({len(plan.inherited_keys) + len(completed)} of "
              f"{len(groups)} groups done); continue with{note}:", file=sys.stderr)
        print(f"  {resume_command(PROGRAM, run_argv)}", file=sys.stderr)

    try:
        with Heartbeat(store, record_id, run_id), checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for group in groups:
                if group in plan.entries_by_key:
                    continue
                so_far = spent()
                if so_far >= args.cost_stop:
                    raise CostStop(so_far, args.cost_stop)
                result = rejudge_group(dump, [n for n in source_norms if group_of(n) == group], judge,
                                       prompt_version=prompt_version, log_path=log_path, build_id=build_id,
                                       max_in_flight=args.max_in_flight)
                ckpt.write(json.dumps({"run_id": run_id, "group": group, "result": result}) + "\n")
                ckpt.flush()
                group_results.append(result)
                completed.append(group)
                # the usage so far rides on the beat: a SIGKILL loses at most the group in flight
                store.heartbeat(record_id, run_id, usage=usage())
                print(f"  {group}: {result['stats']['candidates']} norms, verdicts {result['stats']['verdicts']}",
                      flush=True)

        norms, judge_runs = merge_in_source_order(source_norms, group_results)
        stats = recounted_stats(source_payload.get("stats") or {}, norms)
        changed = changed_verdicts(source_norms, norms)
        sampling = declared_sampling(None, judge)
        source_usage = source_build.get("extraction_usage") or {}
        rejudge_block = {
            "description": description, "source_build": source.name, "source_record_id": source.record_id,
            "source_chain_id": source.chain_id, "source_norms_sha256": source.norms_sha256,
            "source_judge_model": (source_build.get("extraction_models") or {}).get("judge_model"),
            "judge_model": judge_model, "rejudged_at": _now_iso(),
            "carried_generator_usage": source_usage.get("generator"), "source_judge_usage": source_usage.get("judge"),
        }
        replaced = {
            "build": rejudged_build_block(
                source_build, public_models=models, judge_sampling=sampling["judge"],
                judge_effort=str(getattr(judge, "effort", "unknown")), judge_temperature=sampling["judge_temperature"],
                judge_usage=_usage_of(judge), zero_usage=_zero_usage()),
            "norms": norms, "judge_runs": judge_runs, "stats": stats,
        }
        payload = {key: replaced.get(key, value) for key, value in source_payload.items()}
        payload["rejudge"] = rejudge_block
        tmp_path = out_path.with_suffix(".writing.json")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.replace(out_path)
        store.finish_execution(
            record_id, run_id, status="done",
            outputs=[{"output_kind": "norms", "file": relative_to_dump_dir(out_path, out_dir),
                      "sha256": sha256_of_file(out_path)}],
            counts={"source_units": stats.get("source_units"), "candidates": stats["candidates"],
                    "verdicts": stats["verdicts"], "source_verdicts": verdict_counts(source_norms),
                    "changed_verdicts": {"count": len(changed), "norm_ids": changed},
                    **section_2_checks(norms, dump), **addressee_counts(norms)},
            usage=usage(), sampling=sampling, completed_keys=completed,
            work_failures={"nodes_failed": 0, "norms_failed": 0},
        )
    except CostStop as exc:
        # R10: the execution ends failed with the spend, the checkpoint stays
        end_failed(str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        print_resume(" (raise --cost-stop to go on)")
        return 5
    except InferenceBackendUnavailable as exc:
        # spec F D-F30: the terminal policy waited out its pauses
        end_failed(str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        print_resume()
        return 3
    except ModelConfigError as exc:
        # spec F D-F29: a declared parameter the inference backend refused, or a price row missing
        end_failed(str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        return 4
    except BaseException as exc:  # an interrupt too (B79 item 22): the execution never stays running
        end_failed(f"{type(exc).__name__}: {exc}")
        raise
    checkpoint_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(f"candidates: {stats['candidates']}")
    print(f"verdicts: {stats['verdicts']} (the source's {verdict_counts(source_norms)})")
    print(f"changed against the source: {len(changed)}")
    this_run = usage_cost(_usage_of(judge), judge_price)
    print(f"spend: {usd(this_run)} USD at list price in this run, {usd(record_spend(store.read(record_id), prices))} "
          "USD over the record's rejudge executions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

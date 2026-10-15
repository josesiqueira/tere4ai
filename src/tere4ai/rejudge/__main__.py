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
from tere4ai.extract_norms.model_clients import TERMINAL_POLICY, AnthropicJudge, declared_sampling
from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    Heartbeat,
    create_chosen_record,
    relative_to_dump_dir,
    signals_as_interrupt,
)
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
from tere4ai.rejudge.run import (
    Execution,
    Refusal,
    choose_output_record,
    effort_of,
    plan_resume,
    refuse,
    usage_of,
    zero_usage,
)
from tere4ai.rejudge.source import SourceError, name_refusal, read_source

NORMS_COMMAND = "rejudge_norms"
NORMS_RESULT_KEYS = ("norms", "judge_runs", "stats")
EXTRACTION_LOG = "rejudge_extraction_log.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
                        help="stop before the next group or batch once the rejudge executions of the record have "
                             "spent this many USD at list price (a resume may raise it)")
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
    try:
        if args.command == "norms":
            return run_norms(args, run_argv)
    except Refusal as refusal:
        print(refusal.message, file=sys.stderr)
        return refusal.code
    raise AssertionError(f"unknown subcommand {args.command!r}")  # argparse refuses it first


def run_norms(args: argparse.Namespace, run_argv: list[str]) -> int:
    """The Layer 2 flow: every refusal (a Refusal) before any record is written,
    then one execution judging the groups not yet in the checkpoint."""
    try:
        source = read_source(args.source)
        source_payload = json.loads(source.norms_path.read_text(encoding="utf-8"))
    except SourceError as exc:
        raise refuse(str(exc)) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise refuse(f"the source norms file cannot be read ({type(exc).__name__})") from None
    try:
        cfg = load_model_config()
    except ModelConfigError as exc:
        raise Refusal(4, f"stopped: {exc}") from None
    models = cfg.as_public_dict()
    refusal = norms_refusal(source_payload, models)
    if refusal:
        raise refuse(refusal)
    judge_model = models["judge_model"]
    refusal = name_refusal(args.name, source.name, judge_model)
    if refusal is None and args.out_dir.name != args.name:
        refusal = f"the out-dir {args.out_dir} must be named {args.name}"
    if refusal:
        raise refuse(refusal)
    try:
        prices = load_model_prices()
    except ConfigurationError as exc:
        raise Refusal(4, f"stopped: {exc}") from None
    if judge_model not in prices:
        raise Refusal(4, f"stopped: configuration error: config/model_prices.json has no price row for the judge "
                         f"{judge_model!r}, so the cost stop cannot be kept")

    out_dir = args.out_dir
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    layer1_path = out_dir / "layer1.json"
    if layer1_path.exists():
        if sha256_of_file(layer1_path) != source.layer1_sha256:
            raise refuse(f"{layer1_path} is not the source's layer1.json (another sha256)")
    else:
        shutil.copyfile(source.layer1_path, layer1_path)
    out_path = out_dir / f"norms_{args.name}.json"
    log_path = out_dir / "logs" / EXTRACTION_LOG
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")
    store = BuildRecordStore(out_dir)
    dump = json.loads(layer1_path.read_text(encoding="utf-8"))
    choice = choose_output_record(store, out_dir, out_path, alias=args.name,
                                  base_build_id=dump.get("build", {}).get("build_id"),
                                  layer1_digest=source.layer1_sha256, command=NORMS_COMMAND)

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
    plan = plan_resume(checkpoint_path, "group", NORMS_RESULT_KEYS, resume=args.resume, store=store, choice=choice,
                       config=config, inputs=inputs, models=models, prompts=prompts)

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
    execution = Execution(
        store=store, record_id=record_id, run_id=run_id, checkpoint_path=checkpoint_path, run_argv=run_argv,
        expected_total=len(groups), inherited=len(plan.inherited_keys), work_unit="groups",
        usage=lambda: {"generator": zero_usage(), "judge": usage_of(judge)},
        sampling=lambda: declared_sampling(None, judge),
    )
    judge_price = prices[judge_model]

    def judge_groups() -> dict[str, Any]:
        print(f"calls in flight: at most {args.max_in_flight} (--max-in-flight)", flush=True)
        group_results: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
        with Heartbeat(store, record_id, run_id), checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for group in groups:
                if group in plan.entries_by_key:
                    continue
                # R10: the record's other rejudge executions plus this run so far
                so_far = (record_spend(store.read(record_id), prices, excluding=run_id)
                          + usage_cost(usage_of(judge), judge_price))
                if so_far >= args.cost_stop:
                    raise CostStop(so_far, args.cost_stop)
                result = rejudge_group(dump, [n for n in source_norms if group_of(n) == group], judge,
                                       prompt_version=prompt_version, log_path=log_path, build_id=build_id,
                                       max_in_flight=args.max_in_flight)
                ckpt.write(json.dumps({"run_id": run_id, "group": group, "result": result}) + "\n")
                ckpt.flush()
                group_results.append(result)
                execution.completed.append(group)
                # the usage so far rides on the beat: a SIGKILL loses at most the group in flight
                store.heartbeat(record_id, run_id, usage=execution.usage())
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
                source_build, public_models=models, judge_sampling=sampling["judge"], judge_effort=effort_of(judge),
                judge_temperature=sampling["judge_temperature"], judge_usage=usage_of(judge),
                zero_usage=zero_usage()),
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
            usage=execution.usage(), sampling=sampling, completed_keys=execution.completed,
            work_failures={"nodes_failed": 0, "norms_failed": 0},
        )
        return {"stats": stats, "changed": changed}

    code, done = execution.run(judge_groups)
    if code:
        return code
    checkpoint_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(f"candidates: {done['stats']['candidates']}")
    print(f"verdicts: {done['stats']['verdicts']} (the source's {verdict_counts(source_norms)})")
    print(f"changed against the source: {len(done['changed'])}")
    this_run = usage_cost(usage_of(judge), judge_price)
    print(f"spend: {usd(this_run)} USD at list price in this run, {usd(record_spend(store.read(record_id), prices))} "
          "USD over the record's rejudge executions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

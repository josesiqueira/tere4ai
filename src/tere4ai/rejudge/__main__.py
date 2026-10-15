"""Entry point: python -m tere4ai.rejudge {norms,alignments,report} --source SRC --out-dir NEW --name NAME

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
(R7) and resumable as extract_norms is. `alignments` then judges the stored
alignment candidates of the norms the new judge accepts again and aligns
the newly accepted norms with the generator (Layer 3, R9), into
alignments_NAME.json; every attempt is an execution rejudge_alignments
covering LAYER3_STEP1 to LAYER3_STEP3, checkpointed per batch as align_hleg
is, and it runs only over the norms file a done rejudge_norms execution of
the record wrote. The failure mechanics are the sibling commands' (R12)
plus the cost stop (R10, exit 5). `report` writes NEW/README.md and
NEW/changed_verdicts.csv from the files and the record (report.py), and
replaces an existing report only with --overwrite (R11). The source folder
is only read, and the new build's folder never lies inside it, equals it or
holds it. `norms` runs the Layer 3 checks of the source alignments before it
writes anything (layer3_source), so Layer 2 is never paid for a source whose
Layer 3 would be refused; each subcommand names its judge (model, effort,
temperature) before its first call (final review).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

from tere4ai import parallel_calls
from tere4ai.act_parties import ACT_PARTIES_PATH
from tere4ai.align_hleg.__main__ import _attach_source_text
from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.hleg_source import HlegPair, HlegSourceError, load_pair
from tere4ai.extract_norms.actor_audit import addressee_counts, section_2_checks
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    AnthropicJudge,
    OpenAIGenerator,
    declared_sampling,
)
from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    Heartbeat,
    RecordError,
    create_chosen_record,
    relative_to_dump_dir,
    signals_as_interrupt,
)
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE
from tere4ai.judge.config import (
    ConfigurationError,
    ModelConfigError,
    load_model_config,
    load_model_parameters,
    load_model_prices,
)
from tere4ai.rejudge.alignments import (
    ALIGN_PROMPT_KIND,
    JUDGE_MODEL_KEYS,
    SourceAlignments,
    alignments_refusal,
    merge_batches,
    rejudge_batch,
    rejudged_alignment_build,
    source_index,
)
from tere4ai.rejudge.alignments import JUDGE_PROMPT_KIND as ALIGNMENT_JUDGE_PROMPT_KIND
from tere4ai.rejudge.cost import CostStop, record_spend, usage_cost, usd
from tere4ai.rejudge.norms import (
    JUDGE_PROMPT_KIND,
    changed_verdicts,
    group_of,
    groups_in_order,
    materialised_refusal,
    merge_in_source_order,
    norms_refusal,
    recounted_stats,
    rejudge_group,
    rejudged_build_block,
    verdict_counts,
)
from tere4ai.rejudge.report import write_report
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
from tere4ai.rejudge.source import (
    SourceBuild,
    SourceError,
    name_refusal,
    out_dir_refusal,
    read_source,
)

NORMS_COMMAND = "rejudge_norms"
NORMS_RESULT_KEYS = ("norms", "judge_runs", "stats")
EXTRACTION_LOG = "rejudge_extraction_log.jsonl"
ALIGNMENTS_COMMAND = "rejudge_alignments"
ALIGNMENTS_RESULT_KEYS = ("assertions", "mapping_runs", "judge_runs", "stats")
ALIGNMENT_LOG = "rejudge_alignment_log.jsonl"


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


def _batch_size(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("the batch size must be at least 1")
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
    alignments = commands.add_parser(
        "alignments", help="Layer 3: judge the stored alignment candidates again; the generator aligns only the norms "
                           "newly accepted by `norms`")
    _common_arguments(alignments)
    alignments.add_argument("--batch-size", type=_batch_size, default=20,
                            help="norms per checkpointed batch (default 20)")
    parallel_calls.add_max_in_flight_argument(alignments)
    report = commands.add_parser(
        "report", help="write README.md and changed_verdicts.csv of the new build from its files and its record")
    report.add_argument("--source", type=Path, required=True,
                        help="the published build that was re-judged (read only, never written)")
    report.add_argument("--out-dir", type=Path, required=True, help="the new build folder; its name must be --name")
    report.add_argument("--name", required=True, help="the new build's name, as `norms` and `alignments` took it")
    report.add_argument("--overwrite", action="store_true", help="replace an existing README.md and "
                                                                  "changed_verdicts.csv")
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
        if args.command == "alignments":
            return run_alignments(args, run_argv)
        if args.command == "report":
            return run_report(args)
    except Refusal as refusal:
        print(refusal.message, file=sys.stderr)
        return refusal.code
    raise AssertionError(f"unknown subcommand {args.command!r}")  # argparse refuses it first


def _declared_models() -> list[str]:
    """The model ids config/model_parameters.json declares (exit 4 when it
    cannot be read), so a name that spells another model's build is refused."""
    try:
        return list(load_model_parameters())
    except ConfigurationError as exc:
        raise Refusal(4, f"stopped: {exc}") from None


def _check_out_dir(args: argparse.Namespace, source_dir: Path) -> None:
    """The out-dir is named by --name and lies outside the source folder, which
    it neither equals nor holds (exit 2)."""
    refusal = (f"the out-dir {args.out_dir} must be named {args.name}" if args.out_dir.name != args.name
               else out_dir_refusal(args.out_dir, source_dir))
    if refusal:
        raise refuse(refusal)


def _check_name(args: argparse.Namespace, source: SourceBuild, judge_model: str) -> None:
    """R11: the name follows the rule and reads as one judge's build only, and
    the out-dir is named by it and lies outside the source folder (exit 2)."""
    refusal = name_refusal(args.name, source.name, judge_model, _declared_models())
    if refusal:
        raise refuse(refusal)
    _check_out_dir(args, source.dir)


def _announce_judge(judge: object) -> None:
    """The judge the run pays, named before its first call (final review)."""
    print(f"judging with {getattr(judge, 'model', 'unknown')}, effort {effort_of(judge)}, temperature "
          f"{getattr(judge, 'temperature', 'unknown')}", flush=True)


class Layer3Source(NamedTuple):
    """The source alignments as Layer 3 reads them, checked."""

    payload: dict[str, Any]
    pair: HlegPair
    hleg_nodes: list[dict[str, Any]]
    index: SourceAlignments


def layer3_source(source: SourceBuild, models: dict[str, Any]) -> Layer3Source:
    """The Layer 3 checks that need no new folder, run by `alignments` and,
    before it writes anything, by `norms` (final review: Layer 2 is never paid
    for a source whose Layer 3 would be refused): the source alignments file
    read and refused as alignments_refusal refuses it (R5), the HLEG text and
    derivation record today equal to those the source alignments were made on
    (D-G75 (7): a stored quote is checked and judged against the text it was
    made on), and the file indexed by source_index (its invalid assertions,
    the pairing of its mechanical runs, its targets). Raises Refusal (exit 2)."""
    try:
        payload = json.loads(source.alignments_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise refuse(f"the source alignments file cannot be read ({type(exc).__name__})") from None
    refusal = alignments_refusal(payload, models, source.norms_sha256)
    if refusal:
        raise refuse(refusal)
    try:
        pair = load_pair()
    except HlegSourceError as exc:
        raise refuse(f"the HLEG text cannot be read: {exc}") from None
    build = payload["build"]
    if (pair.text_sha256, pair.record_sha256) != (build.get("hleg_text_sha256"),
                                                    build.get("hleg_derivation_record_sha256")):
        raise refuse(f"the HLEG text and derivation record have sha256 {pair.text_sha256} and {pair.record_sha256} "
                     f"today; the source alignments were made on {build.get('hleg_text_sha256')} and "
                     f"{build.get('hleg_derivation_record_sha256')}")
    hleg_nodes = build_hleg_nodes(pair)
    try:
        index = source_index(payload, [node["id"] for node in hleg_nodes])
    except ValueError as exc:
        raise refuse(str(exc)) from None
    return Layer3Source(payload, pair, hleg_nodes, index)


def _consumed_norms_refusal(out_dir: Path, name: str, out_path: Path) -> str | None:
    """Why a fresh `norms` run (no --resume) may not write out_path, or None:
    the file is the output of a done rejudge_norms execution of the record
    NAME resolves to (final review: a second run would pay the judges again
    and leave the alignments made over the first stale). Reads only."""
    if not out_path.is_file():
        return None
    store = BuildRecordStore(out_dir, create=False)
    try:
        record_id = store.resolve(name)
        record = store.read(record_id) if record_id else None
    except RecordError:
        return None  # the record is refused with its reason when the run chooses it
    if record is None:
        return None
    digest = sha256_of_file(out_path)
    for ex in record.get("executions") or []:
        if ex.get("command") == NORMS_COMMAND and ex.get("status") == "done" and any(
                out.get("output_kind") == "norms" and out.get("sha256") == digest for out in ex.get("outputs") or []):
            return (f"{out_path.name} is the output of the done execution {ex.get('run_id')}; choose another --name "
                    "(a re-run would pay the judges again and leave the alignments stale)")
    return None


def _prices_for(models: dict[str, str]) -> dict[str, dict[str, Any]]:
    """The price table with a row for each model component that will make calls,
    {component: model} (exit 4 otherwise: the cost stop could not be kept)."""
    try:
        prices = load_model_prices()
    except ConfigurationError as exc:
        raise Refusal(4, f"stopped: {exc}") from None
    for component, model in models.items():
        if model not in prices:
            raise Refusal(4, f"stopped: configuration error: config/model_prices.json has no price row for the "
                             f"{component} {model!r}, so the cost stop cannot be kept")
    return prices


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
    # Layer 3's checks of the source too, before Layer 2 is paid
    layer3_source(source, models)
    judge_model = models["judge_model"]
    _check_name(args, source, judge_model)
    prices = _prices_for({"judge": judge_model})

    out_dir = args.out_dir
    out_path = out_dir / f"norms_{args.name}.json"
    if not args.resume:
        refusal = _consumed_norms_refusal(out_dir, args.name, out_path)
        if refusal:
            raise refuse(refusal)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    layer1_path = out_dir / "layer1.json"
    if layer1_path.exists():
        if sha256_of_file(layer1_path) != source.layer1_sha256:
            raise refuse(f"{layer1_path} is not the source's layer1.json (another sha256)")
    else:
        shutil.copyfile(source.layer1_path, layer1_path)
    log_path = out_dir / "logs" / EXTRACTION_LOG
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")
    store = BuildRecordStore(out_dir)
    dump = json.loads(layer1_path.read_text(encoding="utf-8"))
    choice = choose_output_record(store, out_dir, out_path, alias=args.name,
                                  base_build_id=dump.get("build", {}).get("build_id"),
                                  layer1_digest=source.layer1_sha256)

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
        _announce_judge(judge)
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


def _norms_output_refusal(out_dir: Path, name: str, norms_path: Path, source_record_id: str,
                          public_models: dict[str, Any]) -> str | None:
    """Why NEW/norms_NAME.json is not the output of a done rejudge_norms
    execution of the record NAME resolves to, made from the source record
    --source names by the judge the environment names now (its model,
    effort, temperature and parameters digest: Layer 3 is judged by Layer 2's
    judge, final review), or None. Reads only: the store is opened without
    creating its folder."""
    run_first = "run `norms` with the same --out-dir and --name first"
    if not norms_path.is_file():
        return f"{norms_path} is missing; {run_first}"
    store = BuildRecordStore(out_dir, create=False)
    try:
        record_id = store.resolve(name)
        record = store.read(record_id) if record_id else None
    except RecordError as exc:
        return f"the build record {name} cannot be read: {exc}"
    if record is None:
        return f"there is no build record {name} in {out_dir}; {run_first}"
    digest = sha256_of_file(norms_path)
    for ex in record.get("executions") or []:
        if ex.get("command") == NORMS_COMMAND and ex.get("status") == "done" and any(
                out.get("output_kind") == "norms" and out.get("sha256") == digest for out in ex.get("outputs") or []):
            made_from = (ex.get("config") or {}).get("source_record_id")
            if made_from != source_record_id:
                return (f"{norms_path.name} was re-judged from the source record {made_from}, not from "
                        f"{source_record_id}, the record of --source")
            theirs = ex.get("models") or {}
            differing = [key for key in JUDGE_MODEL_KEYS if theirs.get(key) != public_models.get(key)]
            if differing:
                return (f"the judge in the environment differs from the one that re-judged {norms_path.name} "
                        f"(execution {ex.get('run_id')}) in "
                        + ", ".join(f"{key} ({public_models.get(key)!r}, the norms run {theirs.get(key)!r})"
                                    for key in differing)
                        + "; Layer 3 is judged by the judge of Layer 2")
            return None
    return (f"{norms_path.name} (sha256 {digest}) is not the output of a done {NORMS_COMMAND} execution of the "
            f"record {name}; {run_first}")


def run_alignments(args: argparse.Namespace, run_argv: list[str]) -> int:
    """The Layer 3 flow: every refusal (a Refusal) before any record is written,
    then one execution re-judging the batches not yet in the checkpoint (R9)."""
    try:
        source = read_source(args.source)
        source_norms_payload = json.loads(source.norms_path.read_text(encoding="utf-8"))
    except SourceError as exc:
        raise refuse(str(exc)) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise refuse(f"the source norms file cannot be read ({type(exc).__name__})") from None
    source_norms = source_norms_payload.get("norms") or []
    try:
        cfg = load_model_config()
    except ModelConfigError as exc:
        raise Refusal(4, f"stopped: {exc}") from None
    models = cfg.as_public_dict()
    refusal = materialised_refusal(source_norms_payload)
    if refusal:
        raise refuse(refusal)
    source_payload, pair, hleg_nodes, source_alignments = layer3_source(source, models)
    judge_model, generator_model = models["judge_model"], models["generator_model"]
    _check_name(args, source, judge_model)
    prices = _prices_for({"judge": judge_model, "generator": generator_model})

    out_dir = args.out_dir
    norms_path = out_dir / f"norms_{args.name}.json"
    refusal = _norms_output_refusal(out_dir, args.name, norms_path, source.record_id, models)
    if refusal:
        raise refuse(refusal)
    source_build = source_payload["build"]
    layer1_path = out_dir / "layer1.json"
    if not layer1_path.is_file() or sha256_of_file(layer1_path) != source.layer1_sha256:
        raise refuse(f"{layer1_path} is not the source's layer1.json")

    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"alignments_{args.name}.json"
    log_path = out_dir / "logs" / ALIGNMENT_LOG
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")
    store = BuildRecordStore(out_dir)
    dump = json.loads(layer1_path.read_text(encoding="utf-8"))
    choice = choose_output_record(store, out_dir, out_path, alias=args.name,
                                  base_build_id=dump.get("build", {}).get("build_id"),
                                  layer1_digest=source.layer1_sha256)

    norms_payload = json.loads(norms_path.read_text(encoding="utf-8"))
    norms: list[dict[str, Any]] = norms_payload.get("norms") or []
    _attach_source_text(norms, dump)
    prompt_version = source_build["alignment_prompt_version"]
    # R6: the judge runs keep the source's base build id
    build_id = source_build.get("build_id", "build-unknown")
    description = f"generator output of {source.name}, judged by {judge_model}"
    norms_digest = sha256_of_file(norms_path)
    inputs = [
        {"input_kind": "norms", "file": relative_to_dump_dir(norms_path, out_dir), "sha256": norms_digest},
        {"input_kind": "source_alignments",
         "file": os.path.relpath(source.alignments_path.resolve(), out_dir.resolve()),
         "sha256": source.alignments_sha256},
        {"input_kind": "layer1_dump", "file": relative_to_dump_dir(layer1_path, out_dir),
         "sha256": source.layer1_sha256},
        {"input_kind": "hleg_text", "file": TEXT_FILE, "sha256": pair.text_sha256},
        {"input_kind": "hleg_derivation_record", "file": RECORD_FILE, "sha256": pair.record_sha256},
    ]
    config = {"prompt_version": prompt_version, "batch_size": args.batch_size, "max_in_flight": args.max_in_flight,
              "cost_stop_usd": args.cost_stop, "source_build": source.name, "source_record_id": source.record_id,
              "source_chain_id": source.chain_id, "judged_by": judge_model, "description": description}
    prompts = {"generator": prompt_sha256(load_prompt(ALIGN_PROMPT_KIND, prompt_version)),
               "judge": prompt_sha256(load_prompt(ALIGNMENT_JUDGE_PROMPT_KIND, prompt_version))}
    plan = plan_resume(checkpoint_path, "batch", ALIGNMENTS_RESULT_KEYS, resume=args.resume, store=store,
                       choice=choice, config=config, inputs=inputs, models=models, prompts=prompts)

    # spec F D-F30: a terminal run with a checkpoint waits out an overload; the
    # generator is called for the newly accepted norms only (R9)
    generator = OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)
    judge = AnthropicJudge(cfg, retry_policy=TERMINAL_POLICY)
    record_id, message = create_chosen_record(store, choice)
    if message:
        print(message)
    batches = [(f"batch:{i}:{norms[i]['norm_id']}", norms[i:i + args.batch_size])
               for i in range(0, len(norms), args.batch_size)]
    run_id = store.start_execution(
        record_id, command=ALIGNMENTS_COMMAND, covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"],
        argv=run_argv, inputs=inputs, config=config, expected_total=len(batches), work_unit="batches",
        checkpoint_file=relative_to_dump_dir(checkpoint_path, out_dir),
        resumes_run_id=plan.resumes_run_id, inherited_keys=plan.inherited_keys, inherited_from=plan.inherited_from,
        models=models, prompt_sha256=prompts, sampling=declared_sampling(generator, judge),
    )
    execution = Execution(
        store=store, record_id=record_id, run_id=run_id, checkpoint_path=checkpoint_path, run_argv=run_argv,
        expected_total=len(batches), inherited=len(plan.inherited_keys), work_unit="batches",
        usage=lambda: {"generator": usage_of(generator), "judge": usage_of(judge)},
        sampling=lambda: declared_sampling(generator, judge),
    )
    source_verdicts = {norm["norm_id"]: norm.get("judge_verdict") for norm in source_norms}
    requirement_ids = [node["id"] for node in hleg_nodes]

    def spent_so_far() -> float:
        return (record_spend(store.read(record_id), prices, excluding=run_id)
                + usage_cost(usage_of(generator), prices[generator_model])
                + usage_cost(usage_of(judge), prices[judge_model]))

    def rejudge_batches() -> dict[str, Any]:
        _announce_judge(judge)
        print(f"calls in flight: at most {args.max_in_flight} (--max-in-flight)", flush=True)
        partials: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
        with Heartbeat(store, record_id, run_id), checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for batch_key, chunk in batches:
                if batch_key in plan.entries_by_key:
                    continue
                # R10: the record's other rejudge executions plus this run so far
                so_far = spent_so_far()
                if so_far >= args.cost_stop:
                    raise CostStop(so_far, args.cost_stop)
                partial = rejudge_batch(chunk, source_verdicts, source_alignments, hleg_nodes, generator, judge,
                                        prompt_version=prompt_version, log_path=log_path, build_id=build_id,
                                        max_in_flight=args.max_in_flight)
                ckpt.write(json.dumps({"run_id": run_id, "batch": batch_key, "result": partial}) + "\n")
                ckpt.flush()
                partials.append(partial)
                execution.completed.append(batch_key)
                # the usage so far rides on the beat: a SIGKILL loses at most the batch in flight
                store.heartbeat(record_id, run_id, usage=execution.usage())
                stats = partial["stats"]
                print(f"  {batch_key}: {len(partial['assertions'])} assertions, verdicts {stats['verdicts']}, "
                      f"{len(stats['newly_aligned_norms'])} newly aligned, {len(stats['dropped_assertions'])} "
                      "dropped", flush=True)

        result = merge_batches(partials, source_alignments, requirement_ids)
        stats = result["stats"]
        sampling = declared_sampling(generator, judge)
        source_usage = source_build.get("alignment_usage") or {}
        rejudge_block = {
            "description": description, "source_build": source.name,
            "source_alignments_sha256": source.alignments_sha256, "source_aligned_at": source_build.get("aligned_at"),
            "carried_generator_usage": source_usage.get("generator"), "source_judge_usage": source_usage.get("judge"),
        }
        payload = {
            "build": rejudged_alignment_build(
                norms_payload.get("build") or {}, source_build, public_models=models,
                judge_sampling=sampling["judge"], judge_effort=effort_of(judge), usage=execution.usage(),
                norms_sha256=norms_digest, hleg_text_sha256=pair.text_sha256,
                hleg_derivation_record_sha256=pair.record_sha256, aligned_at=_now_iso(), rejudge=rejudge_block),
            **result,
        }
        tmp_path = out_path.with_suffix(".writing.json")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.replace(out_path)
        newly, dropped = stats.get("newly_aligned_norms") or [], stats.get("dropped_assertions") or []
        store.finish_execution(
            record_id, run_id, status="done",
            outputs=[{"output_kind": "alignments", "file": relative_to_dump_dir(out_path, out_dir),
                      "sha256": sha256_of_file(out_path)}],
            # A count the stats do not hold is null, never zero (D-G25).
            counts={"norms_total": stats.get("norms_total"),
                    "norms_skipped_not_accepted": stats.get("norms_skipped_not_accepted"),
                    "zero_alignment_norms": stats.get("zero_alignment_norms"),
                    "candidates": stats.get("candidates"), "verdicts": stats.get("verdicts"),
                    "mechanical_rejects_count": (len(stats["mechanical_rejects"])
                                                 if isinstance(stats.get("mechanical_rejects"), list) else None),
                    "newly_aligned_norms": {"count": len(newly), "norm_ids": newly},
                    "dropped_assertions": {"count": len(dropped), "assertion_ids": dropped},
                    "carried_candidates": stats.get("carried_candidates"),
                    "source_verdicts": verdict_counts(source_payload.get("assertions") or [])},
            usage=execution.usage(), sampling=sampling, completed_keys=execution.completed,
            work_failures={"nodes_failed": 0, "norms_failed": len(stats.get("norms_failed") or [])},
        )
        return stats

    code, stats = execution.run(rejudge_batches)
    if code:
        return code
    checkpoint_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(f"norms: {stats.get('norms_total', 0)} total, {stats.get('norms_skipped_not_accepted', 0)} skipped (not "
          f"accepted), {stats.get('zero_alignment_norms', 0)} with zero alignments")
    print(f"candidates: {stats.get('candidates', 0)} ({stats.get('carried_candidates', 0)} stored ones judged again), "
          f"verdicts: {stats.get('verdicts', {})} (the source's "
          f"{verdict_counts(source_payload.get('assertions') or [])})")
    print(f"newly aligned norms: {len(stats.get('newly_aligned_norms') or [])}, assertions dropped: "
          f"{len(stats.get('dropped_assertions') or [])}")
    this_run = (usage_cost(usage_of(generator), prices[generator_model])
                + usage_cost(usage_of(judge), prices[judge_model]))
    print(f"spend: {usd(this_run)} USD at list price in this run, {usd(record_spend(store.read(record_id), prices))} "
          "USD over the record's rejudge executions")
    return 0


def run_report(args: argparse.Namespace) -> int:
    """Write the new build's README.md and changed_verdicts.csv (refusals as a Refusal)."""
    _check_out_dir(args, args.source)
    readme, csv_path = write_report(args.source, args.out_dir, args.name, overwrite=args.overwrite)
    print(f"wrote {readme}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

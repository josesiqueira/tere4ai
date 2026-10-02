"""Checkpointed live ablation runner (M4, user-triggered spend).

@implements: DEC-11, DEC-17
@grounded_by: REF-15, REF-16, REF-17

Runs the five-condition ablation ladder over the gold seed plus the frozen
REF-15 benchmark sample, in checkpointed (strategy, item-batch) units, so a
crash never loses more than one batch (the lesson of the lost extraction run).
Resume by re-running: completed units are skipped; the sidecar
<checkpoint>.record names the record a resume continues (DEC-17), and a
resume under another model declaration is refused (spec F D-F29). After the
sweep, computes the Section 12 metrics per strategy and writes the summary
to --summary, by default eval/results/runs/<record id>/ablation_summary.json.

Gates: requires TERE4AI_LIVE_TESTS=1 and the model config of record
(eval/config_evaluated.yaml); refuses to start otherwise. Cost: roughly
(items x strategies) generator calls plus items judge calls for graph_full.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval import harness, metrics, strategies  # noqa: E402
from tere4ai.eval.evaluation_record import (  # noqa: E402
    RECORD_FILE_STEM,
    EvaluationRecordError,
    EvaluationRecordStore,
    code_version,
    file_ref,
    observe_publication,
    served_input_paths,
)
from tere4ai.eval.metrics import METRICS_VERSION  # noqa: E402
from tere4ai.eval.present_evaluation import JULY_CHECKPOINT_DIGESTS, JULY_DIGESTS  # noqa: E402
from tere4ai.extract_norms.model_clients import (  # noqa: E402
    TERMINAL_POLICY,
    AnthropicJudge,
    OpenAIGenerator,
    ProviderRefused,
    ProviderUnavailable,
    declared_sampling,
)
from tere4ai.graph_store.build_chain import sha256_of_file  # noqa: E402
from tere4ai.graph_store.present import exception_reason  # noqa: E402
from tere4ai.judge.config import ConfigurationError, load_model_config  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
# B81 item 20: an omitted path lands in a fresh directory named after the
# run's record, so a default run never resumes, never appends to and never
# rewrites another run's files (the July measurement included); a resume
# names its checkpoint explicitly.
RUNS_DIRNAME = "runs"
CHECKPOINT_NAME = "ablation_checkpoint.jsonl"
SUMMARY_NAME = "ablation_summary.json"
BATCH_SIZE = 10
# the pinned July summaries and checkpoints: never appended to, never rewritten
JULY_PROTECTED = frozenset(JULY_DIGESTS.values()) | frozenset(JULY_CHECKPOINT_DIGESTS.values())


def _july_refusal(path: Path) -> str | None:
    """The refusal sentence when path holds the bytes of a July file, else None."""
    if path.is_file() and sha256_of_file(path) in JULY_PROTECTED:
        return (f"refusing to write {path}: its bytes are the July 2026 measurement; "
                "pass --summary or --checkpoint with another path")
    return None


def _completed_items(unit_results: list[dict], items: list[dict],
                     strategy_names: list[str]) -> tuple[list[str], list[str]]:
    """(completed, errored) item ids over the checkpointed units: an item is
    completed when every strategy holds a result for it without an error."""
    merged: dict[str, dict] = {}
    for entry in unit_results:
        merged.setdefault(entry["strategy"], {}).update(entry["results"])
    errored = sorted({item_id for results in merged.values() for item_id, r in results.items()
                      if isinstance(r, dict) and r.get("error")})
    completed = [i["id"] for i in items if i["id"] not in set(errored)
                 and all(i["id"] in merged.get(name, {}) for name in strategy_names)]
    return completed, errored


def _resumed_only_notes(built: dict, ran: set[str], resumes: str | None, resumed_units: bool) -> list[str]:
    """A note per strategy this invocation built but ran no unit of (B98 seat
    B P3-5): its models here are this invocation's clients, declared from
    construction since B99 (spec F D-F29), beside metrics another invocation
    produced, so the note names the record the resume continues.
    Only on an actual resume (final re-review B98, New Breakage 3): a fresh
    run over an empty item list also runs no unit of any built strategy, but
    it resumed nothing, so it earns no note."""
    if not resumed_units:
        return []
    where = f"record {resumes}" if resumes is not None else "no record (the checkpoint no record names)"
    return [f"{name}: every unit resumed, none run by this invocation; the models that produced its "
            f"results are named in {where}" for name in built if name not in ran]


def _own_usage(generator, judge) -> dict | None:
    """This invocation's own spend (spec G D-G20: usage of this attempt): the
    clients live for one invocation, so their records are exactly it."""
    if generator is None and judge is None:
        return None
    return {"generator": dict(generator.usage) if generator is not None else None,
            "judge": dict(judge.usage) if judge is not None else None}


def sidecar_path(checkpoint_path: Path) -> Path:
    """The checkpoint's persisted identity (G2): same directory, name plus `.record`."""
    return checkpoint_path.with_name(checkpoint_path.name + ".record")


def _resume_line(argv: list[str], checkpoint_path: Path) -> str:
    """The command that continues a stopped run (spec F D-F30): the same
    arguments, naming the checkpoint when the run used the default path."""
    args = list(argv)
    if not any(a == "--checkpoint" or a.startswith("--checkpoint=") for a in args):
        args += ["--checkpoint", str(checkpoint_path)]
    return f"TERE4AI_LIVE_TESTS=1 .venv/bin/python scripts/run_ablations.py {shlex.join(args)}"


def write_sidecar(checkpoint_path: Path, record_id: str) -> None:
    """Name the record that owns the checkpoint, atomically (temp file plus os.replace)."""
    path = sidecar_path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"record_id": record_id, "checkpoint_file": checkpoint_path.name}) + "\n"
    fd, tmp = tempfile.mkstemp(prefix="tmp", suffix=".record", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def resolve_resume(checkpoint_path: Path, dump_dir: Path) -> tuple[str | None, str | None]:
    """The record a resume of checkpoint_path continues, as (record id, None);
    (None, None) when no sidecar names one; (None, refusal) when the sidecar
    names a record the store cannot confirm. The sidecar is never trusted
    without the store lookup, and the lookup is read-only (G2)."""
    sidecar = sidecar_path(checkpoint_path)
    if not sidecar.exists():
        return None, None
    # every sidecar refusal ends with the way out (G2b): a broken chain is not
    # "no record names it", but removing the sidecar makes it exactly that
    fresh = (f"pass --checkpoint with a fresh path, or remove the sidecar {sidecar.name} to resume it as a "
             "checkpoint no record names (--resume-unrecorded)")
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        rid = data["record_id"]
        named = data["checkpoint_file"]
        if not isinstance(rid, str) or not RECORD_FILE_STEM.match(rid):
            raise ValueError(f"record_id {rid!r} is not a record id")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reason = exception_reason(exc)
        return None, (f"refusing to resume {checkpoint_path}: its sidecar {sidecar.name} is not readable "
                      f"({reason}); {fresh}")
    if named != checkpoint_path.name:
        return None, (f"refusing to resume {checkpoint_path}: its sidecar {sidecar.name} names the checkpoint "
                      f"file {named}; {fresh}")
    store = EvaluationRecordStore(dump_dir, create=False)
    head = f"refusing to resume {checkpoint_path}: its sidecar names evaluation record {rid}"
    if not (store.dir / f"{rid}.json").is_file():
        return None, f"{head}, which this store does not hold; {fresh}"
    try:
        record = store.read(rid)
    except EvaluationRecordError as exc:
        return None, f"{head}, which this store cannot read ({exc}); {fresh}"
    recorded = (record.get("config") or {}).get("checkpoint_file")
    if recorded != checkpoint_path.name:
        which = f"the checkpoint file {recorded}" if recorded else "no checkpoint file"
        return None, f"{head}, which names {which}; {fresh}"
    return rid, None


def _declaration_refusal(checkpoint_path: Path, config: dict, unit_results: list[dict],
                         resumes: str | None, dump_dir: Path) -> str | None:
    """The refusal sentence when a resume would continue under another
    declaration (spec F D-F29, ruling P6), else None: the resumed record's
    models against the loaded ones, then every checkpointed unit's digest
    (the only witness of a checkpoint no record names): under a declared
    configuration a unit without one differs too, otherwise only a unit
    that names one is compared."""
    way_out = ("restore the row in config/model_parameters.json to resume it, or pass --checkpoint with a "
               "fresh path to start again")
    head = f"refusing to resume {checkpoint_path}"
    if resumes is not None:
        recorded = EvaluationRecordStore(dump_dir, create=False).read(resumes).get("models") or {}
        differing = sorted(k for k in set(recorded) | set(config) if recorded.get(k) != config.get(k))
        if differing:
            return f"{head}: evaluation record {resumes} used different models: {', '.join(differing)}; {way_out}"
    # ruling P6: under a declared configuration a unit without the digest
    # (written before B99) differs too
    ours = config.get("model_parameters_sha256")
    if any(("model_parameters_sha256" in e or ours is not None) and e.get("model_parameters_sha256") != ours
           for e in unit_results):
        return f"{head}: a checkpointed unit was run under different models: model_parameters_sha256; {way_out}"
    return None


def load_items(benchmark_path=None, features_path=None) -> list[dict]:
    gold = harness.load_gold_items()
    bench = harness.load_benchmark_items(benchmark_path or harness.BENCHMARK_SAMPLE_PATH)
    # enrich free-text scenarios with cached elicited features when present
    # (scripts/elicit_benchmark_features.py); provenance kept per item
    features_path = features_path or ROOT / "eval" / "gold" / "benchmark_features.json"
    if features_path.exists():
        cache = json.loads(features_path.read_text(encoding="utf-8"))
        by_item = cache.get("features_by_item", {})
        enriched = 0
        for item in bench:
            feats = by_item.get(item["id"])
            if feats and not item.get("system_features"):
                item["system_features"] = feats
                item["features_provenance"] = "llm_elicited"
                enriched += 1
        print(f"elicited features attached to {enriched} benchmark item(s)")
    items = list(gold) + list(bench)
    for item in items:
        assert item.get("id"), "every item needs an id"
    return items


def elicitor_prompt(features_path: Path) -> dict[str, Any]:
    """The elicitor's prompt the facts file names, for the record's
    prompt_versions (B10): its version and template hash from the file's
    "prompt" record (scripts/elicit_benchmark_features.py); a file written
    before B10 names only prompt_version, so its template hash is None."""
    cache = json.loads(features_path.read_text(encoding="utf-8"))
    prompt = cache.get("prompt")
    if isinstance(prompt, dict):
        return {"version": prompt.get("version"), "template_sha256": prompt.get("template_sha256")}
    return {"version": cache.get("prompt_version"), "template_sha256": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", type=Path, default=None,
                        help="benchmark payload (default: the frozen sample)")
    parser.add_argument("--features", type=Path, default=None,
                        help="elicited-features cache (default: run-2 file)")
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help="checkpoint to write or resume (default: a fresh "
                             "eval/results/runs/<record id>/ablation_checkpoint.jsonl)")
    parser.add_argument("--summary", type=Path, default=None,
                        help="summary to write (default: eval/results/runs/<record id>/ablation_summary.json)")
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps",
                        help="where layer1.json, norms_core.json and evaluation_records/ live")
    parser.add_argument("--no-record", action="store_true", help="do not write an evaluation record (D-G33)")
    parser.add_argument("--repeat-of", default=None, help="record id of the run this run repeats")
    parser.add_argument("--resume-unrecorded", action="store_true",
                        help="resume a checkpoint no evaluation record names (the note is recorded)")
    args = parser.parse_args(argv)
    if args.repeat_of is not None and args.no_record:
        print("--repeat-of: a --no-record run records no relation; drop one of the two flags")
        return 2
    if args.no_record and (args.checkpoint is None or args.summary is None):
        print("refusing to run: a --no-record run has no record id to name its directory; "
              "pass --checkpoint and --summary")
        return 2
    checkpoint_path, summary_path = args.checkpoint, args.summary
    # the July files are protected whether or not the run records (F1)
    for target in (p for p in (checkpoint_path, summary_path) if p is not None):
        refusal = _july_refusal(target)
        if refusal is not None:
            print(refusal)
            return 2

    paths = served_input_paths(args.dump_dir)
    for role in ("layer1_dump", "norms"):
        if role not in paths:
            print(f"refusing to run: the active publication names no {role} file")
            return 2
    dump = json.loads(paths["layer1_dump"].read_text())
    norms_payload = json.loads(paths["norms"].read_text())
    items = load_items(args.benchmark, args.features)
    print(f"items: {len(items)} | strategies: {strategies.STRATEGY_NAMES}")

    # live gates up front, zero cost on refusal
    harness._require_live_gate()
    config = harness.guard_live_config().as_public_dict()
    print(f"config of record OK: {config}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    unit_results: list[dict] = []
    if checkpoint_path is not None and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            done.add(entry["unit"])
            unit_results.append(entry)
        print(f"resume: {len(done)} unit(s) already checkpointed")

    notes: list[str] = []
    resumes = None
    if done:
        # the sidecar names the record that owns the checkpoint (G2); a
        # read-only lookup, so a --no-record run is refused the same way
        resumes, refusal = resolve_resume(checkpoint_path, args.dump_dir)
        if refusal is not None:
            print(refusal)
            return 2
        if resumes is None:
            if not args.resume_unrecorded:
                print(f"refusing to resume {checkpoint_path}: no evaluation record names it; pass "
                      "--resume-unrecorded to resume it anyway (the note is recorded) or --checkpoint "
                      "with a fresh path")
                return 2
            notes.append("resumed from a checkpoint no record names")
        # spec F D-F29 (final review I1): a resume never continues under
        # another declaration, in the sentence shape of prepare_resume
        # (ruling P6); a record made before the digest existed differs too
        refusal = _declaration_refusal(checkpoint_path, config, unit_results, resumes, args.dump_dir)
        if refusal is not None:
            print(refusal)
            return 2

    store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
    record_id = None
    elicitor_versions: dict[str, Any] = {}
    if store is not None:
        if args.repeat_of is not None:
            try:
                store.read(args.repeat_of)
            except Exception as exc:  # noqa: BLE001 - the reason is printed, the run refused
                print(f"--repeat-of: {exc}")
                return 2
        features_path = args.features or (ROOT / "eval" / "gold" / "benchmark_features.json")
        inputs = [
            file_ref("layer1_dump", paths["layer1_dump"]),
            file_ref("norms", paths["norms"]),
            file_ref("benchmark", args.benchmark or harness.BENCHMARK_SAMPLE_PATH),
            file_ref("gold_seed", harness.GOLD_SEED_PATH),
        ]
        # the cache is optional to load_items: recorded only when it was read (G7)
        if features_path.is_file():
            inputs.append(file_ref("features", features_path))
            # B10: the record names the elicitor's prompt beside the strategies' models
            elicitor_versions = {"elicit_features": elicitor_prompt(features_path)}
        else:
            notes.append("no elicited-features cache was read")
        if done:
            inputs.append(file_ref("checkpoint_resumed", checkpoint_path))
        publication, publication_reason = observe_publication(args.dump_dir)
        base_build_id = (dump.get("build") or {}).get("build_id")
        record_id = store.begin(
            kind="run", step="E6", command="run_ablations", argv=list(argv) if argv is not None else sys.argv[1:],
            inputs=inputs,
            build={"base_build_id": str(base_build_id) if base_build_id is not None else None,
                   "publication": publication, "publication_reason": publication_reason},
            models=config, prompt_versions=elicitor_versions or None, config={
                "strategies": list(strategies.STRATEGY_NAMES), "batch_size": BATCH_SIZE,
                "metrics_version": METRICS_VERSION, "code_version": code_version(ROOT), "mode": "live"},
            item_selection=[i["id"] for i in items], intended_items=[i["id"] for i in items],
            relations={"repeat_of": args.repeat_of, "resumes_record_id": resumes},
            counts={"units_resumed": len(done)},
            checkpoint_file=(checkpoint_path.name if checkpoint_path is not None else CHECKPOINT_NAME),
        )
        run_dir = RESULTS_DIR / RUNS_DIRNAME / record_id
        checkpoint_path = checkpoint_path or run_dir / CHECKPOINT_NAME
        summary_path = summary_path or run_dir / SUMMARY_NAME

    generator = judge = None
    units_run = 0
    # the strategies as built, so both finishes read their models after the
    # items ran; since B99 the clients report their declared values from
    # construction (spec F D-F29)
    built: dict[str, Any] = {}
    ran: set[str] = set()  # the strategies with at least one unit run by this invocation
    try:
        if store is not None and record_id is not None:
            # the newest record owns the checkpoint from now on (G2)
            write_sidecar(checkpoint_path, record_id)
        cfg = load_model_config()
        # spec F D-F30: a terminal run with a checkpoint waits out an overload
        generator = OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)
        judge = AnthropicJudge(cfg, retry_policy=TERMINAL_POLICY)

        batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
        with checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for strategy_name in strategies.STRATEGY_NAMES:
                fn = strategies.build_strategy(
                    strategy_name,
                    generator=generator,
                    judge=judge,
                    dump=dump,
                    norms_payload=norms_payload,
                )
                built[strategy_name] = fn
                for bi, batch in enumerate(batches):
                    unit = f"{strategy_name}:batch{bi}"
                    if unit in done:
                        continue
                    ran.add(strategy_name)
                    usage_before = {
                        "generator": dict(generator.usage),
                        "judge": dict(judge.usage),
                    }
                    per_item = {}
                    for item in batch:
                        try:
                            per_item[item["id"]] = fn(item)
                        except ProviderRefused as exc:
                            # spec F D-F30, B101 ruling S5: the reason names the item, which is
                            # fixed before the resume, never skipped
                            raise ProviderRefused(f"{exc.cause} (item {item['id']})") from exc
                        except (ProviderUnavailable, ConfigurationError):
                            raise  # spec F D-F29, D-F30: a stop of the run, never an item's error
                        except Exception as exc:  # record, never abort the sweep
                            per_item[item["id"]] = {
                                "error": exception_reason(exc),
                                "answer_text": "",
                                "citations": [],
                            }
                    # provider-reported token deltas for exactly this unit, so the
                    # checkpoint carries true spend across resumes (Section 13)
                    clients = {"generator": generator, "judge": judge}
                    usage = {
                        role: {
                            k: clients[role].usage[k] - before[k] for k in before
                        }
                        for role, before in usage_before.items()
                    }
                    entry = {
                        "unit": unit,
                        "strategy": strategy_name,
                        "results": per_item,
                        "usage": usage,
                    }
                    # spec F D-F29: the unit names the declaration it ran under,
                    # so a resume no record names can still refuse another one
                    if "model_parameters_sha256" in config:
                        entry["model_parameters_sha256"] = config["model_parameters_sha256"]
                    ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    ckpt.flush()
                    units_run += 1
                    unit_results.append(entry)
                    errors = sum(1 for r in per_item.values() if "error" in r)
                    print(f"  {unit}: {len(per_item)} items, {errors} errors", flush=True)

        # merge per strategy
        merged: dict[str, dict] = {}
        for entry in unit_results:
            merged.setdefault(entry["strategy"], {}).update(entry["results"])

        # aggregate provider-reported usage over the checkpointed units; units
        # written before usage tracking existed carry no usage block, so their
        # count is surfaced instead of silently under-reporting spend
        usage_total: dict[str, dict[str, int]] = {}
        units_without_usage = 0
        # B91: a unit written before the two completeness counts existed leaves
        # its role's aggregate without them (completeness not recorded), never
        # a partial count that would read as complete
        roles_missing_counts: set[str] = set()
        # final review A3: likewise a unit written before requests_refused
        # existed leaves only that count unknown for its role
        roles_missing_refused: set[str] = set()
        # spec F D-F32: likewise a unit written before
        # requests_rejected_before_processing existed leaves only that count
        # unknown for its role
        roles_missing_rejected: set[str] = set()
        for entry in unit_results:
            if "usage" not in entry:
                units_without_usage += 1
                continue
            for role, counts in entry["usage"].items():
                bucket = usage_total.setdefault(role, {})
                for k, v in counts.items():
                    bucket[k] = bucket.get(k, 0) + v
                if not {"requests_sent", "replies_with_usage"} <= set(counts):
                    roles_missing_counts.add(role)
                if "requests_refused" not in counts:
                    roles_missing_refused.add(role)
                if "requests_rejected_before_processing" not in counts:
                    roles_missing_rejected.add(role)
        # a unit with no usage block at all (units_without_usage) makes every
        # role's total incomplete: the counts go for every role (review fix C4)
        if units_without_usage:
            roles_missing_counts.update(usage_total)
            roles_missing_refused.update(usage_total)
            roles_missing_rejected.update(usage_total)
        for role in roles_missing_counts:
            usage_total[role].pop("requests_sent", None)
            usage_total[role].pop("replies_with_usage", None)
        for role in roles_missing_refused | roles_missing_counts:
            usage_total[role].pop("requests_refused", None)
        for role in roles_missing_rejected | roles_missing_refused | roles_missing_counts:
            usage_total[role].pop("requests_rejected_before_processing", None)

        # metrics per strategy against gold labels where present
        gold_items = [i for i in items if i.get("gold") or i.get("gold_citations")]
        valid_node_ids = {n["id"] for n in dump["nodes"]}
        summary: dict[str, dict] = {
            "config": config,
            "items_total": len(items),
            "usage_provider_reported": {
                "by_role": usage_total,
                "units_without_usage": units_without_usage,
                "note": (
                    "token counts as reported by the providers per API response, "
                    "summed over checkpoint units; units checkpointed by runner "
                    "versions without usage tracking contribute nothing here; "
                    "the evaluation record's usage is this invocation's own spend; "
                    "this total covers every checkpointed unit"
                ),
            },
            "strategies": {},
        }
        import re

        def article_prefix(cid: str) -> str:
            m = re.match(r"(eu-ai-act:article-\d+)", cid)
            return m.group(1) if m else cid

        # seed items are id-prefixed gold:, benchmark items bench: (loader convention)
        seed_cls = [
            i for i in gold_items
            if i["id"].startswith("gold:") and i.get("kind") == "classification"
        ]
        bench_items = [i for i in items if i["id"].startswith("bench:")]
        bench_cls = [i for i in bench_items if i.get("kind") == "classification"]
        for strategy_name, results in merged.items():
            gold_ok = sum(
                1
                for gi in seed_cls
                if results.get(gi["id"], {}).get("risk_category")
                == gi["gold"].get("risk_category")
            )
            bench_ok = sum(
                1
                for bi in bench_cls
                if results.get(bi["id"], {}).get("risk_category")
                == bi["gold"].get("risk_category")
            )
            # benchmark citation completeness at the benchmark's own granularity
            # (article level; predicted paragraph/point ids credit their article)
            found = required = 0
            for bi in bench_items:
                gold_cites = set(bi.get("gold_citations") or [])
                if not gold_cites:
                    continue
                predicted = {
                    article_prefix(c)
                    for c in (results.get(bi["id"], {}).get("citations") or [])
                }
                required += len(gold_cites)
                found += len(gold_cites & predicted)
            s = {
                "risk_accuracy_overall": metrics.risk_classification_accuracy(
                    results, gold_items
                ),
                "gold_structured_classification": {
                    "correct": gold_ok,
                    "total": len(seed_cls),
                    "note": "seed items with structured system_features; the deterministic path",
                },
                "benchmark_freetext_classification": {
                    "correct": bench_ok,
                    "total": len(bench_cls),
                    "abstained": sum(
                        1
                        for bi in bench_cls
                        if results.get(bi["id"], {}).get("risk_category")
                        in (None, "uncertain")
                    ),
                    "note": (
                        "benchmark scenarios are free text; where an elicited-features "
                        "cache is attached (DEC-13, provenance llm_elicited) the "
                        "deterministic classifier decides from those facts, otherwise "
                        "it abstains rather than guesses. Human-verified features per "
                        "eval/gold/ANNOTATION_PROTOCOL.md supersede elicited ones."
                    ),
                },
                "benchmark_citation_completeness_article_level": {
                    "found": found,
                    "required": required,
                    "completeness": (found / required) if required else None,
                    "note": (
                        "benchmark gold cites at article granularity; predicted "
                        "paragraph/point ids credit their parent article here"
                    ),
                },
                "citations_emitted_total": sum(
                    len(r.get("citations") or []) for r in results.values()
                ),
                "citation_completeness": metrics.citation_completeness(results, gold_items),
                "hallucinated_citation_rate": metrics.hallucinated_citation_rate(
                    results, valid_node_ids
                ),
                "errors": sum(1 for r in results.values() if "error" in r),
            }
            if s["citations_emitted_total"] == 0:
                s["hallucination_note"] = (
                    "zero checkable citations emitted; a 0.0 hallucination rate here "
                    "is vacuous, not a quality signal"
                )
            summary["strategies"][strategy_name] = s

        summary_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = summary_path.with_suffix(".writing.json")
        tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(summary_path)

        if store is not None and record_id is not None:
            completed, errored = _completed_items(unit_results, items, list(strategies.STRATEGY_NAMES))
            outputs = [store.keep_output(record_id, "summary", summary_path),
                       store.keep_output(record_id, "checkpoint", checkpoint_path)]
            models_now = harness.strategy_models(built, list(built))
            store.finish(
                record_id, status="completed" if len(completed) == len(items) else "partial",
                completed_items=completed, outputs=outputs, usage=_own_usage(generator, judge),
                prompt_versions={**models_now, **elicitor_versions},
                prompt_sha256=harness.runtime_judge_prompt_sha256(models_now),
                sampling=declared_sampling(generator, judge),
                counts={"items_total": len(items), "units_without_usage": units_without_usage,
                        "items_with_errors": len(errored), "units_run": units_run},
                notes=notes + _resumed_only_notes(built, ran, resumes, bool(done)),
            )
            print(f"evaluation record {record_id} written under {store.dir}")

        print(f"wrote {summary_path}")
    except BaseException as exc:
        # spec F D-F30: a provider stop ends the record partial and the run
        # resumable from its checkpoint, and a refusal no retry fixes ends it
        # failed at once (ruling P21); spec F D-F29: a refused declaration ends
        # it failed; any other failure ends it failed and is raised
        stopped = isinstance(exc, ProviderUnavailable)
        provider_refused = isinstance(exc, ProviderRefused)
        refused = isinstance(exc, ConfigurationError)
        if store is not None and record_id is not None:
            completed, _ = _completed_items(unit_results, items, list(strategies.STRATEGY_NAMES))
            models_now = harness.strategy_models(built, list(built)) or None
            try:
                store.finish(record_id, status="partial" if stopped else "failed",
                             error=str(exc) if stopped or provider_refused or refused else exception_reason(exc),
                             notes=notes + _resumed_only_notes(built, ran, resumes, bool(done)),
                             completed_items=completed, usage=_own_usage(generator, judge),
                             sampling=declared_sampling(generator, judge) if generator is not None else None,
                             counts={"units_run": units_run},
                             prompt_versions={**(models_now or {}), **elicitor_versions} or None,
                             prompt_sha256=harness.runtime_judge_prompt_sha256(models_now) if models_now else None)
            except EvaluationRecordError:
                pass  # the record already ended inside the try; the original error is what matters
        if stopped or provider_refused:
            print(f"stopped: {exc}", file=sys.stderr)
            if len(done) + units_run:
                print(f"the checkpoint {checkpoint_path} is kept ({len(done) + units_run} unit(s) done); "
                      "continue with:", file=sys.stderr)
            else:
                # review T-M6: an empty checkpoint does not reach resolve_resume,
                # so the next run is a new record that names none
                print("no unit was checkpointed, so this starts a new record that names none; run again with:",
                      file=sys.stderr)
            print(f"  {_resume_line(list(argv) if argv is not None else sys.argv[1:], checkpoint_path)}",
                  file=sys.stderr)
            return 3 if stopped else 5
        if refused:
            print(f"stopped: {exc}", file=sys.stderr)
            return 4
        raise

    for name, s in summary["strategies"].items():
        print(f"  {name}: {json.dumps({k: v for k, v in s.items() if not isinstance(v, dict)})[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

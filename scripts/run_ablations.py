"""Checkpointed live ablation runner (M4, user-triggered spend).

@implements: DEC-11, DEC-17
@grounded_by: REF-15, REF-16, REF-17

Runs the five-condition ablation ladder over the gold seed plus the frozen
REF-15 benchmark sample, in checkpointed (strategy, item-batch) units, so a
crash never loses more than one batch (the lesson of the lost extraction run).
Resume by re-running: completed units are skipped. After the sweep, computes
the Section 12 metrics per strategy and writes eval/results/ablation_summary.json.

Gates: requires TERE4AI_LIVE_TESTS=1 and the model config of record
(eval/config_evaluated.yaml); refuses to start otherwise. Cost: roughly
(items x strategies) generator calls plus items judge calls for graph_full.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval import harness, metrics, strategies  # noqa: E402
from tere4ai.eval.evaluation_record import (  # noqa: E402
    EvaluationRecordError,
    EvaluationRecordStore,
    code_version,
    file_ref,
    observe_publication,
    served_input_paths,
)
from tere4ai.eval.metrics import METRICS_VERSION  # noqa: E402
from tere4ai.eval.present_evaluation import JULY_CHECKPOINT_DIGESTS, JULY_DIGESTS  # noqa: E402
from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator  # noqa: E402
from tere4ai.graph_store.build_chain import sha256_of_file  # noqa: E402
from tere4ai.graph_store.present import exception_reason  # noqa: E402
from tere4ai.judge.config import load_model_config  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
CHECKPOINT = RESULTS_DIR / "ablation_checkpoint.jsonl"
SUMMARY = RESULTS_DIR / "ablation_summary.json"
BATCH_SIZE = 10
# the pinned July summaries and checkpoints: never appended to, never rewritten
JULY_PROTECTED = frozenset(JULY_DIGESTS.values()) | frozenset(JULY_CHECKPOINT_DIGESTS.values())


def _july_refusal(path: Path) -> str | None:
    """The refusal sentence when path holds the bytes of a July file, else None."""
    if path.is_file() and sha256_of_file(path) in JULY_PROTECTED:
        return (f"refusing to write {path}: its bytes are the July 2026 measurement; "
                "pass --summary or --checkpoint with another path")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", type=Path, default=None,
                        help="benchmark payload (default: the frozen sample)")
    parser.add_argument("--features", type=Path, default=None,
                        help="elicited-features cache (default: run-2 file)")
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps",
                        help="where layer1.json, norms_core.json and evaluation_records/ live")
    parser.add_argument("--no-record", action="store_true", help="do not write an evaluation record (D-G33)")
    parser.add_argument("--repeat-of", default=None, help="record id of the run this run repeats")
    parser.add_argument("--resume-unrecorded", action="store_true",
                        help="resume a checkpoint no evaluation record names (the note is recorded)")
    args = parser.parse_args(argv)
    checkpoint_path, summary_path = args.checkpoint, args.summary
    # the July files are protected whether or not the run records (F1)
    for target in (checkpoint_path, summary_path):
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
    if checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            done.add(entry["unit"])
            unit_results.append(entry)
        print(f"resume: {len(done)} unit(s) already checkpointed")

    notes: list[str] = []
    resumes = None
    if done:
        # a read-only lookup, so a --no-record run is refused the same way
        resumes = EvaluationRecordStore(args.dump_dir, create=False).find_by_checkpoint_file(checkpoint_path.name)
        if resumes is None:
            if not args.resume_unrecorded:
                print(f"refusing to resume {checkpoint_path}: no evaluation record names it; pass "
                      "--resume-unrecorded to resume it anyway (the note is recorded) or --checkpoint "
                      "with a fresh path")
                return 2
            notes.append("resumed from a checkpoint no record names")

    store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
    record_id = None
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
            file_ref("features", features_path),
        ]
        if done:
            inputs.append(file_ref("checkpoint_resumed", checkpoint_path))
        publication, publication_reason = observe_publication(args.dump_dir)
        base_build_id = (dump.get("build") or {}).get("build_id")
        record_id = store.begin(
            kind="run", step="E6", command="run_ablations", argv=list(argv) if argv is not None else sys.argv[1:],
            inputs=inputs,
            build={"base_build_id": str(base_build_id) if base_build_id is not None else None,
                   "publication": publication, "publication_reason": publication_reason},
            models=config, prompt_versions=None, config={
                "strategies": list(strategies.STRATEGY_NAMES), "batch_size": BATCH_SIZE,
                "metrics_version": METRICS_VERSION, "code_version": code_version(ROOT), "mode": "live"},
            item_selection=[i["id"] for i in items], intended_items=[i["id"] for i in items],
            relations={"repeat_of": args.repeat_of, "resumes_record_id": resumes},
            counts={"units_resumed": len(done)}, checkpoint_file=checkpoint_path.name,
        )

    try:
        cfg = load_model_config()
        generator = OpenAIGenerator(cfg)
        judge = AnthropicJudge(cfg)

        strategy_models: dict[str, dict] = {}
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
                strategy_models[strategy_name] = dict(getattr(fn, "models", {}))
                for bi, batch in enumerate(batches):
                    unit = f"{strategy_name}:batch{bi}"
                    if unit in done:
                        continue
                    usage_before = {
                        "generator": dict(generator.usage),
                        "judge": dict(judge.usage),
                    }
                    per_item = {}
                    for item in batch:
                        try:
                            per_item[item["id"]] = fn(item)
                        except Exception as exc:  # record, never abort the sweep
                            per_item[item["id"]] = {
                                "error": f"{type(exc).__name__}: {exc}",
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
                    ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    ckpt.flush()
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
        for entry in unit_results:
            if "usage" not in entry:
                units_without_usage += 1
                continue
            for role, counts in entry["usage"].items():
                bucket = usage_total.setdefault(
                    role, {"calls": 0, "input_tokens": 0, "output_tokens": 0}
                )
                for k, v in counts.items():
                    bucket[k] += v

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
                    "versions without usage tracking contribute nothing here"
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

        tmp = summary_path.with_suffix(".writing.json")
        tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(summary_path)

        if store is not None and record_id is not None:
            errored = sorted({item_id for entry in unit_results for item_id, r in entry["results"].items()
                              if isinstance(r, dict) and r.get("error")})
            intended = [i["id"] for i in items]
            completed = [i for i in intended if i not in set(errored)
                         and all(i in merged.get(name, {}) for name in strategies.STRATEGY_NAMES)]
            outputs = [store.keep_output(record_id, "summary", summary_path),
                       store.keep_output(record_id, "checkpoint", checkpoint_path)]
            store.finish(
                record_id, status="completed" if len(completed) == len(intended) else "partial",
                completed_items=completed, outputs=outputs, usage=usage_total, prompt_versions=strategy_models,
                prompt_sha256=harness.runtime_judge_prompt_sha256(strategy_models),
                sampling={"generator": generator.sampling, "judge": judge.sampling},
                counts={"items_total": len(items), "units_without_usage": units_without_usage,
                        "items_with_errors": len(errored)},
                notes=notes,
            )
            print(f"evaluation record {record_id} written under {store.dir}")

        print(f"wrote {summary_path}")
    except BaseException as exc:
        if store is not None and record_id is not None:
            try:
                store.finish(record_id, status="failed", error=exception_reason(exc), notes=notes)
            except EvaluationRecordError:
                pass  # the record already ended inside the try; the original error is what matters
        raise

    for name, s in summary["strategies"].items():
        print(f"  {name}: {json.dumps({k: v for k, v in s.items() if not isinstance(v, dict)})[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

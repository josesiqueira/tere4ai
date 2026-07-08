"""Checkpointed live ablation runner (M4, user-triggered spend).

@implements: DEC-11
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

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval import harness, metrics, strategies  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
CHECKPOINT = RESULTS_DIR / "ablation_checkpoint.jsonl"
SUMMARY = RESULTS_DIR / "ablation_summary.json"
BATCH_SIZE = 10


def load_items() -> list[dict]:
    gold = harness.load_gold_items()
    bench = harness.load_benchmark_items()
    # enrich free-text scenarios with cached elicited features when present
    # (scripts/elicit_benchmark_features.py); provenance kept per item
    features_path = ROOT / "eval" / "gold" / "benchmark_features.json"
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


def main() -> int:
    dump = json.loads((ROOT / "data" / "graph_dumps" / "layer1.json").read_text())
    norms_payload = json.loads(
        (ROOT / "data" / "graph_dumps" / "norms_core.json").read_text()
    )
    items = load_items()
    print(f"items: {len(items)} | strategies: {strategies.STRATEGY_NAMES}")

    # live gates up front, zero cost on refusal
    harness._require_live_gate()
    config = harness.guard_live_config().as_public_dict()
    print(f"config of record OK: {config}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    unit_results: list[dict] = []
    if CHECKPOINT.exists():
        for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            done.add(entry["unit"])
            unit_results.append(entry)
        print(f"resume: {len(done)} unit(s) already checkpointed")

    from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
    from tere4ai.judge.config import load_model_config

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)

    batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    with CHECKPOINT.open("a", encoding="utf-8") as ckpt:
        for strategy_name in strategies.STRATEGY_NAMES:
            fn = strategies.build_strategy(
                strategy_name,
                generator=generator,
                judge=judge,
                dump=dump,
                norms_payload=norms_payload,
            )
            for bi, batch in enumerate(batches):
                unit = f"{strategy_name}:batch{bi}"
                if unit in done:
                    continue
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
                entry = {"unit": unit, "strategy": strategy_name, "results": per_item}
                ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                ckpt.flush()
                unit_results.append(entry)
                errors = sum(1 for r in per_item.values() if "error" in r)
                print(f"  {unit}: {len(per_item)} items, {errors} errors", flush=True)

    # merge per strategy
    merged: dict[str, dict] = {}
    for entry in unit_results:
        merged.setdefault(entry["strategy"], {}).update(entry["results"])

    # metrics per strategy against gold labels where present
    gold_items = [i for i in items if i.get("gold") or i.get("gold_citations")]
    valid_node_ids = {n["id"] for n in dump["nodes"]}
    summary: dict[str, dict] = {"config": config, "items_total": len(items), "strategies": {}}
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
        bench_results = {k: v for k, v in results.items() if k.startswith("bench:")}
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
                    "benchmark scenarios carry system_features null (free text); "
                    "the deterministic classifier abstains rather than guesses. "
                    "Mapping scenarios to structured features is annotation work "
                    "(eval/gold/ANNOTATION_PROTOCOL.md)."
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

    tmp = SUMMARY.with_suffix(".writing.json")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(SUMMARY)
    print(f"wrote {SUMMARY}")
    for name, s in summary["strategies"].items():
        print(f"  {name}: {json.dumps({k: v for k, v in s.items() if not isinstance(v, dict)})[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

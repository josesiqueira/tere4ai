"""Ablation deep-dive: confusion matrices, per-class PRF, abstention (#28).

@implements: DEC-11 (partial: deep-dive analysis over ablation results)
@grounded_by: REF-15, REF-16

Computes, per ladder condition, everything the headline accuracy hides:

- the full gold x predicted confusion matrix over the closed risk
  vocabulary (plus no_prediction for missing outputs);
- per-category precision/recall/F1 (reusing eval.metrics.prf1);
- abstention analysis: how often the condition answers "uncertain", and
  the selective accuracy on the items where it does commit. Abstaining is
  the designed degradation path (Section 13), so an abstention is never
  counted as a wrong answer; it is reported as coverage given up.

Input is either a run_eval results artifact (JSON) or a run checkpoint
(JSONL of {strategy, results} lines); gold labels come from the same
loaders the harness uses. The same command serves the run-2 sample today
and the full-benchmark artifact when task #27 runs.

Usage:
  .venv/bin/python scripts/ablation_deepdive.py \
      [--results eval/results/ablation_checkpoint.jsonl] \
      [--out docs/ablation_deepdive.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.harness import load_benchmark_items, load_gold_items  # noqa: E402
from tere4ai.eval.metrics import prf1  # noqa: E402
from tere4ai.mcp_server.classify import RISK_CATEGORIES  # noqa: E402

DEFAULT_RESULTS = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
DEFAULT_OUT = ROOT / "docs" / "ablation_deepdive.md"
NO_PREDICTION = "no_prediction"
PREDICTED_LABELS = (*RISK_CATEGORIES, NO_PREDICTION)


def load_results(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """{strategy: {item_id: result}} from an artifact JSON or checkpoint JSONL."""
    text = path.read_text(encoding="utf-8")
    per_strategy: dict[str, dict[str, dict[str, Any]]] = {}
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            per_strategy.setdefault(record["strategy"], {}).update(record["results"])
        return per_strategy
    artifact = json.loads(text)
    for name, block in artifact.get("results", {}).items():
        per_strategy[name] = dict(block.get("items", {}))
    return per_strategy


def gold_risk_by_item(benchmark_path: Path | None = None) -> dict[str, str]:
    """Gold risk labels keyed by item id.

    benchmark_path must be the same payload the analysed run used (the
    sample by default, the full payload for the #27 run); otherwise items
    outside the payload have no gold label and are silently not scored.
    """
    bench = (
        load_benchmark_items(benchmark_path) if benchmark_path else load_benchmark_items()
    )
    gold: dict[str, str] = {}
    for item in (*load_gold_items(), *bench):
        if item["kind"] == "classification":
            gold[item["id"]] = item["gold"]["risk_category"]
    return gold


def analyse_strategy(
    results: dict[str, dict[str, Any]], gold: dict[str, str]
) -> dict[str, Any]:
    matrix: dict[str, dict[str, int]] = {
        g: dict.fromkeys(PREDICTED_LABELS, 0) for g in RISK_CATEGORIES
    }
    scored = 0
    for item_id, result in results.items():
        gold_label = gold.get(item_id)
        if gold_label is None:
            continue  # retrieval/qa items have no risk gold
        predicted = result.get("risk_category") or NO_PREDICTION
        if predicted not in PREDICTED_LABELS:
            predicted = NO_PREDICTION
        matrix[gold_label][predicted] += 1
        scored += 1

    per_class: dict[str, dict[str, float]] = {}
    for label in RISK_CATEGORIES:
        tp = matrix[label][label]
        fp = sum(matrix[g][label] for g in RISK_CATEGORIES if g != label)
        fn = sum(count for p, count in matrix[label].items() if p != label)
        per_class[label] = {"support": tp + fn, **prf1(tp, fp, fn)}

    committed = correct_committed = abstained = 0
    for gold_label in RISK_CATEGORIES:
        for predicted, count in matrix[gold_label].items():
            if predicted in ("uncertain", NO_PREDICTION):
                abstained += count
                continue
            committed += count
            if predicted == gold_label:
                correct_committed += count
    overall_correct = sum(matrix[g][g] for g in RISK_CATEGORIES)
    return {
        "scored_items": scored,
        "matrix": matrix,
        "per_class": per_class,
        "overall_accuracy": overall_correct / scored if scored else 0.0,
        "abstention": {
            "abstained": abstained,
            "abstention_rate": abstained / scored if scored else 0.0,
            "committed": committed,
            "selective_accuracy": correct_committed / committed if committed else 0.0,
        },
    }


def render_markdown(source: Path, analyses: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Ablation deep-dive: confusion, per-class PRF, abstention",
        "",
        "> Generated by scripts/ablation_deepdive.py from "
        f"{source.name}; every number is computed from the per-item",
        "> results, nothing is transcribed by hand. Abstentions (uncertain or",
        "> no prediction) are the designed degradation path and are reported",
        "> as given-up coverage, never as correct answers.",
        "",
    ]
    for name, a in analyses.items():
        ab = a["abstention"]
        lines += [
            f"## {name}",
            "",
            f"Scored classification items: {a['scored_items']}; overall accuracy "
            f"{a['overall_accuracy']:.3f}; abstention rate "
            f"{ab['abstention_rate']:.3f} ({ab['abstained']} items); selective "
            f"accuracy on the {ab['committed']} committed answers: "
            f"{ab['selective_accuracy']:.3f}.",
            "",
            "| gold \\\\ predicted | " + " | ".join(PREDICTED_LABELS) + " |",
            "| --- |" + " --- |" * len(PREDICTED_LABELS),
        ]
        for gold_label in RISK_CATEGORIES:
            row = a["matrix"][gold_label]
            lines.append(
                f"| {gold_label} | " + " | ".join(str(row[p]) for p in PREDICTED_LABELS) + " |"
            )
        lines += [
            "",
            "| class | support | precision | recall | f1 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for label, scores in a["per_class"].items():
            lines.append(
                f"| {label} | {scores['support']} | {scores['precision']:.3f} "
                f"| {scores['recall']:.3f} | {scores['f1']:.3f} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--benchmark", type=Path, default=None,
        help="benchmark payload the run used (default: the frozen sample); "
        "must match --results or unmatched items are not scored",
    )
    args = parser.parse_args(argv)

    per_strategy = load_results(args.results)
    gold = gold_risk_by_item(args.benchmark)
    scored = len(next(iter(per_strategy.values()), {}))
    labelled = sum(1 for item_id in next(iter(per_strategy.values()), {}) if item_id in gold)
    print(f"result items per strategy: {scored}; with gold risk labels: {labelled}")
    analyses = {
        name: analyse_strategy(results, gold)
        for name, results in sorted(per_strategy.items())
    }
    args.out.write_text(render_markdown(args.results, analyses), encoding="utf-8")
    for name, a in analyses.items():
        ab = a["abstention"]
        print(
            f"{name}: acc {a['overall_accuracy']:.3f} | abstain "
            f"{ab['abstention_rate']:.3f} | selective acc {ab['selective_accuracy']:.3f}"
        )
    shown = args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

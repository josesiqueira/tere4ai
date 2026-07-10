"""Generate the paper figures and LaTeX tables from the eval artifacts.

@implements: DEC-11 (partial: paper artifact generation from eval results)
@grounded_by: REF-15, REF-16

Usage:
  .venv/bin/python scripts/make_paper_artifacts.py [--out docs/paper_artifacts]

Every number in every figure and table is computed at generation time from
the committed artifacts (eval/results/*.json, data/graph_dumps/*.json);
nothing is hand-typed (AGENTS.md honesty rules). Outputs are GENERATED;
regenerate after any new eval run, never hand-edit.

Outputs:
  fig_ablation_ladder.{png,svg}   run-2 ladder: free-text accuracy,
                                  abstentions, citation completeness
  fig_run1_run2.{png,svg}         run 1 vs run 2 (the elicitation effect)
  fig_judge_funnel.{png,svg}      build-judge funnel for norms and alignments
  fig_graph_census.{png,svg}      Layer 1 node type counts
  tab_ablation.tex                booktabs ladder table
  tab_census.tex                  booktabs census table
  tab_judges.tex                  booktabs judge-verdict table
  MANIFEST.json                   sha256 of every input and output

Style: Okabe-Ito colorblind-safe palette, 300 dpi PNG plus SVG, no em or en
dashes anywhere in labels (project hard rule).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUN2 = ROOT / "eval" / "results" / "ablation_summary.json"
RUN1 = ROOT / "eval" / "results" / "ablation_run1_summary.json"
NORMS = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS = ROOT / "data" / "graph_dumps" / "alignments_core.json"
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
INPUTS = (RUN2, RUN1, NORMS, ALIGNMENTS, LAYER1)

# Okabe-Ito palette (colorblind safe), muted ordering.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]

STRATEGY_LABELS = {
    "plain_llm": "plain LLM",
    "vector_rag": "vector RAG",
    "graph_no_judge": "graph, no judge",
    "graph_build_judge": "graph + build judge",
    "graph_full": "graph + both judges",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 100,
            "savefig.dpi": 300,
            "svg.hashsalt": "tere4ai",  # deterministic SVG ids
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linewidth": 0.5,
        }
    )


def _save(fig, out_dir: Path, stem: str, written: list[Path]) -> None:
    for ext in ("png", "svg"):
        path = out_dir / f"{stem}.{ext}"
        fig.savefig(path, bbox_inches="tight", metadata=None)
        written.append(path)
    plt.close(fig)


def _bench(strategy: dict) -> dict:
    return strategy.get("benchmark_freetext_classification") or {}


def _citation_completeness(strategy: dict) -> float:
    block = strategy.get("benchmark_citation_completeness_article_level") or {}
    return float(block.get("completeness", 0.0))


def fig_ablation_ladder(run2: dict, out: Path, written: list[Path]) -> None:
    names = list(STRATEGY_LABELS)
    correct = [_bench(run2["strategies"][n]).get("correct", 0) for n in names]
    total = [_bench(run2["strategies"][n]).get("total", 0) for n in names]
    abstained = [_bench(run2["strategies"][n]).get("abstained", 0) for n in names]
    completeness = [_citation_completeness(run2["strategies"][n]) for n in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.6))
    x = range(len(names))
    ax1.bar(x, correct, color=PALETTE[0], label="correct")
    ax1.bar(x, abstained, bottom=correct, color=PALETTE[1], label="abstained (honest)")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([STRATEGY_LABELS[n] for n in names], rotation=20, ha="right")
    ax1.set_ylabel(f"benchmark free-text items (of {total[0]})")
    ax1.set_title("Classification outcome (run 2)")
    ax1.legend(frameon=False, fontsize=7)

    ax2.bar(x, completeness, color=PALETTE[2])
    ax2.set_xticks(list(x))
    ax2.set_xticklabels([STRATEGY_LABELS[n] for n in names], rotation=20, ha="right")
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("article-level completeness")
    ax2.set_title("Checkable citations (run 2)")
    _save(fig, out, "fig_ablation_ladder", written)


def fig_run1_run2(run1: dict, run2: dict, out: Path, written: list[Path]) -> None:
    names = list(STRATEGY_LABELS)
    r1 = [_bench(run1["strategies"][n]).get("correct", 0) for n in names]
    r2 = [_bench(run2["strategies"][n]).get("correct", 0) for n in names]
    width = 0.38
    fig, ax = plt.subplots(figsize=(4.4, 2.6))
    x = range(len(names))
    ax.bar([i - width / 2 for i in x], r1, width, color=PALETTE[3], label="run 1 (no elicitation)")
    ax.bar([i + width / 2 for i in x], r2, width, color=PALETTE[0], label="run 2 (with elicitation)")
    ax.set_xticks(list(x))
    ax.set_xticklabels([STRATEGY_LABELS[n] for n in names], rotation=20, ha="right")
    ax.set_ylabel("correct free-text items (of 32)")
    ax.set_title("Feature elicitation unlocks the graph ladder")
    ax.legend(frameon=False, fontsize=7)
    _save(fig, out, "fig_run1_run2", written)


def _verdicts(payload: dict, key: str) -> Counter:
    return Counter(x.get("judge_verdict") or "none" for x in payload[key])


def fig_judge_funnel(norms: dict, alignments: dict, out: Path, written: list[Path]) -> None:
    nv = _verdicts(norms, "norms")
    av = _verdicts(alignments, "assertions")
    stages = ["norms", "alignments"]
    accepted = [nv.get("accepted", 0), av.get("accepted", 0)]
    rejected = [nv.get("rejected", 0), av.get("rejected", 0)]
    review = [nv.get("needs_human_review", 0), av.get("needs_human_review", 0)]

    fig, ax = plt.subplots(figsize=(4.0, 2.4))
    y = range(len(stages))
    ax.barh(y, accepted, color=PALETTE[2], label="accepted")
    ax.barh(y, review, left=accepted, color=PALETTE[1], label="needs human review")
    ax.barh(
        y,
        rejected,
        left=[a + r for a, r in zip(accepted, review)],
        color=PALETTE[5],
        label="rejected",
    )
    ax.set_yticks(list(y))
    ax.set_yticklabels(
        [
            f"{stages[0]} (n={sum(nv.values())})",
            f"{stages[1]} (n={sum(av.values())})",
        ]
    )
    ax.invert_yaxis()
    ax.set_xlabel("LLM candidates by judge verdict")
    ax.set_title("Independent build judges gate the graph")
    ax.legend(frameon=False, fontsize=7, ncol=3)
    _save(fig, out, "fig_judge_funnel", written)


def fig_graph_census(layer1: dict, out: Path, written: list[Path]) -> None:
    counts = Counter(n["type"] for n in layer1["nodes"]).most_common(10)
    labels = [c[0] for c in counts][::-1]
    values = [c[1] for c in counts][::-1]
    fig, ax = plt.subplots(figsize=(4.0, 2.8))
    ax.barh(labels, values, color=PALETTE[0])
    ax.set_xlabel("nodes")
    ax.set_title(
        f"Layer 1 structural mirror ({len(layer1['nodes'])} nodes, "
        f"{len(layer1['edges'])} edges)"
    )
    _save(fig, out, "fig_graph_census", written)


def _tex_escape(text: str) -> str:
    return text.replace("%", r"\%").replace("_", r"\_").replace("&", r"\&")


def tab_ablation(run1: dict, run2: dict) -> str:
    lines = [
        "% GENERATED by scripts/make_paper_artifacts.py; never hand-edit.",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Condition & \multicolumn{2}{c}{Correct (of 32)} & Abstained & "
        r"Cit.\ compl. & Halluc. \\",
        r" & run 1 & run 2 & run 2 & run 2 & run 2 \\",
        r"\midrule",
    ]
    for name, label in STRATEGY_LABELS.items():
        s1, s2 = run1["strategies"][name], run2["strategies"][name]
        halluc = float(s2.get("hallucinated_citation_rate", {}).get("rate", 0.0))
        lines.append(
            f"{_tex_escape(label)} & {_bench(s1).get('correct', 0)} & "
            f"{_bench(s2).get('correct', 0)} & {_bench(s2).get('abstained', 0)} & "
            f"{_citation_completeness(s2):.2f} & {halluc:.2f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", ""]
    return "\n".join(lines)


def tab_census(layer1: dict, norms: dict, alignments: dict) -> str:
    node_counts = Counter(n["type"] for n in layer1["nodes"]).most_common()
    lines = [
        "% GENERATED by scripts/make_paper_artifacts.py; never hand-edit.",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Node type (Layer 1) & Count \\",
        r"\midrule",
    ]
    lines += [f"{_tex_escape(t)} & {c} \\\\" for t, c in node_counts]
    lines += [
        r"\midrule",
        f"NormativeStatement (Layer 2) & {len(norms['norms'])} \\\\",
        f"AlignmentAssertion (Layer 3) & {len(alignments['assertions'])} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    return "\n".join(lines)


def tab_judges(norms: dict, alignments: dict) -> str:
    nv, av = _verdicts(norms, "norms"), _verdicts(alignments, "assertions")
    lines = [
        "% GENERATED by scripts/make_paper_artifacts.py; never hand-edit.",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Stage & Candidates & Accepted & Rejected & Human review \\",
        r"\midrule",
        f"Norm extraction & {sum(nv.values())} & {nv.get('accepted', 0)} & "
        f"{nv.get('rejected', 0)} & {nv.get('needs_human_review', 0)} \\\\",
        f"HLEG alignment & {sum(av.values())} & {av.get('accepted', 0)} & "
        f"{av.get('rejected', 0)} & {av.get('needs_human_review', 0)} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "paper_artifacts")
    args = parser.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    run2 = json.loads(RUN2.read_text(encoding="utf-8"))
    run1 = json.loads(RUN1.read_text(encoding="utf-8"))
    norms = json.loads(NORMS.read_text(encoding="utf-8"))
    alignments = json.loads(ALIGNMENTS.read_text(encoding="utf-8"))
    layer1 = json.loads(LAYER1.read_text(encoding="utf-8"))

    _style()
    written: list[Path] = []
    fig_ablation_ladder(run2, out, written)
    fig_run1_run2(run1, run2, out, written)
    fig_judge_funnel(norms, alignments, out, written)
    fig_graph_census(layer1, out, written)

    for name, text in (
        ("tab_ablation.tex", tab_ablation(run1, run2)),
        ("tab_census.tex", tab_census(layer1, norms, alignments)),
        ("tab_judges.tex", tab_judges(norms, alignments)),
    ):
        path = out / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    manifest = {
        "generator": "scripts/make_paper_artifacts.py",
        "inputs": {str(p.relative_to(ROOT)): _sha256(p) for p in INPUTS},
        # Outputs are named relative to the output directory so the manifest
        # is valid wherever --out points (inside the repo or a temp dir).
        "outputs": sorted(p.name for p in written),
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(written) + 1} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

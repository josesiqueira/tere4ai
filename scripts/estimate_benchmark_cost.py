"""Full-benchmark cost estimator: dry-run the ladder, count tokens, price it.

@implements: DEC-11 (partial: cost gate for the full-benchmark ablation, dry run only)
@grounded_by: REF-15

The full REF-15 benchmark (339 scenarios + 137 QA pairs) is frozen under
data/snapshots/benchmark/ with sha256 checksums matching the provenance
recorded in eval/gold/benchmark_sample.json. This script runs the REAL
strategy code (src/tere4ai/eval/strategies.py) over ALL items with a
counting stand-in client, so every prompt is the exact prompt a live run
would send; no model is called and no network is touched.

Token model, stated plainly so nobody mistakes this for a measurement:
- Input tokens are estimated as prompt characters / 4 (a standard rough
  heuristic; the true OpenAI and Anthropic tokenizers are not available
  offline). The report carries a +/-25 percent band.
- Output tokens come from observed run-2 answer lengths per strategy
  (eval/results/ablation_checkpoint.jsonl) and observed elicitation
  payloads (eval/gold/benchmark_features.json), same chars/4 mapping.

Pricing:
- Judge (claude-opus-4-8): 5.00 USD in / 25.00 USD out per million tokens
  (Anthropic published pricing, cached 2026-06; verify before spending).
- Generator (gpt-5.2): no price is recorded in this repo and none is
  invented here. Set TERE4AI_PRICE_GPT52_IN / TERE4AI_PRICE_GPT52_OUT
  (USD per million tokens) to get a priced total; otherwise the report
  gives token totals and the cost formula.

Usage: .venv/bin/python scripts/estimate_benchmark_cost.py
Writes: docs/benchmark_cost_estimate.md
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.harness import load_benchmark_items, run_eval  # noqa: E402
from tere4ai.eval.strategies import STRATEGY_NAMES  # noqa: E402

BENCH_DIR = ROOT / "data" / "snapshots" / "benchmark"
SAMPLE_PATH = ROOT / "eval" / "gold" / "benchmark_sample.json"
CHECKPOINT = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
RUNTIME_LOG = ROOT / "data" / "review_queue" / "runtime_log.jsonl"
FEATURES = ROOT / "eval" / "gold" / "benchmark_features.json"
ELICIT_PROMPT = ROOT / "prompts" / "elicit_features" / "v1.md"
OUT_PATH = ROOT / "docs" / "benchmark_cost_estimate.md"

CHARS_PER_TOKEN = 4.0
BAND = 0.25  # +/- band on the chars/4 heuristic

# Anthropic published pricing for claude-opus-4-8, USD per 1M tokens
# (cached 2026-06; confirm on the pricing page before the live run).
JUDGE_PRICE_IN = 5.00
JUDGE_PRICE_OUT = 25.00

GEN_PRICE_IN = os.environ.get("TERE4AI_PRICE_GPT52_IN")
GEN_PRICE_OUT = os.environ.get("TERE4AI_PRICE_GPT52_OUT")


def tokens(chars: int | float) -> int:
    return int(round(chars / CHARS_PER_TOKEN))


class CountingClient:
    """ModelClient stand-in: records prompt sizes, returns a parseable stub."""

    def __init__(self, model: str, reply: dict[str, Any]):
        self.model = model
        self._reply = json.dumps(reply)
        self.calls = 0
        self.prompt_chars = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.prompt_chars += len(system) + len(user)
        return self._reply


def verify_full_benchmark() -> Path:
    """Cross-check the frozen full files against the pinned provenance."""
    import hashlib

    provenance = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["provenance"]
    for name, meta in provenance["files"].items():
        path = BENCH_DIR / name
        if not path.exists():
            raise SystemExit(
                f"{path} missing: download scenarios.json and qa_pairs.json from "
                f"{provenance['repository']} into {BENCH_DIR}"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise SystemExit(f"{path}: sha256 {digest} != pinned {meta['sha256']}")

    scenarios = json.loads((BENCH_DIR / "scenarios.json").read_text(encoding="utf-8"))["data"]
    qa_pairs = json.loads((BENCH_DIR / "qa_pairs.json").read_text(encoding="utf-8"))["data"]
    payload = {
        "provenance": provenance,
        "scenarios": [
            dict(s, benchmark_index=i) for i, s in enumerate(scenarios)
        ],
        "qa_pairs": [dict(q, benchmark_index=i) for i, q in enumerate(qa_pairs)],
    }
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    return tmp


def observed_output_chars() -> dict[str, dict[str, float]]:
    """Mean answer payload chars per (strategy, kind) from the run-2 checkpoint."""
    by_key: dict[tuple[str, str], list[int]] = {}
    with CHECKPOINT.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            strategy = rec["strategy"]
            for item_id, result in rec["results"].items():
                kind = "qa" if ":qa" in item_id or ":ret" in item_id else "classification"
                payload = json.dumps(
                    {k: result.get(k) for k in ("answer_text", "citations", "risk_category")}
                )
                by_key.setdefault((strategy, kind), []).append(len(payload))
    out: dict[str, dict[str, float]] = {}
    for (strategy, kind), sizes in by_key.items():
        out.setdefault(strategy, {})[kind] = statistics.mean(sizes)
    return out


def observed_judge_reply_chars() -> float:
    """Mean judge reply size from the real run-2 runtime grounding log."""
    sizes = []
    if RUNTIME_LOG.exists():
        with RUNTIME_LOG.open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("direction") == "judge":
                    sizes.append(
                        len(
                            json.dumps(
                                {k: rec.get(k) for k in ("verdict", "scores", "rationale")}
                            )
                        )
                    )
    # Fallback if no log is present: verdict + five scores + rationale.
    return statistics.mean(sizes) if sizes else 700.0


def main() -> int:
    payload_path = verify_full_benchmark()
    items = load_benchmark_items(payload_path)
    cls_items = [i for i in items if i["kind"] == "classification"]
    qa_items = [i for i in items if i["kind"] != "classification"]
    n_cls, n_qa = len(cls_items), len(qa_items)
    print(f"full benchmark loaded: {n_cls} scenarios + {n_qa} qa = {len(items)} items")

    out_chars = observed_output_chars()
    judge_reply_chars = observed_judge_reply_chars()

    # Dry-run every ladder strategy over every item with counting clients,
    # split by item kind so output-token estimates only charge kinds whose
    # answers the generator actually produced (graph strategies classify
    # deterministically and only call the generator on QA items).
    # LLM-free strategy internals (deterministic classify, TF-IDF retrieval)
    # run for real; only the model boundary is stubbed.
    gen_reply = {"answer_text": "dry-run stub", "citations": [], "risk_category": None}
    judge_reply = {"verdict": "accepted", "scores": {}, "rationale": "dry-run stub"}
    per_strategy: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in STRATEGY_NAMES:
            totals = {
                "gen_calls": 0, "gen_in": 0, "gen_out": 0,
                "judge_calls": 0, "judge_in": 0, "judge_out": 0,
            }
            for kind, subset in (("classification", cls_items), ("qa", qa_items)):
                gen = CountingClient("gpt-5.2", gen_reply)
                judge = CountingClient("claude-opus-4-8", judge_reply)
                run_eval(
                    subset,
                    [name],
                    generator_factory=lambda g=gen: g,
                    judge_factory=lambda j=judge: j,
                    live=False,
                    results_dir=Path(tmp),
                    judge_log_path=Path(tmp) / "judge_log.jsonl",
                )
                mean_out = out_chars.get(name, {}).get(kind, 0)
                totals["gen_calls"] += gen.calls
                totals["gen_in"] += tokens(gen.prompt_chars)
                totals["gen_out"] += tokens(gen.calls * mean_out)
                totals["judge_calls"] += judge.calls
                totals["judge_in"] += tokens(judge.prompt_chars)
                totals["judge_out"] += tokens(judge.calls * judge_reply_chars)
            per_strategy[name] = totals
            print(
                f"{name}: {totals['gen_calls']} generator calls "
                f"({totals['gen_in']} in-tok), {totals['judge_calls']} judge calls "
                f"({totals['judge_in']} in-tok)"
            )

    # Elicitation: one generator call per scenario (DEC-13); prompt is the
    # elicitor system prompt plus the scenario free text, output size from
    # the 32 observed elicitations.
    elicit_system = len(ELICIT_PROMPT.read_text(encoding="utf-8"))
    elicit_user = sum(len(i["system_text"]) for i in items if i["kind"] == "classification")
    feats = json.loads(FEATURES.read_text(encoding="utf-8"))["features_by_item"]
    elicit_out_mean = statistics.mean(len(json.dumps(v)) for v in feats.values())
    elicitation = {
        "calls": n_cls,
        "gen_in": tokens(n_cls * elicit_system + elicit_user),
        "gen_out": tokens(n_cls * elicit_out_mean),
    }

    gen_in = sum(s["gen_in"] for s in per_strategy.values()) + elicitation["gen_in"]
    gen_out = sum(s["gen_out"] for s in per_strategy.values()) + elicitation["gen_out"]
    judge_in = sum(s["judge_in"] for s in per_strategy.values())
    judge_out = sum(s["judge_out"] for s in per_strategy.values())

    judge_cost = judge_in / 1e6 * JUDGE_PRICE_IN + judge_out / 1e6 * JUDGE_PRICE_OUT
    gen_cost = None
    if GEN_PRICE_IN and GEN_PRICE_OUT:
        gen_cost = gen_in / 1e6 * float(GEN_PRICE_IN) + gen_out / 1e6 * float(GEN_PRICE_OUT)

    lines = [
        "# Full-benchmark ablation cost estimate (dry run)",
        "",
        "> Generated by scripts/estimate_benchmark_cost.py. No model was called.",
        "> The dry run executed the real strategy code over the FULL frozen",
        f"> benchmark ({n_cls} scenarios + {n_qa} QA pairs, sha256-verified against",
        "> the provenance in eval/gold/benchmark_sample.json). Token counts use",
        "> a chars/4 heuristic with a +/-25 percent band; output sizes come from",
        "> observed run-2 payloads. This is an estimate, not a measurement.",
        "",
        "## Per-strategy dry-run counts (full ladder, all items)",
        "",
        "| Strategy | Generator calls | Gen in-tokens | Gen out-tokens (obs.) | Judge calls | Judge in-tokens | Judge out-tokens (est.) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in STRATEGY_NAMES:
        s = per_strategy[name]
        lines.append(
            f"| {name} | {s['gen_calls']} | {s['gen_in']:,} | {s['gen_out']:,} "
            f"| {s['judge_calls']} | {s['judge_in']:,} | {s['judge_out']:,} |"
        )
    lines += [
        f"| elicitation (DEC-13, once per scenario) | {elicitation['calls']} "
        f"| {elicitation['gen_in']:,} | {elicitation['gen_out']:,} | 0 | 0 | 0 |",
        "",
        "## Totals",
        "",
        f"- Generator (gpt-5.2): {gen_in:,} input + {gen_out:,} output tokens",
        f"  (band: {int(gen_in * (1 - BAND)):,} to {int(gen_in * (1 + BAND)):,} input).",
        f"- Judge (claude-opus-4-8): {judge_in:,} input + {judge_out:,} output tokens.",
        "",
        "## Cost",
        "",
        f"- Judge cost at 5.00/25.00 USD per MTok (Anthropic pricing, cached "
        f"2026-06): **{judge_cost:.2f} USD** "
        f"(band {judge_cost * (1 - BAND):.2f} to {judge_cost * (1 + BAND):.2f}).",
    ]
    if gen_cost is not None:
        total = gen_cost + judge_cost
        lines += [
            f"- Generator cost at {GEN_PRICE_IN}/{GEN_PRICE_OUT} USD per MTok "
            f"(operator-provided): **{gen_cost:.2f} USD**.",
            f"- **Estimated total: {total:.2f} USD** "
            f"(band {total * (1 - BAND):.2f} to {total * (1 + BAND):.2f}).",
        ]
    else:
        lines += [
            "- Generator (gpt-5.2) price is NOT recorded in this repo and is not",
            "  invented here. Cost formula: gen_in/1e6 x P_in + gen_out/1e6 x P_out.",
            "  Set TERE4AI_PRICE_GPT52_IN and TERE4AI_PRICE_GPT52_OUT (USD per",
            "  million tokens) and rerun this script for a priced total.",
        ]
    lines += [
        "",
        "## Cost-gate notes for task #27",
        "",
        "- Only graph_full calls the runtime judge; the other four conditions",
        "  are generator-only. Dropping graph_full halves nothing else.",
        "- Batch APIs (both providers) typically price at 50 percent; the run",
        "  is embarrassingly parallel and latency-insensitive, so batching is",
        "  the first lever if the total is over budget.",
        "- Second lever: run the ladder on all 339 scenarios but a stratified",
        "  half of the 137 QA pairs; classification is the headline task.",
        "",
    ]
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    payload_path.unlink(missing_ok=True)
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

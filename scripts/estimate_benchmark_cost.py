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
- The elicitation system prompt is the default prompt rendered over the
  repository's dump (data/graph_dumps/layer1.json, spans verified against
  data/snapshots), the text a live call sends (B10: the default elicitor
  prompt prints each provision from the graph), not the template with its
  placeholders.
- Output tokens come from observed run-2 answer lengths per strategy
  (eval/results/ablation_checkpoint.jsonl) and observed elicitation
  payloads (eval/gold/benchmark_features.json), same chars/4 mapping; an
  elicitation payload is its features plus its quotes when the file holds
  quotes, otherwise features only and the report says so.

Pricing (B120, spec F D-F29 discipline):
- The two models are the ones the environment names (TERE4AI_GENERATOR_MODEL
  and TERE4AI_JUDGE_MODEL), checked against their rows in
  config/model_parameters.json; this script names no model.
- Prices are data in config/model_prices.json: one row per model id with the
  provider's pricing page (https) and the day it was read. A row without
  both, or a model the environment names without a row, is refused by name.
  No API key is read and no network is touched.

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

from tere4ai.elicit_features import render_prompt  # noqa: E402
from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION  # noqa: E402
from tere4ai.eval.harness import load_benchmark_items, run_eval  # noqa: E402
from tere4ai.eval.strategies import STRATEGY_NAMES  # noqa: E402
from tere4ai.judge.config import (  # noqa: E402
    _ISO_DAY,
    ConfigurationError,
    ModelParameters,
    declaration_for,
    load_dotenv_once,
    load_model_parameters,
)

BENCH_DIR = ROOT / "data" / "snapshots" / "benchmark"
SAMPLE_PATH = ROOT / "eval" / "gold" / "benchmark_sample.json"
CHECKPOINT = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
RUNTIME_LOG = ROOT / "data" / "review_queue" / "runtime_log.jsonl"
FEATURES = ROOT / "eval" / "gold" / "benchmark_features.json"
ELICIT_PROMPT = ROOT / "prompts" / "elicit_features" / f"{DEFAULT_PROMPT_VERSION}.md"
ELICIT_DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
OUT_PATH = ROOT / "docs" / "benchmark_cost_estimate.md"

CHARS_PER_TOKEN = 4.0
BAND = 0.25  # +/- band on the chars/4 heuristic

PRICES_PATH = ROOT / "config" / "model_prices.json"
PRICES_FILE = "config/model_prices.json"
GENERATOR_VARIABLE = "TERE4AI_GENERATOR_MODEL"
JUDGE_VARIABLE = "TERE4AI_JUDGE_MODEL"
# the provider each role's client talks to (architecture.md Section 7)
ROLE_PROVIDERS = {"generator": "openai", "judge": "anthropic"}
_PRICE_KEYS = ("input", "output", "batch_input", "batch_output")


def _price_problem(row: Any) -> str | None:
    """What is wrong with one price row, or None. The page and the day are
    checked as declaration_for checks the declaration's own (https page,
    YYYY-MM-DD day)."""
    from datetime import date
    from urllib.parse import urlsplit

    if not isinstance(row, dict):
        return "the row is not an object"
    if row.get("provider") not in ("openai", "anthropic"):
        return "provider must be openai or anthropic"
    for key in _PRICE_KEYS:
        try:
            if float(row[key]) < 0:
                return f"{key} is negative"
        except (KeyError, TypeError, ValueError):
            return f"{key} is missing or is not a decimal string"
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return "no pricing page (https) and no day it was read (YYYY-MM-DD)"
    url, read_on = pricing.get("url"), pricing.get("read_on")
    try:
        read_day = (date.fromisoformat(read_on)
                    if isinstance(read_on, str) and _ISO_DAY.fullmatch(read_on) else None)
    except ValueError:
        read_day = None
    try:
        page = urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        page = None
    if page is None or page.scheme != "https" or not page.hostname or read_day is None:
        return "names no pricing page (https) or no day it was read (YYYY-MM-DD)"
    return None


def load_model_prices(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """The price rows keyed by model id, every row checked; the four prices
    come back as floats (USD per million tokens). Raises ConfigurationError
    naming every refused row."""
    path = path or PRICES_PATH
    where = PRICES_FILE if path == PRICES_PATH else path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigurationError(f"configuration error: {where} is missing") from None
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            f"configuration error: {where} cannot be read ({type(exc).__name__})") from None
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or not isinstance(data.get("models"), dict)):
        raise ConfigurationError(
            f"configuration error: {where} must hold schema_version 1 and a models object keyed by model id")
    problems = [f"{model_id}: {problem}" for model_id, row in data["models"].items()
                if (problem := _price_problem(row)) is not None]
    if problems:
        raise ConfigurationError(f"configuration error: {where} has refused rows: " + "; ".join(problems))
    return {model_id: {**row, **{key: float(row[key]) for key in _PRICE_KEYS}}
            for model_id, row in data["models"].items()}


def declared_models(env: Any, parameters_path: Path | None = None) -> dict[str, ModelParameters]:
    """The generator and the judge the environment names, each with its row of
    config/model_parameters.json (provider, effort, documentation). Refused
    when a variable is unset or a model has no declaration row."""
    models = load_model_parameters(parameters_path)
    declared: dict[str, ModelParameters] = {}
    for role, variable in (("generator", GENERATOR_VARIABLE), ("judge", JUDGE_VARIABLE)):
        model_id = env.get(variable)
        if not model_id:
            raise ConfigurationError(f"configuration error: {variable} is not set")
        declared[role] = declaration_for(models, model_id, ROLE_PROVIDERS[role])
    return declared


def price_rows(prices: dict[str, dict[str, Any]],
               declared: dict[str, ModelParameters]) -> dict[str, dict[str, Any]]:
    """The price row of each declared model; refused by name when a model has none."""
    rows = {}
    for role, model in declared.items():
        if model.model_id not in prices:
            raise ConfigurationError(
                f"configuration error: {PRICES_FILE} has no row for model {model.model_id!r} "
                f"(the {role}); add one with its prices, the pricing page and the day it was read")
        rows[role] = prices[model.model_id]
    return rows


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


def elicit_system_prompt() -> str:
    """The default elicitation prompt rendered over the repository's dump,
    as a live call sends it (B10); no model call."""
    dump = json.loads(ELICIT_DUMP.read_text(encoding="utf-8"))
    system, _ = render_prompt(dump, SNAPSHOTS_DIR, DEFAULT_PROMPT_VERSION)
    return system


def elicitation_output_chars(facts: dict[str, Any]) -> tuple[float, str | None]:
    """Mean characters of one elicitation reply, and a note for the report
    when the figure is partial. A reply to the default elicitor prompt
    carries "features" and "quotes" (B10), so when the facts file has
    quotes_by_item each item counts its features plus its quotes as the
    reply sends them ({path: text}; the offsets are added by the code). A
    file without quotes gives the features-only figure and the note says
    so."""
    feats = facts["features_by_item"]
    quotes = facts.get("quotes_by_item")
    if not isinstance(quotes, dict):
        mean = statistics.mean(len(json.dumps(v)) for v in feats.values())
        return mean, (
            "The elicitation output size counts features only: the facts file "
            f"({FEATURES.relative_to(ROOT)}) holds no quotes, so the quotes of a reply "
            "to the default elicitor prompt are not in the figure."
        )
    sizes = []
    for item, features in feats.items():
        sent = {
            path: q.get("text") if isinstance(q, dict) else q
            for path, q in (quotes.get(item) or {}).items()
        }
        sizes.append(len(json.dumps(features)) + len(json.dumps(sent)))
    return statistics.mean(sizes), None


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


# A condition the run-2 checkpoint does not hold takes the observed answer
# sizes of the condition whose generator prompt it shares (B126: the sixth
# condition offers the norms graph_no_judge offers; its judge adds no
# generator output).
OUTPUT_SIZE_PROXY = {"graph_runtime_judge": "graph_no_judge"}


def output_chars_for(out_chars: dict[str, dict[str, float]],
                     name: str) -> tuple[dict[str, float], str | None]:
    """The observed answer sizes per kind for one condition, and the proxy
    condition they were read from (None when the condition's own)."""
    if name in out_chars:
        return out_chars[name], None
    proxy = OUTPUT_SIZE_PROXY.get(name)
    if proxy is not None and proxy in out_chars:
        return out_chars[proxy], proxy
    return {}, None


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
    load_dotenv_once()
    declared = declared_models(os.environ)
    rows = price_rows(load_model_prices(), declared)
    gen_id, judge_id = declared["generator"].model_id, declared["judge"].model_id
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
    proxied: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in STRATEGY_NAMES:
            sizes, proxy = output_chars_for(out_chars, name)
            if proxy is not None:
                proxied[name] = proxy
            totals = {
                "gen_calls": 0, "gen_in": 0, "gen_out": 0,
                "judge_calls": 0, "judge_in": 0, "judge_out": 0,
            }
            for kind, subset in (("classification", cls_items), ("qa", qa_items)):
                gen = CountingClient(gen_id, gen_reply)
                judge = CountingClient(judge_id, judge_reply)
                run_eval(
                    subset,
                    [name],
                    generator_factory=lambda g=gen: g,
                    judge_factory=lambda j=judge: j,
                    live=False,
                    results_dir=Path(tmp),
                    judge_log_path=Path(tmp) / "judge_log.jsonl",
                )
                mean_out = sizes.get(kind, 0)
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
    # elicitor system prompt rendered over the dump plus the scenario free
    # text, output size from the 32 observed elicitations.
    elicit_system = len(elicit_system_prompt())
    elicit_user = sum(len(i["system_text"]) for i in items if i["kind"] == "classification")
    elicit_out_mean, elicit_out_note = elicitation_output_chars(
        json.loads(FEATURES.read_text(encoding="utf-8"))
    )
    elicitation = {
        "calls": n_cls,
        "gen_in": tokens(n_cls * elicit_system + elicit_user),
        "gen_out": tokens(n_cls * elicit_out_mean),
    }

    gen_in = sum(s["gen_in"] for s in per_strategy.values()) + elicitation["gen_in"]
    gen_out = sum(s["gen_out"] for s in per_strategy.values()) + elicitation["gen_out"]
    judge_in = sum(s["judge_in"] for s in per_strategy.values())
    judge_out = sum(s["judge_out"] for s in per_strategy.values())

    gen_row, judge_row = rows["generator"], rows["judge"]
    judge_cost = judge_in / 1e6 * judge_row["input"] + judge_out / 1e6 * judge_row["output"]
    gen_cost = gen_in / 1e6 * gen_row["input"] + gen_out / 1e6 * gen_row["output"]

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
    ]
    if elicit_out_note:
        lines += [elicit_out_note, ""]
    for name, proxy in proxied.items():
        lines += [f"{name} was not run in run 2: its output tokens use the observed "
                  f"answer sizes of {proxy}.", ""]
    lines += [
        "## Totals",
        "",
        f"- Generator ({gen_id}, effort {declared['generator'].effort}): {gen_in:,} input + "
        f"{gen_out:,} output tokens",
        f"  (band: {int(gen_in * (1 - BAND)):,} to {int(gen_in * (1 + BAND)):,} input).",
        f"- Judge ({judge_id}, effort {declared['judge'].effort}): {judge_in:,} input + "
        f"{judge_out:,} output tokens.",
        "",
        "## Cost",
        "",
        f"- Judge cost at {judge_row['input']:.2f}/{judge_row['output']:.2f} USD per MTok "
        f"({judge_row['pricing']['url']}, read {judge_row['pricing']['read_on']}): "
        f"**{judge_cost:.2f} USD** "
        f"(band {judge_cost * (1 - BAND):.2f} to {judge_cost * (1 + BAND):.2f}).",
        f"- Generator cost at {gen_row['input']:.2f}/{gen_row['output']:.2f} USD per MTok "
        f"({gen_row['pricing']['url']}, read {gen_row['pricing']['read_on']}): "
        f"**{gen_cost:.2f} USD**.",
        f"- **Estimated total: {gen_cost + judge_cost:.2f} USD** "
        f"(band {(gen_cost + judge_cost) * (1 - BAND):.2f} to {(gen_cost + judge_cost) * (1 + BAND):.2f}).",
        "",
        "## Cost-gate notes for task #27",
        "",
        "- Only graph_full and graph_runtime_judge call the runtime judge; the",
        "  other four conditions are generator-only. Dropping either removes",
        "  only its own judge calls and changes nothing else.",
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

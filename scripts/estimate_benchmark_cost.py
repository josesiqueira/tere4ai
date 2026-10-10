"""Cost estimator for the B74 sequence: dry-run every step, count tokens, price it.

@implements: DEC-11 (partial: cost estimate for the B74 sequence, dry run only)
@implements: DEC-24 (its price loader in judge/config.py; the demo judge's log lines left out)
@grounded_by: REF-15

The sequence is Layer 2 extraction, Layer 3 alignment, the control backlog,
the benchmark elicitation and the E6 ablation (spec G Section 10.4, repeated
N times); campaigns cost nothing and the calibration judge runs are not in
it. Every step runs the REAL pipeline code (extract_norms, align_norms,
generate_control_backlog, the ablation strategies) with counting stand-in
clients, so every prompt is the exact prompt a live run would send; no model
is called and no network is touched. The full REF-15 benchmark (339
scenarios + 137 QA pairs, frozen under data/snapshots/benchmark/ with the
sha256 of eval/gold/benchmark_sample.json) is priced as one reference line,
outside the total.

Token model, stated plainly so nobody mistakes this for a measurement:
- Input tokens are prompt characters divided by a ratio per model developer,
  measured offline on the aborted B74 extraction (RATIOS, each with its
  source), with a declared band of plus or minus 10 percent.
- Output is priced with reasoning included, since both inference backends bill
  reasoning as output: billed = visible reply / (1 - r), where r is the
  reasoning share, a declared band (low: measured at the API default in
  the aborted extraction; central: the only xhigh measurement; high:
  declared). Nothing is measured at xhigh for either declared model.
- The visible reply sizes come from stored replies: July norms and
  alignments (tracked dumps), the run-2 ablation checkpoint, the runtime
  judge's mean reply size (frozen in RATIOS, runtime_judge_reply_chars) and
  eval/gold/benchmark_features.json. Nothing else outside the tracked tree
  changes a figure: the repository's .env, when present, is loaded, but an
  exported variable wins over the file, and no other variable it may set
  reaches a figure (the API keys go unread; TERE4AI_REPO_ROOT is read at
  import, before the file is loaded).
- Input is priced uncached: the clients send no cache_control and record no
  cached tokens; automatic caching can only lower the figure.

Pricing (B120, spec F D-F29 discipline):
- The two models are the ones the environment names (TERE4AI_GENERATOR_MODEL
  and TERE4AI_JUDGE_MODEL), checked against their rows in
  config/model_parameters.json; this script names no model.
- Prices are data in config/model_prices.json: one row per model id with the
  inference backend's pricing page (https) and the day it was read. A row without
  both, or a model the environment names without a row, is refused by name.
  No API key is read and no network is touched.

Usage: .venv/bin/python scripts/estimate_benchmark_cost.py [--measured-usage PATH ...]
Writes: docs/benchmark_cost_estimate.md
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai import act_parties  # noqa: E402
from tere4ai.act_parties import slots_of  # noqa: E402
from tere4ai.align_hleg import pipeline as align_pipeline  # noqa: E402
from tere4ai.align_hleg.__main__ import _attach_source_text  # noqa: E402
from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes  # noqa: E402
from tere4ai.elicit_features import render_prompt  # noqa: E402
from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION  # noqa: E402
from tere4ai.eval.harness import load_benchmark_items, load_gold_items, run_eval  # noqa: E402
from tere4ai.eval.strategies import STRATEGY_NAMES  # noqa: E402
from tere4ai.extract_norms import pipeline as extract_pipeline  # noqa: E402
from tere4ai.judge.config import (  # noqa: E402
    MODEL_PRICES_FILE,
    MODEL_PRICES_PATH,
    ConfigurationError,
    ModelParameters,
    declaration_for,
    load_dotenv_once,
    load_model_parameters,
    load_model_prices,
    model_developer_of,
)
from tere4ai.mcp_server.backlog import generate_control_backlog  # noqa: E402

BENCH_DIR = ROOT / "data" / "snapshots" / "benchmark"
SAMPLE_PATH = ROOT / "eval" / "gold" / "benchmark_sample.json"
CHECKPOINT = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
FEATURES = ROOT / "eval" / "gold" / "benchmark_features.json"
ELICIT_PROMPT = ROOT / "prompts" / "elicit_features" / f"{DEFAULT_PROMPT_VERSION}.md"
ELICIT_DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
OUT_PATH = ROOT / "docs" / "benchmark_cost_estimate.md"

PRICES_PATH = MODEL_PRICES_PATH
PRICES_FILE = MODEL_PRICES_FILE
GENERATOR_VARIABLE = "TERE4AI_GENERATOR_MODEL"
JUDGE_VARIABLE = "TERE4AI_JUDGE_MODEL"
# the inference backend each model component's client talks to (architecture.md Section 7)
COMPONENT_BACKEND = {"generator": "openai", "judge": "anthropic"}


# DEC-24: the price loader moved to tere4ai.judge.config (load_model_prices,
# imported above), so the demo judge's configuration reads the same table.


def declared_models(env: Any, parameters_path: Path | None = None) -> dict[str, ModelParameters]:
    """The generator and the judge the environment names, each with its row of
    config/model_parameters.json (inference backend, effort, documentation). Refused
    when a variable is unset or a model has no declaration row."""
    models = load_model_parameters(parameters_path)
    declared: dict[str, ModelParameters] = {}
    for component, variable in (("generator", GENERATOR_VARIABLE), ("judge", JUDGE_VARIABLE)):
        model_id = env.get(variable)
        if not model_id:
            raise ConfigurationError(f"configuration error: {variable} is not set")
        declared[component] = declaration_for(models, model_id, COMPONENT_BACKEND[component])
    return declared


def price_rows(prices: dict[str, dict[str, Any]],
               declared: dict[str, ModelParameters]) -> dict[str, dict[str, Any]]:
    """The price row of each declared model; refused by name when a model has none."""
    rows = {}
    for component, model in declared.items():
        if model.model_id not in prices:
            raise ConfigurationError(
                f"configuration error: {PRICES_FILE} has no row for model {model.model_id!r} "
                f"(the {component}); add one with its prices, the pricing page and the day it was read")
        rows[component] = prices[model.model_id]
    return rows


def tokens(chars: int | float, model_developer: str) -> int:
    """Tokens of chars characters at the model developer's own measured ratio
    (a tokenizer is the model's, R14 (e))."""
    return int(round(chars / ratio(f"chars_per_token_{model_developer}")))


class CountingClient:
    """ModelClient stand-in: records prompt and reply sizes, returns a
    parseable stub. reply is one dict sent on every call, or a function of
    (system, user) giving the dict for that call."""

    def __init__(self, model: str, reply: Any):
        self.model = model
        self._reply = reply
        self.calls = 0
        self.prompt_chars = 0
        self.out_chars = 0
        self.max_prompt_chars = 0
        self.last_user = ""

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.prompt_chars += len(system) + len(user)
        self.max_prompt_chars = max(self.max_prompt_chars, len(system) + len(user))
        self.last_user = user
        reply = json.dumps(self._reply(system, user) if callable(self._reply) else self._reply)
        self.out_chars += len(reply)
        return reply


# ------------------------------------------------------------------ B120
# The ratios the token model uses. Each carries its source, printed in the
# report beside the figure (ruling R7). Nothing here is a price.
RATIOS: dict[str, dict[str, Any]] = {
    "chars_per_token_openai": {
        "value": 4.12,
        "source": (
            "recomputed 2026-10-04 from the aborted B74 extraction (data/graph_dumps/"
            "norms_core.b74.json build.extraction_usage, 2026-09-16): extract_norms v1's prompt "
            "rendered over the 405 source units that run saw, divided by its 475,017 measured "
            "generator input tokens; the plan's 4.22 divided the characters of 414 units by the "
            "tokens of 405 calls"
        ),
    },
    "chars_per_token_anthropic": {
        "value": 2.92,
        "source": (
            "recomputed 2026-10-04 from the same run: judge_norms v1 rendered over its 505 "
            "candidates, divided by the 905,340 measured judge input tokens (the Claude API "
            "skill states Opus 5.5 keeps Opus 5's tokenizer); this replaced chars/4, which "
            "under-counted the judge by 1.81 times in July (HISTORY 2026-07-11)"
        ),
    },
    "input_band": {
        "value": 0.10,
        "source": "declared: plus or minus 10 percent on every input token count",
    },
    "candidates_per_unit": {
        "value": 1.247,
        "source": "the aborted B74 extraction: 505 candidates over 405 source units (the run's generator)",
    },
    "accepted_share": {
        "value": 0.885,
        "source": "the aborted B74 extraction: 447 accepted over 505 judged candidates",
    },
    "align_judge_per_accepted": {
        "value": 1.15,
        "source": "the aborted B74 alignment checkpoint: 302 judge calls over 262 generator calls",
    },
    "reasoning_share_central": {
        "value": 0.82,
        "source": (
            "the only xhigh measurement, the luna model of the GPT-6 family in the dashboard's B88 run (2026-09-26): "
            "310 of 379 output tokens were reasoning; applied to both declared models"
        ),
    },
    "reasoning_share_high": {
        "value": 0.90,
        "source": "declared: reasoning ten times the visible output",
    },
    "backlog_generator_billed_tokens": {
        "value": 1510.0,
        "source": (
            "the one measured xhigh backlog call of the declared generator (dashboard project_events 111209, "
            "2026-09-27, Article 8): 1,510 billed output tokens, reasoning not separable; read as "
            "carrying the central reasoning share"
        ),
    },
    "backlog_generator_measured_norms": {
        "value": 2.0,
        "source": "the norms that one measured backlog call sent (dashboard project_events 111209, 2026-09-27, Article 8)",
    },
    "runtime_judge_reply_chars": {
        "value": 636.6847826086956,
        "source": (
            "the mean reply size of 1,104 non-demo runtime judge lines (verdict, scores and rationale as JSON) "
            "of the local data/review_queue/runtime_log.jsonl, 2026-07-08 to 2026-09-23, recomputed 2026-10-10 "
            "(B147); frozen here so the estimate regenerates from the tracked tree"
        ),
    },
}

B74_NORMS = ROOT / "data" / "graph_dumps" / "norms_core.b74.json"
JULY_NORMS = ROOT / "data" / "graph_dumps" / "norms_core.json"
JULY_ALIGNMENTS = ROOT / "data" / "graph_dumps" / "alignments_core.json"
CORE_NODES = ROOT / "data" / "graph_dumps" / "core_nodes.txt"
# Mock data for the backlog step, copied from tere4ai-dashboard scripts/seed.ts
# (the CredScore demo project, line 114): the description a real backlog call
# for Article 25 would send as the system context.
CREDSCORE_DESCRIPTION = (
    "CredScore is a machine learning service that evaluates the creditworthiness of natural "
    "persons applying for consumer loans, producing a score and a recommendation that loan "
    "officers use in their decisions and can override. It is not a fraud detection tool, and is "
    "deployed by a private company under EU jurisdiction as a private entity providing an "
    "essential private service (consumer credit)."
)
BACKLOG_ARTICLE = "eu-ai-act:article-25"


def ratio(name: str) -> float:
    return float(RATIOS[name]["value"])


def core_node_ids(path: Path | None = None) -> list[str]:
    """The ids of the core slice (core_nodes.txt, one comma-separated line)."""
    text = (path or CORE_NODES).read_text(encoding="utf-8")
    return [node_id.strip() for node_id in text.split(",") if node_id.strip()]


def _mean(values: list[float], default: float = 0.0) -> float:
    return statistics.mean(values) if values else default


def _judge_reply_chars(run: dict[str, Any], keys: tuple[str, ...]) -> int:
    return len(json.dumps({key: run.get(key) for key in keys if key in run}, ensure_ascii=False))


def _norm_reply(norms: list[dict[str, Any]]) -> dict[str, Any]:
    """The reply the extractor sent for one unit: the candidate fields of its norms."""
    fields = [key for key in extract_pipeline.candidate_fields(extract_pipeline.DEFAULT_PROMPT_VERSION)
              if key != "target_system_category"]
    names = ("addressee_explicit", "addressee_inferred", "addressee_inference_source_node_id")
    read = [{**norm, **dict(zip(names, slots_of(norm), strict=True))} for norm in norms]
    return {"norms": [{key: norm[key] for key in fields if key in norm} for norm in read]}


def extraction_lines(
    dump: dict[str, Any],
    node_ids: list[str],
    july_norms: list[dict[str, Any]],
    july_judge_runs: list[dict[str, Any]],
    tmp_dir: Path,
) -> tuple[dict[str, dict[str, Any]], float]:
    """Layer 2 dry run: extract_norms() with counting clients, the generator
    scripted to reply each unit's July norms (an empty list for a unit with
    none), the judge a stub verdict. One generator call per unit, the real
    prompt; the judge's input is the pipeline's own _judge_user_message over
    each candidate. Judge calls are units x candidates per unit, at the mean
    judge input of the dry run. Returns ({"generator", "judge"} lines,
    estimated candidates)."""
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for norm in july_norms:
        by_unit.setdefault(norm["source_node_id"], []).append(norm)

    def reply(_system: str, user: str) -> dict[str, Any]:
        node_id = user.split("\n", 1)[0].removeprefix("Source unit node id: ")
        return _norm_reply(by_unit.get(node_id, []))

    judge_stub = {"verdict": "accepted", "scores": {}, "rationale": "dry-run stub"}
    gen = CountingClient("generator", reply)
    judge = CountingClient("judge", judge_stub)
    result = extract_pipeline.extract_norms(
        dump, node_ids, gen, judge, log_path=tmp_dir / "extraction_log.jsonl")
    units = result["stats"]["source_units"]
    if judge.calls == 0:
        raise SystemExit("the extraction dry run reached the judge zero times: no candidate to size")
    candidates = units * ratio("candidates_per_unit")
    judge_calls = round(candidates)
    judge_out = _mean([_judge_reply_chars(run, ("verdict", "scores", "rationale"))
                       for run in july_judge_runs], judge.out_chars / judge.calls)
    # the scripted replies hold the historical candidates (judge.calls of them);
    # the downstream counts use the projected ones, so the candidate payload is
    # scaled to the projection and the per-call JSON overhead stays one per unit
    overhead = len(json.dumps({"norms": []}))
    payload = max(gen.out_chars - gen.calls * overhead, 0) / judge.calls
    gen_out = gen.calls * overhead + candidates * payload
    return {
        "generator": {"calls": gen.calls, "in_chars": gen.prompt_chars, "out_chars": gen_out,
                      "max_chars": gen.max_prompt_chars},
        "judge": {"calls": judge_calls, "in_chars": judge_calls * judge.prompt_chars / judge.calls,
                  "out_chars": judge_calls * judge_out, "max_chars": judge.max_prompt_chars},
    }, candidates


def alignment_lines(
    norms: list[dict[str, Any]],
    hleg_nodes: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    judge_runs: list[dict[str, Any]],
    accepted_norms: float,
    tmp_dir: Path,
) -> dict[str, Any]:
    """Layer 3 dry run: align_norms() over the accepted norms (source_text
    attached) with a generator replying no candidates, so the generator's
    input is the pipeline's own. Generator calls are accepted_norms (the
    extraction's candidates x the accepted share); its output is the size of
    the July reply per norm. The judge's input is align's own
    _judge_user_message over the July assertions; judge calls are
    accepted_norms x alignment judge calls per accepted norm."""
    gen = CountingClient("generator", {"alignments": []})
    judge = CountingClient("judge", {"verdict": "accepted", "scores": {}, "rationale": "dry-run stub"})
    align_pipeline.align_norms(
        norms, hleg_nodes, gen, judge, log_path=tmp_dir / "alignment_log.jsonl")
    if gen.calls == 0:
        raise SystemExit("the alignment dry run made no generator call: no accepted norm")
    accepted = {n["norm_id"]: n for n in norms if n.get("judge_verdict") == "accepted"}
    hleg_by_id = {node["id"]: node for node in hleg_nodes}
    judge_system = align_pipeline.load_prompt("judge_alignment", "v1")
    keys = ("target_id", "relation_type", "source_quote", "target_quote", "rationale")
    per_norm: dict[str, list[dict[str, Any]]] = {norm_id: [] for norm_id in accepted}
    judge_in: list[int] = []
    rationale_chars: list[int] = []
    for a in assertions:
        norm = accepted.get(a["source_norm_id"])
        target = hleg_by_id.get(a["target_id"])
        if norm is None or target is None:
            continue
        candidate = {key: a.get(key) for key in keys}
        per_norm[norm["norm_id"]].append(candidate)
        rationale_chars.append(len(str(candidate.get("rationale") or "")))
        judge_in.append(len(judge_system) + len(align_pipeline._judge_user_message(norm, target, candidate)))
    gen_out = _mean([len(json.dumps({"alignments": c}, ensure_ascii=False)) for c in per_norm.values()])
    mapping = [run for run in judge_runs
               if run.get("judge_kind", "mapping") == "mapping"
               and run.get("judge_model") != align_pipeline.MECHANICAL_JUDGE_MODEL]
    judge_out = _mean([_judge_reply_chars(run, ("verdict", "scores", "rationale", "corrected_relation_type"))
                       for run in mapping])
    judge_calls = round(accepted_norms * ratio("align_judge_per_accepted"))
    # PROXY: a stored assertion's rationale is the judge's (align_hleg/pipeline.py
    # keeps the judge's rationale on the assertion); no record holds the
    # generator's own reply (the logs keep hashes only). The judge's rationale
    # stands in for the generator's, and these are the characters it adds, so
    # the report can price the estimate without it (the lower bound).
    gen_rationale = _mean([sum(len(str(c.get("rationale") or "")) for c in cs)
                           for cs in per_norm.values()])
    return {
        "rationale_proxy": {"gen_out_chars": round(accepted_norms) * gen_rationale,
                            "judge_in_chars": judge_calls * _mean(rationale_chars)},
        "dry_generator_calls": gen.calls,
        "generator": {"calls": round(accepted_norms),
                      "in_chars": round(accepted_norms) * gen.prompt_chars / gen.calls,
                      "out_chars": round(accepted_norms) * gen_out, "max_chars": gen.max_prompt_chars},
        "judge": {"calls": judge_calls, "in_chars": judge_calls * _mean(judge_in),
                  "out_chars": judge_calls * judge_out, "max_chars": max(judge_in, default=0)},
    }


def backlog_lines(
    norms: list[dict[str, Any]],
    system_context: str,
    tmp_dir: Path,
    judge_reply_chars: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Backlog dry run: generate_control_backlog() with counting clients over
    the accepted norms and the system description. One generator call and one
    runtime-judge call. The generator's output is the one measured call's
    billed tokens scaled by the norms sent over the norms that call sent (a
    planning assumption, no source; spec G D-G82 (12)), turned back into
    visible characters at the central reasoning share (the report prices it
    at every share from that). The judge's output is the runtime judge's
    frozen mean reply size unless judge_reply_chars is given."""
    norm_ids = [norm["norm_id"] for norm in norms]
    item = {"title": "Dry-run control", "description": "Dry-run stub.", "norm_ids": norm_ids,
            "suggested_evidence": ["dry-run evidence"], "priority": "must", "requirement_type": None}
    gen = CountingClient("generator", {"items": [item]})
    judge = CountingClient("judge", {"verdict": "accepted", "scores": {}, "rationale": "dry-run stub"})
    generate_control_backlog(norms, system_context, gen, judge, log_path=tmp_dir / "backlog_log.jsonl")
    # B133: this turns one historical billed figure into visible characters and
    # keeps the central share on purpose; a measured share (--measured-usage)
    # applies to the priced steps only
    visible_tokens = (ratio("backlog_generator_billed_tokens")
                      * len(norm_ids) / ratio("backlog_generator_measured_norms")
                      * (1 - ratio("reasoning_share_central")))
    return {
        "generator": {"calls": gen.calls, "in_chars": gen.prompt_chars,
                      "out_chars": visible_tokens * ratio("chars_per_token_openai"),
                      "max_chars": gen.max_prompt_chars},
        "judge": {"calls": judge.calls, "in_chars": judge.prompt_chars,
                  "out_chars": (ratio("runtime_judge_reply_chars") if judge_reply_chars is None
                                else judge_reply_chars),
                  "max_chars": judge.max_prompt_chars},
    }


def every_role_backlog_norms(b74_norms: list[dict[str, Any]], dump: dict[str, Any]) -> list[dict[str, Any]]:
    """Spec G D-G82 (1), (12): Article 25's accepted norms of the aborted B74
    extraction that one click sends: served to one of the six AI Act roles
    (act_parties.serves) or with an addressee not settled. The facade's click
    also applies applicability by classification and target system category,
    which this offline selection does not."""
    roles = act_parties.ai_act_roles()
    out = []
    for norm in b74_norms:
        if norm.get("judge_verdict") != "accepted" or not norm["source_node_id"].startswith(BACKLOG_ARTICLE + ":"):
            continue
        value = act_parties.addressee_of(norm).value
        if value == act_parties.UNSPECIFIED or any(act_parties.serves(value, role) for role in roles):
            out.append(dict(norm))
    _attach_source_text(out, dump)
    return out


def _b74_source_units(dump: dict[str, Any], node_ids: list[str]) -> list[dict[str, Any]]:
    """The 405 source units the aborted B74 extraction saw: the core slice's
    units as they stand in the dump, the deleted ones included (the dump now
    holds the Omnibus units that run could not see, and the extraction no
    longer expands the deleted ones), the inserted ones left out."""
    nodes = extract_pipeline._index_nodes(dump)
    units = []
    for node in dump["nodes"]:
        in_scope = any(node["id"] == i or node["id"].startswith(i + ":") for i in node_ids)
        if node.get("type") in extract_pipeline.SOURCE_UNIT_TYPES and in_scope \
                and node.get("amendment") != "inserted":
            units.append({"node_id": node["id"], "text": node.get("text", ""),
                          "article_context": extract_pipeline._article_context_title(node["id"], nodes)})
    return units


def recompute_chars_per_token(
    b74_path: Path | None = None, dump_path: Path | None = None,
) -> dict[str, float]:
    """The two characters-per-token ratios, recomputed offline from the
    aborted B74 extraction: its v1 prompts rendered over the units and
    candidates it saw, divided by the input tokens it measured."""
    b74 = json.loads((b74_path or B74_NORMS).read_text(encoding="utf-8"))
    dump = json.loads((dump_path or ELICIT_DUMP).read_text(encoding="utf-8"))
    usage = b74["build"]["extraction_usage"]
    version = b74["build"]["prompt_version"]
    units = _b74_source_units(dump, core_node_ids())
    system = extract_pipeline.load_prompt("extract_norms", version)
    gen_chars = sum(len(system) + len(extract_pipeline._generator_user_message(u)) for u in units)

    nodes = extract_pipeline._index_nodes(dump)
    judge_system = extract_pipeline.load_prompt("judge_norms", version)
    fields = [k for k in extract_pipeline._NORM_CANDIDATE_FIELDS if k != "requirement_type"]
    judge_chars = 0
    for norm in b74["norms"]:
        node = nodes[norm["source_node_id"]]
        unit = {"node_id": node["id"], "text": node.get("text", "")}
        candidate = {key: norm.get(key) for key in fields if key in norm}
        block = extract_pipeline.judge_inference_block(dump, nodes, unit, candidate, version)
        judge_chars += len(judge_system) + len(extract_pipeline._judge_user_message(unit, candidate, block))
    return {"openai": gen_chars / usage["generator"]["input_tokens"],
            "anthropic": judge_chars / usage["judge"]["input_tokens"]}


def default_reasoning_shares(payload: dict[str, Any]) -> dict[str, float]:
    """The share of billed output that was reasoning at the API default
    (the low end of the declared band): 1 minus the visible reply's tokens
    over the billed output tokens per call, from the aborted B74 extraction.
    The generator's visible reply is the candidate fields of the norms of
    its unit (an empty list for a unit with none); the judge's is its
    verdict, scores and rationale."""
    usage = payload["build"]["extraction_usage"]
    fields = [k for k in extract_pipeline._NORM_CANDIDATE_FIELDS if k != "requirement_type"]
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for norm in payload["norms"]:
        by_unit.setdefault(norm["source_node_id"], []).append(
            {key: norm[key] for key in fields if key in norm})
    units = payload["stats"]["source_units"]
    gen_chars = sum(len(json.dumps({"norms": v}, ensure_ascii=False)) for v in by_unit.values())
    gen_chars += (units - len(by_unit)) * len(json.dumps({"norms": []}))
    judge_chars = sum(_judge_reply_chars(run, ("verdict", "scores", "rationale"))
                      for run in payload["judge_runs"])
    gen_visible = gen_chars / usage["generator"]["calls"] / ratio("chars_per_token_openai")
    judge_visible = judge_chars / usage["judge"]["calls"] / ratio("chars_per_token_anthropic")
    gen_billed = usage["generator"]["output_tokens"] / usage["generator"]["calls"]
    judge_billed = usage["judge"]["output_tokens"] / usage["judge"]["calls"]
    return {"generator": 1 - gen_visible / gen_billed, "judge": 1 - judge_visible / judge_billed}



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


# ------------------------------------------------------------------ B120 token model
ABLATION_REPETITIONS = 10  # R5, provisional (awaiting Jose): B104 R5's provisional ten
CONTEXT_LIMIT_TOKENS = 272_000  # the short-context limit of the declared generator's price row
LEVELS = ("low", "central", "high")


def ablation_dry_run(
    items: list[dict[str, Any]],
    out_chars: dict[str, dict[str, float]],
    judge_reply_chars: float,
    tmp_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Dry-run every ladder strategy over the items with counting clients, split
    by item kind so output is charged only for kinds whose answers the
    generator produced (graph strategies classify deterministically and only
    call the generator on QA items). LLM-free strategy internals (deterministic
    classify, TF-IDF retrieval) run for real; only the model boundary is
    stubbed. Returns per strategy {gen_calls, gen_in, gen_out, judge_calls,
    judge_in, judge_out, max_chars} in characters, and the proxied conditions."""
    cls_items = [i for i in items if i["kind"] == "classification"]
    qa_items = [i for i in items if i["kind"] != "classification"]
    gen_reply = {"answer_text": "dry-run stub", "citations": [], "risk_category": None}
    judge_reply = {"verdict": "accepted", "scores": {}, "rationale": "dry-run stub"}
    per_strategy: dict[str, dict[str, Any]] = {}
    proxied: dict[str, str] = {}
    for name in STRATEGY_NAMES:
        sizes, proxy = output_chars_for(out_chars, name)
        if proxy is not None:
            proxied[name] = proxy
        totals = {"gen_calls": 0, "gen_in": 0, "gen_out": 0.0,
                  "judge_calls": 0, "judge_in": 0, "judge_out": 0.0, "max_chars": 0}
        for kind, subset in (("classification", cls_items), ("qa", qa_items)):
            if not subset:
                continue
            gen = CountingClient("generator", gen_reply)
            judge = CountingClient("judge", judge_reply)
            run_eval(
                subset,
                [name],
                generator_factory=lambda g=gen: g,
                judge_factory=lambda j=judge: j,
                live=False,
                results_dir=tmp_dir,
                judge_log_path=tmp_dir / "judge_log.jsonl",
            )
            totals["gen_calls"] += gen.calls
            totals["gen_in"] += gen.prompt_chars
            totals["gen_out"] += gen.calls * sizes.get(kind, 0)
            totals["judge_calls"] += judge.calls
            totals["judge_in"] += judge.prompt_chars
            totals["judge_out"] += judge.calls * judge_reply_chars
            totals["max_chars"] = max(totals["max_chars"], gen.max_prompt_chars, judge.max_prompt_chars)
        per_strategy[name] = totals
    return per_strategy, proxied


def ablation_lines(per_strategy: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The two model component lines of one ablation run: the strategies summed."""
    def total(key: str) -> float:
        return sum(s[key] for s in per_strategy.values())
    biggest = max((s["max_chars"] for s in per_strategy.values()), default=0)
    return {
        "generator": {"calls": total("gen_calls"), "in_chars": total("gen_in"),
                      "out_chars": total("gen_out"), "max_chars": biggest},
        "judge": {"calls": total("judge_calls"), "in_chars": total("judge_in"),
                  "out_chars": total("judge_out"), "max_chars": biggest},
    }


def elicitation_line(items: list[dict[str, Any]], system_chars: int, out_chars_mean: float) -> dict[str, Any]:
    """One generator call per scenario still without features (DEC-13): the
    elicitor's system prompt rendered over the dump plus the scenario text."""
    scenarios = [i for i in items if i["kind"] == "classification" and not i.get("system_features")]
    user = [len(i["system_text"]) for i in scenarios]
    return {"calls": len(scenarios),
            "in_chars": len(scenarios) * system_chars + sum(user),
            "out_chars": len(scenarios) * out_chars_mean,
            "max_chars": system_chars + max(user, default=0)}


def reasoning_bands(low: dict[str, float],
                    measured: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, float]]:
    """The reasoning share of billed output per model component at each level
    (R7). A model component with a measured share (B133) has it at all three
    levels, in place of the declared band."""
    bands = {component: {"low": value, "central": ratio("reasoning_share_central"),
                         "high": ratio("reasoning_share_high")} for component, value in low.items()}
    for component, found in (measured or {}).items():
        bands[component] = {level: found["share"] for level in LEVELS}
    return bands


def _complete_reasoning(usage: Any) -> bool:
    """A model component's usage counts every reply's reasoning figure: both counts are
    present and replies_with_reasoning equals replies_with_usage, above zero."""
    if not isinstance(usage, dict):
        return False
    if not {"reasoning_tokens", "replies_with_reasoning", "output_tokens"} <= set(usage):
        return False
    return usage["replies_with_reasoning"] == usage.get("replies_with_usage") and usage["replies_with_reasoning"] > 0


def measured_reasoning(paths: list[Path], declared: dict[str, ModelParameters]) -> dict[str, dict[str, Any]]:
    """B133: per declared model component, the measured reasoning share of
    output over the build records at paths: executions run under the declared
    model id whose usage for the model component is complete. A model
    component with no such execution is absent."""
    sums = {component: {"reasoning": 0, "output": 0, "replies": 0, "files": []} for component in declared}
    for path in paths:
        try:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
            executions = record["executions"]
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SystemExit(f"--measured-usage {path}: not a build record with executions ({exc})") from exc
        if not isinstance(executions, list):
            raise SystemExit(f"--measured-usage {path}: not a build record with executions (not a list)")
        shown = str(Path(path).resolve().relative_to(ROOT)) if Path(path).resolve().is_relative_to(ROOT) else str(path)
        for execution in executions:
            models = execution.get("models") or {}
            usage = execution.get("usage") or {}
            for component, model in declared.items():
                counts = usage.get(component)
                if models.get(f"{component}_model") != model.model_id or not _complete_reasoning(counts):
                    continue
                bucket = sums[component]
                bucket["reasoning"] += counts["reasoning_tokens"]
                bucket["output"] += counts["output_tokens"]
                bucket["replies"] += counts["replies_with_reasoning"]
                if shown not in bucket["files"]:
                    bucket["files"].append(shown)
    return {component: {"share": b["reasoning"] / b["output"], "reasoning": b["reasoning"],
                        "output": b["output"], "replies": b["replies"], "files": b["files"]}
            for component, b in sums.items() if b["replies"] and b["output"]}


def price_line(
    step: str,
    component: str,
    line: dict[str, Any],
    declared: dict[str, ModelParameters],
    rows: dict[str, dict[str, Any]],
    bands: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Tokens and cost of one model component line at the model developer's
    ratio: input plus or minus the declared band, billed output = visible /
    (1 - r) at r low, central and high, priced at the row's standard and
    Batch prices."""
    cpt = ratio(f"chars_per_token_{model_developer_of(COMPONENT_BACKEND[component])}")
    band = ratio("input_band")
    in_tokens = line["in_chars"] / cpt
    visible = line["out_chars"] / cpt
    billed = {level: visible / (1 - bands[component][level]) for level in LEVELS}
    in_scale = {"low": 1 - band, "central": 1.0, "high": 1 + band}
    row = rows[component]

    def usd(prefix: str) -> dict[str, float]:
        return {level: (in_tokens * in_scale[level] * row[prefix + "input"]
                        + billed[level] * row[prefix + "output"]) / 1e6 for level in LEVELS}

    max_tokens = line.get("max_chars", 0) / cpt
    if max_tokens >= CONTEXT_LIMIT_TOKENS:
        raise SystemExit(f"{step} ({component}): a request of {max_tokens:,.0f} tokens passes the "
                         f"{CONTEXT_LIMIT_TOKENS:,} token short-context limit the price row assumes")
    return {"step": step, "component": component, "model": declared[component].model_id, "calls": line["calls"],
            "in_tokens": in_tokens, "visible_tokens": visible, "billed": billed,
            "cost": usd(""), "batch_cost": usd("batch_"), "max_request_tokens": max_tokens}


def scaled(row: dict[str, Any], factor: int, step: str) -> dict[str, Any]:
    """The same row for factor repetitions."""
    out = dict(row, step=step, calls=row["calls"] * factor,
               in_tokens=row["in_tokens"] * factor, visible_tokens=row["visible_tokens"] * factor)
    out["billed"] = {k: v * factor for k, v in row["billed"].items()}
    out["cost"] = {k: v * factor for k, v in row["cost"].items()}
    out["batch_cost"] = {k: v * factor for k, v in row["batch_cost"].items()}
    return out


def sum_cost(rows: list[dict[str, Any]], key: str = "cost") -> dict[str, float]:
    return {level: sum(r[key][level] for r in rows) for level in LEVELS}


def compute(
    inputs: dict[str, Any],
    declared: dict[str, ModelParameters],
    rows: dict[str, dict[str, Any]],
    tmp_dir: Path,
    n_repetitions: int = ABLATION_REPETITIONS,
) -> dict[str, Any]:
    """Every dry run and every price: the data the report prints."""
    bands = reasoning_bands(inputs["reasoning_low"], inputs.get("measured"))
    extraction, candidates = extraction_lines(
        inputs["dump"], inputs["node_ids"], inputs["july_norms"], inputs["july_judge_runs"], tmp_dir)
    norms = [dict(n) for n in inputs["july_norms"]]
    _attach_source_text(norms, inputs["dump"])
    accepted = candidates * ratio("accepted_share")
    alignment = alignment_lines(norms, inputs["hleg_nodes"], inputs["assertions"],
                                inputs["alignment_judge_runs"], accepted, tmp_dir)
    proxy = alignment["rationale_proxy"]
    without = {
        "generator": dict(alignment["generator"],
                          out_chars=alignment["generator"]["out_chars"] - proxy["gen_out_chars"]),
        "judge": dict(alignment["judge"],
                      in_chars=alignment["judge"]["in_chars"] - proxy["judge_in_chars"]),
    }
    backlog = backlog_lines(inputs["backlog_norms"], CREDSCORE_DESCRIPTION, tmp_dir,
                            judge_reply_chars=inputs["judge_reply_chars"])
    elicitation = elicitation_line(inputs["ablation_items"], inputs["elicit_system_chars"],
                                   inputs["elicit_out_chars"])
    per_strategy, proxied = ablation_dry_run(
        inputs["ablation_items"], inputs["out_chars"], inputs["judge_reply_chars"], tmp_dir)
    ablation = ablation_lines(per_strategy)

    def price(step: str, lines: dict[str, Any], components: tuple[str, ...] = ("generator", "judge")):
        return [price_line(step, component, lines[component], declared, rows, bands) for component in components]

    proxy_rows = price("Layer 3 alignment", alignment)
    bare_rows = price("Layer 3 alignment", without)
    one_rep = price("E6 ablation, one repetition", ablation)
    build_rows = (
        price("Layer 2 extraction", extraction)
        + price("Layer 3 alignment", alignment)
        + price("Control backlog", backlog)
        + price("E6 elicitation", {"generator": elicitation}, ("generator",))
    )
    n_rows = [scaled(r, n_repetitions, f"E6 ablation, {n_repetitions} repetitions") for r in one_rep]
    total_rows = build_rows + n_rows
    result: dict[str, Any] = {
        "declared": declared, "rows": rows, "bands": bands, "measured": inputs.get("measured") or {}, "n": n_repetitions,
        "candidates": candidates, "accepted": accepted, "backlog_norms": len(inputs["backlog_norms"]),
        "build_rows": build_rows, "one_rep": one_rep, "n_rows": n_rows,
        "total": sum_cost(total_rows), "batch_total": sum_cost(total_rows, "batch_cost"),
        "one_rep_cost": sum_cost(one_rep), "per_strategy": per_strategy, "proxied": proxied,
        "rationale_bound": {"total_without": {
            level: sum_cost(total_rows)[level] - sum_cost(proxy_rows)[level] + sum_cost(bare_rows)[level]
            for level in LEVELS}},
        "elicit_note": inputs.get("elicit_note"), "full": None, "full_note": inputs.get("full_note"),
        "max_request_tokens": max(r["max_request_tokens"] for r in total_rows),
    }
    if inputs.get("full_items"):
        full_strategy, _ = ablation_dry_run(
            inputs["full_items"], inputs["out_chars"], inputs["judge_reply_chars"], tmp_dir)
        full_ablation = price("Full benchmark ablation, one run", ablation_lines(full_strategy))
        full_elicitation = price("Full benchmark elicitation", {"generator": elicitation_line(
            inputs["full_items"], inputs["elicit_system_chars"], inputs["elicit_out_chars"])},
            ("generator",))
        result["full"] = {
            "items": len(inputs["full_items"]),
            "scenarios": sum(1 for i in inputs["full_items"] if i["kind"] == "classification"),
            "ablation": sum_cost(full_ablation), "elicitation": sum_cost(full_elicitation),
        }
    return result


def _usd(value: float) -> str:
    return f"{value:,.2f}"


def _band(cost: dict[str, float]) -> str:
    return f"{_usd(cost['central'])} USD (band {_usd(cost['low'])} to {_usd(cost['high'])})"


def _step_row(row: dict[str, Any]) -> str:
    billed = row["billed"]
    return (f"| {row['step']} | {row['component']} ({row['model']}) | {round(row['calls']):,} "
            f"| {round(row['in_tokens']):,} | {round(row['visible_tokens']):,} "
            f"| {round(billed['central']):,} ({round(billed['low']):,} to {round(billed['high']):,}) "
            f"| {_usd(row['cost']['low'])} | {_usd(row['cost']['central'])} | {_usd(row['cost']['high'])} |")


def _backlog_judge_input_line(res: dict[str, Any]) -> str:
    """The backlog judge's input is counted over the dry run's one-control
    reply, so it leaves out the controls the generator writes, about the
    generator's visible output; the line says how much, the rows do not add it."""
    gen = next(r for r in res["build_rows"] if r["step"] == "Control backlog" and r["component"] == "generator")
    left_out = gen["visible_tokens"] * ratio("chars_per_token_openai") / ratio("chars_per_token_anthropic")
    usd = left_out * res["rows"]["judge"]["input"] / 1e6
    return (f"The backlog judge's input is counted over the dry run's one-control reply, not the controls the "
            f"generator writes, so it leaves out about {round(left_out):,} input tokens (the generator's visible "
            f"output), about {_usd(usd)} USD at the judge's input price, which the rows above do not add.")


STEP_HEADER = [
    "| Step | Model component (model) | Calls | Input tokens | Visible output tokens "
    "| Billed output tokens, central (low to high) | Low USD | Central USD | High USD |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
]


def _reasoning_share_lines(res: dict[str, Any], low_sources: dict[str, str]) -> list[str]:
    lines = []
    for component in ("generator", "judge"):
        b = res["bands"][component]
        found = res.get("measured", {}).get(component)
        if found:
            lines.append(f"- {component}: measured {found['share']:.3f} at every level (B133, {', '.join(found['files'])}; "
                         f"{found['replies']} replies; {found['reasoning']:,} reasoning tokens of "
                         f"{found['output']:,} output tokens).")
        else:
            lines.append(f"- {component}: low {b['low']:.3f} ({low_sources[component]}), central {b['central']:.2f} "
                         f"(reasoning_share_central above), high {b['high']:.2f} (reasoning_share_high above).")
    return lines


def render_report(res: dict[str, Any], low_sources: dict[str, str]) -> str:
    declared, rows, n = res["declared"], res["rows"], res["n"]
    lines = [
        "# Cost estimate for the B74 sequence (dry run)",
        "",
        "> Generated by scripts/estimate_benchmark_cost.py (B120). No model was called,",
        "> no API key was read and no network was touched. Every step ran the real",
        "> pipeline code with counting clients, so every prompt is the one a live run",
        "> sends. Token counts are characters over a ratio measured per model developer, and",
        "> output carries a declared reasoning band. This is an estimate, not a measurement.",
        "",
        "## Models and prices",
        "",
    ]
    for component in ("generator", "judge"):
        model, row = declared[component], rows[component]
        lines.append(
            f"- The {component} is {model.model_id} ({model.inference_backend}, effort {model.effort}): "
            f"{row['input']:.2f} USD in / {row['output']:.2f} USD out per MTok, Batch "
            f"{row['batch_input']:.2f} / {row['batch_output']:.2f}; "
            f"{row['pricing']['url']}, read {row['pricing']['read_on']}.")
    lines += [
        "",
        "Both ids come from the environment (TERE4AI_GENERATOR_MODEL and TERE4AI_JUDGE_MODEL),",
        "checked against config/model_parameters.json; the prices are in config/model_prices.json.",
        # the values the run read, so this script still names no model (B120)
        f"Regenerate with {GENERATOR_VARIABLE}={declared['generator'].model_id} and "
        f"{JUDGE_VARIABLE}={declared['judge'].model_id}",
        "exported: `.venv/bin/python scripts/estimate_benchmark_cost.py`; nothing else outside the",
        "tracked tree changes a figure: the repository's .env, when present, is loaded, but an exported",
        "variable wins over the file, and no other variable it may set reaches a figure.",
        "Input is priced uncached: the clients send no cache_control (Anthropic caches nothing)",
        "and record no cached tokens; automatic caching on the OpenAI side can only lower the figure.",
        f"Every request stays under {CONTEXT_LIMIT_TOKENS:,} input tokens (asserted; the largest is "
        f"{round(res['max_request_tokens']):,}), so the short-context prices apply. Standard tier.",
        "",
        "## Ratios and their sources",
        "",
    ]
    for name, r in RATIOS.items():
        lines.append(f"- {name} = {r['value']}: {r['source']}")
    lines += ["", "Reasoning share of billed output, r (billed output = visible reply / (1 - r)):", ""]
    lines += _reasoning_share_lines(res, low_sources)
    lines += [
        "- The backlog generator's central output is the one measured call scaled by the norms sent over the "
        "norms that call sent, see backlog_generator_billed_tokens and backlog_generator_measured_norms "
        "(a planning assumption, no source).",
        "",
        "## Steps, with the ablation at N = " + str(n),
        "",
        *STEP_HEADER,
    ]
    for row in res["build_rows"] + res["n_rows"]:
        lines.append(_step_row(row))
    lines += [
        "| Campaigns (Section 10.4) | none | 0 | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 |",
        "",
        "The control backlog prices one click on CredScore Article 25 sending every AI Act role's norms and "
        f"the norms whose addressee is not settled: {res['backlog_norms']} of the article's accepted norms in "
        "the aborted B74 extraction (spec G D-G82 (1)); the facade's real click also applies applicability "
        "by classification and target system category, which this offline selection does not.",
        _backlog_judge_input_line(res),
        "",
        "Campaigns: 0 USD. Creating and pinning the two campaigns makes no model call.",
        "",
        "## E6 ablation, one repetition",
        "",
        *STEP_HEADER,
    ]
    for row in res["one_rep"]:
        lines.append(_step_row(row))
    cost1 = res["one_rep_cost"]
    lines += [
        "",
        f"Per repetition (one repetition costs {_band(cost1)}). The total prices N = {n} "
        "repetitions, the research answer's provisional ten (B104 R5; ruling R5 of B120, "
        "provisional, awaiting Jose), so the figure errs high. At the pilot's N, take the total "
        f"and add (N minus {n}) times the one-repetition cost.",
        "",
        "Per-strategy dry-run counts of one repetition (visible output at the model developer ratio):",
        "",
        "| Strategy | Generator calls | Gen in-tokens | Gen out-tokens (visible) | Judge calls "
        "| Judge in-tokens | Judge out-tokens (visible) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    gen_dev = model_developer_of(COMPONENT_BACKEND["generator"])
    judge_dev = model_developer_of(COMPONENT_BACKEND["judge"])
    for name in STRATEGY_NAMES:
        s = res["per_strategy"][name]
        lines.append(
            f"| {name} | {s['gen_calls']} | {tokens(s['gen_in'], gen_dev):,} "
            f"| {tokens(s['gen_out'], gen_dev):,} | {s['judge_calls']} "
            f"| {tokens(s['judge_in'], judge_dev):,} | {tokens(s['judge_out'], judge_dev):,} |")
    lines.append("")
    if res["elicit_note"]:
        lines += [res["elicit_note"], ""]
    for name, proxy in res["proxied"].items():
        lines += [f"{name} was not run in run 2: its output uses the observed answer sizes of {proxy}.", ""]
    rb = res["rationale_bound"]
    lines += [
        "## Alignment rationale: a proxy, and the cost without it",
        "",
        "- A stored assertion's rationale is the judge's, not the generator's (the pipeline keeps the "
        "judge's on the assertion), and no record holds the generator's own reply (the logs keep hashes "
        "only). The alignment step therefore uses the judge's rationale as a proxy for the generator's, "
        "in the generator's output and in the judge's input. The direction of the proxy's error is "
        "unknown, because the generator's rationale is not recorded: it may be shorter or longer.",
        "- Sensitivity calculation, not a bound: the total without the rationale in both places is "
        f"{_usd(rb['total_without']['central'])} USD central ({_usd(rb['total_without']['low'])} low, "
        f"{_usd(rb['total_without']['high'])} high), against the stated total of "
        f"{_usd(res['total']['central'])} ({_usd(res['total']['low'])} low, "
        f"{_usd(res['total']['high'])} high).",
        "",
        "## Reference outside the total",
        "",
    ]
    if res["full"]:
        f = res["full"]
        lines.append(
            f"- Full benchmark ({f['items']} items), one ablation run: {_band(f['ablation'])}; "
            f"its elicitation of {f['scenarios']} scenarios: {_band(f['elicitation'])}. "
            "Outside the total (ruling R4): E6 is priced as spec G Section 10.4 states it, over the "
            "hand-made test set and the frozen sample.")
    else:
        lines.append(f"- Full benchmark: not computed ({res['full_note'] or 'no items'}).")
    lines += [
        "",
        "## Excluded",
        "",
        "- The calibration judge runs of spec F (ten instruments) are excluded: they run after the human "
        "grading (spec F D-F17 and D-F18; card B74's acceptance ends at \"both campaigns created and "
        "pinned\"), they price from the dashboard's own table (tere4ai-dashboard "
        "src/lib/experiment/prices.json) and they are a B68 cost.",
        "",
        "## Batch",
        "",
        f"- Batch (ruling R6): the same sequence at the Batch prices (50 percent on both inference backends) "
        f"would cost {_band(res['batch_total'])}. It is a lever and not in the total: the clients call "
        "the synchronous APIs.",
        "",
        "## Total",
        "",
        f"Total for the B74 sequence: {_usd(res['total']['central'])} USD "
        f"(band {_usd(res['total']['low'])} to {_usd(res['total']['high'])})",
        "",
        "The band takes the low input and the low reasoning share at its low end, and the high input and "
        f"the high reasoning share at its high end. It includes the ablation at N = {n}.",
        *(["A measured model component's reasoning share is the same at both ends of the band."]
          if res.get("measured") else []),
        "",
    ]
    return "\n".join(lines)


def load_inputs() -> dict[str, Any]:
    """Everything the estimate reads from the repository (no model, no key)."""
    dump = json.loads(ELICIT_DUMP.read_text(encoding="utf-8"))
    july_norms = json.loads(JULY_NORMS.read_text(encoding="utf-8"))
    july_alignments = json.loads(JULY_ALIGNMENTS.read_text(encoding="utf-8"))
    b74 = json.loads(B74_NORMS.read_text(encoding="utf-8"))
    elicit_out, elicit_note = elicitation_output_chars(json.loads(FEATURES.read_text(encoding="utf-8")))
    full_items, full_note = None, None
    if (BENCH_DIR / "scenarios.json").exists() and (BENCH_DIR / "qa_pairs.json").exists():
        payload_path = verify_full_benchmark()
        try:
            full_items = load_benchmark_items(payload_path)
        finally:
            payload_path.unlink(missing_ok=True)
    else:
        full_note = f"the full benchmark files are not in {BENCH_DIR.relative_to(ROOT)}"
    return {
        "dump": dump,
        "node_ids": core_node_ids(),
        "july_norms": july_norms["norms"],
        "july_judge_runs": july_norms["judge_runs"],
        "assertions": july_alignments["assertions"],
        "alignment_judge_runs": july_alignments["judge_runs"],
        "hleg_nodes": build_hleg_nodes(),
        "reasoning_low": default_reasoning_shares(b74),
        "ablation_items": load_gold_items() + load_benchmark_items(SAMPLE_PATH),
        "full_items": full_items,
        "full_note": full_note,
        "out_chars": observed_output_chars(),
        "judge_reply_chars": ratio("runtime_judge_reply_chars"),
        "elicit_system_chars": len(elicit_system_prompt()),
        "elicit_out_chars": elicit_out,
        "elicit_note": elicit_note,
        "backlog_norms": every_role_backlog_norms(b74["norms"], dump),
    }


LOW_SOURCE = ("measured at the API default in the aborted B74 extraction: billed output per call "
              "against the visible reply the stored norms and verdicts give, default_reasoning_shares")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--measured-usage", action="append", default=[], metavar="PATH",
                        help="a build record JSON whose usage carries reasoning_tokens (B133); repeatable")
    args = parser.parse_args([] if argv is None else argv)
    load_dotenv_once()
    declared = declared_models(os.environ)
    rows = price_rows(load_model_prices(), declared)
    measured = measured_reasoning([Path(p) for p in args.measured_usage], declared)
    inputs = load_inputs()
    inputs["measured"] = measured
    with tempfile.TemporaryDirectory() as tmp:
        result = compute(inputs, declared, rows, Path(tmp))
    report = render_report(result, {"generator": LOW_SOURCE, "judge": LOW_SOURCE})
    OUT_PATH.write_text(report, encoding="utf-8")
    print(f"Total for the B74 sequence: {_band(result['total'])}")
    print(f"wrote {OUT_PATH.relative_to(ROOT) if OUT_PATH.is_relative_to(ROOT) else OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

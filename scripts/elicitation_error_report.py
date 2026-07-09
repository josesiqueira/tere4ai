"""Root-cause report for the 3 real over-classifications in ablation run 2.

@implements: DEC-11
@grounded_by: REF-16

eval/results/RUN2_ANALYSIS.md identifies 3 real errors of the graph
strategies on the REF-15 benchmark sample: 2 items over-classified from
limited (transparency_only) to high_risk and 1 from high-risk to
prohibited, all traceable to elicited-flag strength. This script pins those
errors down against the existing artifacts, with ZERO model calls:

1. finds WHICH benchmark items they are (graph_build_judge results in
   eval/results/ablation_checkpoint.jsonl versus the benchmark gold);
2. pulls their elicited features (eval/gold/benchmark_features.json) and
   scenario text (eval/gold/benchmark_sample.json via the harness loader);
3. re-runs the deterministic classify_ai_system offline on the elicited
   features and reads the rule trace in answer.rationale to determine the
   triggering flag or domain;
4. re-runs the classifier with the suspect signal removed or corrected (a
   counterfactual, still deterministic and offline);
5. writes eval/results/ELICITATION_ERRORS.md.

The support/contradiction verdicts are analyst-authored, but every quoted
fragment is verified VERBATIM against the scenario text (or the layer1 node
text) at runtime, and the expected items, triggers, predicted categories,
and counterfactual outcomes are asserted against the artifacts; on any
mismatch the script fails loudly and writes nothing, so the report can
never drift from the data it claims to describe.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.harness import load_benchmark_items  # noqa: E402
from tere4ai.mcp_server.classify import classify_ai_system  # noqa: E402

CHECKPOINT_PATH = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
FEATURES_PATH = ROOT / "eval" / "gold" / "benchmark_features.json"
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
OUT_PATH = ROOT / "eval" / "results" / "ELICITATION_ERRORS.md"

STRATEGY = "graph_build_judge"

# The two real over-classification patterns from RUN2_ANALYSIS.md, in our
# closed vocabulary (benchmark "limited" maps to transparency_only).
OVER_CLASSIFICATION_PATTERNS = (
    ("transparency_only", "high_risk"),
    ("high_risk", "prohibited"),
)

TRIGGER_FLAG_RE = re.compile(r"rule \w+: flag ([\w+ ]+?) matches (\S+)")
TRIGGER_DOMAIN_RE = re.compile(r"rule high_risk: domain '(\w+)' matches [^(]*\((\S+)\)")

# Analyst-authored analysis, verified against the artifacts at runtime.
# Quotes must be verbatim substrings of the item's system_text; layer1
# quotes must be verbatim substrings of the cited node's dump text.
ANALYSIS: dict[str, dict[str, Any]] = {
    "bench:scenario:76": {
        "expected_gold": "high_risk",
        "expected_predicted": "prohibited",
        "expected_triggers": ["flag:predictive_policing_profiling"],
        "trigger_node": "eu-ai-act:article-5:paragraph-1:point-d",
        "trigger_node_quote": (
            "assess or predict the risk of a natural person committing a "
            "criminal offence, based solely on the profiling of a natural person"
        ),
        "support": "contradicted",
        "scenario_quotes": [
            "assess the risk of a person becoming a victim of violent crime"
        ],
        "assessment": (
            "The elicited flag predictive_policing_profiling is contradicted "
            "by the scenario text. Article 5(1)(d) prohibits predicting the "
            "risk of a natural person COMMITTING a criminal offence; the "
            "scenario assesses the risk of a person BECOMING A VICTIM of "
            "violent crime, so the assessed person is a potential victim, "
            "not a potential offender. The flag should have been omitted "
            "(or set false); law_enforcement_use alone already carries the "
            "correct signal."
        ),
        "counterfactual": {
            "change": "drop flags.predictive_policing_profiling",
            "expected_category": "high_risk",
            "note": (
                "with the unsupported flag removed, the ladder lands on "
                "Annex III point 6 (law enforcement) high_risk, which "
                "matches the benchmark gold"
            ),
        },
        "recommendation": (
            "Prompt v2: define predictive_policing_profiling with the "
            "operative Article 5(1)(d) wording (predicting the risk that a "
            "person will COMMIT a criminal offence, based solely on "
            "profiling or personality traits) and add a contrast example: "
            "victim-risk assessment for police resource allocation is "
            "law_enforcement_use, not predictive_policing_profiling."
        ),
    },
    "bench:scenario:159": {
        "expected_gold": "transparency_only",
        "expected_predicted": "high_risk",
        "expected_triggers": ["domain:critical_infrastructure"],
        "trigger_node": "eu-ai-act:annex-iii:point-2",
        "trigger_node_quote": (
            "safety components in the management and operation of critical "
            "digital infrastructure, road traffic, or in the supply of "
            "water, gas, heating or electricity"
        ),
        "support": "contradicted",
        "scenario_quotes": [
            "AI‑driven energy‑consumption advisory for residential "
            "users, offering tips to reduce bills",
            "Domain: Energy.",
        ],
        "assessment": (
            "The elicited domain value critical_infrastructure is an "
            "over-normalization the text does not support. The scenario says "
            "'Domain: Energy.' and describes a consumer advisory tool; "
            "Annex III point 2 covers safety components in the management "
            "and operation of the infrastructure itself, and nothing in the "
            "text says the system manages or operates energy supply. "
            "Consistently, the elicitor did NOT set the "
            "critical_infrastructure_safety flag; the bare domain string "
            "triggered the ladder's domain fallback. Secondary observation, "
            "not the trigger: flags.profiling_of_natural_persons = true "
            "sits badly against the input description 'Anonymised household "
            "electricity usage statistics'."
        ),
        "counterfactual": {
            "change": "set domain to 'consumer' (the supported reading)",
            "expected_category": "transparency_only",
            "note": (
                "with the domain read as consumer, the elicited "
                "interacts_with_natural_persons flag yields "
                "transparency_only, which matches the benchmark gold "
                "(limited)"
            ),
        },
        "recommendation": (
            "Prompt v2: constrain domain normalization: emit "
            "critical_infrastructure only when the system itself is used in "
            "the management or operation of the infrastructure; "
            "consumer-facing energy advice maps to consumer. Also instruct "
            "the elicitor to emit critical_infrastructure_safety: false "
            "when the described scope plainly rules it out, so the ladder "
            "can tell ruled-out from unknown."
        ),
    },
    "bench:scenario:161": {
        "expected_gold": "transparency_only",
        "expected_predicted": "high_risk",
        "expected_triggers": ["domain:education"],
        "trigger_node": "eu-ai-act:annex-iii:point-3",
        "trigger_node_quote": (
            "determine access or admission or to assign natural persons to "
            "educational and vocational training institutions"
        ),
        "support": "domain supported verbatim; the Annex III point 3 use it implies is not",
        "scenario_quotes": [
            "Domain: Education.",
            "helps students practice language skills through interactive exercises",
            "Natural language generation and assessment",
        ],
        "assessment": (
            "The elicited domain value education is supported verbatim "
            "('Domain: Education.'), so this is not a fabricated fact. The "
            "over-classification comes from the ladder's coarse domain "
            "fallback: Annex III point 3 targets access/admission decisions "
            "and the evaluation of learning outcomes, while the text "
            "describes a practice tool ('helps students practice language "
            "skills through interactive exercises'). The system_type does "
            "say 'Natural language generation and assessment', so whether "
            "its assessments steer or gate anything real is undecidable "
            "from the text alone; nothing states an access, admission, "
            "grading, or proctoring role. Note the elicitor also set "
            "preparatory_or_narrow_procedural_task = true with autonomy "
            "advisory, which correctly raised the Article 6(3) derogation "
            "candidate and routed the item to human review, the designed "
            "degradation path."
        ),
        "counterfactual": {
            "change": "add flags.education_scoring_or_access = false (explicit rule-out)",
            "expected_category": "transparency_only",
            "note": (
                "RESOLVED 2026-07-09: the original finding was that the "
                "ladder returned high_risk regardless of the explicit false "
                "flag, so a prompt-side fix alone could not repair this "
                "item. That finding drove a classifier change (commit "
                "23f3ec0): the Annex III domain fallback now yields when "
                "every specific flag of the category is explicitly false "
                "(unknown flags still match). The counterfactual now "
                "returns transparency_only, matching the benchmark gold."
            ),
        },
        "recommendation": (
            "Prompt v2: whenever the domain is education, require an "
            "explicit education_scoring_or_access decision: false when the "
            "described function is practice or support with no stated "
            "access, admission, grading, or proctoring role. Pair with a "
            "classifier change (out of prompt scope, recorded here): the "
            "Annex III domain fallback should not fire when the category's "
            "specific use flag is explicitly false."
        ),
    },
}


def load_strategy_results(path: Path, strategy: str) -> dict[str, dict[str, Any]]:
    """Merge the per-batch checkpoint records of one strategy."""
    results: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("strategy") == strategy:
            results.update(record.get("results", {}))
    return results


def find_over_classified(
    results: dict[str, dict[str, Any]],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Benchmark classification items matching the RUN2 over-classification
    patterns, each with gold, predicted, and the item dict."""
    found: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") != "classification":
            continue
        gold = (item.get("gold") or {}).get("risk_category")
        predicted = (results.get(item["id"]) or {}).get("risk_category")
        if (gold, predicted) in OVER_CLASSIFICATION_PATTERNS:
            found.append({"item": item, "gold": gold, "predicted": predicted})
    return found


def rule_trace_triggers(rationale: list[str]) -> list[str]:
    """Triggering signals from the classifier's rule trace, normalized to
    'flag:<name>' and 'domain:<value>' tokens."""
    triggers: list[str] = []
    for line in rationale:
        m = TRIGGER_FLAG_RE.search(line)
        if m:
            triggers.append(f"flag:{m.group(1).strip()}")
        m = TRIGGER_DOMAIN_RE.search(line)
        if m:
            triggers.append(f"domain:{m.group(1)}")
    return triggers


def apply_counterfactual(features: dict[str, Any], change: str) -> dict[str, Any]:
    """The three hand-specified counterfactual edits, applied structurally."""
    edited = copy.deepcopy(features)
    if change.startswith("drop flags."):
        edited["flags"].pop(change.removeprefix("drop flags."), None)
    elif change.startswith("set domain to "):
        edited["domain"] = change.split("'")[1]
    elif change.startswith("add flags.education_scoring_or_access = false"):
        edited["flags"]["education_scoring_or_access"] = False
    else:
        raise ValueError(f"unknown counterfactual change: {change!r}")
    return edited


def build_report(
    checkpoint_path: Path = CHECKPOINT_PATH,
    features_path: Path = FEATURES_PATH,
    layer1_path: Path = LAYER1_PATH,
) -> str:
    """Assemble the report, verifying every claim against the artifacts.

    Raises ValueError on any mismatch between the analyst-authored analysis
    and what the artifacts actually contain.
    """
    results = load_strategy_results(checkpoint_path, STRATEGY)
    items = load_benchmark_items()
    found = find_over_classified(results, items)

    found_ids = sorted(e["item"]["id"] for e in found)
    if found_ids != sorted(ANALYSIS):
        raise ValueError(
            f"over-classified items in the artifacts are {found_ids}, but the "
            f"authored analysis covers {sorted(ANALYSIS)}; refusing to write "
            "a report that does not match the data"
        )

    features_by_item = json.loads(features_path.read_text(encoding="utf-8"))["features_by_item"]
    dump = json.loads(layer1_path.read_text(encoding="utf-8"))
    layer1_index = {n["id"]: n for n in dump.get("nodes", []) if "id" in n}

    sections: list[str] = []
    for entry in sorted(found, key=lambda e: int(e["item"]["id"].rsplit(":", 1)[1])):
        item = entry["item"]
        item_id = item["id"]
        analysis = ANALYSIS[item_id]
        system_text = item.get("system_text") or ""
        features = features_by_item.get(item_id)
        if features is None:
            raise ValueError(f"{item_id}: no elicited features in {features_path}")

        # Verify gold and predicted against the artifacts.
        if entry["gold"] != analysis["expected_gold"]:
            raise ValueError(f"{item_id}: gold is {entry['gold']}, analysis expected "
                             f"{analysis['expected_gold']}")
        if entry["predicted"] != analysis["expected_predicted"]:
            raise ValueError(f"{item_id}: predicted is {entry['predicted']}, analysis "
                             f"expected {analysis['expected_predicted']}")

        # Re-run the deterministic classifier offline and read the trace.
        envelope = classify_ai_system(features, dump)
        answer = envelope["answer"]
        if answer["risk_category"] != entry["predicted"]:
            raise ValueError(
                f"{item_id}: offline classify_ai_system returns "
                f"{answer['risk_category']}, checkpoint has {entry['predicted']}"
            )
        triggers = rule_trace_triggers(answer["rationale"])
        if triggers != analysis["expected_triggers"]:
            raise ValueError(
                f"{item_id}: rule-trace triggers are {triggers}, analysis "
                f"expected {analysis['expected_triggers']}"
            )

        # Verify every quote verbatim.
        for quote in analysis["scenario_quotes"]:
            if quote not in system_text:
                raise ValueError(f"{item_id}: quote not verbatim in scenario text: {quote!r}")
        node = layer1_index.get(analysis["trigger_node"])
        if node is None or analysis["trigger_node_quote"] not in (node.get("text") or ""):
            raise ValueError(
                f"{item_id}: trigger node quote not verbatim in layer1 text of "
                f"{analysis['trigger_node']}"
            )

        # Counterfactual, still offline and deterministic.
        cf = analysis["counterfactual"]
        cf_answer = classify_ai_system(apply_counterfactual(features, cf["change"]), dump)["answer"]
        if cf_answer["risk_category"] != cf["expected_category"]:
            raise ValueError(
                f"{item_id}: counterfactual '{cf['change']}' returns "
                f"{cf_answer['risk_category']}, analysis expected {cf['expected_category']}"
            )

        flags_line = ", ".join(f"{k}={v}" for k, v in (features.get("flags") or {}).items())
        quote_lines = "\n".join(f"> {q}" for q in analysis["scenario_quotes"])
        trace_lines = "\n".join(f"- `{line}`" for line in answer["rationale"])
        sections.append(
            f"## {item_id}\n"
            f"\n"
            f"- Benchmark gold: `{entry['gold']}` "
            f"(benchmark label '{'limited' if entry['gold'] == 'transparency_only' else 'high-risk'}')\n"
            f"- Predicted ({STRATEGY}): `{entry['predicted']}`\n"
            f"- Elicited domain: `{features.get('domain')}`; elicited flags: {flags_line}\n"
            f"- Triggering signal(s): {', '.join(f'`{t}`' for t in triggers)} "
            f"citing `{analysis['trigger_node']}`\n"
            f"\n"
            f"### Scenario text\n"
            f"\n"
            f"> {system_text}\n"
            f"\n"
            f"### Rule trace (classify_ai_system, offline re-run)\n"
            f"\n"
            f"{trace_lines}\n"
            f"\n"
            f"### Does the scenario text support the triggering signal?\n"
            f"\n"
            f"Verdict: {analysis['support']}.\n"
            f"\n"
            f"Decisive fragments, verbatim:\n"
            f"\n"
            f"{quote_lines}\n"
            f"\n"
            f"Triggering provision text ({analysis['trigger_node']}), verbatim fragment:\n"
            f"\n"
            f"> {analysis['trigger_node_quote']}\n"
            f"\n"
            f"{analysis['assessment']}\n"
            f"\n"
            f"### Counterfactual (offline, deterministic)\n"
            f"\n"
            f"Change: {cf['change']}. Result: `{cf_answer['risk_category']}`. "
            f"{cf['note']}.\n"
            f"\n"
            f"### Prompt v2 recommendation\n"
            f"\n"
            f"{analysis['recommendation']}\n"
        )

    header = (
        "# Elicitation error report: the 3 real over-classifications of run 2\n"
        "\n"
        "> GENERATED by scripts/elicitation_error_report.py from existing\n"
        "> artifacts only (ablation_checkpoint.jsonl, benchmark_sample.json,\n"
        "> benchmark_features.json, layer1.json). Zero model calls: the\n"
        "> classifier re-runs are the deterministic rule ladder, and every\n"
        "> quoted fragment is machine-verified verbatim against its source\n"
        "> before this file is written. Support verdicts and recommendations\n"
        "> are analyst-authored (see RUN2_ANALYSIS.md for the run context).\n"
        "\n"
        "The three items are the 'real over-classification' cells of the\n"
        "RUN2_ANALYSIS.md confusion table: 2 limited -> high_risk and 1\n"
        "high-risk -> prohibited, strategy graph_build_judge (the graph\n"
        "strategies answered identically on these items).\n"
        "\n"
        "Summary: one error (scenario 76) is a genuinely unsupported elicited\n"
        "flag; one (scenario 159) is an over-normalized domain value; one\n"
        "(scenario 161) is a faithful domain plus a too-coarse Annex III\n"
        "domain fallback in the deterministic ladder, which a prompt fix\n"
        "alone cannot repair.\n"
    )
    return header + "\n" + "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    try:
        report = build_report()
    except (ValueError, FileNotFoundError) as exc:
        print(f"refusing to write the report: {exc}")
        return 1
    args.out.write_text(report, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

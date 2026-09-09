#!/usr/bin/env python3
"""Generate COMPLIANCE.md for a HIGH-RISK demo system from live MCP answers.

Written 2026-08-26. Produced demo-systems/highrisk_for_audience/COMPLIANCE.md
and tere4ai2/demo/mcp_demo/projects/credscore/COMPLIANCE.md.

Drives the real server over stdio, classifies, fetches all judge-accepted
requirements, and renders the obligation map grouped by article. Every article,
norm id, span id and count is copied out of an envelope, so the document cannot
state a figure the server did not answer.

Usage: .venv/bin/python scripts/make_compliance.py [out_path]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "demo" / "mcp_demo" / "projects" / "credscore" / "COMPLIANCE.md"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
DUMP = OUT.with_suffix(".envelopes.json")

sys.path.insert(0, str(ROOT / "src"))
from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402

FEATURES: dict[str, Any] = {
    "description": (
        "CredScore, a creditworthiness scoring service for a small consumer loan fintech. "
        "It evaluates the creditworthiness of natural persons applying for consumer loans, "
        "producing a score and a recommendation that loan officers use in their decisions and "
        "can override. Inputs are application data, income, and payment history. It is intended "
        "by its provider for exactly this purpose and is not a fraud detection tool. It profiles "
        "natural persons. The deployer is a private company under EU jurisdiction providing an "
        "essential private service, consumer credit."
    ),
    "domain": "consumer credit and lending",
    "purposes": [
        "evaluate the creditworthiness of natural persons applying for consumer loans",
        "produce a score and an approve, review, or decline recommendation for loan officers",
    ],
    "autonomy": "advisory",
    "affected_persons": ["natural persons applying for consumer loans"],
    "deployer_actor": "deployer",
    "deployer": {
        "body_governed_by_public_law": False,
        "private_entity_providing_public_services": True,
    },
    "flags": {
        "creditworthiness_evaluation": True,
        "essential_services_access": True,
        "profiling_of_natural_persons": True,
        "supports_human_assessment_on_verifiable_facts": False,
        "preparatory_or_narrow_procedural_task": False,
        "improves_previous_human_activity": False,
        "detects_patterns_without_replacing_human_assessment": False,
        "emotion_recognition": False,
        "emotion_recognition_workplace_or_education": False,
        "emotion_recognition_medical_or_safety": False,
        "biometric_identification": False,
        "biometric_categorisation": False,
        "biometric_categorisation_lawful_or_law_enforcement": False,
        "real_time_remote_biometric_public": False,
        "rtrb_strictly_necessary_authorised": False,
        "subliminal_or_manipulative": False,
        "exploits_vulnerabilities": False,
        "social_scoring": False,
        "social_score_detrimental_treatment": False,
        "predictive_policing_profiling": False,
        "facial_image_scraping": False,
        "causes_significant_harm": False,
        "critical_infrastructure_safety": False,
        "education_scoring_or_access": False,
        "employment_decisions": False,
        "life_health_insurance_risk_pricing": False,
        "law_enforcement_use": False,
        "migration_asylum_border_use": False,
        "justice_democratic_use": False,
        "medical_or_safety_component": False,
        "annex_i_covered_product": False,
        "third_party_conformity_assessment_required": False,
        "interacts_with_natural_persons": False,
        "generates_synthetic_content": False,
    },
}

# Flags the README does not literally settle, set from what it does say. Each
# one is reported in COMPLIANCE.md rather than left silent, because a flag set
# by inference is exactly the kind of fact a reviewer must be able to challenge.
ASSUMPTIONS = [
    (
        "flags.essential_services_access",
        "true",
        "the README calls consumer credit an essential private service provided by the deployer",
    ),
    (
        "flags.supports_human_assessment_on_verifiable_facts",
        "false",
        "the service issues a score and a recommendation, not a check of verifiable facts, so the "
        "Article 6(3) carve-out was not claimed",
    ),
    (
        "flags.preparatory_or_narrow_procedural_task",
        "false",
        "scoring an application is the substantive assessment, not a preparatory or narrow "
        "procedural step",
    ),
    (
        "flags.improves_previous_human_activity",
        "false",
        "the README does not describe the service as improving an already completed human activity",
    ),
    (
        "flags.detects_patterns_without_replacing_human_assessment",
        "false",
        "the recommendation feeds the loan officer's decision directly, so it was not treated as "
        "pattern detection outside the assessment",
    ),
    (
        "flags.annex_i_covered_product",
        "false",
        "the README describes a standalone service, not a safety component of an Annex I product",
    ),
    (
        "flags.third_party_conformity_assessment_required",
        "false",
        "not stated in the README; it follows from the conformity route, which is not settled here",
    ),
    (
        "deployer.private_entity_providing_public_services",
        "true",
        "the README says the deployer is a private company providing an essential private service",
    ),
]


def _envelope_of(result: Any) -> dict[str, Any]:
    """The tool's return value, whichever way this fastmcp version hands it back."""
    for attr in ("structured_content", "data"):
        value = getattr(result, attr, None)
        if isinstance(value, dict) and "status" in value:
            return value
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise SystemExit(f"cannot read an envelope out of {result!r}")


def _article_sort_key(name: str) -> int:
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 0


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip() or "not recorded"


def render(classify: dict[str, Any], requirements: dict[str, Any]) -> str:
    c_answer = classify.get("answer") or {}
    r_answer = requirements.get("answer") or {}
    summary = r_answer.get("summary") or {}
    per_article = summary.get("per_article") or {}
    by_article = r_answer.get("requirements_by_article") or {}
    fria = c_answer.get("fria") or {}
    status = requirements.get("status")

    lines: list[str] = []
    add = lines.append

    add("# CredScore, EU AI Act obligation map")
    add("")
    add(
        "Generated from live TERE4AI MCP answers. Nothing below is legal advice; see the "
        "notice at the end, which is the server's own wording."
    )
    add("")
    add(f"- graph version: `{classify.get('graph_version')}`")
    add(f"- classified at: {classify.get('generated_at')}")
    add(f"- requirements fetched at: {requirements.get('generated_at')}")
    add("")

    add("## Classification")
    add("")
    add(f"- risk category: **{c_answer.get('risk_category')}**")
    add(f"- prohibited: {c_answer.get('prohibited')}")
    add(f"- Annex III category: `{c_answer.get('annex_iii_category')}`")
    add(f"- envelope status: `{classify.get('status')}`, confidence {classify.get('confidence')}")
    add(f"- Article 6(3) exception candidate: {c_answer.get('article_6_3_exception_candidate')}")
    add("")
    add("Rule trace returned by the server:")
    add("")
    for item in c_answer.get("rationale") or []:
        add(f"- {item}")
    add("")
    add("Cited nodes:")
    add("")
    for node in classify.get("source_nodes") or []:
        add(f"- `{node}`")
    add("")

    add("## Article 27 fundamental rights impact assessment")
    add("")
    add(f"- applicability: **{fria.get('applicability')}**")
    for item in fria.get("rationale") or []:
        add(f"- {item}")
    applies_from = fria.get("applies_from") or {}
    if applies_from:
        add(
            f"- applies from {applies_from.get('date')} "
            f"(`{applies_from.get('legal_status')}`, source {applies_from.get('source')})"
        )
    add("")

    add("## Scope of the backlog")
    add("")
    add(f"- judge-accepted requirements in scope: **{summary.get('total_accepted_in_scope')}**")
    add(f"- returned in this fetch: {summary.get('returned')}")
    add(f"- articles touched: {len(per_article)}")
    add(f"- norms still in the human review queue, never served: {summary.get('needs_human_review_total')}")
    add(f"- calibrated status carried by every row below: `{status}`")
    add("")
    add(
        "That status is the honest one for a codebase that has submitted no artifacts. The "
        "obligation applies and no evidence has been offered for it yet. Nothing here says "
        "satisfied, compliant, or certified."
    )
    add("")
    add("| article | accepted | in review queue |")
    add("| --- | ---: | ---: |")
    for name in sorted(per_article, key=_article_sort_key):
        counts = per_article[name] or {}
        add(f"| {name} | {counts.get('accepted')} | {counts.get('needs_human_review')} |")
    add("")

    add("## Obligations by article")
    add("")
    for name in sorted(by_article, key=_article_sort_key):
        norms = by_article[name] or []
        add(f"### {name} ({len(norms)} requirements)")
        add("")
        add("| norm id | type | actor | modal | action | object | source span |")
        add("| --- | --- | --- | --- | --- | --- | --- |")
        for norm in norms:
            add(
                "| `{norm_id}` | {deontic} | {actor} | {modal} | {action} | {obj} | `{span}` |".format(
                    norm_id=_cell(norm.get("norm_id")),
                    deontic=_cell(norm.get("deontic_type")),
                    actor=_cell(norm.get("actor")),
                    modal=_cell(norm.get("modal")),
                    action=_cell(norm.get("action")),
                    obj=_cell(norm.get("object")),
                    span=_cell(norm.get("source_span_id")),
                )
            )
        add("")

    add("## Facts that could not be settled from the README")
    add("")
    missing = classify.get("missing_facts") or []
    if missing:
        for fact in missing:
            add(f"- {fact}")
    else:
        add(
            "The server reported no missing facts: every prohibition-relevant and Annex III "
            "relevant flag was answered. That is not the same as every fact being stated "
            "outright in the README. The flags below were set by inference from what it does "
            "say, and each one is open to challenge."
        )
    add("")
    add("| flag | set to | why |")
    add("| --- | --- | --- |")
    for flag, value, why in ASSUMPTIONS:
        add(f"| `{flag}` | {value} | {why} |")
    add("")
    add("Facts the README does not settle at all, and which this document does not assert:")
    add("")
    add("- whether the provider has a quality management system in place (Article 17)")
    add("- whether training, validation and testing data sets exist and how they were governed (Article 10)")
    add("- whether the service is already placed on the market or still in development (Articles 16, 43, 49)")
    add("- whether the deployer is a financial institution under Union financial services law (Article 26(6))")
    add("- the conformity assessment route and whether a notified body is involved (Article 43)")
    add("")

    add("## Notice")
    add("")
    add(f"> {classify.get('non_legal_advice_notice')}")
    add("")
    add(
        "This document maps obligations. It does not implement, satisfy, or discharge any of "
        "them, and it is not a conformity assessment."
    )
    add("")
    return "\n".join(lines)


async def main() -> int:
    transport = StdioTransport(
        command=str(ROOT / ".venv" / "bin" / "python"),
        args=["-m", "tere4ai.mcp_server.server"],
        cwd=str(ROOT),
    )
    async with Client(transport) as client:
        classify = _envelope_of(await client.call_tool("classify_ai_system", {"features": FEATURES}))
        requirements = _envelope_of(
            await client.call_tool(
                "get_applicable_requirements",
                {"classification": classify},
            )
        )

    DUMP.write_text(json.dumps({"classify": classify, "requirements": requirements}, indent=2), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(classify, requirements), encoding="utf-8")

    summary = (requirements.get("answer") or {}).get("summary") or {}
    print(f"wrote {OUT}")
    print(f"risk_category={(classify.get('answer') or {}).get('risk_category')}")
    print(f"returned={summary.get('returned')} of {summary.get('total_accepted_in_scope')}")
    print(f"articles={len(summary.get('per_article') or {})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

#!/usr/bin/env python3
"""Generate COMPLIANCE.md for a PROHIBITED demo system from live MCP answers.

Written 2026-08-26. Produced demo-systems/unacceptablerisk_for_audience/COMPLIANCE.md.

A prohibited system receives zero engineering requirements, so this renders NO
backlog and NO obligation matrix at all: an empty table would invite a reader to
fill it in. It records the prohibition, its verbatim source text, and the
exception that was checked and ruled out. Two classification rounds are kept on
purpose so the missing-facts round trip is visible.

Refuses to write the file if a prohibited system ever returns a nonzero
requirement count (the DEC-08 gate this document relies on).

Usage: .venv/bin/python scripts/make_prohibition.py [out_path]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(
    os.environ.get(
        "TERE4AI_PROHIBITION_OUT",
        ROOT.parent / "demo-systems" / "unacceptablerisk_for_audience" / "COMPLIANCE.md",
    )
)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
DUMP = OUT.with_suffix(".envelopes.json")

sys.path.insert(0, str(ROOT / "src"))
from fastmcp import Client  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402

DESCRIPTION = (
    "MoodWatch, an employee wellbeing dashboard for a mid sized employer. It analyses "
    "employees' facial expressions from webcam feeds and their typing patterns to infer "
    "emotional state (stress, frustration, engagement) during work hours, and aggregates the "
    "result into dashboards visible to management. Participation is a condition of employment."
)
PURPOSES = [
    "infer employee emotional state from facial expressions and keystroke dynamics",
    "aggregate inferred emotion into team level dashboards for management",
    "productivity and wellbeing monitoring",
]

# Round 1: only what a developer would volunteer from a first read. The
# medical-or-safety exception is deliberately absent, because that is the fact
# the ladder must refuse to guess.
ROUND_1: dict[str, Any] = {
    "description": DESCRIPTION,
    "domain": "workplace monitoring and HR wellbeing analytics",
    "purposes": PURPOSES,
    "autonomy": "advisory",
    "affected_persons": ["employees of the deploying employer"],
    "deployer_actor": "deployer",
    "flags": {
        "emotion_recognition": True,
        "emotion_recognition_workplace_or_education": True,
        "profiling_of_natural_persons": True,
    },
}

# Round 2: the same system with every fact the README states, including the
# things it says the product is not.
ROUND_2: dict[str, Any] = {
    "description": DESCRIPTION
    + " It is not a medical device and is not deployed for safety reasons; the stated purpose is "
    "productivity and wellbeing monitoring. Provider and deployer are private companies "
    "established in the EU.",
    "domain": "workplace monitoring and HR wellbeing analytics",
    "purposes": PURPOSES,
    "autonomy": "advisory",
    "affected_persons": ["employees of the deploying employer"],
    "deployer_actor": "deployer",
    "deployer": {
        "body_governed_by_public_law": False,
        "private_entity_providing_public_services": False,
    },
    "flags": {
        "emotion_recognition": True,
        "emotion_recognition_workplace_or_education": True,
        "emotion_recognition_medical_or_safety": False,
        "profiling_of_natural_persons": True,
        "subliminal_or_manipulative": False,
        "exploits_vulnerabilities": False,
        "social_scoring": False,
        "social_score_detrimental_treatment": False,
        "predictive_policing_profiling": False,
        "facial_image_scraping": False,
        "biometric_categorisation": False,
        "biometric_categorisation_lawful_or_law_enforcement": False,
        "real_time_remote_biometric_public": False,
        "rtrb_strictly_necessary_authorised": False,
        "biometric_identification": False,
        "critical_infrastructure_safety": False,
        "education_scoring_or_access": False,
        "employment_decisions": False,
        "essential_services_access": False,
        "creditworthiness_evaluation": False,
        "life_health_insurance_risk_pricing": False,
        "law_enforcement_use": False,
        "migration_asylum_border_use": False,
        "justice_democratic_use": False,
        "medical_or_safety_component": False,
        "annex_i_covered_product": False,
        "third_party_conformity_assessment_required": False,
        "interacts_with_natural_persons": False,
        "generates_synthetic_content": False,
        "causes_significant_harm": False,
    },
}

# Flags the README does not word as flags, set from what it does say. Each is
# listed in the document so a reviewer can attack any one of them.
ASSUMPTIONS = [
    (
        "flags.emotion_recognition_workplace_or_education",
        "true",
        "the README says emotional state is inferred from employees during work hours",
    ),
    (
        "flags.emotion_recognition_medical_or_safety",
        "false",
        "the README states the product is not a medical device and is not deployed for safety "
        "reasons; this is the fact that decides the point (f) exception",
    ),
    (
        "flags.employment_decisions",
        "false",
        "the README describes a management dashboard, not a system making employment decisions; "
        "note that participation being a condition of employment is a separate matter",
    ),
    (
        "flags.biometric_categorisation",
        "false",
        "the README describes emotion inference, not sorting people into categories by biometric "
        "data",
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


def render(
    round_1: dict[str, Any],
    round_2: dict[str, Any],
    requirements: dict[str, Any],
    trace: dict[str, Any],
    span: dict[str, Any],
) -> str:
    a1 = round_1.get("answer") or {}
    a2 = round_2.get("answer") or {}
    r_answer = requirements.get("answer") or {}
    t_answer = trace.get("answer") or {}
    s_answer = span.get("answer") or {}
    fria = a2.get("fria") or {}

    returned = (r_answer.get("summary") or {}).get("returned")
    if returned not in (0, None):
        raise SystemExit(
            f"refusing to render: a prohibited system returned {returned} requirements, "
            "which contradicts the gate this document relies on"
        )

    lines: list[str] = []
    add = lines.append

    add("# MoodWatch, EU AI Act prohibition record")
    add("")
    add(
        "Generated from live TERE4AI MCP answers. Nothing below is legal advice; see the "
        "notice at the end, which is the server's own wording."
    )
    add("")
    add(f"- graph version: `{round_2.get('graph_version')}`")
    add(f"- classified at: {round_2.get('generated_at')}")
    add("")

    add("## Outcome")
    add("")
    add(f"- risk category: **{a2.get('risk_category')}**")
    add(f"- prohibited: **{a2.get('prohibited')}**")
    add(f"- envelope status: `{round_2.get('status')}`, confidence {round_2.get('confidence')}")
    add(f"- engineering requirements returned: **{returned}**")
    add("")
    add(
        "There is no requirement backlog in this document, and its absence is the finding. "
        "Placing on the market, putting into service, and use are banned, so no engineering "
        "work can make this system permissible. An empty obligations table would invite "
        "someone to fill it in."
    )
    add("")
    add("Rule trace returned by the server:")
    add("")
    for item in a2.get("rationale") or []:
        add(f"- {item}")
    add("")

    add("## The prohibition")
    add("")
    for node in round_2.get("source_nodes") or []:
        add(f"- node: `{node}`")
    for note in round_2.get("legal_status_notes") or []:
        add(f"- {note}")
    add("")
    add("Verbatim source text, resolved from the frozen snapshot:")
    add("")
    add(f"- span id: `{s_answer.get('span_id')}`")
    add(f"- snapshot file: `{s_answer.get('snapshot_file')}`")
    add(f"- sha256: `{s_answer.get('sha256')}`")
    add(f"- byte range: {s_answer.get('start')} to {s_answer.get('end')}")
    add(f"- checksum verified: {s_answer.get('found')}")
    add("")
    text = (s_answer.get("text") or "").strip()
    add("```xml")
    add(text)
    add("```")
    add("")
    excerpt = (t_answer.get("excerpt") or "").strip()
    if excerpt:
        add(f"`source_trace` on the same node returns the same slice (anchor `{t_answer.get('anchor')}`),")
        add(
            f"excerpt {t_answer.get('excerpt_chars')} of {t_answer.get('span_chars')} characters, "
            f"truncated: {t_answer.get('excerpt_truncated')}."
        )
        add("")

    add("## The exception, checked and ruled out")
    add("")
    add(
        "Point (f) bans emotion inference in the workplace **except where the use of the AI "
        "system is intended to be put in place or into the market for medical or safety "
        "reasons**. That exception is the whole question, so the ladder refuses to assume it "
        "either way."
    )
    add("")
    add(
        "A first classification was run with only the facts a developer would volunteer, leaving "
        "the exception unstated. It did not answer:"
    )
    add("")
    add(f"- risk category returned: `{a1.get('risk_category')}`")
    add(f"- status: `{round_1.get('status')}`, confidence {round_1.get('confidence')}")
    add(f"- unknown facts reported: {len(round_1.get('missing_facts') or [])}")
    add("")
    deciding = [f for f in (round_1.get("missing_facts") or []) if "point (f)" in f]
    for fact in deciding:
        add(f"> {fact}")
        add("")
    add(
        "The README answers it: not a medical device, not deployed for safety reasons. With that "
        "fact supplied, the second classification prohibits at confidence "
        f"{round_2.get('confidence')} with no exception left to resolve."
    )
    add("")

    add("## Article 27 fundamental rights impact assessment")
    add("")
    add(f"- applicability: **{fria.get('applicability')}**")
    for item in fria.get("rationale") or []:
        add(f"- {item}")
    add("")

    add("## What the requirements call returned")
    add("")
    add(f"- requirements returned: **{returned}**")
    add(f"- envelope status: `{requirements.get('status')}`, confidence {requirements.get('confidence')}")
    add("")
    add("Server message, verbatim:")
    add("")
    add(f"> {r_answer.get('message')}")
    add("")
    for note in requirements.get("legal_status_notes") or []:
        add(f"- {note}")
    add("")

    add("## Facts that could not be settled from the README")
    add("")
    missing = round_2.get("missing_facts") or []
    if missing:
        for fact in missing:
            add(f"- {fact}")
    else:
        add(
            "The server reported no missing facts on the second round: every "
            "prohibition-relevant and Annex III relevant flag was answered. That is not the "
            "same as every fact being worded as a flag in the README. The ones below were set "
            "by inference from what it does say, and each is open to challenge."
        )
    add("")
    add("| flag | set to | why |")
    add("| --- | --- | --- |")
    for flag, value, why in ASSUMPTIONS:
        add(f"| `{flag}` | {value} | {why} |")
    add("")
    add("Facts the README does not settle at all, and which this document does not assert:")
    add("")
    add("- whether any employee consent was sought, and whether it could be freely given at work")
    add("- whether the system has already been placed on the market or put into service")
    add("- what other Union law applies to the same processing, in particular data protection law")
    add("- whether a variant of the same engine could be lawful in a different deployment context")
    add("")

    add("## What to do with this")
    add("")
    add(
        "Stop, and take this to legal review. The correct engineering action is to not build the "
        "system, not to build it carefully. A redesign that removes emotion inference from the "
        "workplace, or a deployment genuinely intended for medical or safety reasons, is a "
        "different system and needs its own classification."
    )
    add("")

    add("## Notice")
    add("")
    add(f"> {round_2.get('non_legal_advice_notice')}")
    add("")
    add(
        "This document records a classification. It is not a legal determination, a conformity "
        "assessment, or a substitute for competent-authority interpretation."
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
        round_1 = _envelope_of(await client.call_tool("classify_ai_system", {"features": ROUND_1}))
        round_2 = _envelope_of(await client.call_tool("classify_ai_system", {"features": ROUND_2}))
        requirements = _envelope_of(
            await client.call_tool("get_applicable_requirements", {"classification": round_2})
        )
        node = (round_2.get("source_nodes") or ["eu-ai-act:article-5:paragraph-1:point-f"])[0]
        trace = _envelope_of(await client.call_tool("source_trace", {"node_id": node}))
        span_id = (round_2.get("source_spans") or [{}])[0].get("span_id")
        span = _envelope_of(await client.call_tool("resolve_span", {"span_id": span_id}))

    DUMP.write_text(
        json.dumps(
            {
                "round_1": round_1,
                "round_2": round_2,
                "requirements": requirements,
                "source_trace": trace,
                "resolve_span": span,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(round_1, round_2, requirements, trace, span), encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"round 1: {(round_1.get('answer') or {}).get('risk_category')} / {round_1.get('status')} "
          f"/ confidence {round_1.get('confidence')} / {len(round_1.get('missing_facts') or [])} missing facts")
    print(f"round 2: {(round_2.get('answer') or {}).get('risk_category')} / {round_2.get('status')} "
          f"/ confidence {round_2.get('confidence')}")
    print(f"requirements returned: {((requirements.get('answer') or {}).get('summary') or {}).get('returned')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

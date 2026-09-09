#!/usr/bin/env python3
"""Record the four demo-tier MCP sessions used by the web MCP demo page.

@implements: DEC-08, DEC-15
@grounded_by: ADD-14, ADD-15

Drives the real TERE4AI MCP server over stdio (the same transport a coding
agent uses) with the honest facts of the four demo systems in
demo-systems/, and writes one session JSONL per system in the contract
tere4ai.report.ingest expects: seq, ts, tool, request, envelope, repo_ref.

Nothing here decides anything. Every recorded answer is whatever the server
returned; the script only chooses which questions to ask and in what order.
The `@implements` tags fed to trace_implementation are scanned CLIENT-SIDE
from the working copies under demo/mcp_demo/projects, because the server
never reads a consumer filesystem.

Only free deterministic tools are called: classify_ai_system,
get_applicable_requirements, trace_implementation, explain_requirement,
source_trace and resolve_span. No paid model call is made.

Usage:
    python scripts/record_mcp_demo.py [--out-dir demo/mcp_demo/sessions]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from tere4ai.trace_scan import scan_tags

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "demo" / "mcp_demo" / "projects"
DEFAULT_OUT = ROOT / "demo" / "mcp_demo" / "sessions"

# One entry per recorded session. `features_rounds` is a list because a real
# agent run asks more than once: the first call reports the facts it is
# missing, the agent answers them from the README, and asks again. Both
# rounds are recorded, so the report shows the superseded first answer.
SYSTEMS: list[dict[str, Any]] = [
    {
        "key": "minimalrisk",
        "project": None,
        "features_rounds": [
            {
                "description": (
                    "SpamGuard: an email spam and phishing filter deployed by a "
                    "20 person company for its own shared inboxes. It classifies "
                    "incoming email as ham, spam, or phishing from message text "
                    "and metadata; likely spam moves to a retrievable quarantine "
                    "folder and suspected phishing links are flagged for the IT "
                    "admin. It never blocks, deletes, or answers mail on its own."
                ),
                "domain": "consumer",
                "purposes": [
                    "classify incoming email as ham, spam, or phishing",
                    "quarantine likely spam for later retrieval",
                    "flag suspected phishing links for the IT admin",
                ],
                "autonomy": "advisory",
                "flags": {
                    "profiling_of_natural_persons": False,
                    "biometric_identification": False,
                    "biometric_categorisation": False,
                    "emotion_recognition": False,
                    "emotion_recognition_workplace_or_education": False,
                    "social_scoring": False,
                    "subliminal_or_manipulative": False,
                    "exploits_vulnerabilities": False,
                    "predictive_policing_profiling": False,
                    "facial_image_scraping": False,
                    "real_time_remote_biometric_public": False,
                    "law_enforcement_use": False,
                    "migration_asylum_border_use": False,
                    "justice_democratic_use": False,
                    "education_scoring_or_access": False,
                    "employment_decisions": False,
                    "essential_services_access": False,
                    "creditworthiness_evaluation": False,
                    "life_health_insurance_risk_pricing": False,
                    "critical_infrastructure_safety": False,
                    "medical_or_safety_component": False,
                    "annex_i_covered_product": False,
                    "interacts_with_natural_persons": False,
                    "generates_synthetic_content": False,
                },
                "affected_persons": ["employees of the deploying company"],
                "deployer_actor": "private_company",
                "deployer": {
                    "body_governed_by_public_law": False,
                    "private_entity_providing_public_services": False,
                },
            }
        ],
        "source_trace": ["eu-ai-act:article-6:paragraph-2"],
        "explain": [],
    },
    {
        "key": "limitedrisk",
        "project": PROJECTS / "shopbot",
        "features_rounds": [
            {
                "description": (
                    "ShopBot: an LLM backed customer support chat assistant "
                    "embedded in a webshop. Site visitors type questions; it "
                    "answers about order status, return policy, and product "
                    "details, and escalates to a human agent on request or when "
                    "unsure. It interacts directly with natural persons and "
                    "generates text."
                ),
                "domain": "consumer",
                "purposes": [
                    "answer visitor questions about orders, returns and products",
                    "escalate to a human agent on request or when unsure",
                ],
                "autonomy": "advisory",
                "flags": {
                    "interacts_with_natural_persons": True,
                    "generates_synthetic_content": True,
                    "profiling_of_natural_persons": False,
                    "biometric_identification": False,
                    "biometric_categorisation": False,
                    "emotion_recognition": False,
                    "emotion_recognition_workplace_or_education": False,
                    "social_scoring": False,
                    "subliminal_or_manipulative": False,
                    "exploits_vulnerabilities": False,
                    "predictive_policing_profiling": False,
                    "facial_image_scraping": False,
                    "real_time_remote_biometric_public": False,
                    "law_enforcement_use": False,
                    "migration_asylum_border_use": False,
                    "justice_democratic_use": False,
                    "education_scoring_or_access": False,
                    "employment_decisions": False,
                    "essential_services_access": False,
                    "creditworthiness_evaluation": False,
                    "life_health_insurance_risk_pricing": False,
                    "critical_infrastructure_safety": False,
                    "medical_or_safety_component": False,
                    "annex_i_covered_product": False,
                },
                "affected_persons": ["webshop visitors"],
                "deployer_actor": "private_company",
                "deployer": {
                    "body_governed_by_public_law": False,
                    "private_entity_providing_public_services": False,
                },
            }
        ],
        "source_trace": ["eu-ai-act:article-50"],
        "explain": [
            "norm:eu-ai-act:article-50:paragraph-5:n1",
            "norm:eu-ai-act:article-50:paragraph-1:n1",
        ],
    },
    {
        "key": "highrisk",
        "project": PROJECTS / "credscore",
        "features_rounds": [
            {
                "description": (
                    "CredScore: a creditworthiness scoring service for a small "
                    "consumer loan fintech. It evaluates the creditworthiness of "
                    "natural persons applying for consumer loans and produces a "
                    "score and a recommendation that loan officers use in their "
                    "decisions and can override. Inputs are application data, "
                    "income, and payment history. It is not a fraud detection "
                    "tool."
                ),
                "domain": "banking",
                "purposes": [
                    "evaluate the creditworthiness of consumer loan applicants",
                    "produce a score and a recommendation for a loan officer",
                ],
                "autonomy": "advisory",
                "flags": {
                    "creditworthiness_evaluation": True,
                    "profiling_of_natural_persons": True,
                    "essential_services_access": True,
                    "biometric_identification": False,
                    "biometric_categorisation": False,
                    "emotion_recognition": False,
                    "emotion_recognition_workplace_or_education": False,
                    "social_scoring": False,
                    "subliminal_or_manipulative": False,
                    "exploits_vulnerabilities": False,
                    "predictive_policing_profiling": False,
                    "facial_image_scraping": False,
                    "real_time_remote_biometric_public": False,
                    "law_enforcement_use": False,
                    "migration_asylum_border_use": False,
                    "justice_democratic_use": False,
                    "education_scoring_or_access": False,
                    "employment_decisions": False,
                    "life_health_insurance_risk_pricing": False,
                    "critical_infrastructure_safety": False,
                    "medical_or_safety_component": False,
                    "annex_i_covered_product": False,
                    "interacts_with_natural_persons": False,
                    "generates_synthetic_content": False,
                },
                "affected_persons": ["consumer loan applicants"],
                "deployer_actor": "private_company",
                "deployer": {
                    "body_governed_by_public_law": False,
                    "private_entity_providing_public_services": True,
                },
            }
        ],
        "source_trace": ["eu-ai-act:annex-iii:point-5", "eu-ai-act:article-27:paragraph-1"],
        "explain": [
            "norm:eu-ai-act:article-12:paragraph-1:n1",
            "norm:eu-ai-act:article-14:paragraph-4:n1",
        ],
    },
    {
        "key": "unacceptablerisk",
        "project": None,
        "features_rounds": [
            # Round one: only the facts the README states outright.
            {
                "description": (
                    "MoodWatch: an employee wellbeing dashboard for a mid sized "
                    "employer. It analyses employees' facial expressions from "
                    "webcam feeds and their typing patterns to infer emotional "
                    "state (stress, frustration, engagement) during work hours, "
                    "and aggregates the result into dashboards visible to "
                    "management. Participation is a condition of employment. It "
                    "is not a medical device and is not deployed for safety "
                    "reasons."
                ),
                "domain": "employment",
                "purposes": [
                    "infer employee emotional state from webcam and keystroke data",
                    "aggregate team level mood for management dashboards",
                    "productivity and wellbeing monitoring",
                ],
                "autonomy": "advisory",
                "flags": {
                    "emotion_recognition": True,
                    "emotion_recognition_workplace_or_education": True,
                    "emotion_recognition_medical_or_safety": False,
                    "medical_or_safety_component": False,
                    "profiling_of_natural_persons": True,
                },
                "affected_persons": ["employees of the deploying company"],
                "deployer_actor": "private_company",
                "deployer": {
                    "body_governed_by_public_law": False,
                    "private_entity_providing_public_services": False,
                },
            },
            # Round two: the facts the first answer asked for, read off the
            # same README. The tier does not move; the unknowns clear.
            {
                "description": (
                    "MoodWatch: an employee wellbeing dashboard for a mid sized "
                    "employer. It analyses employees' facial expressions from "
                    "webcam feeds and their typing patterns to infer emotional "
                    "state (stress, frustration, engagement) during work hours, "
                    "and aggregates the result into dashboards visible to "
                    "management. Participation is a condition of employment. It "
                    "is not a medical device and is not deployed for safety "
                    "reasons."
                ),
                "domain": "employment",
                "purposes": [
                    "infer employee emotional state from webcam and keystroke data",
                    "aggregate team level mood for management dashboards",
                    "productivity and wellbeing monitoring",
                ],
                "autonomy": "advisory",
                "flags": {
                    "emotion_recognition": True,
                    "emotion_recognition_workplace_or_education": True,
                    "emotion_recognition_medical_or_safety": False,
                    "medical_or_safety_component": False,
                    "profiling_of_natural_persons": True,
                    "subliminal_or_manipulative": False,
                    "exploits_vulnerabilities": False,
                    "social_scoring": False,
                    "predictive_policing_profiling": False,
                    "facial_image_scraping": False,
                    "biometric_categorisation": False,
                    "real_time_remote_biometric_public": False,
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
                },
                "affected_persons": ["employees of the deploying company"],
                "deployer_actor": "private_company",
                "deployer": {
                    "body_governed_by_public_law": False,
                    "private_entity_providing_public_services": False,
                },
            },
        ],
        "source_trace": ["eu-ai-act:article-5:paragraph-1:point-f"],
        "explain": [],
    },
    {
        "key": "abstention",
        "project": None,
        "features_rounds": [
            {
                "description": (
                    "MoodWatch driver fatigue variant: the same emotion "
                    "inference engine deployed on in-cab cameras for a haulage "
                    "operator's drivers during work hours. Whether the "
                    "deployment is intended for medical or safety reasons has "
                    "not been established by the team, so that fact is left "
                    "unknown rather than guessed."
                ),
                "domain": "employment",
                "purposes": [
                    "infer driver emotional and fatigue state from an in-cab camera",
                    "surface driver state to fleet operations",
                ],
                "autonomy": "advisory",
                "flags": {
                    "emotion_recognition": True,
                    "emotion_recognition_workplace_or_education": True,
                    "profiling_of_natural_persons": True,
                    "subliminal_or_manipulative": False,
                    "exploits_vulnerabilities": False,
                    "social_scoring": False,
                    "predictive_policing_profiling": False,
                    "facial_image_scraping": False,
                    "biometric_categorisation": False,
                    "real_time_remote_biometric_public": False,
                    "biometric_identification": False,
                },
                "affected_persons": ["employed drivers"],
                "deployer_actor": "private_company",
            }
        ],
        "source_trace": ["eu-ai-act:article-5:paragraph-1:point-f"],
        "explain": [],
    },
]


def _envelope_of(result: Any) -> dict[str, Any]:
    """The tool's return value, whichever way this fastmcp version hands it back."""
    for attr in ("structured_content", "data"):
        value = getattr(result, attr, None)
        if isinstance(value, dict) and "status" in value:
            return value
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise SystemExit(f"cannot read an envelope out of {result!r}")


class Recorder:
    """Accumulates recorded exchanges for one session file."""

    def __init__(self, client: Client, repo_ref: str | None) -> None:
        self.client = client
        self.repo_ref = repo_ref
        self.seq = 0
        self.lines: list[dict[str, Any]] = []

    async def call(self, tool: str, request: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.call_tool(tool, request)
        envelope = _envelope_of(result)
        self.seq += 1
        self.lines.append(
            {
                "seq": self.seq,
                "ts": datetime.now(UTC).isoformat(),
                "tool": tool,
                "request": request,
                "envelope": envelope,
                "repo_ref": self.repo_ref,
            }
        )
        return envelope

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for line in self.lines:
                handle.write(json.dumps(line, sort_keys=True) + "\n")


async def record_system(client: Client, system: dict[str, Any], out_dir: Path) -> Path:
    project: Path | None = system["project"]
    repo_ref = (
        f"demo/mcp_demo/projects/{project.name}" if project is not None else None
    )
    rec = Recorder(client, repo_ref)

    classification: dict[str, Any] = {}
    for features in system["features_rounds"]:
        classification = await rec.call("classify_ai_system", {"features": features})

    await rec.call("get_applicable_requirements", {"classification": classification})

    if project is not None:
        tags = scan_tags(project)
        await rec.call(
            "trace_implementation",
            {"classification": classification, "tags": tags},
        )

    for norm_id in system["explain"]:
        await rec.call("explain_requirement", {"norm_id": norm_id})

    for node_id in system["source_trace"]:
        traced = await rec.call("source_trace", {"node_id": node_id})
        answer = traced.get("answer")
        spans = traced.get("source_spans") or []
        if isinstance(answer, dict) and spans:
            span_id = spans[0].get("span_id")
            if isinstance(span_id, str):
                await rec.call("resolve_span", {"span_id": span_id})

    path = out_dir / f"{system['key']}.jsonl"
    rec.write(path)
    answer = classification.get("answer") or {}
    tier = answer.get("risk_category") if isinstance(answer, dict) else "unknown"
    print(
        f"{system['key']}: {rec.seq} exchanges, risk_category={tier}, "
        f"status={classification.get('status')} -> {path}",
        file=sys.stderr,
    )
    return path


async def run(out_dir: Path, only: list[str]) -> int:
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "tere4ai.mcp_server.server"],
        cwd=str(ROOT),
    )
    systems = [s for s in SYSTEMS if not only or s["key"] in only]
    if not systems:
        print(f"no system matched {only}", file=sys.stderr)
        return 2
    async with Client(transport) as client:
        for system in systems:
            await record_system(client, system, out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="record only these system keys",
    )
    args = parser.parse_args(argv)
    return asyncio.run(run(Path(args.out_dir), list(args.only)))


if __name__ == "__main__":
    raise SystemExit(main())

"""The two systems of the REFSQ 2027 study keep their answers under the nine values of `domain` (B185, DEC-33).

The systems are the public repositories github.com/interviewstreet/hiring-agent
and github.com/wasserth/TotalSegmentator, with the facts their confirmed
revisions held, converted as DEC-32 converted every system: the hiring agent's
removed recruitment fact becomes annex_iii_4a_recruitment, its removed
Article 6(3) fact becomes both Article 6(3) facts false, and its domain
employment stays; TotalSegmentator's domain healthcare is left out, since its
description states no listed use of Annex III point 5. The test pins the
level, the point, the status, the candidate and the duties. Offline: the
published Layer 1 dump on disk, skipped when it is absent.

@implements: DEC-33
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.classify import classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")

HIRING_AGENT = {
    "description": (
        "This tool was built to rank them, helping decide which resumes to read first. "
        "Resumes scoring below the cutoff are filtered out."
    ),
    "domain": "employment",
    "purposes": ["rank intern resumes to prioritise human review", "filter out resumes below a score cutoff"],
    "affected_persons": ["internship applicants"],
    "autonomy": "partial",
    "flags": {
        "annex_iii_4a_recruitment": True,
        "generates_synthetic_content": True,
        "profiling_of_natural_persons": True,
        "narrow_procedural_task": False,
        "preparatory_task": False,
    },
}

TOTALSEGMENTATOR = {
    "description": "Tool for segmentation of most major anatomical structures in any CT or MR image.",
    "purposes": [
        "segment images and return machine-readable reports",
        "predict image modality",
        "estimate CT contrast phase",
        "estimate body measurements and patient attributes",
    ],
    "affected_persons": ["patients whose scans are processed"],
    "flags": {
        "biometric_categorisation": False,
        "biometric_categorisation_system": True,
        "biometric_categorisation_sensitive_or_protected_attributes": True,
        "profiling_of_natural_persons": True,
    },
}


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def test_the_hiring_agent_stays_high_risk_under_point_4(dump):
    env = classify_ai_system(HIRING_AGENT, dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-4"
    assert env["status"] == "requires_human_review"
    # B185 Task 4 (spec G D-G92 (6)): points (b) and (c) are unknown and none
    # is true, but profiling_of_natural_persons is true, so the candidate is
    # false, not unknown, and no condition is named.
    assert a["article_6_3_exception_candidate"] is False
    assert not any(line.endswith("the derogation candidacy is unknown, not no") for line in env["missing_facts"])
    assert a["transparency_duties"] == ["eu-ai-act:article-50:paragraph-2"]


def test_totalsegmentator_stays_high_risk_under_point_1(dump):
    env = classify_ai_system(TOTALSEGMENTATOR, dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-1"
    assert env["status"] == "requires_human_review"
    # B185 Task 4 (spec G D-G92 (6)): every condition is unknown, but
    # profiling_of_natural_persons is true, so the candidate is false, not
    # unknown, and no condition is named.
    assert a["article_6_3_exception_candidate"] is False
    assert not any(line.endswith("the derogation candidacy is unknown, not no") for line in env["missing_facts"])
    assert a["transparency_duties"] == ["eu-ai-act:article-50:paragraph-3"]

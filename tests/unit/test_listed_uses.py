"""The Annex III rule table over the 25 listed uses and annex_iii_listed_uses (B184, D-G91, DEC-32).

A point matches when one of its listed-use facts is true (point 1 also on
real_time_remote_biometric_public); the domain counts until every listed use
of the point is known false; every listed use that is true is named in
annex_iii_listed_uses, in point order, and cited on every exit but the
rejected input and the unacceptable_risk answer, which cites only Article 5
(ruling R14); the six removed broad facts are refused by name
(law_enforcement_use since Task 3). Offline: the published Layer 1 dump on
disk, skipped when it is absent.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.b184_cases import all_false
from tests.unit.b184_cases import case as _case

from tere4ai.mcp_server.classify import classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def test_finding_8_productivity_scoring_is_high_risk_under_point_4b(dump):
    # B185 (P19): the domain "office_software" is left out; it names no area.
    env = classify_ai_system(_case(all_false(annex_iii_4b_work_relationships=True)), dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk"
    assert a["annex_iii_category"] == "eu-ai-act:annex-iii:point-4"
    assert a["annex_iii_listed_uses"] == ["eu-ai-act:annex-iii:point-4:b"]
    assert "eu-ai-act:annex-iii:point-4:b" in env["source_nodes"]
    assert env["status"] == "potentially_applicable" and env["confidence"] == 1.0


def test_every_listed_use_answered_yes_is_cited_and_the_first_point_decides(dump):
    env = classify_ai_system(_case(all_false(annex_iii_4a_recruitment=True, creditworthiness_evaluation=True)), dump)
    a = env["answer"]
    assert a["annex_iii_category"] == "eu-ai-act:annex-iii:point-4"
    assert a["annex_iii_listed_uses"] == ["eu-ai-act:annex-iii:point-4:a", "eu-ai-act:annex-iii:point-5:b"]
    first = next(i for i, line in enumerate(a["rationale"]) if line.startswith("rule high_risk:"))
    assert a["rationale"].index("Annex III listed use true: flag creditworthiness_evaluation is true for "
                                "eu-ai-act:annex-iii:point-5:b; cited with the answer") > first
    assert not any("flag annex_iii_4a_recruitment is true for" in line for line in a["rationale"])
    assert {"eu-ai-act:annex-iii:point-4:a", "eu-ai-act:annex-iii:point-5:b"} <= set(env["source_nodes"])


def test_listed_uses_are_cited_on_the_article_6_1_exit(dump):
    flags = all_false(annex_i_covered_product=True, third_party_conformity_assessment_required=True,
                      annex_i_section_b_legislation=False, annex_iii_4a_recruitment=True)
    env = classify_ai_system(_case(flags), dump)
    assert env["answer"]["annex_iii_category"] is None
    assert "eu-ai-act:annex-iii:point-4:a" in env["source_nodes"]
    assert env["answer"]["high_risk_routes"] == ["article_6_1", "article_6_2"]


def test_domain_counts_until_every_listed_use_is_false(dump):
    point5_false = dict(annex_iii_5a_public_benefits=False, life_health_insurance_risk_pricing=False,
                        annex_iii_5d_emergency_calls=False)
    flags = {k: v for k, v in all_false(**point5_false).items() if k != "creditworthiness_evaluation"}
    # B185: banking to essential_services; the test is about the domain rule
    # of point 5 itself, which Task 2 of B185 rewrites.
    a = classify_ai_system(_case(flags, domain="essential_services"), dump)["answer"]
    assert a["risk_category"] == "high_risk" and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-5"
    assert a["annex_iii_listed_uses"] == []
    a = classify_ai_system(_case(all_false(), domain="essential_services"), dump)["answer"]
    assert a["risk_category"] == "minimal_risk"
    assert any("every listed use of the category is answered false" in line for line in a["rationale"])


def test_an_unknown_listed_use_is_named_and_blocks_minimal(dump):
    flags = {k: v for k, v in all_false().items() if k != "annex_iii_7d_identification"}
    env = classify_ai_system(_case(flags), dump)
    assert env["answer"]["risk_category"] == "undetermined"
    assert ("flags.annex_iii_7d_identification is unknown (Annex III high-risk relevant, Article 6(2)); "
            "absence is not treated as false") in env["missing_facts"]


@pytest.mark.parametrize("removed", ["education_scoring_or_access", "employment_decisions", "essential_services_access",
                                     "migration_asylum_border_use", "justice_democratic_use", "law_enforcement_use",
                                     "preparatory_or_narrow_procedural_task"])
def test_each_removed_fact_is_refused_by_name(dump, removed):
    env = classify_ai_system(_case({removed: False}), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert any(removed in line for line in env["missing_facts"])
    assert env["answer"]["annex_iii_listed_uses"] == [] and env["source_nodes"] == []


def test_a_prohibited_answer_names_its_listed_uses_and_cites_only_article_5(dump):
    """Coordinator ruling R14 (USER.md: prohibited systems get only the Article
    5 prohibition citation and a message): on the unacceptable_risk exit the
    field still names the listed uses that are true, but no Annex III unit is
    cited and no further-listed-use line is added."""
    flags = all_false(emotion_recognition_workplace_or_education=True, emotion_recognition=True,
                      annex_iii_4b_work_relationships=True)
    env = classify_ai_system(_case(flags), dump)
    a = env["answer"]
    assert a["risk_category"] == "unacceptable_risk"
    assert a["annex_iii_listed_uses"] == ["eu-ai-act:annex-iii:point-1:c", "eu-ai-act:annex-iii:point-4:b"]
    assert env["source_nodes"] and all(":article-5:" in n for n in env["source_nodes"])
    assert not any(line.startswith("Annex III listed use true") for line in a["rationale"])
    assert all(":article-5:" in e["provision"] for e in a["application_dates"])

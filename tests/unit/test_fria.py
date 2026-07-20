"""Unit tests for the deterministic Article 27(1) FRIA applicability rule.

DEC-14: whether the fundamental rights impact assessment obligation applies
is decided by a fixed rule over structured facts, never a model. These
tests pin the rule to the operative sentence of Article 27(1): the Article
6(2)-route scope, the Annex III point 2 exception, the two deployer
categories, and the Annex III point 5(b)/(c) system triggers. Unknown
facts are named, never guessed, and the outcome vocabulary is closed.

The pure-rule tests need no dump; the envelope-level tests run against the
real published Layer 0+1 dump and skip when it has not been built.
"""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.fria import (
    ANNEX_III_POINT_2,
    ANNEX_III_POINT_5B,
    ANNEX_III_POINT_5C,
    ARTICLE_27_PARAGRAPH_1,
    FRIA_APPLICABILITY_VOCABULARY,
    assess_fria_applicability,
)
from tere4ai.mcp_server.requirements import get_applicable_requirements

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

POINT_4 = "eu-ai-act:annex-iii:point-4"
POINT_5 = "eu-ai-act:annex-iii:point-5"


# Pure rule -------------------------------------------------------------------


def test_credit_scoring_flag_alone_makes_fria_apply():
    """Annex III point 5(b) systems trigger the FRIA for ANY deployer."""
    block = assess_fria_applicability(
        "high_risk", POINT_5, {"creditworthiness_evaluation": True}, {}
    )
    assert block["applicability"] == "applies"
    assert ARTICLE_27_PARAGRAPH_1 in block["basis_nodes"]
    assert ANNEX_III_POINT_5B in block["basis_nodes"]
    assert any("regardless of deployer type" in r for r in block["rationale"])
    assert any("Prior to deploying" in r for r in block["rationale"])
    assert block["missing_facts"] == []


def test_insurance_pricing_flag_alone_makes_fria_apply():
    block = assess_fria_applicability(
        "high_risk", POINT_5, {"life_health_insurance_risk_pricing": True}, {}
    )
    assert block["applicability"] == "applies"
    assert ANNEX_III_POINT_5C in block["basis_nodes"]


@pytest.mark.parametrize(
    "fact",
    ["body_governed_by_public_law", "private_entity_providing_public_services"],
)
def test_each_deployer_category_triggers_fria_on_any_annex_iii_system(fact):
    """Public-law bodies and public-service providers need a FRIA for any
    Annex III high-risk system, here an employment (point 4) system."""
    block = assess_fria_applicability("high_risk", POINT_4, {}, {fact: True})
    assert block["applicability"] == "applies"
    assert any(fact in r for r in block["rationale"])


def test_critical_infrastructure_exception_excludes_the_obligation():
    block = assess_fria_applicability(
        "high_risk", ANNEX_III_POINT_2, {}, {"body_governed_by_public_law": True}
    )
    assert block["applicability"] == "does_not_apply"
    assert ANNEX_III_POINT_2 in block["basis_nodes"]
    assert any("point 2 of Annex III" in r for r in block["rationale"])


def test_point_2_area_plus_point_5b_trigger_needs_human_review():
    """A system matching both the excepted point 2 area and a point 5(b)
    trigger is not rule-decidable; the rule must say so, not pick."""
    block = assess_fria_applicability(
        "high_risk", ANNEX_III_POINT_2, {"creditworthiness_evaluation": True}, {}
    )
    assert block["applicability"] == "unknown"
    assert any("human legal review" in r for r in block["rationale"])


@pytest.mark.parametrize("category", ["minimal_or_none", "transparency_only"])
def test_non_high_risk_categories_do_not_carry_the_obligation(category):
    block = assess_fria_applicability(category, None, {}, {})
    assert block["applicability"] == "does_not_apply"


def test_prohibited_systems_have_no_deployment_for_fria_to_attach_to():
    block = assess_fria_applicability("prohibited", None, {}, {})
    assert block["applicability"] == "does_not_apply"
    assert any("no lawful deployment" in r for r in block["rationale"])


@pytest.mark.parametrize("category", ["uncertain", None])
def test_unsettled_classification_keeps_fria_unknown(category):
    block = assess_fria_applicability(category, None, {}, {})
    assert block["applicability"] == "unknown"


def test_article_6_1_route_only_is_out_of_article_27_scope():
    block = assess_fria_applicability("high_risk", None, {}, {})
    assert block["applicability"] == "does_not_apply"
    assert any("Article 6(1)" in r for r in block["rationale"])
    assert any("Article 6(2)" in r for r in block["rationale"])


def test_all_trigger_facts_explicitly_false_means_does_not_apply():
    block = assess_fria_applicability(
        "high_risk",
        POINT_4,
        {
            "creditworthiness_evaluation": False,
            "life_health_insurance_risk_pricing": False,
        },
        {
            "body_governed_by_public_law": False,
            "private_entity_providing_public_services": False,
        },
    )
    assert block["applicability"] == "does_not_apply"
    assert block["missing_facts"] == []


def test_unknown_trigger_facts_are_each_named_never_guessed():
    block = assess_fria_applicability("high_risk", POINT_4, {}, {})
    assert block["applicability"] == "unknown"
    named = "\n".join(block["missing_facts"])
    for fact in (
        "flags.creditworthiness_evaluation",
        "flags.life_health_insurance_risk_pricing",
        "deployer.body_governed_by_public_law",
        "deployer.private_entity_providing_public_services",
    ):
        assert fact in named, f"missing fact not named: {fact}"
    assert all("not treated as false" in m for m in block["missing_facts"])


def test_vocabulary_is_closed_and_output_never_claims_compliance():
    scenarios = [
        ("high_risk", POINT_5, {"creditworthiness_evaluation": True}, {}),
        ("high_risk", ANNEX_III_POINT_2, {}, {}),
        ("high_risk", POINT_4, {}, {}),
        ("minimal_or_none", None, {}, {}),
        ("prohibited", None, {}, {}),
        ("uncertain", None, {}, {}),
        ("high_risk", None, {}, {}),
    ]
    for args in scenarios:
        block = assess_fria_applicability(*args)
        assert block["applicability"] in FRIA_APPLICABILITY_VOCABULARY
        serialized = json.dumps(block).lower()
        assert "compliant" not in serialized
        assert "certified" not in serialized


# Envelope level, against the real dump ---------------------------------------

pytestmark_dump = pytest.mark.skipif(
    not DUMP_PATH.is_file(), reason="layer1.json dump not built"
)


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_ids(dump) -> set:
    return {n["id"] for n in dump["nodes"]}


def _credit_scorer_features(**extra) -> dict:
    features = {
        "description": (
            "A retail bank deploys an AI system that evaluates the "
            "creditworthiness of natural persons and establishes their "
            "credit score for consumer loan decisions."
        ),
        "domain": "banking",
        "flags": {
            "creditworthiness_evaluation": True,
            "subliminal_or_manipulative": False,
            "exploits_vulnerabilities": False,
            "social_scoring": False,
            "predictive_policing_profiling": False,
            "facial_image_scraping": False,
            "emotion_recognition_workplace_or_education": False,
            "biometric_categorisation": False,
            "real_time_remote_biometric_public": False,
            "law_enforcement_use": False,
        },
    }
    features.update(extra)
    return features


def test_classify_envelope_carries_an_applies_fria_block(dump, node_ids):
    envelope = classify_ai_system(_credit_scorer_features(), dump)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["annex_iii_category"] == POINT_5
    fria = answer["fria"]
    assert fria["applicability"] == "applies"
    for node in fria["basis_nodes"]:
        assert node in node_ids, f"fria basis node {node} not in dump"


def test_new_subflag_gates_point_5_high_risk_on_its_own(dump):
    """creditworthiness_evaluation alone classifies high-risk (a 5(b)
    system IS an Annex III point 5 system), without the umbrella flag."""
    envelope = classify_ai_system(_credit_scorer_features(domain=None), dump)
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["answer"]["annex_iii_category"] == POINT_5


def test_scenario_161_domain_yield_semantics_are_preserved(dump):
    """Explicit false on the umbrella flag with the subflags unknown must
    still yield the bare domain match (the evidence-driven fix stands)."""
    features = _credit_scorer_features()
    features["flags"].pop("creditworthiness_evaluation")
    features["flags"]["essential_services_access"] = False
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["risk_category"] == "minimal_or_none"
    assert envelope["answer"]["fria"]["applicability"] == "does_not_apply"


def test_deployer_facts_validate_and_trigger_fria(dump):
    features = _credit_scorer_features(
        deployer={"body_governed_by_public_law": True}
    )
    features["flags"].pop("creditworthiness_evaluation")
    features["flags"]["essential_services_access"] = True
    envelope = classify_ai_system(features, dump)
    assert envelope["status"] != "not_applicable", "deployer object must validate"
    assert envelope["answer"]["fria"]["applicability"] == "applies"


def test_unknown_deployer_property_is_rejected_by_the_schema(dump):
    features = _credit_scorer_features(deployer={"invented_fact": True})
    envelope = classify_ai_system(features, dump)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["risk_category"] is None
    assert envelope["answer"]["fria"]["applicability"] == "unknown"


def test_article_6_1_route_still_checks_6_2_membership_for_fria(dump):
    """Both routes can hold at once: a 6(1) embedded product that also
    evaluates creditworthiness keeps the FRIA obligation (Article 27(1)
    covers the 6(2) side), even though the ladder cites the 6(1) route."""
    features = _credit_scorer_features()
    features["flags"]["annex_i_covered_product"] = True
    features["flags"]["third_party_conformity_assessment_required"] = True
    envelope = classify_ai_system(features, dump)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["annex_iii_category"] is None, "ladder took the 6(1) route"
    assert answer["fria"]["applicability"] == "applies"
    assert ANNEX_III_POINT_5B in answer["fria"]["basis_nodes"]


def test_requirements_pass_the_fria_block_through_verbatim(dump):
    if not NORMS_PATH.is_file():
        pytest.skip("norms_core.json dump not built")
    norms_payload = json.loads(NORMS_PATH.read_text(encoding="utf-8"))
    classification = classify_ai_system(_credit_scorer_features(), dump)
    envelope = get_applicable_requirements(
        classification, norms_payload, dump, actor="deployer"
    )
    answer = envelope["answer"]
    assert "article-27" in answer["requirements_by_article"]
    assert answer["fria"] == classification["answer"]["fria"]

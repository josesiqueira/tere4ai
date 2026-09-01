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


# Trust-split guard (audit W6): DEC-14's whole defense is that the FRIA rule
# is deterministic and never calls a model. Pin it, like classify/requirements.
def test_fria_module_imports_no_model_client():
    import tere4ai.mcp_server.fria as fria_mod

    source = Path(fria_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "model_client", "ModelClient", "fastmcp"):
        assert forbidden not in source, f"fria.py must not import {forbidden}"


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
    # 5(b)/5(c) known false, so the point-2 exception settles does_not_apply.
    block = assess_fria_applicability(
        "high_risk",
        ANNEX_III_POINT_2,
        {"creditworthiness_evaluation": False, "life_health_insurance_risk_pricing": False},
        {"body_governed_by_public_law": True},
    )
    assert block["applicability"] == "does_not_apply"
    assert ANNEX_III_POINT_2 in block["basis_nodes"]
    assert any("point 2 of Annex III" in r for r in block["rationale"])


def test_point_2_only_with_unknown_5bc_facts_is_unknown_not_does_not_apply():
    """Audit 2026-07-21: a point-2-only system whose 5(b)/5(c) facts are
    UNKNOWN must not be a confident does_not_apply; either fact being true
    would add a non-excepted point-5 area and trigger the FRIA."""
    block = assess_fria_applicability(
        "high_risk", ANNEX_III_POINT_2, {}, {"body_governed_by_public_law": True}
    )
    assert block["applicability"] == "unknown"
    assert any("creditworthiness_evaluation" in m for m in block["missing_facts"])


def test_point_2_area_plus_point_5b_trigger_applies():
    """Audit D5: the point-2 exception is scoped to the point-2 area. A
    system that also falls under point 5(b) is triggered by that aspect
    regardless of the point-2 overlap, so the FRIA applies, not unknown."""
    block = assess_fria_applicability(
        "high_risk",
        ANNEX_III_POINT_5B,
        {"creditworthiness_evaluation": True},
        {},
        annex_points=[ANNEX_III_POINT_2, ANNEX_III_POINT_5B],
    )
    assert block["applicability"] == "applies"
    assert ANNEX_III_POINT_5B in block["basis_nodes"]


def test_point_2_plus_other_area_public_deployer_applies():
    """Audit D5: a multi-area system (point 2 AND point 6) deployed by a
    public-law body triggers the FRIA on the non-point-2 area; the point-2
    exception must not erase the obligation."""
    block = assess_fria_applicability(
        "high_risk",
        ANNEX_III_POINT_2,
        {},
        {"body_governed_by_public_law": True},
        annex_points=[ANNEX_III_POINT_2, "eu-ai-act:annex-iii:point-6"],
    )
    assert block["applicability"] == "applies"
    assert "eu-ai-act:annex-iii:point-6" in block["basis_nodes"]


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
    # 5(b)/5(c) known false, so the 6(1)-only route settles does_not_apply.
    block = assess_fria_applicability(
        "high_risk",
        None,
        {"creditworthiness_evaluation": False, "life_health_insurance_risk_pricing": False},
        {},
    )
    assert block["applicability"] == "does_not_apply"
    assert any("Article 6(1)" in r for r in block["rationale"])
    assert any("Article 6(2)" in r for r in block["rationale"])


def test_6_1_route_with_unknown_5bc_facts_is_unknown_not_does_not_apply():
    """Audit 2026-07-21: a 6(1)-route-only system whose 5(b)/5(c) facts are
    UNKNOWN could also fall under Article 6(2) point 5, so FRIA applicability
    is unknown, not a confident does_not_apply."""
    block = assess_fria_applicability("high_risk", None, {}, {})
    assert block["applicability"] == "unknown"
    assert any("life_health_insurance_risk_pricing" in m for m in block["missing_facts"])


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


def test_fraud_detection_carve_out_is_inherited_from_the_flag_definition():
    """Annex III point 5(b) carves out AI systems used for the purpose of
    detecting financial fraud. The carve-out is definitional, not a second
    rule: the schema definition of creditworthiness_evaluation excludes
    fraud-detection systems, so their fact enters as explicitly false and
    branch (b) never fires. This test documents that inheritance."""
    block = assess_fria_applicability(
        "high_risk",
        POINT_5,
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


def test_pending_article_6_3_derogation_blocks_the_decision():
    """The ladder never auto-applies the Article 6(3) derogation; while
    candidacy awaits the human decision, the system's Article 6(2) status
    is unsettled and so is Article 27(1). Even a settled deployer trigger
    must not force "applies" past that."""
    block = assess_fria_applicability(
        "high_risk",
        POINT_4,
        {},
        {"body_governed_by_public_law": True},
        article_6_3_exception_candidate=True,
    )
    assert block["applicability"] == "unknown"
    assert any("Article 6(3)" in m for m in block["missing_facts"])
    assert "eu-ai-act:article-6:paragraph-3" in block["basis_nodes"]


def test_applies_from_is_data_never_control_flow():
    """The Omnibus-postponed application date rides on every block as data
    (architecture.md Section 11 overlay pattern) and never changes the
    decision itself."""
    for args in (
        ("high_risk", POINT_5, {"creditworthiness_evaluation": True}, {}),
        ("minimal_or_none", None, {}, {}),
    ):
        block = assess_fria_applicability(*args)
        applies_from = block["applies_from"]
        assert applies_from["date"] == "2027-12-02"
        assert applies_from["legal_status"] == "in_force"
        assert "OJ" in applies_from["source"]


def test_applies_from_source_carries_no_internal_task_references():
    """The applies_from source rides on every classify envelope, so it is
    public-facing text: it must name the amending instrument and its OJ
    citation, never an internal task-board reference."""
    for args in (
        ("high_risk", POINT_5, {"creditworthiness_evaluation": True}, {}),
        ("minimal_or_none", None, {}, {}),
        ("uncertain", None, {}, {}),
    ):
        block = assess_fria_applicability(*args)
        source = block["applies_from"]["source"]
        assert "TASKS.md" not in source
        assert "2026/1744" in source
        assert "24.7.2026" in source


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
            "generates_nonconsensual_intimate_material": False,
            "generates_csam": False,
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


# Every Annex III high-risk flag plus the prohibition flags, all false: the
# only way to reach a confident minimal verdict after audit D1.
_ALL_FLAGS_FALSE = {
    "generates_nonconsensual_intimate_material": False,
    "generates_csam": False,
    "biometric_identification": False,
    "biometric_categorisation": False,
    "real_time_remote_biometric_public": False,
    "emotion_recognition": False,
    "emotion_recognition_workplace_or_education": False,
    "social_scoring": False,
    "subliminal_or_manipulative": False,
    "exploits_vulnerabilities": False,
    "predictive_policing_profiling": False,
    "facial_image_scraping": False,
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
    "interacts_with_natural_persons": False,
    "generates_synthetic_content": False,
    "profiling_of_natural_persons": False,
}


def test_scenario_161_domain_yield_semantics_are_preserved(dump):
    """The domain-yield fix stands: when every point-5 fact (umbrella AND
    both sub-point flags) is explicitly false, a bare banking domain match
    yields to minimal. Post-audit-D1 every Annex III fact must be known
    false, otherwise an unknown one correctly blocks the clear."""
    features = {
        "description": "A bank tool with no high-risk use, fully specified.",
        "domain": "banking",
        "flags": dict(_ALL_FLAGS_FALSE),
    }
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["risk_category"] == "minimal_or_none"
    assert envelope["answer"]["fria"]["applicability"] == "does_not_apply"


def test_unknown_annex_iii_subflag_blocks_a_confident_minimal(dump):
    """Audit D1: with the point-5 umbrella explicitly false but a sub-point
    fact (5(b)) unknown, the system cannot be confidently cleared as
    minimal; it must be requires_human_review naming the unknown fact."""
    flags = dict(_ALL_FLAGS_FALSE)
    del flags["creditworthiness_evaluation"]
    features = {
        "description": "A bank tool whose creditworthiness use is unstated.",
        "domain": "banking",
        "flags": flags,
    }
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["risk_category"] == "uncertain"
    assert envelope["status"] == "requires_human_review"
    assert any(
        "creditworthiness_evaluation" in f for f in envelope["missing_facts"]
    )


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
    # Schema-invalid input is refused, not assessed: rejected_as_unsupported,
    # never the substantive not_applicable verdict (C5 honesty fix).
    assert envelope["status"] == "rejected_as_unsupported"
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


def test_derogation_candidacy_flows_from_ladder_to_fria_block(dump):
    """Envelope level: an Annex III system with a matched Article 6(3)
    condition and profiling explicitly false keeps candidacy, so the fria
    block goes unknown even with a public-law deployer."""
    features = _credit_scorer_features(
        deployer={"body_governed_by_public_law": True}
    )
    features["flags"].pop("creditworthiness_evaluation")
    features["flags"]["employment_decisions"] = True
    features["flags"]["improves_previous_human_activity"] = True
    features["flags"]["profiling_of_natural_persons"] = False
    envelope = classify_ai_system(features, dump)
    answer = envelope["answer"]
    assert answer["article_6_3_exception_candidate"] is True
    assert answer["fria"]["applicability"] == "unknown"
    assert any("Article 6(3)" in m for m in answer["fria"]["missing_facts"])


def test_profiling_cancels_derogation_then_branch_logic_proceeds(dump):
    """Article 6(3) third subparagraph: profiling systems stay high-risk,
    candidacy is cancelled, and the FRIA branches decide normally."""
    features = _credit_scorer_features(
        deployer={"body_governed_by_public_law": True}
    )
    features["flags"].pop("creditworthiness_evaluation")
    features["flags"]["employment_decisions"] = True
    features["flags"]["improves_previous_human_activity"] = True
    features["flags"]["profiling_of_natural_persons"] = True
    envelope = classify_ai_system(features, dump)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["article_6_3_exception_candidate"] is False
    assert answer["fria"]["applicability"] == "applies"


def test_unsettled_prohibition_makes_fria_unknown_not_applies(dump):
    """Audit D6: a high-risk credit system with an unknown prohibition flag
    is requires_human_review (could flip to prohibited); the FRIA block must
    not present a settled 'applies', it stays unknown naming the dependency."""
    features = _credit_scorer_features()
    # Drop a prohibition flag so the classification is unsettled.
    features["flags"].pop("social_scoring")
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["status"] == "requires_human_review"
    fria = envelope["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert any("not settled" in r for r in fria["rationale"])


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

"""Unit tests for classify_ai_system (M3 deterministic runtime classification).

Offline only: runs against the real published Layer 0+1 dump on disk and
skips when it has not been built. No model, no network, no database.
"""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server import classify as classify_module
from tere4ai.mcp_server.classify import (
    ARTICLE_5_POINT_BY_FLAG,
    ARTICLE_5_POINT_H,
    classify_ai_system,
)
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE, STATUS_VOCABULARY

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(
    not DUMP_PATH.is_file(), reason="layer1.json dump not built"
)

# All flags defined in system_features.schema.json, for the all-false scenarios.
ALL_FLAGS = (
    "biometric_identification",
    "biometric_categorisation",
    "real_time_remote_biometric_public",
    "emotion_recognition",
    "emotion_recognition_workplace_or_education",
    "social_scoring",
    "subliminal_or_manipulative",
    "exploits_vulnerabilities",
    "predictive_policing_profiling",
    "facial_image_scraping",
    "law_enforcement_use",
    "migration_asylum_border_use",
    "justice_democratic_use",
    "education_scoring_or_access",
    "employment_decisions",
    "essential_services_access",
    "creditworthiness_evaluation",
    "life_health_insurance_risk_pricing",
    "critical_infrastructure_safety",
    "medical_or_safety_component",
    "interacts_with_natural_persons",
    "generates_synthetic_content",
    "profiling_of_natural_persons",
    "preparatory_or_narrow_procedural_task",
    "improves_previous_human_activity",
    "detects_patterns_without_replacing_human_assessment",
    "annex_i_covered_product",
    "third_party_conformity_assessment_required",
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_ids(dump) -> set:
    return {n["id"] for n in dump["nodes"]}


def all_false_flags(**overrides) -> dict:
    flags = dict.fromkeys(ALL_FLAGS, False)
    flags.update(overrides)
    return flags


def assert_envelope_invariants(envelope: dict, node_ids: set) -> None:
    """DEC-08 invariants shared by every deterministic runtime response."""
    assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    assert envelope["status"] in STATUS_VOCABULARY
    assert envelope["judge_verdict"] == "not_applicable_deterministic"
    serialized = json.dumps(envelope).lower()
    assert "compliant" not in serialized
    assert "certified" not in serialized
    for node_id in envelope["source_nodes"]:
        assert node_id in node_ids, f"cited node {node_id} not in dump"


# The four canonical scenarios ------------------------------------------------


def test_scenario_a_deepfake_generator_is_prohibited(dump, node_ids):
    features = {
        "description": "Generator of deepfake intimate content designed to "
        "manipulate targets into paying for its removal.",
        "purposes": ["generate intimate deepfakes", "coerce targets"],
        "flags": {
            "social_scoring": False,
            "subliminal_or_manipulative": True,
            # The coercion causes significant harm, so the point (a) element
            # is met and the prohibition is settled (audit D2).
            "causes_significant_harm": True,
            "generates_synthetic_content": True,
        },
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "prohibited"
    assert answer["prohibited"] is True
    assert envelope["status"] == "potentially_applicable"
    # Cites an Article 5 point node that exists in the dump.
    cited = [n for n in envelope["source_nodes"] if ":article-5:" in n]
    assert cited == ["eu-ai-act:article-5:paragraph-1:point-a"]
    assert cited[0] in node_ids
    assert envelope["source_spans"], "prohibition citation must carry its span"
    assert any("prohibited" in note for note in envelope["legal_status_notes"])


def test_scenario_b_hospital_triage_is_high_risk(dump, node_ids):
    features = {
        "description": "Hospital emergency department triage support system.",
        "domain": "healthcare",
        "flags": {
            "essential_services_access": True,
            "medical_or_safety_component": True,
        },
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["prohibited"] is False
    assert answer["annex_iii_category"] == "eu-ai-act:annex-iii:point-5"
    assert "eu-ai-act:annex-iii:point-5" in envelope["source_nodes"]
    # Prohibition flags were not provided, so the outcome is not settled.
    assert envelope["status"] == "requires_human_review"
    assert any("prohibition-relevant" in f for f in envelope["missing_facts"])


def test_scenario_b_with_prohibition_flags_known_false(dump, node_ids):
    features = {
        "description": "Hospital emergency department triage support system.",
        "domain": "healthcare",
        "flags": all_false_flags(
            essential_services_access=True, medical_or_safety_component=True
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["answer"]["annex_iii_category"] == "eu-ai-act:annex-iii:point-5"
    assert envelope["status"] == "potentially_applicable"
    assert "eu-ai-act:article-6:paragraph-2" in envelope["source_nodes"]


def test_scenario_c_ecommerce_chatbot_is_transparency_only(dump, node_ids):
    features = {
        "description": "Customer service chatbot for an e-commerce shop.",
        "domain": "consumer",
        "flags": all_false_flags(interacts_with_natural_persons=True),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "transparency_only"
    assert answer["prohibited"] is False
    assert answer["annex_iii_category"] is None
    assert envelope["status"] == "potentially_applicable"
    assert envelope["source_nodes"] == ["eu-ai-act:article-50:paragraph-1"]


def test_scenario_d_movie_recommender_is_minimal(dump, node_ids):
    features = {
        "description": "Movie recommendation engine for a streaming service.",
        "domain": "consumer",
        "flags": all_false_flags(),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "minimal_or_none"
    assert answer["prohibited"] is False
    assert envelope["status"] == "not_applicable"
    assert envelope["missing_facts"] == []


# Unknown-flag behavior -------------------------------------------------------


def test_absent_prohibition_flags_populate_missing_facts_and_uncertain(dump, node_ids):
    features = {"description": "A system described with no structured facts at all."}
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "uncertain"
    assert envelope["status"] == "requires_human_review"
    facts = " ".join(envelope["missing_facts"])
    for flag in ARTICLE_5_POINT_BY_FLAG:
        assert f"flags.{flag}" in facts
    assert "flags.real_time_remote_biometric_public" in facts


def test_absent_annex_iii_flags_block_a_confident_minimal(dump, node_ids):
    """Audit D1: a system with all prohibition flags known false but Annex III
    high-risk flags absent must NOT be cleared as minimal at confidence 1.0;
    it is uncertain, naming each unknown Annex III fact."""
    flags = dict.fromkeys(ARTICLE_5_POINT_BY_FLAG, False)
    flags["real_time_remote_biometric_public"] = False
    envelope = classify_ai_system(
        {"description": "A system with only prohibition facts settled.", "flags": flags},
        dump,
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "uncertain"
    assert envelope["status"] == "requires_human_review"
    facts = " ".join(envelope["missing_facts"])
    for flag in ("employment_decisions", "essential_services_access", "creditworthiness_evaluation"):
        assert f"flags.{flag}" in facts, flag


def test_homoglyph_or_invisible_domain_does_not_silently_clear(dump, node_ids):
    """Audit D8: an invisible or homoglyph character in domain must not turn a
    known domain into a near-miss that reads as confidently out-of-scope. With
    Annex III facts unknown the outcome is uncertain, never confident minimal."""
    flags = dict.fromkeys(ARTICLE_5_POINT_BY_FLAG, False)
    flags["real_time_remote_biometric_public"] = False
    for bad_domain in ("banking​", "ban­king", "бanking"):
        envelope = classify_ai_system(
            {"description": "A finance system, domain obfuscated.", "domain": bad_domain, "flags": flags},
            dump,
        )
        assert envelope["answer"]["risk_category"] != "minimal_or_none", bad_domain
        assert envelope["status"] != "not_applicable", bad_domain
    # A zero-width-padded but otherwise exact known domain normalises cleanly.
    clean = classify_ai_system(
        {"description": "Banking eligibility engine.", "domain": "​banking​",
         "flags": {**flags, "essential_services_access": True}},
        dump,
    )
    assert clean["answer"]["annex_iii_category"] == "eu-ai-act:annex-iii:point-5"


def test_rtrb_without_law_enforcement_context_asks_for_it(dump, node_ids):
    features = {
        "description": "Real-time remote biometric identification in public spaces.",
        "flags": all_false_flags(real_time_remote_biometric_public=True),
    }
    # law_enforcement_use is present (false), so point (h) does not fire and
    # the biometric flag routes to Annex III point 1 instead.
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["answer"]["annex_iii_category"] == "eu-ai-act:annex-iii:point-1"

    # With the context flag unknown, the missing fact is surfaced.
    flags = all_false_flags(real_time_remote_biometric_public=True)
    del flags["law_enforcement_use"]
    envelope = classify_ai_system({"description": features["description"], "flags": flags}, dump)
    assert any("law_enforcement_use" in f for f in envelope["missing_facts"])


def test_rtrb_with_law_enforcement_is_prohibited_point_h(dump, node_ids):
    features = {
        "description": "Live facial recognition in public squares for police use.",
        "flags": all_false_flags(
            real_time_remote_biometric_public=True,
            law_enforcement_use=True,
            # Not the strict-necessity/authorisation carve-out, so the point
            # (h) ban is settled (audit D2).
            rtrb_strictly_necessary_authorised=False,
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "prohibited"
    assert ARTICLE_5_POINT_H in envelope["source_nodes"]


def test_article_5_exception_fact_unknown_routes_to_review_not_ban(dump, node_ids):
    """Audit D2: a qualified prohibition flag true with its exculpating fact
    unknown must NOT be a confident ban; the ban stays for human review."""
    envelope = classify_ai_system(
        {
            "description": "In-cab driver drowsiness detector inferring fatigue.",
            "flags": all_false_flags(emotion_recognition_workplace_or_education=True),
        },
        dump,
    )
    assert envelope["answer"]["risk_category"] != "prohibited"
    assert envelope["status"] == "requires_human_review"
    assert any("emotion_recognition_medical_or_safety" in f for f in envelope["missing_facts"])


def test_article_5_exception_met_continues_the_ladder_not_prohibited(dump, node_ids):
    """The point (f) medical/safety exception, when met, means the emotion
    system is not prohibited; the ladder continues (here to minimal)."""
    envelope = classify_ai_system(
        {
            "description": "Driver drowsiness detector, medical/safety purpose.",
            "flags": all_false_flags(
                emotion_recognition_workplace_or_education=True,
                emotion_recognition_medical_or_safety=True,
            ),
        },
        dump,
    )
    answer = envelope["answer"]
    assert answer["prohibited"] is False
    assert answer["risk_category"] != "prohibited"
    assert any("not prohibited under that point" in r for r in answer["rationale"])


# Article 6(3) exception candidate --------------------------------------------


def test_article_6_3_candidate_requires_human_review_never_downgrades(dump, node_ids):
    features = {
        "description": "Advisory tool that pre-sorts student admission paperwork.",
        "domain": "education",
        "autonomy": "advisory",
        "flags": all_false_flags(
            education_scoring_or_access=True, preparatory_or_narrow_procedural_task=True
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    # Never a silent downgrade: the category stays high_risk.
    assert answer["risk_category"] == "high_risk"
    assert answer["article_6_3_exception_candidate"] is True
    assert envelope["status"] == "requires_human_review"
    assert "eu-ai-act:article-6:paragraph-3" in envelope["source_nodes"]


def test_no_exception_candidate_without_advisory_autonomy(dump, node_ids):
    features = {
        "description": "Automated tool that pre-sorts student admission paperwork.",
        "domain": "education",
        "autonomy": "full",
        "flags": all_false_flags(
            education_scoring_or_access=True, preparatory_or_narrow_procedural_task=True
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["article_6_3_exception_candidate"] is False
    assert envelope["status"] == "potentially_applicable"


def test_point_b_condition_flags_candidacy_and_cites_the_point(dump, node_ids):
    features = {
        "description": "Grammar checker that polishes already-graded essay feedback.",
        "domain": "education",
        "autonomy": "full",
        "flags": all_false_flags(
            education_scoring_or_access=True, improves_previous_human_activity=True
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["article_6_3_exception_candidate"] is True
    assert envelope["status"] == "requires_human_review"
    assert "eu-ai-act:article-6:paragraph-3:point-b" in envelope["source_nodes"]


def test_profiling_cancels_derogation_candidacy(dump, node_ids):
    features = {
        "description": "Pre-screening tool that profiles applicants before review.",
        "domain": "education",
        "autonomy": "advisory",
        "flags": all_false_flags(
            education_scoring_or_access=True,
            preparatory_or_narrow_procedural_task=True,
            profiling_of_natural_persons=True,
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["article_6_3_exception_candidate"] is False
    assert (
        "eu-ai-act:article-6:paragraph-3:subparagraph-3" in envelope["source_nodes"]
    )


# Article 6(1) embedded-product route ------------------------------------------


def test_annex_i_route_is_high_risk_without_derogation(dump, node_ids):
    features = {
        "description": "Vision safety component in an industrial machine.",
        "domain": "manufacturing",
        "flags": all_false_flags(
            annex_i_covered_product=True,
            third_party_conformity_assessment_required=True,
            preparatory_or_narrow_procedural_task=True,
        ),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["annex_iii_category"] is None
    # The 6(3) derogation only derogates from 6(2); never on the 6(1) route.
    assert answer["article_6_3_exception_candidate"] is False
    assert "eu-ai-act:article-6:paragraph-1" in envelope["source_nodes"]
    assert "eu-ai-act:annex-i" in envelope["source_nodes"]
    assert envelope["status"] == "potentially_applicable"


def test_annex_i_route_unresolved_third_party_fact_never_settles(dump, node_ids):
    features = {
        "description": "Safety component of a regulated product.",
        "domain": "manufacturing",
        "flags": all_false_flags(annex_i_covered_product=True)
        | {"third_party_conformity_assessment_required": None},
    }
    features["flags"].pop("third_party_conformity_assessment_required")
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "uncertain"
    assert envelope["status"] == "requires_human_review"
    assert any(
        "third_party_conformity_assessment_required" in fact
        for fact in envelope["missing_facts"]
    )


def test_annex_i_route_explicitly_ruled_out_continues_ladder(dump, node_ids):
    features = {
        "description": "Component of a product that needs no third-party assessment.",
        "domain": "consumer",
        "flags": all_false_flags(annex_i_covered_product=True),
    }
    envelope = classify_ai_system(features, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["risk_category"] == "minimal_or_none"
    assert any("article_6_1" in r for r in envelope["answer"]["rationale"])


# Input validation ------------------------------------------------------------


def test_invalid_input_returns_not_applicable_never_raises(dump, node_ids):
    for bad in (
        {},  # description required
        {"description": "short"},  # minLength 10
        {"description": "long enough description", "flags": {"not_a_flag": True}},
        {"description": "long enough description", "autonomy": "sentient"},
    ):
        envelope = classify_ai_system(bad, dump)
        assert_envelope_invariants(envelope, node_ids)
        assert envelope["status"] == "not_applicable"
        assert envelope["answer"]["risk_category"] is None
        assert envelope["missing_facts"], f"validation errors missing for {bad}"
        assert all("schema validation" in f for f in envelope["missing_facts"])


# Rule table grounding: hardcoded point markers match the real dump text ------


def test_article_5_point_mapping_matches_dump_text(dump):
    nodes = {n["id"]: n for n in dump["nodes"]}
    expected_fragment = {
        "subliminal_or_manipulative": "subliminal techniques",
        "exploits_vulnerabilities": "exploits any of the vulnerabilities",
        "social_scoring": "social behaviour",
        "predictive_policing_profiling": "committing a criminal offence",
        "facial_image_scraping": "untargeted scraping of facial images",
        "emotion_recognition_workplace_or_education": "workplace and education institutions",
        "biometric_categorisation": "biometric categorisation systems",
    }
    for flag, (node_id, _) in ARTICLE_5_POINT_BY_FLAG.items():
        node = nodes[node_id]
        assert node["type"] == "Point"
        assert expected_fragment[flag] in node["text"], (flag, node_id)
    point_h = nodes[ARTICLE_5_POINT_H]
    assert "real-time" in point_h["text"]
    assert "law enforcement" in point_h["text"]


def test_annex_iii_category_nodes_exist_and_are_annex_items(dump):
    nodes = {n["id"]: n for n in dump["nodes"]}
    for rule in classify_module.ANNEX_III_RULES:
        node = nodes[rule["node"]]
        assert node["type"] == "AnnexItem", rule["node"]


# Determinism and purity ------------------------------------------------------


def test_classification_is_deterministic(dump):
    features = {
        "description": "Hospital emergency department triage support system.",
        "domain": "healthcare",
        "flags": all_false_flags(essential_services_access=True),
    }
    first = classify_ai_system(features, dump)
    second = classify_ai_system(features, dump)
    for key in ("answer", "status", "source_nodes", "source_spans", "missing_facts"):
        assert first[key] == second[key]


def test_no_model_client_imports_in_module_source():
    source = Path(classify_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "model_clients", "ModelClient", "fastmcp"):
        assert forbidden not in source, f"classify.py must not reference {forbidden}"
    for dash in (chr(0x2014), chr(0x2013)):
        assert dash not in source, "no em or en dashes"


def test_domain_fallback_yields_to_explicitly_false_flags(dump):
    """Evidence-driven ladder fix (ELICITATION_ERRORS.md, scenario 161):
    education domain with education_scoring_or_access explicitly false must
    not gate high_risk on domain alone."""
    features = {
        "description": "Language learning chatbot for practicing conversation skills",
        "domain": "education",
        "flags": {
            "education_scoring_or_access": False,
            "interacts_with_natural_persons": True,
            **{f: False for f in (
                "social_scoring", "subliminal_or_manipulative",
                "exploits_vulnerabilities", "predictive_policing_profiling",
                "facial_image_scraping", "emotion_recognition_workplace_or_education",
                "biometric_categorisation", "real_time_remote_biometric_public",
            )},
        },
    }
    envelope = classify_ai_system(features, dump)
    assert envelope["answer"]["risk_category"] == "transparency_only"
    assert any("scenario 161" in r for r in envelope["answer"]["rationale"])

    # unknown flags keep the domain match (unknown is never false)
    features_unknown = dict(features)
    features_unknown["flags"] = {
        k: v for k, v in features["flags"].items() if k != "education_scoring_or_access"
    }
    envelope2 = classify_ai_system(features_unknown, dump)
    assert envelope2["answer"]["risk_category"] == "high_risk"

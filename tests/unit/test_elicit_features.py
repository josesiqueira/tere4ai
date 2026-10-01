"""Tests for the feature elicitor (LLM extracts facts, rules decide)."""

import json
from pathlib import Path

from tere4ai.elicit_features import elicit_features
from tere4ai.extract_norms.model_clients import FakeClient

DESC = "A chatbot that answers shopper questions and tracks their mood at work."


def test_valid_elicitation_passes_schema_and_keeps_description():
    payload = {
        "domain": "consumer",
        "autonomy": "advisory",
        "flags": {"interacts_with_natural_persons": True, "social_scoring": False},
        "description": "model tried to overwrite this",
    }
    fake = FakeClient({DESC[:30]: json.dumps(payload)})
    features, notes = elicit_features(DESC, fake)
    assert features is not None
    assert features["description"] == DESC, "original description always wins"
    assert features["flags"]["interacts_with_natural_persons"] is True


def test_unknown_fields_and_non_boolean_flags_stripped():
    payload = {
        "domain": "consumer",
        "risk_category": "high_risk",
        "flags": {"interacts_with_natural_persons": "yes", "social_scoring": False,
                  "invented_flag": True},
    }
    fake = FakeClient({DESC[:30]: json.dumps(payload)})
    features, _ = elicit_features(DESC, fake)
    assert features is not None
    assert "risk_category" not in features, "elicitor never outputs a classification"
    assert "invented_flag" not in features["flags"]
    assert "interacts_with_natural_persons" not in features["flags"], "non-boolean dropped"
    assert features["flags"]["social_scoring"] is False


def test_invalid_json_retries_then_none():
    calls = []

    class Bad:
        model = "fake"

        def complete(self, system, user):
            calls.append(1)
            return "not json at all"

    features, notes = elicit_features(DESC, Bad())
    assert features is None
    assert len(calls) == 2, "exactly one retry"
    assert any("failed" in n for n in notes)


def test_default_prompt_carries_the_dump_verbatim_article_3_definitions():
    """Missing-context audit F3: the elicitor sets flags whose terms have
    binding Article 3 definitions; the default prompt embeds those definitions
    VERBATIM from the graph dump. This guard fails if the prompt's definition
    text ever drifts from the dump's."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    dump_path = root / "data" / "graph_dumps" / "layer1.json"
    if not dump_path.is_file():
        import pytest

        pytest.skip("layer1.json dump not built")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    defs = {n["id"]: n for n in dump["nodes"] if n.get("type") == "Definition"}
    prompt = (root / "prompts" / "elicit_features" / "v4.md").read_text(
        encoding="utf-8"
    )
    for node_id in (
        "eu-ai-act:definition:biometric-identification",
        "eu-ai-act:definition:real-time-remote-biometric-identification-system",
        "eu-ai-act:definition:biometric-categorisation-system",
        "eu-ai-act:definition:emotion-recognition-system",
        "eu-ai-act:definition:safety-component",
        "eu-ai-act:definition:profiling",
    ):
        assert defs[node_id]["text"].strip() in prompt, (
            f"v4 prompt lost or drifted the verbatim definition {node_id}"
        )


def test_v4_prompt_carries_the_article_5_exculpating_facts():
    """Audit B25: v4 teaches the elicitor the Article 5 exculpating facts and
    the FRIA facts, so a genuinely harmful system resolves to prohibited
    instead of abstaining. Every new schema flag must be named in the prompt."""
    from pathlib import Path

    prompt = (
        Path(__file__).resolve().parents[2] / "prompts" / "elicit_features" / "v4.md"
    ).read_text(encoding="utf-8")
    for flag in (
        "causes_significant_harm",
        "social_score_detrimental_treatment",
        "supports_human_assessment_on_verifiable_facts",
        "emotion_recognition_medical_or_safety",
        "biometric_categorisation_lawful_or_law_enforcement",
        "rtrb_strictly_necessary_authorised",
        "creditworthiness_evaluation",
        "life_health_insurance_risk_pricing",
        "body_governed_by_public_law",
        "private_entity_providing_public_services",
    ):
        assert flag in prompt, f"v4 prompt omits the fact {flag}"


def test_default_prompt_version_is_v4():
    import inspect

    from tere4ai.elicit_features.elicitor import elicit_features

    signature = inspect.signature(elicit_features)
    assert signature.parameters["prompt_version"].default == "v4"


# DEC-18, B36.2: the three biometric facts and the point (d) and (g)
# exceptions are defined by the Act's words. Each passage is checked against
# the dump first, so a match in the schema or the prompt proves the copy is
# verbatim (build build-3b753e5e9297).

ROOT = Path(__file__).resolve().parents[2]
ACT_PASSAGES = {
    "eu-ai-act:definition:biometric-categorisation-system": (
        "biometric categorisation system means an AI system for the purpose of "
        "assigning natural persons to specific categories on the basis of their "
        "biometric data, unless it is ancillary to another commercial service and "
        "strictly necessary for objective technical reasons"
    ),
    "eu-ai-act:annex-iii:point-1:b": (
        "AI systems intended to be used for biometric categorisation, according to "
        "sensitive or protected attributes or characteristics based on the inference "
        "of those attributes or characteristics"
    ),
    "eu-ai-act:article-5:paragraph-1:point-g": (
        "biometric categorisation systems that categorise individually natural persons "
        "based on their biometric data to deduce or infer their race, political "
        "opinions, trade union membership, religious or philosophical beliefs, sex "
        "life or sexual orientation"
    ),
    "eu-ai-act:article-5:paragraph-1:point-d": (
        "this prohibition shall not apply to AI systems used to support the human "
        "assessment of the involvement of a person in a criminal activity, which is "
        "already based on objective and verifiable facts directly linked to a "
        "criminal activity"
    ),
}
# Point (g)'s exception, checked against the same node as its trait list.
POINT_G_EXCEPTION = (
    "this prohibition does not cover any labelling or filtering of lawfully acquired "
    "biometric datasets, such as images, based on biometric data or categorizing of "
    "biometric data in the area of law enforcement"
)
SCHEMA_PASSAGES = {
    "biometric_categorisation_system": ACT_PASSAGES["eu-ai-act:definition:biometric-categorisation-system"],
    "biometric_categorisation_sensitive_or_protected_attributes": ACT_PASSAGES["eu-ai-act:annex-iii:point-1:b"],
    "biometric_categorisation": ACT_PASSAGES["eu-ai-act:article-5:paragraph-1:point-g"],
    "supports_human_assessment_on_verifiable_facts": ACT_PASSAGES["eu-ai-act:article-5:paragraph-1:point-d"],
    "biometric_categorisation_lawful_or_law_enforcement": POINT_G_EXCEPTION,
}


def _act_nodes() -> dict:
    import pytest

    dump_path = ROOT / "data" / "graph_dumps" / "layer1.json"
    if not dump_path.is_file():
        pytest.skip("layer1.json dump not built")
    nodes = {n["id"]: n for n in json.loads(dump_path.read_text(encoding="utf-8"))["nodes"]}
    for node_id, passage in ACT_PASSAGES.items():
        assert passage in nodes[node_id]["text"], node_id
    assert POINT_G_EXCEPTION in nodes["eu-ai-act:article-5:paragraph-1:point-g"]["text"]
    return nodes


def test_schema_defines_the_biometric_facts_and_the_exceptions_by_the_acts_words():
    """Jose, 2026-10-01: three biometric facts defined by the Act's words,
    and the point (d) and (g) exceptions corrected to the Act's words."""
    _act_nodes()
    schema = json.loads(
        (ROOT / "schema" / "json_schemas" / "system_features.schema.json").read_text(encoding="utf-8")
    )
    flags = schema["properties"]["flags"]["properties"]
    for flag, passage in SCHEMA_PASSAGES.items():
        assert passage in flags[flag]["description"], flag

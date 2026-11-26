"""The nine values of `domain`, the refusal of any other value, the elicitor's drop (B185, DEC-33).

`domain` is one of the eight areas of Annex III or none_of_these_areas, or
unknown (null or absent). Any other value is refused as an input outside the
schema, with the refusal's wording read from the schema (`x-refusal`), and
for the four words that left the list (`x-removed-values`) the message that
names the value to use. No trimming and no change of case is applied. The
elicitor drops a proposed none_of_these_areas, and a proposed value outside
the list, as a dropped fact. The descriptions of `purposes`,
`affected_persons` and the two deployer facts say what no rule reads and
what the Act does not define. Offline: the published Layer 1 dump on disk,
skipped when it is absent; the elicitor's tests use mock model answers.

@implements: DEC-33
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.b184_cases import all_false, case

from tere4ai.elicit_features import elicit
from tere4ai.elicit_features.elicitor import DOMAIN_DROP_NONE_REASON, DOMAIN_DROP_OUTSIDE_REASON
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.classify import (
    ANNEX_III_POINT_OF_DOMAIN,
    ANNEX_III_RULES,
    classify_ai_system,
)
from tere4ai.mcp_server.removed_facts import domain_refusal

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"

VALUES = ["biometrics", "critical_infrastructure", "education", "employment", "essential_services",
          "law_enforcement", "migration", "justice", "none_of_these_areas"]

POINT_5_MESSAGE = (
    "use essential_services if the system is in the area of Annex III point 5, none_of_these_areas "
    "if it is in none of the eight areas, or leave the domain unknown"
)
CONSUMER_MESSAGE = "use none_of_these_areas if the system is in none of the eight areas, or leave the domain unknown"

DESCRIPTION = (
    "A chatbot on our bank's website answers customers' questions about opening "
    "hours and card fees."
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def test_domain_lists_the_nine_values_and_their_areas():
    domain = _schema()["properties"]["domain"]
    assert domain["enum"] == [*VALUES, None]
    assert domain["x-annex-iii-area-values"] == {v: n for n, v in enumerate(VALUES[:8], start=1)}
    assert domain["x-refusal"] == "domain '{value}' is not a value of the schema"
    assert domain["x-removed-values"] == {
        "healthcare": POINT_5_MESSAGE,
        "banking": POINT_5_MESSAGE,
        "insurance": POINT_5_MESSAGE,
        "consumer": CONSUMER_MESSAGE,
    }
    assert [r["domain"] for r in ANNEX_III_RULES] == VALUES[:8]
    assert ANNEX_III_POINT_OF_DOMAIN["essential_services"] == "eu-ai-act:annex-iii:point-5"
    assert ANNEX_III_POINT_OF_DOMAIN["biometrics"] == "eu-ai-act:annex-iii:point-1"


def test_each_area_value_names_a_heading_of_the_schema():
    schema = _schema()
    headings = schema["properties"]["flags"]["x-annex-iii-areas"]
    for number in schema["properties"]["domain"]["x-annex-iii-area-values"].values():
        assert str(number) in headings


@pytest.mark.parametrize("word,message", [
    ("banking", POINT_5_MESSAGE),
    ("healthcare", POINT_5_MESSAGE),
    ("insurance", POINT_5_MESSAGE),
    ("consumer", CONSUMER_MESSAGE),
])
def test_old_domain_words_are_refused_with_their_message(dump, word, message):
    env = classify_ai_system(case(all_false(), domain=word), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert f"domain '{word}' is not a value of the schema: {message}" in env["missing_facts"]


@pytest.mark.parametrize("word", ["Education", " education", "law enforcement", "email security", "​banking"])
def test_domain_is_not_trimmed_or_case_folded(dump, word):
    env = classify_ai_system(case(all_false(), domain=word), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert f"domain '{word}' is not a value of the schema" in env["missing_facts"]


@pytest.mark.parametrize("value", [["x"], 3])
def test_a_domain_of_another_type_is_refused_without_an_exception(dump, value):
    env = classify_ai_system({"description": "A test system for the refusal checks.", "domain": value, "flags": {}}, dump)
    assert env["status"] == "rejected_as_unsupported"


def test_the_refusal_of_another_type_is_its_json_text():
    assert domain_refusal(["x"]) == "domain '[\"x\"]' is not a value of the schema"
    assert domain_refusal(3) == "domain '3' is not a value of the schema"
    assert domain_refusal("Banking") == "domain 'Banking' is not a value of the schema"
    assert domain_refusal("consumer") == f"domain 'consumer' is not a value of the schema: {CONSUMER_MESSAGE}"


def test_the_rejected_answer_carries_its_fields_and_reads_no_domain(dump):
    env = classify_ai_system(case(all_false(), domain="banking"), dump)
    a = env["answer"]
    assert a["risk_category"] is None
    assert a["fact_conflicts"] == [] and a["annex_iii_listed_uses"] == []
    assert a["high_risk_routes"] == [] and a["annex_i_section"] is None
    assert a["application_dates"] == []
    assert a["legal_text"]
    assert env["source_nodes"] == []


def test_a_value_of_the_list_and_null_are_not_refused(dump):
    for value in [*VALUES, None]:
        features = case(all_false())
        features["domain"] = value
        env = classify_ai_system(features, dump)
        assert env["status"] != "rejected_as_unsupported", value
        assert not any("is not a value of the schema" in line for line in env["missing_facts"])


def _reply(proposed: object) -> dict:
    return {
        "features": {"domain": proposed, "flags": {"interacts_with_natural_persons": True}},
        "quotes": {
            "domain": "on our bank's website",
            "flags.interacts_with_natural_persons": "A chatbot on our bank's website answers",
        },
    }


@pytest.mark.parametrize("proposed,reason", [
    ("none_of_these_areas", DOMAIN_DROP_NONE_REASON),
    ("banking", DOMAIN_DROP_OUTSIDE_REASON.format(refusal=domain_refusal("banking"))),
])
def test_the_elicitor_drops_a_domain_it_cannot_take(dump, proposed, reason):
    reply = _reply(proposed)
    result = elicit(DESCRIPTION, FakeClient({DESCRIPTION[:30]: json.dumps(reply)}), dump=dump,
                    snapshots_dir=SNAPSHOTS_DIR)
    assert result.features is not None and "domain" not in result.features
    assert {"path": "domain", "reason": reason} in result.dropped
    assert result.features["flags"] == {"interacts_with_natural_persons": True}
    assert "domain" not in result.quotes
    assert not any(note.startswith("quote for domain ignored") for note in result.notes)


@pytest.mark.parametrize("proposed,reason", [
    ("none_of_these_areas", DOMAIN_DROP_NONE_REASON),
    ("Education", DOMAIN_DROP_OUTSIDE_REASON.format(refusal=domain_refusal("Education"))),
])
def test_the_elicitor_drops_a_domain_it_cannot_take_without_quotes(proposed, reason):
    reply = {"domain": proposed, "flags": {"interacts_with_natural_persons": True}}
    # v5 renders no provision, so the dump it is given is not read.
    result = elicit(DESCRIPTION, FakeClient({DESCRIPTION[:30]: json.dumps(reply)}), dump={},
                    snapshots_dir=SNAPSHOTS_DIR, prompt_version="v5")
    assert result.features is not None and "domain" not in result.features
    assert result.dropped == [{"path": "domain", "reason": reason}]


def test_the_elicitor_keeps_a_value_of_the_list(dump):
    reply = _reply("essential_services")
    result = elicit(DESCRIPTION, FakeClient({DESCRIPTION[:30]: json.dumps(reply)}), dump=dump,
                    snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["domain"] == "essential_services"
    assert result.dropped == []


def test_the_drop_reasons_are_worded_once():
    assert DOMAIN_DROP_NONE_REASON == (
        "none_of_these_areas is never taken from a proposal (DEC-33); the domain is left unknown"
    )
    assert DOMAIN_DROP_OUTSIDE_REASON == "{refusal}; the domain is left unknown"


def test_descriptions_say_what_no_rule_reads():
    p = _schema()["properties"]
    assert p["purposes"]["description"].endswith("Context only: no classification rule reads it.")
    assert p["affected_persons"]["description"].endswith("Context only: no classification rule reads it.")
    for key in ("body_governed_by_public_law", "private_entity_providing_public_services"):
        d = p["deployer"]["properties"][key]["description"]
        assert "deployers that are bodies governed by public law, or are private entities providing public services" in d
        assert d.endswith("The Act defines neither category.")
    assert p["domain"]["description"].startswith("The Annex III area the person places the system in")
    assert p["domain"]["description"].endswith("the answer requires human review (DEC-33).")

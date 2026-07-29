"""Elicitation envelope: proposals only, never a classification.

The elicited facts are proposals until a human confirms them, so the
envelope status is requires_human_review by construction (DEC-13 keeps
the deterministic ladder the only decision path).
"""

import json

from tere4ai.elicit_features.elicitor import schema_flag_names
from tere4ai.mcp_server.elicit import elicit_envelope
from tere4ai.mcp_server.tools import SECTION_8_ENVELOPE_FIELDS


class FakeGenerator:
    def __init__(self, payload):
        self._payload = payload

    def complete(self, system, user):
        return self._payload


def test_schema_flag_names_lists_all_34_flags():
    names = schema_flag_names()
    assert len(names) == 34
    assert names == sorted(names)
    assert "social_scoring" in names
    assert "creditworthiness_evaluation" in names


def test_elicit_envelope_is_a_section8_proposal():
    gen = FakeGenerator(json.dumps({
        "domain": "email security",
        "flags": {"social_scoring": False, "interacts_with_natural_persons": False},
    }))
    env = elicit_envelope("A spam filter for a small company's inboxes.",
                          gen, graph_version="build-test")
    assert set(env.keys()) == set(SECTION_8_ENVELOPE_FIELDS)
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.5
    assert env["answer"]["features"]["flags"]["social_scoring"] is False
    assert "risk_category" not in json.dumps(env["answer"])
    unspecified = env["missing_facts"]
    assert "flag not elicited: subliminal_or_manipulative" in unspecified
    assert not any("social_scoring" in m for m in unspecified)


def test_elicit_envelope_degrades_when_elicitation_fails():
    env = elicit_envelope("Too vague.", FakeGenerator("not json"),
                          graph_version="build-test")
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.0
    assert env["answer"] is None
    assert env["missing_facts"] == ["elicitation failed; fill the facts manually"]

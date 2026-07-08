"""Tests for the feature elicitor (LLM extracts facts, rules decide)."""

import json

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

"""Cross-cutting Section 8 envelope contract over the live facade.

@implements: DEC-08
@grounded_by: REF-16, REF-31

The per-endpoint facade tests each assert their own answer fields. This
file asserts the UNIVERSAL contract that architecture.md Section 8 makes a
MUST: every user-facing tool response, from every envelope-returning
endpoint and across every classification tier, carries exactly the Section
8 field set, a status drawn only from the calibrated vocabulary (never a
compliance claim), and the non-legal-advice notice. It fires the real
assembled app over the committed graph dumps; paid endpoints use scripted
FakeClients so no model is called.

The point is drift protection at the honesty boundary: if a new endpoint,
or an edited make_envelope, ever emits a response that is not a complete,
calibrated Section 8 envelope, this test fails even when the endpoint's own
test still passes.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    SECTION_8_ENVELOPE_FIELDS,
    STATUS_VOCABULARY,
    make_envelope,
)

ACCEPTED_NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
ACCEPTED_NORM_ID_2 = "norm:eu-ai-act:article-9:paragraph-2:n2"

_PROHIBITION_FALSE = {
    "subliminal_or_manipulative": False,
    "exploits_vulnerabilities": False,
    "social_scoring": False,
    "predictive_policing_profiling": False,
    "facial_image_scraping": False,
    "emotion_recognition_workplace_or_education": False,
    "biometric_categorisation": False,
    "real_time_remote_biometric_public": False,
    "law_enforcement_use": False,
}

# One payload per deterministic classification tier, so the contract is
# checked on prohibited, high_risk, and minimal answers alike, not just the
# happy high-risk path.
HIGH_RISK_FEATURES = {
    "description": "AI system that screens and ranks job applicants for recruitment.",
    "domain": "employment",
    "flags": dict(_PROHIBITION_FALSE),
}
PROHIBITED_FEATURES = {
    "description": "Government system that scores citizens' trustworthiness.",
    "flags": {"social_scoring": True},
}
MINIMAL_FEATURES = {
    "description": "An email spam filter.",
    "flags": dict(_PROHIBITION_FALSE),
}

SCORES = {
    "semantic_similarity": 0.9,
    "normative_relevance": 0.85,
    "operational_utility": 0.8,
    "evidence_strength": 0.75,
    "judge_confidence": 0.9,
}
JUDGE_ACCEPT = json.dumps(
    {"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norms."}
)


@pytest.fixture()
def client():
    with TestClient(facade.create_app()) as test_client:
        yield test_client


@pytest.fixture()
def fake_models(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "tere4ai.mcp_server.evidence.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl"
    )
    monkeypatch.setattr(
        "tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl"
    )

    def install(gen_scripted: dict, judge_scripted: dict) -> None:
        monkeypatch.setattr(facade, "load_model_config", lambda env=None: None)
        monkeypatch.setattr(
            facade, "OpenAIGenerator", lambda cfg: FakeClient(gen_scripted, model="fake-generator")
        )
        monkeypatch.setattr(
            facade, "AnthropicJudge", lambda cfg: FakeClient(judge_scripted, model="fake-judge")
        )

    return install


def assert_section8_envelope(env: dict) -> None:
    """Every invariant Section 8 promises for a user-facing response."""
    assert set(env) == set(SECTION_8_ENVELOPE_FIELDS), (
        f"envelope keys differ from Section 8 set: "
        f"missing={set(SECTION_8_ENVELOPE_FIELDS) - set(env)}, "
        f"extra={set(env) - set(SECTION_8_ENVELOPE_FIELDS)}"
    )
    assert env["status"] in STATUS_VOCABULARY, f"status {env['status']!r} off-vocabulary"
    assert env["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    assert isinstance(env["confidence"], (int, float)) and 0.0 <= env["confidence"] <= 1.0
    assert env["graph_version"], "graph_version must be non-empty"
    # generated_at is a parseable ISO-8601 timestamp.
    datetime.fromisoformat(env["generated_at"])
    for key in ("source_nodes", "source_spans", "legal_status_notes", "missing_facts"):
        assert isinstance(env[key], list), f"{key} must be a list"


def test_make_envelope_matches_the_declared_field_set():
    """The constructor and the declared contract constant cannot drift."""
    env = make_envelope(answer={"x": 1}, status="not_applicable", graph_version="build-test")
    assert set(env) == set(SECTION_8_ENVELOPE_FIELDS)


@pytest.mark.parametrize(
    "features", [HIGH_RISK_FEATURES, PROHIBITED_FEATURES, MINIMAL_FEATURES]
)
def test_classify_every_tier_is_a_calibrated_envelope(client, features):
    env = client.post("/api/classify", json={"features": features}).json()
    assert_section8_envelope(env)
    # The tier lives in answer.risk_category, never as a status compliance claim.
    assert "risk_category" in env["answer"]


def test_requirements_response_is_a_calibrated_envelope(client):
    classification = client.post("/api/classify", json={"features": HIGH_RISK_FEATURES}).json()
    env = client.post(
        "/api/requirements",
        json={"classification": classification["answer"], "actor": "provider"},
    ).json()
    assert_section8_envelope(env)


def test_explain_response_is_a_calibrated_envelope(client):
    env = client.post("/api/explain", json={"norm_id": ACCEPTED_NORM_ID}).json()
    assert_section8_envelope(env)


def test_trace_response_is_a_calibrated_envelope(client):
    env = client.post("/api/trace", json={"id": "eu-ai-act:article-9"}).json()
    assert_section8_envelope(env)


def test_evidence_response_is_a_calibrated_envelope(client, fake_models):
    quote = "We maintain a documented risk management system"
    gen_response = json.dumps(
        {"assessment": "satisfied", "quotes": [quote], "gaps": [], "rationale": "Documented."}
    )
    fake_models({ACCEPTED_NORM_ID: gen_response}, {"evaluate_project_evidence": JUDGE_ACCEPT})
    env = client.post(
        "/api/evidence",
        json={
            "norm_id": ACCEPTED_NORM_ID,
            "artifact_type": "risk_management_plan",
            "content": quote + " reviewed quarterly with tracked mitigations.",
        },
    ).json()
    assert_section8_envelope(env)


def test_backlog_response_is_a_calibrated_envelope(client, fake_models):
    gen_response = json.dumps(
        {
            "items": [
                {
                    "title": "Establish the risk management system",
                    "description": "Stand up a documented, maintained risk process.",
                    "norm_ids": [ACCEPTED_NORM_ID],
                    "suggested_evidence": ["risk_management_plan"],
                    "priority": "must",
                }
            ]
        }
    )
    fake_models({"UNTRUSTED PROJECT CONTEXT": gen_response}, {"generate_control_backlog": JUDGE_ACCEPT})
    env = client.post(
        "/api/backlog",
        json={
            "norm_ids": [ACCEPTED_NORM_ID, ACCEPTED_NORM_ID_2],
            "system_context": "Hospital triage support system, advisory only.",
        },
    ).json()
    assert_section8_envelope(env)


def test_no_endpoint_ever_emits_a_compliance_status(client):
    """The forbidden statuses of Section 8 can never appear on the wire."""
    forbidden = {"compliant", "certified", "legally_approved", "legally approved"}
    for features in (HIGH_RISK_FEATURES, PROHIBITED_FEATURES, MINIMAL_FEATURES):
        env = client.post("/api/classify", json={"features": features}).json()
        assert env["status"] not in forbidden
        assert env["status"] in STATUS_VOCABULARY

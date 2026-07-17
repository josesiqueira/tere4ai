"""Unit tests for the M3 HTTP facade (DEC-08, REF-31).

The facade calls the same pure functions the MCP server exposes over the
real committed graph dumps. All paid model constructors are monkeypatched
to FakeClient, so NO model API is ever called from this file. Runtime log
writes are redirected to tmp_path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.judge.config import ModelConfigError

# The judged dumps are published build artifacts (gitignored), so a fresh
# clone has none; skip cleanly instead of failing, checking the same dump
# location the facade itself resolves (default dir or TERE4AI_DUMP_DIR).
_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not all(
        (_DUMP_DIR / name).is_file()
        for name in ("layer1.json", "norms_core.json", "alignments_core.json")
    ),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)

# Triage scenario: hospital emergency-department triage support. All
# prohibition-relevant flags are known false, so the deterministic ladder
# settles on high_risk via Annex III point 5 (essential services incl.
# healthcare) without a review downgrade.
TRIAGE_FEATURES = {
    "description": (
        "An AI triage assistant that prioritises emergency department "
        "patients by predicted urgency to support clinician decisions."
    ),
    "domain": "healthcare",
    "autonomy": "advisory",
    "flags": {
        "essential_services_access": True,
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

ACCEPTED_NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
ACCEPTED_NORM_ID_2 = "norm:eu-ai-act:article-9:paragraph-2:n2"

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
    """Install FakeClient constructors so paid endpoints never hit a network."""
    # Runtime logs go to tmp_path, never the repo review queue.
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


def test_health_reports_graph_and_norms_builds(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["graph_version"].startswith("build-")
    assert body["norms_build"].startswith("build-")


def test_classify_triage_scenario_is_high_risk_with_annex_iii_citation(client):
    response = client.post("/api/classify", json={"features": TRIAGE_FEATURES})
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["answer"]["annex_iii_category"] == "eu-ai-act:annex-iii:point-5"
    assert envelope["status"] == "potentially_applicable"
    assert "eu-ai-act:annex-iii:point-5" in envelope["source_nodes"]
    assert "eu-ai-act:article-6:paragraph-2" in envelope["source_nodes"]
    assert envelope["source_spans"]
    assert envelope["non_legal_advice_notice"]
    # Deterministic and free: no paid marker.
    assert facade.PAID_HEADER not in response.headers


def test_classify_invalid_features_surfaces_schema_errors_cleanly(client):
    response = client.post(
        "/api/classify", json={"features": {"description": "short", "bogus_field": 1}}
    )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["risk_category"] is None
    assert any("schema validation" in fact for fact in envelope["missing_facts"])


def test_requirements_returns_grouped_accepted_norms(client):
    classification = client.post("/api/classify", json={"features": TRIAGE_FEATURES}).json()
    response = client.post("/api/requirements", json={"classification": classification})
    assert response.status_code == 200
    envelope = response.json()
    grouped = envelope["answer"]["requirements_by_article"]
    assert "article-9" in grouped
    assert all(
        entry["norm_id"] and entry["source_span_id"] for entry in grouped["article-9"]
    )
    summary = envelope["answer"]["summary"]
    assert summary["returned"] == summary["total_accepted_in_scope"] > 0
    assert envelope["status"] == "applicable_missing_evidence"
    assert "eu-ai-act:article-9" in envelope["source_nodes"]


def test_evidence_unknown_norm_id_returns_clean_404(client, fake_models):
    fake_models({}, {})
    response = client.post(
        "/api/evidence",
        json={
            "norm_id": "norm:eu-ai-act:article-999:n1",
            "artifact_type": "test_report",
            "content": "some evidence text",
        },
    )
    assert response.status_code == 404
    body = response.json()
    assert "unknown norm_id" in body["error"]
    assert "Traceback" not in json.dumps(body)


def test_evidence_known_norm_passes_envelope_through_with_paid_header(client, fake_models):
    quote = "We maintain a documented risk management system"
    content = quote + " reviewed quarterly with tracked mitigations."
    gen_response = json.dumps(
        {
            "assessment": "satisfied",
            "quotes": [quote],
            "gaps": [],
            "rationale": "The plan documents the risk management system.",
        }
    )
    fake_models(
        {ACCEPTED_NORM_ID: gen_response},
        {"evaluate_project_evidence": JUDGE_ACCEPT},
    )
    response = client.post(
        "/api/evidence",
        json={
            "norm_id": ACCEPTED_NORM_ID,
            "artifact_type": "risk_management_plan",
            "content": content,
        },
    )
    assert response.status_code == 200
    assert response.headers[facade.PAID_HEADER] == "true"
    envelope = response.json()
    assert envelope["status"] == "satisfied_with_evidence"
    assert envelope["judge_verdict"] == "accepted"
    assert envelope["answer"]["assessment"] == "satisfied"
    assert envelope["answer"]["quotes"] == [quote]
    assert envelope["answer"]["judge_rationale"] == "Grounded in the cited norms."
    assert envelope["source_nodes"] == ["eu-ai-act:article-9:paragraph-1"]
    assert envelope["source_spans"] == [{"span_id": "span:009.001"}]


def test_backlog_items_cite_only_input_norm_ids(client, fake_models):
    gen_response = json.dumps(
        {
            "items": [
                {
                    "title": "Establish the risk management system",
                    "description": "Stand up a documented, maintained risk process.",
                    "norm_ids": [ACCEPTED_NORM_ID],
                    "suggested_evidence": ["risk_management_plan"],
                    "priority": "must",
                },
                {
                    "title": "Hallucinated item",
                    "description": "Cites a norm outside the input set.",
                    "norm_ids": ["norm:eu-ai-act:article-999:n1"],
                    "suggested_evidence": [],
                    "priority": "must",
                },
            ]
        }
    )
    fake_models(
        {"UNTRUSTED PROJECT CONTEXT": gen_response},
        {"generate_control_backlog": JUDGE_ACCEPT},
    )
    response = client.post(
        "/api/backlog",
        json={
            "norm_ids": [ACCEPTED_NORM_ID, ACCEPTED_NORM_ID_2],
            "system_context": "Hospital triage support system, advisory only.",
        },
    )
    assert response.status_code == 200
    assert response.headers[facade.PAID_HEADER] == "true"
    envelope = response.json()
    input_ids = {ACCEPTED_NORM_ID, ACCEPTED_NORM_ID_2}
    assert envelope["answer"]["items"], "at least one item must survive"
    for item in envelope["answer"]["items"]:
        assert set(item["norm_ids"]) <= input_ids
    # The hallucinated citation never surfaces; it is dropped and counted.
    assert envelope["answer"]["dropped_items"] == 1
    assert envelope["status"] == "applicable_missing_evidence"
    assert envelope["judge_verdict"] == "accepted"


def test_backlog_unknown_norm_ids_return_clean_404(client, fake_models):
    fake_models({}, {})
    response = client.post(
        "/api/backlog",
        json={"norm_ids": ["norm:nope:n1"], "system_context": "ctx"},
    )
    assert response.status_code == 404
    assert response.json()["unknown_norm_ids"] == ["norm:nope:n1"]


def test_missing_dumps_yield_clean_503_payload(tmp_path):
    with TestClient(facade.create_app(tmp_path)) as bad_client:
        health = bad_client.get("/api/health")
        assert health.status_code == 503
        assert health.json()["ok"] is False
        assert "graph dumps unavailable" in health.json()["error"]
        classify = bad_client.post("/api/classify", json={"features": TRIAGE_FEATURES})
        assert classify.status_code == 503
        assert "graph dumps unavailable" in classify.json()["error"]
        assert "Traceback" not in classify.text


def test_model_config_error_returns_clean_json_error(client, monkeypatch):
    message = (
        "missing model configuration: OPENAI_API_KEY (generator API key). "
        "Set these in .env (see .env.example); the pipeline never falls "
        "back to defaults."
    )

    def raise_config_error(env=None):
        raise ModelConfigError(message)

    monkeypatch.setattr(facade, "load_model_config", raise_config_error)
    response = client.post(
        "/api/evidence",
        json={
            "norm_id": ACCEPTED_NORM_ID,
            "artifact_type": "risk_management_plan",
            "content": "some evidence",
        },
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == message
    assert "Traceback" not in response.text


def test_discovery_endpoints(client):
    r = client.get("/llms.txt")
    assert r.status_code == 200
    assert "does not certify" in r.text and "classify" in r.text

    r = client.get("/.well-known/tere4ai.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["endpoints"]["evidence"]["paid"] is True
    assert doc["endpoints"]["classify"]["paid"] is False
    assert "compliant" not in " ".join(doc["status_vocabulary"])


def test_discovery_advertises_exactly_the_real_api_routes(client):
    """The .well-known endpoints block must match the app's real /api routes.

    That block is a hand-maintained literal in the facade, so it can drift
    from reality: an added, renamed, or removed endpoint would silently make
    the agent-readiness contract lie. This pins the advertisement to the
    actual FastAPI routes in both directions, so drift fails the build
    (architecture Section 8 honesty; the agent-readiness surface, task 36).
    """
    import re

    from fastapi.routing import APIRoute

    def _template(path: str) -> str:
        # Normalise FastAPI path-converter annotations ({id:path}) to the
        # human-facing template ({id}) the discovery doc advertises; the
        # converter is an internal routing detail, not part of the contract.
        return re.sub(r"\{(\w+):[^}]+\}", r"{\1}", path)

    doc = client.get("/.well-known/tere4ai.json").json()
    advertised = {
        (meta["method"], _template(meta["path"])) for meta in doc["endpoints"].values()
    }
    real_api = {
        (method, _template(route.path))
        for route in client.app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods
        if method in {"GET", "POST"}
    }
    assert advertised == real_api, (
        f"discovery drift: advertised-not-real={advertised - real_api}, "
        f"real-not-advertised={real_api - advertised}"
    )


# Explanation and trace endpoints (deterministic, free) ------------------------


def test_explain_endpoint_returns_full_explanation(client):
    response = client.post("/api/explain", json={"norm_id": ACCEPTED_NORM_ID})
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["norm_id"] == ACCEPTED_NORM_ID
    assert "risk management system" in answer["source"]["text"]
    assert answer["hleg_alignments"]["accepted"]
    assert answer["span_trace"]
    assert envelope["non_legal_advice_notice"]
    # Deterministic and free: no paid marker.
    assert facade.PAID_HEADER not in response.headers


def test_explain_endpoint_unknown_norm_is_clean_envelope(client):
    response = client.post(
        "/api/explain", json={"norm_id": "norm:eu-ai-act:article-999:n1"}
    )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["found"] is False
    assert envelope["missing_facts"]
    assert "Traceback" not in response.text


def test_trace_endpoint_hleg_id_returns_reified_chains(client):
    response = client.post(
        "/api/trace", json={"id": "hleg:technical-robustness-and-safety"}
    )
    assert response.status_code == 200
    envelope = response.json()
    answer = envelope["answer"]
    assert answer["mode"] == "hleg_target"
    assert answer["assertion_count"] >= 1
    for assertion in answer["assertions"]:
        assert assertion["mapping_run"]["generator_model"]
        assert assertion["judge_run"]["judge_model"]
        assert assertion["evidence"]["source_evidence_span_ids"]
        assert assertion["evidence"]["target_evidence_span_ids"]
    assert facade.PAID_HEADER not in response.headers


def test_trace_endpoint_unknown_id_is_clean_envelope(client):
    response = client.post("/api/trace", json={"id": "hleg:no-such-requirement"})
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["found"] is False


def test_span_endpoint_returns_verified_slice(client):
    response = client.get("/api/span/span:009.001")
    assert response.status_code == 200
    body = response.json()
    assert body["span_id"] == "span:009.001"
    assert "risk management system" in body["text"]
    assert len(body["sha256"]) == 64
    assert facade.PAID_HEADER not in response.headers


def test_span_endpoint_resolves_hleg_target_spans(client):
    response = client.get("/api/span/span:hleg:req2")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_file"] == "hleg_ethics_guidelines_2019_en_v1text.txt"
    assert "robustness" in body["text"].lower()


def test_span_endpoint_unknown_span_returns_clean_404(client):
    response = client.get("/api/span/span:no-such-span")
    assert response.status_code == 404
    body = response.json()
    assert body["span_id"] == "span:no-such-span"
    assert "does not match any node" in body["error"]
    assert "Traceback" not in response.text

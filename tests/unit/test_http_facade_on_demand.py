"""DEC-24 (spec G D-G74 (2), (3)): the facade's generator-only mode on
/api/backlog, its signed record, its refusals before any model call, and
/api/health's readiness of each route (B138 builds phase 5; /api/evidence's
on-demand mode is B140's). FakeClient only: no model API is called; the
runtime log goes to tmp_path."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.http_facade.signed import verify
from tere4ai.judge.config import ModelConfigError

_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not all((_DUMP_DIR / name).is_file() for name in ("layer1.json", "norms_core.json", "alignments_core.json")),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)

KEY = bytes(range(32))
ACCEPTED_NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
ACCEPTED_NORM_ID_2 = "norm:eu-ai-act:article-9:paragraph-2:n2"
CONTEXT = "Opens the office door for staff and keeps a log of each event."
CALLER = {"project": "22222222-2222-4222-8222-222222222222", "repository_run": "11111111-1111-4111-8111-111111111111", "document": None}
ITEMS = [{"title": "Establish the system", "description": "Do it.", "norm_ids": [ACCEPTED_NORM_ID], "suggested_evidence": ["a plan"],
          "priority": "must", "requirement_type": "process"}]


@pytest.fixture()
def client():
    with TestClient(facade.create_app()) as test_client:
        yield test_client


@pytest.fixture()
def generator_only(monkeypatch, tmp_path):
    """The generator-only mode with a FakeClient generator; building a judge
    or the inline clients fails the test."""
    monkeypatch.setattr("tere4ai.mcp_server.evidence.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
    monkeypatch.setattr("tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
    monkeypatch.setattr(facade, "load_signing_key", lambda env=None: KEY)
    monkeypatch.setattr(facade, "load_generator_config", lambda env=None: None)

    def no_inline_clients():
        raise AssertionError("the generator-only mode built the inline clients")

    monkeypatch.setattr(facade, "_build_paid_clients", no_inline_clients)

    def install(scripted: dict) -> FakeClient:
        generator = FakeClient(scripted, model="gpt-gen")
        monkeypatch.setattr(facade, "OpenAIGenerator", lambda cfg: generator)
        return generator

    return install


def _build(client) -> str:
    return client.get("/api/health").json()["norms_build"]


def _backlog(client, **over):
    body = {"norm_ids": [ACCEPTED_NORM_ID_2, ACCEPTED_NORM_ID], "system_context": CONTEXT, "judge": "on_demand", "caller": CALLER, **over}
    if "expected_norms_build" not in over:
        body["expected_norms_build"] = _build(client)
    return client.post("/api/backlog", json=body)


def test_an_on_demand_backlog_is_not_checked_and_signs_its_items_for_its_caller(client, generator_only):
    generator_only({ACCEPTED_NORM_ID: json.dumps({"items": ITEMS})})
    response = _backlog(client)
    assert response.status_code == 200 and response.headers[facade.PAID_HEADER] == "true"
    envelope = response.json()
    assert (envelope["status"], envelope["judge_verdict"]) == ("requires_human_review", "not_checked")
    record = envelope["answer"]["signed_record"]
    assert verify(record, envelope["answer"]["signature"], KEY)
    assert (record["route"], record["caller"]) == ("/api/backlog", CALLER)
    assert record["norm_ids"] == sorted([ACCEPTED_NORM_ID, ACCEPTED_NORM_ID_2]) and record["core"] == {"items": envelope["answer"]["items"]}
    assert record["norms_build"] == _build(client) and record["graph_version"] == envelope["graph_version"]
    assert record["untrusted_sha256"] == hashlib.sha256(CONTEXT.encode("utf-8")).hexdigest()
    assert record["generator_model"] == "gpt-gen" and record["judge_prompt"]["name"] == "runtime_grounding"


def test_another_loaded_norms_build_is_refused_before_any_model_call(client, generator_only):
    generator = generator_only({})
    response = _backlog(client, expected_norms_build="build-elsewhere")
    assert response.status_code == 409
    body = response.json()
    assert body["model_called"] is False and body["expected_norms_build"] == "build-elsewhere"
    assert generator.calls == []


def test_a_missing_signing_key_or_generator_setting_is_refused_before_any_model_call(client, generator_only, monkeypatch):
    generator = generator_only({})

    def missing(env=None):
        raise ModelConfigError("configuration error: TERE4AI_ANSWER_SIGNING_KEY is not set")

    monkeypatch.setattr(facade, "load_signing_key", missing)
    response = _backlog(client)
    assert (response.status_code, response.json()["model_called"]) == (503, False)
    assert "TERE4AI_ANSWER_SIGNING_KEY" in response.json()["error"]
    monkeypatch.setattr(facade, "load_signing_key", lambda env=None: KEY)

    def no_generator(env=None):
        raise ModelConfigError("missing model configuration for the generator: OPENAI_API_KEY")

    monkeypatch.setattr(facade, "load_generator_config", no_generator)
    response = _backlog(client)
    assert (response.status_code, response.json()["model_called"]) == (503, False)
    assert generator.calls == []


def test_an_unloaded_graph_on_demand_says_no_model_was_called(client, generator_only):
    generator = generator_only({})
    build = _build(client)
    client.app.state.load_error = "graph dumps unavailable: mock"
    on_demand = _backlog(client, expected_norms_build=build)
    inline = client.post("/api/backlog", json={"norm_ids": [ACCEPTED_NORM_ID], "system_context": CONTEXT})
    assert (on_demand.status_code, on_demand.json()["model_called"]) == (503, False)
    assert inline.status_code == 503 and "model_called" not in inline.json()
    assert generator.calls == []


def test_an_on_demand_request_names_its_build_and_its_caller(client, generator_only):
    generator_only({})
    assert _backlog(client, caller=None).status_code == 422
    assert _backlog(client, expected_norms_build=None).status_code == 422


def test_an_unknown_norm_on_demand_says_no_model_was_called(client, generator_only):
    generator_only({})
    response = _backlog(client, norm_ids=["norm:eu-ai-act:article-999:n1"])
    assert (response.status_code, response.json()["model_called"]) == (404, False)


def test_a_degraded_on_demand_answer_is_not_signed(client, generator_only):
    generator_only({ACCEPTED_NORM_ID: "not json"})
    envelope = _backlog(client).json()
    assert envelope["judge_verdict"] != "not_checked" and "signed_record" not in envelope["answer"]


def test_health_reports_each_route_readiness_and_never_the_key(client, monkeypatch):
    monkeypatch.setenv("TERE4AI_ANSWER_SIGNING_KEY", "ab" * 32)
    routes = client.get("/api/health").json()["routes"]
    assert set(routes) == {"generator_only", "demo_judge", "signing_key"}
    assert routes["signing_key"] == {"present": True, "error": None}
    assert "ab" * 32 not in json.dumps(routes)


# Review I9: a model failure after the generator's request answers 502 with
# model_called true (billed); a deleted source is refused with 422 before any
# model call; another build is refused before any norm is looked up (R69).
def test_a_generator_failure_is_billed_and_a_deleted_source_or_another_build_is_not(client, generator_only, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("upstream overloaded")

    generator = generator_only({})
    real = facade.backlog_tool.generate_control_backlog_on_demand
    monkeypatch.setattr(facade.backlog_tool, "generate_control_backlog_on_demand", broken)
    response = _backlog(client)
    assert (response.status_code, response.json()["model_called"]) == (502, True)
    monkeypatch.setattr(facade.backlog_tool, "generate_control_backlog_on_demand", real)
    norms = client.app.state.norms
    norm = next(n for n in norms["norms"] if n.get("judge_verdict") == "accepted")
    moved = {**norm, "norm_id": "norm:eu-ai-act:article-10:paragraph-5:n9", "source_node_id": "eu-ai-act:article-10:paragraph-5"}
    monkeypatch.setitem(norms, "norms", [*norms["norms"], moved])
    deleted = _backlog(client, norm_ids=[moved["norm_id"]])
    assert (deleted.status_code, deleted.json()["model_called"]) == (422, False)
    unknown = _backlog(client, norm_ids=["norm:eu-ai-act:article-999:n1"], expected_norms_build="build-elsewhere")
    assert (unknown.status_code, unknown.json()["model_called"]) == (409, False)
    assert generator.calls == []


# Ruling R68 (review I1): a record the facade cannot sign after the paid
# generator call returns the generator's answer unsigned, with the reason,
# never a 500: it cannot be judged.
def test_an_answer_the_facade_cannot_sign_is_returned_unsigned_with_its_reason(client, generator_only, monkeypatch):
    from tere4ai.http_facade.signed import RecordError

    generator_only({ACCEPTED_NORM_ID: json.dumps({"items": ITEMS})})

    def unsignable(**kwargs):
        raise RecordError("the record's core holds a character UTF-8 cannot write (a lone surrogate)")

    monkeypatch.setattr(facade, "build_record", unsignable)
    response = _backlog(client)
    assert response.status_code == 200 and response.headers[facade.PAID_HEADER] == "true"
    answer = response.json()["answer"]
    assert "signed_record" not in answer and "signature" not in answer
    assert answer["unsigned_reason"].startswith("the facade could not sign this answer: ")
    assert response.json()["judge_verdict"] == "not_checked"


# B138 fix wave W4 (final review F4): a norm the judge did not accept is
# refused before any model call, with model_called false and without the
# paid header; the inline path answers as before.
def test_a_norm_not_accepted_on_demand_is_refused_before_any_model_call_and_not_billed(client, generator_only, monkeypatch):
    generator = generator_only({})
    norms = client.app.state.norms
    norm = next(n for n in norms["norms"] if n.get("judge_verdict") == "accepted")
    rejected = {**norm, "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n99", "judge_verdict": "rejected"}
    monkeypatch.setitem(norms, "norms", [*norms["norms"], rejected])
    response = _backlog(client, norm_ids=[rejected["norm_id"]])
    assert (response.status_code, response.json()["model_called"]) == (422, False)
    assert facade.PAID_HEADER not in response.headers
    assert "judge-accepted" in response.json()["error"] and rejected["norm_id"] in response.json()["error"]
    assert generator.calls == []


# B138 fix wave W8 (final review F8): the on-demand catch covers only the
# steps before the generator call; a ValueError raised once the generator is
# reached is a paid failure (502, model_called true), never "nothing billed".
def test_a_value_error_after_the_generator_is_reached_is_a_paid_failure(client, generator_only, monkeypatch):
    generator_only({})

    def late(*args, **kwargs):
        raise ValueError("a check after the generator's request")

    monkeypatch.setattr(facade.backlog_tool, "generate_control_backlog_on_demand", late)
    response = _backlog(client)
    assert (response.status_code, response.json()["model_called"]) == (502, True)


# B138 fix wave W7 (final review F7): a generated string holding U+0000 is
# signed with U+FFFD in its place, said in the answer's notes, so the
# dashboard can store the paid answer in jsonb.
def test_a_generated_nul_is_replaced_before_signing_and_said_in_the_notes(client, generator_only):
    items = [{**ITEMS[0], "title": "Keep\u0000 a log", "suggested_evidence": ["a\u0000plan"]}]
    generator_only({ACCEPTED_NORM_ID: json.dumps({"items": items})})
    response = _backlog(client)
    assert response.status_code == 200
    text = response.text
    assert "\\u0000" not in text and "\u0000" not in text
    answer = response.json()["answer"]
    assert answer["items"][0]["title"] == "Keep� a log" and answer["items"][0]["suggested_evidence"] == ["a�plan"]
    assert answer["signed_record"]["core"] == {"items": answer["items"]}
    assert verify(answer["signed_record"], answer["signature"], KEY)
    assert any("U+0000" in note and "U+FFFD" in note and "2" in note for note in answer["notes"])

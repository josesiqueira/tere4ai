"""DEC-24 (spec G D-G74 (3), (4), rulings S52, S53, S69, S73, S84): the judge
route /api/backlog/judge judges a signed generator-only backlog and nothing
else (B138 builds phase 5; /api/evidence/judge is B140's). Every check comes
before any model call; every field sent apart from the record is compared
with it. FakeClient only: no model API is called."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.http_facade.signed import sign
from tere4ai.judge.config import ModelConfigError

_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
pytestmark = pytest.mark.skipif(
    not all((_DUMP_DIR / name).is_file() for name in ("layer1.json", "norms_core.json", "alignments_core.json")),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)

KEY = bytes(range(32))
NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
NORM_ID_2 = "norm:eu-ai-act:article-9:paragraph-2:n2"
CONTEXT = "Opens a door."
CALLER = {"project": "p-1", "repository_run": "r-1", "document": None}
SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8, "evidence_strength": 0.75, "judge_confidence": 0.9}
ACCEPT = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norm.",
                     "type_views": [{"item": 1, "requirement_type_agrees": True, "requirement_type": "process"}]})


@pytest.fixture()
def client():
    with TestClient(facade.create_app()) as test_client:
        yield test_client


@pytest.fixture()
def models(monkeypatch, tmp_path):
    """A FakeClient generator and a FakeClient demo judge (gpt-judge)."""
    monkeypatch.setattr("tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
    monkeypatch.setattr(facade, "load_signing_key", lambda env=None: KEY)
    monkeypatch.setattr(facade, "load_generator_config", lambda env=None: None)
    monkeypatch.setattr(facade, "load_demo_judge_config", lambda env=None: SimpleNamespace(model="gpt-judge"))
    judge = FakeClient({"Generated runtime answer": ACCEPT}, model="gpt-judge")
    monkeypatch.setattr(facade, "OpenAIDemoJudge", lambda cfg: judge)
    items = [{"title": "Establish the system", "description": "Do it.", "norm_ids": [NORM_ID], "suggested_evidence": ["a plan"],
              "priority": "must", "requirement_type": "process"}]
    generator = FakeClient({"UNTRUSTED PROJECT CONTEXT": json.dumps({"items": items})}, model="gpt-gen")
    monkeypatch.setattr(facade, "OpenAIGenerator", lambda cfg: generator)
    return SimpleNamespace(judge=judge, generator=generator)


def _answer(client) -> dict:
    build = client.get("/api/health").json()["norms_build"]
    return client.post("/api/backlog", json={"norm_ids": [NORM_ID], "system_context": CONTEXT, "judge": "on_demand",
                                             "expected_norms_build": build, "caller": CALLER}).json()["answer"]


def _body(answer, **over):
    return {"norm_ids": [NORM_ID], "system_context": CONTEXT, "signed_record": answer["signed_record"], "signature": answer["signature"], **over}


def _judge(client, answer, **over):
    return client.post("/api/backlog/judge", json=_body(answer, **over))


def test_a_signed_backlog_is_judged_and_the_route_returns_the_judge_part_only(client, models):
    answer = _answer(client)
    reordered = json.loads(json.dumps(answer["signed_record"], sort_keys=True))  # a jsonb copy's order
    response = _judge(client, answer, signed_record=reordered)
    assert response.status_code == 200 and response.headers[facade.PAID_HEADER] == "true"
    part = response.json()
    assert (part["judge_verdict"], part["status"], part["judge_setting"], part["model_called"]) == ("accepted", "applicable_missing_evidence", "demo", True)
    assert part["generation_id"] == answer["signed_record"]["generation_id"] and part["judge_model"] == "gpt-judge"
    assert part["judge_type_views"] == [{"judge_type_agrees": True, "judge_requirement_type": "process"}]
    assert "items" not in part
    assert len(models.judge.calls) == 1


@pytest.mark.parametrize("over, field", [
    ({"system_context": "Opens another door."}, "system_context"),
    ({"norm_ids": [NORM_ID, NORM_ID_2]}, "norm_ids"),
])
def test_a_field_that_differs_from_the_record_is_refused_naming_it_before_any_model_call(client, models, over, field):
    response = _judge(client, _answer(client), **over)
    assert response.status_code == 422
    assert (response.json()["field"], response.json()["model_called"]) == (field, False)
    assert models.judge.calls == []


def test_a_forged_or_edited_record_does_not_verify(client, models):
    answer = _answer(client)
    edited = copy.deepcopy(answer["signed_record"])
    edited["core"]["items"][0]["title"] = "edited"
    for record, signature in ((answer["signed_record"], "0" * 64), (edited, answer["signature"]), (edited, sign(edited, bytes(32)))):
        response = _judge(client, answer, signed_record=record, signature=signature)
        assert (response.status_code, response.json()["field"], response.json()["model_called"]) == (422, "signature", False)
    assert models.judge.calls == []


def test_a_record_signed_on_another_build_is_refused_and_a_record_of_another_route_too(client, models):
    answer = _answer(client)
    moved = {**answer["signed_record"], "norms_build": "build-elsewhere"}
    response = _judge(client, answer, signed_record=moved, signature=sign(moved, KEY))
    assert (response.status_code, response.json()["field"]) == (409, "norms_build")
    rerouted = {**answer["signed_record"], "route": "/api/evidence", "core": {
        "tool": "evaluate_project_evidence", "norm_id": NORM_ID, "artifact_type": "repository file excerpt", "artifact_id": None,
        "assessment": "satisfied", "quotes": [], "gaps": [], "rationale": "Documented."}}
    response = _judge(client, answer, signed_record=rerouted, signature=sign(rerouted, KEY))
    assert (response.status_code, response.json()["field"]) == (422, "route")
    assert models.judge.calls == []


def test_the_demo_judge_is_never_the_model_that_generated_the_answer(client, models, monkeypatch):
    answer = _answer(client)
    monkeypatch.setattr(facade, "load_demo_judge_config", lambda env=None: SimpleNamespace(model="GPT-GEN"))
    response = _judge(client, answer)
    assert (response.status_code, response.json()["field"], response.json()["model_called"]) == (422, "generator_model", False)


def test_a_demo_judge_not_configured_is_refused_before_any_model_call(client, models, monkeypatch):
    answer = _answer(client)

    def missing(env=None):
        raise ModelConfigError("missing model configuration for the demo judge: TERE4AI_DEMO_JUDGE_MODEL")

    monkeypatch.setattr(facade, "load_demo_judge_config", missing)
    response = _judge(client, answer)
    assert (response.status_code, response.json()["model_called"]) == (503, False)


# Review M5 (phase 5 plan): an unloaded graph answers 503 with model_called
# false at the judge route, before any check or model call.
def test_an_unloaded_graph_is_refused_before_any_model_call(client, models):
    answer = _answer(client)
    client.app.state.load_error = "graph dumps unavailable: mock"
    response = _judge(client, answer)
    assert (response.status_code, response.json()["model_called"]) == (503, False)
    assert models.judge.calls == []


def test_an_unknown_norm_is_refused_before_any_model_call(client, models):
    answer = _answer(client)
    unknown = "norm:eu-ai-act:article-999:n1"
    moved = {**answer["signed_record"], "norm_ids": [unknown]}
    response = _judge(client, answer, norm_ids=[unknown], signed_record=moved, signature=sign(moved, KEY))
    assert (response.status_code, response.json()["model_called"]) == (404, False)
    assert models.judge.calls == []


# Ruling R68 (review I1): a record of the wrong kinds, or holding a character
# UTF-8 cannot write, does not verify: 422 before any model call, never a 500.
@pytest.mark.parametrize("change", [
    lambda r: {**r, "norm_ids": [1, NORM_ID]},
    lambda r: {**r, "route": ["/api/backlog"]},
    lambda r: {**r, "caller": {**r["caller"], "project": 5}},
    lambda r: {**r, "generator_prompt": {"name": None, "version": "v1"}},
])
def test_a_record_of_the_wrong_kinds_does_not_verify_before_any_model_call(client, models, change):
    answer = _answer(client)
    body = _body(answer, signed_record=change(answer["signed_record"]))
    response = client.post("/api/backlog/judge", content=json.dumps(body), headers={"content-type": "application/json"})
    assert (response.status_code, response.json()["field"], response.json()["model_called"]) == (422, "signature", False)
    assert models.judge.calls == []


def test_a_lone_surrogate_in_a_record_is_refused_by_the_request_check_before_any_model_call(client, models):
    answer = _answer(client)
    items = [{**answer["signed_record"]["core"]["items"][0], "description": "\ud800"}]
    body = _body(answer, signed_record={**answer["signed_record"], "core": {"items": items}})
    # Sent as JSON text with escapes, as any client may: a lone surrogate
    # arrives as \ud800 and is decoded by the server.
    response = client.post("/api/backlog/judge", content=json.dumps(body), headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert models.judge.calls == []


# Ruling R61 and review I9: another graph answers 409 naming graph_version;
# a judge prompt this route does not run 422 naming judge_prompt.
def test_a_record_signed_on_another_graph_is_refused_with_409_and_another_judge_prompt_with_422(client, models):
    answer = _answer(client)
    moved = {**answer["signed_record"], "graph_version": "build-elsewhere"}
    response = _judge(client, answer, signed_record=moved, signature=sign(moved, KEY))
    assert (response.status_code, response.json()["field"], response.json()["model_called"]) == (409, "graph_version", False)
    prompt = {**answer["signed_record"], "judge_prompt": {"name": "another_judge", "version": "v1"}}
    response = _judge(client, answer, signed_record=prompt, signature=sign(prompt, KEY))
    assert (response.status_code, response.json()["field"], response.json()["model_called"]) == (422, "judge_prompt", False)
    assert models.judge.calls == []


# Review I9: a judge that fails before any request answers 503 with
# model_called false (not billed); one that fails after its request was sent
# answers judge_error with model_called true (billed).
class _Failing(FakeClient):
    """A judge whose request fails, after it was sent or before."""

    def __init__(self, sends: bool):
        super().__init__({}, model="gpt-judge")
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "requests_sent": 0}
        self._sends = sends

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._sends:
            self.usage["requests_sent"] += 1
        raise RuntimeError("overloaded")


def test_a_judge_failing_before_its_request_is_not_billed_and_after_it_is(client, models, monkeypatch):
    answer = _answer(client)
    monkeypatch.setattr(facade, "OpenAIDemoJudge", lambda cfg: _Failing(sends=False))
    response = _judge(client, answer)
    assert (response.status_code, response.json()["model_called"]) == (503, False)
    monkeypatch.setattr(facade, "OpenAIDemoJudge", lambda cfg: _Failing(sends=True))
    response = _judge(client, answer)
    part = response.json()
    assert response.status_code == 200
    assert (part["judge_verdict"], part["status"], part["model_called"]) == ("judge_error", "requires_human_review", True)
    assert "overloaded" in part["error"]

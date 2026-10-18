"""B165: the runtime judge and the generators receive each cited norm's
verbatim source_text on every path, as the MCP tools do and as
runtime_grounding v2's check 0 requires.

Paths: the facade's POST /api/evidence (inline), POST /api/backlog (inline,
and on demand where the generator alone runs), POST /api/backlog/judge, and
E6's GraphStrategy (conditions 5 and 6) with a runtime judge. The facade
tests read the node text from the served dump, E6's from the mock dump
written here. FakeClient only: no model API, no network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.eval.strategies import GraphStrategy
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.source_text import attach_source_text, with_source_text

_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
needs_dumps = pytest.mark.skipif(
    not all((_DUMP_DIR / name).is_file() for name in ("layer1.json", "norms_core.json", "alignments_core.json")),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)

KEY = bytes(range(32))
NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
NORM_ID_2 = "norm:eu-ai-act:article-9:paragraph-2:n2"
CALLER = {"project": "22222222-2222-4222-8222-222222222222", "repository_run": "11111111-1111-4111-8111-111111111111", "document": None}
CONTEXT = "Opens the office door for staff and keeps a log of each event."
SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8, "evidence_strength": 0.75, "judge_confidence": 0.9}
ACCEPT = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norms.",
                     "type_views": [{"item": 1, "requirement_type_agrees": True, "requirement_type": "process"}]})
ITEMS = json.dumps({"items": [{"title": "Establish the system", "description": "Do it.", "norm_ids": [NORM_ID],
                               "suggested_evidence": ["a plan"], "priority": "must", "requirement_type": "process"}]})
QUOTE = "We maintain a documented risk management system"
EVIDENCE = json.dumps({"assessment": "satisfied", "quotes": [QUOTE], "gaps": [], "rationale": "Documented."})


def _escaped(text: str) -> str:
    """How json.dumps(ensure_ascii=False) writes the text inside a string."""
    return json.dumps(text, ensure_ascii=False)[1:-1]


def _source_text(app, norm_id: str) -> str:
    norm = next(n for n in app.state.served.norms["norms"] if n["norm_id"] == norm_id)
    node = next(n for n in app.state.served.dump["nodes"] if n["id"] == norm["source_node_id"])
    assert node["text"]
    return node["text"]


@pytest.fixture()
def client():
    with TestClient(facade.create_app()) as test_client:
        yield test_client


@pytest.fixture()
def clients(monkeypatch, tmp_path):
    """FakeClient generator and judge for every facade path, kept for inspection."""
    monkeypatch.setattr("tere4ai.mcp_server.evidence.DEFAULT_LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr("tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(facade, "load_signing_key", lambda env=None: KEY)
    monkeypatch.setattr(facade, "load_generator_config", lambda env=None: None)
    monkeypatch.setattr(facade, "load_demo_judge_config", lambda env=None: SimpleNamespace(model="gpt-judge"))
    generator = FakeClient({"UNTRUSTED PROJECT CONTEXT": ITEMS, NORM_ID: EVIDENCE}, model="gpt-gen")
    judge = FakeClient({"": ACCEPT}, model="gpt-judge")
    monkeypatch.setattr(facade, "_build_paid_clients", lambda: (generator, judge))
    monkeypatch.setattr(facade, "OpenAIGenerator", lambda cfg: generator)
    monkeypatch.setattr(facade, "OpenAIDemoJudge", lambda cfg: judge)
    return SimpleNamespace(generator=generator, judge=judge)


def test_with_source_text_copies_and_attach_source_text_fills_in_place():
    dump = {"nodes": [{"id": "n1", "text": "Exact wording."}, {"id": "n2", "text": ""}]}
    norms = [{"norm_id": "a", "source_node_id": "n1"}, {"norm_id": "b", "source_node_id": "n2"},
             {"norm_id": "c", "source_node_id": "n1", "source_text": "kept"}]
    copies = with_source_text(norms, dump)
    assert [c.get("source_text") for c in copies] == ["Exact wording.", None, "kept"]
    assert all("source_text" not in n for n in norms[:2]), "the input list's dicts are not mutated"
    attach_source_text(norms, dump)
    assert [n.get("source_text") for n in norms] == ["Exact wording.", None, "kept"]


@needs_dumps
def test_facade_evidence_inline_judge_and_generator_hold_the_source_text(client, clients):
    text = _source_text(client.app, NORM_ID)
    response = client.post("/api/evidence", json={"norm_id": NORM_ID, "artifact_type": "plan",
                                                  "content": QUOTE + " reviewed quarterly."})
    assert response.status_code == 200
    assert _escaped(text) in clients.judge.calls[-1][1]
    assert text in clients.generator.calls[-1][1]


@needs_dumps
def test_facade_backlog_inline_judge_and_generator_hold_the_source_text(client, clients):
    texts = [_source_text(client.app, n) for n in (NORM_ID, NORM_ID_2)]
    response = client.post("/api/backlog", json={"norm_ids": [NORM_ID, NORM_ID_2], "system_context": CONTEXT})
    assert response.status_code == 200
    for text in texts:
        assert _escaped(text) in clients.judge.calls[-1][1]
        assert _escaped(text) in clients.generator.calls[-1][1]


def _on_demand(client):
    build = client.get("/api/health").json()["norms_build"]
    body = {"norm_ids": [NORM_ID], "system_context": CONTEXT, "judge": "on_demand",
            "expected_norms_build": build, "caller": CALLER}
    return client.post("/api/backlog", json=body)


@needs_dumps
def test_facade_backlog_on_demand_generator_holds_the_source_text(client, clients, monkeypatch):
    monkeypatch.setattr(facade, "_build_paid_clients", lambda: (_ for _ in ()).throw(AssertionError("inline clients built")))
    text = _source_text(client.app, NORM_ID)
    assert _on_demand(client).status_code == 200
    assert _escaped(text) in clients.generator.calls[-1][1]
    assert clients.judge.calls == []


@needs_dumps
def test_facade_backlog_judge_route_judge_holds_the_source_text(client, clients):
    text = _source_text(client.app, NORM_ID)
    answer = _on_demand(client).json()["answer"]
    body = {"norm_ids": [NORM_ID], "system_context": CONTEXT, "signed_record": answer["signed_record"],
            "signature": answer["signature"]}
    response = client.post("/api/backlog/judge", json=body)
    assert response.status_code == 200 and response.json()["judge_verdict"] == "accepted"
    assert _escaped(text) in clients.judge.calls[-1][1]


@needs_dumps
def test_facade_does_not_mutate_its_loaded_norms_payload(client, clients):
    before = json.dumps(client.app.state.served.norms, sort_keys=True)
    assert client.post("/api/backlog", json={"norm_ids": [NORM_ID], "system_context": CONTEXT}).status_code == 200
    assert client.post("/api/evidence", json={"norm_id": NORM_ID, "artifact_type": "plan",
                                              "content": QUOTE + " reviewed quarterly."}).status_code == 200
    assert _on_demand(client).status_code == 200
    assert json.dumps(client.app.state.served.norms, sort_keys=True) == before
    served = client.post("/api/requirements", json={"classification": client.post(
        "/api/classify", json={"features": {"description": "x", "domain": "healthcare", "autonomy": "advisory",
                                            "flags": {"essential_services_access": True}}}).json()})
    assert "source_text" not in json.dumps(served.json()["answer"]["requirements_by_article"])


# E6 (conditions 5 and 6), mock data written here
_TEXT = 'Providers shall keep "a risk management system" in place.'
_DUMP = {"nodes": [{"id": "eu-ai-act:article-9:paragraph-1", "text": _TEXT},
                   {"id": "eu-ai-act:article-9:paragraph-2", "text": "Other wording."}]}
_NORMS = {"norms": [
    {"norm_id": "norm:a", "source_node_id": "eu-ai-act:article-9:paragraph-1", "deontic_type": "obligation",
     "modal": "shall", "actor_explicit": "provider", "action": "keep a risk management system", "object": "system",
     "conditions": [], "exceptions": [], "judge_verdict": "accepted"},
    {"norm_id": "norm:b", "source_node_id": "eu-ai-act:article-9:paragraph-2", "deontic_type": "obligation",
     "modal": "shall", "actor_explicit": "deployer", "action": "unrelated duty", "object": "thing",
     "conditions": [], "exceptions": [], "judge_verdict": "accepted"}]}
_ANSWER = json.dumps({"answer_text": "A risk management system is required.", "citations": ["eu-ai-act:article-9:paragraph-1"]})


def _graph_strategy(judge):
    generator = FakeClient({"": _ANSWER}, model="gpt-gen")
    return generator, GraphStrategy("graph_build_judge", generator, _DUMP, _NORMS, judged_only=True,
                                    runtime_judge=judge, top_k_norms=1, judge_prompt_version="v2")


_ITEM = {"id": "q1", "kind": "qa", "question": "Which risk management system must a provider keep?"}


def test_e6_runtime_judge_receives_each_cited_norms_source_text():
    judge = FakeClient({"": ACCEPT}, model="claude-judge")
    _generator, strategy = _graph_strategy(judge)
    result = strategy(_ITEM)
    assert result["offered_norm_ids"] == ["norm:a"]
    assert _escaped(_TEXT) in judge.calls[0][1]


def test_e6_generator_input_is_unchanged_by_the_source_text():
    judge = FakeClient({"": ACCEPT}, model="claude-judge")
    generator, strategy = _graph_strategy(judge)
    strategy(_ITEM)
    user = generator.calls[0][1]
    assert "source_text" not in user and _TEXT not in user and _escaped(_TEXT) not in user
    assert json.dumps(strategy._norm_digest(_NORMS["norms"][0]), sort_keys=True) in user
    assert "source_text" not in _NORMS["norms"][0], "the strategy's norms are not mutated"

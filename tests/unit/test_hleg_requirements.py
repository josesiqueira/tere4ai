"""DEC-31: the HLEG requirements of a tailored requirement's cited norms, a
deterministic join over accepted alignments added after the judge. Mock
clients and mock data only: no model API is called."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.align_hleg.hleg_nodes import CANONICAL
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.mcp_server import hleg_requirements as hr
from tere4ai.mcp_server import replay, server
from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT

N1 = "norm:eu-ai-act:article-9:paragraph-1:n1"
N2 = "norm:eu-ai-act:article-9:paragraph-2:n2"
TRANSPARENCY = "hleg:transparency"
ROBUSTNESS = "hleg:technical-robustness-and-safety"
ACCOUNTABILITY = "hleg:accountability"
AGENCY = "hleg:human-agency-and-oversight"


def assertion(norm, target, relation="partially_operationalizes", status="accepted", n=1, score=0.8):
    return {
        "id": f"align:{norm}:{target}:{n}",
        "source_norm_id": norm,
        "target_id": target,
        "relation_type": relation,
        "review_status": status,
        "final_score": score,
    }


PAYLOAD = {
    "assertions": [
        assertion(N2, ACCOUNTABILITY, "supports", score=0.7),
        assertion(N1, ACCOUNTABILITY),
        assertion(N1, ROBUSTNESS),
        assertion(N2, ROBUSTNESS, "supports"),
        assertion(N1, TRANSPARENCY, "related_to"),
        assertion(N1, AGENCY, "conflicts_with"),
        assertion(N1, AGENCY, "needs_review"),
        assertion(N1, TRANSPARENCY, "partially_operationalizes", status="needs_review", n=2),
        assertion("norm:other", TRANSPARENCY),
    ]
}


def envelope(tailored):
    return {
        "answer": {"tailored_requirements": tailored, "dropped_tailored_requirements": 0},
        "status": "applicable_missing_evidence",
        "judge_verdict": "accepted",
        "confidence": 0.8,
        "legal_status_notes": ["n"],
    }


def tailored(*norm_ids):
    return {"title": "T", "description": "D", "norm_ids": list(norm_ids), "priority": "must"}


def test_only_the_two_relations_and_accepted_assertions_are_joined():
    names = {e["hleg_id"] for e in hr.hleg_requirements_of([N1, N2], PAYLOAD)}
    assert names == {ROBUSTNESS, ACCOUNTABILITY}
    for entry in hr.hleg_requirements_of([N1, N2], PAYLOAD):
        assert entry["relation"] == "supports"
        for a in entry["alignments"]:
            assert "relation_type" not in a


def test_order_is_canonical_then_norm_ids_then_id():
    entries = hr.hleg_requirements_of([N2, N1], PAYLOAD)
    assert [e["hleg_id"] for e in entries] == [ROBUSTNESS, ACCOUNTABILITY]
    assert [h for h, _ in CANONICAL].index(ROBUSTNESS) < [h for h, _ in CANONICAL].index(ACCOUNTABILITY)
    assert entries[0]["name"] == "Technical robustness and safety"
    assert [a["norm_id"] for a in entries[0]["alignments"]] == [N2, N1]
    assert set(entries[0]["alignments"][0]) == {"alignment_id", "norm_id", "final_score"}
    assert [a["norm_id"] for a in hr.hleg_requirements_of([N1, N2], PAYLOAD)[0]["alignments"]] == [N1, N2]


def test_a_norm_without_alignment_adds_nothing():
    assert hr.hleg_requirements_of(["norm:none"], PAYLOAD) == []
    assert hr.hleg_requirements_of([], PAYLOAD) == []


def test_the_input_is_not_mutated_and_keys_are_added():
    original = envelope([tailored(N1), tailored("norm:none")])
    before = copy.deepcopy(original)
    result = hr.with_hleg_requirements(original, PAYLOAD)
    assert original == before
    first, second = result["answer"]["tailored_requirements"]
    assert [e["hleg_id"] for e in first["hleg_requirements"]] == [ROBUSTNESS, ACCOUNTABILITY]
    assert second["hleg_requirements"] == []
    assert result["answer"]["hleg_caveat"] == HLEG_MAPPING_CAVEAT
    for key in ("status", "judge_verdict", "confidence", "legal_status_notes"):
        assert result[key] == original[key]


def test_a_none_payload_keeps_the_answer_and_says_why():
    original = envelope([tailored(N1)])
    result = hr.with_hleg_requirements(original, None)
    assert "hleg_requirements" not in result["answer"]["tailored_requirements"][0]
    assert result["answer"]["hleg_requirements_unavailable"] == hr.UNAVAILABLE_REASON
    assert "hleg_caveat" not in result["answer"]
    assert result["answer"]["tailored_requirements"] == original["answer"]["tailored_requirements"]


@pytest.mark.parametrize(
    "degraded",
    [
        {"answer": None, "status": "requires_human_review"},
        {"answer": {"refused_norm_ids": ["x"]}, "status": "not_applicable"},
        {"answer": {"unknown_norm_ids": ["x"]}, "status": "not_applicable"},
    ],
)
def test_an_envelope_without_tailored_requirements_is_unchanged(degraded):
    before = copy.deepcopy(degraded)
    assert hr.with_hleg_requirements(degraded, PAYLOAD) == before
    assert hr.with_hleg_requirements(degraded, None) == before


# The MCP tool over mock data, with fake clients.

NORM = {
    "norm_id": N1, "layer": 2, "type": "NormativeStatement", "source_node_id": "eu-ai-act:article-9:paragraph-1",
    "source_span_id": "span:009.001", "deontic_type": "obligation", "modal": "shall", "actor_explicit": "provider",
    "actor_inferred": None, "actor_inference_source_node_id": None, "action": "document", "object": "the process",
    "target_system_category": "high_risk", "conditions": [], "exceptions": [], "extraction_method": "llm_extract_v1",
    "extractor_model": "fake", "confidence": 0.9, "judge_verdict": "accepted", "review_status": "accepted",
}
GEN_REPLY = json.dumps({"tailored_requirements": [{
    "title": "Risk process", "description": "Do the work.", "norm_ids": [N1], "suggested_evidence": ["a plan"],
    "priority": "must", "requirement_type": "process"}]})
SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8,
          "evidence_strength": 0.75, "judge_confidence": 0.9}
JUDGE_REPLY = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded."})


class Recording(FakeClient):
    def __init__(self, scripted, model):
        super().__init__(scripted, model=model)
        self.seen: list[str] = []

    def complete(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.seen.append(json.dumps([args, kwargs], default=str))
        return super().complete(*args, **kwargs)


def _hleg_words():
    return [name for _, name in CANONICAL] + [hid for hid, _ in CANONICAL] + ["hleg_requirements", HLEG_MAPPING_CAVEAT]


@pytest.fixture()
def mcp_world(monkeypatch, tmp_path):
    monkeypatch.setattr("tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
    monkeypatch.setattr(server, "_REPLAY", replay.ReplayStore(window_seconds=600))
    dump = {"build": {"build_id": "b"}, "nodes": [], "edges": []}
    state = {"alignments": PAYLOAD}
    clients = {}

    def active():
        return LoadedBuild(dump, {"norms": [dict(NORM)]}, state["alignments"], "b", "legacy", None)

    def paid():
        clients["generator"] = Recording({N1: GEN_REPLY}, "fake-generator")
        clients["judge"] = Recording({N1: JUDGE_REPLY}, "fake-judge")
        return server.PaidClients(clients["generator"], clients["judge"], "p")

    monkeypatch.setattr(server, "_active", active)
    monkeypatch.setattr(server, "_paid_clients_or_envelope", paid)
    return state, clients


def test_the_mcp_answer_carries_the_hleg_requirements_and_the_judge_never_saw_them(mcp_world):
    _, clients = mcp_world
    result = server.generate_tailored_requirements([N1], "A triage system.")
    tailored_requirement = result["answer"]["tailored_requirements"][0]
    assert [e["hleg_id"] for e in tailored_requirement["hleg_requirements"]] == [ROBUSTNESS, ACCOUNTABILITY]
    assert result["answer"]["hleg_caveat"] == HLEG_MAPPING_CAVEAT
    for client in clients.values():
        assert client.seen, "the client was called"
        for sent in client.seen:
            for word in _hleg_words():
                assert word not in sent
    assert result["judge_verdict"] == "accepted"


def test_the_status_verdict_and_confidence_equal_the_answer_without_alignments(mcp_world):
    state, _ = mcp_world
    with_hleg = server.generate_tailored_requirements([N1], "A triage system.")
    state["alignments"] = None
    server._REPLAY = replay.ReplayStore(window_seconds=600)
    without = server.generate_tailored_requirements([N1], "A triage system.")
    assert without["answer"]["hleg_requirements_unavailable"]
    for key in ("status", "judge_verdict", "confidence", "missing_facts", "legal_status_notes"):
        assert with_hleg[key] == without[key]


def test_a_replayed_mcp_answer_carries_it_too(mcp_world):
    first = server.generate_tailored_requirements([N1], "A triage system.")
    second = server.generate_tailored_requirements([N1], "A triage system.")
    assert second["answer"]["tailored_requirements"][0]["hleg_requirements"] == \
        first["answer"]["tailored_requirements"][0]["hleg_requirements"]
    assert second["answer"]["hleg_caveat"] == HLEG_MAPPING_CAVEAT


# The facade over the served build (skipped when the dumps are absent).

_DUMP_DIR = Path(os.environ.get(facade.DUMP_DIR_ENV) or facade.DEFAULT_DUMP_DIR)
needs_dumps = pytest.mark.skipif(
    not all((_DUMP_DIR / name).is_file() for name in ("layer1.json", "norms_core.json", "alignments_core.json")),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)
FACADE_GEN = json.dumps({"tailored_requirements": [{
    "title": "Establish", "description": "Do it.", "norm_ids": [N1], "suggested_evidence": ["a plan"],
    "priority": "must", "requirement_type": "process"}]})


@pytest.fixture()
def facade_client(monkeypatch, tmp_path):
    monkeypatch.setattr("tere4ai.mcp_server.backlog.DEFAULT_LOG_PATH", tmp_path / "runtime_log.jsonl")
    monkeypatch.setattr(facade, "load_model_config", lambda env=None: None)
    monkeypatch.setattr(facade, "OpenAIGenerator", lambda cfg: FakeClient({N1: FACADE_GEN}, model="gpt-gen"))
    monkeypatch.setattr(facade, "AnthropicJudge", lambda cfg: FakeClient({N1: JUDGE_REPLY}, model="fake-judge"))
    with TestClient(facade.create_app()) as client:
        yield client


@needs_dumps
def test_the_facade_inline_answer_carries_the_hleg_requirements(facade_client):
    response = facade_client.post("/api/tailored-requirements", json={"norm_ids": [N1], "system_context": "Hospital triage."})
    assert response.status_code == 200
    answer = response.json()["answer"]
    ids = [e["hleg_id"] for e in answer["tailored_requirements"][0]["hleg_requirements"]]
    assert ids == [ROBUSTNESS, ACCOUNTABILITY]
    assert answer["hleg_caveat"] == HLEG_MAPPING_CAVEAT


@needs_dumps
def test_the_on_demand_answer_does_not(facade_client, monkeypatch):
    monkeypatch.setattr(facade, "load_signing_key", lambda env=None: bytes(range(32)))
    monkeypatch.setattr(facade, "load_generator_config", lambda env=None: None)
    caller = {"project": "22222222-2222-4222-8222-222222222222",
              "repository_run": "11111111-1111-4111-8111-111111111111", "document": None}
    build = facade_client.get("/api/health").json()["norms_build"]
    response = facade_client.post("/api/tailored-requirements", json={
        "norm_ids": [N1], "system_context": "Hospital triage.", "judge": "on_demand",
        "caller": caller, "expected_norms_build": build})
    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "hleg_caveat" not in answer and "hleg_requirements_unavailable" not in answer
    assert all("hleg_requirements" not in t for t in answer["tailored_requirements"])


# POST /api/hleg-requirements: free, deterministic, any groups of norm ids.

import dataclasses  # noqa: E402


@pytest.fixture()
def route_client(monkeypatch):
    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("the free route touched a model client")

    monkeypatch.setattr(facade, "OpenAIGenerator", boom)
    monkeypatch.setattr(facade, "AnthropicJudge", boom)
    with TestClient(facade.create_app()) as client:
        client.app.state.served = dataclasses.replace(client.app.state.served, alignments=PAYLOAD)
        yield client


@needs_dumps
def test_the_route_answers_one_group_per_group_in_order(route_client):
    response = route_client.post("/api/hleg-requirements", json={"norm_id_groups": [[N2], [N1, N2], ["norm:unknown"], []]})
    assert response.status_code == 200
    body = response.json()
    assert body["caveat"] == HLEG_MAPPING_CAVEAT
    assert body["graph_version"] and body["norms_build"]
    groups = body["groups"]
    assert len(groups) == 4
    assert groups[0] == hr.hleg_requirements_of([N2], PAYLOAD)
    assert groups[1] == hr.hleg_requirements_of([N1, N2], PAYLOAD)
    assert groups[2] == [] and groups[3] == []
    assert response.headers.get("X-TERE4AI-Paid-Call") is None


@needs_dumps
def test_the_route_is_deterministic(route_client):
    body = {"norm_id_groups": [[N1, N2]]}
    assert route_client.post("/api/hleg-requirements", json=body).json() == \
        route_client.post("/api/hleg-requirements", json=body).json()


@needs_dumps
def test_the_route_refuses_beyond_the_limits_with_422(route_client):
    assert route_client.post("/api/hleg-requirements", json={"norm_id_groups": [[N1]] * 501}).status_code == 422
    assert route_client.post("/api/hleg-requirements", json={"norm_id_groups": [["n"] * 201]}).status_code == 422
    assert route_client.post("/api/hleg-requirements", json={"norm_id_groups": [[N1]] * 500}).status_code == 200
    assert route_client.post("/api/hleg-requirements", json={"norm_id_groups": [["n"] * 200]}).status_code == 200
    assert route_client.post("/api/hleg-requirements", json={"norm_id_groups": []}).status_code == 422


@needs_dumps
def test_the_route_answers_the_clean_503_without_alignments(route_client):
    route_client.app.state.served = dataclasses.replace(route_client.app.state.served, alignments=None)
    response = route_client.post("/api/hleg-requirements", json={"norm_id_groups": [[N1]]})
    assert response.status_code == 503
    assert "alignments payload unavailable" in response.json()["error"]


@needs_dumps
def test_the_route_is_listed_as_free_in_discovery(route_client):
    entry = route_client.get("/.well-known/tere4ai.json").json()["endpoints"]["hleg_requirements"]
    assert entry == {"method": "POST", "path": "/api/hleg-requirements", "paid": False}
    assert "/api/hleg-requirements" in route_client.get("/llms.txt").text


def test_the_tool_docstring_names_the_hleg_fields():
    doc = server.generate_tailored_requirements.__doc__ or ""
    assert "hleg_requirements" in doc and "hleg_caveat" in doc

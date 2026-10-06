"""DEC-24 (spec G D-G74 (12)): the tool functions evaluate_project_evidence,
evaluate_evidence_batch (behind evaluate_project_evidence_batch) and
generate_control_backlog answer byte for byte as they did before the
backlog tool was split into a generator part and a judge part. The MCP
tools and the facade's inline mode call these functions; this test calls
the functions, not the routes, whose inline path the existing facade tests
hold (B138 phase 5 plan ruling P24). The answers were recorded from the code
before the split (tests/fixtures/inline_answers_golden.json); only the time
of the answer and the judge run's random id are left out of the comparison.
FakeClient only: no network, no key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.backlog import generate_control_backlog
from tere4ai.mcp_server.evidence import evaluate_evidence_batch, evaluate_project_evidence

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "inline_answers_golden.json"
SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8,
          "evidence_strength": 0.75, "judge_confidence": 0.9}
ACCEPT = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norm."})
REJECT = json.dumps({"verdict": "rejected", "scores": {**SCORES, "evidence_strength": 0.1}, "rationale": "Not supported."})


def _norm(article: int, index: int = 1, **over: Any) -> dict[str, Any]:
    node = f"eu-ai-act:article-{article}:paragraph-1"
    norm = {"norm_id": f"norm:{node}:n{index}", "source_node_id": node, "source_span_id": f"span:{article:03d}.001",
            "deontic_type": "obligation", "modal": "shall", "actor_explicit": "provider", "actor_inferred": None,
            "action": "keep", "object": "logs of each event", "target_system_category": "high_risk", "conditions": [],
            "exceptions": [], "judge_verdict": "accepted"}
    norm.update(over)
    return norm


NORM = _norm(12)
EVIDENCE = {"artifact_type": "repository file excerpt", "artifact_id": "run:1:1-3",
            "content": "==> src/audit/events.py, lines 1 to 3, commit 9b41e0c00000 <==\ndef record(event):\n    log.append(event)"}


def _gen(assessment: str, quotes: list[str]) -> str:
    return json.dumps({"assessment": assessment, "quotes": quotes, "gaps": ["no retention period"], "rationale": "Appended to a log."})


def _items(*items: dict[str, Any]) -> str:
    return json.dumps({"items": list(items)})


def _item(title: str, norm_ids: list[str], priority: Any = "must", requirement_type: Any = "functional") -> dict[str, Any]:
    return {"title": title, "description": f"Do {title}.", "norm_ids": norm_ids, "suggested_evidence": ["a log"],
            "priority": priority, "requirement_type": requirement_type}


def _random_ids(value: Any) -> Any:
    """Every judge run's random id, wherever the answer holds one."""
    if isinstance(value, dict):
        return {key: ("judgerun:runtime_grounding:<random>" if key == "judge_run_id" else _random_ids(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_random_ids(item) for item in value]
    return value


def _normalised(envelope: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(envelope))
    out.pop("generated_at", None)
    if isinstance(out.get("answer"), dict):
        out["answer"] = _random_ids(out["answer"])
    return out


def _evidence(tmp: Path, gen: str, judge: str, norm: dict[str, Any] = NORM) -> dict[str, Any]:
    return evaluate_project_evidence(norm, EVIDENCE, FakeClient({"Norm id": gen}, "fake-generator"),
                                     FakeClient({"Generated runtime answer": judge}, "fake-judge"),
                                     graph_version="build-test", log_path=tmp / "log.jsonl")


def _batch(tmp: Path) -> dict[str, Any]:
    norms = [_norm(12), _norm(12, 2), _norm(12, 3, judge_verdict="rejected")]
    return evaluate_evidence_batch(norms, EVIDENCE, FakeClient({"Norm id": _gen("partially_satisfied", ["log.append(event)"])}, "fake-generator"),
                                   FakeClient({"Generated runtime answer": ACCEPT}, "fake-judge"),
                                   graph_version="build-test", log_path=tmp / "log.jsonl")


def _backlog(tmp: Path, gen: str, judge: str, version: str = "v2") -> dict[str, Any]:
    norms = [_norm(12), _norm(12, 2, deontic_type="permission"), _norm(14, conditions=["where needed"])]
    return generate_control_backlog(norms, "Opens the office door for staff.", FakeClient({"UNTRUSTED PROJECT CONTEXT": gen}, "fake-generator"),
                                    FakeClient({"Generated runtime answer": judge}, "fake-judge"), prompt_version=version,
                                    graph_version="build-test", log_path=tmp / "log.jsonl")


def scenarios(tmp: Path) -> dict[str, dict[str, Any]]:
    ids = [_norm(12)["norm_id"], _norm(12, 2)["norm_id"], _norm(14)["norm_id"]]
    typed_views = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Fine.",
                              "type_views": [{"item": 1, "requirement_type_agrees": False, "requirement_type": "quality"}]})
    return {
        "evidence accepted": _evidence(tmp, _gen("partially_satisfied", ["log.append(event)"]), ACCEPT),
        "evidence rejected": _evidence(tmp, _gen("satisfied", ["log.append(event)"]), REJECT),
        "evidence invalid assessment": _evidence(tmp, _gen("compliant", ["log.append(event)"]), ACCEPT),
        "evidence quote dropped": _evidence(tmp, _gen("satisfied", ["never written"]), ACCEPT),
        "evidence unparsable": _evidence(tmp, "not json", ACCEPT),
        "evidence norm not accepted": _evidence(tmp, _gen("satisfied", []), ACCEPT, _norm(12, judge_verdict="rejected")),
        "evidence batch": _batch(tmp),
        "backlog accepted typed": _backlog(tmp, _items(_item("Keep a log", [ids[0]]), _item("Log access", [ids[0]], requirement_type="bogus"),
                                                       _item("Ask", [ids[1]], priority="maybe"), _item("Ghost", ["norm:nowhere"])), typed_views),
        "backlog rejected v1": _backlog(tmp, _items(_item("Keep a log", [ids[2]], priority="soon")), REJECT, "v1"),
        "backlog nothing survives": _backlog(tmp, _items(_item("Ghost", ["norm:nowhere"])), ACCEPT),
        "backlog unparsable": _backlog(tmp, "{\"no\": \"items\"}", ACCEPT),
    }


def test_the_inline_answers_are_those_recorded_before_the_split(tmp_path):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    current = {name: _normalised(envelope) for name, envelope in scenarios(tmp_path).items()}
    assert sorted(current) == sorted(golden)
    for name in golden:
        assert json.dumps(current[name], sort_keys=True) == json.dumps(golden[name], sort_keys=True), name


@pytest.mark.parametrize("name", ["evidence accepted", "backlog accepted typed"])
def test_the_inline_answers_keep_their_key_order(tmp_path, name):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert list(_normalised(scenarios(tmp_path)[name])["answer"]) == list(golden[name]["answer"])

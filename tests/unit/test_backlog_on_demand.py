"""DEC-24 (spec G D-G74 (2), (4)): the backlog tool's generator part alone,
for the facade's generator-only mode, and its judge part alone, for the
judge route. FakeClient only: no network, no key."""

from __future__ import annotations

import json

import pytest

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.backlog import (
    generate_control_backlog,
    generate_control_backlog_on_demand,
    judge_backlog_on_demand,
)
from tere4ai.mcp_server.evidence import NOT_CHECKED, NOT_CHECKED_NOTE


def _norm(article: int, **over):
    node = f"eu-ai-act:article-{article}:paragraph-1"
    norm = {"norm_id": f"norm:{node}:n1", "source_node_id": node, "source_span_id": f"span:{article:03d}.001",
            "deontic_type": "obligation", "modal": "shall", "action": "keep", "object": "logs", "conditions": [], "judge_verdict": "accepted"}
    norm.update(over)
    return norm


NORMS = [_norm(12), _norm(14)]
SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8, "evidence_strength": 0.75, "judge_confidence": 0.9}
ITEMS = json.dumps({"items": [
    {"title": "Keep a log", "description": "Record every event.", "norm_ids": [NORMS[0]["norm_id"]], "suggested_evidence": ["a log"], "priority": "must", "requirement_type": "functional"},
    {"title": "Oversee", "description": "Name an overseer.", "norm_ids": [NORMS[1]["norm_id"]], "suggested_evidence": [], "priority": "should", "requirement_type": "process"},
]})
JUDGE = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Within the cited norms.",
                    "type_views": [{"item": 2, "requirement_type_agrees": False, "requirement_type": "quality"}]})
CONTEXT = "Opens the office door for staff (fictitious)."


def _generator():
    return FakeClient({"UNTRUSTED PROJECT CONTEXT": ITEMS}, model="gpt-gen")


def test_the_generator_alone_answers_not_checked_with_the_items_as_produced(tmp_path):
    envelope = generate_control_backlog_on_demand(NORMS, CONTEXT, _generator(), graph_version="build-a", log_path=tmp_path / "l.jsonl")
    assert (envelope["status"], envelope["judge_verdict"]) == ("requires_human_review", NOT_CHECKED)
    answer = envelope["answer"]
    assert [item["title"] for item in answer["items"]] == ["Keep a log", "Oversee"]
    assert (answer["dropped_items"], answer["merged_items"], answer["generator_model"], answer["judge_prompt_version"]) == (0, 0, "gpt-gen", "v2")
    assert "judge_model" not in answer and "judge_rationale" not in answer and answer["usage"]["judge"] is None
    assert envelope["missing_facts"][-1] == NOT_CHECKED_NOTE


def test_the_judge_part_reads_what_the_inline_judge_reads_and_returns_each_item_type_view(tmp_path):
    inline_judge = FakeClient({"Generated runtime answer": JUDGE}, model="claude-judge")
    generate_control_backlog(NORMS, CONTEXT, _generator(), inline_judge, log_path=tmp_path / "i.jsonl")
    items = generate_control_backlog_on_demand(NORMS, CONTEXT, _generator(), log_path=tmp_path / "g.jsonl")["answer"]["items"]
    stored = json.loads(json.dumps(items, sort_keys=True))  # as a jsonb copy may come back
    demo_judge = FakeClient({"Generated runtime answer": JUDGE}, model="gpt-judge")
    part = judge_backlog_on_demand(NORMS, stored, CONTEXT, demo_judge, log_path=tmp_path / "j.jsonl")
    assert demo_judge.calls[0] == inline_judge.calls[0]
    assert (part["judge_verdict"], part["status"], part["judge_setting"]) == ("accepted", "applicable_missing_evidence", "demo")
    assert part["judge_type_views"] == [{"judge_type_agrees": None, "judge_requirement_type": None},
                                        {"judge_type_agrees": False, "judge_requirement_type": "quality"}]


def test_a_backlog_judge_that_does_not_accept_gives_requires_human_review(tmp_path):
    items = generate_control_backlog_on_demand(NORMS, CONTEXT, _generator(), log_path=tmp_path / "g.jsonl")["answer"]["items"]
    reject = json.dumps({"verdict": "rejected", "scores": SCORES, "rationale": "No."})
    part = judge_backlog_on_demand(NORMS, items, CONTEXT, FakeClient({"Generated runtime answer": reject}, model="gpt-judge"), log_path=tmp_path / "j.jsonl")
    assert (part["judge_verdict"], part["status"]) == ("rejected", "requires_human_review")


def test_a_refused_norm_is_degraded_with_nothing_to_judge(tmp_path):
    envelope = generate_control_backlog_on_demand([_norm(12, judge_verdict="rejected")], CONTEXT, _generator(), log_path=tmp_path / "g.jsonl")
    assert envelope["judge_verdict"] == "not_run" and envelope["answer"]["refused"] is True


class _Failing:
    """A judge whose request fails, after it was sent or before."""

    model = "gpt-judge"

    def __init__(self, sends: bool):
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "requests_sent": 0}
        self._sends = sends

    def complete(self, system: str, user: str) -> str:
        if self._sends:
            self.usage["requests_sent"] += 1
        raise RuntimeError("overloaded")


# Review I9: the backlog judge's failure branch: after its request was sent,
# judge_error with requires_human_review and the judge's usage; before any
# request, the failure is raised to the route (503, not billed).
def test_a_backlog_judge_failing_after_its_request_answers_judge_error_and_before_it_raises(tmp_path):
    items = generate_control_backlog_on_demand(NORMS, CONTEXT, _generator(), log_path=tmp_path / "g.jsonl")["answer"]["items"]
    part = judge_backlog_on_demand(NORMS, items, CONTEXT, _Failing(sends=True), log_path=tmp_path / "j.jsonl")
    assert (part["judge_verdict"], part["status"], part["judge_setting"]) == ("judge_error", "requires_human_review", "demo")
    assert part["usage"]["judge"]["requests_sent"] >= 1
    with pytest.raises(RuntimeError):
        judge_backlog_on_demand(NORMS, items, CONTEXT, _Failing(sends=False), log_path=tmp_path / "j.jsonl")

"""Batch evidence mode tests (#35): per-norm results, conservative envelope."""

from __future__ import annotations

import json

import pytest
from test_evidence import EVIDENCE, JUDGE_ACCEPT, JUDGE_REJECT, NORM, REAL_QUOTE, gen_answer

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.evidence import (
    accepted_norms_for_article,
    evaluate_evidence_batch,
)

NORM_B = {
    **NORM,
    "norm_id": "norm:eu-ai-act:article-9:paragraph-2:n1",
    "source_node_id": "eu-ai-act:article-9:paragraph-2",
    "source_span_id": "span:009.002",
    "action": "review and update",
    "object": "the risk management system",
}
NORM_REJECTED = {**NORM, "norm_id": "norm:x", "judge_verdict": "rejected"}


def run_batch(norms, gen_by_norm, judge_by_norm, tmp_path):
    generator = FakeClient(gen_by_norm, model="fake-generator")
    judge = FakeClient(judge_by_norm, model="fake-judge")
    return evaluate_evidence_batch(
        norms,
        EVIDENCE,
        generator,
        judge,
        graph_version="build-test",
        log_path=tmp_path / "runtime_log.jsonl",
    )


def test_batch_returns_one_envelope_with_per_norm_results(tmp_path):
    envelope = run_batch(
        [NORM, NORM_B],
        {
            NORM["norm_id"]: gen_answer("satisfied", [REAL_QUOTE]),
            NORM_B["norm_id"]: gen_answer("missing", []),
        },
        {NORM["norm_id"]: JUDGE_ACCEPT, NORM_B["norm_id"]: JUDGE_ACCEPT},
        tmp_path,
    )
    answer = envelope["answer"]
    assert answer["evaluated"] == 2
    by_norm = {r["norm_id"]: r for r in answer["results"]}
    assert by_norm[NORM["norm_id"]]["status"] == "satisfied_with_evidence"
    assert by_norm[NORM_B["norm_id"]]["status"] == "applicable_missing_evidence"
    # Most conservative per-norm status wins the envelope.
    assert envelope["status"] == "applicable_missing_evidence"
    assert envelope["judge_verdict"] == "accepted"
    assert set(envelope["source_nodes"]) == {
        "eu-ai-act:article-9:paragraph-1",
        "eu-ai-act:article-9:paragraph-2",
    }


def test_batch_judge_rejection_on_one_norm_degrades_the_envelope(tmp_path):
    envelope = run_batch(
        [NORM, NORM_B],
        {
            NORM["norm_id"]: gen_answer("satisfied", [REAL_QUOTE]),
            NORM_B["norm_id"]: gen_answer("satisfied", [REAL_QUOTE]),
        },
        {NORM["norm_id"]: JUDGE_ACCEPT, NORM_B["norm_id"]: JUDGE_REJECT},
        tmp_path,
    )
    assert envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "needs_human_review"
    assert envelope["confidence"] == 0.0


def test_batch_skips_non_accepted_norms_and_reports_them(tmp_path):
    envelope = run_batch(
        [NORM, NORM_REJECTED],
        {NORM["norm_id"]: gen_answer("satisfied", [REAL_QUOTE])},
        {NORM["norm_id"]: JUDGE_ACCEPT},
        tmp_path,
    )
    answer = envelope["answer"]
    assert answer["evaluated"] == 1
    assert answer["skipped"] == [
        {"norm_id": "norm:x", "reason": "judge_verdict 'rejected' is not accepted"}
    ]
    assert any("norm:x skipped" in fact for fact in envelope["missing_facts"])


def test_batch_with_no_accepted_norms_is_refused(tmp_path):
    envelope = run_batch([NORM_REJECTED], {}, {}, tmp_path)
    assert envelope["status"] == "requires_human_review"
    assert envelope["answer"]["refused"] is True


def test_batch_requires_norms():
    with pytest.raises(ValueError, match="at least one norm"):
        evaluate_evidence_batch(
            [], EVIDENCE, FakeClient({}), FakeClient({}), graph_version="t"
        )


def test_accepted_norms_for_article_filters_by_prefix_and_verdict():
    payload = {"norms": [NORM, NORM_B, NORM_REJECTED,
                         {**NORM, "norm_id": "n:14", "source_node_id": "eu-ai-act:article-14:paragraph-1"}]}
    selected = accepted_norms_for_article(payload, "eu-ai-act:article-9")
    assert [n["norm_id"] for n in selected] == [NORM["norm_id"], NORM_B["norm_id"]]


def test_batch_audit_log_has_one_generator_event_per_norm(tmp_path):
    run_batch(
        [NORM, NORM_B],
        {
            NORM["norm_id"]: gen_answer("satisfied", [REAL_QUOTE]),
            NORM_B["norm_id"]: gen_answer("missing", []),
        },
        {NORM["norm_id"]: JUDGE_ACCEPT, NORM_B["norm_id"]: JUDGE_ACCEPT},
        tmp_path,
    )
    events = [
        json.loads(line)
        for line in (tmp_path / "runtime_log.jsonl").read_text().splitlines()
    ]
    gen_events = [e for e in events if e.get("direction") == "generator"]
    assert {e["norm_id"] for e in gen_events} == {NORM["norm_id"], NORM_B["norm_id"]}

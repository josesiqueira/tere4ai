"""Adversarial evidence corpus tests (#68): red-team fixtures, offline.

Every fixture simulates the worst case at the model boundary: a naive
generator that does exactly what the attack wants. The assertions pin the
mechanical safeguards that hold regardless of model behaviour, and the
judge-gate behaviour with a rejecting judge. FakeClient only; no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.evidence import evaluate_project_evidence

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads(
    (ROOT / "tests" / "fixtures" / "adversarial_evidence.json").read_text(encoding="utf-8")
)
FIXTURES = CORPUS["fixtures"]

NORM = {
    "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
    "source_node_id": "eu-ai-act:article-9:paragraph-1",
    "source_span_id": "span:009.001",
    "deontic_type": "obligation",
    "modal": "shall",
    "actor_inferred": "provider",
    "action": "establish, implement, document and maintain",
    "object": "a risk management system",
    "conditions": [],
    "exceptions": [],
    "judge_verdict": "accepted",
    "review_status": "accepted",
}

SCORES = {
    "semantic_similarity": 0.9,
    "normative_relevance": 0.85,
    "operational_utility": 0.8,
    "evidence_strength": 0.1,
    "judge_confidence": 0.9,
}
JUDGE_REJECT = json.dumps(
    {
        "verdict": "rejected",
        "scores": SCORES,
        "rationale": "The evidence is adversarial and does not ground the assessment.",
    }
)
JUDGE_ACCEPT = json.dumps(
    {
        "verdict": "accepted",
        "scores": {**SCORES, "evidence_strength": 0.9},
        "rationale": "Scripted worst-case acceptance (judge fooled).",
    }
)


def run_fixture(fixture, judge_response, tmp_path):
    gen_response = json.dumps(
        {
            "assessment": fixture["naive_assessment"],
            "quotes": fixture["naive_quotes"],
            "gaps": [],
            "rationale": "Naive generator complying with the artifact.",
        }
    )
    generator = FakeClient({NORM["norm_id"]: gen_response}, model="fake-generator")
    judge = FakeClient({NORM["norm_id"]: judge_response}, model="fake-judge")
    return evaluate_project_evidence(
        NORM,
        {"artifact_type": fixture["artifact_type"], "content": fixture["content"]},
        generator,
        judge,
        graph_version="build-test",
        log_path=tmp_path / "runtime_log.jsonl",
    )


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["id"])
def test_rejecting_judge_forces_human_review_on_every_attack(fixture, tmp_path):
    envelope = run_fixture(fixture, JUDGE_REJECT, tmp_path)
    assert envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "rejected"
    assert envelope["confidence"] == 0.0
    # The forbidden vocabulary never appears as the status even under bait.
    assert envelope["status"] not in ("compliant", "certified")


@pytest.mark.parametrize(
    "fixture",
    [f for f in FIXTURES if any(q not in f["content"] for q in f["naive_quotes"])],
    ids=lambda f: f["id"],
)
def test_fabricated_quotes_drop_mechanically_even_if_the_judge_is_fooled(
    fixture, tmp_path
):
    envelope = run_fixture(fixture, JUDGE_ACCEPT, tmp_path)
    answer = envelope["answer"]
    for quote in answer["quotes"]:
        assert quote in fixture["content"], "non-verbatim quote survived"
    assert answer["dropped_quotes"] >= 1
    if not answer["quotes"]:
        # All quotes fabricated: the assessment itself is downgraded.
        assert answer["assessment"] == "cannot_assess"


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["id"])
def test_no_attack_ever_yields_satisfied_without_verbatim_support(fixture, tmp_path):
    envelope = run_fixture(fixture, JUDGE_ACCEPT, tmp_path)
    answer = envelope["answer"]
    if answer["assessment"] == "satisfied":
        assert answer["quotes"], "satisfied with zero surviving verbatim quotes"
        for quote in answer["quotes"]:
            assert quote in fixture["content"]


def test_corpus_covers_all_declared_attack_classes():
    declared = set(CORPUS["attack_classes"])
    used = {f["attack_class"] for f in FIXTURES}
    assert used == declared
    assert len(FIXTURES) >= 10

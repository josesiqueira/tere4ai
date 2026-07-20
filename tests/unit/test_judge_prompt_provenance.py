"""Judge decisions are bound to the exact prompt bytes that produced them.

Hardening (2026-07-20): prompt_version alone cannot detect an in-place edit
of a prompt file (the label still reads "v1"). Every generator and judge
event, and every JudgeRun record, now also carries prompt_sha256, the
content hash of the prompt actually used. This test proves the hash is
present, equals the real prompt file's hash, and changes when the prompt
text changes, so a judge change is always detectable and tied to the
decisions it made.

FakeClient only: no network, no keys.
"""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.pipeline import (
    extract_norms,
    load_prompt,
    prompt_sha256,
)
from tere4ai.judge.runtime_grounding import ground_check

REPO_ROOT = Path(__file__).resolve().parents[2]


def _span(anchor: str) -> dict:
    return {
        "span_id": f"span:{anchor}",
        "snapshot_file": "fake.html",
        "snapshot_sha256": "0" * 64,
        "start": 0,
        "end": 10,
        "anchor": anchor,
    }


FAKE_DUMP = {
    "build": {"build_id": "build-test"},
    "nodes": [
        {
            "id": "eu-ai-act:article-99:paragraph-1",
            "layer": 1,
            "type": "Paragraph",
            "index": 1,
            "text": "1. A risk log shall be kept for high-risk AI systems.",
            "source_span": _span("099.001"),
        },
    ],
    "edges": [],
}

GENERATOR_ANSWER = json.dumps(
    {
        "norms": [
            {
                "deontic_type": "obligation",
                "modal": "shall",
                "actor_explicit": "provider",
                "actor_inferred": None,
                "actor_inference_source_node_id": None,
                "action": "keep",
                "object": "a risk log",
                "target_system_category": "high_risk",
                "conditions": [],
                "exceptions": [],
                "lifecycle_phase_ids": ["operation_monitoring"],
            }
        ]
    }
)

JUDGE_ACCEPT = json.dumps(
    {
        "verdict": "accepted",
        "scores": {
            "semantic_similarity": 0.95,
            "normative_relevance": 0.9,
            "operational_utility": 0.8,
            "evidence_strength": 0.88,
            "judge_confidence": 0.9,
        },
        "rationale": "Supported verbatim.",
    }
)


def _run_extraction(tmp_path):
    # "Context (orientation only)" appears only in the generator message;
    # "Candidate norm (JSON)" appears only in the judge message.
    generator = FakeClient(
        {"Context (orientation only)": GENERATOR_ANSWER}, model="fake-generator"
    )
    judge = FakeClient({"Candidate norm (JSON)": JUDGE_ACCEPT}, model="fake-judge")
    log_path = tmp_path / "extraction_log.jsonl"
    result = extract_norms(
        FAKE_DUMP,
        ["eu-ai-act:article-99:paragraph-1"],
        generator,
        judge,
        log_path=log_path,
    )
    events = [json.loads(line) for line in log_path.read_text().splitlines()]
    return result, events


def test_extraction_events_and_judgeruns_carry_the_real_prompt_hash(tmp_path):
    result, events = _run_extraction(tmp_path)
    extract_hash = prompt_sha256(load_prompt("extract_norms", "v1"))
    judge_hash = prompt_sha256(load_prompt("judge_norms", "v1"))

    gen_events = [e for e in events if e["direction"] == "generator"]
    judge_events = [e for e in events if e["direction"] == "judge"]
    assert gen_events and judge_events
    for event in gen_events:
        assert event["prompt_sha256"] == extract_hash
    for event in judge_events:
        assert event["prompt_sha256"] == judge_hash

    assert result["judge_runs"], "expected at least one JudgeRun"
    for judge_run in result["judge_runs"]:
        assert judge_run["prompt_sha256"] == judge_hash
        # The hash is tied to the same version label, not a substitute for it.
        assert judge_run["prompt_version"] == "v1"


def test_prompt_hash_changes_when_the_prompt_text_changes():
    """The whole point: an in-place edit is detectable even at the same version."""
    current = prompt_sha256(load_prompt("judge_norms", "v1"))
    edited = prompt_sha256(load_prompt("judge_norms", "v1") + "\nnew instruction\n")
    assert current != edited


def test_runtime_grounding_judgerun_carries_the_real_prompt_hash(tmp_path):
    judge = FakeClient({"Cited norms": JUDGE_ACCEPT}, model="fake-judge")
    out = ground_check(
        answer_text="Some grounded answer citing norm:x.",
        cited_norms=[{"norm_id": "norm:x", "conditions": [], "exceptions": []}],
        evidence_text=None,
        judge=judge,
        log_path=tmp_path / "runtime_log.jsonl",
    )
    expected = prompt_sha256(load_prompt("runtime_grounding", "v1"))
    assert out["judge_run"]["prompt_sha256"] == expected
    events = [
        json.loads(line)
        for line in (tmp_path / "runtime_log.jsonl").read_text().splitlines()
    ]
    assert events and all(e["prompt_sha256"] == expected for e in events)

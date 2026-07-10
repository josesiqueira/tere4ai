"""Offline tests for generate_control_backlog (DEC-06 partial, DEC-08).

Uses FakeClient only: no network, no keys, no graph dumps. Verifies the
behavioral safeguards: items citing unknown norm_ids are mechanically
dropped and counted, truncation beyond max_norms is flagged (no silent
caps), the obligation/prohibition to "must" mapping is honored, non-accepted
norms are refused, a judge-rejected backlog degrades to
requires_human_review with the rationale attached, and the runtime log
carries no key material.
"""

from __future__ import annotations

import json

import pytest

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.backlog import generate_control_backlog
from tere4ai.mcp_server.tools import STATUS_VOCABULARY


def make_norm(article, index, deontic_type="obligation", **overrides):
    node = f"eu-ai-act:article-{article}:paragraph-1"
    norm = {
        "norm_id": f"norm:{node}:n{index}",
        "layer": 2,
        "type": "NormativeStatement",
        "source_node_id": node,
        "source_span_id": f"span:{article:03d}.001",
        "deontic_type": deontic_type,
        "modal": "shall",
        "actor_explicit": "provider",
        "actor_inferred": None,
        "actor_inference_source_node_id": None,
        "action": "document",
        "object": "the required process",
        "target_system_category": "high_risk",
        "conditions": [],
        "exceptions": [],
        "extraction_method": "llm_extract_v1",
        "extractor_model": "fake-generator",
        "confidence": 0.9,
        "judge_verdict": "accepted",
        "review_status": "accepted",
    }
    norm.update(overrides)
    return norm


NORM_A = make_norm(9, 1)
NORM_B = make_norm(10, 1)
NORM_C = make_norm(5, 1, deontic_type="prohibition")
KEY = NORM_A["norm_id"]  # present in generator and judge user messages

SCORES = {
    "semantic_similarity": 0.9,
    "normative_relevance": 0.85,
    "operational_utility": 0.8,
    "evidence_strength": 0.75,
    "judge_confidence": 0.9,
}
JUDGE_ACCEPT = json.dumps(
    {"verdict": "accepted", "scores": SCORES, "rationale": "Items stay within the cited norms."}
)
JUDGE_REJECT = json.dumps(
    {
        "verdict": "rejected",
        "scores": {**SCORES, "evidence_strength": 0.1},
        "rationale": "An item asserts more than the cited norms support.",
    }
)


def item(title, norm_ids, priority="must", suggested=("documentation",)):
    return {
        "title": title,
        "description": f"Do the engineering work for {title}.",
        "norm_ids": list(norm_ids),
        "suggested_evidence": list(suggested),
        "priority": priority,
    }


def gen_items(*items_):
    return json.dumps({"items": list(items_)})


def run_tool(gen_response, judge_response, tmp_path, norms=None, **kwargs):
    norms = norms if norms is not None else [NORM_A, NORM_B, NORM_C]
    generator = FakeClient({KEY: gen_response}, model="fake-generator")
    judge = FakeClient({KEY: judge_response}, model="fake-judge")
    log_path = tmp_path / "runtime_log.jsonl"
    envelope = generate_control_backlog(
        norms,
        "A high-risk AI triage system for a hospital.",
        generator,
        judge,
        prompt_version="v1",
        graph_version="build-test",
        log_path=log_path,
        **kwargs,
    )
    return envelope, generator, judge, log_path


def test_happy_path_status_and_items(tmp_path):
    envelope, _, judge, _ = run_tool(
        gen_items(
            item("Risk management process", [NORM_A["norm_id"]]),
            item("Data governance and prohibition guardrails", [NORM_B["norm_id"], NORM_C["norm_id"]]),
        ),
        JUDGE_ACCEPT,
        tmp_path,
    )
    # A backlog defines work; nothing is satisfied yet (DEC-08).
    assert envelope["status"] == "applicable_missing_evidence"
    assert envelope["judge_verdict"] == "accepted"
    answer = envelope["answer"]
    assert len(answer["items"]) == 2
    assert answer["dropped_items"] == 0
    assert answer["truncated"] is False
    assert answer["judge_rationale"] == "Items stay within the cited norms."
    assert answer["judge_model"] == "fake-judge"
    cited = {norm_id for it in answer["items"] for norm_id in it["norm_ids"]}
    assert cited <= {NORM_A["norm_id"], NORM_B["norm_id"], NORM_C["norm_id"]}
    assert set(envelope["source_nodes"]) == {
        NORM_A["source_node_id"],
        NORM_B["source_node_id"],
        NORM_C["source_node_id"],
    }
    assert len(judge.calls) == 1


def test_items_citing_unknown_norm_ids_are_dropped_and_counted(tmp_path):
    envelope, _, _, _ = run_tool(
        gen_items(
            item("Grounded item", [NORM_A["norm_id"]]),
            item("Hallucinated item", ["norm:eu-ai-act:article-999:paragraph-1:n1"]),
        ),
        JUDGE_ACCEPT,
        tmp_path,
    )
    answer = envelope["answer"]
    assert len(answer["items"]) == 1
    assert answer["items"][0]["title"] == "Grounded item"
    assert answer["dropped_items"] == 1
    assert any("outside" in note and "article-999" in note for note in answer["notes"])


def test_all_items_dropped_degrades_without_judge_call(tmp_path):
    envelope, _, judge, _ = run_tool(
        gen_items(item("Hallucinated item", ["norm:eu-ai-act:article-999:paragraph-1:n1"])),
        JUDGE_ACCEPT,
        tmp_path,
    )
    assert envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "not_run"
    assert envelope["answer"]["refused"] is True
    assert judge.calls == []


def test_truncation_beyond_max_norms_is_flagged_never_silent(tmp_path):
    envelope, generator, _, _ = run_tool(
        gen_items(item("Risk management process", [NORM_A["norm_id"]])),
        JUDGE_ACCEPT,
        tmp_path,
        max_norms=2,
    )
    answer = envelope["answer"]
    assert answer["truncated"] is True
    assert any("max_norms=2" in note for note in answer["notes"])
    # The generator never saw the truncated norm.
    _, gen_user = generator.calls[0]
    assert NORM_C["norm_id"] not in gen_user
    assert NORM_A["norm_id"] in gen_user and NORM_B["norm_id"] in gen_user


def test_obligation_and_prohibition_map_to_must_in_the_fake_path(tmp_path):
    envelope, _, _, _ = run_tool(
        gen_items(
            item("Obligation control", [NORM_A["norm_id"]], priority="must"),
            item("Prohibition guardrail", [NORM_C["norm_id"]], priority="must"),
        ),
        JUDGE_ACCEPT,
        tmp_path,
    )
    priorities = {it["title"]: it["priority"] for it in envelope["answer"]["items"]}
    assert priorities == {"Obligation control": "must", "Prohibition guardrail": "must"}


def test_invalid_priority_is_recomputed_from_deontic_types(tmp_path):
    envelope, _, _, _ = run_tool(
        gen_items(item("Obligation control", [NORM_A["norm_id"]], priority="urgent")),
        JUDGE_ACCEPT,
        tmp_path,
    )
    answer = envelope["answer"]
    assert answer["items"][0]["priority"] == "must"  # obligation forces must
    assert any("recomputed mechanically" in note for note in answer["notes"])


def test_non_accepted_norm_refuses_the_whole_call(tmp_path):
    rejected = make_norm(11, 1, judge_verdict="rejected", review_status="rejected")
    generator = FakeClient({}, model="fake-generator")
    judge = FakeClient({}, model="fake-judge")
    envelope = generate_control_backlog(
        [NORM_A, rejected],
        "context",
        generator,
        judge,
        graph_version="build-test",
        log_path=tmp_path / "runtime_log.jsonl",
    )
    assert envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "not_run"
    assert rejected["norm_id"] in envelope["answer"]["message"]
    assert "judge-accepted" in envelope["answer"]["message"]
    assert generator.calls == []
    assert judge.calls == []


def test_judge_rejected_backlog_degrades_with_rationale(tmp_path):
    envelope, _, _, _ = run_tool(
        gen_items(item("Risk management process", [NORM_A["norm_id"]])),
        JUDGE_REJECT,
        tmp_path,
    )
    assert envelope["status"] == "requires_human_review"
    assert envelope["status"] != "applicable_missing_evidence"
    assert envelope["judge_verdict"] == "rejected"
    assert envelope["confidence"] == 0.0
    answer = envelope["answer"]
    assert answer["items"]  # visible for the human reviewer, never as accepted output
    assert answer["judge_rationale"] == "An item asserts more than the cited norms support."
    assert any("requires human review" in fact for fact in envelope["missing_facts"])


def test_generator_parse_failure_degrades_without_judge_call(tmp_path):
    envelope, generator, judge, _ = run_tool(
        ["%%% not json", "%%% still not json"], JUDGE_ACCEPT, tmp_path
    )
    assert envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "not_run"
    assert len(generator.calls) == 2
    assert judge.calls == []


def test_empty_norms_list_raises(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        generate_control_backlog(
            [],
            "context",
            FakeClient({}, model="g"),
            FakeClient({}, model="j"),
            log_path=tmp_path / "log.jsonl",
        )


def test_envelope_carries_notice_and_no_compliance_claims(tmp_path):
    envelope, _, _, _ = run_tool(
        gen_items(item("Risk management process", [NORM_A["norm_id"]])),
        JUDGE_ACCEPT,
        tmp_path,
    )
    assert envelope["non_legal_advice_notice"]
    dumped = json.dumps(envelope)
    assert "compliant" not in dumped
    assert "certified" not in dumped
    assert "approved" not in dumped
    assert envelope["status"] in STATUS_VOCABULARY


def test_runtime_log_written_with_no_key_material(tmp_path):
    _, _, _, log_path = run_tool(
        gen_items(item("Risk management process", [NORM_A["norm_id"]])),
        JUDGE_ACCEPT,
        tmp_path,
    )
    assert log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    directions = [line["direction"] for line in lines]
    assert directions == ["generator", "judge"]
    for line in lines:
        assert len(line["input_sha256"]) == 64
    assert lines[1]["judge_kind"] == "runtime_grounding"
    raw = log_path.read_text()
    for secret_marker in ("sk-", "api_key", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert secret_marker not in raw
    # No full prompts and no full untrusted context in the log.
    assert "control-backlog generator" not in raw


# Grouping + condition-aware priority (#35) -------------------------------------


def test_items_citing_identical_norm_set_are_merged(tmp_path):
    norm = make_norm(9, 1)
    two_items = json.dumps(
        {
            "items": [
                {
                    "title": "Establish the risk register",
                    "description": "Set up and maintain the register.",
                    "norm_ids": [norm["norm_id"]],
                    "suggested_evidence": ["risk register"],
                    "priority": "should",
                },
                {
                    "title": "Create a register of risks",
                    "description": "Duplicate control expressed differently.",
                    "norm_ids": [norm["norm_id"]],
                    "suggested_evidence": ["risk policy"],
                    "priority": "must",
                },
            ]
        }
    )
    envelope, _, _, _ = run_tool(two_items, JUDGE_ACCEPT, tmp_path, norms=[norm])
    answer = envelope["answer"]
    assert len(answer["items"]) == 1
    assert answer["merged_items"] == 1
    item = answer["items"][0]
    assert item["title"] == "Establish the risk register"
    assert item["suggested_evidence"] == ["risk register", "risk policy"]
    # Strictest priority survives the merge.
    assert item["priority"] == "must"
    assert any("merged into" in note for note in answer["notes"])


def test_mechanical_priority_downgrades_conditional_obligations(tmp_path):
    conditional = make_norm(9, 1, conditions=["where the system is high-risk"])
    item = json.dumps(
        {
            "items": [
                {
                    "title": "Conditional control",
                    "description": "Applies only under the stated condition.",
                    "norm_ids": [conditional["norm_id"]],
                    "suggested_evidence": [],
                    "priority": "not-a-priority",
                }
            ]
        }
    )
    envelope, _, _, _ = run_tool(item, JUDGE_ACCEPT, tmp_path, norms=[conditional])
    assert envelope["answer"]["items"][0]["priority"] == "should"


def test_mechanical_priority_keeps_unconditional_obligations_must(tmp_path):
    unconditional = make_norm(9, 1, conditions=[])
    item = json.dumps(
        {
            "items": [
                {
                    "title": "Unconditional control",
                    "description": "Always applies.",
                    "norm_ids": [unconditional["norm_id"]],
                    "suggested_evidence": [],
                    "priority": "not-a-priority",
                }
            ]
        }
    )
    envelope, _, _, _ = run_tool(item, JUDGE_ACCEPT, tmp_path, norms=[unconditional])
    assert envelope["answer"]["items"][0]["priority"] == "must"

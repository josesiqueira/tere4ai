"""Offline tests for generate_control_backlog (DEC-06 partial, DEC-08).

Uses FakeClient only: no network, no keys, no graph dumps. Verifies the
behavioral safeguards: items citing unknown norm_ids are mechanically
dropped and counted, every norm given reaches the generator with no cap
and no truncation (B71, decided 2026-09-08), the obligation/prohibition to
"must" mapping is honored, non-accepted norms are refused, a
judge-rejected backlog degrades to requires_human_review with the
rationale attached, and the runtime log carries no key material.
"""

from __future__ import annotations

import json

import pytest

from tere4ai.extract_norms.model_clients import FakeClient, _new_usage
from tere4ai.extract_norms.pipeline import load_prompt
from tere4ai.extract_norms.requirement_type import DEFINITIONS_TEXT, SCOPE_TEXT
from tere4ai.judge import runtime_grounding
from tere4ai.mcp_server.backlog import DEFAULT_PROMPT_VERSION, generate_control_backlog
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
    assert "truncated" not in answer
    assert answer["judge_rationale"] == "Items stay within the cited norms."
    assert answer["judge_model"] == "fake-judge"
    assert answer["judge_effort"] == "not configured"  # FakeClient declares no effort; a real client carries its declared one
    assert answer["judge_temperature"] == "not configured"
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


def test_all_given_norms_reach_the_generator_no_cap_no_truncation(tmp_path):
    """B71 (decided 2026-09-08): no norm cap, no truncation, anywhere on the
    backlog path. The tool takes every norm it is given; a call the model
    cannot serve fails loudly, it is never served with fewer norms."""
    norms = [make_norm(article, 1) for article in range(1, 61)]
    received_ids: list[str] = []

    class RecordingGenerator:
        model = "fake-generator-recording"

        def complete(self, system: str, user: str) -> str:
            received_ids.extend(
                norm["norm_id"] for norm in norms if norm["norm_id"] in user
            )
            return gen_items(item("Full backlog", [norms[0]["norm_id"]]))

    judge = FakeClient({"": JUDGE_ACCEPT}, model="fake-judge")
    envelope = generate_control_backlog(
        norms,
        "A high-risk AI triage system for a hospital.",
        RecordingGenerator(),
        judge,
        prompt_version="v1",
        graph_version="build-test",
        log_path=tmp_path / "runtime_log.jsonl",
    )
    assert received_ids == [norm["norm_id"] for norm in norms]
    assert len(received_ids) == 60
    assert "truncated" not in envelope["answer"]


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


# Generator model id, effort, and both roles' usage (B91, spec F D-F26 (g)) ----


class CountingClient(FakeClient):
    """A FakeClient with the real clients' usage record (B91) and declared effort and temperature."""

    def __init__(self, scripted, model, effort="xhigh", temperature="0", tokens=(100, 20)):
        super().__init__(scripted, model=model)
        self.effort = effort
        self.temperature = temperature
        self.usage = _new_usage()
        self._tokens = tokens

    def complete(self, system, user):
        self.usage["requests_sent"] += 1
        reply = super().complete(system, user)
        self.usage["calls"] += 1
        self.usage["replies_with_usage"] += 1
        self.usage["input_tokens"] += self._tokens[0]
        self.usage["output_tokens"] += self._tokens[1]
        return reply


def _counted_run(tmp_path, gen_response, judge_response, generator=None):
    generator = generator or CountingClient({KEY: gen_response}, model="fake-generator")
    judge = CountingClient({KEY: judge_response}, model="fake-judge", tokens=(40, 8))
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator, judge,
        prompt_version="v1", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    return envelope, generator, judge


def test_backlog_answer_names_the_generator_and_both_roles_usage(tmp_path):
    envelope, _, _ = _counted_run(tmp_path, gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT)
    answer = envelope["answer"]
    assert answer["generator_model"] == "fake-generator" and answer["generator_effort"] == "xhigh"
    assert answer["judge_model"] == "fake-judge" and answer["judge_effort"] == "xhigh"
    assert answer["generator_temperature"] == "0" and answer["judge_temperature"] == "0"
    # final review A3 adds the sixth count, requests_refused, and spec F D-F32
    # the seventh, requests_rejected_before_processing (none here)
    assert answer["usage"] == {
        "generator": {"calls": 1, "input_tokens": 100, "output_tokens": 20, "requests_sent": 1,
                      "replies_with_usage": 1, "requests_refused": 0, "requests_rejected_before_processing": 0},
        "judge": {"calls": 1, "input_tokens": 40, "output_tokens": 8, "requests_sent": 1,
                  "replies_with_usage": 1, "requests_refused": 0, "requests_rejected_before_processing": 0},
    }


def test_backlog_usage_is_the_spend_of_this_call_only(tmp_path):
    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))},
                               model="fake-generator")
    generator.usage.update({"calls": 5, "input_tokens": 999, "requests_sent": 6, "replies_with_usage": 5})
    envelope, _, _ = _counted_run(tmp_path, None, JUDGE_ACCEPT, generator=generator)
    assert envelope["answer"]["usage"]["generator"]["calls"] == 1
    assert envelope["answer"]["usage"]["generator"]["input_tokens"] == 100


def test_backlog_usage_of_a_client_without_a_usage_record_is_none(tmp_path):
    envelope, _, _, _ = run_tool(gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT, tmp_path)
    answer = envelope["answer"]
    assert answer["usage"] == {"generator": None, "judge": None}
    assert answer["generator_model"] == "fake-generator" and answer["generator_effort"] == "not configured"


def test_a_degraded_answer_after_the_generator_request_still_carries_its_spend(tmp_path):
    envelope, generator, _ = _counted_run(tmp_path, "not json at all", JUDGE_ACCEPT)
    answer = envelope["answer"]
    assert answer["refused"] is True and envelope["status"] == "requires_human_review"
    assert answer["usage"]["generator"]["requests_sent"] == len(generator.calls)
    assert answer["usage"]["judge"]["requests_sent"] == 0
    assert answer["generator_model"] == "fake-generator"


def test_the_refusal_before_any_request_carries_no_spend(tmp_path):
    rejected = dict(NORM_A, judge_verdict="rejected")
    generator = CountingClient({KEY: "{}"}, model="fake-generator")
    judge = CountingClient({KEY: JUDGE_ACCEPT}, model="fake-judge")
    envelope = generate_control_backlog([rejected], "ctx", generator, judge, log_path=tmp_path / "l.jsonl")
    assert "usage" not in envelope["answer"] and "generator_model" not in envelope["answer"]
    # spec F D-F35 (1): nor the prompts, which travel with the spend
    assert not set(envelope["answer"]) & {"generator_prompt", "generator_prompt_version", "generator_prompt_sha256",
                                          "judge_prompt", "judge_prompt_version", "judge_prompt_sha256"}


def test_a_judge_failure_after_the_generator_answered_returns_a_degraded_answer_with_the_spend(tmp_path):
    """Final review A4: a raising grounding judge after a paid generation answers
    degraded with the spend, never a 502 that loses the generator's cost."""

    class FailingJudge(CountingClient):
        def complete(self, system, user):
            self.usage["requests_sent"] += 1
            raise RuntimeError("judge provider unreachable")

    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))}, model="fake-generator")
    judge = FailingJudge({KEY: JUDGE_ACCEPT}, model="fake-judge")
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator, judge,
        prompt_version="v1", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    answer = envelope["answer"]
    assert answer["refused"] is True and envelope["status"] == "requires_human_review"
    assert "runtime grounding judge failed" in answer["message"] and "RuntimeError" in answer["message"]
    assert answer["usage"]["generator"]["calls"] == 1 and answer["usage"]["judge"]["requests_sent"] == 1
    assert answer["generator_model"] == "fake-generator"


# B97 item 5: the judge that ran and failed is named so; a generator that
# raises after its retries still answers degraded with the requests it sent


def test_a_judge_failure_is_labelled_judge_error_not_not_run(tmp_path):
    class FailingJudge(CountingClient):
        def complete(self, system, user):
            self.usage["requests_sent"] += 1
            raise RuntimeError("judge provider unreachable")

    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))}, model="fake-generator")
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator,
        FailingJudge({KEY: JUDGE_ACCEPT}, model="fake-judge"),
        prompt_version="v1", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    assert envelope["judge_verdict"] == "judge_error"


def test_a_judge_error_answer_names_the_judge_model_and_effort_so_its_tokens_can_be_priced(tmp_path):
    """B98 seat B P3-3: a judge whose first reply did not parse and whose
    second attempt raised has spent tokens; the degraded answer names the
    judge's model and effort beside its usage, as it names the generator's."""

    class HalfFailingJudge(CountingClient):
        def complete(self, system, user):
            if self.usage["requests_sent"] == 0:
                self.usage["requests_sent"] += 1
                self.usage["calls"] += 1
                self.usage["replies_with_usage"] += 1
                self.usage["input_tokens"] += 100
                self.usage["output_tokens"] += 20
                return "not json"
            self.usage["requests_sent"] += 1
            raise RuntimeError("judge provider unreachable")

    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))}, model="fake-generator")
    judge = HalfFailingJudge({KEY: JUDGE_ACCEPT}, model="fake-judge", effort="high")
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator, judge,
        prompt_version="v1", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    answer = envelope["answer"]
    assert envelope["judge_verdict"] == "judge_error" and answer["usage"]["judge"]["input_tokens"] == 100
    assert answer["judge_model"] == "fake-judge" and answer["judge_effort"] == "high"
    assert answer["generator_model"] == "fake-generator" and answer["generator_effort"] == "xhigh"


def test_a_generator_that_raises_after_its_retries_answers_degraded_with_its_spend(tmp_path):
    class FailingGenerator(CountingClient):
        def complete(self, system, user):
            self.usage["requests_sent"] += 3  # the first attempt and the client's two retries
            self.usage["requests_refused"] += 3
            self.usage["requests_rejected_before_processing"] += 1  # one of the three was a 429 (spec F D-F32)
            raise RuntimeError("503 upstream overloaded")

    generator = FailingGenerator({KEY: "{}"}, model="fake-generator")
    judge = CountingClient({KEY: JUDGE_ACCEPT}, model="fake-judge")
    log_path = tmp_path / "runtime_log.jsonl"
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator, judge,
        prompt_version="v1", graph_version="build-test", log_path=log_path,
    )
    answer = envelope["answer"]
    assert answer["refused"] is True and envelope["status"] == "requires_human_review"
    assert envelope["judge_verdict"] == "not_run" and judge.calls == []
    assert answer["message"] == ("generator request failed, no backlog produced: "
                                 "RuntimeError: 503 upstream overloaded")
    assert answer["usage"]["generator"]["requests_sent"] == 3 and answer["usage"]["generator"]["calls"] == 0
    assert answer["usage"]["generator"]["requests_rejected_before_processing"] == 1
    assert answer["generator_model"] == "fake-generator"
    (event,) = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert event["direction"] == "generator" and event["parse_ok"] is False
    assert event["error"] == "generator request failed: RuntimeError: 503 upstream overloaded"


def test_an_interrupt_during_the_generator_request_still_propagates(tmp_path):
    class InterruptedGenerator(CountingClient):
        def complete(self, system, user):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        generate_control_backlog(
            [NORM_A], "ctx", InterruptedGenerator({KEY: "{}"}, model="fake-generator"),
            CountingClient({KEY: JUDGE_ACCEPT}, model="fake-judge"), log_path=tmp_path / "l.jsonl",
        )


def test_a_judge_step_that_raises_before_any_request_reads_not_run(tmp_path, monkeypatch):
    """Review M1: judge_error only when the judge sent a request."""
    import tere4ai.judge.runtime_grounding as rg

    real_load = rg.load_prompt

    def missing_prompt(kind, version):
        if kind == "runtime_grounding":
            raise FileNotFoundError("prompts/runtime_grounding_v1.md")
        return real_load(kind, version)

    monkeypatch.setattr(rg, "load_prompt", missing_prompt)
    envelope, _, judge = _counted_run(tmp_path, gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT)
    assert judge.calls == [] and envelope["answer"]["usage"]["judge"]["requests_sent"] == 0
    assert envelope["judge_verdict"] == "not_run" and envelope["answer"]["refused"] is True


# Spec F D-F35 (1): the answer names the prompt, the version and the SHA-256 of
# the prompt file's text for both roles, generate_backlog for the generator and
# runtime_grounding for the runtime judge, on every answer that carries the spend.


def _prompt_fields(version="v1", judge_sha256="read"):
    from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256

    if judge_sha256 == "read":
        judge_sha256 = prompt_sha256(load_prompt("runtime_grounding", version))
    return {
        "generator_prompt": "generate_backlog",
        "generator_prompt_version": version,
        "generator_prompt_sha256": prompt_sha256(load_prompt("generate_backlog", version)),
        "judge_prompt": "runtime_grounding",
        "judge_prompt_version": version,
        "judge_prompt_sha256": judge_sha256,
    }


def _fields_of(answer):
    return {key: answer.get(key) for key in _prompt_fields()}


def test_a_judged_answer_names_both_prompts_with_version_and_hash(tmp_path):
    envelope, _, _ = _counted_run(tmp_path, gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT)
    answer = envelope["answer"]
    assert _fields_of(answer) == _prompt_fields()
    # the judge's hash is the one the judge run and the audit log record
    events = [json.loads(line) for line in (tmp_path / "runtime_log.jsonl").read_text().splitlines()]
    (judge_event,) = [e for e in events if e["direction"] == "judge"]
    (generator_event,) = [e for e in events if e["direction"] == "generator"]
    assert answer["judge_prompt_sha256"] == judge_event["prompt_sha256"]
    assert answer["generator_prompt_sha256"] == generator_event["prompt_sha256"]


@pytest.mark.parametrize("gen_response", [
    "not json at all",  # generator output unusable
    gen_items(item("Risk management", ["norm:unknown"])),  # no item survives the citation check
])
def test_a_degraded_answer_with_the_spend_names_both_prompts(tmp_path, gen_response):
    envelope, _, _ = _counted_run(tmp_path, gen_response, JUDGE_ACCEPT)
    assert envelope["answer"]["refused"] is True
    assert _fields_of(envelope["answer"]) == _prompt_fields()


def test_a_failed_generator_request_or_judge_names_both_prompts(tmp_path):
    class FailingGenerator(CountingClient):
        def complete(self, system, user):
            self.usage["requests_sent"] += 1
            raise RuntimeError("503 upstream overloaded")

    envelope, _, _ = _counted_run(tmp_path, "{}", JUDGE_ACCEPT,
                                  generator=FailingGenerator({KEY: "{}"}, model="fake-generator"))
    assert _fields_of(envelope["answer"]) == _prompt_fields()

    class FailingJudge(CountingClient):
        def complete(self, system, user):
            self.usage["requests_sent"] += 1
            raise RuntimeError("judge provider unreachable")

    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))}, model="fake-generator")
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "A high-risk AI triage system for a hospital.", generator,
        FailingJudge({KEY: JUDGE_ACCEPT}, model="fake-judge"),
        prompt_version="v1", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    assert envelope["judge_verdict"] == "judge_error"
    assert _fields_of(envelope["answer"]) == _prompt_fields()


def test_an_unreadable_judge_prompt_is_named_with_no_hash(tmp_path, monkeypatch):
    import tere4ai.judge.runtime_grounding as rg

    real_load = rg.load_prompt

    def missing_prompt(kind, version):
        if kind == "runtime_grounding":
            raise FileNotFoundError("prompts/runtime_grounding/v1.md")
        return real_load(kind, version)

    monkeypatch.setattr(rg, "load_prompt", missing_prompt)
    envelope, _, _ = _counted_run(tmp_path, gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT)
    assert envelope["judge_verdict"] == "not_run"
    assert _fields_of(envelope["answer"]) == _prompt_fields(judge_sha256=None)


def test_the_prompt_version_reaches_both_roles(tmp_path, monkeypatch):
    """A version other than v1 is named on both roles (a v2 file is written for the test)."""
    import tere4ai.extract_norms.pipeline as pipeline

    prompts = tmp_path / "prompts"
    for kind in ("generate_backlog", "runtime_grounding"):
        (prompts / kind).mkdir(parents=True)
        text = (pipeline.PROMPTS_DIR / kind / "v1.md").read_text(encoding="utf-8")
        (prompts / kind / "v2.md").write_text(text + "\n", encoding="utf-8")
    monkeypatch.setattr(pipeline, "PROMPTS_DIR", prompts)
    generator = CountingClient({KEY: gen_items(item("Risk management", [NORM_A["norm_id"]]))}, model="fake-generator")
    judge = CountingClient({KEY: JUDGE_ACCEPT}, model="fake-judge")
    envelope = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "ctx", generator, judge, prompt_version="v2",
        graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    v2_hashes = {kind: pipeline.prompt_sha256((prompts / kind / "v2.md").read_text(encoding="utf-8"))
                 for kind in ("generate_backlog", "runtime_grounding")}
    answer = envelope["answer"]
    assert answer["generator_prompt_version"] == answer["judge_prompt_version"] == "v2"
    assert answer["generator_prompt_sha256"] == v2_hashes["generate_backlog"]
    assert answer["judge_prompt_sha256"] == v2_hashes["runtime_grounding"]
    # a degraded answer, which takes the judge's hash from the read before the
    # generator call, names v2 too
    degraded = generate_control_backlog(
        [NORM_A, NORM_B, NORM_C], "ctx", CountingClient({KEY: "not json"}, model="fake-generator"),
        CountingClient({KEY: JUDGE_ACCEPT}, model="fake-judge"), prompt_version="v2",
        graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )["answer"]
    assert degraded["refused"] is True and degraded["judge_prompt_version"] == "v2"
    assert degraded["judge_prompt_sha256"] == v2_hashes["runtime_grounding"]


def test_a_judged_answer_takes_the_judge_hash_from_its_judge_run(tmp_path, monkeypatch):
    """The read before the generator call fails, the judge's own read succeeds:
    the judged answer carries the hash the judge run records, never null."""
    import tere4ai.judge.runtime_grounding as rg

    real_load = rg.load_prompt
    reads = []

    def first_read_fails(kind, version):
        if kind == "runtime_grounding":
            reads.append(version)
            if len(reads) == 1:
                raise FileNotFoundError("prompts/runtime_grounding/v1.md")
        return real_load(kind, version)

    monkeypatch.setattr(rg, "load_prompt", first_read_fails)
    envelope, _, _ = _counted_run(tmp_path, gen_items(item("Risk management", [NORM_A["norm_id"]])), JUDGE_ACCEPT)
    assert len(reads) == 2 and envelope["answer"]["judge_prompt_sha256"] == _prompt_fields()["judge_prompt_sha256"]


# DEC-19, B65: each control carries its own requirement type; the runtime
# judge records its view of it without changing the backlog's verdict.


def run_v2(gen_response, judge_response, tmp_path, norms=None):
    """The backlog under its default prompts, generate_backlog v2 and
    runtime_grounding v2 (run_tool pins v1)."""
    norms = norms if norms is not None else [NORM_A, NORM_B, NORM_C]
    generator = FakeClient({KEY: gen_response}, model="fake-generator")
    judge = FakeClient({KEY: judge_response}, model="fake-judge")
    envelope = generate_control_backlog(
        norms, "A high-risk AI triage system for a hospital.", generator, judge,
        prompt_version="v2", graph_version="build-test", log_path=tmp_path / "runtime_log.jsonl",
    )
    return envelope, generator, judge


def typed_item(title, norm_ids, requirement_type, **extra):
    return {**item(title, norm_ids), "requirement_type": requirement_type, **extra}


def judge_with_views(verdict_json, views):
    reply = json.loads(verdict_json)
    reply["type_views"] = views
    return json.dumps(reply)


def test_the_v2_backlog_prompts_carry_the_definitions_and_are_the_default(tmp_path):
    assert DEFAULT_PROMPT_VERSION == "v2"
    generate = load_prompt("generate_backlog", "v2")
    grounding = load_prompt("runtime_grounding", "v2")
    for prompt in (generate, grounding):
        assert DEFINITIONS_TEXT in prompt
        assert SCOPE_TEXT not in prompt  # every control is typed; the scope is the norms'
    assert '"requirement_type": "process"' in generate
    assert '"type_views"' in grounding and "never a reason" in grounding
    assert '"requirement_type_agrees": false' not in grounding  # the example shows agreement
    generator = FakeClient({KEY: gen_items(typed_item("Risk process", [KEY], "process"))}, model="fake-generator")
    judge = FakeClient({KEY: JUDGE_ACCEPT}, model="fake-judge")
    envelope = generate_control_backlog([NORM_A], "A triage system.", generator, judge,
                                        log_path=tmp_path / "runtime_log.jsonl")
    assert generator.calls[0][0].startswith("# generate_backlog system prompt, version v2")
    assert judge.calls[0][0].startswith("# runtime_grounding system prompt, version v2")
    assert envelope["answer"]["generator_prompt_version"] == "v2"
    assert envelope["answer"]["judge_prompt_version"] == "v2"


def test_each_control_keeps_its_own_type(tmp_path):
    envelope, _, _ = run_v2(
        gen_items(typed_item("Retain logs for six months", [KEY], "functional"),
                  typed_item("Tamper-evident log storage", [NORM_B["norm_id"]], "quality")),
        JUDGE_ACCEPT, tmp_path,
    )
    assert [i["requirement_type"] for i in envelope["answer"]["items"]] == ["functional", "quality"]


@pytest.mark.parametrize("bad", [None, "non-functional", "", 7])
def test_a_control_without_a_valid_type_is_kept_with_null_and_a_note(tmp_path, bad):
    raw = item("Risk process", [KEY]) if bad is None else typed_item("Risk process", [KEY], bad)
    envelope, _, _ = run_v2(gen_items(raw), JUDGE_ACCEPT, tmp_path)
    answer = envelope["answer"]
    assert answer["dropped_items"] == 0
    assert answer["items"][0]["requirement_type"] is None
    assert any("no valid requirement_type" in note for note in answer["notes"])


def test_the_generator_and_the_judge_never_see_the_norms_types(tmp_path):
    """B65 ruling 10: the norms' types are left out of both digests, so a
    control's type and the judge's view of it are their own."""
    typed_norms = [{**n, "requirement_type": "process"} for n in (NORM_A, NORM_B, NORM_C)]
    _, generator, judge = run_v2(
        gen_items(typed_item("Retain logs", [KEY], "functional")), JUDGE_ACCEPT, tmp_path, norms=typed_norms
    )
    assert "requirement_type" not in generator.calls[0][1]
    assert "requirement_type" not in runtime_grounding._norm_digest(typed_norms[0])
    # the judge sees the control's own type, in the answer under review
    assert '"requirement_type": "functional"' in judge.calls[0][1]


def test_a_merged_control_keeps_the_first_items_type_and_says_so(tmp_path):
    envelope, _, _ = run_v2(
        gen_items(typed_item("Retain logs", [KEY], "functional"),
                  typed_item("Keep the logs", [KEY], "process")),
        JUDGE_ACCEPT, tmp_path,
    )
    answer = envelope["answer"]
    assert answer["merged_items"] == 1
    assert answer["items"][0]["requirement_type"] == "functional"
    assert any("requirement_type 'process' differs" in note for note in answer["notes"])


def test_the_judges_type_views_are_recorded_and_never_change_the_verdict(tmp_path):
    """Jose, 2026-10-01: "Record, do not gate (Recommended)"."""
    items_json = gen_items(
        typed_item("Retain logs", [KEY], "functional"),
        typed_item("Tamper-evident storage", [NORM_B["norm_id"]], "quality"),
        item("Untyped control", [NORM_C["norm_id"]]),
    )
    views = [
        {"item": 1, "requirement_type_agrees": True, "requirement_type": None},
        {"item": 2, "requirement_type_agrees": False, "requirement_type": "process"},
        {"item": 3, "requirement_type_agrees": True, "requirement_type": None},
    ]
    accepted, _, _ = run_v2(items_json, judge_with_views(JUDGE_ACCEPT, views), tmp_path)
    assert accepted["judge_verdict"] == "accepted"
    assert accepted["status"] == "applicable_missing_evidence"
    assert accepted["answer"]["judge_type_views"] == [
        {"judge_type_agrees": True, "judge_requirement_type": "functional"},
        {"judge_type_agrees": False, "judge_requirement_type": "process"},
        {"judge_type_agrees": None, "judge_requirement_type": None},  # a null-typed control records nothing
    ]
    rejected, _, _ = run_v2(items_json, judge_with_views(JUDGE_REJECT, views), tmp_path)
    assert rejected["judge_verdict"] == "rejected"
    assert rejected["answer"]["judge_type_views"] == accepted["answer"]["judge_type_views"]


@pytest.mark.parametrize("raw_views", [None, "agrees", [{"item": "1", "requirement_type_agrees": True}], []])
def test_unusable_type_views_record_null_and_keep_the_verdict(tmp_path, raw_views):
    reply = JUDGE_ACCEPT if raw_views is None else judge_with_views(JUDGE_ACCEPT, raw_views)
    envelope, _, _ = run_v2(gen_items(typed_item("Retain logs", [KEY], "functional")), reply, tmp_path)
    assert envelope["judge_verdict"] == "accepted"
    assert envelope["answer"]["judge_type_views"] == [{"judge_type_agrees": None, "judge_requirement_type": None}]


def test_a_v1_backlog_keeps_its_old_input_and_output(tmp_path):
    """Review I1 (ruling 49): under generate_backlog v1 and runtime_grounding
    v1 a control gains no type field, the judge's input carries none, and
    the answer has no judge_type_views."""
    envelope, _, judge, _ = run_tool(
        gen_items(typed_item("Retain logs", [KEY], "functional")),
        judge_with_views(JUDGE_ACCEPT, [{"item": 1, "requirement_type_agrees": True}]),
        tmp_path,
    )
    answer = envelope["answer"]
    assert "requirement_type" not in answer["items"][0]
    assert "judge_type_views" not in answer
    assert not any("requirement_type" in note for note in answer["notes"])
    assert "requirement_type" not in judge.calls[0][1]

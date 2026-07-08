"""Offline tests for the M2 alignment pipeline (DEC-05, DEC-06 partial).

Uses FakeClient only: no network, no keys. Verifies the hard invariants:
schema-valid reified assertions with evidence spans on both sides, judge
gating (never accepted without an accepting verdict), the mechanical quote
check (a bad quote never reaches the judge), corrected relation types,
skipping of non-accepted norms, zero-alignment answers, and a key-free
alignment log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tere4ai.align_hleg_altai.pipeline import MECHANICAL_JUDGE_MODEL, align_norms
from tere4ai.extract_norms.model_clients import FakeClient

REPO_ROOT = Path(__file__).resolve().parents[2]
ALIGNMENTS_SCHEMA = json.loads(
    (REPO_ROOT / "schema" / "json_schemas" / "alignments.schema.json").read_text(
        encoding="utf-8"
    )
)
ALIGNMENTS_VALIDATOR = Draft202012Validator(ALIGNMENTS_SCHEMA)

NORM_ID = "norm:eu-ai-act:article-99:paragraph-1:n1"
ROBUSTNESS_ID = "hleg:technical-robustness-and-safety"
TRANSPARENCY_ID = "hleg:transparency"

SOURCE_TEXT = (
    "1. A risk log shall be kept and maintained for high-risk AI systems, "
    "so that failures can be traced and corrected."
)


def _norm(**overrides) -> dict:
    norm = {
        "norm_id": NORM_ID,
        "layer": 2,
        "type": "NormativeStatement",
        "source_node_id": "eu-ai-act:article-99:paragraph-1",
        "source_span_id": "span:099.001",
        "deontic_type": "obligation",
        "modal": "shall",
        "actor_explicit": None,
        "actor_inferred": "provider",
        "actor_inference_source_node_id": "eu-ai-act:article-16",
        "action": "keep and maintain",
        "object": "a risk log",
        "target_system_category": "high_risk",
        "conditions": ["for high-risk AI systems"],
        "exceptions": [],
        "condition_ids": [],
        "exception_ids": [],
        "lifecycle_phase_ids": ["operation_monitoring"],
        "extraction_method": "llm_extract_v1",
        "extractor_model": "fake-generator",
        "extractor_prompt_version": "v1",
        "confidence": 0.9,
        "judge_verdict": "accepted",
        "judge_run_id": "judgerun:extraction:eu-ai-act:article-99:paragraph-1:n1",
        "review_status": "accepted",
        "source_text": SOURCE_TEXT,
    }
    norm.update(overrides)
    return norm


HLEG_NODES = [
    {
        "id": ROBUSTNESS_ID,
        "type": "HLEGRequirement",
        "layer": 3,
        "order": 2,
        "name": "Technical robustness and safety",
        "description": (
            "Technical robustness requires that AI systems be developed with a "
            "preventative approach to risks, with resilience and fallback plans, "
            "so that unintentional harm can be minimised and traced."
        ),
        "source_span": {"span_id": "span:hleg:req2"},
    },
    {
        "id": TRANSPARENCY_ID,
        "type": "HLEGRequirement",
        "layer": 3,
        "order": 4,
        "name": "Transparency",
        "description": (
            "This requirement encompasses traceability, explainability and "
            "communication: the data sets and processes that yield the AI "
            "system's decision should be documented to allow for traceability."
        ),
        "source_span": {"span_id": "span:hleg:req4"},
    },
]

SCORES = {
    "semantic_similarity": 0.8,
    "normative_relevance": 0.9,
    "operational_utility": 0.7,
    "evidence_strength": 0.85,
    "judge_confidence": 0.9,
}


def _generator_answer(**candidate_overrides) -> str:
    candidate = {
        "target_id": ROBUSTNESS_ID,
        "relation_type": "supports",
        "source_quote": "A risk log shall be kept and maintained",
        "target_quote": "preventative approach to risks",
        "rationale": "A kept risk log serves the preventative approach to risks.",
    }
    candidate.update(candidate_overrides)
    return json.dumps({"alignments": [candidate]})


def _judge_answer(verdict="accepted", corrected=None, rationale="Both quotes ground the relation."):
    return json.dumps(
        {
            "verdict": verdict,
            "corrected_relation_type": corrected,
            "scores": SCORES,
            "rationale": rationale,
        }
    )


def run_pipeline(generator_script, judge_script, norms, tmp_path):
    generator = FakeClient(generator_script, model="fake-generator")
    judge = FakeClient(judge_script, model="fake-judge")
    log_path = tmp_path / "alignment_log.jsonl"
    result = align_norms(
        norms,
        HLEG_NODES,
        generator,
        judge,
        prompt_version="v1",
        log_path=log_path,
        build_id="build-test",
    )
    return result, generator, judge, log_path


def test_accept_flow_yields_schema_valid_assertion_with_both_evidence_sides(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path
    )
    assert len(result["assertions"]) == 1
    assertion = result["assertions"][0]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert assertion["id"] == (
        "align:eu-ai-act:article-99:paragraph-1:n1:technical-robustness-and-safety:1"
    )
    assert assertion["type"] == "AlignmentAssertion"
    assert assertion["source_norm_id"] == NORM_ID
    assert assertion["target_id"] == ROBUSTNESS_ID
    assert assertion["relation_type"] == "supports"
    assert assertion["source_evidence_span_ids"] == ["span:099.001"]
    assert assertion["target_evidence_span_ids"] == ["span:hleg:req2"]
    assert assertion["judge_verdict"] == "accepted"
    assert assertion["review_status"] == "accepted"
    assert assertion["final_score"] == pytest.approx(sum(SCORES.values()) / 5)
    assert result["stats"]["verdicts"]["accepted"] == 1


def test_one_mapping_run_per_invocation_referenced_by_assertions(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path
    )
    assert len(result["mapping_runs"]) == 1
    run = result["mapping_runs"][0]
    ALIGNMENTS_VALIDATOR.validate(run)
    assert run["type"] == "MappingRun"
    assert run["generator_model"] == "fake-generator"
    assert run["prompt_version"] == "v1"
    assert run["build_id"] == "build-test"
    assert result["assertions"][0]["mapping_run_id"] == run["id"]


def test_judge_run_shape_and_mapping_kind(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path
    )
    assert len(result["judge_runs"]) == 1
    run = result["judge_runs"][0]
    ALIGNMENTS_VALIDATOR.validate(run)
    assert run["judge_kind"] == "mapping"
    assert run["judge_model"] == "fake-judge"
    assert run["verdict"] == "accepted"
    assert run["build_id"] == "build-test"
    assert result["assertions"][0]["judge_run_id"] == run["id"]


def test_judge_rejection_yields_needs_review_never_accepted(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: _judge_answer(verdict="rejected", rationale="Rationale imports outside concepts.")},
        [_norm()],
        tmp_path,
    )
    assert len(result["assertions"]) == 1
    assertion = result["assertions"][0]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert assertion["judge_verdict"] == "rejected"
    assert assertion["review_status"] == "needs_review"
    assert assertion["review_status"] not in ("accepted", "auto_accepted")
    assert result["stats"]["verdicts"]["rejected"] == 1
    assert result["stats"]["verdicts"]["accepted"] == 0


def test_zero_alignment_answer_is_valid(tmp_path):
    result, _, judge, _ = run_pipeline(
        {NORM_ID: json.dumps({"alignments": []})}, {}, [_norm()], tmp_path
    )
    assert result["assertions"] == []
    assert result["judge_runs"] == []
    assert judge.calls == []
    assert result["stats"]["zero_alignment_norms"] == 1
    assert result["stats"]["candidates"] == 0


def test_mechanical_quote_check_bad_quote_never_reaches_judge(tmp_path):
    result, _, judge, _ = run_pipeline(
        {NORM_ID: _generator_answer(source_quote="this fragment is not in the norm text")},
        {},
        [_norm()],
        tmp_path,
    )
    assert judge.calls == []  # the judge FakeClient was never called
    assert result["assertions"] == []
    assert len(result["judge_runs"]) == 1
    run = result["judge_runs"][0]
    ALIGNMENTS_VALIDATOR.validate(run)
    assert run["judge_model"] == MECHANICAL_JUDGE_MODEL
    assert run["judge_model"] == "mechanical:quote_check"
    assert run["judge_kind"] == "mapping"
    assert run["verdict"] == "rejected"
    assert run["review_status"] == "rejected"
    assert run["rationale"] == "quote not found in source"
    assert len(result["stats"]["mechanical_rejects"]) == 1
    assert result["stats"]["mechanical_rejects"][0]["source_quote_found"] is False


def test_mechanical_quote_check_bad_target_quote_also_rejected(tmp_path):
    result, _, judge, _ = run_pipeline(
        {NORM_ID: _generator_answer(target_quote="an invented ethics fragment")},
        {},
        [_norm()],
        tmp_path,
    )
    assert judge.calls == []
    assert result["assertions"] == []
    assert result["judge_runs"][0]["judge_model"] == "mechanical:quote_check"
    assert result["stats"]["mechanical_rejects"][0]["target_quote_found"] is False


def test_whitespace_normalised_quote_passes_mechanical_check(tmp_path):
    result, _, judge, _ = run_pipeline(
        {NORM_ID: _generator_answer(source_quote="A risk log  shall\nbe kept and maintained")},
        {ROBUSTNESS_ID: _judge_answer()},
        [_norm()],
        tmp_path,
    )
    assert len(judge.calls) == 1
    assert len(result["assertions"]) == 1


def test_corrected_relation_type_overrides_proposed(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer(relation_type="directly_operationalizes")},
        {ROBUSTNESS_ID: _judge_answer(corrected="partially_operationalizes")},
        [_norm()],
        tmp_path,
    )
    assertion = result["assertions"][0]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert assertion["relation_type"] == "partially_operationalizes"
    assert result["judge_runs"][0]["corrected_relation_type"] == "partially_operationalizes"


def test_non_accepted_input_norms_are_skipped(tmp_path):
    rejected = _norm(
        norm_id="norm:eu-ai-act:article-99:paragraph-1:n2",
        judge_verdict="rejected",
        review_status="needs_review",
    )
    result, generator, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: _judge_answer()},
        [_norm(), rejected],
        tmp_path,
    )
    assert len(generator.calls) == 1  # no generator call for the rejected norm
    assert result["stats"]["norms_skipped_not_accepted"] == 1
    assert len(result["assertions"]) == 1
    assert result["assertions"][0]["source_norm_id"] == NORM_ID


def test_unknown_target_id_is_recorded_and_dropped(tmp_path):
    result, _, judge, _ = run_pipeline(
        {NORM_ID: _generator_answer(target_id="hleg:an-invented-eighth-requirement")},
        {},
        [_norm()],
        tmp_path,
    )
    assert judge.calls == []
    assert result["assertions"] == []
    assert result["judge_runs"] == []
    assert len(result["stats"]["invalid_candidates"]) == 1
    assert "unknown target_id" in result["stats"]["invalid_candidates"][0]["reason"]


def test_unusable_judge_response_defaults_to_human_review_never_accepted(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: ["%%%", "%%%"]},
        [_norm()],
        tmp_path,
    )
    assert len(result["assertions"]) == 1
    assertion = result["assertions"][0]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert assertion["judge_verdict"] == "needs_human_review"
    assert assertion["review_status"] == "needs_review"
    assert assertion["final_score"] == 0.0


def test_every_produced_assertion_validates_against_alignments_schema(tmp_path):
    two_candidates = json.dumps(
        {
            "alignments": [
                json.loads(_generator_answer())["alignments"][0],
                {
                    "target_id": TRANSPARENCY_ID,
                    "relation_type": "related_to",
                    "source_quote": "so that failures can be traced",
                    "target_quote": "to allow for traceability",
                    "rationale": "Tracing failures relates to traceability.",
                },
            ]
        }
    )
    result, _, _, _ = run_pipeline(
        {NORM_ID: two_candidates},
        {ROBUSTNESS_ID: _judge_answer(), TRANSPARENCY_ID: _judge_answer(verdict="needs_human_review")},
        [_norm()],
        tmp_path,
    )
    assert len(result["assertions"]) == 2
    for assertion in result["assertions"]:
        ALIGNMENTS_VALIDATOR.validate(assertion)
        assert assertion["source_evidence_span_ids"]
        assert assertion["target_evidence_span_ids"]
        if assertion["judge_verdict"] != "accepted":
            assert assertion["review_status"] != "accepted"


def test_alignment_log_written_with_no_key_material(tmp_path):
    _, _, _, log_path = run_pipeline(
        {NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path
    )
    assert log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(lines) == 2
    assert {line["direction"] for line in lines} == {"generator", "judge"}
    for line in lines:
        assert line["norm_id"] == NORM_ID
        assert line["prompt_version"] == "v1"
        assert len(line["input_sha256"]) == 64
        assert line["model"] in ("fake-generator", "fake-judge")
    judge_line = next(line for line in lines if line["direction"] == "judge")
    assert judge_line["verdict"] == "accepted"
    assert judge_line["target_id"] == ROBUSTNESS_ID
    assert judge_line["rationale"]
    raw = log_path.read_text()
    for secret_marker in ("sk-", "api_key", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert secret_marker not in raw
    # no full prompts in the log: system prompt phrases must not appear
    assert "alignment generator for TERE4AI" not in raw
    assert "build-time mapping judge" not in raw


def test_mechanical_reject_is_logged(tmp_path):
    _, _, _, log_path = run_pipeline(
        {NORM_ID: _generator_answer(source_quote="not in the text at all")},
        {},
        [_norm()],
        tmp_path,
    )
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    mechanical = [line for line in lines if line["direction"] == "mechanical"]
    assert len(mechanical) == 1
    assert mechanical[0]["model"] == "mechanical:quote_check"
    assert mechanical[0]["verdict"] == "rejected"
    assert mechanical[0]["rationale"] == "quote not found in source"


def test_norm_without_source_text_is_recorded_failed(tmp_path):
    norm = _norm()
    del norm["source_text"]
    result, generator, _, _ = run_pipeline({}, {}, [norm], tmp_path)
    assert generator.calls == []
    assert result["assertions"] == []
    assert len(result["stats"]["norms_failed"]) == 1
    assert result["stats"]["norms_failed"][0]["reason"] == "missing source_text"

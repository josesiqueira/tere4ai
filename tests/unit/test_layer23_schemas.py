"""Layer 2/3 schema contract tests (architecture.md Sections 3 and 4).

The schemas are the machine-readable source of truth (Section 2); these tests
pin the invariants that the M2 extraction and judge pipelines build against.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError, validate

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schema" / "json_schemas"

norms_schema = json.loads((SCHEMAS / "norms.schema.json").read_text(encoding="utf-8"))
align_schema = json.loads((SCHEMAS / "alignments.schema.json").read_text(encoding="utf-8"))


def _valid_norm():
    return {
        "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
        "layer": 2,
        "type": "NormativeStatement",
        "source_node_id": "eu-ai-act:article-9:paragraph-1",
        "source_span_id": "span:009.001",
        "deontic_type": "obligation",
        "modal": "shall",
        "actor_explicit": None,
        "actor_inferred": "provider",
        "actor_inference_source_node_id": "eu-ai-act:article-16",
        "action": "establish, implement, document and maintain",
        "object": "a risk management system",
        "target_system_category": "high_risk",
        "condition_ids": [],
        "exception_ids": [],
        "lifecycle_phase_ids": ["cross_phase"],
        "required_artifact_ids": [],
        "evidence_expectation_ids": [],
        "extraction_method": "llm_extract_v1",
        "extractor_model": "test-model-pinned",
        "confidence": 0.9,
        "judge_verdict": "pending",
        "review_status": "needs_review",
    }


def test_valid_norm_passes():
    validate(_valid_norm(), norms_schema)


def test_inferred_actor_requires_inference_source():
    norm = _valid_norm()
    norm.pop("actor_inference_source_node_id")
    with pytest.raises(ValidationError):
        validate(norm, norms_schema)


def test_norm_requires_source_span_and_judge_verdict():
    for missing in ("source_span_id", "judge_verdict", "extractor_model"):
        norm = _valid_norm()
        norm.pop(missing)
        with pytest.raises(ValidationError):
            validate(norm, norms_schema)


def test_hleg_ids_are_a_closed_set():
    hleg = {
        "id": "hleg:transparency",
        "type": "HLEGRequirement",
        "layer": 3,
        "order": 4,
        "name": "Transparency",
    }
    validate(hleg, align_schema)
    hleg["id"] = "hleg:some-invented-principle"
    with pytest.raises(ValidationError):
        validate(hleg, align_schema)


def test_alignment_requires_evidence_spans_on_both_sides():
    assertion = {
        "id": "align:norm-9-1-n1:hleg-technical-robustness:1",
        "type": "AlignmentAssertion",
        "layer": 3,
        "source_norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
        "target_id": "hleg:technical-robustness-and-safety",
        "relation_type": "directly_operationalizes",
        "source_evidence_span_ids": ["span:009.001"],
        "target_evidence_span_ids": ["span:hleg:req2"],
        "final_score": 0.8,
        "mapping_run_id": "mappingrun:b1:1",
        "judge_run_id": "judgerun:b1:1",
        "judge_verdict": "accepted",
        "review_status": "accepted",
    }
    validate(assertion, align_schema)
    for side in ("source_evidence_span_ids", "target_evidence_span_ids"):
        broken = dict(assertion)
        broken[side] = []
        with pytest.raises(ValidationError):
            validate(broken, align_schema)


def test_judge_run_requires_rationale_and_model():
    run = {
        "id": "judgerun:b1:1",
        "type": "JudgeRun",
        "layer": 3,
        "judge_kind": "mapping",
        "judge_model": "test-judge-pinned",
        "prompt_version": "v1",
        "verdict": "accepted",
        "rationale": "target concepts present in both spans",
        "started_at": "2026-07-08T00:00:00Z",
        "build_id": "build-test",
    }
    validate(run, align_schema)
    for missing in ("rationale", "judge_model"):
        broken = dict(run)
        broken.pop(missing)
        with pytest.raises(ValidationError):
            validate(broken, align_schema)


def test_schemas_are_valid_draft_2020_12():
    Draft202012Validator.check_schema(norms_schema)
    Draft202012Validator.check_schema(align_schema)

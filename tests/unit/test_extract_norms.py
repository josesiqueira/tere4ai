"""Offline tests for the M2 norm-extraction pipeline (DEC-03, DEC-06 partial).

Uses FakeClient only: no network, no keys. Verifies the hard invariants:
schema-valid output, judge gating (never accepted without an accepting
verdict), retry-then-record on malformed generator JSON, the recital guard,
source_span_id and judge_verdict on every norm, and a key-free extraction log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.pipeline import expand_source_units, extract_norms

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMS_SCHEMA = json.loads(
    (REPO_ROOT / "schema" / "json_schemas" / "norms.schema.json").read_text(encoding="utf-8")
)
NORM_VALIDATOR = Draft202012Validator(NORMS_SCHEMA)

PARA_ID = "eu-ai-act:article-99:paragraph-1"
POINT_ID = "eu-ai-act:article-99:paragraph-2:point-a"
RECITAL_ID = "eu-ai-act:recital-7"


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
            "id": "eu-ai-act:article-99",
            "layer": 1,
            "type": "Article",
            "number": 99,
            "title": "Fake risk duties",
            "source_span": _span("art_99"),
        },
        {
            "id": PARA_ID,
            "layer": 1,
            "type": "Paragraph",
            "index": 1,
            "text": "1. A risk log shall be kept for high-risk AI systems.",
            "source_span": _span("099.001"),
        },
        {
            "id": POINT_ID,
            "layer": 1,
            "type": "Point",
            "marker": "a",
            "text": "the provider shall notify the authority, unless exempted;",
            "source_span": _span("099.002.a"),
        },
        {
            "id": RECITAL_ID,
            "layer": 1,
            "type": "Recital",
            "number": 7,
            "text": "(7) Recitals give context only.",
            "binding": False,
            "source_span": _span("rct_7"),
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
                "actor_explicit": None,
                "actor_inferred": "provider",
                "actor_inference_source_node_id": "eu-ai-act:article-16",
                "action": "keep",
                "object": "a risk log",
                "target_system_category": "high_risk",
                "conditions": ["for high-risk AI systems"],
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
        "rationale": "The source text supports the obligation verbatim.",
    }
)

JUDGE_REJECT = json.dumps(
    {
        "verdict": "rejected",
        "scores": {
            "semantic_similarity": 0.2,
            "normative_relevance": 0.3,
            "operational_utility": 0.1,
            "evidence_strength": 0.1,
            "judge_confidence": 0.9,
        },
        "rationale": "The actor is invented; the text names no provider.",
    }
)


def run_pipeline(generator_script, judge_script, node_ids, tmp_path):
    generator = FakeClient(generator_script, model="fake-generator")
    judge = FakeClient(judge_script, model="fake-judge")
    log_path = tmp_path / "extraction_log.jsonl"
    result = extract_norms(
        FAKE_DUMP, node_ids, generator, judge, prompt_version="v1", log_path=log_path
    )
    return result, log_path


def test_accepted_flow_yields_schema_valid_accepted_norms(tmp_path):
    result, _ = run_pipeline(
        {PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, [PARA_ID], tmp_path
    )
    assert len(result["norms"]) == 1
    norm = result["norms"][0]
    NORM_VALIDATOR.validate(norm)
    assert norm["norm_id"] == f"norm:{PARA_ID}:n1"
    assert norm["review_status"] == "accepted"
    assert norm["judge_verdict"] == "accepted"
    assert norm["confidence"] == pytest.approx(0.88)
    assert norm["extractor_model"] == "fake-generator"
    assert norm["extraction_method"] == "llm_extract_v1"
    assert result["stats"]["verdicts"]["accepted"] == 1


def test_judge_run_shape_and_extraction_kind(tmp_path):
    result, _ = run_pipeline(
        {PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, [PARA_ID], tmp_path
    )
    assert len(result["judge_runs"]) == 1
    run = result["judge_runs"][0]
    assert run["type"] == "JudgeRun"
    assert run["judge_kind"] == "extraction"
    assert run["judge_model"] == "fake-judge"
    assert run["prompt_version"] == "v1"
    assert run["verdict"] == "accepted"
    assert run["rationale"]
    assert run["build_id"] == "build-test"
    assert set(run["scores"]) == {
        "semantic_similarity",
        "normative_relevance",
        "operational_utility",
        "evidence_strength",
        "judge_confidence",
    }
    assert result["norms"][0]["judge_run_id"] == run["id"]


def test_judge_rejection_never_reaches_accepted(tmp_path):
    result, _ = run_pipeline(
        {PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_REJECT}, [PARA_ID], tmp_path
    )
    assert len(result["norms"]) == 1
    norm = result["norms"][0]
    NORM_VALIDATOR.validate(norm)
    assert norm["judge_verdict"] == "rejected"
    assert norm["review_status"] == "needs_review"
    assert norm["review_status"] not in ("accepted", "auto_accepted")
    assert result["stats"]["verdicts"]["rejected"] == 1
    assert result["stats"]["verdicts"]["accepted"] == 0


def test_malformed_generator_json_retries_once_then_records_failure(tmp_path):
    generator = FakeClient({PARA_ID: ["not json {", "still not json"]}, model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    log_path = tmp_path / "extraction_log.jsonl"
    result = extract_norms(
        FAKE_DUMP, [PARA_ID], generator, judge, prompt_version="v1", log_path=log_path
    )
    assert result["norms"] == []
    assert result["judge_runs"] == []
    assert len(generator.calls) == 2  # exactly one retry
    assert len(result["stats"]["nodes_failed"]) == 1
    assert result["stats"]["nodes_failed"][0]["node_id"] == PARA_ID
    assert "unparseable" in result["stats"]["nodes_failed"][0]["reason"]


def test_malformed_then_valid_generator_json_recovers_on_retry(tmp_path):
    generator = FakeClient(
        {PARA_ID: ["not json {", GENERATOR_ANSWER]}, model="fake-generator"
    )
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    result = extract_norms(
        FAKE_DUMP,
        [PARA_ID],
        generator,
        judge,
        prompt_version="v1",
        log_path=tmp_path / "log.jsonl",
    )
    assert len(result["norms"]) == 1
    assert result["stats"]["nodes_failed"] == []


def test_recital_node_id_raises(tmp_path):
    generator = FakeClient({}, model="fake-generator")
    judge = FakeClient({}, model="fake-judge")
    with pytest.raises(ValueError, match="never extraction sources"):
        extract_norms(
            FAKE_DUMP,
            [RECITAL_ID],
            generator,
            judge,
            log_path=tmp_path / "log.jsonl",
        )
    with pytest.raises(ValueError, match="never extraction sources"):
        expand_source_units(FAKE_DUMP, [RECITAL_ID])


def test_article_expands_to_paragraphs_and_points(tmp_path):
    units = expand_source_units(FAKE_DUMP, ["eu-ai-act:article-99"])
    assert [unit["node_id"] for unit in units] == [PARA_ID, POINT_ID]
    assert all(unit["span_id"] for unit in units)
    assert units[0]["article_context"].startswith("Article 99")


def test_every_norm_has_source_span_and_judge_verdict(tmp_path):
    result, _ = run_pipeline(
        {PARA_ID: GENERATOR_ANSWER, POINT_ID: GENERATOR_ANSWER},
        {PARA_ID: JUDGE_ACCEPT, POINT_ID: JUDGE_REJECT},
        ["eu-ai-act:article-99"],
        tmp_path,
    )
    assert len(result["norms"]) == 2
    for norm in result["norms"]:
        NORM_VALIDATOR.validate(norm)
        assert norm["source_span_id"].startswith("span:")
        assert norm["judge_verdict"] in ("accepted", "rejected", "needs_human_review")
        assert norm["judge_run_id"]
        if norm["judge_verdict"] != "accepted":
            assert norm["review_status"] != "accepted"


def test_unusable_judge_response_defaults_to_human_review_never_accepted(tmp_path):
    generator = FakeClient({PARA_ID: GENERATOR_ANSWER}, model="fake-generator")
    judge = FakeClient({PARA_ID: ["%%%", "%%%"]}, model="fake-judge")
    result = extract_norms(
        FAKE_DUMP,
        [PARA_ID],
        generator,
        judge,
        log_path=tmp_path / "log.jsonl",
    )
    assert len(result["norms"]) == 1
    norm = result["norms"][0]
    assert norm["judge_verdict"] == "needs_human_review"
    assert norm["review_status"] == "needs_review"
    assert norm["confidence"] == 0.0


def test_extraction_log_written_with_no_key_material(tmp_path):
    _, log_path = run_pipeline(
        {PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, [PARA_ID], tmp_path
    )
    assert log_path.exists()
    lines = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(lines) == 2
    directions = {line["direction"] for line in lines}
    assert directions == {"generator", "judge"}
    for line in lines:
        assert line["node_id"] == PARA_ID
        assert line["prompt_version"] == "v1"
        assert len(line["input_sha256"]) == 64
        assert line["model"] in ("fake-generator", "fake-judge")
    judge_line = next(line for line in lines if line["direction"] == "judge")
    assert judge_line["verdict"] == "accepted"
    assert judge_line["rationale"]
    raw = log_path.read_text()
    for secret_marker in ("sk-", "api_key", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert secret_marker not in raw
    # no full prompts in the log: the system prompt text must not appear
    assert "Institutional Grammar" not in raw


def test_unknown_node_id_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown node id"):
        expand_source_units(FAKE_DUMP, ["eu-ai-act:article-404"])

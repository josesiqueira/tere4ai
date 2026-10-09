"""Offline tests for the MILESTONE2 norm-extraction pipeline (DEC-03, DEC-06 partial).

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
from tere4ai.extract_norms.pipeline import (
    DEFAULT_PROMPT_VERSION,
    _inference_source_block,
    expand_source_units,
    extract_norms,
    judge_inference_block,
    load_prompt,
)
from tere4ai.extract_norms.requirement_type import DEFINITIONS_TEXT, SCOPE_TEXT

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
    assert run["judge_effort"] == "not configured"  # FakeClient declares no effort; a real client carries its declared one
    assert run["judge_temperature"] == "not configured"
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


def test_judge_run_records_the_judge_effort_when_the_client_declares_one(tmp_path):
    generator = FakeClient({PARA_ID: GENERATOR_ANSWER}, model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    judge.effort = "xhigh"
    log_path = tmp_path / "extraction_log.jsonl"
    result = extract_norms(
        FAKE_DUMP, [PARA_ID], generator, judge, prompt_version="v1", log_path=log_path
    )
    run = result["judge_runs"][0]
    assert run["judge_effort"] == "xhigh"


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


def test_judge_run_records_the_declared_judge_temperature(tmp_path):
    """B99 (spec F D-F29): every JudgeRun names the temperature as declared."""
    generator = FakeClient({PARA_ID: GENERATOR_ANSWER}, model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    judge.effort, judge.temperature = "xhigh", "N/A"
    result = extract_norms(FAKE_DUMP, [PARA_ID], generator, judge, prompt_version="v1",
                           log_path=tmp_path / "extraction_log.jsonl")
    run = result["judge_runs"][0]
    assert (run["judge_effort"], run["judge_temperature"]) == ("xhigh", "N/A")


# DEC-19, B65: from prompt v2 on, every norm carries its requirement type,
# scoped in code, and the judge's view of it beside a verdict it never
# changes; a v1 run keeps its old input and output (ruling 49).


def _generator_with(**overrides):
    norm = json.loads(GENERATOR_ANSWER)["norms"][0]
    norm.update(overrides)
    return json.dumps({"norms": [norm]})


def _judge_with(verdict_json, **view):
    reply = json.loads(verdict_json)
    reply.update(view)
    return json.dumps(reply)


def run_v2(generator_script, judge_script, tmp_path, dump=FAKE_DUMP):
    generator = FakeClient(generator_script, model="fake-generator")
    judge = FakeClient(judge_script, model="fake-judge")
    log_path = tmp_path / "extraction_log.jsonl"
    result = extract_norms(dump, [PARA_ID], generator, judge, prompt_version="v2", log_path=log_path)
    return result, judge, log_path


def test_an_in_scope_norm_keeps_the_extractors_type_and_the_judges_agreement(tmp_path):
    result, _, log_path = run_v2(
        {PARA_ID: _generator_with(requirement_type="process")},
        {PARA_ID: _judge_with(JUDGE_ACCEPT, requirement_type_agrees=True, requirement_type=None)},
        tmp_path,
    )
    norm = result["norms"][0]
    NORM_VALIDATOR.validate(norm)
    assert norm["requirement_type"] == "process"
    assert (norm["judge_type_agrees"], norm["judge_requirement_type"]) == (True, "process")
    run = result["judge_runs"][0]
    assert (run["judge_type_agrees"], run["judge_requirement_type"]) == (True, "process")
    judge_line = [json.loads(x) for x in log_path.read_text().splitlines()][-1]
    assert judge_line["judge_requirement_type"] == "process"
    assert result["stats"]["untyped_in_scope"] == 0


def test_a_judge_that_disagrees_on_the_type_keeps_its_verdict(tmp_path):
    """Jose, 2026-10-01: "Record, do not gate (Recommended)"."""
    result, _, _ = run_v2(
        {PARA_ID: _generator_with(requirement_type="process")},
        {PARA_ID: _judge_with(JUDGE_ACCEPT, requirement_type_agrees=False, requirement_type="functional")},
        tmp_path,
    )
    norm = result["norms"][0]
    assert norm["judge_verdict"] == "accepted" and norm["review_status"] == "accepted"
    assert norm["requirement_type"] == "process"
    assert (norm["judge_type_agrees"], norm["judge_requirement_type"]) == (False, "functional")
    assert result["stats"]["verdicts"]["accepted"] == 1


def test_a_judge_reply_without_the_view_keeps_its_verdict_and_records_null(tmp_path):
    result, _, _ = run_v2({PARA_ID: _generator_with(requirement_type="quality")}, {PARA_ID: JUDGE_REJECT}, tmp_path)
    norm = result["norms"][0]
    assert norm["judge_verdict"] == "rejected"
    assert norm["requirement_type"] == "quality"
    assert norm["judge_type_agrees"] is None and norm["judge_requirement_type"] is None


def test_a_missing_or_invalid_type_is_null_and_the_norm_is_never_dropped(tmp_path):
    """DEC-19: the field is nullable, so an extractor reply that omits it or
    gives a value outside the three is kept with null (today a schema
    failure would drop the norm), and the in-scope gap is counted (ruling 54)."""
    for generator_answer in (GENERATOR_ANSWER, _generator_with(requirement_type="non-functional")):
        result, _, _ = run_v2({PARA_ID: generator_answer}, {PARA_ID: JUDGE_ACCEPT}, tmp_path)
        assert result["stats"]["invalid_norms"] == []
        norm = result["norms"][0]
        NORM_VALIDATOR.validate(norm)
        assert norm["requirement_type"] is None
        assert result["stats"]["untyped_in_scope"] == 1


def test_outside_the_scope_the_type_is_null_and_the_judge_records_nothing(tmp_path):
    """A permission carries no type whatever the extractor proposed, the
    judge's agreement on it is not recorded (DEC-19), and it is not counted
    as untyped."""
    result, judge, _ = run_v2(
        {PARA_ID: _generator_with(deontic_type="permission", modal="may", requirement_type="functional")},
        {PARA_ID: _judge_with(JUDGE_ACCEPT, requirement_type_agrees=True)},
        tmp_path,
    )
    norm = result["norms"][0]
    assert norm["requirement_type"] is None
    assert norm["judge_type_agrees"] is None and norm["judge_requirement_type"] is None
    assert result["stats"]["untyped_in_scope"] == 0
    # The judge saw the scoped candidate, never the discarded type.
    assert '"requirement_type": null' in judge.calls[0][1]


def test_a_v1_run_keeps_its_old_input_and_output(tmp_path):
    """Review I1 (ruling 49): under v1 the extractor's type is not kept, the
    judge's input carries no type and no inference text, and the norm, the
    judge run, the log and the stats gain no type field."""
    generator = FakeClient({PARA_ID: _generator_with(requirement_type="process")}, model="fake-generator")
    judge = FakeClient({PARA_ID: _judge_with(JUDGE_ACCEPT, requirement_type_agrees=True)}, model="fake-judge")
    log_path = tmp_path / "log.jsonl"
    result = extract_norms(FAKE_DUMP, [PARA_ID], generator, judge, prompt_version="v1", log_path=log_path)
    assert "requirement_type" not in judge.calls[0][1]
    assert "Actor-inference source" not in judge.calls[0][1]
    norm, run = result["norms"][0], result["judge_runs"][0]
    for field in ("requirement_type", "judge_type_agrees", "judge_requirement_type"):
        assert field not in norm and field not in run
    assert "judge_type_agrees" not in [json.loads(x) for x in log_path.read_text().splitlines()][-1]
    assert "untyped_in_scope" not in result["stats"]


# DEC-19 and thesis task B4 (folded into B65): extract_norms v2 and
# judge_norms v2 carry the one definitions text and the scope; the judge's
# input carries the verbatim text of the actor-inference source.

ARTICLE_16_PARA = "eu-ai-act:article-16:paragraph-1"
B4_DUMP = {
    "build": {"build_id": "build-test"},
    "nodes": FAKE_DUMP["nodes"] + [
        {"id": "eu-ai-act:article-16", "layer": 1, "type": "Article", "number": 16,
         "title": "Obligations of providers of high-risk AI systems", "source_span": _span("art_16")},
        {"id": ARTICLE_16_PARA, "layer": 1, "type": "Paragraph", "index": 1,
         "text": "Providers of high-risk AI systems shall keep the risk log.", "source_span": _span("016.001")},
    ],
    "edges": [],
}


def test_the_v2_prompts_carry_the_definitions_and_the_scope_verbatim():
    extract = load_prompt("extract_norms", "v2")
    judge = load_prompt("judge_norms", "v2")
    assert extract.startswith("# extract_norms system prompt, version v2")
    assert judge.startswith("# judge_norms system prompt, version v2")
    for prompt in (extract, judge):
        assert DEFINITIONS_TEXT in prompt
        assert SCOPE_TEXT in prompt
    assert '"requirement_type": "process"' in extract
    assert '"requirement_type_agrees": true' in judge  # the example shows agreement
    assert "never a reason" in judge  # recorded, never gating (DEC-19)
    assert "serves check 3 only" in judge  # the inference text feeds the actor check alone
    # v1 is kept unchanged for reading old records
    assert "requirement_type" not in load_prompt("judge_norms", "v1")


def test_extraction_defaults_to_the_v4_prompts(tmp_path):
    assert DEFAULT_PROMPT_VERSION == "v4"
    generator = FakeClient({PARA_ID: GENERATOR_ANSWER}, model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    result = extract_norms(FAKE_DUMP, [PARA_ID], generator, judge, log_path=tmp_path / "log.jsonl")
    assert generator.calls[0][0].startswith("# extract_norms system prompt, version v4")
    assert judge.calls[0][0].startswith("# judge_norms system prompt, version v4")
    assert result["norms"][0]["extractor_prompt_version"] == "v4"
    assert result["judge_runs"][0]["prompt_version"] == "v4"


def test_the_v2_judge_receives_the_actor_inference_source_text(tmp_path):
    """B4 (Jose, 2026-09-30: "Fix before B74"): an actor inferred via
    Article 16 is judged against Article 16's own words."""
    _, judge, _ = run_v2({PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, tmp_path, dump=B4_DUMP)
    user = judge.calls[0][1]
    assert "Actor-inference source: eu-ai-act:article-16 (Article)" in user
    assert f"[{ARTICLE_16_PARA}] Providers of high-risk AI systems shall keep the risk log." in user
    assert user.index("Actor-inference source") < user.index("Candidate norm (JSON)")


def test_an_explicit_actor_gets_no_inference_text(tmp_path):
    explicit = _generator_with(actor_explicit="provider", actor_inferred=None, actor_inference_source_node_id=None)
    _, judge, _ = run_v2({PARA_ID: explicit}, {PARA_ID: JUDGE_ACCEPT}, tmp_path, dump=B4_DUMP)
    assert "Actor-inference source: none (the candidate's actor is not inferred)." in judge.calls[0][1]


def test_an_inferred_actor_without_a_source_id_is_named_as_such(tmp_path):
    unsourced = _generator_with(actor_inference_source_node_id=None)
    _, judge, _ = run_v2({PARA_ID: unsourced}, {PARA_ID: JUDGE_ACCEPT}, tmp_path, dump=B4_DUMP)
    assert "Actor-inference source: none recorded (the candidate infers its actor" in judge.calls[0][1]


def test_an_inference_source_missing_from_the_dump_is_named_not_hidden(tmp_path):
    _, judge, _ = run_v2({PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, tmp_path)
    assert "Actor-inference source: eu-ai-act:article-16, not present in the graph dump (no text)." in judge.calls[0][1]


def test_an_article_source_lists_the_topmost_units_with_text_once():
    """Article 16 shape: paragraph 1 already contains points (a) and (b), so
    the points are not listed a second time."""
    dump = {"nodes": [
        {"id": "eu-ai-act:article-16", "type": "Article"},
        {"id": "eu-ai-act:article-16:paragraph-1", "type": "Paragraph",
         "text": "Providers shall: (a) ensure compliance; (b) indicate their name."},
        {"id": "eu-ai-act:article-16:paragraph-1:point-a", "type": "Point", "text": "(a) ensure compliance;"},
        {"id": "eu-ai-act:article-16:paragraph-1:point-b", "type": "Point", "text": "(b) indicate their name."},
        {"id": "eu-ai-act:article-16:paragraph-2", "type": "Paragraph", "text": "On request, providers demonstrate it."},
    ]}
    nodes = {n["id"]: n for n in dump["nodes"]}
    candidate = {"actor_inferred": "provider", "actor_inference_source_node_id": "eu-ai-act:article-16"}
    block = _inference_source_block(dump, nodes, {"node_id": "x"}, candidate)
    assert block.count("ensure compliance") == 1
    assert block.count("indicate their name") == 1
    assert "[eu-ai-act:article-16:paragraph-1]" in block
    assert "[eu-ai-act:article-16:paragraph-2]" in block
    assert "point-a" not in block


# DEC-21 (B124, spec G D-G62): target_system_category is set by rule from
# the norm's source Article or Annex under every prompt version; the model's
# label is never kept. Under v1 and v2 the judge still reads it (read and
# dropped); a norm on a unit outside the rule table carries null and is
# counted.


def test_the_rule_sets_the_category_and_drops_the_models_label_under_v1_and_v2(tmp_path):
    for version in ("v1", "v2"):
        generator = FakeClient({ARTICLE_16_PARA: GENERATOR_ANSWER}, model="fake-generator")
        judge = FakeClient({ARTICLE_16_PARA: JUDGE_ACCEPT}, model="fake-judge")
        result = extract_norms(B4_DUMP, [ARTICLE_16_PARA], generator, judge, prompt_version=version,
                               log_path=tmp_path / f"log-{version}.jsonl")
        norm = result["norms"][0]
        NORM_VALIDATOR.validate(norm)
        assert norm["target_system_category"] == "high_risk_ai_system", version
        # the judge reads the candidate the model wrote, as it always did
        assert '"target_system_category": "high_risk"' in judge.calls[0][1], version
        assert result["stats"]["without_target_system_category"] == 0


def test_a_unit_outside_the_rule_table_gets_null_and_is_counted(tmp_path):
    """Article 99 of the mock dump is not in the table: the model's
    "high_risk" is not kept and no value is guessed."""
    result, _ = run_pipeline({PARA_ID: GENERATOR_ANSWER}, {PARA_ID: JUDGE_ACCEPT}, [PARA_ID], tmp_path)
    norm = result["norms"][0]
    NORM_VALIDATOR.validate(norm)
    assert norm["target_system_category"] is None
    assert result["stats"]["without_target_system_category"] == 1


def test_the_v3_prompts_drop_the_field_and_keep_everything_else():
    """DEC-21 (B124, spec G D-G62): extract_norms v3 is v2 without the
    field's example key and vocabulary line; judge_norms v3 is v2 under a new
    version line (the two share one version); v3 was the default and the
    version of record from B124 until B144 (DEC-26)."""
    extract, judge = load_prompt("extract_norms", "v3"), load_prompt("judge_norms", "v3")
    assert extract == (
        load_prompt("extract_norms", "v2")
        .replace("# extract_norms system prompt, version v2", "# extract_norms system prompt, version v3", 1)
        .replace('      "target_system_category": "high_risk",\n', "")
        .replace('- target_system_category: a short label such as "high_risk", "gpai",\n'
                 '  "prohibited_practice", "any", or null when the text does not scope it.\n', "")
    )
    assert judge == load_prompt("judge_norms", "v2").replace(
        "# judge_norms system prompt, version v2", "# judge_norms system prompt, version v3", 1)
    for prompt in (extract, judge):
        assert "target_system_category" not in prompt
        assert DEFINITIONS_TEXT in prompt and SCOPE_TEXT in prompt


def test_under_v3_the_judge_never_sees_the_field_and_the_norm_takes_the_rule_value(tmp_path):
    """Review focus 1: a v3 extractor that writes a label unasked."""
    stray = _generator_with(target_system_category="gpai")
    generator = FakeClient({ARTICLE_16_PARA: stray}, model="fake-generator")
    judge = FakeClient({ARTICLE_16_PARA: JUDGE_ACCEPT}, model="fake-judge")
    result = extract_norms(B4_DUMP, [ARTICLE_16_PARA], generator, judge, prompt_version="v3",
                           log_path=tmp_path / "log.jsonl")
    assert "target_system_category" not in judge.calls[0][1]
    norm = result["norms"][0]
    NORM_VALIDATOR.validate(norm)
    assert norm["target_system_category"] == "high_risk_ai_system"


# B144 (DEC-26, spec G D-G76 (4)): from judge_norms v4 on, a Point given as
# the actor-inference source reaches the judge with the Paragraph that holds
# it; every other source, and every v1 to v3 run, keeps its input.

D3_POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"
D3_DUMP = {
    "build": {"build_id": "build-test"},
    "nodes": FAKE_DUMP["nodes"] + [
        {"id": "eu-ai-act:article-16", "layer": 1, "type": "Article", "number": 16,
         "title": "Obligations of providers of high-risk AI systems", "source_span": _span("art_16")},
        {"id": "eu-ai-act:article-16:paragraph-1", "layer": 1, "type": "Paragraph", "index": 1,
         "text": "Providers of high-risk AI systems shall: (a) ensure compliance with Section 2; (c) keep a system.",
         "source_span": _span("016.001")},
        {"id": D3_POINT_A, "layer": 1, "type": "Point", "marker": "a",
         "text": "ensure compliance with Section 2;", "source_span": _span("016.001.a")},
        {"id": "eu-ai-act:article-16:paragraph-1:point-a:point-i", "layer": 1, "type": "Point", "marker": "i",
         "text": "first indent;", "source_span": _span("016.001.a.i")},
        {"id": "eu-ai-act:article-16:paragraph-2", "layer": 1, "type": "Paragraph", "index": 2,
         "text": "2. Providers shall keep it.", "source_span": _span("016.002")},
        {"id": "eu-ai-act:article-16:paragraph-2:subparagraph-1", "layer": 1, "type": "Subparagraph",
         "text": "Providers shall keep it.", "source_span": _span("016.002.1")},
        {"id": "eu-ai-act:annex-iii", "layer": 1, "type": "Annex", "number": "III", "title": "Annex III",
         "source_span": _span("anx_iii")},
        {"id": "eu-ai-act:annex-iii:point-1:point-a", "layer": 1, "type": "Point", "marker": "a",
         "text": "remote biometric identification systems;", "source_span": _span("anx_iii.1.a")},
    ],
    "edges": [],
}
D3_PARAGRAPH = (
    "Verbatim text of the paragraph that holds it:\n"
    "[eu-ai-act:article-16:paragraph-1] Providers of high-risk AI systems shall: (a) ensure compliance with "
    "Section 2; (c) keep a system."
)


def _judge_input(tmp_path, version, source_id, dump=D3_DUMP):
    generator = FakeClient({PARA_ID: _generator_with(actor_inference_source_node_id=source_id)}, model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    extract_norms(dump, [PARA_ID], generator, judge, prompt_version=version, log_path=tmp_path / f"log-{version}.jsonl")
    return judge.calls[0][1]


def test_a_v4_judge_receives_the_paragraph_that_holds_a_point_source(tmp_path):
    user = _judge_input(tmp_path, "v4", D3_POINT_A)
    assert (
        f"Actor-inference source: {D3_POINT_A} (Point)\n"
        "Verbatim text of the actor-inference source:\n"
        f"[{D3_POINT_A}] ensure compliance with Section 2;\n"
        f"{D3_PARAGRAPH}\n\nCandidate norm (JSON):"
    ) in user


def test_a_v3_judge_keeps_the_point_text_alone(tmp_path):
    """The version gate: a v1 to v3 run keeps the input it had."""
    user = _judge_input(tmp_path, "v3", D3_POINT_A)
    assert f"[{D3_POINT_A}] ensure compliance with Section 2;\n\nCandidate norm (JSON):" in user
    assert "paragraph that holds it" not in user


def test_under_v4_a_paragraph_or_a_container_source_reaches_the_judge_as_under_v3(tmp_path):
    for source_id in ("eu-ai-act:article-16:paragraph-1", "eu-ai-act:article-16"):
        assert _judge_input(tmp_path, "v4", source_id) == _judge_input(tmp_path, "v3", source_id), source_id


def test_a_subparagraph_source_gets_no_paragraph_under_v4(tmp_path):
    """Only a Point is given its paragraph (R9): the type guard."""
    user = _judge_input(tmp_path, "v4", "eu-ai-act:article-16:paragraph-2:subparagraph-1")
    assert "[eu-ai-act:article-16:paragraph-2:subparagraph-1] Providers shall keep it.\n\nCandidate norm" in user
    assert "paragraph that holds it" not in user


def test_a_nested_point_gets_its_nearest_paragraph(tmp_path):
    user = _judge_input(tmp_path, "v4", "eu-ai-act:article-16:paragraph-1:point-a:point-i")
    assert f"[eu-ai-act:article-16:paragraph-1:point-a:point-i] first indent;\n{D3_PARAGRAPH}" in user


def test_a_point_without_a_paragraph_above_it_keeps_its_text_alone():
    nodes = {n["id"]: n for n in D3_DUMP["nodes"]}
    candidate = {"actor_inferred": "provider", "actor_inference_source_node_id": "eu-ai-act:annex-iii:point-1:point-a"}
    with_paragraph = _inference_source_block(D3_DUMP, nodes, {"node_id": PARA_ID}, candidate, paragraph_of_point=True)
    assert with_paragraph == _inference_source_block(D3_DUMP, nodes, {"node_id": PARA_ID}, candidate)
    assert with_paragraph.endswith("[eu-ai-act:annex-iii:point-1:point-a] remote biometric identification systems;")


def test_a_point_that_is_the_source_unit_itself_is_named_as_before():
    nodes = {n["id"]: n for n in D3_DUMP["nodes"]}
    candidate = {"actor_inferred": "unspecified_needs_review", "actor_inference_source_node_id": D3_POINT_A}
    block = judge_inference_block(D3_DUMP, nodes, {"node_id": D3_POINT_A}, candidate, "v4")
    assert block == f"Actor-inference source: {D3_POINT_A}, the source unit above."


def test_judge_inference_block_follows_the_prompt_version():
    nodes = {n["id"]: n for n in D3_DUMP["nodes"]}
    candidate = {"actor_inferred": "provider", "actor_inference_source_node_id": D3_POINT_A}
    unit = {"node_id": PARA_ID}
    assert judge_inference_block(D3_DUMP, nodes, unit, candidate, "v1") is None
    for version in ("v2", "v3"):
        assert "paragraph that holds it" not in judge_inference_block(D3_DUMP, nodes, unit, candidate, version)
    assert judge_inference_block(D3_DUMP, nodes, unit, candidate, "v4").endswith(D3_PARAGRAPH)


def test_the_holding_paragraph_is_the_nearest_one_above_the_point():
    from tere4ai.extract_norms.pipeline import _holding_paragraph

    outer = {"id": "x:paragraph-1", "type": "Paragraph", "text": "outer"}
    inner = {"id": "x:paragraph-1:paragraph-2", "type": "Paragraph", "text": "inner"}
    point = {"id": "x:paragraph-1:paragraph-2:point-a", "type": "Point", "text": "p"}
    nodes = {n["id"]: n for n in (outer, inner, point)}
    assert _holding_paragraph(nodes, point["id"]) is inner


# B145 (brief R27, A14): the scope step of a v1 to v4 run reads the first
# reading, so "the Board" keeps its proposed type, as at 8440c99.
def test_the_scope_step_of_a_v4_run_reads_the_first_reading(tmp_path):
    generator = FakeClient(
        {PARA_ID: _generator_with(actor_explicit="the Board", actor_inferred=None,
                                  actor_inference_source_node_id=None, requirement_type="process")},
        model="fake-generator")
    judge = FakeClient({PARA_ID: JUDGE_ACCEPT}, model="fake-judge")
    result = extract_norms(FAKE_DUMP, [PARA_ID], generator, judge, prompt_version="v4",
                           log_path=tmp_path / "extraction_log.jsonl")
    (norm,) = result["norms"]
    assert norm["actor_explicit"] == "the Board"
    assert norm["requirement_type"] == "process"

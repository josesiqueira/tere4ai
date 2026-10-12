"""Offline tests for the MILESTONE2 alignment pipeline (DEC-05, DEC-06 partial).

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

from tere4ai import act_parties as ap
from tere4ai.align_hleg.pipeline import (
    MECHANICAL_JUDGE_MODEL,
    PROPOSABLE_RELATION_TYPES,
    SPREAD_KEYS,
    _generator_user_message,
    _judge_user_message,
    align_norms,
    judge_texts,
)
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


def run_pipeline(generator_script, judge_script, norms, tmp_path, prompt_version="v1"):
    generator = FakeClient(generator_script, model="fake-generator")
    judge = FakeClient(judge_script, model="fake-judge")
    log_path = tmp_path / "alignment_log.jsonl"
    result = align_norms(
        norms,
        HLEG_NODES,
        generator,
        judge,
        prompt_version=prompt_version,
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
    # B121 (spec F D-F22): the generator's effort beside its model id
    assert run["generator_effort"] == "not configured"  # FakeClient declares no effort
    assert run["generator_temperature"] == "not configured"
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
    assert run["judge_effort"] == "not configured"  # FakeClient declares no effort; a real client carries its declared one
    assert run["judge_temperature"] == "not configured"
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
    assert run["judge_effort"] == "not applicable (mechanical gate)"
    assert run["judge_temperature"] == "not applicable (mechanical gate)"  # B99: B84 ruling R12 stands for the temperature
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
        assert line["effort"] == "not configured"  # FakeClient declares no effort
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
    assert mechanical[0]["effort"] == "not applicable (mechanical gate)"
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


def test_l3_2_accepts_a_quote_of_every_subtopic_from_its_parent(tmp_path):
    """B143 (acceptance 1): a scripted generator quotes each of the 23 subtopics' first
    sentences against its parent requirement; the mechanical quote check rejects none."""
    from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
    from tere4ai.align_hleg.hleg_subtopics import build_hleg_subtopics

    nodes = build_hleg_nodes()
    subtopics = build_hleg_subtopics()["nodes"]
    norms, scripted = [], {}
    for i, s in enumerate(subtopics, start=1):
        norm_id = f"norm:eu-ai-act:article-99:paragraph-{i}:n1"
        norms.append(_norm(norm_id=norm_id, source_node_id=f"eu-ai-act:article-99:paragraph-{i}",
                           source_span_id=f"span:099.{i:03d}"))
        scripted[norm_id] = _generator_answer(target_id=s["hleg_requirement_id"], target_quote=s["description"])
    generator = FakeClient(scripted, model="fake-generator")
    judge = FakeClient({"Target HLEG requirement:": _judge_answer()}, model="fake-judge")
    result = align_norms(norms, nodes, generator, judge, prompt_version="v1",
                         log_path=tmp_path / "alignment_log.jsonl", build_id="build-test")
    assert result["stats"]["mechanical_rejects"] == []
    assert not [r for r in result["judge_runs"] if r["judge_model"] == MECHANICAL_JUDGE_MODEL]
    assert len(result["assertions"]) == 23
    assert sorted(a["target_id"] for a in result["assertions"]) == sorted(s["hleg_requirement_id"] for s in subtopics)


# B163 (DEC-28, spec G D-G86): v2 beside v1, offline. The v1 messages below
# are what the code at tere4ai2 ad86369 wrote for the mock norm above.

ZERO = {k: 0.0 for k in SCORES}
JULY = REPO_ROOT / "data" / "graph_dumps" / "alignments_core.json"

V1_GENERATOR_MESSAGE = (
    "Norm id: norm:eu-ai-act:article-99:paragraph-1:n1\n"
    "Deontic type: obligation\n"
    "Actor: provider\n"
    "Action: keep and maintain\n"
    "Object: a risk log\n"
    'Conditions: ["for high-risk AI systems"]\n'
    "Exceptions: []\n"
    "Verbatim legal source text of the norm:\n"
    f"{SOURCE_TEXT}\n"
    "\n"
    "The seven HLEG requirements (closed set, quote target_quote from the description):\n"
    "--- hleg:technical-robustness-and-safety (Technical robustness and safety) ---\n"
    f"{HLEG_NODES[0]['description']}\n"
    "--- hleg:transparency (Transparency) ---\n"
    f"{HLEG_NODES[1]['description']}"
)

V1_JUDGE_MESSAGE = (
    "Norm id: norm:eu-ai-act:article-99:paragraph-1:n1\n"
    "Verbatim legal source text of the norm:\n"
    f"{SOURCE_TEXT}\n"
    "\n"
    "Target HLEG requirement: hleg:technical-robustness-and-safety (Technical robustness and safety)\n"
    "HLEG requirement description:\n"
    f"{HLEG_NODES[0]['description']}\n"
    "\n"
    "Candidate alignment (JSON):\n"
    "{\n"
    ' "target_id": "hleg:technical-robustness-and-safety",\n'
    ' "relation_type": "supports",\n'
    ' "source_quote": "A risk log shall be kept and maintained",\n'
    ' "target_quote": "preventative approach to risks",\n'
    ' "rationale": "A kept risk log serves the preventative approach to risks."\n'
    "}"
)


def _guard_rationale(verdict, rationale):
    return ("judge response unusable, defaulting to human review: verdict "
            f"{verdict!r} with corrected_relation_type no_clear_relation, which only a rejection may "
            f"carry (judge_alignment checks 3 and 4); the judge's rationale: {rationale}")


def test_a_v1_generator_message_is_what_it_was_at_ad86369():
    """A6, G2: a v1 run keeps the input v1 had, its party labelled Actor."""
    assert _generator_user_message(_norm(), HLEG_NODES, prompt_version="v1") == V1_GENERATOR_MESSAGE
    assert _generator_user_message(ap.in_v2_names(_norm()), HLEG_NODES, prompt_version="v1") == V1_GENERATOR_MESSAGE


def test_the_v2_generator_message_differs_from_v1_only_in_the_label():
    """A6, CHANGE6 (R6): Addressee, the value unchanged, in either norms schema version."""
    expected = V1_GENERATOR_MESSAGE.replace("\nActor: provider\n", "\nAddressee: provider\n")
    assert expected != V1_GENERATOR_MESSAGE
    assert _generator_user_message(_norm(), HLEG_NODES, prompt_version="v2") == expected
    assert _generator_user_message(ap.in_v2_names(_norm()), HLEG_NODES, prompt_version="v2") == expected
    no_party = _norm(actor_inferred=None, actor_inference_source_node_id=None)
    assert "\nAddressee: unspecified\n" in _generator_user_message(no_party, HLEG_NODES, prompt_version="v2")


def test_the_judge_message_is_what_it_was_and_its_texts_come_from_judge_texts():
    """The judge's input is unchanged in form (D-G86 (2)); judge_texts gives
    the two texts it holds, which the E1 sheet shows (R19, R28)."""
    candidate = json.loads(_generator_answer())["alignments"][0]
    assert _judge_user_message(_norm(), HLEG_NODES[0], candidate) == V1_JUDGE_MESSAGE
    assert judge_texts(_norm(), HLEG_NODES[0]) == {
        "norm_source_text": SOURCE_TEXT,
        "hleg_requirement": "hleg:technical-robustness-and-safety (Technical robustness and safety)",
        "hleg_description": HLEG_NODES[0]["description"],
    }


def test_a_v2_run_sends_the_v2_prompts_and_records_v2(tmp_path):
    result, generator, judge, log_path = run_pipeline(
        {NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path, prompt_version="v2")
    v2 = {kind: (REPO_ROOT / "prompts" / kind / "v2.md").read_text(encoding="utf-8")
          for kind in ("align_hleg", "judge_alignment")}
    assert [s for s, _u in generator.calls] == [v2["align_hleg"]]
    assert [s for s, _u in judge.calls] == [v2["judge_alignment"]]
    assert "\nAddressee: provider\n" in generator.calls[0][1]
    assert result["mapping_runs"][0]["prompt_version"] == result["judge_runs"][0]["prompt_version"] == "v2"
    raw = log_path.read_text()
    assert "build-time alignment judge" not in raw and "alignment generator for TERE4AI" not in raw


@pytest.mark.parametrize("verdict", ["accepted", "needs_human_review"])
def test_under_v2_no_clear_relation_with_a_verdict_other_than_rejected_goes_to_human_review(tmp_path, verdict):
    """A8, CHANGE3 (R3): unusable, like an invalid verdict (G13)."""
    result, _, judge, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: _judge_answer(verdict=verdict, corrected="no_clear_relation", rationale="The judge's own words.")},
        [_norm()], tmp_path, prompt_version="v2")
    assert len(judge.calls) == 1
    (assertion,) = result["assertions"]
    (run,) = result["judge_runs"]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    ALIGNMENTS_VALIDATOR.validate(run)
    assert (run["verdict"], run["corrected_relation_type"], run["scores"]) == ("needs_human_review", None, ZERO)
    assert run["rationale"] == assertion["rationale"] == _guard_rationale(verdict, "The judge's own words.")
    assert assertion["relation_type"] == assertion["proposed_relation_type"] == "supports"
    assert (assertion["judge_verdict"], assertion["review_status"], assertion["final_score"]) == (
        "needs_human_review", "needs_review", 0.0)
    assert result["stats"]["verdicts"] == {"accepted": 0, "rejected": 0, "needs_human_review": 1}


@pytest.mark.parametrize("verdict", ["accepted", "needs_human_review"])
def test_under_v1_the_same_reply_is_stored_as_given(tmp_path, verdict):
    """A8, G2: v1 keeps the handling it had at ad86369."""
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: _judge_answer(verdict=verdict, corrected="no_clear_relation")},
        [_norm()], tmp_path, prompt_version="v1")
    (assertion,) = result["assertions"]
    (run,) = result["judge_runs"]
    assert (run["verdict"], run["corrected_relation_type"], run["scores"]) == (verdict, "no_clear_relation", SCORES)
    assert assertion["relation_type"] == "no_clear_relation"
    assert assertion["review_status"] == ("accepted" if verdict == "accepted" else "needs_review")


def test_under_v2_a_rejection_with_no_clear_relation_is_kept_as_given(tmp_path):
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer()},
        {ROBUSTNESS_ID: _judge_answer(verdict="rejected", corrected="no_clear_relation", rationale="No relation.")},
        [_norm()], tmp_path, prompt_version="v2")
    (assertion,) = result["assertions"]
    (run,) = result["judge_runs"]
    assert (run["verdict"], run["corrected_relation_type"], run["rationale"]) == (
        "rejected", "no_clear_relation", "No relation.")
    assert (assertion["relation_type"], assertion["proposed_relation_type"]) == ("no_clear_relation", "supports")


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_every_assertion_keeps_the_generators_claimed_type_and_rationale(tmp_path, version):
    """A12, CHANGE10 (R11): record fields, written for every version."""
    result, _, _, _ = run_pipeline(
        {NORM_ID: _generator_answer(relation_type="directly_operationalizes")},
        {ROBUSTNESS_ID: _judge_answer(corrected="partially_operationalizes")},
        [_norm()], tmp_path, prompt_version=version)
    (assertion,) = result["assertions"]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert (assertion["relation_type"], assertion["proposed_relation_type"]) == (
        "partially_operationalizes", "directly_operationalizes")
    assert assertion["generator_rationale"] == "A kept risk log serves the preventative approach to risks."
    assert assertion["rationale"] == "Both quotes ground the relation."


@pytest.mark.parametrize("rationale", ["absent", None, 7])
def test_a_candidate_without_a_text_rationale_keeps_a_null_generator_rationale(tmp_path, rationale):
    """Review Focus 5 (R25): the candidate is judged as today; the record keeps null."""
    candidate = json.loads(_generator_answer())["alignments"][0]
    if rationale == "absent":
        del candidate["rationale"]
    else:
        candidate["rationale"] = rationale
    result, _, judge, _ = run_pipeline(
        {NORM_ID: json.dumps({"alignments": [candidate]})}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path,
        prompt_version="v2")
    assert len(judge.calls) == 1
    (assertion,) = result["assertions"]
    ALIGNMENTS_VALIDATOR.validate(assertion)
    assert assertion["generator_rationale"] is None and assertion["proposed_relation_type"] == "supports"


def test_the_schema_describes_the_two_fields_and_requires_neither():
    (branch,) = [b for b in ALIGNMENTS_SCHEMA["oneOf"] if b["title"].startswith("AlignmentAssertion")]
    props = branch["properties"]
    assert props["proposed_relation_type"]["enum"] == list(PROPOSABLE_RELATION_TYPES)
    assert props["generator_rationale"]["type"] == ["string", "null"]
    assert "proposed_relation_type" not in branch["required"] and "generator_rationale" not in branch["required"]


def test_a_proposed_no_clear_relation_fails_the_schema(tmp_path):
    result, _, _, _ = run_pipeline({NORM_ID: _generator_answer()}, {ROBUSTNESS_ID: _judge_answer()}, [_norm()], tmp_path)
    (assertion,) = result["assertions"]
    assert not ALIGNMENTS_VALIDATOR.is_valid({**assertion, "proposed_relation_type": "no_clear_relation"})


@pytest.mark.skipif(not JULY.is_file(), reason="the tracked July alignments are absent")
def test_the_july_alignments_validate_against_the_changed_schema():
    """A12: a file written before the change stays valid; no reader invents the fields."""
    july = json.loads(JULY.read_text(encoding="utf-8"))
    assert len(july["assertions"]) == 522
    for assertion in july["assertions"]:
        assert "proposed_relation_type" not in assertion
        ALIGNMENTS_VALIDATOR.validate(assertion)


def test_a_requirement_proposed_twice_is_judged_twice_and_counted_once_among_the_pairs(tmp_path):
    """A7, A13 (R8, R13): two quote pairs for one norm and one requirement."""
    second = {"target_id": ROBUSTNESS_ID, "relation_type": "related_to",
              "source_quote": "so that failures can be traced and corrected",
              "target_quote": "with resilience and fallback plans", "rationale": "Corrected failures need fallbacks."}
    two = json.dumps({"alignments": [json.loads(_generator_answer())["alignments"][0], second]})
    for version in ("v1", "v2"):
        (tmp_path / version).mkdir()
        result, _, judge, _ = run_pipeline(
            {NORM_ID: two},
            {'"source_quote": "A risk log': _judge_answer(), '"source_quote": "so that failures': _judge_answer("rejected")},
            [_norm()], tmp_path / version, prompt_version=version)
        assert len(judge.calls) == 2
        assert [a["id"].rsplit(":", 1)[1] for a in result["assertions"]] == ["1", "2"]
        stats = result["stats"]
        assert stats["assertions_by_requirement"] == {ROBUSTNESS_ID: 2, TRANSPARENCY_ID: 0}
        assert stats["accepted_by_requirement"] == {ROBUSTNESS_ID: 1, TRANSPARENCY_ID: 0}
        assert stats["pairs_by_requirement"] == {ROBUSTNESS_ID: 1, TRANSPARENCY_ID: 0}
        assert stats["accepted_pairs_by_requirement"] == {ROBUSTNESS_ID: 1, TRANSPARENCY_ID: 0}


def test_the_four_spread_counts_cover_all_seven_requirements_with_zeros(tmp_path):
    """A13: flat dicts over the seven ids in their order, zeros included."""
    from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes

    nodes = build_hleg_nodes()
    generator = FakeClient({NORM_ID: json.dumps({"alignments": []})}, model="fake-generator")
    judge = FakeClient({}, model="fake-judge")
    result = align_norms([_norm()], nodes, generator, judge, prompt_version="v2",
                         log_path=tmp_path / "alignment_log.jsonl", build_id="build-test")
    assert SPREAD_KEYS == ("assertions_by_requirement", "accepted_by_requirement",
                           "pairs_by_requirement", "accepted_pairs_by_requirement")
    for key in SPREAD_KEYS:
        assert list(result["stats"][key]) == [n["id"] for n in nodes] and set(result["stats"][key].values()) == {0}


def test_the_trace_serves_the_claimed_type_only_when_the_assertion_carries_it():
    """R43: the dashboard's lineage reads the generator's claim from the trace;
    an answer over an older file keeps its keys."""
    from tere4ai.mcp_server.trace import _render_assertion

    base = {"id": "align:x:transparency:1", "source_norm_id": "norm:x", "target_id": TRANSPARENCY_ID,
            "relation_type": "supports"}
    assert "proposed_relation_type" not in _render_assertion(base, {}, {}, [])
    claimed = _render_assertion({**base, "proposed_relation_type": "related_to"}, {}, {}, [])
    assert (claimed["relation_type"], claimed["proposed_relation_type"]) == ("supports", "related_to")

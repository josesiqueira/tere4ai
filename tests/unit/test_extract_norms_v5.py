"""B145 (spec G D-G80 (4), (9), (15), (21); brief A7, A14): the pipeline
under extract_norms v5 and judge_norms v5. Scripted models (FakeClient), no
network; the units are read from the tracked layer1.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.extract_norms import pipeline
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.pipeline import extract_norms

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")
U17, U72_1, U72_2, U12 = ("eu-ai-act:article-17:paragraph-1", "eu-ai-act:article-72:paragraph-1",
                          "eu-ai-act:article-72:paragraph-2", "eu-ai-act:article-12:paragraph-1")
ACCEPT = json.dumps({"verdict": "accepted", "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9,
                     "operational_utility": 0.8, "evidence_strength": 0.85, "judge_confidence": 0.9},
                     "rationale": "scripted"})


@pytest.fixture(scope="module")
def dump():
    return json.loads(LAYER1.read_text(encoding="utf-8"))


def _candidate(version, explicit=None, inferred=None, source=None, requirement_type="process", action="collect"):
    names = pipeline.candidate_fields(version)
    slots = [n for n in names if n.endswith(("_explicit", "_inferred", "_inference_source_node_id"))]
    return {"deontic_type": "obligation", "modal": "shall", slots[0]: explicit, slots[1]: inferred,
            slots[2]: source, "action": action, "object": "relevant data", "conditions": [], "exceptions": [],
            "lifecycle_phase_ids": [], "requirement_type": requirement_type}


def _run(dump, unit, candidate, version, tmp_path):
    generator = FakeClient({f"Source unit node id: {unit}\n": json.dumps({"norms": [candidate]})}, model="g")
    judge = FakeClient({"Candidate norm (JSON)": ACCEPT}, model="j")
    result = extract_norms(dump, [unit], generator, judge, prompt_version=version,
                           log_path=tmp_path / f"log-{version}.jsonl")
    return result, judge.calls[0][1]


def test_v5_is_the_default_and_the_version_of_record_for_b74():
    assert pipeline.DEFAULT_PROMPT_VERSION == "v5"
    record = (ROOT / "eval" / "config_evaluated.yaml").read_text(encoding="utf-8")
    assert "  extract_norms: v5\n" in record and "  judge_norms: v5\n" in record
    assert pipeline.writes_addressee("v5") and not any(pipeline.writes_addressee(v) for v in ("v1", "v2", "v3", "v4"))
    assert pipeline.candidate_fields("v4") == pipeline._NORM_CANDIDATE_FIELDS
    assert "addressee_explicit" in pipeline.candidate_fields("v5")
    assert not [f for f in pipeline.candidate_fields("v5") if f.startswith("actor")]


def test_a_v5_run_writes_version_2_names_with_the_stored_value(dump, tmp_path):
    candidate = _candidate("v5", inferred="provider", source=U72_1)
    result, judge_input = _run(dump, U72_2, candidate, "v5", tmp_path)
    (norm,) = result["norms"]
    assert (norm["addressee_explicit"], norm["addressee_inferred"], norm["addressee_inference_source_node_id"]) == (
        None, "provider", U72_1)
    assert (norm["addressee"], norm["addressee_method"], norm["addressee_placement"]) == (
        "provider", "act_parties_v1", "inferred")
    assert not [k for k in norm if k.startswith("actor")]
    assert norm["extractor_prompt_version"] == "v5"
    assert result["stats"]["invalid_norms"] == []


def test_the_v5_judge_reads_the_source_and_the_units_set_up_rows(dump, tmp_path):
    nodes = {n["id"]: n for n in dump["nodes"]}
    _result, judge_input = _run(dump, U72_2, _candidate("v5", inferred="provider", source=U72_1), "v5", tmp_path)
    assert (f"Addressee-inference source: {U72_1} (Paragraph)\n"
            f"Verbatim text of the addressee-inference source:\n[{U72_1}] {nodes[U72_1]['text']}\n\n"
            "Set-up rows for this unit:\n"
            "- “The post-market monitoring system”; “post-market monitoring”; "
            "“This obligation” is provider's; setting-up node " + U72_1 + "\n"
            f"  Verbatim text of the setting-up node: [{U72_1}] {nodes[U72_1]['text']}\n\n"
            "Candidate norm (JSON):") in judge_input
    assert "Actor" not in judge_input and "actor" not in judge_input


def test_a_written_thing_still_reaches_the_v5_judge_with_the_units_rows(dump, tmp_path):
    """A4: the row's thing as written addressee reaches the judge with the rows (D-G80 (9))."""
    candidate = _candidate("v5", explicit="the post-market monitoring system")
    result, judge_input = _run(dump, U72_2, candidate, "v5", tmp_path)
    assert "Addressee-inference source: none (the candidate's addressee is not inferred)." in judge_input
    assert "Set-up rows for this unit:" in judge_input
    (norm,) = result["norms"]
    assert (norm["addressee"], norm["addressee_placement"]) == ("unspecified_needs_review", "unplaced")


def test_a_unit_without_rows_gets_no_set_up_block_and_a_v4_input_is_as_before(dump, tmp_path):
    _r, v5_input = _run(dump, U12, _candidate("v5", inferred="provider",
                                               source="eu-ai-act:article-16:paragraph-1:point-a"), "v5", tmp_path)
    assert "Set-up rows" not in v5_input
    candidate = _candidate("v4", explicit="the post-market monitoring system")
    _r, v4_input = _run(dump, U72_2, candidate, "v4", tmp_path)
    nodes = {n["id"]: n for n in dump["nodes"]}
    expected = (f"Source unit node id: {U72_2}\nVerbatim source text:\n{nodes[U72_2]['text']}\n\n"
                "Actor-inference source: none (the candidate's actor is not inferred).\n\n"
                "Candidate norm (JSON):\n")
    assert v4_input.startswith(expected)
    assert '"actor_explicit": "the post-market monitoring system"' in v4_input


def test_the_board_keeps_process_under_v4_and_reaches_the_v5_judge_without_a_type(dump, tmp_path):
    """A14: the scope is read per version before the judge sees the candidate."""
    v4_result, v4_input = _run(dump, U17, _candidate("v4", explicit="the Board"), "v4", tmp_path)
    assert '"requirement_type": "process"' in v4_input
    assert v4_result["norms"][0]["requirement_type"] == "process"
    assert "actor_explicit" in v4_result["norms"][0] and "addressee" not in v4_result["norms"][0]
    v5_result, v5_input = _run(dump, U17, _candidate("v5", explicit="the Board"), "v5", tmp_path)
    assert '"requirement_type": null' in v5_input
    (norm,) = v5_result["norms"]
    assert (norm["requirement_type"], norm["addressee"], norm["addressee_placement"]) == (None, "board", "placed")

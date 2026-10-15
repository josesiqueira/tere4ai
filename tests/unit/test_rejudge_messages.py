"""B173 task 1: the message a stored norm or alignment is re-judged with equals
the message its judge received when it was made. FakeClient only, no network;
the Layer 1 dump is written here and the HLEG requirements are the tracked pair.

@implements: DEC-06 (partial: the shared judge message functions)
@grounded_by: REF-24
"""

from __future__ import annotations

import json

import pytest

from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.align_hleg.pipeline import _judge_user_message, align_norms, alignment_candidate_of
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.pipeline import (
    _index_nodes,
    candidate_of_norm,
    extract_norms,
    judge_message,
    unit_of_norm,
)

A16, A16_P1, A16_PA = (
    "eu-ai-act:article-16",
    "eu-ai-act:article-16:paragraph-1",
    "eu-ai-act:article-16:paragraph-1:point-a",
)
A17_P1 = "eu-ai-act:article-17:paragraph-1"  # a unit the set-up table covers
A99_P1 = "eu-ai-act:article-99:paragraph-1"
JUDGE_MARK = "Candidate norm (JSON):\n"
ACCEPT = json.dumps({
    "verdict": "accepted",
    "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9, "operational_utility": 0.8,
               "evidence_strength": 0.85, "judge_confidence": 0.9},
    "rationale": "scripted",
})


def _span(anchor: str) -> dict:
    return {"span_id": f"span:{anchor}", "snapshot_file": "fake.html", "snapshot_sha256": "0" * 64,
            "start": 0, "end": 10, "anchor": anchor}


def _dump() -> dict:
    return {"build": {"build_id": "build-test"}, "nodes": [
        {"id": "eu-ai-act:article-16", "layer": 1, "type": "Article", "number": 16, "title": "Obligations of providers",
         "source_span": _span("art_16")},
        {"id": A16_P1, "layer": 1, "type": "Paragraph", "index": 1,
         "text": "1. Providers of high-risk AI systems shall:", "source_span": _span("016.001")},
        {"id": A16_PA, "layer": 1, "type": "Point", "marker": "a",
         "text": "(a) ensure that their high-risk AI systems are compliant with the requirements;",
         "source_span": _span("016.001.a")},
        {"id": "eu-ai-act:article-17", "layer": 1, "type": "Article", "number": 17, "title": "Quality management system",
         "source_span": _span("art_17")},
        {"id": A17_P1, "layer": 1, "type": "Paragraph", "index": 1,
         "text": "1. Providers of high-risk AI systems shall put a quality management system in place. "
                 "That system shall be documented.", "source_span": _span("017.001")},
        {"id": "eu-ai-act:article-99", "layer": 1, "type": "Article", "number": 99, "title": "Penalties",
         "source_span": _span("art_99")},
        {"id": A99_P1, "layer": 1, "type": "Paragraph", "index": 1,
         "text": "1. A risk log shall be kept and maintained for high-risk AI systems, unless exempted.",
         "source_span": _span("099.001")},
    ]}


def _v6(**overrides) -> dict:
    candidate = {
        "deontic_type": "obligation", "modal": "shall",
        "addressee_explicit": None, "addressee_inferred": None, "addressee_inference_source_node_id": None,
        "action": "keep", "object": "a risk log", "conditions": [], "exceptions": [],
        "requirement_type": "process",
    }
    candidate.update(overrides)
    return candidate


def _extract(dump: dict, replies: dict, tmp_path) -> tuple[dict, FakeClient]:
    generator = FakeClient({f"Source unit node id: {unit}\n": json.dumps({"norms": cands})
                            for unit, cands in replies.items()}, model="g")
    judge = FakeClient({JUDGE_MARK: ACCEPT}, model="j")
    result = extract_norms(dump, [A99_P1, A17_P1, A16], generator, judge, prompt_version="v6",
                           log_path=tmp_path / "log.jsonl")
    assert result["stats"]["invalid_norms"] == [] and result["stats"]["nodes_failed"] == []
    return result, judge


def test_rebuilt_norm_message_equals_the_generation_time_message(tmp_path):
    dump = _dump()
    replies = {
        # an inferred addressee with its source node, conditions and exceptions filled
        A99_P1: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A16_PA,
                     conditions=["for high-risk AI systems"], exceptions=["unless exempted"])],
        # the unit the set-up table covers
        A17_P1: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A17_P1,
                     action="document", object="that system")],
        A16_P1: [_v6(addressee_explicit="providers", action="comply", object="with the requirements")],
        A16_PA: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A16_PA,
                     action="ensure", object="that systems are compliant")],
    }
    result, judge = _extract(dump, replies, tmp_path)
    norms = result["norms"]
    assert len(norms) == 4 and len(judge.calls) == 4
    nodes = _index_nodes(dump)
    captured_by_unit = {}
    for norm, (_system, captured) in zip(norms, judge.calls, strict=True):
        captured_by_unit[norm["source_node_id"]] = captured
        unit = unit_of_norm(dump, norm)
        rebuilt = judge_message(dump, nodes, unit, candidate_of_norm(norm, "v6"), "v6")
        assert rebuilt == captured, norm["norm_id"]
    # the set-up unit's message really carried the rows and the inference text
    assert "Set-up rows for this unit:" in captured_by_unit[A17_P1]
    assert "Addressee-inference source: " + A16_PA in captured_by_unit[A99_P1]


def test_rebuilt_message_differs_only_where_the_norm_normalised(tmp_path):
    dump = _dump()
    candidate = _v6(addressee_explicit="providers", conditions=None)
    del candidate["exceptions"]
    result, judge = _extract(dump, {A99_P1: [candidate], A17_P1: [], A16_P1: [], A16_PA: []}, tmp_path)
    (norm,) = result["norms"]
    (_system, captured), nodes = judge.calls[0], _index_nodes(dump)
    rebuilt = judge_message(dump, nodes, unit_of_norm(dump, norm), candidate_of_norm(norm, "v6"), "v6")
    captured_head, captured_json = captured.split(JUDGE_MARK)
    rebuilt_head, rebuilt_json = rebuilt.split(JUDGE_MARK)
    assert rebuilt_head == captured_head
    was, now = json.loads(captured_json), json.loads(rebuilt_json)
    assert "exceptions" not in was and was["conditions"] is None
    assert now["exceptions"] == [] and now["conditions"] == []
    assert {k for k in was.keys() | now.keys() if was.get(k, "<absent>") != now.get(k, "<absent>")} == {
        "conditions", "exceptions"}


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_candidate_of_norm_refuses_v1_and_v2(version):
    with pytest.raises(ValueError, match="DEC-21"):
        candidate_of_norm({"norm_id": "norm:x"}, version)


SOURCE_TEXT = "1. A risk log shall be kept and maintained for high-risk AI systems, unless exempted."
NORM_ID = "norm:eu-ai-act:article-99:paragraph-1:n1"


def _aligned_norm() -> dict:
    return {
        "norm_id": NORM_ID, "source_node_id": A99_P1, "source_span_id": "span:099.001",
        "deontic_type": "obligation", "modal": "shall", "addressee_explicit": None,
        "addressee_inferred": "provider", "addressee_inference_source_node_id": A16_PA,
        "action": "keep and maintain", "object": "a risk log", "conditions": ["for high-risk AI systems"],
        "exceptions": ["unless exempted"], "judge_verdict": "accepted", "source_text": SOURCE_TEXT,
    }


def test_rebuilt_alignment_message_equals_the_generation_time_message(tmp_path):
    hleg = build_hleg_nodes(load_pair())
    by_id = {h["id"]: h for h in hleg}
    robustness = next(h["id"] for h in hleg if h["name"] == "Technical robustness and safety")
    transparency = next(h["id"] for h in hleg if h["name"] == "Transparency")
    first = {"target_id": robustness, "relation_type": "partially_operationalizes",
             "source_quote": "A risk log shall be kept", "target_quote": "developed with a preventative approach to risks",
             "rationale": "A kept log serves a preventative approach."}
    second = {"target_id": transparency, "relation_type": "related_to",
              "source_quote": "kept and maintained", "target_quote": "to allow for traceability",
              "rationale": "A log allows traceability."}
    generator = FakeClient({f"Norm id: {NORM_ID}\n": json.dumps({"alignments": [first, second]})}, model="g")
    reply = json.dumps({"verdict": "accepted", "corrected_relation_type": None, "scores": {
        "semantic_similarity": 0.8, "normative_relevance": 0.9, "operational_utility": 0.7,
        "evidence_strength": 0.85, "judge_confidence": 0.9}, "rationale": "scripted"})
    judge = FakeClient({'"source_quote": "A risk log shall be kept"': reply,
                        '"source_quote": "kept and maintained"': reply}, model="j")
    norm = _aligned_norm()
    result = align_norms([norm], hleg, generator, judge, prompt_version="v2",
                         log_path=tmp_path / "log.jsonl", build_id="build-test")
    assertions = result["assertions"]
    assert len(assertions) == 2 and len(judge.calls) == 2
    for assertion, (_system, captured) in zip(assertions, judge.calls, strict=True):
        candidate = alignment_candidate_of(assertion)
        assert list(candidate) == ["target_id", "relation_type", "source_quote", "target_quote", "rationale"]
        assert _judge_user_message(norm, by_id[assertion["target_id"]], candidate) == captured


def test_alignment_candidate_of_refuses_an_assertion_without_proposed_relation_type():
    with pytest.raises(ValueError, match="proposed_relation_type"):
        alignment_candidate_of({"id": "align:x", "target_id": "hleg:y", "relation_type": "supports",
                                "source_quote": "a", "target_quote": "b"})

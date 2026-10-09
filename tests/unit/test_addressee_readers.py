"""B145 (brief R16, R48, R50; A19, A20): every reader outside the served
path reads a norm of either schema version through tere4ai.act_parties,
and the digests that pass a norm's party to another instrument's model keep
their key "actor" and their content byte for byte."""

from __future__ import annotations

from pathlib import Path

import pytest

from tere4ai import act_parties as ap
from tere4ai.align_hleg import pipeline as align_pipeline
from tere4ai.canonicalize.canonicalizer import canonicalize_norms
from tere4ai.eval.strategies import GraphStrategy
from tere4ai.extract_norms.dedup import find_near_duplicates
from tere4ai.graph_store.layer23 import norms_to_graph
from tere4ai.judge import runtime_grounding
from tere4ai.mcp_server import evidence
from tere4ai.review_queue.apply import apply_decisions
from tere4ai.review_queue.queue import _norm_digest, record_decision, validate_human_payload

ROOT = Path(__file__).resolve().parents[2]

V1 = {
    "norm_id": "norm:eu-ai-act:article-17:paragraph-1:n1", "layer": 2, "type": "NormativeStatement",
    "source_node_id": "eu-ai-act:article-17:paragraph-1", "source_span_id": "span:017.001",
    "deontic_type": "obligation", "modal": "shall",
    "actor_explicit": "providers of high-risk AI systems", "actor_inferred": None,
    "actor_inference_source_node_id": None, "action": "put in place", "object": "a quality management system",
    "target_system_category": "high_risk_ai_system", "conditions": [], "exceptions": [],
    "condition_ids": [], "exception_ids": [], "lifecycle_phase_ids": [], "requirement_type": "process",
    "extraction_method": "llm_extract_v1", "extractor_model": "g", "extractor_prompt_version": "v4",
    "confidence": 0.9, "judge_verdict": "accepted", "judge_run_id": None, "review_status": "accepted",
}
V2 = ap.in_v2_names(V1)


def test_the_helpers_read_either_version():
    assert ap.slots_of(V1) == ap.slots_of(V2) == ("providers of high-risk AI systems", None, None)
    assert ap.actor_slots_for_digests(V2) == {"actor_explicit": "providers of high-risk AI systems",
                                              "actor_inferred": None, "actor_inference_source_node_id": None}
    assert ap.in_v1_names(V2) == {k: v for k, v in V1.items()}
    assert ap.norms_schema_version({"norms": []}) == 1
    assert ap.norms_schema_version({"norms_schema_version": 2, "norms": []}) == 2
    assert ap.NORMS_SCHEMA_PATHS[2].name == "norms.v2.schema.json"


def test_the_model_digests_keep_their_key_and_content_in_either_version():
    """A20: the content at tere4ai2 8440c99 for a version 1 norm, the same for version 2."""
    for norm in (V1, V2):
        norm = {**norm, "source_text": "1. Providers of high-risk AI systems shall put a quality management system in place"}
        align = align_pipeline._generator_user_message(norm, [])
        assert "Actor: providers of high-risk AI systems\n" in align
        ev = evidence._generator_user_message(norm, {"artifact_type": "document", "content": "x"})
        assert "Actor: providers of high-risk AI systems\n" in ev
        assert GraphStrategy._norm_text(norm).startswith("providers of high-risk AI systems put in place")
        digest = runtime_grounding._norm_digest(norm)
        assert (digest["actor_explicit"], digest["actor_inferred"]) == ("providers of high-risk AI systems", None)
    text = {"source_text": "1. Providers ..."}
    assert align_pipeline._generator_user_message({**V1, **text}, []) == align_pipeline._generator_user_message({**V2, **text}, [])


def test_the_review_queue_digest_is_the_same_for_either_version():
    assert _norm_digest(V1) == _norm_digest(V2)
    assert "actor=providers of high-risk AI systems " in _norm_digest(V2)


HUMAN_V2 = {
    "source_node_id": "eu-ai-act:article-25:paragraph-4", "source_span_id": "span:025.004",
    "deontic_type": "obligation", "modal": "shall",
    "addressee_explicit": "the third party that supplies an AI system, AI model, tools, services, components, or processes",
    "addressee_inferred": None, "addressee_inference_source_node_id": None,
    "action": "specify", "object": "the necessary information", "conditions": [], "exceptions": [],
    "lifecycle_phase_ids": [], "requirement_type": "process",
}


def test_a_human_norm_in_version_2_names_is_validated_and_lands_in_the_files_version():
    validate_human_payload("add", HUMAN_V2)
    with pytest.raises(ValueError, match="addressee_explicit"):
        validate_human_payload("add", {k: v for k, v in HUMAN_V2.items() if k != "addressee_explicit"})
    with pytest.raises(ValueError, match="addressee_inference_source_node_id"):
        validate_human_payload("add", {**HUMAN_V2, "addressee_explicit": None, "addressee_inferred": "provider"})
    decisions = {}
    record_decision(decisions, "norm:eu-ai-act:article-25:paragraph-4:h1", "add", "Article 25(4)", "annotator a",
                    payload=HUMAN_V2)
    into_v1 = apply_decisions({"norms": []}, decisions)["norms"][0]
    assert into_v1["actor_explicit"] == HUMAN_V2["addressee_explicit"]
    assert not [k for k in into_v1 if k.startswith("addressee")]
    into_v2 = apply_decisions({"norms_schema_version": 2, "norms": []}, decisions)["norms"][0]
    assert into_v2["addressee_explicit"] == HUMAN_V2["addressee_explicit"]
    assert (into_v2["addressee"], into_v2["addressee_method"], into_v2["addressee_placement"]) == (
        "third_party_supplier", "act_parties_v1", "placed")
    assert not [k for k in into_v2 if k.startswith("actor_")]


def test_canonicalize_norms_gives_a_version_2_norm_its_stored_value():
    out = canonicalize_norms({"norms_schema_version": 2, "norms": [V2]})["norms"][0]
    assert (out["addressee"], out["addressee_placement"]) == ("provider", "placed")
    assert "actor_canonical" not in out
    v1_out = canonicalize_norms({"norms": [V1]})["norms"][0]
    assert v1_out["actor_canonical"] == "provider"


def test_layer_2_publication_carries_the_addressee_in_version_2_names_for_either_version():
    for norm in (V1, V2):
        (node,) = [n for n in norms_to_graph({"norms": [norm], "judge_runs": []}, "b")["nodes"]
                   if n["type"] == "NormativeStatement"]
        assert node["addressee_explicit"] == "providers of high-risk AI systems"
        assert node["addressee"] == "provider"
        assert not [k for k in node if k.startswith("actor_")]


def test_the_near_duplicate_blocks_read_the_stored_value():
    """R16: "provider" and "providers" are one block now; two parties never pair."""
    a = {**V1, "norm_id": "n1", "actor_explicit": "provider", "action": "keep", "object": "the logs"}
    b = {**V1, "norm_id": "n2", "actor_explicit": "providers", "action": "keep", "object": "the logs"}
    c = {**V1, "norm_id": "n3", "actor_explicit": "deployers", "action": "keep", "object": "the logs"}
    pairs = find_near_duplicates([a, ap.in_v2_names(b), c])
    assert [(p["norm_a"], p["norm_b"], p["addressee"]) for p in pairs] == [("n1", "n2", "provider")]


def test_the_ui_export_rows_are_the_same_for_either_version():
    """export_ui_data's review-queue rows keep their keys "actor" and "actor_source"."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("export_ui_data", ROOT / "scripts" / "export_ui_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    review = {**V1, "judge_verdict": "needs_human_review"}
    rows = [module.build_review_queue({"nodes": []}, {"norms": [norm]}, None)
            for norm in (review, ap.in_v2_names(review))]
    assert rows[0] == rows[1]
    (item,) = rows[0]["norms_needing_review"]
    assert (item["actor"], item["actor_source"]) == ("providers of high-risk AI systems", "explicit")


def test_r100_an_addressee_outside_version_1s_enumeration_lands_in_a_version_2_file():
    """Plan R100: the dashboard form offers all 37 of the Act's parties; "board" is
    not among version 1's 15, so a version 2 file takes it (checked against
    norms.v2.schema.json) and a version 1 file keeps its version 1 check, which
    refuses it."""
    payload = {**HUMAN_V2, "addressee_explicit": None, "addressee_inferred": "board",
               "addressee_inference_source_node_id": "eu-ai-act:article-25:paragraph-3"}
    decisions = {}
    record_decision(decisions, "norm:eu-ai-act:article-25:paragraph-4:h1", "add", "Article 25(4)", "annotator a",
                    payload=payload)
    into_v2 = apply_decisions({"norms_schema_version": 2, "norms": []}, decisions)["norms"][0]
    assert into_v2["addressee"] == "board"
    assert into_v2["addressee_inferred"] == "board"
    with pytest.raises(ValueError, match="norms.schema.json"):
        apply_decisions({"norms": []}, decisions)

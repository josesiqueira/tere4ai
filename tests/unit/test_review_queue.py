"""Tests for the human review queue adjudication tooling (DEC-06).

Covers the unified queue over the real dumps, decision recording and
validation, applying decisions to payload copies, HUMAN_REVIEWED provenance
through the layer23 graph adapter, and the publish-time integration.
"""

import json
from pathlib import Path

import pytest

from tere4ai.graph_store.layer23 import alignments_to_graph, norms_to_graph
from tere4ai.review_queue import (
    apply_decisions,
    count_applied,
    list_pending,
    load_decisions,
    record_decision,
    save_decisions,
)

ROOT = Path(__file__).resolve().parents[2]
DUMPS = ROOT / "data" / "graph_dumps"
NORMS_PATH = DUMPS / "norms_core.json"
ALIGNMENTS_PATH = DUMPS / "alignments_core.json"
LAYER1_PATH = DUMPS / "layer1.json"

REAL_DUMPS_PRESENT = (
    NORMS_PATH.is_file() and ALIGNMENTS_PATH.is_file() and LAYER1_PATH.is_file()
)


def _norms_payload():
    return {
        "norms": [
            {
                "norm_id": "norm:eu-ai-act:article-5:paragraph-2:n4",
                "source_node_id": "eu-ai-act:article-5:paragraph-2",
                "source_span_id": "span:005.002",
                "deontic_type": "obligation",
                "modal": "shall",
                "action": "be authorised",
                "object": "the use of the system",
                "extraction_method": "llm_extract_v1",
                "extractor_model": "gpt-test",
                "confidence": 0.8,
                "judge_verdict": "needs_human_review",
                "judge_run_id": "judgerun:x:1",
                "review_status": "needs_review",
            },
            {
                "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
                "source_node_id": "eu-ai-act:article-9:paragraph-1",
                "source_span_id": "span:009.001",
                "deontic_type": "obligation",
                "modal": "shall",
                "action": "be established",
                "object": "a risk management system",
                "extraction_method": "llm_extract_v1",
                "extractor_model": "gpt-test",
                "confidence": 0.9,
                "judge_verdict": "accepted",
                "judge_run_id": "judgerun:x:2",
                "review_status": "accepted",
            },
        ],
        "judge_runs": [
            {
                "id": "judgerun:x:1",
                "judge_kind": "extraction",
                "verdict": "needs_human_review",
                "rationale": "carve-out possibly dropped; human should resolve",
            }
        ],
    }


def _alignments_payload():
    return {
        "assertions": [
            {
                "id": "align:x:1",
                "source_norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
                "target_id": "hleg:technical-robustness-and-safety",
                "relation_type": "supports",
                "final_score": 0.45,
                "judge_verdict": "rejected",
                "review_status": "needs_review",
                "rationale": "overlap is only the word harm",
                "mapping_run_id": "mappingrun:x",
                "judge_run_id": "judgerun:y:1",
                "source_evidence_span_ids": ["span:009.001"],
                "target_evidence_span_ids": ["span:hleg:req2"],
                "source_quote": "a risk management system shall be established",
                "target_quote": "minimising unintentional and unexpected harm",
            },
            {
                "id": "align:x:2",
                "source_norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
                "target_id": "hleg:human-agency-and-oversight",
                "relation_type": "supports",
                "final_score": 0.9,
                "judge_verdict": "accepted",
                "review_status": "accepted",
                "mapping_run_id": "mappingrun:x",
                "judge_run_id": "judgerun:y:2",
                "source_evidence_span_ids": ["span:009.001"],
                "target_evidence_span_ids": ["span:hleg:req1"],
            },
        ],
        "mapping_runs": [],
        "judge_runs": [],
    }


def _layer1_dump():
    return {
        "build": {"build_id": "b-test", "snapshots": []},
        "nodes": [
            {
                "id": "eu-ai-act:article-5:paragraph-2",
                "layer": 1,
                "type": "Paragraph",
                "text": "2. The use of real-time remote biometric identification systems ...",
                "source_span": {"span_id": "span:005.002"},
            }
        ],
        "edges": [],
        "review_queue": [
            {
                "item_id": "xrefq:1",
                "kind": "cross_reference",
                "citation_text": "Chapter II of Regulation (EU) 2022/2065",
                "source_span_id": "span:005.002",
                "from_node_id": "eu-ai-act:article-2",
                "reason": "external_instrument",
            }
        ],
    }


# --- unified queue -----------------------------------------------------------


def test_list_pending_unifies_three_kinds():
    items = list_pending(_norms_payload(), _alignments_payload(), _layer1_dump())
    by_kind = {}
    for it in items:
        by_kind.setdefault(it["kind"], []).append(it)
    assert len(by_kind["norm"]) == 1
    assert len(by_kind["alignment"]) == 1
    assert len(by_kind["crossref"]) == 1
    ids = {it["queue_id"] for it in items}
    assert ids == {"norm:eu-ai-act:article-5:paragraph-2:n4", "align:x:1", "xrefq:1"}


def test_list_pending_carries_source_text_and_rationale():
    items = {it["queue_id"]: it for it in list_pending(
        _norms_payload(), _alignments_payload(), _layer1_dump()
    )}
    norm_item = items["norm:eu-ai-act:article-5:paragraph-2:n4"]
    assert "real-time remote biometric" in norm_item["source_excerpt"]
    assert "human should resolve" in norm_item["judge_rationale"]
    align_item = items["align:x:1"]
    assert "risk management system" in align_item["source_excerpt"]
    assert "overlap is only the word harm" in align_item["judge_rationale"]
    xref_item = items["xrefq:1"]
    assert "biometric" in xref_item["source_excerpt"]
    assert "external_instrument" in xref_item["judge_rationale"]


def test_list_pending_excludes_decided_items():
    decisions = {}
    record_decision(decisions, "xrefq:1", "reject", "external instrument, out of scope", "jose")
    items = list_pending(
        _norms_payload(), _alignments_payload(), _layer1_dump(), decisions=decisions
    )
    assert {it["queue_id"] for it in items} == {
        "norm:eu-ai-act:article-5:paragraph-2:n4",
        "align:x:1",
    }


@pytest.mark.skipif(not REAL_DUMPS_PRESENT, reason="real graph dumps not present")
def test_list_pending_counts_against_real_dumps():
    norms_payload = json.loads(NORMS_PATH.read_text(encoding="utf-8"))
    alignments_payload = json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))
    layer1 = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    items = list_pending(norms_payload, alignments_payload, layer1)

    expected_norms = sum(
        1 for n in norms_payload["norms"] if n.get("judge_verdict") == "needs_human_review"
    )
    expected_aligns = sum(
        1
        for a in alignments_payload["assertions"]
        if a.get("judge_verdict") == "needs_human_review"
        or a.get("review_status") == "needs_review"
    )
    expected_xrefs = len(layer1["review_queue"])

    counts = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    assert counts["norm"] == expected_norms
    assert counts["alignment"] == expected_aligns
    assert counts["crossref"] == expected_xrefs
    assert expected_norms > 0 and expected_aligns > 0 and expected_xrefs > 0
    # stable ids, no collisions across the three pools
    ids = [it["queue_id"] for it in items]
    assert len(ids) == len(set(ids))


# --- decision recording and the decisions file -------------------------------


def test_record_decision_refuses_empty_rationale():
    decisions = {}
    with pytest.raises(ValueError, match="rationale"):
        record_decision(decisions, "norm:x", "accept", "", "jose")
    with pytest.raises(ValueError, match="rationale"):
        record_decision(decisions, "norm:x", "accept", "   ", "jose")
    assert decisions == {}


def test_record_decision_refuses_bad_decision_and_reviewer():
    decisions = {}
    with pytest.raises(ValueError, match="decision"):
        record_decision(decisions, "norm:x", "maybe", "seems fine", "jose")
    with pytest.raises(ValueError, match="reviewer"):
        record_decision(decisions, "norm:x", "accept", "seems fine", "")
    assert decisions == {}


def test_record_decision_records_who_when_what_why():
    decisions = {}
    entry = record_decision(decisions, "norm:x", "accept", "grounded in the span", "jose")
    assert entry["decision"] == "accept"
    assert entry["rationale"] == "grounded in the span"
    assert entry["reviewer"] == "jose"
    assert entry["decided_at"]  # ISO timestamp set automatically
    assert decisions["norm:x"] is entry


def test_decisions_file_round_trips(tmp_path):
    path = tmp_path / "decisions.json"
    assert load_decisions(path) == {}
    decisions = {}
    record_decision(decisions, "norm:x", "accept", "grounded", "jose", decided_at="2026-07-09T00:00:00+00:00")
    record_decision(decisions, "align:y", "reject", "forced connection", "jose", decided_at="2026-07-09T00:00:01+00:00")
    save_decisions(decisions, path)
    assert load_decisions(path) == decisions
    # update in place: re-deciding overwrites, does not duplicate
    record_decision(decisions, "norm:x", "reject", "on second look the carve-out is dropped", "jose")
    save_decisions(decisions, path)
    reloaded = load_decisions(path)
    assert len(reloaded) == 2
    assert reloaded["norm:x"]["decision"] == "reject"


# --- applying decisions -------------------------------------------------------


def test_apply_decisions_flips_verdict_status_and_sets_provenance():
    decisions = {}
    record_decision(
        decisions, "norm:eu-ai-act:article-5:paragraph-2:n4", "accept", "grounded", "jose"
    )
    original = _norms_payload()
    applied = apply_decisions(original, decisions)
    # the original payload is never mutated (dumps stay pristine)
    assert original["norms"][0]["judge_verdict"] == "needs_human_review"
    assert "human_review" not in original["norms"][0]

    decided = applied["norms"][0]
    assert decided["judge_verdict"] == "accepted"
    assert decided["review_status"] == "accepted"
    hr = decided["human_review"]
    assert hr["provenance"] == "HUMAN_REVIEWED_ACCEPTED"
    assert hr["reviewer"] == "jose"
    assert hr["rationale"] == "grounded"
    assert hr["decided_at"]
    # undecided items untouched
    assert "human_review" not in applied["norms"][1]
    assert count_applied(applied) == 1


def test_apply_decisions_reject_on_alignments_payload():
    decisions = {}
    record_decision(decisions, "align:x:1", "reject", "forced connection", "jose")
    applied = apply_decisions(_alignments_payload(), decisions)
    decided = applied["assertions"][0]
    assert decided["judge_verdict"] == "rejected"
    assert decided["review_status"] == "rejected"
    assert decided["human_review"]["provenance"] == "HUMAN_REVIEWED_REJECTED"


def test_apply_decisions_rejects_unknown_payload_shape():
    with pytest.raises(ValueError):
        apply_decisions({"nodes": []}, {"x": {"decision": "accept"}})


# --- provenance through the layer23 graph adapter -----------------------------


def test_human_accepted_norm_graphs_with_human_reviewed_provenance():
    decisions = {}
    record_decision(
        decisions, "norm:eu-ai-act:article-5:paragraph-2:n4", "accept", "grounded", "jose"
    )
    applied = apply_decisions(_norms_payload(), decisions)
    g = norms_to_graph(applied, build_id="b-test")
    derived = {e["from"]: e for e in g["edges"] if e["edge_type"] == "DERIVED_FROM"}
    assert (
        derived["norm:eu-ai-act:article-5:paragraph-2:n4"]["provenance_class"]
        == "HUMAN_REVIEWED_ACCEPTED"
    )
    # untouched, judge-accepted norm keeps LLM_JUDGED_ACCEPTED
    assert (
        derived["norm:eu-ai-act:article-9:paragraph-1:n1"]["provenance_class"]
        == "LLM_JUDGED_ACCEPTED"
    )
    # the human trail is persisted on the node as flat scalar properties
    node = next(
        n for n in g["nodes"] if n["id"] == "norm:eu-ai-act:article-5:paragraph-2:n4"
    )
    assert node["human_review_provenance"] == "HUMAN_REVIEWED_ACCEPTED"
    assert node["human_review_reviewer"] == "jose"
    assert node["human_review_rationale"] == "grounded"
    assert node["judge_verdict"] == "accepted"


def test_human_decided_alignment_edges_carry_human_provenance():
    decisions = {}
    record_decision(decisions, "align:x:1", "accept", "relation holds on both spans", "jose")
    applied = apply_decisions(_alignments_payload(), decisions)
    g = alignments_to_graph(applied, hleg_nodes=[], build_id="b-test")
    of_edges = {e["from"]: e for e in g["edges"] if e["edge_type"] == "ASSERTS_ALIGNMENT_OF"}
    assert of_edges["align:x:1"]["provenance_class"] == "HUMAN_REVIEWED_ACCEPTED"
    assert of_edges["align:x:2"]["provenance_class"] == "LLM_JUDGED_ACCEPTED"


# --- publish integration ------------------------------------------------------


def test_publish_applies_decisions_before_gates(tmp_path, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "publish_layer23", ROOT / "scripts" / "publish_layer23.py"
    )
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)

    norms_path = tmp_path / "norms.json"
    norms_path.write_text(json.dumps(_norms_payload()), encoding="utf-8")
    align_path = tmp_path / "alignments.json"
    align_path.write_text(json.dumps(_alignments_payload()), encoding="utf-8")
    dump_path = tmp_path / "layer1.json"
    dump_path.write_text(json.dumps(_layer1_dump()), encoding="utf-8")

    decisions = {}
    record_decision(
        decisions, "norm:eu-ai-act:article-5:paragraph-2:n4", "accept", "grounded", "jose"
    )
    record_decision(decisions, "align:x:1", "reject", "forced connection", "jose")
    decisions_path = tmp_path / "decisions.json"
    save_decisions(decisions, decisions_path)

    seen = {}

    class _Report:
        passed = True
        failures = []
        stats = {}

    def fake_validate_build(dump, norms=None, alignments=None):
        seen["norms"] = norms
        seen["alignments"] = alignments
        return _Report()

    monkeypatch.setattr(publish, "validate_build", fake_validate_build)

    rc = publish.main(
        [
            "--norms", str(norms_path),
            "--alignments", str(align_path),
            "--dump", str(dump_path),
            "--decisions", str(decisions_path),
            "--gates-only",
        ]
    )
    assert rc == 0
    # the gates saw the payloads with human decisions already applied
    decided_norm = next(
        n for n in seen["norms"] if n["norm_id"] == "norm:eu-ai-act:article-5:paragraph-2:n4"
    )
    assert decided_norm["judge_verdict"] == "accepted"
    assert decided_norm["human_review"]["provenance"] == "HUMAN_REVIEWED_ACCEPTED"
    decided_align = next(a for a in seen["alignments"] if a["id"] == "align:x:1")
    assert decided_align["judge_verdict"] == "rejected"

    out = capsys.readouterr().out
    assert "human review: 2 decisions applied" in out
    assert out.index("human review") < out.index("gates:")
    # the dumps on disk are untouched
    on_disk = json.loads(norms_path.read_text(encoding="utf-8"))
    assert on_disk["norms"][0]["judge_verdict"] == "needs_human_review"


def test_publish_without_decisions_file_is_silent(tmp_path, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "publish_layer23_nodec", ROOT / "scripts" / "publish_layer23.py"
    )
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)

    norms_path = tmp_path / "norms.json"
    norms_path.write_text(json.dumps(_norms_payload()), encoding="utf-8")
    dump_path = tmp_path / "layer1.json"
    dump_path.write_text(json.dumps(_layer1_dump()), encoding="utf-8")

    class _Report:
        passed = True
        failures = []
        stats = {}

    monkeypatch.setattr(publish, "validate_build", lambda *a, **k: _Report())
    rc = publish.main(
        [
            "--norms", str(norms_path),
            "--dump", str(dump_path),
            "--decisions", str(tmp_path / "absent.json"),
            "--gates-only",
        ]
    )
    assert rc == 0
    assert "human review" not in capsys.readouterr().out


HUMAN_NORM = {
    "source_node_id": "eu-ai-act:article-12:paragraph-1",
    "source_span_id": "span:fmx:art_12.par_1",
    "deontic_type": "obligation",
    "modal": "shall",
    "actor_explicit": "high-risk AI systems",
    "actor_inferred": None,
    "actor_inference_source_node_id": None,
    "action": "technically allow for",
    "object": "the automatic recording of events (logs)",
    "conditions": ["over the lifetime of the system"],
    "exceptions": [],
    "lifecycle_phase_ids": ["cross_phase"],
}


def test_record_decision_replace_requires_a_payload():
    with pytest.raises(ValueError, match="payload"):
        record_decision({}, "norm:x:n1", "replace", "wrong object", "annotator a")


def test_record_decision_add_requires_source_node_and_span():
    bad = dict(HUMAN_NORM)
    bad.pop("source_span_id")
    with pytest.raises(ValueError, match="source_span_id"):
        record_decision({}, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "missing norm", "annotator a", payload=bad)


def test_apply_decisions_replace_overwrites_slots_and_stamps_human_provenance():
    payload = {"norms": [{"norm_id": "norm:x:n1", "source_node_id": "x", "source_span_id": "s",
                          "deontic_type": "permission", "modal": "may", "actor_explicit": None,
                          "action": "old", "object": "old", "extraction_method": "llm_extract_v1",
                          "extractor_model": "gpt-6-astra", "confidence": 0.4,
                          "judge_verdict": "rejected", "review_status": "rejected", "judge_run_id": "r1"}]}
    decisions = {}
    record_decision(decisions, "norm:x:n1", "replace", "the sentence is an obligation", "annotator a",
                    payload={**HUMAN_NORM, "source_node_id": "x", "source_span_id": "s"})
    out = apply_decisions(payload, decisions)
    norm = out["norms"][0]
    assert norm["deontic_type"] == "obligation" and norm["action"] == "technically allow for"
    assert norm["extraction_method"] == "human"
    assert norm["extractor_model"] == "human:annotator a"
    assert norm["confidence"] == 1.0
    assert norm["judge_verdict"] == "accepted" and norm["review_status"] == "accepted"
    assert norm["judge_run_id"] is None
    assert norm["human_review"]["provenance"] == "HUMAN_AUTHORED"
    assert payload["norms"][0]["action"] == "old"  # input untouched


def test_apply_decisions_add_appends_a_new_norm():
    payload = {"norms": []}
    decisions = {}
    record_decision(decisions, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "the unit holds an obligation", "annotator a", payload=HUMAN_NORM)
    out = apply_decisions(payload, decisions)
    assert len(out["norms"]) == 1
    added = out["norms"][0]
    assert added["norm_id"] == "norm:eu-ai-act:article-12:paragraph-1:h1"
    assert added["human_review"]["provenance"] == "HUMAN_AUTHORED"
    assert added["extraction_method"] == "human"


def test_apply_decisions_add_refuses_a_duplicate_norm_id():
    payload = {"norms": [{"norm_id": "norm:u:h1", "source_node_id": "u", "source_span_id": "s",
                          "deontic_type": "obligation", "modal": "shall", "actor_explicit": "x",
                          "action": "a", "object": "o", "extraction_method": "human",
                          "extractor_model": "human:b", "confidence": 1.0,
                          "judge_verdict": "accepted", "review_status": "accepted"}]}
    decisions = {}
    record_decision(decisions, "norm:u:h1", "add", "dup", "annotator a", payload=HUMAN_NORM)
    with pytest.raises(ValueError, match="already exists"):
        apply_decisions(payload, decisions)


def test_edges_schema_lists_human_authored():
    import json
    from pathlib import Path
    schema = json.loads((Path(__file__).resolve().parents[2] / "schema" / "json_schemas" / "edges.schema.json").read_text())
    text = json.dumps(schema)
    assert "HUMAN_AUTHORED" in text


# --- review fix round 1: actor_explicit required, replace cannot move a norm ----


def test_record_decision_add_requires_actor_explicit():
    bad = dict(HUMAN_NORM)
    bad.pop("actor_explicit")
    with pytest.raises(ValueError, match="actor_explicit"):
        record_decision({}, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "missing actor_explicit", "annotator a", payload=bad)


def test_record_decision_add_requires_inference_source_when_actor_inferred_is_set():
    bad = {**HUMAN_NORM, "actor_explicit": None, "actor_inferred": "provider"}
    bad.pop("actor_inference_source_node_id", None)
    with pytest.raises(ValueError, match="actor_inference_source_node_id"):
        record_decision({}, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "inferred actor without a source", "annotator a", payload=bad)


def test_apply_decisions_add_defaults_actor_inference_fields_to_none():
    payload = {"norms": []}
    decisions = {}
    bare = dict(HUMAN_NORM)
    bare.pop("actor_inferred", None)
    bare.pop("actor_inference_source_node_id", None)
    record_decision(decisions, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "no inference given", "annotator a", payload=bare)
    out = apply_decisions(payload, decisions)
    added = out["norms"][0]
    assert "actor_inferred" in added and added["actor_inferred"] is None
    assert "actor_inference_source_node_id" in added and added["actor_inference_source_node_id"] is None


def test_apply_decisions_replace_refuses_to_move_a_norm_to_another_span():
    payload = {"norms": [{"norm_id": "norm:x:n1", "source_node_id": "x", "source_span_id": "s",
                          "deontic_type": "permission", "modal": "may", "actor_explicit": None,
                          "action": "old", "object": "old", "extraction_method": "llm_extract_v1",
                          "extractor_model": "gpt-6-astra", "confidence": 0.4,
                          "judge_verdict": "rejected", "review_status": "rejected", "judge_run_id": "r1"}]}
    decisions = {}
    record_decision(decisions, "norm:x:n1", "replace", "the sentence is an obligation", "annotator a",
                    payload={**HUMAN_NORM, "source_node_id": "y", "source_span_id": "s"})
    with pytest.raises(ValueError, match="cannot move"):
        apply_decisions(payload, decisions)


def test_record_decision_add_requires_inference_source_even_for_the_sentinel():
    bad = {**HUMAN_NORM, "actor_explicit": None, "actor_inferred": "unspecified_needs_review"}
    bad.pop("actor_inference_source_node_id", None)
    with pytest.raises(ValueError, match="actor_inference_source_node_id"):
        record_decision({}, "norm:eu-ai-act:article-12:paragraph-1:h1", "add", "sentinel actor without a source", "annotator a", payload=bad)

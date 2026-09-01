"""Tests for the Section 13 critical validation gates."""

import json
from pathlib import Path

from tere4ai.validate_graph.gates import validate_build

ROOT = Path(__file__).resolve().parents[2]
DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"


def _real_dump():
    return json.loads(DUMP.read_text(encoding="utf-8"))


def test_real_build_passes_all_gates():
    report = validate_build(_real_dump())
    assert report.passed, report.failures[:5]
    assert report.stats["orphans"] == 0


def test_orphan_detection():
    dump = _real_dump()
    dump["nodes"].append({"id": "eu-ai-act:article-999", "layer": 1, "type": "Article", "number": 999})
    report = validate_build(dump)
    assert any("G1" in f and "article-999" in f for f in report.failures)


def test_norm_gates():
    dump = _real_dump()
    norms = [
        {"norm_id": "norm:x:n1", "source_span_id": "", "source_node_id": "eu-ai-act:article-9:paragraph-1"},
        {"norm_id": "norm:x:n2", "source_span_id": "span:ok", "source_node_id": "eu-ai-act:recital-12"},
    ]
    report = validate_build(dump, norms=norms)
    assert any("G3" in f and "norm:x:n1" in f for f in report.failures)
    assert any("G5" in f and "norm:x:n2" in f for f in report.failures)


def test_accepted_alignment_needs_two_sided_evidence():
    dump = _real_dump()
    alignments = [
        {
            "id": "align:bad",
            "judge_verdict": "accepted",
            "source_evidence_span_ids": ["span:a"],
            "target_evidence_span_ids": [],
        },
        {
            "id": "align:pending-ok",
            "judge_verdict": "pending",
            "source_evidence_span_ids": [],
            "target_evidence_span_ids": [],
        },
    ]
    report = validate_build(dump, alignments=alignments)
    assert any("G4" in f and "align:bad" in f for f in report.failures)
    assert not any("align:pending-ok" in f for f in report.failures)


def test_version_pin_gate():
    dump = _real_dump()
    for n in dump["nodes"]:
        if n["id"] == "src:omnibus-com-2025-836":
            n["merged_into_base"] = True
    report = validate_build(dump)
    assert any("G6" in f and "silent replacement" in f for f in report.failures)


def test_version_pin_gate_missing_merge_marker():
    # An in-force amending instrument must SAY merged_into_base False; an
    # absent marker is treated as silent replacement, not as innocence.
    dump = _real_dump()
    for n in dump["nodes"]:
        if n["id"] == "src:omnibus-com-2025-836":
            n["legal_status"] = "in_force"
            n.pop("merged_into_base", None)
    report = validate_build(dump)
    assert any("G6" in f and "silent replacement" in f for f in report.failures)

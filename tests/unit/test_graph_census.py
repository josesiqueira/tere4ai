"""Graph census tests (#76): counts derived from dumps, never hand-typed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "graph_census", ROOT / "scripts" / "graph_census.py"
)
graph_census = importlib.util.module_from_spec(_spec)
sys.modules["graph_census"] = graph_census
_spec.loader.exec_module(graph_census)

LAYER1 = {
    "build": {"build_id": "build-x"},
    "nodes": [
        {"id": "a", "type": "Article"},
        {"id": "b", "type": "Article"},
        {"id": "r", "type": "Recital"},
    ],
    "edges": [
        {"edge_id": "e1", "edge_type": "HAS_ARTICLE", "provenance_class": "EXTRACTED_SOURCE"},
        {"edge_id": "e2", "edge_type": "REFERS_TO", "provenance_class": "RESOLVED_DETERMINISTIC"},
    ],
}
NORMS = {
    "build": {"build_id": "build-n"},
    "norms": [
        {"norm_id": "n1", "judge_verdict": "accepted"},
        {"norm_id": "n2", "judge_verdict": "rejected"},
        {"norm_id": "n3", "judge_verdict": "accepted"},
    ],
}
ALIGNMENTS = {
    "assertions": [
        {"assertion_id": "a1", "judge_verdict": "accepted", "relation_type": "supports"},
        {"assertion_id": "a2", "judge_verdict": "rejected", "relation_type": "related_to"},
    ]
}


def test_census_counts():
    data = graph_census.census(LAYER1, NORMS, ALIGNMENTS)
    assert data["layer1_nodes"] == 3
    assert data["layer1_edges"] == 2
    assert data["node_types"] == {"Article": 2, "Recital": 1}
    assert data["provenance_classes"]["EXTRACTED_SOURCE"] == 1
    assert data["norms_total"] == 3
    assert data["norm_verdicts"] == {"accepted": 2, "rejected": 1}
    assert data["assertions_total"] == 2
    assert data["alignment_relations"] == {"supports": 1, "related_to": 1}


def test_census_without_alignments():
    data = graph_census.census(LAYER1, NORMS, None)
    assert "assertions_total" not in data


def test_render_contains_no_hand_typed_numbers():
    data = graph_census.census(LAYER1, NORMS, ALIGNMENTS)
    text = graph_census.render(data, {"layer1.json": "abc"})
    assert "GENERATED" in text
    assert "| Article | 2 |" in text
    assert "build-x" in text
    assert "layer1.json: abc" in text

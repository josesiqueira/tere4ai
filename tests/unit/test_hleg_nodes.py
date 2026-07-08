"""Tests for the deterministic HLEG requirement nodes (Layer 3 targets)."""

import json
from pathlib import Path

from jsonschema import validate

from tere4ai.align_hleg_altai.hleg_nodes import CANONICAL, build_hleg_nodes

ROOT = Path(__file__).resolve().parents[2]
ALIGN_SCHEMA = json.loads(
    (ROOT / "schema" / "json_schemas" / "alignments.schema.json").read_text(encoding="utf-8")
)


def test_exactly_seven_canonical_nodes_in_order():
    nodes = build_hleg_nodes()
    assert [n["id"] for n in nodes] == [cid for cid, _ in CANONICAL]
    assert [n["order"] for n in nodes] == [1, 2, 3, 4, 5, 6, 7]


def test_nodes_validate_against_closed_set_schema():
    for node in build_hleg_nodes():
        validate(node, ALIGN_SCHEMA)


def test_descriptions_and_spans_are_grounded():
    text = (
        ROOT / "data" / "snapshots" / "hleg_ethics_guidelines_2019_en_v1text.txt"
    ).read_text(encoding="utf-8")
    for node in build_hleg_nodes():
        assert len(node["description"]) > 40, node["id"]
        span = node["source_span"]
        sliced = text[span["start"] : span["end"]]
        # the span really contains the section heading and the description start
        assert node["name"].split()[0].lower() in sliced.lower()
        assert node["description"][:30] in " ".join(sliced.split())


def test_deterministic():
    assert build_hleg_nodes() == build_hleg_nodes()

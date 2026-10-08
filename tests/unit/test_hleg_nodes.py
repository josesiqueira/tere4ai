"""The seven HLEGRequirement nodes, each its whole section (B143, DEC-25, spec G D-G75 (5))."""

import json
from pathlib import Path

import pytest
from jsonschema import validate

from tere4ai.align_hleg.hleg_nodes import CANONICAL, build_hleg_nodes
from tere4ai.align_hleg.hleg_source import HlegSourceError, load_pair, read_pair
from tere4ai.align_hleg.hleg_subtopics import build_hleg_subtopics
from tere4ai.align_hleg.pipeline import _quote_found
from tere4ai.ingest import hleg_text as ht

ROOT = Path(__file__).resolve().parents[2]
ALIGN_SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "alignments.schema.json").read_text(encoding="utf-8"))
SECTION_LENGTHS = [3600, 3793, 2231, 2400, 2726, 2037, 2928]  # measured, whitespace collapsed


@pytest.fixture(scope="module")
def pair():
    return load_pair()


def test_exactly_seven_canonical_nodes_in_order(pair):
    nodes = build_hleg_nodes(pair)
    assert [n["id"] for n in nodes] == [cid for cid, _ in CANONICAL]
    assert [n["name"] for n in nodes] == [name for _, name in CANONICAL]
    assert [n["order"] for n in nodes] == [1, 2, 3, 4, 5, 6, 7]
    assert [n["source_span"]["span_id"] for n in nodes] == [f"span:hleg:req{i}" for i in range(1, 8)]


def test_nodes_validate_against_closed_set_schema(pair):
    for node in build_hleg_nodes(pair):
        validate(node, ALIGN_SCHEMA)


def test_each_description_is_its_section_body(pair):
    nodes = build_hleg_nodes(pair)
    assert [len(" ".join(n["description"].split())) for n in nodes] == SECTION_LENGTHS
    for node, head in zip(nodes, pair.record["requirement_headings"]):
        span = node["source_span"]
        assert pair.text[span["start"]:span["end"]] == f"{head['text']}\n\n{node['description']}"
        assert "\n\n\n" not in node["description"] and not node["description"].endswith("\n")


def test_each_span_is_the_whole_section_and_1_7_ends_with_it(pair):
    nodes = build_hleg_nodes(pair)
    for node in nodes:
        span = node["source_span"]
        assert (span["snapshot_file"], span["snapshot_sha256"]) == (ht.TEXT_FILE, pair.text_sha256)
        assert pair.text[span["start"]:].startswith(span["anchor"]) and span["anchor"].startswith(f"1.{node['order']} ")
    for first, second in zip(nodes, nodes[1:]):
        assert pair.text[first["source_span"]["end"]:second["source_span"]["start"]] == "\n\n"
    last = nodes[-1]["source_span"]
    assert last["end"] == len(pair.text.rstrip("\n")) and pair.text[:last["end"]].endswith("vulnerable persons or groups.")
    assert ht.END_HEADING not in pair.text[last["start"]:last["end"]]


def test_every_subtopic_heading_and_first_sentence_is_quotable_from_its_parent(pair):
    """Acceptance 1, first half: LAYER3_STEP2's own check, _quote_found, over every subtopic."""
    parents = {n["id"]: n["description"] for n in build_hleg_nodes(pair)}
    subtopics = build_hleg_subtopics(pair)["nodes"]
    assert len(subtopics) == 23
    for s in subtopics:
        assert _quote_found(f"{s['label']}.", parents[s["hleg_requirement_id"]]), s["id"]
        assert _quote_found(s["description"], parents[s["hleg_requirement_id"]]), s["id"]
    for words in ("Accuracy pertains to an AI system", "human-in-the-loop (HITL)", "Redress. When unjust adverse impact"):
        assert any(_quote_found(words, d) for d in parents.values()), words


def test_a_file_that_differs_from_its_recorded_sha256_is_refused(tmp_path, pair):
    for name in (ht.TEXT_FILE, ht.RECORD_FILE):
        (tmp_path / name).write_bytes((ht.SNAPSHOTS_DIR / name).read_bytes())
    expected = {ht.TEXT_FILE: pair.text_sha256, ht.RECORD_FILE: "0" * 64}
    with pytest.raises(HlegSourceError, match=f"checksum mismatch for {ht.RECORD_FILE}"):
        read_pair(tmp_path, expected)


def test_deterministic(pair):
    assert build_hleg_nodes(pair) == build_hleg_nodes(load_pair())


@pytest.mark.parametrize("content", ["[1, 2]", '"text"', "null", "42", "not json at all"])
def test_a_record_that_is_not_a_json_object_is_refused(tmp_path, content):
    """Final review F2 (M1): a record whose sha256 matches but which is not a JSON
    object is an HlegSourceError, never an AttributeError or a JSONDecodeError."""
    import hashlib

    (tmp_path / ht.TEXT_FILE).write_bytes((ht.SNAPSHOTS_DIR / ht.TEXT_FILE).read_bytes())
    (tmp_path / ht.RECORD_FILE).write_text(content, encoding="utf-8")
    expected = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() for name in (ht.TEXT_FILE, ht.RECORD_FILE)}
    with pytest.raises(HlegSourceError, match="not a JSON object"):
        read_pair(tmp_path, expected)

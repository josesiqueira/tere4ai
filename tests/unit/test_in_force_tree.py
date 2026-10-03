"""The Layer 1 nodes of the Act in force, deleted units and earlier versions (B132, DEC-23).

Spec G D-G68 (1) and (3): an in-force span leaves out the wording the
Omnibus deleted; a deleted unit keeps its id with no text and no span; each
replaced or deleted unit and each composed container keeps its 2024
wording as a UnitVersion whose span is named with the version date.
Frozen files only; no model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tere4ai.mcp_server.spans import resolve_span
from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.consolidated import (
    CONSOLIDATED_REL,
    checked_amendments,
    layer1_nodes,
    read_sources,
    read_trees,
)
from tere4ai.parse_legal_structure.definitions import enrich_with_definitions

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "data" / "snapshots"
MANIFEST = SNAPSHOTS / "MANIFEST.json"
DELETED_WORDS = "To the extent that it is strictly necessary for the purpose of ensuring bias detection"
pytestmark = pytest.mark.skipif(not (SNAPSHOTS / CONSOLIDATED_REL).is_file(), reason="consolidated Formex not frozen")


@pytest.fixture(scope="module")
def dump():
    sources = read_sources(MANIFEST)
    consolidated, baseline, _ = read_trees(sources)
    changes, _ = checked_amendments(sources, consolidated, baseline)
    nodes, edges = layer1_nodes(consolidated, baseline, changes, sources.shas, "build-test")
    dump = {"build": {"build_id": "build-test", "built_at": "x", "tere4ai_version": "x", "snapshots": []},
            "nodes": nodes, "edges": edges}
    return enrich_with_definitions(dump, SNAPSHOTS / "formex", MANIFEST)


@pytest.fixture(scope="module")
def by_id(dump):
    return {n["id"]: n for n in dump["nodes"]}


def test_article_10_span_and_text_leave_out_the_deleted_paragraph_5(dump, by_id):
    """Review focus 1: no repealed wording under the in-force label."""
    span = by_id["eu-ai-act:article-10"]["source_span"]
    assert span["snapshot_file"] == CONSOLIDATED_REL and len(span["exclude"]) == 1
    resolved = resolve_span("span:art_10", dump, SNAPSHOTS)
    assert DELETED_WORDS not in resolved["text"]
    assert "Data and data governance" in resolved["text"]
    assert resolved["exclude"] == span["exclude"]
    assert DELETED_WORDS not in resolve_span("span:eu-ai-act", dump, SNAPSHOTS)["text"]
    earlier = resolve_span("span:010.005@2024-07-12", dump, SNAPSHOTS)
    assert earlier["snapshot_file"] == "formex/L_202401689EN.000101.fmx.xml"
    assert DELETED_WORDS in earlier["text"]


def test_a_deleted_unit_keeps_its_id_and_says_who_deleted_it(by_id):
    node = by_id["eu-ai-act:article-10:paragraph-5"]
    assert node == {
        "id": "eu-ai-act:article-10:paragraph-5", "layer": 1, "type": "Paragraph", "index": "5", "sort_key": 500,
        "amendment": "deleted", "deleted_by": "Regulation (EU) 2026/1744, Article 1, point (9)(b)",
        "deleted_from": "2026-07-27",
    }
    assert amend.is_deleted(node)
    assert amend.deleted_note(node) == (
        "Deleted by Regulation (EU) 2026/1744, Article 1, point (9)(b), from 27 July 2026.")
    for point in "abcdef":
        assert amend.is_deleted(by_id[f"eu-ai-act:article-10:paragraph-5:point-{point}"])
    assert by_id["eu-ai-act:annex-i:section-a:point-1"]["deleted_by"].endswith("point (41)(a)")
    assert by_id["eu-ai-act:article-56:paragraph-6:subparagraph-2"]["deleted_by"].endswith("point (21)")


def test_each_unit_says_what_enacted_its_wording(by_id):
    assert by_id["eu-ai-act:article-9:paragraph-1"]["enacted_by"] == "Regulation (EU) 2024/1689"
    assert by_id["eu-ai-act:article-10:paragraph-1"]["enacted_by"] == "Regulation (EU) 2026/1744, Article 1, point (9)(a)"
    assert by_id["eu-ai-act:article-10:paragraph-1"]["amendment"] == "replaced"
    assert by_id["eu-ai-act:article-10"]["enacted_by"] == "composed"
    assert by_id["eu-ai-act:article-4a"]["amendment"] == "inserted"
    assert by_id["eu-ai-act:annex-xiv"]["enacted_by"] == "Regulation (EU) 2026/1744, Article 1, point (43)"
    assert by_id["eu-ai-act:definition:small-mid-cap-enterprise"]["enacted_by"].endswith("point (4)(b)")


def test_version_spans_carry_the_version_date(dump, by_id):
    """Review focus 2: an earlier version never shares an in-force span id."""
    versions = [n for n in dump["nodes"] if n["type"] == "UnitVersion"]
    assert len(versions) == 130
    version = by_id["version:2024-07-12:eu-ai-act:article-10:paragraph-5"]
    assert {k: version[k] for k in ("unit_id", "unit_type", "version_date", "valid_from", "valid_to",
                                    "legal_status", "enacted_by")} == {
        "unit_id": "eu-ai-act:article-10:paragraph-5", "unit_type": "Paragraph", "version_date": "2024-07-12",
        "valid_from": "2024-08-01", "valid_to": "2026-07-26", "legal_status": "superseded",
        "enacted_by": "Regulation (EU) 2024/1689"}
    assert version["source_span"]["span_id"] == "span:010.005@2024-07-12"
    assert by_id["version:2024-07-12:eu-ai-act:article-4:paragraph-1"]["source_span"]["span_id"] == (
        "span:art_4:body@2024-07-12")
    in_force = {n["source_span"]["span_id"] for n in dump["nodes"] if n["type"] != "UnitVersion" and "source_span" in n}
    assert not in_force & {v["source_span"]["span_id"] for v in versions}
    has_version = {(e["from"], e["to"]) for e in dump["edges"] if e["edge_type"] == "HAS_VERSION"}
    assert ("eu-ai-act:article-10", "version:2024-07-12:eu-ai-act:article-10") in has_version
    assert len(has_version) == 130


def test_the_definitions_come_from_the_consolidated_points(by_id):
    definitions = [n for n in by_id.values() if n["type"] == "Definition"]
    assert len(definitions) == 70
    sme = by_id["eu-ai-act:definition:micro-small-and-medium-sized-enterprise"]
    assert sme["source_span"]["snapshot_file"] == CONSOLIDATED_REL
    assert sme["text"].startswith("\N{LEFT SINGLE QUOTATION MARK}micro, small and medium-sized enterprise\N{RIGHT SINGLE QUOTATION MARK} or \N{LEFT SINGLE QUOTATION MARK}SME\N{RIGHT SINGLE QUOTATION MARK} means")


def test_every_node_validates_against_the_node_schema(dump):
    schemas = {name: json.loads((ROOT / "schema" / "json_schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
               for name in ("nodes", "edges")}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    nodes = Draft202012Validator(schemas["nodes"], registry=registry)
    edges = Draft202012Validator(schemas["edges"], registry=registry)
    assert not [e for n in dump["nodes"] for e in nodes.iter_errors(n)][:3]
    assert not [e for x in dump["edges"] for e in edges.iter_errors(x)][:3]

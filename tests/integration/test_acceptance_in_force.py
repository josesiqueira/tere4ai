"""Layer 1 acceptance on the Act in force (B132, DEC-23, spec G D-G68 (4)).

The published layer1.json is the AI Act as amended by the Digital Omnibus.
Its counts follow from the parsed units: 119 articles and 14 annexes, the
recitals unchanged at 180, the rest as asserted below; deleted units and
earlier versions are counted apart, never in the in-force counts; every
difference from the 2024 counts is explained unit by unit by the reviewed
marker list (inserted minus deleted, per unit type). These counts are the
ones spec G passage (b) of D-G68 states.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tere4ai.parse_legal_structure.formex import DOC_FILE, MAIN_BODY_FILE, _annex_order_from_doc
from tere4ai.parse_legal_structure.units import read_formex_2024

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
MARKER_LIST = ROOT / "data" / "amendments" / "omnibus_markers.json"
FORMEX = ROOT / "data" / "snapshots" / "formex"
pytestmark = pytest.mark.skipif(not (LAYER1.is_file() and MARKER_LIST.is_file()), reason="layer1.json not built")

IN_FORCE = {
    "Regulation": 1, "Chapter": 13, "Section": 16, "Article": 119, "Paragraph": 571, "Subparagraph": 91,
    "Point": 521, "Annex": 14, "AnnexItem": 247, "Recital": 180, "Definition": 70, "CrossReference": 515,
}
AS_ENACTED = {"Chapter": 13, "Section": 16, "Article": 113, "Paragraph": 519, "Subparagraph": 63,
              "Point": 467, "Annex": 13, "AnnexItem": 217}


@pytest.fixture(scope="module")
def dump():
    return json.loads(LAYER1.read_text(encoding="utf-8"))


def _in_force(dump) -> Counter:
    return Counter(n["type"] for n in dump["nodes"]
                   if n["layer"] == 1 and n["type"] != "UnitVersion" and n.get("amendment") != "deleted")


def test_the_in_force_counts(dump):
    assert dict(_in_force(dump)) == IN_FORCE


def test_deleted_units_and_earlier_versions_are_counted_apart(dump):
    deleted = Counter(n["type"] for n in dump["nodes"] if n.get("amendment") == "deleted")
    assert deleted == {"Paragraph": 1, "Point": 6, "AnnexItem": 3, "Subparagraph": 1}
    assert sum(1 for n in dump["nodes"] if n["type"] == "UnitVersion") == 130


def test_text_bearing_units_in_force(dump):
    """[T] of spec G passage (j): paragraphs, subparagraphs, points, annex items, recitals."""
    counts = _in_force(dump)
    assert sum(counts[t] for t in ("Paragraph", "Subparagraph", "Point", "AnnexItem", "Recital")) == 1610


def test_every_difference_from_the_2024_counts_is_in_the_marker_list(dump):
    annex_files = _annex_order_from_doc((FORMEX / DOC_FILE).read_text(encoding="utf-8"))
    enacted = Counter(u.type for u in read_formex_2024(FORMEX, MAIN_BODY_FILE, annex_files).units)
    assert dict(enacted) == AS_ENACTED
    types = {n["id"]: n["type"] for n in dump["nodes"]}
    units = json.loads(MARKER_LIST.read_text(encoding="utf-8"))["units"]
    inserted = Counter(types[i] for i in units["inserted"])
    deleted = Counter(types[i] for i in units["deleted"])
    in_force = _in_force(dump)
    for unit_type, count in AS_ENACTED.items():
        assert in_force[unit_type] == count + inserted[unit_type] - deleted[unit_type], unit_type


def test_the_units_spec_g_names_exist(dump):
    by_id = {n["id"]: n for n in dump["nodes"]}
    for unit_id in ("eu-ai-act:article-4a", "eu-ai-act:article-6:paragraph-1a",
                    "eu-ai-act:article-5:paragraph-1:point-ba", "eu-ai-act:annex-xiv",
                    "eu-ai-act:annex-i:section-b:point-21"):
        assert by_id[unit_id]["amendment"] == "inserted", unit_id
    assert by_id["eu-ai-act:article-10:paragraph-5"]["amendment"] == "deleted"
    assert by_id["version:2024-07-12:eu-ai-act:article-10:paragraph-5"]["source_span"]["span_id"] == (
        "span:010.005@2024-07-12")


def test_coverage_report_accepts_the_amended_structure(dump):
    from tere4ai.mcp_server.tools import coverage_report

    answer = coverage_report(dump)["answer"]
    assert all(check["ok"] for check in answer["checks"]), answer["checks"]
    assert answer["expected"]["articles"] == 119 and answer["expected"]["annexes"] == 14
    assert answer["actual"]["paragraphs"] == 571 and answer["actual"]["deleted_units"] == 11
    assert answer["per_chapter_articles"]["I"] == ["1", "2", "3", "4", "4a"]

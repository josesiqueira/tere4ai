"""One unit reader for the 2024 Formex and the consolidated Formex (B132).

Spec G D-G68 (1): Layer 1 is parsed from EUR-Lex's consolidated text in
Formex and every unit is compared with the 2024 act in Formex, so both are
read by one reader (parse_legal_structure/units.py) with one text rule.
Over the 2024 files it must give exactly the ids, span names and offsets the
2024 parse gave. Reads the frozen files only; no model, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tere4ai.parse_legal_structure.formex import (
    DOC_FILE,
    MAIN_BODY_FILE,
    _annex_order_from_doc,
    enrich_with_formex,
)
from tere4ai.parse_legal_structure.parser import parse_snapshot
from tere4ai.parse_legal_structure.subparagraphs import enrich_with_subparagraphs
from tere4ai.parse_legal_structure.units import formex_text, read_consolidated, read_formex_2024

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "data" / "snapshots"
FORMEX = SNAPSHOTS / "formex"
CONSOLIDATED = FORMEX / "CL2024R1689EN0010010.0001.xml"
CONSOLIDATED_REL = "formex/CL2024R1689EN0010010.0001.xml"
HTML = SNAPSHOTS / "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"
pytestmark = pytest.mark.skipif(not CONSOLIDATED.is_file(), reason="consolidated Formex not frozen")
UNIT_TYPES = {"Chapter", "Section", "Article", "Paragraph", "Subparagraph", "Point", "Annex", "AnnexItem"}


@pytest.fixture(scope="module")
def baseline():
    annex_files = _annex_order_from_doc((FORMEX / DOC_FILE).read_text(encoding="utf-8"))
    return read_formex_2024(FORMEX, MAIN_BODY_FILE, annex_files).by_id()


@pytest.fixture(scope="module")
def consolidated():
    return read_consolidated(CONSOLIDATED, CONSOLIDATED_REL).by_id()


def test_over_the_2024_files_the_reader_gives_the_2024_parse_ids_and_spans(baseline):
    """The equivalence that keeps every span name of an unchanged unit (D-G68 (1))."""
    manifest = SNAPSHOTS / "MANIFEST.json"
    old = enrich_with_subparagraphs(enrich_with_formex(parse_snapshot(HTML), FORMEX, manifest), FORMEX, manifest)
    old_units = {n["id"]: n for n in old["nodes"] if n["type"] in UNIT_TYPES}
    assert set(old_units) == set(baseline)
    assert len(baseline) == 1421
    for unit_id, node in old_units.items():
        assert node["source_span"]["span_id"] == baseline[unit_id].span_name, unit_id
        if node["source_span"]["snapshot_file"].startswith("formex/"):
            span = node["source_span"]
            assert (span["start"], span["end"]) == (baseline[unit_id].start, baseline[unit_id].end), unit_id


def test_inserted_units_take_the_acts_numbers(consolidated):
    article = consolidated["eu-ai-act:article-4a"]
    assert (article.number, article.sort_key, article.span_name) == ("4a", 401, "span:art_4a")
    assert article.title == "Processing of special categories of personal data for bias detection and correction"
    paragraph = consolidated["eu-ai-act:article-5:paragraph-1a"]
    assert (paragraph.index, paragraph.sort_key, paragraph.span_name) == ("1a", 101, "span:005.001a")
    assert consolidated["eu-ai-act:article-4a:paragraph-1"].span_name == "span:004a.001"
    point = consolidated["eu-ai-act:article-5:paragraph-1:point-ba"]
    assert point.span_name == "span:fmx:art_005.parag_001.np_ba"
    assert point.text.startswith("the placing on the market, the putting into service or the use of an AI system")
    assert "eu-ai-act:annex-i:section-b:point-21" in consolidated
    assert consolidated["eu-ai-act:article-75b:paragraph-1"].span_name == "span:art_75b:body"
    assert consolidated["eu-ai-act:article-4:paragraph-3"].span_name == "span:004.003"


def test_the_consolidated_file_keeps_deleted_wording_in_place(consolidated):
    # Article 10(5) and Annex I Section A point 1 are still in the file;
    # amendments.py marks them deleted, the reader only reads them.
    assert "eu-ai-act:article-10:paragraph-5:point-f" in consolidated
    assert consolidated["eu-ai-act:annex-i:section-a:point-1"].text.startswith("Directive 2006/42/EC")


def test_the_counts_of_the_consolidated_units(consolidated):
    counts: dict[str, int] = {}
    for unit in consolidated.values():
        counts[unit.type] = counts.get(unit.type, 0) + 1
    # The 10 units the Omnibus deleted are still in the file and counted here.
    assert counts == {"Chapter": 13, "Section": 16, "Article": 119, "Paragraph": 572, "Subparagraph": 91,
                      "Point": 527, "Annex": 14, "AnnexItem": 250}


def test_annex_titles_in_all_three_layouts(consolidated):
    assert consolidated["eu-ai-act:annex-iii"].title == "High-risk AI systems referred to in Article 6(2)"
    assert consolidated["eu-ai-act:annex-x"].title == (
        "Union legislative acts on large-scale IT systems in the area of Freedom, Security and Justice")
    assert consolidated["eu-ai-act:annex-xiv"].title.startswith("The list of codes, categories and corresponding types")


def test_annex_xiv_nested_headings_and_table_rows(consolidated):
    assert consolidated["eu-ai-act:annex-xiv:point-2:a"].text == "AI systems subject to Annex I"
    assert consolidated["eu-ai-act:annex-xiv:point-2:a"].parent == "eu-ai-act:annex-xiv:point-2"
    row = consolidated["eu-ai-act:annex-xiv:point-2:a:row-1"]
    assert (row.marker, row.text) == ("AIP 0102", "AIP 0102 AI systems subject to point 2 of Section A of Annex I")
    assert row.span_name == "span:fmx:anx_xiv.np_2.np_a.row_1"
    assert consolidated["eu-ai-act:annex-xiv:point-1"].text.startswith(
        "Introduction Conformity assessment of high-risk AI systems pursuant to this Regulation")


def test_the_text_rule():
    xml = ('<P>the <QUOT.START CODE="2018" ID="Q1"/>AI system<QUOT.END CODE="2019" ID="Q2"/> of '
           '<DATE ISO="20240613">13 June 2024</DATE> (<REF.DOC.OJ>OJ L 1</REF.DOC.OJ>), greater than 10'
           '<HT TYPE="SUP">25</HT>.<NOTE NOTE.ID="E1"><P>A footnote.</P></NOTE> Council<?PAGE NO="3"?>.</P>')
    assert formex_text(xml, 0, len(xml)) == (
        "the \N{LEFT SINGLE QUOTATION MARK}AI system\N{RIGHT SINGLE QUOTATION MARK} of 13 June 2024 (OJ L 1), greater than 10 25. Council.")
    assert formex_text(xml, 0, len(xml), [(xml.index("of "), xml.index("("))]) == (
        "the \N{LEFT SINGLE QUOTATION MARK}AI system\N{RIGHT SINGLE QUOTATION MARK} (OJ L 1), greater than 10 25. Council.")


def test_unchanged_paragraph_text_is_identical_in_both_files(baseline, consolidated):
    for unit_id in ("eu-ai-act:article-9:paragraph-1", "eu-ai-act:article-14:paragraph-4",
                    "eu-ai-act:article-5:paragraph-2", "eu-ai-act:annex-iii:point-5:b"):
        assert consolidated[unit_id].text == baseline[unit_id].text, unit_id
    assert "\N{LEFT SINGLE QUOTATION MARK}real-time\N{RIGHT SINGLE QUOTATION MARK}" in consolidated["eu-ai-act:article-5:paragraph-2"].text

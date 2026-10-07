"""Checks C0 to C4 of the derived HLEG text against the official PDF (B143, DEC-25, spec G D-G75 (3)).

The mock data of the negative tests is a copy of the PDF's facts with one
element retagged, removed or given other characters, or the derived files
with one byte changed. No model, no network.
"""

from __future__ import annotations

import collections
import copy
import json

import pytest
from tests.unit.test_hleg_text import element_starting

from tere4ai.ingest import hleg_checks as hc
from tere4ai.ingest import hleg_text as ht


@pytest.fixture(scope="module")
def pdf_bytes():
    return ht.read_checked(ht.DEFAULT_MANIFEST, ht.PDF_FILE)


@pytest.fixture(scope="module")
def facts(pdf_bytes):
    return ht.read_pdf(pdf_bytes)


@pytest.fixture(scope="module")
def frozen():
    text = ht.read_checked(ht.DEFAULT_MANIFEST, ht.TEXT_FILE)
    record = ht.read_checked(ht.DEFAULT_MANIFEST, ht.RECORD_FILE)
    return text, record, text.decode("utf-8"), json.loads(record)


@pytest.fixture(scope="module")
def readings(pdf_bytes):
    return hc.pypdf_pages(pdf_bytes)


@pytest.fixture(scope="module")
def reviewed():
    return json.loads((ht.SNAPSHOTS_DIR / ht.EXCLUSIONS_FILE).read_text(encoding="utf-8"))


def _c2(facts, readings, reviewed):
    text, record = ht.derive_from(facts)
    return hc.check_c2(text, record, readings[0], reviewed, hc.body_bottoms(facts))


def test_c0_passes_on_the_frozen_files(facts, frozen):
    assert hc.check_c0(frozen[0], frozen[1], facts) == []


def test_c0_reports_the_first_difference_of_an_altered_text(facts, frozen):
    altered = frozen[0].replace(b"Fundamental rights.", b"Fundamental right.", 1)
    failures = hc.check_c0(altered, frozen[1], facts)
    assert failures and failures[0].startswith("C0 ") and ht.TEXT_FILE in failures[0] and "byte" in failures[0]


def test_c0_reports_the_first_difference_when_the_libraries_differ(facts, frozen):
    record = json.loads(frozen[1])
    record["libraries"]["pdfplumber"] = "0.11.9"
    failures = hc.check_c0(frozen[0], ht.record_bytes(record), facts)
    assert failures and ht.RECORD_FILE in failures[0]


def test_c1_finds_every_stretch_in_pypdfs_text_of_its_page(frozen, readings):
    _, _, text, record = frozen
    assert len(hc.stretches(text, record)) == 52  # measured
    assert hc.check_c1(text, record, readings[0]) == []


def test_c1_names_the_page_and_offset_of_a_stretch_pypdf_does_not_read(frozen, readings):
    _, _, text, record = frozen
    altered = text.replace("Human oversight helps", "Human oversight help", 1)
    failures = hc.check_c1(altered, record, readings[0])
    assert failures and failures[0].startswith("C1 page 18, offset ")


def test_c2_leaves_nothing_on_any_page_and_the_exclusions_are_the_reviewed_ones(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    assert record["exclusions"] == reviewed and len(reviewed) == 39
    assert collections.Counter(i["kind"] for i in reviewed) == {
        "footnote": 15, "removed_marker": 15, "page_number": 6, "outside_section": 3}
    assert hc.check_c2(text, record, readings[0], reviewed, hc.body_bottoms(facts)) == []


def test_each_exclusion_passes_the_test_of_its_kind(frozen, reviewed, facts):
    _, _, _, record = frozen
    bottoms = hc.body_bottoms(facts)
    assert [f for item in reviewed for f in hc.kind_failures(item, record, bottoms, reviewed)] == []
    pages = {i["page"]: i["text"] for i in reviewed if i["kind"] == "page_number"}
    assert pages == {17: "15", 18: "16", 19: "17", 20: "18", 21: "19", 22: "20"}


def test_a_body_paragraph_tagged_as_a_footnote_fails_c2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    element_starting(mock, 19, "Accuracy.").type = "Note"
    failures = _c2(mock, readings, reviewed)
    assert any(f.startswith("C2 page 19, top ") and "not in the reviewed list" in f and "Accuracy." in f for f in failures)


def test_a_body_paragraph_tagged_as_an_artifact_fails_c2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    target = element_starting(mock, 19, "Accuracy.")
    for element, _note, _skipped in ht.walk(mock.tree):
        element.children = [c for c in element.children if c is not target]
    failures = _c2(mock, readings, reviewed)
    assert any(f.startswith("C2 page 19, top ") and "exclusion not in the reviewed list: " in f for f in failures)


def test_a_page_number_left_in_a_paragraph_fails_c2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    paragraph = element_starting(mock, 19, "Reliability and Reproducibility.")
    for c in mock.chars[19]:
        if c.get("mcid") is None and c["text"].strip():  # the page number "17", an artifact
            c["mcid"] = paragraph.mcids[0]
    failures = _c2(mock, readings, reviewed)
    assert any("page 19" in f and "page_number" in f for f in failures)


def test_a_reviewed_exclusion_the_derivation_did_not_make_fails(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    extra = [*reviewed, {"kind": "footnote", "page": 20, "top": 760.0, "number": "99", "text": "99 Invented."}]
    failures = hc.check_c2(text, record, readings[0], extra, hc.body_bottoms(facts))
    assert any(f.startswith("C2 page 20, top 760.0: reviewed exclusion the derivation did not make") for f in failures)


def _kind(item, frozen, facts, items=None):
    record = frozen[3]
    return hc.kind_failures(item, record, hc.body_bottoms(facts), items if items is not None else record["exclusions"])


def _item(reviewed, kind, page):
    return copy.deepcopy(next(i for i in reviewed if i["kind"] == kind and i["page"] == page))


def test_a_footnote_with_no_removed_marker_in_the_body_of_its_page_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "footnote", 19)
    item["number"], item["text"] = "99", "99 " + item["text"].split(" ", 1)[1]
    assert _kind(item, frozen, facts) == [
        f"C2 page 19, top {item['top']}: footnote 99 has no removed marker in the body of page 19"]


def test_a_footnote_above_the_footnote_area_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "footnote", 19)
    bottom = hc.body_bottoms(facts)[19]
    item["top"] = bottom - 1.0
    assert _kind(item, frozen, facts) == [
        f"C2 page 19, top {item['top']}: footnote {item['number']} is not below the page's last body line ({bottom})"]


def test_a_page_number_that_is_not_the_printed_one_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "page_number", 19)
    item["text"] = "18"
    assert _kind(item, frozen, facts) == [
        f"C2 page 19, top {item['top']}: '18' is not the printed page number 17 below the body"]


def test_text_outside_the_section_on_a_page_inside_it_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "outside_section", 17)
    item["page"] = 19
    assert _kind(item, frozen, facts) == [
        f"C2 page 19, top {item['top']}: text outside the section on a page inside it: {item['text'][:40]!r}"]


def test_a_stretch_pypdf_reads_that_is_not_in_the_derived_text_leaves_a_residue_on_its_page(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    stretch = next(s for s in hc.stretches(text, record) if s.page == 20 and len(s.text) > 100)
    word = stretch.text.split()[0]
    blanked = stretch.text.replace(word, " " * len(word), 1)  # same length, so every offset holds
    altered = text[:stretch.start] + blanked + text[stretch.end:]
    assert altered != text
    failures = hc.check_c2(altered, record, readings[0], reviewed, hc.body_bottoms(facts))
    assert any(f.startswith("C2 page 20: pypdf reads ") and f.endswith(", which is neither derived nor excluded")
               for f in failures)

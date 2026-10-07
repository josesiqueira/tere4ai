"""The HLEG text derived from the Guidelines' official PDF (B143, DEC-25, spec G D-G75 (1) and (2)).

Reads the frozen PDF only; no model, no network. The mock data of the
negative tests is a copy of the PDF's facts with one element retagged or one
character resized.
"""

from __future__ import annotations

import collections
import copy
import hashlib
import json
import re
import subprocess
import sys

import pytest

from tere4ai.ingest import hleg_text as ht

PDF_SHA = "ad76062612b92522f10d02c7239e4e6e5a159af779c657fdd34a98c23984e63e"
SUBTOPIC_LABELS = [
    "Fundamental rights", "Human agency", "Human oversight",
    "Resilience to attack and security", "Fallback plan and general safety", "Accuracy",
    "Reliability and Reproducibility",
    "Privacy and data protection", "Quality and integrity of data", "Access to data",
    "Traceability", "Explainability", "Communication",
    "Avoidance of unfair bias", "Accessibility and universal design", "Stakeholder Participation",
    "Sustainable and environmentally friendly AI", "Social impact", "Society and Democracy",
    "Auditability", "Minimisation and reporting of negative impacts", "Trade-offs", "Redress",
]
SECTION_LENGTHS = [3600, 3793, 2231, 2400, 2726, 2037, 2928]  # measured, whitespace collapsed


@pytest.fixture(scope="module")
def facts():
    return ht.read_pdf(ht.read_checked(ht.DEFAULT_MANIFEST, ht.PDF_FILE))


@pytest.fixture(scope="module")
def derived(facts):
    return ht.derive_from(facts)


def _entries():
    return ht.manifest_entries(ht.DEFAULT_MANIFEST)


def element_starting(facts, page, prefix):
    """The structure element on `page` whose characters read as `prefix` first."""
    by_mcid = collections.defaultdict(list)
    for c in facts.chars[page]:
        by_mcid[c.get("mcid")].append(c)
    for element, _note, _skipped in ht.walk(facts.tree):
        if element.page == page and element.mcids:
            text = "".join(c["text"] for m in element.mcids for c in by_mcid[m])
            if text.startswith(prefix):
                return element
    raise AssertionError(f"no element on page {page} starts with {prefix!r}")


def test_the_pdf_entry_names_the_publications_office_edition():
    pdf = _entries()[ht.PDF_FILE]
    assert pdf["sha256"] == PDF_SHA and pdf["manifestation"] == "pdf-official"
    assert pdf["cellar_work_uuid"] == "d3988569-0434-11ea-8c1f-01aa75ed71a1"
    assert pdf["cellar_item_uri"].endswith("d3988569-0434-11ea-8c1f-01aa75ed71a1.0004.03/DOC_1")
    assert (pdf["isbn"], pdf["doi"], pdf["catalogue_number"]) == ("978-92-76-11998-2", "10.2759/346720", "KK-02-19-841-EN-N")
    assert pdf["retrieval_method"] == f"GET {pdf['cellar_item_uri']}"
    assert "re-checked against the CELLAR item on 2026-10-07" in pdf["notes"]


def test_the_derived_files_are_listed_under_the_guidelines():
    entries = _entries()
    for name, manifestation in ((ht.TEXT_FILE, "derived-text"), (ht.RECORD_FILE, "derivation-record")):
        entry = entries[name]
        assert (entry["source_document"], entry["manifestation"], entry["legal_status"]) == (
            "hleg-ethics-guidelines", manifestation, "non_binding")
        assert len(entry["sha256"]) == 64
    assert PDF_SHA in entries[ht.TEXT_FILE]["notes"] and "hleg_text --write" in entries[ht.TEXT_FILE]["notes"]


def test_the_derivation_reproduces_the_frozen_files_byte_for_byte(derived):
    text, record = derived
    assert text.encode("utf-8") == ht.read_checked(ht.DEFAULT_MANIFEST, ht.TEXT_FILE)
    assert ht.record_bytes(record) == ht.read_checked(ht.DEFAULT_MANIFEST, ht.RECORD_FILE)
    assert record["pdf"] == {"file": ht.PDF_FILE, "sha256": PDF_SHA} and record["derived_file"] == ht.TEXT_FILE
    assert record["libraries"] == {"pdfplumber": "0.11.10", "pdfminer.six": "20260107"}
    assert record["format"] == ht.RECORD_FORMAT and record["rules"] == ht.RULES


def test_the_text_runs_from_1_1_to_before_chapter_ii_section_2(derived):
    text, _ = derived
    assert text.startswith(ht.START_HEADING + "\n\n") and text.endswith("vulnerable persons or groups.\n")
    assert ht.END_HEADING not in text and not text.endswith("\n\n")
    assert "\n\n\n" not in text and "  " not in text


def test_the_record_counts(derived):
    _, record = derived
    kinds = collections.Counter(p["kind"] for p in record["paragraphs"])
    assert kinds == {"requirement_heading": 7, "paragraph": 30}
    assert [h["order"] for h in record["requirement_headings"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [s["label"] for s in record["subtopic_headings"]] == SUBTOPIC_LABELS
    assert [m["number"] for m in record["markers_removed"]] == [str(n) for n in range(36, 51)]
    assert [(j["from_page"], j["to_page"]) for j in record["page_joins"]] == [(17, 18), (18, 19), (20, 21), (21, 22)]
    assert record["hyphen_joins"] == [{"page": 18, "word": "human-in-the-loop"}, {"page": 20, "word": "non-transparent"}]
    assert collections.Counter(e["kind"] for e in record["exclusions"]) == {
        "footnote": 15, "removed_marker": 15, "page_number": 6, "outside_section": 3}


def test_every_range_of_the_record_points_at_its_text(derived):
    text, record = derived
    for h in record["requirement_headings"]:
        assert text[h["start"]:h["end"]] == h["text"] and text[h["end"]:h["end"] + 2] == "\n\n"
    for s in record["subtopic_headings"]:
        assert text[s["start"]:s["end"] + 1] == s["label"] + "."
    for p in record["paragraphs"]:
        assert "\n" not in text[p["start"]:p["end"]]


def test_each_section_is_whole(derived):
    text, record = derived
    heads = record["requirement_headings"]
    lengths = []
    for i, h in enumerate(heads):
        end = heads[i + 1]["start"] if i + 1 < len(heads) else len(text)
        lengths.append(len(" ".join(text[h["end"]:end].split())))
    assert lengths == SECTION_LENGTHS and sum(lengths) == 19715


def test_no_footnote_marker_page_number_or_lost_hyphen_in_the_text(derived):
    text, record = derived
    headings = {h["text"] for h in record["requirement_headings"]}
    body = "\n".join(line for line in text.split("\n") if line not in headings)
    assert re.findall(r"\d+", body) == [], "the only digits of the text are the seven heading numbers"
    assert not [line for line in text.split("\n") if line.strip().isdigit()]
    for item in record["exclusions"]:
        if item["kind"] == "footnote":
            words = item["text"].split()[1:9]
            assert " ".join(words) not in text, item
    assert "human-in-the-loop (HITL)" in text and "non-transparent" in text
    assert "human-in-theloop" not in text and "nontransparent" not in text


def test_the_derivation_is_deterministic(facts, derived):
    assert ht.derive_from(copy.deepcopy(facts)) == derived


def test_a_small_character_that_is_not_a_footnote_number_stops_the_derivation(facts):
    mock = copy.deepcopy(facts)
    element = element_starting(mock, 20, "This requirement is closely linked")
    letter = next(c for m in element.mcids for c in mock.chars[20] if c.get("mcid") == m and c["text"] == "s")
    letter["size"] *= 0.5
    with pytest.raises(ht.DerivationError, match=r"page 20, element [0-9.]+: small characters 's' are not a footnote number"):
        ht.derive_from(mock)


def test_a_marker_whose_footnote_is_not_a_note_stops_the_derivation(facts):
    mock = copy.deepcopy(facts)
    for element, _note, _skipped in ht.walk(mock.tree):
        if element.type == "Note" and element.page == 18:
            element.type = "Sect"  # the page's footnotes read as body text
    with pytest.raises(ht.DerivationError, match=r"page 18, offset \d+: removed characters '36'"):
        ht.derive_from(mock)


def test_importing_the_file_names_needs_no_pdf_library():
    code = "import sys, tere4ai.ingest.hleg_text; assert not {'pdfplumber', 'pypdf', 'pdfminer'} & set(sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0


def test_write_sets_the_two_checksums_and_refuses_a_missing_entry(tmp_path):
    (tmp_path / ht.PDF_FILE).write_bytes(ht.read_checked(ht.DEFAULT_MANIFEST, ht.PDF_FILE))
    manifest = json.loads(ht.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    keep = [e for e in manifest["snapshots"] if e["file"] in (ht.PDF_FILE, ht.TEXT_FILE, ht.RECORD_FILE)]
    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps({"snapshots": [{**e, "sha256": "pending"} if e["file"] != ht.PDF_FILE else e
                                              for e in keep]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert ht.main(["--write", "--manifest", str(path)]) == 0
    written = {e["file"]: e["sha256"] for e in json.loads(path.read_text(encoding="utf-8"))["snapshots"]}
    for name in (ht.TEXT_FILE, ht.RECORD_FILE):
        assert written[name] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    path.write_text(json.dumps({"snapshots": keep[:1]}, indent=2) + "\n", encoding="utf-8")
    assert ht.main(["--write", "--manifest", str(path)]) == 1

"""Checks HLEG_CHECK0 to HLEG_CHECK4 of the derived HLEG text against the official PDF (B143, DEC-25, spec G D-G75 (3)).

The mock data of the negative tests is a copy of the PDF's facts with one
element retagged, removed or given other characters, or the derived files
with one byte changed. No model, no network.
"""

from __future__ import annotations

import collections
import copy
import json
import re

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


def _hleg2(facts, readings, reviewed):
    text, record = ht.derive_from(facts)
    return hc.check_hleg2(text, record, readings[0], reviewed, hc.body_bottoms(facts))


def test_hleg0_passes_on_the_frozen_files(facts, frozen):
    assert hc.check_hleg0(frozen[0], frozen[1], facts) == []


def test_hleg0_reports_the_first_difference_of_an_altered_text(facts, frozen):
    altered = frozen[0].replace(b"Fundamental rights.", b"Fundamental right.", 1)
    failures = hc.check_hleg0(altered, frozen[1], facts)
    assert failures and failures[0].startswith("HLEG_CHECK0 ") and ht.TEXT_FILE in failures[0] and "byte" in failures[0]


def test_hleg0_reports_the_first_difference_when_the_libraries_differ(facts, frozen):
    record = json.loads(frozen[1])
    record["libraries"]["pdfplumber"] = "0.11.9"
    failures = hc.check_hleg0(frozen[0], ht.record_bytes(record), facts)
    assert failures and ht.RECORD_FILE in failures[0]


def test_hleg1_finds_every_stretch_in_pypdfs_text_of_its_page(frozen, readings):
    _, _, text, record = frozen
    assert len(hc.stretches(text, record)) == 52  # measured
    assert hc.check_hleg1(text, record, readings[0]) == []


def test_hleg1_names_the_page_and_offset_of_a_stretch_pypdf_does_not_read(frozen, readings):
    _, _, text, record = frozen
    altered = text.replace("Human oversight helps", "Human oversight help", 1)
    failures = hc.check_hleg1(altered, record, readings[0])
    assert failures and failures[0].startswith("HLEG_CHECK1 page 18, offset ")


def test_hleg2_leaves_nothing_on_any_page_and_the_exclusions_are_the_reviewed_ones(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    assert record["exclusions"] == reviewed and len(reviewed) == 39
    assert collections.Counter(i["kind"] for i in reviewed) == {
        "footnote": 15, "removed_marker": 15, "page_number": 6, "outside_section": 3}
    assert hc.check_hleg2(text, record, readings[0], reviewed, hc.body_bottoms(facts)) == []


def test_each_exclusion_passes_the_test_of_its_kind(frozen, reviewed, facts):
    _, _, _, record = frozen
    bottoms = hc.body_bottoms(facts)
    assert [f for item in reviewed for f in hc.kind_failures(item, record, bottoms, reviewed)] == []
    pages = {i["page"]: i["text"] for i in reviewed if i["kind"] == "page_number"}
    assert pages == {17: "15", 18: "16", 19: "17", 20: "18", 21: "19", 22: "20"}


def test_a_body_paragraph_tagged_as_a_footnote_fails_hleg2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    element_starting(mock, 19, "Accuracy.").type = "Note"
    failures = _hleg2(mock, readings, reviewed)
    assert any(f.startswith("HLEG_CHECK2 page 19, top ") and "not in the reviewed list" in f and "Accuracy." in f for f in failures)


def test_a_body_paragraph_tagged_as_an_artifact_fails_hleg2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    target = element_starting(mock, 19, "Accuracy.")
    for element, _note, _skipped in ht.walk(mock.tree):
        element.children = [c for c in element.children if c is not target]
    failures = _hleg2(mock, readings, reviewed)
    assert any(f.startswith("HLEG_CHECK2 page 19, top ") and "exclusion not in the reviewed list: " in f for f in failures)


def test_a_page_number_left_in_a_paragraph_fails_hleg2_naming_its_page(facts, readings, reviewed):
    mock = copy.deepcopy(facts)
    paragraph = element_starting(mock, 19, "Reliability and Reproducibility.")
    for c in mock.chars[19]:
        if c.get("mcid") is None and c["text"].strip():  # the page number "17", an artifact
            c["mcid"] = paragraph.mcids[0]
    failures = _hleg2(mock, readings, reviewed)
    assert any("page 19" in f and "page_number" in f for f in failures)


def test_a_reviewed_exclusion_the_derivation_did_not_make_fails(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    extra = [*reviewed, {"kind": "footnote", "page": 20, "top": 760.0, "number": "99", "text": "99 Invented."}]
    failures = hc.check_hleg2(text, record, readings[0], extra, hc.body_bottoms(facts))
    assert any(f.startswith("HLEG_CHECK2 page 20, top 760.0: reviewed exclusion the derivation did not make") for f in failures)


def _kind(item, frozen, facts, items=None):
    record = frozen[3]
    return hc.kind_failures(item, record, hc.body_bottoms(facts), items if items is not None else record["exclusions"])


def _item(reviewed, kind, page):
    return copy.deepcopy(next(i for i in reviewed if i["kind"] == kind and i["page"] == page))


def test_a_footnote_with_no_removed_marker_in_the_body_of_its_page_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "footnote", 19)
    item["number"], item["text"] = "99", "99 " + item["text"].split(" ", 1)[1]
    assert _kind(item, frozen, facts) == [
        f"HLEG_CHECK2 page 19, top {item['top']}: footnote 99 has no removed marker in the body of page 19"]


def test_a_footnote_above_the_footnote_area_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "footnote", 19)
    bottom = hc.body_bottoms(facts)[19]
    item["top"] = bottom - 1.0
    assert _kind(item, frozen, facts) == [
        f"HLEG_CHECK2 page 19, top {item['top']}: footnote {item['number']} is not below the page's last body line ({bottom})"]


def test_a_page_number_that_is_not_the_printed_one_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "page_number", 19)
    item["text"] = "18"
    assert _kind(item, frozen, facts) == [
        f"HLEG_CHECK2 page 19, top {item['top']}: '18' is not the printed page number 17 below the body"]


def test_text_outside_the_section_on_a_page_inside_it_fails_its_kind_test(frozen, reviewed, facts):
    item = _item(reviewed, "outside_section", 17)
    item["page"] = 19
    assert _kind(item, frozen, facts) == [
        f"HLEG_CHECK2 page 19, top {item['top']}: text outside the section on a page inside it: {item['text'][:40]!r}"]


def test_a_stretch_pypdf_reads_that_is_not_in_the_derived_text_leaves_a_residue_on_its_page(frozen, readings, reviewed, facts):
    _, _, text, record = frozen
    stretch = next(s for s in hc.stretches(text, record) if s.page == 20 and len(s.text) > 100)
    word = stretch.text.split()[0]
    blanked = stretch.text.replace(word, " " * len(word), 1)  # same length, so every offset holds
    altered = text[:stretch.start] + blanked + text[stretch.end:]
    assert altered != text
    failures = hc.check_hleg2(altered, record, readings[0], reviewed, hc.body_bottoms(facts))
    assert any(f.startswith("HLEG_CHECK2 page 20: pypdf reads ") and f.endswith(", which is neither derived nor excluded")
               for f in failures)


@pytest.fixture(scope="module")
def rows():
    return json.loads((ht.SNAPSHOTS_DIR / ht.WORD_ROWS_FILE).read_text(encoding="utf-8"))


def _other(frozen, readings, reviewed):
    _, _, _, record = frozen
    return {n: hc.body_words(readings[1][n], n, record, reviewed) for n in ht.PAGES}


def test_hleg3_every_difference_has_its_reviewed_row(frozen, readings, reviewed, rows):
    _, _, text, record = frozen
    failures, used = hc.check_hleg3(text, record, _other(frozen, readings, reviewed), rows)
    assert failures == [] and used == [r["id"] for r in rows] and len(rows) == 13  # measured
    assert all(r["reason"].strip() and r["derived"] != r["other"] for r in rows)


def test_hleg3_is_ordered_and_sees_two_swapped_sentences():
    derived = "It is a part. It is apart."
    record = {"paragraphs": [{"start": 0, "end": len(derived), "pages": [ht.PAGES[0]]}],
              "markers_removed": [], "page_joins": []}
    other = {n: [] for n in ht.PAGES}
    other[ht.PAGES[0]] = "It is apart. It is a part.".split()
    assert sorted(derived.split()) == sorted(other[ht.PAGES[0]]), "the same words, so a set test would pass"
    failures, used = hc.check_hleg3(derived, record, other, [])
    assert failures and failures[0].startswith(f"HLEG_CHECK3 page {ht.PAGES[0]}, offset ") and used == []


def test_a_difference_without_its_row_fails_with_its_location(frozen, readings, reviewed, rows):
    _, _, text, record = frozen
    failures, _ = hc.check_hleg3(text, record, _other(frozen, readings, reviewed), rows[1:])
    assert failures == [f"HLEG_CHECK3 page {rows[0]['page']}, offset {rows[0]['offset']}: derived {rows[0]['derived']} "
                        f"against pypdf {rows[0]['other']}"]


def test_a_row_that_matches_no_difference_fails(frozen, readings, reviewed, rows):
    _, _, text, record = frozen
    moved = [*rows, {**rows[0], "id": "w99", "offset": rows[0]["offset"] + 1}]
    failures, _ = hc.check_hleg3(text, record, _other(frozen, readings, reviewed), moved)
    assert any(f.endswith("reviewed row w99 matches no difference") for f in failures)


@pytest.mark.parametrize("phrase, replacement, glued, page", [
    # the prototype's fault before layout spacing, at footnote marker 47 (HLEG_CHECK1 and HLEG_CHECK2 cannot see it)
    ("social AI systems in all areas", "social AI systemsin all areas", "systemsin", 21),
    ("Like many technologies", "Likemany technologies", "Likemany", 17),
])
def test_a_glued_word_in_the_derived_text_is_a_hleg3_difference(frozen, readings, reviewed, rows, phrase, replacement,
                                                             glued, page):
    _, _, text, record = frozen
    altered = text.replace(phrase, replacement, 1)
    assert glued in altered and altered != text
    failures, _ = hc.check_hleg3(altered, record, _other(frozen, readings, reviewed), rows)
    assert any(f.startswith(f"HLEG_CHECK3 page {page}, offset ") and glued in f for f in failures)


def test_hleg4_passes_and_names_a_missing_heading(frozen):
    _, _, text, record = frozen
    assert hc.check_hleg4(text, record) == []
    broken = text.replace("1.4 Transparency\n", "1.4 Transparence\n", 1)
    assert any(f.startswith("HLEG_CHECK4 the requirement headings are") for f in hc.check_hleg4(broken, record))
    lonely = text.replace("\n\n1.2 Technical", "\n\n17\n\n1.2 Technical", 1)
    assert any(f.startswith("HLEG_CHECK4 line ") and "only digits" in f for f in hc.check_hleg4(lonely, record))


def test_run_hleg_checks_passes_and_returns_the_outcome():
    outcome = hc.run_hleg_checks()
    assert outcome["checks_passed"] == ["HLEG_CHECK0", "HLEG_CHECK1", "HLEG_CHECK2", "HLEG_CHECK3", "HLEG_CHECK4"]
    assert (outcome["paragraphs"], outcome["requirement_headings"], outcome["subtopic_headings"]) == (30, 7, 23)
    assert (outcome["page_joins"], outcome["hyphen_joins"], outcome["markers_removed"]) == (4, 2, 15)
    assert (outcome["exclusions_reviewed"], outcome["stretches_checked"], len(outcome["word_rows_used"])) == (39, 52, 13)
    assert outcome["derived_text"]["file"] == ht.TEXT_FILE and len(outcome["word_rows"]["sha256"]) == 64


@pytest.mark.parametrize("name, check", [(ht.EXCLUSIONS_FILE, "HLEG_CHECK2"), (ht.WORD_ROWS_FILE, "HLEG_CHECK3")])
def test_a_missing_reviewed_file_fails_the_check_that_reads_it(tmp_path, name, check):
    """Review M4: the error names its check and the file, never a bare FileNotFoundError."""
    manifest = json.loads(ht.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    keep = [e for e in manifest["snapshots"] if e["file"] in (ht.PDF_FILE, ht.TEXT_FILE, ht.RECORD_FILE)]
    for entry in keep:
        (tmp_path / entry["file"]).write_bytes((ht.SNAPSHOTS_DIR / entry["file"]).read_bytes())
    for other in (ht.EXCLUSIONS_FILE, ht.WORD_ROWS_FILE):
        if other != name:
            (tmp_path / other).write_bytes((ht.SNAPSHOTS_DIR / other).read_bytes())
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"snapshots": keep}, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(hc.HlegCheckError, match=f"^{check} failed: {check} the reviewed file {name} cannot be read"):
        hc.run_hleg_checks(tmp_path / "MANIFEST.json")


def test_the_check_command_reports_pass_and_fail(tmp_path, capsys):
    assert ht.main(["--check"]) == 0
    assert "HLEG_CHECK0, HLEG_CHECK1, HLEG_CHECK2, HLEG_CHECK3, HLEG_CHECK4 pass" in capsys.readouterr().out
    manifest = json.loads(ht.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["snapshots"]:
        source = ht.SNAPSHOTS_DIR / entry["file"]
        if entry["file"] in (ht.PDF_FILE, ht.TEXT_FILE, ht.RECORD_FILE):
            (tmp_path / entry["file"]).write_bytes(source.read_bytes())
    for name in (ht.EXCLUSIONS_FILE, ht.WORD_ROWS_FILE):
        (tmp_path / name).write_bytes((ht.SNAPSHOTS_DIR / name).read_bytes())
    text = (tmp_path / ht.TEXT_FILE).read_bytes().replace(b"Accuracy pertains", b"Accuracy pertain", 1)
    (tmp_path / ht.TEXT_FILE).write_bytes(text)
    import hashlib
    for entry in manifest["snapshots"]:
        if entry["file"] == ht.TEXT_FILE:
            entry["sha256"] = hashlib.sha256(text).hexdigest()
    keep = [e for e in manifest["snapshots"] if e["file"] in (ht.PDF_FILE, ht.TEXT_FILE, ht.RECORD_FILE)]
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"snapshots": keep}, indent=2) + "\n", encoding="utf-8")
    assert ht.main(["--check", "--manifest", str(tmp_path / "MANIFEST.json")]) == 1
    assert "CHECK FAIL HLEG_CHECK0 failed: HLEG_CHECK0 hleg_ethics_guidelines_2019_en_requirements.txt differs" in capsys.readouterr().err


def test_a_word_pypdf_reads_after_the_last_derived_word_is_a_difference_at_the_end():
    derived = "One two three."
    record = {"paragraphs": [{"start": 0, "end": len(derived), "pages": [ht.PAGES[0]]}],
              "markers_removed": [], "page_joins": []}
    other = {n: [] for n in ht.PAGES}
    other[ht.PAGES[0]] = ["One", "two", "three.", "four"]
    failures, _ = hc.check_hleg3(derived, record, other, [])
    assert failures == [f"HLEG_CHECK3 page {ht.PAGES[0]}, offset {len(derived)}: derived [] against pypdf ['four']"]


def test_hleg4_names_a_wrong_subtopic_count_and_a_subtopic_that_does_not_open_its_paragraph(frozen):
    _, _, text, record = frozen
    fewer = {**record, "subtopic_headings": record["subtopic_headings"][1:]}
    assert any(f.startswith("HLEG_CHECK4 22 subtopic headings, not 23") for f in hc.check_hleg4(text, fewer))
    moved = copy.deepcopy(record)
    moved["subtopic_headings"][3]["start"] += 1
    moved["subtopic_headings"][3]["end"] += 1
    assert any(f.startswith(f"HLEG_CHECK4 offset {moved['subtopic_headings'][3]['start']}: subtopic heading")
               for f in hc.check_hleg4(text, moved))


def test_an_unparsable_reviewed_file_fails_the_check_that_reads_it(tmp_path):
    (tmp_path / "rows.json").write_text("[not json", encoding="utf-8")
    with pytest.raises(hc.HlegCheckError, match="^HLEG_CHECK3 failed: HLEG_CHECK3 the reviewed file rows.json cannot be read"):
        hc._reviewed_file(tmp_path, "rows.json", "HLEG_CHECK3")


def test_a_missing_library_names_its_check(monkeypatch):
    def refuse(_):
        raise ImportError("No module named 'pdfplumber'")

    monkeypatch.setattr(ht, "read_pdf", refuse)
    with pytest.raises(hc.HlegCheckError, match=r"^HLEG_CHECK0 failed: HLEG_CHECK0 the hleg extra is not installed"):
        hc.run_hleg_checks()
    monkeypatch.undo()
    monkeypatch.setattr(hc, "pypdf_pages", refuse)
    with pytest.raises(hc.HlegCheckError, match=r"^HLEG_CHECK1 failed: HLEG_CHECK1 the hleg extra is not installed"):
        hc.run_hleg_checks()


def test_a_row_at_another_offset_does_not_cover_the_difference(frozen, readings, reviewed, rows):
    _, _, text, record = frozen
    shifted = [{**rows[0], "offset": rows[0]["offset"] + 1}, *rows[1:]]
    failures, used = hc.check_hleg3(text, record, _other(frozen, readings, reviewed), shifted)
    assert any(f.startswith(f"HLEG_CHECK3 page {rows[0]['page']}, offset {rows[0]['offset']}: derived") for f in failures)
    assert any(f.endswith("reviewed row w01 matches no difference") for f in failures) and "w01" not in used


def _copy_snapshots(tmp_path, rows=None):
    """The manifest's three files and the two reviewed files in tmp_path; rows replaces the rows file."""
    manifest = json.loads(ht.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    keep = [e for e in manifest["snapshots"] if e["file"] in (ht.PDF_FILE, ht.TEXT_FILE, ht.RECORD_FILE)]
    for entry in keep:
        (tmp_path / entry["file"]).write_bytes((ht.SNAPSHOTS_DIR / entry["file"]).read_bytes())
    (tmp_path / ht.EXCLUSIONS_FILE).write_bytes((ht.SNAPSHOTS_DIR / ht.EXCLUSIONS_FILE).read_bytes())
    content = json.dumps(rows) if rows is not None else (ht.SNAPSHOTS_DIR / ht.WORD_ROWS_FILE).read_text(encoding="utf-8")
    (tmp_path / ht.WORD_ROWS_FILE).write_text(content, encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(json.dumps({"snapshots": keep}, indent=2) + "\n", encoding="utf-8")
    return tmp_path / "MANIFEST.json"


def test_run_hleg_checks_stops_at_hleg3_when_a_row_is_missing(tmp_path, rows):
    manifest = _copy_snapshots(tmp_path, rows=rows[1:])
    with pytest.raises(hc.HlegCheckError, match=r"^HLEG_CHECK3 failed: HLEG_CHECK3 page 18, offset 2377: derived \['as'\]") as raised:
        hc.run_hleg_checks(manifest)
    assert raised.value.check == "HLEG_CHECK3"


def test_run_hleg_checks_stops_at_hleg4_when_the_structure_check_fails(tmp_path, monkeypatch):
    manifest = _copy_snapshots(tmp_path)
    monkeypatch.setattr(hc, "check_hleg4", lambda text, record: ["HLEG_CHECK4 line 1 is only digits: '7'"])
    with pytest.raises(hc.HlegCheckError, match=r"^HLEG_CHECK4 failed: HLEG_CHECK4 line 1") as raised:
        hc.run_hleg_checks(manifest)
    assert raised.value.check == "HLEG_CHECK4"


def test_a_file_that_differs_from_its_manifest_digest_fails_hleg0(tmp_path):
    manifest = _copy_snapshots(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    source = json.loads(ht.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    digests = {e["file"]: e["sha256"] for e in source["snapshots"]}
    for entry in data["snapshots"]:
        entry["sha256"] = digests[entry["file"]]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / ht.TEXT_FILE).write_bytes((tmp_path / ht.TEXT_FILE).read_bytes() + b"x")
    with pytest.raises(hc.HlegCheckError, match=r"^HLEG_CHECK0 failed: HLEG_CHECK0 ") as raised:
        hc.run_hleg_checks(manifest)
    assert raised.value.check == "HLEG_CHECK0"


def test_no_check_name_is_a_letter_plus_a_number():
    src = open(hc.__file__, encoding="utf-8").read()
    assert not re.search(r'"C[0-4]"', src)  # HlegCheckError("C0"), _reviewed_file(..., "C2"), the ("C1", check_c1(...)) tuples
    assert not re.search(r'"C[0-4] ', src)  # the failure-string prefixes
    assert re.search(r'"checks_passed": \["HLEG_CHECK0"', src)

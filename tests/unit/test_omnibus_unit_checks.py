"""Every unit checked against the Official Journal wording of the act that enacted it (B132, DEC-23).

Spec G D-G68 (1): the consolidated text has no legal effect, so before the
parse completes an unchanged unit equals the 2024 unit, Formex against
Formex; a replaced or inserted unit is in the Omnibus quotation of its
point; a partly amended unit is checked as composed; Annex XIV equals the
Omnibus annex member file; every Omnibus quotation is applied somewhere;
any other difference stops the parse unless a reviewed row covers it.
Frozen files, mutated in memory; no model.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.consolidated import (
    CONSOLIDATED_REL,
    OMNIBUS_MAIN_REL,
    checked_amendments,
    read_sources,
    read_trees,
)
from tere4ai.parse_legal_structure.units import read_text_units

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"
pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "snapshots" / CONSOLIDATED_REL).is_file(), reason="consolidated Formex not frozen"
)


@pytest.fixture(scope="module")
def world():
    sources = read_sources(MANIFEST)
    consolidated, baseline, _ = read_trees(sources)
    return sources, consolidated, baseline


def _units(world, text=None, rows=None, omnibus=None):
    sources, consolidated, baseline = world
    if text is not None:
        consolidated = read_text_units(text, CONSOLIDATED_REL)
    rows = rows if rows is not None else amend.load_exceptions()
    cons_text = consolidated.texts[CONSOLIDATED_REL]
    changes = amend.derive_changes(consolidated, baseline, amend.read_markers(cons_text), rows)
    quotations = amend.read_quotations(omnibus if omnibus is not None else sources.read(OMNIBUS_MAIN_REL))
    return amend.check_units(changes, consolidated, baseline, cons_text, quotations, rows)


def test_every_unit_passes_and_every_row_is_needed(world):
    sources, consolidated, baseline = world
    changes, rows = checked_amendments(sources, consolidated, baseline)  # raises on any failure
    assert changes.used_rows == {r["id"] for r in rows}


def test_an_unmarked_change_in_an_unchanged_paragraph_stops_the_parse(world):
    """Review focus 3: the consolidated text is checked, not trusted."""
    text = world[1].texts[CONSOLIDATED_REL]
    start = text.index('IDENTIFIER="009.001"')
    at = text.index("risk management system", start)
    mutated = text[:at] + "risk-management system" + text[at + len("risk management system"):]
    assert _units(world, text=mutated) == [
        "eu-ai-act:article-9:paragraph-1: no marker touches it and its text differs from the 2024 text"]


def test_an_omnibus_quotation_left_unapplied_is_found(world):
    """The reverse check: an amendment the Publications Office failed to apply."""
    text = world[1].texts[CONSOLIDATED_REL]
    # Drop point (1)'s marker and put the 2024 point (g) back: the quotation is applied nowhere.
    old_g = world[2].by_id()["eu-ai-act:article-1:paragraph-2:point-g"].text
    match = re.search(r'<\?CLG\.MDFO ID="O001001M001000"[^?]*\?>(.*?)<\?CLG\.MDFC[^?]*IDREF="O001001M001000"[^?]*\?>',
                      text, re.S)
    start = match.group(1).index("<TXT>") + len("<TXT>")
    end = match.group(1).index("</TXT>")
    item = match.group(1)[:start] + old_g + match.group(1)[end:]
    mutated = text[: match.start()] + item + text[match.end():]
    failures = _units(world, text=mutated)
    assert "the Omnibus quotation of point (1) is in no marked range (left unapplied?)" in failures


def test_a_composed_paragraph_keeps_its_unmarked_rest(world):
    """Article 5(1) gained points (ba) and (bb); the rest must be the 2024 text."""
    text = world[1].texts[CONSOLIDATED_REL]
    start = text.index('IDENTIFIER="005.001"')
    at = text.index("subliminal techniques", start)
    mutated = text[:at] + "hidden techniques" + text[at + len("subliminal techniques"):]
    failures = _units(world, text=mutated)
    assert any(f.startswith("eu-ai-act:article-5:paragraph-1: its unmarked text") for f in failures)
    assert any(f.startswith("eu-ai-act:article-5:paragraph-1:point-a: no marker touches it") for f in failures)


def test_an_exception_row_no_check_needs_stops_the_parse(world, tmp_path):
    import json

    sources, consolidated, baseline = world
    payload = json.loads(amend.DEFAULT_EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    payload["rows"].append({"id": "E10", "kind": "unmarked_title", "unit_id": "eu-ai-act:article-2",
                            "baseline": "Scope", "consolidated": "Scope", "reason": "a stale row"})
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(amend.AmendmentCheckError) as error:
        checked_amendments(sources, consolidated, baseline, exceptions_path=exceptions)
    assert error.value.failures == ["exception row E10 (unmarked_title) was not needed by any check: review it"]


def test_without_the_title_row_article_1_stops_the_parse(world):
    rows = [r for r in amend.load_exceptions() if r["id"] != "E8"]
    assert "eu-ai-act:article-1: its title changed and no marker over the heading enacts it" in _units(world, rows=rows)


def test_a_failed_check_raises_with_every_failure(world, tmp_path):
    sources, consolidated, baseline = world
    inventory = tmp_path / "inventory.md"
    inventory.write_text(amend.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8").replace(
        "- Point (9)(b):", "- Point (99)(z):"), encoding="utf-8")
    with pytest.raises(amend.AmendmentCheckError) as error:
        checked_amendments(sources, consolidated, baseline, inventory_path=inventory)
    assert "docs/omnibus_amendments.md has no entry for point (9)(b)" in error.value.failures


def _mutated(world, anchor: str, old: str, new: str) -> str:
    text = world[1].texts[CONSOLIDATED_REL]
    at = text.index(old, text.index(anchor))
    return text[:at] + new + text[at + len(old):]


def test_a_changed_replaced_unit_fails_at_unit_level(world):
    mutated = _mutated(world, 'IDENTIFIER="010.001"', "whenever such data sets are used", "whenever such data sets are kept")
    assert "eu-ai-act:article-10:paragraph-1: not in the Omnibus quotation of point (9)(a)" in _units(world, text=mutated)


def test_a_changed_inserted_unit_fails_at_unit_level(world):
    mutated = _mutated(world, 'IDENTIFIER="004A.001"', "To the extent strictly necessary", "To the extent necessary")
    assert "eu-ai-act:article-4a:paragraph-1: not in the Omnibus quotation of point (6)" in _units(world, text=mutated)


def test_a_changed_annex_opening_sentence_stops_the_parse(world):
    """Wording a container holds outside its units (Annex III's opening sentence)
    is inside the Annex span resolve_span serves, so it is checked too."""
    mutated = _mutated(world, "<P>ANNEX III</P>", "listed in any of", "listed in some of")
    assert _units(world, text=mutated) == [
        "eu-ai-act:annex-iii: its wording outside its units differs from the 2024 text"]


def test_without_the_nested_marks_row_the_quotations_do_not_match(world):
    """Row E9 is reviewed, not a hidden normalisation: without it the Omnibus's
    double marks inside its quotations do not read as the Act's single marks."""
    rows = [r for r in amend.load_exceptions() if r["id"] != "E9"]
    failures = _units(world, rows=rows)
    assert "eu-ai-act:article-3:paragraph-1:point-14a: not in the Omnibus quotation of point (4)(b)" in failures
    assert "the Omnibus quotation of point (7)(a) is in no marked range (left unapplied?)" in failures


def test_a_nested_marks_row_with_other_marks_is_not_used(world, tmp_path):
    import json

    sources, consolidated, baseline = world
    payload = json.loads(amend.DEFAULT_EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["id"] == "E9":
            row["omnibus"], row["consolidated"] = "x y", "x y"
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(amend.AmendmentCheckError) as error:
        checked_amendments(sources, consolidated, baseline, exceptions_path=exceptions)
    assert "exception row E9 (nested_quotation_marks) was not needed by any check: review it" in error.value.failures
    assert "eu-ai-act:article-5:paragraph-1:point-bb: not in the Omnibus quotation of point (7)(a)" in error.value.failures

"""The Omnibus's changes read from the consolidated text's markers and checked three ways (B132, DEC-23).

Spec G D-G68 (2): 77 markers at 72 points, read per Layer 1 unit, written
as a reviewed file, each checked against the Omnibus text, the 2024 tree
and docs/omnibus_amendments.md; where a marker and the Omnibus disagree the
Omnibus decides through a reviewed row. Frozen files only; no model.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.consolidated import (
    CONSOLIDATED_REL,
    OMNIBUS_ANNEX_REL,
    OMNIBUS_MAIN_REL,
    current_marker_list,
    main,
    marker_list_bytes,
    read_sources,
    read_trees,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"
MARKER_LIST = ROOT / "data" / "amendments" / "omnibus_markers.json"
pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "snapshots" / CONSOLIDATED_REL).is_file(), reason="consolidated Formex not frozen"
)


@pytest.fixture(scope="module")
def world():
    sources = read_sources(MANIFEST)
    consolidated, baseline, _ = read_trees(sources)
    rows = amend.load_exceptions()
    text = consolidated.texts[CONSOLIDATED_REL]
    changes = amend.derive_changes(consolidated, baseline, amend.read_markers(text), rows)
    return sources, consolidated, baseline, rows, text, changes


def _check(world, text=None, rows=None, inventory=None, omnibus=None):
    sources, consolidated, baseline, rows0, text0, _ = world
    text = text if text is not None else text0
    rows = rows if rows is not None else rows0
    if text is not text0:
        from tere4ai.parse_legal_structure.units import read_text_units

        consolidated = read_text_units(text, CONSOLIDATED_REL)
    changes = amend.derive_changes(consolidated, baseline, amend.read_markers(text), rows)
    quotations = amend.read_quotations(omnibus if omnibus is not None else sources.read(OMNIBUS_MAIN_REL))
    inventory = inventory if inventory is not None else amend.read_inventory(amend.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8"))
    return amend.check_markers(changes, consolidated, baseline, text, quotations, inventory, rows,
                               sources.read(OMNIBUS_ANNEX_REL))


def test_the_77_markers_at_72_points(world):
    *_, changes = world
    markers = changes.markers
    assert len(markers) == 77
    assert Counter((m.action, m.level) for m in markers) == {
        ("REPLACED", "STRUCTURE"): 44, ("INSERTED", "STRUCTURE"): 25,
        ("DELETED", "STRUCTURE"): 4, ("REPLACED", "TEXT"): 4,
    }
    assert len({changes.points[m.marker_id] for m in markers}) == 72
    assert amend.point_of_label("AR:1;PT:9;PT:b") == "(9)(b)"
    assert amend.enacted_by("(9)(b)") == "Regulation (EU) 2026/1744, Article 1, point (9)(b)"


def test_every_unit_gets_one_change(world):
    *_, changes = world
    assert Counter(c.amendment for c in changes.changes.values()) == {
        "unchanged": 1291, "inserted": 182, "replaced": 42, "composed": 77, "deleted": 11,
    }
    change = changes.changes["eu-ai-act:article-10:paragraph-5:point-c"]
    assert (change.amendment, change.point) == ("deleted", "(9)(b)")
    assert changes.changes["eu-ai-act:article-10:paragraph-1"].amendment == "replaced"
    assert changes.changes["eu-ai-act:article-10"].amendment == "composed"
    assert changes.changes["eu-ai-act:article-4a"].point == "(6)"
    assert changes.changes["eu-ai-act:article-9:paragraph-1"].amendment == "unchanged"


def test_ranges_over_several_units_part_of_one_and_a_heading(world):
    """Review focus 5: a marker is not one element."""
    *_, changes = world
    by_point = {}
    for marker in changes.markers:
        by_point.setdefault(changes.points[marker.marker_id], []).append(marker.marker_id)
    six = by_point["(8)"][0]
    assert {"eu-ai-act:article-6:paragraph-1a", "eu-ai-act:article-6:paragraph-1b",
            "eu-ai-act:article-6:paragraph-1c"} <= set(changes.inside[six])
    assert {f"eu-ai-act:article-75{x}" for x in "abcd"} <= set(changes.inside[by_point["(32)"][0]])
    intro = by_point["(23)(a)"][0]  # Article 58(1)'s introductory words only
    assert changes.inside[intro] == []
    assert "eu-ai-act:article-58:paragraph-1" in changes.partly[intro]
    heading = by_point["(31)(a)"][0]  # Article 75's heading only
    assert changes.inside[heading] == [] and "eu-ai-act:article-75" in changes.partly[heading]
    # A sub-unit the replacing wording no longer has is deleted by that point.
    gone = changes.changes["eu-ai-act:article-56:paragraph-6:subparagraph-2"]
    assert (gone.amendment, gone.point) == ("deleted", "(21)")
    # A sub-unit the replacing wording adds is inserted by that point.
    assert changes.changes["eu-ai-act:article-25:paragraph-2:point-a"].amendment == "inserted"


def test_the_mislabelled_insertion_follows_the_omnibus(world):
    *_, changes = world
    assert changes.points["O001001M006000"] == "(4)(b)"
    assert changes.changes["eu-ai-act:article-3:paragraph-1:point-14a"].point == "(4)(b)"


def test_every_marker_passes_the_three_checks(world):
    assert _check(world) == []


def test_without_the_label_row_the_mislabelled_insertion_fails(world):
    rows = [r for r in world[3] if r["id"] != "OMNIBUS_EXCEPTION1"]
    failures = _check(world, rows=rows)
    assert "O001001M006000: its wording is not in the Omnibus quotation of point (14)(b)" in failures
    assert "docs/omnibus_amendments.md has no entry for point (14)(b)" in failures


def test_a_point_missing_from_the_inventory_fails(world):
    inventory = amend.read_inventory(amend.DEFAULT_INVENTORY_PATH.read_text(encoding="utf-8"))
    assert inventory["(2)(a)"] == ("replaced", {"2"})
    assert inventory["(32)"] == ("inserted", {"75a", "75b", "75c", "75d"})
    inventory.pop("(9)(b)")
    assert _check(world, inventory=inventory) == ["docs/omnibus_amendments.md has no entry for point (9)(b)"]


def test_a_changed_omnibus_quotation_fails(world):
    sources = world[0]
    omnibus = sources.read(OMNIBUS_MAIN_REL).replace(
        "including start-ups.<QUOT.END", "including start-ups and SMCs.<QUOT.END")
    assert "O001001M001000: its wording is not in the Omnibus quotation of point (1)" in _check(world, omnibus=omnibus)


def test_an_insertion_of_a_unit_the_2024_text_has_fails(world):
    text = world[4]
    # Mark Article 9(1), which the 2024 text has, as inserted by point (9)(a).
    start = text.index('<PARAG IDENTIFIER="009.001">')
    end = text.index("</PARAG>", start) + len("</PARAG>")
    mutated = (text[:start] + '<?CLG.MDFO ID="O001001M999000" ACTION="INSERTED" LEVEL="STRUCTURE" '
               'ACTIVE.LOC="AR:1;PT:9;PT:a"?>' + text[start:end] + '<?CLG.MDFC IDREF="O001001M999000"?>' + text[end:])
    failures = _check(world, text=mutated)
    assert any(f.startswith("O001001M999000 ((9)(a)) inserts units the 2024 text already has") for f in failures)


def test_the_committed_marker_list_is_the_generated_one(world):
    """The reviewed file differs from the markers only through a reviewed regeneration."""
    sources, *_, rows, _, changes = world
    assert MARKER_LIST.read_bytes() == marker_list_bytes(current_marker_list(sources, changes, rows))
    payload = json.loads(MARKER_LIST.read_text(encoding="utf-8"))
    deletion = next(m for m in payload["markers"] if m["marker_id"] == "O001001M013000")
    assert deletion["omnibus_point"] == "(9)(b)"
    assert "eu-ai-act:article-10:paragraph-5" in deletion["units_inside"]
    label = next(m for m in payload["markers"] if m["marker_id"] == "O001001M006000")
    assert (label["marker_label"], label["omnibus_point"], label["exception"]) == ("AR:1;PT:14;PT:b", "(4)(b)", "OMNIBUS_EXCEPTION1")
    assert {k: len(v) for k, v in payload["units"].items()} == {
        "replaced": 42, "inserted": 182, "deleted": 11, "composed": 77}


def test_the_command_reports_the_marker_list_current(capsys):
    assert main(["--check"]) == 0
    assert "marker list is current" in capsys.readouterr().err


def test_every_exception_row_has_a_reason_and_a_known_kind():
    rows = amend.load_exceptions()
    assert [r["id"] for r in rows] == [f"OMNIBUS_EXCEPTION{i}" for i in range(1, 10)]
    assert all(r["reason"].strip() for r in rows)


@pytest.mark.parametrize("action, words", [
    ("DELETED", "deletes units the 2024 text lacks"),
    ("REPLACED", "replaces units the 2024 text lacks"),
])
def test_a_range_over_units_the_2024_text_lacks_fails_check_2(world, action, words):
    # Article 6(1a) to (1c) are inserted by point (8); read the marker as another action.
    text = world[4]
    opening = re.search(r'<\?CLG\.MDFO ID="O001001M011000"[^?]*\?>', text).group(0)
    mutated = text.replace(opening, opening.replace('ACTION="INSERTED"', f'ACTION="{action}"'))
    failures = _check(world, text=mutated)
    assert any(f.startswith(f"O001001M011000 ((8)) {words}") for f in failures), failures[:3]

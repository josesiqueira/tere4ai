"""The Digital Omnibus's changes, read from the consolidated text's markers and checked.

@implements: DEC-01 (partial: the change markers and their checks)
@implements: DEC-12
@grounded_by: REF-02, REF-03, REF-04, REF-05

EUR-Lex's consolidated text of 27 July 2026 (CELEX 02024R1689-20260727)
wraps every change the Omnibus (Regulation (EU) 2026/1744) made in a pair
of processing instructions:

    <?CLG.MDFO ID="O001001M013000" ACTION="DELETED" LEVEL="STRUCTURE"
      ACTIVE.LOC="AR:1;PT:9;PT:b" ...?> ... <?CLG.MDFC IDREF="O001001M013000"?>

ACTIVE.LOC names the Omnibus point: AR:1;PT:9;PT:b is Article 1, point
(9)(b). There are 77 markers at 72 points (44 REPLACED and 25 INSERTED
STRUCTURE, 4 DELETED STRUCTURE, 4 REPLACED TEXT). A marker's range may hold
several units (Article 6(1a) to (1c)), part of one (Article 58(1)'s
introductory words) or an Article heading. derive_changes reads them per
Layer 1 unit (units.py): a unit inside a REPLACED, INSERTED or DELETED
range is replaced, inserted or deleted by that point; a unit inside a
REPLACED range that the 2024 text did not have is inserted by it (Article
25(2)'s new points); a 2024 unit the consolidated text no longer has sits
under a replaced unit and is deleted by the same point (Article 56(6),
second subparagraph); a unit a range touches without holding it whole is
composed; any other unit is unchanged. The Act's own words for the kinds
are used (replaced, inserted, deleted); Akoma Ntoso (REF-03) calls them
substitution, insertion and repeal.

The consolidated text has no legal effect (EUR-Lex: "This text is meant
purely as a documentation tool and has no legal effect"), so every marker
is checked three ways (check_markers, spec G D-G68 (2)): its wording is in
the Omnibus quotation of its point; the units it replaces or deletes exist
in the 2024 text and the units it inserts do not; docs/omnibus_amendments.md
has an entry for its point naming the same Article or Annex and the same
kind of change. Every unit is then checked against the Official Journal
wording of the act that enacted it (check_units, D-G68 (1)): an unchanged
unit equals the 2024 unit of the same id; a replaced or inserted unit is in
the quotation of its point; a composed unit's marked parts are in the
quotation and its unmarked rest equals its 2024 text; Annex XIV equals the
Omnibus annex member file; every quotation of the Omnibus's Article 1 is
in some marked range, so an amendment left unapplied is found; an
unchanged or composed container's wording outside its units (an Article's
number line, an annex's opening sentence, the Section headings inside an
annex) equals its 2024 wording. Quotations the Omnibus nests inside its own
quotation are printed with double marks there and single marks in the
consolidated text; the comparison reads them as equal only through the
reviewed row that says so, and only where a comparison needs it. Any other
difference stops the parse unless a row of the
reviewed exception list (data/amendments/omnibus_exceptions.json) covers
it; a row no check used stops the parse too. Where a marker and the
Omnibus disagree the Omnibus decides, through such a row (the Article
3(14a) and (14b) insertion is marked as point (14)(b); the Omnibus enacts
it in point (4)(b)).

marker_list writes the derived list, every marker with its point, its
action and the units it touches, to data/amendments/omnibus_markers.json, a
reviewed file the parse regenerates and compares (a difference stops it).
Deterministic, no model calls (DEC-01).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure.formex import _child_roots, _El, _find, _parse_xml, _walk
from tere4ai.parse_legal_structure.units import Unit, UnitTree, formex_text

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MARKER_LIST_PATH = _REPO_ROOT / "data" / "amendments" / "omnibus_markers.json"
DEFAULT_EXCEPTIONS_PATH = _REPO_ROOT / "data" / "amendments" / "omnibus_exceptions.json"
DEFAULT_INVENTORY_PATH = _REPO_ROOT / "docs" / "omnibus_amendments.md"

BASE_ACT = "Regulation (EU) 2024/1689"
OMNIBUS_ACT = "Regulation (EU) 2026/1744"
OMNIBUS_IN_FORCE = "2026-07-27"
# The 2024 wording as an earlier version (D-G68 (3)): named by the date of
# its Official Journal publication, as ELI (REF-04) names an act's version;
# in force from the 2024 act's entry into force to the day before the
# Omnibus's.
VERSION_DATE = "2024-07-12"
VERSION_VALID_FROM = "2024-08-01"
VERSION_VALID_TO = "2026-07-26"

TEXT_UNIT_TYPES = frozenset({"Paragraph", "Subparagraph", "Point", "AnnexItem"})
EXCEPTION_KINDS = frozenset({
    "marker_label", "punctuation", "trailing_punctuation", "annex_member", "unmarked_title", "nested_quotation_marks",
})
_MDFO = re.compile(r"<\?CLG\.MDFO ([^?]*)\?>")
_ATTR = re.compile(r'([A-Z.]+)="([^"]*)"')
OPEN_QUOTE, CLOSE_QUOTE = "\N{LEFT SINGLE QUOTATION MARK}", "\N{RIGHT SINGLE QUOTATION MARK}"
_METADATA = re.compile(r"<BIB\.INSTANCE>.*?</BIB\.INSTANCE>", re.S)
_WS = re.compile(r"\s+")
_INVENTORY_ENTRY = re.compile(r"^- Point ((?:\(\d+\))(?:\([a-z]\))?): (.+)$", re.M)
_KIND_WORD = re.compile(r"\b(replaced|inserted|added|deleted)\b")
_KIND_OF_ACTION = {"REPLACED": {"replaced"}, "INSERTED": {"inserted", "added"}, "DELETED": {"deleted"}}
_AMENDMENT_OF_ACTION = {"REPLACED": "replaced", "INSERTED": "inserted", "DELETED": "deleted"}


class AmendmentCheckError(ValueError):
    """A marker or a unit failed a check no reviewed exception row covers."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__(f"{len(failures)} amendment check failures: " + "; ".join(failures[:10]))
        self.failures = failures


@dataclass(frozen=True)
class Marker:
    """One change marker: its attributes and the offsets of its range."""

    marker_id: str
    action: str
    level: str
    label: str
    start: int  # the opening instruction
    inner_start: int  # just past the opening instruction
    inner_end: int  # the closing instruction
    end: int  # just past the closing instruction


@dataclass(frozen=True)
class UnitChange:
    unit_id: str
    amendment: str  # unchanged, replaced, inserted, deleted, composed
    point: str | None  # "(9)(b)" for replaced, inserted, deleted
    marker_ids: tuple[str, ...] = ()


@dataclass
class Amendments:
    """The markers with their points and every unit's change."""

    markers: list[Marker]
    points: dict[str, str]  # marker id -> Omnibus point, after the label rows
    changes: dict[str, UnitChange]
    inside: dict[str, list[str]]  # marker id -> unit ids wholly inside its range
    partly: dict[str, list[str]]  # marker id -> unit ids it touches without holding
    used_rows: set[str] = field(default_factory=set)


def read_markers(text: str) -> list[Marker]:
    """Every CLG.MDFO marker of the consolidated file with its closing CLG.MDFC."""
    markers = []
    for match in _MDFO.finditer(text):
        attrs = dict(_ATTR.findall(match.group(1)))
        closing = re.compile(rf'<\?CLG\.MDFC[^?]*IDREF="{re.escape(attrs["ID"])}"[^?]*\?>')
        close = closing.search(text, match.end())
        if close is None:
            raise AmendmentCheckError([f"marker {attrs['ID']} is never closed"])
        markers.append(Marker(attrs["ID"], attrs["ACTION"], attrs["LEVEL"], attrs.get("ACTIVE.LOC", ""),
                              match.start(), match.end(), close.start(), close.end()))
    return markers


def point_of_label(label: str) -> str:
    """The point an ACTIVE.LOC names: AR:1;PT:9;PT:b -> (9)(b); only Article 1 amends the AI Act."""
    parts = label.split(";")
    if not parts or parts[0] != "AR:1" or len(parts) < 2 or not all(p.startswith("PT:") for p in parts[1:]):
        raise AmendmentCheckError([f"marker location {label!r} is not a point of the Omnibus's Article 1"])
    return "".join(f"({p[3:]})" for p in parts[1:])


def enacted_by(point: str) -> str:
    """The Omnibus point as a citation: (9)(b) -> Regulation (EU) 2026/1744, Article 1, point (9)(b)."""
    return f"{OMNIBUS_ACT}, Article 1, point {point}"


def normalise(text: str) -> str:
    """Whitespace collapsed; nothing else is changed (quotation marks only through a row, _found)."""
    return _WS.sub(" ", text).strip()


def _translated(text: str, row: dict[str, Any]) -> str:
    """The text with the row's Omnibus marks read as its consolidated marks (double marks as single ones)."""
    return text.translate(str.maketrans(dict(zip(row["omnibus"].split(), row["consolidated"].split(), strict=True))))


def _found(wording: str, texts: list[str], rows: list[dict[str, Any]], amendments: Amendments) -> bool:
    """wording is inside one of texts. When it is not as printed, the reviewed
    nested_quotation_marks row, if present, is applied to both sides, and the
    row counts as used only when that made the comparison succeed."""
    if any(wording in text for text in texts):
        return True
    row = next(iter(_rows(rows, "nested_quotation_marks")), None)
    if row is None:
        return False
    wording = _translated(wording, row)
    if any(wording in _translated(text, row) for text in texts):
        amendments.used_rows.add(row["id"])
        return True
    return False


def read_quotations(text: str) -> dict[str, list[str]]:
    """{"(9)(a)": [quotation text, ...]}: each QUOT.S of the Omnibus's Article 1 under its point."""
    root = _parse_xml(text)
    article = next(a for a in _child_roots(root, "ARTICLE") if a.attrs.get("IDENTIFIER") == "001")
    found: dict[str, list[str]] = {}

    def own_quotations(el: _El, out: list[_El]) -> None:
        for child in el.children:
            if child.tag == "QUOT.S":
                out.append(child)
            elif child.tag != "NP":
                own_quotations(child, out)

    def visit(np_el: _El, path: str) -> None:
        no_p = next(c for c in np_el.children if c.tag == "NO.P")
        here = f"{path}({formex_text(text, no_p.start, no_p.end).strip('()')})"
        quotes: list[_El] = []
        own_quotations(np_el, quotes)
        if quotes:
            found.setdefault(here, []).extend(formex_text(text, q.start, q.end) for q in quotes)
        for child in _child_roots(np_el, "NP", skip_tags=frozenset({"QUOT.S"})):
            visit(child, here)

    top = next(c for c in _walk(article) if c.tag == "LIST")
    for item in (c for c in top.children if c.tag == "ITEM"):
        visit(next(c for c in item.children if c.tag == "NP"), "")
    return found


def load_exceptions(path: Path | str = DEFAULT_EXCEPTIONS_PATH) -> list[dict[str, Any]]:
    """The reviewed exception rows; each has an id, a kind, a reason and its kind's fields."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["rows"]
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)):
        raise AmendmentCheckError(["the exception list repeats a row id"])
    for row in rows:
        if row.get("kind") not in EXCEPTION_KINDS or not str(row.get("reason", "")).strip():
            raise AmendmentCheckError([f"exception row {row.get('id')} has an unknown kind or no reason"])
    return rows


def _rows(rows: list[dict[str, Any]], kind: str, **match: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["kind"] == kind and all(r.get(k) == v for k, v in match.items())]


def derive_changes(consolidated: UnitTree, baseline: UnitTree, markers: list[Marker],
                   rows: list[dict[str, Any]]) -> Amendments:
    """Each unit's change, read from the marker ranges (module docstring)."""
    points: dict[str, str] = {}
    used: set[str] = set()
    for marker in markers:
        label_rows = _rows(rows, "marker_label", marker_id=marker.marker_id)
        if label_rows and label_rows[0].get("marker_label") == marker.label:
            points[marker.marker_id] = label_rows[0]["omnibus_point"]
            used.add(label_rows[0]["id"])
        else:
            points[marker.marker_id] = point_of_label(marker.label)
    old = baseline.by_id()
    inside: dict[str, list[str]] = {m.marker_id: [] for m in markers}
    partly: dict[str, list[str]] = {m.marker_id: [] for m in markers}
    changes: dict[str, UnitChange] = {}
    for unit in consolidated.units:
        holding = [m for m in markers if m.inner_start <= unit.start and unit.end <= m.inner_end]
        touching = [m for m in markers if m not in holding and m.inner_start < unit.end and m.inner_end > unit.start]
        for m in holding:
            inside[m.marker_id].append(unit.id)
        for m in touching:
            partly[m.marker_id].append(unit.id)
        if len(holding) > 1:
            raise AmendmentCheckError([f"{unit.id} lies inside {len(holding)} marker ranges"])
        if holding:
            marker = holding[0]
            amendment = _AMENDMENT_OF_ACTION[marker.action]
            if amendment == "replaced" and unit.id not in old:
                amendment = "inserted"
            changes[unit.id] = UnitChange(unit.id, amendment, points[marker.marker_id], (marker.marker_id,))
        elif touching:
            changes[unit.id] = UnitChange(unit.id, "composed", None, tuple(m.marker_id for m in touching))
        else:
            changes[unit.id] = UnitChange(unit.id, "unchanged", None)
    present = consolidated.by_id()
    for unit in baseline.units:
        if unit.id in present:
            continue
        ancestor = unit.parent
        while ancestor not in present:
            ancestor = old[ancestor].parent
        change = changes[ancestor]
        if change.amendment != "replaced":
            raise AmendmentCheckError([f"{unit.id} is in the 2024 text and not in the consolidated text, "
                                       f"and {ancestor} above it is {change.amendment}, not replaced"])
        changes[unit.id] = UnitChange(unit.id, "deleted", change.point, change.marker_ids)
    return Amendments(markers, points, changes, inside, partly, used)


def _outermost(unit_ids: list[str], tree: dict[str, Unit]) -> list[str]:
    held = set(unit_ids)
    return [u for u in unit_ids if tree[u].parent not in held]


def _marker_containers(amendments: Amendments, marker: Marker, tree: dict[str, Unit]) -> set[str]:
    """The labels of the Articles and Annexes a marker's range lies in or holds ("10", "XIV")."""
    labels = set()
    for unit_id in amendments.inside[marker.marker_id] + amendments.partly[marker.marker_id]:
        unit = tree[unit_id]
        if unit.type in ("Article", "Annex"):
            labels.add(str(unit.number))
    return labels


def read_inventory(text: str) -> dict[str, tuple[str, set[str]]]:
    """{"(9)(b)": ("deleted", {"10"}), ...} from docs/omnibus_amendments.md's "- Point" entries.

    The kind is the first of replaced, inserted, added or deleted in the
    entry; the Articles and Annexes named are those of its first sentence.
    """
    entries: dict[str, tuple[str, set[str]]] = {}
    for match in _INVENTORY_ENTRY.finditer(text):
        point, body = match.group(1), match.group(2)
        kind = _KIND_WORD.search(body)
        if kind is None:
            continue
        head = body.split(". ", 1)[0]
        named = set(re.findall(r"\bAnnex ([IVX]+)\b", head))
        for list_match in re.finditer(r"\bArticles? ((?:\d+[a-z]?)(?:(?:, | and )\d+[a-z]?)*)", head):
            named.update(re.findall(r"\d+[a-z]?", list_match.group(1)))
        if point in entries:
            raise AmendmentCheckError([f"docs/omnibus_amendments.md has two entries for point {point}"])
        entries[point] = (kind.group(1), named)
    return entries


def check_markers(amendments: Amendments, consolidated: UnitTree, baseline: UnitTree, cons_text: str,
                  quotations: dict[str, list[str]], inventory: dict[str, tuple[str, set[str]]],
                  rows: list[dict[str, Any]], annex_member_text: str) -> list[str]:
    """D-G68 (2): each marker against the Omnibus, the 2024 tree and the inventory. Returns failures."""
    failures: list[str] = []
    tree, old = consolidated.by_id(), baseline.by_id()
    quotes = {point: [normalise(q) for q in qs] for point, qs in quotations.items()}
    by_id = {m.marker_id: m for m in amendments.markers}
    for marker in amendments.markers:
        point = amendments.points[marker.marker_id]
        marked = normalise(formex_text(cons_text, marker.inner_start, marker.inner_end))
        # 1. the Omnibus
        if marker.level == "TEXT":
            row = next(iter(_rows(rows, "punctuation", marker_id=marker.marker_id)), None)
            beside = by_id.get(row.get("beside")) if row else None
            if (row is None or row.get("text") != marked or beside is None or beside.label != marker.label
                    or beside.level != "STRUCTURE" or beside.action not in ("INSERTED", "DELETED")):
                failures.append(f"{marker.marker_id} ({point}): a {marker.action} TEXT range {marked!r} "
                                "with no punctuation row beside an insertion or deletion of its point")
            else:
                amendments.used_rows.add(row["id"])
        elif marker.action in ("REPLACED", "INSERTED"):
            member = next(iter(_rows(rows, "annex_member", marker_id=marker.marker_id)), None)
            trailing = next(iter(_rows(rows, "trailing_punctuation", marker_id=marker.marker_id)), None)
            if member is not None:
                amendments.used_rows.add(member["id"])
                failure = _annex_member_failure(cons_text, tree[member["unit_id"]], annex_member_text, member)
                if failure:
                    failures.append(failure)
            else:
                wording = marked
                if trailing is not None and marked.endswith(trailing["trailing"]):
                    wording = marked[: -len(trailing["trailing"])].rstrip()
                    amendments.used_rows.add(trailing["id"])
                if not _found(wording, quotes.get(point, []), rows, amendments):
                    failures.append(f"{marker.marker_id}: its wording is not in the Omnibus quotation of point {point}")
        # 2. the 2024 tree
        held = _outermost(amendments.inside[marker.marker_id], tree)
        if marker.action == "INSERTED":
            stale = [u for u in amendments.inside[marker.marker_id] if u in old]
            if not held or stale:
                failures.append(f"{marker.marker_id} ({point}) inserts units the 2024 text already has: {stale[:3]}"
                                if stale else f"{marker.marker_id} ({point}) inserts no unit")
        elif marker.action == "DELETED":
            missing = [u for u in amendments.inside[marker.marker_id] if u not in old]
            if not held or missing:
                failures.append(f"{marker.marker_id} ({point}) deletes units the 2024 text lacks: {missing[:3]}"
                                if missing else f"{marker.marker_id} ({point}) deletes no unit")
        else:
            missing = [u for u in held if u not in old] + [u for u in amendments.partly[marker.marker_id] if u not in old]
            if missing:
                failures.append(f"{marker.marker_id} ({point}) replaces units the 2024 text lacks: {missing[:3]}")
    # 3. the inventory, point by point (the punctuation ranges share their point)
    structural: dict[str, list[Marker]] = {}
    for marker in amendments.markers:
        if marker.level == "STRUCTURE":
            structural.setdefault(amendments.points[marker.marker_id], []).append(marker)
    for point, markers in structural.items():
        entry = inventory.get(point)
        if entry is None:
            failures.append(f"docs/omnibus_amendments.md has no entry for point {point}")
            continue
        kind, named = entry
        for marker in markers:
            if kind not in _KIND_OF_ACTION[marker.action]:
                failures.append(f"point {point}: the inventory says {kind}, marker {marker.marker_id} says {marker.action}")
            unnamed = _marker_containers(amendments, marker, tree) - named
            if unnamed:
                failures.append(f"point {point}: the inventory entry does not name {sorted(unnamed)}")
    for point in sorted(set(inventory) - set(structural)):
        failures.append(f"docs/omnibus_amendments.md has an entry for point {point}, which no marker carries")
    return failures


def _annex_member_failure(cons_text: str, annex: Unit, member_text: str, row: dict[str, Any]) -> str | None:
    """Annex XIV against the Omnibus annex member file: headings equal but for case and the
    quotation mark, contents equal once the member's closing mark and full stop are stripped."""
    member_root = _find(_parse_xml(member_text), "ANNEX")
    cons_root = _parse_xml(cons_text)
    cons_annex = next(el for el in _walk(cons_root) if el.tag == "CONS.ANNEX" and el.start == annex.start)
    parts = []
    for root, text in ((member_root, member_text), (cons_annex, cons_text)):
        heading = _find(next(c for c in root.children if c.tag == "TITLE"), "TI")
        contents = next(c for c in root.children if c.tag == "CONTENTS")
        parts.append((formex_text(text, heading.start, heading.end).strip(OPEN_QUOTE + CLOSE_QUOTE).lower(),
                      formex_text(text, contents.start, contents.end)))
    (member_heading, member_contents), (cons_heading, cons_contents) = parts
    if member_heading != cons_heading:
        return f"{annex.id}: heading {cons_heading!r} differs from the annex member's {member_heading!r}"
    if not member_contents.endswith(row["strip_suffix"]) or member_contents[: -len(row["strip_suffix"])] != cons_contents:
        return f"{annex.id}: the contents differ from the Omnibus annex member file"
    return None


def marker_list(amendments: Amendments, rows: list[dict[str, Any]], consolidated: dict[str, str],
                omnibus: dict[str, str]) -> dict[str, Any]:
    """The reviewed file's content: every marker with its point and units, then every changed unit."""
    rows_by_marker = {r["marker_id"]: r["id"] for r in rows if r.get("marker_id")}
    return {
        "description": (
            "Generated by tere4ai.parse_legal_structure.amendments.marker_list from the consolidated "
            "text's change markers; reviewed; the parse regenerates it and stops on any difference."
        ),
        "consolidated": consolidated,
        "omnibus": omnibus,
        "markers": [
            {
                "marker_id": m.marker_id,
                "action": m.action,
                "level": m.level,
                "marker_label": m.label,
                "omnibus_point": amendments.points[m.marker_id],
                "enacted_by": enacted_by(amendments.points[m.marker_id]),
                "units_inside": amendments.inside[m.marker_id],
                "units_partly": amendments.partly[m.marker_id],
                **({"exception": rows_by_marker[m.marker_id]} if m.marker_id in rows_by_marker else {}),
            }
            for m in amendments.markers
        ],
        "units": {
            kind: sorted(c.unit_id for c in amendments.changes.values() if c.amendment == kind)
            for kind in ("replaced", "inserted", "deleted", "composed")
        },
    }

def check_units(amendments: Amendments, consolidated: UnitTree, baseline: UnitTree, cons_text: str,
                quotations: dict[str, list[str]], rows: list[dict[str, Any]]) -> list[str]:
    """D-G68 (1): every unit against the Official Journal wording that enacted it. Returns failures."""
    failures: list[str] = []
    old = baseline.by_id()
    quotes = {point: [normalise(q) for q in qs] for point, qs in quotations.items()}
    by_id = {m.marker_id: m for m in amendments.markers}
    member_markers = {r["marker_id"] for r in rows if r["kind"] == "annex_member"}
    for unit in consolidated.units:
        change = amendments.changes[unit.id]
        before = old.get(unit.id)
        if before is None and change.amendment in ("unchanged", "composed"):
            failures.append(f"{unit.id}: {change.amendment} by the markers, but the 2024 text has no unit with this id")
            continue
        if change.amendment == "unchanged":
            if (unit.text or "") != (before.text or ""):
                failures.append(f"{unit.id}: no marker touches it and its text differs from the 2024 text")
            if (unit.title or "") != (before.title or ""):
                row = next(iter(_rows(rows, "unmarked_title", unit_id=unit.id)), None)
                if row and row.get("baseline") == before.title and row.get("consolidated") == unit.title:
                    amendments.used_rows.add(row["id"])
                else:
                    failures.append(f"{unit.id}: no marker touches it and its title differs from the 2024 title")
        elif change.amendment in ("replaced", "inserted"):
            if change.marker_ids[0] in member_markers:
                continue  # Annex XIV: compared whole with the annex member file (check_markers)
            for wording in (unit.text, unit.title):
                if not wording:
                    continue
                cut = normalise(wording)
                trailing = next(iter(_rows(rows, "trailing_punctuation", marker_id=change.marker_ids[0])), None)
                if trailing and cut.endswith(trailing["trailing"]) and not _found(cut, quotes.get(change.point, []),
                                                                                  rows, amendments):
                    cut = cut[: -len(trailing["trailing"])].rstrip()
                if not _found(cut, quotes.get(change.point, []), rows, amendments):
                    failures.append(f"{unit.id}: not in the Omnibus quotation of point {change.point}")
        elif change.amendment == "composed":
            marks = [by_id[m] for m in change.marker_ids]
            if unit.type in TEXT_UNIT_TYPES:
                failure = _composed_failure(unit, before, marks, cons_text)
                if failure:
                    failures.append(failure)
            elif (unit.title or "") != (before.title or ""):
                heading = [m for m in marks if unit.title_range and m.inner_start <= unit.title_range[0]
                           and unit.title_range[1] <= m.inner_end]
                if not heading or not _found(normalise(unit.title),
                                             quotes.get(amendments.points[heading[0].marker_id], []), rows, amendments):
                    row = next(iter(_rows(rows, "unmarked_title", unit_id=unit.id)), None)
                    if row and row.get("baseline") == before.title and row.get("consolidated") == unit.title:
                        amendments.used_rows.add(row["id"])
                    else:
                        failures.append(f"{unit.id}: its title changed and no marker over the heading enacts it")
    # the reverse check: every quotation is applied somewhere
    marked = [normalise(formex_text(cons_text, m.inner_start, m.inner_end)) for m in amendments.markers]
    for point, qs in quotes.items():
        for quotation in qs:
            core = quotation.removeprefix(OPEN_QUOTE).removesuffix(CLOSE_QUOTE).strip()
            if not _found(core, marked, rows, amendments):
                failures.append(f"the Omnibus quotation of point {point} is in no marked range (left unapplied?)")
    # the containers' wording outside their units
    for unit in consolidated.units:
        change = amendments.changes[unit.id]
        if unit.type in TEXT_UNIT_TYPES or change.amendment not in ("unchanged", "composed"):
            continue
        before = old[unit.id]
        old_own = normalise(formex_text(baseline.texts[before.file], before.start, before.end,
                                        _outside_units(before, baseline)))
        ranges = _outside_units(unit, consolidated)
        if change.amendment == "unchanged":
            if normalise(formex_text(cons_text, unit.start, unit.end, ranges)) != old_own:
                failures.append(f"{unit.id}: its wording outside its units differs from the 2024 text")
            continue
        marks = [by_id[m] for m in change.marker_ids
                 if not any(s <= by_id[m].start and by_id[m].end <= e for s, e in ranges)]
        failure = _rest_failure(unit.id, cons_text, unit.start, unit.end, ranges, marks, old_own,
                                "its wording outside its units")
        if failure:
            failures.append(failure)
    return failures


def _outside_units(unit: Unit, tree: UnitTree) -> list[tuple[int, int]]:
    """What a container's own wording leaves out: its child units, its title (compared on
    its own) and the file's bibliographic block (the 2024 annex member files carry one)."""
    text = tree.texts[unit.file]
    ranges = [(c.start, c.end) for c in tree.units if c.parent == unit.id and c.file == unit.file]
    if unit.title_range:
        ranges.append(unit.title_range)
    ranges += [(m.start(), m.end()) for m in _METADATA.finditer(text, unit.start, unit.end)]
    return ranges


def stale_rows(amendments: Amendments, rows: list[dict[str, Any]]) -> list[str]:
    """After check_markers and check_units: a row no check needed is a failure too."""
    return [f"exception row {row['id']} ({row['kind']}) was not needed by any check: review it"
            for row in rows if row["id"] not in amendments.used_rows]


def _composed_failure(unit: Unit, before: Unit, marks: list[Marker], cons_text: str) -> str | None:
    """The unmarked rest of a partly amended unit equals its 2024 text."""
    return _rest_failure(unit.id, cons_text, unit.start, unit.end, list(unit.own_exclude), marks,
                         normalise(before.text or ""), "its unmarked text")


def _rest_failure(unit_id: str, cons_text: str, start: int, end: int, exclude: list[tuple[int, int]],
                  marks: list[Marker], old: str, what: str) -> str | None:
    """The unmarked pieces of cons_text[start:end] (exclude left out) appear in the
    2024 text old in order, and 2024 text between them is allowed only where a
    REPLACED or DELETED range sat."""
    pos, pending = 0, False
    segments: list[tuple[int, int] | Marker] = []
    cursor = start
    for mark in sorted(marks, key=lambda m: m.start):
        segments.append((cursor, max(cursor, mark.start)))
        segments.append(mark)
        cursor = max(cursor, min(mark.end, end))
    segments.append((cursor, end))
    for segment in segments:
        if isinstance(segment, Marker):
            pending = pending or segment.action in ("REPLACED", "DELETED")
            continue
        piece = normalise(formex_text(cons_text, segment[0], segment[1], exclude))
        if not piece:
            continue
        found = old.find(piece, pos)
        if found < 0:
            return f"{unit_id}: {what} {piece[:50]!r} is not in its 2024 text"
        if old[pos:found].strip() and not pending:
            return f"{unit_id}: its 2024 text has {old[pos:found].strip()[:40]!r} where nothing was replaced"
        pos, pending = found + len(piece), False
    if old[pos:].strip() and not pending:
        return f"{unit_id}: its 2024 text ends with {old[pos:].strip()[:40]!r} where nothing was replaced"
    return None


def is_deleted(node: dict[str, Any] | None) -> bool:
    """A Layer 1 node the Omnibus deleted: it keeps its id and has no text or span."""
    return isinstance(node, dict) and node.get("amendment") == "deleted"


def deleted_note(node: dict[str, Any]) -> str:
    """The answer for a deleted unit: Deleted by <act, point>, from 27 July 2026."""
    return f"Deleted by {node['deleted_by']}, from 27 July 2026."


def version_node_id(unit_id: str) -> str:
    """The earlier version's node id; it never starts with eu-ai-act, so no prefix walk meets it."""
    return f"version:{VERSION_DATE}:{unit_id}"


def version_span_id(span_name: str) -> str:
    """span:010.005 -> span:010.005@2024-07-12, never the id of an in-force span."""
    return f"{span_name}@{VERSION_DATE}"

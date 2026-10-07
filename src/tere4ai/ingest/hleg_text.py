"""Derive the text of the HLEG Guidelines' seven requirements from their official PDF.

@implements: DEC-25 (partial: the derivation and its record)
@grounded_by: ADD-01

python -m tere4ai.ingest.hleg_text --write derives, from the frozen
Publications Office PDF (read through its manifest sha256), the text of
Chapter II Section 1 of the Ethics Guidelines for Trustworthy AI and its
derivation record, writes both to data/snapshots and sets their sha256 in
MANIFEST.json; --check runs the checks C0 to C4 (hleg_checks.py). The PDF
is tagged: reading follows its structure tree, footnotes (Note) and figures
are skipped, page numbers are artifacts outside the tree. RULES lists the
rules and is copied into the record. pdfplumber is imported inside the
functions that need it, so importing this module for its file names needs
no PDF library (the facade and the MCP server do). Deterministic, no model.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
DEFAULT_MANIFEST = SNAPSHOTS_DIR / "MANIFEST.json"

PDF_FILE = "hleg_ethics_guidelines_2019_en.pdf"
TEXT_FILE = "hleg_ethics_guidelines_2019_en_requirements.txt"
RECORD_FILE = "hleg_ethics_guidelines_2019_en_requirements_derivation.json"
EXCLUSIONS_FILE = "hleg_ethics_guidelines_2019_en_requirements_exclusions.json"
WORD_ROWS_FILE = "hleg_ethics_guidelines_2019_en_requirements_word_rows.json"
RECORD_FORMAT = "tere4ai.hleg_derivation.v1"

PAGES = (17, 18, 19, 20, 21, 22)
START_HEADING = "1.1 Human agency and oversight"
END_HEADING = "2. Technical and non-technical methods to realise Trustworthy AI"
MARKER_SIZE_RATIO = 0.75
X_TOLERANCE = 1.5
LINE_TOLERANCE = 3
MARGIN_TOLERANCE = 1.0
SKIPPED_TYPES = ("Note", "Figure")
_REQUIREMENT_HEADING = re.compile(r"^1\.([1-7]) \S")
RULES = [
    "reading order is the structure tree's order",
    "Note and Figure subtrees are skipped whatever the tags inside them",
    "artifacts (page numbers, running headers) are outside the structure tree and never read",
    f"characters smaller than {MARKER_SIZE_RATIO} times the paragraph's median character size are footnote "
    "markers and are removed; each removed run is the number of a footnote whose Note is on the same page; "
    "a run of small whitespace is a space",
    f"words are spaced from the character positions by pdfplumber's word reading, x tolerance {X_TOLERANCE}",
    "a line ending with a hyphen is joined to the next line without a space, the hyphen kept",
    f"a page's last paragraph whose last line reaches the right text margin (within {MARGIN_TOLERANCE} pt of "
    "the page's widest body line) is joined with one space to the next page's first paragraph when that is "
    "not a heading",
]


class DerivationError(ValueError):
    """The PDF does not satisfy a rule; the message names the page and the element or offset."""


@dataclass
class Element:
    """One structure element: its tag, page, marked-content ids and path of child indexes."""

    type: str
    page: int | None
    mcids: list[int]
    path: str
    children: list[Element] = field(default_factory=list)


@dataclass
class PdfFacts:
    """What the derivation reads from the PDF; tests alter a copy of it to make mock data."""

    sha256: str
    chars: dict[int, list[dict[str, Any]]]
    tree: list[Element]
    libraries: dict[str, str]


def manifest_entries(manifest_path: Path | str = DEFAULT_MANIFEST) -> dict[str, dict[str, Any]]:
    return {e["file"]: e for e in json.loads(Path(manifest_path).read_text(encoding="utf-8"))["snapshots"]}


def read_checked(manifest_path: Path | str, name: str) -> bytes:
    """The bytes of a manifest file, read only after its sha256 is checked."""
    entry = manifest_entries(manifest_path).get(name)
    if entry is None:
        raise ValueError(f"{name} is not listed in {Path(manifest_path).name}")
    raw = (Path(manifest_path).parent / name).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(f"checksum mismatch for {name}: manifest {entry['sha256']}, file {actual}")
    return raw


def read_pdf(source: Path | str | bytes) -> PdfFacts:
    from importlib.metadata import version

    import pdfplumber
    from pdfplumber.structure import PDFStructTree

    raw = source if isinstance(source, bytes) else Path(source).read_bytes()

    def convert(element: Any, path: str) -> Element:
        return Element(element.type, element.page_number, list(element.mcids or []), path,
                       [convert(child, f"{path}.{i}") for i, child in enumerate(element.children)])

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        tree = [convert(element, str(i)) for i, element in enumerate(PDFStructTree(pdf))]
        chars = {n: [dict(c) for c in pdf.pages[n - 1].chars] for n in PAGES}
    return PdfFacts(hashlib.sha256(raw).hexdigest(), chars, tree,
                    {"pdfplumber": version("pdfplumber"), "pdfminer.six": version("pdfminer.six")})


def walk(tree: list[Element]) -> list[tuple[Element, Element | None, bool]]:
    """Every element in reading order with its footnote (the Note's child, or the
    Note itself when it carries text) and whether it is inside a skipped subtree."""
    out: list[tuple[Element, Element | None, bool]] = []

    def visit(element: Element, note: Element | None, skipped: bool, parent_is_note: bool) -> None:
        if parent_is_note or (element.type == "Note" and element.mcids):
            note = element
        skipped = skipped or element.type in SKIPPED_TYPES
        out.append((element, note, skipped))
        for child in element.children:
            visit(child, note, skipped, element.type == "Note" and note is None)

    for element in tree:
        visit(element, None, False, False)
    return out


def _text(chars: list[dict[str, Any]]) -> str:
    from pdfplumber.utils import extract_text

    return " ".join(extract_text(chars, x_tolerance=X_TOLERANCE).split())


def _piece(chars: list[dict[str, Any]], page: int, path: str) -> dict[str, Any]:
    """One element's text on one page: words spaced by position, lines joined by the
    hyphen rule, small runs removed as markers (each with its offset in the piece)."""
    from pdfplumber.utils import cluster_objects, extract_words

    body = statistics.median(c["size"] for c in chars if c["text"].strip())
    kept: list[dict[str, Any]] = []
    runs: list[tuple[dict[str, Any] | None, list[dict[str, Any]]]] = []
    current: list[dict[str, Any]] = []
    run_before: dict[str, Any] | None = None
    for c in chars:
        if c["size"] < MARKER_SIZE_RATIO * body:
            if not current:
                run_before = kept[-1] if kept else None
            current.append(c)
            continue
        if current:
            runs.append((run_before, current))
            current = []
        kept.append(c)
    if current:
        runs.append((kept[-1] if kept else None, current))
    words = extract_words(kept, x_tolerance=X_TOLERANCE, return_chars=True)
    text, offsets, hyphens = "", {}, []
    for line in cluster_objects(words, "top", LINE_TOLERANCE):
        for i, word in enumerate(sorted(line, key=lambda w: w["x0"])):
            if text and i == 0 and text.endswith("-"):
                hyphens.append(text.rsplit(" ", 1)[-1] + word["text"])
            elif text:
                text += " "
            for c in word["chars"]:
                offsets[id(c)] = len(text)
                text += c["text"]
    markers = []
    for before, run in runs:
        number = "".join(c["text"] for c in run).strip()
        if not number:
            continue  # a run of small whitespace is a space (R11)
        if not number.isdigit():
            raise DerivationError(f"page {page}, element {path}: small characters {number!r} are not a footnote number")
        at = offsets[id(before)] + 1 if before is not None else 0
        markers.append({"number": number, "piece_offset": at, "top": round(min(c["top"] for c in run), 2)})
    runin = ""
    for c in kept:
        if "BoldItalic" not in (c.get("fontname") or ""):
            break
        runin += c["text"]
    last_top = max(c["top"] for c in kept)
    last_x1 = max(c["x1"] for c in kept if abs(c["top"] - last_top) < 1)
    return {"text": text, "markers": markers, "hyphens": hyphens, "runin": runin.strip(), "last_x1": last_x1,
            "page": page, "path": path}


def derive_from(facts: PdfFacts) -> tuple[str, dict[str, Any]]:
    """The derived text and its record (module docstring); raises DerivationError."""
    by_mcid: dict[int, dict[int, list[dict[str, Any]]]] = {n: {} for n in PAGES}
    for n in PAGES:
        for c in facts.chars[n]:
            if c.get("mcid") is not None:
                by_mcid[n].setdefault(c["mcid"], []).append(c)
    order = walk(facts.tree)
    pieces = []
    for element, _note, skipped in order:
        if skipped or element.page not in PAGES or not element.mcids:
            continue
        chars = [c for m in element.mcids for c in by_mcid[element.page].get(m, [])]
        if not "".join(c["text"] for c in chars).strip():
            continue
        piece = _piece(chars, element.page, element.path)
        piece["type"] = element.type
        pieces.append(piece)
    starts = [i for i, p in enumerate(pieces) if p["text"] == START_HEADING]
    ends = [i for i, p in enumerate(pieces) if p["text"] == END_HEADING]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise DerivationError(f"on pages {PAGES[0]} to {PAGES[-1]} the start heading is found {len(starts)} times "
                              f"and the end heading {len(ends)} times; each must be found once, in order")
    section = pieces[starts[0]:ends[0]]
    margin = {n: max((p["last_x1"] for p in section if p["page"] == n), default=0.0) for n in PAGES}
    blocks: list[dict[str, Any]] = []
    for piece in section:
        heading = piece["type"] != "P" and bool(_REQUIREMENT_HEADING.match(piece["text"]))
        last = blocks[-1]["pieces"][-1] if blocks else None
        if (last is not None and not heading and not blocks[-1]["heading"] and last["page"] != piece["page"]
                and last["last_x1"] >= margin[last["page"]] - MARGIN_TOLERANCE):
            blocks[-1]["pieces"].append(piece)
            continue
        blocks.append({"heading": heading, "pieces": [piece]})
    text = ""
    paragraphs, requirement_headings, subtopic_headings = [], [], []
    markers, joins, hyphen_joins = [], [], []
    for block in blocks:
        if text:
            text += "\n\n"
        start = len(text)
        for k, piece in enumerate(block["pieces"]):
            if k:
                joins.append({"from_page": block["pieces"][k - 1]["page"], "to_page": piece["page"], "offset": len(text)})
                text += " "
            for m in piece["markers"]:
                markers.append({"number": m["number"], "page": piece["page"], "offset": len(text) + m["piece_offset"],
                                "top": m["top"]})
            hyphen_joins += [{"page": piece["page"], "word": word} for word in piece["hyphens"]]
            text += piece["text"]
        end = len(text)
        first = block["pieces"][0]
        paragraphs.append({"index": len(paragraphs), "kind": "requirement_heading" if block["heading"] else "paragraph",
                           "start": start, "end": end, "pages": [p["page"] for p in block["pieces"]],
                           "elements": [p["path"] for p in block["pieces"]]})
        if block["heading"]:
            requirement_headings.append({"order": int(first["text"][2]), "text": text[start:end], "start": start,
                                         "end": end})
        elif first["runin"]:
            label = first["runin"].rstrip(".").strip()
            if not requirement_headings or not text[start:].startswith(label + "."):
                raise DerivationError(f"page {first['page']}, element {first['path']}: the bold italic heading "
                                      f"{label!r} does not open its paragraph followed by a period")
            subtopic_headings.append({"requirement_order": requirement_headings[-1]["order"], "label": label,
                                      "start": start, "end": start + len(label),
                                      "paragraph_index": len(paragraphs) - 1})
    text += "\n"
    exclusions = _exclusions(facts, order, {p["path"] for p in section}, section, markers)
    footnotes = {(e["page"], e["number"]) for e in exclusions
                 if e["kind"] in ("footnote", "outside_section") and e.get("number")}
    for m in markers:
        if (m["page"], m["number"]) not in footnotes:
            raise DerivationError(f"page {m['page']}, offset {m['offset']}: removed characters {m['number']!r} are "
                                  "not the number of a footnote on that page")
    record = {
        "format": RECORD_FORMAT,
        "pdf": {"file": PDF_FILE, "sha256": facts.sha256},
        "derived_file": TEXT_FILE,
        "libraries": facts.libraries,
        "rules": RULES,
        "pages": list(PAGES),
        "range": {"start_heading": START_HEADING, "end_heading_exclusive": END_HEADING},
        "paragraphs": paragraphs,
        "requirement_headings": requirement_headings,
        "subtopic_headings": subtopic_headings,
        "markers_removed": [{k: m[k] for k in ("number", "page", "offset")} for m in markers],
        "page_joins": joins,
        "hyphen_joins": hyphen_joins,
        "exclusions": exclusions,
    }
    return text, record


def _exclusions(facts: PdfFacts, order: list[tuple[Element, Element | None, bool]], read_paths: set[str],
                section: list[dict[str, Any]], markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every character of the pages that is not in the derived text, grouped into
    items with their location (page, top), kind and text, in page then top order."""
    position = {element.path: i for i, (element, _n, _s) in enumerate(order)}
    first = position[section[0]["path"]]
    owner: dict[tuple[int, int], tuple[Element, Element | None, bool]] = {}
    for element, note, skipped in order:
        if element.page in PAGES:
            for m in element.mcids:
                owner[(element.page, m)] = (element, note, skipped)
    section_markers = {(m["page"], m["number"]) for m in markers}
    items: list[dict[str, Any]] = []
    for n in PAGES:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for c in facts.chars[n]:
            if not c["text"].strip():
                continue
            found = owner.get((n, c.get("mcid")))
            if found is None:
                key = ("artifact", f"{round(c['top']):06d}")
            else:
                element, note, skipped = found
                if note is not None:
                    key = ("note", note.path)
                elif skipped:
                    key = ("figure", element.path)
                elif element.path in read_paths:
                    continue
                else:
                    key = ("outside", "before" if position[element.path] < first else "after")
            groups.setdefault(key, []).append(c)
        page_items = []
        for (group, _), chars in groups.items():
            text = _text(chars)
            if not text:
                continue
            item: dict[str, Any] = {"page": n, "top": round(min(c["top"] for c in chars), 2)}
            if group == "artifact":
                item["kind"] = "page_number" if text.isdigit() else "artifact"
            elif group == "note":
                number = re.match(r"^(\d+)", text)
                item["number"] = number.group(1) if number else None
                item["kind"] = "footnote" if (n, item["number"]) in section_markers else "outside_section"
            elif group == "figure":
                item["kind"] = "figure"
            else:
                item["kind"] = "outside_section"
            item["text"] = text
            page_items.append(item)
        for m in markers:
            if m["page"] == n:
                page_items.append({"page": n, "top": m["top"], "kind": "removed_marker", "number": m["number"],
                                   "offset": m["offset"], "text": m["number"]})
        items += sorted(page_items, key=lambda i: (i["top"], i["kind"], i.get("offset", 0)))
    return [{k: item[k] for k in ("kind", "page", "top", "number", "offset", "text") if k in item} for item in items]


def record_bytes(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def derive(source: Path | str | bytes) -> tuple[bytes, bytes]:
    """(the derived text's bytes, the record's bytes) from the PDF."""
    text, record = derive_from(read_pdf(source))
    return text.encode("utf-8"), record_bytes(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tere4ai.ingest.hleg_text")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="derive the text and record, set their sha256")
    group.add_argument("--check", action="store_true", help="run the checks C0 to C4")
    args = parser.parse_args(argv)
    if args.check:
        from tere4ai.ingest.hleg_checks import HlegCheckError, run_hleg_checks

        try:
            outcome = run_hleg_checks(args.manifest)
        except (HlegCheckError, ValueError) as exc:  # run_hleg_checks names the check for a missing file or library
            print(f"CHECK FAIL {exc}", file=sys.stderr)
            return 1
        print(f"HLEG text checks {', '.join(outcome['checks_passed'])} pass: {outcome['paragraphs']} paragraphs, "
              f"{outcome['subtopic_headings']} subtopic headings, {outcome['exclusions_reviewed']} reviewed exclusions, "
              f"{len(outcome['word_rows_used'])} word rows")
        return 0
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    names = {e["file"] for e in manifest["snapshots"]}
    missing = [n for n in (TEXT_FILE, RECORD_FILE) if n not in names]
    if missing:
        print(f"refusing to write: {', '.join(missing)} has no entry in {args.manifest.name}; add the entry "
              "(source_document, manifestation, notes) first", file=sys.stderr)
        return 1
    try:
        text_bytes, record = derive(read_checked(args.manifest, PDF_FILE))
    except (DerivationError, ValueError) as exc:
        print(f"DERIVATION FAIL {exc}", file=sys.stderr)
        return 1
    folder = args.manifest.parent
    (folder / TEXT_FILE).write_bytes(text_bytes)
    (folder / RECORD_FILE).write_bytes(record)
    shas = {TEXT_FILE: hashlib.sha256(text_bytes).hexdigest(), RECORD_FILE: hashlib.sha256(record).hexdigest()}
    for entry in manifest["snapshots"]:
        if entry["file"] in shas:
            entry["sha256"] = shas[entry["file"]]
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {TEXT_FILE} ({len(text_bytes)} bytes) and {RECORD_FILE}; sha256 set in {args.manifest.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The checks C0 to C4 of the derived HLEG text against the Guidelines' official PDF.

@implements: DEC-25 (partial: the checks)
@grounded_by: ADD-01

Spec G D-G75 (3). pypdf, a parser separate from pdfplumber's pdfminer.six,
is the second reader. C0 re-derives both files byte for byte; C1 finds every
derived stretch (the text between two removed markers or page joins) in
pypdf's text of its page, whitespace removed; C2 accounts for every
character pypdf reads on the pages: derived, or one of the excluded items,
which must equal the reviewed list item by item and each pass the test of
its kind; C3 compares each page's words, in order, with pypdf's layout
reading and accepts only the differences a reviewed row names (page, offset,
both readings, the reason); C4 checks the structure (the seven headings, the
23 subtopic headings opening their paragraphs, no line of only digits).
run_hleg_checks runs C0 to C4 and returns the outcome the build records. A
failing check raises HlegCheckError, which names the check and carries its
diagnostics, each with its location. Deterministic, no model.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tere4ai.ingest import hleg_text as ht

_SPACE = re.compile(r"\s+")


class HlegCheckError(RuntimeError):
    """A check failed: check is C0 to C4, diagnostics carry the locations."""

    def __init__(self, check: str, diagnostics: list[str]):
        self.check, self.diagnostics = check, list(diagnostics)
        more = f"; (and {len(diagnostics) - 5} more)" if len(diagnostics) > 5 else ""
        super().__init__(f"{check} failed: {'; '.join(diagnostics[:5])}{more}")


@dataclass(frozen=True)
class Stretch:
    page: int
    start: int
    end: int
    text: str


def _nows(value: str) -> str:
    return _SPACE.sub("", value)


def pypdf_pages(pdf_bytes: bytes) -> tuple[dict[int, str], dict[int, str]]:
    """pypdf's plain and layout readings of each page of PAGES."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    plain = {n: reader.pages[n - 1].extract_text() for n in ht.PAGES}
    layout = {n: reader.pages[n - 1].extract_text(extraction_mode="layout") for n in ht.PAGES}
    return plain, layout


def stretches(text: str, record: dict[str, Any], at_markers: bool = True) -> list[Stretch]:
    """The derived text cut at every page join, and at every removed marker unless
    at_markers is False (C3 compares whole words, so it never cuts at a marker),
    paragraph by paragraph."""
    markers = {m["offset"] for m in record["markers_removed"]} if at_markers else set()
    cuts = sorted(markers | {j["offset"] for j in record["page_joins"]})
    out: list[Stretch] = []
    for p in record["paragraphs"]:
        joins = [j["offset"] for j in record["page_joins"] if p["start"] < j["offset"] < p["end"]]
        bounds = [p["start"], *[c for c in cuts if p["start"] < c < p["end"]], p["end"]]
        for a, b in zip(bounds, bounds[1:]):
            if text[a:b].strip():
                out.append(Stretch(p["pages"][sum(1 for j in joins if j <= a)], a, b, text[a:b]))
    return out


def first_difference(frozen: bytes, fresh: bytes) -> str:
    at = next((i for i, (a, b) in enumerate(zip(frozen, fresh)) if a != b), min(len(frozen), len(fresh)))
    return f"at byte {at}: frozen {frozen[at:at + 40]!r}, derived again {fresh[at:at + 40]!r}"


def check_c0(text_bytes: bytes, record_bytes_: bytes, facts: ht.PdfFacts) -> list[str]:
    try:
        text, record = ht.derive_from(facts)
    except ht.DerivationError as exc:
        return [f"C0 the derivation stops: {exc}"]
    failures = []
    for name, frozen, fresh in ((ht.TEXT_FILE, text_bytes, text.encode("utf-8")),
                                (ht.RECORD_FILE, record_bytes_, ht.record_bytes(record))):
        if frozen != fresh:
            failures.append(f"C0 {name} differs from a fresh derivation {first_difference(frozen, fresh)}")
    return failures


def check_c1(text: str, record: dict[str, Any], plain: dict[int, str]) -> list[str]:
    return [f"C1 page {s.page}, offset {s.start}: {s.text[:60]!r} is not in pypdf's text of the page"
            for s in stretches(text, record) if _nows(s.text) not in _nows(plain[s.page])]


def body_bottoms(facts: ht.PdfFacts) -> dict[int, float]:
    """The bottom of each page's last line of body text (any element outside a skipped subtree)."""
    owned = {(element.page, m) for element, _n, skipped in ht.walk(facts.tree)
             if element.page in ht.PAGES and not skipped for m in element.mcids}
    return {n: max(c["bottom"] for c in facts.chars[n] if c["text"].strip() and (n, c.get("mcid")) in owned)
            for n in ht.PAGES}


def kind_failures(item: dict[str, Any], record: dict[str, Any], bottoms: dict[int, float],
                  items: list[dict[str, Any]]) -> list[str]:
    """The test of an exclusion's kind, independent of the tag that excluded it."""
    page, kind = item["page"], item["kind"]
    where = f"C2 page {page}, top {item['top']}"
    numbers = {m["number"] for m in record["markers_removed"] if m["page"] == page}
    if kind == "footnote":
        if not item.get("number") or not item["text"].startswith(item["number"]):
            return [f"{where}: a footnote must open with its number: {item['text'][:40]!r}"]
        if item["number"] not in numbers:
            return [f"{where}: footnote {item['number']} has no removed marker in the body of page {page}"]
        if item["top"] <= bottoms[page]:
            return [f"{where}: footnote {item['number']} is not below the page's last body line ({bottoms[page]})"]
    elif kind == "page_number":
        if not item["text"].isdigit() or int(item["text"]) != page - 2 or item["top"] <= bottoms[page]:
            return [f"{where}: {item['text']!r} is not the printed page number {page - 2} below the body"]
    elif kind == "running_header":
        if any(not any(o["kind"] == "running_header" and o["page"] == n and o["text"] == item["text"] for o in items)
               for n in ht.PAGES):
            return [f"{where}: running header {item['text']!r} is not on every page"]
    elif kind == "removed_marker":
        if not any(o["kind"] == "footnote" and o["page"] == page and o.get("number") == item["number"] for o in items):
            return [f"{where}: removed marker {item['number']} has no footnote on page {page}"]
    elif kind == "outside_section":
        if page not in (ht.PAGES[0], ht.PAGES[-1]):
            return [f"{where}: text outside the section on a page inside it: {item['text'][:40]!r}"]
        if item.get("number") in numbers:
            return [f"{where}: footnote {item['number']} belongs to the section"]
    else:
        return [f"{where}: excluded {kind} {item['text'][:60]!r} is not a footnote, a page number, a running header, "
                "a removed marker or text outside the section"]
    return []


def check_c2(text: str, record: dict[str, Any], plain: dict[int, str], reviewed: list[dict[str, Any]],
             bottoms: dict[int, float]) -> list[str]:
    made = record["exclusions"]
    failures = [f"C2 page {i['page']}, top {i['top']}: exclusion not in the reviewed list: {i['kind']} {i['text'][:60]!r}"
                for i in made if i not in reviewed]
    failures += [f"C2 page {i['page']}, top {i['top']}: reviewed exclusion the derivation did not make: "
                 f"{i['kind']} {i['text'][:60]!r}" for i in reviewed if i not in made]
    if not failures and made != reviewed:
        failures.append("C2 the exclusions are the reviewed ones in another order")
    for item in made:
        failures += kind_failures(item, record, bottoms, made)
    pieces = stretches(text, record)
    for n in ht.PAGES:
        rest = _nows(plain[n])
        for s in pieces:
            if s.page == n:
                rest = rest.replace(_nows(s.text), "", 1)
        # Longest first, so a short item (a page number, "45 For instance EN 301 549.")
        # cannot take characters from a longer one. Each item is removed at its first
        # occurrence, not at its own position (pypdf's text has no positions). That
        # cannot hide a residue: a short item that matched elsewhere would leave its
        # own copy behind, so the rest would still be non-empty and reported.
        for item in sorted((i for i in made if i["page"] == n and i["kind"] != "removed_marker"),
                           key=lambda i: -len(_nows(i["text"]))):
            rest = rest.replace(_nows(item["text"]), "", 1)
        for item in made:  # the markers last: their digits occur in other text too
            if item["page"] == n and item["kind"] == "removed_marker":
                rest = rest.replace(item["text"], "", 1)
        if rest:
            failures.append(f"C2 page {n}: pypdf reads {rest[:60]!r}, which is neither derived nor excluded")
    return failures


CANONICAL_HEADINGS = [
    "1.1 Human agency and oversight", "1.2 Technical robustness and safety", "1.3 Privacy and data governance",
    "1.4 Transparency", "1.5 Diversity, non-discrimination and fairness",
    "1.6 Societal and environmental well-being", "1.7 Accountability",
]
SUBTOPIC_COUNT = 23


def _find(words: list[str], seq: list[str], start: int = 0) -> int:
    for i in range(start, len(words) - len(seq) + 1):
        if words[i:i + len(seq)] == seq:
            return i
    return -1


def body_words(layout_text: str, page: int, record: dict[str, Any], reviewed: list[dict[str, Any]]) -> list[str]:
    """pypdf's layout reading of the page's body, in order: from the start heading on
    the first page, up to the page's first footnote, its page number, and the end
    heading on the last page, located by the reviewed exclusions (R13); a marker
    number glued to a word or standing alone is removed and a line-end hyphen is
    joined, the derivation's own rules applied to the other reading."""
    words = layout_text.split()
    start, end = 0, len(words)
    if page == ht.PAGES[0]:
        start = max(_find(words, ht.START_HEADING.split()), 0)
    anchors = [[i["text"]] for i in reviewed if i["page"] == page and i["kind"] == "page_number"]
    notes = sorted((i for i in reviewed if i["page"] == page and i["kind"] in ("footnote", "outside_section")
                    and i.get("number")), key=lambda i: i["top"])
    if notes:
        anchors.append(notes[0]["text"].split()[:3])
    if page == ht.PAGES[-1]:
        anchors.append(ht.END_HEADING.split()[:4])
    for anchor in anchors:
        at = _find(words, anchor, start)
        if at >= 0:
            end = min(end, at)
    numbers = {m["number"] for m in record["markers_removed"] if m["page"] == page}
    out: list[str] = []
    for word in words[start:end]:
        for number in numbers:
            if word.endswith(number) and len(word) > len(number) and not word[: -len(number)].isdigit():
                word = word[: -len(number)]
                break
        if word in numbers:
            continue
        if out and out[-1].endswith("-") and len(out[-1]) > 1:
            out[-1] += word
            continue
        out.append(word)
    return out


def word_differences(derived: list[str], other: list[str]) -> list[tuple[str, int, int, int, int]]:
    return [op for op in difflib.SequenceMatcher(None, derived, other, autojunk=False).get_opcodes() if op[0] != "equal"]


def check_c3(text: str, record: dict[str, Any], other_body: dict[int, list[str]],
             rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    used: list[str] = []
    # Whole words: the text is cut at page joins only, never at a removed marker,
    # so a word glued across a marker ("systems47 in" read as "systemsin") is one
    # derived word and is seen (the planner's mock data test found the gap).
    pieces = stretches(text, record, at_markers=False)
    for n in ht.PAGES:
        located = [(m.group(0), s.start + m.start()) for s in pieces if s.page == n for m in re.finditer(r"\S+", s.text)]
        derived = [w for w, _ in located]
        for _tag, i1, i2, j1, j2 in word_differences(derived, other_body.get(n, [])):
            if i1 < len(located):
                offset = located[i1][1]
            else:
                offset = located[-1][1] + len(located[-1][0]) if located else 0
            found = {"page": n, "offset": offset, "derived": derived[i1:i2], "other": other_body[n][j1:j2]}
            row = next((r for r in rows if {k: r[k] for k in found} == found), None)
            if row is None:
                failures.append(f"C3 page {n}, offset {offset}: derived {found['derived']} against pypdf {found['other']}")
            else:
                used.append(row["id"])
    failures += [f"C3 page {r['page']}, offset {r['offset']}: reviewed row {r['id']} matches no difference"
                 for r in rows if r["id"] not in used]
    return failures, used


def check_c4(text: str, record: dict[str, Any]) -> list[str]:
    failures = []
    lines = text.split("\n")
    headings = [line for line in lines if re.match(r"^1\.[1-7] ", line)]
    if headings != CANONICAL_HEADINGS:
        failures.append(f"C4 the requirement headings are {headings}, not the seven in order")
    if len(record["subtopic_headings"]) != SUBTOPIC_COUNT:
        failures.append(f"C4 {len(record['subtopic_headings'])} subtopic headings, not {SUBTOPIC_COUNT}")
    for s in record["subtopic_headings"]:
        opens = s["start"] == 0 or text[s["start"] - 2:s["start"]] == "\n\n"
        if not opens or text[s["start"]:s["end"] + 1] != s["label"] + ".":
            failures.append(f"C4 offset {s['start']}: subtopic heading {s['label']!r} does not open its paragraph")
    failures += [f"C4 line {i + 1} is only digits: {line!r}" for i, line in enumerate(lines) if line.strip().isdigit()]
    return failures


def _reviewed_file(folder: Path, name: str, check: str) -> bytes:
    """A reviewed file beside the manifest; a missing or unreadable one fails the check that reads it."""
    try:
        raw = (folder / name).read_bytes()
        json.loads(raw)
    except (OSError, ValueError) as exc:
        raise HlegCheckError(check, [f"{check} the reviewed file {name} cannot be read: {exc}"]) from exc
    return raw


def run_hleg_checks(manifest_path: Path | str = ht.DEFAULT_MANIFEST) -> dict[str, Any]:
    """C0 to C4 over the files the manifest lists (each read through its sha256) and
    the two reviewed files beside it; raises HlegCheckError at the first failing check."""
    manifest_path = Path(manifest_path)
    folder = manifest_path.parent
    try:
        pdf_bytes = ht.read_checked(manifest_path, ht.PDF_FILE)
        text_bytes = ht.read_checked(manifest_path, ht.TEXT_FILE)
        record_raw = ht.read_checked(manifest_path, ht.RECORD_FILE)
    except (ValueError, OSError) as exc:
        raise HlegCheckError("C0", [f"C0 {exc}"]) from exc
    try:
        facts = ht.read_pdf(pdf_bytes)
    except ImportError as exc:  # review M4: a missing library names its check
        raise HlegCheckError("C0", [f"C0 the hleg extra is not installed ({exc}): pip install -e '.[hleg]'"]) from exc
    c0 = check_c0(text_bytes, record_raw, facts)
    if c0:
        raise HlegCheckError("C0", c0)
    text, record = text_bytes.decode("utf-8"), json.loads(record_raw)
    reviewed_raw = _reviewed_file(folder, ht.EXCLUSIONS_FILE, "C2")
    rows_raw = _reviewed_file(folder, ht.WORD_ROWS_FILE, "C3")
    reviewed, rows = json.loads(reviewed_raw), json.loads(rows_raw)
    try:
        plain, layout = pypdf_pages(pdf_bytes)
    except ImportError as exc:
        raise HlegCheckError("C1", [f"C1 the hleg extra is not installed ({exc}): pip install -e '.[hleg]'"]) from exc
    for check, failures in (("C1", check_c1(text, record, plain)),
                            ("C2", check_c2(text, record, plain, reviewed, body_bottoms(facts)))):
        if failures:
            raise HlegCheckError(check, failures)
    c3, used = check_c3(text, record, {n: body_words(layout[n], n, record, reviewed) for n in ht.PAGES}, rows)
    if c3:
        raise HlegCheckError("C3", c3)
    c4 = check_c4(text, record)
    if c4:
        raise HlegCheckError("C4", c4)

    def ref(name: str, raw: bytes) -> dict[str, str]:
        return {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}

    return {
        "pdf": ref(ht.PDF_FILE, pdf_bytes), "derived_text": ref(ht.TEXT_FILE, text_bytes),
        "derivation_record": ref(ht.RECORD_FILE, record_raw),
        "reviewed_exclusions": ref(ht.EXCLUSIONS_FILE, reviewed_raw), "word_rows": ref(ht.WORD_ROWS_FILE, rows_raw),
        "checks_passed": ["C0", "C1", "C2", "C3", "C4"],
        "paragraphs": sum(1 for p in record["paragraphs"] if p["kind"] == "paragraph"),
        "requirement_headings": len(record["requirement_headings"]),
        "subtopic_headings": len(record["subtopic_headings"]),
        "page_joins": len(record["page_joins"]), "hyphen_joins": len(record["hyphen_joins"]),
        "markers_removed": len(record["markers_removed"]), "exclusions_reviewed": len(reviewed),
        "stretches_checked": len(stretches(text, record)), "word_rows_used": used,
    }

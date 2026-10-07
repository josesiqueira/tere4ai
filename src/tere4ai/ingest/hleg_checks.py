"""The checks C0 to C4 of the derived HLEG text against the Guidelines' official PDF.

@implements: DEC-25 (partial: the checks)
@grounded_by: ADD-01

Spec G D-G75 (3). pypdf, a parser separate from pdfplumber's pdfminer.six,
is the second reader. C0 re-derives both files byte for byte; C1 finds every
derived stretch (the text between two removed markers or page joins) in
pypdf's text of its page, whitespace removed; C2 accounts for every
character pypdf reads on the pages: derived, or one of the excluded items,
which must equal the reviewed list item by item and each pass the test of
its kind; C3 and C4 are added by the next part. A failing check raises
HlegCheckError, which names the check and carries its diagnostics, each
with its location. Deterministic, no model.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
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
        for item in made:
            if item["page"] == n and item["kind"] != "removed_marker":
                rest = rest.replace(_nows(item["text"]), "", 1)
        for item in made:  # the markers last: their digits occur in other text too
            if item["page"] == n and item["kind"] == "removed_marker":
                rest = rest.replace(item["text"], "", 1)
        if rest:
            failures.append(f"C2 page {n}: pypdf reads {rest[:60]!r}, which is neither derived nor excluded")
    return failures

"""One reader for the units of a Formex text: the 2024 act and the consolidated text.

@implements: DEC-01 (partial: the Formex unit reader)
@grounded_by: REF-01, REF-05, REF-08

Since B132 Layer 1 is parsed from EUR-Lex's consolidated text of 27 July
2026 in Formex (CELEX 02024R1689-20260727) and every unit is compared with
the 2024 act in Formex (spec G D-G68 (1)). Both comparisons need the same
units with the same ids, spans and text, so one reader reads both: the 2024
main body with its thirteen annex member files, and the consolidated file,
whose fourteen annexes sit inside it as CONS.ANNEX.

A unit is a Chapter, Section, Article, Paragraph, Subparagraph, Point,
Annex or AnnexItem. Ids and span names follow the scheme the 2024 parse
used (architecture.md Section 2): eu-ai-act:article-9:paragraph-1 with span
span:009.001; points eu-ai-act:article-5:paragraph-1:point-c with span
span:fmx:art_005.parag_001.np_c; an Article without PARAG gets one
paragraph-1 over its body, span span:art_16:body; annex items
eu-ai-act:annex-iii:point-5:a, items under a "Section A" heading
eu-ai-act:annex-viii:section-a:point-1, unnumbered dash items
eu-ai-act:annex-ii:item-1. Over the 2024 files the reader gives the 1,421
unit ids and span names the 2024 parse gave (tested). Letter-suffixed
numbers go through labels.py (eu-ai-act:article-4a, span:004a.001,
eu-ai-act:article-5:paragraph-1:point-ba). Two shapes only Annex XIV has
are read here: numbered GR.SEQ headings nested inside one another (ids by
the heading path, eu-ai-act:annex-xiv:point-2:a) and tables, one AnnexItem
per data row (eu-ai-act:annex-xiv:point-2:a:row-1, its marker the code in
the first cell, its text the cells' text).

The text rule (formex_text), the same for every unit and both files:
QUOT.START and QUOT.END become the quotation mark their CODE names (2018 is
the left single mark, 2019 the right one); DATE, HT, REF.DOC, REF.DOC.OJ,
FT, IE and LINK are inline and add nothing, except a superscript (HT
TYPE="SUP"), which adds a space so 10 to the power 25 reads "10 25" as the
HTML did, never "1025"; a NOTE (a footnote) is left out; a processing
instruction (a page break, a change marker) or a comment adds nothing;
every other tag is one space; entities are unescaped and
whitespace runs collapse. Ranges given as exclude (the wording the Omnibus
deleted, which the consolidated file keeps in place) are left out.

formex.py's tokenizer and helpers are reused (_parse_xml, _El, _walk,
_find, _child_roots, _marker). Its enrich_with_formex and subparagraphs.py
stay as the parse of the 2024 act's own files, which they read correctly;
they are no longer on the build path. Deterministic, no model calls.
"""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from pathlib import Path

from tere4ai.parse_legal_structure.formex import (
    _child_roots,
    _El,
    _find,
    _marker,
    _parse_xml,
    _walk,
)
from tere4ai.parse_legal_structure.labels import label_of, padded, sort_key
from tere4ai.parse_legal_structure.parser import REGULATION_ID

INLINE_TAGS = frozenset({"DATE", "HT", "QUOT.START", "QUOT.END", "REF.DOC", "REF.DOC.OJ", "FT", "IE", "LINK"})
_TOKEN = re.compile(r"<(\?[^>]*\?|![^>]*|/?([A-Za-z0-9._-]+)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)/?)>")
_NOTE = re.compile(r"<NOTE\b[^>]*>.*?</NOTE>", re.S)
_CODE = re.compile(r'CODE="([0-9A-Fa-f]{4})"')
_WS = re.compile(r"\s+")
_CHAPTER = re.compile(r"^CHAPTER\s+([IVXLC]+)$")
_SECTION = re.compile(r"^SECTION\s+(\d+)$")
_ANNEX_HEADING = re.compile(r"^ANNEX\s+([IVXLC]+)\b", re.IGNORECASE)
_SECTION_HEADING = re.compile(r"^Section\s+([A-Za-z0-9]+)")
_PARAG_IDENTIFIER = re.compile(r"^(\d{3}[A-Za-z]?)\.(\d{3}[A-Za-z]?)$")
OPEN_QUOTE = "\N{LEFT SINGLE QUOTATION MARK}"
FORMEX_METHOD = "formex_structure"
SUBPARAGRAPH_METHOD = "formex_subparagraph_v1"
BODY_FALLBACK_METHOD = "article_body_fallback"


def _visible(fragment: str) -> str:
    fragment = _NOTE.sub("", fragment)
    out: list[str] = []
    pos = 0
    for match in _TOKEN.finditer(fragment):
        out.append(fragment[pos : match.start()])
        tag = match.group(2)
        if tag is None:  # a processing instruction (a page break, a change marker) or a comment
            pass
        elif tag in ("QUOT.START", "QUOT.END"):
            code = _CODE.search(match.group(0))
            out.append(chr(int(code.group(1), 16)) if code else "")
        elif tag not in INLINE_TAGS or 'TYPE="SUP"' in match.group(0):
            out.append(" ")
        pos = match.end()
    out.append(fragment[pos:])
    return "".join(out)


def formex_text(text: str, start: int, end: int, exclude: list[tuple[int, int]] | None = None) -> str:
    """The visible text of text[start:end], the exclude ranges left out (module docstring)."""
    cuts = sorted((max(s, start), min(e, end)) for s, e in (exclude or []) if s < end and e > start)
    pieces: list[str] = []
    pos = start
    for cut_start, cut_end in cuts:
        if cut_start > pos:
            pieces.append(_visible(text[pos:cut_start]))
        pieces.append(" ")
        pos = max(pos, cut_end)
    if pos < end:
        pieces.append(_visible(text[pos:end]))
    return _WS.sub(" ", htmllib.unescape("".join(pieces))).strip()


@dataclass
class Unit:
    """One unit with its element's offsets in its file and its text or title."""

    id: str
    type: str
    parent: str
    edge_type: str
    file: str
    start: int
    end: int
    span_name: str
    anchor: str
    method: str = FORMEX_METHOD
    text: str | None = None
    title: str | None = None
    number: str | int | None = None
    index: str | int | None = None
    marker: str | None = None
    sort_key: int | None = None
    own_exclude: tuple[tuple[int, int], ...] = ()
    title_range: tuple[int, int] | None = None


@dataclass
class UnitTree:
    """The units of one text in document order and the decoded files they come from."""

    units: list[Unit] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)

    def by_id(self) -> dict[str, Unit]:
        return {u.id: u for u in self.units}


def _child(el: _El | None, tag: str) -> _El | None:
    if el is None:
        return None
    return next((c for c in el.children if c.tag == tag), None)


class _Reader:
    def __init__(self, tree: UnitTree, text: str, file: str) -> None:
        self.tree, self.text, self.file = tree, text, file
        self.seen = {u.id for u in tree.units}
        self.dash = 0
        self.row = 0

    def el_text(self, el: _El, exclude: list[_El] | None = None) -> str:
        return formex_text(self.text, el.start, el.end, [(c.start, c.end) for c in exclude or []])

    def add(self, unit: Unit) -> None:
        if unit.id in self.seen:
            raise ValueError(f"duplicate unit id {unit.id} in {self.file}")
        self.seen.add(unit.id)
        self.tree.units.append(unit)

    # enacting terms ----------------------------------------------------
    def divisions(self, el: _El, parent_id: str, chapter: str | None) -> None:
        for child in el.children:
            if child.tag == "ARTICLE":
                self.article(child, parent_id)
            elif child.tag == "DIVISION":
                title = _child(child, "TITLE")
                ti, sti = _find(title, "TI"), _find(title, "STI")
                heading = self.el_text(ti) if ti is not None else ""
                name = self.el_text(sti) if sti is not None else ""
                m_chapter, m_section = _CHAPTER.match(heading), _SECTION.match(heading)
                if m_chapter:
                    roman = m_chapter.group(1)
                    uid = f"{REGULATION_ID}:chapter-{roman.lower()}"
                    self.add(Unit(uid, "Chapter", REGULATION_ID, "HAS_CHAPTER", self.file, child.start, child.end,
                                  f"span:cpt_{roman}", f"cpt_{roman}", title=name, number=roman))
                    self.divisions(child, uid, roman)
                elif m_section and chapter is not None:
                    number = int(m_section.group(1))
                    uid = f"{parent_id}:section-{number}"
                    anchor = f"cpt_{chapter}.sct_{number}"
                    self.add(Unit(uid, "Section", parent_id, "HAS_SECTION", self.file, child.start, child.end,
                                  f"span:{anchor}", anchor, title=name, number=number))
                    self.divisions(child, uid, chapter)
                else:
                    raise ValueError(f"DIVISION heading {heading!r} in {self.file} is neither a Chapter nor a Section")

    def article(self, article: _El, parent_id: str) -> None:
        label = label_of(article.attrs["IDENTIFIER"])
        art_id = f"{REGULATION_ID}:article-{label}"
        ti, sti = _child(article, "TI.ART"), _child(article, "STI.ART")
        self.add(Unit(art_id, "Article", parent_id, "HAS_ARTICLE", self.file, article.start, article.end,
                      f"span:art_{label}", f"art_{label}", title=self.el_text(sti) if sti is not None else "",
                      number=label, sort_key=sort_key(label),
                      title_range=(sti.start, sti.end) if sti is not None else None))
        art_anchor = f"fmx:art_{padded(label)}"
        parags = _child_roots(article, "PARAG")
        for parag in parags:
            match = _PARAG_IDENTIFIER.match(parag.attrs.get("IDENTIFIER", ""))
            if match is None or label_of(match.group(1)) != label:
                raise ValueError(f"PARAG {parag.attrs.get('IDENTIFIER')!r} does not belong to Article {label}")
            par = label_of(match.group(2))
            no_parag = _find(parag, "NO.PARAG")
            shown = formex_text(self.text, no_parag.start, no_parag.end).lstrip(OPEN_QUOTE).rstrip(".")
            if shown != par:
                raise ValueError(f"PARAG {parag.attrs['IDENTIFIER']} is numbered {shown!r} in the text")
            par_id = f"{art_id}:paragraph-{par}"
            name = f"{padded(label)}.{padded(par)}"
            self.add(Unit(par_id, "Paragraph", art_id, "HAS_PARAGRAPH", self.file, parag.start, parag.end,
                          f"span:{name}", name, text=self.el_text(parag), index=par, sort_key=sort_key(par)))
            par_anchor = f"{art_anchor}.parag_{padded(par)}"
            self.paragraph_points(parag, par_id, par_anchor)
            alineas = [c for c in parag.children if c.tag == "ALINEA"]
            for k, alinea in enumerate(alineas[1:], start=2):
                anchor = f"{par_anchor}.alinea_{k}"
                self.add(Unit(f"{par_id}:subparagraph-{k}", "Subparagraph", par_id, "HAS_SUBPARAGRAPH", self.file,
                              alinea.start, alinea.end, f"span:{anchor}", anchor, method=SUBPARAGRAPH_METHOD,
                              text=self.el_text(alinea), index=k))
        if not parags:
            heading_end = max((h.end for h in (ti, sti) if h is not None), default=article.start)
            par_id = f"{art_id}:paragraph-1"
            self.add(Unit(par_id, "Paragraph", art_id, "HAS_PARAGRAPH", self.file, heading_end, article.end,
                          f"span:art_{label}:body", f"art_{label}", method=BODY_FALLBACK_METHOD,
                          text=formex_text(self.text, heading_end, article.end), index="1", sort_key=100))
            for np_el in _child_roots(article, "NP", skip_tags=frozenset({"QUOT.S", "PARAG"})):
                self.np(np_el, par_id, par_id, art_anchor, "Point", "HAS_POINT", "point")

    def paragraph_points(self, parag: _El, par_id: str, par_anchor: str) -> None:
        roots = _child_roots(parag, "NP")
        markers = [_marker(self.text, _child(n, "NO.P")) for n in roots if _child(n, "NO.P") is not None]
        colliding = len(markers) != len(set(markers))
        for np_el in roots:
            prefix, anchor = par_id, par_anchor
            if colliding:
                # Only Article 43(1): the subparagraphs restart the point
                # letters, so the id carries the subparagraph ordinal.
                alineas = [c for c in parag.children if c.tag == "ALINEA"]
                k = next(i for i, a in enumerate(alineas, start=1) if a.start <= np_el.start and np_el.end <= a.end)
                prefix, anchor = f"{par_id}:subparagraph-{k}", f"{par_anchor}.alinea_{k}"
            self.np(np_el, prefix, par_id, anchor, "Point", "HAS_POINT", "point")

    def np(self, np_el: _El, prefix: str, edge_from: str, parent_anchor: str, node_type: str,
           edge_type: str, segment: str) -> None:
        no_p = _child(np_el, "NO.P")
        if no_p is None:
            raise ValueError(f"NP without NO.P at offset {np_el.start} in {self.file}")
        marker = _marker(self.text, no_p)
        uid = f"{prefix}:point-{marker}" if segment == "point" else f"{prefix}:{marker}"
        anchor = f"{parent_anchor}.np_{marker}"
        self.add(Unit(uid, node_type, edge_from, edge_type, self.file, np_el.start, np_el.end, f"span:{anchor}",
                      anchor, text=self.el_text(np_el, exclude=[no_p]), marker=marker,
                      own_exclude=((no_p.start, no_p.end),)))
        child_segment = "point" if node_type == "Point" else "bare"
        for child in _child_roots(np_el, "NP"):
            self.np(child, uid, uid, anchor, node_type, edge_type, child_segment)

    # annexes -------------------------------------------------------------
    def annex(self, annex_el: _El) -> None:
        title = _child(annex_el, "TITLE")
        ti = _find(title, "TI")
        heading = self.el_text(ti) if ti is not None else ""
        match = _ANNEX_HEADING.match(heading)
        if match is None:
            raise ValueError(f"cannot read the annex number from {heading[:40]!r} in {self.file}")
        roman = match.group(1).upper()
        contents = _child(annex_el, "CONTENTS")
        if contents is None:
            raise ValueError(f"Annex {roman} in {self.file} has no CONTENTS")
        sti = _find(title, "STI")
        lead = None
        if sti is not None:  # Annexes I to IX and XI to XIII
            name = self.el_text(sti)
        elif heading[match.end():].strip():  # Annex X: number and title in one TI
            name = heading[match.end():].strip()
        else:  # Annex XIV: the first paragraph of the contents is the title
            lead = _child(contents, "P")
            name = self.el_text(lead) if lead is not None else ""
        annex_id = f"{REGULATION_ID}:annex-{roman.lower()}"
        self.add(Unit(annex_id, "Annex", REGULATION_ID, "HAS_ANNEX", self.file, annex_el.start, annex_el.end,
                      f"span:anx_{roman}", f"anx_{roman}", title=name, number=roman))
        self.dash = 0
        self.annex_children([c for c in contents.children if c is not lead], annex_id, annex_id,
                            f"fmx:anx_{roman.lower()}", "point")

    def annex_children(self, children: list[_El], prefix: str, edge_from: str, anchor: str, segment: str) -> None:
        for child in children:
            if child.tag == "NP":
                self.np(child, prefix, edge_from, anchor, "AnnexItem", "HAS_ANNEX_ITEM", segment)
            elif child.tag == "GR.SEQ":
                self.gr_seq(child, prefix, edge_from, anchor, segment)
            elif child.tag == "LIST" and child.attrs.get("TYPE") == "DASH":
                for item in (c for c in child.children if c.tag == "ITEM"):
                    nps = _child_roots(item, "NP")
                    for np_el in nps:
                        self.np(np_el, prefix, edge_from, anchor, "AnnexItem", "HAS_ANNEX_ITEM", segment)
                    if not nps:  # Annex II: unnumbered dash items, ordinal ids
                        self.dash += 1
                        item_anchor = f"{anchor}.item_{self.dash}"
                        self.add(Unit(f"{prefix}:item-{self.dash}", "AnnexItem", edge_from, "HAS_ANNEX_ITEM",
                                      self.file, item.start, item.end, f"span:{item_anchor}", item_anchor,
                                      text=self.el_text(item), marker="-"))
            elif child.tag == "TBL":
                self.row = 0
                self.annex_children(child.children, prefix, edge_from, anchor, segment)
            elif child.tag == "ROW":
                if child.attrs.get("TYPE") == "HEADER":
                    continue
                self.row += 1
                cells = [c for c in child.children if c.tag == "CELL"]
                row_anchor = f"{anchor}.row_{self.row}"
                self.add(Unit(f"{prefix}:row-{self.row}", "AnnexItem", edge_from, "HAS_ANNEX_ITEM", self.file,
                              child.start, child.end, f"span:{row_anchor}", row_anchor,
                              text=" ".join(self.el_text(c) for c in cells),
                              marker=self.el_text(cells[0]) if cells else str(self.row)))
            else:
                self.annex_children(child.children, prefix, edge_from, anchor, segment)

    def gr_seq(self, gr_seq: _El, prefix: str, edge_from: str, anchor: str, segment: str) -> None:
        title = _child(gr_seq, "TITLE")
        if title is None:
            raise ValueError(f"GR.SEQ without TITLE in {self.file}")
        body = [c for c in gr_seq.children if c is not title]
        title_np = _find(title, "NP")
        if title_np is not None:
            # A numbered heading (Annexes VII, X, XIV): the item spans the
            # whole GR.SEQ; its text is the heading plus any paragraph of the
            # body that holds no item; the body's items are its children.
            no_p = _child(title_np, "NO.P")
            marker = _marker(self.text, no_p)
            uid = f"{prefix}:point-{marker}" if segment == "point" else f"{prefix}:{marker}"
            item_anchor = f"{anchor}.np_{marker}"
            loose = [c for c in body if c.tag == "P"
                     and not any(d.tag in ("NP", "TBL", "GR.SEQ", "LIST") for d in _walk(c))]
            item_text = " ".join([self.el_text(title_np, exclude=[no_p])] + [self.el_text(p) for p in loose])
            self.add(Unit(uid, "AnnexItem", edge_from, "HAS_ANNEX_ITEM", self.file, gr_seq.start, gr_seq.end,
                          f"span:{item_anchor}", item_anchor, text=item_text, marker=marker,
                          own_exclude=((no_p.start, no_p.end),)))
            self.annex_children(body, uid, uid, item_anchor, "bare")
            return
        heading = self.el_text(title)
        match = _SECTION_HEADING.match(heading)
        if match is None:
            raise ValueError(f"GR.SEQ heading {heading[:60]!r} in {self.file} is neither numbered nor a Section")
        # A Section heading (Annexes I, VIII, XI) has no node: its letter goes
        # into the item ids, the edges start at the node above.
        slug = match.group(1).lower()
        self.annex_children(body, f"{prefix}:section-{slug}", edge_from, f"{anchor}.sct_{slug}", "point")


def read_text_units(text: str, file: str, tree: UnitTree | None = None) -> UnitTree:
    """Read the enacting terms and every annex of one Formex file into tree."""
    tree = tree if tree is not None else UnitTree()
    tree.texts[file] = text
    reader = _Reader(tree, text, file)
    root = _parse_xml(text)
    terms = _find(root, "ENACTING.TERMS")
    if terms is not None:
        reader.divisions(terms, REGULATION_ID, None)
    for annex in (el for el in _walk(root) if el.tag in ("ANNEX", "CONS.ANNEX")):
        reader.annex(annex)
    return tree


def read_formex_2024(formex_dir: Path | str, main_file: str, annex_files: list[str]) -> UnitTree:
    """The 2024 act: its main body, then its annex member files in order."""
    formex_dir = Path(formex_dir)
    tree = UnitTree()
    for name in [main_file, *annex_files]:
        read_text_units((formex_dir / name).read_text(encoding="utf-8"), f"formex/{name}", tree)
    return tree


def read_consolidated(path: Path | str, rel: str) -> UnitTree:
    """The consolidated text: one file, enacting terms then CONS.ANNEX."""
    return read_text_units(Path(path).read_text(encoding="utf-8"), rel)

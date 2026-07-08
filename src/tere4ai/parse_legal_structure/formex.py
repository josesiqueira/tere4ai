"""Deterministic Formex 4 enrichment: Point and AnnexItem depth for Layer 1.

@implements: DEC-01 (partial: Formex point and annex-item depth)
@grounded_by: REF-27, REF-08, REF-05

Extends the Layer 1 dump built from the EUR-Lex HTML manifestation with the
point, subpoint, and annex-item granularity that only the Formex 4 (fmx4)
manifestation carries (docs/architecture.md Section 6, ingestion route b).
The frozen Formex member files live in data/snapshots/formex/ and are
verified against data/snapshots/MANIFEST.json before parsing.

No LLM or model client is used anywhere in this module (DEC-01): the
structure is derived purely from the Formex XML element tree (ARTICLE,
PARAG, NO.PARAG, ALINEA, NP, NO.P, LIST, GR.SEQ) via a position-tracking
tokenizer over the raw file text, so two runs over the same snapshots
produce byte-identical output apart from the built_at timestamp.

Verified Formex structure (inspected against the frozen files):
  - Main body L_202401689EN.000101.fmx.xml: 113 ARTICLE (IDENTIFIER "001"
    to "113"), 509 PARAG of which 9 sit inside QUOT.S (quoted text of
    AMENDED acts in Articles 102 to 110) and are skipped; the 500 kept
    PARAG all carry NO.PARAG and an IDENTIFIER "aaa.ppp" that matches the
    containing article. Points are NP with a NO.P marker inside
    LIST TYPE="alpha" / "ARAB"; nested romanettes appear as an inner
    LIST TYPE="roman" wrapped in a P INSIDE the parent NP (never NP
    directly inside NP). Unnumbered subparagraphs are ALINEA (no node
    emitted; their NP descendants are still points of the paragraph).
  - 14 articles (3, 4, 16, 32, 39, 66, 85, 87, 94, 102, 103, 104, 110,
    113) have no PARAG; their points attach to the HTML fallback
    paragraph-1 (reconciliation rule below).
  - Annex files: items are NP under CONTENTS. Three container variants:
    plain NP lists (Annexes III to VI, IX, XII, XIII), GR.SEQ whose TITLE
    is itself a numbered NP with the sub-items in the GR.SEQ body
    (Annexes VII, X), and GR.SEQ section headings ("Section A", "Section
    1") with the items in the body (Annexes I, VIII, XI). Annexes VIII
    and XI RESTART item numbering per section, so items inside a section
    heading carry a section segment in their id
    (eu-ai-act:annex-viii:section-a:point-1) to keep ids unique. Annex II
    is a LIST TYPE="DASH" of unnumbered items; these are emitted as
    AnnexItem with marker "-" and ordinal ids (eu-ai-act:annex-ii:item-1).

Reconciliation rule (fail loudly): Formex ARTICLE IDENTIFIER "005" maps to
eu-ai-act:article-5; a kept PARAG with NO.PARAG N maps to
eu-ai-act:article-5:paragraph-N, which MUST already exist in the dump
(raise if not; never skip silently). Articles without PARAG map to the
HTML fallback paragraph-1.
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure.parser import (
    DEFAULT_MANIFEST_PATH,
    REGULATION_ID,
    _hierarchy_edge,
    _source_span,
)

MAIN_BODY_FILE = "L_202401689EN.000101.fmx.xml"
DOC_FILE = "L_202401689EN.doc.fmx.xml"
TOC_FILE = "L_202401689EN.toc.fmx.xml"

FORMEX_METHOD = "formex_structure"

# The 13 annexes of the Act, in legal order.
_ANNEX_ROMANS = [
    "I", "II", "III", "IV", "V", "VI", "VII",
    "VIII", "IX", "X", "XI", "XII", "XIII",
]

# One XML token: processing instruction, declaration/comment, or a tag.
# Group 1: "/" for a closing tag; group 2: tag name; group 4: "/" if
# self-closing. Formex files carry no CDATA sections.
_RE_XML_TOKEN = re.compile(
    r"<(?:\?[^>]*\?|![^>]*|(/?)([A-Za-z0-9._-]+)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?))>"
)
_RE_ATTR = re.compile(r"([A-Za-z0-9._-]+)=\"([^\"]*)\"")
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_ANNEX_TITLE = re.compile(r"^ANNEX\s+([IVXLC]+)\b")
_RE_SECTION_TITLE = re.compile(r"^Section\s+([A-Za-z0-9]+)")
_RE_MARKER = re.compile(r"^\(?([A-Za-z0-9.]+?)\)?\.?$")


@dataclass
class _El:
    """XML element with char offsets into the decoded file text."""

    tag: str
    attrs: dict[str, str]
    start: int  # offset of the opening "<"
    end: int = 0  # offset just past the closing ">"
    children: list["_El"] = field(default_factory=list)


def _parse_xml(text: str) -> _El:
    """Parse well-formed Formex XML into an offset-carrying element tree."""
    root = _El("#document", {}, 0, len(text))
    stack = [root]
    for m in _RE_XML_TOKEN.finditer(text):
        tag = m.group(2)
        if tag is None:  # processing instruction or declaration
            continue
        if m.group(1) == "/":  # closing tag
            if stack[-1].tag != tag:
                raise ValueError(
                    f"malformed Formex XML: </{tag}> closes <{stack[-1].tag}> at {m.start()}"
                )
            stack[-1].end = m.end()
            stack.pop()
            continue
        el = _El(tag, dict(_RE_ATTR.findall(m.group(3) or "")), m.start())
        stack[-1].children.append(el)
        if m.group(4) == "/":  # self-closing
            el.end = m.end()
        else:
            stack.append(el)
    if len(stack) != 1:
        raise ValueError(f"malformed Formex XML: unclosed <{stack[-1].tag}>")
    return root


def _strip_text(fragment: str) -> str:
    """Visible text: tags removed, entities unescaped, whitespace collapsed."""
    text = _RE_TAG.sub(" ", fragment)
    text = htmllib.unescape(text)
    return _RE_WS.sub(" ", text).strip()


def _el_text(text: str, el: _El, exclude: list[_El] | None = None) -> str:
    """Visible text of an element, minus the slices of excluded children."""
    if not exclude:
        return _strip_text(text[el.start : el.end])
    cuts = sorted((c.start, c.end) for c in exclude)
    parts, pos = [], el.start
    for c_start, c_end in cuts:
        parts.append(text[pos:c_start])
        pos = c_end
    parts.append(text[pos : el.end])
    return _strip_text(" ".join(parts))


def _walk(el: _El):
    for child in el.children:
        yield child
        yield from _walk(child)


def _find(el: _El, tag: str) -> _El | None:
    for node in _walk(el):
        if node.tag == tag:
            return node
    return None


def _child_roots(el: _El, tag: str, skip_tags: frozenset[str] = frozenset({"QUOT.S"})):
    """Top-level descendants with the given tag: matched elements are not
    descended into, and skip_tags subtrees (quoted text of other acts) are
    ignored entirely."""
    out: list[_El] = []

    def rec(node: _El) -> None:
        for child in node.children:
            if child.tag in skip_tags:
                continue
            if child.tag == tag:
                out.append(child)
            else:
                rec(child)

    rec(el)
    return out


def _marker(text: str, no_p: _El) -> str:
    """Normalise a NO.P marker: '(a)' -> 'a', '(i)' -> 'i', '1.' -> '1',
    '3.1.' -> '3.1'. Lowercase, no parentheses, no trailing dot."""
    visible = _strip_text(text[no_p.start : no_p.end])
    m = _RE_MARKER.match(visible)
    if not m:
        raise ValueError(f"unrecognised Formex NO.P marker: {visible!r}")
    return m.group(1).lower()


def _alinea_index(parag: _El, np_el: _El) -> int:
    """1-based ordinal of the top-level ALINEA of parag that contains np_el."""
    index = 0
    for child in parag.children:
        if child.tag != "ALINEA":
            continue
        index += 1
        if child.start <= np_el.start and np_el.end <= child.end:
            return index
    raise ValueError(
        f"NP at offset {np_el.start} is not inside any ALINEA of PARAG "
        f"{parag.attrs.get('IDENTIFIER')}"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_formex_manifest(manifest_path: Path) -> dict[str, str]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return {
        entry["file"]: entry["sha256"]
        for entry in manifest["snapshots"]
        if entry["file"].startswith("formex/")
    }


class _Emitter:
    """Collects Point / AnnexItem nodes and their hierarchy edges."""

    def __init__(self, build_id: str, existing_ids: set[str]) -> None:
        self.build_id = build_id
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.seen_ids = set(existing_ids)

    def emit(
        self,
        node_type: str,
        node_id: str,
        marker: str,
        node_text: str,
        parent_id: str,
        edge_type: str,
        anchor: str,
        snapshot_file: str,
        sha256: str,
        start: int,
        end: int,
    ) -> None:
        if node_id in self.seen_ids:
            raise ValueError(f"duplicate Formex-derived node id: {node_id}")
        self.seen_ids.add(node_id)
        span = _source_span(f"span:{anchor}", snapshot_file, sha256, start, end, anchor)
        self.nodes.append(
            {
                "id": node_id,
                "layer": 1,
                "type": node_type,
                "marker": marker,
                "text": node_text,
                "source_span": span,
            }
        )
        self.edges.append(
            _hierarchy_edge(
                edge_type,
                parent_id,
                node_id,
                span["span_id"],
                self.build_id,
                method=FORMEX_METHOD,
            )
        )


def _emit_np_tree(
    emitter: _Emitter,
    text: str,
    np_el: _El,
    id_prefix: str,
    edge_from: str,
    parent_anchor: str,
    node_type: str,
    edge_type: str,
    id_segment: str,
    snapshot_file: str,
    sha256: str,
) -> None:
    """Emit one NP as a node, then its nested NPs as children.

    id_prefix builds the child id; edge_from is the EXISTING node the
    hierarchy edge starts at (they differ when the id carries a structural
    qualifier such as an annex section that has no node of its own).
    id_segment "point" yields child ids like prefix:point-c (articles and
    top-level annex items); id_segment "bare" yields prefix:c (nested annex
    items, per the id convention in docs/architecture.md Section 2).
    """
    no_p = None
    for child in np_el.children:
        if child.tag == "NO.P":
            no_p = child
            break
    if no_p is None:
        raise ValueError(f"NP without NO.P marker at offset {np_el.start} in {snapshot_file}")
    marker = _marker(text, no_p)
    node_id = (
        f"{id_prefix}:point-{marker}" if id_segment == "point" else f"{id_prefix}:{marker}"
    )
    anchor = f"{parent_anchor}.np_{marker}"
    nested = _child_roots(np_el, "NP")
    node_text = _el_text(text, np_el, exclude=[no_p])
    emitter.emit(
        node_type, node_id, marker, node_text, edge_from, edge_type,
        anchor, snapshot_file, sha256, np_el.start, np_el.end,
    )
    child_segment = "point" if node_type == "Point" else "bare"
    for child_np in nested:
        _emit_np_tree(
            emitter, text, child_np, node_id, node_id, anchor, node_type, edge_type,
            child_segment, snapshot_file, sha256,
        )


def _enrich_main_body(
    emitter: _Emitter, text: str, snapshot_file: str, sha256: str, paragraph_ids: set[str]
) -> None:
    root = _parse_xml(text)
    articles = _child_roots(root, "ARTICLE")
    if len(articles) != 113:
        raise ValueError(f"expected 113 ARTICLE elements, found {len(articles)}")

    for article in articles:
        art_no = int(article.attrs["IDENTIFIER"])
        art_anchor = f"fmx:art_{art_no:03d}"
        parags = _child_roots(article, "PARAG")

        for parag in parags:
            no_parag = _find(parag, "NO.PARAG")
            if no_parag is None:
                raise ValueError(
                    f"PARAG {parag.attrs.get('IDENTIFIER')} outside QUOT.S lacks NO.PARAG"
                )
            par_no = int(_strip_text(text[no_parag.start : no_parag.end]).rstrip("."))
            identifier = parag.attrs.get("IDENTIFIER", "")
            if identifier != f"{art_no:03d}.{par_no:03d}":
                raise ValueError(
                    f"PARAG identifier {identifier!r} does not match "
                    f"article {art_no} paragraph {par_no}"
                )
            paragraph_id = f"{REGULATION_ID}:article-{art_no}:paragraph-{par_no}"
            if paragraph_id not in paragraph_ids:
                raise ValueError(
                    f"Formex paragraph {identifier} maps to {paragraph_id}, "
                    "which does not exist in the HTML-derived dump"
                )
            par_anchor = f"{art_anchor}.parag_{par_no:03d}"
            np_roots = _child_roots(parag, "NP")
            markers = [
                _marker(text, next(c for c in np_el.children if c.tag == "NO.P"))
                for np_el in np_roots
                if any(c.tag == "NO.P" for c in np_el.children)
            ]
            colliding = len(markers) != len(set(markers))
            for np_el in np_roots:
                id_prefix, parent_anchor = paragraph_id, par_anchor
                if colliding:
                    # A paragraph whose subparagraphs restart the point
                    # markers (only Article 43(1) in this Act): scope each
                    # point id by its subparagraph ordinal, matching the
                    # Act's citation style ("first subparagraph, point (a)").
                    # The edge still starts at the Paragraph node.
                    k = _alinea_index(parag, np_el)
                    id_prefix = f"{paragraph_id}:subparagraph-{k}"
                    parent_anchor = f"{par_anchor}.alinea_{k}"
                _emit_np_tree(
                    emitter, text, np_el, id_prefix, paragraph_id, parent_anchor,
                    "Point", "HAS_POINT", "point", snapshot_file, sha256,
                )

        if not parags:
            # Article without numbered paragraphs: the HTML parse gave it a
            # fallback paragraph-1; its points attach there.
            paragraph_id = f"{REGULATION_ID}:article-{art_no}:paragraph-1"
            if paragraph_id not in paragraph_ids:
                raise ValueError(
                    f"article {art_no} has no PARAG and no fallback {paragraph_id} in the dump"
                )
            for np_el in _child_roots(article, "NP", skip_tags=frozenset({"QUOT.S", "PARAG"})):
                _emit_np_tree(
                    emitter, text, np_el, paragraph_id, paragraph_id, art_anchor,
                    "Point", "HAS_POINT", "point", snapshot_file, sha256,
                )
        else:
            # Sanity: no stray points outside the paragraphs of this article.
            stray = _child_roots(article, "NP", skip_tags=frozenset({"QUOT.S", "PARAG"}))
            if stray:
                raise ValueError(
                    f"article {art_no} has {len(stray)} NP outside its PARAG elements"
                )


def _annex_order_from_doc(doc_text: str) -> list[str]:
    """Ordered annex member files as listed by DOC.SUB.PUB TYPE=ANNEX."""
    root = _parse_xml(doc_text)
    files = []
    for node in _walk(root):
        if node.tag == "DOC.SUB.PUB" and node.attrs.get("TYPE") == "ANNEX":
            ref = _find(node, "REF.PHYS")
            if ref is None or "FILE" not in ref.attrs:
                raise ValueError("DOC.SUB.PUB annex entry without REF.PHYS FILE")
            files.append(ref.attrs["FILE"])
    return files


def _enrich_annex(
    emitter: _Emitter, text: str, snapshot_file: str, sha256: str, annex_ids: set[str]
) -> str:
    """Emit the AnnexItem tree of one annex member file; returns its Roman."""
    root = _parse_xml(text)
    title = _find(root, "TITLE")
    ti = _find(title, "TI") if title is not None else None
    if ti is None:
        raise ValueError(f"annex file {snapshot_file} has no TITLE/TI")
    m = _RE_ANNEX_TITLE.match(_el_text(text, ti))
    if not m:
        raise ValueError(f"cannot read annex numeral from {snapshot_file} title")
    roman = m.group(1)
    annex_id = f"{REGULATION_ID}:annex-{roman.lower()}"
    if annex_id not in annex_ids:
        raise ValueError(f"annex {roman} maps to {annex_id}, missing from the dump")
    annex_anchor = f"fmx:anx_{roman.lower()}"

    contents = _find(root, "CONTENTS")
    if contents is None:
        raise ValueError(f"annex file {snapshot_file} has no CONTENTS")

    dash_count = 0

    def emit_children(
        children: list[_El], id_prefix: str, edge_from: str, parent_anchor: str, segment: str
    ) -> None:
        """Dispatch a sibling list: NP becomes an item, GR.SEQ a container,
        DASH lists yield unnumbered items, everything else is recursed."""
        nonlocal dash_count
        for child in children:
            if child.tag == "NP":
                _emit_np_tree(
                    emitter, text, child, id_prefix, edge_from, parent_anchor,
                    "AnnexItem", "HAS_ANNEX_ITEM", segment, snapshot_file, sha256,
                )
            elif child.tag == "GR.SEQ":
                emit_gr_seq(child)
            elif child.tag == "LIST" and child.attrs.get("TYPE") == "DASH":
                for item in child.children:
                    if item.tag != "ITEM":
                        continue
                    nps = _child_roots(item, "NP")
                    if nps:
                        for np_el in nps:
                            _emit_np_tree(
                                emitter, text, np_el, id_prefix, edge_from,
                                parent_anchor, "AnnexItem", "HAS_ANNEX_ITEM",
                                segment, snapshot_file, sha256,
                            )
                        continue
                    # Unnumbered dash item (Annex II): ordinal id, marker "-".
                    dash_count += 1
                    emitter.emit(
                        "AnnexItem",
                        f"{id_prefix}:item-{dash_count}",
                        "-",
                        _el_text(text, item),
                        edge_from,
                        "HAS_ANNEX_ITEM",
                        f"{parent_anchor}.item_{dash_count}",
                        snapshot_file,
                        sha256,
                        item.start,
                        item.end,
                    )
            else:
                emit_children(child.children, id_prefix, edge_from, parent_anchor, segment)

    def emit_gr_seq(gr_seq: _El) -> None:
        """GR.SEQ is either a numbered item whose TITLE holds the NP
        (Annexes VII, X) or a section heading (Annexes I, VIII, XI)."""
        gr_title = None
        for child in gr_seq.children:
            if child.tag == "TITLE":
                gr_title = child
                break
        if gr_title is None:
            raise ValueError(f"GR.SEQ without TITLE in {snapshot_file}")
        title_np = _find(gr_title, "NP")
        if title_np is not None:
            no_p = _find(title_np, "NO.P")
            if no_p is None:
                raise ValueError(f"GR.SEQ title NP without NO.P in {snapshot_file}")
            marker = _marker(text, no_p)
            item_id = f"{annex_id}:point-{marker}"
            item_anchor = f"{annex_anchor}.np_{marker}"
            # The item spans the whole GR.SEQ (heading plus body); its text
            # is the heading text, the body items become its children.
            emitter.emit(
                "AnnexItem", item_id, marker, _el_text(text, title_np, exclude=[no_p]),
                annex_id, "HAS_ANNEX_ITEM", item_anchor,
                snapshot_file, sha256, gr_seq.start, gr_seq.end,
            )
            emit_children(
                [c for c in gr_seq.children if c.tag != "TITLE"],
                item_id, item_id, item_anchor, "bare",
            )
        else:
            heading = _el_text(text, gr_title)
            m_sect = _RE_SECTION_TITLE.match(heading)
            if not m_sect:
                raise ValueError(
                    f"GR.SEQ heading {heading[:60]!r} in {snapshot_file} is neither "
                    "a numbered item nor a Section heading"
                )
            # Section heading with no node of its own: the section slug goes
            # into the item ids (Annexes VIII and XI restart numbering per
            # section) while the edges start at the Annex node.
            slug = m_sect.group(1).lower()
            section_prefix = f"{annex_id}:section-{slug}"
            section_anchor = f"{annex_anchor}.sct_{slug}"
            emit_children(
                [c for c in gr_seq.children if c.tag != "TITLE"],
                section_prefix, annex_id, section_anchor, "point",
            )

    emit_children(contents.children, annex_id, annex_id, annex_anchor, "point")
    return roman


def enrich_with_formex(
    dump: dict[str, Any],
    formex_dir: Path | str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Enrich a Layer 1 dump with Point and AnnexItem nodes from Formex 4.

    Verifies every parsed member file against MANIFEST.json (frozen-source
    rule), parses the main body for points and the 13 annex files for annex
    items, and appends the nodes and HAS_POINT / HAS_ANNEX_ITEM edges to the
    dump in place. Returns the dump. Raises (never skips silently) when a
    Formex paragraph or annex has no counterpart in the HTML-derived dump.
    """
    manifest_path = Path(manifest_path)
    if formex_dir is None:
        formex_dir = manifest_path.parent / "formex"
    formex_dir = Path(formex_dir)

    shas = _load_formex_manifest(manifest_path)

    def load(filename: str) -> tuple[str, str, str]:
        rel = f"formex/{filename}"
        if rel not in shas:
            raise ValueError(f"{rel} is not listed in {manifest_path}")
        path = formex_dir / filename
        actual = _sha256(path)
        if actual != shas[rel]:
            raise ValueError(
                f"snapshot checksum mismatch for {rel}: manifest {shas[rel]}, file {actual}"
            )
        return path.read_text(encoding="utf-8"), rel, actual

    paragraph_ids = {n["id"] for n in dump["nodes"] if n.get("type") == "Paragraph"}
    annex_ids = {n["id"] for n in dump["nodes"] if n.get("type") == "Annex"}
    emitter = _Emitter(dump["build"]["build_id"], {n["id"] for n in dump["nodes"]})

    main_text, main_rel, main_sha = load(MAIN_BODY_FILE)
    _enrich_main_body(emitter, main_text, main_rel, main_sha, paragraph_ids)

    # Annex member files in document order, verified against the doc file.
    doc_text, _, _ = load(DOC_FILE)
    annex_files = _annex_order_from_doc(doc_text)
    if len(annex_files) != 13:
        raise ValueError(f"doc file lists {len(annex_files)} annex members, expected 13")

    parsed_files = [(main_rel, main_sha)]
    romans = []
    for filename in annex_files:
        annex_text, rel, sha = load(filename)
        romans.append(_enrich_annex(emitter, annex_text, rel, sha, annex_ids))
        parsed_files.append((rel, sha))
    if romans != _ANNEX_ROMANS:
        raise ValueError(f"annex files out of order: parsed {romans}")

    dump["nodes"] = dump["nodes"] + emitter.nodes
    dump["edges"] = dump["edges"] + emitter.edges
    known = {s["file"] for s in dump["build"]["snapshots"]}
    for rel, sha in parsed_files:
        if rel not in known:
            dump["build"]["snapshots"].append({"file": rel, "sha256": sha})
    return dump

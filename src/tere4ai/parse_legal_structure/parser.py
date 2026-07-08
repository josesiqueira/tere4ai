"""Deterministic Layer 1 parser for the frozen EUR-Lex HTML manifestation.

@implements: DEC-01
@grounded_by: REF-27, REF-08

Parses the frozen snapshot of Regulation (EU) 2024/1689 (data/snapshots/,
checksummed in MANIFEST.json) into the Layer 1 structural mirror defined in
docs/architecture.md Sections 1, 2, 6, and 10: Regulation, Chapter, Section,
Article, Paragraph, Recital, and Annex nodes, plus hierarchy edges, all with
source spans into the snapshot. No LLM or model client is used anywhere in
this module (DEC-01): the structure is derived purely from the verified HTML
anchor id schemes (cpt_R, cpt_R.sct_N, art_N, NNN.MMM, rct_N, anx_R) by
regular expressions over the raw snapshot text, so two runs over the same
snapshot produce byte-identical output apart from the built_at timestamp.

Anchor-scheme note (verified against the snapshot): inside the amendment
articles (Articles 102 to 110, which amend other Union acts) the numeric
NNN.MMM anchors refer to the AMENDED regulation's article and paragraph
numbers, not to this Regulation. A numeric anchor is therefore accepted as a
Paragraph of Article N only when its article prefix equals the number of the
article that contains it in document order; the 9 mismatched anchors (quoted
amendment text) are skipped. Articles left without any own paragraph anchor
receive a single fallback Paragraph built from the article body text, with
edge method "article_body_fallback".
"""

from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REGULATION_ID = "eu-ai-act"
REGULATION_TITLE = "Regulation (EU) 2024/1689 (Artificial Intelligence Act)"
TERE4AI_VERSION = "2.0.0a0"

# Default project paths (repo root is three levels above this file:
# src/tere4ai/parse_legal_structure/parser.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = _REPO_ROOT / "data" / "snapshots" / "MANIFEST.json"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "graph_dumps" / "layer1.json"

# Verified anchor id schemes (docs/architecture.md Section 6).
_RE_CHAPTER = re.compile(r"^cpt_([IVXLC]+)$")
_RE_CHAPTER_TITLE = re.compile(r"^cpt_([IVXLC]+)\.tit_1$")
_RE_SECTION = re.compile(r"^cpt_([IVXLC]+)\.sct_(\d+)$")
_RE_SECTION_TITLE = re.compile(r"^cpt_([IVXLC]+)\.sct_(\d+)\.tit_1$")
_RE_ARTICLE = re.compile(r"^art_(\d+)$")
_RE_ARTICLE_TITLE = re.compile(r"^art_(\d+)\.tit_1$")
_RE_PARAGRAPH = re.compile(r"^(\d{3})\.(\d{3})$")
_RE_RECITAL = re.compile(r"^rct_(\d+)$")
_RE_ANNEX = re.compile(r"^anx_([IVXLC]+)$")

_RE_ID_ATTR = re.compile(r'id="([^"]+)"')
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_ANNEX_DOC_TI = re.compile(r'<p[^>]*class="oj-doc-ti"[^>]*>(.*?)</p>', re.S)

# Structural ranks used to close spans: an element ends where the next anchor
# of equal or higher rank begins. Recitals sit at article rank (both are
# direct children of a rank-1 container in document order).
_RANK = {"chapter": 1, "annex": 1, "section": 2, "article": 3, "recital": 3, "paragraph": 4}


@dataclass
class _Anchor:
    kind: str
    anchor_id: str
    start: int  # offset of the opening "<" of the anchor's element tag
    end: int = 0  # filled in by _close_spans
    number: Any = None  # int for art/rct/par index, str Roman for cpt/anx
    chapter: str | None = None  # owning chapter Roman numeral (sections, articles)
    section: int | None = None  # owning section number (articles inside a section)
    extra: dict = field(default_factory=dict)


def _strip_text(fragment: str) -> str:
    """Visible text of an HTML fragment: tags removed, entities unescaped, whitespace collapsed."""
    text = _RE_TAG.sub(" ", fragment)
    text = htmllib.unescape(text)
    return _RE_WS.sub(" ", text).strip()


def _title_from_div(text: str, tag_start: int) -> str:
    """Text of an eli-title div: the div holds only <p>/<span>, so it ends at the first </div>."""
    close = text.find("</div>", tag_start)
    if close == -1:
        return ""
    return _strip_text(text[tag_start:close])


def _source_span(
    span_id: str, snapshot_file: str, sha256: str, start: int, end: int, anchor: str | None
) -> dict[str, Any]:
    span: dict[str, Any] = {
        "span_id": span_id,
        "snapshot_file": snapshot_file,
        "snapshot_sha256": sha256,
        "start": start,
        "end": end,
    }
    if anchor is not None:
        span["anchor"] = anchor
    return span


def _hierarchy_edge(
    edge_type: str,
    from_id: str,
    to_id: str,
    source_span_id: str,
    build_id: str,
    method: str = "html_anchor_hierarchy",
) -> dict[str, Any]:
    return {
        "edge_id": f"edge:{edge_type.lower()}:{to_id}",
        "edge_type": edge_type,
        "from": from_id,
        "to": to_id,
        "provenance_class": "EXTRACTED_SOURCE",
        "source_span_id": source_span_id,
        "method": method,
        "confidence": 1.0,
        "review_status": "auto_accepted",
        "build_id": build_id,
    }


def _collect_anchors(text: str) -> tuple[list[_Anchor], dict[str, int]]:
    """Walk every id attribute in document order.

    Returns the structural anchors (with chapter/section/article membership
    resolved from document order) and a map of title-anchor id to the offset
    of its element's opening tag.
    """
    structural: list[_Anchor] = []
    titles: dict[str, int] = {}
    current_chapter: str | None = None
    current_section: int | None = None
    current_article: int | None = None
    seen_paragraph_ids: set[tuple[int, int]] = set()

    for match in _RE_ID_ATTR.finditer(text):
        anchor_id = match.group(1)
        tag_start = text.rfind("<", 0, match.start())

        m = _RE_CHAPTER.match(anchor_id)
        if m:
            current_chapter, current_section, current_article = m.group(1), None, None
            structural.append(_Anchor("chapter", anchor_id, tag_start, number=m.group(1)))
            continue
        m = _RE_SECTION.match(anchor_id)
        if m:
            current_section = int(m.group(2))
            current_article = None
            structural.append(
                _Anchor(
                    "section",
                    anchor_id,
                    tag_start,
                    number=current_section,
                    chapter=m.group(1),
                )
            )
            continue
        m = _RE_ARTICLE.match(anchor_id)
        if m:
            current_article = int(m.group(1))
            structural.append(
                _Anchor(
                    "article",
                    anchor_id,
                    tag_start,
                    number=current_article,
                    chapter=current_chapter,
                    section=current_section,
                )
            )
            continue
        m = _RE_PARAGRAPH.match(anchor_id)
        if m:
            art_no, par_no = int(m.group(1)), int(m.group(2))
            # Accept only anchors whose article prefix matches the containing
            # article; mismatches are quoted text of amended acts (see module
            # docstring) and are not paragraphs of this Regulation.
            if current_article is not None and art_no == current_article:
                key = (art_no, par_no)
                if key in seen_paragraph_ids:
                    raise ValueError(f"duplicate paragraph anchor within article: {anchor_id}")
                seen_paragraph_ids.add(key)
                structural.append(
                    _Anchor("paragraph", anchor_id, tag_start, number=par_no, extra={"article": art_no})
                )
            continue
        m = _RE_RECITAL.match(anchor_id)
        if m:
            structural.append(_Anchor("recital", anchor_id, tag_start, number=int(m.group(1))))
            continue
        m = _RE_ANNEX.match(anchor_id)
        if m:
            current_chapter, current_section, current_article = None, None, None
            structural.append(_Anchor("annex", anchor_id, tag_start, number=m.group(1)))
            continue
        if _RE_CHAPTER_TITLE.match(anchor_id) or _RE_SECTION_TITLE.match(anchor_id) or _RE_ARTICLE_TITLE.match(anchor_id):
            titles[anchor_id] = tag_start

    return structural, titles


def _close_spans(structural: list[_Anchor], text_length: int) -> None:
    """End each element's span at the next anchor of equal or higher rank."""
    for i, anchor in enumerate(structural):
        rank = _RANK[anchor.kind]
        anchor.end = text_length
        for later in structural[i + 1 :]:
            if _RANK[later.kind] <= rank:
                anchor.end = later.start
                break


def parse_snapshot(snapshot_path: Path) -> dict[str, Any]:
    """Parse the frozen EUR-Lex HTML snapshot into a Layer 1 dump dict.

    Deterministic: regex over the raw snapshot text, no network, no model.
    The returned dict conforms to schema/json_schemas/layer1_dump.schema.json
    (Layer 1 nodes and edges only; build_layer1 merges Layer 0 on top).
    """
    snapshot_path = Path(snapshot_path)
    raw = snapshot_path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    snapshot_file = snapshot_path.name
    build_id = f"build-{sha256[:12]}"

    structural, titles = _collect_anchors(text)
    _close_spans(structural, len(text))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    regulation_span = _source_span(
        f"span:{REGULATION_ID}", snapshot_file, sha256, 0, len(text), None
    )
    nodes.append(
        {
            "id": REGULATION_ID,
            "layer": 1,
            "type": "Regulation",
            "title": REGULATION_TITLE,
            "source_span": regulation_span,
        }
    )

    def span_of(anchor: _Anchor) -> dict[str, Any]:
        return _source_span(
            f"span:{anchor.anchor_id}",
            snapshot_file,
            sha256,
            anchor.start,
            anchor.end,
            anchor.anchor_id,
        )

    articles_with_paragraphs: set[int] = set()
    article_anchors: list[_Anchor] = []

    for anchor in structural:
        span = span_of(anchor)
        span_id = span["span_id"]

        if anchor.kind == "chapter":
            roman = anchor.number
            node_id = f"{REGULATION_ID}:chapter-{roman.lower()}"
            title_pos = titles.get(f"cpt_{roman}.tit_1")
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Chapter",
                    "number": roman,
                    "title": _title_from_div(text, title_pos) if title_pos is not None else "",
                    "source_span": span,
                }
            )
            edges.append(_hierarchy_edge("HAS_CHAPTER", REGULATION_ID, node_id, span_id, build_id))

        elif anchor.kind == "section":
            chapter_id = f"{REGULATION_ID}:chapter-{anchor.chapter.lower()}"
            node_id = f"{chapter_id}:section-{anchor.number}"
            title_pos = titles.get(f"cpt_{anchor.chapter}.sct_{anchor.number}.tit_1")
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Section",
                    "number": anchor.number,
                    "title": _title_from_div(text, title_pos) if title_pos is not None else "",
                    "source_span": span,
                }
            )
            edges.append(_hierarchy_edge("HAS_SECTION", chapter_id, node_id, span_id, build_id))

        elif anchor.kind == "article":
            node_id = f"{REGULATION_ID}:article-{anchor.number}"
            title_pos = titles.get(f"art_{anchor.number}.tit_1")
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Article",
                    "number": anchor.number,
                    "title": _title_from_div(text, title_pos) if title_pos is not None else "",
                    "source_span": span,
                }
            )
            if anchor.chapter is None:
                raise ValueError(f"article {anchor.number} found outside any chapter")
            if anchor.section is not None:
                parent_id = f"{REGULATION_ID}:chapter-{anchor.chapter.lower()}:section-{anchor.section}"
            else:
                parent_id = f"{REGULATION_ID}:chapter-{anchor.chapter.lower()}"
            edges.append(_hierarchy_edge("HAS_ARTICLE", parent_id, node_id, span_id, build_id))
            article_anchors.append(anchor)

        elif anchor.kind == "paragraph":
            art_no = anchor.extra["article"]
            articles_with_paragraphs.add(art_no)
            article_id = f"{REGULATION_ID}:article-{art_no}"
            node_id = f"{article_id}:paragraph-{anchor.number}"
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Paragraph",
                    "index": anchor.number,
                    "text": _strip_text(text[anchor.start : anchor.end]),
                    "source_span": span,
                }
            )
            edges.append(_hierarchy_edge("HAS_PARAGRAPH", article_id, node_id, span_id, build_id))

        elif anchor.kind == "recital":
            node_id = f"{REGULATION_ID}:recital-{anchor.number}"
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Recital",
                    "number": anchor.number,
                    "text": _strip_text(text[anchor.start : anchor.end]),
                    "binding": False,
                    "source_span": span,
                }
            )
            edges.append(_hierarchy_edge("HAS_RECITAL", REGULATION_ID, node_id, span_id, build_id))

        elif anchor.kind == "annex":
            roman = anchor.number
            node_id = f"{REGULATION_ID}:annex-{roman.lower()}"
            # Annexes have no .tit_1 anchor; the title is the second
            # oj-doc-ti heading (the first is "ANNEX <R>").
            headings = _RE_ANNEX_DOC_TI.findall(text[anchor.start : anchor.end])
            title = _strip_text(headings[1]) if len(headings) > 1 else ""
            nodes.append(
                {
                    "id": node_id,
                    "layer": 1,
                    "type": "Annex",
                    "number": roman,
                    "title": title,
                    "source_span": span,
                }
            )
            edges.append(_hierarchy_edge("HAS_ANNEX", REGULATION_ID, node_id, span_id, build_id))

    # Fallback paragraphs for articles with no own numeric paragraph anchor:
    # single-paragraph articles and the amendment articles whose numeric
    # anchors belong to the amended acts. The paragraph text is the article
    # body after the title div; its span carries the article anchor.
    for anchor in article_anchors:
        if anchor.number in articles_with_paragraphs:
            continue
        article_id = f"{REGULATION_ID}:article-{anchor.number}"
        node_id = f"{article_id}:paragraph-1"
        body_start = anchor.start
        title_pos = titles.get(f"art_{anchor.number}.tit_1")
        if title_pos is not None:
            close = text.find("</div>", title_pos)
            if close != -1:
                body_start = close + len("</div>")
        span = _source_span(
            f"span:{anchor.anchor_id}:body",
            snapshot_file,
            sha256,
            body_start,
            anchor.end,
            anchor.anchor_id,
        )
        nodes.append(
            {
                "id": node_id,
                "layer": 1,
                "type": "Paragraph",
                "index": 1,
                "text": _strip_text(text[body_start : anchor.end]),
                "source_span": span,
            }
        )
        edges.append(
            _hierarchy_edge(
                "HAS_PARAGRAPH",
                article_id,
                node_id,
                span["span_id"],
                build_id,
                method="article_body_fallback",
            )
        )

    return {
        "build": {
            "build_id": build_id,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "tere4ai_version": TERE4AI_VERSION,
            "snapshots": [{"file": snapshot_file, "sha256": sha256}],
        },
        "nodes": nodes,
        "edges": edges,
    }


def build_layer1(
    out_path: Path | str = DEFAULT_OUT_PATH,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Build the merged Layer 0 + Layer 1 dump and write it to out_path.

    Reads the snapshot listed in MANIFEST.json, verifies its checksum against
    the manifest (frozen-source rule, docs/architecture.md Section 6), merges
    the Layer 0 source registry from tere4ai.ingest.sources.layer0, and writes
    the dump JSON. Returns the dump dict.
    """
    from tere4ai.ingest.sources import layer0

    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snap_entry = manifest["snapshots"][0]
    snapshot_path = manifest_path.parent / snap_entry["file"]

    actual_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    if actual_sha != snap_entry["sha256"]:
        raise ValueError(
            f"snapshot checksum mismatch for {snap_entry['file']}: "
            f"manifest {snap_entry['sha256']}, file {actual_sha}"
        )

    dump = parse_snapshot(snapshot_path)
    build_id = dump["build"]["build_id"]
    l0_nodes, l0_edges = layer0(build_id, manifest_path)
    dump["nodes"] = l0_nodes + dump["nodes"]
    dump["edges"] = l0_edges + dump["edges"]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return dump

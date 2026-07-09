"""Deterministic Definition nodes from the Article 3 quoted terms (Layer 1).

@implements: DEC-01 (partial: Article 3 Definition nodes and usage links)
@grounded_by: REF-27, REF-08, REF-05

Each point of Article 3, paragraph 1 (eu-ai-act:article-3:paragraph-1:point-N)
defines exactly one term. In the Formex 4 manifestation the term sits between
a QUOT.START and a QUOT.END marker at the start of the point (the typographic
quotes of the OJ rendering), so the term is extracted from the frozen Formex
main-body file at the point's own source span, never guessed. Each term
becomes a Definition node (docs/architecture.md Section 1, Layer 1):

    eu-ai-act:definition:<slug-of-term>  {term, text, layer 1}

Edge direction (documented choice): the defining Point carries a DEFINES_TERM
edge TO the Definition node (Point --DEFINES_TERM--> Definition), provenance
EXTRACTED_SOURCE, so the Definition hangs off the legal hierarchy at its
defining point.

Usage links: for each term, the HIGH-RISK CORE nodes (Articles 5 to 27, 50,
72, 73: their Paragraph, Point, and Subparagraph texts, plus every AnnexItem
text) are scanned for the exact term (word-boundary, case-insensitive).
Matches yield Definition --CONTEXT_FOR--> usage edges, provenance
RESOLVED_DETERMINISTIC, capped at USAGE_CAP edges per term. Per the
no-silent-degradation rule (Section 13) the cap is never silent: every
Definition node stores usage_count_total (all matches found) next to
usage_count_linked (edges actually emitted), so a capped term is visible in
the graph itself.

No LLM or model client is used anywhere in this module (DEC-01).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure.formex import (
    MAIN_BODY_FILE,
    _load_formex_manifest,
    _sha256,
    _strip_text,
)
from tere4ai.parse_legal_structure.parser import (
    DEFAULT_MANIFEST_PATH,
    REGULATION_ID,
    _hierarchy_edge,
    _source_span,
)

DEFINES_TERM_METHOD = "definition_quot_v1"
USAGE_METHOD = "definition_usage_v1"
USAGE_CAP = 30

# The v2 high-risk core articles (docs/architecture.md Section 10).
CORE_ARTICLES = frozenset(range(5, 28)) | {50, 72, 73}

_DEFINITION_POINT_ID = re.compile(
    rf"^{REGULATION_ID}:article-3:paragraph-1:point-(\d+)$"
)
_ARTICLE_OF_ID = re.compile(rf"^{REGULATION_ID}:article-(\d+):")
_ANNEX_ITEM_PREFIX = f"{REGULATION_ID}:annex-"
# First quoted term of a Formex fragment: the OJ typographic quotes are
# self-closing QUOT.START / QUOT.END elements around the defined term.
_QUOT_TERM = re.compile(r"<QUOT\.START[^>]*/>(.*?)<QUOT\.END[^>]*/>", re.S)
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slug(term: str) -> str:
    slug = _SLUG_STRIP.sub("-", term.lower()).strip("-")
    if not slug:
        raise ValueError(f"term {term!r} yields an empty slug")
    return slug


def _usage_candidates(dump: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(node_id, text, span_id) of every scannable high-risk-core node, in
    dump order. Article nodes carry only a title, so the text-bearing levels
    (Paragraph, Point, Subparagraph) represent them; AnnexItem covers the
    annex side."""
    candidates: list[tuple[str, str, str]] = []
    for node in dump["nodes"]:
        node_type = node.get("type")
        text = node.get("text") or ""
        span_id = (node.get("source_span") or {}).get("span_id")
        if not text or not span_id:
            continue
        if node_type in ("Paragraph", "Point", "Subparagraph"):
            match = _ARTICLE_OF_ID.match(node["id"])
            if match and int(match.group(1)) in CORE_ARTICLES:
                candidates.append((node["id"], text, span_id))
        elif node_type == "AnnexItem" and node["id"].startswith(_ANNEX_ITEM_PREFIX):
            candidates.append((node["id"], text, span_id))
    return candidates


def enrich_with_definitions(
    dump: dict[str, Any],
    formex_dir: Path | str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Append Definition nodes, DEFINES_TERM edges, and CONTEXT_FOR usage
    edges to a Formex-enriched Layer 1 dump.

    Verifies the frozen main-body member file against MANIFEST.json first
    (frozen-source rule). Raises (never guesses) when an Article 3 point has
    no quoted term or two terms collide on the same slug.
    """
    manifest_path = Path(manifest_path)
    if formex_dir is None:
        formex_dir = manifest_path.parent / "formex"
    formex_dir = Path(formex_dir)

    shas = _load_formex_manifest(manifest_path)
    rel = f"formex/{MAIN_BODY_FILE}"
    if rel not in shas:
        raise ValueError(f"{rel} is not listed in {manifest_path}")
    path = formex_dir / MAIN_BODY_FILE
    sha256 = _sha256(path)
    if sha256 != shas[rel]:
        raise ValueError(
            f"snapshot checksum mismatch for {rel}: manifest {shas[rel]}, file {sha256}"
        )
    text = path.read_text(encoding="utf-8")

    build_id = dump["build"]["build_id"]
    node_ids = {n["id"] for n in dump["nodes"]}

    points = [
        n
        for n in dump["nodes"]
        if n.get("type") == "Point" and _DEFINITION_POINT_ID.match(n["id"])
    ]
    if not points:
        raise ValueError(
            "no Article 3 paragraph 1 points in the dump; run the Formex pass first"
        )
    points.sort(key=lambda n: int(_DEFINITION_POINT_ID.match(n["id"]).group(1)))

    candidates = _usage_candidates(dump)

    new_nodes: list[dict[str, Any]] = []
    new_edges: list[dict[str, Any]] = []
    seen_slugs: dict[str, str] = {}

    for point in points:
        span = point["source_span"]
        if span["snapshot_file"] != rel:
            raise ValueError(
                f"{point['id']} span cites {span['snapshot_file']}, expected {rel}"
            )
        fragment = text[span["start"] : span["end"]]
        match = _QUOT_TERM.search(fragment)
        if match is None:
            raise ValueError(f"{point['id']} has no quoted term in its Formex span")
        term = _strip_text(match.group(1))
        if not term:
            raise ValueError(f"{point['id']} quoted term is empty")
        slug = _slug(term)
        if slug in seen_slugs:
            raise ValueError(
                f"slug collision: {term!r} ({point['id']}) and {seen_slugs[slug]}"
            )
        seen_slugs[slug] = point["id"]

        definition_id = f"{REGULATION_ID}:definition:{slug}"
        if definition_id in node_ids:
            raise ValueError(f"duplicate Definition id: {definition_id}")
        node_ids.add(definition_id)

        def_span = _source_span(
            f"span:{definition_id}",
            span["snapshot_file"],
            span["snapshot_sha256"],
            span["start"],
            span["end"],
            span.get("anchor"),
        )

        # Usage scan: exact term, word-boundary, case-insensitive, over the
        # high-risk core only. Deterministic order is dump order.
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        matches = [
            (node_id, span_id)
            for node_id, node_text, span_id in candidates
            if pattern.search(node_text)
        ]
        linked = matches[:USAGE_CAP]

        new_nodes.append(
            {
                "id": definition_id,
                "layer": 1,
                "type": "Definition",
                "term": term,
                "text": point.get("text", ""),
                "usage_count_total": len(matches),
                "usage_count_linked": len(linked),
                "source_span": def_span,
            }
        )
        new_edges.append(
            _hierarchy_edge(
                "DEFINES_TERM",
                point["id"],
                definition_id,
                def_span["span_id"],
                build_id,
                method=DEFINES_TERM_METHOD,
            )
        )
        for usage_id, usage_span_id in linked:
            new_edges.append(
                {
                    "edge_id": f"defctx:{definition_id}->{usage_id}",
                    "edge_type": "CONTEXT_FOR",
                    "from": definition_id,
                    "to": usage_id,
                    "provenance_class": "RESOLVED_DETERMINISTIC",
                    "source_span_id": usage_span_id,
                    "method": USAGE_METHOD,
                    "confidence": 1.0,
                    "review_status": "auto_accepted",
                    "build_id": build_id,
                    "citation_text": term,
                }
            )

    dump["nodes"] = dump["nodes"] + new_nodes
    dump["edges"] = dump["edges"] + new_edges
    return dump

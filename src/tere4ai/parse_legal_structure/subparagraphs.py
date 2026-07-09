"""Deterministic Formex 4 enrichment: Subparagraph depth for Layer 1.

@implements: DEC-01 (partial: Formex subparagraph depth)
@grounded_by: REF-27, REF-08, REF-05

Extends the Layer 1 dump with Subparagraph nodes for the unnumbered ALINEA
blocks of the Formex 4 main body (docs/architecture.md Sections 1, 2, 6).
Rule: within each kept PARAG (QUOT.S subtrees, the quoted text of amended
acts, are skipped), the FIRST top-level ALINEA is the paragraph's leading
text block and gets no node of its own; every later top-level ALINEA becomes
a Subparagraph node.

Numbering: the id ordinal K is the 1-based position of the ALINEA among ALL
top-level ALINEA of the PARAG (so the first emitted node is subparagraph-2).
This matches the Act's citation style ("first subparagraph, point (a)") and
is by construction consistent with the point ids formex.py already scopes by
subparagraph ordinal in Article 43(1)
(eu-ai-act:article-43:paragraph-1:subparagraph-2:point-a).

No LLM or model client is used anywhere in this module (DEC-01): the
structure is derived from the Formex XML element tree via the same
position-tracking tokenizer formex.py uses (imported, not duplicated), so
two runs over the same snapshots produce identical output.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure.formex import (
    MAIN_BODY_FILE,
    _child_roots,
    _el_text,
    _find,
    _load_formex_manifest,
    _parse_xml,
    _sha256,
    _strip_text,
)
from tere4ai.parse_legal_structure.parser import (
    DEFAULT_MANIFEST_PATH,
    REGULATION_ID,
    _hierarchy_edge,
    _source_span,
)

SUBPARAGRAPH_METHOD = "formex_subparagraph_v1"

SUBPARAGRAPH_ID = re.compile(
    rf"^{REGULATION_ID}:article-\d+:paragraph-\d+:subparagraph-([2-9]|[1-9]\d+)$"
)


def enrich_with_subparagraphs(
    dump: dict[str, Any],
    formex_dir: Path | str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Append Subparagraph nodes and HAS_SUBPARAGRAPH edges to the dump.

    Verifies the frozen main-body member file against MANIFEST.json first
    (frozen-source rule, architecture.md Section 6). Raises (never skips
    silently) when a Formex paragraph has no counterpart in the dump or a
    generated id collides with an existing node.
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
    paragraph_ids = {n["id"] for n in dump["nodes"] if n.get("type") == "Paragraph"}

    root = _parse_xml(text)
    articles = _child_roots(root, "ARTICLE")
    if len(articles) != 113:
        raise ValueError(f"expected 113 ARTICLE elements, found {len(articles)}")

    new_nodes: list[dict[str, Any]] = []
    new_edges: list[dict[str, Any]] = []

    for article in articles:
        art_no = int(article.attrs["IDENTIFIER"])
        for parag in _child_roots(article, "PARAG"):
            no_parag = _find(parag, "NO.PARAG")
            if no_parag is None:
                raise ValueError(
                    f"PARAG {parag.attrs.get('IDENTIFIER')} outside QUOT.S lacks NO.PARAG"
                )
            par_no = int(_strip_text(text[no_parag.start : no_parag.end]).rstrip("."))
            paragraph_id = f"{REGULATION_ID}:article-{art_no}:paragraph-{par_no}"
            if paragraph_id not in paragraph_ids:
                raise ValueError(
                    f"Formex paragraph {art_no}({par_no}) maps to {paragraph_id}, "
                    "which does not exist in the dump"
                )
            # Direct ALINEA children only: an ALINEA inside a QUOT.S child of
            # the PARAG is quoted text of another act and is never reached.
            alineas = [c for c in parag.children if c.tag == "ALINEA"]
            for k, alinea in enumerate(alineas, start=1):
                if k == 1:
                    continue  # the paragraph's leading text block, not a subparagraph
                node_id = f"{paragraph_id}:subparagraph-{k}"
                if node_id in node_ids:
                    raise ValueError(f"duplicate Subparagraph id: {node_id}")
                node_ids.add(node_id)
                anchor = f"fmx:art_{art_no:03d}.parag_{par_no:03d}.alinea_{k}"
                span = _source_span(
                    f"span:{anchor}", rel, sha256, alinea.start, alinea.end, anchor
                )
                new_nodes.append(
                    {
                        "id": node_id,
                        "layer": 1,
                        "type": "Subparagraph",
                        "index": k,
                        "text": _el_text(text, alinea),
                        "source_span": span,
                    }
                )
                new_edges.append(
                    _hierarchy_edge(
                        "HAS_SUBPARAGRAPH",
                        paragraph_id,
                        node_id,
                        span["span_id"],
                        build_id,
                        method=SUBPARAGRAPH_METHOD,
                    )
                )

    dump["nodes"] = dump["nodes"] + new_nodes
    dump["edges"] = dump["edges"] + new_edges
    if rel not in {s["file"] for s in dump["build"]["snapshots"]}:
        dump["build"]["snapshots"].append({"file": rel, "sha256": sha256})
    return dump

"""Deterministic recital-to-article CONTEXT_FOR links (Layer 1 context).

@implements: DEC-01 (partial: recital context links)
@grounded_by: REF-27, REF-08, REF-26

Rule pass over every Recital text in a Layer 1 dump: a recital that cites
"Article N" OF THIS REGULATION gets a CONTEXT_FOR edge to that Article node
(recital -> article), provenance RESOLVED_DETERMINISTIC, method
recital_context_v1. The mention grammar and range expansion are imported
from the cross-reference resolver (DEC-02 rule family), not duplicated.

Recitals stay context only (architecture.md Section 1): CONTEXT_FOR is NOT a
hierarchy edge, the orphan gate still reaches recitals via HAS_RECITAL, and
no runtime requirement may cite a recital.

Recital-grade external filter (verified against the frozen text): recitals
cite other instruments far more often than the operative text does, and the
resolver's filter alone is not enough there. Beyond the resolver's
_external_citation check, a mention is external when the text right after it
names another legal order before naming this Regulation: TFEU, TEU, "of the
Treaty/Treaties", "of the Charter", "of Protocol", "of that
Regulation/Directive/Decision", or "of Regulation/Directive/Decision ...".
A mention followed by "of this Regulation" before any such marker stays
internal. External and unresolved mentions are queued (review_queue), never
silently dropped. Wrong citations are worse than missing ones (USER.md), so
this filter errs on the side of the queue.

Honest yield note: the frozen text contains only a handful of recitals that
cite AI Act articles by number (most "Article N" mentions in recitals point
at the TFEU, TEU, the Charter, protocols, or the GDPR). The edge count is
therefore small by construction; see tests/unit/test_graph_depth.py for the
verified figures.

No LLM or model client is used anywhere in this module (DEC-01).
"""

from __future__ import annotations

import re
from typing import Any

from tere4ai.resolve_crossrefs.resolver import (
    _ARTICLE_MENTION,
    _article_targets,
    _external_citation,
)

RECITAL_CONTEXT_METHOD = "recital_context_v1"

# Window (chars) scanned after a mention for internal / external markers.
_MARKER_WINDOW = 90
_INTERNAL_MARKER = re.compile(r"\bof this Regulation\b")
_EXTERNAL_MARKER = re.compile(
    r"\bTFEU\b|\bTEU\b"
    r"|\bof the Treat(?:y|ies)\b"
    r"|\bof the Charter\b"
    r"|\bof Protocol\b"
    r"|\bof that (?:Regulation|Directive|Decision)\b"
    r"|\bof (?:Council\s+)?(?:Regulation|Directive|Decision)\b"
)


def _is_external(text: str, start: int, end: int) -> bool:
    """True when the mention at [start, end) points at another instrument."""
    if _external_citation(text, start, end) is not None:
        return True
    window = text[end : end + _MARKER_WINDOW]
    internal = _INTERNAL_MARKER.search(window)
    external = _EXTERNAL_MARKER.search(window)
    if external is None:
        return False
    return internal is None or external.start() < internal.start()


def add_recital_context(dump: dict[str, Any]) -> dict[str, Any]:
    """Append recital -> article CONTEXT_FOR edges to a Layer 1 dump.

    Deduplicated on (recital, article); external or unresolved mentions go to
    the review_queue. The dump is enriched in place and returned.
    """
    build_id = dump["build"]["build_id"]
    node_ids = {n["id"] for n in dump["nodes"]}

    new_edges: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_queue: set[tuple[str, str, str]] = set()

    def _enqueue(recital_id: str, citation: str, span_id: str, reason: str) -> None:
        key = (recital_id, citation, reason)
        if key in seen_queue:
            return
        seen_queue.add(key)
        queue.append(
            {
                "item_id": f"rctxq:{len(queue) + 1}",
                "kind": "recital_context",
                "citation_text": citation,
                "source_span_id": span_id,
                "from_node_id": recital_id,
                "reason": reason,
            }
        )

    for node in dump["nodes"]:
        if node.get("type") != "Recital":
            continue
        text = node.get("text") or ""
        span_id = (node.get("source_span") or {}).get("span_id")
        if not text or not span_id:
            continue
        for match in _ARTICLE_MENTION.finditer(text):
            citation = match.group(0)
            if _is_external(text, match.start(), match.end()):
                _enqueue(node["id"], citation, span_id, "external_instrument")
                continue
            for target in _article_targets(citation):
                if target not in node_ids:
                    _enqueue(node["id"], citation, span_id, "unresolved_target")
                    continue
                pair = (node["id"], target)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                new_edges.append(
                    {
                        "edge_id": f"rctx:{node['id']}->{target}",
                        "edge_type": "CONTEXT_FOR",
                        "from": node["id"],
                        "to": target,
                        "provenance_class": "RESOLVED_DETERMINISTIC",
                        "source_span_id": span_id,
                        "method": RECITAL_CONTEXT_METHOD,
                        "confidence": 1.0,
                        "review_status": "auto_accepted",
                        "build_id": build_id,
                        "citation_text": citation,
                    }
                )

    dump["edges"] = dump["edges"] + new_edges
    dump["review_queue"] = list(dump.get("review_queue", [])) + queue
    return dump

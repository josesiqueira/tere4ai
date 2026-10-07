"""Deterministic HLEGRequirementSubtopic nodes (Layer 3 subtopic targets).

@implements: DEC-05 (partial: subtopic targets under the seven HLEG requirements)
@implements: DEC-25 (partial: the publisher's headings)
@grounded_by: ADD-01, REF-10

The 23 subtopics are the publisher's own headings: the bold italic words that
open a paragraph of the seven requirement sections, listed in the derivation
record (tere4ai.ingest.hleg_text; spec G D-G75 (6)). A node's span runs from
its heading to the next subtopic heading of its section or to the section's
end; its description is the first sentence after the heading; its id is
hleg:<req-slug>:subtopic:<slug of the heading>. Each parent HLEGRequirement
gets a HAS_SUBTOPIC edge, provenance EXTRACTED_SOURCE, method
SUBTOPIC_METHOD. No LLM or model client is used anywhere in this module.
"""

from __future__ import annotations

import re
from typing import Any

from tere4ai.align_hleg.hleg_nodes import CANONICAL, section_end
from tere4ai.align_hleg.hleg_source import HlegPair, load_pair
from tere4ai.ingest.hleg_text import TEXT_FILE

SUBTOPIC_METHOD = "hleg_subtopic_headings_v2"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# First sentence end: a period followed by whitespace and an uppercase start.
_SENTENCE_END = re.compile(r"\.(?=\s+[A-Z0-9(])")
_MAX_DESCRIPTION_CHARS = 600


def _slug(label: str) -> str:
    slug = _SLUG_STRIP.sub("-", label.lower()).strip("-")
    if not slug:
        raise ValueError(f"heading {label!r} yields an empty slug")
    return slug


def _first_sentence(text: str, start: int, end: int) -> str:
    """Whitespace-collapsed first sentence of text[start:end]."""
    raw = " ".join(text[start:end].split())
    match = _SENTENCE_END.search(raw)
    sentence = raw[: match.end()] if match else raw
    return sentence[:_MAX_DESCRIPTION_CHARS]


def build_hleg_subtopics(pair: HlegPair | None = None, build_id: str | None = None) -> dict[str, Any]:
    """{"nodes": [...], "edges": [...]}, deterministic; raises ValueError when a
    heading of the record does not open a paragraph of its section."""
    pair = pair or load_pair()
    text, record = pair.text, pair.record
    heads = record["requirement_headings"]
    if build_id is None:
        build_id = f"build-{pair.text_sha256[:12]}"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for i, head in enumerate(heads):
        req_id, _ = CANONICAL[head["order"] - 1]
        limit = section_end(text, heads, i)
        mine = [s for s in record["subtopic_headings"] if s["requirement_order"] == head["order"]]
        for j, sub in enumerate(mine):
            if not head["end"] < sub["start"] < limit or text[sub["start"]:sub["end"] + 1] != f"{sub['label']}.":
                raise ValueError(f"subtopic heading {sub['label']!r} at {sub['start']} is not in section 1.{head['order']}")
            end = len(text[: mine[j + 1]["start"]].rstrip("\n")) if j + 1 < len(mine) else limit
            subtopic_id = f"{req_id}:subtopic:{_slug(sub['label'])}"
            span_id = f"span:{subtopic_id}"
            nodes.append({
                "id": subtopic_id,
                "type": "HLEGRequirementSubtopic",
                "layer": 3,
                "hleg_requirement_id": req_id,
                "order": j + 1,
                "label": sub["label"],
                "description": _first_sentence(text, sub["end"] + 1, end),
                "source_span": {
                    "span_id": span_id,
                    "snapshot_file": TEXT_FILE,
                    "snapshot_sha256": pair.text_sha256,
                    "start": sub["start"],
                    "end": end,
                    "anchor": f"{sub['label']}.",
                },
            })
            edges.append({
                "edge_id": f"edge:has_subtopic:{subtopic_id}",
                "edge_type": "HAS_SUBTOPIC",
                "from": req_id,
                "to": subtopic_id,
                "provenance_class": "EXTRACTED_SOURCE",
                "source_span_id": span_id,
                "method": SUBTOPIC_METHOD,
                "confidence": 1.0,
                "review_status": "auto_accepted",
                "build_id": build_id,
            })
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate subtopic ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return {"nodes": nodes, "edges": edges}

"""Deterministic builder for the seven HLEGRequirement nodes (Layer 3).

@implements: DEC-05 (partial: target-side HLEG nodes; assertions arrive with the alignment pipeline)
@implements: DEC-25 (partial: each requirement given whole)
@grounded_by: ADD-01, REF-10

Each requirement's description is its section of Chapter II Section 1 of
the Ethics Guidelines for Trustworthy AI, from after its heading to the next
requirement's heading (1.7 to the end of the text), paragraphs separated by
one blank line; its span is the whole section with its heading. Text and
ranges come from the derived text and its derivation record
(tere4ai.ingest.hleg_text), read through their checksums (hleg_source; spec
G D-G75 (5)). The set is closed (alignments.schema.json enforces the ids);
this module never invents an eighth.

The ALTAI question lists (assessment section of the same document) are NOT
emitted here: ALTAI is not in the graph, a future study (B111) with its own
licence check.
"""

from __future__ import annotations

from typing import Any

from tere4ai.align_hleg.hleg_source import HlegPair, load_pair
from tere4ai.ingest.hleg_text import TEXT_FILE

# Canonical order and ids (closed set; mirrors alignments.schema.json).
CANONICAL = [
    ("hleg:human-agency-and-oversight", "Human agency and oversight"),
    ("hleg:technical-robustness-and-safety", "Technical robustness and safety"),
    ("hleg:privacy-and-data-governance", "Privacy and data governance"),
    ("hleg:transparency", "Transparency"),
    (
        "hleg:diversity-non-discrimination-and-fairness",
        "Diversity, non-discrimination and fairness",
    ),
    ("hleg:societal-and-environmental-well-being", "Societal and environmental well-being"),
    ("hleg:accountability", "Accountability"),
]


def section_end(text: str, heads: list[dict[str, Any]], i: int) -> int:
    """Where section i ends: before the blank line that precedes the next heading,
    or before the final newline of the text."""
    following = heads[i + 1]["start"] if i + 1 < len(heads) else len(text)
    return len(text[:following].rstrip("\n"))


def build_hleg_nodes(pair: HlegPair | None = None) -> list[dict[str, Any]]:
    """The seven HLEGRequirement nodes with their spans; raises ValueError when the
    record's seven headings are not the canonical ones, once each, in order."""
    pair = pair or load_pair()
    text, heads = pair.text, pair.record["requirement_headings"]
    if [h["order"] for h in heads] != [1, 2, 3, 4, 5, 6, 7]:
        raise ValueError(f"expected the requirement headings 1.1 to 1.7 in order, found {[h['order'] for h in heads]}")
    nodes: list[dict[str, Any]] = []
    for i, head in enumerate(heads):
        req_id, name = CANONICAL[head["order"] - 1]
        if text[head["start"]:head["end"]] != head["text"] or head["text"] != f"1.{head['order']} {name}":
            raise ValueError(f"heading {head['text']!r} at {head['start']} is not 1.{head['order']} {name}")
        end = section_end(text, heads, i)
        nodes.append({
            "id": req_id,
            "type": "HLEGRequirement",
            "layer": 3,
            "order": head["order"],
            "name": name,
            "description": text[head["end"]:end].strip("\n"),
            "source_span": {
                "span_id": f"span:hleg:req{head['order']}",
                "snapshot_file": TEXT_FILE,
                "snapshot_sha256": pair.text_sha256,
                "start": head["start"],
                "end": end,
                "anchor": head["text"],
            },
        })
    return nodes

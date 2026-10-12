"""Resolve each norm's verbatim source_text from its Layer 1 source node.

One helper for every path that hands norms to the runtime grounding judge
or to the evidence and backlog generators: the MCP tools, the HTTP facade
and the evaluation harness's graph strategies (B165). runtime_grounding v2's
check 0 compares the answer with each cited norm's exact legal wording, but
the served norms payload does not carry source_text, so it is resolved from
the dump before a model sees the norm (audit 2026-07-20 D4/F6).

@implements: DEC-08, DEC-10
@grounded_by: REF-16, REF-17, REF-15, REF-31
"""

from __future__ import annotations

from typing import Any


def _nodes_by_id(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}


def attach_source_text(norms: list[dict[str, Any]], dump: dict[str, Any]) -> None:
    """Set each norm's verbatim source_text from its Layer 1 source node, in
    place. A norm that already has one keeps it."""
    nodes = _nodes_by_id(dump)
    for norm in norms:
        if norm.get("source_text"):
            continue
        node = nodes.get(norm.get("source_node_id", ""))
        if node is not None and node.get("text"):
            norm["source_text"] = node["text"]


def with_source_text(norms: list[dict[str, Any]], dump: dict[str, Any]) -> list[dict[str, Any]]:
    """Shallow copies of the norms with source_text attached, so a caller that
    serves the same norms elsewhere (the facade's loaded payload) never has
    them mutated."""
    copies = [dict(norm) for norm in norms]
    attach_source_text(copies, dump)
    return copies

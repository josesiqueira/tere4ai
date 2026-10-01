"""Provisions of the Act rendered into an elicitor prompt from the graph.

@implements: DEC-13, DEC-18
@grounded_by: REF-17, REF-16

A prompt template names a provision with the placeholder
``{{provision:<node id>}}``. Rendering replaces it with ``[<node id>] <text>``,
where text is the node's ``text`` field in the dump of the build the call is
served on. The node's span is verified against its snapshot checksum first
(spans.resolve_span); the span's own text, raw Formex XML or EUR-Lex HTML,
is never printed. A node that is unknown, has no text, has no span, or whose
span fails verification raises ProvisionUnresolved, so the elicitation stops
before any model call. Deterministic, no model calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.spans import SpanResolutionError, resolve_span

PLACEHOLDER_RE = re.compile(r"\{\{provision:([^{}\s]+)\}\}")
FACTS_SECTION_HEADING = "## Facts and their provisions"
FACTS_LINE_PREFIX = "- Facts:"


class ProvisionUnresolved(Exception):
    """A provision named in a prompt template cannot be read from the graph."""


def _build_id(dump: dict[str, Any]) -> str:
    build = dump.get("build")
    if isinstance(build, dict) and build.get("build_id"):
        return str(build["build_id"])
    return "unknown"


def _unresolved(node_id: str, dump: dict[str, Any], reason: str) -> ProvisionUnresolved:
    return ProvisionUnresolved(
        f"provision '{node_id}' on build '{_build_id(dump)}': {reason}"
    )


def provision_text(
    node_id: str, dump: dict[str, Any], snapshots_dir: Path | str
) -> dict[str, str]:
    """Return {node_id, span_id, text} for one node, its span verified.

    The text is the node's own ``text`` field. resolve_span runs over a dump
    holding only this node, so the span verified is this node's span even
    when other nodes share its span id; its returned slice is discarded.
    """
    node = next(
        (
            n
            for n in dump.get("nodes", [])
            if isinstance(n, dict) and n.get("id") == node_id
        ),
        None,
    )
    if node is None:
        raise _unresolved(node_id, dump, "unknown node")
    text = node.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _unresolved(node_id, dump, "node has no text")
    span = node.get("source_span")
    span_id = span.get("span_id") if isinstance(span, dict) else None
    if not isinstance(span_id, str) or not span_id:
        raise _unresolved(node_id, dump, "node has no source span")
    try:
        resolve_span(span_id, {"nodes": [node]}, snapshots_dir)
    except SpanResolutionError as exc:
        raise _unresolved(node_id, dump, f"span verification failed: {exc}") from exc
    return {"node_id": node_id, "span_id": span_id, "text": text}


def render_template(
    text: str, dump: dict[str, Any], snapshots_dir: Path | str
) -> tuple[str, list[dict[str, str]]]:
    """Replace every placeholder with ``[<node id>] <text>``.

    Returns the rendered text and the provisions it carries ({node_id,
    span_id}, in order of first appearance, without duplicates). Every
    placeholder is resolved before anything is returned, so one unresolved
    provision raises ProvisionUnresolved for the whole template.
    """
    resolved: dict[str, dict[str, str]] = {}
    for node_id in PLACEHOLDER_RE.findall(text):
        if node_id not in resolved:
            resolved[node_id] = provision_text(node_id, dump, snapshots_dir)
    if not resolved:
        return text, []
    rendered = PLACEHOLDER_RE.sub(
        lambda m: f"[{m.group(1)}] {resolved[m.group(1)]['text']}", text
    )
    provisions = [
        {"node_id": p["node_id"], "span_id": p["span_id"]} for p in resolved.values()
    ]
    return rendered, provisions


def fact_provisions(text: str) -> dict[str, list[str]]:
    """Read the fact-to-provision table from a template.

    The section headed ``## Facts and their provisions`` runs to the next
    ``## `` heading. In it, a line ``- Facts: <path>[, <path>...]`` opens a
    group, and every placeholder on the lines after it, up to the next
    ``- Facts:`` line, is a provision of each of those facts. Returns
    {fact path: [node id, ...]} in order, without duplicates; {} when the
    template has no such section. A placeholder in the section before any
    ``- Facts:`` line raises ValueError.
    """
    table: dict[str, list[str]] = {}
    in_section = False
    current: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == FACTS_SECTION_HEADING
            current = None
            continue
        if not in_section:
            continue
        if stripped.startswith(FACTS_LINE_PREFIX):
            paths = [
                p.strip()
                for p in stripped[len(FACTS_LINE_PREFIX):].split(",")
                if p.strip()
            ]
            if not paths:
                raise ValueError(f"a Facts line names no fact: {line!r}")
            current = paths
            for path in paths:
                table.setdefault(path, [])
            continue
        for node_id in PLACEHOLDER_RE.findall(line):
            if current is None:
                raise ValueError(
                    f"provision '{node_id}' appears before any '{FACTS_LINE_PREFIX}' line"
                )
            for path in current:
                if node_id not in table[path]:
                    table[path].append(node_id)
    return table

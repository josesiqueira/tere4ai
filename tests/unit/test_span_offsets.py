"""Span start and end count code points, not bytes (B34 item c, DEC-22).

The offsets index the snapshot decoded as UTF-8. A node whose span starts
after enough multi-byte characters shows the difference: the first words of
the node's own text (the parser's extracted text, a value independent of
the span function) appear in the decoded slice and not in the byte slice.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from tere4ai.mcp_server import server, spans

ROOT = Path(__file__).resolve().parents[2]
DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS = ROOT / "data" / "snapshots"

pytestmark = pytest.mark.skipif(
    not DUMP.is_file(),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)


def _plain(text: str) -> str:
    """Tags stripped, whitespace normalised."""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def _shifted_node(dump: dict) -> dict:
    """The first node, in dump order, whose span starts after non-ASCII
    characters that shift its byte offset past its own end, so the byte
    slice cannot hold its text."""
    decoded: dict[str, str] = {}
    for node in dump["nodes"]:
        span = node.get("source_span")
        if not isinstance(span, dict) or not node.get("text"):
            continue
        name = span["snapshot_file"]
        if name not in decoded:
            decoded[name] = (SNAPSHOTS / name).read_bytes().decode("utf-8")
        prefix = decoded[name][: span["start"]]
        if prefix.isascii():
            continue
        shift = len(prefix.encode("utf-8")) - span["start"]
        if shift > span["end"] - span["start"]:
            return node
    raise AssertionError("no node whose byte offset differs from its code point offset")


def test_offsets_are_code_points_of_the_decoded_snapshot():
    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    node = _shifted_node(dump)
    resolved = spans.resolve_span(node["source_span"]["span_id"], dump, SNAPSHOTS)
    raw = (SNAPSHOTS / resolved["snapshot_file"]).read_bytes()
    start, end = resolved["start"], resolved["end"]
    words = " ".join(node["text"].split()[:8])
    assert words in _plain(raw.decode("utf-8")[start:end])
    assert words not in _plain(raw[start:end].decode("utf-8", "replace"))


def test_served_descriptions_state_the_offset_unit():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    for name in ("resolve_span", "source_trace"):
        description = tools[name].description or ""
        assert "code points" in description, name
        assert "not bytes" in description, name

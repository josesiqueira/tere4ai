"""FastMCP server exposing the M1 read-only tools over the offline dump.

Wraps the pure functions in tools.py as read-only MCP tools. The dump is
read from data/graph_dumps/layer1.json (the versioned build artifact); no
running Neo4j is required to answer the M1 tools. If the dump has not been
built, the tools return a degraded envelope instead of failing silently
(architecture.md Section 13).

@implements: DEC-08, DEC-10
@grounded_by: REF-16, REF-17, REF-15
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from tere4ai.mcp_server import tools

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DUMP_PATH = _PROJECT_ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = _PROJECT_ROOT / "data" / "snapshots"

_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

mcp = FastMCP(
    name="tere4ai",
    instructions=(
        "TERE4AI v2 M1 tools over the EU AI Act Layer 0+1 structural graph. "
        "Read-only. " + tools.NON_LEGAL_ADVICE_NOTICE
    ),
)


def _read_dump(dump_path: Path = DUMP_PATH) -> dict[str, Any] | None:
    if not dump_path.is_file():
        return None
    try:
        return json.loads(dump_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@mcp.tool(annotations=_READ_ONLY)
def coverage_report() -> dict[str, Any]:
    """Structural coverage of the Layer 0+1 graph against the M1 acceptance
    (113 articles, 180 recitals, 13 annexes, chapters I to XIII, high-risk
    core presence), with per-chapter article listing and layer 2/3 status."""
    dump = _read_dump()
    if dump is None:
        return tools.dump_unavailable_envelope(
            f"graph dump not available at {DUMP_PATH}; build it with "
            "python -m tere4ai.parse_legal_structure"
        )
    return tools.coverage_report(dump)


@mcp.tool(annotations=_READ_ONLY)
def source_trace(node_id: str) -> dict[str, Any]:
    """Trace a graph node to its frozen source snapshot: file, sha256, span
    start/end, HTML anchor, and a text excerpt."""
    dump = _read_dump()
    if dump is None:
        return tools.dump_unavailable_envelope(
            f"graph dump not available at {DUMP_PATH}; build it with "
            "python -m tere4ai.parse_legal_structure"
        )
    return tools.source_trace(dump, node_id, snapshots_dir=SNAPSHOTS_DIR)


if __name__ == "__main__":
    mcp.run()

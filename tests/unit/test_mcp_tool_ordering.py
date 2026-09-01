"""tools/list determinism (B49 prep for the 2026-07-28 MCP spec revision).

The 2026-07-28 MCP revision raises deterministic tools/list ordering to a
spec SHOULD. It also serves the project's own determinism argument
(architecture.md Section 13): two consumers of the same build must see the
same tool surface in the same order, independent of registration order or
future refactors of server.py.
"""

from __future__ import annotations

import asyncio

from tere4ai.mcp_server import server
from tere4ai.mcp_server.keys import TOOL_SCOPES


def _served_tool_names() -> list[str]:
    tools = asyncio.run(server.mcp.list_tools())
    return [tool.name for tool in tools]


def test_tools_list_is_alphabetically_sorted():
    names = _served_tool_names()
    assert names == sorted(names), (
        "tools/list must serve tools in a deterministic alphabetical order, "
        f"got {names}"
    )


def test_tools_list_serves_every_scoped_tool_exactly_once():
    names = _served_tool_names()
    assert sorted(names) == sorted(TOOL_SCOPES), (
        "the served tool set must match the scope table in keys.py "
        "(every tool has exactly one scope, docs/PHASE2_DESIGN.md Section 3)"
    )

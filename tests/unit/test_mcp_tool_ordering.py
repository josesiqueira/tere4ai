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


def test_instructions_name_every_served_tool_and_every_paid_one():
    # The instructions string is what every client receives at initialize.
    # It named 9 of the 11 tools and left evaluate_project_evidence_batch
    # out of the paid ones (found 2026-09-26 by the single-source docs
    # research); a check on tools/list alone passed while this text was
    # stale, so the text is checked against the served tools here.
    instructions = server.mcp.instructions or ""
    tools = asyncio.run(server.mcp.list_tools())
    missing = [t.name for t in tools if t.name not in instructions]
    assert missing == [], f"instructions do not name {missing}"
    paid = sorted(
        t.name for t in tools if t.annotations and t.annotations.open_world_hint
    )
    paid_sentence = instructions.split("Read-only;", 1)[1].split(
        "perform paid", 1
    )[0]
    unnamed = [name for name in paid if name not in paid_sentence]
    assert unnamed == [], f"the paid sentence does not name {unnamed}"

"""Read what a client of the MCP server is served (DEC-22).

Starts the server as a subprocess over stdio, as a client launches it, and
connects with the official MCP Python SDK client in legacy mode, whose
initialize result carries the instructions. The environment holds no model
keys, so the server cannot pay even if a paid tool were called; only the
two free, deterministic tools in CALLED_TOOLS are called, through a wrapper
that records each name sent.

The SDK client comes with the dev extra (pyproject.toml); it is imported
inside read_surface, so the package never imports it at load time.

@implements: DEC-22
@grounded_by: REF-31
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CALLED_TOOLS = ("coverage_report", "classify_ai_system")
DEV_EXTRA_MESSAGE = (
    "the server docs generator needs the dev extra: python -m pip install -e '.[dev]'"
)
_SDK_MINOR = ("2", "2")
_CALL_TIMEOUT_SECONDS = 60


def server_env(extra: dict[str, str] | None = None, root: Path = ROOT) -> dict[str, str]:
    """A minimal environment for the server process: no model keys, no
    network update check, no banner on stdout (stdio carries the protocol)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(root / "src"),
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
    }
    env.update(extra or {})
    return env


@dataclass(frozen=True)
class ServedTool:
    """One entry of tools/list, as served."""

    name: str
    description: str
    annotations: dict[str, Any]
    input_schema: dict[str, Any]


@dataclass
class Surface:
    """What a client is served: the instructions, the tool list in served
    order, the answers of the two free calls, the features the example call
    sent, and the names of the tools actually called."""

    instructions: str
    tools: list[ServedTool]
    coverage: dict[str, Any]
    classification: dict[str, Any]
    request: dict[str, Any]
    called: list[str] = field(default_factory=list)


def _sdk_client():
    """The SDK's Client and StdioServerParameters, or a stop naming the dev
    extra when the installed mcp is missing or not 2.2."""
    try:
        version = metadata.version("mcp")
    except metadata.PackageNotFoundError:
        raise SystemExit(DEV_EXTRA_MESSAGE) from None
    if tuple(version.split(".")[:2]) != _SDK_MINOR:
        raise SystemExit(f"{DEV_EXTRA_MESSAGE} (installed mcp {version})")
    from mcp import Client, StdioServerParameters

    return Client, StdioServerParameters


async def _read(features: dict[str, Any], root: Path) -> Surface:
    client_class, parameters = _sdk_client()
    params = parameters(
        command=sys.executable,
        args=["-m", "tere4ai.mcp_server.server"],
        cwd=str(root),
        env=server_env(root=root),
    )
    called: list[str] = []
    async with client_class(
        params, mode="legacy", read_timeout_seconds=_CALL_TIMEOUT_SECONDS
    ) as client:
        send = client.call_tool

        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            called.append(name)
            result = await send(name, arguments)
            if result.is_error or not isinstance(result.structured_content, dict):
                raise RuntimeError(f"{name} gave no answer: {result!r}")
            return result.structured_content

        listed = await client.list_tools()
        tools = [
            ServedTool(
                name=tool.name,
                description=tool.description or "",
                annotations=(
                    tool.annotations.model_dump(exclude_none=True, by_alias=True)
                    if tool.annotations
                    else {}
                ),
                input_schema=dict(tool.input_schema or {}),
            )
            for tool in listed.tools
        ]
        coverage = await call(CALLED_TOOLS[0], {})
        classification = await call(CALLED_TOOLS[1], {"features": features})
        instructions = client.instructions or ""
    return Surface(
        instructions=instructions,
        tools=tools,
        coverage=coverage,
        classification=classification,
        request=features,
        called=called,
    )


def read_surface(example_features: dict[str, Any], root: Path = ROOT) -> Surface:
    """Start the server, read what it serves and call the two free tools,
    classify_ai_system with example_features."""
    return asyncio.run(_read(example_features, root))

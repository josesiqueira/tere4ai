"""Both MCP revisions over both transports, with the official MCP Python SDK
client (C3 Task 1).

One server answers clients of the 2026-07-28 revision (stateless, version
per request, server/discover) and legacy clients that negotiate 2025-11-25
through initialize (ruling R2 of the C3 plan in the private research
repository). Each test starts the real server as a subprocess, over stdio
or over streamable HTTP on a free localhost port, and drives it with
mcp.Client in mode "legacy" and in mode "2026-07-28": the negotiated
version, tools/list (every tool of TOOL_SCOPES, alphabetical) and one free
tool call (coverage_report). No paid tool is called.

The server advertises no MCP logging capability in either era (ruling R4):
its diagnostics are Python logging on stderr, and nothing in src sends MCP
log messages.
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2
import pytest
from mcp import Client, MCPDeprecationWarning, MCPError, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import METHOD_NOT_FOUND, DiscoverResult

from tere4ai.mcp_server.keys import TOOL_SCOPES, create_key

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_LEGACY = "legacy"
_MODERN = "2026-07-28"
_NEGOTIATED = {_LEGACY: "2025-11-25", _MODERN: "2026-07-28"}
_PORT_WAIT_SECONDS = 30.0
_CALL_TIMEOUT_SECONDS = 60


def _server_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """A minimal environment for the server process: no model keys, no
    network update check, no banner on stdout (stdio carries the protocol)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(_SRC),
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
    }
    env.update(extra or {})
    return env


async def _exercise(client: Client, mode: str) -> dict[str, object]:
    """Run the checks every transport and mode shares; return what was seen."""
    seen: dict[str, object] = {"protocol_version": client.protocol_version}
    if mode == _LEGACY:
        seen["capabilities"] = client.server_capabilities
    else:
        # Mode "2026-07-28" adopts the version without a probe and holds a
        # synthesized, empty discover result (session.discover() returns that
        # one), so send server/discover on the wire and read the server's own.
        discovered = DiscoverResult.model_validate(await client.session.send_discover(_MODERN))
        seen["capabilities"] = discovered.capabilities
        seen["supported_versions"] = list(discovered.supported_versions)
    listed = await client.list_tools()
    seen["tool_names"] = [tool.name for tool in listed.tools]
    result = await client.call_tool("coverage_report", {})
    seen["coverage_is_error"] = result.is_error
    seen["coverage_structured"] = result.structured_content
    return seen


def _assert_revision(seen: dict[str, object], mode: str) -> None:
    assert seen["protocol_version"] == _NEGOTIATED[mode]
    if mode == _MODERN:
        assert _MODERN in seen["supported_versions"]
    names = seen["tool_names"]
    assert names == sorted(TOOL_SCOPES), (
        f"tools/list must serve every scoped tool in alphabetical order, got {names}"
    )
    assert seen["coverage_is_error"] is False
    structured = seen["coverage_structured"]
    assert isinstance(structured, dict) and structured, "coverage_report gave no answer"
    capabilities = seen["capabilities"]
    assert capabilities.tools is not None
    assert capabilities.logging is None, (
        f"the server must not advertise the MCP logging capability ({mode}): "
        f"{capabilities.logging!r}"
    )


async def _refuse_set_level(client: Client, seen: dict[str, object]) -> None:
    """Ruling R4: logging/setLevel is not served (method not found). The SDK
    marks the call itself deprecated, which is the point."""
    with pytest.raises(MCPError) as refused, pytest.warns(MCPDeprecationWarning):
        await client.set_logging_level("info")
    seen["set_level_code"] = refused.value.code


async def _stdio_session(mode: str) -> dict[str, object]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tere4ai.mcp_server.server"],
        cwd=str(_REPO_ROOT),
        env=_server_env(),
    )
    async with Client(params, mode=mode, read_timeout_seconds=_CALL_TIMEOUT_SECONDS) as client:
        seen = await _exercise(client, mode)
        if mode == _LEGACY:
            await _refuse_set_level(client, seen)
        return seen


@pytest.mark.parametrize("mode", [_LEGACY, _MODERN])
def test_stdio_serves_both_revisions(mode):
    seen = asyncio.run(_stdio_session(mode))
    _assert_revision(seen, mode)
    if mode == _LEGACY:
        assert seen["set_level_code"] == METHOD_NOT_FOUND


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stderr_tail(path: Path, limit: int = 2000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no stderr file)"
    return text[-limit:] if text.strip() else "(stderr empty)"


class _ServerExited(AssertionError):
    """The HTTP server process ended before it accepted a connection."""


def _wait_for_port(port: int, process: subprocess.Popen, stderr_path: Path) -> None:
    """Wait until the server says on stderr that it listens on the port (so a
    connection to another process that took the port is not mistaken for
    it) and the port accepts a connection."""
    listening = f"Uvicorn running on http://127.0.0.1:{port}"
    deadline = time.monotonic() + _PORT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise _ServerExited(
                f"the HTTP server exited early with code {process.returncode}; "
                f"stderr tail:\n{_stderr_tail(stderr_path)}"
            )
        if listening not in stderr_path.read_text(encoding="utf-8", errors="replace"):
            time.sleep(0.1)
            continue
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(
        f"the HTTP server did not accept connections on {port} in time; "
        f"stderr tail:\n{_stderr_tail(stderr_path)}"
    )


def _stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


_ADDRESS_IN_USE = re.compile(r"address already in use|errno 98|errno 48", re.IGNORECASE)


def _start_http_server(
    env: dict[str, str], log_dir: Path, pick_port=None
) -> tuple[subprocess.Popen, int]:
    """Start the server on a free port and wait until it accepts connections.

    The port is free when picked but another process can take it before the
    server binds it; when the server exits with an address-in-use error, it
    is started once more on a newly picked port. Its stderr goes to a file
    in log_dir, whose tail is in every failure message.
    """
    pick_port = pick_port or _free_port
    for attempt in (1, 2):
        port = pick_port()
        stderr_path = log_dir / f"server-stderr-{attempt}.log"
        with stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                [sys.executable, "-m", "tere4ai.mcp_server.server"],
                cwd=str(_REPO_ROOT),
                env={**env, "TERE4AI_MCP_PORT": str(port)},
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
            )
        try:
            _wait_for_port(port, process, stderr_path)
            return process, port
        except _ServerExited:
            if attempt == 2 or not _ADDRESS_IN_USE.search(_stderr_tail(stderr_path)):
                raise
        except BaseException:
            _stop(process)
            raise
    raise AssertionError("unreachable")


async def _http_session(url: str, key: str, mode: str) -> dict[str, object]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {key}"}, timeout=_CALL_TIMEOUT_SECONDS
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(
            transport, mode=mode, read_timeout_seconds=_CALL_TIMEOUT_SECONDS
        ) as client:
            seen = await _exercise(client, mode)
            if mode == _LEGACY:
                await _refuse_set_level(client, seen)
            return seen


@pytest.fixture(scope="module")
def http_server(tmp_path_factory):
    """The server on a free localhost port, TERE4AI_MCP_TRANSPORT=http, with
    a key minted into a temporary key store (never the real one)."""
    store_dir = tmp_path_factory.mktemp("mcp_keys")
    keys_file = store_dir / "mcp_keys.json"
    usage_file = store_dir / "mcp_usage.jsonl"
    key, _record = create_key("c3-protocol-test", ["read_graph"], path=keys_file)
    process, port = _start_http_server(_http_env(keys_file, usage_file), store_dir)
    try:
        yield {"url": f"http://127.0.0.1:{port}/mcp", "key": key, "usage_file": usage_file}
    finally:
        _stop(process)


def _http_env(keys_file: Path, usage_file: Path) -> dict[str, str]:
    return _server_env(
        {
            "TERE4AI_MCP_TRANSPORT": "http",
            "TERE4AI_MCP_HOST": "127.0.0.1",
            "TERE4AI_MCP_KEYS": str(keys_file),
            "TERE4AI_MCP_USAGE": str(usage_file),
        }
    )


@pytest.mark.parametrize("mode", [_LEGACY, _MODERN])
def test_streamable_http_serves_both_revisions(mode, http_server):
    seen = asyncio.run(_http_session(http_server["url"], http_server["key"], mode))
    _assert_revision(seen, mode)
    # The key middleware authenticated the call from the temporary store.
    usage = http_server["usage_file"].read_text(encoding="utf-8")
    assert '"tool": "coverage_report"' in usage and '"allowed": true' in usage
    if mode == _LEGACY:
        # C3: the logging/setLevel refusal is asserted over HTTP too (final review fix).
        assert seen["set_level_code"] == METHOD_NOT_FOUND


def test_the_http_server_start_retries_once_on_a_port_taken_meanwhile(tmp_path):
    """A port picked free but taken before the server binds it: the server
    exits with address in use and is started again on a new port."""
    keys_file = tmp_path / "mcp_keys.json"
    create_key("c3-port-race", ["read_graph"], path=keys_file)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        taken_port = taken.getsockname()[1]
        ports = iter([taken_port, _free_port()])
        process, port = _start_http_server(
            _http_env(keys_file, tmp_path / "mcp_usage.jsonl"), tmp_path,
            pick_port=lambda: next(ports),
        )
        try:
            assert port != taken_port
            first_stderr = (tmp_path / "server-stderr-1.log").read_text(encoding="utf-8")
            assert _ADDRESS_IN_USE.search(first_stderr), first_stderr[-2000:]
        finally:
            _stop(process)


def test_a_server_that_exits_early_names_its_stderr(tmp_path):
    env = _server_env({"TERE4AI_MCP_TRANSPORT": "http", "TERE4AI_MCP_HOST": "127.0.0.1",
                       "TERE4AI_MCP_REPLAY_WINDOW_SECONDS": "ten"})
    with pytest.raises(AssertionError, match="TERE4AI_MCP_REPLAY_WINDOW_SECONDS"):
        _start_http_server(env, tmp_path)


# Calls that would send an MCP log message: a fastmcp Context log method,
# the SDK session's send_log_message, or the notification itself.
_MCP_LOG_CALL = re.compile(
    r"\b(?:ctx|context|fastmcp_context)\.(?:log|debug|info|warning|error)\("
    r"|send_log_message|notifications/message"
)


def test_no_source_file_sends_mcp_log_messages():
    offenders = []
    for path in sorted(_SRC.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _MCP_LOG_CALL.search(line):
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}: {line.strip()}")
    assert offenders == [], (
        "diagnostics go to Python logging on stderr, never MCP logging: " + "; ".join(offenders)
    )

"""A JSON object that names one key twice, measured on both surfaces (B34
item d, DEC-22).

The request names `features` twice: first a minimal-risk system, then the
same facts with employment_decisions true (Annex III point 4, high risk).
Each object is valid on its own and gives its own answer, so the answer
shows which one the surface read. Measured 2026-10-03 and pinned here: the
facade and the MCP server over stdio both read the last one; neither
refuses the request.
"""

from __future__ import annotations

import json
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.server_docs.session import server_env

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
_READ_TIMEOUT_SECONDS = 60.0

# Both surfaces classify against the Layer 1 dump; a fresh clone has none.
pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "graph_dumps" / "layer1.json").is_file(),
    reason="graph dumps not present (published build artifacts; see README quick start)",
)


def _features_pair() -> tuple[str, str]:
    """The two objects as JSON text: every flag known, so each answer is
    settled (minimal_risk and high_risk, nothing missing)."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    all_false = {name: False for name in schema["properties"]["flags"]["properties"]}
    minimal = {"description": "An email spam filter for a company mailbox.", "flags": all_false}
    hiring = {
        "description": "A system that ranks job applicants for hiring.",
        "flags": dict(all_false, employment_decisions=True),
    }
    return json.dumps(minimal), json.dumps(hiring)


def _twice(first: str, second: str) -> str:
    """An object whose `features` key appears twice, as raw JSON text."""
    return '{"features": ' + first + ', "features": ' + second + "}"


def test_facade_reads_the_last_of_a_repeated_key():
    first, second = _features_pair()
    with TestClient(facade.create_app()) as client:
        response = client.post(
            "/api/classify",
            content=_twice(first, second),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["missing_facts"] == []


def _send(process: subprocess.Popen, line: str) -> None:
    assert process.stdin is not None
    process.stdin.write((line + "\n").encode("utf-8"))
    process.stdin.flush()


def _response(process: subprocess.Popen, request_id: int) -> dict:
    """The JSON-RPC response with this id; other lines are skipped."""
    assert process.stdout is not None
    deadline = time.monotonic() + _READ_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], 1.0)
        if not ready:
            continue
        line = process.stdout.readline()
        if not line:
            break
        message = json.loads(line)
        if message.get("id") == request_id:
            return message
    raise AssertionError(f"no response to request {request_id} from the MCP server")


def test_mcp_server_reads_the_last_of_a_repeated_key():
    first, second = _features_pair()
    process = subprocess.Popen(
        [sys.executable, "-m", "tere4ai.mcp_server.server"],
        cwd=str(ROOT),
        env=server_env(root=ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        _send(
            process,
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "duplicate-keys-test", "version": "0"},
                    },
                }
            ),
        )
        assert "result" in _response(process, 1)
        _send(process, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        # One raw line: the arguments object names `features` twice.
        _send(
            process,
            '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": '
            '{"name": "classify_ai_system", "arguments": ' + _twice(first, second) + "}}",
        )
        response = _response(process, 2)
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.terminate()
        process.wait(timeout=10)
    result = response["result"]
    assert result["isError"] is False
    envelope = result["structuredContent"]
    assert envelope["answer"]["risk_category"] == "high_risk"
    assert envelope["missing_facts"] == []

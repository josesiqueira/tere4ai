"""Remote MCP transport flag tests (#70): stdio default, HTTP behind a flag."""

from __future__ import annotations

import pytest

from tere4ai.mcp_server import server


class _RunRecorder:
    def __init__(self):
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture()
def recorded_run(monkeypatch):
    recorder = _RunRecorder()
    monkeypatch.setattr(server.mcp, "run", recorder)
    return recorder


def test_default_is_stdio(monkeypatch, recorded_run):
    monkeypatch.delenv("TERE4AI_MCP_TRANSPORT", raising=False)
    server.main()
    assert recorded_run.kwargs == {}


def test_http_flag_selects_streamable_http(monkeypatch, recorded_run):
    monkeypatch.setenv("TERE4AI_MCP_TRANSPORT", "http")
    monkeypatch.setenv("TERE4AI_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("TERE4AI_MCP_PORT", "9100")
    server.main()
    assert recorded_run.kwargs == {"transport": "http", "host": "0.0.0.0", "port": 9100}


def test_http_defaults_bind_localhost(monkeypatch, recorded_run):
    monkeypatch.setenv("TERE4AI_MCP_TRANSPORT", "http")
    monkeypatch.delenv("TERE4AI_MCP_HOST", raising=False)
    monkeypatch.delenv("TERE4AI_MCP_PORT", raising=False)
    server.main()
    assert recorded_run.kwargs == {"transport": "http", "host": "127.0.0.1", "port": 8765}


def test_unknown_transport_fails_loudly(monkeypatch, recorded_run):
    monkeypatch.setenv("TERE4AI_MCP_TRANSPORT", "websocket")
    with pytest.raises(SystemExit, match="unsupported"):
        server.main()
    assert recorded_run.kwargs is None

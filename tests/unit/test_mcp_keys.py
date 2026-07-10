"""Key scope and usage accounting tests (#71)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp.exceptions import ToolError

from tere4ai.mcp_server import keys


@pytest.fixture()
def store_path(tmp_path):
    return tmp_path / "mcp_keys.json"


@pytest.fixture()
def usage_file(tmp_path):
    return tmp_path / "mcp_usage.jsonl"


def test_create_verify_roundtrip(store_path):
    plaintext, record = keys.create_key("uni-lab", ["read_graph"], store_path)
    assert plaintext.startswith(f"t4a_{record['key_id']}_")
    assert plaintext.split("_", 2)[2] not in json.dumps(keys.load_store(store_path))
    verified = keys.verify_key(plaintext, keys.load_store(store_path))
    assert verified is not None and verified["tenant"] == "uni-lab"


def test_wrong_secret_and_malformed_rejected(store_path):
    plaintext, record = keys.create_key("t", ["classify"], store_path)
    store = keys.load_store(store_path)
    assert keys.verify_key(f"t4a_{record['key_id']}_wrong", store) is None
    assert keys.verify_key("not-a-key", store) is None
    assert keys.verify_key("", store) is None


def test_revocation_takes_effect_on_next_lookup(store_path):
    plaintext, record = keys.create_key("t", ["read_graph"], store_path)
    assert keys.revoke_key(record["key_id"], store_path)
    assert keys.verify_key(plaintext, keys.load_store(store_path)) is None
    assert not keys.revoke_key(record["key_id"], store_path)


def test_unknown_or_empty_scopes_rejected(store_path):
    with pytest.raises(ValueError, match="unknown scopes"):
        keys.create_key("t", ["write_graph"], store_path)
    with pytest.raises(ValueError, match="at least one"):
        keys.create_key("t", [], store_path)


def test_every_mcp_tool_has_a_scope():
    from tere4ai.mcp_server import server

    tool_names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert tool_names == set(keys.TOOL_SCOPES)
    assert set(keys.TOOL_SCOPES.values()) <= keys.SCOPES


class _Ctx:
    def __init__(self, tool):
        self.message = type("M", (), {"name": tool})()


def _call(mw, tool, credential):
    mw._credential = lambda: credential

    async def call_next(ctx):
        return "TOOL RAN"

    return asyncio.run(mw.on_call_tool(_Ctx(tool), call_next))


def test_middleware_gates_by_scope_and_meters(store_path, usage_file):
    plaintext, _ = keys.create_key("t", ["read_graph"], store_path)
    mw = keys.ScopedKeyMiddleware(keys_file=store_path, usage_file=usage_file)

    assert _call(mw, "coverage_report", plaintext) == "TOOL RAN"
    with pytest.raises(ToolError, match="classify"):
        _call(mw, "classify_ai_system", plaintext)
    with pytest.raises(ToolError, match="authentication required"):
        _call(mw, "coverage_report", "")

    summary = keys.usage_summary(usage_file)
    key_id = plaintext.split("_")[1]
    assert summary[key_id]["tools"]["coverage_report"]["allowed"] == 1
    assert summary[key_id]["tools"]["classify_ai_system"]["denied"] == 1
    assert summary["anonymous"]["tools"]["coverage_report"]["denied"] == 1


def test_admin_scope_covers_everything(store_path, usage_file):
    plaintext, _ = keys.create_key("ops", ["admin"], store_path)
    mw = keys.ScopedKeyMiddleware(keys_file=store_path, usage_file=usage_file)
    assert _call(mw, "generate_control_backlog", plaintext) == "TOOL RAN"


def test_usage_events_are_body_free(store_path, usage_file):
    plaintext, _ = keys.create_key("t", ["classify"], store_path)
    mw = keys.ScopedKeyMiddleware(keys_file=store_path, usage_file=usage_file)
    _call(mw, "classify_ai_system", plaintext)
    event = json.loads(usage_file.read_text().splitlines()[0])
    assert set(event) == {"timestamp", "key_id", "tenant", "tool", "scope", "allowed"}

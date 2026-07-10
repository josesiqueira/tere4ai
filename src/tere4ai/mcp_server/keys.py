"""API key scopes and usage accounting for the MCP server.

@grounded_by: REF-31

Implements the key mechanics proposed in docs/PHASE2_DESIGN.md Section 3
against architecture.md Section 8 (authentication, scopes, read-only
default, request logging, revocable per-consumer keys) and Section 13
(secret redaction, body-free observability):

- Key format t4a_<key_id>_<secret>. The store keeps only the key_id, the
  tenant, the scope set, timestamps, and a salted sha256 of the secret;
  the plaintext secret is returned once at creation and never stored.
- Revocation marks the row; every request re-reads the store, so a
  revoked key dies on its next call while its usage history survives.
- Usage accounting appends one body-free JSONL event per tool call
  (timestamp, key_id, tenant, tool, scope, allowed); aggregates come
  from usage_summary(), never from stored request content.

Enforcement lives in ScopedKeyMiddleware, attached by server.main() for
the HTTP transport (or when TERE4AI_MCP_REQUIRE_KEY=1). Local stdio use
stays keyless: it is the Mode B trusted-workstation path.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets as pysecrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_KEYS_PATH = _PROJECT_ROOT / "data" / "keys" / "mcp_keys.json"
DEFAULT_USAGE_PATH = _PROJECT_ROOT / "data" / "keys" / "mcp_usage.jsonl"

SCOPES = frozenset({"read_graph", "classify", "evidence_paid", "backlog_paid", "admin"})

# docs/PHASE2_DESIGN.md Section 3: every MCP tool maps to exactly one scope.
TOOL_SCOPES: dict[str, str] = {
    "coverage_report": "read_graph",
    "source_trace": "read_graph",
    "explain_requirement": "read_graph",
    "trace_alignment": "read_graph",
    "resolve_span": "read_graph",
    "get_applicable_requirements": "read_graph",
    "classify_ai_system": "classify",
    "evaluate_project_evidence": "evidence_paid",
    "evaluate_project_evidence_batch": "evidence_paid",
    "generate_control_backlog": "backlog_paid",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash_secret(secret: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{secret}".encode()).hexdigest()


def keys_path() -> Path:
    return Path(os.environ.get("TERE4AI_MCP_KEYS", DEFAULT_KEYS_PATH))


def usage_path() -> Path:
    return Path(os.environ.get("TERE4AI_MCP_USAGE", DEFAULT_USAGE_PATH))


def load_store(path: Path | None = None) -> dict[str, Any]:
    path = path or keys_path()
    if not path.is_file():
        return {"keys": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_store(store: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=1) + "\n", encoding="utf-8")


def create_key(
    tenant: str, scopes: list[str], path: Path | None = None
) -> tuple[str, dict[str, Any]]:
    """Mint a key; returns (plaintext shown once, stored record)."""
    bad = sorted(set(scopes) - SCOPES)
    if bad:
        raise ValueError(f"unknown scopes: {', '.join(bad)}")
    if not scopes:
        raise ValueError("a key needs at least one scope")
    path = path or keys_path()
    store = load_store(path)
    key_id = pysecrets.token_hex(6)
    secret = pysecrets.token_urlsafe(24)
    salt = pysecrets.token_hex(8)
    record = {
        "key_id": key_id,
        "tenant": tenant,
        "scopes": sorted(set(scopes)),
        "salt": salt,
        "secret_hash": _hash_secret(secret, salt),
        "created_at": _now(),
        "revoked_at": None,
    }
    store["keys"].append(record)
    _write_store(store, path)
    return f"t4a_{key_id}_{secret}", record


def revoke_key(key_id: str, path: Path | None = None) -> bool:
    path = path or keys_path()
    store = load_store(path)
    for record in store["keys"]:
        if record["key_id"] == key_id and record["revoked_at"] is None:
            record["revoked_at"] = _now()
            _write_store(store, path)
            return True
    return False


def verify_key(raw: str, store: dict[str, Any]) -> dict[str, Any] | None:
    """Return the active key record for a t4a_ credential, else None."""
    parts = raw.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != "t4a":
        return None
    _, key_id, secret = parts
    for record in store["keys"]:
        if record["key_id"] != key_id or record["revoked_at"] is not None:
            continue
        candidate = _hash_secret(secret, record["salt"])
        if pysecrets.compare_digest(candidate, record["secret_hash"]):
            return record
    return None


def record_usage(event: dict[str, Any], path: Path | None = None) -> None:
    """Append one body-free accounting event; never raises into the caller."""
    path = path or usage_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        pass


def usage_summary(path: Path | None = None) -> dict[str, Any]:
    """Per-key, per-tool call counts split by allowed/denied."""
    path = path or usage_path()
    summary: dict[str, Any] = {}
    if not path.is_file():
        return summary
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            event = json.loads(line)
            per_key = summary.setdefault(
                event.get("key_id") or "anonymous", {"tenant": event.get("tenant"), "tools": {}}
            )
            per_tool = per_key["tools"].setdefault(
                event.get("tool", "unknown"), {"allowed": 0, "denied": 0}
            )
            per_tool["allowed" if event.get("allowed") else "denied"] += 1
    return summary


class ScopedKeyMiddleware(Middleware):
    """Per-key scope gate plus usage accounting on every tool call.

    Reads the Bearer credential from the HTTP Authorization header. A
    missing, malformed, revoked, or under-scoped key raises ToolError
    (the MCP-visible failure), and every decision is metered body-free.
    """

    def __init__(self, keys_file: Path | None = None, usage_file: Path | None = None):
        self._keys_file = keys_file
        self._usage_file = usage_file

    def _credential(self) -> str:
        from fastmcp.server.dependencies import get_http_headers

        # get_http_headers strips the authorization header by default (it is
        # designed for forwarding); include it explicitly.
        auth = get_http_headers(include={"authorization"}).get("authorization", "")
        return auth.removeprefix("Bearer ").strip()

    async def on_call_tool(self, context, call_next):
        tool = context.message.name
        scope = TOOL_SCOPES.get(tool)
        store = load_store(self._keys_file)
        record = verify_key(self._credential(), store)
        allowed = (
            record is not None
            and scope is not None
            and (scope in record["scopes"] or "admin" in record["scopes"])
        )
        record_usage(
            {
                "timestamp": _now(),
                "key_id": record["key_id"] if record else None,
                "tenant": record["tenant"] if record else None,
                "tool": tool,
                "scope": scope,
                "allowed": allowed,
            },
            self._usage_file,
        )
        if record is None:
            raise ToolError("authentication required: pass a t4a_ key as a Bearer token")
        if not allowed:
            raise ToolError(f"key lacks the {scope!r} scope required by {tool}")
        return await call_next(context)

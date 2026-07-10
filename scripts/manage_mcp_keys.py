"""Manage MCP API keys: create, revoke, list, and read usage aggregates.

@grounded_by: REF-31

Admin CLI for the key store in src/tere4ai/mcp_server/keys.py (architecture.md
Section 8: revocable, scoped per-consumer keys; docs/PHASE2_DESIGN.md Section
3 mechanics). The plaintext key is printed exactly once at creation; the
store keeps only a salted hash. Store and usage paths honour TERE4AI_MCP_KEYS
and TERE4AI_MCP_USAGE (defaults under data/keys/, which is gitignored).

Usage:
  .venv/bin/python scripts/manage_mcp_keys.py create --tenant NAME --scopes read_graph classify
  .venv/bin/python scripts/manage_mcp_keys.py revoke KEY_ID
  .venv/bin/python scripts/manage_mcp_keys.py list
  .venv/bin/python scripts/manage_mcp_keys.py usage
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.mcp_server import keys  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="mint a new key (plaintext shown once)")
    create.add_argument("--tenant", required=True)
    create.add_argument(
        "--scopes", nargs="+", required=True, choices=sorted(keys.SCOPES)
    )
    revoke = sub.add_parser("revoke", help="revoke a key by key_id")
    revoke.add_argument("key_id")
    sub.add_parser("list", help="list key metadata (never secrets)")
    sub.add_parser("usage", help="per-key, per-tool usage aggregates")

    args = parser.parse_args(argv)
    if args.command == "create":
        plaintext, record = keys.create_key(args.tenant, args.scopes)
        print(f"key_id: {record['key_id']}  tenant: {record['tenant']}")
        print(f"scopes: {', '.join(record['scopes'])}")
        print(f"key (shown once, store it now): {plaintext}")
        return 0
    if args.command == "revoke":
        if keys.revoke_key(args.key_id):
            print(f"revoked {args.key_id}")
            return 0
        print(f"no active key {args.key_id}", file=sys.stderr)
        return 1
    if args.command == "list":
        for record in keys.load_store()["keys"]:
            status = "revoked" if record["revoked_at"] else "active"
            print(
                f"{record['key_id']}  {status:8}  tenant={record['tenant']}  "
                f"scopes={','.join(record['scopes'])}  created={record['created_at']}"
            )
        return 0
    print(json.dumps(keys.usage_summary(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Load the Layer 0+1 dump into Neo4j (idempotent, constraints first).

@implements: DEC-09 (partial: repeatable Layer 1 load entrypoint)
@grounded_by: REF-08, REF-23

Usage:
  .venv/bin/python scripts/load_layer1.py [--dump data/graph_dumps/layer1.json]

Connection via NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD, defaulting to the
local v2 container (bolt://localhost:7688). MERGE semantics throughout, so
re-running never duplicates. This is the first step of the canonical
rebuild-from-source restore (docs/RUNBOOK_backup_restore.md); Layer 2/3
follows via scripts/publish_layer23.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.store import GraphStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dump", type=Path, default=ROOT / "data" / "graph_dumps" / "layer1.json"
    )
    args = parser.parse_args(argv)

    dump = json.loads(args.dump.read_text(encoding="utf-8"))
    build_id = dump.get("build", {}).get("build_id", "unknown")

    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "change_me")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    store = GraphStore()

    constraints = store.apply_constraints(driver)
    print(
        f"constraints: {constraints['applied']} applied, "
        f"{constraints['skipped_enterprise_only']} enterprise-only skipped"
    )
    counts = store.load_dump(dump, driver)
    driver.close()

    nodes = sum(v for k, v in counts.items() if k.startswith("node:"))
    edges = sum(v for k, v in counts.items() if k.startswith("edge:"))
    print(f"loaded {build_id} to {uri}: {nodes} nodes, {edges} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Export the judged Layer 2/3 subgraph as N-Triples via n10s.

@implements: DEC-09 (partial: RDF export CLI)
@grounded_by: REF-23

Usage:
  .venv/bin/python scripts/export_rdf.py [--out data/graph_dumps/layer23.nt]

Connection via NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD (defaults to the
local v2 container). The output is a build artifact, gitignored like the
JSON dumps; regenerate after any publish.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.rdf_export import export_ntriples  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "graph_dumps" / "layer23.nt"
    )
    args = parser.parse_args(argv)

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://localhost:7688"),
        auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "change_me"),
        ),
    )
    count = export_ntriples(driver, args.out)
    driver.close()
    print(f"exported {count} triples to {args.out.relative_to(ROOT)}")
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

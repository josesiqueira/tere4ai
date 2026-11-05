"""Point the facade and the MCP server at a published build (D-G21).

@implements: DEC-16 (partial: activation)
@grounded_by: REF-27, ADD-20

Usage: .venv/bin/python scripts/activate_build.py <chain_id> [--dump-dir data/graph_dumps]
Publishing writes the manifest; this is the explicit act that selects it.
The facade loads at startup: restart it to serve the activated build. The
MCP server loads per call and follows the pointer at once. The directory
must carry core_nodes.txt beside the published files (B182), or the served
build's /api/units answers 503.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# The core ids the facade's /api/units serves (http_facade/served_state.py
# reads them from the served directory); the hand-kept copy is
# data/graph_dumps/core_nodes.txt (B182).
CORE_NODES_FILE = "core_nodes.txt"

from tere4ai.graph_store.publication import ActivationError, activate, active_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chain_id")
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    args = parser.parse_args(argv)
    # B182 (2026-11-05): the facade reads the core ids from core_nodes.txt in
    # the served directory (/api/units answers 503 without it), and a build
    # published by hand into thesis/builds/<name>/ had none; refuse here, at
    # the one explicit act, so no served build lacks it again.
    if not (args.dump_dir / CORE_NODES_FILE).is_file():
        print(f"not activated: {CORE_NODES_FILE} is missing from {args.dump_dir}: the served build could not say "
              f"which units are its core (/api/units would answer 503); copy data/graph_dumps/{CORE_NODES_FILE} "
              "beside the published files first", file=sys.stderr)
        return 1
    try:
        activate(args.dump_dir, args.chain_id)
    except ActivationError as exc:
        print(f"not activated: {exc}", file=sys.stderr)
        return 1
    manifest = active_manifest(args.dump_dir)
    number = manifest.get("build_number")
    # Spec G D-G50: the number beside the full build id, never in its place.
    named = (f"Build {number} ({manifest['build_id']})" if number is not None
             else f"{manifest['build_id']} (no build number: published before B94)")
    print(f"activated {named}; restart the facade to serve it")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Point the facade and the MCP server at a published build (D-G21).

@implements: DEC-16 (partial: activation)
@grounded_by: REF-27, ADD-20

Usage: .venv/bin/python scripts/activate_build.py <chain_id> [--dump-dir data/graph_dumps]
Publishing writes the manifest; this is the explicit act that selects it.
The facade loads at startup: restart it to serve the activated build. The
MCP server loads per call and follows the pointer at once.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.publication import ActivationError, activate, active_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chain_id")
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    args = parser.parse_args(argv)
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

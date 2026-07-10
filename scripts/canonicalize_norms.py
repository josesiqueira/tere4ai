"""Run the canonicalize step over the judged norms payload (#33, DEC-04).

@implements: DEC-04 (partial: CLI entry for the canonicalize step)
@grounded_by: REF-11, REF-12

Reads data/graph_dumps/norms_core.json, applies actor canonicalisation and
Condition/Exception materialisation (deterministic rules, no model), and
writes the payload back with condition_ids/exception_ids populated and the
clause node lists attached. Re-running is a no-op. Republish with
scripts/publish_layer23.py afterwards so the clause nodes reach Neo4j.

Usage: .venv/bin/python scripts/canonicalize_norms.py [--norms PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.canonicalize.canonicalizer import canonicalize_norms  # noqa: E402

DEFAULT_NORMS = ROOT / "data" / "graph_dumps" / "norms_core.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--norms", type=Path, default=DEFAULT_NORMS)
    parser.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = parser.parse_args(argv)

    payload = json.loads(args.norms.read_text(encoding="utf-8"))
    result = canonicalize_norms(payload)
    stats = result["canonicalization"]
    total = len(result.get("norms", []))
    print(
        f"actors: {stats['actors_resolved']}/{total} resolved to the canonical "
        f"table; unresolved kinds: {len(stats['actors_unresolved'])}"
    )
    for actor, count in list(stats["actors_unresolved"].items())[:10]:
        print(f"  unresolved actor ({count}x): {actor!r}")
    print(
        f"clauses: {stats['condition_nodes']} Condition + "
        f"{stats['exception_nodes']} Exception nodes materialised"
    )
    if args.dry_run:
        return 0
    args.norms.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.norms}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

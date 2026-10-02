"""Print the build id a dump directory serves, the id the facade reports.

@implements: DEC-16 (partial: the served build named by the facade image)
@grounded_by: REF-27, ADD-20

Usage: .venv/bin/python scripts/served_build_id.py [--dump-dir data/graph_dumps] [--expect <build id>]

The id comes from the facade's own loader (load_active): the activated
publication's build id when an activation pointer exists, else the legacy
files' id with the chain over the files in the directory. The image build
runs this after the dumps are copied in and labels the image with the id
the release script passes; --expect makes the build fail when that id is
not the one the copied files serve, so the label cannot name another
graph. An empty --expect only prints. Exit 1 when the directory serves no
graph (a missing or drifted file) or the expected id differs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.publication import load_active  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    parser.add_argument("--expect", default="")
    args = parser.parse_args(argv)
    loaded = load_active(args.dump_dir)
    if loaded.error is not None:
        print(f"the dump directory serves no graph: {loaded.error}", file=sys.stderr)
        return 1
    if loaded.dump is None or loaded.norms is None or not loaded.build_id:
        print("the dump directory serves no graph: missing or unreadable layer1.json or norms_core.json",
              file=sys.stderr)
        return 1
    if args.expect and args.expect != loaded.build_id:
        print(f"expected build {args.expect}, but the files serve {loaded.build_id}", file=sys.stderr)
        return 1
    print(loaded.build_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())

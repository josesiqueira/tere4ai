"""CLI: python -m tere4ai.trace_scan <project_dir>

@implements: DEC-15
@grounded_by: ADD-14, ADD-15

Prints the tag-record JSON that trace_implementation takes as `tags`.
"""

import json
import sys
from pathlib import Path

from tere4ai.trace_scan import scan_tags


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m tere4ai.trace_scan <project_dir>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    print(json.dumps(scan_tags(root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

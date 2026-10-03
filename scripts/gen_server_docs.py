#!/usr/bin/env python3
"""Generate the public explanation of the MCP server from the running server.

@implements: DEC-22
@grounded_by: REF-31

Reads the example request from docs/server/index.md, starts the server over
stdio with no model keys, reads what it serves (instructions, tool list,
the answers of coverage_report and classify_ai_system) and writes the
source's generated regions, docs/server/tools.md, the README part into
README.md and the reading part into SKILL.md. Refuses to run when a tool's
openWorldHint, the word PAID in its description and its scope in
TOOL_SCOPES disagree.

Usage:
    python scripts/gen_server_docs.py             write the generated files
    python scripts/gen_server_docs.py --sessions  also write docs/server/sessions.md
    python scripts/gen_server_docs.py --check     write nothing; exit 1 naming
                                                  each file that would change
Exit codes: 0 current or written, 1 a file would change (--check), 2 refused.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.server_docs import render, session  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 on drift")
    parser.add_argument("--sessions", action="store_true", help="also write sessions.md")
    args = parser.parse_args(argv)

    source = (ROOT / render.SOURCE).read_text(encoding="utf-8")
    surface = session.read_surface(render.example_request(source), root=ROOT)
    problems = render.paid_disagreements(surface.tools)
    if problems:
        for problem in problems:
            print(f"refused: free or paid disagrees for {problem}", file=sys.stderr)
        return 2

    if args.check:
        changed = render.check(ROOT, surface)
        for name in changed:
            print(f"{name} is not current; run scripts/gen_server_docs.py", file=sys.stderr)
        return 1 if changed else 0

    texts = {name: (ROOT / name).read_text(encoding="utf-8") for name in render.SOURCE_FILES}
    with_sessions = args.sessions or (ROOT / render.SESSIONS_PAGE).is_file()
    sessions = render.read_sessions(ROOT) if with_sessions else None
    for name, text in render.render_files(texts, surface, sessions).items():
        path = ROOT / name
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8")
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

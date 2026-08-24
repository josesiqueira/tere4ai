"""CLI: python -m tere4ai.report <session.jsonl> [more...] [--envelope FILE ...] -o report.html

@implements: DEC-08, DEC-15
@grounded_by: ADD-14, ADD-15

Renders one self-contained HTML report from recorded MCP session JSONL files
and optional loose Section 8 envelope files. Exit codes: 0 on success, 2 on
usage errors or unreadable input.
"""

import sys
from pathlib import Path

from tere4ai.report.render import render_report_from_paths

USAGE = (
    "usage: python -m tere4ai.report <session.jsonl> [more...] "
    "[--envelope FILE ...] -o report.html"
)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    sessions: list[str] = []
    envelopes: list[str] = []
    out_path: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            print(USAGE)
            return 0
        if arg == "--envelope":
            if i + 1 >= len(args):
                print("--envelope requires a file argument", file=sys.stderr)
                print(USAGE, file=sys.stderr)
                return 2
            envelopes.append(args[i + 1])
            i += 2
            continue
        if arg in ("-o", "--out"):
            if i + 1 >= len(args):
                print(f"{arg} requires a file argument", file=sys.stderr)
                print(USAGE, file=sys.stderr)
                return 2
            out_path = args[i + 1]
            i += 2
            continue
        if arg.startswith("-"):
            print(f"unknown option: {arg}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 2
        sessions.append(arg)
        i += 1

    if out_path is None or (not sessions and not envelopes):
        print(USAGE, file=sys.stderr)
        return 2

    for path in [*sessions, *envelopes]:
        if not Path(path).is_file():
            print(f"not a readable file: {path}", file=sys.stderr)
            return 2

    try:
        html = render_report_from_paths(sessions, envelopes)
    except OSError as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2

    try:
        Path(out_path).write_text(html, encoding="utf-8")
    except OSError as exc:
        print(f"cannot write output: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

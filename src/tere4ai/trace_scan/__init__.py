"""Reference scanner for `@implements: <norm-id>` tags in a consumer project.

@implements: DEC-15
@grounded_by: ADD-14, ADD-15

Runs CLIENT-SIDE, in the consumer's checkout, because the MCP server never
reads a consumer filesystem (architecture.md Section 8). Deterministic: a
regex over text files, no model, no network. The output is the tag-record
list that the trace_implementation MCP tool takes as its `tags` input:

    [{"norm_id": "norm:eu-ai-act:...", "path": "src/x.py", "line": 12}, ...]

The scanner validates NOTHING about the ids it finds; validation against the
judge-accepted set is the server's job, so a consumer cannot accidentally
trust a tag the graph would reject.

Documentation files (.md, .txt) are deliberately NOT scanned: a tag written
in a README or prompt file is an example or description of the convention,
never an implementation claim, and treating it as one would let prose
manufacture trace locations (see SCANNED_SUFFIXES).

Usage:
    python -m tere4ai.trace_scan <project_dir>          # JSON to stdout
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# One norm id per tag, on its own line (comment or docstring), the same
# shape the repo's own decision tags use. The id charset mirrors the
# deterministic id scheme of architecture.md Section 2.
TAG_RE = re.compile(r"@implements:\s*(norm:[A-Za-z0-9:._-]+)")

# Files a consumer project plausibly carries code or config in. Kept
# explicit so binary and vendored content is never scanned by accident.
# Documentation suffixes (.md, .txt) are deliberately excluded: a literal
# tag example in a README or prompt file is prose about the convention,
# not a claim that the document implements the norm, and scanning it would
# turn documentation into implementation claims.
SCANNED_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".kt", ".go", ".rs",
    ".rb", ".cs", ".c", ".h", ".cpp", ".hpp", ".sql", ".sh",
    ".yaml", ".yml", ".toml", ".cfg", ".ini",
}

SKIPPED_DIRS = {
    ".git", ".hg", ".venv", "venv", "node_modules", "__pycache__",
    ".next", "dist", "build", ".mypy_cache", ".ruff_cache",
}


def scan_tags(project_dir: str | Path) -> list[dict[str, Any]]:
    """All `@implements: norm:...` tags under project_dir, sorted for
    deterministic output (path, then line)."""
    root = Path(project_dir)
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in TAG_RE.finditer(line):
                records.append(
                    {
                        "norm_id": match.group(1),
                        "path": path.relative_to(root).as_posix(),
                        "line": lineno,
                    }
                )
    records.sort(key=lambda r: (r["path"], r["line"]))
    return records

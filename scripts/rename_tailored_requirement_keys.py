#!/usr/bin/env python3
"""One-off: rewrite a kept file to the tailored requirement keys (B181, DEC-30, rulings R11 and R16).

@implements: DEC-30

The rule (R11, as Jose decided it on 2026-11-04, brief Q3: "b but you do
carefully : so there is no risk :)"): a key or a value inside a kept file is
migrated to the new word by one script that maps the keys and values and
proves its result equal to its input apart from the renamed keys and values.
Here the answer keys items, dropped_items and merged_items become
tailored_requirements, dropped_tailored_requirements and
merged_tailored_requirements, and answer.tool generate_control_backlog
becomes generate_tailored_requirements, through the report's one reader
(tere4ai.report.ingest.tailored_requirements_of_record, R6). Every other key
and value stays as it is (truncated included). The file is refused, exit 2
and nothing written, when nothing would be renamed or when any difference
between input and result is not one of those renames. For each file the run
prints the file, the sha256 of its bytes before, each difference and the
sha256 of its bytes after. The result keeps the input's form: its indent (1
when the second line starts with ' "', else 2), its \\u escapes when the
input is all ASCII, its final newline when it had one, so a diff shows only
the renamed lines. A file outside any git repository (no .git directory
above it, R16) has its original bytes copied first to <stem>.pre-B181<suffix>
beside it, and is refused when that copy already exists.

Usage: .venv/bin/python scripts/rename_tailored_requirement_keys.py <file>... [--keep-original | --no-keep-original]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.backlog import OLD_TOOL_NAME, TOOL_NAME
from tere4ai.report.ingest import (
    TAILORED_REQUIREMENT_KEYS_OF_RECORD,
    differences,
    tailored_requirements_of_record,
)


class Refused(Exception):
    """The file is left as it is; the run exits 2."""


def _under_git(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in path.resolve().parents)


def _indent_of(text: str) -> int:
    lines = text.splitlines()
    return 1 if len(lines) > 1 and lines[1].startswith(' "') else 2


def _renames(before: dict[str, Any], after: dict[str, Any], diffs: list[str], prefix: str) -> list[str]:
    """The differences as renames, in the order found; Refused when one is not."""
    allowed: dict[str, str | None] = {}
    for old_key, new_key in TAILORED_REQUIREMENT_KEYS_OF_RECORD.items():
        if old_key in before and new_key not in before and after.get(new_key) == before[old_key]:
            allowed[f"{prefix}.{old_key}: before only"] = (
                f"{prefix}.{old_key} renamed {prefix}.{new_key}, the value unchanged"
            )
            allowed[f"{prefix}.{new_key}: after only"] = None
    if before.get("tool") == OLD_TOOL_NAME:
        tool_diff = f"{prefix}.tool from {OLD_TOOL_NAME!r} to {TOOL_NAME!r}"
        allowed[tool_diff] = tool_diff
    unexpected = [d for d in diffs if d not in allowed]
    if unexpected:
        raise Refused("not a rename: " + "; ".join(unexpected))
    return [line for d in diffs if (line := allowed[d]) is not None]


def rewrite(path: Path, *, keep_original: bool) -> dict:
    """Rewrite one kept file; returns what was done. Raises Refused."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise Refused("not a JSON object")
    if isinstance(obj.get("answer"), dict):
        before, after_answer = obj["answer"], tailored_requirements_of_record(obj["answer"])
        result: dict[str, Any] = {**obj, "answer": after_answer}
        diffs = differences(obj, result, path="")
    else:
        # a bare answer, mapped at its top level
        before = obj
        result = after_answer = tailored_requirements_of_record(obj)
        diffs = differences(obj, result)
    if not diffs:
        raise Refused("nothing to rename")
    renames = _renames(before, after_answer, diffs, "answer")
    copy = path.with_name(f"{path.stem}.pre-B181{path.suffix}")
    if keep_original and copy.exists():
        raise Refused(f"{copy.name} already exists")
    body = json.dumps(result, indent=_indent_of(text), ensure_ascii=raw.isascii())
    if text.endswith("\n"):
        body += "\n"
    if keep_original:
        copy.write_bytes(raw)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {
        "path": str(path),
        "sha256_before": hashlib.sha256(raw).hexdigest(),
        "sha256_after": hashlib.sha256(path.read_bytes()).hexdigest(),
        "differences": renames,
        "original_copy": str(copy) if keep_original else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--keep-original",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="copy the original to <stem>.pre-B181<suffix> first (default: when the file is outside any git repository)",
    )
    args = parser.parse_args(argv)
    status = 0
    for path in args.files:
        keep = args.keep_original if args.keep_original is not None else not _under_git(path)
        try:
            before_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            done = rewrite(path, keep_original=keep)
        except (Refused, OSError, ValueError) as exc:
            print(f"refused {path}: {exc}", file=sys.stderr)
            status = 2
            continue
        print(path)
        print(f"sha256 before: {before_digest}")
        for line in done["differences"]:
            print(f"difference: {line}")
        if done["original_copy"]:
            print(f"original kept as {done['original_copy']}")
        print(f"sha256 after: {done['sha256_after']}")
    return status


if __name__ == "__main__":
    sys.exit(main())

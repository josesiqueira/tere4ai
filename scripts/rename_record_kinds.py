#!/usr/bin/env python3
"""One-off: rewrite stored records to the input and output kind keys (B158, spec G D-G81 (6)).

@implements: DEC-16 (the build record contract), DEC-17 (the evaluation record contract)

Pre-B74 records are disposable (Jose, 2026-09-30); this keeps the tracked
build chain records, the served build and the mock runs readable until the
B74 re-run writes fresh ones. Run it while no build command is live: the
rewrite does not take the store's per-record lock.

Usage: python scripts/rename_record_kinds.py <file>... [--dump-dir DIR]

In every inputs list the key role becomes input_kind, in every outputs list
output_kind; build_record.v2 becomes build_record.v3, evaluation_record.v1
evaluation_record.v2 and publication.v1 publication.v2. The chain files are
rewritten first; an output whose kind is build_chain then takes the sha256
of that file in DIR (default data/graph_dumps), since the rewrite changed
its bytes. Each file keeps its own indent, so a diff shows only the changed
lines. A second run changes nothing. A file that is not readable JSON is
reported and skipped, and the run exits 1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VERSIONS = {"build_record.v2": "build_record.v3", "evaluation_record.v1": "evaluation_record.v2",
            "publication.v1": "publication.v2"}
KEY_OF_LIST = {"inputs": "input_kind", "outputs": "output_kind"}


def _rekey(entry, new_key):
    if not isinstance(entry, dict) or "role" not in entry:
        return entry
    return {(new_key if k == "role" else k): v for k, v in entry.items()}


def rename(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in KEY_OF_LIST and isinstance(item, list):
                out[key] = [rename(_rekey(e, KEY_OF_LIST[key])) for e in item]
            elif key == "schema_version" and isinstance(item, str):
                out[key] = VERSIONS.get(item, item)
            else:
                out[key] = rename(item)
        return out
    if isinstance(value, list):
        return [rename(v) for v in value]
    return value


def refresh_chain_digests(value, dump_dir: Path):
    if isinstance(value, dict):
        out = {k: refresh_chain_digests(v, dump_dir) for k, v in value.items()}
        name = out.get("file")
        if out.get("output_kind") == "build_chain" and isinstance(name, str) and (dump_dir / name).is_file():
            out["sha256"] = hashlib.sha256((dump_dir / name).read_bytes()).hexdigest()
        return out
    if isinstance(value, list):
        return [refresh_chain_digests(v, dump_dir) for v in value]
    return value


def _indent_of(text: str) -> int:
    """The indent the file was written with: the leading spaces of its second line (1 when none)."""
    lines = text.splitlines()
    if len(lines) < 2:
        return 1
    return (len(lines[1]) - len(lines[1].lstrip(" "))) or 1


def _write_like(path: Path, payload, text: str) -> None:
    """Write payload atomically with the indent and final newline the file had."""
    body = json.dumps(payload, ensure_ascii=False, indent=_indent_of(text)) + ("\n" if text.endswith("\n") else "")
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    args = parser.parse_args(argv)
    chains = [p for p in args.files if p.name.startswith("build_chain_")]
    others = [p for p in args.files if not p.name.startswith("build_chain_")]
    skipped = 0
    for path in chains + others:
        # A file that is not readable JSON (a tmp file left by a crash, a
        # corrupt file, bytes that are not UTF-8) is reported and skipped; the
        # run goes on and exits 1. ValueError covers both decode errors.
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, ValueError) as exc:
            print(f"skipped {path.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        after = refresh_chain_digests(rename(data), args.dump_dir)
        if after != data:
            _write_like(path, after, text)
            print(path.name)
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

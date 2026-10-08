#!/usr/bin/env python3
"""One-off: rewrite stored build records to the full-word step ids (B155).

@implements: DEC-16 (the build record contract)

Pre-B74 records are disposable (Jose, 2026-09-30) and untracked local state
(.gitignore); this keeps the mock runs and the served build list working
until the B74 re-run writes fresh records.
Run once over a records directory: python scripts/rename_build_record_steps.py data/graph_dumps/build_records
Run it while no build command is live: the rewrite does not take the store's per-record lock.

Only the fields that hold a step id are renamed: each string of a
covers_steps list, and a dict key that is exactly an old step id (the steps
map of a presented record or a checkpoint). Every other string (an artifact
file name such as norms-L2.1.json, a record alias) is left as it is.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.build_record import SCHEMA_VERSION, atomic_write_json  # noqa: E402

MAP = {"L0.1": "LAYER0_STEP1", "L1.1": "LAYER1_STEP1", "L2.1": "LAYER2_STEP1", "L2.2": "LAYER2_STEP2", "L2.3": "LAYER2_STEP3",
       "L2.4": "LAYER2_STEP4", "L3.1": "LAYER3_STEP1", "L3.2": "LAYER3_STEP2", "L3.3": "LAYER3_STEP3", "L3.4": "LAYER3_STEP4",
       "L3.5": "LAYER3_STEP5", "P.1": "PUBLICATION_STEP1", "P.2": "PUBLICATION_STEP2"}
USAGE = "usage: python scripts/rename_build_record_steps.py <records_dir>"


def rename(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "covers_steps" and isinstance(item, list):
                out[key] = [MAP.get(s, s) if isinstance(s, str) else s for s in item]
            else:
                out[MAP.get(key, key)] = rename(item)
        return out
    if isinstance(value, list):
        return [rename(v) for v in value]
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print(USAGE, file=sys.stderr)
        return 2
    root = Path(argv[0])
    skipped = 0
    for path in sorted(root.rglob("*.json")):
        # A file that is not readable JSON (a tmp*.json left by a crash, a
        # corrupt file, bytes that are not UTF-8) is reported and skipped; the
        # run goes on and exits 1. ValueError covers both decode errors.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"skipped {path.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        after = rename(data)
        if isinstance(after, dict) and after.get("schema_version") == "build_record.v1":
            after["schema_version"] = SCHEMA_VERSION
        if after != data:
            atomic_write_json(path, after)
            print(path.name)
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

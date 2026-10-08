#!/usr/bin/env python3
"""One-off: rewrite stored build records to the full-word step ids (B155).

@implements: DEC-16 (the build record contract)

Pre-B74 records are disposable (Jose, 2026-09-30) and untracked local state
(.gitignore); this keeps the mock runs and the served build list working
until the B74 re-run writes fresh records.
Run once over a records directory: python scripts/rename_build_record_steps.py data/graph_dumps/build_records
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tere4ai.graph_store.build_record import SCHEMA_VERSION, atomic_write_json

MAP = {"L0.1": "LAYER0_STEP1", "L1.1": "LAYER1_STEP1", "L2.1": "LAYER2_STEP1", "L2.2": "LAYER2_STEP2", "L2.3": "LAYER2_STEP3",
       "L2.4": "LAYER2_STEP4", "L3.1": "LAYER3_STEP1", "L3.2": "LAYER3_STEP2", "L3.3": "LAYER3_STEP3", "L3.4": "LAYER3_STEP4",
       "L3.5": "LAYER3_STEP5", "P.1": "PUBLICATION_STEP1", "P.2": "PUBLICATION_STEP2"}
PAT = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(k) for k in MAP) + r")(?![0-9])")


def rename(value):
    if isinstance(value, dict):
        return {PAT.sub(lambda m: MAP[m.group(1)], k): rename(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rename(v) for v in value]
    if isinstance(value, str):
        return PAT.sub(lambda m: MAP[m.group(1)], value)
    return value


def main(argv: list[str]) -> int:
    root = Path(argv[0])
    skipped = 0
    for path in sorted(root.rglob("*.json")):
        # A file that is not readable JSON (a tmp*.json left by a crash, a
        # corrupt file) is reported and skipped; the run goes on and exits 1.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
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

#!/usr/bin/env python3
"""One-off: rewrite stored build records to the full-word step ids (B155, extended for the gate names by B156).

@implements: DEC-16 (the build record contract)

Pre-B74 records are disposable (Jose, 2026-09-30) and untracked local state
(.gitignore); this keeps the mock runs and the served build list working
until the B74 re-run writes fresh records.
Run once over a records directory: python scripts/rename_build_record_steps.py data/graph_dumps/build_records
Run it again after B156 for the gate names: the step rename is idempotent.
Run it while no build command is live: the rewrite does not take the store's per-record lock.

Only the fields that hold a step id are renamed: each string of a
covers_steps list, and a dict key that is exactly an old step id (the steps
map of a presented record or a checkpoint). Every other string (an artifact
file name such as norms-L2.1.json, a record alias) is left as it is.
Since B156 the gate entries of each gates and postload_gates list are
renamed too: the name G1 to G6 becomes PUBLICATION_GATE1 to
PUBLICATION_GATE6, P1 to P5 becomes POSTLOAD_GATE1 to POSTLOAD_GATE5, and
the gate name that opens each clause of the entry's detail follows.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.build_record import atomic_write_json  # noqa: E402

MAP = {"L0.1": "LAYER0_STEP1", "L1.1": "LAYER1_STEP1", "L2.1": "LAYER2_STEP1", "L2.2": "LAYER2_STEP2", "L2.3": "LAYER2_STEP3",
       "L2.4": "LAYER2_STEP4", "L3.1": "LAYER3_STEP1", "L3.2": "LAYER3_STEP2", "L3.3": "LAYER3_STEP3", "L3.4": "LAYER3_STEP4",
       "L3.5": "LAYER3_STEP5", "P.1": "PUBLICATION_STEP1", "P.2": "PUBLICATION_STEP2"}
GATE_MAP = {**{f"G{i}": f"PUBLICATION_GATE{i}" for i in range(1, 7)}, **{f"P{i}": f"POSTLOAD_GATE{i}" for i in range(1, 6)}}
_PREFIX = re.compile(r"^(G[1-6]|P[1-5]) ")
USAGE = "usage: python scripts/rename_build_record_steps.py <records_dir>"


def rename_gate_entry(entry):
    """A gate entry's name, and the gate name that opens each clause of its detail (B156)."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if isinstance(out.get("name"), str):
        out["name"] = GATE_MAP.get(out["name"], out["name"])
    if isinstance(out.get("detail"), str):
        out["detail"] = "; ".join(_PREFIX.sub(lambda m: GATE_MAP[m.group(1)] + " ", c) for c in out["detail"].split("; "))
    return out


def rename(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in ("gates", "postload_gates") and isinstance(item, list):
                out[key] = [rename_gate_entry(e) for e in item]
                continue
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
            # Its own target, not the store's current version: since B158 the
            # store reads build_record.v3, which scripts/rename_record_kinds.py writes.
            after["schema_version"] = "build_record.v2"
        if after != data:
            atomic_write_json(path, after)
            print(path.name)
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

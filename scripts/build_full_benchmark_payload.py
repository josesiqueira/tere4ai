"""Build the full REF-15 benchmark payload for the #27 ablation run.

@implements: DEC-11 (partial: full-benchmark payload assembly for the ablation ladder)
@grounded_by: REF-15

Combines the frozen full benchmark files (data/snapshots/benchmark/
scenarios.json and qa_pairs.json) into one payload file with the exact
shape eval.harness.load_benchmark_items expects: the provenance block
copied from eval/gold/benchmark_sample.json, plus every scenario and QA
pair stamped with benchmark_index = its position in the source file
(the same convention the sample's provenance documents).

Before combining, both source files are sha256-verified against the
pinned provenance, so the payload can only ever be built from the exact
bytes the sample was drawn from. The output is deterministic: same
inputs, same bytes. The file is generated (gitignored), never edited.

Usage:
  .venv/bin/python scripts/build_full_benchmark_payload.py \
      [--out data/snapshots/benchmark/full_payload.json] [--development-set]

--development-set writes the pilot run's sample of the development set (B150
Q10): from the items outside the frozen sample (spec G D-G84 (5)), a random
sample with the frozen sample's composition, drawn by the E6 declaration's
seed, stamped with the sample's digest, the draw and the drawn indexes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.ablation_declaration import load_declaration, pilot_draw  # noqa: E402
from tere4ai.eval.harness import (  # noqa: E402
    development_payload,
    load_benchmark_items,
    load_development_items,
)

BENCH_DIR = ROOT / "data" / "snapshots" / "benchmark"
SAMPLE_PATH = ROOT / "eval" / "gold" / "benchmark_sample.json"
DEFAULT_OUT = BENCH_DIR / "full_payload.json"
DEFAULT_DEVELOPMENT_OUT = BENCH_DIR / "development_payload.json"


def build_payload() -> dict:
    provenance = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))["provenance"]
    for name, meta in provenance["files"].items():
        path = BENCH_DIR / name
        if not path.exists():
            raise SystemExit(
                f"{path} missing: download scenarios.json and qa_pairs.json from "
                f"{provenance['repository']} into {BENCH_DIR}"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise SystemExit(f"{path}: sha256 {digest} != pinned {meta['sha256']}")

    scenarios = json.loads((BENCH_DIR / "scenarios.json").read_text(encoding="utf-8"))["data"]
    qa_pairs = json.loads((BENCH_DIR / "qa_pairs.json").read_text(encoding="utf-8"))["data"]
    return {
        "provenance": provenance,
        "scenarios": [dict(s, benchmark_index=i) for i, s in enumerate(scenarios)],
        "qa_pairs": [dict(q, benchmark_index=i) for i, q in enumerate(qa_pairs)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--development-set", action="store_true",
                        help="write the pilot run's sample of the development set (B150 Q10)")
    args = parser.parse_args(argv)

    payload = build_payload()
    out = args.out or (DEFAULT_DEVELOPMENT_OUT if args.development_set else DEFAULT_OUT)
    draw = pilot_draw(load_declaration()) if args.development_set else None
    if args.development_set:
        sample_bytes = SAMPLE_PATH.read_bytes()
        payload = development_payload(payload, json.loads(sample_bytes), hashlib.sha256(sample_bytes).hexdigest(),
                                      draw)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    items = load_development_items(out, draw=draw) if args.development_set else load_benchmark_items(out)
    kinds: dict[str, int] = {}
    for item in items:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(
        f"wrote {shown}: {len(payload['scenarios'])} scenarios + "
        f"{len(payload['qa_pairs'])} qa_pairs -> {len(items)} harness items {kinds}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

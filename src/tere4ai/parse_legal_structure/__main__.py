"""Build entry point: python -m tere4ai.parse_legal_structure

@implements: DEC-01, DEC-16 (partial: the L0.1 and L1.1 execution record)
@grounded_by: REF-27, REF-08, ADD-20

Builds the merged Layer 0 + Layer 1 dump from the frozen snapshot, runs the
deterministic cross-reference rule pass (DEC-02), validates the result against
the Section 13 critical gates, and publishes data/graph_dumps/layer1.json only
when every gate passes. Every attempt writes an execution record covering
L0.1 (the manifest check) and L1.1 (the parse) into the build record store
(D-G20), with one outcome per gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore, gate_entries
from tere4ai.parse_legal_structure.parser import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_OUT_PATH,
    build_layer1,
)
from tere4ai.resolve_crossrefs.resolver import resolve
from tere4ai.validate_graph.gates import validate_build

GATES = ("G1", "G2", "G3", "G4", "G5", "G6")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tere4ai.parse_legal_structure")
    parser.add_argument("--dump-dir", type=Path, default=DEFAULT_OUT_PATH.parent)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    out_path = args.dump_dir / DEFAULT_OUT_PATH.name
    tmp_path = out_path.with_suffix(".building.json")
    manifest_files: list[dict] = []
    inputs: list[dict] = []
    if args.manifest.is_file():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest_files = [{"file": m.get("file"), "sha256": m.get("sha256")} for m in manifest.get("snapshots", [])]
        inputs.append({"role": "manifest", "file": args.manifest.name, "sha256": sha256_of_file(args.manifest)})

    store = BuildRecordStore(args.dump_dir)
    record_id = store.create_record(f"parse-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}", None, None)
    run_id = store.start_execution(
        record_id, command="parse_legal_structure", covers_steps=["L0.1", "L1.1"], argv=raw_argv, inputs=inputs,
        config={"manifest_files_count": len(manifest_files)}, expected_total=None, work_unit=None,
        checkpoint_file=None,
    )
    try:
        dump = build_layer1(out_path=tmp_path, manifest_path=args.manifest)
        dump = resolve(dump)
        report = validate_build(dump)
        by_type: dict[str, int] = {}
        for node in dump["nodes"]:
            by_type[node["type"]] = by_type.get(node["type"], 0) + 1
        counts = {
            "nodes": len(dump["nodes"]), "edges": len(dump.get("edges", [])), "nodes_by_type": by_type,
            "review_queue": len(dump.get("review_queue", [])), "manifest_files": manifest_files,
            "manifest_files_count": len(manifest_files),
        }
        gates = gate_entries(report.failures, GATES, report.stats)
        if not report.passed:
            for failure in report.failures[:20]:
                print(f"GATE FAIL {failure}", file=sys.stderr)
            tmp_path.unlink(missing_ok=True)
            store.finish_execution(record_id, run_id, status="failed", counts=counts, gates=gates,
                                   error="; ".join(report.failures[:20]))
            print("build NOT published: critical validation failed", file=sys.stderr)
            return 1
        out_path.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
        digest = sha256_of_file(out_path)
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised for the operator
        store.finish_execution(record_id, run_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    store.finish_execution(
        record_id, run_id, status="done", counts=counts, gates=gates,
        outputs=[{"role": "layer1_dump", "file": out_path.name, "sha256": digest}],
    )
    store.set_layer1_digest(record_id, digest)
    base = dump.get("build", {}).get("build_id")
    if base:
        store.set_base_build_id(record_id, base)
    store.add_alias(record_id, f"layer1-{digest[:12]}")
    print(f"wrote {out_path}")
    print(f"build_id: {dump['build']['build_id']}")
    print(f"nodes: {len(dump['nodes'])}, edges: {len(dump['edges'])}")
    for node_type in sorted(by_type):
        print(f"  {node_type}: {by_type[node_type]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

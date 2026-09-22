"""Materialise a frozen campaign's decisions into a reference norms or alignments file.

@implements: DEC-16 (partial: CLI of the materialise step, D-G27)
@grounded_by: REF-24, REF-27, ADD-20

Usage:
  .venv/bin/python scripts/materialize_reference.py --pristine data/graph_dumps/norms_core.json \
      --decisions <decisions.json> --manifest <freeze-manifest.json> [--out ...] [--dump-dir ...] [--source-build-id ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.build_chain import served_build_id, sha256_of_file  # noqa: E402
from tere4ai.graph_store.build_record import (  # noqa: E402
    BuildRecordStore,
    atomic_write_json,
    relative_to_dump_dir,
)
from tere4ai.review_queue import load_decisions  # noqa: E402
from tere4ai.review_queue.materialize import (  # noqa: E402
    MaterializeError,
    materialize,
    verify_freeze_manifest,
)

SUFFIX = {"norms": ".reference", "alignments": ".adjudicated"}
STEP = {"norms": ["L2.4"], "alignments": ["L3.5"]}


def _source_build_id(args, store: BuildRecordStore, pristine_digest: str, base: str | None) -> str | None:
    if args.source_build_id:
        return args.source_build_id
    rid = store.find_by_output_digest(pristine_digest)
    if rid is not None:
        publication = store.read(rid)["publication"]
        if publication:
            return publication["build_id"]
    dump_dir = args.dump_dir or args.pristine.parent
    if args.pristine.resolve().parent == Path(dump_dir).resolve() and args.pristine.name in ("norms_core.json", "alignments_core.json") and base:
        return served_build_id(dump_dir, base)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--dump-dir", type=Path, default=None)
    parser.add_argument("--source-build-id", default=None, help="the served build id the freeze pinned (default: from the record or the served chain)")
    args = parser.parse_args(argv)
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    pristine = json.loads(args.pristine.read_text(encoding="utf-8"))
    kind = "norms" if "norms" in pristine else "alignments"
    slug = args.pristine.stem.removeprefix(f"{kind}_")
    out = args.out or args.pristine.with_name(f"{kind}_{slug}{SUFFIX[kind]}.json")
    for other in (args.pristine, args.decisions, args.manifest):
        if out.resolve() == other.resolve():
            print(f"not materialised: --out is the same file as {other.name}", file=sys.stderr)
            return 1
    if out.exists():
        print(f"not materialised: {out} exists; a reference file is never overwritten", file=sys.stderr)
        return 1

    dump_dir = args.dump_dir or args.pristine.parent
    store = BuildRecordStore(dump_dir)
    digests = {"pristine": sha256_of_file(args.pristine), "decisions": sha256_of_file(args.decisions),
               "manifest": sha256_of_file(args.manifest)}
    base = pristine.get("build", {}).get("build_id")
    source_build_id = _source_build_id(args, store, digests["pristine"], base)
    if source_build_id is None:
        print("not materialised: cannot establish the build this file was served under; pass --source-build-id", file=sys.stderr)
        return 1
    source_rid = store.find_by_output_digest(digests["pristine"])
    alias = f"{slug}{SUFFIX[kind]}"
    if source_rid is not None and store.is_frozen(source_rid):
        record_id = store.create_record(alias, base, store.read(source_rid)["layer1_digest"], parent_record_id=source_rid)
    elif source_rid is not None:
        record_id = source_rid
    else:
        record_id = store.create_record(alias, base, None)
        print(f"note: no record published {args.pristine.name}; materialising under a new record {record_id}")
    run_id = store.start_execution(
        record_id, command="materialize_reference", covers_steps=STEP[kind], argv=raw_argv,
        inputs=[{"role": kind, "file": relative_to_dump_dir(args.pristine, dump_dir), "sha256": digests["pristine"]},
                {"role": "decisions", "file": relative_to_dump_dir(args.decisions, dump_dir), "sha256": digests["decisions"]},
                {"role": "freeze_manifest", "file": relative_to_dump_dir(args.manifest, dump_dir), "sha256": digests["manifest"]}],
        config={"source_build_id": source_build_id}, expected_total=None, work_unit=None, checkpoint_file=None,
    )
    try:
        manifest = verify_freeze_manifest(json.loads(args.manifest.read_text(encoding="utf-8")), args.decisions,
                                          expected_pinned_build_id=source_build_id)
        decisions = load_decisions(args.decisions)
        result = materialize(kind, pristine, decisions, manifest, source_sha256=digests["pristine"],
                             source_build_id=source_build_id, decisions_sha256=digests["decisions"])
        atomic_write_json(out, result)
    except (MaterializeError, ValueError, OSError) as exc:
        store.finish_execution(record_id, run_id, status="failed", error=str(exc))
        print(f"not materialised: {exc}", file=sys.stderr)
        return 1
    applied = result["build"]["reference"]["decisions_applied"]
    store.finish_execution(
        record_id, run_id, status="done",
        outputs=[{"role": f"{kind}_reference", "file": relative_to_dump_dir(out, dump_dir), "sha256": sha256_of_file(out)}],
        counts={"decisions_applied": applied},
    )
    print(f"wrote {out} ({applied} decisions applied); record {record_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

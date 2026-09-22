"""Build entry point: python -m tere4ai.extract_norms --nodes eu-ai-act:article-9

@implements: DEC-03, DEC-06 (partial: extraction judge only), DEC-16 (partial: the L2.1 and L2.2 execution record)
@grounded_by: REF-11, REF-12, REF-13, REF-16, REF-24, REF-27, ADD-20

Runs the judged norm-extraction pipeline over the given Layer 1 node ids
(article ids expand to their paragraphs and points) and writes
data/graph_dumps/norms_<slug>.json. Use --dry-run to list the source units
without calling any model. Every attempt writes an execution record covering
L2.1 and L2.2 into the build record store (D-G20), with run ids on every
checkpoint line and a validated resume.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.extract_norms.pipeline import (
    DEFAULT_DUMP_PATH,
    REPO_ROOT,
    expand_source_units,
    extract_norms,
    load_prompt,
    prompt_sha256,
)
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore, select_record
from tere4ai.graph_store.checkpoints import CheckpointError, prepare_resume
from tere4ai.judge.config import load_model_config

GENERATOR_PROMPT_KIND = "extract_norms"
JUDGE_PROMPT_KIND = "judge_norms"
RESULT_KEYS = ("norms", "judge_runs", "stats")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slug(node_ids: list[str]) -> str:
    """Short, filesystem-safe slug.

    Never concatenates every node id: a 29-node core run once produced a
    filename beyond the OS limit and lost a completed run at the final write.
    Uses up to two leading names plus a count and a stable hash.
    """
    import hashlib

    parts = [n.removeprefix("eu-ai-act:").replace(":", "-") for n in node_ids[:2]]
    digest = hashlib.sha1(",".join(node_ids).encode()).hexdigest()[:8]
    if len(node_ids) > 2:
        parts.append(f"plus{len(node_ids) - 2}")
    parts.append(digest)
    return "_".join(parts)


def _sampling_of(client: object) -> str:
    """What the client actually sent (B74); "unknown" for a stub without the record."""
    return str(getattr(client, "sampling", "unknown"))


def _usage_of(client: object) -> dict:
    """Provider-reported token counts over this run; empty for a stub."""
    return dict(getattr(client, "usage", None) or {})


def _relative_to_dump_dir(path: Path, dump_dir: Path) -> str:
    """Path relative to dump_dir when it lies under it, else the absolute path.
    The presenter later resolves dump_dir / this value."""
    try:
        return str(path.relative_to(dump_dir))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tere4ai.extract_norms",
        description="Judged norm extraction over Layer 1 source units (M2).",
    )
    parser.add_argument(
        "--nodes",
        required=True,
        help="comma-separated Layer 1 node ids; article/annex ids expand to "
        "their paragraphs, points, and annex items",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        default=DEFAULT_DUMP_PATH,
        help=f"layer1 dump path (default {DEFAULT_DUMP_PATH})",
    )
    parser.add_argument(
        "--prompt-version", default="v1", help="prompt version for generator and judge"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list the source units that would be extracted, without model calls",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default data/graph_dumps/norms_<slug>.json)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip node groups already present in the checkpoint file",
    )
    parser.add_argument("--dump-dir", type=Path, default=None,
                        help="where build records live (default: the output file's directory)")
    parser.add_argument("--record", default=None,
                        help="build record alias or id (default: the output slug)")
    parser.add_argument("--accept-legacy-checkpoint", action="store_true",
                        help="inherit checkpoint lines written before build records existed (no run id)")
    args = parser.parse_args(argv)

    node_ids = [node_id.strip() for node_id in args.nodes.split(",") if node_id.strip()]
    if not node_ids:
        parser.error("--nodes is empty")

    dump = json.loads(args.dump.read_text(encoding="utf-8"))

    if args.dry_run:
        units = expand_source_units(dump, node_ids)
        print(f"{len(units)} source unit(s) for {', '.join(node_ids)}:")
        for unit in units:
            print(f"  {unit['node_id']} ({unit['node_type']}, span {unit['span_id']}, "
                  f"{len(unit['text'])} chars)")
        return 0

    out_path = args.out or (
        REPO_ROOT / "data" / "graph_dumps" / f"norms_{_slug(node_ids)}.json"
    )
    dump_dir = args.dump_dir or out_path.parent
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # fail fast at ZERO cost if the output path is unwritable (the 405-unit
    # core run of 2026-07-08 was lost to a too-long filename at the final write)
    out_path.touch()
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    layer1_digest = sha256_of_file(args.dump)
    inputs = [{"role": "layer1_dump", "file": _relative_to_dump_dir(args.dump, dump_dir),
               "sha256": layer1_digest}]
    config = {"prompt_version": args.prompt_version, "nodes": node_ids}
    store = BuildRecordStore(dump_dir)
    record_id, message = select_record(store, args.record or out_path.stem.removeprefix("norms_"),
                                       dump.get("build", {}).get("build_id"), layer1_digest)
    if message:
        print(message)
    try:
        plan = prepare_resume(checkpoint_path, "group", RESULT_KEYS, resume=args.resume,
                              accept_legacy=args.accept_legacy_checkpoint, store=store, record_id=record_id,
                              expected_config=config, expected_inputs=inputs)
    except CheckpointError as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2
    if plan.inherited_keys:
        print(f"resume: {len(plan.inherited_keys)} group(s) inherited from {plan.inherited_from}")

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)
    run_id = store.start_execution(
        record_id, command="extract_norms", covers_steps=["L2.1", "L2.2"],
        argv=list(sys.argv[1:] if argv is None else argv), inputs=inputs, config=config,
        expected_total=len(node_ids), work_unit="groups",
        checkpoint_file=_relative_to_dump_dir(checkpoint_path, dump_dir),
        resumes_run_id=plan.resumes_run_id, inherited_keys=plan.inherited_keys, inherited_from=plan.inherited_from,
        models=cfg.as_public_dict(),
        prompt_sha256={"generator": prompt_sha256(load_prompt(GENERATOR_PROMPT_KIND, args.prompt_version)),
                       "judge": prompt_sha256(load_prompt(JUDGE_PROMPT_KIND, args.prompt_version))},
        sampling={"generator": _sampling_of(generator), "judge": _sampling_of(judge)},
    )

    group_results: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
    completed: list[str] = []

    def usage() -> dict:
        return {"generator": _usage_of(generator), "judge": _usage_of(judge)}

    try:
        # one pipeline call per top-level node id, checkpointed immediately, so a
        # crash can never lose more than the group in flight
        with checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for group_id in node_ids:
                if group_id in plan.entries_by_key:
                    continue
                result = extract_norms(
                    dump, [group_id], generator, judge, prompt_version=args.prompt_version
                )
                ckpt.write(json.dumps({"run_id": run_id, "group": group_id, "result": result}) + "\n")
                ckpt.flush()
                group_results.append(result)
                completed.append(group_id)
                store.heartbeat(record_id, run_id)
                verdicts = result["stats"].get("verdicts", {})
                print(f"  {group_id}: {len(result['norms'])} norms, verdicts {verdicts}",
                      flush=True)

        merged: dict = {"norms": [], "judge_runs": [], "stats": {
            "source_units": 0, "candidates": 0, "verdicts": {},
            "nodes_failed": [], "invalid_norms": [],
        }}
        for result in group_results:
            merged["norms"].extend(result["norms"])
            merged["judge_runs"].extend(result["judge_runs"])
            stats = result["stats"]
            merged["stats"]["source_units"] += stats.get("source_units", 0)
            merged["stats"]["candidates"] += stats.get("candidates", 0)
            for verdict, count in stats.get("verdicts", {}).items():
                merged["stats"]["verdicts"][verdict] = (
                    merged["stats"]["verdicts"].get(verdict, 0) + count
                )
            merged["stats"]["nodes_failed"].extend(stats.get("nodes_failed", []))
            merged["stats"]["invalid_norms"].extend(stats.get("invalid_norms", []))

        payload = {
            "build": {
                **dump.get("build", {}),
                "extraction_models": cfg.as_public_dict(),
                "extraction_sampling": {"generator": _sampling_of(generator), "judge": _sampling_of(judge)},
                "extraction_usage": usage(),
                "extracted_at": _now_iso(),
                "prompt_version": args.prompt_version,
            },
            **merged,
        }
        tmp_path = out_path.with_suffix(".writing.json")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.replace(out_path)
        stats = merged["stats"]
        store.finish_execution(
            record_id, run_id, status="done",
            outputs=[{"role": "norms", "file": _relative_to_dump_dir(out_path, dump_dir),
                     "sha256": sha256_of_file(out_path)}],
            counts={"source_units": stats["source_units"], "candidates": stats["candidates"],
                    "verdicts": stats["verdicts"], "invalid_norms_count": len(stats["invalid_norms"])},
            usage=usage(), sampling=payload["build"]["extraction_sampling"], completed_keys=completed,
            work_failures={"nodes_failed": len(stats["nodes_failed"]), "norms_failed": 0},
        )
    except Exception as exc:  # noqa: BLE001 - recorded with what is known, then re-raised
        store.finish_execution(record_id, run_id, status="failed", usage=usage(), completed_keys=completed,
                               error=f"{type(exc).__name__}: {exc}")
        raise
    checkpoint_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(f"source units: {stats['source_units']}, candidates: {stats['candidates']}")
    print(f"verdicts: {stats['verdicts']}")
    if stats["nodes_failed"]:
        print(f"failed nodes: {len(stats['nodes_failed'])} (see stats in the output file)")
    if stats["invalid_norms"]:
        print(f"invalid norms dropped: {len(stats['invalid_norms'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

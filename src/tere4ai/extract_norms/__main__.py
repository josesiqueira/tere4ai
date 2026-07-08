"""Build entry point: python -m tere4ai.extract_norms --nodes eu-ai-act:article-9

@implements: DEC-03, DEC-06 (partial: extraction judge only)
@grounded_by: REF-11, REF-12, REF-13, REF-16, REF-24

Runs the judged norm-extraction pipeline over the given Layer 1 node ids
(article ids expand to their paragraphs and points) and writes
data/graph_dumps/norms_<slug>.json. Use --dry-run to list the source units
without calling any model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.extract_norms.pipeline import (
    DEFAULT_DUMP_PATH,
    REPO_ROOT,
    expand_source_units,
    extract_norms,
)
from tere4ai.judge.config import load_model_config


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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # fail fast at ZERO cost if the output path is unwritable (the 405-unit
    # core run of 2026-07-08 was lost to a too-long filename at the final write)
    out_path.touch()
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    done_groups: set[str] = set()
    group_results: list[dict] = []
    if args.resume and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            done_groups.add(entry["group"])
            group_results.append(entry["result"])
        print(f"resume: {len(done_groups)} group(s) already checkpointed")

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)

    # one pipeline call per top-level node id, checkpointed immediately, so a
    # crash can never lose more than the group in flight
    with checkpoint_path.open("a", encoding="utf-8") as ckpt:
        for group_id in node_ids:
            if group_id in done_groups:
                continue
            result = extract_norms(
                dump, [group_id], generator, judge, prompt_version=args.prompt_version
            )
            ckpt.write(json.dumps({"group": group_id, "result": result}) + "\n")
            ckpt.flush()
            group_results.append(result)
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
            "prompt_version": args.prompt_version,
        },
        **merged,
    }
    tmp_path = out_path.with_suffix(".writing.json")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp_path.replace(out_path)
    checkpoint_path.unlink(missing_ok=True)

    stats = merged["stats"]
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

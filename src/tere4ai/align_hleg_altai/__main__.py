"""Build entry point: python -m tere4ai.align_hleg_altai --norms data/graph_dumps/norms_<slug>.json

@implements: DEC-05, DEC-06 (partial: mapping judge)
@grounded_by: REF-24, REF-21, REF-10, REF-16

Runs the judged alignment pipeline over the accepted norms in the given
norms dump, against the seven HLEG requirement nodes, and writes
data/graph_dumps/alignments_<slug>.json. Norm source text is resolved from
the layer1 dump via each norm's source_node_id. Use --dry-run to list the
norms that would be aligned without calling any model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg_altai.pipeline import align_norms
from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.extract_norms.pipeline import DEFAULT_DUMP_PATH, REPO_ROOT
from tere4ai.judge.config import load_model_config


def _attach_source_text(norms: list[dict], layer1: dict) -> None:
    """Resolve each norm's source_text from its layer1 source node."""
    nodes = {node["id"]: node for node in layer1["nodes"]}
    for norm in norms:
        if norm.get("source_text"):
            continue
        node = nodes.get(norm.get("source_node_id", ""))
        if node is not None and node.get("text"):
            norm["source_text"] = node["text"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tere4ai.align_hleg_altai",
        description="Judged alignment of accepted norms to the seven HLEG requirements (M2).",
    )
    parser.add_argument(
        "--norms",
        type=Path,
        required=True,
        help="norms dump written by python -m tere4ai.extract_norms "
        "(data/graph_dumps/norms_<slug>.json)",
    )
    parser.add_argument(
        "--dump",
        type=Path,
        default=DEFAULT_DUMP_PATH,
        help=f"layer1 dump used to resolve norm source text (default {DEFAULT_DUMP_PATH})",
    )
    parser.add_argument(
        "--prompt-version", default="v1", help="prompt version for generator and judge"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list the norms that would be aligned, without model calls",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output path (default data/graph_dumps/alignments_<slug>.json)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="skip norm batches already present in the checkpoint file",
    )
    parser.add_argument(
        "--batch-size", type=int, default=20,
        help="norms per checkpointed batch (default 20)",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.norms.read_text(encoding="utf-8"))
    norms = payload.get("norms", [])
    build_id = payload.get("build", {}).get("build_id", "adhoc")

    layer1 = json.loads(args.dump.read_text(encoding="utf-8"))
    _attach_source_text(norms, layer1)

    if args.dry_run:
        eligible = [norm for norm in norms if norm.get("judge_verdict") == "accepted"]
        skipped = len(norms) - len(eligible)
        print(f"{len(eligible)} accepted norm(s) would be aligned ({skipped} skipped):")
        for norm in eligible:
            missing = "" if norm.get("source_text") else "  [NO SOURCE TEXT, would fail]"
            print(
                f"  {norm['norm_id']} ({norm['deontic_type']}: "
                f"{norm['action']} / {norm['object']}){missing}"
            )
        return 0

    slug = args.norms.stem.removeprefix("norms_")
    out_path = args.out or (
        REPO_ROOT / "data" / "graph_dumps" / f"alignments_{slug}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # fail fast at zero cost if the output path is unwritable (lesson of the
    # lost 2026-07-08 extraction run)
    out_path.touch()
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    batches: list[tuple[str, list[dict]]] = []
    for i in range(0, len(norms), args.batch_size):
        chunk = norms[i : i + args.batch_size]
        batches.append((f"batch:{i}:{chunk[0]['norm_id']}", chunk))

    done: set[str] = set()
    partials: list[dict] = []
    if args.resume and checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            done.add(entry["batch"])
            partials.append(entry["result"])
        print(f"resume: {len(done)} batch(es) already checkpointed")

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)
    hleg_nodes = build_hleg_nodes()

    with checkpoint_path.open("a", encoding="utf-8") as ckpt:
        for batch_key, chunk in batches:
            if batch_key in done:
                continue
            partial = align_norms(
                chunk, hleg_nodes, generator, judge,
                prompt_version=args.prompt_version, build_id=build_id,
            )
            ckpt.write(json.dumps({"batch": batch_key, "result": partial}) + "\n")
            ckpt.flush()
            partials.append(partial)
            print(f"  {batch_key}: {len(partial['assertions'])} assertions, "
                  f"verdicts {partial['stats'].get('verdicts', {})}", flush=True)

    result: dict = {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}
    for partial in partials:
        result["assertions"].extend(partial["assertions"])
        result["mapping_runs"].extend(partial["mapping_runs"])
        result["judge_runs"].extend(partial["judge_runs"])
        for key, value in partial["stats"].items():
            if isinstance(value, int):
                result["stats"][key] = result["stats"].get(key, 0) + value
            elif isinstance(value, list):
                result["stats"].setdefault(key, []).extend(value)
            elif isinstance(value, dict):
                bucket = result["stats"].setdefault(key, {})
                for k, v in value.items():
                    bucket[k] = bucket.get(k, 0) + v

    out_payload = {
        "build": {
            **payload.get("build", {}),
            "alignment_models": cfg.as_public_dict(),
            "alignment_prompt_version": args.prompt_version,
        },
        **result,
    }
    tmp_path = out_path.with_suffix(".writing.json")
    tmp_path.write_text(
        json.dumps(out_payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    tmp_path.replace(out_path)
    checkpoint_path.unlink(missing_ok=True)

    stats = result["stats"]
    print(f"wrote {out_path}")
    print(
        f"norms: {stats.get('norms_total', 0)} total, "
        f"{stats.get('norms_skipped_not_accepted', 0)} skipped (not accepted), "
        f"{stats.get('zero_alignment_norms', 0)} with zero alignments"
    )
    print(f"candidates: {stats.get('candidates', 0)}, verdicts: {stats.get('verdicts', {})}")
    if stats.get("mechanical_rejects"):
        print(f"mechanical quote-check rejects: {len(stats['mechanical_rejects'])}")
    if stats.get("norms_failed"):
        print(f"failed norms: {len(stats['norms_failed'])} (see stats in the output file)")
    if stats.get("invalid_candidates") or stats.get("invalid_assertions"):
        print(
            f"invalid candidates: {len(stats.get('invalid_candidates', []))}, "
            f"invalid assertions dropped: {len(stats.get('invalid_assertions', []))}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

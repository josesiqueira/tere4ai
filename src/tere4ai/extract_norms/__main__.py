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
    parts = []
    for node_id in node_ids:
        short = node_id.removeprefix("eu-ai-act:")
        parts.append(short.replace(":", "-"))
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

    cfg = load_model_config()
    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)
    result = extract_norms(
        dump, node_ids, generator, judge, prompt_version=args.prompt_version
    )

    out_path = REPO_ROOT / "data" / "graph_dumps" / f"norms_{_slug(node_ids)}.json"
    payload = {
        "build": {
            **dump.get("build", {}),
            "extraction_models": cfg.as_public_dict(),
            "prompt_version": args.prompt_version,
        },
        **result,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    stats = result["stats"]
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

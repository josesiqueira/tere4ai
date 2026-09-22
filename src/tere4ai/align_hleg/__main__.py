"""Build entry point: python -m tere4ai.align_hleg --norms data/graph_dumps/norms_<slug>.json

@implements: DEC-05, DEC-06 (partial: mapping judge), DEC-16 (partial: the L3.1 to L3.3 execution record)
@grounded_by: REF-24, REF-21, REF-10, REF-16, ADD-20

Runs the judged alignment pipeline over the accepted norms in the given
norms dump, against the seven HLEG requirement nodes, and writes
data/graph_dumps/alignments_<slug>.json. Norm source text is resolved from
the layer1 dump via each norm's source_node_id. Use --dry-run to list the
norms that would be aligned without calling any model. Every attempt writes
an execution record covering L3.1 to L3.3 into the build record store
(D-G20), with run ids on every checkpoint line and a validated resume.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.pipeline import align_norms
from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator
from tere4ai.extract_norms.pipeline import DEFAULT_DUMP_PATH, REPO_ROOT, load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    existing_artefact_digest,
    published_artefact_owner,
    relative_to_dump_dir,
    select_record,
)
from tere4ai.graph_store.checkpoints import CheckpointError, prepare_resume
from tere4ai.judge.config import load_model_config

ALIGN_PROMPT_KIND = "align_hleg"
JUDGE_PROMPT_KIND = "judge_alignment"
RESULT_KEYS = ("assertions", "mapping_runs", "judge_runs", "stats")


def _attach_source_text(norms: list[dict], layer1: dict) -> None:
    """Resolve each norm's source_text from its layer1 source node."""
    nodes = {node["id"]: node for node in layer1["nodes"]}
    for norm in norms:
        if norm.get("source_text"):
            continue
        node = nodes.get(norm.get("source_node_id", ""))
        if node is not None and node.get("text"):
            norm["source_text"] = node["text"]


def _sampling_of(client: object) -> str:
    """What the client actually sent (B74); "unknown" for a stub without the record."""
    return str(getattr(client, "sampling", "unknown"))


def _usage_of(client: object) -> dict:
    """Provider-reported token counts over this run; empty for a stub."""
    return dict(getattr(client, "usage", None) or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tere4ai.align_hleg",
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
    parser.add_argument("--dump-dir", type=Path, default=None,
                        help="where build records live (default: the output directory)")
    parser.add_argument("--record", default=None,
                        help="build record alias or id (default: the record that wrote the norms file, else the slug)")
    parser.add_argument("--accept-legacy-checkpoint", action="store_true",
                        help="inherit checkpoint lines written before build records existed (no run id)")
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
    out_path = args.out or (REPO_ROOT / "data" / "graph_dumps" / f"alignments_{slug}.json")
    dump_dir = args.dump_dir or out_path.parent
    out_path.parent.mkdir(parents=True, exist_ok=True)
    store = BuildRecordStore(dump_dir)
    # Nothing in a published build is edited in place (spec G Section 2):
    # refuse before any work when the output names a published artefact.
    existing = existing_artefact_digest(out_path)
    owner = published_artefact_owner(store, dump_dir, existing) if existing else None
    if owner:
        print(f"refusing to overwrite {out_path.name}: it is {owner}; pass --out with a new slug", file=sys.stderr)
        return 1
    # fail fast at zero cost if the output path is unwritable (lesson of the
    # lost 2026-07-08 extraction run)
    out_path.touch()
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    batches: list[tuple[str, list[dict]]] = []
    for i in range(0, len(norms), args.batch_size):
        chunk = norms[i : i + args.batch_size]
        batches.append((f"batch:{i}:{chunk[0]['norm_id']}", chunk))

    norms_digest = sha256_of_file(args.norms)
    layer1_digest = sha256_of_file(args.dump)
    inputs = [{"role": "norms", "file": relative_to_dump_dir(args.norms, dump_dir), "sha256": norms_digest},
              {"role": "layer1_dump", "file": relative_to_dump_dir(args.dump, dump_dir), "sha256": layer1_digest}]
    config = {"prompt_version": args.prompt_version, "batch_size": args.batch_size}
    ref = args.record or store.find_by_output_digest(norms_digest) or slug
    record_id, message = select_record(store, ref, payload.get("build", {}).get("build_id"), layer1_digest)
    if message and existing:
        print(f"refusing to overwrite {out_path.name}: {message}, and the file belongs to the record it continues; "
              "pass --out with a new slug", file=sys.stderr)
        return 1
    if message:
        print(message)
    # The models and prompt texts a resume must share with the run it
    # inherits from (D-G20): known before the checkpoint is judged.
    cfg = load_model_config()
    models = cfg.as_public_dict()
    prompts = {"generator": prompt_sha256(load_prompt(ALIGN_PROMPT_KIND, args.prompt_version)),
               "judge": prompt_sha256(load_prompt(JUDGE_PROMPT_KIND, args.prompt_version))}
    try:
        plan = prepare_resume(checkpoint_path, "batch", RESULT_KEYS, resume=args.resume,
                              accept_legacy=args.accept_legacy_checkpoint, store=store, record_id=record_id,
                              expected_config=config, expected_inputs=inputs, expected_models=models,
                              expected_prompt_sha256=prompts)
    except CheckpointError as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2
    if plan.inherited_keys:
        print(f"resume: {len(plan.inherited_keys)} batch(es) inherited from {plan.inherited_from}")

    generator = OpenAIGenerator(cfg)
    judge = AnthropicJudge(cfg)
    hleg_nodes = build_hleg_nodes()
    run_id = store.start_execution(
        record_id, command="align_hleg", covers_steps=["L3.1", "L3.2", "L3.3"],
        argv=list(sys.argv[1:] if argv is None else argv), inputs=inputs, config=config,
        expected_total=len(batches), work_unit="batches", checkpoint_file=relative_to_dump_dir(checkpoint_path, dump_dir),
        resumes_run_id=plan.resumes_run_id, inherited_keys=plan.inherited_keys, inherited_from=plan.inherited_from,
        models=models, prompt_sha256=prompts,
        sampling={"generator": _sampling_of(generator), "judge": _sampling_of(judge)},
    )

    partials: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
    completed: list[str] = []

    def usage() -> dict:
        return {"generator": _usage_of(generator), "judge": _usage_of(judge)}

    try:
        with checkpoint_path.open("a", encoding="utf-8") as ckpt:
            for batch_key, chunk in batches:
                if batch_key in plan.entries_by_key:
                    continue
                partial = align_norms(chunk, hleg_nodes, generator, judge,
                                      prompt_version=args.prompt_version, build_id=build_id)
                ckpt.write(json.dumps({"run_id": run_id, "batch": batch_key, "result": partial}) + "\n")
                ckpt.flush()
                partials.append(partial)
                completed.append(batch_key)
                store.heartbeat(record_id, run_id)
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

        # The norms file's own reference block (a materialised Layer 2) is
        # upstream provenance, kept under norms_reference: build.reference is
        # written only by materialisation of the alignments themselves, so a
        # copied marker never reads as a Layer 3 decision (gating, binding).
        upstream = dict(payload.get("build", {}))
        norms_reference = upstream.pop("reference", None)
        out_payload = {
            "build": {
                **upstream,
                "norms_reference": norms_reference,
                "alignment_models": cfg.as_public_dict(),
                "alignment_sampling": {"generator": _sampling_of(generator), "judge": _sampling_of(judge)},
                "alignment_usage": usage(),
                "alignment_input_sha256": norms_digest,
                "aligned_at": datetime.now(UTC).isoformat(),
                "alignment_prompt_version": args.prompt_version,
            },
            **result,
        }
        tmp_path = out_path.with_suffix(".writing.json")
        tmp_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp_path.replace(out_path)
        stats = result["stats"]
        store.finish_execution(
            record_id, run_id, status="done",
            outputs=[{"role": "alignments", "file": relative_to_dump_dir(out_path, dump_dir),
                     "sha256": sha256_of_file(out_path)}],
            # A count the stats do not hold is null, never zero (D-G25).
            counts={"norms_total": stats.get("norms_total"),
                    "norms_skipped_not_accepted": stats.get("norms_skipped_not_accepted"),
                    "zero_alignment_norms": stats.get("zero_alignment_norms"),
                    "candidates": stats.get("candidates"), "verdicts": stats.get("verdicts"),
                    "mechanical_rejects_count": (len(stats["mechanical_rejects"])
                                                 if isinstance(stats.get("mechanical_rejects"), list) else None)},
            usage=usage(), sampling=out_payload["build"]["alignment_sampling"], completed_keys=completed,
            work_failures={"nodes_failed": 0, "norms_failed": len(stats.get("norms_failed", []))},
        )
    except Exception as exc:  # noqa: BLE001 - recorded with what is known, then re-raised
        store.finish_execution(record_id, run_id, status="failed", usage=usage(), completed_keys=completed,
                               error=f"{type(exc).__name__}: {exc}")
        raise
    checkpoint_path.unlink(missing_ok=True)

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

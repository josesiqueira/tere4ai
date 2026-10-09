"""Build entry point: python -m tere4ai.extract_norms --nodes eu-ai-act:article-9

@implements: DEC-03, DEC-06 (partial: extraction judge only), DEC-16 (partial: the LAYER2_STEP1 and LAYER2_STEP2 execution record)
@implements: DEC-19
@implements: DEC-21
@implements: DEC-26
@implements: DEC-27
@grounded_by: REF-01, REF-11, REF-12, REF-13, REF-16, REF-24, REF-27, ADD-20

Runs the judged norm-extraction pipeline over the given Layer 1 node ids
(article ids expand to their paragraphs and points) and writes
data/graph_dumps/norms_<slug>.json. Use --dry-run to list the source units
without calling any model. Every attempt writes an execution record covering
LAYER2_STEP1 and LAYER2_STEP2 into the build record store (D-G20), with run ids on every
checkpoint line and a validated resume.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from tere4ai.act_parties import ACT_PARTIES_PATH
from tere4ai.extract_norms.actor_audit import (
    addressee_counts,
    addressee_report_lines,
    report_lines,
    section_2_checks,
)
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    AnthropicJudge,
    OpenAIGenerator,
    ProviderUnavailable,
    declared_sampling,
)
from tere4ai.extract_norms.pipeline import (
    DEFAULT_DUMP_PATH,
    DEFAULT_PROMPT_VERSION,
    REPO_ROOT,
    expand_source_units,
    extract_norms,
    load_prompt,
    prompt_sha256,
    writes_addressee,
)
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    Heartbeat,
    RecordError,
    choose_record,
    create_chosen_record,
    existing_artefact_digest,
    live_run_refusal,
    published_artefact_owner,
    relative_to_dump_dir,
    signals_as_interrupt,
)
from tere4ai.graph_store.checkpoints import CheckpointError, prepare_resume, resume_command
from tere4ai.judge.config import ConfigurationError, load_model_config

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


def _effort_of(client: object) -> str:
    """The effort the client applied (B84, spec F D-F22); "unknown" for a stub without the record."""
    return str(getattr(client, "effort", "unknown"))


def _usage_of(client: object) -> dict:
    """Provider-reported token counts over this run; empty for a stub."""
    return dict(getattr(client, "usage", None) or {})


def main(argv: list[str] | None = None) -> int:
    """Run the command with SIGTERM and SIGHUP raising KeyboardInterrupt, so a
    closed terminal ends the execution failed with its usage (final review A2 (a))."""
    with signals_as_interrupt():
        return _main(argv)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tere4ai.extract_norms",
        description="Judged norm extraction over Layer 1 source units (MILESTONE2).",
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
        "--prompt-version", default=DEFAULT_PROMPT_VERSION,
        help=f"prompt version for generator and judge (default {DEFAULT_PROMPT_VERSION})"
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
    store = BuildRecordStore(dump_dir)
    # Nothing in a published build is edited in place (spec G Section 2):
    # refuse before any work when the output names a published artefact.
    existing = existing_artefact_digest(out_path)
    owner = published_artefact_owner(store, dump_dir, existing) if existing else None
    if owner:
        print(f"refusing to overwrite {out_path.name}: it is {owner}; pass --out with a new slug", file=sys.stderr)
        return 1
    # fail fast at ZERO cost if the output path is unwritable (the 405-unit
    # core run of 2026-07-08 was lost to a too-long filename at the final write)
    out_path.touch()
    checkpoint_path = out_path.with_suffix(".checkpoint.jsonl")

    layer1_digest = sha256_of_file(args.dump)
    inputs = [{"role": "layer1_dump", "file": relative_to_dump_dir(args.dump, dump_dir),
               "sha256": layer1_digest}]
    # B145 (D-G80 (11), R76): the Act's parties the run read, by digest
    inputs.append({"role": "act_parties",
                   "file": os.path.relpath(ACT_PARTIES_PATH.resolve(), Path(dump_dir).resolve()),
                   "sha256": sha256_of_file(ACT_PARTIES_PATH)})
    config = {"prompt_version": args.prompt_version, "nodes": node_ids}
    # B79 item 10: the record is chosen here and created only after every
    # refusal below, so a refused run leaves no record and moves no alias
    choice = choose_record(store, args.record or out_path.stem.removeprefix("norms_"),
                           dump.get("build", {}).get("build_id"), layer1_digest)
    refusal = live_run_refusal(store, choice.record_id, "extract_norms") if choice.record_id else None
    if refusal:
        print(f"refusing to start: {refusal}", file=sys.stderr)
        return 2
    if choice.message and existing:
        print(f"refusing to overwrite {out_path.name}: {choice.message}, and the file belongs to the record it "
              "continues; pass --out with a new slug", file=sys.stderr)
        return 1
    # The models and prompt texts a resume must share with the run it
    # inherits from (D-G20): known before the checkpoint is judged.
    cfg = load_model_config()
    models = cfg.as_public_dict()
    prompts = {"generator": prompt_sha256(load_prompt(GENERATOR_PROMPT_KIND, args.prompt_version)),
               "judge": prompt_sha256(load_prompt(JUDGE_PROMPT_KIND, args.prompt_version))}
    try:
        plan = prepare_resume(checkpoint_path, "group", RESULT_KEYS, resume=args.resume,
                              accept_legacy=args.accept_legacy_checkpoint, store=store, record_id=choice.record_id,
                              expected_config=config, expected_inputs=inputs, expected_models=models,
                              expected_prompt_sha256=prompts)
    except CheckpointError as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2
    if plan.inherited_keys:
        print(f"resume: {len(plan.inherited_keys)} group(s) inherited from {plan.inherited_from}")

    # spec F D-F30: a terminal run with a checkpoint waits out an overload
    generator = OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)
    judge = AnthropicJudge(cfg, retry_policy=TERMINAL_POLICY)
    # B79 item 10: created only now, after every refusal and every build step
    # that can fail, so nothing before the run starts leaves a record
    record_id, message = create_chosen_record(store, choice)
    if message:
        print(message)
    run_argv = list(sys.argv[1:] if argv is None else argv)
    run_id = store.start_execution(
        record_id, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"],
        argv=run_argv, inputs=inputs, config=config,
        expected_total=len(node_ids), work_unit="groups",
        checkpoint_file=relative_to_dump_dir(checkpoint_path, dump_dir),
        resumes_run_id=plan.resumes_run_id, inherited_keys=plan.inherited_keys, inherited_from=plan.inherited_from,
        models=models, prompt_sha256=prompts,
        sampling=declared_sampling(generator, judge),
    )

    group_results: list[dict] = [plan.entries_by_key[k]["result"] for k in plan.inherited_keys]
    completed: list[str] = []

    def usage() -> dict:
        return {"generator": _usage_of(generator), "judge": _usage_of(judge)}

    def end_failed(error: str) -> None:
        # a record published under this run refuses the write too (B79 item
        # 15); the original error is the one reported
        try:
            store.finish_execution(record_id, run_id, status="failed", usage=usage(), completed_keys=completed,
                                   sampling=declared_sampling(generator, judge), error=error)
        except RecordError as record_exc:
            print(f"the failure could not be recorded: {record_exc}", file=sys.stderr)

    try:
        # one pipeline call per top-level node id, checkpointed immediately, so a
        # crash can never lose more than the group in flight; the heartbeat
        # beats on a clock while the paid calls run (B79 item 4)
        with Heartbeat(store, record_id, run_id), checkpoint_path.open("a", encoding="utf-8") as ckpt:
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
                # the usage so far rides on the per-unit beat: a SIGKILL loses at
                # most the unit in flight (final review A2 (b))
                store.heartbeat(record_id, run_id, usage=usage())
                verdicts = result["stats"].get("verdicts", {})
                print(f"  {group_id}: {len(result['norms'])} norms, verdicts {verdicts}",
                      flush=True)

        merged: dict = {"norms": [], "judge_runs": [], "stats": {
            "source_units": 0, "candidates": 0, "verdicts": {},
            "nodes_failed": [], "invalid_norms": [],
            # B124 (spec G D-G62): a group written before B124 carries no count
            "without_target_system_category": 0,
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
            merged["stats"]["without_target_system_category"] += stats.get("without_target_system_category", 0)
            # B65 ruling 54: summed when the groups count it (prompt v2 on)
            if "untyped_in_scope" in stats:
                merged["stats"]["untyped_in_scope"] = (
                    merged["stats"].get("untyped_in_scope", 0) + stats["untyped_in_scope"]
                )

        # B144 (spec G D-G76 (7)): over every group of the run, inherited ones included
        section_2 = section_2_checks(merged["norms"], dump)
        addressees = addressee_counts(merged["norms"])

        generator_sampling = declared_sampling(generator, judge)
        payload = {
            # B145 (D-G80 (21)): a v5 run writes norms schema version 2
            **({"norms_schema_version": 2} if writes_addressee(args.prompt_version) else {}),
            "build": {
                **dump.get("build", {}),
                "extraction_models": cfg.as_public_dict(),
                "extraction_sampling": {"generator": generator_sampling["generator"],
                                       "judge": generator_sampling["judge"]},
                "extraction_effort": {"generator": _effort_of(generator), "judge": _effort_of(judge)},
                # Spec F D-F22, D-F29: the declared temperatures beside the efforts
                "extraction_temperature": {"generator": generator_sampling["generator_temperature"],
                                           "judge": generator_sampling["judge_temperature"]},
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
            outputs=[{"role": "norms", "file": relative_to_dump_dir(out_path, dump_dir),
                     "sha256": sha256_of_file(out_path)}],
            counts={"source_units": stats["source_units"], "candidates": stats["candidates"],
                    "verdicts": stats["verdicts"], "invalid_norms_count": len(stats["invalid_norms"]),
                    "without_target_system_category": stats["without_target_system_category"],
                    **section_2,
                    **addressees,
                    **({"untyped_in_scope": stats["untyped_in_scope"]} if "untyped_in_scope" in stats else {})},
            usage=usage(),
            sampling=declared_sampling(generator, judge),
            completed_keys=completed,
            work_failures={"nodes_failed": len(stats["nodes_failed"]), "norms_failed": 0},
        )
    except ProviderUnavailable as exc:
        # spec F D-F30: the terminal policy waited out five pauses; the
        # execution ends failed with the reason, the checkpoint stays, and the
        # command that continues it is printed
        end_failed(str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        print(f"the checkpoint {checkpoint_path.name} is kept ({len(plan.inherited_keys) + len(completed)} of "
              f"{len(node_ids)} groups done); continue with:", file=sys.stderr)
        print(f"  {resume_command('.venv/bin/python -m tere4ai.extract_norms', run_argv)}", file=sys.stderr)
        return 3
    except ConfigurationError as exc:
        # spec F D-F29: a declared parameter the provider refused stops the run
        end_failed(str(exc))
        print(f"stopped: {exc}", file=sys.stderr)
        return 4
    except BaseException as exc:  # an interrupt too (B79 item 22): the execution never stays running
        end_failed(f"{type(exc).__name__}: {exc}")
        raise
    checkpoint_path.unlink(missing_ok=True)

    print(f"wrote {out_path}")
    print(f"source units: {stats['source_units']}, candidates: {stats['candidates']}")
    print(f"verdicts: {stats['verdicts']}")
    for line in report_lines(section_2):
        print(line)
    for line in addressee_report_lines(addressees):
        print(line)
    if stats["nodes_failed"]:
        print(f"failed nodes: {len(stats['nodes_failed'])} (see stats in the output file)")
    if stats["invalid_norms"]:
        print(f"invalid norms dropped: {len(stats['invalid_norms'])}")
    if stats.get("untyped_in_scope"):
        print(f"in-scope norms without a requirement type: {stats['untyped_in_scope']}")
    if stats["without_target_system_category"]:
        print("norms without a target_system_category (source unit outside the rule table): "
              f"{stats['without_target_system_category']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Publish judged or adjudicated Layer 2/3 results into Neo4j, gated by Section 13.

@implements: DEC-10 (partial: publication gating and reproducibility chain for Layer 2/3)
@implements: DEC-16 (partial: publication evidence, per-gate outcomes, Neo4j target state, D-G21, D-G27)
@grounded_by: REF-27, ADD-20

Usage:
  .venv/bin/python scripts/publish_layer23.py --norms data/graph_dumps/norms_core.json
  .venv/bin/python scripts/publish_layer23.py --norms ... --alignments data/graph_dumps/alignments_core.json
  .venv/bin/python scripts/publish_layer23.py --norms <norms_x.reference.json> --alignments ... \
      --manifest <freeze manifest in the dump dir> [--manifest ...]

Flow, recorded as one execution of the build record that produced --norms
(or --record): evidence first (a file carrying decisions must carry the
reference block materialise_reference.py stamped, the alignments must have
been computed over this exact norms file, and every reference block is
bound to exactly one --manifest), then the critical gates G1 to G6, then
the load into Neo4j and the post-load gates P1 to P5. Only after the
post-load gates pass are the chain record, the publication manifest and
BUILD_CHAIN_CURRENT.txt written and the record frozen; activation is a
separate step (scripts/activate_build.py). Decisions are never applied
here: materialise them first. Connection: NEO4J_URI / NEO4J_USER /
NEO4J_PASSWORD env vars, defaulting to the local v2 container
(bolt://localhost:7688, neo4j); only scheme, host and port are recorded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import ExitStack, nullcontext
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes  # noqa: E402
from tere4ai.align_hleg.hleg_subtopics import build_hleg_subtopics  # noqa: E402
from tere4ai.graph_store.build_chain import (  # noqa: E402
    build_chain,
    chained_build_id,
    sha256_of_file,
)
from tere4ai.graph_store.build_record import (  # noqa: E402
    HEARTBEAT_EXPIRY_SECONDS,
    BuildRecordStore,
    Heartbeat,
    NumberingError,
    atomic_write_json,
    gate_entries,
    select_record,
    signals_as_interrupt,
)
from tere4ai.graph_store.layer23 import alignments_to_graph, norms_to_graph  # noqa: E402
from tere4ai.graph_store.publication import (  # noqa: E402
    CURRENT_POINTER_FILENAME,
    GATES,
    LABEL_NEEDS_CORE_NODES,
    POSTLOAD_GATES,
    PUBLICATIONS_DIRNAME,
    PublicationError,
    bind_manifests,
    check_schema,
    gating_of,
    manifest_path,
    public_uri,
    publication_manifest,
    set_target_state,
    whole_build_label,
    write_current_pointer,
)
from tere4ai.graph_store.store import GraphStore  # noqa: E402
from tere4ai.review_queue.materialize import (  # noqa: E402
    MaterializeError,
    already_materialised,
    verify_freeze_manifest,
)
from tere4ai.validate_graph.gates import validate_build  # noqa: E402
from tere4ai.validate_graph.postload import validate_postload  # noqa: E402

MANIFEST_REF_KEYS = ("campaign_id", "freeze_id", "campaign_type", "stage", "decisions_sha256", "layer")


def _manifest_refs(bound: list[dict]) -> list[dict]:
    return [{k: m[k] for k in MANIFEST_REF_KEYS} for m in bound]


def _reference(payload: dict | None) -> dict | None:
    ref = (payload or {}).get("build", {}).get("reference")
    return ref if isinstance(ref, dict) else None


def _core_nodes(dump_dir: Path) -> list[str] | None:
    core_path = dump_dir / "core_nodes.txt"
    if not core_path.is_file():
        return None
    return [n.strip() for n in core_path.read_text(encoding="utf-8").split(",") if n.strip()]


def _continues_the_same_norms(candidate: dict, published_record_id: str, norms_digest: str) -> bool:
    """Whether the open record select_record's first branch reused (final
    re-review B98, New Breakage 1: it checks only that the aliased record is
    open and on the same Layer 1) is a safe continuation of this publish: it
    descends from the record being published, and none of its recorded norms
    outputs differs from the norms file now being published. A record that
    fails either check may hold a newer extraction under the same slug, so
    the republish must make its own descendant instead of landing in it."""
    if candidate["parent_record_id"] != published_record_id:
        return False
    return all(out.get("sha256") == norms_digest for ex in candidate["executions"]
              for out in ex.get("outputs", []) if out.get("role") == "norms")


def _by(publisher: dict) -> str:
    """' (Build N) by record R', or ' by record R' for a publication made before build numbers."""
    number = publisher["publication"].get("build_number")
    return f"{f' (Build {number})' if number is not None else ''} by record {publisher['record_id']}"


def _already_published(dump_dir: Path, chain_id: str, publisher: dict | None) -> str | None:
    """The refusal for inputs already published as chain_id, or None. Each
    case names the step that helps (spec G D-G50, B94a final review B-P2-2):
    activation needs the manifest, the manifest repair needs the chain record
    and the frozen record, and a chain is never published a second time."""
    repair = f"scripts/write_publication_manifest.py {chain_id} --dump-dir {dump_dir}"
    chain_name = f"build_chain_{chain_id}.json"
    if manifest_path(dump_dir, chain_id).exists():
        return f"already published as chain {chain_id}; activate it with scripts/activate_build.py {chain_id}"
    if (dump_dir / chain_name).exists() and publisher is not None:
        number = publisher["publication"].get("build_number")
        return (f"chain {chain_id} is published (record {publisher['record_id']}"
                f"{f', Build {number}' if number is not None else ''}) but its publication manifest is missing: "
                f"write it with {repair}; never publish the same inputs again")
    if (dump_dir / chain_name).exists():
        return (f"already published as chain {chain_id}: {chain_name} exists, but no publication manifest and no "
                "build record holds its publication, so it cannot be activated; nothing is published")
    if publisher is not None:
        # review I2: a record holds the publication with both files gone
        return (f"already published as chain {chain_id}{_by(publisher)}; both its chain record and its "
                "publication manifest are missing: write them from the record, never publish the same inputs again")
    return None


def _evidence(norms_payload: dict, alignments_payload: dict | None, norms_digest: str,
              manifest_paths: list[Path]) -> tuple[str | None, dict, list[dict]]:
    """The evidence steps (1) to (3) (D-G27): the refusal message or None, the
    gating and the bound manifests. Reads files only and writes nothing, so it
    can run before a published record continues as a descendant (B98 seat B
    P2-1)."""
    # (1) Evidence before any gate (D-G27).
    for name, payload in (("norms", norms_payload), ("alignments", alignments_payload)):
        if payload is not None and already_materialised(payload) and not payload.get("build", {}).get("reference"):
            return (f"NOT published: {name} carry decisions but no reference block; "
                    "materialise from the pristine dump"), {}, []
    gating = gating_of(norms_payload, alignments_payload)
    # (2) The alignments were computed over this exact norms file.
    if alignments_payload is not None:
        recorded = alignments_payload.get("build", {}).get("alignment_input_sha256")
        if recorded is None and gating["layer2"] == "human":
            return ("NOT published: alignments carry no input digest; "
                    "re-run the alignment command over the reference norms"), gating, []
        if recorded is not None and recorded != norms_digest:
            return "NOT published: alignments were computed over a different norms file than --norms", gating, []
    # (3) Every reference block bound to exactly one freeze manifest.
    # Each file's own reference block: the alignments' only when it is
    # of kind alignments (an older file may carry a copied norms marker).
    references = [ref for ref, kind in ((_reference(norms_payload), "norms"), (_reference(alignments_payload), "alignments"))
                  if ref is not None and ref.get("kind") == kind]
    try:
        manifests = [verify_freeze_manifest(json.loads(m.read_text(encoding="utf-8")), None,
                                            expected_pinned_build_id=None) for m in manifest_paths]
        bound = bind_manifests(references, manifests)
    except (MaterializeError, PublicationError, OSError, json.JSONDecodeError) as exc:
        return f"NOT published: {exc}", gating, []
    return None, gating, bound


def main(argv: list[str] | None = None) -> int:
    """Run the command with SIGTERM and SIGHUP raising KeyboardInterrupt, so a
    closed terminal ends the execution failed with its usage (final review A2 (a))."""
    with signals_as_interrupt():
        return _main(argv)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--norms", type=Path, required=True)
    parser.add_argument("--alignments", type=Path, default=None)
    parser.add_argument("--dump", type=Path, default=ROOT / "data" / "graph_dumps" / "layer1.json")
    parser.add_argument("--dump-dir", type=Path, default=None,
                        help="where records, the chain record and the manifests live (default: the norms file's directory)")
    parser.add_argument("--manifest", type=Path, action="append", default=[],
                        help="a freeze manifest, copied into the dump dir, per reference block of the inputs")
    parser.add_argument("--record", default=None, help="build record id or alias (default: the record that produced --norms)")
    parser.add_argument("--gates-only", action="store_true", help="validate, do not load into Neo4j")
    parser.add_argument("--decisions", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if args.decisions is not None:
        print("--decisions is retired: decisions are materialised by scripts/materialize_reference.py; "
              "publish takes the reference file as --norms", file=sys.stderr)
        return 2

    dump_dir = Path(args.dump_dir or args.norms.parent)
    # Every --manifest must be a file in the dump dir, checked before any
    # record is resolved (B97 item 3): a typo'd or misplaced manifest used to
    # skip the early double-publish check below, so a published record
    # continued as a descendant and the alias moved before the evidence step
    # refused. Nothing is recorded: no build was touched.
    missing = [str(m) for m in args.manifest if not m.is_file()]
    if missing:
        print(f"NOT published: freeze manifest not found: {', '.join(missing)}", file=sys.stderr)
        return 1
    for m in args.manifest:
        if m.resolve().parent != dump_dir.resolve():
            print(f"NOT published: copy the freeze manifest {m.name} into {dump_dir} first; "
                  "publication names its inputs by file under that directory", file=sys.stderr)
            return 1
    layer1 = json.loads(args.dump.read_text(encoding="utf-8"))
    norms_payload = json.loads(args.norms.read_text(encoding="utf-8"))
    alignments_payload = json.loads(args.alignments.read_text(encoding="utf-8")) if args.alignments else None
    norms_digest = sha256_of_file(args.norms)

    store = BuildRecordStore(dump_dir)
    ref = args.record or store.find_by_output_digest(norms_digest)
    record_id = store.resolve(ref) if ref is not None else None
    if record_id is None:
        print("NOT published: no build record produced this norms file; pass --record", file=sys.stderr)
        return 1
    if not args.gates_only:
        # The chain id is a function of the input digests (Section 13): identical
        # inputs published already are refused here, before a published record
        # continues as a descendant and the alias moves to it (final review A6).
        # Every manifest exists here (checked above, B97 item 3).
        early_chain = build_chain(args.dump, args.norms, alignments_path=args.alignments,
                                  manifest_paths=args.manifest or None)
        # A record that holds this chain's publication makes it published even
        # when its chain record or manifest was lost or removed (spec G D-G50,
        # review I2): a second publication would give one chain two numbers.
        refusal = _already_published(dump_dir, early_chain["chain_id"], store.publisher_of(early_chain["chain_id"]))
        if refusal is not None:
            print(refusal, file=sys.stderr)
            return 1
        # A build number must be issuable before any record is touched (spec G
        # D-G50, review I1): the check reads files only, like the evidence
        # steps, so a refusal leaves the alias and every record as they are.
        try:
            store.next_build_number()
        except NumberingError as exc:
            print(f"NOT published: {exc}", file=sys.stderr)
            return 1
    unrecorded = False
    evidence: tuple[str | None, dict, list[dict]] | None = None
    if store.is_frozen(record_id):
        parent = store.read(record_id)
        if args.gates_only:
            # A gates-only check of a published record (B97 item 2; the
            # restore runbook runs one) writes nothing into the build, so it
            # records nothing: the frozen record takes no execution (D-G20)
            # and a descendant holding only a P.1 check would take the alias
            # from the published record.
            unrecorded = True
            print(f"record {record_id} is published as {parent['publication']['chain_id']}; checking the gates "
                  "only: nothing is recorded, no descendant is made and the alias stays")
        else:
            # The evidence steps read files only: a refusal there comes before
            # a descendant is made, so the published record keeps the alias
            # and nothing is recorded (B98 seat B P2-1).
            evidence = _evidence(norms_payload, alignments_payload, norms_digest, args.manifest)
            if evidence[0] is not None:
                print(f"{evidence[0]} (record {record_id} is published as {parent['publication']['chain_id']}; "
                      "nothing is recorded, no descendant is made and the alias stays)", file=sys.stderr)
                return 1
            # A published record is frozen (D-G20): a second publication of the
            # same inputs continues as a descendant, never overwrites history.
            # An open descendant of an earlier refused attempt is reused, so a
            # retry leaves no orphan record (B98 seat B P2-1).
            alias = parent["aliases"][0]
            record_id, message = select_record(store, alias, parent["base_build_id"], parent["layer1_digest"])
            if message is None and not _continues_the_same_norms(store.read(record_id), parent["record_id"],
                                                                  norms_digest):
                # select_record's first branch reused whatever open record the
                # alias names; a republish must not land in one that holds a
                # different norms extraction under the same slug (final
                # re-review B98, New Breakage 1). Make a new descendant.
                record_id = store.create_record(alias, parent["base_build_id"], parent["layer1_digest"],
                                                parent_record_id=parent["record_id"])
                message = (f"record {parent['record_id']} is published as {parent['publication']['chain_id']}; "
                          f"continuing as descendant {record_id}")
            print(message or f"record {parent['record_id']} is published as {parent['publication']['chain_id']}; "
                             f"continuing in open record {record_id}, which the alias {alias} names")
    # A record is published only when no other execution of it is live
    # (B79 item 15): refused here, before any gate or load, so Neo4j never
    # holds a build whose record another run is still writing.
    live = store.live_executions(record_id)
    if live:
        named = ", ".join(f"{ex['run_id']} ({ex['command']})" for ex in live)
        print(f"NOT published: record {record_id} has a live running execution: {named}; "
              f"wait for it to end or stop it (a killed run stops blocking {HEARTBEAT_EXPIRY_SECONDS} s after its "
              "last heartbeat)",
              file=sys.stderr)
        return 1
    inputs = [{"role": "layer1_dump", "file": args.dump.name, "sha256": sha256_of_file(args.dump)},
              {"role": "norms", "file": args.norms.name, "sha256": norms_digest}]
    if args.alignments:
        inputs.append({"role": "alignments", "file": args.alignments.name, "sha256": sha256_of_file(args.alignments)})
    for m in args.manifest:
        inputs.append({"role": "freeze_manifest", "file": m.name, "sha256": sha256_of_file(m)})
    steps = ["P.1"] if args.gates_only else ["P.1", "P.2"]
    run_id = None if unrecorded else store.start_execution(
        record_id, command="publish_layer23", covers_steps=steps, argv=raw_argv, inputs=inputs,
        config={"gates_only": args.gates_only}, expected_total=None, work_unit=None, checkpoint_file=None)

    finished = False
    gates: list[dict] = []
    uri = public_uri(os.environ.get("NEO4J_URI", "bolt://localhost:7688"))
    build_id: str | None = None
    loading = False
    driver = None
    written: list[str] = []
    chain_unpublished: Path | None = None
    # The numbering lock (spec G D-G50) is entered at step (7) and released
    # in the finally below, after the last write.
    numbering = ExitStack()
    build_number: int | None = None
    counter_note: str | None = None
    frozen = False

    def finish(status: str, *, error: str | None = None, **fields) -> None:
        nonlocal finished
        if run_id is not None:  # an unrecorded gates-only check has no execution (B97 item 2)
            store.finish_execution(record_id, run_id, status=status, error=error, **fields)
        finished = True

    def fail(message: str, recorded_gates: list[dict] | None = None) -> int:
        print(message, file=sys.stderr)
        finish("failed", gates=recorded_gates or [], error=message)
        return 1

    # The publish execution beats while it runs (B79 item 15): gates plus the
    # load can outlast the heartbeat expiry, and a second publish of the same
    # record must still see this one live. The same store object beats, so
    # its beats stay allowed after it writes the publication.
    with Heartbeat(store, record_id, run_id) if run_id is not None else nullcontext():
        try:
            # (1) to (3) Evidence before any gate (D-G27); taken before the
            # descendant was made when the record is published.
            refusal, gating, bound = evidence or _evidence(norms_payload, alignments_payload, norms_digest,
                                                           args.manifest)
            if refusal is not None:
                return fail(refusal)

            # (4) The critical gates, one recorded outcome per gate.
            norms = norms_payload.get("norms", [])
            assertions = alignments_payload.get("assertions", []) if alignments_payload else None
            report = validate_build(layer1, norms=norms, alignments=assertions)
            gates = gate_entries(report.failures, GATES, report.stats)
            print(f"gates: {'PASS' if report.passed else 'FAIL'} | stats {report.stats}")
            if not report.passed:
                for failure in report.failures[:20]:
                    print(f"  GATE FAIL {failure}", file=sys.stderr)
                return fail("NOT published: critical validation failed", gates)
            accepted = sum(1 for n in norms if n.get("judge_verdict") == "accepted")
            print(f"norms: {len(norms)} total, {accepted} judge-accepted")
            if assertions is not None:
                acc_a = sum(1 for a in assertions if a.get("judge_verdict") == "accepted")
                print(f"assertions: {len(assertions)} total, {acc_a} judge-accepted")
            # (5) Gates only: step P.1, nothing published.
            if args.gates_only:
                finish("done", gates=gates)
                return 0

            # (6) Load, then the post-load gates; the target state says what Neo4j holds.
            from neo4j import GraphDatabase

            # Reproducibility chain (Section 13): the build_id stamped on every
            # published node and edge embeds a digest of the exact input files,
            # freeze manifests included.
            chain = build_chain(args.dump, args.norms, alignments_path=args.alignments,
                                manifest_paths=args.manifest or None)
            chain_path = dump_dir / f"build_chain_{chain['chain_id']}.json"
            # The chain id is a function of the input digests: identical inputs
            # were published already, and published history is never rewritten
            # (D-G20).
            refusal = _already_published(dump_dir, chain["chain_id"], store.publisher_of(chain["chain_id"]))
            if refusal is not None:
                return fail(refusal, gates)
            base_build_id = norms_payload.get("build", {}).get("build_id", "layer2-adhoc")
            build_id = chained_build_id(base_build_id, chain)
            graph = norms_to_graph(norms_payload, build_id=build_id)
            if alignments_payload is not None:
                g3 = alignments_to_graph(alignments_payload, build_hleg_nodes(), build_id=build_id)
                graph["nodes"].extend(g3["nodes"])
                graph["edges"].extend(g3["edges"])
                # Deterministic HLEG subtopic targets (DEC-05 partial); skipped
                # heading candidates are printed, never silently dropped.
                subtopics = build_hleg_subtopics(build_id=build_id)
                graph["nodes"].extend(subtopics["nodes"])
                graph["edges"].extend(subtopics["edges"])
                print(f"hleg subtopics: {len(subtopics['nodes'])} nodes, {len(subtopics['skipped'])} skipped heading candidates")
                for item in subtopics["skipped"]:
                    print(f"  subtopic candidate skipped ({item['reason']}): {item['heading_candidate']!r}")
            build = norms_payload.get("build", {})
            pseudo_dump = {"build": {"build_id": build_id, "built_at": build.get("built_at", ""),
                                     "tere4ai_version": build.get("tere4ai_version", ""),
                                     "snapshots": build.get("snapshots", []), "input_checksums": chain["inputs"]},
                           "nodes": graph["nodes"], "edges": graph["edges"]}

            set_target_state(dump_dir, state="loading", build_id=build_id, uri=uri, reason=None)
            loading = True
            driver = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7688"),
                                          auth=(os.environ.get("NEO4J_USER", "neo4j"),
                                                os.environ.get("NEO4J_PASSWORD", "change_me")))
            counts = GraphStore().load_dump(pseudo_dump, driver)
            nodes = sum(v for k, v in counts.items() if k.startswith("node:"))
            edges = sum(v for k, v in counts.items() if k.startswith("edge:"))
            print(f"published to {uri}: {nodes} nodes, {edges} edges")
            for k in sorted(counts):
                print(f"  {k}: {counts[k]}")
            postload = validate_postload(driver, build_id=build_id, expected_norms=len(norms),
                                         expected_assertions=len(assertions) if assertions is not None else None)
            postload_gates = gate_entries(postload.failures, POSTLOAD_GATES, postload.stats)
            print(f"post-load gates: {'PASS' if postload.passed else 'FAIL'} | {postload.stats}")
            if not postload.passed:
                for failure in postload.failures:
                    print(f"  POST-LOAD FAIL {failure}", file=sys.stderr)
                reason = "; ".join(postload.failures)
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=reason)
                loading = False
                return fail("published data FAILED post-load validation: " + reason, gates + postload_gates)

            # (7) Only now does the build exist as a published one (D-G21).
            core_nodes = _core_nodes(dump_dir)
            if core_nodes is None and gating == {"layer2": "human", "layer3": "human"}:
                print(f"label withheld: {LABEL_NEEDS_CORE_NODES} ({dump_dir})")
            # The build number (spec G D-G50): reserved under the numbering
            # lock, held until the last write, and the publication is dated
            # under the same lock, so number order is publication order.
            try:
                build_number = numbering.enter_context(store.reserve_build_number())
            except NumberingError as exc:
                reason = str(exc)
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=reason)
                loading = False
                return fail(f"NOT published: {reason}", gates + postload_gates)
            # The "already published" checks again, now under the numbering
            # lock that every writer of a chain record, a manifest and a number
            # holds (spec G D-G50, B94a final review B-P2-1): another record
            # may have published the same inputs while this run loaded and
            # gated them, and a chain gets one number. Nothing is written yet,
            # so no number is used.
            holder = store.publisher_of(chain["chain_id"])
            if holder is not None or chain_path.exists() or manifest_path(dump_dir, chain["chain_id"]).exists():
                reason = (f"already published as chain {chain['chain_id']}{_by(holder) if holder else ''} while this "
                          f"run loaded it; this run publishes nothing")
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=reason)
                loading = False
                return fail(reason, gates + postload_gates)
            publication = {
                "chain_id": chain["chain_id"], "build_id": build_id, "published_at": datetime.now(UTC).isoformat(),
                "gating": gating, "label": whole_build_label(gating, bound, core_nodes), "gates": gates,
                "postload_gates": postload_gates, "manifests": _manifest_refs(bound), "build_number": build_number,
            }
            chain_record = {**publication, **chain, "record_id": record_id}
            # Everything is validated before the target is declared available and
            # before the first write, so a schema failure leaves no publication
            # artefact behind and Neo4j marked unavailable, never available.
            try:
                check_schema("publication", publication)
                manifest = publication_manifest(publication, record_id=record_id, inputs=chain["inputs"],
                                                files={"layer1_dump": args.dump.name, "norms": args.norms.name,
                                                       "alignments": args.alignments.name if args.alignments else None})
            except PublicationError as exc:
                reason = f"the publication does not validate: {exc}"
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=reason)
                loading = False
                return fail(f"NOT published: {reason}", gates + postload_gates)
            # an execution that started during the gates or the load blocks the
            # publication before Neo4j is declared available (B79 item 15)
            late = [ex for ex in store.live_executions(record_id) if ex["run_id"] != run_id]
            if late:
                named = ", ".join(f"{ex['run_id']} ({ex['command']})" for ex in late)
                reason = f"an execution of record {record_id} became live after the first check: {named}"
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=reason)
                loading = False
                return fail(f"NOT published: {reason}", gates + postload_gates)
            set_target_state(dump_dir, state="available", build_id=build_id, uri=uri, reason=None)
            # Write order: the chain record, the record's publication block, the
            # publication manifest (activation consumes it, so it goes last and a
            # partial publication can never be activated), then the pointer.
            atomic_write_json(chain_path, chain_record)
            written.append(chain_path.name)
            chain_unpublished = chain_path
            # set_publication checks a third time under the record lock; loading
            # stays true until it returns, so a refusal there marks Neo4j
            # unavailable in the except below (B79 item 15, review fix C2).
            store.set_publication(record_id, publication, run_id=run_id)
            chain_unpublished = None
            loading = False
            frozen = True
            written.append(f"record {record_id} publication block")
            # The counter follows the frozen record at once (spec G D-G50,
            # review M2), so it is never behind a number a record holds.
            counter_note = store.record_build_number(build_number)
            mpath = manifest_path(dump_dir, chain["chain_id"])
            mpath.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(mpath, manifest)
            written.append(f"{PUBLICATIONS_DIRNAME}/{mpath.name}")
            write_current_pointer(dump_dir, chain["chain_id"])
            written.append(CURRENT_POINTER_FILENAME)
            finish("done", gates=gates + postload_gates,
                   outputs=[{"role": "build_chain", "file": chain_path.name, "sha256": sha256_of_file(chain_path)}],
                   counts={"nodes": nodes, "edges": edges})
        except BaseException as exc:  # an interrupt too: the target never stays loading, the execution never running
            error = f"{type(exc).__name__}: {exc}"
            if chain_unpublished is not None:
                # The interrupt may land after set_publication returned and
                # before chain_unpublished was cleared (B94a final review
                # A-M1): the record, read here, says whether it is frozen.
                try:
                    published: bool | None = store.read(record_id)["publication"] is not None
                except Exception:  # an unreadable record: the chain record is kept
                    published = None
                if published is False:
                    # set_publication did not freeze the record (final review
                    # F2): this run's chain file would make the next publish
                    # read "already published", so it goes.
                    chain_unpublished.unlink(missing_ok=True)
                    written.remove(chain_unpublished.name)
                elif published:
                    frozen = True
                    written.append(f"record {record_id} publication block")
                    counter_note = store.record_build_number(build_number)
                else:
                    error += (f"; record {record_id} could not be read to tell whether it is published, so "
                              f"{chain_unpublished.name} is kept: remove it only after the record shows no publication")
            if frozen:
                # The record is published and frozen with its number (spec G
                # D-G50, review I2): removing the chain record would let the
                # same inputs take a second number, so it is never offered.
                # The message goes to the terminal too (final review B-P2-2)
                # and names what is not written and the command that writes it.
                missing = [name for name in (f"{PUBLICATIONS_DIRNAME}/{chain['chain_id']}.json",
                                             CURRENT_POINTER_FILENAME) if name not in written]
                error += (f"; record {record_id} is published as Build {build_number}, chain {chain['chain_id']}; "
                          f"already written: {', '.join(written)}")
                if missing:
                    error += (f"; not written: {', '.join(missing)}; write {'them' if len(missing) > 1 else 'it'} "
                              f"with scripts/write_publication_manifest.py {chain['chain_id']} --dump-dir {dump_dir} "
                              "--pointer")
                error += "; never remove the chain record"
                if counter_note:
                    error += f"; {counter_note}"
                print(error, file=sys.stderr)
            elif written:
                error += f"; already written, clean up by hand: {', '.join(written)}"
            if loading:
                set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=error)
            if not finished:
                finish("failed", gates=gates, error=error)
            raise
        finally:
            numbering.close()
            if driver is not None:
                driver.close()
    if counter_note:
        print(counter_note, file=sys.stderr)
    print(f"published Build {build_number}: {build_id}, record {record_id}, published_at {publication['published_at']}")
    print(f"build chain: {build_id} ({len(chain['inputs'])} inputs) -> {chain_path.name}; label {publication['label']}")
    print(f"activate with: scripts/activate_build.py {chain['chain_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

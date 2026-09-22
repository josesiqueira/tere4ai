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
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes  # noqa: E402
from tere4ai.align_hleg_altai.hleg_subtopics import build_hleg_subtopics  # noqa: E402
from tere4ai.graph_store.build_chain import (  # noqa: E402
    build_chain,
    chained_build_id,
    sha256_of_file,
)
from tere4ai.graph_store.build_record import BuildRecordStore, gate_entries  # noqa: E402
from tere4ai.graph_store.layer23 import alignments_to_graph, norms_to_graph  # noqa: E402
from tere4ai.graph_store.publication import (  # noqa: E402
    GATES,
    POSTLOAD_GATES,
    PublicationError,
    bind_manifests,
    gating_of,
    public_uri,
    set_target_state,
    whole_build_label,
    write_publication_manifest,
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


def _core_nodes(dump_dir: Path) -> list[str] | None:
    core_path = dump_dir / "core_nodes.txt"
    if not core_path.is_file():
        return None
    return [n.strip() for n in core_path.read_text(encoding="utf-8").split(",") if n.strip()]


def main(argv: list[str] | None = None) -> int:
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
    if store.is_frozen(record_id):
        # A published record is frozen (D-G20): a second publication of the
        # same inputs continues as a descendant, never overwrites history.
        parent = store.read(record_id)
        record_id = store.create_record(parent["aliases"][0], parent["base_build_id"], parent["layer1_digest"],
                                        parent_record_id=parent["record_id"])
        print(f"record {parent['record_id']} is published as {parent['publication']['chain_id']}; "
              f"continuing as descendant {record_id}")
    inputs = [{"role": "layer1_dump", "file": args.dump.name, "sha256": sha256_of_file(args.dump)},
              {"role": "norms", "file": args.norms.name, "sha256": norms_digest}]
    if args.alignments:
        inputs.append({"role": "alignments", "file": args.alignments.name, "sha256": sha256_of_file(args.alignments)})
    for m in args.manifest:
        if m.is_file():
            inputs.append({"role": "freeze_manifest", "file": m.name, "sha256": sha256_of_file(m)})
    steps = ["P.1"] if args.gates_only else ["P.1", "P.2"]
    run_id = store.start_execution(record_id, command="publish_layer23", covers_steps=steps, argv=raw_argv,
                                   inputs=inputs, config={"gates_only": args.gates_only}, expected_total=None,
                                   work_unit=None, checkpoint_file=None)

    finished = False
    gates: list[dict] = []
    uri = public_uri(os.environ.get("NEO4J_URI", "bolt://localhost:7688"))
    build_id: str | None = None
    loading = False
    driver = None

    def finish(status: str, *, error: str | None = None, **fields) -> None:
        nonlocal finished
        store.finish_execution(record_id, run_id, status=status, error=error, **fields)
        finished = True

    def fail(message: str, recorded_gates: list[dict] | None = None) -> int:
        print(message, file=sys.stderr)
        finish("failed", gates=recorded_gates or [], error=message)
        return 1

    try:
        # (1) Evidence before any gate (D-G27).
        for name, payload in (("norms", norms_payload), ("alignments", alignments_payload)):
            if payload is not None and already_materialised(payload) and not payload.get("build", {}).get("reference"):
                return fail(f"NOT published: {name} carry decisions but no reference block; "
                            "materialise from the pristine dump")
        gating = gating_of(norms_payload, alignments_payload)
        # (2) The alignments were computed over this exact norms file.
        if alignments_payload is not None:
            recorded = alignments_payload.get("build", {}).get("alignment_input_sha256")
            if recorded is None and gating["layer2"] == "human":
                return fail("NOT published: alignments carry no input digest; "
                            "re-run the alignment command over the reference norms")
            if recorded is not None and recorded != norms_digest:
                return fail("NOT published: alignments were computed over a different norms file than --norms")
        # (3) Every reference block bound to exactly one freeze manifest.
        references = [p["build"]["reference"] for p in (norms_payload, alignments_payload)
                      if p and p.get("build", {}).get("reference")]
        for m in args.manifest:
            if m.resolve().parent != dump_dir.resolve():
                return fail(f"NOT published: copy the freeze manifest {m.name} into {dump_dir} first; "
                            "publication names its inputs by file under that directory")
        try:
            manifests = [verify_freeze_manifest(json.loads(m.read_text(encoding="utf-8")), None,
                                                expected_pinned_build_id=None) for m in args.manifest]
            bound = bind_manifests(references, manifests)
        except (MaterializeError, PublicationError, OSError, json.JSONDecodeError) as exc:
            return fail(f"NOT published: {exc}")

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
        set_target_state(dump_dir, state="available", build_id=build_id, uri=uri, reason=None)
        loading = False
        publication = {
            "chain_id": chain["chain_id"], "build_id": build_id, "published_at": datetime.now(UTC).isoformat(),
            "gating": gating, "label": whole_build_label(gating, bound, _core_nodes(dump_dir)), "gates": gates,
            "postload_gates": postload_gates, "manifests": _manifest_refs(bound),
        }
        chain_path = dump_dir / f"build_chain_{chain['chain_id']}.json"
        chain_path.write_text(json.dumps({**publication, **chain, "record_id": record_id}, indent=2) + "\n",
                              encoding="utf-8")
        write_publication_manifest(dump_dir, publication, record_id=record_id, inputs=chain["inputs"],
                                   files={"layer1_dump": args.dump.name, "norms": args.norms.name,
                                          "alignments": args.alignments.name if args.alignments else None})
        (dump_dir / "BUILD_CHAIN_CURRENT.txt").write_text(chain["chain_id"] + "\n", encoding="utf-8")
        store.set_publication(record_id, publication)
        finish("done", gates=gates + postload_gates,
               outputs=[{"role": "build_chain", "file": chain_path.name, "sha256": sha256_of_file(chain_path)}],
               counts={"nodes": nodes, "edges": edges})
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if loading:
            set_target_state(dump_dir, state="unavailable", build_id=build_id, uri=uri, reason=error)
        if not finished:
            finish("failed", gates=gates, error=error)
        raise
    finally:
        if driver is not None:
            driver.close()
    print(f"build chain: {build_id} ({len(chain['inputs'])} inputs) -> {chain_path.name}; label {publication['label']}")
    print(f"activate with: scripts/activate_build.py {chain['chain_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

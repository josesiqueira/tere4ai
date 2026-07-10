"""Publish judged Layer 2/3 results into Neo4j, gated by Section 13.

@implements: DEC-10 (partial: publication gating and reproducibility chain for Layer 2/3)
@grounded_by: REF-27, ADD-20

Usage:
  .venv/bin/python scripts/publish_layer23.py --norms data/graph_dumps/norms_core.json
  .venv/bin/python scripts/publish_layer23.py --norms ... --alignments data/graph_dumps/alignments_core.json

Runs the critical validation gates over the layer1 dump plus the given norms
(and alignments when provided); refuses to load anything into Neo4j if a gate
fails (a build that fails critical validation is not published). Connection:
NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD env vars, defaulting to the local v2
container (bolt://localhost:7688, neo4j).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes  # noqa: E402
from tere4ai.align_hleg_altai.hleg_subtopics import build_hleg_subtopics  # noqa: E402
from tere4ai.graph_store.build_chain import build_chain, chained_build_id  # noqa: E402
from tere4ai.graph_store.layer23 import alignments_to_graph, norms_to_graph  # noqa: E402
from tere4ai.graph_store.store import GraphStore  # noqa: E402
from tere4ai.review_queue import apply_decisions, count_applied, load_decisions  # noqa: E402
from tere4ai.validate_graph.gates import validate_build  # noqa: E402
from tere4ai.validate_graph.postload import validate_postload  # noqa: E402

DEFAULT_DECISIONS = ROOT / "data" / "review_queue" / "decisions.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--norms", type=Path, required=True)
    parser.add_argument("--alignments", type=Path, default=None)
    parser.add_argument(
        "--dump", type=Path, default=ROOT / "data" / "graph_dumps" / "layer1.json"
    )
    parser.add_argument(
        "--gates-only", action="store_true", help="validate, do not load into Neo4j"
    )
    parser.add_argument(
        "--decisions", type=Path, default=DEFAULT_DECISIONS,
        help="human review decisions file, applied before gating when present",
    )
    args = parser.parse_args(argv)

    layer1 = json.loads(args.dump.read_text(encoding="utf-8"))
    norms_payload = json.loads(args.norms.read_text(encoding="utf-8"))
    alignments_payload = None
    if args.alignments:
        alignments_payload = json.loads(args.alignments.read_text(encoding="utf-8"))

    # Human review decisions are applied to in-memory copies before gating and
    # loading; the pipeline dumps on disk stay pristine (architecture.md
    # Section 2 provenance discipline, Section 13).
    decisions = load_decisions(args.decisions)
    if decisions:
        norms_payload = apply_decisions(norms_payload, decisions)
        applied = count_applied(norms_payload)
        if alignments_payload is not None:
            alignments_payload = apply_decisions(alignments_payload, decisions)
            applied += count_applied(alignments_payload)
        print(f"human review: {applied} decisions applied from {args.decisions}")

    norms = norms_payload.get("norms", [])
    assertions = alignments_payload.get("assertions", []) if alignments_payload else None

    report = validate_build(layer1, norms=norms, alignments=assertions)
    print(f"gates: {'PASS' if report.passed else 'FAIL'} | stats {report.stats}")
    if not report.passed:
        for failure in report.failures[:20]:
            print(f"  GATE FAIL {failure}", file=sys.stderr)
        print("NOT published: critical validation failed", file=sys.stderr)
        return 1

    accepted = sum(1 for n in norms if n.get("judge_verdict") == "accepted")
    print(f"norms: {len(norms)} total, {accepted} judge-accepted")
    if assertions is not None:
        acc_a = sum(1 for a in assertions if a.get("judge_verdict") == "accepted")
        print(f"assertions: {len(assertions)} total, {acc_a} judge-accepted")

    if args.gates_only:
        return 0

    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7688")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "change_me")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    store = GraphStore()

    # Reproducibility chain (Section 13): the build_id stamped on every
    # published node and edge embeds a digest of the exact input files, so
    # the graph is verifiable back to its artifacts. Checksums are of the
    # pristine on-disk files; review decisions enter the chain as their own
    # input, mirroring how they are applied in memory only.
    chain = build_chain(
        args.dump,
        args.norms,
        alignments_path=args.alignments,
        decisions_path=args.decisions if decisions else None,
    )
    base_build_id = norms_payload.get("build", {}).get("build_id", "layer2-adhoc")
    build_id = chained_build_id(base_build_id, chain)
    chain_path = args.norms.parent / f"build_chain_{chain['chain_id']}.json"
    chain_path.write_text(
        json.dumps({"build_id": build_id, **chain}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"build chain: {build_id} ({len(chain['inputs'])} inputs) -> {chain_path.name}")
    graph = norms_to_graph(norms_payload, build_id=build_id)
    if alignments_payload is not None:
        g3 = alignments_to_graph(alignments_payload, build_hleg_nodes(), build_id=build_id)
        graph["nodes"].extend(g3["nodes"])
        graph["edges"].extend(g3["edges"])
        # Deterministic HLEG subtopic targets (DEC-05 partial) alongside the
        # seven requirement nodes; skipped heading candidates are printed,
        # never silently dropped (Section 13).
        subtopics = build_hleg_subtopics(build_id=build_id)
        graph["nodes"].extend(subtopics["nodes"])
        graph["edges"].extend(subtopics["edges"])
        print(
            f"hleg subtopics: {len(subtopics['nodes'])} nodes, "
            f"{len(subtopics['skipped'])} skipped heading candidates"
        )
        for item in subtopics["skipped"]:
            print(
                f"  subtopic candidate skipped ({item['reason']}): "
                f"{item['heading_candidate']!r}"
            )

    pseudo_dump = {
        "build": {
            "build_id": build_id,
            "built_at": norms_payload.get("build", {}).get("built_at", ""),
            "tere4ai_version": norms_payload.get("build", {}).get("tere4ai_version", ""),
            "snapshots": norms_payload.get("build", {}).get("snapshots", []),
            "input_checksums": chain["inputs"],
        },
        "nodes": graph["nodes"],
        "edges": graph["edges"],
    }
    counts = store.load_dump(pseudo_dump, driver)
    nodes = sum(v for k, v in counts.items() if k.startswith("node:"))
    edges = sum(v for k, v in counts.items() if k.startswith("edge:"))
    print(f"published to {uri}: {nodes} nodes, {edges} edges")
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")

    # Post-load gates (Section 13): verify what actually landed in the
    # database, so a partial load cannot pass as a published build.
    postload = validate_postload(
        driver,
        build_id=build_id,
        expected_norms=len(norms),
        expected_assertions=len(assertions) if assertions is not None else None,
    )
    print(f"post-load gates: {'PASS' if postload.passed else 'FAIL'} | {postload.stats}")
    driver.close()
    if not postload.passed:
        for failure in postload.failures:
            print(f"  POST-LOAD FAIL {failure}", file=sys.stderr)
        print("published data FAILED post-load validation", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

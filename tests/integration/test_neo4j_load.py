"""Live Neo4j round-trip test for DEC-09 (skipped without a reachable DB).

Enable with: NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j
NEO4J_PASSWORD=... .venv/bin/python -m pytest tests/integration/test_neo4j_load.py
"""

import json
import os
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DUMP = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD")),
    reason="NEO4J_URI / NEO4J_PASSWORD not set",
)


@pytest.fixture(scope="module")
def driver():
    from neo4j import GraphDatabase

    drv = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    try:
        with drv.session() as s:
            s.run("RETURN 1")
    except Exception as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")
    yield drv
    drv.close()


def test_constraints_and_load_round_trip(driver):
    from tere4ai.graph_store.store import GraphStore

    store = GraphStore()
    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    # load_dump MERGEs the dump and then reconciles Layer 0 to it: SourceFile and
    # SourceDocument nodes the dump does not list are removed. So this test runs only
    # when the database's Layer 0 node ids equal the tracked dump's (or it has none).
    listed = {n["id"] for n in dump["nodes"] if n["type"] in ("SourceFile", "SourceDocument")}
    with driver.session() as s:
        held = {r["id"] for r in s.run("MATCH (n) WHERE n:SourceFile OR n:SourceDocument RETURN n.id AS id")}
    if held and held != listed:
        pytest.skip(f"the database's Layer 0 differs from the tracked layer1.json ({len(held - listed)} nodes "
                    f"it holds are not listed, {len(listed - held)} listed are not held); load_dump would "
                    "remove the unlisted ones")
    result = store.apply_constraints(driver)
    assert result["applied"] > 0

    store.load_dump(dump, driver)  # MERGE then reconcile Layer 0 to the dump; repeatable on a matching database

    labels = ("Article", "Recital", "Annex", "Point", "AnnexItem")
    with driver.session() as s:
        counts = {
            label: s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            for label in labels
        }
    # The Act in force (DEC-23), the deleted units' nodes included: 119 Articles,
    # 180 Recitals, 14 Annexes, 527 Points (521 in force, 6 deleted) and 250
    # AnnexItems (247 in force, 3 deleted) in today's dump; counted from it.
    expected = Counter(n["type"] for n in dump["nodes"] if n["type"] in labels)
    assert counts == dict(expected)
    in_force = Counter(n["type"] for n in dump["nodes"] if n.get("amendment") != "deleted")
    assert (in_force["Article"], in_force["Recital"], in_force["Annex"]) == (119, 180, 14)


def test_crossref_queryable(driver):
    with driver.session() as s:
        annexes = s.run(
            "MATCH (:Article {number: '6'})-[:REFERS_TO]->(x:Annex) RETURN collect(x.number) AS a"
        ).single()["a"]
    assert set(annexes) >= {"I", "III"}


def test_a_reload_removes_the_layer0_files_and_edges_the_dump_no_longer_lists(driver):
    """Final review F1 (Codex P2, R30): load a dump that has an extra SourceFile and an extra
    ownership edge (the shape of a pre-B143 database), then the B143-shaped dump; the stale
    ones are gone, the listed ones stay. Test ids start with test:f1: and are removed in the
    finally block.

    load_dump reconciles Layer 0 of the WHOLE database to the dump, so the test refuses to
    run (skips) on a database that holds any Layer 0 node of its own; point NEO4J_URI at an
    empty or scratch database to run it."""
    from tere4ai.graph_store.store import GraphStore

    with driver.session() as s:
        foreign = s.run("MATCH (n) WHERE (n:SourceFile OR n:SourceDocument) AND NOT n.id STARTS WITH 'test:f1:' "
                        "RETURN count(n) AS c").single()["c"]
    if foreign:
        pytest.skip(f"the database holds {foreign} Layer 0 nodes of its own; load_dump would reconcile them away")

    def node(id_, type_, **props):
        return {"id": id_, "layer": 0, "type": type_, **props}

    def edge(id_, edge_type, from_, to):
        return {"edge_id": id_, "edge_type": edge_type, "from": from_, "to": to,
                "provenance_class": "RESOLVED_DETERMINISTIC", "method": "test", "confidence": 1.0,
                "review_status": "auto_accepted", "build_id": "test:f1:build"}

    act = node("test:f1:act", "SourceDocument", title="Act")
    guidelines = node("test:f1:guidelines", "SourceDocument", title="Guidelines")
    pdf = node("test:f1:pdf", "SourceFile", file="g.pdf", sha256="1" * 64)
    text = node("test:f1:text", "SourceFile", file="g.txt", sha256="2" * 64)
    v1 = node("test:f1:v1", "SourceFile", file="v1.txt", sha256="3" * 64)
    old = {"build": {"build_id": "test:f1:build"}, "nodes": [act, guidelines, pdf, text, v1], "edges": [
        edge("test:f1:e-pdf-act", "DERIVED_FROM_SOURCE", "test:f1:pdf", "test:f1:act"),
        edge("test:f1:e-v1-act", "DERIVED_FROM_SOURCE", "test:f1:v1", "test:f1:act"),
        edge("test:f1:e-text-pdf", "DERIVED_FROM", "test:f1:text", "test:f1:pdf")]}
    new = {"build": {"build_id": "test:f1:build"}, "nodes": [act, guidelines, pdf, text], "edges": [
        edge("test:f1:e-pdf-guidelines", "DERIVED_FROM_SOURCE", "test:f1:pdf", "test:f1:guidelines"),
        edge("test:f1:e-text-pdf", "DERIVED_FROM", "test:f1:text", "test:f1:pdf")]}

    def state():
        with driver.session() as s:
            nodes = {r["id"] for r in s.run("MATCH (n) WHERE n.id STARTS WITH 'test:f1:' RETURN n.id AS id")}
            edges = {r["id"] for r in s.run(
                "MATCH (:SourceFile)-[r]->() WHERE r.edge_id STARTS WITH 'test:f1:' RETURN r.edge_id AS id")}
        return nodes, edges

    store = GraphStore()
    try:
        store.load_dump(old, driver)
        nodes, edges = state()
        assert "test:f1:v1" in nodes and "test:f1:e-pdf-act" in edges
        counts = store.load_dump(new, driver)
        nodes, edges = state()
        assert nodes == {"test:f1:act", "test:f1:guidelines", "test:f1:pdf", "test:f1:text"}
        assert edges == {"test:f1:e-pdf-guidelines", "test:f1:e-text-pdf"}
        assert counts["removed:node:SourceFile"] == 1 and counts["removed:edge:SourceFile"] == 2  # the old pdf edge and the v1 edge
        assert counts["removed:node:SourceDocument"] == 0
    finally:
        with driver.session() as s:
            s.run("MATCH (n) WHERE n.id STARTS WITH 'test:f1:' DETACH DELETE n")

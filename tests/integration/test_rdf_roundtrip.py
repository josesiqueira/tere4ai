"""Live RDF export roundtrip for DEC-09 (skipped without Neo4j).

Roundtrip: export the judged Layer 2/3 subgraph via n10s, then parse the
N-Triples back with rdflib and verify the parsed graph matches what was
emitted (count) and contains the known published content (spot checks).
"""

from __future__ import annotations

import os

import pytest

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
            if not s.run(
                "SHOW PROCEDURES YIELD name WHERE name = 'n10s.rdf.export.cypher' "
                "RETURN count(*) AS n"
            ).single()["n"]:
                pytest.skip("n10s plugin not installed")
    except Exception as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")
    yield drv
    drv.close()


def test_export_parses_back_losslessly(driver, tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from tere4ai.graph_store.rdf_export import export_ntriples

    out = tmp_path / "layer23.nt"
    emitted = export_ntriples(driver, out)
    assert emitted > 0

    graph = rdflib.Graph()
    graph.parse(out, format="nt")
    # Lossless roundtrip: an RDF graph is a SET of triples, and the export
    # query's undirected (n)-[r]-(m) pattern emits some triples twice, so
    # the exact invariant is distinct emitted lines == parsed triples.
    distinct_lines = len(set(out.read_text(encoding="utf-8").splitlines()))
    assert len(graph) == distinct_lines
    assert distinct_lines <= emitted

    text = out.read_text(encoding="utf-8")
    # Spot checks: the published content is present as RDF.
    assert "norm:eu-ai-act:article-9" in text
    assert "hleg:" in text


def test_export_covers_all_judged_norms(driver, tmp_path):
    from tere4ai.graph_store.rdf_export import export_ntriples

    out = tmp_path / "layer23.nt"
    export_ntriples(driver, out)
    text = out.read_text(encoding="utf-8")
    with driver.session() as s:
        db_norms = s.run(
            "MATCH (n:NormativeStatement) RETURN n.id AS id"
        ).value()
    missing = [nid for nid in db_norms if nid not in text]
    assert not missing, f"{len(missing)} norms absent from the RDF export"

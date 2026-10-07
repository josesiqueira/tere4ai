"""Live post-load gate test against the published Layer 2/3 graph.

Skipped without a reachable Neo4j (same env gate as test_neo4j_load.py).
Asserts the published database passes P1..P5 for the current dumps, and that
a wrong expectation is caught rather than absorbed.
"""

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NORMS = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS = ROOT / "data" / "graph_dumps" / "alignments_core.json"

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


@pytest.fixture(scope="module")
def published_build_id(driver):
    with driver.session() as s:
        record = s.run(
            "MATCH (:NormativeStatement)-[r:DERIVED_FROM]->() RETURN r.build_id AS b LIMIT 1"
        ).single()
    if not record or not record["b"]:
        pytest.skip("no published Layer 2/3 build in this database")
    return record["b"]


def test_published_graph_passes_postload_gates(driver, published_build_id):
    from tere4ai.validate_graph.postload import validate_postload

    norms = json.loads(NORMS.read_text(encoding="utf-8"))["norms"]
    assertions = json.loads(ALIGNMENTS.read_text(encoding="utf-8"))["assertions"]
    report = validate_postload(
        driver,
        build_id=published_build_id,
        expected_norms=len(norms),
        expected_assertions=len(assertions),
    )
    assert report.passed, report.failures


def test_wrong_expected_count_fails_p1(driver, published_build_id):
    from tere4ai.validate_graph.postload import validate_postload

    report = validate_postload(
        driver, build_id=published_build_id, expected_norms=1
    )
    assert not report.passed
    assert any(f.startswith("P1") for f in report.failures)


def test_wrong_build_id_fails_p5(driver):
    from tere4ai.validate_graph.postload import validate_postload

    norms = json.loads(NORMS.read_text(encoding="utf-8"))["norms"]
    report = validate_postload(
        driver, build_id="not-the-published-build", expected_norms=len(norms)
    )
    assert not report.passed
    assert any(f.startswith("P5") for f in report.failures)


def test_p5_passes_a_layer0_derived_from_edge_and_fails_a_stale_norm_edge(driver):
    """B143 (R4, R23): a Layer 0 DERIVED_FROM edge with the parse's build id passes P5;
    a NormativeStatement's DERIVED_FROM edge with a stale build id fails it. The
    test's nodes have ids starting test:b143: and are removed in the finally block."""
    from tere4ai.validate_graph.postload import _STALE_BUILD_EDGES

    def violations(session):
        return session.run(_STALE_BUILD_EDGES, {"build_id": "test:b143:published"}).single()["violations"]

    with driver.session() as session:
        try:
            before = violations(session)
            session.run("CREATE (:SourceFile {id: 'test:b143:text'})-[:DERIVED_FROM {build_id: 'build-test:b143'}]->(:SourceFile {id: 'test:b143:pdf'})")
            assert violations(session) == before
            session.run("CREATE (:NormativeStatement {id: 'test:b143:norm'})-[:DERIVED_FROM {build_id: 'test:b143:stale'}]->(:Paragraph {id: 'test:b143:unit'})")
            assert violations(session) == before + 1
        finally:
            session.run("MATCH (n) WHERE n.id STARTS WITH 'test:b143:' DETACH DELETE n")

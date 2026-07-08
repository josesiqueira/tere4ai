"""Live Neo4j round-trip test for DEC-09 (skipped without a reachable DB).

Enable with: NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j
NEO4J_PASSWORD=... .venv/bin/python -m pytest tests/integration/test_neo4j_load.py
"""

import json
import os
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
    result = store.apply_constraints(driver)
    assert result["applied"] > 0

    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    store.load_dump(dump, driver)  # idempotent MERGE, safe to repeat

    with driver.session() as s:
        counts = {
            label: s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            for label in ("Article", "Recital", "Annex", "Point", "AnnexItem")
        }
    assert counts["Article"] == 113
    assert counts["Recital"] == 180
    assert counts["Annex"] == 13
    assert counts["Point"] == 467
    assert counts["AnnexItem"] == 217


def test_crossref_queryable(driver):
    with driver.session() as s:
        annexes = s.run(
            "MATCH (:Article {number: 6})-[:REFERS_TO]->(x:Annex) RETURN collect(x.number) AS a"
        ).single()["a"]
    assert set(annexes) >= {"I", "III"}

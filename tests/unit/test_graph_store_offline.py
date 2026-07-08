"""Offline graph_store test (DEC-09): load_dump issues MERGE statements
for every node and edge through a fake driver, no live Neo4j needed."""

from pathlib import Path

from tere4ai.graph_store.store import GraphStore

ROOT = Path(__file__).resolve().parents[2]


class FakeSession:
    def __init__(self, log):
        self.log = log

    def run(self, query, params=None, **kwargs):
        self.log.append((query, params or kwargs))
        return []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDriver:
    def __init__(self):
        self.log = []

    def session(self, **kw):
        return FakeSession(self.log)


def _tiny_dump():
    return {
        "build": {
            "build_id": "build-test",
            "built_at": "2026-07-08T00:00:00",
            "tere4ai_version": "2.0.0a0",
            "snapshots": [{"file": "x.html", "sha256": "0" * 64}],
        },
        "nodes": [
            {"id": "eu-ai-act", "layer": 1, "type": "Regulation", "title": "AI Act"},
            {
                "id": "eu-ai-act:article-9",
                "layer": 1,
                "type": "Article",
                "number": 9,
                "title": "Risk management system",
                "source_span": {
                    "span_id": "span:art_9",
                    "snapshot_file": "x.html",
                    "snapshot_sha256": "0" * 64,
                    "start": 0,
                    "end": 10,
                    "anchor": "art_9",
                },
            },
        ],
        "edges": [
            {
                "edge_id": "e1",
                "edge_type": "HAS_ARTICLE",
                "from": "eu-ai-act",
                "to": "eu-ai-act:article-9",
                "provenance_class": "EXTRACTED_SOURCE",
                "source_span_id": "span:art_9",
                "method": "html_anchor_hierarchy",
                "confidence": 1.0,
                "review_status": "auto_accepted",
                "build_id": "build-test",
            }
        ],
    }


def test_load_dump_merges_all_nodes_and_edges():
    driver = FakeDriver()
    counts = GraphStore().load_dump(_tiny_dump(), driver)
    queries = [q for q, _ in driver.log]
    merges = [q for q in queries if "MERGE" in q]
    assert merges, "load_dump must issue MERGE statements (idempotent load)"
    joined = " ".join(queries)
    assert "Article" in joined and "HAS_ARTICLE" in joined
    node_total = sum(v for k, v in counts.items() if k.startswith("node:"))
    edge_total = sum(v for k, v in counts.items() if k.startswith("edge:"))
    assert node_total == 2 and edge_total == 1


def test_constraints_file_labels_never_split():
    text = (ROOT / "schema" / "cypher_constraints" / "constraints.cypher").read_text(
        encoding="utf-8"
    )
    statements = [
        line for line in text.splitlines() if line.strip() and not line.strip().startswith("//")
    ]
    assert statements, "constraints.cypher must contain statements"
    for line in statements:
        # a full statement per line: no label or type broken across lines
        assert "CONSTRAINT" in line.upper() or "REQUIRE" in line.upper(), line

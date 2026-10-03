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


def _neo4j_property(value) -> bool:
    """A value Neo4j can store as a property: a scalar or a homogeneous list of scalars."""
    if isinstance(value, (str, int, float, bool)):
        return True
    return isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) for v in value) and len(
        {type(v) for v in value}) <= 1


def test_span_exclusions_flatten_to_neo4j_property_types():
    """Final review F2 (Codex P1): a span's exclude list of {start, end} maps would
    be a list of maps, which Neo4j cannot store; the store writes two integer lists."""
    import json

    from tere4ai.graph_store.store import flatten_node_properties

    dump = json.loads((ROOT / "data" / "graph_dumps" / "layer1.json").read_text(encoding="utf-8"))
    article_10 = next(n for n in dump["nodes"] if n["id"] == "eu-ai-act:article-10")
    assert article_10["source_span"]["exclude"], "Article 10's span excludes the deleted paragraph 5"
    props = flatten_node_properties(article_10)
    assert props["span_exclude_starts"] == [r["start"] for r in article_10["source_span"]["exclude"]]
    assert props["span_exclude_ends"] == [r["end"] for r in article_10["source_span"]["exclude"]]
    assert "span_exclude" not in props
    for node in dump["nodes"]:
        bad = {k: v for k, v in flatten_node_properties(node).items() if not _neo4j_property(v)}
        assert not bad, (node["id"], bad)


def test_a_deleted_unit_loses_its_stored_text_and_span_on_reload():
    """Final review F3 (Codex P2): SET n += row.props keeps what an earlier load stored,
    so a reload over a 2024 database would keep Article 10(5)'s text and span; the
    loader removes them from every node the dump marks deleted."""
    dump = _tiny_dump()
    dump["nodes"].append({"id": "eu-ai-act:article-10:paragraph-5", "layer": 1, "type": "Paragraph", "index": "5",
                          "sort_key": 500, "amendment": "deleted",
                          "deleted_by": "Regulation (EU) 2026/1744, Article 1, point (9)(b)",
                          "deleted_from": "2026-07-27"})
    driver = FakeDriver()
    GraphStore().load_dump(dump, driver)
    removals = [(q, p) for q, p in driver.log if "REMOVE" in q]
    assert len(removals) == 1
    query, params = removals[0]
    assert [row["id"] for row in params["rows"]] == ["eu-ai-act:article-10:paragraph-5"]
    for prop in ("text", "span_id", "span_snapshot_file", "span_snapshot_sha256", "span_start", "span_end",
                 "span_anchor", "span_exclude_starts", "span_exclude_ends"):
        assert f"n.{prop}" in query, prop
    merge_at = next(i for i, (q, _) in enumerate(driver.log) if "MERGE (n:Paragraph" in q)
    assert driver.log.index(removals[0]) > merge_at


def test_the_integer_label_constraints_are_dropped_before_the_string_ones_are_created():
    """Final review F4 (Codex P2): CREATE ... IF NOT EXISTS keeps an existing constraint
    of the same name, so on a database loaded before B132 the INTEGER type constraints
    on Article.number and Paragraph.index would stay and refuse the Act's labels ("4a").
    The file drops them by name before it creates the STRING ones."""
    from tere4ai.graph_store.store import parse_constraint_statements

    statements = parse_constraint_statements(
        (ROOT / "schema" / "cypher_constraints" / "constraints.cypher").read_text(encoding="utf-8"))
    for label, prop, old_name in (("Article", "number", "article_number_type"),
                                  ("Paragraph", "index", "paragraph_index_type")):
        drop = statements.index(f"DROP CONSTRAINT {old_name} IF EXISTS")
        create = next(i for i, s in enumerate(statements)
                      if f"FOR (n:{label}) REQUIRE n.{prop} IS :: STRING" in s)
        assert drop < create, (label, prop)
        assert f"CONSTRAINT {old_name} " not in statements[create], "a new name, so a later run drops nothing"
        assert not any(f"FOR (n:{label}) REQUIRE n.{prop} IS :: INTEGER" in s for s in statements)

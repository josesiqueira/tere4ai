"""Reified CrossReference nodes + paragraph-level targets (#44, DEC-02)."""

from __future__ import annotations

from tere4ai.resolve_crossrefs.resolver import resolve

SPAN = {"span_id": "span:test", "anchor": "art_1"}


def make_dump(text: str, extra_nodes=()):
    return {
        "build": {"build_id": "build-test"},
        "nodes": [
            {"id": "eu-ai-act:article-1", "type": "Article", "number": 1},
            {
                "id": "eu-ai-act:article-1:paragraph-1",
                "type": "Paragraph",
                "text": text,
                "source_span": SPAN,
            },
            {"id": "eu-ai-act:article-6", "type": "Article", "number": 6},
            {"id": "eu-ai-act:article-6:paragraph-2", "type": "Paragraph", "text": "x"},
            *extra_nodes,
        ],
        "edges": [],
        "review_queue": [],
    }


def xref_nodes(dump):
    return [n for n in dump["nodes"] if n["type"] == "CrossReference"]


def edges_of(dump, edge_type):
    return [e for e in dump["edges"] if e["edge_type"] == edge_type]


def test_resolved_mention_is_reified_with_span_and_citation():
    result = resolve(make_dump("As referred to in Article 6, widgets apply."))
    nodes = xref_nodes(result)
    assert len(nodes) == 1
    node = nodes[0]
    assert node["citation_text"] == "Article 6"
    assert node["from_node_id"] == "eu-ai-act:article-1:paragraph-1"
    assert node["source_span"] == SPAN
    has_xref = edges_of(result, "HAS_CROSS_REFERENCE")
    assert [(e["from"], e["to"]) for e in has_xref] == [
        ("eu-ai-act:article-1:paragraph-1", node["id"])
    ]
    resolves = edges_of(result, "RESOLVES_TO")
    assert [(e["from"], e["to"]) for e in resolves] == [
        (node["id"], "eu-ai-act:article-6")
    ]
    for edge in has_xref + resolves:
        assert edge["provenance_class"] == "RESOLVED_DETERMINISTIC"
        assert edge["source_span_id"] == "span:test"


def test_article_paragraph_citation_resolves_to_paragraph_level():
    result = resolve(make_dump("Classification under Article 6(2) applies."))
    resolves = edges_of(result, "RESOLVES_TO")
    assert [e["to"] for e in resolves] == ["eu-ai-act:article-6:paragraph-2"]
    # The coarse navigation edge stays at article level.
    refers = edges_of(result, "REFERS_TO")
    assert [e["to"] for e in refers] == ["eu-ai-act:article-6"]


def test_paragraph_target_falls_back_to_article_when_node_missing():
    result = resolve(make_dump("Pursuant to Article 6(9), widgets apply."))
    resolves = edges_of(result, "RESOLVES_TO")
    assert [e["to"] for e in resolves] == ["eu-ai-act:article-6"]


def test_external_citation_is_not_reified():
    result = resolve(
        make_dump("Under Article 4(2) of Regulation (EU) 2016/679, data applies.")
    )
    assert xref_nodes(result) == []
    assert any(
        item["reason"] == "external_instrument" for item in result["review_queue"]
    )


def test_unresolved_target_is_not_reified():
    result = resolve(make_dump("As set out in Article 999, nothing applies."))
    assert xref_nodes(result) == []
    assert any(
        item["reason"] == "unresolved_target" for item in result["review_queue"]
    )


def test_range_mention_reifies_once_with_all_targets():
    extra = tuple(
        {"id": f"eu-ai-act:article-{n}", "type": "Article", "number": n}
        for n in (8, 9, 10)
    )
    result = resolve(make_dump("Articles 8 to 10 apply here.", extra_nodes=extra))
    nodes = xref_nodes(result)
    assert len(nodes) == 1
    resolves = edges_of(result, "RESOLVES_TO")
    assert sorted(e["to"] for e in resolves) == [
        "eu-ai-act:article-10",
        "eu-ai-act:article-8",
        "eu-ai-act:article-9",
    ]


def test_reification_is_deterministic():
    dump = make_dump("As referred to in Article 6(2) and Article 6, widgets apply.")
    a = resolve(dump)
    b = resolve(dump)
    assert a == b

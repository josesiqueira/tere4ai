"""Letter-suffixed numbers through the parse, the resolver and the readers (B132, DEC-23).

Spec G D-G68 (3): the Omnibus inserts Article 4a, Article 6(1a) to (1c),
Article 5(1), first subparagraph, point (ba) and Annex XIV. Before B132 the
resolver read "Article 4a" as Article 4 and "Article 5(1a)" as Article 5,
and the parse, the schema and the readers took Article numbers for
integers. Deterministic; small mock dumps and the frozen 2024 HTML.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tere4ai.resolve_crossrefs.resolver import resolve

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshots" / "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"


def _span(span_id: str) -> dict:
    return {"span_id": span_id, "snapshot_file": "x", "snapshot_sha256": "0" * 64, "start": 0, "end": 1}


def _mock_dump(text: str, extra: list[dict] | None = None) -> dict:
    nodes = [
        {"id": "eu-ai-act", "layer": 1, "type": "Regulation"},
        {"id": "eu-ai-act:article-4", "layer": 1, "type": "Article", "number": "4", "sort_key": 400},
        {"id": "eu-ai-act:article-4a", "layer": 1, "type": "Article", "number": "4a", "sort_key": 401},
        {"id": "eu-ai-act:article-5", "layer": 1, "type": "Article", "number": "5", "sort_key": 500},
        {"id": "eu-ai-act:article-5:paragraph-1", "layer": 1, "type": "Paragraph", "index": "1", "sort_key": 100,
         "text": "1. The following AI practices shall be prohibited:", "source_span": _span("span:005.001")},
        {"id": "eu-ai-act:article-5:paragraph-1a", "layer": 1, "type": "Paragraph", "index": "1a",
         "sort_key": 101, "text": "1a. For the purposes of paragraph 1.", "source_span": _span("span:005.001a")},
        {"id": "eu-ai-act:article-10", "layer": 1, "type": "Article", "number": "10", "sort_key": 1000},
        {"id": "eu-ai-act:article-10:paragraph-1", "layer": 1, "type": "Paragraph", "index": "1", "sort_key": 100,
         "text": text, "source_span": _span("span:010.001")},
        {"id": "eu-ai-act:annex-xiv", "layer": 1, "type": "Annex", "number": "XIV"},
        *(extra or []),
    ]
    return {"build": {"build_id": "build-test"}, "nodes": nodes, "edges": []}


def _resolves_to(dump: dict) -> set[str]:
    return {e["to"] for e in dump["edges"] if e["edge_type"] == "RESOLVES_TO"}


def test_resolver_reads_letter_suffixed_articles_and_paragraphs():
    out = resolve(_mock_dump(
        "Without prejudice to Article 4a(1) and Article 5(1a), point (ba), as listed in Annex XIV."
    ))
    targets = _resolves_to(out)
    assert "eu-ai-act:article-4a" in targets  # no paragraph-1 node in the mock: the Article
    assert "eu-ai-act:article-5:paragraph-1a" in targets
    assert "eu-ai-act:annex-xiv" in targets
    assert "eu-ai-act:article-4" not in targets
    refers = {(e["from"], e["to"]) for e in out["edges"] if e["edge_type"] == "REFERS_TO"}
    assert ("eu-ai-act:article-10", "eu-ai-act:article-4a") in refers


def test_a_range_of_plain_numbers_still_expands():
    out = resolve(_mock_dump("as referred to in Articles 4 to 5"))
    assert {"eu-ai-act:article-4", "eu-ai-act:article-5"} <= _resolves_to(out)
    assert "eu-ai-act:article-4a" not in _resolves_to(out)


def test_a_deleted_paragraph_is_never_a_precise_target():
    deleted = {"id": "eu-ai-act:article-10:paragraph-5", "layer": 1, "type": "Paragraph", "index": "5",
               "sort_key": 500, "amendment": "deleted",
               "deleted_by": "Regulation (EU) 2026/1744, Article 1, point (9)(b)", "deleted_from": "2026-07-27"}
    out = resolve(_mock_dump("in accordance with Article 10(5)", extra=[deleted]))
    assert "eu-ai-act:article-10:paragraph-5" not in _resolves_to(out)
    assert "eu-ai-act:article-10" in _resolves_to(out)


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="frozen snapshot not present")
def test_the_2024_parse_writes_labels_and_sort_keys():
    from tere4ai.parse_legal_structure.parser import parse_snapshot

    nodes = {n["id"]: n for n in parse_snapshot(SNAPSHOT)["nodes"]}
    article = nodes["eu-ai-act:article-9"]
    assert article["number"] == "9" and article["sort_key"] == 900
    paragraph = nodes["eu-ai-act:article-9:paragraph-2"]
    assert paragraph["index"] == "2" and paragraph["sort_key"] == 200
    fallback = nodes["eu-ai-act:article-4:paragraph-1"]
    assert fallback["index"] == "1" and fallback["source_span"]["span_id"] == "span:art_4:body"


def test_the_ablation_runner_credits_the_whole_article_label():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_ablations", ROOT / "scripts" / "run_ablations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._article_prefix("eu-ai-act:article-4a:paragraph-1") == "eu-ai-act:article-4a"
    assert module._article_prefix("eu-ai-act:article-4:paragraph-1") == "eu-ai-act:article-4"
    assert module._article_prefix("eu-ai-act:article-50") == "eu-ai-act:article-50"


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="frozen snapshot not present")
def test_coverage_report_reads_article_labels():
    from tere4ai.mcp_server.tools import coverage_report
    from tere4ai.parse_legal_structure.parser import parse_snapshot

    answer = coverage_report(parse_snapshot(SNAPSHOT))["answer"]
    checks = {c["name"]: c["ok"] for c in answer["checks"]}
    assert checks["article_count"] and checks["high_risk_core_present"]
    assert answer["per_chapter_articles"]["III"][:3] == ["6", "7", "8"]
    assert answer["per_chapter_articles"]["XIII"][-1] == "113"
    assert answer["actual"]["deleted_units"] == 0

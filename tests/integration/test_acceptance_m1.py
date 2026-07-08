"""M1 acceptance fixtures (docs/architecture.md Sections 10 and 14).

Covers DEC-01 (deterministic Layer 1) and DEC-02 (rule-based crossrefs)
against the real frozen snapshot.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshots" / "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"

pytestmark = pytest.mark.skipif(not SNAPSHOT.exists(), reason="frozen snapshot not present")


@pytest.fixture(scope="module")
def dump():
    from tere4ai.parse_legal_structure.parser import parse_snapshot
    from tere4ai.resolve_crossrefs.resolver import resolve

    return resolve(parse_snapshot(SNAPSHOT))


def _count(dump, node_type):
    return sum(1 for n in dump["nodes"] if n["type"] == node_type)


def test_structural_mirror_counts(dump):
    assert _count(dump, "Article") == 113
    assert _count(dump, "Recital") == 180
    assert _count(dump, "Annex") == 13
    assert _count(dump, "Chapter") == 13
    assert _count(dump, "Paragraph") >= 509


def test_chapter_iii_section_2_holds_articles_8_to_15(dump):
    s2 = "eu-ai-act:chapter-iii:section-2"
    arts = sorted(
        int(e["to"].rsplit("-", 1)[1])
        for e in dump["edges"]
        if e["edge_type"] == "HAS_ARTICLE" and e["from"] == s2
    )
    assert arts == [8, 9, 10, 11, 12, 13, 14, 15]


def test_article_6_links_annexes_i_and_iii(dump):
    refs = {
        (e["from"], e["to"]) for e in dump["edges"] if e["edge_type"] == "REFERS_TO"
    }
    assert ("eu-ai-act:article-6", "eu-ai-act:annex-i") in refs
    assert ("eu-ai-act:article-6", "eu-ai-act:annex-iii") in refs


def test_article_11_links_annex_iv(dump):
    refs = {
        (e["from"], e["to"]) for e in dump["edges"] if e["edge_type"] == "REFERS_TO"
    }
    assert ("eu-ai-act:article-11", "eu-ai-act:annex-iv") in refs


def test_no_external_instrument_resolved_internally(dump):
    for e in dump["edges"]:
        if e["edge_type"] == "REFERS_TO":
            ct = e.get("citation_text", "")
            assert "of Regulation" not in ct and "of Directive" not in ct


def test_every_edge_has_provenance(dump):
    for e in dump["edges"]:
        assert e.get("source_span_id") or e.get("derivation_id"), e["edge_id"]
        assert e["provenance_class"] in {
            "EXTRACTED_SOURCE",
            "EXTRACTED_CROSS_REFERENCE",
            "RESOLVED_DETERMINISTIC",
            "AMBIGUOUS_NEEDS_REVIEW",
        }


def test_every_layer1_node_has_source_span(dump):
    for n in dump["nodes"]:
        if n["layer"] == 1 and n["type"] != "Regulation":
            span = n.get("source_span")
            assert span, n["id"]
            assert span["snapshot_sha256"] == (
                "3b753e5e9297ec27ede1324e670dc23ad4ac7c47a75374b6cdd9eb9e0db2993d"
            )


def test_parse_is_deterministic(dump):
    from tere4ai.parse_legal_structure.parser import parse_snapshot
    from tere4ai.resolve_crossrefs.resolver import resolve

    second = resolve(parse_snapshot(SNAPSHOT))

    def strip(d):
        d = json.loads(json.dumps(d))
        d["build"].pop("built_at", None)
        return d

    assert strip(dump) == strip(second)


def test_dump_validates_against_schema(dump):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = {}
    for name in ("nodes", "edges", "layer1_dump"):
        p = ROOT / "schema" / "json_schemas" / f"{name}.schema.json"
        schemas[name] = json.loads(p.read_text(encoding="utf-8"))

    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas.values()
    )
    validator = Draft202012Validator(schemas["layer1_dump"], registry=registry)
    errors = list(validator.iter_errors(dump))
    assert not errors, errors[:3]


def test_no_model_calls_in_deterministic_modules():
    for mod in ("parse_legal_structure/parser.py", "resolve_crossrefs/resolver.py"):
        src = (ROOT / "src" / "tere4ai" / mod).read_text(encoding="utf-8")
        for banned in ("openai", "anthropic", "litellm"):
            assert banned not in src, f"{mod} must stay deterministic (DEC-01/DEC-02)"

"""Tests for the four deterministic graph-depth features.

Covers, against the real frozen snapshots:
  - Definition nodes from the Article 3 quoted terms plus capped, logged
    CONTEXT_FOR usage links (definitions.py, DEC-01 partial).
  - Subparagraph nodes from the Formex ALINEA blocks (subparagraphs.py,
    DEC-01 partial).
  - Recital -> Article CONTEXT_FOR context links (recital_links.py, DEC-01
    partial). Honesty note: the frozen text contains only FOUR recital
    mentions of AI Act articles that survive the external-instrument filter
    (recitals overwhelmingly cite the TFEU, TEU, the Charter, protocols, or
    other regulations). The verified counts below are asserted exactly;
    recital 12 mentions no article number at all, so no recital-12 edge
    exists.
  - HLEGRequirementSubtopic nodes sliced from the frozen HLEG text
    (hleg_subtopics.py, DEC-05 partial), including the skipped-candidate
    report (never guess, never silently drop).
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshots" / "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"
FORMEX_DIR = ROOT / "data" / "snapshots" / "formex"
MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"
HLEG_TEXT = ROOT / "data" / "snapshots" / "hleg_ethics_guidelines_2019_en_v1text.txt"

pytestmark = pytest.mark.skipif(
    not (SNAPSHOT.exists() and FORMEX_DIR.is_dir() and HLEG_TEXT.exists()),
    reason="frozen snapshots not present",
)

CORE_ARTICLES = set(range(5, 28)) | {50, 72, 73}


def _build():
    from tere4ai.parse_legal_structure.definitions import enrich_with_definitions
    from tere4ai.parse_legal_structure.formex import enrich_with_formex
    from tere4ai.parse_legal_structure.parser import parse_snapshot
    from tere4ai.parse_legal_structure.recital_links import add_recital_context
    from tere4ai.parse_legal_structure.subparagraphs import enrich_with_subparagraphs

    dump = parse_snapshot(SNAPSHOT)
    dump = enrich_with_formex(dump, FORMEX_DIR, MANIFEST)
    dump = enrich_with_subparagraphs(dump, FORMEX_DIR, MANIFEST)
    dump = enrich_with_definitions(dump, FORMEX_DIR, MANIFEST)
    return add_recital_context(dump)


@pytest.fixture(scope="module")
def dump():
    return _build()


@pytest.fixture(scope="module")
def by_id(dump):
    return {n["id"]: n for n in dump["nodes"]}


def _nodes(dump, node_type):
    return [n for n in dump["nodes"] if n["type"] == node_type]


def _edges(dump, edge_type):
    return [e for e in dump["edges"] if e["edge_type"] == edge_type]


def _manifest_shas():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {e["file"]: e["sha256"] for e in manifest["snapshots"]}


# ---------------------------------------------------------------------------
# Feature 32: Definition nodes and usage links
# ---------------------------------------------------------------------------


def test_definition_count_and_key_terms(dump):
    definitions = _nodes(dump, "Definition")
    assert len(definitions) >= 60
    assert len(definitions) == 68  # Article 3 of the frozen Act defines 68 terms
    terms = {n["term"] for n in definitions}
    assert "AI system" in terms
    assert "provider" in terms
    for n in definitions:
        assert re.fullmatch(r"eu-ai-act:definition:[a-z0-9-]+", n["id"]), n["id"]
        assert n["layer"] == 1


def test_definitions_are_span_grounded(dump):
    shas = _manifest_shas()
    for n in _nodes(dump, "Definition"):
        span = n["source_span"]
        assert span["snapshot_file"].startswith("formex/"), n["id"]
        assert span["snapshot_sha256"] == shas[span["snapshot_file"]], n["id"]
        assert 0 <= span["start"] < span["end"], n["id"]
        assert n["term"].strip(), n["id"]


def test_defines_term_edges_from_article_3_points(dump, by_id):
    edges = _edges(dump, "DEFINES_TERM")
    assert len(edges) == len(_nodes(dump, "Definition"))
    for e in edges:
        assert re.fullmatch(
            r"eu-ai-act:article-3:paragraph-1:point-\d+", e["from"]
        ), e["edge_id"]
        assert by_id[e["to"]]["type"] == "Definition", e["edge_id"]
        assert e["provenance_class"] == "EXTRACTED_SOURCE"
        assert e["method"] == "definition_quot_v1"
        assert e["source_span_id"]


def test_usage_cap_is_logged_never_silent(dump):
    """Section 13 no-silent-caps: usage_count_total records ALL matches; the
    emitted CONTEXT_FOR edges are capped at 30 and counted separately."""
    usage_edges_by_def = {}
    for e in _edges(dump, "CONTEXT_FOR"):
        if e["from"].startswith("eu-ai-act:definition:"):
            usage_edges_by_def.setdefault(e["from"], []).append(e)

    capped_terms = []
    for n in _nodes(dump, "Definition"):
        emitted = usage_edges_by_def.get(n["id"], [])
        assert n["usage_count_linked"] == len(emitted), n["id"]
        assert n["usage_count_linked"] == min(n["usage_count_total"], 30), n["id"]
        if n["usage_count_total"] > 30:
            capped_terms.append(n["term"])
            assert len(emitted) == 30, n["id"]
    # High-frequency terms really hit the cap, and the cap is visible.
    assert "AI system" in capped_terms
    assert "provider" in capped_terms


def test_definition_usages_stay_in_high_risk_core(dump, by_id):
    for e in _edges(dump, "CONTEXT_FOR"):
        if not e["from"].startswith("eu-ai-act:definition:"):
            continue
        assert e["provenance_class"] == "RESOLVED_DETERMINISTIC", e["edge_id"]
        assert e["method"] == "definition_usage_v1", e["edge_id"]
        target = by_id[e["to"]]
        m = re.match(r"eu-ai-act:article-(\d+):", e["to"])
        if m:
            assert int(m.group(1)) in CORE_ARTICLES, e["edge_id"]
            assert target["type"] in ("Paragraph", "Point", "Subparagraph"), e["edge_id"]
        else:
            assert target["type"] == "AnnexItem", e["edge_id"]
        # word-boundary, case-insensitive term match really present
        term = e["citation_text"]
        assert re.search(rf"\b{re.escape(term)}\b", target["text"], re.IGNORECASE), e["edge_id"]


# ---------------------------------------------------------------------------
# Feature 43: Subparagraph nodes
# ---------------------------------------------------------------------------


def test_subparagraph_count_and_ids(dump):
    subs = _nodes(dump, "Subparagraph")
    assert len(subs) > 0
    assert len(subs) == 63  # non-leading ALINEA blocks in the frozen main body
    shas = _manifest_shas()
    for n in subs:
        m = re.fullmatch(
            r"eu-ai-act:article-\d+:paragraph-\d+:subparagraph-(\d+)", n["id"]
        )
        assert m, n["id"]
        assert n["index"] == int(m.group(1)) >= 2, n["id"]  # leading block has no node
        span = n["source_span"]
        assert span["snapshot_file"].startswith("formex/"), n["id"]
        assert span["snapshot_sha256"] == shas[span["snapshot_file"]], n["id"]
        assert n["text"].strip(), n["id"]


def test_article_43_1_subparagraphs_consistent_with_point_ids(dump, by_id):
    """formex.py already scopes the Article 43(1) point ids by subparagraph
    ordinal; the Subparagraph nodes must use the same numbering."""
    p1 = "eu-ai-act:article-43:paragraph-1"
    assert f"{p1}:subparagraph-2" in by_id
    assert f"{p1}:subparagraph-3" in by_id
    assert f"{p1}:subparagraph-1" not in by_id  # the leading text block
    # every subparagraph-scoped point id shares its prefix with a real node
    for n in _nodes(dump, "Point"):
        m = re.match(r"^(.*:subparagraph-(\d+)):point-[a-z0-9]+$", n["id"])
        if not m:
            continue
        if int(m.group(2)) >= 2:
            assert m.group(1) in by_id, n["id"]
            assert by_id[m.group(1)]["type"] == "Subparagraph", n["id"]


def test_has_subparagraph_edges(dump, by_id):
    edges = _edges(dump, "HAS_SUBPARAGRAPH")
    assert len(edges) == len(_nodes(dump, "Subparagraph"))
    for e in edges:
        assert by_id[e["from"]]["type"] == "Paragraph", e["edge_id"]
        child = by_id[e["to"]]
        assert child["type"] == "Subparagraph", e["edge_id"]
        assert e["provenance_class"] == "EXTRACTED_SOURCE"
        assert e["method"] == "formex_subparagraph_v1"
        assert e["source_span_id"] == child["source_span"]["span_id"], e["edge_id"]


# ---------------------------------------------------------------------------
# Feature 45: recital -> article CONTEXT_FOR links
# ---------------------------------------------------------------------------


def _recital_context(dump):
    return [
        e
        for e in _edges(dump, "CONTEXT_FOR")
        if e["from"].startswith("eu-ai-act:recital-")
    ]


def test_recital_links_verified_against_real_text(dump, by_id):
    """Verified against the frozen text: only recitals 40 and 41 cite AI Act
    articles by number and survive the external-instrument filter (TFEU, TEU,
    Charter, protocols, GDPR and other regulations are queued, not linked).
    Recital 12 (the AI system notion) cites NO article number, so the edge
    set is exactly these four. A wrong citation is worse than a missing one,
    so the count is asserted exactly, not inflated."""
    pairs = {(e["from"], e["to"]) for e in _recital_context(dump)}
    assert pairs == {
        ("eu-ai-act:recital-40", "eu-ai-act:article-5"),
        ("eu-ai-act:recital-40", "eu-ai-act:article-26"),
        ("eu-ai-act:recital-41", "eu-ai-act:article-5"),
        ("eu-ai-act:recital-41", "eu-ai-act:article-26"),
    }
    recital_12 = by_id["eu-ai-act:recital-12"]
    assert not re.search(r"\bArticles?\s+\d", recital_12["text"])


def test_recital_links_only_target_articles(dump, by_id):
    for e in _recital_context(dump):
        assert by_id[e["to"]]["type"] == "Article", e["edge_id"]
        assert re.fullmatch(r"eu-ai-act:article-\d+", e["to"]), e["edge_id"]
        assert e["provenance_class"] == "RESOLVED_DETERMINISTIC"
        assert e["method"] == "recital_context_v1"
        assert e["source_span_id"] == by_id[e["from"]]["source_span"]["span_id"]


def test_external_recital_mentions_are_queued_not_linked(dump):
    queued = [
        q for q in dump.get("review_queue", []) if q.get("kind") == "recital_context"
    ]
    assert queued, "external recital mentions must be queued, never silently dropped"
    assert all(
        q["reason"] in ("external_instrument", "unresolved_target") for q in queued
    )
    # the TFEU mentions of recital 3 are external, never AI Act links
    assert any(q["from_node_id"] == "eu-ai-act:recital-3" for q in queued)


def test_context_for_is_not_a_hierarchy_edge_and_recitals_stay_context_only(dump):
    from tere4ai.validate_graph.gates import HIERARCHY_EDGES, REACHABILITY_EDGES

    assert "CONTEXT_FOR" not in HIERARCHY_EDGES
    assert "CONTEXT_FOR" not in REACHABILITY_EDGES
    # recitals are reached exactly as before: one HAS_RECITAL each, no other
    # hierarchy edge arrives at or leaves a recital
    recital_ids = {n["id"] for n in _nodes(dump, "Recital")}
    for e in dump["edges"]:
        if e["edge_type"] in HIERARCHY_EDGES:
            if e["to"] in recital_ids:
                assert e["edge_type"] == "HAS_RECITAL", e["edge_id"]
            assert e["from"] not in recital_ids or e["edge_type"] == "HAS_RECITAL"


# ---------------------------------------------------------------------------
# Feature 46: HLEG requirement subtopics
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def subtopics():
    from tere4ai.align_hleg_altai.hleg_subtopics import build_hleg_subtopics

    return build_hleg_subtopics()


def test_subtopic_count_and_closed_parents(subtopics):
    from tere4ai.align_hleg_altai.hleg_nodes import CANONICAL

    nodes = subtopics["nodes"]
    assert len(nodes) >= 10
    assert len(nodes) == 23  # verified against the frozen HLEG text
    canonical_ids = {cid for cid, _ in CANONICAL}
    parents = {n["hleg_requirement_id"] for n in nodes}
    assert parents == canonical_ids  # all 7 requirements have subtopics
    for n in nodes:
        assert n["hleg_requirement_id"] in canonical_ids, n["id"]
        assert n["id"].startswith(f"{n['hleg_requirement_id']}:subtopic:"), n["id"]
        assert n["layer"] == 3
        assert n["label"].strip() and n["description"].strip(), n["id"]


def test_every_subtopic_is_span_grounded(subtopics):
    text = HLEG_TEXT.read_text(encoding="utf-8")
    manifest_shas = _manifest_shas()
    for n in subtopics["nodes"]:
        span = n["source_span"]
        assert span["snapshot_sha256"] == manifest_shas[span["snapshot_file"]], n["id"]
        sliced = text[span["start"] : span["end"]]
        assert sliced.startswith(n["label"] + "."), n["id"]
        # the description is the first sentence of the sliced paragraph
        assert n["description"][:40] in " ".join(sliced.split()), n["id"]


def test_has_subtopic_edges(subtopics):
    nodes_by_id = {n["id"]: n for n in subtopics["nodes"]}
    edges = subtopics["edges"]
    assert len(edges) == len(subtopics["nodes"])
    for e in edges:
        assert e["edge_type"] == "HAS_SUBTOPIC"
        child = nodes_by_id[e["to"]]
        assert e["from"] == child["hleg_requirement_id"], e["edge_id"]
        assert e["provenance_class"] == "EXTRACTED_SOURCE"
        assert e["method"] == "hleg_subtopic_slice_v1"
        assert e["source_span_id"] == child["source_span"]["span_id"], e["edge_id"]


def test_ambiguous_headings_are_skipped_and_reported(subtopics):
    """Never guess: candidates failing the strict heading test are excluded
    from the nodes and recorded in the module-level report."""
    from tere4ai.align_hleg_altai.hleg_subtopics import SKIPPED_REPORT

    skipped = subtopics["skipped"]
    assert skipped == SKIPPED_REPORT
    # the frozen text yields exactly these three rejected candidates
    assert [(s["section_id"], s["reason"]) for s in skipped] == [
        ("hleg:technical-robustness-and-safety", "prefix contains punctuation or digits"),
        ("hleg:technical-robustness-and-safety", "prefix has 9 words (max 7)"),
        ("hleg:privacy-and-data-governance", "prefix has 14 words (max 7)"),
    ]
    emitted_labels = {n["label"] for n in subtopics["nodes"]}
    for s in skipped:
        assert s["heading_candidate"] not in emitted_labels
        assert s["reason"]
        assert s["offset"] >= 0


def test_subtopics_deterministic(subtopics):
    from tere4ai.align_hleg_altai.hleg_subtopics import build_hleg_subtopics

    assert build_hleg_subtopics() == subtopics


# ---------------------------------------------------------------------------
# Cross-cutting: determinism, provenance, schema, gates, no model calls
# ---------------------------------------------------------------------------


def test_enrichment_chain_is_deterministic(dump):
    second = _build()

    def strip(d):
        d = json.loads(json.dumps(d))
        d["build"].pop("built_at", None)
        return d

    assert strip(dump) == strip(second)


def test_every_new_edge_has_full_provenance(dump):
    build_id = dump["build"]["build_id"]
    new_types = {"HAS_SUBPARAGRAPH", "DEFINES_TERM", "CONTEXT_FOR"}
    seen = set()
    for e in dump["edges"]:
        if e["edge_type"] not in new_types:
            continue
        seen.add(e["edge_type"])
        assert e["provenance_class"] in ("EXTRACTED_SOURCE", "RESOLVED_DETERMINISTIC")
        assert e.get("source_span_id") or e.get("derivation_id"), e["edge_id"]
        assert e["confidence"] == 1.0
        assert e["review_status"] == "auto_accepted"
        assert e["build_id"] == build_id
    assert seen == new_types


def test_enriched_dump_validates_against_schema(dump):
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


def test_published_dump_passes_gates_with_new_features():
    from tere4ai.validate_graph.gates import validate_build

    dump_path = ROOT / "data" / "graph_dumps" / "layer1.json"
    if not dump_path.exists():
        pytest.skip("published dump not present")
    published = json.loads(dump_path.read_text(encoding="utf-8"))
    types = {n["type"] for n in published["nodes"]}
    assert {"Definition", "Subparagraph"} <= types
    edge_types = {e["edge_type"] for e in published["edges"]}
    assert {"HAS_SUBPARAGRAPH", "DEFINES_TERM", "CONTEXT_FOR"} <= edge_types
    report = validate_build(published)
    assert report.passed, report.failures[:5]
    assert report.stats["orphans"] == 0


def test_no_model_calls_in_new_modules():
    modules = (
        "parse_legal_structure/definitions.py",
        "parse_legal_structure/subparagraphs.py",
        "parse_legal_structure/recital_links.py",
        "align_hleg_altai/hleg_subtopics.py",
    )
    for mod in modules:
        src = (ROOT / "src" / "tere4ai" / mod).read_text(encoding="utf-8")
        for banned in ("openai", "anthropic", "litellm"):
            assert banned not in src, f"{mod} must stay deterministic (DEC-01/DEC-05)"

"""Formex 4 enrichment acceptance fixtures (DEC-01 partial, M2 point depth).

Covers the Point and AnnexItem granularity parsed deterministically from the
frozen Formex fmx4 member files (docs/architecture.md Section 6, ingestion
route b) on top of the HTML-derived Layer 1 dump.

Observed exact counts (frozen snapshots, asserted for determinism):
  - 467 Point nodes. The main body holds 648 NP elements; 180 of them are
    the recital markers in the preamble (GR.CONSID, already Recital nodes
    from the HTML parse) and 1 sits inside QUOT.S (quoted text of an
    amended act), leaving 467 article points including nested romanettes.
  - 217 AnnexItem nodes across all 13 annexes (201 numbered or lettered NP
    items plus the 16 unnumbered dash items of Annex II).
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshots" / "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"
FORMEX_DIR = ROOT / "data" / "snapshots" / "formex"
MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"

pytestmark = pytest.mark.skipif(
    not (SNAPSHOT.exists() and FORMEX_DIR.is_dir()),
    reason="frozen snapshots not present",
)

EXPECTED_POINTS = 467
EXPECTED_ANNEX_ITEMS = 217


@pytest.fixture(scope="module")
def dump():
    from tere4ai.parse_legal_structure.formex import enrich_with_formex
    from tere4ai.parse_legal_structure.parser import parse_snapshot
    from tere4ai.resolve_crossrefs.resolver import resolve

    return resolve(enrich_with_formex(parse_snapshot(SNAPSHOT), FORMEX_DIR, MANIFEST))


@pytest.fixture(scope="module")
def by_id(dump):
    return {n["id"]: n for n in dump["nodes"]}


def _nodes(dump, node_type):
    return [n for n in dump["nodes"] if n["type"] == node_type]


def test_article_5_1_point_c_exists(by_id):
    point = by_id.get("eu-ai-act:article-5:paragraph-1:point-c")
    assert point is not None
    assert point["type"] == "Point"
    assert point["layer"] == 1
    assert point["marker"] == "c"
    assert point["text"].strip()


def test_article_5_1_point_c_nested_romanettes(dump, by_id):
    for marker in ("i", "ii"):
        nested = by_id.get(f"eu-ai-act:article-5:paragraph-1:point-c:point-{marker}")
        assert nested is not None, marker
        assert nested["type"] == "Point"
        assert nested["marker"] == marker
        assert nested["text"].strip()
    edges = {
        (e["from"], e["to"]) for e in dump["edges"] if e["edge_type"] == "HAS_POINT"
    }
    parent = "eu-ai-act:article-5:paragraph-1:point-c"
    assert ("eu-ai-act:article-5:paragraph-1", parent) in edges
    assert (parent, f"{parent}:point-i") in edges


def test_annex_iii_point_5_and_5a(by_id):
    p5 = by_id.get("eu-ai-act:annex-iii:point-5")
    assert p5 is not None and p5["type"] == "AnnexItem" and p5["marker"] == "5"
    p5a = by_id.get("eu-ai-act:annex-iii:point-5:a")
    assert p5a is not None and p5a["type"] == "AnnexItem" and p5a["marker"] == "a"
    assert p5a["text"].startswith("AI systems intended to be used by public authorities")


def test_exact_counts_for_determinism(dump):
    assert len(_nodes(dump, "Point")) == EXPECTED_POINTS
    assert len(_nodes(dump, "AnnexItem")) == EXPECTED_ANNEX_ITEMS


def test_every_point_and_item_span_matches_manifest(dump):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    shas = {e["file"]: e["sha256"] for e in manifest["snapshots"]}
    for node in _nodes(dump, "Point") + _nodes(dump, "AnnexItem"):
        span = node.get("source_span")
        assert span, node["id"]
        assert span["snapshot_file"].startswith("formex/"), node["id"]
        assert span["snapshot_sha256"] == shas[span["snapshot_file"]], node["id"]
        assert 0 <= span["start"] < span["end"], node["id"]


def test_all_13_annexes_have_items(dump):
    romans = [
        "i", "ii", "iii", "iv", "v", "vi", "vii",
        "viii", "ix", "x", "xi", "xii", "xiii",
    ]
    per_annex = {r: 0 for r in romans}
    for node in _nodes(dump, "AnnexItem"):
        per_annex[node["id"].split(":")[1].removeprefix("annex-")] += 1
    for roman in romans:
        assert per_annex[roman] > 0, f"annex {roman} has no items"


def test_annex_iii_and_iv_spot_checks(dump, by_id):
    annex_iii_markers = {
        n["marker"]
        for n in _nodes(dump, "AnnexItem")
        if n["id"].startswith("eu-ai-act:annex-iii:") and ":point-" in n["id"]
        and n["id"].count(":") == 2
    }
    assert "5" in annex_iii_markers
    assert {"1", "2", "3", "4", "6", "7", "8"} <= annex_iii_markers
    # Annex IV has numbered top-level items 1 to 9.
    for k in range(1, 10):
        assert f"eu-ai-act:annex-iv:point-{k}" in by_id, k


def test_hierarchy_edges_carry_full_provenance(dump):
    build_id = dump["build"]["build_id"]
    formex_edges = [
        e for e in dump["edges"] if e["edge_type"] in ("HAS_POINT", "HAS_ANNEX_ITEM")
    ]
    assert len(formex_edges) == EXPECTED_POINTS + EXPECTED_ANNEX_ITEMS
    ids = {n["id"] for n in dump["nodes"]}
    spans = {
        n["source_span"]["span_id"]: n["id"]
        for n in dump["nodes"]
        if n.get("source_span")
    }
    for e in formex_edges:
        assert e["provenance_class"] == "EXTRACTED_SOURCE"
        assert e["method"] == "formex_structure"
        assert e["confidence"] == 1.0
        assert e["review_status"] == "auto_accepted"
        assert e["build_id"] == build_id
        assert e["from"] in ids, e["edge_id"]
        assert e["to"] in ids, e["edge_id"]
        # source_span_id is the span of the child node.
        assert spans.get(e["source_span_id"]) == e["to"], e["edge_id"]


def test_points_attach_to_existing_html_paragraphs(dump, by_id):
    for e in dump["edges"]:
        if e["edge_type"] != "HAS_POINT":
            continue
        parent = by_id[e["from"]]
        assert parent["type"] in ("Paragraph", "Point"), e["edge_id"]


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


def test_enrichment_is_deterministic(dump):
    from tere4ai.parse_legal_structure.formex import enrich_with_formex
    from tere4ai.parse_legal_structure.parser import parse_snapshot
    from tere4ai.resolve_crossrefs.resolver import resolve

    second = resolve(enrich_with_formex(parse_snapshot(SNAPSHOT), FORMEX_DIR, MANIFEST))

    def strip(d):
        d = json.loads(json.dumps(d))
        d["build"].pop("built_at", None)
        return d

    assert strip(dump) == strip(second)


def test_no_model_calls_in_formex_module():
    src = (ROOT / "src" / "tere4ai" / "parse_legal_structure" / "formex.py").read_text(
        encoding="utf-8"
    )
    for banned in ("openai", "anthropic", "litellm"):
        assert banned not in src, "formex.py must stay deterministic (DEC-01)"


def test_checksum_mismatch_fails_loudly(tmp_path):
    from tere4ai.parse_legal_structure.formex import MAIN_BODY_FILE, enrich_with_formex
    from tere4ai.parse_legal_structure.parser import parse_snapshot

    bad_dir = tmp_path / "formex"
    bad_dir.mkdir()
    for path in FORMEX_DIR.iterdir():
        (bad_dir / path.name).write_bytes(path.read_bytes())
    tampered = bad_dir / MAIN_BODY_FILE
    tampered.write_bytes(tampered.read_bytes() + b" ")

    dump = parse_snapshot(SNAPSHOT)
    with pytest.raises(ValueError, match="checksum mismatch"):
        enrich_with_formex(dump, bad_dir, MANIFEST)

"""Versioning test for DEC-12 (architecture.md Section 11 version pin)."""

from pathlib import Path

from tere4ai.ingest.sources import BASE_ACT_ID, OMNIBUS_ID, layer0

MANIFEST = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "MANIFEST.json"


def test_version_pin_nodes_and_edges():
    nodes, edges = layer0("build-test", MANIFEST)
    by_id = {n["id"]: n for n in nodes}

    base = by_id[BASE_ACT_ID]
    omnibus = by_id[OMNIBUS_ID]
    assert base["legal_status"] == "in_force"
    assert omnibus["legal_status"] == "in_force"
    assert omnibus["merged_into_base"] is False

    edge_types = {(e["edge_type"], e["from"], e["to"]) for e in edges}
    assert ("AMENDS", OMNIBUS_ID, BASE_ACT_ID) in edge_types
    assert ("HAS_VERSION", BASE_ACT_ID, OMNIBUS_ID) in edge_types

    # every snapshot in the manifest becomes a SourceFile with a checksum
    files = [n for n in nodes if n["type"] == "SourceFile"]
    assert files, "manifest snapshots must appear as SourceFile nodes"
    assert all(len(f["sha256"]) == 64 for f in files)

    # no edge without provenance (architecture.md Section 2)
    assert all(e.get("derivation_id") or e.get("source_span_id") for e in edges)


def test_omnibus_never_merged_into_base():
    nodes, _ = layer0("build-test", MANIFEST)
    base = next(n for n in nodes if n["id"] == BASE_ACT_ID)
    # the base act text status stays in_force; the omnibus stays a distinct source
    assert base["legal_status"] == "in_force"
    assert not any(
        n["id"] == BASE_ACT_ID and "omnibus" in n.get("title", "").lower() for n in nodes
    )


def test_omnibus_snapshot_derives_from_omnibus_source():
    """B59: the frozen Omnibus text manifests the amending instrument, not
    the base Act; every other snapshot keeps the base-act linkage."""
    nodes, edges = layer0("build-test", MANIFEST)
    omnibus_files = [
        n["id"]
        for n in nodes
        if n["type"] == "SourceFile" and "omnibus" in n["file"]
    ]
    assert omnibus_files, "the Omnibus snapshot must be in the manifest"
    derived = {
        (e["from"], e["to"]) for e in edges if e["edge_type"] == "DERIVED_FROM_SOURCE"
    }
    for file_id in omnibus_files:
        assert (file_id, OMNIBUS_ID) in derived
        assert (file_id, BASE_ACT_ID) not in derived


NEW_SOURCES = {
    # file under data/snapshots: (sha256, source_document, legal_status)
    "formex/eu_ai_act_consolidated_02024R1689-20260727_fmx4_2026-10-03.zip": (
        "655c4c6c957d1484426e1eb859a4fc65ad58978c1edd4d3a936fee87e4bf153b", "eu-ai-act-consolidated", "non_binding"),
    "formex/CL2024R1689EN0010010.0001.xml": (
        "dfeac37ec03557cfe751427429c6314c11792f88bf654a381484e5c7239f7893", "eu-ai-act-consolidated", "non_binding"),
    "formex/CL2024R1689EN0010010.0001.doc.xml": (
        "6e9ad69c9dc5afabbe9705021c0617630ee65c949cc4f051a7f273abf97a449b", "eu-ai-act-consolidated", "non_binding"),
    "eu_ai_act_consolidated_02024R1689-20260727_eurlex_xhtml_2026-10-03.html": (
        "5e7719f77e8a606b257dc25958ee3222c4383300a5a34270a5b850a2ce8b8715", "eu-ai-act-consolidated", "non_binding"),
    "formex/digital_omnibus_ai_32026R1744_fmx4_2026-10-03.zip": (
        "769abda7d6eed642d298afa2b878159e9c27957fc6f2d0e70b5006d860508145", "omnibus", "in_force"),
    "formex/L_202601744EN.000101.fmx.xml": (
        "301232bf667c2a9dd61cfc28cab6be3facc665bb8adbf183aebd366334cfab1f", "omnibus", "in_force"),
    "formex/L_202601744EN.003601.fmx.xml": (
        "02aceebd7e71daf1a099451869ec5946e5dd2fd199f1111b1b1def15a434f91e", "omnibus", "in_force"),
    "formex/L_202601744EN.doc.fmx.xml": (
        "d1cb1db20b659eec151a7986f73c8eab69e274a2332c45a21e37ff91ac54e4f6", "omnibus", "in_force"),
    "formex/L_202601744EN.toc.fmx.xml": (
        "bc763b15f85079eb9eed75cd8508b885223a13bc586250a285192ead7a491df2", "omnibus", "in_force"),
}


def test_the_omnibus_and_the_consolidated_text_are_frozen_with_their_status():
    """B132 (spec G D-G68 (5)): Layer 0 freezes both in Formex, each with its
    sha256 and legal status; the consolidated text is non_binding."""
    import hashlib
    import json

    manifest = {e["file"]: e for e in json.loads(MANIFEST.read_text(encoding="utf-8"))["snapshots"]}
    for file, (sha256, document, status) in NEW_SOURCES.items():
        entry = manifest[file]
        assert entry["sha256"] == sha256, file
        assert hashlib.sha256((MANIFEST.parent / file).read_bytes()).hexdigest() == sha256, file
        assert (entry["source_document"], entry["legal_status"], entry["language"]) == (document, status, "en"), file
        assert entry["celex"] == ("02024R1689-20260727" if document == "eu-ai-act-consolidated" else "32026R1744")
        assert entry["cellar_work_uuid"] and entry["eli"] and entry["retrieved_at"] == "2026-10-03", file
        if document == "eu-ai-act-consolidated":
            assert "This text is meant purely as a documentation tool and has no legal effect" in entry["notes"]


def test_the_consolidated_text_is_its_own_non_binding_source():
    from tere4ai.ingest.sources import CONSOLIDATED_ID

    nodes, edges = layer0("build-test", MANIFEST)
    by_id = {n["id"]: n for n in nodes}
    consolidated = by_id[CONSOLIDATED_ID]
    assert (consolidated["legal_status"], consolidated["celex"]) == ("non_binding", "02024R1689-20260727")
    assert "documentation tool and has no legal effect" in consolidated["notes"]
    derived = {(e["from"], e["to"]) for e in edges if e["edge_type"] == "DERIVED_FROM_SOURCE"}
    assert ("srcfile:formex/CL2024R1689EN0010010.0001.xml", CONSOLIDATED_ID) in derived
    assert ("srcfile:formex/L_202601744EN.000101.fmx.xml", OMNIBUS_ID) in derived
    assert ("srcfile:formex/L_202401689EN.000101.fmx.xml", BASE_ACT_ID) in derived


def test_the_guidelines_are_their_own_non_binding_source_document():
    """B143 (spec G D-G75 (4)): guidance, not law, with its DOI; no versioning edge."""
    from tere4ai.ingest.sources import HLEG_ID

    nodes, edges = layer0("build-test", MANIFEST)
    hleg = next(n for n in nodes if n["id"] == HLEG_ID)
    assert (hleg["type"], hleg["layer"], hleg["legal_status"], hleg["doi"]) == (
        "SourceDocument", 0, "non_binding", "10.2759/346720")
    assert hleg["title"] == "Ethics Guidelines for Trustworthy AI (High-Level Expert Group on Artificial Intelligence, 2019)"
    for words in ("978-92-76-11998-2", "KK-02-19-841-EN-N", "d3988569-0434-11ea-8c1f-01aa75ed71a1", "guidance, not law"):
        assert words in hleg["notes"].lower() or words in hleg["notes"]
    assert not [e for e in edges if e["edge_type"] in ("AMENDS", "HAS_VERSION") and HLEG_ID in (e["from"], e["to"])]


def test_the_hleg_files_belong_to_the_guidelines_and_not_to_the_act():
    from tere4ai.ingest.hleg_text import PDF_FILE, RECORD_FILE, TEXT_FILE
    from tere4ai.ingest.sources import HLEG_ID

    _, edges = layer0("build-test", MANIFEST)
    derived = {(e["from"], e["to"]) for e in edges if e["edge_type"] == "DERIVED_FROM_SOURCE"}
    for name in (PDF_FILE, TEXT_FILE, RECORD_FILE):
        assert (f"srcfile:{name}", HLEG_ID) in derived
        assert (f"srcfile:{name}", BASE_ACT_ID) not in derived
    made = [(e["from"], e["to"], e["method"], e["build_id"]) for e in edges if e["edge_type"] == "DERIVED_FROM"]
    assert sorted(made) == sorted([(f"srcfile:{TEXT_FILE}", f"srcfile:{PDF_FILE}", "hleg_text_derivation_v1", "build-test"),
                                   (f"srcfile:{RECORD_FILE}", f"srcfile:{PDF_FILE}", "hleg_text_derivation_v1", "build-test")])


def test_every_source_document_value_of_the_manifest_is_named():
    import json

    from tere4ai.ingest.sources import SOURCE_DOCUMENT_IDS

    values = {e["source_document"] for e in json.loads(MANIFEST.read_text(encoding="utf-8"))["snapshots"]}
    assert values == set(SOURCE_DOCUMENT_IDS) == {"eu-ai-act", "omnibus", "eu-ai-act-consolidated", "hleg-ethics-guidelines"}


def test_an_unknown_source_document_stops_layer0(tmp_path):
    import json

    import pytest

    path = tmp_path / "MANIFEST.json"
    path.write_text(json.dumps({"snapshots": [{"file": "x.pdf", "sha256": "0" * 64, "source_document": "altai"}]}))
    with pytest.raises(ValueError, match=r"x\.pdf: source_document 'altai' is not one layer0\(\) knows"):
        layer0("build-test", path)


def test_layer0s_edges_and_hleg_nodes_validate_and_the_schema_has_the_doi():
    """Review I4: the edges (DERIVED_FROM included) and the four HLEG nodes validate; the
    other SourceFile ids (upper case, "/") break nodeId's pattern since before B143, outside
    this card. The SourceDocument branch allows extra properties, so the doi property is
    checked in the schema itself."""
    import json
    import re

    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from tere4ai.ingest.hleg_text import PDF_FILE, RECORD_FILE, TEXT_FILE
    from tere4ai.ingest.sources import HLEG_ID

    root = MANIFEST.parents[2] / "schema" / "json_schemas"
    schemas = {n: json.loads((root / f"{n}.schema.json").read_text(encoding="utf-8")) for n in ("nodes", "edges")}
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())
    nodes, edges = layer0("build-test", MANIFEST)
    edge_validator = Draft202012Validator(schemas["edges"], registry=registry)
    assert [list(edge_validator.iter_errors(e)) for e in edges] == [[] for _ in edges]
    assert any(e["edge_type"] == "DERIVED_FROM" for e in edges), "the edges checked hold a DERIVED_FROM edge"
    hleg_ids = {HLEG_ID, *(f"srcfile:{name}" for name in (PDF_FILE, TEXT_FILE, RECORD_FILE))}
    node_validator = Draft202012Validator(schemas["nodes"], registry=registry)
    hleg_nodes = [n for n in nodes if n["id"] in hleg_ids]
    assert len(hleg_nodes) == 4 and [list(node_validator.iter_errors(n)) for n in hleg_nodes] == [[]] * 4
    branch = next(b for b in schemas["nodes"]["oneOf"] if b["properties"]["type"].get("const") == "SourceDocument")
    doi = branch["properties"]["doi"]
    assert doi["type"] == "string" and re.fullmatch(doi["pattern"], "10.2759/346720")


def test_the_legal_status_notes_name_the_guidelines():
    """Review M6: coverage_report and source_trace list every SourceDocument (tools.py:233)."""
    from tere4ai.mcp_server.tools import _legal_status_notes

    nodes, _ = layer0("build-test", MANIFEST)
    assert "src:hleg:ethics-guidelines-2019: legal_status non_binding" in _legal_status_notes(nodes)


def test_the_comment_no_longer_promises_an_hleg_node_at_layer3_publication():
    source = (MANIFEST.parents[2] / "src" / "tere4ai" / "ingest" / "sources.py").read_text(encoding="utf-8")
    assert "only exists at Layer 3 publication" not in source and "keeps the historical base-act linkage" not in source


def test_the_manifest_lists_31_files_three_of_them_the_guidelines():
    import json

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["snapshots"]
    assert len(entries) == 31
    assert sorted(e["file"] for e in entries if e["source_document"] == "hleg-ethics-guidelines") == [
        "hleg_ethics_guidelines_2019_en.pdf", "hleg_ethics_guidelines_2019_en_requirements.txt",
        "hleg_ethics_guidelines_2019_en_requirements_derivation.json"]

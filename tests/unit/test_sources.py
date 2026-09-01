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

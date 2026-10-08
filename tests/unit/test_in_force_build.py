"""The build of the Act in force: build id, Layer 0 merge record and gates PUBLICATION_GATE1, PUBLICATION_GATE2, PUBLICATION_GATE6 (B132, DEC-23).

Spec G D-G68 (5): the build id is a digest over every frozen legal source
the parse reads; the Omnibus SourceDocument says merged_into_base true with
the date and the reviewed marker list's digest; gate PUBLICATION_GATE6 lets the merge
through only with the record of every check, PUBLICATION_GATE1 reaches the earlier
versions through HAS_VERSION and PUBLICATION_GATE2 refuses a span id shared by an in-force
node and a version node. Builds into a temporary file; no model.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from tere4ai.ingest.sources import CONSOLIDATED_ID, OMNIBUS_ID, layer0
from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.consolidated import (
    CONSOLIDATED_REL,
    build_in_force_dump,
    legal_sources_digest,
)
from tere4ai.parse_legal_structure.parser import build_layer1
from tere4ai.resolve_crossrefs.resolver import resolve
from tere4ai.validate_graph.gates import validate_build

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"
pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "snapshots" / CONSOLIDATED_REL).is_file(), reason="consolidated Formex not frozen"
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return resolve(build_layer1(tmp_path_factory.mktemp("parse") / "layer1.json", MANIFEST))


def _omnibus(dump):
    return next(n for n in dump["nodes"] if n["id"] == OMNIBUS_ID)


def test_the_build_passes_every_gate(built):
    report = validate_build(built)
    assert report.passed, report.failures[:5]
    assert report.stats["orphans"] == 0


def test_the_build_id_covers_every_frozen_legal_source(built):
    files = {s["file"] for s in built["build"]["snapshots"]}
    assert {"eu_ai_act_32024R1689_eurlex_html_2026-07-08.html", "formex/L_202401689EN.000101.fmx.xml",
            CONSOLIDATED_REL, "formex/L_202601744EN.000101.fmx.xml", "formex/L_202601744EN.003601.fmx.xml"} <= files
    assert len(files) == 19  # the HTML, 15 Formex files of 2024, the consolidated file, 2 Omnibus files
    digest = legal_sources_digest([(s["file"], s["sha256"]) for s in built["build"]["snapshots"]])
    assert built["build"]["build_id"] == f"build-{digest[:12]}"
    assert built["build"]["build_id"] != "build-3b753e5e9297"  # the 2024-only build


def test_the_omnibus_is_merged_with_the_marker_lists_digest(built):
    omnibus = _omnibus(built)
    digest = hashlib.sha256(amend.DEFAULT_MARKER_LIST_PATH.read_bytes()).hexdigest()
    assert (omnibus["merged_into_base"], omnibus["merged_on"], omnibus["marker_list_sha256"]) == (
        True, "2026-07-27", digest)
    assert built["build"]["amendments"] == {
        "marker_list": "data/amendments/omnibus_markers.json", "marker_list_sha256": digest,
        "markers_read": 77, "markers_checked": 77, "units_checked": 1603, "units_failed": 0,
        "exception_rows": [f"E{i}" for i in range(1, 10)],
        # final review M1: the exception list and the inventory the checks read, by digest
        "exceptions_sha256": hashlib.sha256(amend.DEFAULT_EXCEPTIONS_PATH.read_bytes()).hexdigest(),
        "inventory_sha256": hashlib.sha256(amend.DEFAULT_INVENTORY_PATH.read_bytes()).hexdigest(),
    }
    consolidated = next(n for n in built["nodes"] if n["id"] == CONSOLIDATED_ID)
    assert consolidated["legal_status"] == "non_binding"


def test_layer0_without_the_marker_list_keeps_the_omnibus_apart():
    nodes, _ = layer0("build-test", MANIFEST)
    assert next(n for n in nodes if n["id"] == OMNIBUS_ID)["merged_into_base"] is False


def test_publication_gate6_refuses_a_merge_without_the_record_of_its_checks(built):
    dump = copy.deepcopy(built)
    dump["build"].pop("amendments")
    assert any("PUBLICATION_GATE6" in f and "silent replacement" in f for f in validate_build(dump).failures)


def test_publication_gate6_refuses_another_marker_list(built):
    dump = copy.deepcopy(built)
    _omnibus(dump)["marker_list_sha256"] = "0" * 64
    assert any("PUBLICATION_GATE6" in f and "marker list" in f for f in validate_build(dump).failures)


def test_publication_gate6_refuses_unchecked_markers_or_units(built):
    dump = copy.deepcopy(built)
    dump["build"]["amendments"]["markers_checked"] = 76
    dump["build"]["amendments"]["units_checked"] = 1602
    failures = validate_build(dump).failures
    assert any("PUBLICATION_GATE6" in f and "not every change marker" in f for f in failures)
    assert any("PUBLICATION_GATE6" in f and "units checked" in f for f in failures)


def test_publication_gate6_refuses_changed_units_under_an_omnibus_kept_apart(built):
    dump = copy.deepcopy(built)
    _omnibus(dump)["merged_into_base"] = False
    assert any("PUBLICATION_GATE6" in f and "merged_into_base is False" in f for f in validate_build(dump).failures)


def test_publication_gate6_refuses_an_amended_dump_without_the_omnibus(built):
    """Final review F5 (Codex P2): with the Omnibus SourceDocument, its edges and the
    build's amendment record removed, the units it changed are still in the dump."""
    dump = copy.deepcopy(built)
    dump["nodes"] = [n for n in dump["nodes"] if n["id"] != OMNIBUS_ID]
    dump["edges"] = [e for e in dump["edges"] if OMNIBUS_ID not in (e["from"], e["to"])]
    dump["build"].pop("amendments")
    failures = validate_build(dump).failures
    assert any("PUBLICATION_GATE6" in f and "no Omnibus SourceDocument" in f for f in failures), failures
    assert any("PUBLICATION_GATE6" in f and "no amendment checks" in f for f in failures)


@pytest.mark.parametrize("change", ["missing", "binding"])
def test_publication_gate6_refuses_a_merge_without_the_non_binding_consolidated_text(built, change):
    """Final review M11: the consolidated text must be a SourceDocument marked non_binding."""
    dump = copy.deepcopy(built)
    if change == "missing":
        dump["nodes"] = [n for n in dump["nodes"] if n["id"] != CONSOLIDATED_ID]
    else:
        next(n for n in dump["nodes"] if n["id"] == CONSOLIDATED_ID)["legal_status"] = "in_force"
    assert any("PUBLICATION_GATE6 the consolidated text is missing or not marked non_binding" in f
               for f in validate_build(dump).failures)


def test_publication_gate6_refuses_an_omnibus_that_does_not_say_whether_it_is_merged(built):
    """Final review M11: an Omnibus SourceDocument without merged_into_base."""
    dump = copy.deepcopy(built)
    _omnibus(dump).pop("merged_into_base")
    assert any("PUBLICATION_GATE6" in f and "does not say whether it is merged" in f for f in validate_build(dump).failures)


def test_publication_gate1_reaches_the_earlier_versions_through_has_version(built):
    dump = copy.deepcopy(built)
    dump["edges"] = [e for e in dump["edges"] if e["edge_type"] != "HAS_VERSION"]
    assert any("PUBLICATION_GATE1" in f and "version:2024-07-12:eu-ai-act:" in f for f in validate_build(dump).failures)


def test_a_version_span_never_shares_an_in_force_span_id(built):
    """Review focus 2: span lookup returns the first match."""
    dump = copy.deepcopy(built)
    version = next(n for n in dump["nodes"] if n["id"] == "version:2024-07-12:eu-ai-act:article-10:paragraph-5")
    version["source_span"]["span_id"] = "span:009.001"
    assert any("PUBLICATION_GATE2" in f and "span:009.001" in f for f in validate_build(dump).failures)


def test_a_stale_marker_list_stops_the_parse(tmp_path):
    stale = tmp_path / "omnibus_markers.json"
    stale.write_text("{}\n", encoding="utf-8")
    with pytest.raises(amend.AmendmentCheckError, match="omnibus_markers.json differs"):
        build_in_force_dump(MANIFEST, marker_list_path=stale)


def test_the_build_block_records_the_hleg_checks(built):
    hleg = built["build"]["hleg"]
    assert hleg["checks_passed"] == ["C0", "C1", "C2", "C3", "C4"]
    assert hleg["derived_text"]["file"] == "hleg_ethics_guidelines_2019_en_requirements.txt"
    assert (hleg["exclusions_reviewed"], len(hleg["word_rows_used"])) == (39, 13)


def test_the_build_id_does_not_cover_the_hleg_files(built):
    assert not [s for s in built["build"]["snapshots"] if s["file"].startswith("hleg_")]


def _snapshots_with_altered_hleg_text(tmp_path):
    """A copy of data/snapshots (links, so nothing large is copied) whose derived HLEG
    text has one word changed and whose manifest carries the changed file's sha256."""
    import json

    from tere4ai.ingest import hleg_text as ht

    folder = tmp_path / "snapshots"
    folder.mkdir()
    for item in MANIFEST.parent.iterdir():
        if item.name not in ("MANIFEST.json", ht.TEXT_FILE):
            (folder / item.name).symlink_to(item)
    text = (MANIFEST.parent / ht.TEXT_FILE).read_bytes().replace(b"Redress. When", b"Redress. Where", 1)
    (folder / ht.TEXT_FILE).write_bytes(text)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["snapshots"]:
        if entry["file"] == ht.TEXT_FILE:
            entry["sha256"] = hashlib.sha256(text).hexdigest()
    (folder / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder / "MANIFEST.json"


def test_an_altered_hleg_text_stops_the_parse_before_any_node(tmp_path):
    from tere4ai.ingest.hleg_checks import HlegCheckError

    with pytest.raises(HlegCheckError, match=r"^C0 failed: C0 hleg_ethics_guidelines_2019_en_requirements.txt differs"):
        build_in_force_dump(_snapshots_with_altered_hleg_text(tmp_path))

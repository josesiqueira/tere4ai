"""Layer 1 of the AI Act in force: the consolidated Formex, checked, with the 2024 wording kept.

@implements: DEC-01 (partial: the in-force parse)
@implements: DEC-12
@grounded_by: REF-01, REF-02, REF-03, REF-04, REF-05

Spec G D-G68: every build is made from Regulation (EU) 2024/1689 as amended
by Regulation (EU) 2026/1744. build_in_force_dump reads the frozen sources
listed in data/snapshots/MANIFEST.json (each checked against its sha256),
reads the units of the consolidated text and of the 2024 Formex
(units.py), derives and checks every change (amendments.py; a failure
stops the parse with AmendmentCheckError) and returns the Layer 0 and
Layer 1 nodes and edges before definitions, cross-references and recital
links are added:

- every unit of the consolidated text as a node with its id, its span in
  the consolidated file (span names as before: span:005.001), its text or
  title, enacted_by ("Regulation (EU) 2024/1689", "Regulation (EU)
  2026/1744, Article 1, point (9)(a)" or "composed" for a container whose
  children come from both acts) and amendment (unchanged, replaced,
  inserted, composed). A span over wording the Omnibus deleted, which the
  consolidated file keeps in place, lists that range under exclude, and
  the node's text leaves it out (Article 10 without paragraph 5);
- a deleted unit (and every unit inside its range) as a node with its id
  and number, amendment "deleted", deleted_by and deleted_from, no text
  and no span; its hierarchy edge carries a derivation id;
- the 180 recitals from the 2024 act's EUR-Lex HTML, unchanged (the
  consolidated text leaves the preamble out);
- for each replaced or deleted unit and each composed container, its 2024
  wording as a UnitVersion node (id version:2024-07-12:<unit id>, span
  span:<name>@2024-07-12 in the 2024 Formex file), linked by HAS_VERSION;
  UnitVersion is not a unit type, so nothing that walks the unit types
  meets it.

The build id is build-<12 hex> of a sha256 over every frozen legal source
the parse reads (legal_sources_digest), so a build with the Omnibus and one
without it never share an id. Deterministic, no model calls (DEC-01).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.formex import DOC_FILE, MAIN_BODY_FILE, _annex_order_from_doc
from tere4ai.parse_legal_structure.parser import (
    DEFAULT_MANIFEST_PATH,
    REGULATION_ID,
    REGULATION_TITLE,
    TERE4AI_VERSION,
    _hierarchy_edge,
    parse_snapshot,
)
from tere4ai.parse_legal_structure.units import UnitTree, formex_text, read_text_units

HTML_FILE = "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"
CONSOLIDATED_REL = "formex/CL2024R1689EN0010010.0001.xml"
OMNIBUS_MAIN_REL = "formex/L_202601744EN.000101.fmx.xml"
OMNIBUS_ANNEX_REL = "formex/L_202601744EN.003601.fmx.xml"
DELETED_METHOD = "omnibus_deleted_unit_v1"
VERSION_METHOD = "omnibus_version_v1"


@dataclass
class Sources:
    """The frozen files of MANIFEST.json, each read only after its sha256 is checked."""

    snapshots_dir: Path
    shas: dict[str, str]

    def read(self, rel: str) -> str:
        if rel not in self.shas:
            raise ValueError(f"{rel} is not listed in MANIFEST.json")
        raw = (self.snapshots_dir / rel).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != self.shas[rel]:
            raise ValueError(f"snapshot checksum mismatch for {rel}: manifest {self.shas[rel]}, file {actual}")
        return raw.decode("utf-8")


def read_sources(manifest_path: Path | str = DEFAULT_MANIFEST_PATH) -> Sources:
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return Sources(manifest_path.parent, {e["file"]: e["sha256"] for e in manifest["snapshots"]})


def legal_sources_digest(files: list[tuple[str, str]]) -> str:
    """sha256 over "<file> <sha256>" lines, sorted: the base of the build id (D-G68 (5))."""
    return hashlib.sha256("\n".join(f"{f} {s}" for f, s in sorted(files)).encode("utf-8")).hexdigest()


def read_trees(sources: Sources) -> tuple[UnitTree, UnitTree, list[str]]:
    """(the consolidated units, the 2024 units, the 2024 Formex files read), every file checked."""
    annex_files = _annex_order_from_doc(sources.read(f"formex/{DOC_FILE}"))
    baseline = UnitTree()
    for name in [MAIN_BODY_FILE, *annex_files]:
        read_text_units(sources.read(f"formex/{name}"), f"formex/{name}", baseline)
    consolidated = read_text_units(sources.read(CONSOLIDATED_REL), CONSOLIDATED_REL)
    return consolidated, baseline, [f"formex/{n}" for n in [MAIN_BODY_FILE, DOC_FILE, *annex_files]]


def checked_amendments(sources: Sources, consolidated: UnitTree, baseline: UnitTree,
                       exceptions_path: Path | str = amend.DEFAULT_EXCEPTIONS_PATH,
                       inventory_path: Path | str = amend.DEFAULT_INVENTORY_PATH) -> tuple[amend.Amendments, list]:
    """Derive every change and run every check; raises AmendmentCheckError on any failure."""
    rows = amend.load_exceptions(exceptions_path)
    cons_text = consolidated.texts[CONSOLIDATED_REL]
    changes = amend.derive_changes(consolidated, baseline, amend.read_markers(cons_text), rows)
    quotations = amend.read_quotations(sources.read(OMNIBUS_MAIN_REL))
    inventory = amend.read_inventory(Path(inventory_path).read_text(encoding="utf-8"))
    failures = amend.check_markers(changes, consolidated, baseline, cons_text, quotations, inventory, rows,
                                   sources.read(OMNIBUS_ANNEX_REL))
    failures += amend.check_units(changes, consolidated, baseline, cons_text, quotations, rows)
    failures += amend.stale_rows(changes, rows)
    if failures:
        raise amend.AmendmentCheckError(failures)
    return changes, rows


def current_marker_list(sources: Sources, changes: amend.Amendments, rows: list) -> dict[str, Any]:
    return amend.marker_list(
        changes, rows,
        {"file": CONSOLIDATED_REL, "sha256": sources.shas[CONSOLIDATED_REL]},
        {"file": OMNIBUS_MAIN_REL, "sha256": sources.shas[OMNIBUS_MAIN_REL]},
    )


def marker_list_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _deleted_edge(edge_type: str, parent: str, unit_id: str, point: str, build_id: str) -> dict[str, Any]:
    """A deleted unit's hierarchy edge: no span to cite, so a derivation id names the
    Omnibus point (point (9)(b) -> derivation:omnibus:article-1:point-9-b)."""
    return {
        "edge_id": f"edge:{edge_type.lower()}:{unit_id}",
        "edge_type": edge_type,
        "from": parent,
        "to": unit_id,
        "provenance_class": "EXTRACTED_SOURCE",
        "derivation_id": f"derivation:omnibus:article-1:point-{'-'.join(re.findall(r'[0-9a-z]+', point))}",
        "method": DELETED_METHOD,
        "confidence": 1.0,
        "review_status": "auto_accepted",
        "build_id": build_id,
    }


def layer1_nodes(consolidated: UnitTree, baseline: UnitTree, changes: amend.Amendments,
                 shas: dict[str, str], build_id: str) -> tuple[list[dict], list[dict]]:
    """The Regulation, every unit (in force or deleted) and every earlier version, with their edges."""
    cons_text = consolidated.texts[CONSOLIDATED_REL]
    cons_sha = shas[CONSOLIDATED_REL]
    deleted_ranges = [(m.start, m.end) for m in changes.markers if m.action == "DELETED"]
    nodes: list[dict] = [{
        "id": REGULATION_ID, "layer": 1, "type": "Regulation", "title": REGULATION_TITLE,
        "enacted_by": "composed", "amendment": "composed",
        "source_span": {"span_id": f"span:{REGULATION_ID}", "snapshot_file": CONSOLIDATED_REL,
                        "snapshot_sha256": cons_sha, "start": 0, "end": len(cons_text),
                        "exclude": [{"start": s, "end": e} for s, e in deleted_ranges]},
    }]
    edges: list[dict] = []

    def identity(unit) -> dict[str, Any]:
        node: dict[str, Any] = {"id": unit.id, "layer": 1, "type": unit.type}
        for key in ("number", "index", "marker", "sort_key"):
            if getattr(unit, key) is not None:
                node[key] = getattr(unit, key)
        return node

    old = baseline.by_id()
    gone = [u for u in baseline.units if u.id not in consolidated.by_id()]
    for unit in [*consolidated.units, *gone]:
        change = changes.changes[unit.id]
        node = identity(unit)
        if change.amendment == "deleted":
            node.update({"amendment": "deleted", "deleted_by": amend.enacted_by(change.point),
                         "deleted_from": amend.OMNIBUS_IN_FORCE})
            nodes.append(node)
            edges.append(_deleted_edge(unit.edge_type, unit.parent, unit.id, change.point, build_id))
            continue
        excluded = [(s, e) for s, e in deleted_ranges if unit.start <= s and e <= unit.end]
        if unit.title is not None:
            node["title"] = unit.title
        if unit.text is not None:
            node["text"] = (formex_text(cons_text, unit.start, unit.end, [*unit.own_exclude, *excluded])
                            if excluded else unit.text)
        node["enacted_by"] = (amend.BASE_ACT if change.amendment == "unchanged" else "composed"
                              if change.amendment == "composed" else amend.enacted_by(change.point))
        node["amendment"] = change.amendment
        span = {"span_id": unit.span_name, "snapshot_file": CONSOLIDATED_REL, "snapshot_sha256": cons_sha,
                "start": unit.start, "end": unit.end, "anchor": unit.anchor}
        if excluded:
            span["exclude"] = [{"start": s, "end": e} for s, e in excluded]
        node["source_span"] = span
        nodes.append(node)
        edges.append(_hierarchy_edge(unit.edge_type, unit.parent, unit.id, unit.span_name, build_id,
                                     method=unit.method))
    for unit_id, change in changes.changes.items():
        if change.amendment not in ("replaced", "deleted", "composed"):
            continue
        before = old[unit_id]
        version_id = amend.version_node_id(unit_id)
        span_id = amend.version_span_id(before.span_name)
        version: dict[str, Any] = {
            "id": version_id, "layer": 1, "type": "UnitVersion", "unit_id": unit_id, "unit_type": before.type,
            "version_date": amend.VERSION_DATE, "valid_from": amend.VERSION_VALID_FROM,
            "valid_to": amend.VERSION_VALID_TO, "legal_status": "superseded", "enacted_by": amend.BASE_ACT,
        }
        if before.title is not None:
            version["title"] = before.title
        if before.text is not None:
            version["text"] = before.text
        version["source_span"] = {"span_id": span_id, "snapshot_file": before.file,
                                  "snapshot_sha256": shas[before.file], "start": before.start, "end": before.end,
                                  "anchor": before.anchor}
        nodes.append(version)
        edges.append({
            "edge_id": f"edge:has_version:{version_id}", "edge_type": "HAS_VERSION", "from": unit_id,
            "to": version_id, "provenance_class": "EXTRACTED_SOURCE", "source_span_id": span_id,
            "method": VERSION_METHOD, "confidence": 1.0, "review_status": "auto_accepted", "build_id": build_id,
        })
    return nodes, edges


def build_in_force_dump(manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
                        marker_list_path: Path | str = amend.DEFAULT_MARKER_LIST_PATH,
                        exceptions_path: Path | str = amend.DEFAULT_EXCEPTIONS_PATH,
                        inventory_path: Path | str = amend.DEFAULT_INVENTORY_PATH) -> dict[str, Any]:
    """Layer 0 and Layer 1 of the Act in force (module docstring), every check passed."""
    from tere4ai.ingest.sources import layer0

    sources = read_sources(manifest_path)
    consolidated, baseline, formex_files = read_trees(sources)
    changes, rows = checked_amendments(sources, consolidated, baseline, exceptions_path, inventory_path)
    expected = marker_list_bytes(current_marker_list(sources, changes, rows))
    marker_list_path = Path(marker_list_path)
    if not marker_list_path.is_file() or marker_list_path.read_bytes() != expected:
        raise amend.AmendmentCheckError([
            f"{marker_list_path.name} differs from the markers of the consolidated text; review the "
            "difference, then regenerate it with: python -m tere4ai.parse_legal_structure.consolidated "
            "--write-marker-list"])
    sources.read(HTML_FILE)  # checked like every other source
    read_files = [HTML_FILE, *formex_files, CONSOLIDATED_REL, OMNIBUS_MAIN_REL, OMNIBUS_ANNEX_REL]
    files = [(f, sources.shas[f]) for f in read_files]
    build_id = f"build-{legal_sources_digest(files)[:12]}"
    l0_nodes, l0_edges = layer0(build_id, manifest_path, marker_list_path)
    nodes, edges = layer1_nodes(consolidated, baseline, changes, sources.shas, build_id)
    html = parse_snapshot(sources.snapshots_dir / HTML_FILE)
    nodes += [{**n, "enacted_by": amend.BASE_ACT, "amendment": "unchanged"}
              for n in html["nodes"] if n["type"] == "Recital"]
    edges += [{**e, "build_id": build_id} for e in html["edges"] if e["edge_type"] == "HAS_RECITAL"]
    return {
        "build": {
            "build_id": build_id,
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "tere4ai_version": TERE4AI_VERSION,
            "snapshots": [{"file": f, "sha256": s} for f, s in files],
            "amendments": {
                "marker_list": "data/amendments/omnibus_markers.json",
                "marker_list_sha256": hashlib.sha256(expected).hexdigest(),
                "markers_read": len(changes.markers),
                "markers_checked": len(changes.markers),
                "units_checked": len(changes.changes),
                "units_failed": 0,
                "exception_rows": sorted(changes.used_rows),
            },
        },
        "nodes": l0_nodes + nodes,
        "edges": l0_edges + edges,
    }


def main(argv: list[str] | None = None) -> int:
    """--write-marker-list regenerates data/amendments/omnibus_markers.json after every
    check passes; --check reports whether the committed file is current."""
    parser = argparse.ArgumentParser(prog="python -m tere4ai.parse_legal_structure.consolidated")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--marker-list", type=Path, default=amend.DEFAULT_MARKER_LIST_PATH)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-marker-list", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    sources = read_sources(args.manifest)
    consolidated, baseline, _ = read_trees(sources)
    try:
        changes, rows = checked_amendments(sources, consolidated, baseline)
    except amend.AmendmentCheckError as exc:
        for failure in exc.failures:
            print(f"CHECK FAIL {failure}", file=sys.stderr)
        return 1
    payload = marker_list_bytes(current_marker_list(sources, changes, rows))
    if args.write_marker_list:
        args.marker_list.parent.mkdir(parents=True, exist_ok=True)
        args.marker_list.write_bytes(payload)
        print(f"wrote {args.marker_list}: {len(changes.markers)} markers")
        return 0
    current = args.marker_list.is_file() and args.marker_list.read_bytes() == payload
    print("marker list is current" if current else f"{args.marker_list} differs from the markers", file=sys.stderr)
    return 0 if current else 1


if __name__ == "__main__":
    sys.exit(main())

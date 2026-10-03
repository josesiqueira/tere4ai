"""The AI Act in force, read from EUR-Lex's consolidated text in Formex: sources and checks.

@implements: DEC-01 (partial: the in-force parse)
@implements: DEC-12
@grounded_by: REF-01, REF-02, REF-03, REF-04, REF-05

Spec G D-G68: every build is made from Regulation (EU) 2024/1689 as amended
by Regulation (EU) 2026/1744. read_sources gives the frozen files listed in
data/snapshots/MANIFEST.json, each read only after its sha256 is checked;
read_trees reads the units of the consolidated text and of the 2024 Formex
(units.py); checked_amendments derives every change from the markers and
runs the checks of amendments.py (a failure raises AmendmentCheckError).
The command regenerates or checks the reviewed marker list:

    python -m tere4ai.parse_legal_structure.consolidated --write-marker-list
    python -m tere4ai.parse_legal_structure.consolidated --check

Deterministic, no model calls (DEC-01).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tere4ai.parse_legal_structure import amendments as amend
from tere4ai.parse_legal_structure.formex import DOC_FILE, MAIN_BODY_FILE, _annex_order_from_doc
from tere4ai.parse_legal_structure.parser import DEFAULT_MANIFEST_PATH
from tere4ai.parse_legal_structure.units import UnitTree, read_text_units

CONSOLIDATED_REL = "formex/CL2024R1689EN0010010.0001.xml"
OMNIBUS_MAIN_REL = "formex/L_202601744EN.000101.fmx.xml"
OMNIBUS_ANNEX_REL = "formex/L_202601744EN.003601.fmx.xml"


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
    """Derive every change and check every marker; raises AmendmentCheckError on any failure."""
    rows = amend.load_exceptions(exceptions_path)
    cons_text = consolidated.texts[CONSOLIDATED_REL]
    changes = amend.derive_changes(consolidated, baseline, amend.read_markers(cons_text), rows)
    quotations = amend.read_quotations(sources.read(OMNIBUS_MAIN_REL))
    inventory = amend.read_inventory(Path(inventory_path).read_text(encoding="utf-8"))
    failures = amend.check_markers(changes, consolidated, baseline, cons_text, quotations, inventory, rows,
                                   sources.read(OMNIBUS_ANNEX_REL))
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

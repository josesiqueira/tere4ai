"""Build reproducibility chain: pin every published build to its exact inputs.

@implements: DEC-10 (partial: reproducibility chain on Layer 2/3 publication)
@grounded_by: REF-27, ADD-20

Engineering MUST (architecture.md Section 13: reproducibility, no silent
degradation). A published build must be verifiable back to the exact input
artifacts it was made from. This module computes sha256 checksums of the
publication inputs (layer1 dump, norms file, alignments file, human review
decisions) and composes them into a chain id that is appended to the build_id
stamped on every published node and edge. An auditor holding the same files
can recompute the chain id and confirm the graph in Neo4j came from exactly
those artifacts; any edit to any input changes every edge's build_id.

Deterministic by construction: file bytes only, no timestamps, no randomness.
The chain record is grounded in the PROV notion of an activity linking used
entities to generated entities (ADD-20), kept as plain JSON rather than RDF;
the RDF export path (DEC-09) can map it to PROV-O later.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Roles are fixed vocabulary so chain records are comparable across builds.
INPUT_ROLES = ("layer1_dump", "norms", "alignments", "decisions")


def sha256_of_file(path: Path | str) -> str:
    """Hex sha256 of the file's exact bytes on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compose_chain_id(input_checksums: dict[str, str]) -> str:
    """Deterministic 12-hex chain id over the role-to-sha256 map.

    Sorted by role so dict ordering never changes the id. Absent optional
    inputs (no alignments file, no decisions file) are simply not part of
    the digest, so "same files present, same bytes" implies "same id".
    """
    canonical = json.dumps(
        {k: input_checksums[k] for k in sorted(input_checksums)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def build_chain(
    layer1_path: Path | str,
    norms_path: Path | str,
    alignments_path: Path | str | None = None,
    decisions_path: Path | str | None = None,
) -> dict[str, Any]:
    """Checksum the publication inputs and compose the chain record.

    Returns {"chain_id", "inputs": [{"role", "file", "sha256"}, ...]}.
    Optional inputs that do not exist on disk are omitted (not hashed as
    empty), so the record states exactly what was used.
    """
    paths: list[tuple[str, Path]] = [
        ("layer1_dump", Path(layer1_path)),
        ("norms", Path(norms_path)),
    ]
    if alignments_path is not None:
        paths.append(("alignments", Path(alignments_path)))
    if decisions_path is not None and Path(decisions_path).is_file():
        paths.append(("decisions", Path(decisions_path)))

    inputs = []
    checksums: dict[str, str] = {}
    for role, path in paths:
        digest = sha256_of_file(path)
        checksums[role] = digest
        inputs.append({"role": role, "file": path.name, "sha256": digest})
    return {"chain_id": compose_chain_id(checksums), "inputs": inputs}


def chained_build_id(base_build_id: str, chain: dict[str, Any]) -> str:
    """Append the chain id to the base build id: <base>+chain-<12hex>.

    Idempotent on re-publish of identical inputs (same id both times) and
    collision-safe against a base id that already carries a chain suffix:
    the previous suffix is replaced, never stacked.
    """
    base = base_build_id.split("+chain-", 1)[0]
    return f"{base}+chain-{chain['chain_id']}"

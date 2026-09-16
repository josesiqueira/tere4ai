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


def verify_dumps_against_chain(
    dump_dir: Path | str,
) -> tuple[bool, str]:
    """Recompute the published dumps' chain and match it to a recorded chain.

    Runtime integrity gate (audit 2026-07-20 D3): the served dumps must
    reproduce EXACTLY ONE build_chain_<id>.json record in the same directory.
    Returns (ok, detail). ok is False (with a human-readable reason) when a
    dump is missing, unreadable, or its recomputed chain matches no recorded
    record, i.e. the dump has drifted from any published build. This turns
    the CI-only build-chain check into one the runtime can call at load, so a
    tampered or corrupted dump is refused loudly instead of served.
    """
    directory = Path(dump_dir)
    layer1 = directory / "layer1.json"
    norms = directory / "norms_core.json"
    alignments = directory / "alignments_core.json"
    for path in (layer1, norms):
        if not path.is_file():
            return False, f"required dump missing: {path.name}"
    align_arg = alignments if alignments.is_file() else None
    try:
        chain = build_chain(layer1, norms, align_arg)
    except OSError as exc:
        return False, f"could not read a dump to verify integrity: {exc}"
    recorded_path = directory / f"build_chain_{chain['chain_id']}.json"
    if not recorded_path.is_file():
        return (
            False,
            "the published dumps match no recorded build chain "
            f"(recomputed chain {chain['chain_id']}); the dumps may be "
            "corrupted, tampered, or from an unpublished build",
        )
    # Cross-check the recorded per-input checksums against the live files, so
    # the gate proves more than an internally consistent filename (audit
    # 2026-07-21 defense-in-depth): every role in the record must match.
    try:
        recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"build chain record is unreadable: {exc}"
    live = {i["role"]: i["sha256"] for i in chain["inputs"]}
    for item in recorded.get("inputs", []):
        role, digest = item.get("role"), item.get("sha256")
        if live.get(role) != digest:
            return (
                False,
                f"build chain record {chain['chain_id']} disagrees with the "
                f"live dump for role '{role}'; integrity is not established",
            )
    return True, f"dumps verified against build chain {chain['chain_id']}"


# B74 (2026-09-16): the id a dump is SERVED under. publish_layer23 stamps
# <base>+chain-<12hex> on every published node and edge, but the facade and
# the MCP server used to report only the base id, the legal snapshot hash,
# which does not change when the norms are re-extracted with other models.
# A rebuild was therefore indistinguishable from the build it replaced, and
# the dashboard, which pins a campaign to this id, could not refuse grading
# a campaign on the wrong build. The served id is now the chain over the
# exact files in the dump directory, the same recipe publication uses, and
# the base id alone only when no norms are published there (a structural,
# Layer 1 only checkout). Cached per directory on the files' size and mtime
# so a per-call reader does not re-hash six megabytes on every tool call.
_SERVED_CHAIN_CACHE: dict[tuple, str] = {}


def _served_chain_id(dump_dir: Path) -> str | None:
    layer1 = dump_dir / "layer1.json"
    norms = dump_dir / "norms_core.json"
    alignments = dump_dir / "alignments_core.json"
    if not (layer1.is_file() and norms.is_file()):
        return None
    present = [layer1, norms] + ([alignments] if alignments.is_file() else [])
    try:
        key = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in present)
    except OSError:
        return None
    cache_key = (str(dump_dir.resolve()), key)
    cached = _SERVED_CHAIN_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        chain = build_chain(layer1, norms, alignments if alignments.is_file() else None)
    except OSError:
        return None
    _SERVED_CHAIN_CACHE[cache_key] = chain["chain_id"]
    return chain["chain_id"]


def served_build_id(dump_dir: Path | str, base_build_id: str) -> str:
    """<base>+chain-<12hex> over the dumps in dump_dir, or the base id alone
    when that directory publishes no norms. Idempotent on an already chained
    base (the suffix is replaced, never stacked)."""
    chain_id = _served_chain_id(Path(dump_dir))
    if chain_id is None:
        return base_build_id
    return chained_build_id(base_build_id, {"chain_id": chain_id})


def stamp_served_build(payload: Any, dump_dir: Path | str) -> Any:
    """Rewrite payload["build"]["build_id"] to the served id, in place.

    Applied once at load by every reader of a dump directory so each
    envelope's graph_version and the health answer's norms_build name the
    published build, not merely its snapshot. Payloads without a build
    record (fixtures, non-dump files) are returned untouched."""
    if not isinstance(payload, dict):
        return payload
    build = payload.get("build")
    if not isinstance(build, dict) or "build_id" not in build:
        return payload
    build["build_id"] = served_build_id(dump_dir, str(build["build_id"]))
    return payload

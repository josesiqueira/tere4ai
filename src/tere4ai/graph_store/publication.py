"""Publication evidence and the activation of a published build.

@implements: DEC-16 (partial: publication and activation, D-G21, D-G27)
@grounded_by: REF-27, ADD-20

A build is published only after the gates, the load and the post-load
gates; the chain record and the publication manifest are written last, so
their existence means success. Gating is recorded per layer from the
reference blocks the materialise command stamped, every human-gated layer
is bound to exactly one freeze manifest, and the whole-build label is
granted from that evidence alone. Neo4j is a publication target whose
state (loading, available, unavailable) is recorded separately from the
files the facade serves.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tere4ai.graph_store.build_record import atomic_write_json
from tere4ai.review_queue.materialize import _validator

PUBLICATIONS_DIRNAME = "publications"
TARGET_FILENAME = "NEO4J_TARGET.json"
PUBLICATION_SCHEMA_VERSION = "publication.v1"
GATES = ("G1", "G2", "G3", "G4", "G5", "G6")
POSTLOAD_GATES = ("P1", "P2", "P3", "P4", "P5")


class PublicationError(ValueError):
    pass


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _check(definition: str, payload: dict[str, Any]) -> None:
    errors = sorted(_validator(definition).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        where = "/".join(str(p) for p in errors[0].path) or "the payload"
        raise PublicationError(f"{definition}: {errors[0].message} at {where}")


def public_uri(uri: str) -> str:
    """scheme://host[:port] of a connection URI: userinfo, path and query
    are dropped, so no credential ever reaches a recorded file."""
    parts = urlsplit(uri)
    host = parts.hostname
    if not parts.scheme or not host:
        return "unparsed"
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")


def manifest_path(dump_dir: Path | str, chain_id: str) -> Path:
    return Path(dump_dir) / PUBLICATIONS_DIRNAME / f"{chain_id}.json"


def write_publication_manifest(dump_dir: Path | str, publication: dict[str, Any], *, record_id: str,
                               inputs: list[dict[str, Any]], files: dict[str, str | None]) -> Path:
    path = manifest_path(dump_dir, publication["chain_id"])
    payload = {"schema_version": PUBLICATION_SCHEMA_VERSION, **publication, "record_id": record_id,
               "inputs": inputs, "files": files}
    _check("publication_manifest", payload)
    _write(path, payload)
    return path


def set_target_state(dump_dir: Path | str, *, state: str, build_id: str | None, uri: str,
                     reason: str | None) -> dict[str, Any]:
    if state not in ("loading", "available", "unavailable"):
        raise ValueError(f"unknown target state {state!r}")
    payload = {"state": state, "build_id": build_id, "uri": public_uri(uri),
               "since": datetime.now(UTC).isoformat(), "reason": reason}
    _write(Path(dump_dir) / TARGET_FILENAME, payload)
    return payload


def read_target_state(dump_dir: Path | str) -> dict[str, Any] | None:
    return _read(Path(dump_dir) / TARGET_FILENAME)


def _reference(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    ref = payload.get("build", {}).get("reference")
    return ref if isinstance(ref, dict) else None


def gating_of(norms_payload: dict[str, Any], alignments_payload: dict[str, Any] | None) -> dict[str, str]:
    l2_ref = _reference(norms_payload)
    layer2 = "human" if l2_ref and l2_ref.get("kind") == "norms" else "llm"
    if alignments_payload is None:
        return {"layer2": layer2, "layer3": "absent"}
    l3_ref = _reference(alignments_payload)
    return {"layer2": layer2, "layer3": "human" if l3_ref and l3_ref.get("kind") == "alignments" else "llm"}


def bind_manifests(references: list[dict[str, Any]], manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bind every reference block to exactly one freeze manifest (R19)."""
    bound: list[dict[str, Any]] = []
    used: set[int] = set()
    given = ", ".join(sorted(str(m.get("freeze_id")) for m in manifests)) or "none"
    for ref in references:
        matches = [i for i, m in enumerate(manifests)
                   if m.get("campaign_id") == ref["campaign_id"] and m.get("freeze_id") == ref["freeze_id"]]
        if not matches:
            raise PublicationError(
                f"freeze {ref['freeze_id']} materialised this file but no --manifest names it (given: {given})"
            )
        if len(matches) > 1:
            raise PublicationError(f"freeze {ref['freeze_id']} is named twice among the manifests")
        m = manifests[matches[0]]
        if m.get("decisions_sha256") != ref.get("decisions_sha256"):
            raise PublicationError(
                f"freeze {ref['freeze_id']}: manifest decisions digest differs from the one materialised"
            )
        if m.get("campaign_type") != ref.get("campaign_type"):
            raise PublicationError(
                f"freeze {ref['freeze_id']}: manifest campaign_type differs from the reference block"
            )
        if m.get("pinned_build_id") != ref.get("source_build_id"):
            raise PublicationError(
                f"freeze {ref['freeze_id']}: manifest pinned build differs from the build the file was "
                "materialised from"
            )
        used.add(matches[0])
        bound.append({"campaign_id": m["campaign_id"], "freeze_id": m["freeze_id"],
                      "campaign_type": m["campaign_type"], "stage": m.get("stage"),
                      "decisions_sha256": m["decisions_sha256"], "layer": ref["layer"],
                      "units_undecided": m.get("units_undecided"), "units_adjudicated": m.get("units_adjudicated"),
                      "units_in_scope": m.get("units_in_scope"), "scope_core_nodes": m.get("scope_core_nodes")})
    stray = [m.get("freeze_id") for i, m in enumerate(manifests) if i not in used]
    if stray:
        raise PublicationError(f"manifest(s) {', '.join(str(s) for s in stray)} match no reference block of the inputs")
    return bound


def _complete_production(m: dict[str, Any], core_nodes: list[str] | None) -> bool:
    if m.get("stage") != "production" or m.get("units_undecided") != 0:
        return False
    if m.get("units_adjudicated") is None or m.get("units_adjudicated") != m.get("units_in_scope"):
        return False
    if core_nodes is not None and sorted(m.get("scope_core_nodes") or []) != sorted(core_nodes):
        return False
    return True


def whole_build_label(gating: dict[str, str], bound: list[dict[str, Any]], core_nodes: list[str] | None) -> str | None:
    """llm-gated, human-adjudicated, or None (an intermediate or norms-only build)."""
    if gating == {"layer2": "llm", "layer3": "llm"}:
        return "llm-gated"
    if gating != {"layer2": "human", "layer3": "human"}:
        return None
    by_layer = {m["layer"]: m for m in bound}
    if set(by_layer) != {2, 3}:
        return None
    return "human-adjudicated" if all(_complete_production(by_layer[layer], core_nodes) for layer in (2, 3)) else None

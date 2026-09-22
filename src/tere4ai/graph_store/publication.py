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
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tere4ai.graph_store.build_record import atomic_write_json
from tere4ai.review_queue.materialize import CAMPAIGN_TYPE_OF_KIND, _validator

PUBLICATIONS_DIRNAME = "publications"
TARGET_FILENAME = "NEO4J_TARGET.json"
CURRENT_POINTER_FILENAME = "BUILD_CHAIN_CURRENT.txt"
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


def check_schema(definition: str, payload: dict[str, Any]) -> None:
    """Raise PublicationError when payload does not validate against the schema definition."""
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


def publication_manifest(publication: dict[str, Any], *, record_id: str, inputs: list[dict[str, Any]],
                         files: dict[str, str | None]) -> dict[str, Any]:
    """The publication manifest payload, validated against the schema before anyone writes it."""
    payload = {"schema_version": PUBLICATION_SCHEMA_VERSION, **publication, "record_id": record_id,
               "inputs": inputs, "files": files}
    check_schema("publication_manifest", payload)
    return payload


def write_publication_manifest(dump_dir: Path | str, publication: dict[str, Any], *, record_id: str,
                               inputs: list[dict[str, Any]], files: dict[str, str | None]) -> Path:
    path = manifest_path(dump_dir, publication["chain_id"])
    _write(path, publication_manifest(publication, record_id=record_id, inputs=inputs, files=files))
    return path


def write_current_pointer(dump_dir: Path | str, chain_id: str) -> Path:
    """BUILD_CHAIN_CURRENT.txt through a temp file in the same directory and
    os.replace, so a reader sees the old id or the new one, never a partial."""
    path = Path(dump_dir) / CURRENT_POINTER_FILENAME
    fd, tmp = tempfile.mkstemp(prefix="tmp", suffix=".txt", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(chain_id + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
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
        if matches[0] in used:
            raise PublicationError(f"freeze {ref['freeze_id']} is bound to two reference blocks")
        m = manifests[matches[0]]
        wanted = CAMPAIGN_TYPE_OF_KIND.get(ref.get("kind"))
        if m.get("campaign_type") != wanted:
            raise PublicationError(
                f"freeze {ref['freeze_id']}: a {ref.get('kind')} reference needs a {wanted} freeze, "
                f"the manifest is {m.get('campaign_type')!r}"
            )
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


def _complete_production(m: dict[str, Any], core_nodes: list[str]) -> bool:
    if m.get("stage") != "production" or m.get("units_undecided") != 0:
        return False
    if m.get("units_adjudicated") is None or m.get("units_adjudicated") != m.get("units_in_scope"):
        return False
    return sorted(m.get("scope_core_nodes") or []) == sorted(core_nodes)


LABEL_NEEDS_CORE_NODES = "core_nodes.txt is missing from the dump directory: the whole declared core scope cannot be verified"


def whole_build_label(gating: dict[str, str], bound: list[dict[str, Any]], core_nodes: list[str] | None) -> str | None:
    """llm-gated, human-adjudicated, or None (an intermediate or norms-only
    build). The human-adjudicated label fails closed: it needs the declared
    core scope (core_nodes.txt), both layers' freezes complete in production
    and both scopes equal to each other and to that core scope."""
    if gating == {"layer2": "llm", "layer3": "llm"}:
        return "llm-gated"
    if gating != {"layer2": "human", "layer3": "human"} or core_nodes is None:
        return None
    by_layer = {m["layer"]: m for m in bound}
    if set(by_layer) != {2, 3}:
        return None
    if sorted(by_layer[2].get("scope_core_nodes") or []) != sorted(by_layer[3].get("scope_core_nodes") or []):
        return None
    return "human-adjudicated" if all(_complete_production(by_layer[layer], core_nodes) for layer in (2, 3)) else None


ACTIVE_POINTER = "ACTIVE_MANIFEST.json"
_LEGACY_FILES = {"layer1_dump": "layer1.json", "norms": "norms_core.json", "alignments": "alignments_core.json"}


class ActivationError(RuntimeError):
    pass


@dataclass
class LoadedBuild:
    """What the facade (at startup) and the MCP server (per tool call) serve.

    source is "manifest" when an activation pointer exists, "legacy" when
    the three fixed dump files are served; error is set, and the payloads
    are None, when the activated publication's files have drifted."""

    dump: dict[str, Any] | None
    norms: dict[str, Any] | None
    alignments: dict[str, Any] | None
    build_id: str | None
    source: str
    error: str | None


def active_manifest(dump_dir: Path | str) -> dict[str, Any] | None:
    """The publication manifest the activation pointer names, or None (no
    pointer, an unreadable pointer, an unreadable manifest)."""
    dump_dir = Path(dump_dir)
    pointer = _read(dump_dir / ACTIVE_POINTER)
    if not pointer or "chain_id" not in pointer:
        return None
    return _read(manifest_path(dump_dir, str(pointer["chain_id"])))


def activate(dump_dir: Path | str, chain_id: str) -> dict[str, Any]:
    """Select a published build: its files must verify against its
    publication manifest, then the pointer is written atomically."""
    from tere4ai.graph_store.build_chain import verify_dumps_against_chain

    dump_dir = Path(dump_dir)
    ok, detail = verify_dumps_against_chain(dump_dir, chain_id=chain_id)
    if not ok:
        raise ActivationError(detail)
    pointer = {"chain_id": chain_id, "activated_at": datetime.now(UTC).isoformat()}
    _write(dump_dir / ACTIVE_POINTER, pointer)
    return pointer


def _stamp(payload: dict[str, Any] | None, build_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict) and isinstance(payload.get("build"), dict):
        payload["build"]["build_id"] = build_id
    return payload


def load_active(dump_dir: Path | str) -> LoadedBuild:
    """The one loader: the activated publication when a pointer exists
    (verified, then its three files stamped with its build id), otherwise
    the three legacy files stamped with the served id as before. Every call
    reads fresh; nothing is cached here."""
    from tere4ai.graph_store.build_chain import stamp_served_build, verify_dumps_against_chain

    dump_dir = Path(dump_dir)
    pointer = _read(dump_dir / ACTIVE_POINTER)
    if pointer is None:
        if (dump_dir / ACTIVE_POINTER).is_file():
            return LoadedBuild(None, None, None, None, "manifest", "the activation pointer is unreadable")
        # Each payload keeps its own base id under the directory's chain,
        # exactly as the per-file stamping did before the loader existed.
        dump = stamp_served_build(_read(dump_dir / _LEGACY_FILES["layer1_dump"]), dump_dir)
        norms = stamp_served_build(_read(dump_dir / _LEGACY_FILES["norms"]), dump_dir)
        alignments = stamp_served_build(_read(dump_dir / _LEGACY_FILES["alignments"]), dump_dir)
        build_id = None
        if dump is not None:
            build_id = str(dump.get("build", {}).get("build_id", "unknown"))
        return LoadedBuild(dump, norms, alignments, build_id, "legacy", None)
    chain_id = str(pointer.get("chain_id"))
    manifest = _read(manifest_path(dump_dir, chain_id))
    if manifest is None:
        return LoadedBuild(None, None, None, None, "manifest", f"no readable publication manifest for chain {chain_id}")
    ok, detail = verify_dumps_against_chain(dump_dir, chain_id=chain_id)
    if not ok:
        return LoadedBuild(None, None, None, manifest.get("build_id"), "manifest", detail)
    files = manifest["files"]
    build_id = str(manifest["build_id"])
    dump = _stamp(_read(dump_dir / files["layer1_dump"]), build_id)
    norms = _stamp(_read(dump_dir / files["norms"]), build_id)
    alignments = _stamp(_read(dump_dir / files["alignments"]), build_id) if files.get("alignments") else None
    return LoadedBuild(dump, norms, alignments, build_id, "manifest", None)

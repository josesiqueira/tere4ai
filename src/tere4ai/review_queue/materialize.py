"""Materialise a frozen campaign's decisions once into a reference file.

@implements: DEC-16 (partial: the reference file of D-G27)
@grounded_by: REF-24, REF-27, ADD-20

Spec G Section 6: after the production Layer 2 freeze the decisions are
applied exactly once, through the same transformation publication used to
apply in memory (apply_decisions, then canonicalize_norms), into a NEW
file that the alignment command and publication consume. The pristine
dump stays pristine. The freeze manifest the dashboard exports beside the
decisions file is verified here against its typed schema, its digest and
the build the freeze was taken on, and its identity is stamped into the
output's build block so publication grants or withholds the
human-adjudicated label from evidence, never from a file's presence.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.canonicalize.canonicalizer import canonicalize_norms
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.review_queue.apply import apply_decisions, count_applied

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "json_schemas" / "build_record.schema.json"
_TYPES = {"layer2_annotation": "freeze_manifest_layer2", "hleg_alignment": "freeze_manifest_hleg"}
CAMPAIGN_TYPE_OF_KIND = {"norms": "layer2_annotation", "alignments": "hleg_alignment"}


class MaterializeError(ValueError):
    pass


@lru_cache(maxsize=4)
def _validator(definition: str) -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


def verify_freeze_manifest(manifest: dict[str, Any], decisions_path: Path | str | None, *,
                           expected_pinned_build_id: str | None) -> dict[str, Any]:
    kind = manifest.get("campaign_type")
    if kind not in _TYPES:
        raise MaterializeError(f"freeze manifest campaign_type {kind!r} is not one of {sorted(_TYPES)}")
    errors = sorted(_validator(_TYPES[kind]).iter_errors(manifest), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "the manifest"
        raise MaterializeError(f"freeze manifest: {first.message} at {where}")
    if decisions_path is not None:
        if manifest.get("decisions_sha256") is None:
            raise MaterializeError(
                "this freeze holds no decisions to materialise; Layer 3 decisions arrive with sub-project 4"
            )
        actual = sha256_of_file(decisions_path)
        if manifest["decisions_sha256"] != actual:
            raise MaterializeError(
                f"freeze manifest decisions_sha256 {manifest['decisions_sha256'][:12]} does not match the "
                f"decisions file ({actual[:12]})"
            )
    if expected_pinned_build_id is not None and manifest["pinned_build_id"] != expected_pinned_build_id:
        raise MaterializeError(
            f"the freeze was taken on build {manifest['pinned_build_id']}, this file belongs to build "
            f"{expected_pinned_build_id}"
        )
    return manifest


def already_materialised(payload: dict[str, Any]) -> bool:
    """True when the payload carries human decisions: its own reference block
    (for an alignments payload, one of kind alignments only; an upstream norms
    marker is not its own) or an item with a human_review record."""
    build = payload.get("build") if isinstance(payload.get("build"), dict) else {}
    ref = build.get("reference")
    if ref:
        is_alignments = "assertions" in payload and "norms" not in payload
        if not is_alignments or (isinstance(ref, dict) and ref.get("kind") == "alignments"):
            return True
    items = payload.get("norms") or payload.get("assertions") or []
    return any(isinstance(i, dict) and i.get("human_review") for i in items)


def apply_human_decisions(norms_payload: dict[str, Any], decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the decisions to a norms payload and re-materialise its clauses.

    A human replace or add rewrites the norm's conditions and exceptions
    text, the only source of the Condition and Exception nodes and edges;
    apply_decisions clears the model's clause ids, so canonicalize_norms
    runs again over the applied payload to rebuild them (deterministic, a
    second run over an untouched norm is a no-op)."""
    return canonicalize_norms(apply_decisions(norms_payload, decisions))


def materialize(kind: str, pristine: dict[str, Any], decisions: dict[str, dict[str, Any]], manifest: dict[str, Any], *,
                source_sha256: str, source_build_id: str, decisions_sha256: str) -> dict[str, Any]:
    if kind not in ("norms", "alignments"):
        raise MaterializeError(f"kind must be norms or alignments, got {kind!r}")
    if manifest.get("campaign_type") != CAMPAIGN_TYPE_OF_KIND[kind]:
        raise MaterializeError(
            f"freeze {manifest.get('freeze_id')}: a {kind} file needs a {CAMPAIGN_TYPE_OF_KIND[kind]} freeze, "
            f"the manifest is {manifest.get('campaign_type')!r}"
        )
    if already_materialised(pristine):
        raise MaterializeError(f"the {kind} payload already carries human decisions; materialise from the pristine dump")
    if not decisions:
        raise MaterializeError("a freeze with no decisions materialises nothing")
    result = apply_human_decisions(pristine, decisions) if kind == "norms" else apply_decisions(pristine, decisions)
    result = copy.deepcopy(result)
    result.setdefault("build", {})["reference"] = {
        "kind": kind, "layer": 2 if kind == "norms" else 3, "source_sha256": source_sha256,
        "source_build_id": source_build_id, "decisions_sha256": decisions_sha256,
        "campaign_id": manifest["campaign_id"], "freeze_id": manifest["freeze_id"],
        "campaign_type": manifest["campaign_type"], "stage": manifest.get("stage"), "round": manifest.get("round"),
        "units_in_scope": manifest.get("units_in_scope"), "units_adjudicated": manifest.get("units_adjudicated"),
        "units_undecided": manifest.get("units_undecided"), "scope_core_nodes": manifest.get("scope_core_nodes"),
        "decisions_applied": count_applied(result), "materialized_at": datetime.now(UTC).isoformat(),
    }
    return result

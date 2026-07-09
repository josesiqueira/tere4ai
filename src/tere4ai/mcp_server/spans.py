"""Span helper: resolve a SourceSpan id to its checksum-verified snapshot text.

Every span in the graph carries the frozen snapshot file, its sha256, and
exact character offsets. This module resolves a span_id to the literal
snapshot slice, verifying the file checksum first so a drifted snapshot can
never silently masquerade as the frozen source (architecture.md Sections 6
and 13). Spans may point into subpaths of the snapshots directory, for
example data/snapshots/formex/. Deterministic, no model calls.

@implements: DEC-01 (partial: span rendering)
@grounded_by: REF-27
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.tools import make_envelope


class SpanResolutionError(Exception):
    """Base error for span resolution failures."""


class SpanNotFoundError(SpanResolutionError):
    """No node in the provided dump carries the requested span_id."""


class SpanIntegrityError(SpanResolutionError):
    """The snapshot file is missing, unreadable, outside the snapshots
    directory, or fails its checksum; the span cannot be trusted."""


def _find_span(
    span_id: str, dump: dict[str, Any], extra_nodes: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """First source_span whose span_id matches, searching the dump nodes and
    then any extra nodes (for example the HLEG requirement nodes, which live
    outside the Layer 0+1 dump)."""
    for node in list(dump.get("nodes", [])) + list(extra_nodes or []):
        span = node.get("source_span") if isinstance(node, dict) else None
        if isinstance(span, dict) and span.get("span_id") == span_id:
            return span
    return None


def resolve_span(
    span_id: str,
    dump: dict[str, Any],
    snapshots_dir: Path | str,
    extra_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve span_id to {span_id, snapshot_file, sha256, start, end, text}.

    Finds any node whose source_span.span_id matches, verifies the snapshot
    file's sha256 against the span's recorded checksum, and slices the
    decoded text exactly at [start:end] (offsets are over the utf-8 decoded
    snapshot). Raises SpanNotFoundError for an unknown span_id and
    SpanIntegrityError for a missing, escaping, or drifted snapshot.
    """
    span = _find_span(span_id, dump, extra_nodes)
    if span is None:
        raise SpanNotFoundError(
            f"span_id '{span_id}' does not match any node source_span in the graph dump"
        )

    snapshot_file = str(span.get("snapshot_file", ""))
    base = Path(snapshots_dir).resolve()
    path = (base / snapshot_file).resolve()
    if not path.is_relative_to(base):
        raise SpanIntegrityError(
            f"snapshot file '{snapshot_file}' escapes the snapshots directory"
        )
    if not path.is_file():
        raise SpanIntegrityError(
            f"snapshot file '{snapshot_file}' for span '{span_id}' is not present "
            f"under {base}"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SpanIntegrityError(
            f"snapshot file '{snapshot_file}' for span '{span_id}' is unreadable: {exc}"
        ) from exc

    expected = str(span.get("snapshot_sha256", ""))
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise SpanIntegrityError(
            f"checksum mismatch for snapshot '{snapshot_file}': span records "
            f"{expected}, file is {actual}; the frozen source has drifted"
        )

    start, end = span.get("start"), span.get("end")
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end):
        raise SpanIntegrityError(
            f"span '{span_id}' carries invalid offsets start={start!r} end={end!r}"
        )
    text = raw.decode("utf-8", errors="replace")[start:end]
    return {
        "span_id": span_id,
        "snapshot_file": snapshot_file,
        "sha256": actual,
        "start": start,
        "end": end,
        "text": text,
    }


def resolve_span_envelope(
    span_id: str,
    dump: dict[str, Any],
    snapshots_dir: Path | str,
    extra_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """resolve_span wrapped in the Section 8 envelope, never an exception.

    Unknown span ids come back as not_applicable with missing_facts; an
    integrity failure (missing or drifted snapshot) comes back as
    requires_human_review, never a confident answer over untrusted bytes.
    """
    graph_version = str(dump.get("build", {}).get("build_id", "unknown"))
    try:
        resolved = resolve_span(span_id, dump, snapshots_dir, extra_nodes=extra_nodes)
    except SpanNotFoundError as exc:
        return make_envelope(
            answer={"span_id": span_id, "found": False},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[str(exc)],
        )
    except SpanIntegrityError as exc:
        return make_envelope(
            answer={"span_id": span_id, "found": False},
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[str(exc)],
        )
    return make_envelope(
        answer={**resolved, "found": True},
        status="satisfied_with_evidence",
        graph_version=graph_version,
        source_spans=[
            {
                "span_id": resolved["span_id"],
                "snapshot_file": resolved["snapshot_file"],
                "snapshot_sha256": resolved["sha256"],
                "start": resolved["start"],
                "end": resolved["end"],
            }
        ],
    )

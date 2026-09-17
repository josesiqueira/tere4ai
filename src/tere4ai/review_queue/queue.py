"""Unified human review queue over the pipeline dump artifacts.

@implements: DEC-06 (partial: human review loop)
@grounded_by: REF-24, REF-32

Builds one adjudication queue out of the three pending pools:
- norms (norms_core.json) with judge_verdict == needs_human_review,
- alignment assertions (alignments_core.json) with judge_verdict ==
  needs_human_review or review_status == needs_review,
- unresolved cross-reference items (layer1.json review_queue).

Provenance discipline (architecture.md Sections 2 and 13): adjudication never
edits the pipeline dumps in place. Human decisions live in a separate
decisions file (data/review_queue/decisions.json) and are applied at publish
time (see tere4ai.review_queue.apply), so the pipeline artifacts stay
pristine and the human trail is separate and auditable. Every decision
records who (reviewer), when (decided_at, UTC ISO), what (accept or reject),
and why (a required, non-empty rationale).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXCERPT_CHARS = 280

VALID_DECISIONS = ("accept", "reject", "replace", "add")
HUMAN_NORM_REQUIRED = (
    "source_node_id", "source_span_id", "deontic_type", "modal", "actor_explicit", "action", "object",
)


def _excerpt(text: str | None) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS].rstrip() + " [...]"


def _layer1_lookups(layer1_dump: dict[str, Any] | None) -> tuple[dict, dict]:
    """Return (node text by node id, node text by span id) for the dump."""
    by_node_id: dict[str, str] = {}
    by_span_id: dict[str, str] = {}
    for node in (layer1_dump or {}).get("nodes", []):
        text = node.get("text")
        if not text:
            continue
        by_node_id[node["id"]] = text
        span = node.get("source_span") or {}
        span_id = span.get("span_id")
        if span_id:
            by_span_id[span_id] = text
    return by_node_id, by_span_id


def _judge_rationales(payload: dict[str, Any] | None) -> dict[str, str]:
    """Map judge_run_id -> rationale for a norms or alignments payload."""
    out: dict[str, str] = {}
    for run in (payload or {}).get("judge_runs", []):
        if run.get("id") and run.get("rationale"):
            out[run["id"]] = run["rationale"]
    return out


def _norm_digest(norm: dict[str, Any]) -> str:
    actor = norm.get("actor_explicit") or norm.get("actor_inferred") or "?"
    return (
        f"{norm.get('deontic_type', '?')}/{norm.get('modal', '?')} "
        f"actor={actor} action={norm.get('action', '?')} "
        f"object={_excerpt(norm.get('object'))[:80]}"
    )


def _alignment_digest(assertion: dict[str, Any]) -> str:
    return (
        f"{assertion.get('relation_type', '?')} "
        f"{assertion.get('source_norm_id', '?')} -> {assertion.get('target_id', '?')} "
        f"score={assertion.get('final_score', '?')} "
        f"verdict={assertion.get('judge_verdict', '?')}"
    )


def _crossref_digest(item: dict[str, Any]) -> str:
    return (
        f"{item.get('reason', '?')}: {_excerpt(item.get('citation_text'))[:100]} "
        f"(from {item.get('from_node_id', '?')})"
    )


def list_pending(
    norms_payload: dict[str, Any] | None = None,
    alignments_payload: dict[str, Any] | None = None,
    layer1_dump: dict[str, Any] | None = None,
    decisions: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The unified adjudication queue, in stable dump order.

    Each entry: {queue_id, kind (norm | alignment | crossref), digest,
    source_excerpt, judge_rationale, item (the raw dump record)}. queue_ids
    are the stable pipeline ids (norm_id, assertion id, crossref item_id).
    When decisions is given, already-decided items are excluded.
    """
    decided = set(decisions or {})
    text_by_node, text_by_span = _layer1_lookups(layer1_dump)
    items: list[dict[str, Any]] = []

    norm_rationales = _judge_rationales(norms_payload)
    for norm in (norms_payload or {}).get("norms", []):
        if norm.get("judge_verdict") != "needs_human_review":
            continue
        if norm["norm_id"] in decided:
            continue
        items.append(
            {
                "queue_id": norm["norm_id"],
                "kind": "norm",
                "digest": _norm_digest(norm),
                "source_excerpt": _excerpt(text_by_node.get(norm.get("source_node_id", ""))),
                "judge_rationale": norm_rationales.get(norm.get("judge_run_id", ""), ""),
                "item": norm,
            }
        )

    align_rationales = _judge_rationales(alignments_payload)
    for assertion in (alignments_payload or {}).get("assertions", []):
        pending = (
            assertion.get("judge_verdict") == "needs_human_review"
            or assertion.get("review_status") == "needs_review"
        )
        if not pending or assertion["id"] in decided:
            continue
        rationale = assertion.get("rationale") or align_rationales.get(
            assertion.get("judge_run_id", ""), ""
        )
        source_text = assertion.get("source_quote") or text_by_span.get(
            (assertion.get("source_evidence_span_ids") or [""])[0], ""
        )
        items.append(
            {
                "queue_id": assertion["id"],
                "kind": "alignment",
                "digest": _alignment_digest(assertion),
                "source_excerpt": _excerpt(source_text),
                "judge_rationale": rationale,
                "item": assertion,
            }
        )

    for entry in (layer1_dump or {}).get("review_queue", []):
        if entry["item_id"] in decided:
            continue
        source_text = text_by_span.get(entry.get("source_span_id", "")) or text_by_node.get(
            entry.get("from_node_id", ""), ""
        )
        items.append(
            {
                "queue_id": entry["item_id"],
                "kind": "crossref",
                "digest": _crossref_digest(entry),
                "source_excerpt": _excerpt(source_text),
                "judge_rationale": (
                    f"deterministic resolver left this unresolved: {entry.get('reason', '?')}"
                ),
                "item": entry,
            }
        )
    return items


def validate_human_payload(decision: Any, payload: dict[str, Any] | None) -> None:
    """Check one decision entry's payload, whoever wrote the file.

    replace and add carry a human-written norm: every field in
    HUMAN_NORM_REQUIRED must be present, and an actor_inferred value of any
    kind, the "unspecified_needs_review" sentinel included, must name the
    node the inference came from. Every other decision takes no payload.
    record_decision, load_decisions and apply_decisions all go through this,
    so a decisions file exported by the dashboard is held to the same rules
    as one written by the review CLI.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
    if decision not in ("replace", "add"):
        if payload is not None:
            raise ValueError(f"decision {decision!r} takes no payload")
        return
    if not isinstance(payload, dict):
        raise ValueError(f"decision {decision!r} requires a payload with the norm's slots")
    missing = [k for k in HUMAN_NORM_REQUIRED if k not in payload]
    if missing:
        raise ValueError(f"payload is missing {', '.join(missing)}")
    actor_inferred = payload.get("actor_inferred")
    if actor_inferred is not None and not payload.get("actor_inference_source_node_id"):
        raise ValueError(
            f"payload sets actor_inferred={actor_inferred!r} but is missing "
            "actor_inference_source_node_id"
        )


def load_decisions(path: Path | str) -> dict[str, dict[str, Any]]:
    """Load the decisions file; an absent file is an empty decision set.

    Every entry is validated on the way in (validate_human_payload), so a
    file produced outside record_decision, for example the annotation
    campaign export, cannot carry a malformed human norm into publish.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"decisions file {path} must hold a JSON object")
    for queue_id, entry in data.items():
        if not isinstance(entry, dict):
            raise ValueError(
                f"decisions file {path}: entry {queue_id!r} must be a JSON object"
            )
        try:
            validate_human_payload(entry.get("decision"), entry.get("payload"))
        except ValueError as exc:
            raise ValueError(f"decisions file {path}: entry {queue_id!r}: {exc}") from exc
    return data


def record_decision(
    decisions: dict[str, dict[str, Any]],
    queue_id: str,
    decision: str,
    rationale: str,
    reviewer: str,
    decided_at: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add or update one decision in the in-memory decision set.

    accept and reject adjudicate an existing item. replace and add (B77
    plan 1) carry a human-written norm in payload: replace overwrites the
    slots of the existing norm queue_id names; add appends a new norm whose
    id is queue_id (norm:<unit>:h<n>). Both require the slot fields in
    HUMAN_NORM_REQUIRED so the schema gate at publish cannot be surprised.
    """
    if not queue_id or not str(queue_id).strip():
        raise ValueError("queue_id must be a non-empty string")
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("rationale is required and must be non-empty")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("reviewer is required and must be non-empty")
    entry: dict[str, Any] = {
        "decision": decision,
        "rationale": rationale.strip(),
        "reviewer": reviewer.strip(),
        "decided_at": decided_at or datetime.now(UTC).isoformat(),
    }
    validate_human_payload(decision, payload)
    if decision in ("replace", "add"):
        entry["payload"] = dict(payload or {})
    decisions[queue_id] = entry
    return entry


def save_decisions(decisions: dict[str, dict[str, Any]], path: Path | str) -> None:
    """Write the decision set to disk (stable key order, trailing newline)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decisions, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

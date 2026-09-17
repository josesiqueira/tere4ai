"""Apply human review decisions to pipeline payloads at publish time.

@implements: DEC-06 (partial: human review loop)
@grounded_by: REF-24, REF-32

The pipeline dumps are never edited in place. This module takes a pristine
norms or alignments payload plus the separate decisions file and returns a
NEW payload in which each decided item gets:
- judge_verdict and review_status flipped to accepted or rejected,
- a human_review record {reviewer, decided_at, rationale, provenance} with
  provenance HUMAN_REVIEWED_ACCEPTED or HUMAN_REVIEWED_REJECTED
  (architecture.md Section 2 provenance classes).
replace and add (B77 plan 1) carry a human-written norm instead: replace
overwrites an existing norm's slots, add appends a brand new norm, and both
stamp extraction_method "human" and human_review.provenance HUMAN_AUTHORED.
The graph adapter (tere4ai.graph_store.layer23) prefers
human_review.provenance over the judge-derived class when persisting edges.
"""

from __future__ import annotations

import copy
from typing import Any

_PROVENANCE = {
    "accept": "HUMAN_REVIEWED_ACCEPTED",
    "reject": "HUMAN_REVIEWED_REJECTED",
    "replace": "HUMAN_AUTHORED",
    "add": "HUMAN_AUTHORED",
}
_VERDICT = {"accept": "accepted", "reject": "rejected", "replace": "accepted", "add": "accepted"}
_SLOT_FIELDS = (
    "source_node_id", "source_span_id", "deontic_type", "modal", "actor_explicit", "actor_inferred",
    "actor_inference_source_node_id", "action", "object", "conditions", "exceptions", "lifecycle_phase_ids",
)


def _items_and_id_field(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    if "norms" in payload:
        return payload["norms"], "norm_id"
    if "assertions" in payload:
        return payload["assertions"], "id"
    raise ValueError("payload has neither 'norms' nor 'assertions'; cannot apply decisions")


def _human_review(entry: dict[str, Any], decision: str) -> dict[str, Any]:
    return {
        "reviewer": entry["reviewer"],
        "decided_at": entry["decided_at"],
        "rationale": entry["rationale"],
        "provenance": _PROVENANCE[decision],
    }


def _stamp_human_norm(item: dict[str, Any], entry: dict[str, Any]) -> None:
    payload = entry["payload"]
    for field in _SLOT_FIELDS:
        if field in payload:
            item[field] = copy.deepcopy(payload[field])
    item.setdefault("conditions", [])
    item.setdefault("exceptions", [])
    item.setdefault("lifecycle_phase_ids", [])
    item.setdefault("actor_inferred", None)
    item.setdefault("actor_inference_source_node_id", None)
    item["extraction_method"] = "human"
    item["extractor_model"] = f"human:{entry['reviewer']}"
    item["extractor_prompt_version"] = "n/a"
    item["confidence"] = 1.0
    item["judge_verdict"] = "accepted"
    item["review_status"] = "accepted"
    item["judge_run_id"] = None


def apply_decisions(
    payload: dict[str, Any], decisions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return a new payload with the human decisions applied.

    Never mutates the input. accept and reject flip an existing item; replace
    overwrites an existing norm's slots with the human's; add appends a new
    norm (norms payloads only). On a norms payload, a decision naming an id
    that exists for add, or that is absent for replace, is an error, never a
    silent skip. replace and add are norm-only decisions: on any other
    payload (for example alignments), they do not apply and are skipped, the
    same way accept and reject already ignore ids absent from the payload.
    This lets one decisions file, mixing norm and assertion ids, be applied
    to both the norms pass and the alignments pass of a single publish run.
    """
    new_payload = copy.deepcopy(payload)
    if not decisions:
        return new_payload
    items, id_field = _items_and_id_field(new_payload)
    present = {item.get(id_field) for item in items}
    for item in items:
        entry = decisions.get(item.get(id_field, ""))
        if entry is None:
            continue
        decision = entry["decision"]
        if decision not in _VERDICT:
            raise ValueError(f"unknown decision {decision!r} for {item.get(id_field)!r}")
        if decision == "add":
            raise ValueError(f"norm {item.get(id_field)!r} already exists; an add decision cannot reuse its id")
        if decision == "replace":
            if id_field != "norm_id":
                raise ValueError("replace applies to norms only")
            norm_id = item.get(id_field)
            replace_payload = entry["payload"]
            for moved_field in ("source_node_id", "source_span_id"):
                if moved_field in replace_payload and replace_payload[moved_field] != item.get(moved_field):
                    raise ValueError(
                        f"replace cannot move norm {norm_id!r}: {moved_field} differs; "
                        "use reject plus add"
                    )
            _stamp_human_norm(item, entry)
        else:
            item["judge_verdict"] = _VERDICT[decision]
            item["review_status"] = _VERDICT[decision]
        item["human_review"] = _human_review(entry, decision)
    for queue_id, entry in decisions.items():
        if id_field != "norm_id" and entry["decision"] in ("add", "replace"):
            # replace and add are norm-only; on an alignments (or any other
            # non-norms) payload they simply do not apply here, so one
            # decisions file can serve both publish passes.
            continue
        if entry["decision"] == "add" and queue_id not in present:
            new_norm: dict[str, Any] = {
                "norm_id": queue_id,
                "layer": 2,
                "type": "NormativeStatement",
                "condition_ids": [],
                "exception_ids": [],
            }
            _stamp_human_norm(new_norm, entry)
            new_norm["human_review"] = _human_review(entry, "add")
            items.append(new_norm)
        elif entry["decision"] == "replace" and queue_id not in present:
            raise ValueError(f"replace names {queue_id!r}, which is not in the payload")
    return new_payload


def count_applied(payload: dict[str, Any]) -> int:
    """How many items in the payload carry a human_review record."""
    items, _ = _items_and_id_field(payload)
    return sum(1 for item in items if item.get("human_review"))

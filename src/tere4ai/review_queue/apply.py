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
The graph adapter (tere4ai.graph_store.layer23) prefers
human_review.provenance over the judge-derived class when persisting edges.
"""

from __future__ import annotations

import copy
from typing import Any

_PROVENANCE = {
    "accept": "HUMAN_REVIEWED_ACCEPTED",
    "reject": "HUMAN_REVIEWED_REJECTED",
}
_VERDICT = {"accept": "accepted", "reject": "rejected"}


def _items_and_id_field(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    if "norms" in payload:
        return payload["norms"], "norm_id"
    if "assertions" in payload:
        return payload["assertions"], "id"
    raise ValueError("payload has neither 'norms' nor 'assertions'; cannot apply decisions")


def apply_decisions(
    payload: dict[str, Any], decisions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Return a new payload with the human decisions applied.

    Never mutates the input. Items whose stable id (norm_id for norms, id for
    assertions) has a decision get verdict, status, and a human_review
    provenance record; everything else passes through untouched.
    """
    new_payload = copy.deepcopy(payload)
    if not decisions:
        return new_payload
    items, id_field = _items_and_id_field(new_payload)
    for item in items:
        entry = decisions.get(item.get(id_field, ""))
        if entry is None:
            continue
        decision = entry["decision"]
        if decision not in _VERDICT:
            raise ValueError(f"unknown decision {decision!r} for {item.get(id_field)!r}")
        item["judge_verdict"] = _VERDICT[decision]
        item["review_status"] = _VERDICT[decision]
        item["human_review"] = {
            "reviewer": entry["reviewer"],
            "decided_at": entry["decided_at"],
            "rationale": entry["rationale"],
            "provenance": _PROVENANCE[decision],
        }
    return new_payload


def count_applied(payload: dict[str, Any]) -> int:
    """How many items in the payload carry a human_review record."""
    items, _ = _items_and_id_field(payload)
    return sum(1 for item in items if item.get("human_review"))

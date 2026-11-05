"""The HLEG requirements each tailored requirement's cited norms are aligned to.

A deterministic join over the judged alignments payload, added to the
finished envelope of generate_tailored_requirements after the judge ran. The
join reads accepted alignment assertions only (review_status "accepted") of
the relation types partially_operationalizes and supports. The HLEG content
never enters a prompt, the text the judge reads, the grounding check, the
status, the verdict or the confidence: with_hleg_requirements takes the
finished envelope and returns a copy that differs only by the keys it adds.
No model is called and nothing is stored.

When no alignments payload is loaded the answer says so
(hleg_requirements_unavailable) and keeps everything the paid call produced.
The caveat is the one explain_requirement shows beside every alignment.

@implements: DEC-31
@grounded_by: REF-24
"""

from __future__ import annotations

import copy
from typing import Any

from tere4ai.align_hleg.hleg_nodes import CANONICAL
from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT

USE_TIME_RELATIONS = ("partially_operationalizes", "supports")

UNAVAILABLE_REASON = (
    "the judged alignments payload is not loaded, so the HLEG requirements of "
    "the cited norms are not shown; the tailored requirements are unchanged"
)


def hleg_requirements_of(norm_ids: list[str], alignments_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per HLEG requirement the norms are aligned to, in the order
    of CANONICAL; its alignments follow the order of norm_ids, then id."""
    assertions = [
        a
        for a in (alignments_payload or {}).get("assertions", [])
        if isinstance(a, dict)
        and a.get("review_status") == "accepted"
        and a.get("relation_type") in USE_TIME_RELATIONS
    ]
    position: dict[str, int] = {}
    for norm_id in norm_ids:
        position.setdefault(norm_id, len(position))
    entries: list[dict[str, Any]] = []
    for hleg_id, name in CANONICAL:
        reached = [
            a for a in assertions if a.get("target_id") == hleg_id and a.get("source_norm_id") in position
        ]
        if not reached:
            continue
        reached.sort(key=lambda a: (position[a["source_norm_id"]], str(a.get("id"))))
        entries.append(
            {
                "hleg_id": hleg_id,
                "name": name,
                "alignments": [
                    {
                        "alignment_id": a.get("id"),
                        "norm_id": a["source_norm_id"],
                        "relation_type": a["relation_type"],
                        "final_score": a.get("final_score"),
                    }
                    for a in reached
                ],
            }
        )
    return entries


def with_hleg_requirements(envelope: dict[str, Any], alignments_payload: dict[str, Any] | None) -> dict[str, Any]:
    """A copy of the envelope with the HLEG requirements added to each tailored
    requirement; an envelope without tailored requirements is returned as is."""
    answer = envelope.get("answer") if isinstance(envelope, dict) else None
    if not isinstance(answer, dict) or not isinstance(answer.get("tailored_requirements"), list):
        return envelope
    result = copy.deepcopy(envelope)
    new_answer = result["answer"]
    if alignments_payload is None:
        new_answer["hleg_requirements_unavailable"] = UNAVAILABLE_REASON
        return result
    for tailored in new_answer["tailored_requirements"]:
        if not isinstance(tailored, dict):
            continue
        cited = tailored.get("norm_ids")
        tailored["hleg_requirements"] = hleg_requirements_of(
            [n for n in cited if isinstance(n, str)] if isinstance(cited, list) else [], alignments_payload
        )
    new_answer["hleg_caveat"] = HLEG_MAPPING_CAVEAT
    return result

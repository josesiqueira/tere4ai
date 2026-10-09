"""Canonicalisation step: actors to the closed table, conditions to nodes.

@implements: DEC-04
@implements: DEC-27
@grounded_by: REF-11, REF-12

Build pipeline step 5 (architecture.md Section 6). Two deterministic passes
over the judged norms payload, no model involved:

- Actor canonicalisation (Section 3): a raw actor string is placed on one
  value of the Act's parties (schema/act_parties.json, DEC-27) by
  tere4ai.act_parties.place. A string the list cannot place stays untouched
  and is reported; nothing is guessed (REF-12: multi-party texts cause actor
  misidentification, so unresolved means human review, not a default).
- Condition/Exception materialisation (Section 3): each distinct normalised
  condition or exception text becomes one shared node with a content-hash
  id, and every norm's condition_ids/exception_ids are populated. The same
  wording used by several norms resolves to the SAME node, which is what
  makes conditions queryable across the graph.
"""

from __future__ import annotations

import hashlib
from typing import Any

from tere4ai.act_parties import METHOD as ACT_PARTIES_METHOD
from tere4ai.act_parties import place

METHOD = "canonicalize_rule_v1"

def canonicalize_actor(raw: str | None) -> tuple[str | None, str]:
    """(value of the Act's parties, "act_parties_v1") or (None, reason): the
    normaliser of schema/act_parties.json (DEC-27, spec G D-G80 (4)), kept
    under its old name for its callers and the dashboard's parity test."""
    if not raw or not str(raw).strip():
        return None, "empty"
    value = place(str(raw))
    return (value, ACT_PARTIES_METHOD) if value is not None else (None, "unplaced")


def _clause_id(kind: str, text: str) -> str:
    normalised = " ".join(text.lower().split())
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{digest}"


def canonicalize_norms(norms_payload: dict[str, Any]) -> dict[str, Any]:
    """Return a new payload with actors canonicalised and clauses reified.

    Adds per norm: actor_canonical (when resolvable), condition_ids,
    exception_ids. Adds payload-level: conditions and exceptions node
    lists (deduped by normalised text) and canonicalization stats.
    Deterministic for a fixed input; running it twice is a no-op.
    """
    payload = dict(norms_payload)
    conditions: dict[str, dict[str, Any]] = {}
    exceptions: dict[str, dict[str, Any]] = {}
    resolved = 0
    unresolved: dict[str, int] = {}

    norms_out = []
    for norm in payload.get("norms", []):
        norm = dict(norm)
        raw_actor = norm.get("actor_explicit") or norm.get("actor_inferred")
        canonical, method = canonicalize_actor(raw_actor)
        if canonical is not None:
            norm["actor_canonical"] = canonical
            norm["actor_canonicalization_method"] = method
            resolved += 1
        else:
            norm.pop("actor_canonical", None)
            key = str(raw_actor)
            unresolved[key] = unresolved.get(key, 0) + 1

        for kind, registry, field in (
            ("cond", conditions, "condition"),
            ("exc", exceptions, "exception"),
        ):
            ids = []
            for text in norm.get(f"{field}s") or []:
                text = str(text).strip()
                if not text:
                    continue
                clause_id = _clause_id(kind, text)
                registry.setdefault(
                    clause_id,
                    {
                        "id": clause_id,
                        "type": "Condition" if kind == "cond" else "Exception",
                        "layer": 2,
                        "text": text,
                        "method": METHOD,
                    },
                )
                if clause_id not in ids:
                    ids.append(clause_id)
            norm[f"{field}_ids"] = ids
        norms_out.append(norm)

    payload["norms"] = norms_out
    payload["conditions"] = sorted(conditions.values(), key=lambda n: n["id"])
    payload["exceptions"] = sorted(exceptions.values(), key=lambda n: n["id"])
    payload["canonicalization"] = {
        "method": METHOD,
        "actors_resolved": resolved,
        "actors_unresolved": dict(sorted(unresolved.items())),
        "condition_nodes": len(conditions),
        "exception_nodes": len(exceptions),
    }
    return payload

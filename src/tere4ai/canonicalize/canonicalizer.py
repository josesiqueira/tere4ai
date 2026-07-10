"""Canonicalisation step: actors to the closed table, conditions to nodes.

@implements: DEC-04
@grounded_by: REF-11, REF-12

Build pipeline step 5 (architecture.md Section 6). Two deterministic passes
over the judged norms payload, no model involved:

- Actor canonicalisation (Section 3): raw actor strings map onto the closed
  actor table via normalisation rules (article stripping, plural folding,
  descriptor-tail removal). A string that does not map stays untouched and
  is reported; nothing is guessed (REF-12: multi-party texts cause actor
  misidentification, so unresolved means human review, not a default).
- Condition/Exception materialisation (Section 3): each distinct normalised
  condition or exception text becomes one shared node with a content-hash
  id, and every norm's condition_ids/exception_ids are populated. The same
  wording used by several norms resolves to the SAME node, which is what
  makes conditions queryable across the graph.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

METHOD = "canonicalize_rule_v1"

# The closed actor table (architecture.md Section 3; roles named by the Act).
CANONICAL_ACTORS = (
    "provider",
    "deployer",
    "importer",
    "distributor",
    "authorised_representative",
    "product_manufacturer",
    "operator",
    "notified_body",
    "national_competent_authority",
    "market_surveillance_authority",
    "commission",
    "ai_office",
    "member_state",
)

# Normalised phrase -> canonical actor, for wordings that survive the
# mechanical normalisation but are not the bare role name.
_SYNONYMS = {
    "european commission": "commission",
    "the eu ai office": "ai_office",
    "office": None,  # too ambiguous alone; never map
    "member states": "member_state",
    "national competent authorities": "national_competent_authority",
    "market surveillance authorities": "market_surveillance_authority",
    "authorised representatives": "authorised_representative",
    "product manufacturers": "product_manufacturer",
    "notified bodies": "notified_body",
}

_DESCRIPTOR_TAIL = re.compile(
    r"\s+of\s+(?:such\s+)?(?:the\s+)?(?:high-risk\s+)?(?:general-purpose\s+)?ai\s+(?:systems?|models?).*$"
)


def canonicalize_actor(raw: str | None) -> tuple[str | None, str]:
    """(canonical actor, method) or (None, reason) when it does not map."""
    if not raw or not str(raw).strip():
        return None, "empty"
    text = " ".join(str(raw).lower().split())
    text = re.sub(r"^(?:the|a|an)\s+", "", text)
    text = _DESCRIPTOR_TAIL.sub("", text).strip(" ,.")
    if text in _SYNONYMS:
        mapped = _SYNONYMS[text]
        return (mapped, METHOD) if mapped else (None, "ambiguous")
    candidates = {text, text.replace(" ", "_")}
    if text.endswith("s"):
        singular = text[:-1]
        candidates |= {singular, singular.replace(" ", "_")}
    for candidate in candidates:
        if candidate in CANONICAL_ACTORS:
            return candidate, METHOD
    return None, "unresolved"


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

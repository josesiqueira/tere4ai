"""The first reading of DEC-19's operator condition, frozen (brief R27).

@implements: DEC-19
@grounded_by: ADD-54

Prompt versions v1 to v4 apply the requirement type scope to the candidate
before the judge sees it (pipeline.py), so a run under one of them must read
the scope exactly as it did at tere4ai2 8440c99, whatever the Act's parties
list says later. This module holds that reading verbatim: the canonical
actor table and its synonyms (canonicalize/canonicalizer.py at 8440c99), the
operator roles and the word lists (requirement_type.py at 8440c99). Nothing
else may import it; extract_norms v5 reads schema/act_parties.json instead
(requirement_type.is_operator_actor). The guard test of spec G D-G80 (3)
excepts this file by name.
"""

from __future__ import annotations

import re
from typing import Any

FIRST_READING_VERSIONS = frozenset({"v1", "v2", "v3", "v4"})

_CANONICAL_ACTORS = (
    "provider", "deployer", "importer", "distributor", "authorised_representative",
    "product_manufacturer", "operator", "notified_body", "national_competent_authority",
    "market_surveillance_authority", "commission", "ai_office", "member_state",
)
_SYNONYMS = {
    "european commission": "commission",
    "the eu ai office": "ai_office",
    "office": None,
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
OPERATOR_ROLES = (
    "provider", "deployer", "importer", "distributor", "authorised_representative",
    "product_manufacturer", "operator_general", "unspecified_needs_review",
)
_OPERATOR_CANONICAL = frozenset(
    {"provider", "deployer", "importer", "distributor", "authorised_representative",
     "product_manufacturer", "operator"}
)
_OPERATOR_WORDS = ("provider", "deployer", "importer", "distributor",
                   "authorised representative", "manufacturer", "operator")
_NON_OPERATOR_WORDS = ("commission", "ai office", "member state", "authorit",
                       "notified bod", "affected person")


def _canonical_actor(raw: str) -> str | None:
    text = " ".join(raw.lower().split())
    text = re.sub(r"^(?:the|a|an)\s+", "", text)
    text = _DESCRIPTOR_TAIL.sub("", text).strip(" ,.")
    if text in _SYNONYMS:
        return _SYNONYMS[text]
    candidates = {text, text.replace(" ", "_")}
    if text.endswith("s"):
        singular = text[:-1]
        candidates |= {singular, singular.replace(" ", "_")}
    for candidate in candidates:
        if candidate in _CANONICAL_ACTORS:
            return candidate
    return None


def is_operator_actor_first_reading(actor_explicit: Any, actor_inferred: Any) -> bool:
    """requirement_type.is_operator_actor as it read at tere4ai2 8440c99."""
    if isinstance(actor_inferred, str) and actor_inferred:
        return actor_inferred in OPERATOR_ROLES
    if not isinstance(actor_explicit, str) or not actor_explicit.strip():
        return True
    canonical = _canonical_actor(actor_explicit)
    if canonical is not None:
        return canonical in _OPERATOR_CANONICAL
    text = " ".join(actor_explicit.lower().split())
    if any(word in text for word in _OPERATOR_WORDS):
        return True
    return not any(word in text for word in _NON_OPERATOR_WORDS)

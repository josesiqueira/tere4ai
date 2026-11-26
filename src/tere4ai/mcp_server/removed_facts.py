"""The facts that left the features schema with DEC-32, each with the facts that replace it,
and the refusal of a `domain` that is not a value of the schema (DEC-33).

Kept in a module of its own so that the guard over the removed fact names
(tests/unit/test_removed_facts_guard.py) allows these names here and nowhere
else in the classifier: a removed fact that came back into the classifier's
logic would still fail the guard. The four words that left the list of
`domain` (B185) are read from the schema's x-removed-values, never written
here.

@implements: DEC-32
@implements: DEC-33
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_FEATURES_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schema" / "json_schemas" / "system_features.schema.json"
)

# B184 (DEC-32; final review, M2): the seven facts that left the schema, each
# with the facts that replace it (CHANGELOG.md, the B184 entry). A rejected
# input that carries one gets a line naming them, after the schema's errors.
REMOVED_FACT_REPLACEMENTS: dict[str, str] = {
    "education_scoring_or_access": (
        "annex_iii_3a_admission, annex_iii_3b_learning_outcomes, annex_iii_3c_education_level and "
        "annex_iii_3d_test_monitoring (Annex III points 3(a) to 3(d))"
    ),
    "employment_decisions": (
        "annex_iii_4a_recruitment and annex_iii_4b_work_relationships (Annex III points 4(a) and 4(b))"
    ),
    "essential_services_access": (
        "annex_iii_5a_public_benefits and annex_iii_5d_emergency_calls (Annex III points 5(a) and 5(d)), "
        "beside creditworthiness_evaluation and life_health_insurance_risk_pricing (points 5(b) and 5(c))"
    ),
    "law_enforcement_use": (
        "law_enforcement_purpose for Article 5(1) point (h), and annex_iii_6a_victim_risk, "
        "annex_iii_6b_polygraphs, annex_iii_6c_evidence_reliability, annex_iii_6d_offending_risk and "
        "annex_iii_6e_profiling for Annex III points 6(a) to 6(e)"
    ),
    "migration_asylum_border_use": (
        "annex_iii_7a_polygraphs, annex_iii_7b_entry_risk, annex_iii_7c_applications and "
        "annex_iii_7d_identification (Annex III points 7(a) to 7(d))"
    ),
    "justice_democratic_use": (
        "annex_iii_8a_judicial and annex_iii_8b_elections (Annex III points 8(a) and 8(b))"
    ),
    "preparatory_or_narrow_procedural_task": (
        "narrow_procedural_task (Article 6(3) point (a)) and preparatory_task (Article 6(3) point (d))"
    ),
}


# B185 (DEC-33, spec G D-G92 (4) and (iii)): the value of `domain` that names
# none of the eight areas; it is never a reason to read a listed use as false.
# Defined once here, read by the classifier and the elicitor.
DOMAIN_NONE_OF_THESE_AREAS = "none_of_these_areas"


@lru_cache(maxsize=1)
def _domain_property() -> dict[str, Any]:
    """The schema's `domain` property, read once from the schema file."""
    schema = json.loads(_FEATURES_SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema["properties"]["domain"]


def domain_refusal(value: object) -> str:
    """The one wording of the refusal of a `domain` outside the schema (B185, ruling P30).

    The schema's x-refusal formatted with the value, a string as it is (no
    trimming, no change of case) and any other type as its JSON text (a value
    JSON cannot encode, a set for one, as the JSON text of its str); for a
    word of x-removed-values, ": " and the message that names the value to use.

    @implements: DEC-33
    """
    domain = _domain_property()
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    refusal = domain["x-refusal"].format(value=shown)
    message = domain["x-removed-values"].get(value) if isinstance(value, str) else None
    return f"{refusal}: {message}" if message else refusal


def domain_is_a_value(value: object) -> bool:
    """Whether a given `domain` is a value of the schema's enum (null included).

    @implements: DEC-33
    """
    return any(value == v and type(value) is type(v) for v in _domain_property()["enum"])

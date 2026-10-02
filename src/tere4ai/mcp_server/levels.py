"""The classifier's level vocabulary (B118, spec G D-G60).

@implements: DEC-20
"""

# B118 (spec G D-G60): one stored value per level, the Commission
# pyramid's names; undetermined is not a level but a statement that facts
# are missing (DEC-18).
RISK_CATEGORIES = (
    "unacceptable_risk",
    "high_risk",
    "limited_risk",
    "minimal_risk",
    "undetermined",
)

# B118: the name a person reads for each stored value, in sentences and on
# screens. Machine tokens (risk_category, the unacceptable_risk field, the
# rationale's rule names) keep the stored value.
LEVEL_NAMES: dict[str, str] = {
    "unacceptable_risk": "Unacceptable risk",
    "high_risk": "High risk",
    "limited_risk": "Limited risk",
    "minimal_risk": "Minimal risk",
    "undetermined": "Undetermined: facts missing",
}

# B118 (ruling R6): the values stored before B118, for reading a result
# file written before the rename (the July ablation checkpoints) so its
# numbers stay reproducible. Never applied to a live answer.
LEGACY_LEVEL_VALUES: dict[str, str] = {
    "prohibited": "unacceptable_risk",
    "high_risk": "high_risk",
    "transparency_only": "limited_risk",
    "minimal_or_none": "minimal_risk",
    "uncertain": "undetermined",
}


def level_name(value: str | None) -> str | None:
    """The shown name of a stored value; an unknown value is returned as it is."""
    if value is None:
        return None
    return LEVEL_NAMES.get(value, value)

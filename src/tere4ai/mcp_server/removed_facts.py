"""The facts that left the features schema with DEC-32, each with the facts that replace it.

Kept in a module of its own so that the guard over the removed fact names
(tests/unit/test_removed_facts_guard.py) allows these names here and nowhere
else in the classifier: a removed fact that came back into the classifier's
logic would still fail the guard.

@implements: DEC-32
"""

from __future__ import annotations

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

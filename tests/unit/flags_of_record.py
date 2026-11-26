"""The facts and rule tables of tag v2.0.0-beta.1, frozen for the tests of prompts v5 to v8 (B184, ruling P15).

Prompts v5 to v8 are records of the tag: each names the facts the schema had at
commit dff1b48 (39 flags). B184 changes the schema and the rule tables, so the
tests that check those prompts against them read these values and never the
live schema or classifier. Written from the schema and classify.py at dff1b48.

B185 (ruling P27): prompt v9 is frozen the same way (FLAGS_OF_V9 and
ARTICLE_50_RULES_OF_V9, at the end), from the schema and classify.py at 09472d6.

@implements: DEC-32
@implements: DEC-33
@grounded_by: REF-01
"""

from __future__ import annotations

# The 39 flag names of the features schema at dff1b48, in the schema's order.
FLAGS_OF_V8: tuple[str, ...] = (
    "biometric_identification",
    "biometric_categorisation",
    "biometric_categorisation_system",
    "biometric_categorisation_sensitive_or_protected_attributes",
    "causes_significant_harm",
    "social_score_detrimental_treatment",
    "supports_human_assessment_on_verifiable_facts",
    "emotion_recognition_medical_or_safety",
    "biometric_categorisation_lawful_or_law_enforcement",
    "rtrb_strictly_necessary_authorised",
    "real_time_remote_biometric_public",
    "emotion_recognition",
    "emotion_recognition_workplace_or_education",
    "social_scoring",
    "subliminal_or_manipulative",
    "exploits_vulnerabilities",
    "predictive_policing_profiling",
    "facial_image_scraping",
    "law_enforcement_use",
    "migration_asylum_border_use",
    "justice_democratic_use",
    "education_scoring_or_access",
    "employment_decisions",
    "essential_services_access",
    "creditworthiness_evaluation",
    "life_health_insurance_risk_pricing",
    "critical_infrastructure_safety",
    "medical_or_safety_component",
    "interacts_with_natural_persons",
    "generates_synthetic_content",
    "profiling_of_natural_persons",
    "preparatory_or_narrow_procedural_task",
    "improves_previous_human_activity",
    "detects_patterns_without_replacing_human_assessment",
    "annex_i_covered_product",
    "third_party_conformity_assessment_required",
    "annex_i_section_b_legislation",
    "generates_nonconsensual_intimate_material",
    "generates_csam",
)

# Fact to the Annex III point node ANNEX_III_RULES gave it at dff1b48 (flags and subflags).
ANNEX_III_FACT_POINTS_OF_V8: dict[str, str] = {
    "biometric_identification": "eu-ai-act:annex-iii:point-1",
    "emotion_recognition": "eu-ai-act:annex-iii:point-1",
    "real_time_remote_biometric_public": "eu-ai-act:annex-iii:point-1",
    "biometric_categorisation_sensitive_or_protected_attributes": "eu-ai-act:annex-iii:point-1",
    "critical_infrastructure_safety": "eu-ai-act:annex-iii:point-2",
    "education_scoring_or_access": "eu-ai-act:annex-iii:point-3",
    "employment_decisions": "eu-ai-act:annex-iii:point-4",
    "essential_services_access": "eu-ai-act:annex-iii:point-5",
    "creditworthiness_evaluation": "eu-ai-act:annex-iii:point-5",
    "life_health_insurance_risk_pricing": "eu-ai-act:annex-iii:point-5",
    "law_enforcement_use": "eu-ai-act:annex-iii:point-6",
    "migration_asylum_border_use": "eu-ai-act:annex-iii:point-7",
    "justice_democratic_use": "eu-ai-act:annex-iii:point-8",
}

# ARTICLE_6_3_CONDITIONS at dff1b48: fact, the Point nodes it stands for, the note.
ARTICLE_6_3_CONDITIONS_OF_V8: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "preparatory_or_narrow_procedural_task",
        (
            "eu-ai-act:article-6:paragraph-3:point-a",
            "eu-ai-act:article-6:paragraph-3:point-d",
        ),
        "narrow procedural task (point a) or preparatory task (point d)",
    ),
    (
        "improves_previous_human_activity",
        (
            "eu-ai-act:article-6:paragraph-3:point-b",
        ),
        "improves the result of a previously completed human activity (point b)",
    ),
    (
        "detects_patterns_without_replacing_human_assessment",
        (
            "eu-ai-act:article-6:paragraph-3:point-c",
        ),
        "detects decision-making patterns without replacing human assessment (point c)",
    ),
)


# B185 (spec G D-G92 (7), ruling P27): prompt v9 is the prompt of B184's
# record and a record from B185 Task 5 on, where the schema gains the two
# Article 50(4) facts; the tests of v9 read these values, never the live
# schema or ARTICLE_50_RULES. Written from the schema and classify.py at
# 09472d6 (the facts unchanged at 2ce6e2c). Task 8 makes v10 the prompt of record.

# The 54 flag names of the features schema at 09472d6, in the schema file's order.
FLAGS_OF_V9: tuple[str, ...] = (
    "biometric_categorisation",
    "biometric_categorisation_system",
    "causes_significant_harm",
    "social_score_detrimental_treatment",
    "supports_human_assessment_on_verifiable_facts",
    "emotion_recognition_medical_or_safety",
    "biometric_categorisation_lawful_or_law_enforcement",
    "rtrb_strictly_necessary_authorised",
    "law_enforcement_purpose",
    "real_time_remote_biometric_public",
    "emotion_recognition_workplace_or_education",
    "social_scoring",
    "subliminal_or_manipulative",
    "exploits_vulnerabilities",
    "predictive_policing_profiling",
    "facial_image_scraping",
    "biometric_identification",
    "biometric_categorisation_sensitive_or_protected_attributes",
    "emotion_recognition",
    "critical_infrastructure_safety",
    "annex_iii_3a_admission",
    "annex_iii_3b_learning_outcomes",
    "annex_iii_3c_education_level",
    "annex_iii_3d_test_monitoring",
    "annex_iii_4a_recruitment",
    "annex_iii_4b_work_relationships",
    "annex_iii_5a_public_benefits",
    "creditworthiness_evaluation",
    "life_health_insurance_risk_pricing",
    "annex_iii_5d_emergency_calls",
    "annex_iii_6a_victim_risk",
    "annex_iii_6b_polygraphs",
    "annex_iii_6c_evidence_reliability",
    "annex_iii_6d_offending_risk",
    "annex_iii_6e_profiling",
    "annex_iii_7a_polygraphs",
    "annex_iii_7b_entry_risk",
    "annex_iii_7c_applications",
    "annex_iii_7d_identification",
    "annex_iii_8a_judicial",
    "annex_iii_8b_elections",
    "medical_or_safety_component",
    "interacts_with_natural_persons",
    "generates_synthetic_content",
    "profiling_of_natural_persons",
    "narrow_procedural_task",
    "improves_previous_human_activity",
    "detects_patterns_without_replacing_human_assessment",
    "preparatory_task",
    "annex_i_covered_product",
    "third_party_conformity_assessment_required",
    "annex_i_section_b_legislation",
    "generates_nonconsensual_intimate_material",
    "generates_csam",
)

# ARTICLE_50_RULES at 09472d6: fact, the Paragraph node, the note.
ARTICLE_50_RULES_OF_V9: tuple[tuple[str, str, str], ...] = (
    (
        "interacts_with_natural_persons",
        "eu-ai-act:article-50:paragraph-1",
        "interaction with natural persons must be disclosed",
    ),
    (
        "generates_synthetic_content",
        "eu-ai-act:article-50:paragraph-2",
        "synthetic content must be marked as artificially generated or manipulated",
    ),
    (
        "emotion_recognition",
        "eu-ai-act:article-50:paragraph-3",
        "exposed persons must be informed of emotion recognition",
    ),
    (
        "biometric_categorisation_system",
        "eu-ai-act:article-50:paragraph-3",
        "exposed persons must be informed of biometric categorisation",
    ),
)

# ARTICLE_50_RULES at dff1b48, the rows prompts v5 to v8 were checked against:
# the same four rows as at 09472d6 (compared 2026-11-26, comments aside).
ARTICLE_50_RULES_OF_V8: tuple[tuple[str, str, str], ...] = ARTICLE_50_RULES_OF_V9

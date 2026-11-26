"""The table of area cases of B185 (spec G D-G92, DEC-33): the inputs and the
expected answer of each case, one dict per task that builds its columns.

Base for every case: every schema flag false (b184_cases.all_false), then the
overrides, then the absent facts removed; the deployer is known to be neither
a body governed by public law nor a private entity providing public services;
the domain is education unless the case says otherwise. P61 means
annex_i_covered_product and third_party_conformity_assessment_required true.
Each case's "expected" holds a dict per task ("t2", "t3", then the later
tasks' own), so a task adds its columns and never edits another's. The t5
column (Task 5) says whether the case, with every Article 50 trigger fact it
does not set true removed, names those facts; test_article_50_facts.py reads it.

@implements: DEC-33
"""

from __future__ import annotations

from typing import Any

from tests.unit.b184_cases import all_false, case

DEPLOYER = {"body_governed_by_public_law": False, "private_entity_providing_public_services": False}
P61 = {"annex_i_covered_product": True, "third_party_conformity_assessment_required": True}

POINT_1 = "eu-ai-act:annex-iii:point-1"
POINT_2 = "eu-ai-act:annex-iii:point-2"
POINT_3 = "eu-ai-act:annex-iii:point-3"
POINT_4 = "eu-ai-act:annex-iii:point-4"
ARTICLE_6_1 = "eu-ai-act:article-6:paragraph-1"
ARTICLE_6_2 = "eu-ai-act:article-6:paragraph-2"
ANNEX_I = "eu-ai-act:annex-i"
ARTICLE_50_1 = "eu-ai-act:article-50:paragraph-1"
ARTICLE_6_3 = "eu-ai-act:article-6:paragraph-3"
ARTICLE_6_3_A = "eu-ai-act:article-6:paragraph-3:point-a"
ARTICLE_6_4 = "eu-ai-act:article-6:paragraph-4"

REVIEW = ("requires_human_review", 0.5)
SETTLED = ("potentially_applicable", 1.0)

# The fixed lines of the area (ruling P7), written out word for word.
AREA_ALONE_POINT_3 = (
    "eu-ai-act:annex-iii:point-3: the level rests on the area alone: domain 'education' places the system in "
    "Annex III point 3 (Education and vocational training), and no listed use of the point is confirmed; "
    "the listed uses still unknown: annex_iii_3a_admission"
)
AREA_ALONE_POINT_1 = (
    "eu-ai-act:annex-iii:point-1: the level rests on the area alone: domain 'biometrics' places the system in "
    "Annex III point 1 (Biometrics, in so far as their use is permitted under relevant Union or national law), "
    "and no listed use of the point is confirmed; the listed uses still unknown: biometric_identification"
)
SCOPE_UNCONFIRMED_POINT_3 = (
    "eu-ai-act:annex-iii:point-3: domain 'education' places the system in Annex III point 3 (Education and "
    "vocational training), but no listed use of the point is confirmed, so the Annex III scope is not "
    "confirmed and the answer rests on the Article 6(1) route; the listed uses still unknown: "
    "annex_iii_3a_admission"
)
SCOPE_UNCONFIRMED_POINT_2 = (
    "eu-ai-act:annex-iii:point-2: domain 'critical_infrastructure' places the system in Annex III point 2 "
    "(Critical infrastructure), but no listed use of the point is confirmed, so the Annex III scope is not "
    "confirmed and the answer rests on the Article 6(1) route; the listed uses still unknown: "
    "critical_infrastructure_safety"
)
# The candidate's lines (B185 Task 4, spec G D-G92 (6), (iv), rulings P9, P29),
# written out word for word.
ARTICLE_6_4_NOTE = (
    "eu-ai-act:article-6:paragraph-4: a provider who considers that the system is not high-risk documents the "
    "assessment before placing it on the market or putting it into service, registers under Article 49(2), and "
    "provides the documentation of the assessment to the national competent authorities on request"
)
CANDIDATE_FLAGGED_NOTE = (
    "eu-ai-act:article-6:paragraph-3: Article 6(3) derogation candidacy is flagged for human review; the "
    "classification stays high_risk until a human legal reviewer decides"
)
CANDIDATE_BOTH_ROUTES_NOTE = (
    "eu-ai-act:article-6:paragraph-3: an Article 6(3) condition is true for the Annex III part of the answer; "
    "the level stays high_risk under Article 6(1), which the derogation does not reach"
)
UNKNOWN_CONDITION_POINT_A = (
    "flags.narrow_procedural_task is unknown (Article 6(3) narrow procedural task (point a)); no condition is "
    "true, so the derogation candidacy is unknown, not no"
)
AREA_RULED_OUT_POINT_3 = (
    "domain 'education' names Annex III point 3 (eu-ai-act:annex-iii:point-3), but every listed use of the "
    "category is answered false, so the area does not count (ELICITATION_ERRORS.md, scenario 161)"
)


def _features(
    true: tuple[str, ...] = (),
    absent: tuple[str, ...] = (),
    domain: str | None = "education",
    **values: Any,
) -> dict[str, Any]:
    """The features of one case: every flag false, the named ones true, the
    keyword ones as given, the absent ones removed."""
    flags = all_false(**dict.fromkeys(true, True), **values)
    for fact in absent:
        flags.pop(fact)
    return case(flags, domain=domain, deployer=dict(DEPLOYER))


def _conflict(fact: str) -> dict[str, str]:
    """One entry of area_conflicts (B185 Task 3), written out word for word."""
    return {
        "domain": "none_of_these_areas",
        "fact": fact,
        "note": f"domain is none_of_these_areas while flags.{fact} is true; the fact keeps its effect",
    }


AREA_CASES: dict[str, dict[str, Any]] = {
    "C1": {
        "features": _features(absent=("annex_iii_3a_admission",)),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": [], "annex_i_section": None, "transparency_duties": [], "status": REVIEW,
            "cites": (ARTICLE_6_2, POINT_3), "notes": (AREA_ALONE_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)},
        "t5": {"article_50_absent_named": True}},
    },
    "C2": {
        "features": _features(),
        "expected": {"t2": {
            "risk_category": "minimal_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": [], "status": ("not_applicable", 1.0), "not_cited": (POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C3": {
        "features": _features(true=("annex_iii_4a_recruitment",), absent=("annex_iii_3a_admission",)),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"], "status": SETTLED, "cites": (ARTICLE_6_2, POINT_4),
            "not_cited": (POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C4": {
        "features": _features(true=("annex_iii_4a_recruitment",), domain="employment"),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"], "status": SETTLED, "cites": (ARTICLE_6_2, POINT_4),
            "not_cited": (POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C5": {
        "features": _features(true=("annex_iii_4a_recruitment",), domain="none_of_these_areas"),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"],
        },
        "t3": {"area_conflicts": [_conflict("annex_iii_4a_recruitment")], "status": REVIEW},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C6": {
        "features": _features(domain="none_of_these_areas"),
        "expected": {"t2": {
            "risk_category": "minimal_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": [], "status": ("not_applicable", 1.0),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C7": {
        "features": _features(absent=("annex_iii_3a_admission",), domain="none_of_these_areas"),
        "expected": {"t2": {
            "risk_category": "undetermined", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": [], "status": REVIEW,
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C8": {
        "features": _features(absent=("annex_iii_3a_admission",), domain=None),
        "expected": {"t2": {
            "risk_category": "undetermined", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": [], "status": REVIEW,
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)},
        "t5": {"article_50_absent_named": True}},
    },
    "C9": {
        # The route is open: the Annex I fact is unknown and the third-party
        # assessment true (false would rule the route out, B123 R4).
        "features": _features(absent=("annex_iii_3a_admission", "annex_i_covered_product"),
                              third_party_conformity_assessment_required=True),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": [], "annex_i_section": None, "status": REVIEW,
            "cites": (ARTICLE_6_2, POINT_3), "notes": (AREA_ALONE_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C10": {
        "features": _features(absent=("annex_iii_3a_admission",), **P61, annex_i_section_b_legislation=False),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": ["article_6_1"], "annex_i_section": "A", "status": SETTLED,
            "cites": (ARTICLE_6_1, ANNEX_I), "not_cited": (ARTICLE_6_2, POINT_3),
            "notes": (SCOPE_UNCONFIRMED_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C11": {
        "features": _features(absent=("annex_iii_3a_admission",), **P61, annex_i_section_b_legislation=True),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": ["article_6_1"], "annex_i_section": "B", "transparency_duties": [],
            "status": REVIEW, "not_cited": (ARTICLE_6_2, POINT_3), "notes": (SCOPE_UNCONFIRMED_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)},
        "t5": {"article_50_absent_named": False}},
    },
    "C12": {
        "features": _features(absent=("annex_iii_3a_admission", "annex_i_section_b_legislation"), **P61),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": ["article_6_1"], "annex_i_section": "unknown", "status": SETTLED,
            "notes": (SCOPE_UNCONFIRMED_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C13": {
        "features": _features(absent=("critical_infrastructure_safety",), domain="critical_infrastructure",
                              **P61, annex_i_section_b_legislation=False),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_2,
            "high_risk_routes": ["article_6_1"], "annex_i_section": "A", "status": SETTLED,
            "not_cited": (POINT_2,), "notes": (SCOPE_UNCONFIRMED_POINT_2,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C14": {
        "features": _features(absent=("biometric_identification",), domain="biometrics"),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_1,
            "high_risk_routes": [], "status": REVIEW, "cites": (ARTICLE_6_2, POINT_1),
            "notes": (AREA_ALONE_POINT_1,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C15": {
        "features": _features(true=("annex_iii_4a_recruitment",), domain=None, **P61,
                              annex_i_section_b_legislation=True),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_1", "article_6_2"], "annex_i_section": "B", "status": SETTLED,
            "cites": (ARTICLE_6_1, ARTICLE_6_2),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C16": {
        "features": _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"), domain=None, **P61,
                              annex_i_section_b_legislation=False),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_1", "article_6_2"], "annex_i_section": "A",
            "cites": (ARTICLE_6_1, ARTICLE_6_2),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": True, "status": SETTLED,
               "cites": (ARTICLE_6_3, ARTICLE_6_3_A, ARTICLE_6_4), "notes": (ARTICLE_6_4_NOTE, CANDIDATE_BOTH_ROUTES_NOTE)}},
    },
    "C17": {
        "features": _features(true=("interacts_with_natural_persons",), absent=("annex_iii_3a_admission",)),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": [], "transparency_duties": [ARTICLE_50_1], "status": REVIEW,
            "cites": (ARTICLE_6_2, POINT_3, ARTICLE_50_1), "notes": (AREA_ALONE_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)},
        "t5": {"article_50_absent_named": True}},
    },
    "C18": {
        "features": _features(absent=("annex_iii_3a_admission", "facial_image_scraping")),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": POINT_3,
            "high_risk_routes": [], "status": REVIEW, "notes": (AREA_ALONE_POINT_3,),
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C19": {
        "features": _features(true=("annex_iii_4a_recruitment",), absent=("narrow_procedural_task",), domain=None),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"],
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": None, "status": SETTLED, "missing": (UNKNOWN_CONDITION_POINT_A,),
               "not_cited": (ARTICLE_6_3, ARTICLE_6_4)}},
    },
    "C20": {
        "features": _features(true=("real_time_remote_biometric_public",), absent=("biometric_identification",),
                              domain="none_of_these_areas"),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_1, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"],
        },
        "t3": {"area_conflicts": [_conflict("biometric_identification")], "status": REVIEW},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)}},
    },
    "C21": {
        "features": _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"), domain=None, **P61,
                              annex_i_section_b_legislation=True),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_1", "article_6_2"], "annex_i_section": "B",
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": True, "status": REVIEW,
               "cites": (ARTICLE_6_3, ARTICLE_6_3_A, ARTICLE_6_4), "notes": (ARTICLE_6_4_NOTE, CANDIDATE_FLAGGED_NOTE)}},
    },
    "C22": {
        "features": _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"), domain=None),
        "expected": {"t2": {
            "risk_category": "high_risk", "annex_iii_category": POINT_4, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": ["article_6_2"],
        },
        "t3": {"area_conflicts": []},
        "t4": {"article_6_3_exception_candidate": True, "status": REVIEW,
               "cites": (ARTICLE_6_3, ARTICLE_6_3_A, ARTICLE_6_4), "notes": (ARTICLE_6_4_NOTE, CANDIDATE_FLAGGED_NOTE)}},
    },
    "C23": {
        "features": _features(
            true=("annex_iii_4b_work_relationships", "emotion_recognition_workplace_or_education",
                  "emotion_recognition"),
            domain="none_of_these_areas",
        ),
        "expected": {"t2": {
            "risk_category": "unacceptable_risk", "annex_iii_category": None, "annex_iii_area_unconfirmed": None,
            "high_risk_routes": [], "transparency_duties": [],
        },
        "t3": {"area_conflicts": [_conflict("emotion_recognition"), _conflict("annex_iii_4b_work_relationships")],
               "status": REVIEW},
        "t4": {"article_6_3_exception_candidate": False, "not_cited": (ARTICLE_6_4,)},
        "t5": {"article_50_absent_named": False}},
    },
}

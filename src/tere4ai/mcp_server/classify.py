"""MILESTONE3 runtime tool: classify_ai_system as a pure, deterministic function.

Risk classification is decided by a fixed rule ladder over the structured
system features (schema/json_schemas/system_features.schema.json), never by
a model (@USER.md domain guardrail: the LLM never decides the risk
classification). The ladder is: Article 5 prohibitions, then the Article
6(1) embedded-product route (Annex I plus third-party conformity
assessment), then Article 6(2) plus Annex III high-risk categories, then
Article 6(3) derogation candidacy over the real second-subparagraph
conditions (with the third-subparagraph profiling override), then Article
50 transparency, else minimal risk. Every cited node id
is resolved against the offline Layer 0+1 dump; unknown facts are never
guessed, they surface in missing_facts and lower the status to
requires_human_review where they could change the outcome.
The Article 6(1) route is resolved like an Article 5 path: proven when both of
its facts are true, ruled out when either is known false, open otherwise, and
an open route names its unknown fact and blocks a confident minimal (B123).

The rule logic follows the FLI compliance checker's decision structure as a
classification-logic source and baseline (REF-30, architecture.md Section
8); the text tested against is the frozen Regulation source (REF-01).

@implements: DEC-08, DEC-10 (partial: runtime classification)
@implements: DEC-18
@implements: DEC-23
@implements: DEC-30 (the unacceptable_risk note names a tailored requirement; the sentence of record)
@implements: DEC-32 (the Annex III rule table over the 25 listed uses; annex_iii_listed_uses; the facts corrected by the Act's definitions, fact_conflicts)
@implements: DEC-33 (domain is one of the nine values of the schema, read as given; a refused input returns before any lookup by domain, with the refusal of a domain outside the schema; one Annex III reading, read_annex_iii, in which a true listed use decides the point and a level that rests on the area alone is said, named in annex_iii_area_unconfirmed and marked for human review; area_conflicts, a listed use that is true while domain is none_of_these_areas, marked for human review on every exit; the Article 6(3) candidate of the Annex III part, true, false or null with the unknown conditions named, Article 6(4) cited with a candidate)
@grounded_by: REF-30, REF-17, REF-01
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.mcp_server.application_dates import (
    ROUTE_ANNEX_I,
    ROUTE_ANNEX_III,
    dates_for,
    legal_text,
)
from tere4ai.mcp_server.fria import assess_fria_applicability
from tere4ai.mcp_server.levels import (  # noqa: F401
    LEGACY_LEVEL_VALUES,
    LEVEL_NAMES,
    RISK_CATEGORIES,
    level_name,
)
from tere4ai.mcp_server.removed_facts import (
    DOMAIN_NONE_OF_THESE_AREAS,
    REMOVED_FACT_REPLACEMENTS,
    domain_is_a_value,
    domain_refusal,
)
from tere4ai.mcp_server.review_causes import (
    ANNEX_III_UNKNOWN_TAG,
    STATUS_LINE_PREFIX,
    review_causes,
    review_status_line,
)
from tere4ai.mcp_server.tools import make_envelope

_REPO_ROOT = Path(__file__).resolve().parents[3]
FEATURES_SCHEMA_PATH = _REPO_ROOT / "schema" / "json_schemas" / "system_features.schema.json"

# Article 5(1) prohibition rules: feature flag -> the real Point node in the
# Layer 1 dump. Each point marker was resolved by matching the dump text of
# eu-ai-act:article-5:paragraph-1:point-* (build build-3b753e5e9297); the
# quoted fragment below is from that node's text.
ARTICLE_5_POINT_BY_FLAG: dict[str, tuple[str, str]] = {
    # point (a): "deploys subliminal techniques beyond a person's
    # consciousness or purposefully manipulative or deceptive techniques"
    "subliminal_or_manipulative": (
        "eu-ai-act:article-5:paragraph-1:point-a",
        "subliminal, purposefully manipulative or deceptive techniques that "
        "materially distort behaviour",
    ),
    # point (b): "exploits any of the vulnerabilities of a natural person or a
    # specific group of persons due to their age, disability or a specific
    # social or economic situation"
    "exploits_vulnerabilities": (
        "eu-ai-act:article-5:paragraph-1:point-b",
        "exploitation of vulnerabilities due to age, disability or a specific "
        "social or economic situation",
    ),
    # point (ba), inserted by Regulation (EU) 2026/1744 (B132): "generates or
    # manipulates realistic images, videos, audio or similar material of an
    # identifiable natural person's intimate parts, or of an identifiable
    # natural person engaged in sexually explicit activities, without that
    # person's freely-given, specific, informed, unambiguous and explicit
    # consent"; Article 5(1a) and (1b) say when it prohibits
    # (ARTICLE_5_SCOPING_PARAGRAPHS).
    "generates_nonconsensual_intimate_material": (
        "eu-ai-act:article-5:paragraph-1:point-ba",
        "generating or manipulating realistic intimate or sexually explicit "
        "material of an identifiable person without explicit consent",
    ),
    # point (bb), inserted by Regulation (EU) 2026/1744 (B132): "generates or
    # manipulates material or performance within the meaning of Article 2,
    # points (c) and (e), of Directive 2011/93/EU, except where a 'without
    # right' defence applies under national law"; Article 5(1a) says when.
    "generates_csam": (
        "eu-ai-act:article-5:paragraph-1:point-bb",
        "generating or manipulating child sexual abuse material (Directive "
        "2011/93/EU, Article 2, points (c) and (e))",
    ),
    # point (c): "evaluation or classification of natural persons or groups of
    # persons over a certain period of time based on their social behaviour
    # ... with the social score leading to ..."
    "social_scoring": (
        "eu-ai-act:article-5:paragraph-1:point-c",
        "social scoring leading to detrimental or unfavourable treatment",
    ),
    # point (d): "making risk assessments of natural persons in order to
    # assess or predict the risk of a natural person committing a criminal
    # offence, based solely on the profiling of a natural person"
    "predictive_policing_profiling": (
        "eu-ai-act:article-5:paragraph-1:point-d",
        "predicting the risk of committing a criminal offence based solely on "
        "profiling or personality traits",
    ),
    # point (e): "create or expand facial recognition databases through the
    # untargeted scraping of facial images from the internet or CCTV footage"
    "facial_image_scraping": (
        "eu-ai-act:article-5:paragraph-1:point-e",
        "facial recognition databases built by untargeted scraping of facial "
        "images from the internet or CCTV footage",
    ),
    # point (f): "infer emotions of a natural person in the areas of workplace
    # and education institutions"
    "emotion_recognition_workplace_or_education": (
        "eu-ai-act:article-5:paragraph-1:point-f",
        "inferring emotions of a natural person in the areas of workplace and "
        "education institutions",
    ),
    # point (g): "biometric categorisation systems that categorise
    # individually natural persons based on their biometric data to deduce or
    # infer their race, political opinions, trade union membership, religious
    # or philosophical beliefs, sex life or sexual orientation". DEC-18: the
    # flag means exactly these traits; categorisation by other sensitive or
    # protected attributes is the Annex III point 1(b) fact, and the general
    # Article 3(40) system is biometric_categorisation_system.
    "biometric_categorisation": (
        "eu-ai-act:article-5:paragraph-1:point-g",
        "biometric categorisation deducing or inferring race, political "
        "opinions, trade union membership, religious or philosophical beliefs, "
        "sex life or sexual orientation",
    ),
}

# Article 5(1a) and (1b), inserted with points (ba) and (bb) by Regulation
# (EU) 2026/1744 (B132, spec G D-G68 (6)), say when those points prohibit:
# 5(1a) for both, 5(1b) for point (ba). A hit on the point cites them beside
# it. The flags' schema definitions carry the complete practice, the way
# points (c) to (g) embed their qualifiers. The date the points apply from,
# 2 December 2026, is data from application_dates.py, never control flow.
ARTICLE_5_SCOPING_PARAGRAPHS: dict[str, tuple[str, ...]] = {
    "generates_nonconsensual_intimate_material": (
        "eu-ai-act:article-5:paragraph-1a",
        "eu-ai-act:article-5:paragraph-1b",
    ),
    "generates_csam": ("eu-ai-act:article-5:paragraph-1a",),
}

# point (h): "the use of real-time remote biometric identification systems in
# publicly accessible spaces for the purposes of law enforcement". This one
# needs BOTH flags: the biometric flag and the purpose of law enforcement,
# law_enforcement_purpose, which Article 3(46) defines (B184, DEC-32, as
# amending DEC-18 for point (h)); no Annex III fact is read for it.
ARTICLE_5_POINT_H = "eu-ai-act:article-5:paragraph-1:point-h"
LAW_ENFORCEMENT_PURPOSE_FACT = "law_enforcement_purpose"
ARTICLE_5_POINT_H_FRAGMENT = (
    "real-time remote biometric identification in publicly accessible spaces "
    "for the purposes of law enforcement"
)

# Article 5 statutory qualifiers and exceptions (audit 2026-07-20 D2). Each
# qualified point carries an EXCULPATING FACT: a boolean the caller can set
# that, when equal to `exculpating_value`, means the prohibition does NOT
# apply (the statute's exception is met, or its harm/outcome element is
# absent). When the fact is unknown the ban is not settled, so the system is
# routed to human review instead of being confidently prohibited; only an
# explicit non-exculpating value yields a confident prohibition. The point
# with no entry (facial image scraping, (e)) is a clean 1:1 with no statutory
# exception. Anchors are the frozen point texts.
# Tuple: (fact_name, exculpating_value, human-readable element description).
ARTICLE_5_EXCULPATING_FACT: dict[str, tuple[str, bool, str]] = {
    # (a)/(b) prohibit only "in a manner that causes or is reasonably likely
    # to cause ... significant harm"; without that element, not prohibited.
    "subliminal_or_manipulative": (
        "causes_significant_harm",
        False,
        "the point (a) 'significant harm' element",
    ),
    "exploits_vulnerabilities": (
        "causes_significant_harm",
        False,
        "the point (b) 'significant harm' element",
    ),
    # (c) prohibits social scoring "leading to detrimental or unfavourable
    # treatment" in unrelated contexts or unjustified/disproportionate.
    "social_scoring": (
        "social_score_detrimental_treatment",
        False,
        "the point (c) detrimental-treatment element",
    ),
    # (d) "this prohibition shall not apply to AI systems used to support the
    # human assessment of the involvement of a person in a criminal activity,
    # which is already based on objective and verifiable facts directly linked
    # to a criminal activity" (DEC-18: the fact carries the Act's words).
    "predictive_policing_profiling": (
        "supports_human_assessment_on_verifiable_facts",
        True,
        "the point (d) exception (support of a human assessment already based "
        "on objective and verifiable facts directly linked to a criminal activity)",
    ),
    # (f) "except where ... intended ... for medical or safety reasons".
    "emotion_recognition_workplace_or_education": (
        "emotion_recognition_medical_or_safety",
        True,
        "the point (f) medical or safety exception",
    ),
    # (g) "this prohibition does not cover any labelling or filtering of
    # lawfully acquired biometric datasets, such as images, based on
    # biometric data or categorizing of biometric data in the area of law
    # enforcement" (DEC-18: the fact carries the Act's words; a
    # law-enforcement user alone does not meet it).
    "biometric_categorisation": (
        "biometric_categorisation_lawful_or_law_enforcement",
        True,
        "the point (g) exception (labelling or filtering of lawfully acquired "
        "biometric datasets, or categorising of biometric data in the area of "
        "law enforcement)",
    ),
}
# (h) real-time RBI for law enforcement is conditionally permitted where
# "strictly necessary" for objectives (i) to (iii) and duly authorised.
ARTICLE_5_POINT_H_EXCULPATING = (
    "rtrb_strictly_necessary_authorised",
    True,
    "the point (h) strict-necessity and authorisation carve-out (i) to (iii)",
)

REMOVED_FACT_LINE = "flags.{removed} left the schema (DEC-32); answer {replacements}"

# Flags whose unknown value can change the prohibition outcome. Absence is
# NOT treated as false (system_features.schema.json). law_enforcement_purpose
# can change it too, but only while real_time_remote_biometric_public is true,
# so the point (h) rule names it there and it is not listed here (B184,
# DEC-32); the exculpating facts are named by their own rule in the same way.
PROHIBITION_RELEVANT_FLAGS: tuple[str, ...] = (
    *ARTICLE_5_POINT_BY_FLAG.keys(),
    "real_time_remote_biometric_public",
)

# Article 6(2) + Annex III (B184, spec G D-G91, DEC-32): the eight high-risk
# points, each cited by its real AnnexItem node (eu-ai-act:annex-iii:point-1
# .. point-8 in the dump), read through the 25 listed uses, one fact each,
# paired with the legal unit the fact quotes whole (system_features.schema.json,
# x-annex-iii-area and x-annex-iii-use). A point matches when one of its
# listed-use facts is true; point 1 also matches on
# real_time_remote_biometric_public (also_matching), which reaches point 1(a)
# and does not count for the area (ruling P5). B185 (DEC-33, rulings P2 and
# P4): each point has one value of `domain`, the schema's value of its area
# (x-annex-iii-area-values); read_annex_iii reads the domain's point only when
# no listed use of any point is true (spec G D-G92 (2) and (ii)). Checked in
# point order; the first point with a true fact becomes annex_iii_category. The introductory
# words of points 1, 6 and 7 ("in so far as their use is permitted under
# relevant Union or national law") are printed by the schema and are not a
# fact.
# @implements: DEC-32
# @implements: DEC-33
ANNEX_III_RULES: tuple[dict[str, Any], ...] = (
    {
        # point 1: "Biometrics, in so far as their use is permitted under
        # relevant Union or national law: (a) remote biometric identification
        # systems ..."; (b) biometric categorisation according to sensitive or
        # protected attributes (DEC-18); (c) emotion recognition.
        "node": "eu-ai-act:annex-iii:point-1",
        "label": "biometrics",
        "uses": (
            ("biometric_identification", "eu-ai-act:annex-iii:point-1:a"),
            ("biometric_categorisation_sensitive_or_protected_attributes", "eu-ai-act:annex-iii:point-1:b"),
            ("emotion_recognition", "eu-ai-act:annex-iii:point-1:c"),
        ),
        "also_matching": (("real_time_remote_biometric_public", "eu-ai-act:annex-iii:point-1:a"),),
        "domain": "biometrics",
    },
    {
        # point 2: "Critical infrastructure: AI systems intended to be used
        # as safety components in the management and operation of critical
        # digital infrastructure, road traffic, or in the supply of water,
        # gas, heating or electricity." The point has no sub-node, so its
        # listed use is the point itself.
        "node": "eu-ai-act:annex-iii:point-2",
        "label": "critical infrastructure",
        "uses": (("critical_infrastructure_safety", "eu-ai-act:annex-iii:point-2"),),
        "also_matching": (),
        "domain": "critical_infrastructure",
    },
    {
        # point 3: "Education and vocational training: (a) AI systems
        # intended to be used to determine access or admission ..." and (b)
        # to (d).
        "node": "eu-ai-act:annex-iii:point-3",
        "label": "education and vocational training",
        "uses": (
            ("annex_iii_3a_admission", "eu-ai-act:annex-iii:point-3:a"),
            ("annex_iii_3b_learning_outcomes", "eu-ai-act:annex-iii:point-3:b"),
            ("annex_iii_3c_education_level", "eu-ai-act:annex-iii:point-3:c"),
            ("annex_iii_3d_test_monitoring", "eu-ai-act:annex-iii:point-3:d"),
        ),
        "also_matching": (),
        "domain": "education",
    },
    {
        # point 4: "Employment, workers' management and access to
        # self-employment: (a) AI systems intended to be used for the
        # recruitment or selection of natural persons ..." and (b).
        "node": "eu-ai-act:annex-iii:point-4",
        "label": "employment and workers management",
        "uses": (
            ("annex_iii_4a_recruitment", "eu-ai-act:annex-iii:point-4:a"),
            ("annex_iii_4b_work_relationships", "eu-ai-act:annex-iii:point-4:b"),
        ),
        "also_matching": (),
        "domain": "employment",
    },
    {
        # point 5: "Access to and enjoyment of essential private services and
        # essential public services and benefits: (a) AI systems intended to
        # be used by public authorities or on behalf of public authorities to
        # evaluate ..." and (b) to (d). The 5(b) and 5(c) facts also feed the
        # FRIA rule (fria.py, DEC-14).
        "node": "eu-ai-act:annex-iii:point-5",
        "label": "essential private and public services",
        "uses": (
            ("annex_iii_5a_public_benefits", "eu-ai-act:annex-iii:point-5:a"),
            ("creditworthiness_evaluation", "eu-ai-act:annex-iii:point-5:b"),
            ("life_health_insurance_risk_pricing", "eu-ai-act:annex-iii:point-5:c"),
            ("annex_iii_5d_emergency_calls", "eu-ai-act:annex-iii:point-5:d"),
        ),
        "also_matching": (),
        "domain": "essential_services",
    },
    {
        # point 6: "Law enforcement, in so far as their use is permitted
        # under relevant Union or national law: (a) AI systems intended to be
        # used by or on behalf of law enforcement authorities ..." and (b) to
        # (e). The purpose of law enforcement (law_enforcement_purpose,
        # Article 3(46)) is an Article 5(1)(h) fact, not a point 6 fact.
        "node": "eu-ai-act:annex-iii:point-6",
        "label": "law enforcement",
        "uses": (
            ("annex_iii_6a_victim_risk", "eu-ai-act:annex-iii:point-6:a"),
            ("annex_iii_6b_polygraphs", "eu-ai-act:annex-iii:point-6:b"),
            ("annex_iii_6c_evidence_reliability", "eu-ai-act:annex-iii:point-6:c"),
            ("annex_iii_6d_offending_risk", "eu-ai-act:annex-iii:point-6:d"),
            ("annex_iii_6e_profiling", "eu-ai-act:annex-iii:point-6:e"),
        ),
        "also_matching": (),
        "domain": "law_enforcement",
    },
    {
        # point 7: "Migration, asylum and border control management, in so
        # far as their use is permitted under relevant Union or national law:
        # (a) AI systems intended to be used by or on behalf of competent
        # public authorities ..." and (b) to (d).
        "node": "eu-ai-act:annex-iii:point-7",
        "label": "migration, asylum and border control",
        "uses": (
            ("annex_iii_7a_polygraphs", "eu-ai-act:annex-iii:point-7:a"),
            ("annex_iii_7b_entry_risk", "eu-ai-act:annex-iii:point-7:b"),
            ("annex_iii_7c_applications", "eu-ai-act:annex-iii:point-7:c"),
            ("annex_iii_7d_identification", "eu-ai-act:annex-iii:point-7:d"),
        ),
        "also_matching": (),
        "domain": "migration",
    },
    {
        # point 8: "Administration of justice and democratic processes: (a)
        # AI systems intended to be used by a judicial authority or on their
        # behalf ..." and (b).
        "node": "eu-ai-act:annex-iii:point-8",
        "label": "administration of justice and democratic processes",
        "uses": (
            ("annex_iii_8a_judicial", "eu-ai-act:annex-iii:point-8:a"),
            ("annex_iii_8b_elections", "eu-ai-act:annex-iii:point-8:b"),
        ),
        "also_matching": (),
        "domain": "justice",
    },
)

# B185 (DEC-33, ruling P2): each value of `domain` that names an area, to the
# node of its Annex III point; none_of_these_areas (DOMAIN_NONE_OF_THESE_AREAS,
# defined once in removed_facts.py beside the refusal) names no area.
ANNEX_III_POINT_OF_DOMAIN: dict[str, str] = {rule["domain"]: rule["node"] for rule in ANNEX_III_RULES}

# The 25 listed-use facts, in point order (B184, DEC-32).
ANNEX_III_LISTED_USE_FACTS: tuple[str, ...] = tuple(
    fact for rule in ANNEX_III_RULES for fact, _unit in rule["uses"]
)

# The legal unit each Annex III fact is read for: the 25 listed uses, and
# real_time_remote_biometric_public, which reaches point 1(a).
ANNEX_III_UNIT_OF_FACT: dict[str, str] = {
    fact: unit
    for rule in ANNEX_III_RULES
    for fact, unit in (*rule["uses"], *rule["also_matching"])
}

# Flags whose unknown value can change an Annex III high-risk outcome: the 25
# listed uses, then real_time_remote_biometric_public. Like the prohibition
# flags, absence is NOT treated as false: an unknown Annex III fact is
# surfaced in missing_facts and blocks a confident minimal_risk verdict
# (audit 2026-07-20 D1). Built from the rule table so it can never drift from
# the categories. A flag that is also an Article 5 flag
# (real_time_remote_biometric_public) stays in this list: its Article 5 path
# can be ruled out while its Annex III one is not (DEC-18). Since B185 Task 7's
# follow-up the ladder names it under both tags when both sides are open
# (spec G D-G92 (2)); until then it skipped the Annex III tag when the Article
# 5 side already named it.
ANNEX_III_RELEVANT_FLAGS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *ANNEX_III_LISTED_USE_FACTS,
            *(fact for rule in ANNEX_III_RULES for fact, _unit in rule["also_matching"]),
        )
    )
)

# B184 (ruling P7): the rationale line of each further listed use that is
# true, as answered or as it follows from another fact by a definition of the
# Act (Task 4), so the line never says "answered yes". Deliberately not the
# "rule X: flag Y matches Z" grammar, which scripts/elicitation_error_report.py
# parses as the classification trigger.
ANNEX_III_LISTED_USE_LINE = (
    "Annex III listed use true: flag {fact} is true for {unit}; cited with the answer"
)


def annex_iii_listed_uses(flags: dict[str, Any]) -> list[str]:
    """The legal units of the listed-use facts that are true, in point order.

    real_time_remote_biometric_public is not among them: it reaches point
    1(a) through the entailment of Article 3(42) (B184 Task 4).

    @implements: DEC-32
    """
    if not isinstance(flags, dict):
        return []
    return [
        unit
        for rule in ANNEX_III_RULES
        for fact, unit in rule["uses"]
        if flags.get(fact) is True
    ]


def _annex_iii_trigger_fact(rule: dict[str, Any], flags: dict[str, Any]) -> str | None:
    """The first true fact of a point: its listed uses, then also_matching.

    @implements: DEC-32
    """
    return next(
        (fact for fact, _unit in (*rule["uses"], *rule["also_matching"]) if flags.get(fact) is True),
        None,
    )


def _every_listed_use_false(rule: dict[str, Any], flags: dict[str, Any]) -> bool:
    """Whether every listed use of a point is known false, so the domain no
    longer counts (ELICITATION_ERRORS.md, scenario 161; DEC-32)."""
    return bool(rule["uses"]) and all(flags.get(fact) is False for fact, _unit in rule["uses"])


# B185 (spec G D-G92 (3), (5) and (ii), DEC-33, ruling P7): the fixed lines of
# a point that rests on the area. {number} is the point's number, {heading} its
# heading in the schema (annex_iii_area_headings), {facts} its listed uses
# still unknown, joined by ", ". The first two go into legal_status_notes, the
# last two into the rationale. The rule line has a rule name of its own,
# high_risk_area_alone, apart from the grammar "rule high_risk: domain ...
# matches" of the runs before B185 (TRIGGER_DOMAIN_RE); scripts/
# elicitation_error_report.py reads it as the domain's trigger through
# TRIGGER_AREA_RE, so its words change only together with that pattern.
ANNEX_III_AREA_ALONE_LINE = (
    "{node}: the level rests on the area alone: domain '{domain}' places the system in Annex III point "
    "{number} ({heading}), and no listed use of the point is confirmed; the listed uses still unknown: {facts}"
)
ANNEX_III_SCOPE_UNCONFIRMED_LINE = (
    "{node}: domain '{domain}' places the system in Annex III point {number} ({heading}), but no listed use "
    "of the point is confirmed, so the Annex III scope is not confirmed and the answer rests on the Article "
    "6(1) route; the listed uses still unknown: {facts}"
)
ANNEX_III_AREA_RULED_OUT_LINE = (
    "domain '{domain}' names Annex III point {number} ({node}), but every listed use of the category is "
    "answered false, so the area does not count (ELICITATION_ERRORS.md, scenario 161)"
)
ANNEX_III_AREA_ALONE_RULE_LINE = (
    "rule high_risk_area_alone: domain '{domain}' names Annex III point {number} ({node}) and no listed use "
    "of any point is true; high_risk on the area alone, for human review"
)


@lru_cache(maxsize=1)
def _features_schema() -> dict[str, Any]:
    return json.loads(FEATURES_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def annex_iii_area_headings() -> dict[str, str]:
    """The Act's heading of each Annex III point, keyed by its number as a
    string, read once from the schema (flags["x-annex-iii-areas"]).

    @implements: DEC-33
    """
    return dict(_features_schema()["properties"]["flags"]["x-annex-iii-areas"])


@dataclass(frozen=True)
class AnnexIIIReading:
    """One reading of Annex III for one input (B185, spec G D-G92, ruling P4).

    confirmed: the point nodes with a true fact of their listed uses or of
    also_matching, in point order. first_rule and trigger_fact: the rule of
    confirmed[0] and its first true fact. area_point: the domain's point, set
    only when confirmed is empty and not every listed use of that point is
    false; area_unknown_uses: its listed uses absent from the flags, in point
    order. area_ruled_out: confirmed is empty, the domain names an area and
    every listed use of it is false.
    """

    confirmed: tuple[str, ...]
    first_rule: dict[str, Any] | None
    trigger_fact: str | None
    area_point: str | None
    area_unknown_uses: tuple[str, ...]
    area_ruled_out: bool


def read_annex_iii(flags: dict[str, Any], domain: str | None) -> AnnexIIIReading:
    """Read Annex III once: a listed use that is true decides the point, and the
    domain's point is read only when no listed use of any point is true.

    Spec G D-G92 (2), (3) and (ii): the confirmed points are those with a true
    fact (as answered or as it follows from a definition of the Act, since
    classify_ai_system corrects the facts first); with none, a domain that
    names an area gives the point that rests on the area while a listed use of
    it is not known false, and the area stops counting when every listed use
    of it is false (ELICITATION_ERRORS.md, scenario 161). A true listed use
    anywhere means the domain is not read. Every reader of Annex III (the
    exits, the Section B checks, the routes, the citations, the dates and
    the FRIA block, which counts only the confirmed points as areas) reads
    this one reading.

    @implements: DEC-32
    @implements: DEC-33
    """
    confirmed_rules = [rule for rule in ANNEX_III_RULES if _annex_iii_trigger_fact(rule, flags) is not None]
    if confirmed_rules:
        first = confirmed_rules[0]
        return AnnexIIIReading(
            confirmed=tuple(rule["node"] for rule in confirmed_rules),
            first_rule=first,
            trigger_fact=_annex_iii_trigger_fact(first, flags),
            area_point=None,
            area_unknown_uses=(),
            area_ruled_out=False,
        )
    node = ANNEX_III_POINT_OF_DOMAIN.get(domain) if isinstance(domain, str) else None
    rule = next((r for r in ANNEX_III_RULES if r["node"] == node), None)
    if rule is None:
        return AnnexIIIReading((), None, None, None, (), False)
    if _every_listed_use_false(rule, flags):
        return AnnexIIIReading((), None, None, None, (), True)
    return AnnexIIIReading(
        confirmed=(),
        first_rule=None,
        trigger_fact=None,
        area_point=rule["node"],
        area_unknown_uses=tuple(fact for fact, _unit in rule["uses"] if fact not in flags),
        area_ruled_out=False,
    )


def annex_iii_area_line(template: str, reading: AnnexIIIReading, domain: str) -> str:
    """One of the fixed area lines, filled for the domain's point (ruling P7).

    @implements: DEC-33
    """
    node = ANNEX_III_POINT_OF_DOMAIN[domain]
    number = _features_schema()["properties"]["domain"]["x-annex-iii-area-values"][domain]
    return template.format(
        node=node,
        domain=domain,
        number=number,
        heading=annex_iii_area_headings()[str(number)],
        facts=", ".join(reading.area_unknown_uses),
    )


# DEC-18: exculpating facts that settle their Article 5 point even when the
# point's own flag is absent, because each is the statute's complete element
# or exception for that point: (a) and (b) significant harm, (c) the
# detrimental-treatment element, (f) the medical or safety exception. The
# point (d) and (g) facts are left out on purpose: their definitions were
# wider than the Act's exceptions, so an answer of "no" must not rest on
# them. Point (h) is handled in _unresolved_article_5_facts.
ARTICLE_5_CLEARS_ABSENT_FLAG: frozenset[str] = frozenset(
    {
        "subliminal_or_manipulative",
        "exploits_vulnerabilities",
        "social_scoring",
        "emotion_recognition_workplace_or_education",
    }
)

# B184 (spec G D-G91 (6) and (10), DEC-32, rulings R4, R6, R7, P9): the facts
# that follow from the Act's definitions, as (narrower, wider, provision), the
# provision being the legal unit of the definition. Article 3(40) defines a
# biometric categorisation system as "an AI system for the purpose of
# assigning natural persons to specific categories on the basis of their
# biometric data"; Annex III point 1(b) lists "AI systems intended to be used
# for biometric categorisation, according to sensitive or protected
# attributes or characteristics", which hold the traits point (g) names;
# Article 3(42) defines a real-time remote biometric identification system as
# "a remote biometric identification system, whereby the capturing of
# biometric data, the comparison and the identification all occur without a
# significant delay"; Article 3(39) defines an emotion recognition system as
# "an AI system for the purpose of identifying or inferring emotions or
# intentions of natural persons on the basis of their biometric data". An
# exception answered yes while its practice is answered no is not a
# contradiction, so no exception fact is in this table.
FACT_ENTAILMENTS: tuple[tuple[str, str, str], ...] = (
    ("biometric_categorisation", "biometric_categorisation_system", "eu-ai-act:article-3:paragraph-1:point-40"),
    ("biometric_categorisation", "biometric_categorisation_sensitive_or_protected_attributes", "eu-ai-act:annex-iii:point-1:b"),
    ("real_time_remote_biometric_public", "biometric_identification", "eu-ai-act:article-3:paragraph-1:point-42"),
    ("emotion_recognition_workplace_or_education", "emotion_recognition", "eu-ai-act:article-3:paragraph-1:point-39"),
)

# The line among the missing facts for a pair answered against its definition
# (the spec's sentence, D-G91 (10)), the rationale line for a wider fact read
# true from unknown, and the status line of a marked answer (ruling P10).
FACT_CONFLICT_LINE = (
    "flags.{wider} was answered false while flags.{narrower} is true; {provision} makes the "
    "first follow from the second, so it is read as true; one of the two answers is wrong"
)
FACT_ENTAILED_FROM_UNKNOWN_LINE = (
    "flags.{wider} is unknown while flags.{narrower} is true; {provision} makes the "
    "first follow from the second, so it is read as true"
)
# B185 Task 6 (ruling P11): the status line of the cause fact_conflict.
FACT_CONFLICT_STATUS_LINE = review_status_line("fact_conflict", {})


def fact_conflict_line(narrower: str, wider: str, provision: str) -> str:
    """The line among the missing facts for one pair of FACT_ENTAILMENTS
    whose wider fact was answered false (D-G91 (10)).

    @implements: DEC-32
    """
    return FACT_CONFLICT_LINE.format(narrower=narrower, wider=wider, provision=provision)


# B185 (spec G D-G92 (4) and (iii), DEC-33): the note of each entry of
# area_conflicts, the spec's words, which also joins the missing facts, and
# the rationale's status line of an answer it marks (B185 Task 6: the status
# line of the cause area_conflict, from review_causes.py).
AREA_CONFLICT_NOTE = "domain is none_of_these_areas while flags.{fact} is true; the fact keeps its effect"
AREA_CONFLICT_STATUS_LINE = review_status_line("area_conflict", {})


def area_conflicts(flags: dict[str, Any], domain: str | None) -> list[dict[str, str]]:
    """One entry per listed use of Annex III that is true while domain is
    none_of_these_areas, in point order (spec G D-G92 (4) and (iii)).

    flags are the facts as classify_ai_system corrects them (apply_entailments),
    so a listed use that follows from a definition of the Act counts as one
    answered true. Each entry is {"domain", "fact", "note"}. Any other domain,
    unknown included, gives no entry, and a listed use that is false or
    unknown never gives one: none_of_these_areas is never a reason to read a
    listed use as no, and the true fact keeps its effect.

    @implements: DEC-33
    """
    if domain != DOMAIN_NONE_OF_THESE_AREAS or not isinstance(flags, dict):
        return []
    return [
        {"domain": DOMAIN_NONE_OF_THESE_AREAS, "fact": fact, "note": AREA_CONFLICT_NOTE.format(fact=fact)}
        for fact in ANNEX_III_LISTED_USE_FACTS
        if flags.get(fact) is True
    ]


def apply_entailments(
    flags: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    """The flags corrected by FACT_ENTAILMENTS (B184, D-G91 (6) and (10)).

    Returns a new flags dict (the input is never mutated), the conflict
    entries {narrower, wider, provision, note} for each pair whose narrower
    fact is true and whose wider fact was answered false, and the rationale
    lines for each wider fact read true from unknown (absent). Only `is True`
    and `is False` are read: a wider fact present with any other value is
    left as it is, so the schema still refuses it, and the narrower fact is
    never changed.

    @implements: DEC-32
    """
    corrected = dict(flags)
    conflicts: list[dict[str, str]] = []
    unknown_lines: list[str] = []
    for narrower, wider, provision in FACT_ENTAILMENTS:
        if flags.get(narrower) is not True:
            continue
        if flags.get(wider) is False:
            corrected[wider] = True
            conflicts.append(
                {
                    "narrower": narrower,
                    "wider": wider,
                    "provision": provision,
                    "note": fact_conflict_line(narrower, wider, provision),
                }
            )
        elif wider not in flags:
            corrected[wider] = True
            unknown_lines.append(
                FACT_ENTAILED_FROM_UNKNOWN_LINE.format(narrower=narrower, wider=wider, provision=provision)
            )
    return corrected, conflicts, unknown_lines


def _unresolved_article_5_facts(flags: dict[str, Any]) -> list[str]:
    """Absent facts that leave an Article 5 path unresolved (DEC-18).

    A path is ruled out when its flag is false, or when its exculpating fact
    is known and exculpating (only for the points in
    ARTICLE_5_CLEARS_ABSENT_FLAG, and for point (h)). A path whose flag is
    true is resolved by the Article 5 rule itself (proven, exception met, or
    pending exception fact), so only absent flags are returned here. Point
    (h) needs both real_time_remote_biometric_public and
    law_enforcement_purpose (Article 3(46)): either known false, or the
    strict-necessity carve-out known true, rules it out (DEC-18 as amended
    by DEC-32); the purpose is asked for by the Article 5 rule when the
    biometric flag is true.

    @implements: DEC-18
    @implements: DEC-32
    """
    missing: list[str] = []
    for flag in ARTICLE_5_POINT_BY_FLAG:
        if flag in flags:
            continue
        exculpating = ARTICLE_5_EXCULPATING_FACT.get(flag)
        if flag in ARTICLE_5_CLEARS_ABSENT_FLAG and exculpating is not None:
            fact_name, exculpating_value, _desc = exculpating
            if flags.get(fact_name) is exculpating_value:
                continue
        missing.append(flag)
    point_h_ruled_out = (
        flags.get("real_time_remote_biometric_public") is False
        or flags.get(LAW_ENFORCEMENT_PURPOSE_FACT) is False
        or flags.get(ARTICLE_5_POINT_H_EXCULPATING[0]) is ARTICLE_5_POINT_H_EXCULPATING[1]
    )
    if not point_h_ruled_out and "real_time_remote_biometric_public" not in flags:
        missing.append("real_time_remote_biometric_public")
    return missing


ARTICLE_5_OTHER_FACT_LINE = (
    "flags.{fact} is unknown (prohibition-relevant, Article 5); answered {value}, it rules out {points} "
    "while {open_facts} {verb} unknown, so absence is not treated as false"
)


def _joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _article_5_other_fact_lines(flags: dict[str, Any]) -> list[tuple[str, str]]:
    """The other fact of each open Article 5 point, with its line (B185, the
    evidence task; DEC-18).

    A point whose own flag is unknown is open, and _unresolved_article_5_facts
    names that flag. The point's other fact can rule it out on its own where
    it is the statute's complete element or exception (the points of
    ARTICLE_5_CLEARS_ABSENT_FLAG: (a) and (b) significant harm, (c) the
    detrimental treatment, (f) the medical or safety exception) and, for point
    (h), the purpose of law enforcement (false) and the strict-necessity
    carve-out (true). Absent, it was named nowhere, so the answer read as if
    it were the value that keeps the point open. It is returned here, as
    (fact, line), while its point is open and only then: never when the point
    is ruled out by another fact, never for the point (d) and (g) exception
    facts, which rule out nothing while their flag is unknown (DEC-18), and
    the caller adds the lines past the Article 5 rule only, since on the
    unacceptable_risk exit no other point can change the answer. A fact whose
    point has its flag true is named by the Article 5 rule itself (pending
    exception) and the purpose beside a true biometric fact by the point (h)
    rule (DEC-32), so the caller skips a fact already named.

    @implements: DEC-18
    @implements: DEC-33
    """
    open_points: dict[str, list[str]] = {}
    for flag, (node_id, _fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        if flag not in ARTICLE_5_CLEARS_ABSENT_FLAG or flag in flags:
            continue
        fact, _value, _desc = ARTICLE_5_EXCULPATING_FACT[flag]
        if fact not in flags:
            open_points.setdefault(fact, []).append(flag)
    lines: list[tuple[str, str]] = []
    for fact, point_flags in open_points.items():
        value = ARTICLE_5_EXCULPATING_FACT[point_flags[0]][1]
        letters = [f"({ARTICLE_5_POINT_BY_FLAG[f][0].rsplit('-', 1)[1]})" for f in point_flags]
        lines.append((fact, ARTICLE_5_OTHER_FACT_LINE.format(
            fact=fact,
            value=str(value).lower(),
            points=("point " if len(letters) == 1 else "points ") + _joined(letters),
            open_facts=_joined([f"flags.{f}" for f in point_flags]),
            verb="is" if len(point_flags) == 1 else "are",
        )))
    biometric = "real_time_remote_biometric_public"
    carve_out, carve_out_value, _desc = ARTICLE_5_POINT_H_EXCULPATING
    point_h_ruled_out = (
        flags.get(biometric) is False
        or flags.get(LAW_ENFORCEMENT_PURPOSE_FACT) is False
        or flags.get(carve_out) is carve_out_value
    )
    unknown_h = [f for f in (biometric, LAW_ENFORCEMENT_PURPOSE_FACT) if f not in flags]
    if not point_h_ruled_out and unknown_h:
        for fact, value in ((LAW_ENFORCEMENT_PURPOSE_FACT, False), (carve_out, carve_out_value)):
            if fact in flags:
                continue
            keeping_open = [f for f in unknown_h if f != fact]
            if not keeping_open:
                continue
            lines.append((fact, ARTICLE_5_OTHER_FACT_LINE.format(
                fact=fact,
                value=str(value).lower(),
                points="point (h)",
                open_facts=_joined([f"flags.{f}" for f in keeping_open]),
                verb="is" if len(keeping_open) == 1 else "are",
            )))
    return lines

ARTICLE_6_PARAGRAPH_1 = "eu-ai-act:article-6:paragraph-1"
ARTICLE_6_PARAGRAPH_2 = "eu-ai-act:article-6:paragraph-2"
ARTICLE_6_PARAGRAPH_3 = "eu-ai-act:article-6:paragraph-3"
# B185 (spec G D-G92 (6), ruling P9): cited with every Article 6(3) candidate.
ARTICLE_6_PARAGRAPH_4 = "eu-ai-act:article-6:paragraph-4"
ANNEX_I = "eu-ai-act:annex-i"
# Article 6(3) third subparagraph: "shall always be considered to be
# high-risk where the AI system performs profiling of natural persons".
ARTICLE_6_3_PROFILING_OVERRIDE = "eu-ai-act:article-6:paragraph-3:subparagraph-3"

# B123 (spec G D-G59): the two facts of the Article 6(1) route. Article
# 6(1) points (a) and (b) are cumulative, so the route is resolved like an
# Article 5 path (DEC-18): proven when both are true, ruled out when either
# is known false, open otherwise.
ARTICLE_6_1_FLAGS: tuple[str, str] = (
    "annex_i_covered_product",
    "third_party_conformity_assessment_required",
)

# B132 (spec G D-G68 (6), rulings R6, R14, R26 and R36): the Annex I section
# of an Article 6(1) system's product legislation, a third fact of the
# route. True means Section B (points 13 to 21), false Section A (points 2
# to 12), absent unknown. The level is high_risk under either section. For
# Section B, Article 2(2) applies to the Article 6(1) classification only
# the provisions it names: not the Chapter III requirements, not Article 50.
# It limits only what that classification brings, so the Annex III rules
# are still checked and a match decides the route (R26). An unknown section
# never reads as Section B: the level and the status rules do not change,
# the fact is named (R14).
ANNEX_I_SECTION_FACT = "annex_i_section_b_legislation"
ARTICLE_2_PARAGRAPH_2 = "eu-ai-act:article-2:paragraph-2"
# Article 2(2), verbatim from its Layer 1 node (tests/unit/test_classify.py).
ARTICLE_2_2_WORDING = (
    "For AI systems classified as high-risk AI systems in accordance with Article 6(1) related to products "
    "covered by the Union harmonisation legislation listed in Section B of Annex I, only Article 6(1), "
    "Article 60a and Articles 102 to 112 shall apply."
)
ARTICLE_2_2_CONDITION = (
    "Articles 57, 58 and 59 shall apply only in so far as the requirements for high-risk AI systems under "
    "this Regulation have been integrated in that Union harmonisation legislation."
)
# The provisions Article 2(2) applies, then the three it applies on its condition.
ARTICLE_2_2_PROVISIONS: tuple[str, ...] = (
    "eu-ai-act:article-6:paragraph-1",
    "eu-ai-act:article-60a",
    *(f"eu-ai-act:article-{number}" for number in range(102, 113)),
)
ARTICLE_2_2_CONDITIONAL_PROVISIONS: tuple[str, ...] = (
    "eu-ai-act:article-57",
    "eu-ai-act:article-58",
    "eu-ai-act:article-59",
)
# Named on the Article 6(1) exit while the section is unknown (R14), and by
# get_applicable_requirements beside the Chapter III requirements it serves.
ANNEX_I_SECTION_UNKNOWN_FACT = (
    f"flags.{ANNEX_I_SECTION_FACT} is unknown (the Annex I section of the "
    "product's legislation); the level is high_risk under either section, "
    "but for a Section B product Article 2(2) applies only the provisions "
    "it names, not the Chapter III requirements"
)
SECTION_B_NOTE = (
    f"{ARTICLE_2_PARAGRAPH_2}: the product's legislation is listed in Annex I Section B; Article 2(2): "
    f"\"{ARTICLE_2_2_WORDING} {ARTICLE_2_2_CONDITION}\" The Chapter III requirements do not apply to "
    "it; whether that condition holds is not decided here"
)
# R36: where the Article 50 duties would be listed for a system high-risk
# only under Article 6(1) with Section B legislation.
ARTICLE_50_SECTION_B_NOTE = (
    "eu-ai-act:article-50: no transparency duty is listed: Article 2(2) applies only Article 6(1), "
    "Article 60a and Articles 102 to 112 to a system high-risk under Article 6(1) whose product "
    "legislation is listed in Annex I Section B"
)
# R37: the high-risk routes that hold, on every high_risk answer
# (high_risk_routes), so the dates and the requirements follow every route,
# not only the one that decided the answer (annex_iii_category stays the
# deciding route's field: none when the Article 6(1) route decided).
HIGH_RISK_ROUTE_ARTICLE_6_1 = "article_6_1"
HIGH_RISK_ROUTE_ARTICLE_6_2 = "article_6_2"
# R39: the words that mark an unknown Annex III fact among the missing facts,
# which get_applicable_requirements reads for a Section B system, are
# ANNEX_III_UNKNOWN_TAG, imported from review_causes.py (B185 Task 6), where
# the cause listed_use_unknown reads them.
# The end of the legal_status_notes line each Article 5 hit of an
# unacceptable_risk answer gives.
PROHIBITED_PRACTICE_NOTE_END = (
    "placing on the market, putting into service, and use are banned, so no "
    "tailored requirement can make the system permissible"
)
# B184 (spec G D-G91, DEC-32, rulings R2, R12, P8): the end of that line when
# point (h) is the only prohibition that fired. Point (h) prohibits "the use
# of 'real-time' remote biometric identification systems in publicly
# accessible spaces for the purposes of law enforcement", not the placing on
# the market; the system is listed in Annex III point 1(a). With another
# point beside it, every line keeps PROHIBITED_PRACTICE_NOTE_END.
POINT_H_PRACTICE_NOTE_END = (
    "point (h) prohibits the use for the purposes of law enforcement in publicly "
    "accessible spaces and does not prohibit placing on the market; the system is "
    "listed in Annex III point 1(a), and no tailored requirement can make the "
    "prohibited use permissible"
)
# B184 (DEC-32; final review, M3): the clause a prohibited answer marked by a
# fact conflict adds to each of its prohibited-practice notes, and the
# applicable requirements to their message.
PROHIBITION_FACT_CONFLICT_CLAUSE = (
    "This rests on the facts as read: answers contradict a definition of the Act (fact_conflicts), so it "
    "stands for human review."
)
# B185 (DEC-33, ruling P26): the clause a prohibited answer marked by an area
# conflict adds to each of its prohibited-practice notes, after the fact
# conflict's clause when both hold, and the applicable requirements to their
# message.
PROHIBITION_AREA_CONFLICT_CLAUSE = (
    "This rests on the facts as read: a listed use is true while domain is none_of_these_areas "
    "(area_conflicts), so it stands for human review."
)
# The rationale line of each Article 5 hit ("rule unacceptable_risk: flag X
# matches <node> (...)"); the applicable requirements read the point from it
# when they are given the bare answer, which carries no cited provisions.
PROHIBITED_RULE_LINE = re.compile(r"^rule unacceptable_risk: flag .+? matches (?P<node>eu-ai-act:article-5:\S+) \(")
PROHIBITED_PRACTICE_NOTE_MARK = "this practice is a prohibited AI practice under Article 5(1)"

# B181 (DEC-30): the end a session recorded before the rename keeps; the
# parity test reads it through prohibited_practice_note_of_record.
PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181 = (
    "placing on the market, putting into service, and use are banned, so no "
    "engineering requirement can make the system permissible"
)


def prohibited_practice_note_of_record(text: str) -> str:
    """The live line for a line a session recorded before B181 holds (its end
    PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181); any other text unchanged."""
    if text.endswith("; " + PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181):
        return text[: -len(PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181)] + PROHIBITED_PRACTICE_NOTE_END
    return text


# R26: a Section B product whose facts also match an Annex III category.
SECTION_B_ALSO_ANNEX_III_NOTE = (
    f"{ARTICLE_2_PARAGRAPH_2}: the product's legislation is listed in Annex I Section B, so the system is "
    "also high-risk under Article 6(1), and for that classification Article 2(2) applies only Article "
    "6(1), Article 60a and Articles 102 to 112; Article 2(2) limits only what the Article 6(1) "
    "classification brings, and the system is high-risk under Article 6(2) and Annex III as well, so that "
    "route decides the requirements served, the fundamental rights impact assessment and the Article 50 "
    "duties"
)


def _unresolved_article_6_1_facts(flags: dict[str, Any]) -> list[str]:
    """The absent fact that leaves the Article 6(1) route open (B123).

    Empty when the route is proven or ruled out. The third-party
    assessment is returned only once the product is known to be covered
    by Annex I: before that it decides nothing (ruling R1, the way
    law_enforcement_purpose is asked for only when the biometric flag is
    true).

    @implements: DEC-18
    """
    annex_i, third_party = ARTICLE_6_1_FLAGS
    if flags.get(annex_i) is False or flags.get(third_party) is False:
        return []
    if annex_i not in flags:
        return [annex_i]
    if flags.get(annex_i) is True and third_party not in flags:
        return [third_party]
    return []


# B185, the evidence task (DEC-18, the sentence "a medical or safety component
# with the Annex I fact unknown holds the answer at uncertain only while the
# route is open"): the safety component is named where it could change the
# level and only there, on the limited_risk exit while the Annex I fact is
# unknown and the third-party assessment is not known false, where answered
# true it gives undetermined. The third-party assessment keeps ruling R1: it
# is named once the product is known to be covered by Annex I.
MEDICAL_OR_SAFETY_UNKNOWN_FACT = (
    "flags.medical_or_safety_component is unknown while flags.annex_i_covered_product is unknown (Article 6(1) "
    "high-risk relevant, Annex I); a safety component whose Annex I coverage is unknown holds the classification "
    "at undetermined, so absence is not treated as false"
)

# Article 6(3) second-subparagraph conditions: flag -> the real Point node, in
# point order a, b, c, d, one fact per point (B184, D-G91 (7), ruling R5: the
# combined fact of points (a) and (d) is split, and no condition depends on
# the system's autonomy).
ARTICLE_6_3_CONDITIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "narrow_procedural_task",
        ("eu-ai-act:article-6:paragraph-3:point-a",),
        "narrow procedural task (point a)",
    ),
    (
        "improves_previous_human_activity",
        ("eu-ai-act:article-6:paragraph-3:point-b",),
        "improves the result of a previously completed human activity (point b)",
    ),
    (
        "detects_patterns_without_replacing_human_assessment",
        ("eu-ai-act:article-6:paragraph-3:point-c",),
        "detects decision-making patterns without replacing human assessment (point c)",
    ),
    (
        "preparatory_task",
        ("eu-ai-act:article-6:paragraph-3:point-d",),
        "preparatory task to an assessment relevant for the purposes of the use cases "
        "listed in Annex III (point d)",
    ),
)

# B185 (spec G D-G92 (6), (iv), DEC-33, rulings P9 and P29): the fixed lines
# of the candidate field. The first two join the missing facts when the
# candidate is unknown ({label} from ARTICLE_6_3_CONDITIONS); the Article 6(4)
# line joins legal_status_notes with every candidate (Article 49(2) named, not
# cited); the last two replace the "rule article_6_3:" lines and the
# "flagged for human review" note on the Article 6(1) exit (a system whose
# level and status the Article 6(1) route gives, with a listed use that is
# true or a point that rests on the area, a Section B product among them).
ARTICLE_6_3_UNKNOWN_CONDITION_LINE = (
    "flags.{flag} is unknown (Article 6(3) {label}); no condition is true, so the derogation candidacy "
    "is unknown, not no"
)
ARTICLE_6_3_UNKNOWN_PROFILING_LINE = (
    "flags.profiling_of_natural_persons is unknown while the Article 6(3) derogation candidacy is unknown; "
    "profiling cancels the derogation (Article 6(3) third subparagraph)"
)
ARTICLE_6_4_LINE = (
    "eu-ai-act:article-6:paragraph-4: a provider who considers that the system is not high-risk documents the "
    "assessment before placing it on the market or putting it into service, registers under Article 49(2), "
    "and provides the documentation of the assessment to the national competent authorities on request"
)
ARTICLE_6_3_BOTH_ROUTES_LINE = (
    "Article 6(3) condition for the Annex III part: '{label}' met by {flag}; the level stays high_risk under "
    "Article 6(1), which the derogation does not reach"
)
ARTICLE_6_3_BOTH_ROUTES_NOTE = (
    "eu-ai-act:article-6:paragraph-3: an Article 6(3) condition is true for the Annex III part of the answer; "
    "the level stays high_risk under Article 6(1), which the derogation does not reach"
)

# Article 50 transparency rules: flag -> the real Paragraph node.
ARTICLE_50_RULES: tuple[tuple[str, str, str], ...] = (
    # 50(1): "Providers shall ensure that AI systems intended to interact
    # directly with natural persons are designed and developed ..."
    (
        "interacts_with_natural_persons",
        "eu-ai-act:article-50:paragraph-1",
        "interaction with natural persons must be disclosed",
    ),
    # 50(2): "Providers of AI systems ... generating synthetic audio, image,
    # video or text content ..."
    (
        "generates_synthetic_content",
        "eu-ai-act:article-50:paragraph-2",
        "synthetic content must be marked as artificially generated or manipulated",
    ),
    # 50(3): "Deployers of an emotion recognition system or a biometric
    # categorisation system shall inform the natural persons ..."
    (
        "emotion_recognition",
        "eu-ai-act:article-50:paragraph-3",
        "exposed persons must be informed of emotion recognition",
    ),
    # DEC-18: the 50(3) trigger for "a biometric categorisation system"
    # (Article 3(40), with its ancillary-service exclusion).
    (
        "biometric_categorisation_system",
        "eu-ai-act:article-50:paragraph-3",
        "exposed persons must be informed of biometric categorisation",
    ),
    # B185 (spec G D-G92 (7), DEC-33, ruling P10): one fact per duty of
    # 50(4). The first subparagraph: "Deployers of an AI system that
    # generates or manipulates image, audio or video content constituting a
    # deep fake, shall disclose ..." (Article 3(60) defines a deep fake).
    (
        "generates_deep_fake",
        "eu-ai-act:article-50:paragraph-4",
        "a deep fake must be disclosed as artificially generated or manipulated",
    ),
    # The second subparagraph, its own node: "Deployers of an AI system that
    # generates or manipulates text which is published with the purpose of
    # informing the public on matters of public interest shall disclose ...".
    # No entailment row reads either fact: a deep fake does not make
    # generates_synthetic_content follow (D-G92 (x)).
    (
        "generates_public_interest_text",
        "eu-ai-act:article-50:paragraph-4:subparagraph-2",
        "text published to inform the public on matters of public interest must be disclosed as "
        "artificially generated or manipulated",
    ),
)

# DEC-18: each Article 50 trigger fact once, in rule order. An absent one is
# named in missing_facts, information only (Jose, 2026-10-01: "Keep minimal,
# name the fact"); B185 (spec G D-G92 (7)): on every exit on which Article 50
# can apply, that is every exit but the rejected input, the unacceptable_risk
# exit and a Section B product served under Article 2(2).
ARTICLE_50_TRIGGER_FLAGS: tuple[str, ...] = tuple(
    dict.fromkeys(flag for flag, _node_id, _note in ARTICLE_50_RULES)
)

# DEC-18: a listed paragraph or subparagraph is triggered by a fact that is
# true, never proven. B185 (spec G D-G92 (7), (8), (x)): the two facts of 50(4) answer
# no where its exceptions apply, so paragraph 4 is decided by its facts;
# paragraph 5 stays outside the rules; for a deep fake in an evidently
# artistic, creative, satirical, fictional or analogous work the duty stays
# and only its manner changes, which the note states.
ARTICLE_50_TRIGGERED_NOTE = (
    "eu-ai-act:article-50: the paragraphs or subparagraphs in transparency_duties are "
    "triggered by a fact that is true, not proven to apply: their own exceptions "
    "(an interaction obvious to the person, assistive editing, uses "
    "authorised by law to detect, prevent, investigate or prosecute criminal "
    "offences in 50(1) and 50(2), uses permitted by law to detect, prevent or "
    "investigate criminal offences in 50(3)) and paragraph 5 are not decided by "
    "the rules; the two facts of 50(4) are false where its exceptions apply, and "
    "for a deep fake that forms part of an evidently artistic, creative, "
    "satirical, fictional or analogous work or programme the 50(4) duty stays "
    "and only its manner changes"
)


@lru_cache(maxsize=1)
def _features_validator() -> Draft202012Validator:
    # One read of the schema file (_features_schema), shared with the area
    # headings and values.
    return Draft202012Validator(_features_schema())


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _node_index(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}


class _Citations:
    """Collects cited node ids and spans, resolved against the dump."""

    def __init__(self, node_index: dict[str, dict[str, Any]]):
        self._index = node_index
        self.node_ids: list[str] = []
        self.spans: list[dict[str, Any]] = []
        self.unresolved: list[str] = []

    def cite(self, node_id: str) -> None:
        if node_id in self.node_ids:
            return
        node = self._index.get(node_id)
        if node is None:
            # Never cite a node that does not exist in the dump; surface it.
            self.unresolved.append(
                f"cited node '{node_id}' is not present in the graph dump; "
                "citation withheld"
            )
            return
        self.node_ids.append(node_id)
        span = node.get("source_span")
        if isinstance(span, dict):
            self.spans.append(span)


def _unknown_annex_iii_facts(flags: dict[str, Any]) -> dict[str, str]:
    """Every Annex III fact absent from flags, mapped to its point node.

    In point order, from ANNEX_III_RULES (uses, then also_matching). A flag
    that is also an Article 5 one (real_time_remote_biometric_public) counts
    here too: its Annex III side is open whatever the Article 5 side says.
    Input to the FRIA rule, which reads an unknown Annex III fact where the
    answer would otherwise be does_not_apply for want of an Annex III area
    (B125, DEC-14).

    @implements: DEC-32
    """
    unknown: dict[str, str] = {}
    for rule in ANNEX_III_RULES:
        for fact, _unit in (*rule["uses"], *rule["also_matching"]):
            if fact not in flags:
                unknown.setdefault(fact, rule["node"])
    return unknown


def article_6_3_candidate(flags: dict[str, Any]) -> bool | None:
    """The Article 6(3) derogation candidacy of the facts (spec G D-G92 (6)).

    True when a second-subparagraph condition (points (a) to (d)) is true and
    profiling is not true; false when profiling is true (the third
    subparagraph keeps a profiling system high-risk) or every condition is
    false; None, shown as unknown, otherwise. Each condition is the one fact
    of its point (B184, D-G91 (7)). The value describes the Annex III
    part of an answer only: _annex_iii_candidacy reads it on the exits that
    have an Annex III point (ruling P9), and every other answer carries false.

    @implements: DEC-32
    @implements: DEC-33
    """
    conditions = [flags.get(flag) for flag, _points, _label in ARTICLE_6_3_CONDITIONS]
    profiling = flags.get("profiling_of_natural_persons")
    if profiling is True:
        return False
    if any(value is True for value in conditions):
        return True
    if all(value is False for value in conditions):
        return False
    return None


def _annex_iii_candidacy(
    flags: dict[str, Any],
    citations: _Citations,
    rationale: list[str],
    legal_status_notes: list[str],
    missing_facts: list[str],
    *,
    both_routes: bool,
) -> bool | None:
    """The candidate field of an answer that has an Annex III point, with its
    lines and citations (spec G D-G92 (6), (iv), rulings P9, P28, P29).

    Used by the three exits that have an Annex III point: the Annex III exit
    and the area-alone exit (both_routes False), and the Article 6(1) exit
    with a listed use that is true or a point that rests on the area
    (both_routes True). A matched condition with profiling true is cancelled
    by the third subparagraph, cited and said in the rationale. A true
    candidate cites Article 6(3), its points and Article 6(4), with
    ARTICLE_6_4_LINE; with both_routes False each condition gives its "rule
    article_6_3:" line and the note says the candidacy is flagged for human
    review, with both_routes True each gives ARTICLE_6_3_BOTH_ROUTES_LINE and
    the note is ARTICLE_6_3_BOTH_ROUTES_NOTE (the level and status stay the
    Article 6(1) route's). An unknown profiling fact beside a true condition is
    named as before. An unknown candidate names each unknown condition and
    an unknown profiling fact among the missing facts and cites nothing. The
    status is the caller's. The derogation needs human legal judgment; it is
    flagged, never applied.

    @implements: DEC-32
    @implements: DEC-33
    """
    matched_conditions = [
        (flag, point_nodes, label)
        for flag, point_nodes, label in ARTICLE_6_3_CONDITIONS
        if flags.get(flag) is True
    ]
    if matched_conditions and flags.get("profiling_of_natural_persons") is True:
        # Article 6(3) third subparagraph: profiling systems are always
        # high-risk, so candidacy is cancelled, not merely flagged.
        citations.cite(ARTICLE_6_3_PROFILING_OVERRIDE)
        rationale.append(
            "rule article_6_3_profiling: a derogation condition matched but "
            "profiling_of_natural_persons is true; Article 6(3) third "
            "subparagraph keeps profiling systems high-risk, so no "
            "derogation candidacy"
        )
        matched_conditions = []
    candidate = article_6_3_candidate(flags)
    # B185 (Task 4's review): the lines follow the returned value, never a
    # second reading of the facts: a condition that is true and not cancelled
    # by profiling is exactly a true candidate (tests/unit/test_review_causes.py
    # holds this over the table of area cases and a generated set).
    if candidate is True:
        citations.cite(ARTICLE_6_PARAGRAPH_3)
        for flag, point_nodes, label in matched_conditions:
            for node_id in point_nodes:
                citations.cite(node_id)
            if both_routes:
                rationale.append(ARTICLE_6_3_BOTH_ROUTES_LINE.format(label=label, flag=flag))
            else:
                # Wording note: this line must not read "rule X: flag Y
                # matches Z", which is the classification-trigger grammar
                # parsed by scripts/elicitation_error_report.py; derogation
                # candidacy is not a classification trigger.
                rationale.append(
                    f"rule article_6_3: derogation condition '{label}' met "
                    f"by {flag}; the Article 6(3) derogation may apply but "
                    "requires human legal judgment, no automatic downgrade"
                )
        if both_routes:
            legal_status_notes.append(ARTICLE_6_3_BOTH_ROUTES_NOTE)
        else:
            legal_status_notes.append(
                f"{ARTICLE_6_PARAGRAPH_3}: Article 6(3) derogation candidacy is "
                "flagged for human review; the classification stays high_risk "
                "until a human legal reviewer decides"
            )
        citations.cite(ARTICLE_6_PARAGRAPH_4)
        legal_status_notes.append(ARTICLE_6_4_LINE)
        if "profiling_of_natural_persons" not in flags:
            missing_facts.append(
                "flags.profiling_of_natural_persons is unknown while an "
                "Article 6(3) derogation condition matched; profiling "
                "cancels the derogation (Article 6(3) third subparagraph)"
            )
    elif candidate is None:
        for flag, _point_nodes, label in ARTICLE_6_3_CONDITIONS:
            if flags.get(flag) is None:
                missing_facts.append(ARTICLE_6_3_UNKNOWN_CONDITION_LINE.format(flag=flag, label=label))
        if flags.get("profiling_of_natural_persons") is None:
            missing_facts.append(ARTICLE_6_3_UNKNOWN_PROFILING_LINE)
    return candidate


def _classify_core(features: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    """Deterministic EU AI Act risk classification of a described AI system.

    Consumes structured system features (system_features.schema.json) and the
    offline Layer 0+1 dump. Returns the mandatory response envelope with
    answer fields: risk_category, unacceptable_risk, annex_iii_category,
    article_6_3_exception_candidate, transparency_duties (DEC-18: the Article
    50 paragraphs triggered by a fact that is true, as answered or as it
    follows from a definition of the Act, since classify_ai_system corrects
    the facts before this function reads them), rationale. Schema-invalid input returns
    status rejected_as_unsupported (never an exception) with the validation
    errors in missing_facts: the input was refused, not assessed, so it must
    not borrow not_applicable, which is a substantive in-scope verdict ("this
    system is out of the high-risk or Article 5 regime") that a consumer
    reading only status could mistake a rejected input for. A well-formed
    system that is simply out of scope still returns not_applicable. No model
    is involved anywhere in this function.
    """
    graph_version = _graph_version(dump)

    errors = sorted(_features_validator().iter_errors(features), key=lambda e: list(e.path))
    if errors:
        return make_envelope(
            answer={
                "risk_category": None,
                # DEC-18: no rule ran, so nothing about Article 5 is known.
                "unacceptable_risk": None,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "transparency_duties": [],
                "rationale": ["input rejected: features do not conform to system_features.schema.json"],
            },
            status="rejected_as_unsupported",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"schema validation: {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                for e in errors
            ],
        )

    flags = features.get("flags") or {}
    # B185 (DEC-33): the domain as given; the schema check above refused any
    # value outside the list, so no trimming and no change of case.
    domain = features.get("domain")
    # B185 (ruling P4): Annex III is read once; every check below reads this.
    reading = read_annex_iii(flags, domain)

    node_index = _node_index(dump)
    citations = _Citations(node_index)
    rationale: list[str] = []
    legal_status_notes: list[str] = []
    missing_facts: list[str] = []

    # Unresolved Article 5 paths (DEC-18): an absent fact is named only when
    # its path is not already ruled out by another known fact. Absence is
    # never treated as false.
    unknown_prohibition_flags = _unresolved_article_5_facts(flags)
    for flag in unknown_prohibition_flags:
        missing_facts.append(
            f"flags.{flag} is unknown (prohibition-relevant, Article 5); "
            "absence is not treated as false"
        )

    # Unknown Annex III high-risk flags: same discipline (audit 2026-07-20 D1).
    # An absent Annex III fact could be the one that makes the system
    # high-risk, so it must not be silently read as false and cleared as
    # minimal. Surfaced here; the minimal and transparency exits consult it.
    # B185 Task 7 follow-up (spec G D-G92 (2), (8)): a fact that is also an
    # Article 5 fact (real_time_remote_biometric_public) is named under both
    # tags while its Article 5 path is open, since it also gives Annex III
    # point 1; until then it was named once, as prohibition-relevant, and the
    # cause "an unknown listed use" was never named for it.
    unknown_annex_flags = [f for f in ANNEX_III_RELEVANT_FLAGS if f not in flags]
    for flag in unknown_annex_flags:
        missing_facts.append(
            f"flags.{flag} is unknown {ANNEX_III_UNKNOWN_TAG}; absence is not treated as false"
        )

    # B123 (D-G59): an open Article 6(1) route names its unknown fact on
    # every exit, the unacceptable_risk exit included, like the Annex III facts.
    unknown_article_6_1_facts = _unresolved_article_6_1_facts(flags)
    for flag in unknown_article_6_1_facts:
        if flag == "annex_i_covered_product":
            missing_facts.append(
                "flags.annex_i_covered_product is unknown (Article 6(1) "
                "high-risk relevant, Annex I); absence is not treated as false"
            )
        else:
            missing_facts.append(
                "flags.third_party_conformity_assessment_required is unknown while "
                "flags.annex_i_covered_product is true; Article 6(1) point (b) "
                "requires a third-party conformity assessment for the route to fire"
            )

    # Rule 1: Article 5 prohibitions. A prohibition flag names a candidate
    # practice; where the statute qualifies the point (D2), the ban only
    # fires once the exculpating fact settles against the exception. Pending
    # exception facts go to prohibition_review, which (like an unknown
    # prohibition flag) blocks a confident not-unacceptable verdict downstream.
    prohibition_hits: list[tuple[str, str, str]] = []
    prohibition_review: list[str] = []

    def _resolve_prohibition(
        flag: str,
        node_id: str,
        fragment: str,
        exculpating: tuple[str, bool, str] | None,
    ) -> None:
        if exculpating is None:
            prohibition_hits.append((flag, node_id, fragment))
            return
        fact_name, exculpating_value, desc = exculpating
        value = flags.get(fact_name)
        if value is exculpating_value:
            # The statutory exception is met / the harm element is absent.
            rationale.append(
                f"Article 5 exception: {flag} is true but {fact_name} is "
                f"{value}, so {desc} means the practice is not prohibited "
                "under that point; continuing the ladder"
            )
            return
        if fact_name not in flags:
            prohibition_review.append(fact_name)
            missing_facts.append(
                f"flags.{fact_name} is unknown; {desc} decides whether "
                f"{flag} is prohibited (Article 5); absence does not settle "
                "the ban, so the classification stays for human review"
            )
            return
        prohibition_hits.append((flag, node_id, fragment))

    for flag, (node_id, fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        if flags.get(flag) is True:
            _resolve_prohibition(
                flag, node_id, fragment, ARTICLE_5_EXCULPATING_FACT.get(flag)
            )
    # B184 (DEC-32, amending DEC-18 for point (h)): point (h) reads the
    # purpose of law enforcement (Article 3(46)) and no Annex III fact.
    if flags.get("real_time_remote_biometric_public") is True:
        if flags.get("law_enforcement_purpose") is True:
            _resolve_prohibition(
                "real_time_remote_biometric_public + law_enforcement_purpose",
                ARTICLE_5_POINT_H,
                ARTICLE_5_POINT_H_FRAGMENT,
                ARTICLE_5_POINT_H_EXCULPATING,
            )
        elif (
            LAW_ENFORCEMENT_PURPOSE_FACT not in flags
            and flags.get(ARTICLE_5_POINT_H_EXCULPATING[0]) is not ARTICLE_5_POINT_H_EXCULPATING[1]
        ):
            # The unknown purpose could change the outcome to unacceptable_risk.
            unknown_prohibition_flags.append(LAW_ENFORCEMENT_PURPOSE_FACT)
            missing_facts.append(
                f"flags.{LAW_ENFORCEMENT_PURPOSE_FACT} is unknown while "
                "flags.real_time_remote_biometric_public is true; Article 5(1) "
                "point (h) applies only to use for the purposes of law enforcement "
                "(Article 3(46))"
            )

    if prohibition_hits:
        # B184 (rulings R2, R12): the point (h) sentence when point (h) is the
        # only prohibition that fired; otherwise the general end on every line.
        point_h_alone = len(prohibition_hits) == 1 and prohibition_hits[0][1] == ARTICLE_5_POINT_H
        note_end = POINT_H_PRACTICE_NOTE_END if point_h_alone else PROHIBITED_PRACTICE_NOTE_END
        for flag, node_id, fragment in prohibition_hits:
            citations.cite(node_id)
            rationale.append(f"rule unacceptable_risk: flag {flag} matches {node_id} ({fragment})")
            for scoping in ARTICLE_5_SCOPING_PARAGRAPHS.get(flag, ()):
                citations.cite(scoping)
            if flag in ARTICLE_5_SCOPING_PARAGRAPHS:
                enacted_by = (node_index.get(node_id) or {}).get("enacted_by") or "Regulation (EU) 2026/1744"
                legal_status_notes.append(
                    f"{node_id}: inserted by {enacted_by}; "
                    + " and ".join(ARTICLE_5_SCOPING_PARAGRAPHS[flag])
                    + " say when the point prohibits; the date it applies from is in application_dates"
                )
            legal_status_notes.append(
                f"{node_id}: this practice is a prohibited AI practice under "
                f"Article 5(1) ({fragment}); {note_end}"
            )
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "unacceptable_risk",
                "unacceptable_risk": True,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                # DEC-18: no Article 50 duty is listed on this exit: a
                # prohibited answer gets only the Article 5 citation and a
                # message (USER.md domain guardrail). When point (h) alone
                # fired, the prohibited thing is the use for the purposes of
                # law enforcement in publicly accessible spaces, not the
                # placing on the market (DEC-32).
                "transparency_duties": [],
                "rationale": rationale,
            },
            status="potentially_applicable",
            graph_version=graph_version,
            confidence=1.0,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # B185, the evidence task (DEC-18): past the Article 5 rule, the other
    # fact of each open point is named, unless a line already names it.
    for fact, line in _article_5_other_fact_lines(flags):
        if not any(m.startswith(f"flags.{fact} is unknown") for m in missing_facts):
            missing_facts.append(line)

    # Pending Article 5 exception facts keep the ban unsettled: fold them into
    # the unknown-prohibition set so every downstream exit lowers to
    # requires_human_review and a bare no-match yields undetermined rather than a
    # confident not-unacceptable verdict (audit D2).
    unknown_prohibition_flags.extend(prohibition_review)

    # DEC-18: past the Article 5 rule nothing is proven, so the field is
    # unknown while any path is unresolved and false only when every path is
    # ruled out. The status lowering below reads the same list.
    unacceptable_risk_state: bool | None = None if unknown_prohibition_flags else False

    # DEC-18: the Article 50 duties are read once, before the exits, so a
    # high-risk answer keeps them: under Article 50(6) the transparency
    # obligations "shall not affect the requirements and obligations set out
    # in Chapter III". The list holds the paragraphs whose trigger fact is
    # true; empty means none is triggered by a fact that is true, never ruled out.
    article_50_hits = [
        (flag, node_id, note)
        for flag, node_id, note in ARTICLE_50_RULES
        if flags.get(flag) is True
    ]
    transparency_duties = list(dict.fromkeys(node_id for _f, node_id, _n in article_50_hits))

    def _carry_transparency_duties() -> None:
        # On an exit other than the Article 50 rule. Deliberately not the
        # "rule X: flag Y matches Z" grammar, which
        # scripts/elicitation_error_report.py parses as the classification
        # trigger: here Article 50 does not decide the category.
        for flag, node_id, note in article_50_hits:
            citations.cite(node_id)
            rationale.append(
                f"Article 50 duty triggered: flag {flag} is true for {node_id} "
                f"({note}); listed in transparency_duties beside the "
                "classification (Article 50(6))"
            )
        if transparency_duties:
            legal_status_notes.append(ARTICLE_50_TRIGGERED_NOTE)

    def _name_absent_article_50_facts() -> None:
        # Information only: the status and the category do not change. Called
        # on every exit on which Article 50 can apply (B185, spec G D-G92 (7)):
        # never on the rejected input, the unacceptable_risk exit or the
        # Section B branch that Article 2(2) limits.
        for flag, node_id, _note in ARTICLE_50_RULES:
            if flag not in flags:
                if node_id in transparency_duties:
                    # The paragraph is listed through another trigger, so no
                    # duty can be missing from the list because of this fact.
                    consequence = f"{node_id} is already listed through another trigger"
                else:
                    consequence = "that duty may be missing from transparency_duties"
                missing_facts.append(
                    f"flags.{flag} is unknown (Article 50 transparency trigger, "
                    f"{node_id}); absence is not treated as false, so {consequence}"
                )

    # Rule 2a: Article 6(1) embedded-product route. High-risk when the
    # system is a safety component of (or is itself) a product covered by
    # Annex I Union harmonisation legislation AND that product requires a
    # third-party conformity assessment. Both facts must be explicitly true;
    # this route is independent of Annex III and the Article 6(3) derogation
    # does not apply to it (6(3) derogates from paragraph 2 only).
    annex_i_covered = flags.get("annex_i_covered_product")
    third_party_required = flags.get("third_party_conformity_assessment_required")
    article_6_1_unresolved = False
    # R26: set when a Section B product also matches an Annex III category;
    # the Annex III rule below then decides and says so.
    section_b_also_article_6_1 = False
    if annex_i_covered is True and third_party_required is True:
        # B132 (D-G68 (6), R6, R14, R26, R36): the Annex I section decides
        # what the Article 6(1) classification brings, never the level.
        section_b = flags.get(ANNEX_I_SECTION_FACT)
        annex_i_section = "B" if section_b is True else "A" if section_b is False else "unknown"
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        citations.cite(ANNEX_I)
        rationale.append(
            "rule article_6_1: annex_i_covered_product and "
            "third_party_conformity_assessment_required are both true; the "
            "system is high-risk under Article 6(1) via Annex I"
        )
        # B185 (spec G D-G92 (vi)): the move to Annex III reads listed uses
        # that are true, never the domain.
        if annex_i_section == "B" and reading.confirmed:
            citations.cite(ARTICLE_2_PARAGRAPH_2)
            rationale.append(
                f"Annex I section: {ANNEX_I_SECTION_FACT} is true and an Annex III "
                "category also matches; Article 2(2) limits only what the Article "
                "6(1) classification brings, so the Annex III rule below decides"
            )
            legal_status_notes.append(SECTION_B_ALSO_ANNEX_III_NOTE)
            section_b_also_article_6_1 = True
        else:
            legal_status_notes.append(
                f"{ARTICLE_6_PARAGRAPH_3}: the Article 6(3) derogation applies "
                "only to Annex III systems under Article 6(2), not to the "
                "Article 6(1) embedded-product route"
            )
            if annex_i_section == "B":
                citations.cite(ARTICLE_2_PARAGRAPH_2)
                rationale.append(
                    f"Annex I section: {ANNEX_I_SECTION_FACT} is true, so the product's "
                    "legislation is listed in Section B and Article 2(2) applies only "
                    "the provisions it names, not the Chapter III requirements and not Article 50"
                )
                legal_status_notes.append(SECTION_B_NOTE)
                # R36: Article 2(2) applies no Article 50 duty to this system.
                if transparency_duties:
                    rationale.append(
                        "Article 50 duties not listed: " + ", ".join(transparency_duties)
                        + " would be triggered by a fact that is true, but Article 2(2) applies none of Article 50"
                    )
                legal_status_notes.append(ARTICLE_50_SECTION_B_NOTE)
                duties: list[str] = []
            else:
                # R44: with an Annex III match Chapter III is served whatever
                # the section, so the section fact matters on the Article 6(1)
                # route alone.
                # B185 (D-G92 (vi)): read from listed uses that are true.
                if annex_i_section == "unknown" and not reading.confirmed:
                    missing_facts.append(ANNEX_I_SECTION_UNKNOWN_FACT)
                _carry_transparency_duties()
                _name_absent_article_50_facts()
                duties = transparency_duties
            if reading.area_point is not None:
                # B185 (spec G D-G92 (5), (vii)): the area names a point that
                # no listed use confirms; the answer rests on Article 6(1)
                # alone and is cited and dated as on that route.
                legal_status_notes.append(annex_iii_area_line(ANNEX_III_SCOPE_UNCONFIRMED_LINE, reading, domain))
            elif reading.area_ruled_out:
                # B185 (spec G D-G92 (3)): every listed use of the domain's area
                # is known false, so the area stops counting, and the answer
                # says so in the same line as the Annex III branch below.
                rationale.append(annex_iii_area_line(ANNEX_III_AREA_RULED_OUT_LINE, reading, domain))
            # B185 (spec G D-G92 (iv), rulings P9 and P29): with an Annex III
            # point (a listed use that is true, or a point that rests on the
            # area) the field follows (6) for the Annex III part, and the
            # status stays the one the Article 6(1) route gives: a true
            # candidate adds no mark on a Section A product (with the section
            # unknown ruling R5 makes it a cause of review, which the wrapper
            # reads through review_causes). A Section B product reaches this
            # branch only without a true listed use, so its point rests on the
            # area, whose unknown listed uses already mark it (R39), as
            # passage (k) requires.
            annex_iii_part_candidate: bool | None = False
            if reading.confirmed or reading.area_point is not None:
                annex_iii_part_candidate = _annex_iii_candidacy(
                    flags, citations, rationale, legal_status_notes, missing_facts, both_routes=True
                )
            if annex_i_section == "unknown" and reading.confirmed and annex_iii_part_candidate is True:
                # B185 Task 6 (ruling R5): with a true listed use the section
                # fact decides whether the derogation would change what is
                # served (Section B, passage (k)), so it is named, and the
                # candidate is a cause of review (review_causes.py).
                missing_facts.append(ANNEX_I_SECTION_UNKNOWN_FACT)
            missing_facts.extend(citations.unresolved)
            status = "potentially_applicable"
            confidence = 1.0
            if unknown_prohibition_flags:
                status = "requires_human_review"
                confidence = 0.5
                rationale.append(
                    "status lowered to requires_human_review: unknown "
                    "prohibition-relevant flags could change the outcome to Unacceptable risk"
                )
            if annex_i_section == "B" and unknown_annex_flags:
                # R39: an unknown Annex III fact could put this Section B
                # product on the Annex III route (R26), which brings what
                # Article 2(2) does not; never read as the answer that serves less.
                status = "requires_human_review"
                confidence = 0.5
                rationale.append(
                    "status lowered to requires_human_review: unknown Annex III facts could "
                    "put this Section B product on the Annex III route, which brings the "
                    "Chapter III requirements and the Article 50 duties Article 2(2) does not"
                )
            return make_envelope(
                answer={
                    "risk_category": "high_risk",
                    "unacceptable_risk": unacceptable_risk_state,
                    "annex_iii_category": None,
                    "annex_i_section": annex_i_section,
                    "article_6_3_exception_candidate": annex_iii_part_candidate,
                    "transparency_duties": duties,
                    "rationale": rationale,
                },
                status=status,
                graph_version=graph_version,
                confidence=confidence,
                source_nodes=citations.node_ids,
                source_spans=citations.spans,
                legal_status_notes=legal_status_notes,
                missing_facts=missing_facts,
            )
    if annex_i_covered is True and third_party_required is None:
        # Named at the top (B123); here it only holds the route open.
        article_6_1_unresolved = True
    if annex_i_covered is True and third_party_required is False:
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        rationale.append(
            "rule article_6_1: annex_i_covered_product is true but no "
            "third-party conformity assessment is required, so the Article "
            "6(1) route does not fire; continuing down the ladder"
        )

    # Rule 2b: Article 6(2) + Annex III high-risk categories, from the one
    # reading (B185, ruling P4): the first point with a true fact decides.
    annex_match = reading.first_rule
    if reading.area_ruled_out:
        # Evidence-driven fix (eval/results/ELICITATION_ERRORS.md, scenario
        # 161), kept by B185 (D-G92 (3)): with every listed use of the area
        # known false the area does not count, and the answer says so.
        rationale.append(annex_iii_area_line(ANNEX_III_AREA_RULED_OUT_LINE, reading, domain))
    if annex_match is not None:
        rationale.append(
            f"rule high_risk: flag {reading.trigger_fact} matches Annex III category "
            f"'{annex_match['label']}' ({annex_match['node']}), high-risk "
            "under Article 6(2)"
        )

    if annex_match is not None:
        citations.cite(annex_match["node"])
        citations.cite(ARTICLE_6_PARAGRAPH_2)

        # Rule 3: Article 6(3) derogation candidacy over the real second-
        # subparagraph conditions (B185, ruling P28: the logic lives in
        # _annex_iii_candidacy, shared with the area-alone and Article 6(1)
        # exits). Annex III decides what is served here, a Section B product
        # on both routes included (R26), so a true candidate marks the answer
        # for review (passage (k)); an unknown one does not (D-G92 (iv)).
        exception_candidate = _annex_iii_candidacy(
            flags, citations, rationale, legal_status_notes, missing_facts, both_routes=False
        )

        _carry_transparency_duties()
        _name_absent_article_50_facts()
        missing_facts.extend(citations.unresolved)
        status = "potentially_applicable"
        confidence = 1.0
        if exception_candidate is True:
            status = "requires_human_review"
            confidence = 0.5
        elif unknown_prohibition_flags:
            # An unknown prohibition flag could change high_risk to
            # unacceptable_risk, so the outcome is not settled.
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to Unacceptable risk"
            )
        return make_envelope(
            answer={
                "risk_category": "high_risk",
                "unacceptable_risk": unacceptable_risk_state,
                "annex_iii_category": annex_match["node"],
                # R26: a Section B product also high-risk under Article 6(1).
                **({"annex_i_section": "B"} if section_b_also_article_6_1 else {}),
                "article_6_3_exception_candidate": exception_candidate,
                "transparency_duties": transparency_duties,
                "rationale": rationale,
            },
            status=status,
            graph_version=graph_version,
            confidence=confidence,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # B185 (spec G D-G92 (3), (vii), ruling P5): no listed use of any point is
    # true, the domain names an area with a listed use still unknown, and the
    # Article 6(1) route is not proven (its exit returned above): high_risk on
    # the area alone, for human review. It stands before the undetermined
    # exit of an open Article 6(1) route, so an open route with an area gives
    # high_risk here. No listed use is cited; Article 6(2) and the point are.
    if reading.area_point is not None:
        citations.cite(reading.area_point)
        citations.cite(ARTICLE_6_PARAGRAPH_2)
        rationale.append(annex_iii_area_line(ANNEX_III_AREA_ALONE_RULE_LINE, reading, domain))
        legal_status_notes.append(annex_iii_area_line(ANNEX_III_AREA_ALONE_LINE, reading, domain))
        # B185 (spec G D-G92 (iv), ruling P9): the field describes the point
        # that rests on the area; the answer is already marked for review.
        area_candidate = _annex_iii_candidacy(
            flags, citations, rationale, legal_status_notes, missing_facts, both_routes=False
        )
        if unknown_prohibition_flags:
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to Unacceptable risk"
            )
        _carry_transparency_duties()
        _name_absent_article_50_facts()
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "high_risk",
                "unacceptable_risk": unacceptable_risk_state,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": area_candidate,
                "transparency_duties": transparency_duties,
                "rationale": rationale,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Safety valve, not an auto-classification: the Article 6(1) route was
    # not settled (its facts are unknown, or a safety component was declared
    # without the Annex I facts). Never silently call that minimal. A
    # third-party assessment known false rules the route out (B123, R4).
    if article_6_1_unresolved or (
        flags.get("medical_or_safety_component") is True and annex_i_covered is None
        and third_party_required is not False
    ):
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        rationale.append(
            "rule undetermined: the Article 6(1) plus Annex I embedded-product "
            "route cannot be settled from the provided facts and no Annex III "
            "category matched; human legal review is needed"
        )
        missing_facts.append(
            "whether the system is a safety component of a product covered by "
            "Annex I Union harmonisation legislation requiring third-party "
            "conformity assessment (Article 6(1)) cannot be decided "
            "deterministically from the provided facts"
        )
        # DEC-18 (Codex spec review finding 5): this exit returns before the
        # Article 50 rule, so a trigger that is true is listed here too, and
        # (B185, D-G92 (7)) an unknown one is named.
        _carry_transparency_duties()
        _name_absent_article_50_facts()
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "undetermined",
                "unacceptable_risk": unacceptable_risk_state,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "transparency_duties": transparency_duties,
                "rationale": rationale,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Rule 4: Article 50 transparency obligations (the hits read above).
    if article_50_hits:
        if annex_i_covered is None and third_party_required is not False and "medical_or_safety_component" not in flags:
            # B185, the evidence task: answered true, the safety component
            # gives the undetermined exit above.
            missing_facts.append(MEDICAL_OR_SAFETY_UNKNOWN_FACT)
        for flag, node_id, note in article_50_hits:
            citations.cite(node_id)
            rationale.append(f"rule limited_risk: flag {flag} matches {node_id} ({note})")
        legal_status_notes.append(ARTICLE_50_TRIGGERED_NOTE)
        # B185 (spec G D-G92 (7)): an unknown trigger beside a true one is
        # named; information only, the status below does not read it.
        _name_absent_article_50_facts()
        missing_facts.extend(citations.unresolved)
        status = "potentially_applicable"
        confidence = 1.0
        if unknown_prohibition_flags:
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to Unacceptable risk"
            )
        else:
            # A transparency system could also be high-risk under Annex III
            # or Article 6(1); with those facts unknown, do not present
            # transparency-only as settled (audit 2026-07-20 D1; B123). When
            # no Article 5 fact is unknown, each high-risk kind that applies
            # (Annex III, Article 6(1)) adds its line and the status is
            # lowered once; an unknown Article 5 fact takes precedence with
            # its own line, as before.
            lowering: list[str] = []
            if unknown_annex_flags:
                lowering.append(
                    "status lowered to requires_human_review: unknown Annex III "
                    "high-risk flags could add high-risk obligations on top of the "
                    "Article 50 transparency duty"
                )
            if unknown_article_6_1_facts:
                lowering.append(
                    "status lowered to requires_human_review: unknown Article "
                    "6(1) facts could add high-risk obligations on top of the "
                    "Article 50 transparency duty"
                )
            if lowering:
                status = "requires_human_review"
                confidence = 0.5
                rationale.extend(lowering)
        return make_envelope(
            answer={
                "risk_category": "limited_risk",
                "unacceptable_risk": unacceptable_risk_state,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "transparency_duties": transparency_duties,
                "rationale": rationale,
            },
            status=status,
            graph_version=graph_version,
            confidence=confidence,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Rule 5: nothing fired. A confident minimal verdict requires that every
    # prohibition-relevant AND Annex III-relevant fact is known: an unknown
    # one could be the fact that makes the system high-risk or unacceptable risk, so
    # absence must never be read as a clean "not regulated" (audit D1). The
    # Article 6(1) route must likewise be ruled out, not merely unmentioned (B123).
    if unknown_prohibition_flags or unknown_article_6_1_facts or unknown_annex_flags:
        which = []
        if unknown_prohibition_flags:
            which.append("prohibition-relevant (Article 5)")
        if unknown_article_6_1_facts:
            which.append("Article 6(1) (Annex I)")
        if unknown_annex_flags:
            which.append("Annex III high-risk (Article 6(2))")
        rationale.append(
            "rule undetermined: no rule fired but "
            + " and ".join(which)
            + " flags are unknown, so the classification cannot be settled "
            "deterministically; the named facts must be provided before a "
            "minimal verdict is safe"
        )
        # B185 (spec G D-G92 (7)): Article 50 can apply here, so an unknown
        # trigger is named, as on the minimal exit.
        _name_absent_article_50_facts()
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "undetermined",
                "unacceptable_risk": unacceptable_risk_state,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                # Empty here by construction: a true trigger would have
                # returned at the Article 50 rule above.
                "transparency_duties": transparency_duties,
                "rationale": rationale,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    rationale.append(
        "rule minimal_risk: every Article 5 path ruled out, the Article 6(1) "
        "route ruled out, every Annex III high-risk flag known false, no "
        "Annex III category matched, no Article 50 transparency flag set"
    )
    # DEC-18 (Jose, 2026-10-01: "Keep minimal, name the fact"): an absent
    # Article 50 trigger is named, the answer stays minimal_risk.
    _name_absent_article_50_facts()
    missing_facts.extend(citations.unresolved)
    return make_envelope(
        answer={
            "risk_category": "minimal_risk",
            "unacceptable_risk": unacceptable_risk_state,
            "annex_iii_category": None,
            "article_6_3_exception_candidate": False,
            "transparency_duties": transparency_duties,
            "rationale": rationale,
        },
        status="not_applicable",
        graph_version=graph_version,
        confidence=1.0,
        legal_status_notes=legal_status_notes,
        missing_facts=missing_facts,
    )


def route_of(answer: dict[str, Any]) -> str | None:
    """Article 113(c)'s route for an answer's dates (R37): Annex III or Annex
    I when only that route holds, None (both points) when both hold or none
    does. An answer without high_risk_routes (a bare answer, or one stored
    before B132) is read from its deciding route's fields. B185 (spec G D-G92
    (vii)): a high_risk answer whose level rests on the area (no route, the
    point in annex_iii_area_unconfirmed) is dated as an Annex III system.

    @implements: DEC-33
    """
    routes = answer.get("high_risk_routes")
    if not isinstance(routes, list):
        routes = (
            [HIGH_RISK_ROUTE_ARTICLE_6_2] if answer.get("annex_iii_category")
            else [HIGH_RISK_ROUTE_ARTICLE_6_1] if answer.get("annex_i_section") is not None
            else []
        )
    if not routes and answer.get("risk_category") == "high_risk" and answer.get("annex_iii_area_unconfirmed"):
        return ROUTE_ANNEX_III
    if routes == [HIGH_RISK_ROUTE_ARTICLE_6_2]:
        return ROUTE_ANNEX_III
    if routes == [HIGH_RISK_ROUTE_ARTICLE_6_1]:
        return ROUTE_ANNEX_I
    return None


def _cite_listed_uses(
    envelope: dict[str, Any], flags: dict[str, Any], reading: AnnexIIIReading, dump: dict[str, Any]
) -> None:
    """Set annex_iii_listed_uses and cite each of its units (B184, ruling R14).

    The rejected input gets an empty list and no citation (no rule ran).
    Otherwise every legal unit of a listed use that is true is named in point
    order; on the unacceptable_risk exit nothing more is done (ruling R14:
    only the Article 5 provisions are cited there); on every other exit each
    unit is cited (its node into source_nodes, its span into source_spans,
    resolved against the dump as _Citations resolves them), with one rationale
    line each after the core's lines (rulings P7, P10), except for the unit of
    the fact the Article 6(2) exit's "rule high_risk" line already names
    (reading.trigger_fact, B185 ruling P4).

    @implements: DEC-32
    @implements: DEC-33
    """
    answer = envelope["answer"]
    if envelope.get("status") == "rejected_as_unsupported":
        answer["annex_iii_listed_uses"] = []
        return
    units = annex_iii_listed_uses(flags)
    answer["annex_iii_listed_uses"] = units
    if not units or answer.get("risk_category") == "unacceptable_risk":
        # Ruling R14 (USER.md domain guardrail: a prohibited system gets only
        # the Article 5 prohibition citation and a message): on the
        # unacceptable_risk exit the field names the listed uses, and nothing
        # is cited or added to the rationale for them.
        return
    named_fact = reading.trigger_fact if answer.get("annex_iii_category") else None
    true_facts = [fact for fact in ANNEX_III_LISTED_USE_FACTS if flags.get(fact) is True]
    answer.setdefault("rationale", []).extend(
        ANNEX_III_LISTED_USE_LINE.format(fact=fact, unit=ANNEX_III_UNIT_OF_FACT[fact])
        for fact in true_facts
        if fact != named_fact
    )
    _cite_more(envelope, [ANNEX_III_UNIT_OF_FACT[fact] for fact in true_facts], dump)


def _cite_more(envelope: dict[str, Any], node_ids: list[str], dump: dict[str, Any]) -> None:
    """Cite further nodes on a built envelope, resolved against the dump as
    _Citations resolves them, an unresolved one named among the missing facts.
    The one place the wrapper adds citations after the core (the listed uses,
    Article 6(2) on both routes).

    @implements: DEC-32
    @implements: DEC-33
    """
    citations = _Citations(_node_index(dump))
    citations.node_ids = list(envelope.get("source_nodes") or [])
    citations.spans = list(envelope.get("source_spans") or [])
    for node_id in node_ids:
        citations.cite(node_id)
    envelope["source_nodes"] = citations.node_ids
    envelope["source_spans"] = citations.spans
    if citations.unresolved:
        envelope["missing_facts"] = [*(envelope.get("missing_facts") or []), *citations.unresolved]


def _rejected_answer(
    envelope: dict[str, Any], features: Any, dump: dict[str, Any]
) -> dict[str, Any]:
    """The answer of a refused input: no rule ran, so nothing is read from the facts.

    B185 (DEC-33, the guard I10): the answer's fields are set here and the
    envelope is returned before any lookup by domain. After the schema's own
    errors come one line for each fact that left the schema (B184, final
    review, M2), naming the facts that replace it, then, when the given
    domain is not a value of the schema and is neither absent nor null, the
    refusal of P30 (domain_refusal), word for word. B185 Task 6 (spec G
    D-G92 (9), ruling P14): a refused input carries no Article 27(1) block,
    so answer["fria"] is null, the key kept.

    @implements: DEC-32
    @implements: DEC-33
    """
    answer = envelope["answer"]
    answer["fact_conflicts"] = []
    # B185 (Task 3): no rule ran, so no fact is read beside the domain.
    answer["area_conflicts"] = []
    # B185 (ruling P6): no rule ran, so no point rests on an area.
    answer["annex_iii_area_unconfirmed"] = None
    missing = list(envelope.get("missing_facts") or [])
    given = features.get("flags") if isinstance(features, dict) else None
    if isinstance(given, dict):
        missing.extend(
            REMOVED_FACT_LINE.format(removed=removed, replacements=replacements)
            for removed, replacements in REMOVED_FACT_REPLACEMENTS.items()
            if removed in given
        )
    if isinstance(features, dict) and features.get("domain") is not None:
        domain = features["domain"]
        if not domain_is_a_value(domain):
            missing.append(domain_refusal(domain))
    envelope["missing_facts"] = missing
    answer["fria"] = None
    answer["annex_i_section"] = None
    answer["high_risk_routes"] = []
    answer["annex_iii_listed_uses"] = []
    answer["application_dates"] = []
    answer["legal_text"] = legal_text(dump)
    return envelope


def classify_ai_system(features: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    """Deterministic classification plus the Article 27(1) FRIA block.

    Runs the rule ladder (_classify_core), then adds answer["fria"], the
    deterministic FRIA applicability block (fria.py, DEC-14): applies,
    does_not_apply, or unknown with the missing facts named. The FRIA rule
    reuses the same Annex III reading as the ladder, so when the ladder took
    the Article 6(1) embedded-product route the system's separate Article
    6(2) membership is still checked (both routes can hold at once, and
    Article 27(1) covers the 6(2) side). The fria block is self-contained:
    it never changes risk_category, envelope status, confidence, or the
    envelope's missing_facts. The block is unknown, not does_not_apply,
    while an Annex III fact absent from the input could still make the
    system high-risk under Article 6(2) and the assessment apply (B125):
    on a limited_risk or minimal_risk answer, and on a high_risk answer
    through the Article 6(1) route only or in the point 2 area only (there
    beside an unknown 5(b) or 5(c) fact, which keeps its own line). Each
    such fact is named in the block's missing_facts only. A fact that cannot change the outcome
    is not named: a point 2 fact never is (Article 27(1) excepts that
    area), and a fact of another area other than 5(b) and 5(c) is not
    once the deployer is known to be neither a body governed by public
    law nor a private entity providing public services.

    B184 (spec G D-G91 (6) and (10), DEC-32): the facts are corrected once,
    here, by FACT_ENTAILMENTS before any rule reads them, so the level, the
    Article 50 duties, the FRIA block, high_risk_routes and
    annex_iii_listed_uses read the same facts; the caller's input is never
    changed. answer["fact_conflicts"] is on every answer (empty on the
    rejected input, where no rule ran). A pair answered against its
    definition is named there and among the missing facts, and the status is
    lowered to requires_human_review with confidence 0.5 before the FRIA
    block is computed (ruling P11), the level unchanged; a wider fact read
    true from unknown adds a rationale line only (ruling R6).

    B185 (spec G D-G92 (1) and (viii), DEC-33): a refused input returns from
    _rejected_answer before any lookup by domain, and a domain outside the
    schema's list gets the schema's refusal among the missing facts; every
    other answer reads the domain as given. B185 (D-G92 (3), (5), (vii),
    ruling P6): answer["annex_iii_area_unconfirmed"] is the point that rests
    on the area on a high_risk answer, null on every other answer;
    high_risk_routes holds Article 6(2) only with a listed use that is true;
    a system on both routes cites Article 6(2) beside Article 6(1); and a
    level that rests on the area is dated as an Annex III system.

    B185 (spec G D-G92 (4), (iii), DEC-33, ruling P26):
    answer["area_conflicts"] is on every answer (empty on the rejected
    input): one entry per listed use that is true, on the corrected facts,
    while domain is none_of_these_areas. An entry marks the answer as an
    entry of fact_conflicts does, on every exit, unacceptable_risk included:
    its note joins the missing facts, the status is requires_human_review with
    confidence 0.5 before the Article 27 block is computed, the level is
    unchanged, and on unacceptable_risk each prohibited-practice note gains
    PROHIBITION_AREA_CONFLICT_CLAUSE.

    B185 (spec G D-G92 (6), (iv), passage (k), DEC-33, rulings P9, P28,
    P29): answer["article_6_3_exception_candidate"] is true, false or null
    for the Annex III part of an answer that has an Annex III point (a listed
    use that is true, or a point that rests on the area), whatever other
    route holds, and false on every other answer; the core sets it
    (_annex_iii_candidacy) and the Article 27 block reads that one value,
    holding at unknown for the candidacy only when it is true.

    B185 Task 6 (spec G D-G92 (8), (9), (v), DEC-33, rulings P11 to P14,
    P32, P33, R5): the causes of review are decided in one place
    (review_causes.py) from the answer's own fields. The core's lines that
    start "status lowered to requires_human_review:" are replaced by one line
    per cause that holds, in the spec's order, and the status is
    requires_human_review with confidence 0.5 exactly when a cause holds (an
    undetermined answer keeps its "rule undetermined:" line and prints no
    cause). The Article 27 block reads the confirmed points only, the point
    that rests on the area apart with its unknown listed uses, and names
    every cause, the area first. A refused input carries "fria": null.

    @implements: DEC-32
    @implements: DEC-33
    """
    conflicts: list[dict[str, str]] = []
    unknown_lines: list[str] = []
    if isinstance(features, dict) and isinstance(features.get("flags"), dict):
        corrected_flags, conflicts, unknown_lines = apply_entailments(features["flags"])
        features = {**features, "flags": corrected_flags}
    envelope = _classify_core(features, dump)
    answer = envelope.get("answer")
    if not isinstance(answer, dict) or "risk_category" not in answer:
        return envelope
    if envelope.get("status") == "rejected_as_unsupported":
        return _rejected_answer(envelope, features, dump)
    flags = features.get("flags") if isinstance(features, dict) else None
    if not isinstance(flags, dict):
        flags = {}
    deployer = features.get("deployer") if isinstance(features, dict) else None
    if not isinstance(deployer, dict):
        deployer = {}
    # B185 (DEC-33): a rejected input returned above, so the domain here is a
    # value of the schema or unknown, read as given.
    domain = features.get("domain") if isinstance(features, dict) else None
    answer["fact_conflicts"] = conflicts
    # B185 (spec G D-G92 (4), (iii), DEC-33): read on the corrected facts, so a
    # listed use that follows from a definition counts as one answered true.
    areas = area_conflicts(flags, domain)
    answer["area_conflicts"] = areas
    rationale = answer.setdefault("rationale", [])
    rationale.extend(unknown_lines)
    # B184 (ruling P11) and B185 (the rule added after the plan's review of
    # D-G92): each mark joins its notes to the missing facts on every exit,
    # unacceptable_risk included, the level unchanged; the status follows the
    # causes of review below, before the Article 27 block is computed.
    clauses: list[str] = []
    for entries, clause in (
        (conflicts, PROHIBITION_FACT_CONFLICT_CLAUSE),
        (areas, PROHIBITION_AREA_CONFLICT_CLAUSE),
    ):
        if not entries:
            continue
        envelope["missing_facts"] = [
            *(envelope.get("missing_facts") or []),
            *(entry["note"] for entry in entries),
        ]
        clauses.append(clause)
    if clauses and answer.get("risk_category") == "unacceptable_risk":
        # B184 (final review, M3) and B185 (ruling P26): each prohibited-
        # practice note says what the prohibition rests on, the fact conflict
        # first when both hold.
        envelope["legal_status_notes"] = [
            f"{note}. {' '.join(clauses)}" if PROHIBITED_PRACTICE_NOTE_MARK in note else note
            for note in envelope.get("legal_status_notes") or []
        ]
    # B185 (ruling P4): the same one reading of Annex III the core made.
    reading = read_annex_iii(flags, domain)
    # B185 (spec G D-G92 (3), (5), ruling P6): the point that rests on the
    # area, on a high_risk answer only; null on every other answer.
    answer["annex_iii_area_unconfirmed"] = (
        reading.area_point if answer.get("risk_category") == "high_risk" else None
    )
    # B132 (spec G D-G68 (6)): the Annex I section on every answer (null off
    # the Article 6(1) route) and the high-risk routes that hold (R37).
    answer.setdefault("annex_i_section", None)
    article_6_1_holds = (
        flags.get("annex_i_covered_product") is True
        and flags.get("third_party_conformity_assessment_required") is True
    )
    # B185 (spec G D-G92 (5)): a route holds on confirmed facts, never on the
    # area, so Article 6(2) is a route only with a listed use that is true.
    answer["high_risk_routes"] = [
        name for name, holds in (
            (HIGH_RISK_ROUTE_ARTICLE_6_1, article_6_1_holds),
            (HIGH_RISK_ROUTE_ARTICLE_6_2, bool(reading.confirmed)),
        )
        if holds
    ] if answer.get("risk_category") == "high_risk" else []
    # B185 Task 6 (spec G D-G92 (8), rulings P11, P12, P32, R5): the causes of
    # review decide the status and are named in order. The core's status
    # lines are replaced by one line per cause that holds; the status is
    # requires_human_review with confidence 0.5 whenever a cause holds, the
    # level unchanged. An undetermined answer keeps its "rule undetermined:"
    # line as its reason and prints no cause (P32).
    causes = review_causes(answer, envelope.get("missing_facts") or [])
    rationale[:] = [line for line in rationale if not line.startswith(STATUS_LINE_PREFIX)]
    if answer.get("risk_category") != "undetermined" and causes:
        envelope["status"] = "requires_human_review"
        envelope["confidence"] = 0.5
        rationale.extend(review_status_line(cause, answer) for cause in causes)
    # B185 Task 6 (spec G D-G92 (5), (v), passage (j), ruling P13): the
    # Article 27 block reads the confirmed points only; a point that rests on
    # the area comes apart, with its unknown listed uses, and is never
    # counted as a confirmed area. The full set of confirmed points scopes
    # the point-2 exception to the area, not the whole system (audit D5), and
    # recovers the 6(2) side of a system that took the 6(1) route.
    annex_points = list(reading.confirmed)
    annex_node = answer.get("annex_iii_category") or (annex_points[0] if annex_points else None)
    area = None
    if answer["annex_iii_area_unconfirmed"] is not None:
        area = {
            "domain": domain,
            "point": reading.area_point,
            "number": _features_schema()["properties"]["domain"]["x-annex-iii-area-values"][domain],
            "unknown_uses": list(reading.area_unknown_uses),
        }
    answer["fria"] = assess_fria_applicability(
        answer.get("risk_category"),
        annex_node,
        flags,
        deployer,
        # B185 (spec G D-G92 (iv)): the answer's own field, which every exit
        # with an Annex III point computes for the Annex III part (the
        # Article 6(1) exit of a dual-route system included, audit D7); the
        # block holds at unknown for a candidate only when it is true.
        article_6_3_exception_candidate=answer.get("article_6_3_exception_candidate") is True,
        annex_points=annex_points,
        # An unknown Annex III fact keeps the FRIA block open when it could
        # make Article 27(1) apply (B125); only the fria block reads it,
        # never the level or status.
        unknown_annex_iii_facts=_unknown_annex_iii_facts(flags),
        annex_iii_area=area,
        # The causes of review of the classification, the ones its status
        # lines name (ruling R6). The block reads a true candidate from the
        # field above (step 4, D-G92 (iv)); where the candidate is no cause
        # (passage (k)) the block's sentence never says the classification is
        # not settled on an answer that is settled.
        review_causes=causes,
    )
    # B132 (spec G D-G68 (6)): the application dates of every provision the
    # answer cites, from the reviewed table of Article 113 as amended, by the
    # routes (both points of Article 113(c) when both hold; data, never
    # control flow: nothing above reads them), and the text it follows.
    route = route_of(answer)
    _cite_listed_uses(envelope, flags, reading, dump)
    if answer["high_risk_routes"] == [HIGH_RISK_ROUTE_ARTICLE_6_1, HIGH_RISK_ROUTE_ARTICLE_6_2]:
        # B185 (spec G D-G92 (9)): a system on both routes cites Article 6(1)
        # and Article 6(2), before the dates are read from the citations.
        _cite_more(envelope, [ARTICLE_6_PARAGRAPH_2], dump)
    cited = list(envelope.get("source_nodes") or [])
    if answer.get("annex_i_section") == "B" and HIGH_RISK_ROUTE_ARTICLE_6_2 in answer["high_risk_routes"]:
        # R45: Article 2(2) excludes Article 6(2), Article 6(3) and the rest
        # of Chapter III on the product route, so for a Section B product on
        # the Annex III route every cited provision but the Article 6(1)
        # node and Annex I is dated by point (c)(i) only; those two keep
        # their dates as built (R43).
        product_route = (ARTICLE_6_PARAGRAPH_1, ANNEX_I)
        answer["application_dates"] = [
            entry
            for node_id in dict.fromkeys(cited)
            for entry in dates_for(
                [node_id], dump, route if node_id in product_route else ROUTE_ANNEX_III
            )
        ]
    else:
        answer["application_dates"] = dates_for(cited, dump, route)
    answer["legal_text"] = legal_text(dump)
    return envelope

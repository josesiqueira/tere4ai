"""The causes of review of a classification, in one place (B185, spec G D-G92 (8)).

Every fixed sentence that gives a reason for review, in the classification's
answer, in the Article 27(1) block and in the note of the applicable
requirements, names the causes that hold, all of them, in one order: an
unknown Article 5 fact; facts that contradict a definition of the Act; a
listed use that is true while the domain says none of these areas; the level
that rests on the area alone; an Article 6(3) candidate where Annex III
decides what is served; an open Article 6(1) route; an unknown listed use.
This module decides from an answer's own fields which causes hold (ruling
P12, with ruling R5 for an unknown Annex I section) and gives the sentences
the three places print (ruling P11). It reads no model and imports neither
classify nor fria, so both can import it.

Rules of each cause (P12, R5), read from the answer's fields; the last two
only when the envelope's missing facts are given:
- article_5_unknown: unacceptable_risk is null on a high_risk or limited_risk
  answer (DEC-18: an unknown Article 5 fact could change the level);
- fact_conflict: fact_conflicts is not empty (DEC-32), on any level;
- area_conflict: area_conflicts is not empty, on any level (D-G92 (iii) and
  the rule added after the plan's review);
- area_alone: annex_iii_area_unconfirmed is set and high_risk_routes is empty
  (D-G92 (3));
- article_6_3_candidate: the candidate field is true and Annex III decides
  what is served (passage (k)): Article 6(1) is not a route; or a listed use
  is true (Article 6(2) a route) and the Annex I section is B, or unknown
  (ruling R5: if it were B the derogation would change what is served). A
  product whose Annex III point only rests on the area is served as its
  section gives whatever the derogation, so a true candidate there is never
  a cause, for a known Section B as for an unknown section (the
  coordinator's ruling of fix round 1); such an answer stays under review
  when another cause holds (an unknown listed use of a Section B product).
  For the Article 27(1) block (for_fria) the field true is enough (D-G92
  (iv));
- article_6_1_open: a limited_risk answer whose missing facts name an
  Article 6(1) fact (B123);
- listed_use_unknown: a limited_risk answer, or a Section B answer on the
  Article 6(1) route alone, whose missing facts carry ANNEX_III_UNKNOWN_TAG
  (audit D1, R39).

@implements: DEC-33
"""

from __future__ import annotations

from typing import Any

REVIEW_CAUSES: tuple[str, ...] = (
    "article_5_unknown",
    "fact_conflict",
    "area_conflict",
    "area_alone",
    "article_6_3_candidate",
    "article_6_1_open",
    "listed_use_unknown",
)

# B184 (DEC-32; review of Task 4, I1 and I2), moved here from fria.py with its
# text unchanged: the reason a classification marked by a fact conflict is not
# settled. Count-neutral, since one narrower fact can contradict two definitions.
FACT_CONFLICT_REASON = (
    "answers contradict a definition of the Act (fact_conflicts) and one answer of each pair is "
    "wrong, so the classification could change once they are corrected"
)
# B185 (DEC-33, ruling P26), moved here from fria.py with its text unchanged:
# the reason a classification marked by an area conflict is not settled.
AREA_CONFLICT_REASON = (
    "a listed use of Annex III is true while the domain says none of these areas (area_conflicts), so one "
    "of the two answers is wrong"
)

REVIEW_CAUSE_REASONS: dict[str, str] = {
    "article_5_unknown": "an unknown Article 5 fact could change the level to Unacceptable risk",
    "fact_conflict": FACT_CONFLICT_REASON,
    "area_conflict": AREA_CONFLICT_REASON,
    "area_alone": (
        "the level rests on the area alone: no listed use of the area is confirmed (annex_iii_area_unconfirmed)"
    ),
    "article_6_3_candidate": (
        "an Article 6(3) derogation candidacy is pending human legal review, and a confirmed derogation takes "
        "the system out of Article 6(2)"
    ),
    "article_6_1_open": "an unknown Article 6(1) fact could make the system high-risk",
    "listed_use_unknown": "an unknown Annex III listed use could put the system on the Annex III route",
}

STATUS_LINE_PREFIX = "status lowered to requires_human_review: "

_STATUS_LINE_TEXT: dict[str, str] = {
    "article_5_unknown": "unknown prohibition-relevant flags could change the outcome to Unacceptable risk",
    "fact_conflict": "answers contradict a definition of the Act: see fact_conflicts",
    "area_conflict": "a listed use is true while domain is none_of_these_areas: see area_conflicts",
    "area_alone": "the level rests on the area alone; no listed use of the area is confirmed",
    "article_6_3_candidate": "an Article 6(3) derogation candidacy is flagged for human legal review",
    "article_6_1_open": (
        "unknown Article 6(1) facts could add high-risk obligations on top of the Article 50 transparency duty"
    ),
}
_LISTED_USE_UNKNOWN_LIMITED = (
    "unknown Annex III high-risk flags could add high-risk obligations on top of the Article 50 transparency duty"
)
_LISTED_USE_UNKNOWN_SECTION_B = (
    "unknown Annex III facts could put this Section B product on the Annex III route, which brings the "
    "Chapter III requirements and the Article 50 duties Article 2(2) does not"
)

# The words that mark an unknown Annex III fact among the missing facts (R39);
# classify.py and requirements.py import it from here.
ANNEX_III_UNKNOWN_TAG = "(Annex III high-risk relevant, Article 6(2))"
# The two facts of the Article 6(1) route; the classifier's missing line for
# each starts "flags.<fact> is unknown" (B123).
ARTICLE_6_1_FACTS: tuple[str, ...] = ("annex_i_covered_product", "third_party_conformity_assessment_required")
_ROUTE_ARTICLE_6_1 = "article_6_1"
_ROUTE_ARTICLE_6_2 = "article_6_2"


def _names_article_6_1_fact(missing_facts: list[str]) -> bool:
    return any(
        isinstance(line, str) and line.startswith(f"flags.{fact} is unknown")
        for line in missing_facts
        for fact in ARTICLE_6_1_FACTS
    )


def _carries_annex_iii_tag(missing_facts: list[str]) -> bool:
    return any(isinstance(line, str) and ANNEX_III_UNKNOWN_TAG in line for line in missing_facts)


def _section_b_on_article_6_1_alone(answer: dict[str, Any]) -> bool:
    return (
        answer.get("risk_category") == "high_risk"
        and answer.get("annex_i_section") == "B"
        and answer.get("high_risk_routes") == [_ROUTE_ARTICLE_6_1]
    )


def review_causes(
    answer: dict[str, Any], missing_facts: list[str] | None = None, *, for_fria: bool = False
) -> list[str]:
    """The causes of review that hold for a classification answer, in the
    order of REVIEW_CAUSES (spec G D-G92 (8), rulings P12 and R5).

    answer is the classification's answer (the bare answer is enough for the
    first five causes); missing_facts the envelope's missing facts, without
    which article_6_1_open and listed_use_unknown are not read. for_fria drops
    the condition that Annex III decides what is served from
    article_6_3_candidate: the Article 27(1) block holds at unknown for a
    candidate whenever the field is true (D-G92 (iv)). An undetermined answer
    gets its reason from its missing facts and is never given a cause here
    (ruling P32).

    @implements: DEC-33
    """
    if not isinstance(answer, dict):
        return []
    level = answer.get("risk_category")
    if level not in ("unacceptable_risk", "high_risk", "limited_risk", "minimal_risk"):
        return []
    routes = answer.get("high_risk_routes")
    routes = routes if isinstance(routes, list) else []
    holds: set[str] = set()
    if level in ("high_risk", "limited_risk") and "unacceptable_risk" in answer and answer["unacceptable_risk"] is None:
        holds.add("article_5_unknown")
    if answer.get("fact_conflicts"):
        holds.add("fact_conflict")
    if answer.get("area_conflicts"):
        holds.add("area_conflict")
    if level == "high_risk" and answer.get("annex_iii_area_unconfirmed") and not routes:
        holds.add("area_alone")
    if answer.get("article_6_3_exception_candidate") is True and (
        for_fria
        or _ROUTE_ARTICLE_6_1 not in routes
        or (_ROUTE_ARTICLE_6_2 in routes and answer.get("annex_i_section") in ("B", "unknown"))
    ):
        holds.add("article_6_3_candidate")
    if missing_facts is not None:
        if level == "limited_risk" and _names_article_6_1_fact(missing_facts):
            holds.add("article_6_1_open")
        if (level == "limited_risk" or _section_b_on_article_6_1_alone(answer)) and _carries_annex_iii_tag(
            missing_facts
        ):
            holds.add("listed_use_unknown")
    return [cause for cause in REVIEW_CAUSES if cause in holds]


def review_reason(causes: list[str]) -> str:
    """The reasons of the causes, in REVIEW_CAUSES order, joined by "; ".

    @implements: DEC-33
    """
    return "; ".join(REVIEW_CAUSE_REASONS[cause] for cause in REVIEW_CAUSES if cause in causes)


def review_status_line(cause: str, answer: dict[str, Any]) -> str:
    """The answer's rationale line for one cause that holds (ruling P11): the
    words of the classifier's lines before B185 Task 6 for the causes that had
    one; listed_use_unknown says the Section B words on a Section B answer
    and the Article 50 words otherwise.

    @implements: DEC-33
    """
    if cause == "listed_use_unknown":
        text = _LISTED_USE_UNKNOWN_SECTION_B if answer.get("annex_i_section") == "B" else _LISTED_USE_UNKNOWN_LIMITED
    else:
        text = _STATUS_LINE_TEXT[cause]
    return STATUS_LINE_PREFIX + text

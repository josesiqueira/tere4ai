"""FRIA applicability: Article 27(1) as a pure, deterministic rule.

Article 27(1) obliges certain DEPLOYERS of high-risk AI systems to perform
a fundamental rights impact assessment (FRIA) before first use. Whether
that obligation applies is decided here under the same trust split as the
risk ladder (DEC-13): a fixed rule over structured facts decides, never a
model, and any fact the input does not settle is reported by name, never
guessed.

The rule mirrors the operative sentence of Article 27(1) in the frozen
source text (node eu-ai-act:article-27:paragraph-1), which has three parts:
- scope: "Prior to deploying a high-risk AI system referred to in
  Article 6(2)", so the Annex III route only, never the Article 6(1)
  embedded-product route alone;
- exception: "with the exception of high-risk AI systems intended to be
  used in the area listed in point 2 of Annex III" (critical
  infrastructure);
- deployer triggers: "deployers that are bodies governed by public law, or
  are private entities providing public services, and deployers of
  high-risk AI systems referred to in points 5 (b) and (c) of Annex III".

Scope limit, stated plainly: this module decides only whether the
obligation applies. It does not generate or evaluate the assessment
itself (the content elements of Article 27(1) points (a) to (f) and the
Article 27(5) template are a separate, source-gated work item).

A point of Annex III that rests on the domain alone, with no listed use of
it confirmed, is never counted as a confirmed area (B185, spec G D-G92 (5),
(v)): while the level itself rests on it the block answers unknown, and
beside a proven Article 6(1) route it answers as for that route for point 2
and unknown otherwise. Every cause of review that holds is named in the
block's sentence, the area first (D-G92 (8) and the rule added after the
plan's review).

An Annex III fact absent from the input is not read as false (B125): on a
limited_risk or minimal_risk answer, and on a high-risk answer through the
Article 6(1) route only or in the point 2 area only, while the fact could
make the system high-risk under Article 6(2) and the assessment apply, the
outcome is unknown and the fact is named. Only facts that could change the
outcome are named.

The free-text deployer_kind field is never read here: it is an open
vocabulary and cannot be mapped deterministically onto the Article 27(1)
legal categories. Only the structured deployer facts decide.

@implements: DEC-14
@implements: DEC-20
@implements: DEC-23
@implements: DEC-32 (a classification marked by a fact conflict keeps the block unknown)
@implements: DEC-33 (a prohibited classification marked by an area conflict keeps the block unknown;
B185 Task 6: the block names every cause of review, the area first, and never counts a point that
rests on the area as a confirmed area)
@grounded_by: REF-01, REF-30
"""

from __future__ import annotations

from typing import Any

from tere4ai.mcp_server.application_dates import fria_applies_from
from tere4ai.mcp_server.levels import level_name

# Re-exported for the readers that import them from here (requirements.py).
from tere4ai.mcp_server.review_causes import AREA_CONFLICT_REASON as AREA_CONFLICT_REASON
from tere4ai.mcp_server.review_causes import FACT_CONFLICT_REASON as FACT_CONFLICT_REASON
from tere4ai.mcp_server.review_causes import review_reason

ARTICLE_27_PARAGRAPH_1 = "eu-ai-act:article-27:paragraph-1"
ARTICLE_6_PARAGRAPH_3 = "eu-ai-act:article-6:paragraph-3"
ANNEX_III_POINT_2 = "eu-ai-act:annex-iii:point-2"
ANNEX_III_POINT_5B = "eu-ai-act:annex-iii:point-5:b"
ANNEX_III_POINT_5C = "eu-ai-act:annex-iii:point-5:c"

# Timeline as DATA, never control flow: Article 27's date from the reviewed
# table of Article 113 as amended (application_dates.py, point (c)(i), B132),
# the same table every classification and requirement group reads.
FRIA_APPLIES_FROM = fria_applies_from()

# Closed outcome vocabulary. Never "compliant", never a percentage.
FRIA_APPLICABILITY_VOCABULARY = ("applies", "does_not_apply", "unknown")

# System-side triggers: feature flag -> (AnnexItem node, fragment of its
# dump text). The 5(b) fraud-detection carve-out lives in the flag's schema
# definition: a system used for detecting financial fraud must not set the
# flag, mirroring how every other Annex III flag embeds its legal meaning.
SYSTEM_TRIGGER_FLAGS: dict[str, tuple[str, str]] = {
    "creditworthiness_evaluation": (
        ANNEX_III_POINT_5B,
        "evaluate the creditworthiness of natural persons or establish "
        "their credit score (Annex III point 5(b))",
    ),
    "life_health_insurance_risk_pricing": (
        ANNEX_III_POINT_5C,
        "risk assessment and pricing in relation to natural persons in the "
        "case of life and health insurance (Annex III point 5(c))",
    ),
}

# Deployer-side triggers, named verbatim after the Article 27(1) categories.
DEPLOYER_TRIGGER_FACTS: dict[str, str] = {
    "body_governed_by_public_law": "a body governed by public law",
    "private_entity_providing_public_services": (
        "a private entity providing public services"
    ),
}

_SCOPE_NOTE = (
    "This block decides only whether the Article 27(1) FRIA obligation "
    "applies to the deployer. Conducting the assessment itself (the content "
    "elements of Article 27(1) points (a) to (f) and the Article 27(5) "
    "template) is out of scope here."
)


def _block(
    applicability: str,
    rationale: list[str],
    basis_nodes: list[str],
    missing_facts: list[str],
) -> dict[str, Any]:
    assert applicability in FRIA_APPLICABILITY_VOCABULARY
    return {
        "applicability": applicability,
        "rationale": rationale,
        "basis_nodes": basis_nodes,
        "missing_facts": missing_facts,
        "applies_from": FRIA_APPLIES_FROM,
        "note": _SCOPE_NOTE,
    }


# B185 Task 6 (ruling P11): the reasons of review live in review_causes.py,
# which decides which causes hold; FACT_CONFLICT_REASON and
# AREA_CONFLICT_REASON are imported from there with their text unchanged.

# B185 Task 6 (spec G D-G92 (5), (v), (8), the rules added after the plan's
# review, ruling P13): the block's sentences for a point that rests on the
# area and for the causes of review, word for word. The area sentences say
# only what holds for every point, point 2 included (I4).
FRIA_AREA_ALONE_REASON = (
    "the level rests on the area alone: domain '{domain}' places the system in Annex III point {number}, and "
    "no listed use of the point is confirmed, so whether the system is a high-risk AI system referred to in "
    "Article 6(2) is not settled and FRIA applicability stays unknown"
)
FRIA_AREA_BESIDE_ARTICLE_6_1_REASON = (
    "the system is high-risk via the Article 6(1) embedded-product route; domain '{domain}' places it in "
    "Annex III point {number}, but no listed use of the point is confirmed, so whether it is also a high-risk "
    "AI system referred to in Article 6(2) is not settled and FRIA applicability stays unknown"
)
FRIA_AREA_UNKNOWN_USE_LINE = (
    "flags.{fact} is unknown (a listed use of Annex III point {number}); the level rests on the area alone "
    "until a listed use of the point is answered"
)
# B185 Task 6, fix round 1: the same line beside a proven Article 6(1) route,
# where the level rests on that route and only the Article 6(2) part is open.
FRIA_AREA_BESIDE_UNKNOWN_USE_LINE = (
    "flags.{fact} is unknown (a listed use of Annex III point {number}); whether the system is also one "
    "referred to in Article 6(2) is open until a listed use of the point is answered"
)
FRIA_OTHER_CAUSES_TEMPLATE = "the classification is also not settled for these reasons: {reasons}"
FRIA_UNSETTLED_TEMPLATE = (
    "the risk classification is high-risk but not settled: {reasons}; FRIA applicability stays unknown until "
    "the classification is confirmed"
)

_UNKNOWN_ANNEX_III_NONE_CAN = (
    "no unknown Annex III fact can make Article 27(1) apply: each is in "
)
_UNKNOWN_ANNEX_III_POINT_2_REASON = (
    "the area listed in point 2 of Annex III, which Article 27(1) excepts"
)
_UNKNOWN_ANNEX_III_DEPLOYER_REASON = (
    "an area whose trigger is the deployer, who is known to be neither a body "
    "governed by public law nor a private entity providing public services"
)


def _read_unknown_annex_iii_facts(
    unknown_facts: dict[str, str], deployer: dict[str, Any]
) -> tuple[list[str], str | None]:
    """Split the unknown Annex III facts by whether they could bring Article 27(1) in.

    Returns the facts that could, in input order, and, when there are
    unknown facts but none could, the rationale line that says why, built
    from the reasons that hold: the point 2 area (excepted by Article
    27(1)), the deployer known to be neither trigger category, or both.
    A 5(b) or 5(c) fact always could (any deployer); a point 2 fact never
    could; any other fact could unless every deployer trigger fact is known
    false (R1).
    """
    deployer_known_neither = all(
        deployer.get(k) is False for k in DEPLOYER_TRIGGER_FACTS
    )
    could_trigger = [
        flag
        for flag, node in unknown_facts.items()
        if flag in SYSTEM_TRIGGER_FLAGS
        or (node != ANNEX_III_POINT_2 and not deployer_known_neither)
    ]
    if could_trigger or not unknown_facts:
        return could_trigger, None
    reasons = []
    if any(node == ANNEX_III_POINT_2 for node in unknown_facts.values()):
        reasons.append(_UNKNOWN_ANNEX_III_POINT_2_REASON)
    if any(node != ANNEX_III_POINT_2 for node in unknown_facts.values()):
        reasons.append(_UNKNOWN_ANNEX_III_DEPLOYER_REASON)
    return could_trigger, _UNKNOWN_ANNEX_III_NONE_CAN + ", or in ".join(reasons)


# B185, the evidence task (DEC-14, DEC-18): the deployer fact that settles a
# block held at unknown only by listed uses whose trigger is the deployer.
DEPLOYER_FACT_SETTLES_LINE = (
    "deployer.{fact} is unknown (Article 27(1) FRIA-relevant); deployer.{other} is false, so if this is false too "
    "no unknown Annex III fact named here can make Article 27(1) apply; absence is not treated as false"
)


def _deployer_fact_that_settles(could_trigger: list[str], deployer: dict[str, Any]) -> list[str]:
    """The line of the absent deployer fact that would settle the block
    (B185, the evidence task).

    The block is unknown because the facts in could_trigger are unknown. When
    none of them is a point 5(b) or 5(c) fact, which trigger for any deployer,
    each is an area whose trigger is the deployer, and once the deployer is
    known to be neither category none of them can bring Article 27(1) in (R1).
    So when one deployer fact is known false and the other is absent, the
    absent one answered false settles the block at does_not_apply: it is
    named, in the block's missing facts only. With both absent neither alone
    settles it, and with one true the deployer already triggers, so nothing
    is named then.

    @implements: DEC-14
    @implements: DEC-33
    """
    if not could_trigger or any(flag in SYSTEM_TRIGGER_FLAGS for flag in could_trigger):
        return []
    absent = [fact for fact in DEPLOYER_TRIGGER_FACTS if fact not in deployer]
    if len(absent) != 1:
        return []
    other = next(fact for fact in DEPLOYER_TRIGGER_FACTS if fact != absent[0])
    if deployer.get(other) is not False:
        return []
    return [DEPLOYER_FACT_SETTLES_LINE.format(fact=absent[0], other=other)]


def _unknown_annex_iii_line(flag: str) -> str:
    return (
        f"flags.{flag} is unknown (Annex III high-risk relevant, Article 6(2)); "
        "if true the system is high-risk under Article 6(2), which Article "
        "27(1) covers, so absence is not treated as false"
    )


def assess_fria_applicability(
    risk_category: str | None,
    annex_iii_category: str | None,
    flags: dict[str, Any],
    deployer: dict[str, Any],
    article_6_3_exception_candidate: bool = False,
    annex_points: list[str] | None = None,
    unknown_annex_iii_facts: dict[str, str] | None = None,
    annex_iii_area: dict[str, Any] | None = None,
    review_causes: list[str] | None = None,
) -> dict[str, Any]:
    """Decide whether the Article 27(1) FRIA obligation applies.

    risk_category, the Article 6(3) derogation candidacy, and the set of
    matched Annex III points come from the deterministic classification;
    flags and deployer are the structured input facts. Returns the
    closed-vocabulary fria block. Absent facts are unknown, never false;
    when they could change the outcome the answer is "unknown" with each
    missing fact named.

    annex_points is the FULL set of Annex III point nodes confirmed by a
    listed use that is true, so the point-2 exception is scoped to the
    point-2 AREA and never erases the obligation of a system that also falls
    under another point (audit D5). B185 (spec G D-G92 (5), passage (j)): a
    point that rests on the area is never among them; it comes in
    annex_iii_area ({"domain", "point", "number", "unknown_uses"}) and the
    block never counts it as a confirmed area.

    review_causes are the causes of review of the classification that hold
    (review_causes.py), in the order of spec G D-G92 (8); the classifier
    passes the ones its status lines name. A true candidate is read from
    article_6_3_exception_candidate (step 4 below, D-G92 (iv)), so beside a
    proven Article 6(1) route of a Section A product, where the candidate is
    no cause (passage (k)), the block never says the classification is not
    settled. review_causes.py is the one decider of the causes: a caller that
    passes none gets a block with no cause of review (B185 Task 6, fix round
    1), so a direct caller builds them with review_causes.review_causes. The
    fact conflicts, the area conflicts and an unknown Article 5 fact reach
    the block only as these causes.

    unknown_annex_iii_facts maps each Annex III fact absent from the input to
    the Annex III point node it belongs to, in point order (the classifier
    builds it; this module never imports classify). It is read where the
    answer would otherwise be does_not_apply for want of an Annex III
    area: on a limited_risk or minimal_risk answer, and on a high_risk
    answer with no Annex III point confirmed (the Article 6(1) route only,
    or beside it a point 2 area that rests on the domain) or with only the
    point 2 area confirmed. While an unknown fact could make the system
    high-risk under Article 6(2) and the assessment apply, the block is
    unknown, not does_not_apply, and names that fact; on those high-risk
    answers an unknown 5(b) or 5(c) fact keeps its own line, and the other
    facts that could trigger are named beside it. Facts that cannot change
    the outcome are not named: the point 2 area (excepted by Article 27(1)),
    and, once the deployer is known to be neither a public-law body nor a
    private entity providing public services, every area except points 5(b)
    and 5(c), which trigger for any deployer; the does_not_apply rationale
    then says which of these two reasons holds.

    The order on a high_risk answer (B185 Task 6, spec G D-G92 (v), (8), the
    rules added after the plan's review, ruling P13): (1) the level rests on
    the area alone: unknown, FRIA_AREA_ALONE_REASON, then
    FRIA_OTHER_CAUSES_TEMPLATE naming every other cause, before any other
    reading; (2) a point that rests on the area beside the Article 6(1)
    route: for point 2 the Article 6(1)-only reading, for any other point
    unknown with FRIA_AREA_BESIDE_ARTICLE_6_1_REASON; (3) no Annex III point:
    the Article 6(1)-only reading; (4) a true candidate: the candidacy
    sentence (audit D7); (5) any other cause: unknown with
    FRIA_UNSETTLED_TEMPLATE naming every cause (audit D6); (6) the triggers.
    Wherever (2) to (4) answer unknown while other causes hold, the sentence
    after it names them. On an unacceptable_risk answer a fact conflict or
    an area conflict leaves the block unknown, the sentence naming each
    (ruling P26); limited_risk and minimal_risk answers keep their reading
    and name no cause (ruling P33).

    @implements: DEC-33
    """
    rationale: list[str] = []
    basis = [ARTICLE_27_PARAGRAPH_1]
    missing: list[str] = []

    if risk_category is None or risk_category == "undetermined":
        rationale.append(
            "the risk classification is not settled; Article 27(1) applies "
            "only to high-risk AI systems referred to in Article 6(2), so "
            "FRIA applicability cannot be decided yet"
        )
        return _block("unknown", rationale, basis, missing)

    causes = list(review_causes or [])

    if risk_category == "unacceptable_risk":
        marks = [cause for cause in causes if cause in ("fact_conflict", "area_conflict")]
        if marks:
            rationale.append(
                "the system falls under an Article 5 prohibited practice on the facts as read, but "
                + review_reason(marks)
                + "; FRIA applicability stays unknown until the classification is confirmed"
            )
            return _block("unknown", rationale, basis, missing)
        rationale.append(
            "the system falls under an Article 5 prohibited practice; there "
            "is no lawful deployment for Article 27(1) to attach to, and no "
            "assessment can make a prohibited system permissible"
        )
        return _block("does_not_apply", rationale, basis, missing)

    unknown_facts = unknown_annex_iii_facts or {}

    if risk_category in ("minimal_risk", "limited_risk"):
        could_trigger, none_can = _read_unknown_annex_iii_facts(unknown_facts, deployer)
        if could_trigger:
            rationale.append(
                f"the system is classified {level_name(risk_category)} on the "
                "facts given, but an unknown Annex III fact could make it "
                "high-risk under Article 6(2), which Article 27(1) covers, so "
                "FRIA applicability cannot be settled yet"
            )
            missing.extend(_unknown_annex_iii_line(f) for f in could_trigger)
            missing.extend(_deployer_fact_that_settles(could_trigger, deployer))
            return _block("unknown", rationale, basis, missing)
        rationale.append(
            f"the system is classified {level_name(risk_category)}; Article 27(1) "
            "applies only to high-risk AI systems referred to in Article 6(2)"
        )
        if none_can:
            rationale.append(none_can)
        return _block("does_not_apply", rationale, basis, missing)

    # high_risk from here on. Resolve the confirmed Annex III points.
    if annex_points is None:
        annex_points = [annex_iii_category] if annex_iii_category else []
    annex_points = [p for p in annex_points if p]

    def _naming_other_causes(block: dict[str, Any], others: list[str]) -> dict[str, Any]:
        # B185 (the rule added after the plan's review: every cause that holds
        # is named): a block that answers unknown names the other causes.
        if block["applicability"] == "unknown" and others:
            block["rationale"].append(FRIA_OTHER_CAUSES_TEMPLATE.format(reasons=review_reason(others)))
        return block

    if annex_iii_area is not None:
        # B185 (spec G D-G92 (5), (v), ruling P13): a point that rests on the
        # area is never counted as a confirmed area.
        def area_lines(template: str) -> list[str]:
            return [
                template.format(fact=fact, number=annex_iii_area["number"])
                for fact in annex_iii_area.get("unknown_uses") or ()
            ]

        if "area_alone" in causes:
            # The level itself rests on the area: unknown before any other
            # reading, even where no listed use of the area could bring
            # Article 27(1) in (the choice D-G92 records after Codex's review).
            rationale.append(
                FRIA_AREA_ALONE_REASON.format(domain=annex_iii_area["domain"], number=annex_iii_area["number"])
            )
            missing.extend(area_lines(FRIA_AREA_UNKNOWN_USE_LINE))
            return _naming_other_causes(
                _block("unknown", rationale, basis, missing), [c for c in causes if c != "area_alone"]
            )
        if annex_iii_area["point"] != ANNEX_III_POINT_2:
            rationale.append(
                FRIA_AREA_BESIDE_ARTICLE_6_1_REASON.format(
                    domain=annex_iii_area["domain"], number=annex_iii_area["number"]
                )
            )
            # The level rests on the Article 6(1) route here, so the line says
            # only that the Article 6(2) part is open (fix round 1).
            missing.extend(area_lines(FRIA_AREA_BESIDE_UNKNOWN_USE_LINE))
            return _naming_other_causes(_block("unknown", rationale, basis, missing), causes)
        # Point 2 beside the Article 6(1) route: Article 27(1) excepts the
        # point 2 area, so the block answers as for that route (item (v)).

    # An unknown 5(b)/5(c) fact means annex_points may be INCOMPLETE: if the
    # fact were true the system would fall under Annex III point 5 and the
    # FRIA would apply. So a does_not_apply that rests on the absence of a
    # point-5 match is only safe once those facts are known (audit 2026-07-21).
    unknown_system_triggers = [f for f in SYSTEM_TRIGGER_FLAGS if f not in flags]

    def _name_unknown_triggers() -> bool:
        for f in unknown_system_triggers:
            missing.append(
                f"flags.{f} is unknown (Article 27(1) FRIA-relevant); if true "
                "it places the system under Annex III point 5(b)/(c) and "
                "triggers the FRIA, so absence is not treated as false"
            )
        # Another unknown Annex III fact that could trigger (R1) decides once
        # the 5(b)/5(c) facts turn out false, so it is named now as well
        # (B125 re-review N1).
        could_trigger, _ = _read_unknown_annex_iii_facts(unknown_facts, deployer)
        others = [f for f in could_trigger if f not in SYSTEM_TRIGGER_FLAGS]
        missing.extend(_unknown_annex_iii_line(f) for f in others)
        return bool(others)

    other_area_line = (
        "an unknown Annex III fact of another area could also make the "
        "system high-risk under Article 6(2) and the assessment apply, so it "
        "is named as well"
    )

    def _article_6_1_only() -> dict[str, Any]:
        if unknown_system_triggers:
            named_others = _name_unknown_triggers()
            rationale.append(
                "the system is high-risk via the Article 6(1) embedded-product "
                "route and no Annex III category matched the provided facts, "
                "but the point 5(b)/5(c) facts are unknown; either being true "
                "would place it under Article 6(2), so FRIA applicability "
                "cannot be settled yet"
            )
            if named_others:
                rationale.append(other_area_line)
            return _block("unknown", rationale, basis, missing)
        # The 5(b)/5(c) facts are known false. Another unknown Annex III fact
        # could still place the system under Article 6(2) as well (B125, R5).
        could_trigger, none_can = _read_unknown_annex_iii_facts(unknown_facts, deployer)
        if could_trigger:
            missing.extend(_unknown_annex_iii_line(f) for f in could_trigger)
            missing.extend(_deployer_fact_that_settles(could_trigger, deployer))
            rationale.append(
                "the system is high-risk via the Article 6(1) embedded-product "
                "route and no Annex III category matched the provided facts, "
                "but an unknown Annex III fact could also place it under "
                "Article 6(2), which Article 27(1) covers, so FRIA "
                "applicability cannot be settled yet"
            )
            return _block("unknown", rationale, basis, missing)
        rationale.append(
            "the system is high-risk via the Article 6(1) embedded-product "
            "route only; Article 27(1) covers high-risk AI systems referred "
            "to in Article 6(2) (Annex III), and no Annex III category "
            "matched the provided facts"
        )
        if none_can:
            rationale.append(none_can)
        return _block("does_not_apply", rationale, basis, missing)

    if not annex_points:
        return _naming_other_causes(_article_6_1_only(), causes)

    if article_6_3_exception_candidate:
        # The ladder never auto-applies the Article 6(3) derogation; it
        # flags candidacy for a human legal decision. Until that decision
        # exists the system's Article 6(2) status is unsettled, and so is
        # the Article 27(1) obligation that presupposes it (audit D7). On a
        # system on both routes this is the sentence too (D-G92 (8), I6).
        basis.append(ARTICLE_6_PARAGRAPH_3)
        missing.append(
            "the Article 6(3) derogation candidacy is pending human legal "
            "review; a confirmed derogation takes the system out of Article "
            "6(2) and with it out of the Article 27(1) FRIA obligation"
        )
        rationale.append(
            "the classification flags Article 6(3) derogation candidacy; "
            "FRIA applicability stays unknown until a human reviewer "
            "settles whether the system remains high-risk under Article 6(2)"
        )
        return _naming_other_causes(
            _block("unknown", rationale, basis, missing), [c for c in causes if c != "article_6_3_candidate"]
        )

    if causes:
        # The high-risk classification is not settled (audit D6): the
        # sentence names every cause that holds, so it never names a change
        # to Unacceptable risk unless an Article 5 fact is unknown.
        rationale.append(FRIA_UNSETTLED_TEMPLATE.format(reasons=review_reason(causes)))
        return _block("unknown", rationale, basis, missing)

    # Branches (b)/(c): a point 5(b) or 5(c) system triggers the FRIA for
    # ANY deployer. These points are not point 2, so the exception never
    # touches them, even when the system also spans the point-2 area.
    system_trigger_hits = [
        (flag, node, label)
        for flag, (node, label) in SYSTEM_TRIGGER_FLAGS.items()
        if flags.get(flag) is True
    ]
    if system_trigger_hits:
        for flag, node, label in system_trigger_hits:
            basis.append(node)
            rationale.append(
                f"Article 27(1) trigger: {flag} is true ({label}); the FRIA "
                "obligation covers deployers of these systems regardless of "
                "deployer type"
            )
        rationale.append(
            "the assessment must be performed 'Prior to deploying a "
            "high-risk AI system referred to in Article 6(2)' (Article 27(1))"
        )
        return _block("applies", rationale, basis, missing)

    # Branch (a): a public-law body or a private entity providing public
    # services triggers the FRIA for any Annex III area EXCEPT point 2. The
    # point-2 exception is scoped to the point-2 area, so a system that also
    # falls under another point is not excused (audit D5).
    non_point2 = [p for p in annex_points if p != ANNEX_III_POINT_2]
    deployer_trigger_hits = [
        (fact, label)
        for fact, label in DEPLOYER_TRIGGER_FACTS.items()
        if deployer.get(fact) is True
    ]

    if not non_point2:
        # Point-2-only system: branch (a) can never fire. It does_not_apply
        # only once the 5(b)/5(c) facts are known false; while they are unknown
        # either being true would add a non-excepted point-5 area and trigger
        # the FRIA, so the answer stays unknown (audit 2026-07-21).
        basis.append(ANNEX_III_POINT_2)
        if unknown_system_triggers:
            named_others = _name_unknown_triggers()
            rationale.append(
                "the only settled Annex III area is the area listed in point 2 "
                "of Annex III (critical infrastructure, which Article 27(1) "
                "excepts), but the point 5(b)/5(c) facts are unknown; either "
                "being true adds a non-excepted area and triggers the FRIA, so "
                "applicability cannot be settled yet"
            )
            if named_others:
                rationale.append(other_area_line)
            return _block("unknown", rationale, basis, missing)
        # The 5(b)/5(c) facts are known false. Another unknown Annex III fact
        # could still add an area Article 27(1) does not except (B125, R5).
        could_trigger, none_can = _read_unknown_annex_iii_facts(unknown_facts, deployer)
        if could_trigger:
            missing.extend(_unknown_annex_iii_line(f) for f in could_trigger)
            missing.extend(_deployer_fact_that_settles(could_trigger, deployer))
            rationale.append(
                "the only settled Annex III area is the area listed in point 2 "
                "of Annex III (critical infrastructure, which Article 27(1) "
                "excepts) and the point 5(b)/5(c) facts are known false, but an "
                "unknown Annex III fact could add an area Article 27(1) does "
                "not except, so FRIA applicability cannot be settled yet"
            )
            return _block("unknown", rationale, basis, missing)
        rationale.append(
            "the only Annex III area matched is the area listed in point 2 "
            "of Annex III (critical infrastructure), which Article 27(1) "
            "explicitly excepts from the FRIA obligation, and the point "
            "5(b)/5(c) facts are known false, so no trigger applies"
        )
        if none_can:
            rationale.append(none_can)
        return _block("does_not_apply", rationale, basis, missing)

    if deployer_trigger_hits:
        for node in non_point2:
            basis.append(node)
        for fact, label in deployer_trigger_hits:
            rationale.append(
                f"Article 27(1) trigger: the deployer is {label} "
                f"(deployer.{fact}), and the system falls under an Annex III "
                "area other than point 2"
            )
        rationale.append(
            "the assessment must be performed 'Prior to deploying a "
            "high-risk AI system referred to in Article 6(2)' (Article 27(1))"
        )
        return _block("applies", rationale, basis, missing)

    # No trigger fired. Name the facts that, if provided, could still trigger.
    unknown_trigger_facts = [
        f"flags.{flag}" for flag in SYSTEM_TRIGGER_FLAGS if flag not in flags
    ] + [
        f"deployer.{fact}"
        for fact in DEPLOYER_TRIGGER_FACTS
        if fact not in deployer
    ]

    if not unknown_trigger_facts:
        rationale.append(
            "every Article 27(1) trigger fact is explicitly false: the "
            "deployer is neither a body governed by public law nor a "
            "private entity providing public services, and the system falls "
            "under neither point 5(b) nor point 5(c) of Annex III"
        )
        return _block("does_not_apply", rationale, basis, missing)

    for fact in unknown_trigger_facts:
        missing.append(
            f"{fact} is unknown (Article 27(1) FRIA-relevant); absence is "
            "not treated as false"
        )
    rationale.append(
        "the system is high-risk under Article 6(2) but no Article 27(1) "
        "trigger fact is settled; FRIA applicability stays unknown until "
        "the missing facts are provided"
    )
    return _block("unknown", rationale, basis, missing)

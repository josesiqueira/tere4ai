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

The free-text deployer_actor field is never read here: it is an open
vocabulary and cannot be mapped deterministically onto the Article 27(1)
legal categories. Only the structured deployer facts decide.

@implements: DEC-14
@grounded_by: REF-01, REF-30
"""

from __future__ import annotations

from typing import Any

ARTICLE_27_PARAGRAPH_1 = "eu-ai-act:article-27:paragraph-1"
ARTICLE_6_PARAGRAPH_3 = "eu-ai-act:article-6:paragraph-3"
ANNEX_III_POINT_2 = "eu-ai-act:annex-iii:point-2"
ANNEX_III_POINT_5B = "eu-ai-act:annex-iii:point-5:b"
ANNEX_III_POINT_5C = "eu-ai-act:annex-iii:point-5:c"

# Timeline as DATA, never control flow (architecture.md Section 11: the
# Omnibus is an overlay, both versions stay answerable). Checked 2026-07-20:
# Parliament approved 16 June 2026, Council 29 June 2026; the final OJ text
# is not yet published (TASKS.md C1), so the status stays
# adopted_not_yet_applicable and the date must be reconfirmed against the
# OJ text when it lands.
FRIA_APPLIES_FROM = {
    "date": "2027-12-02",
    "meaning": (
        "standalone Annex III high-risk obligations, Article 27 included, "
        "apply at the latest from this date under the Digital Omnibus on AI"
    ),
    "legal_status": "adopted_not_yet_applicable",
    "source": (
        "REF-02 (Digital Omnibus on AI); final OJ reference pending "
        "publication, date to reconfirm against the OJ text (TASKS.md C1)"
    ),
}

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


def assess_fria_applicability(
    risk_category: str | None,
    annex_iii_category: str | None,
    flags: dict[str, Any],
    deployer: dict[str, Any],
    article_6_3_exception_candidate: bool = False,
) -> dict[str, Any]:
    """Decide whether the Article 27(1) FRIA obligation applies.

    risk_category, annex_iii_category, and the Article 6(3) derogation
    candidacy come from the deterministic classification answer; flags and
    deployer are the structured input facts. Returns the closed-vocabulary
    fria block. Absent facts are unknown, never false; when they could
    change the outcome the answer is "unknown" with each missing fact
    named. A pending Article 6(3) derogation blocks the decision: a
    confirmed derogation would take the system out of Article 6(2), and
    with it out of Article 27(1).
    """
    rationale: list[str] = []
    basis = [ARTICLE_27_PARAGRAPH_1]
    missing: list[str] = []

    if risk_category is None or risk_category == "uncertain":
        rationale.append(
            "the risk classification is not settled; Article 27(1) applies "
            "only to high-risk AI systems referred to in Article 6(2), so "
            "FRIA applicability cannot be decided yet"
        )
        return _block("unknown", rationale, basis, missing)

    if risk_category == "prohibited":
        rationale.append(
            "the system falls under an Article 5 prohibited practice; there "
            "is no lawful deployment for Article 27(1) to attach to, and no "
            "assessment can make a prohibited system permissible"
        )
        return _block("does_not_apply", rationale, basis, missing)

    if risk_category in ("minimal_or_none", "transparency_only"):
        rationale.append(
            f"the system is classified {risk_category}; Article 27(1) "
            "applies only to high-risk AI systems referred to in Article 6(2)"
        )
        return _block("does_not_apply", rationale, basis, missing)

    # high_risk from here on.
    if annex_iii_category is None:
        rationale.append(
            "the system is high-risk via the Article 6(1) embedded-product "
            "route only; Article 27(1) covers high-risk AI systems referred "
            "to in Article 6(2) (Annex III), and no Annex III category "
            "matched the provided facts"
        )
        return _block("does_not_apply", rationale, basis, missing)

    if article_6_3_exception_candidate:
        # The ladder never auto-applies the Article 6(3) derogation; it
        # flags candidacy for a human legal decision. Until that decision
        # exists the system's Article 6(2) status is unsettled, and so is
        # the Article 27(1) obligation that presupposes it.
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
        return _block("unknown", rationale, basis, missing)

    system_trigger_hits = [
        (flag, node, label)
        for flag, (node, label) in SYSTEM_TRIGGER_FLAGS.items()
        if flags.get(flag) is True
    ]

    if annex_iii_category == ANNEX_III_POINT_2:
        basis.append(ANNEX_III_POINT_2)
        if system_trigger_hits:
            # The point 2 exception and a point 5(b)/(c) trigger are both
            # supported by the facts; how the exception interacts with a
            # system spanning two Annex III areas is not rule-decidable.
            for flag, node, label in system_trigger_hits:
                basis.append(node)
                rationale.append(
                    f"Article 27(1) trigger supported: {flag} is true "
                    f"({label})"
                )
            rationale.append(
                "the system matches the Annex III point 2 area, which "
                "Article 27(1) excepts, AND a point 5(b)/(c) trigger; the "
                "interaction of the exception with a system spanning "
                "several Annex III areas needs human legal review"
            )
            return _block("unknown", rationale, basis, missing)
        rationale.append(
            "the system is intended to be used in the area listed in point "
            "2 of Annex III (critical infrastructure), which Article 27(1) "
            "explicitly excepts from the FRIA obligation"
        )
        return _block("does_not_apply", rationale, basis, missing)

    deployer_trigger_hits = [
        (fact, label)
        for fact, label in DEPLOYER_TRIGGER_FACTS.items()
        if deployer.get(fact) is True
    ]

    if system_trigger_hits or deployer_trigger_hits:
        for flag, node, label in system_trigger_hits:
            basis.append(node)
            rationale.append(
                f"Article 27(1) trigger: {flag} is true ({label}); the FRIA "
                "obligation covers deployers of these systems regardless of "
                "deployer type"
            )
        for fact, label in deployer_trigger_hits:
            rationale.append(
                f"Article 27(1) trigger: the deployer is {label} "
                f"(deployer.{fact})"
            )
        rationale.append(
            "the assessment must be performed prior to deploying the "
            "system (Article 27(1): 'Prior to deploying a high-risk AI "
            "system referred to in Article 6(2)')"
        )
        return _block("applies", rationale, basis, missing)

    unknown_facts = [
        f"flags.{flag}" for flag in SYSTEM_TRIGGER_FLAGS if flag not in flags
    ] + [
        f"deployer.{fact}"
        for fact in DEPLOYER_TRIGGER_FACTS
        if fact not in deployer
    ]

    if not unknown_facts:
        rationale.append(
            "every Article 27(1) trigger fact is explicitly false: the "
            "deployer is neither a body governed by public law nor a "
            "private entity providing public services, and the system falls "
            "under neither point 5(b) nor point 5(c) of Annex III"
        )
        return _block("does_not_apply", rationale, basis, missing)

    for fact in unknown_facts:
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

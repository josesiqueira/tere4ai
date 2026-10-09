"""MILESTONE3 runtime tool: get_applicable_requirements as a pure, deterministic function.

Consumes the deterministic classification (classify_ai_system), the judged
Layer 2 norms payload (extract_norms build artifact, judged at build time by
the extraction judge), and the offline Layer 0+1 dump. Only judge-ACCEPTED
NormativeStatements are ever returned as requirements; needs_human_review
norms are counted transparently in the summary but excluded from the list,
and rejected norms are excluded entirely. Prohibited systems receive zero
requirements, only the prohibition citation. No model is involved anywhere
in this module; selection and grouping are structural rules over already
judged data.

@implements: DEC-08, DEC-03 (partial: runtime consumption)
@implements: DEC-18
@implements: DEC-19
@implements: DEC-20
@implements: DEC-23
@grounded_by: REF-17, REF-16
"""

from __future__ import annotations

import re
from typing import Any

from tere4ai.act_parties import addressee_of, requestable, serves
from tere4ai.mcp_server.application_dates import (
    ROUTE_ANNEX_I,
    ROUTE_ANNEX_III,
    legal_text,
    provision_dates,
)
from tere4ai.mcp_server.classify import (
    ANNEX_I_SECTION_UNKNOWN_FACT,
    ANNEX_III_UNKNOWN_TAG,
    ARTICLE_2_2_CONDITION,
    ARTICLE_2_2_CONDITIONAL_PROVISIONS,
    ARTICLE_2_2_PROVISIONS,
    ARTICLE_2_2_WORDING,
    ARTICLE_2_PARAGRAPH_2,
    route_of,
)
from tere4ai.mcp_server.tools import make_envelope
from tere4ai.parse_legal_structure.amendments import is_deleted
from tere4ai.parse_legal_structure.labels import LABEL_PATTERN, sort_key

# B145 (spec G D-G80 (10), (21); brief R49): the argument that names the
# party a request is for is addressee; "actor" is retired and refused, the
# message naming the new argument, so a caller of the old tool is told
# rather than served every party's norms (R61).
ACTOR_RETIRED = (
    "the argument 'actor' is retired (spec G D-G80 (21)); name the party with "
    "'addressee', one value of schema/act_parties.json"
)

TRANSPARENCY_GROUP = "article-50"

# Source groups that state a classification rule or a prohibition, not an
# engineering requirement, so they are never served as applicable
# requirements for a (non-prohibited) high-risk system (audit 2026-07-20 W3).
# A high-risk system is by definition not prohibited, so Article 5 norms are
# never its requirements; Articles 6 to 7 and the Annex lists are the
# classification machinery, not obligations on the provider or deployer. The
# obligation regime (Articles 8 to 27 requirements and duties, 50 transparency
# where it also triggers, 72 to 73 monitoring) is kept.
NON_REQUIREMENT_ARTICLE_GROUPS = frozenset(
    {"article-5", "article-6", "article-7"}
)


def _is_requirement_group(group: str) -> bool:
    """False for classification/prohibition groups that are not requirements."""
    return group not in NON_REQUIREMENT_ARTICLE_GROUPS and not group.startswith("annex-")

PROHIBITED_MESSAGE = (
    "This system falls under an Article 5 prohibited AI practice. Prohibited "
    "systems receive no engineering requirements: placing on the market, "
    "putting into service, and use are banned, so no requirement backlog can "
    "make the system permissible. Seek legal review."
)
MINIMAL_MESSAGE = (
    "No Annex III high-risk category, Article 5 prohibition, or Article 50 "
    "transparency obligation matched the provided facts, so no requirements "
    "from the v2 high-risk core apply. General provisions such as AI literacy "
    "(Article 4) are outside this deterministic check."
)
# DEC-18: the message follows why the classification is undetermined, read from
# the classifier's unacceptable_risk field: null means an Article 5 fact is
# missing; false means every Article 5 path is ruled out and the missing
# facts decide whether the system is high-risk. A bare answer without the
# field gets the Article 5 message, the conservative one.
UNCERTAIN_MESSAGE = (
    "The classification is Undetermined: facts missing. Facts that decide "
    "whether an Article 5 prohibition applies are unknown (see the missing facts). No requirements "
    "are returned until the missing facts are provided or a human reviewer "
    "settles the classification."
)
UNCERTAIN_HIGH_RISK_MESSAGE = (
    "The classification is Undetermined: facts missing. Every Article 5 "
    "prohibition is ruled out, but facts that decide whether the system is "
    "high-risk are unknown "
    "(see the missing facts). No requirements are returned until the missing "
    "facts are provided or a human reviewer settles the classification."
)


# B132 (spec G D-G68 (6), rulings R6, R14, R26 and R36): Article 2(2) for a
# system high-risk under Article 6(1) whose product legislation is listed in
# Annex I Section B and which matches no Annex III category (a match makes
# the classification take the Annex III route, R26). Its provisions are
# cited, never served as norms: they are outside the extraction scope (most
# address Member States or amend other acts), and the condition on Articles
# 57 to 59 is stated, never decided.
SECTION_B_MESSAGE = (
    "The product's legislation is listed in Annex I Section B. Under Article 2(2) only Article 6(1), "
    "Article 60a and Articles 102 to 112 apply to this system, and Articles 57, 58 and 59 only in so far "
    "as the requirements for high-risk AI systems have been integrated in that Union harmonisation "
    "legislation, which this answer does not decide. The Chapter III requirements and the Article 50 "
    "transparency obligations do not apply, so no requirement is served; the provisions are cited, "
    "without norms."
)
# R39: a Section B system whose Annex III facts are unknown: an Annex III
# match would put it on the Annex III route (R26), so the Article 2(2)
# answer is not settled.
SECTION_B_ANNEX_III_UNKNOWN_MESSAGE = (
    "The product's legislation is listed in Annex I Section B. Under Article 2(2) only Article 6(1), "
    "Article 60a and Articles 102 to 112 apply to this system, and Articles 57, 58 and 59 only in so far "
    "as the requirements for high-risk AI systems have been integrated in that Union harmonisation "
    "legislation, which this answer does not decide. The Chapter III requirements and the Article 50 "
    "transparency obligations do not apply unless an Annex III point applies, and facts that decide "
    "whether one does are unknown (see the missing facts); the provisions are cited, without norms, "
    "until they are known."
)
# R26 path: what an Article 6(3) derogation candidate can change for a
# Section B product on the Annex III route.
SECTION_B_DEROGATION_NOTE = (
    " For this product, whose legislation is listed in Annex I Section B, an Article 6(3) derogation "
    "that applies would end the Annex III route, and the answer would become the Article 2(2) one, "
    "which serves no Chapter III requirement and no Article 50 obligation."
)
SECTION_UNKNOWN_NOTE = (
    f"{ARTICLE_2_PARAGRAPH_2}: the Annex I section of the product's legislation is unknown; the Chapter "
    "III requirements below are served as for a Section A product, but for a Section B product only "
    "Article 2(2)'s provisions apply (Article 6(1), Article 60a and Articles 102 to 112, and Articles 57 "
    "to 59 on its condition)"
)


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _unwrap_classification(
    classification: dict[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """Accept either the classify_ai_system envelope or its bare answer dict.

    Returns (answer, cited_source_nodes, upstream). The bare answer carries no
    node citations, so the caller falls back to the Article 5 node for the
    prohibited message. When the full envelope form is passed, upstream carries
    the classification's own status, confidence, and missing_facts so the
    requirements envelope can never claim more certainty than the
    classification it rests on (DEC-08). The bare-answer form carries none of
    these, so upstream is empty and the caller applies the documented
    fallbacks.
    """
    if (
        isinstance(classification.get("answer"), dict)
        and "status" in classification
        and "risk_category" in classification["answer"]
    ):
        upstream = {
            "status": classification.get("status"),
            "confidence": classification.get("confidence"),
            "missing_facts": list(classification.get("missing_facts") or []),
        }
        return classification["answer"], list(classification.get("source_nodes", [])), upstream
    return classification, [], {}


def _source_group(source_node_id: str) -> str:
    """Group key for a norm: the article or annex segment of its source node.

    eu-ai-act:article-9:paragraph-1 -> article-9;
    eu-ai-act:annex-iii:point-1 -> annex-iii.
    """
    parts = source_node_id.split(":")
    return parts[1] if len(parts) > 1 else source_node_id


_ARTICLE_GROUP = re.compile(rf"^article-({LABEL_PATTERN})$")


def _group_sort_key(group: str) -> tuple[int, Any]:
    """Articles in the Act's order (4, 4a, 5: labels.sort_key), then the other groups by name."""
    match = _ARTICLE_GROUP.match(group)
    if match:
        return (0, sort_key(match.group(1)))
    return (1, group)


def _actor_matches(norm: dict[str, Any], addressee: str) -> bool:
    """D-G80 (10): the norm's stored addressee value, read in either norms
    schema version (act_parties.addressee_of), is served to the requested
    value: equal, by the Act's one-way construction (Article 3(47), 3(48)),
    or as operators in general to an AI Act role. Never a substring."""
    return serves(addressee_of(norm).value, addressee)


def _requirement_entry(norm: dict[str, Any]) -> dict[str, Any]:
    addressee = addressee_of(norm)
    entry = {
        "norm_id": norm.get("norm_id"),
        "deontic_type": norm.get("deontic_type"),
        "modal": norm.get("modal"),
        "addressee": addressee.value,
        "addressee_explicit": addressee.explicit,
        "addressee_source": "explicit" if addressee.explicit else "inferred",
        "addressee_inference_source_node_id": addressee.source_node_id,
        "action": norm.get("action"),
        "object": norm.get("object"),
        "source_node_id": norm.get("source_node_id"),
        "source_span_id": norm.get("source_span_id"),
    }
    # DEC-19: the requirement type, passed on when the norm carries it; null
    # has a meaning of its own, so a norm from a build before DEC-19, which
    # has no type, gets no key rather than an invented null.
    if "requirement_type" in norm:
        entry["requirement_type"] = norm["requirement_type"]
    conditions = norm.get("conditions") or []
    if conditions:
        entry["conditions"] = conditions
    # Exceptions are carve-outs ("shall not apply where..."); dropping them
    # would hand the consumer a broader obligation than the law states.
    exceptions = norm.get("exceptions") or []
    if exceptions:
        entry["exceptions"] = exceptions
    return entry


def get_applicable_requirements(
    classification_answer: dict[str, Any],
    norms_payload: dict[str, Any],
    dump: dict[str, Any],
    addressee: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    """Judge-accepted engineering requirements applicable to a classified system.

    Deterministic selection over the judged norms build artifact: high_risk
    returns all accepted norms grouped by source article; limited_risk
    returns only Article 50 norms; unacceptable_risk, minimal_risk, and undetermined
    return no requirements with an explanatory message. The optional addressee
    filter takes one value of the Act's parties (schema/act_parties.json) but
    the two sentinels; the argument actor is retired and refused (ACTOR_RETIRED).
    """
    graph_version = _graph_version(dump)
    text = legal_text(dump)
    answer_in, classification_nodes, upstream = _unwrap_classification(classification_answer)
    risk_category = answer_in.get("risk_category")
    node_index = {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}

    # The requirements envelope must never claim more certainty than the
    # classification it rests on (DEC-08). Defer to the classifier's own
    # determination: it already decides whether unresolved facts leave the
    # system unsettled (status requires_human_review, as when a
    # prohibition-relevant fact is unknown) or leave a confident verdict
    # standing (a settled high_risk whose only unknowns are further Annex III
    # categories that cannot change the outcome). We therefore key off the
    # classifier's status and risk_category, never the mere presence of
    # missing facts, so a confident classification with benign category
    # unknowns is not wrongly downgraded.
    upstream_status = upstream.get("status")
    upstream_confidence = upstream.get("confidence")
    upstream_missing = list(upstream.get("missing_facts") or [])
    unsettled = (
        upstream_status == "requires_human_review"
        or risk_category == "undetermined"
    )

    refusal = None
    if actor is not None:
        refusal = ACTOR_RETIRED
    elif addressee is not None and addressee not in requestable():
        refusal = (
            f"addressee filter '{addressee}' is not a party a request can name; "
            f"the accepted values of schema/act_parties.json: {', '.join(requestable())}"
        )
    if refusal is not None:
        return make_envelope(
            answer={"risk_category": risk_category, "requirements_by_article": {}, "summary": {}, "legal_text": text},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[refusal],
        )

    # Prohibited: zero requirements, only the prohibition citation.
    if risk_category == "unacceptable_risk":
        prohibition_nodes = [n for n in classification_nodes if ":article-5" in n]
        if not prohibition_nodes:
            # Bare answer without citations: fall back to the Article 5 node.
            prohibition_nodes = ["eu-ai-act:article-5"]
        cited = [n for n in prohibition_nodes if n in node_index]
        spans = [
            node_index[n]["source_span"]
            for n in cited
            if isinstance(node_index[n].get("source_span"), dict)
        ]
        return make_envelope(
            answer={
                "risk_category": "unacceptable_risk",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": PROHIBITED_MESSAGE,
                "legal_text": text,
            },
            status="not_applicable",
            graph_version=graph_version,
            confidence=1.0,
            source_nodes=cited,
            source_spans=spans,
            legal_status_notes=[
                f"{n}: prohibited AI practice under Article 5; no engineering "
                "requirements are generated for prohibited systems"
                for n in cited
            ],
            missing_facts=[
                f"prohibition node '{n}' from the classification is not present in the graph dump"
                for n in prohibition_nodes
                if n not in node_index
            ],
        )

    if risk_category == "minimal_risk":
        return make_envelope(
            answer={
                "risk_category": "minimal_risk",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": MINIMAL_MESSAGE,
                "legal_text": text,
            },
            status="not_applicable",
            graph_version=graph_version,
            confidence=1.0,
        )

    if risk_category == "undetermined":
        return make_envelope(
            answer={
                "risk_category": "undetermined",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": (
                    UNCERTAIN_HIGH_RISK_MESSAGE
                    if answer_in.get("unacceptable_risk") is False
                    else UNCERTAIN_MESSAGE
                ),
                "legal_text": text,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=upstream_confidence if upstream_confidence is not None else 0.5,
            missing_facts=upstream_missing
            or [
                "the classification is Undetermined: facts missing; requirements "
                "cannot be determined until the classification is settled"
            ],
        )

    if risk_category not in ("high_risk", "limited_risk"):
        return make_envelope(
            answer={"risk_category": risk_category, "requirements_by_article": {}, "summary": {}, "legal_text": text},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"risk_category '{risk_category}' is not a recognised deterministic "
                "classification (expected unacceptable_risk, high_risk, limited_risk, "
                "minimal_risk, or undetermined)"
            ],
        )

    # R37: the dates follow every high-risk route that holds (route_of
    # reads high_risk_routes); the Section B answer is for a system on the
    # Article 6(1) route only.
    route = route_of(answer_in)
    section = answer_in.get("annex_i_section")
    if risk_category == "high_risk" and section == "B" and route == ROUTE_ANNEX_I:
        provisions = [*ARTICLE_2_2_PROVISIONS, *ARTICLE_2_2_CONDITIONAL_PROVISIONS]
        cited = [n for n in (ARTICLE_2_PARAGRAPH_2, *provisions) if n in node_index]
        # R39: the classifier names unknown Annex III facts among its missing facts.
        annex_iii_unknown = [m for m in upstream_missing if ANNEX_III_UNKNOWN_TAG in m]
        section_b_message = SECTION_B_ANNEX_III_UNKNOWN_MESSAGE if annex_iii_unknown else SECTION_B_MESSAGE
        section_b_missing = [f"provision '{n}' named by Article 2(2) is not present in the graph dump"
                             for n in provisions if n not in node_index]
        return make_envelope(
            answer={
                "risk_category": "high_risk",
                "annex_i_section": "B",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": section_b_message,
                "article_2_2": {
                    "node": ARTICLE_2_PARAGRAPH_2,
                    "wording": f"{ARTICLE_2_2_WORDING} {ARTICLE_2_2_CONDITION}",
                    "provisions": list(ARTICLE_2_2_PROVISIONS),
                    "conditional_provisions": list(ARTICLE_2_2_CONDITIONAL_PROVISIONS),
                    "condition": ARTICLE_2_2_CONDITION,
                    "condition_decided": False,
                },
                "application_dates": {n: provision_dates(n, dump, route) for n in provisions},
                "legal_text": text,
            },
            status="requires_human_review" if unsettled or annex_iii_unknown else "potentially_applicable",
            graph_version=graph_version,
            confidence=(upstream_confidence if upstream_confidence is not None else 0.5)
            if unsettled or annex_iii_unknown else 1.0,
            source_nodes=cited,
            source_spans=[node_index[n]["source_span"] for n in cited
                          if isinstance(node_index[n].get("source_span"), dict)],
            legal_status_notes=[section_b_message],
            missing_facts=(upstream_missing if unsettled else annex_iii_unknown) + section_b_missing,
        )

    norms = norms_payload.get("norms")
    if not isinstance(norms, list) or not norms:
        return make_envelope(
            answer={
                "risk_category": risk_category,
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "legal_text": text,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=["norms payload contains no norms; the Layer 2 build artifact is missing"],
        )

    # Scope: limited_risk consumes only Article 50 norms; high_risk
    # consumes the obligation regime, never the classification/prohibition
    # groups (audit W3), so a high-risk system is not handed Article 5
    # prohibitions or Annex classification rows as "requirements".
    if risk_category == "limited_risk":
        in_scope = [n for n in norms if _source_group(str(n.get("source_node_id", ""))) == TRANSPARENCY_GROUP]
    else:
        in_scope = [
            n for n in norms if _is_requirement_group(_source_group(str(n.get("source_node_id", ""))))
        ]

    # A norm on a unit the Omnibus deleted is no requirement of the Act in force
    # (DEC-23; the dev norms were extracted from the 2024 text): skipped and
    # counted. A norm whose unit is missing from the dump is handled as before.
    deleted_source = [n for n in in_scope if is_deleted(node_index.get(str(n.get("source_node_id", ""))))]
    in_scope = [n for n in in_scope if not is_deleted(node_index.get(str(n.get("source_node_id", ""))))]

    accepted = [n for n in in_scope if n.get("judge_verdict") == "accepted"]
    needs_review = [n for n in in_scope if n.get("judge_verdict") == "needs_human_review"]

    returned = [n for n in accepted if addressee is None or _actor_matches(n, addressee)]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for norm in returned:
        grouped.setdefault(_source_group(str(norm.get("source_node_id", ""))), []).append(
            _requirement_entry(norm)
        )
    grouped = {g: grouped[g] for g in sorted(grouped, key=_group_sort_key)}

    per_article: dict[str, dict[str, int]] = {}
    for norm in accepted:
        group = _source_group(str(norm.get("source_node_id", "")))
        per_article.setdefault(group, {"accepted": 0, "needs_human_review": 0})
        per_article[group]["accepted"] += 1
    for norm in needs_review:
        group = _source_group(str(norm.get("source_node_id", "")))
        per_article.setdefault(group, {"accepted": 0, "needs_human_review": 0})
        per_article[group]["needs_human_review"] += 1
    per_article = {g: per_article[g] for g in sorted(per_article, key=_group_sort_key)}

    # Cite the article/annex nodes of the returned groups, resolved in the dump.
    missing_facts: list[str] = []
    source_nodes: list[str] = []
    for group in grouped:
        node_id = f"eu-ai-act:{group}"
        if node_id in node_index:
            source_nodes.append(node_id)
        else:
            missing_facts.append(
                f"source group node '{node_id}' is not present in the graph dump"
            )
    source_spans = [
        {"span_id": n.get("source_span_id"), "norm_id": n.get("norm_id")} for n in returned
    ]

    summary = {
        "risk_category": risk_category,
        "addressee_filter": addressee,
        "total_accepted_in_scope": len(accepted),
        "returned": len(returned),
        "needs_human_review_total": len(needs_review),
        "needs_human_review_note": (
            "needs_human_review norms are counted here for transparency about "
            "the review queue but are never returned as requirements"
        ),
        "per_article": per_article,
        "deleted_source_skipped": len(deleted_source),
        "deleted_source_note": (
            "norms whose source unit the Digital Omnibus deleted are not requirements "
            "of the Act in force and are never returned"
        ),
        "norms_build_id": str(norms_payload.get("build", {}).get("build_id", "unknown")),
    }

    if not returned:
        # Applicable category but nothing survives the filter: say so.
        missing_facts.append(
            "no judge-accepted norms match the requested scope"
            + (f" and addressee filter '{addressee}'" if addressee else "")
        )

    # R43: Article 2(2) excludes point (c)(ii)'s Article 6(1) systems for a
    # Section B product, so with an Annex III match its Chapter III groups are
    # dated by the Annex III route only.
    routes_held = answer_in.get("high_risk_routes")
    annex_iii_holds = route == ROUTE_ANNEX_III or (isinstance(routes_held, list) and "article_6_2" in routes_held)
    group_route = ROUTE_ANNEX_III if section == "B" and annex_iii_holds else route
    answer_out: dict[str, Any] = {
        "risk_category": risk_category,
        "requirements_by_article": grouped,
        "summary": summary,
        # B132 (D-G68 (6)): each served group's application dates from the
        # table of Article 113 as amended, by the classification's route, as data.
        "application_dates": {g: provision_dates(f"eu-ai-act:{g}", dump, group_route) for g in grouped},
        "legal_text": text,
    }
    legal_status_notes: list[str] = []
    if risk_category == "high_risk" and section == "unknown":
        answer_out["annex_i_section"] = "unknown"
        # R44: the note and the fact matter on the Article 6(1) route alone;
        # with an Annex III match Chapter III is served whatever the section.
        if route == ROUTE_ANNEX_I:
            legal_status_notes.append(SECTION_UNKNOWN_NOTE)
            if ANNEX_I_SECTION_UNKNOWN_FACT not in missing_facts:
                missing_facts.append(ANNEX_I_SECTION_UNKNOWN_FACT)
    elif section is not None:
        answer_out["annex_i_section"] = section
    # Pass the classification's deterministic FRIA block (fria.py, DEC-14)
    # through verbatim, so the Article 27(1) applicability answer sits next
    # to the article-27 obligations it governs. Never recomputed here.
    fria = answer_in.get("fria")
    if isinstance(fria, dict):
        answer_out["fria"] = fria

    # Requirements are applicable; no project evidence has been evaluated yet,
    # hence applicable_missing_evidence (DEC-08 vocabulary).
    status = "applicable_missing_evidence" if returned else "requires_human_review"
    confidence = 1.0 if returned else 0.5

    if unsettled:
        # The upstream classification is not settled, so this envelope must
        # not upgrade its certainty (DEC-08). Keep the provisional requirements
        # for the tentative risk_category so the answer stays useful, but carry
        # the upstream abstention verbatim: the classification could still
        # change (for example to unacceptable_risk, which yields zero requirements).
        status = "requires_human_review"
        confidence = upstream_confidence if upstream_confidence is not None else 0.5
        missing_facts = list(upstream_missing) + [
            m for m in missing_facts if m not in upstream_missing
        ]
        if not missing_facts:
            missing_facts = [
                "the upstream classification is unsettled and flagged for human "
                "review; requirements are provisional until it is settled"
            ]
        answer_out["provisional"] = True
        answer_out["provisional_note"] = (
            "These requirements are provisional pending the human-review "
            "determination of the classification. The risk category is "
            "tentative and could change, for example to Unacceptable risk, "
            "which yields zero requirements."
        )
        if section == "B" and answer_in.get("annex_iii_category"):
            answer_out["provisional_note"] += SECTION_B_DEROGATION_NOTE

    return make_envelope(
        answer=answer_out,
        status=status,
        graph_version=graph_version,
        confidence=confidence,
        source_nodes=source_nodes,
        source_spans=source_spans,
        legal_status_notes=legal_status_notes,
        missing_facts=missing_facts,
    )

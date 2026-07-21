"""M3 runtime tool: get_applicable_requirements as a pure, deterministic function.

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
@grounded_by: REF-17, REF-16
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.tools import make_envelope

_REPO_ROOT = Path(__file__).resolve().parents[3]
NORMS_SCHEMA_PATH = _REPO_ROOT / "schema" / "json_schemas" / "norms.schema.json"

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
UNCERTAIN_MESSAGE = (
    "The classification is uncertain because prohibition-relevant facts are "
    "unknown. No requirements are returned until the missing facts are "
    "provided or a human reviewer settles the classification."
)


@lru_cache(maxsize=1)
def _canonical_actor_roles() -> tuple[str, ...]:
    schema = json.loads(NORMS_SCHEMA_PATH.read_text(encoding="utf-8"))
    return tuple(schema["$defs"]["actorRole"]["enum"])


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _unwrap_classification(classification: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Accept either the classify_ai_system envelope or its bare answer dict.

    Returns (answer, cited_source_nodes). The bare answer carries no node
    citations, so the caller falls back to the Article 5 node for the
    prohibited message.
    """
    if (
        isinstance(classification.get("answer"), dict)
        and "status" in classification
        and "risk_category" in classification["answer"]
    ):
        return classification["answer"], list(classification.get("source_nodes", []))
    return classification, []


def _source_group(source_node_id: str) -> str:
    """Group key for a norm: the article or annex segment of its source node.

    eu-ai-act:article-9:paragraph-1 -> article-9;
    eu-ai-act:annex-iii:point-1 -> annex-iii.
    """
    parts = source_node_id.split(":")
    return parts[1] if len(parts) > 1 else source_node_id


def _group_sort_key(group: str) -> tuple[int, Any]:
    if group.startswith("article-"):
        suffix = group.removeprefix("article-")
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, group)


def _actor_matches(norm: dict[str, Any], actor: str) -> bool:
    """Deterministic actor filter against the canonical vocabulary.

    Matches when actor_inferred equals the canonical role, or when the
    canonical role's words appear in the lowercased free-text actor_explicit
    (for example 'provider' matches 'providers of high-risk AI systems').
    """
    if norm.get("actor_inferred") == actor:
        return True
    explicit = (norm.get("actor_explicit") or "").lower()
    return bool(explicit) and actor.replace("_", " ") in explicit


def _requirement_entry(norm: dict[str, Any]) -> dict[str, Any]:
    explicit = norm.get("actor_explicit")
    entry = {
        "norm_id": norm.get("norm_id"),
        "deontic_type": norm.get("deontic_type"),
        "modal": norm.get("modal"),
        "actor": explicit or norm.get("actor_inferred"),
        "actor_source": "explicit" if explicit else "inferred",
        "action": norm.get("action"),
        "object": norm.get("object"),
        "source_node_id": norm.get("source_node_id"),
        "source_span_id": norm.get("source_span_id"),
    }
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
    actor: str | None = None,
) -> dict[str, Any]:
    """Judge-accepted engineering requirements applicable to a classified system.

    Deterministic selection over the judged norms build artifact: high_risk
    returns all accepted norms grouped by source article; transparency_only
    returns only Article 50 norms; prohibited, minimal_or_none, and uncertain
    return no requirements with an explanatory message. The optional actor
    filter uses the canonical actor vocabulary of norms.schema.json.
    """
    graph_version = _graph_version(dump)
    answer_in, classification_nodes = _unwrap_classification(classification_answer)
    risk_category = answer_in.get("risk_category")
    node_index = {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}

    if actor is not None and actor not in _canonical_actor_roles():
        return make_envelope(
            answer={"risk_category": risk_category, "requirements_by_article": {}, "summary": {}},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"actor filter '{actor}' is not in the canonical actor vocabulary "
                f"of norms.schema.json: {', '.join(_canonical_actor_roles())}"
            ],
        )

    # Prohibited: zero requirements, only the prohibition citation.
    if risk_category == "prohibited":
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
                "risk_category": "prohibited",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": PROHIBITED_MESSAGE,
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

    if risk_category == "minimal_or_none":
        return make_envelope(
            answer={
                "risk_category": "minimal_or_none",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": MINIMAL_MESSAGE,
            },
            status="not_applicable",
            graph_version=graph_version,
            confidence=1.0,
        )

    if risk_category == "uncertain":
        return make_envelope(
            answer={
                "risk_category": "uncertain",
                "requirements_by_article": {},
                "summary": {"returned": 0},
                "message": UNCERTAIN_MESSAGE,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            missing_facts=[
                "risk classification is uncertain; requirements cannot be "
                "determined until the classification is settled"
            ],
        )

    if risk_category not in ("high_risk", "transparency_only"):
        return make_envelope(
            answer={"risk_category": risk_category, "requirements_by_article": {}, "summary": {}},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"risk_category '{risk_category}' is not a recognised deterministic "
                "classification (expected prohibited, high_risk, transparency_only, "
                "minimal_or_none, or uncertain)"
            ],
        )

    norms = norms_payload.get("norms")
    if not isinstance(norms, list) or not norms:
        return make_envelope(
            answer={
                "risk_category": risk_category,
                "requirements_by_article": {},
                "summary": {"returned": 0},
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=["norms payload contains no norms; the Layer 2 build artifact is missing"],
        )

    # Scope: transparency_only consumes only Article 50 norms; high_risk
    # consumes the obligation regime, never the classification/prohibition
    # groups (audit W3), so a high-risk system is not handed Article 5
    # prohibitions or Annex classification rows as "requirements".
    if risk_category == "transparency_only":
        in_scope = [n for n in norms if _source_group(str(n.get("source_node_id", ""))) == TRANSPARENCY_GROUP]
    else:
        in_scope = [
            n for n in norms if _is_requirement_group(_source_group(str(n.get("source_node_id", ""))))
        ]

    accepted = [n for n in in_scope if n.get("judge_verdict") == "accepted"]
    needs_review = [n for n in in_scope if n.get("judge_verdict") == "needs_human_review"]

    returned = [n for n in accepted if actor is None or _actor_matches(n, actor)]

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
        "actor_filter": actor,
        "total_accepted_in_scope": len(accepted),
        "returned": len(returned),
        "needs_human_review_total": len(needs_review),
        "needs_human_review_note": (
            "needs_human_review norms are counted here for transparency about "
            "the review queue but are never returned as requirements"
        ),
        "per_article": per_article,
        "norms_build_id": str(norms_payload.get("build", {}).get("build_id", "unknown")),
    }

    if not returned:
        # Applicable category but nothing survives the filter: say so.
        missing_facts.append(
            "no judge-accepted norms match the requested scope"
            + (f" and actor filter '{actor}'" if actor else "")
        )

    answer_out: dict[str, Any] = {
        "risk_category": risk_category,
        "requirements_by_article": grouped,
        "summary": summary,
    }
    # Pass the classification's deterministic FRIA block (fria.py, DEC-14)
    # through verbatim, so the Article 27(1) applicability answer sits next
    # to the article-27 obligations it governs. Never recomputed here.
    fria = answer_in.get("fria")
    if isinstance(fria, dict):
        answer_out["fria"] = fria

    return make_envelope(
        answer=answer_out,
        # Requirements are applicable; no project evidence has been evaluated
        # yet, hence applicable_missing_evidence (DEC-08 vocabulary).
        status="applicable_missing_evidence" if returned else "requires_human_review",
        graph_version=graph_version,
        confidence=1.0 if returned else 0.5,
        source_nodes=source_nodes,
        source_spans=source_spans,
        missing_facts=missing_facts,
    )

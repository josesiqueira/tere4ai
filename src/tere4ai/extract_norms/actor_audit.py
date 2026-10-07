"""B144 (spec G D-G76 (7)): the extraction build record's two checks over
the norms of Articles 8 to 15.

@implements: DEC-26
@grounded_by: REF-01, REF-11

(i) The served count: the accepted norms of Articles 8 to 15, on units the
Digital Omnibus did not delete, that the role filter of U3 does not serve
to the provider (mcp_server/requirements.py, _actor_matches), with their
ids. (ii) The actor audit: every norm of Articles 8 to 15, whatever its
verdict, in exactly one of four groups, applied in this order: against the
representation, the rule applied, a written party, outside the rule; and
the norms outside Articles 8 to 15 whose actor source is the Article 16(a)
node. Nothing is removed or changed: the checks read the norms. They run
over the merged norms of a run, inherited checkpoint groups included.
"""

from __future__ import annotations

from typing import Any

from tere4ai.canonicalize.canonicalizer import canonicalize_actor
from tere4ai.mcp_server.requirements import _actor_matches
from tere4ai.parse_legal_structure.amendments import is_deleted

# Chapter III Section 2 of the Act as amended, "Requirements for high-risk
# AI systems": Layer 1's HAS_ARTICLE edges from SECTION_2_NODE go to these
# Articles and to nothing else (test_actor_audit.py reads them in
# layer1.json). extract_norms v4 and judge_norms v4 name the same range.
SECTION_2_ARTICLES = tuple(f"article-{n}" for n in range(8, 16))
SECTION_2_NODE = "eu-ai-act:chapter-iii:section-2"
# Article 16(a): "ensure that their high-risk AI systems are compliant with
# the requirements set out in Section 2;"
POINT_A_NODE = "eu-ai-act:article-16:paragraph-1:point-a"
PROVIDER = "provider"
COUNT_KEYS = (
    "section_2_not_served_to_provider",
    "section_2_actor_audit",
    "point_a_source_outside_section_2",
)


def in_section_2(source_node_id: Any) -> bool:
    """A unit of Articles 8 to 15, read from the Article segment of its id
    (eu-ai-act:article-80 is not Article 8)."""
    if not isinstance(source_node_id, str):
        return False
    parts = source_node_id.split(":")
    return len(parts) >= 2 and parts[0] == "eu-ai-act" and parts[1] in SECTION_2_ARTICLES


def _written(norm: dict[str, Any]) -> str | None:
    value = norm.get("actor_explicit")
    return value if isinstance(value, str) and value.strip() else None


def _inferred(norm: dict[str, Any]) -> str | None:
    value = norm.get("actor_inferred")
    return value if isinstance(value, str) and value else None


def not_served_to_provider(norms: list[dict[str, Any]], dump: dict[str, Any]) -> list[str]:
    """(i): accepted norms of Articles 8 to 15 on undeleted units the provider is not served."""
    nodes = {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}
    return [
        str(norm.get("norm_id"))
        for norm in norms
        if in_section_2(norm.get("source_node_id"))
        and norm.get("judge_verdict") == "accepted"
        and not is_deleted(nodes.get(norm["source_node_id"]))
        and not _actor_matches(norm, PROVIDER)
    ]


def _against_reason(norm: dict[str, Any]) -> str | None:
    written, inferred = _written(norm), _inferred(norm)
    if written and inferred:
        return "both actor slots set"
    if not written and not inferred:
        return "both actor slots empty"
    if inferred == PROVIDER:
        source = norm.get("actor_inference_source_node_id")
        if not source:
            return "provider inferred with no source"
        if source != POINT_A_NODE:
            return f"provider inferred with another source: {source}"
    return None


def actor_audit(norms: list[dict[str, Any]]) -> dict[str, Any]:
    """(ii): every norm of Articles 8 to 15 in the first group whose condition it meets."""
    rule_applied: list[str] = []
    written_party: list[dict[str, Any]] = []
    outside_the_rule: list[dict[str, Any]] = []
    against: list[dict[str, Any]] = []
    section_2 = [norm for norm in norms if in_section_2(norm.get("source_node_id"))]
    for norm in section_2:
        norm_id = str(norm.get("norm_id"))
        reason = _against_reason(norm)
        written = _written(norm)
        if reason is not None:
            against.append({"norm_id": norm_id, "reason": reason})
        elif _inferred(norm) == PROVIDER:
            # the source is the point (a) node and actor_explicit is empty,
            # or _against_reason would have named it
            rule_applied.append(norm_id)
        elif written:
            canonical, _method = canonicalize_actor(written)
            written_party.append(
                {"norm_id": norm_id, "label": canonical} if canonical is not None
                else {"norm_id": norm_id, "label": "unresolved", "phrase": written}
            )
        else:
            outside_the_rule.append(
                {"norm_id": norm_id, "actor_inferred": _inferred(norm), "deontic_type": norm.get("deontic_type")}
            )
    return {
        "rule_applied": {"count": len(rule_applied), "norm_ids": rule_applied},
        "written_party": {"count": len(written_party), "norms": written_party},
        "outside_the_rule": {"count": len(outside_the_rule), "norms": outside_the_rule},
        "against_the_representation": {"count": len(against), "norms": against},
        "sum": len(rule_applied) + len(written_party) + len(outside_the_rule) + len(against),
        "norms_of_section_2": len(section_2),
    }


def point_a_outside_section_2(norms: list[dict[str, Any]]) -> list[str]:
    """Every norm outside Articles 8 to 15 whose actor source is the point (a) node."""
    return [
        str(norm.get("norm_id"))
        for norm in norms
        if not in_section_2(norm.get("source_node_id"))
        and norm.get("actor_inference_source_node_id") == POINT_A_NODE
    ]


def section_2_checks(norms: list[dict[str, Any]], dump: dict[str, Any]) -> dict[str, Any]:
    """The three entries of the execution's counts (spec G D-G76 (7))."""
    unserved = not_served_to_provider(norms, dump)
    outside = point_a_outside_section_2(norms)
    return {
        "section_2_not_served_to_provider": {"count": len(unserved), "norm_ids": unserved},
        "section_2_actor_audit": actor_audit(norms),
        "point_a_source_outside_section_2": {"count": len(outside), "norm_ids": outside},
    }


def report_lines(checks: dict[str, Any]) -> list[str]:
    """What the command prints: the counts, and the ids a person reads first."""
    unserved = checks["section_2_not_served_to_provider"]
    audit = checks["section_2_actor_audit"]
    outside = checks["point_a_source_outside_section_2"]
    lines = [f"Articles 8 to 15, accepted norms the provider is not served: {unserved['count']}"]
    lines += [f"  {norm_id}" for norm_id in unserved["norm_ids"]]
    lines.append(
        f"Articles 8 to 15, actor audit of {audit['norms_of_section_2']} norms: "
        f"rule applied {audit['rule_applied']['count']}, written party {audit['written_party']['count']}, "
        f"outside the rule {audit['outside_the_rule']['count']}, "
        f"against the representation {audit['against_the_representation']['count']} (sum {audit['sum']})"
    )
    lines += [
        f"  against the representation: {entry['norm_id']} ({entry['reason']})"
        for entry in audit["against_the_representation"]["norms"]
    ]
    lines.append(f"Norms outside Articles 8 to 15 whose actor source is {POINT_A_NODE}: {outside['count']}")
    lines += [f"  {norm_id}" for norm_id in outside["norm_ids"]]
    return lines

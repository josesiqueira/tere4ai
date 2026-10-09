"""B144 (spec G D-G76 (7)): the extraction build record's two checks over
the norms of Articles 8 to 15.

@implements: DEC-26
@implements: DEC-27
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

B145 (spec G D-G80 (11)): every reader goes through tere4ai.act_parties, so a
v5 run's version 2 norms are audited as a v4 run's were, and four counts of
the addressee are added.
"""

from __future__ import annotations

from typing import Any

from tere4ai import act_parties as ap
from tere4ai.extract_norms.set_up_rule import rows_for
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
    value = ap.slots_of(norm)[0]
    return value if isinstance(value, str) and value.strip() else None


def _inferred(norm: dict[str, Any]) -> str | None:
    value = ap.slots_of(norm)[1]
    return value if isinstance(value, str) and value.strip() else None


def _source(norm: dict[str, Any]) -> Any:
    return ap.slots_of(norm)[2]


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
        source = _source(norm)
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
            addressee = ap.addressee_of(norm)
            written_party.append(
                {"norm_id": norm_id, "label": addressee.value} if addressee.placement == "placed"
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
        and _source(norm) == POINT_A_NODE
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


# B145 (spec G D-G80 (11)): the four counts of the addressee over every norm
# of the run, inherited checkpoint groups included.
ADDRESSEE_COUNT_KEYS = (
    "addressee_values",
    "unplaced_written_addressees",
    "set_up_rule_applied",
    "set_up_thing_as_written_addressee",
)


def _thing_words(text: str) -> str:
    return ap._strip_leading(" ".join(text.lower().replace("\u2019", "'").split()))


def addressee_counts(norms: list[dict[str, Any]]) -> dict[str, Any]:
    """addressee_values: norms per value of the Act's parties (the list's order,
    values with none left out); unplaced_written_addressees: each written
    phrase the list could not place, with its norms; set_up_rule_applied: the
    norms whose inferred party (not a sentinel) rests on a set-up row of their
    unit or on their own unit; set_up_thing_as_written_addressee: the norms on
    a covered unit whose written addressee is the row's thing (the rule missed
    by the model and passed by the judge)."""
    per_value: dict[str, int] = {}
    unplaced: dict[str, list[str]] = {}
    applied: list[str] = []
    thing_written: list[str] = []
    for norm in norms:
        norm_id = str(norm.get("norm_id"))
        addressee = ap.addressee_of(norm)
        per_value[addressee.value] = per_value.get(addressee.value, 0) + 1
        if addressee.placement == "unplaced" and addressee.explicit is not None:
            unplaced.setdefault(addressee.explicit, []).append(norm_id)
        unit = str(norm.get("source_node_id") or "")
        rows = rows_for(unit)
        if addressee.inferred and addressee.inferred not in ap.SENTINELS and (
            addressee.source_node_id == unit
            or any(row.source == addressee.source_node_id and row.party == addressee.inferred for row in rows)
        ):
            applied.append(norm_id)
        if addressee.explicit is not None and any(
            _thing_words(addressee.explicit) == _thing_words(thing) for row in rows for thing in row.things
        ):
            thing_written.append(norm_id)
    return {
        "addressee_values": {value: per_value[value] for value in ap.values() if value in per_value},
        "unplaced_written_addressees": [{"phrase": phrase, "norm_ids": ids} for phrase, ids in unplaced.items()],
        "set_up_rule_applied": {"count": len(applied), "norm_ids": applied},
        "set_up_thing_as_written_addressee": {"count": len(thing_written), "norm_ids": thing_written},
    }


def addressee_report_lines(counts: dict[str, Any]) -> list[str]:
    """What the command prints of the four counts, zeros included (D-G80 (11))."""
    values = ", ".join(f"{value} {n}" for value, n in counts["addressee_values"].items()) or "none"
    lines = [f"Addressees by value of the Act's parties: {values}"]
    unplaced = counts["unplaced_written_addressees"]
    lines.append(f"Written addressees the Act's parties could not place: {sum(len(e['norm_ids']) for e in unplaced)}")
    lines += [f"  \"{entry['phrase']}\": {', '.join(entry['norm_ids'])}" for entry in unplaced]
    applied = counts["set_up_rule_applied"]
    lines.append(f"Norms whose addressee rests on the set-up rule: {applied['count']}")
    lines += [f"  {norm_id}" for norm_id in applied["norm_ids"]]
    thing = counts["set_up_thing_as_written_addressee"]
    lines.append(f"Norms on a set-up unit whose written addressee is the row's thing: {thing['count']}")
    lines += [f"  {norm_id}" for norm_id in thing["norm_ids"]]
    return lines

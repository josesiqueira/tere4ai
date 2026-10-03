"""Critical validation gates: a build that fails these is not published.

@implements: DEC-10 (partial: structural gates; deep-extraction gates activate with M2 data)
@grounded_by: REF-27, REF-26, ADD-21

Architecture.md Section 13. Gates implemented here:
  G1 no orphan legal nodes (every Layer 1 node reachable from the Regulation)
  G2 no source-derived node without a frozen source file (span sha in build snapshots)
  G3 no norm without a source span
  G4 no accepted alignment without evidence spans on both sides
  G5 no recital treated as binding (recitals never norm sources, never point parents)
  G6 no amendment silently replacing the in-force source: the Omnibus is either kept
     apart (merged_into_base False, no unit changed) or merged with every marker read
     and checked and every unit checked (spec G D-G68)
  G2 also refuses a span id carried by an in-force node and an earlier version (B132)

validate_build returns a report; the build entry point refuses to publish on
failure (no silent degradation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HIERARCHY_EDGES = {
    "HAS_CHAPTER",
    "HAS_SECTION",
    "HAS_ARTICLE",
    "HAS_PARAGRAPH",
    "HAS_SUBPARAGRAPH",
    "HAS_POINT",
    "HAS_RECITAL",
    "HAS_ANNEX",
    "HAS_ANNEX_ITEM",
}

# Edges that make a Layer 1 node reachable for the orphan gate (G1). Beyond
# the hierarchy, a Definition node hangs off its defining Article 3 point via
# DEFINES_TERM (a containment edge, kept out of HIERARCHY_EDGES so the G5
# recital rule stays strict). CONTEXT_FOR is deliberately NOT here: it is a
# context edge, never hierarchy, so recitals remain reachable only via
# HAS_RECITAL (recitals are context only, architecture.md Section 1).
# HAS_CROSS_REFERENCE is likewise containment: a reified CrossReference
# node belongs to the paragraph whose text carries the citation (#44).
# HAS_VERSION links a changed unit to its 2024 wording (B132, D-G68 (3)).
REACHABILITY_EDGES = HIERARCHY_EDGES | {"DEFINES_TERM", "HAS_CROSS_REFERENCE", "HAS_VERSION"}
UNIT_TYPES = ("Chapter", "Section", "Article", "Paragraph", "Subparagraph", "Point", "Annex", "AnnexItem")
CONSOLIDATED_ID = "src:eu-ai-act:consolidated-2026-07-27"


@dataclass
class ValidationReport:
    failures: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures


def validate_build(
    dump: dict,
    norms: list[dict] | None = None,
    alignments: list[dict] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    nodes = {n["id"]: n for n in dump["nodes"]}
    edges = dump["edges"]

    # G1: reachability from the Regulation root over hierarchy edges
    children: dict[str, list[str]] = {}
    for e in edges:
        if e["edge_type"] in REACHABILITY_EDGES:
            children.setdefault(e["from"], []).append(e["to"])
    reachable: set[str] = set()
    stack = ["eu-ai-act"]
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        stack.extend(children.get(cur, []))
    layer1_ids = {i for i, n in nodes.items() if n.get("layer") == 1}
    orphans = sorted(layer1_ids - reachable)
    for orphan in orphans[:20]:
        report.failures.append(f"G1 orphan legal node: {orphan}")
    if len(orphans) > 20:
        report.failures.append(f"G1 plus {len(orphans) - 20} more orphans")
    report.stats["layer1_nodes"] = len(layer1_ids)
    report.stats["orphans"] = len(orphans)

    # G2: every source span cites a snapshot listed in the build
    build_shas = {s["sha256"] for s in dump["build"]["snapshots"]}
    bad_span = 0
    for n in dump["nodes"]:
        span = n.get("source_span")
        if span and span["snapshot_sha256"] not in build_shas:
            bad_span += 1
            if bad_span <= 5:
                report.failures.append(
                    f"G2 node {n['id']} cites a snapshot not in the build inputs"
                )
    report.stats["nodes_with_unlisted_snapshot"] = bad_span
    # G2, span ids: an earlier version's span never shares an id with an
    # in-force span, because span lookup returns the first match (B132).
    version_spans = {n["source_span"]["span_id"] for n in dump["nodes"]
                     if n.get("type") == "UnitVersion" and n.get("source_span")}
    in_force_spans = {n["source_span"]["span_id"] for n in dump["nodes"]
                      if n.get("type") != "UnitVersion" and n.get("source_span")}
    for span_id in sorted(version_spans & in_force_spans)[:5]:
        report.failures.append(f"G2 span id {span_id} is carried by an in-force node and a version node")

    # G3: no norm without a source span
    recital_ids = {i for i, n in nodes.items() if n.get("type") == "Recital"}
    for norm in norms or []:
        if not norm.get("source_span_id"):
            report.failures.append(f"G3 norm without source span: {norm.get('norm_id')}")
        # G5 half: norms never derive from recitals
        if norm.get("source_node_id") in recital_ids:
            report.failures.append(
                f"G5 norm derived from a recital: {norm.get('norm_id')}"
            )
    report.stats["norms_checked"] = len(norms or [])

    # G4: accepted alignments need evidence spans on both sides
    for a in alignments or []:
        if a.get("judge_verdict") == "accepted" or a.get("review_status") == "accepted":
            if not a.get("source_evidence_span_ids") or not a.get("target_evidence_span_ids"):
                report.failures.append(
                    f"G4 accepted alignment without two-sided evidence: {a.get('id')}"
                )
    report.stats["alignments_checked"] = len(alignments or [])

    # G5 other half: recitals never own operative children
    for e in edges:
        if e["from"] in recital_ids and e["edge_type"] in HIERARCHY_EDGES - {"HAS_RECITAL"}:
            report.failures.append(f"G5 recital with operative child: {e['edge_id']}")

    # G6: no silent replacement. Since B132 the Omnibus is merged into the
    # base text: Layer 1 is the Act as amended. The checks themselves run in
    # the parse (consolidated.build_in_force_dump raises on any failure); G6
    # verifies their record on the dump (every marker read and checked, every
    # unit checked, the reviewed marker list's digest equal on the Omnibus
    # SourceDocument and in the build), so a dump whose record is missing or
    # edited is refused. Kept apart (merged_into_base False), no unit may
    # carry a change.
    sources = {n["id"]: n for n in dump["nodes"] if n.get("type") == "SourceDocument"}
    base = sources.get("src:eu-ai-act:oj-2024-07-12")
    omnibus = sources.get("src:omnibus-com-2025-836")
    if base is None or base.get("legal_status") != "in_force":
        report.failures.append("G6 base act missing or not marked in_force")
    changed = [i for i, n in nodes.items() if n.get("amendment") not in (None, "unchanged")]
    if omnibus is not None:
        if not any(e["edge_type"] == "AMENDS" and e["from"] == omnibus["id"] for e in edges):
            report.failures.append("G6 amending instrument without an AMENDS edge")
        merged = omnibus.get("merged_into_base")
        if merged is True:
            record = dump["build"].get("amendments") or {}
            units = sum(1 for n in dump["nodes"] if n.get("type") in UNIT_TYPES)
            if not record:
                report.failures.append(
                    "G6 the Omnibus is merged but the build records no amendment checks: "
                    "silent replacement forbidden")
            else:
                if record.get("marker_list_sha256") != omnibus.get("marker_list_sha256"):
                    report.failures.append("G6 the build's marker list is not the one the Omnibus SourceDocument names")
                if not record.get("markers_read") or record.get("markers_checked") != record.get("markers_read"):
                    report.failures.append("G6 not every change marker was read and checked")
                if record.get("units_failed") != 0 or record.get("units_checked") != units:
                    report.failures.append(
                        f"G6 {record.get('units_checked')} units checked of {units} in the dump, "
                        f"{record.get('units_failed')} failed")
            consolidated = sources.get(CONSOLIDATED_ID)
            if consolidated is None or consolidated.get("legal_status") != "non_binding":
                report.failures.append("G6 the consolidated text is missing or not marked non_binding")
        elif merged is False:
            for unit_id in changed[:5]:
                report.failures.append(f"G6 {unit_id} carries an Omnibus change while merged_into_base is False")
        else:
            report.failures.append(
                "G6 the amending instrument does not say whether it is merged into the base: "
                "silent replacement forbidden")
    report.stats["units_changed"] = len(changed)
    return report

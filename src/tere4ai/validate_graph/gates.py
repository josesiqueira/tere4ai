"""Critical validation gates: a build that fails these is not published.

@implements: DEC-10 (partial: structural gates; deep-extraction gates activate with M2 data)
@grounded_by: REF-27, REF-26, ADD-21

Architecture.md Section 13. Gates implemented here:
  G1 no orphan legal nodes (every Layer 1 node reachable from the Regulation)
  G2 no source-derived node without a frozen source file (span sha in build snapshots)
  G3 no norm without a source span
  G4 no accepted alignment without evidence spans on both sides
  G5 no recital treated as binding (recitals never norm sources, never point parents)
  G6 no proposed amendment silently replacing the in-force source (version pin intact)

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
REACHABILITY_EDGES = HIERARCHY_EDGES | {"DEFINES_TERM"}


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

    # G6: version pin intact (base in force; amendment distinct and marked)
    sources = {n["id"]: n for n in dump["nodes"] if n.get("type") == "SourceDocument"}
    base = sources.get("src:eu-ai-act:oj-2024-07-12")
    omnibus = sources.get("src:omnibus-com-2025-836")
    if base is None or base.get("legal_status") != "in_force":
        report.failures.append("G6 base act missing or not marked in_force")
    if omnibus is not None:
        if omnibus.get("legal_status") == "in_force":
            report.failures.append(
                "G6 amending instrument marked in_force: silent replacement forbidden"
            )
        amends = any(
            e["edge_type"] == "AMENDS" and e["from"] == omnibus["id"] for e in edges
        )
        if not amends:
            report.failures.append("G6 amending instrument without an AMENDS edge")

    return report

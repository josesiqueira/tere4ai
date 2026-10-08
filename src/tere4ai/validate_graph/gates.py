"""Critical validation gates: a build that fails these is not published.

@implements: DEC-10 (partial: structural gates; deep-extraction gates activate with MILESTONE2 data)
@implements: DEC-23
@implements: DEC-25
@grounded_by: REF-27, REF-26, ADD-21

Architecture.md Section 13. Gates implemented here:
  PUBLICATION_GATE1 no orphan legal nodes (every Layer 1 node reachable from the Regulation)
  PUBLICATION_GATE2 no source-derived node without a frozen source file (span sha in build snapshots)
  PUBLICATION_GATE3 no norm without a source span
  PUBLICATION_GATE4 no accepted alignment without evidence spans on both sides
  PUBLICATION_GATE5 no recital treated as binding (recitals never norm sources, never point parents)
  PUBLICATION_GATE6 no amendment silently replacing the in-force source: the Omnibus is either kept
                    apart (merged_into_base False, no unit changed) or merged with every marker read
                    and checked and every unit checked (spec G D-G68); a dump that reads as amended
                    without the Omnibus SourceDocument is refused
  PUBLICATION_GATE2 also refuses a span id carried by an in-force node and an earlier version (B132)
  PUBLICATION_GATE3 and PUBLICATION_GATE4 also refuse a norm, and an alignment of a norm, whose source unit the
                    Omnibus deleted; deleted_unit_citations refuses a test-set item that cites
                    one (B132, spec G D-G68 (3))
  PUBLICATION_GATE2 also checks, at publication with alignments, the HLEG requirement and subtopic
                    nodes: the derived text and record they were built from are the ones Layer 0
                    lists and the alignments name, and every HLEG span cites the derived text as
                    Layer 0 lists it (hleg_failures; spec G D-G75 (8))

validate_build returns a report; the build entry point refuses to publish on
failure (no silent degradation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tere4ai.parse_legal_structure.amendments import OMNIBUS_ACT, is_deleted

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

# Edges that make a Layer 1 node reachable for the orphan gate (PUBLICATION_GATE1). Beyond
# the hierarchy, a Definition node hangs off its defining Article 3 point via
# DEFINES_TERM (a containment edge, kept out of HIERARCHY_EDGES so the PUBLICATION_GATE5
# recital rule stays strict). CONTEXT_FOR is deliberately NOT here: it is a
# context edge, never hierarchy, so recitals remain reachable only via
# HAS_RECITAL (recitals are context only, architecture.md Section 1).
# HAS_CROSS_REFERENCE is likewise containment: a reified CrossReference
# node belongs to the paragraph whose text carries the citation (#44).
# HAS_VERSION links a changed unit to its 2024 wording (B132, D-G68 (3)).
REACHABILITY_EDGES = HIERARCHY_EDGES | {"DEFINES_TERM", "HAS_CROSS_REFERENCE", "HAS_VERSION"}
UNIT_TYPES = ("Chapter", "Section", "Article", "Paragraph", "Subparagraph", "Point", "Annex", "AnnexItem")
CONSOLIDATED_ID = "src:eu-ai-act:consolidated-2026-07-27"


def _norm_unit(norm_id: object) -> str | None:
    """The source unit a norm id names: norm:<unit id>:n<k> -> <unit id>."""
    if not isinstance(norm_id, str) or not norm_id.startswith("norm:") or ":" not in norm_id[5:]:
        return None
    return norm_id[len("norm:"):].rsplit(":", 1)[0]


def deleted_unit_citations(dump: dict, items: list[dict]) -> list[str]:
    """One line per hand-made test-set item that cites a unit the Omnibus
    deleted (B132, D-G68 (3)): in gold_citations, or as a node id among the
    gold answer's values. The answer key is corrected to the unit that now
    holds the rule, never served on a deleted unit."""
    deleted = {n["id"] for n in dump.get("nodes", []) if is_deleted(n)}
    failures: list[str] = []
    for item in items:
        gold = item.get("gold") if isinstance(item.get("gold"), dict) else {}
        cited = [*item.get("gold_citations", []), *(v for v in gold.values() if isinstance(v, str))]
        for node_id in dict.fromkeys(cited):
            if node_id in deleted:
                failures.append(f"test-set item {item.get('id')} cites a unit the Omnibus deleted: {node_id}")
    return failures


@dataclass
class ValidationReport:
    failures: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failures


def hleg_failures(dump: dict, alignments_build: dict, pair: Any, requirement_nodes: list[dict],
                  subtopic_nodes: list[dict]) -> list[str]:
    """Spec G D-G75 (8), reported under PUBLICATION_GATE2: the HLEG pair the targets were built from
    is the one Layer 0 lists (the files the parse's checks passed) and the one the
    alignments name, and every HLEG span cites the derived text as Layer 0 lists it."""
    from tere4ai.align_hleg.hleg_source import listed_pair
    from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE

    failures: list[str] = []
    listed = listed_pair(dump)
    for name, sha in ((TEXT_FILE, pair.text_sha256), (RECORD_FILE, pair.record_sha256)):
        if name not in listed:
            failures.append(f"PUBLICATION_GATE2 Layer 0 does not list {name}: the parse of this build did not check that HLEG text")
        elif listed[name] != sha:
            failures.append(f"PUBLICATION_GATE2 Layer 0 lists {name} with sha256 {listed[name]}, the frozen file is {sha}")
    for key, name, sha in (("hleg_text_sha256", TEXT_FILE, pair.text_sha256),
                           ("hleg_derivation_record_sha256", RECORD_FILE, pair.record_sha256)):
        made_on = alignments_build.get(key)
        if made_on is None:
            failures.append(f"PUBLICATION_GATE2 the alignments name no {key}: they were made before spec G D-G75; run the alignment "
                            "command again")
        elif made_on != sha:
            failures.append(f"PUBLICATION_GATE2 the alignments were made on {name} {made_on}, the frozen file is {sha}")
    for node in [*requirement_nodes, *subtopic_nodes]:
        span = node.get("source_span") or {}
        if span.get("snapshot_file") != TEXT_FILE or span.get("snapshot_sha256") != listed.get(TEXT_FILE):
            failures.append(f"PUBLICATION_GATE2 node {node.get('id')} cites {span.get('snapshot_file')} {span.get('snapshot_sha256')}, "
                            "not the derived text Layer 0 lists")
    return failures


def validate_build(
    dump: dict,
    norms: list[dict] | None = None,
    alignments: list[dict] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    nodes = {n["id"]: n for n in dump["nodes"]}
    edges = dump["edges"]

    # PUBLICATION_GATE1: reachability from the Regulation root over hierarchy edges
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
        report.failures.append(f"PUBLICATION_GATE1 orphan legal node: {orphan}")
    if len(orphans) > 20:
        report.failures.append(f"PUBLICATION_GATE1 plus {len(orphans) - 20} more orphans")
    report.stats["layer1_nodes"] = len(layer1_ids)
    report.stats["orphans"] = len(orphans)

    # PUBLICATION_GATE2: every source span cites a snapshot listed in the build
    build_shas = {s["sha256"] for s in dump["build"]["snapshots"]}
    bad_span = 0
    for n in dump["nodes"]:
        span = n.get("source_span")
        if span and span["snapshot_sha256"] not in build_shas:
            bad_span += 1
            if bad_span <= 5:
                report.failures.append(
                    f"PUBLICATION_GATE2 node {n['id']} cites a snapshot not in the build inputs"
                )
    report.stats["nodes_with_unlisted_snapshot"] = bad_span
    # PUBLICATION_GATE2, span ids: an earlier version's span never shares an id with an
    # in-force span, because span lookup returns the first match (B132).
    version_spans = {n["source_span"]["span_id"] for n in dump["nodes"]
                     if n.get("type") == "UnitVersion" and n.get("source_span")}
    in_force_spans = {n["source_span"]["span_id"] for n in dump["nodes"]
                      if n.get("type") != "UnitVersion" and n.get("source_span")}
    for span_id in sorted(version_spans & in_force_spans)[:5]:
        report.failures.append(f"PUBLICATION_GATE2 span id {span_id} is carried by an in-force node and a version node")

    # PUBLICATION_GATE3: no norm without a source span
    recital_ids = {i for i, n in nodes.items() if n.get("type") == "Recital"}
    deleted_ids = {i for i, n in nodes.items() if is_deleted(n)}
    for norm in norms or []:
        if not norm.get("source_span_id"):
            report.failures.append(f"PUBLICATION_GATE3 norm without source span: {norm.get('norm_id')}")
        # B132 (D-G68 (3)): a deleted unit has no span of its own; nothing stands on it.
        if norm.get("source_node_id") in deleted_ids:
            report.failures.append(
                f"PUBLICATION_GATE3 norm on a unit the Omnibus deleted: {norm.get('norm_id')} ({norm.get('source_node_id')})")
        # PUBLICATION_GATE5 half: norms never derive from recitals
        if norm.get("source_node_id") in recital_ids:
            report.failures.append(
                f"PUBLICATION_GATE5 norm derived from a recital: {norm.get('norm_id')}"
            )
    report.stats["norms_checked"] = len(norms or [])

    # PUBLICATION_GATE4: accepted alignments need evidence spans on both sides
    for a in alignments or []:
        if _norm_unit(a.get("source_norm_id")) in deleted_ids:
            report.failures.append(f"PUBLICATION_GATE4 alignment of a norm on a unit the Omnibus deleted: {a.get('id')}")
        if a.get("judge_verdict") == "accepted" or a.get("review_status") == "accepted":
            if not a.get("source_evidence_span_ids") or not a.get("target_evidence_span_ids"):
                report.failures.append(
                    f"PUBLICATION_GATE4 accepted alignment without two-sided evidence: {a.get('id')}"
                )
    report.stats["alignments_checked"] = len(alignments or [])

    # PUBLICATION_GATE5 other half: recitals never own operative children
    for e in edges:
        if e["from"] in recital_ids and e["edge_type"] in HIERARCHY_EDGES - {"HAS_RECITAL"}:
            report.failures.append(f"PUBLICATION_GATE5 recital with operative child: {e['edge_id']}")

    # PUBLICATION_GATE6: no silent replacement. Since B132 the Omnibus is merged into the
    # base text: Layer 1 is the Act as amended. The checks themselves run in
    # the parse (consolidated.build_in_force_dump raises on any failure); PUBLICATION_GATE6
    # verifies their record on the dump (every marker read and checked, every
    # unit checked, the reviewed marker list's digest equal on the Omnibus
    # SourceDocument and in the build), so a dump whose record is missing or
    # edited is refused. Kept apart (merged_into_base False), no unit may
    # carry a change.
    sources = {n["id"]: n for n in dump["nodes"] if n.get("type") == "SourceDocument"}
    base = sources.get("src:eu-ai-act:oj-2024-07-12")
    omnibus = sources.get("src:omnibus-com-2025-836")
    if base is None or base.get("legal_status") != "in_force":
        report.failures.append("PUBLICATION_GATE6 base act missing or not marked in_force")
    changed = [i for i, n in nodes.items() if n.get("amendment") not in (None, "unchanged")]
    # A dump that reads as amended (a unit with an amendment field, an earlier
    # version, wording enacted by the Omnibus) needs the Omnibus SourceDocument
    # and the build's record of the checks (final review F5).
    amended = any(n.get("amendment") is not None or n.get("type") == "UnitVersion"
                  or OMNIBUS_ACT in str(n.get("enacted_by") or "") for n in dump["nodes"])
    if omnibus is None and amended:
        report.failures.append(
            "PUBLICATION_GATE6 the dump holds amended units but no Omnibus SourceDocument: silent replacement forbidden")
        if not dump["build"].get("amendments"):
            report.failures.append("PUBLICATION_GATE6 the dump holds amended units but the build records no amendment checks")
    if omnibus is not None:
        if not any(e["edge_type"] == "AMENDS" and e["from"] == omnibus["id"] for e in edges):
            report.failures.append("PUBLICATION_GATE6 amending instrument without an AMENDS edge")
        merged = omnibus.get("merged_into_base")
        if merged is True:
            record = dump["build"].get("amendments") or {}
            units = sum(1 for n in dump["nodes"] if n.get("type") in UNIT_TYPES)
            if not record:
                report.failures.append(
                    "PUBLICATION_GATE6 the Omnibus is merged but the build records no amendment checks: "
                    "silent replacement forbidden")
            else:
                if record.get("marker_list_sha256") != omnibus.get("marker_list_sha256"):
                    report.failures.append("PUBLICATION_GATE6 the build's marker list is not the one the Omnibus SourceDocument names")
                if not record.get("markers_read") or record.get("markers_checked") != record.get("markers_read"):
                    report.failures.append("PUBLICATION_GATE6 not every change marker was read and checked")
                if record.get("units_failed") != 0 or record.get("units_checked") != units:
                    report.failures.append(
                        f"PUBLICATION_GATE6 {record.get('units_checked')} units checked of {units} in the dump, "
                        f"{record.get('units_failed')} failed")
            consolidated = sources.get(CONSOLIDATED_ID)
            if consolidated is None or consolidated.get("legal_status") != "non_binding":
                report.failures.append("PUBLICATION_GATE6 the consolidated text is missing or not marked non_binding")
        elif merged is False:
            for unit_id in changed[:5]:
                report.failures.append(f"PUBLICATION_GATE6 {unit_id} carries an Omnibus change while merged_into_base is False")
        else:
            report.failures.append(
                "PUBLICATION_GATE6 the amending instrument does not say whether it is merged into the base: "
                "silent replacement forbidden")
    report.stats["units_changed"] = len(changed)
    return report

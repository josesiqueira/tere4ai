"""Post-load Neo4j validation gates for Layer 2/3 (what landed in the DB).

@implements: DEC-10 (partial: post-load database gates for Layer 2/3)
@grounded_by: REF-27, ADD-21

Engineering MUST (architecture.md Section 13: no silent degradation). The
pre-publication gates (validate_graph/gates.py) check the dump; these gates
check the database AFTER GraphStore.load_dump, so a partial or failed load
cannot masquerade as a published build. All checks are read-only Cypher run
through the same driver, in the spirit of SHACL shape validation (ADD-21)
expressed as property-graph queries.

Checks (each returns a violation count; 0 everywhere means PASS):
  P1 norm count in DB equals the norms in the published payload
  P2 assertion count in DB equals the assertions in the payload
  P3 no judge-accepted NormativeStatement without a source_span_id
  P4 no judge-accepted AlignmentAssertion missing evidence span ids on
     either side
  P5 no DERIVED_FROM or ASSERTS_ALIGNMENT_* edge carrying a build_id other
     than the one just published (stale-build residue detection)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# One entry per check: (name, cypher, kind). Count queries return `n`;
# violation queries return `violations`. Labels and relationship types are
# fixed literals from the schema, never interpolated from input.
_COUNT_NORMS = "MATCH (n:NormativeStatement) RETURN count(n) AS n"
_COUNT_ASSERTIONS = "MATCH (a:AlignmentAssertion) RETURN count(a) AS n"
_ACCEPTED_NORM_NO_SPAN = (
    "MATCH (n:NormativeStatement) "
    "WHERE n.judge_verdict = 'accepted' AND n.source_span_id IS NULL "
    "RETURN count(n) AS violations"
)
_ACCEPTED_ASSERTION_NO_EVIDENCE = (
    "MATCH (a:AlignmentAssertion) "
    "WHERE a.judge_verdict = 'accepted' "
    "AND (coalesce(size(a.source_evidence_span_ids), 0) = 0 "
    "OR coalesce(size(a.target_evidence_span_ids), 0) = 0) "
    "RETURN count(a) AS violations"
)
_STALE_BUILD_EDGES = (
    "MATCH ()-[r]->() "
    "WHERE type(r) IN ['DERIVED_FROM', 'ASSERTS_ALIGNMENT_OF', 'ASSERTS_ALIGNMENT_TO'] "
    "AND r.build_id <> $build_id "
    "RETURN count(r) AS violations"
)


@dataclass
class PostLoadReport:
    passed: bool
    stats: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)


def _scalar(session: Any, query: str, **params: Any) -> int:
    record = session.run(query, params).single()
    return int(record[0]) if record else 0


def validate_postload(
    driver: Any,
    build_id: str,
    expected_norms: int,
    expected_assertions: int | None = None,
) -> PostLoadReport:
    """Run the P1..P5 database gates; see the module docstring."""
    failures: list[str] = []
    stats: dict[str, int] = {}
    with driver.session() as session:
        db_norms = _scalar(session, _COUNT_NORMS)
        stats["db_norms"] = db_norms
        if db_norms != expected_norms:
            failures.append(
                f"P1 norm count mismatch: db has {db_norms}, payload had {expected_norms}"
            )

        if expected_assertions is not None:
            db_assertions = _scalar(session, _COUNT_ASSERTIONS)
            stats["db_assertions"] = db_assertions
            if db_assertions != expected_assertions:
                failures.append(
                    "P2 assertion count mismatch: db has "
                    f"{db_assertions}, payload had {expected_assertions}"
                )

        no_span = _scalar(session, _ACCEPTED_NORM_NO_SPAN)
        stats["accepted_norms_without_span"] = no_span
        if no_span:
            failures.append(f"P3 {no_span} accepted norms lack source_span_id")

        no_evidence = _scalar(session, _ACCEPTED_ASSERTION_NO_EVIDENCE)
        stats["accepted_assertions_without_evidence"] = no_evidence
        if no_evidence:
            failures.append(
                f"P4 {no_evidence} accepted assertions lack evidence spans on a side"
            )

        stale = _scalar(session, _STALE_BUILD_EDGES, build_id=build_id)
        stats["stale_build_edges"] = stale
        if stale:
            failures.append(
                f"P5 {stale} Layer 2/3 edges carry a build_id other than {build_id}"
            )

    return PostLoadReport(passed=not failures, stats=stats, failures=failures)

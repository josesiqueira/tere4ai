"""Neo4j graph store loader for the Layer 0+1 dump.

Loads the versioned build artifact (schema/json_schemas/layer1_dump.schema.json)
into Neo4j idempotently: nodes are MERGEd on their id property with the node
type as the label, edges are MERGEd on edge_id with the edge_type as the
relationship type and all provenance fields as relationship properties.

@implements: DEC-09 (partial: Neo4j store; RDF export via n10s deferred to a later milestone)
@grounded_by: REF-21, REF-22, REF-08, REF-23
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

# Labels and relationship types allowed in the Layer 0+1 dump. Kept in sync
# with schema/json_schemas/nodes.schema.json and edges.schema.json. Because
# Cypher cannot parameterise labels or relationship types, values are checked
# against these sets (and a strict identifier pattern) before interpolation.
NODE_LABELS = frozenset(
    {
        "SourceDocument",
        "SourceFile",
        "BuildRun",
        "Regulation",
        "Chapter",
        "Section",
        "Article",
        "Paragraph",
        "Subparagraph",
        "Point",
        "Recital",
        "Annex",
        "AnnexItem",
        "Definition",
        "CrossReference",
        "NormativeStatement",
        "HLEGRequirement",
        "HLEGRequirementSubtopic",
        "AlignmentAssertion",
        "MappingRun",
        "JudgeRun",
    }
)

EDGE_TYPES = frozenset(
    {
        "HAS_CHAPTER",
        "HAS_SECTION",
        "HAS_ARTICLE",
        "HAS_PARAGRAPH",
        "HAS_SUBPARAGRAPH",
        "HAS_POINT",
        "HAS_RECITAL",
        "HAS_ANNEX",
        "HAS_ANNEX_ITEM",
        "DEFINES_TERM",
        "CONTEXT_FOR",
        "HAS_SUBTOPIC",
        "REFERS_TO",
        "HAS_CROSS_REFERENCE",
        "RESOLVES_TO",
        "AMENDS",
        "HAS_VERSION",
        "DERIVED_FROM_SOURCE",
        "DERIVED_FROM",
        "ASSERTS_ALIGNMENT_OF",
        "ASSERTS_ALIGNMENT_TO",
        "PRODUCED_BY_MAPPING_RUN",
        "JUDGED_BY",
    }
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

DEFAULT_CONSTRAINTS_PATH = (
    Path(__file__).resolve().parents[3] / "schema" / "cypher_constraints" / "constraints.cypher"
)


def _checked_identifier(value: str, allowed: frozenset[str], kind: str) -> str:
    """Return value if it is a known, syntactically safe Cypher identifier."""
    if value not in allowed or not _SAFE_IDENTIFIER.match(value):
        raise ValueError(f"unknown or unsafe {kind}: {value!r}")
    return value


def flatten_node_properties(node: dict[str, Any]) -> dict[str, Any]:
    """Flatten a node dict to scalar Neo4j properties.

    The nested source_span object becomes span_* properties (span_id,
    span_snapshot_file, span_snapshot_sha256, span_start, span_end,
    span_anchor). All other schema properties pass through unchanged.
    """
    props: dict[str, Any] = {}
    for key, value in node.items():
        if key == "source_span" and isinstance(value, dict):
            for span_key, span_value in value.items():
                flat_key = span_key if span_key.startswith("span_") else f"span_{span_key}"
                props[flat_key] = span_value
        else:
            props[key] = value
    return props


def flatten_edge_properties(edge: dict[str, Any]) -> dict[str, Any]:
    """All provenance properties of the edge, minus the endpoint pointers."""
    return {k: v for k, v in edge.items() if k not in ("from", "to")}


class GraphStore:
    """Idempotent loader for the Layer 0+1 dump into Neo4j."""

    def load_dump(self, dump: dict[str, Any], driver: Any) -> dict[str, int]:
        """Write all nodes and edges of the dump via the given neo4j driver.

        Idempotent: nodes MERGE on id, edges MERGE on edge_id, so re-loading
        the same dump does not duplicate anything. Returns a summary of node
        and edge counts submitted per label and relationship type.
        """
        nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in dump.get("nodes", []):
            nodes_by_type[node["type"]].append(node)

        edges_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in dump.get("edges", []):
            edges_by_type[edge["edge_type"]].append(edge)

        summary: dict[str, int] = {}
        with driver.session() as session:
            for node_type, nodes in nodes_by_type.items():
                label = _checked_identifier(node_type, NODE_LABELS, "node label")
                rows = [{"id": n["id"], "props": flatten_node_properties(n)} for n in nodes]
                query = (
                    f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row.props"
                )
                session.run(query, {"rows": rows})
                summary[f"node:{label}"] = len(rows)

            for edge_type, edges in edges_by_type.items():
                rel = _checked_identifier(edge_type, EDGE_TYPES, "edge type")
                rows = [
                    {
                        "edge_id": e["edge_id"],
                        "from_id": e["from"],
                        "to_id": e["to"],
                        "props": flatten_edge_properties(e),
                    }
                    for e in edges
                ]
                query = (
                    "UNWIND $rows AS row "
                    "MATCH (a {id: row.from_id}) "
                    "MATCH (b {id: row.to_id}) "
                    f"MERGE (a)-[r:{rel} {{edge_id: row.edge_id}}]->(b) "
                    "SET r += row.props"
                )
                session.run(query, {"rows": rows})
                summary[f"edge:{rel}"] = len(rows)

        return summary

    def apply_constraints(
        self, driver: Any, constraints_path: Path | str = DEFAULT_CONSTRAINTS_PATH
    ) -> dict[str, int]:
        """Apply the uniqueness and type constraints from constraints.cypher.

        The file format is one full statement per line, comment lines start
        with //, blank lines separate statements.

        Property TYPE constraints (IS :: INTEGER / STRING) require Neo4j
        Enterprise; on Community they fail with ConstraintCreationFailed and
        are skipped with a count, never silently: property types are already
        enforced upstream by the JSON schemas and Pydantic (architecture.md
        Section 5). Uniqueness constraints failing is a hard error.
        Returns {"applied": n, "skipped_enterprise_only": m}.
        """
        statements = parse_constraint_statements(Path(constraints_path).read_text())
        applied = 0
        skipped = 0
        with driver.session() as session:
            for statement in statements:
                try:
                    session.run(statement)
                    applied += 1
                except Exception as exc:  # neo4j DatabaseError on community
                    if " IS :: " in statement and "ConstraintCreationFailed" in str(exc):
                        skipped += 1
                    else:
                        raise
        return {"applied": applied, "skipped_enterprise_only": skipped}


def parse_constraint_statements(text: str) -> list[str]:
    """Extract executable single-line statements from constraints.cypher."""
    statements: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        statements.append(stripped.rstrip(";"))
    return statements

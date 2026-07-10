"""RDF export of the published graph via neosemantics (n10s).

@implements: DEC-09 (partial: RDF export bridge; AIRO/TAIR OWL alignment stays deferred)
@grounded_by: REF-23, REF-21, REF-25

Architecture.md Section 5 (OVR-8): Neo4j stays the operational store; RDF is
the interoperability artifact for legal-informatics tooling and the future
AIRO alignment (REF-25). Export goes through n10s.rdf.export.cypher, which
streams (subject, predicate, object) rows for any read-only Cypher query;
this module serializes those rows as N-Triples, the simplest lossless
line-oriented RDF syntax, so a reviewer can diff exports across builds.

The default export covers the judged Layer 2/3 subgraph (NormativeStatement,
AlignmentAssertion, HLEGRequirement and their edges): the reified assertion
nodes are exactly the part that ports cleanly to RDF (REF-21).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Read-only by construction: n10s.rdf.export.cypher runs the query and maps
# the result graph to triples; it cannot write. Labels are fixed literals.
DEFAULT_EXPORT_QUERY = (
    "MATCH (n) WHERE n:NormativeStatement OR n:AlignmentAssertion "
    "OR n:HLEGRequirement OR n:HLEGRequirementSubtopic "
    "OPTIONAL MATCH (n)-[r]-(m) "
    "RETURN n, r, m"
)


def _escape_literal(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _object_term(row: dict[str, Any]) -> str:
    if row.get("isLiteral"):
        literal = f'"{_escape_literal(str(row["object"]))}"'
        literal_type = row.get("literalType")
        lang = row.get("literalLang")
        if lang:
            return f"{literal}@{lang}"
        if literal_type and not str(literal_type).endswith("#string"):
            return f"{literal}^^<{literal_type}>"
        return literal
    return f"<{row['object']}>"


STATEMENT_NS = "neo4j://graph.statements#"


def _statement_iri(s: str, p: str, o: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{s} {p} {o}".encode()).hexdigest()[:20]
    return f"{STATEMENT_NS}{digest}"


_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def row_to_ntriples(row: dict[str, Any], reified_seen: set[str]) -> list[str]:
    """Serialize one n10s export row as standard N-Triples lines.

    n10s emits relationship properties as RDF-star quoted triples (the
    subject field arrives as "s p o" with spaces). Plain N-Triples has no
    quoted triples, so those rows are mapped to standard RDF reification
    (REF-21: edge-native properties port to RDF via reification): one
    rdf:Statement per distinct edge, then the property on that statement.
    """
    subject_raw = str(row["subject"])
    obj = _object_term(row)
    predicate = f"<{row['predicate']}>"

    if not subject_raw.startswith("<<"):
        return [f"<{subject_raw}> {predicate} {obj} ."]

    # RDF-star quoted-triple subject as the driver delivers it:
    # "<<iri iri iri>>" (double-angle wrapper, space-separated bare IRIs).
    inner = subject_raw[2:-2] if subject_raw.endswith(">>") else subject_raw[2:]
    parts = inner.split(" ")
    if len(parts) != 3:
        raise ValueError(f"unparseable quoted-triple subject: {subject_raw!r}")
    s, p, o = parts
    stmt = _statement_iri(s, p, o)
    lines: list[str] = []
    if stmt not in reified_seen:
        reified_seen.add(stmt)
        lines += [
            f"<{stmt}> <{_RDF}type> <{_RDF}Statement> .",
            f"<{stmt}> <{_RDF}subject> <{s}> .",
            f"<{stmt}> <{_RDF}predicate> <{p}> .",
            f"<{stmt}> <{_RDF}object> <{o}> .",
        ]
    lines.append(f"<{stmt}> {predicate} {obj} .")
    return lines


def ensure_graphconfig(driver: Any) -> bool:
    """Initialise the n10s graph config once; True if newly initialised.

    handleVocabUris IGNORE maps properties and labels to the neo4j://
    default namespace without prefix bookkeeping, which is right for an
    export-only bridge (imports would want stricter handling).
    """
    with driver.session() as session:
        existing = session.run("CALL n10s.graphconfig.show()").data()
        if existing:
            return False
        session.run("CALL n10s.graphconfig.init({handleVocabUris: 'IGNORE'})")
        return True


def export_ntriples(
    driver: Any,
    out_path: Path | str,
    query: str = DEFAULT_EXPORT_QUERY,
) -> int:
    """Stream the query's subgraph as N-Triples to out_path; returns count."""
    ensure_graphconfig(driver)
    count = 0
    reified_seen: set[str] = set()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with driver.session() as session, out.open("w", encoding="utf-8") as fh:
        result = session.run(
            "CALL n10s.rdf.export.cypher($query, {}) "
            "YIELD subject, predicate, object, isLiteral, literalType, literalLang "
            "RETURN subject, predicate, object, isLiteral, literalType, literalLang",
            {"query": query},
        )
        for record in result:
            for line in row_to_ntriples(record.data(), reified_seen):
                fh.write(line + "\n")
                count += 1
    return count

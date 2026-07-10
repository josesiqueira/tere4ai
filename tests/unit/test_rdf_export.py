"""N-Triples serialization tests for the RDF export bridge (DEC-09)."""

from __future__ import annotations

from tere4ai.graph_store.rdf_export import row_to_ntriples


def row_to_ntriple(row):
    lines = row_to_ntriples(row, set())
    assert len(lines) == 1
    return lines[0]


def test_iri_object():
    row = {
        "subject": "neo4j://graph.individuals#1",
        "predicate": "neo4j://graph.schema#DERIVED_FROM",
        "object": "neo4j://graph.individuals#2",
        "isLiteral": False,
    }
    assert row_to_ntriple(row) == (
        "<neo4j://graph.individuals#1> <neo4j://graph.schema#DERIVED_FROM> "
        "<neo4j://graph.individuals#2> ."
    )


def test_plain_string_literal_has_no_datatype_suffix():
    row = {
        "subject": "neo4j://graph.individuals#1",
        "predicate": "neo4j://graph.schema#action",
        "object": "establish a risk management system",
        "isLiteral": True,
        "literalType": "http://www.w3.org/2001/XMLSchema#string",
        "literalLang": None,
    }
    line = row_to_ntriple(row)
    assert line.endswith('"establish a risk management system" .')
    assert "^^" not in line


def test_typed_literal_keeps_datatype():
    row = {
        "subject": "neo4j://graph.individuals#1",
        "predicate": "neo4j://graph.schema#confidence",
        "object": "0.9",
        "isLiteral": True,
        "literalType": "http://www.w3.org/2001/XMLSchema#double",
        "literalLang": None,
    }
    assert '"0.9"^^<http://www.w3.org/2001/XMLSchema#double>' in row_to_ntriple(row)


def test_literal_escaping():
    row = {
        "subject": "s:1",
        "predicate": "p:1",
        "object": 'quote " backslash \\ newline \n end',
        "isLiteral": True,
        "literalType": None,
        "literalLang": None,
    }
    line = row_to_ntriple(row)
    assert '\\"' in line and "\\\\" in line and "\\n" in line
    assert "\n" not in line.rstrip("\n")


def test_language_tagged_literal():
    row = {
        "subject": "s:1",
        "predicate": "p:1",
        "object": "hello",
        "isLiteral": True,
        "literalType": None,
        "literalLang": "en",
    }
    assert row_to_ntriple(row).endswith('"hello"@en .')


def test_edge_property_row_becomes_standard_reification():
    row = {
        "subject": "<<neo4j://i#1 neo4j://s#JUDGED_BY neo4j://i#2>>",
        "predicate": "neo4j://s#provenance_class",
        "object": "LLM_JUDGED_ACCEPTED",
        "isLiteral": True,
        "literalType": None,
        "literalLang": None,
    }
    seen = set()
    lines = row_to_ntriples(row, seen)
    assert len(lines) == 5
    assert any("rdf-syntax-ns#Statement" in x for x in lines)
    assert all("<<" not in x for x in lines)
    row2 = dict(row, predicate="neo4j://s#confidence", object="0.9")
    assert len(row_to_ntriples(row2, seen)) == 1

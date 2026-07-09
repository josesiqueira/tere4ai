## Cypher / Neo4j Rules
- Never break node labels, relationship types, or property names across lines.
- Always output Cypher queries as copyable single-line strings or use line breaks ONLY at safe points (after clauses like MATCH, WHERE, RETURN, ORDER BY).
- Safe line break example:
```
  MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
  RETURN a.title
```
- NEVER break inside a label like `HLEG\nRequirement` or a relationship like `ALIGNS_WITH_HLEG_\nREQUIREMENT`.
- Never print Cypher queries to the terminal. Always write them to `_queries.cypher` (underscore prefix), with each query separated by a blank line and preceded by a comment explaining what it does.
- `_queries.cypher` is in .gitignore — never remove that entry.

## Neo4j Graph Schema & Property Types
```
(Regulation {document_id: str})
  -[:HAS_RECITAL]-> (Recital {number: int, text: str})
  -[:HAS_CHAPTER]-> (Chapter {number: str, title: str})        // 'I', 'II', 'III' (Roman numerals)
    -[:HAS_SECTION]-> (Section {number: int, title: str})       // 1, 2, 3
      -[:HAS_ARTICLE]-> (Article {number: int, title: str})     // 9, 10, 15
    -[:HAS_ARTICLE]-> (Article)                                 // chapters without sections
      -[:HAS_PARAGRAPH]-> (Paragraph {index: int, text: str})
        -[:HAS_POINT]-> (Point {marker: str, text: str})
        -[:ALIGNS_WITH_HLEG_REQUIREMENT {relevance: float, rationale: str}]-> (HLEGRequirement)
  -[:HAS_ANNEX]-> (Annex {number: str, title: str, raw_text: str})

(HLEG)
  -[:HAS_REQUIREMENT]-> (HLEGRequirement {id: str, order: int, name: str, description: str, full_text: str})
    -[:HAS_SUBTOPIC]-> (HLEGRequirementSubtopic {id: str, label: str, description: str})
```

CRITICAL property types (these cause silent query failures if wrong):
- Chapter.number = STRING ('I', 'III', 'XIII')
- Section.number = INTEGER (1, 2, 3, 4, 5)
- Article.number = INTEGER (1-113)
- Recital.number = INTEGER (1-180)

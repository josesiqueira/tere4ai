"""
Deterministic Neo4j Ingestion for AI HLEG Requirements

This module takes a HlegStructuredDoc (output from agent_hleg_preprocess.py)
and writes it to Neo4j.

Key principles:
  - NO LLM calls here - all data comes from HlegStructuredDoc.
  - Deterministic and idempotent:
      * Uses MERGE for HLEG document node, requirement nodes,
        and requirement subtopic nodes.
      * MERGE for relationships to avoid duplicates.
  - Simple, explicit graph schema:

      (h:HLEG {document_id})
        -[:HAS_REQUIREMENT]->
      (r:HLEGRequirement {id})
        -[:HAS_SUBTOPIC]->
      (s:HLEGRequirementSubtopic {id})

This mirrors the deterministic ingestion pattern used for the EU AI Act.
"""

from typing import List

from neo4j import Driver
from models.ai_hleg import (
    HlegStructuredDoc,
    HlegRequirement,
    HlegRequirementSubtopic,
)
from config.neo4j_config import get_neo4j_driver


def ingest_hleg_document(doc: HlegStructuredDoc) -> None:
    """
    Ingest a HlegStructuredDoc into Neo4j in a deterministic way.

    Graph schema:

      - (h:HLEG {document_id})
          * h.official_title
          * h.short_title
          * h.year

      - (r:HLEGRequirement {id})
          * r.order
          * r.name
          * r.short_description
          * r.full_text
          * r.related_principles (array)
          * r.tags (array)

      - (s:HLEGRequirementSubtopic {id})
          * s.label
          * s.description

      - (h)-[:HAS_REQUIREMENT]->(r)
      - (r)-[:HAS_SUBTOPIC]->(s)

    Args:
        doc: The HlegStructuredDoc produced by the preprocessing agent.
    """
    with get_neo4j_driver() as driver:
        _create_hleg_document_and_requirements(driver, doc)

    print(f"✓ Ingested HLEG document '{doc.document_id}' to Neo4j")
    print(f"  - Requirements: {len(doc.requirements)}")


def _create_hleg_document_and_requirements(driver: Driver, doc: HlegStructuredDoc) -> None:
    """
    Create or merge the HLEG document node, its requirements, and subtopics.
    """
    # Step 1: Create/merge HLEG document node
    cypher_doc = """
    MERGE (h:HLEG {document_id: $document_id})
    SET h.official_title = $official_title,
        h.short_title    = $short_title,
        h.year           = $year
    """
    driver.execute_query(
        cypher_doc,
        document_id=doc.document_id,
        official_title=doc.official_title,
        short_title=doc.short_title,
        year=doc.year,
    )

    # Step 2: Create/merge requirement nodes and :HAS_REQUIREMENT relationships
    #         plus RequirementSubtopics and :HAS_SUBTOPIC relationships.
    cypher_req = """
    MATCH (h:HLEG {document_id: $document_id})
    UNWIND $requirements AS req
    MERGE (r:HLEGRequirement {id: req.id})
    SET r.order             = req.order,
        r.name              = req.name,
        r.short_description = req.short_description,
        r.full_text         = req.full_text,
        r.related_principles = req.related_principles,
        r.tags               = req.tags
    MERGE (h)-[:HAS_REQUIREMENT]->(r)

    // Handle subtopics (if any) for this requirement
    FOREACH (sub IN req.subtopics |
      MERGE (s:HLEGRequirementSubtopic {id: sub.id})
      SET s.label       = sub.label,
          s.description = sub.description
      MERGE (r)-[:HAS_SUBTOPIC]->(s)
    )
    """

    requirements_data: List[dict] = []
    for r in doc.requirements:
        subtopics_data: List[dict] = [
            {
                "id": s.id,
                "label": s.label,
                "description": s.description,
            }
            for s in r.subtopics
        ]
        requirements_data.append(
            {
                "id": r.id,
                "order": r.order,
                "name": r.name,
                "short_description": r.short_description,
                "full_text": r.full_text,
                "related_principles": r.related_principles,
                "tags": r.tags,
                "subtopics": subtopics_data,
            }
        )

    driver.execute_query(
        cypher_req,
        document_id=doc.document_id,
        requirements=requirements_data,
    )

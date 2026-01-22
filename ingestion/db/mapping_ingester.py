"""
Deterministic Neo4j ingestion for EU→HLEG mappings.

This module takes a EuToHlegMapping (output from agent_eu_hleg_mapping.py)
and writes relationships from the relevant EU paragraph to HLEGRequirement
nodes.

Graph pattern (assumed):

  (d:Regulation {document_id: document_id})
    -[:HAS_CHAPTER]->(c:Chapter {number: chapter_number})
    -[:HAS_ARTICLE]->(a:Article {number: article_number})
    -[:HAS_PARAGRAPH]->(p:Paragraph {index: paragraph_index})

  (h:HLEGRequirement {id: hleg_requirement_id})

  (p)-[:ALIGNS_WITH_HLEG_REQUIREMENT {
        relevance,
        rationale,
        source,
        mapped_at
      }]->(h)

TRUSTWORTHINESS PRINCIPLES:

  - This module has NO LLM calls. It is deterministic.

  - It does not invent document structure; it assumes the EU AI Act
    and HLEG requirements have already been ingested using the
    structural pipelines.

  - MERGE is used for the relationship to avoid duplicates. Properties
    (relevance, rationale, source, mapped_at) can be updated on reruns.
"""

from typing import Optional

from neo4j import Driver
from config.neo4j_config import get_neo4j_driver
from models.eu_hleg_mapping import EuToHlegMapping, HlegLink


def ingest_eu_hleg_mapping(
    mapping: EuToHlegMapping,
    source: str = "eu_to_hleg_mapping_agent_v1",
) -> None:
    """
    Ingest a single EuToHlegMapping into Neo4j.

    If mapping.links is empty, nothing is written.

    Args:
        mapping: EuToHlegMapping instance from the mapping agent.
        source: Short string identifying the mapping pipeline version.
    """
    if not mapping.links:
        # Nothing to ingest for this paragraph
        return

    loc = mapping.location

    with get_neo4j_driver() as driver:
        for link in mapping.links:
            _create_alignment_relationship(
                driver=driver,
                document_id=loc.document_id,
                chapter_number=loc.chapter_number,
                article_number=loc.article_number,
                paragraph_index=loc.paragraph_index,
                link=link,
                source=source,
                paragraph_text=mapping.paragraph_text,
            )


def _create_alignment_relationship(
    driver: Driver,
    document_id: str,
    chapter_number: str,
    article_number: str,
    paragraph_index: int,
    link: HlegLink,
    source: str,
    paragraph_text: str,
) -> None:
    """
    Create or merge one ALIGNS_WITH_HLEG_REQUIREMENT relationship between
    a Paragraph and a HLEGRequirement.
    """
    # Handle both structures: Chapter->Article and Chapter->Section->Article
    cypher = """
    MATCH (d:Regulation {document_id: $document_id})
          -[:HAS_CHAPTER]->(c:Chapter {number: $chapter_number})
    MATCH (a:Article {number: $article_number})
          -[:HAS_PARAGRAPH]->(p:Paragraph {number: $paragraph_index})
    WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
    MATCH (h:HLEGRequirement {id: $hleg_requirement_id})
    MERGE (p)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h)
    SET r.relevance = $relevance,
        r.rationale = $rationale,
        r.source    = $source,
        r.mapped_at = datetime(),
        r.paragraph_text_snapshot = $paragraph_text
    """

    driver.execute_query(
        cypher,
        document_id=document_id,
        chapter_number=chapter_number,
        article_number=int(article_number),  # Convert to integer for Neo4j MATCH
        paragraph_index=paragraph_index,
        hleg_requirement_id=link.hleg_requirement_id,
        relevance=link.relevance,
        rationale=link.rationale,
        source=source,
        paragraph_text=paragraph_text,
    )

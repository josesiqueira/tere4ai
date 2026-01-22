"""
Deterministic Neo4j ingestion for EU→HLEG detailed mappings.

This module takes a EuToHlegDetailedMapping (output from agent_eu_hleg_mapping.py)
and writes relationships from the relevant EU paragraph to HLEGRequirement
and HLEGSubtopic nodes.

Graph patterns created:

  (p:Paragraph)-[:ALIGNS_WITH_HLEG_REQUIREMENT {
        relevance,
        rationale,
        source,
        mapped_at
      }]->(h:HLEGRequirement)

  (p:Paragraph)-[:ALIGNS_WITH_HLEG_SUBTOPIC {
        relevance,
        rationale,
        source,
        mapped_at
      }]->(s:HLEGSubtopic)

TRUSTWORTHINESS PRINCIPLES:

  - This module has NO LLM calls. It is deterministic.
  - MERGE is used for relationships to avoid duplicates.
  - Properties can be updated on reruns (idempotent).
  - Uses the regex Neo4j database (port 7688).
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from dotenv import load_dotenv

from models.eu_hleg_detailed_mapping import (
    EuToHlegDetailedMapping,
    HlegRequirementLink,
    HlegSubtopicLink,
)

# Load environment variables
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

# Neo4j connection settings (regex database on port 7688)
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def get_driver():
    """Get Neo4j driver instance."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def ingest_eu_hleg_detailed_mapping(
    mapping: EuToHlegDetailedMapping,
    source: str = "eu_to_hleg_detailed_mapping_v1",
) -> tuple[int, int]:
    """
    Ingest a single EuToHlegDetailedMapping into Neo4j.

    Creates:
      - ALIGNS_WITH_HLEG_REQUIREMENT relationships for requirement links
      - ALIGNS_WITH_HLEG_SUBTOPIC relationships for subtopic links

    Args:
        mapping: EuToHlegDetailedMapping instance from the mapping agent.
        source: Short string identifying the mapping pipeline version.

    Returns:
        Tuple of (requirement_links_count, subtopic_links_count)
    """
    if not mapping.requirement_links:
        return (0, 0)

    loc = mapping.location
    req_count = 0
    sub_count = 0

    driver = get_driver()
    try:
        with driver.session() as session:
            for req_link in mapping.requirement_links:
                # Create requirement relationship
                _create_requirement_relationship(
                    session=session,
                    document_id=loc.document_id,
                    chapter_number=loc.chapter_number,
                    article_number=loc.article_number,
                    paragraph_index=loc.paragraph_index,
                    req_link=req_link,
                    source=source,
                    paragraph_text=mapping.paragraph_text,
                )
                req_count += 1

                # Create subtopic relationships
                for sub_link in req_link.subtopic_links:
                    _create_subtopic_relationship(
                        session=session,
                        document_id=loc.document_id,
                        chapter_number=loc.chapter_number,
                        article_number=loc.article_number,
                        paragraph_index=loc.paragraph_index,
                        sub_link=sub_link,
                        source=source,
                        paragraph_text=mapping.paragraph_text,
                    )
                    sub_count += 1
    finally:
        driver.close()

    return (req_count, sub_count)


def _create_requirement_relationship(
    session,
    document_id: str,
    chapter_number: str,
    article_number: str,
    paragraph_index: int,
    req_link: HlegRequirementLink,
    source: str,
    paragraph_text: str,
) -> None:
    """
    Create or merge one ALIGNS_WITH_HLEG_REQUIREMENT relationship.
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
    SET r.confidence = $confidence,
        r.explanation = $explanation,
        r.source    = $source,
        r.mapped_at = datetime(),
        r.paragraph_text_snapshot = $paragraph_text
    """

    session.run(
        cypher,
        document_id=document_id,
        chapter_number=chapter_number,
        article_number=int(article_number),
        paragraph_index=paragraph_index,
        hleg_requirement_id=req_link.requirement_id,
        confidence=req_link.confidence,
        explanation=req_link.explanation,
        source=source,
        paragraph_text=paragraph_text,
    )


def _create_subtopic_relationship(
    session,
    document_id: str,
    chapter_number: str,
    article_number: str,
    paragraph_index: int,
    sub_link: HlegSubtopicLink,
    source: str,
    paragraph_text: str,
) -> None:
    """
    Create or merge one ALIGNS_WITH_HLEG_SUBTOPIC relationship.
    """
    # Handle both structures: Chapter->Article and Chapter->Section->Article
    cypher = """
    MATCH (d:Regulation {document_id: $document_id})
          -[:HAS_CHAPTER]->(c:Chapter {number: $chapter_number})
    MATCH (a:Article {number: $article_number})
          -[:HAS_PARAGRAPH]->(p:Paragraph {number: $paragraph_index})
    WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
    MATCH (s:HLEGSubtopic {id: $hleg_subtopic_id})
    MERGE (p)-[r:ALIGNS_WITH_HLEG_SUBTOPIC]->(s)
    SET r.confidence = $confidence,
        r.explanation = $explanation,
        r.source    = $source,
        r.mapped_at = datetime(),
        r.paragraph_text_snapshot = $paragraph_text
    """

    session.run(
        cypher,
        document_id=document_id,
        chapter_number=chapter_number,
        article_number=int(article_number),
        paragraph_index=paragraph_index,
        hleg_subtopic_id=sub_link.subtopic_id,
        confidence=sub_link.confidence,
        explanation=sub_link.explanation,
        source=source,
        paragraph_text=paragraph_text,
    )


def clear_existing_mappings(chapter_number: str = "III") -> None:
    """
    Clear existing mapping relationships for a specific chapter.

    This allows re-running the mapping without duplicates.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            # Clear requirement mappings
            session.run("""
                MATCH (c:Chapter {number: $chapter_number})
                      -[:HAS_SECTION|HAS_ARTICLE*1..2]->(a:Article)
                      -[:HAS_PARAGRAPH]->(p:Paragraph)
                      -[r:ALIGNS_WITH_HLEG_REQUIREMENT]->()
                DELETE r
            """, chapter_number=chapter_number)

            # Clear subtopic mappings
            session.run("""
                MATCH (c:Chapter {number: $chapter_number})
                      -[:HAS_SECTION|HAS_ARTICLE*1..2]->(a:Article)
                      -[:HAS_PARAGRAPH]->(p:Paragraph)
                      -[r:ALIGNS_WITH_HLEG_SUBTOPIC]->()
                DELETE r
            """, chapter_number=chapter_number)

        print(f"Cleared existing mappings for Chapter {chapter_number}")
    finally:
        driver.close()

"""
Deterministic Neo4j Ingestion for Legal Document Structure

This module takes a PreprocessedLegalDocument (output from agent_preprocess_eu_ai_act.py)
and writes it to Neo4j following a clean graph schema.

Key principles:
  - NO LLM calls - all data comes from PreprocessedLegalDocument
  - Deterministic: re-running ingestion is idempotent (uses MERGE)
  - Creates nodes: Regulation, Recital, Chapter, Section, Article, Paragraph, Point, Annex
  - Creates relationships: HAS_RECITAL, HAS_CHAPTER, HAS_SECTION, HAS_ARTICLE, etc.

Graph Schema:
  - (r:Regulation {document_id})
    -[:HAS_RECITAL]-> (rec:Recital {document_id, number})
    -[:HAS_CHAPTER]-> (ch:Chapter {document_id, number})
    -[:HAS_ANNEX]-> (ax:Annex {document_id, number})

  - (ch)-[:HAS_SECTION]->(sec:Section {document_id, number})
  - (ch)-[:HAS_ARTICLE]->(art:Article {document_id, number})
  - (sec)-[:HAS_ARTICLE]->(art:Article {document_id, number})

  - (art)-[:HAS_PARAGRAPH]->(par:Paragraph {document_id, article_number, index})
  - (par)-[:HAS_POINT]->(pt:Point {document_id, article_number, paragraph_index, marker})

Note: This ingestion is idempotent - you can re-run it safely.

Neo4j connection is managed via config.neo4j_config; do not create drivers directly here.
"""

from typing import Optional

from neo4j import Driver
from models.legal_structure import PreprocessedLegalDocument, Chapter, Section, Article, Paragraph, Point, Recital, Annex
from config.neo4j_config import get_neo4j_driver


# ============================================================================
# High-level Ingestion Function
# ============================================================================

def ingest_preprocessed_legal_document(
    preprocessed: PreprocessedLegalDocument,
) -> None:
    """
    Deterministically write a PreprocessedLegalDocument to Neo4j.

    Graph schema (initial, simple version):

      (r:Regulation {document_id})
        -[:HAS_RECITAL]-> (rec:Recital {document_id, number})
        -[:HAS_CHAPTER]-> (ch:Chapter {document_id, number})
        -[:HAS_ANNEX]-> (ax:Annex {document_id, number})

      (ch)-[:HAS_SECTION]->(sec:Section {document_id, number})
      (ch)-[:HAS_ARTICLE]->(art:Article {document_id, number})
      (sec)-[:HAS_ARTICLE]->(art:Article {document_id, number})

      (art)-[:HAS_PARAGRAPH]->(par:Paragraph {document_id, article_number, index})
      (par)-[:HAS_POINT]->(pt:Point {document_id, article_number, paragraph_index, marker})

    This ingestion must:
      - NOT call any LLMs.
      - Use MERGE so re-running is idempotent at the node/relationship level.
      - Be deterministic given the same PreprocessedLegalDocument.

    For now, do NOT delete existing nodes; we keep it simple (future
    cleanup logic can be added later).

    Args:
        preprocessed: The PreprocessedLegalDocument from the preprocessing agent

    Example:
        >>> from agent_preprocess_eu_ai_act import preprocess_legal_agent
        >>> result = await preprocess_legal_agent.run(prompt, deps=deps)
        >>> preprocessed = result.output
        >>> ingest_preprocessed_legal_document(preprocessed)
    """
    with get_neo4j_driver() as driver:
        # Step 1: Create/merge Regulation node
        _merge_regulation_node(driver, preprocessed)

        # Step 2: Create/merge Recitals
        _merge_recitals(driver, preprocessed)

        # Step 3: Create/merge Chapters, Sections, and Articles
        _merge_chapters_and_articles(driver, preprocessed)

        # Step 4: Create/merge Annexes
        _merge_annexes(driver, preprocessed)

    print(f"✓ Ingested legal document '{preprocessed.document_id}' to Neo4j")
    print(f"  - Official title: {preprocessed.official_title[:80]}...")
    print(f"  - Recitals: {len(preprocessed.recitals)}")
    print(f"  - Chapters: {len(preprocessed.chapters)}")
    print(f"  - Annexes: {len(preprocessed.annexes)}")


# ============================================================================
# Helper Functions for Node Creation
# ============================================================================

def _merge_regulation_node(
    driver: Driver,
    preprocessed: PreprocessedLegalDocument,
) -> None:
    """
    Create or merge the root Regulation node.

    Args:
        driver: Neo4j driver instance
        preprocessed: PreprocessedLegalDocument instance
    """
    cypher = """
    MERGE (r:Regulation {document_id: $document_id})
    SET r.official_title = $official_title,
        r.short_title = $short_title,
        r.year = $year
    """

    driver.execute_query(
        cypher,
        document_id=preprocessed.document_id,
        official_title=preprocessed.official_title,
        short_title=preprocessed.short_title,
        year=preprocessed.year,
    )


def _merge_recitals(
    driver: Driver,
    preprocessed: PreprocessedLegalDocument,
) -> None:
    """
    Create or merge Recital nodes and link them to the Regulation.

    Args:
        driver: Neo4j driver instance
        preprocessed: PreprocessedLegalDocument instance
    """
    if not preprocessed.recitals:
        return

    recitals_data = [
        {
            "number": rec.number,
            "text": rec.text,
        }
        for rec in preprocessed.recitals
    ]

    cypher = """
    MATCH (r:Regulation {document_id: $document_id})
    UNWIND $recitals AS recital
    MERGE (rec:Recital {document_id: $document_id, number: recital.number})
    SET rec.text = recital.text
    MERGE (r)-[:HAS_RECITAL]->(rec)
    """

    driver.execute_query(
        cypher,
        document_id=preprocessed.document_id,
        recitals=recitals_data,
    )


def _merge_chapters_and_articles(
    driver: Driver,
    preprocessed: PreprocessedLegalDocument,
) -> None:
    """
    Create or merge Chapter, Section, Article, Paragraph, and Point nodes.

    This handles the main body structure of the regulation.

    Args:
        driver: Neo4j driver instance
        preprocessed: PreprocessedLegalDocument instance
    """
    for chapter in preprocessed.chapters:
        # Create chapter node
        _merge_chapter_node(driver, preprocessed.document_id, chapter)

        # Handle sections if present
        if chapter.sections:
            for section in chapter.sections:
                _merge_section_node(driver, preprocessed.document_id, chapter.number, section)
                # Articles under section
                for article in section.articles:
                    _merge_article_with_paragraphs(
                        driver,
                        preprocessed.document_id,
                        article,
                        parent_type="section",
                        parent_number=section.number,
                        chapter_number=chapter.number,
                    )

        # Handle articles directly under chapter (when no sections)
        if chapter.articles:
            for article in chapter.articles:
                _merge_article_with_paragraphs(
                    driver,
                    preprocessed.document_id,
                    article,
                    parent_type="chapter",
                    parent_number=chapter.number,
                )


def _merge_chapter_node(
    driver: Driver,
    document_id: str,
    chapter: Chapter,
) -> None:
    """Create or merge a Chapter node."""
    cypher = """
    MATCH (r:Regulation {document_id: $document_id})
    MERGE (ch:Chapter {document_id: $document_id, number: $number})
    SET ch.title = $title
    MERGE (r)-[:HAS_CHAPTER]->(ch)
    """

    driver.execute_query(
        cypher,
        document_id=document_id,
        number=chapter.number,
        title=chapter.title,
    )


def _merge_section_node(
    driver: Driver,
    document_id: str,
    chapter_number: str,
    section: Section,
) -> None:
    """Create or merge a Section node."""
    cypher = """
    MATCH (ch:Chapter {document_id: $document_id, number: $chapter_number})
    MERGE (sec:Section {document_id: $document_id, chapter_number: $chapter_number, number: $number})
    SET sec.title = $title
    MERGE (ch)-[:HAS_SECTION]->(sec)
    """

    driver.execute_query(
        cypher,
        document_id=document_id,
        chapter_number=chapter_number,
        number=section.number,
        title=section.title,
    )


def _merge_article_with_paragraphs(
    driver: Driver,
    document_id: str,
    article: Article,
    parent_type: str,
    parent_number: str,
    chapter_number: Optional[str] = None,
) -> None:
    """
    Create or merge an Article node and its paragraphs/points.

    Args:
        driver: Neo4j driver instance
        document_id: Document ID
        article: Article instance
        parent_type: Either "chapter" or "section"
        parent_number: Number of the parent chapter or section
        chapter_number: Chapter number (required if parent_type is "section")
    """
    # Create article node
    if parent_type == "chapter":
        cypher_article = """
        MATCH (ch:Chapter {document_id: $document_id, number: $parent_number})
        MERGE (art:Article {document_id: $document_id, number: $article_number})
        SET art.title = $title
        MERGE (ch)-[:HAS_ARTICLE]->(art)
        """
        driver.execute_query(
            cypher_article,
            document_id=document_id,
            parent_number=parent_number,
            article_number=article.number,
            title=article.title,
        )
    else:  # parent_type == "section"
        cypher_article = """
        MATCH (sec:Section {document_id: $document_id, chapter_number: $chapter_number, number: $parent_number})
        MERGE (art:Article {document_id: $document_id, number: $article_number})
        SET art.title = $title
        MERGE (sec)-[:HAS_ARTICLE]->(art)
        """
        driver.execute_query(
            cypher_article,
            document_id=document_id,
            chapter_number=chapter_number,
            parent_number=parent_number,
            article_number=article.number,
            title=article.title,
        )

    # Create paragraphs and points
    for paragraph in article.paragraphs:
        _merge_paragraph_with_points(driver, document_id, article.number, paragraph)


def _merge_paragraph_with_points(
    driver: Driver,
    document_id: str,
    article_number: int,
    paragraph: Paragraph,
) -> None:
    """Create or merge a Paragraph node and its points."""
    # Create paragraph node
    cypher_paragraph = """
    MATCH (art:Article {document_id: $document_id, number: $article_number})
    MERGE (par:Paragraph {document_id: $document_id, article_number: $article_number, index: $index})
    SET par.text = $text
    MERGE (art)-[:HAS_PARAGRAPH]->(par)
    """

    driver.execute_query(
        cypher_paragraph,
        document_id=document_id,
        article_number=article_number,
        index=paragraph.index,
        text=paragraph.text,
    )

    # Create point nodes if present
    if paragraph.points:
        points_data = [
            {
                "marker": pt.marker,
                "text": pt.text,
            }
            for pt in paragraph.points
        ]

        cypher_points = """
        MATCH (par:Paragraph {document_id: $document_id, article_number: $article_number, index: $paragraph_index})
        UNWIND $points AS point
        MERGE (pt:Point {document_id: $document_id, article_number: $article_number, paragraph_index: $paragraph_index, marker: point.marker})
        SET pt.text = point.text
        MERGE (par)-[:HAS_POINT]->(pt)
        """

        driver.execute_query(
            cypher_points,
            document_id=document_id,
            article_number=article_number,
            paragraph_index=paragraph.index,
            points=points_data,
        )


def _merge_annexes(
    driver: Driver,
    preprocessed: PreprocessedLegalDocument,
) -> None:
    """
    Create or merge Annex nodes and link them to the Regulation.

    Args:
        driver: Neo4j driver instance
        preprocessed: PreprocessedLegalDocument instance
    """
    if not preprocessed.annexes:
        return

    annexes_data = [
        {
            "number": annex.number,
            "title": annex.title,
            "raw_text": annex.raw_text,
        }
        for annex in preprocessed.annexes
    ]

    cypher = """
    MATCH (r:Regulation {document_id: $document_id})
    UNWIND $annexes AS annex
    MERGE (ax:Annex {document_id: $document_id, number: annex.number})
    SET ax.title = annex.title,
        ax.raw_text = annex.raw_text
    MERGE (r)-[:HAS_ANNEX]->(ax)
    """

    driver.execute_query(
        cypher,
        document_id=preprocessed.document_id,
        annexes=annexes_data,
    )

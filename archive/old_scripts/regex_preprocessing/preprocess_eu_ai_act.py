#!/usr/bin/env python3
"""
EU AI Act Regex-Based Preprocessor

This script extracts ALL structural data from the EU AI Act using only regex
and deterministic Python operations. No LLMs are used.

Structure extracted:
- Document metadata
- Recitals (1) through (180)
- Chapters I through XIII
- Sections within chapters
- Articles 1 through 113
- Paragraphs within articles
- Points within paragraphs
- Annexes I through XIII

All data is ingested into Neo4j for graph-based querying.
"""

import re
import sys
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables (local .env takes priority, override existing)
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

# Neo4j connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


# =============================================================================
# Data Classes for Structured Output
# =============================================================================

@dataclass
class Point:
    """A point within a paragraph, e.g., (a), (b), (i), (ii)"""
    marker: str
    text: str


@dataclass
class Paragraph:
    """A paragraph within an article"""
    number: int
    text: str
    points: list[Point] = field(default_factory=list)


@dataclass
class Article:
    """An article within a chapter or section"""
    number: int
    title: str
    full_text: str
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class Section:
    """A section within a chapter"""
    number: int
    title: str
    articles: list[Article] = field(default_factory=list)


@dataclass
class Chapter:
    """A chapter of the regulation"""
    number: str  # Roman numeral
    number_int: int  # Integer equivalent
    title: str
    sections: list[Section] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)  # Direct articles (no section)


@dataclass
class Recital:
    """A recital (Whereas clause)"""
    number: int
    text: str


@dataclass
class AnnexItem:
    """An item within an annex"""
    number: str
    text: str
    subitems: list['AnnexItem'] = field(default_factory=list)


@dataclass
class Annex:
    """An annex to the regulation"""
    number: str  # Roman numeral
    number_int: int  # Integer equivalent
    title: str
    full_text: str
    items: list[AnnexItem] = field(default_factory=list)


@dataclass
class EUAIAct:
    """Complete structure of the EU AI Act"""
    document_id: str
    official_title: str
    short_title: str
    regulation_number: str
    year: int
    recitals: list[Recital] = field(default_factory=list)
    chapters: list[Chapter] = field(default_factory=list)
    annexes: list[Annex] = field(default_factory=list)


# =============================================================================
# Roman Numeral Conversion
# =============================================================================

def roman_to_int(roman: str) -> int:
    """Convert Roman numeral to integer."""
    roman = roman.upper().strip()
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    result = 0
    prev = 0
    for char in reversed(roman):
        curr = values.get(char, 0)
        if curr < prev:
            result -= curr
        else:
            result += curr
        prev = curr
    return result


# =============================================================================
# Regex Patterns
# =============================================================================

# Pattern for recitals: (1), (2), etc. at start of line
RECITAL_PATTERN = re.compile(r'^\((\d+)\)\s*$', re.MULTILINE)

# Pattern for chapters: CHAPTER I, CHAPTER II, etc.
CHAPTER_PATTERN = re.compile(r'^CHAPTER\s+([IVXLCDM]+)\s*$', re.MULTILINE)

# Pattern for sections: SECTION 1, SECTION 2, etc.
SECTION_PATTERN = re.compile(r'^SECTION\s+(\d+)\s*$', re.MULTILINE)

# Pattern for articles: Article 1, Article 2, etc.
ARTICLE_PATTERN = re.compile(r'^Article\s+(\d+)\s*$', re.MULTILINE)

# Pattern for annexes: ANNEX I, ANNEX II, etc.
ANNEX_PATTERN = re.compile(r'^ANNEX\s+([IVXLCDM]+)\s*$', re.MULTILINE)

# Pattern for paragraphs: 1., 2., 3. at start of line (with possible spaces)
PARAGRAPH_PATTERN = re.compile(r'^(\d+)\.\s+', re.MULTILINE)

# Pattern for points: (a), (b), (i), (ii), etc.
POINT_PATTERN = re.compile(r'^\(([a-z]|[ivxlcdm]+|\d+)\)\s*$', re.MULTILINE)


# =============================================================================
# Parsing Functions
# =============================================================================

def read_file(filepath: str) -> str:
    """Read the EU AI Act text file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    # Remove excessive whitespace while preserving structure
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_title_after_marker(text: str, start_pos: int) -> str:
    """Extract the title that follows a structural marker (chapter, section, article, annex)."""
    # Find the next non-empty line after the marker
    remaining = text[start_pos:].lstrip('\n')
    lines = remaining.split('\n')

    title_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            break
        # Stop if we hit another structural marker
        if (CHAPTER_PATTERN.match(line) or SECTION_PATTERN.match(line) or
            ARTICLE_PATTERN.match(line) or ANNEX_PATTERN.match(line) or
            RECITAL_PATTERN.match(line) or PARAGRAPH_PATTERN.match(line)):
            break
        title_lines.append(line)

    return ' '.join(title_lines)


def find_section_boundaries(text: str) -> list[tuple[int, int, str, str]]:
    """
    Find all major section boundaries in the document.
    Returns list of (start_pos, end_pos, type, identifier).
    """
    boundaries = []

    # Find all recitals
    for match in RECITAL_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'recital', match.group(1)))

    # Find all chapters
    for match in CHAPTER_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'chapter', match.group(1)))

    # Find all sections
    for match in SECTION_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'section', match.group(1)))

    # Find all articles
    for match in ARTICLE_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'article', match.group(1)))

    # Find all annexes
    for match in ANNEX_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'annex', match.group(1)))

    # Sort by position
    boundaries.sort(key=lambda x: x[0])

    return boundaries


def find_section_boundaries_main(text: str) -> list[tuple[int, int, str, str]]:
    """
    Find structural boundaries in the main body (chapters, sections, articles, annexes).
    Excludes recitals (handled separately).
    """
    boundaries = []

    # Find all chapters
    for match in CHAPTER_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'chapter', match.group(1)))

    # Find all sections
    for match in SECTION_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'section', match.group(1)))

    # Find all articles
    for match in ARTICLE_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'article', match.group(1)))

    # Find all annexes
    for match in ANNEX_PATTERN.finditer(text):
        boundaries.append((match.start(), match.end(), 'annex', match.group(1)))

    # Sort by position
    boundaries.sort(key=lambda x: x[0])

    return boundaries


def extract_content_between(text: str, start: int, end: int) -> str:
    """Extract and clean content between two positions."""
    return clean_text(text[start:end])


def parse_points_from_text(text: str) -> list[Point]:
    """Parse points (a), (b), etc. from paragraph text."""
    points = []

    # Split by point markers
    # Pattern to find point markers in the text
    point_split = re.compile(r'\n\(([a-z]|[ivxlcdm]+)\)\s*\n', re.IGNORECASE)

    # Find all point markers
    markers = list(point_split.finditer(text))

    if not markers:
        return points

    for i, match in enumerate(markers):
        marker = match.group(1)
        start = match.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        point_text = clean_text(text[start:end])
        if point_text:
            points.append(Point(marker=marker, text=point_text))

    return points


def parse_paragraphs_from_article(article_text: str) -> list[Paragraph]:
    """Parse paragraphs from article text."""
    paragraphs = []

    # Find paragraph markers: "1.   ", "2.   ", etc.
    para_pattern = re.compile(r'^(\d+)\.\s{2,}', re.MULTILINE)
    matches = list(para_pattern.finditer(article_text))

    if not matches:
        # Single paragraph article (no numbered paragraphs)
        # Keep full text including points (consistent with numbered paragraphs)
        text = clean_text(article_text)
        if text:
            points = parse_points_from_text(text)
            paragraphs.append(Paragraph(number=1, text=text, points=points))
        return paragraphs

    for i, match in enumerate(matches):
        para_num = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(article_text)
        para_text = clean_text(article_text[start:end])

        if para_text:
            points = parse_points_from_text(para_text)
            paragraphs.append(Paragraph(number=para_num, text=para_text, points=points))

    return paragraphs


def extract_recitals(text: str) -> list[Recital]:
    """Extract recitals from the 'Whereas:' section before CHAPTER I."""
    recitals = []

    # Find the recitals section (between "Whereas:" and "CHAPTER I")
    whereas_match = re.search(r'Whereas:\s*\n', text, re.IGNORECASE)
    chapter_match = re.search(r'^CHAPTER\s+I\s*$', text, re.MULTILINE)

    if not whereas_match or not chapter_match:
        print("Warning: Could not locate recitals section boundaries")
        return recitals

    recitals_section = text[whereas_match.end():chapter_match.start()]

    # Find all recitals in this section
    # Pattern: (N) at start of line, followed by text until next (N+1) or end
    recital_starts = list(RECITAL_PATTERN.finditer(recitals_section))

    for i, match in enumerate(recital_starts):
        recital_num = int(match.group(1))
        start = match.end()
        end = recital_starts[i + 1].start() if i + 1 < len(recital_starts) else len(recitals_section)

        recital_text = clean_text(recitals_section[start:end])
        if recital_text:
            recitals.append(Recital(number=recital_num, text=recital_text))

    return recitals


def parse_eu_ai_act(text: str) -> EUAIAct:
    """Parse the complete EU AI Act document."""

    print("Starting EU AI Act parsing...")

    # Create the main document structure
    doc = EUAIAct(
        document_id="eu_ai_act_2024",
        official_title="REGULATION (EU) 2024/1689 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL",
        short_title="Artificial Intelligence Act",
        regulation_number="2024/1689",
        year=2024
    )

    # Extract recitals first (from dedicated section)
    doc.recitals = extract_recitals(text)
    print(f"Extracted {len(doc.recitals)} recitals")

    # Find all structural boundaries (excluding recitals now)
    boundaries = find_section_boundaries_main(text)
    print(f"Found {len(boundaries)} structural markers in main body")

    # Track current context
    current_chapter: Optional[Chapter] = None
    current_section: Optional[Section] = None

    # Statistics
    article_count = 0
    chapter_count = 0
    section_count = 0
    annex_count = 0

    # Process each boundary
    for i, (start, end, marker_type, identifier) in enumerate(boundaries):
        # Get end position (next boundary or end of text)
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)

        # Extract the full content for this element
        content = extract_content_between(text, end, next_start)

        if marker_type == 'chapter':
            # Get chapter title
            title = extract_title_after_marker(text, end)
            chapter = Chapter(
                number=identifier,
                number_int=roman_to_int(identifier),
                title=title
            )
            doc.chapters.append(chapter)
            current_chapter = chapter
            current_section = None  # Reset section when entering new chapter
            chapter_count += 1
            print(f"  Chapter {identifier}: {title[:50]}...")

        elif marker_type == 'section':
            if current_chapter is None:
                print(f"  Warning: Section {identifier} found outside of chapter context")
                continue

            # Get section title
            title = extract_title_after_marker(text, end)
            section = Section(
                number=int(identifier),
                title=title
            )
            current_chapter.sections.append(section)
            current_section = section
            section_count += 1

        elif marker_type == 'article':
            article_num = int(identifier)

            # Get article title
            title = extract_title_after_marker(text, end)

            # Get full article text (everything until next major boundary)
            article_text = content

            # Parse paragraphs
            paragraphs = parse_paragraphs_from_article(article_text)

            article = Article(
                number=article_num,
                title=title,
                full_text=article_text,
                paragraphs=paragraphs
            )

            # Add to current section or chapter
            if current_section is not None:
                current_section.articles.append(article)
            elif current_chapter is not None:
                current_chapter.articles.append(article)
            else:
                print(f"  Warning: Article {article_num} found outside of chapter context")

            article_count += 1

        elif marker_type == 'annex':
            # Get annex title
            title = extract_title_after_marker(text, end)
            annex_text = content

            annex = Annex(
                number=identifier,
                number_int=roman_to_int(identifier),
                title=title,
                full_text=annex_text
            )
            doc.annexes.append(annex)
            annex_count += 1
            print(f"  Annex {identifier}: {title[:50]}...")

            # Reset context when entering annexes
            current_chapter = None
            current_section = None

    print(f"\nParsing complete:")
    print(f"  - Recitals: {len(doc.recitals)}")
    print(f"  - Chapters: {chapter_count}")
    print(f"  - Sections: {section_count}")
    print(f"  - Articles: {article_count}")
    print(f"  - Annexes: {annex_count}")

    return doc


# =============================================================================
# Neo4j Ingestion
# =============================================================================

class Neo4jIngester:
    """Handles ingestion of parsed data into Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def clear_database(self):
        """Clear all existing data (optional, for fresh start)."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("Database cleared.")

    def create_constraints(self):
        """Create uniqueness constraints for better performance."""
        constraints = [
            "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.document_id IS UNIQUE",
            "CREATE CONSTRAINT recital_id IF NOT EXISTS FOR (r:Recital) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT paragraph_id IF NOT EXISTS FOR (p:Paragraph) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT point_id IF NOT EXISTS FOR (p:Point) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT annex_id IF NOT EXISTS FOR (a:Annex) REQUIRE a.id IS UNIQUE",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    # Constraint might already exist
                    pass
        print("Constraints created.")

    def ingest(self, doc: EUAIAct):
        """Ingest the entire document into Neo4j."""

        print("\nIngesting into Neo4j...")

        with self.driver.session() as session:
            # Create the main regulation node
            session.run("""
                MERGE (r:Regulation {document_id: $doc_id})
                SET r.official_title = $official_title,
                    r.short_title = $short_title,
                    r.regulation_number = $regulation_number,
                    r.year = $year
            """,
                doc_id=doc.document_id,
                official_title=doc.official_title,
                short_title=doc.short_title,
                regulation_number=doc.regulation_number,
                year=doc.year
            )
            print(f"Created Regulation node: {doc.document_id}")

            # Ingest recitals
            for recital in doc.recitals:
                self._ingest_recital(session, doc.document_id, recital)
            print(f"Ingested {len(doc.recitals)} recitals")

            # Ingest chapters
            for chapter in doc.chapters:
                self._ingest_chapter(session, doc.document_id, chapter)
            print(f"Ingested {len(doc.chapters)} chapters")

            # Ingest annexes
            for annex in doc.annexes:
                self._ingest_annex(session, doc.document_id, annex)
            print(f"Ingested {len(doc.annexes)} annexes")

        print("Ingestion complete!")

    def _ingest_recital(self, session, doc_id: str, recital: Recital):
        """Ingest a single recital."""
        recital_id = f"{doc_id}_recital_{recital.number}"
        session.run("""
            MATCH (r:Regulation {document_id: $doc_id})
            MERGE (rec:Recital {id: $recital_id})
            SET rec.number = $number,
                rec.text = $text
            MERGE (r)-[:HAS_RECITAL]->(rec)
        """,
            doc_id=doc_id,
            recital_id=recital_id,
            number=recital.number,
            text=recital.text
        )

    def _ingest_chapter(self, session, doc_id: str, chapter: Chapter):
        """Ingest a chapter with all its contents."""
        chapter_id = f"{doc_id}_chapter_{chapter.number}"

        # Create chapter node
        session.run("""
            MATCH (r:Regulation {document_id: $doc_id})
            MERGE (c:Chapter {id: $chapter_id})
            SET c.number = $number,
                c.number_int = $number_int,
                c.title = $title
            MERGE (r)-[:HAS_CHAPTER]->(c)
        """,
            doc_id=doc_id,
            chapter_id=chapter_id,
            number=chapter.number,
            number_int=chapter.number_int,
            title=chapter.title
        )

        # Ingest sections
        for section in chapter.sections:
            self._ingest_section(session, chapter_id, section)

        # Ingest direct articles (not in sections)
        for article in chapter.articles:
            self._ingest_article(session, chapter_id, article, parent_type="Chapter")

    def _ingest_section(self, session, chapter_id: str, section: Section):
        """Ingest a section with all its articles."""
        section_id = f"{chapter_id}_section_{section.number}"

        # Create section node
        session.run("""
            MATCH (c:Chapter {id: $chapter_id})
            MERGE (s:Section {id: $section_id})
            SET s.number = $number,
                s.title = $title
            MERGE (c)-[:HAS_SECTION]->(s)
        """,
            chapter_id=chapter_id,
            section_id=section_id,
            number=section.number,
            title=section.title
        )

        # Ingest articles
        for article in section.articles:
            self._ingest_article(session, section_id, article, parent_type="Section")

    def _ingest_article(self, session, parent_id: str, article: Article, parent_type: str):
        """Ingest an article with all its paragraphs."""
        article_id = f"article_{article.number}"

        # Create article node with relationship to parent
        if parent_type == "Chapter":
            session.run("""
                MATCH (c:Chapter {id: $parent_id})
                MERGE (a:Article {id: $article_id})
                SET a.number = $number,
                    a.title = $title,
                    a.full_text = $full_text
                MERGE (c)-[:HAS_ARTICLE]->(a)
            """,
                parent_id=parent_id,
                article_id=article_id,
                number=article.number,
                title=article.title,
                full_text=article.full_text
            )
        else:  # Section
            session.run("""
                MATCH (s:Section {id: $parent_id})
                MERGE (a:Article {id: $article_id})
                SET a.number = $number,
                    a.title = $title,
                    a.full_text = $full_text
                MERGE (s)-[:HAS_ARTICLE]->(a)
            """,
                parent_id=parent_id,
                article_id=article_id,
                number=article.number,
                title=article.title,
                full_text=article.full_text
            )

        # Ingest paragraphs
        for para in article.paragraphs:
            self._ingest_paragraph(session, article_id, para)

    def _ingest_paragraph(self, session, article_id: str, paragraph: Paragraph):
        """Ingest a paragraph with all its points."""
        para_id = f"{article_id}_para_{paragraph.number}"

        session.run("""
            MATCH (a:Article {id: $article_id})
            MERGE (p:Paragraph {id: $para_id})
            SET p.number = $number,
                p.text = $text
            MERGE (a)-[:HAS_PARAGRAPH]->(p)
        """,
            article_id=article_id,
            para_id=para_id,
            number=paragraph.number,
            text=paragraph.text
        )

        # Ingest points
        for i, point in enumerate(paragraph.points):
            self._ingest_point(session, para_id, point, i)

    def _ingest_point(self, session, para_id: str, point: Point, index: int):
        """Ingest a point."""
        point_id = f"{para_id}_point_{point.marker}"

        session.run("""
            MATCH (p:Paragraph {id: $para_id})
            MERGE (pt:Point {id: $point_id})
            SET pt.marker = $marker,
                pt.text = $text,
                pt.order = $order
            MERGE (p)-[:HAS_POINT]->(pt)
        """,
            para_id=para_id,
            point_id=point_id,
            marker=point.marker,
            text=point.text,
            order=index
        )

    def _ingest_annex(self, session, doc_id: str, annex: Annex):
        """Ingest an annex."""
        annex_id = f"{doc_id}_annex_{annex.number}"

        session.run("""
            MATCH (r:Regulation {document_id: $doc_id})
            MERGE (a:Annex {id: $annex_id})
            SET a.number = $number,
                a.number_int = $number_int,
                a.title = $title,
                a.full_text = $full_text
            MERGE (r)-[:HAS_ANNEX]->(a)
        """,
            doc_id=doc_id,
            annex_id=annex_id,
            number=annex.number,
            number_int=annex.number_int,
            title=annex.title,
            full_text=annex.full_text
        )


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main function to run the preprocessing pipeline."""

    print("=" * 70)
    print("EU AI Act Regex-Based Preprocessor")
    print("=" * 70)

    # Paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    data_file = project_dir / "data" / "eu_ai_act.txt"

    # Check if file exists
    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)

    print(f"\nReading file: {data_file}")

    # Read the file
    text = read_file(str(data_file))
    print(f"File size: {len(text):,} characters, {len(text.splitlines()):,} lines")

    # Parse the document
    doc = parse_eu_ai_act(text)

    # Calculate total articles
    total_articles = sum(
        len(chapter.articles) + sum(len(section.articles) for section in chapter.sections)
        for chapter in doc.chapters
    )
    print(f"\nTotal articles extracted: {total_articles}")

    # Ingest into Neo4j
    print(f"\nConnecting to Neo4j at {NEO4J_URI}...")

    ingester = Neo4jIngester(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Test connection
        with ingester.driver.session() as session:
            result = session.run("RETURN 1")
            result.single()
        print("Connection successful!")

        # Clear and recreate
        ingester.clear_database()
        ingester.create_constraints()
        ingester.ingest(doc)

        # Print summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Document: {doc.official_title}")
        print(f"Recitals: {len(doc.recitals)}")
        print(f"Chapters: {len(doc.chapters)}")
        print(f"Articles: {total_articles}")
        print(f"Annexes: {len(doc.annexes)}")

        # Print chapter details
        print("\nChapter breakdown:")
        for chapter in doc.chapters:
            section_count = len(chapter.sections)
            direct_articles = len(chapter.articles)
            section_articles = sum(len(s.articles) for s in chapter.sections)
            total = direct_articles + section_articles
            print(f"  Chapter {chapter.number}: {chapter.title[:40]}...")
            print(f"    - Sections: {section_count}, Direct articles: {direct_articles}, Section articles: {section_articles}, Total: {total}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ingester.close()

    print("\nDone!")
    return doc


if __name__ == "__main__":
    main()

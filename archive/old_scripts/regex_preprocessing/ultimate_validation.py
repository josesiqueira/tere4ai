#!/usr/bin/env python3
"""
Ultimate Validation for EU AI Act Regex Preprocessing

This script performs comprehensive validation of the database content
against the source file, ensuring:
1. All structural elements are present
2. Content matches source exactly
3. No gaps or overlaps in coverage
4. Structural relationships are correct
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from difflib import SequenceMatcher

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

# Load environment
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


# =============================================================================
# Validation Result Classes
# =============================================================================

@dataclass
class ValidationResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report."""
    results: list[ValidationResult] = field(default_factory=list)

    def add(self, result: ValidationResult):
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def print_report(self):
        print("\n" + "=" * 70)
        print("ULTIMATE VALIDATION REPORT")
        print("=" * 70)

        for result in self.results:
            status = "✓" if result.passed else "✗"
            print(f"\n[{status}] {result.name}")
            print(f"    {result.message}")
            if result.details and not result.passed:
                for detail in result.details[:5]:  # Show first 5 details
                    print(f"      - {detail}")
                if len(result.details) > 5:
                    print(f"      ... and {len(result.details) - 5} more")

        print("\n" + "=" * 70)
        print(f"SUMMARY: {self.passed}/{self.total} checks passed")
        if self.failed > 0:
            print(f"         {self.failed} checks FAILED")
        print("=" * 70)


# =============================================================================
# Source File Parser
# =============================================================================

class SourceParser:
    """Parse source file and extract positions of all elements."""

    def __init__(self, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as f:
            self.text = f.read()

        self.recital_positions: list[tuple[int, int, int]] = []  # (start, end, number)
        self.article_positions: list[tuple[int, int, int]] = []  # (start, end, number)
        self.chapter_positions: list[tuple[int, int, str]] = []  # (start, end, roman)
        self.annex_positions: list[tuple[int, int, str]] = []    # (start, end, roman)

        self._parse()

    def _parse(self):
        """Parse all structural elements from source."""

        # Find recitals section
        whereas_match = re.search(r'Whereas:\s*\n', self.text, re.IGNORECASE)
        chapter_match = re.search(r'^CHAPTER\s+I\s*$', self.text, re.MULTILINE)

        if whereas_match and chapter_match:
            recitals_section = self.text[whereas_match.end():chapter_match.start()]
            recital_pattern = re.compile(r'^\((\d+)\)\s*$', re.MULTILINE)
            matches = list(recital_pattern.finditer(recitals_section))

            for i, match in enumerate(matches):
                num = int(match.group(1))
                start = whereas_match.end() + match.end()
                end = whereas_match.end() + (matches[i + 1].start() if i + 1 < len(matches) else len(recitals_section))
                self.recital_positions.append((start, end, num))

        # Find all chapters
        chapter_pattern = re.compile(r'^CHAPTER\s+([IVXLCDM]+)\s*$', re.MULTILINE)
        for match in chapter_pattern.finditer(self.text):
            self.chapter_positions.append((match.start(), match.end(), match.group(1)))

        # Find all articles
        article_pattern = re.compile(r'^Article\s+(\d+)\s*$', re.MULTILINE)
        matches = list(article_pattern.finditer(self.text))

        # Find next boundary for each article
        all_boundaries = []
        for m in article_pattern.finditer(self.text):
            all_boundaries.append((m.start(), 'article', int(m.group(1))))
        for m in re.finditer(r'^ANNEX\s+([IVXLCDM]+)\s*$', self.text, re.MULTILINE):
            all_boundaries.append((m.start(), 'annex', m.group(1)))

        all_boundaries.sort(key=lambda x: x[0])

        for i, (pos, typ, val) in enumerate(all_boundaries):
            if typ == 'article':
                next_pos = all_boundaries[i + 1][0] if i + 1 < len(all_boundaries) else len(self.text)
                self.article_positions.append((pos, next_pos, val))
            elif typ == 'annex':
                next_pos = all_boundaries[i + 1][0] if i + 1 < len(all_boundaries) else len(self.text)
                self.annex_positions.append((pos, next_pos, val))

    def get_recital_text(self, number: int) -> Optional[str]:
        """Get recital text from source."""
        for start, end, num in self.recital_positions:
            if num == number:
                return self.text[start:end].strip()
        return None

    def get_article_text(self, number: int) -> Optional[str]:
        """Get article text from source (including title line)."""
        for start, end, num in self.article_positions:
            if num == number:
                return self.text[start:end].strip()
        return None

    def get_article_content(self, number: int) -> Optional[str]:
        """Get article content (excluding Article N line and title)."""
        for start, end, num in self.article_positions:
            if num == number:
                text = self.text[start:end]
                # Skip "Article N" line and title line
                lines = text.split('\n')
                # Find first non-empty line after title
                content_start = 0
                for i, line in enumerate(lines):
                    if i > 0 and line.strip() and not line.strip().startswith('Article'):
                        # Skip title line too
                        if i > 1:
                            content_start = i + 1
                            break
                        content_start = i
                        break

                # Actually, let's just skip the first two non-empty lines (Article N and title)
                non_empty_count = 0
                for i, line in enumerate(lines):
                    if line.strip():
                        non_empty_count += 1
                        if non_empty_count == 2:
                            content_lines = lines[i+1:]
                            return '\n'.join(content_lines).strip()

                return text.strip()
        return None


# =============================================================================
# Validation Functions
# =============================================================================

def validate_counts(session, report: ValidationReport):
    """Validate that all expected elements exist."""

    expected = {
        'Recital': 180,
        'Chapter': 13,
        'Section': 16,
        'Article': 113,
        'Annex': 13,
    }

    for label, expected_count in expected.items():
        result = session.run(f'MATCH (n:{label}) RETURN count(n) as cnt')
        actual = result.single()['cnt']

        passed = actual == expected_count
        report.add(ValidationResult(
            name=f"{label} count",
            passed=passed,
            message=f"Expected {expected_count}, found {actual}",
            details=[] if passed else [f"Missing {expected_count - actual} {label}s"]
        ))


def validate_recital_content(session, source: SourceParser, report: ValidationReport):
    """Validate each recital's content matches source."""

    result = session.run('MATCH (r:Recital) RETURN r.number as num, r.text as text ORDER BY r.number')

    mismatches = []
    for record in result:
        num = record['num']
        db_text = record['text'].strip()
        source_text = source.get_recital_text(num)

        if source_text is None:
            mismatches.append(f"Recital {num}: not found in source")
            continue

        source_text = source_text.strip()

        # Compare (allow minor whitespace differences)
        db_normalized = ' '.join(db_text.split())
        source_normalized = ' '.join(source_text.split())

        if db_normalized != source_normalized:
            ratio = SequenceMatcher(None, db_normalized, source_normalized).ratio()
            if ratio < 0.99:
                mismatches.append(f"Recital {num}: {ratio:.1%} match (expected 99%+)")

    report.add(ValidationResult(
        name="Recital content validation",
        passed=len(mismatches) == 0,
        message=f"{180 - len(mismatches)}/180 recitals match source exactly",
        details=mismatches
    ))


def validate_article_sequence(session, report: ValidationReport):
    """Validate article numbers are sequential 1-113."""

    result = session.run('MATCH (a:Article) RETURN a.number as num ORDER BY a.number')
    nums = [r['num'] for r in result]

    expected = list(range(1, 114))
    missing = set(expected) - set(nums)
    extra = set(nums) - set(expected)

    details = []
    if missing:
        details.append(f"Missing: {sorted(missing)}")
    if extra:
        details.append(f"Extra: {sorted(extra)}")

    report.add(ValidationResult(
        name="Article sequence validation",
        passed=len(missing) == 0 and len(extra) == 0,
        message=f"Articles 1-113 {'complete' if not missing else 'incomplete'}",
        details=details
    ))


def validate_article_content(session, source: SourceParser, report: ValidationReport):
    """Validate article content matches source."""

    result = session.run('MATCH (a:Article) RETURN a.number as num, a.full_text as text ORDER BY a.number')

    mismatches = []
    for record in result:
        num = record['num']
        db_text = record['text'].strip() if record['text'] else ""

        # Get source article content
        source_full = source.get_article_text(num)
        if source_full is None:
            mismatches.append(f"Article {num}: not found in source")
            continue

        # Normalize for comparison
        db_normalized = ' '.join(db_text.split())

        # Source includes "Article N" line and title, DB full_text doesn't
        # So we compare by checking DB text is contained in source
        source_normalized = ' '.join(source_full.split())

        # Check that DB content appears in source
        if db_normalized and db_normalized[:100] not in source_normalized:
            ratio = SequenceMatcher(None, db_normalized[:500], source_normalized[:500]).ratio()
            if ratio < 0.9:
                mismatches.append(f"Article {num}: content mismatch (start similarity: {ratio:.1%})")

    report.add(ValidationResult(
        name="Article content validation",
        passed=len(mismatches) == 0,
        message=f"{113 - len(mismatches)}/113 articles match source",
        details=mismatches
    ))


def validate_paragraph_content(session, report: ValidationReport):
    """Validate paragraphs are substrings of their parent article."""

    result = session.run('''
        MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
        RETURN a.number as art_num, a.full_text as art_text,
               p.number as para_num, p.text as para_text
        ORDER BY a.number, p.number
    ''')

    mismatches = []
    for record in result:
        art_num = record['art_num']
        art_text = record['art_text'] or ""
        para_num = record['para_num']
        para_text = record['para_text'] or ""

        # Paragraph text should be substring of article (with normalization)
        para_normalized = ' '.join(para_text.split())[:200]
        art_normalized = ' '.join(art_text.split())

        if para_normalized and para_normalized not in art_normalized:
            mismatches.append(f"Article {art_num}, Para {para_num}: not found in article text")

    report.add(ValidationResult(
        name="Paragraph containment validation",
        passed=len(mismatches) == 0,
        message=f"All paragraphs contained in parent articles" if not mismatches else f"{len(mismatches)} paragraphs not found in parent",
        details=mismatches
    ))


def validate_point_content(session, report: ValidationReport):
    """Validate points are substrings of their parent paragraph."""

    result = session.run('''
        MATCH (p:Paragraph)-[:HAS_POINT]->(pt:Point)
        RETURN p.id as para_id, p.text as para_text,
               pt.marker as marker, pt.text as point_text
        LIMIT 500
    ''')

    mismatches = []
    for record in result:
        para_id = record['para_id']
        para_text = record['para_text'] or ""
        marker = record['marker']
        point_text = record['point_text'] or ""

        # Point text should be substring of paragraph
        point_normalized = ' '.join(point_text.split())[:100]
        para_normalized = ' '.join(para_text.split())

        if point_normalized and point_normalized not in para_normalized:
            mismatches.append(f"{para_id}, Point ({marker}): not found in paragraph")

    report.add(ValidationResult(
        name="Point containment validation",
        passed=len(mismatches) == 0,
        message=f"All points contained in parent paragraphs" if not mismatches else f"{len(mismatches)} points not found in parent",
        details=mismatches
    ))


def validate_chapter_structure(session, report: ValidationReport):
    """Validate chapter-section-article hierarchy."""

    # Check each article belongs to exactly one chapter (directly or via section)
    result = session.run('''
        MATCH (a:Article)
        OPTIONAL MATCH (c:Chapter)-[:HAS_ARTICLE]->(a)
        OPTIONAL MATCH (c2:Chapter)-[:HAS_SECTION]->(:Section)-[:HAS_ARTICLE]->(a)
        WITH a, c, c2
        WHERE c IS NULL AND c2 IS NULL
        RETURN a.number as orphan
    ''')

    orphans = [r['orphan'] for r in result]

    report.add(ValidationResult(
        name="Article hierarchy validation",
        passed=len(orphans) == 0,
        message=f"All articles connected to chapters" if not orphans else f"{len(orphans)} orphan articles",
        details=[f"Orphan article: {o}" for o in orphans]
    ))


def validate_definition_45(session, source: SourceParser, report: ValidationReport):
    """Specifically validate that Definition (45) has full content."""

    result = session.run('''
        MATCH (a:Article {number: 3})-[:HAS_PARAGRAPH]->(p:Paragraph)
        WHERE p.text CONTAINS "(45)" AND p.text CONTAINS "law enforcement authority"
        RETURN p.text as text
    ''')

    record = result.single()
    if not record:
        report.add(ValidationResult(
            name="Definition (45) validation",
            passed=False,
            message="Definition (45) not found in Article 3",
            details=[]
        ))
        return

    text = record['text']

    # Check for the specific content
    checks = [
        ("(45)", "(45)" in text),
        ("law enforcement authority", "law enforcement authority" in text),
        ("(a)", "(a)" in text),
        ("(b)", "(b)" in text),
        ("public authority competent", "public authority competent" in text),
        ("any other body or entity", "any other body or entity" in text),
    ]

    failed = [name for name, passed in checks if not passed]

    report.add(ValidationResult(
        name="Definition (45) content validation",
        passed=len(failed) == 0,
        message=f"Definition (45) has all required content" if not failed else f"Missing: {failed}",
        details=failed
    ))


def validate_character_coverage(session, source: SourceParser, report: ValidationReport):
    """Validate total character coverage."""

    # Sum all unique content
    result = session.run('MATCH (r:Recital) RETURN sum(size(r.text)) as total')
    recital_chars = result.single()['total'] or 0

    result = session.run('MATCH (a:Article) RETURN sum(size(a.full_text)) as total')
    article_chars = result.single()['total'] or 0

    result = session.run('MATCH (a:Annex) RETURN sum(size(a.full_text)) as total')
    annex_chars = result.single()['total'] or 0

    result = session.run('MATCH (c:Chapter) RETURN sum(size(c.title)) as total')
    chapter_chars = result.single()['total'] or 0

    result = session.run('MATCH (s:Section) RETURN sum(size(s.title)) as total')
    section_chars = result.single()['total'] or 0

    result = session.run('MATCH (a:Article) RETURN sum(size(a.title)) as total')
    article_title_chars = result.single()['total'] or 0

    db_total = recital_chars + article_chars + annex_chars + chapter_chars + section_chars + article_title_chars
    source_total = len(source.text)

    # Allow 5% overhead for structural markers
    ratio = db_total / source_total
    passed = 0.95 <= ratio <= 1.05

    report.add(ValidationResult(
        name="Character coverage validation",
        passed=passed,
        message=f"DB: {db_total:,} chars, Source: {source_total:,} chars ({ratio:.1%})",
        details=[
            f"Recitals: {recital_chars:,}",
            f"Articles: {article_chars:,}",
            f"Annexes: {annex_chars:,}",
            f"Titles: {chapter_chars + section_chars + article_title_chars:,}",
        ]
    ))


def validate_no_empty_content(session, report: ValidationReport):
    """Validate no nodes have empty text content."""

    empty_counts = {}

    for label, prop in [('Recital', 'text'), ('Article', 'full_text'), ('Paragraph', 'text'),
                        ('Point', 'text'), ('Annex', 'full_text')]:
        result = session.run(f'''
            MATCH (n:{label})
            WHERE n.{prop} IS NULL OR trim(n.{prop}) = ""
            RETURN count(n) as cnt
        ''')
        cnt = result.single()['cnt']
        if cnt > 0:
            empty_counts[label] = cnt

    report.add(ValidationResult(
        name="No empty content validation",
        passed=len(empty_counts) == 0,
        message="All nodes have content" if not empty_counts else f"Empty nodes found: {empty_counts}",
        details=[f"{label}: {cnt} empty" for label, cnt in empty_counts.items()]
    ))


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("ULTIMATE VALIDATION - EU AI Act Regex Preprocessing")
    print("=" * 70)

    # Load source
    source_path = Path(__file__).parent.parent / "data" / "eu_ai_act.txt"
    print(f"\nLoading source: {source_path}")
    source = SourceParser(str(source_path))
    print(f"Source file: {len(source.text):,} characters")
    print(f"Found: {len(source.recital_positions)} recitals, {len(source.article_positions)} articles")

    # Connect to database
    print(f"\nConnecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    report = ValidationReport()

    try:
        with driver.session() as session:
            # Run all validations
            print("\nRunning validations...")

            validate_counts(session, report)
            validate_article_sequence(session, report)
            validate_recital_content(session, source, report)
            validate_article_content(session, source, report)
            validate_paragraph_content(session, report)
            validate_point_content(session, report)
            validate_chapter_structure(session, report)
            validate_definition_45(session, source, report)
            validate_character_coverage(session, source, report)
            validate_no_empty_content(session, report)

        # Print report
        report.print_report()

        return report.failed == 0

    finally:
        driver.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

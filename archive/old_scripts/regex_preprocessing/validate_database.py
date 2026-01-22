#!/usr/bin/env python3
"""
EU AI Act Database Validation Script

This script validates that the data stored in the Neo4j database
matches the source EU AI Act text file. It performs comprehensive
checks to ensure no data was lost during preprocessing.

Validation checks:
1. All recitals present (1-180)
2. All chapters present (I-XIII)
3. All articles present (1-113)
4. All sections present
5. All annexes present (I-XIII)
6. Text content integrity verification
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables (local .env takes priority, override existing)
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


@dataclass
class ValidationResult:
    """Result of a validation check."""
    passed: bool
    message: str
    details: list = None

    def __post_init__(self):
        if self.details is None:
            self.details = []


class DatabaseValidator:
    """Validates Neo4j database against source file."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def validate_all(self, source_file: str) -> list[ValidationResult]:
        """Run all validation checks."""
        results = []

        # Read source file
        print("Reading source file...")
        with open(source_file, 'r', encoding='utf-8') as f:
            source_text = f.read()

        # Run validations
        print("\nRunning validation checks...\n")

        results.append(self.validate_regulation_exists())
        results.append(self.validate_recitals(source_text))
        results.append(self.validate_chapters(source_text))
        results.append(self.validate_articles(source_text))
        results.append(self.validate_sections(source_text))
        results.append(self.validate_annexes(source_text))
        results.append(self.validate_text_content_samples(source_text))
        results.append(self.validate_graph_structure())

        return results

    def validate_regulation_exists(self) -> ValidationResult:
        """Check that the main regulation node exists."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Regulation {document_id: 'eu_ai_act_2024'})
                RETURN r.official_title as title, r.year as year
            """)
            record = result.single()

            if record:
                return ValidationResult(
                    passed=True,
                    message="Regulation node exists",
                    details=[f"Title: {record['title'][:60]}...", f"Year: {record['year']}"]
                )
            else:
                return ValidationResult(
                    passed=False,
                    message="Regulation node NOT found",
                    details=["No Regulation node with document_id='eu_ai_act_2024' exists"]
                )

    def validate_recitals(self, source_text: str) -> ValidationResult:
        """Validate all recitals are in the database."""
        # Find recitals in source
        recital_pattern = re.compile(r'^\((\d+)\)\s*$', re.MULTILINE)
        source_recitals = set(int(m.group(1)) for m in recital_pattern.finditer(source_text))

        # Get recitals from database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (r:Recital)
                RETURN r.number as number
            """)
            db_recitals = set(record['number'] for record in result)

        # Compare
        missing = source_recitals - db_recitals
        extra = db_recitals - source_recitals

        if not missing and not extra:
            return ValidationResult(
                passed=True,
                message=f"All {len(source_recitals)} recitals present",
                details=[f"Recitals 1-{max(source_recitals)} verified"]
            )
        else:
            details = []
            if missing:
                details.append(f"Missing recitals: {sorted(missing)}")
            if extra:
                details.append(f"Extra recitals: {sorted(extra)}")
            return ValidationResult(
                passed=False,
                message=f"Recital mismatch: {len(missing)} missing, {len(extra)} extra",
                details=details
            )

    def validate_chapters(self, source_text: str) -> ValidationResult:
        """Validate all chapters are in the database."""
        # Find chapters in source
        chapter_pattern = re.compile(r'^CHAPTER\s+([IVXLCDM]+)\s*$', re.MULTILINE)
        source_chapters = set(m.group(1) for m in chapter_pattern.finditer(source_text))

        # Get chapters from database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Chapter)
                RETURN c.number as number, c.title as title
            """)
            db_chapters = {}
            for record in result:
                db_chapters[record['number']] = record['title']

        db_chapter_nums = set(db_chapters.keys())

        # Compare
        missing = source_chapters - db_chapter_nums
        extra = db_chapter_nums - source_chapters

        if not missing and not extra:
            details = [f"Chapter {num}: {title[:40]}..." for num, title in sorted(db_chapters.items(), key=lambda x: self._roman_to_int(x[0]))]
            return ValidationResult(
                passed=True,
                message=f"All {len(source_chapters)} chapters present",
                details=details
            )
        else:
            details = []
            if missing:
                details.append(f"Missing chapters: {sorted(missing)}")
            if extra:
                details.append(f"Extra chapters: {sorted(extra)}")
            return ValidationResult(
                passed=False,
                message=f"Chapter mismatch: {len(missing)} missing, {len(extra)} extra",
                details=details
            )

    def validate_articles(self, source_text: str) -> ValidationResult:
        """Validate all articles are in the database."""
        # Find articles in source
        article_pattern = re.compile(r'^Article\s+(\d+)\s*$', re.MULTILINE)
        source_articles = set(int(m.group(1)) for m in article_pattern.finditer(source_text))

        # Get articles from database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Article)
                RETURN a.number as number, a.title as title
            """)
            db_articles = {}
            for record in result:
                db_articles[record['number']] = record['title']

        db_article_nums = set(db_articles.keys())

        # Compare
        missing = source_articles - db_article_nums
        extra = db_article_nums - source_articles

        if not missing and not extra:
            return ValidationResult(
                passed=True,
                message=f"All {len(source_articles)} articles present (1-{max(source_articles)})",
                details=[f"Articles verified: {sorted(source_articles)[:10]}... (showing first 10)"]
            )
        else:
            details = []
            if missing:
                details.append(f"Missing articles: {sorted(missing)}")
            if extra:
                details.append(f"Extra articles: {sorted(extra)}")
            return ValidationResult(
                passed=False,
                message=f"Article mismatch: {len(missing)} missing, {len(extra)} extra",
                details=details
            )

    def validate_sections(self, source_text: str) -> ValidationResult:
        """Validate all sections are in the database."""
        # Find sections in source
        section_pattern = re.compile(r'^SECTION\s+(\d+)\s*$', re.MULTILINE)
        source_sections = list(int(m.group(1)) for m in section_pattern.finditer(source_text))

        # Get sections from database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Section)
                RETURN s.number as number, s.title as title
                ORDER BY s.number
            """)
            db_sections = [(record['number'], record['title']) for record in result]

        if len(source_sections) == len(db_sections):
            return ValidationResult(
                passed=True,
                message=f"All {len(source_sections)} sections present",
                details=[f"Section {num}: {title[:40]}..." for num, title in db_sections[:5]]
            )
        else:
            return ValidationResult(
                passed=False,
                message=f"Section count mismatch: source={len(source_sections)}, db={len(db_sections)}",
                details=[f"Source sections: {source_sections}", f"DB sections: {[s[0] for s in db_sections]}"]
            )

    def validate_annexes(self, source_text: str) -> ValidationResult:
        """Validate all annexes are in the database."""
        # Find annexes in source
        annex_pattern = re.compile(r'^ANNEX\s+([IVXLCDM]+)\s*$', re.MULTILINE)
        source_annexes = set(m.group(1) for m in annex_pattern.finditer(source_text))

        # Get annexes from database
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Annex)
                RETURN a.number as number, a.title as title
            """)
            db_annexes = {}
            for record in result:
                db_annexes[record['number']] = record['title']

        db_annex_nums = set(db_annexes.keys())

        # Compare
        missing = source_annexes - db_annex_nums
        extra = db_annex_nums - source_annexes

        if not missing and not extra:
            details = [f"Annex {num}: {title[:40]}..." for num, title in sorted(db_annexes.items(), key=lambda x: self._roman_to_int(x[0]))]
            return ValidationResult(
                passed=True,
                message=f"All {len(source_annexes)} annexes present",
                details=details
            )
        else:
            details = []
            if missing:
                details.append(f"Missing annexes: {sorted(missing)}")
            if extra:
                details.append(f"Extra annexes: {sorted(extra)}")
            return ValidationResult(
                passed=False,
                message=f"Annex mismatch: {len(missing)} missing, {len(extra)} extra",
                details=details
            )

    def validate_text_content_samples(self, source_text: str) -> ValidationResult:
        """Validate text content by checking samples."""
        samples_verified = 0
        failed_samples = []

        with self.driver.session() as session:
            # Check Article 1 title
            result = session.run("""
                MATCH (a:Article {number: 1})
                RETURN a.title as title
            """)
            record = result.single()
            if record and 'Subject matter' in record['title']:
                samples_verified += 1
            else:
                failed_samples.append("Article 1 title mismatch")

            # Check Article 5 title
            result = session.run("""
                MATCH (a:Article {number: 5})
                RETURN a.title as title
            """)
            record = result.single()
            if record and 'Prohibited AI practices' in record['title']:
                samples_verified += 1
            else:
                failed_samples.append("Article 5 title mismatch")

            # Check recital 1 contains expected content
            result = session.run("""
                MATCH (r:Recital {number: 1})
                RETURN r.text as text
            """)
            record = result.single()
            if record and 'internal market' in record['text'].lower():
                samples_verified += 1
            else:
                failed_samples.append("Recital 1 content mismatch")

            # Check Chapter III title
            result = session.run("""
                MATCH (c:Chapter {number: 'III'})
                RETURN c.title as title
            """)
            record = result.single()
            if record and 'HIGH-RISK' in record['title'].upper():
                samples_verified += 1
            else:
                failed_samples.append("Chapter III title mismatch")

            # Check Annex I title
            result = session.run("""
                MATCH (a:Annex {number: 'I'})
                RETURN a.title as title
            """)
            record = result.single()
            if record and 'harmonisation' in record['title'].lower():
                samples_verified += 1
            else:
                failed_samples.append("Annex I title mismatch")

        if not failed_samples:
            return ValidationResult(
                passed=True,
                message=f"All {samples_verified} content samples verified",
                details=["Article 1 title OK", "Article 5 title OK", "Recital 1 content OK",
                        "Chapter III title OK", "Annex I title OK"]
            )
        else:
            return ValidationResult(
                passed=False,
                message=f"Content verification failed: {len(failed_samples)} issues",
                details=failed_samples
            )

    def validate_graph_structure(self) -> ValidationResult:
        """Validate the graph structure and relationships."""
        issues = []

        with self.driver.session() as session:
            # Check Regulation -> Chapter relationships
            result = session.run("""
                MATCH (r:Regulation)-[:HAS_CHAPTER]->(c:Chapter)
                RETURN count(c) as count
            """)
            chapter_count = result.single()['count']
            if chapter_count == 0:
                issues.append("No HAS_CHAPTER relationships found")

            # Check Chapter -> Article relationships (direct or via Section)
            result = session.run("""
                MATCH (c:Chapter)-[:HAS_ARTICLE]->(a:Article)
                RETURN count(a) as direct_count
            """)
            direct_articles = result.single()['direct_count']

            result = session.run("""
                MATCH (c:Chapter)-[:HAS_SECTION]->(s:Section)-[:HAS_ARTICLE]->(a:Article)
                RETURN count(a) as section_count
            """)
            section_articles = result.single()['section_count']

            total_connected = direct_articles + section_articles
            if total_connected == 0:
                issues.append("No articles connected to chapters")

            # Check Article -> Paragraph relationships
            result = session.run("""
                MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
                RETURN count(p) as count
            """)
            para_count = result.single()['count']

            # Check orphan nodes
            result = session.run("""
                MATCH (a:Article)
                WHERE NOT (()-[:HAS_ARTICLE]->(a))
                RETURN count(a) as orphans
            """)
            orphan_articles = result.single()['orphans']
            if orphan_articles > 0:
                issues.append(f"{orphan_articles} orphan Article nodes found")

            # Check Regulation -> Recital relationships
            result = session.run("""
                MATCH (r:Regulation)-[:HAS_RECITAL]->(rec:Recital)
                RETURN count(rec) as count
            """)
            recital_rel_count = result.single()['count']
            if recital_rel_count == 0:
                issues.append("No HAS_RECITAL relationships found")

            # Check Regulation -> Annex relationships
            result = session.run("""
                MATCH (r:Regulation)-[:HAS_ANNEX]->(a:Annex)
                RETURN count(a) as count
            """)
            annex_rel_count = result.single()['count']
            if annex_rel_count == 0:
                issues.append("No HAS_ANNEX relationships found")

        if not issues:
            return ValidationResult(
                passed=True,
                message="Graph structure valid",
                details=[
                    f"Chapters connected: {chapter_count}",
                    f"Direct articles: {direct_articles}",
                    f"Section articles: {section_articles}",
                    f"Paragraphs: {para_count}",
                    f"Recitals connected: {recital_rel_count}",
                    f"Annexes connected: {annex_rel_count}"
                ]
            )
        else:
            return ValidationResult(
                passed=False,
                message="Graph structure issues found",
                details=issues
            )

    def _roman_to_int(self, roman: str) -> int:
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

    def get_database_statistics(self) -> dict:
        """Get comprehensive statistics from the database."""
        stats = {}

        with self.driver.session() as session:
            # Count all node types
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY count DESC
            """)
            for record in result:
                stats[record['label']] = record['count']

            # Count relationships
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) as type, count(r) as count
                ORDER BY count DESC
            """)
            stats['_relationships'] = {record['type']: record['count'] for record in result}

            # Get article range
            result = session.run("""
                MATCH (a:Article)
                RETURN min(a.number) as min_article, max(a.number) as max_article
            """)
            record = result.single()
            if record:
                stats['article_range'] = f"{record['min_article']}-{record['max_article']}"

            # Get recital range
            result = session.run("""
                MATCH (r:Recital)
                RETURN min(r.number) as min_recital, max(r.number) as max_recital
            """)
            record = result.single()
            if record:
                stats['recital_range'] = f"{record['min_recital']}-{record['max_recital']}"

        return stats


def print_results(results: list[ValidationResult]):
    """Print validation results in a formatted way."""
    print("\n" + "=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    passed = 0
    failed = 0

    for result in results:
        status = "[PASS]" if result.passed else "[FAIL]"
        color = "\033[92m" if result.passed else "\033[91m"
        reset = "\033[0m"

        print(f"\n{color}{status}{reset} {result.message}")
        for detail in result.details:
            print(f"       {detail}")

        if result.passed:
            passed += 1
        else:
            failed += 1

    print("\n" + "-" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(results)} checks")

    if failed == 0:
        print("\n\033[92m*** ALL VALIDATIONS PASSED ***\033[0m")
    else:
        print(f"\n\033[91m*** {failed} VALIDATION(S) FAILED ***\033[0m")

    return failed == 0


def main():
    """Main validation function."""
    print("=" * 70)
    print("EU AI Act Database Validation")
    print("=" * 70)

    # Paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    source_file = project_dir / "data" / "eu_ai_act.txt"

    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}")
        sys.exit(1)

    print(f"\nSource file: {source_file}")
    print(f"Neo4j URI: {NEO4J_URI}")

    # Create validator
    validator = DatabaseValidator(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Test connection
        with validator.driver.session() as session:
            result = session.run("RETURN 1")
            result.single()
        print("Database connection: OK\n")

        # Get statistics first
        print("Database Statistics:")
        print("-" * 40)
        stats = validator.get_database_statistics()
        for key, value in stats.items():
            if key.startswith('_'):
                continue
            print(f"  {key}: {value}")

        if '_relationships' in stats:
            print("\nRelationships:")
            for rel_type, count in stats['_relationships'].items():
                print(f"  {rel_type}: {count}")

        # Run validations
        results = validator.validate_all(str(source_file))

        # Print results
        all_passed = print_results(results)

        return 0 if all_passed else 1

    except Exception as e:
        print(f"\nError during validation: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        validator.close()


if __name__ == "__main__":
    sys.exit(main())

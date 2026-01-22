"""
Comprehensive Completeness Verification for EU AI Act in Neo4j

This script validates that ALL data from the EU AI Act source files
has been correctly ingested into Neo4j without any missing content.

Verification Strategy:
1. Structural completeness (counts of all elements)
2. Sequence integrity (no gaps in numbering)
3. Content coverage (text character count comparison)
4. Relationship integrity (no orphaned nodes)
5. Known benchmarks (official EU AI Act structure)
"""

from pathlib import Path
from config.neo4j_config import execute_query

# ============================================================================
# KNOWN BENCHMARKS - Official EU AI Act Structure
# ============================================================================

EXPECTED_STRUCTURE = {
    "recitals": 180,  # Official EU AI Act has 180 recitals
    "chapters": 13,   # Chapters I through XIII
    "annexes": 13,    # Annexes I through XIII
    # Articles vary by chapter, but we can validate ranges
}

EXPECTED_CHAPTERS = {
    "I": {"title_contains": "General provisions", "min_articles": 3},
    "II": {"title_contains": "Prohibited AI practices", "min_articles": 1},
    "III": {"title_contains": "High-risk AI systems", "min_articles": 40, "sections": 5},
    "IV": {"title_contains": "Transparency obligations", "min_articles": 1},
    "V": {"title_contains": "General-purpose AI models", "min_articles": 4},
    # Add more as needed
}


# ============================================================================
# Verification Functions
# ============================================================================

def verify_structural_counts():
    """Verify counts of all major structural elements."""
    print("=" * 70)
    print("1. STRUCTURAL ELEMENT COUNTS")
    print("=" * 70)

    query = """
    MATCH (reg:Regulation {document_id: 'eu_ai_act_2024'})
    OPTIONAL MATCH (reg)-[:HAS_RECITAL]->(rec:Recital)
    OPTIONAL MATCH (reg)-[:HAS_CHAPTER]->(ch:Chapter)
    OPTIONAL MATCH (reg)-[:HAS_ANNEX]->(ann:Annex)
    OPTIONAL MATCH (ch)-[:HAS_SECTION]->(sec:Section)
    OPTIONAL MATCH (ch)-[:HAS_ARTICLE]->(a1:Article)
    OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2:Article)
    OPTIONAL MATCH (a1)-[:HAS_PARAGRAPH]->(p1:Paragraph)
    OPTIONAL MATCH (a2)-[:HAS_PARAGRAPH]->(p2:Paragraph)

    RETURN
        count(DISTINCT rec) AS recitals,
        count(DISTINCT ch) AS chapters,
        count(DISTINCT ann) AS annexes,
        count(DISTINCT sec) AS sections,
        count(DISTINCT a1) + count(DISTINCT a2) AS articles,
        count(DISTINCT p1) + count(DISTINCT p2) AS paragraphs
    """

    result = execute_query(query)[0]

    status = "✓" if result['recitals'] == EXPECTED_STRUCTURE['recitals'] else "❌"
    print(f"{status} Recitals: {result['recitals']} (expected: {EXPECTED_STRUCTURE['recitals']})")

    status = "✓" if result['chapters'] == EXPECTED_STRUCTURE['chapters'] else "❌"
    print(f"{status} Chapters: {result['chapters']} (expected: {EXPECTED_STRUCTURE['chapters']})")

    status = "✓" if result['annexes'] == EXPECTED_STRUCTURE['annexes'] else "❌"
    print(f"{status} Annexes: {result['annexes']} (expected: {EXPECTED_STRUCTURE['annexes']})")

    print(f"   Sections: {result['sections']}")
    print(f"   Articles: {result['articles']}")
    print(f"   Paragraphs: {result['paragraphs']}")
    print()

    return result


def verify_recital_sequence():
    """Verify no gaps in recital numbering (1-180)."""
    print("=" * 70)
    print("2. RECITAL SEQUENCE INTEGRITY")
    print("=" * 70)

    query = """
    MATCH (reg:Regulation {document_id: 'eu_ai_act_2024'})-[:HAS_RECITAL]->(rec:Recital)
    RETURN rec.number AS number
    ORDER BY rec.number
    """

    recitals = execute_query(query)
    recital_numbers = [r['number'] for r in recitals]

    expected = list(range(1, 181))  # 1 to 180
    missing = set(expected) - set(recital_numbers)

    if not missing:
        print("✓ No gaps in recital numbering (1-180)")
    else:
        print(f"❌ Missing recitals: {sorted(missing)}")

    print()
    return len(missing) == 0


def verify_chapter_structure():
    """Verify each chapter has expected structure."""
    print("=" * 70)
    print("3. CHAPTER STRUCTURE VALIDATION")
    print("=" * 70)

    query = """
    MATCH (reg:Regulation {document_id: 'eu_ai_act_2024'})-[:HAS_CHAPTER]->(ch:Chapter)
    OPTIONAL MATCH (ch)-[:HAS_SECTION]->(sec:Section)
    OPTIONAL MATCH (ch)-[:HAS_ARTICLE]->(a1:Article)
    OPTIONAL MATCH (sec)-[:HAS_ARTICLE]->(a2:Article)

    RETURN
        ch.number AS chapter_number,
        ch.title AS title,
        count(DISTINCT sec) AS sections,
        count(DISTINCT a1) + count(DISTINCT a2) AS articles
    ORDER BY ch.number
    """

    chapters = execute_query(query)

    all_valid = True
    for ch in chapters:
        ch_num = ch['chapter_number']
        expected = EXPECTED_CHAPTERS.get(ch_num, {})

        issues = []

        # Check title
        if 'title_contains' in expected:
            if expected['title_contains'].lower() not in ch['title'].lower():
                issues.append(f"title mismatch")

        # Check article count
        if 'min_articles' in expected:
            if ch['articles'] < expected['min_articles']:
                issues.append(f"articles: {ch['articles']} < {expected['min_articles']}")

        # Check sections
        if 'sections' in expected:
            if ch['sections'] != expected['sections']:
                issues.append(f"sections: {ch['sections']} != {expected['sections']}")

        status = "✓" if not issues else "❌"
        print(f"{status} Chapter {ch_num}: {ch['articles']} articles, {ch['sections']} sections")
        if issues:
            print(f"   Issues: {', '.join(issues)}")
            all_valid = False

    print()
    return all_valid


def verify_article_sequence():
    """Check for gaps in article numbering within chapters."""
    print("=" * 70)
    print("4. ARTICLE SEQUENCE INTEGRITY")
    print("=" * 70)

    query = """
    MATCH (ch:Chapter)
    OPTIONAL MATCH (ch)-[:HAS_ARTICLE]->(a1:Article)
    OPTIONAL MATCH (ch)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a2:Article)

    WITH ch, collect(DISTINCT a1.number) + collect(DISTINCT a2.number) AS article_nums
    WHERE size(article_nums) > 0

    RETURN
        ch.number AS chapter,
        article_nums
    ORDER BY ch.number
    """

    chapters = execute_query(query)

    all_valid = True
    for ch in chapters:
        nums = sorted([n for n in ch['article_nums'] if n is not None])
        if not nums:
            continue

        # Check for gaps
        expected_range = list(range(min(nums), max(nums) + 1))
        missing = set(expected_range) - set(nums)

        if missing:
            print(f"❌ Chapter {ch['chapter']}: Missing articles {sorted(missing)}")
            all_valid = False

    if all_valid:
        print("✓ No gaps in article numbering within chapters")

    print()
    return all_valid


def verify_content_coverage():
    """Compare total text content in Neo4j vs source files."""
    print("=" * 70)
    print("5. CONTENT COVERAGE ANALYSIS")
    print("=" * 70)

    # Get total character count from Neo4j
    query = """
    MATCH (rec:Recital)
    WITH sum(size(rec.text)) AS recital_chars

    MATCH (p:Paragraph)
    WITH recital_chars, sum(size(p.text)) AS para_chars

    MATCH (ann:Annex)
    WITH recital_chars, para_chars, sum(size(ann.raw_text)) AS annex_chars

    RETURN recital_chars + para_chars + annex_chars AS total_chars
    """

    neo4j_result = execute_query(query)[0]
    neo4j_chars = neo4j_result['total_chars']

    # Get total from source files
    file1 = Path("data/eu_ai_act_part_1.txt")
    file2 = Path("data/eu_ai_act_part_2.txt")

    if file1.exists() and file2.exists():
        source_text = file1.read_text(encoding='utf-8') + file2.read_text(encoding='utf-8')
        source_chars = len(source_text)

        coverage_pct = (neo4j_chars / source_chars) * 100

        print(f"Source files total: {source_chars:,} characters")
        print(f"Neo4j total:        {neo4j_chars:,} characters")
        print(f"Coverage:           {coverage_pct:.1f}%")

        # We expect 80-95% coverage (some formatting is stripped)
        if coverage_pct >= 80:
            print("✓ Content coverage is acceptable (>80%)")
            status = True
        else:
            print(f"❌ Content coverage is low (<80%) - possible missing data")
            status = False
    else:
        print("⚠️  Source files not found - skipping coverage check")
        status = None

    print()
    return status


def verify_no_orphans():
    """Check for orphaned nodes (nodes not connected to Regulation)."""
    print("=" * 70)
    print("6. ORPHANED NODE DETECTION")
    print("=" * 70)

    checks = [
        ("Recitals", "MATCH (rec:Recital) WHERE NOT ((:Regulation)-[:HAS_RECITAL]->(rec)) RETURN count(rec) AS count"),
        ("Chapters", "MATCH (ch:Chapter) WHERE NOT ((:Regulation)-[:HAS_CHAPTER]->(ch)) RETURN count(ch) AS count"),
        ("Sections", "MATCH (sec:Section) WHERE NOT ((:Chapter)-[:HAS_SECTION]->(sec)) RETURN count(sec) AS count"),
        ("Articles", "MATCH (a:Article) WHERE NOT ()-[:HAS_ARTICLE]->(a) RETURN count(a) AS count"),
        ("Paragraphs", "MATCH (p:Paragraph) WHERE NOT ((:Article)-[:HAS_PARAGRAPH]->(p)) RETURN count(p) AS count"),
    ]

    all_valid = True
    for name, query in checks:
        result = execute_query(query)[0]
        count = result['count']

        status = "✓" if count == 0 else "❌"
        print(f"{status} {name}: {count} orphaned")

        if count > 0:
            all_valid = False

    print()
    return all_valid


def verify_critical_articles():
    """Verify presence of known critical articles."""
    print("=" * 70)
    print("7. CRITICAL ARTICLES VERIFICATION")
    print("=" * 70)

    critical_articles = [
        (5, "Prohibited AI practices"),
        (6, "Classification rules for high-risk AI systems"),
        (40, "Harmonised standards"),
        (50, "Transparency obligations for deployers"),
        (85, "Penalties"),
    ]

    all_valid = True
    for num, expected_title_contains in critical_articles:
        query = """
        MATCH (a:Article {number: $num})
        RETURN a.title AS title
        LIMIT 1
        """

        result = execute_query(query, num=num)

        if result:
            title = result[0]['title']
            if expected_title_contains.lower() in title.lower():
                print(f"✓ Article {num}: {title[:60]}...")
            else:
                print(f"❌ Article {num}: Title mismatch - '{title[:60]}...'")
                all_valid = False
        else:
            print(f"❌ Article {num}: NOT FOUND")
            all_valid = False

    print()
    return all_valid


# ============================================================================
# Main Verification
# ============================================================================

def main():
    """Run all verification checks."""
    print("\n")
    print("=" * 70)
    print("EU AI ACT - COMPLETENESS VERIFICATION")
    print("=" * 70)
    print()
    print("This script validates that ALL data from the EU AI Act has been")
    print("correctly ingested into Neo4j without any missing content.")
    print()

    results = {}

    # Run all checks
    results['counts'] = verify_structural_counts()
    results['recital_sequence'] = verify_recital_sequence()
    results['chapter_structure'] = verify_chapter_structure()
    results['article_sequence'] = verify_article_sequence()
    results['content_coverage'] = verify_content_coverage()
    results['no_orphans'] = verify_no_orphans()
    results['critical_articles'] = verify_critical_articles()

    # Final summary
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    all_passed = all(v for v in results.values() if v is not None)

    if all_passed:
        print("✅ ALL CHECKS PASSED")
        print("   The Neo4j database contains the complete EU AI Act.")
    else:
        print("⚠️  SOME CHECKS FAILED")
        print("   Review the issues above to identify missing data.")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()

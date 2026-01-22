"""
Validation script for EU AI Act preprocessing.

Outputs a clear table showing expected vs actual structure in Neo4j.
"""

from config.neo4j_config import execute_query
from pathlib import Path
import re

DOCUMENT_ID = "eu_ai_act_2024"

# Expected structure based on source files
EXPECTED_STRUCTURE = {
    "recitals": 180,
    "chapters": 13,
    "articles_total": 113,
    "chapters_detail": {
        "I": {"articles": [1, 2, 3, 4], "title": "General provisions"},
        "II": {"articles": [5], "title": "Prohibited AI practices"},
        "III": {"articles": list(range(6, 50)), "title": "High-risk AI systems"},  # 6-49 = 44 articles
        "IV": {"articles": [50], "title": "Transparency obligations"},
        "V": {"articles": [51, 52, 53, 54, 55, 56], "title": "General-purpose AI models"},
        "VI": {"articles": [57, 58, 59, 60, 61, 62, 63], "title": "Measures in support of innovation"},
        "VII": {"articles": list(range(64, 75)), "title": "Governance"},  # 64-74 = 11 articles
        "VIII": {"articles": [75], "title": "EU database for high-risk AI systems"},
        "IX": {"articles": list(range(76, 105)), "title": "Post-market monitoring"},  # 76-104 = 29 articles
        "X": {"articles": [105, 106], "title": "Codes of conduct and guidelines"},
        "XI": {"articles": [107, 108], "title": "Delegation of powers"},
        "XII": {"articles": [109, 110, 111], "title": "Penalties"},
        "XIII": {"articles": list(range(112, 114)), "title": "Final provisions"},  # 112-113 = 2 articles
    }
}


def count_articles_in_source() -> int:
    """Count article numbers in source files."""
    file1 = Path("data/eu_ai_act_part_1.txt")
    file2 = Path("data/eu_ai_act_part_2.txt")

    if not file1.exists() or not file2.exists():
        return 113  # Default expected count

    text = file1.read_text() + "\n" + file2.read_text()
    article_pattern = re.compile(r'^Article\s+(\d+)', re.MULTILINE)
    article_numbers = set(int(m) for m in article_pattern.findall(text))

    return len(article_numbers)


def get_neo4j_counts():
    """Get all structure counts from Neo4j."""
    query = """
    MATCH (r:Regulation {document_id: $document_id})
    OPTIONAL MATCH (r)-[:HAS_RECITAL]->(rec:Recital)
    OPTIONAL MATCH (r)-[:HAS_CHAPTER]->(ch:Chapter)
    OPTIONAL MATCH (ch)-[:HAS_SECTION]->(s:Section)
    OPTIONAL MATCH (ch)-[:HAS_SECTION|HAS_ARTICLE*..2]->(a:Article)
    OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
    RETURN
        count(DISTINCT rec) AS recitals,
        count(DISTINCT ch) AS chapters,
        count(DISTINCT s) AS sections,
        count(DISTINCT a) AS articles,
        count(DISTINCT p) AS paragraphs
    """
    result = execute_query(query, document_id=DOCUMENT_ID)
    return result[0] if result else {}


def get_articles_by_chapter():
    """Get article numbers grouped by chapter from Neo4j."""
    query = """
    MATCH (ch:Chapter)-[:HAS_SECTION|HAS_ARTICLE*..2]->(a:Article)
    RETURN ch.number AS chapter, collect(DISTINCT a.number) AS articles
    ORDER BY ch.number
    """
    results = execute_query(query)

    chapter_articles = {}
    for r in results:
        chapter_articles[r['chapter']] = sorted(r['articles'])

    return chapter_articles


def get_missing_articles():
    """Get list of missing article numbers."""
    query = """
    MATCH (a:Article)
    RETURN collect(DISTINCT a.number) AS present_articles
    """
    result = execute_query(query)
    present = set(result[0]['present_articles']) if result else set()

    all_expected = set(range(1, 114))  # Articles 1-113
    missing = sorted(all_expected - present)

    return missing, len(present)


def status_symbol(expected, actual):
    """Return status symbol based on completeness."""
    if actual == 0:
        return "❌"
    elif actual == expected:
        return "✅"
    else:
        pct = (actual / expected) * 100
        if pct >= 90:
            return "⚠️"
        else:
            return "❌"


def format_article_range(articles):
    """Format list of articles as compact ranges."""
    if not articles:
        return "None"

    # Group consecutive articles
    ranges = []
    start = articles[0]
    end = articles[0]

    for num in articles[1:]:
        if num == end + 1:
            end = num
        else:
            if start == end:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{end}")
            start = num
            end = num

    # Add final range
    if start == end:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{end}")

    return ", ".join(ranges)


def print_header():
    """Print report header."""
    print("\n" + "=" * 80)
    print("EU AI ACT - STRUCTURE VALIDATION REPORT")
    print("=" * 80)
    print()


def print_overall_summary(counts, missing_articles, present_count):
    """Print overall summary table."""
    source_articles = count_articles_in_source()

    print("OVERALL SUMMARY")
    print("-" * 80)
    print()
    print(f"{'Element':<20} {'Expected':>12} {'Actual':>12} {'Status':>8}")
    print("-" * 54)

    # Recitals
    expected_rec = EXPECTED_STRUCTURE["recitals"]
    actual_rec = counts.get('recitals', 0)
    print(f"{'Recitals':<20} {expected_rec:>12} {actual_rec:>12} {status_symbol(expected_rec, actual_rec):>8}")

    # Chapters
    expected_ch = EXPECTED_STRUCTURE["chapters"]
    actual_ch = counts.get('chapters', 0)
    print(f"{'Chapters':<20} {expected_ch:>12} {actual_ch:>12} {status_symbol(expected_ch, actual_ch):>8}")

    # Sections
    actual_sec = counts.get('sections', 0)
    print(f"{'Sections':<20} {'~16':>12} {actual_sec:>12} {('✅' if actual_sec >= 15 else '⚠️'):>8}")

    # Articles
    expected_art = source_articles
    actual_art = present_count
    print(f"{'Articles':<20} {expected_art:>12} {actual_art:>12} {status_symbol(expected_art, actual_art):>8}")

    # Paragraphs
    actual_para = counts.get('paragraphs', 0)
    print(f"{'Paragraphs':<20} {'~600+':>12} {actual_para:>12} {('✅' if actual_para >= 400 else '⚠️'):>8}")

    print()

    # Coverage percentage
    coverage_pct = (actual_art / expected_art * 100) if expected_art > 0 else 0
    print(f"📊 Article Coverage: {coverage_pct:.1f}% ({actual_art}/{expected_art})")

    if missing_articles:
        print(f"❌ Missing Articles: {len(missing_articles)}")
        print(f"   {missing_articles}")
    else:
        print("✅ All articles present!")

    print()


def print_chapter_breakdown(chapter_articles):
    """Print detailed chapter-by-chapter breakdown."""
    print("\nCHAPTER-BY-CHAPTER BREAKDOWN")
    print("-" * 80)
    print()
    print(f"{'Chapter':<8} {'Expected':>10} {'Actual':>10} {'Status':>8}  {'Articles Present'}")
    print("-" * 80)

    for chapter_num in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"]:
        expected_info = EXPECTED_STRUCTURE["chapters_detail"][chapter_num]
        expected_articles = expected_info["articles"]
        expected_count = len(expected_articles)

        actual_articles = chapter_articles.get(chapter_num, [])
        actual_count = len(actual_articles)

        status = status_symbol(expected_count, actual_count)
        article_range = format_article_range(actual_articles)

        print(f"{chapter_num:<8} {expected_count:>10} {actual_count:>10} {status:>8}  {article_range}")

    print()


def print_critical_issues(chapter_articles):
    """Print critical issues that need attention."""
    print("\nCRITICAL ISSUES")
    print("-" * 80)
    print()

    issues_found = False

    # Check each chapter for completeness
    for chapter_num, expected_info in EXPECTED_STRUCTURE["chapters_detail"].items():
        expected_articles = set(expected_info["articles"])
        actual_articles = set(chapter_articles.get(chapter_num, []))
        missing = expected_articles - actual_articles

        if missing:
            issues_found = True
            title = expected_info["title"]
            missing_count = len(missing)
            missing_str = format_article_range(sorted(missing))

            print(f"❌ Chapter {chapter_num}: {title}")
            print(f"   Missing {missing_count} article(s): {missing_str}")
            print()

    if not issues_found:
        print("✅ No critical issues found!")
        print()


def main():
    """Run validation and print report."""
    print_header()

    # Get data from Neo4j
    counts = get_neo4j_counts()
    chapter_articles = get_articles_by_chapter()
    missing_articles, present_count = get_missing_articles()

    # Print sections
    print_overall_summary(counts, missing_articles, present_count)
    print_chapter_breakdown(chapter_articles)
    print_critical_issues(chapter_articles)

    # Final verdict
    print("=" * 80)
    if not missing_articles:
        print("✅ VALIDATION PASSED: All articles present and accounted for!")
    else:
        coverage = (present_count / 113) * 100
        print(f"⚠️  VALIDATION INCOMPLETE: {coverage:.1f}% coverage ({present_count}/113 articles)")
    print("=" * 80)
    print()


# ============================================================================
# COVERAGE CHECK UTILITIES (Overlapping Window Validation)
# ============================================================================

def build_extraction_index(preprocessed_doc):
    """
    Build an index of extracted articles from PreprocessedLegalDocument.

    Returns:
        Dict mapping (chapter_number, article_number) -> Article object
    """
    index = {}

    for chapter in preprocessed_doc.chapters:
        # Direct articles under chapter
        for article in chapter.articles:
            key = (chapter.number, article.number)
            index[key] = article

        # Articles under sections
        for section in chapter.sections:
            for article in section.articles:
                key = (chapter.number, article.number)
                index[key] = article

    return index


def extract_articles_from_source(chapter_text: str) -> list:
    """
    Extract article boundaries from source text.

    Returns:
        List of dicts: [{"number": int, "text": str, "start": int, "end": int}]
    """
    article_pattern = re.compile(
        r'^(Article\s+(\d+).*?)(?=^Article\s+\d+|\Z)',
        re.MULTILINE | re.DOTALL
    )

    articles = []
    for match in article_pattern.finditer(chapter_text):
        article_num = int(match.group(2))
        article_text = match.group(1).strip()
        articles.append({
            "number": article_num,
            "text": article_text,
            "start": match.start(),
            "end": match.end()
        })

    return articles


def generate_overlapping_windows(articles: list, window_size: int = 10, stride: int = 7):
    """
    Generate overlapping windows of articles.

    Args:
        articles: List of article dicts from extract_articles_from_source
        window_size: Number of articles per window (default: 10)
        stride: Number of articles to skip between windows (default: 7)

    Returns:
        List of windows: [{"articles": [list], "article_numbers": [list]}]
    """
    windows = []

    for start_idx in range(0, len(articles), stride):
        end_idx = min(start_idx + window_size, len(articles))
        window_articles = articles[start_idx:end_idx]

        if window_articles:
            windows.append({
                "articles": window_articles,
                "article_numbers": [a["number"] for a in window_articles],
                "start_idx": start_idx,
                "end_idx": end_idx
            })

        # Stop if we've covered all articles
        if end_idx >= len(articles):
            break

    return windows


async def check_window_coverage(window_text: str, expected_articles: list, chapter_num: str):
    """
    Run lightweight coverage check on a window of text.

    Uses a simple LLM call to extract article numbers present in the text.

    Args:
        window_text: Text of the window
        expected_articles: List of article numbers that should be in this window
        chapter_num: Chapter number (e.g., "IX")

    Returns:
        List of article numbers found in the window
    """
    # Import here to avoid circular dependencies
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic import BaseModel

    class CoverageResult(BaseModel):
        """Article numbers found in text."""
        article_numbers: list[int]

    # Lightweight model for coverage check
    model = OpenAIChatModel(model_name="gpt-5-nano")

    coverage_agent = Agent(
        model,
        output_type=CoverageResult,
        instructions="""You are a coverage checker for legal documents.

Your ONLY task is to identify which Article numbers are present in the provided text.

DO NOT extract full structure - just list the Article numbers you see.

Example:
Text: "Article 76\n\nFoo...\n\nArticle 77\n\nBar..."
Output: {"article_numbers": [76, 77]}

Be thorough - scan the ENTIRE text for all Article numbers."""
    )

    prompt = f"""Scan this text from Chapter {chapter_num} and list ALL Article numbers present.

Expected articles in this window: {expected_articles}

Text:
{window_text}

Return the article numbers you actually found in the text."""

    try:
        result = await coverage_agent.run(prompt)
        return result.output.article_numbers
    except Exception as e:
        print(f"⚠️  Coverage check failed for window: {e}")
        return []


def find_missing_articles(extraction_index: dict, source_articles: list, chapter_num: str) -> list:
    """
    Compare extraction index against source to find missing articles.

    Args:
        extraction_index: Index from build_extraction_index()
        source_articles: Articles from extract_articles_from_source()
        chapter_num: Chapter number to check

    Returns:
        List of missing article numbers
    """
    expected_numbers = {a["number"] for a in source_articles}
    extracted_numbers = {
        art_num for (ch, art_num) in extraction_index.keys()
        if ch == chapter_num
    }

    missing = sorted(expected_numbers - extracted_numbers)
    return missing


async def coverage_check_chapter(
    chapter_num: str,
    chapter_text: str,
    preprocessed_doc,
    window_size: int = 10,
    stride: int = 7
):
    """
    Run full coverage check on a chapter using overlapping windows.

    Args:
        chapter_num: Chapter number (e.g., "IX")
        chapter_text: Source text of the chapter
        preprocessed_doc: PreprocessedLegalDocument from primary extraction
        window_size: Articles per window (default: 10)
        stride: Articles between windows (default: 7)

    Returns:
        Dict with:
          - missing_articles: List of article numbers not found
          - coverage_results: Detailed results per window
    """
    print(f"\n🔍 Running coverage check on Chapter {chapter_num}")
    print(f"   Window size: {window_size}, Stride: {stride}")

    # Step 1: Build index from extraction
    extraction_index = build_extraction_index(preprocessed_doc)

    # Step 2: Extract articles from source
    source_articles = extract_articles_from_source(chapter_text)
    print(f"   Found {len(source_articles)} articles in source")

    # Step 3: Initial diff
    missing_articles = find_missing_articles(extraction_index, source_articles, chapter_num)
    print(f"   Missing from extraction: {missing_articles}")

    if not missing_articles:
        print("   ✅ No missing articles!")
        return {"missing_articles": [], "coverage_results": []}

    # Step 4: Generate overlapping windows
    windows = generate_overlapping_windows(source_articles, window_size, stride)
    print(f"   Generated {len(windows)} overlapping windows")

    # Step 5: Check coverage in each window (only for windows with missing articles)
    coverage_results = []

    for i, window in enumerate(windows):
        # Check if this window contains any missing articles
        window_missing = set(window["article_numbers"]) & set(missing_articles)

        if not window_missing:
            # Skip windows that don't contain missing articles
            continue

        print(f"   Checking window {i+1}/{len(windows)}: Articles {window['article_numbers'][0]}-{window['article_numbers'][-1]}")

        # Build window text
        window_text = "\n\n".join(a["text"] for a in window["articles"])

        # Run coverage check
        found_articles = await check_window_coverage(
            window_text,
            window["article_numbers"],
            chapter_num
        )

        coverage_results.append({
            "window_idx": i,
            "expected": window["article_numbers"],
            "found": found_articles,
            "missing_in_window": sorted(set(window["article_numbers"]) - set(found_articles))
        })

    # Step 6: Aggregate results
    print(f"\n   📊 Coverage Check Results:")
    for result in coverage_results:
        if result["missing_in_window"]:
            print(f"      Window {result['window_idx']}: Missing {result['missing_in_window']}")

    return {
        "missing_articles": missing_articles,
        "coverage_results": coverage_results
    }


# ============================================================================
# CLI ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    import sys
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="EU AI Act Structure Validation")
    parser.add_argument("--mode", choices=["validation", "coverage_check"], default="validation",
                        help="Mode: validation (default) or coverage_check")
    parser.add_argument("--window", type=int, default=10,
                        help="Window size for coverage check (default: 10)")
    parser.add_argument("--stride", type=int, default=7,
                        help="Stride for coverage check (default: 7)")
    parser.add_argument("--chapter", type=str, default=None,
                        help="Chapter to check (e.g., 'IX'), or None for all")

    args = parser.parse_args()

    if args.mode == "validation":
        # Standard validation mode
        main()

    elif args.mode == "coverage_check":
        # Coverage check mode
        print("\n" + "=" * 80)
        print("EU AI ACT - COVERAGE CHECK MODE")
        print("=" * 80)
        print()

        # Load source text
        file1 = Path("data/eu_ai_act_part_1.txt")
        file2 = Path("data/eu_ai_act_part_2.txt")

        if not file1.exists() or not file2.exists():
            print("❌ Source files not found!")
            sys.exit(1)

        full_text = file1.read_text() + "\n" + file2.read_text()

        # Extract chapter text (simplified - would need proper chapter splitting)
        if args.chapter:
            chapter_pattern = re.compile(
                rf'^CHAPTER {args.chapter}.*?(?=^CHAPTER [IVXL]+|\Z)',
                re.MULTILINE | re.DOTALL | re.IGNORECASE
            )
            match = chapter_pattern.search(full_text)

            if not match:
                print(f"❌ Chapter {args.chapter} not found in source!")
                sys.exit(1)

            chapter_text = match.group(0)

            print(f"Running coverage check on Chapter {args.chapter}")
            print(f"Window size: {args.window}, Stride: {args.stride}\n")

            # For now, we'd need to load the PreprocessedLegalDocument
            # This would come from running the primary extraction first
            print("⚠️  Coverage check requires primary extraction to be run first")
            print("    Use this in conjunction with run_preprocess_eu_ai_act.py")
        else:
            print("❌ --chapter is required for coverage_check mode")
            sys.exit(1)

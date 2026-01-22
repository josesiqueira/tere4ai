"""
Detect Missing Chunks - Map missing articles back to source chunks

This module identifies which preprocessing chunks failed or are incomplete
by analyzing gaps in the article sequence in Neo4j.
"""

from typing import List, Set, Dict
from config.neo4j_config import execute_query


def get_missing_article_numbers() -> Set[int]:
    """
    Identify missing articles by detecting gaps in article numbering.

    Returns:
        Set of missing article numbers
    """
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

    missing_articles = set()

    for ch in chapters:
        nums = sorted([n for n in ch['article_nums'] if n is not None])
        if not nums:
            continue

        # Check for gaps in the sequence
        expected_range = set(range(min(nums), max(nums) + 1))
        actual = set(nums)
        gaps = expected_range - actual

        missing_articles.update(gaps)

    return missing_articles


def map_articles_to_chunks(missing_articles: Set[int]) -> List[str]:
    """
    Map missing article numbers to their source chunk labels.

    The EU AI Act is split into chunks with known patterns:
    - CHAPTER I through XIII (may be split into sections)
    - CHAPTER III is split into SECTION 1-5

    Args:
        missing_articles: Set of missing article numbers

    Returns:
        List of chunk labels to re-process
    """
    # Article number ranges for each chunk (approximate based on EU AI Act structure)
    # This mapping is based on the official EU AI Act structure
    article_to_chunk_map = {
        # Chapter I: Articles 1-4
        (1, 4): "CHAPTER I - General provisions",

        # Chapter II: Article 5
        (5, 5): "CHAPTER II - Prohibited artificial intelligence practices",

        # Chapter III (Sections 1-5): Articles 6-49
        (6, 7): "CHAPTER III - SECTION 1",     # Section 1
        (8, 15): "CHAPTER III - SECTION 2",    # Section 2
        (16, 27): "CHAPTER III - SECTION 3",   # Section 3
        (28, 39): "CHAPTER III - SECTION 4",   # Section 4
        (40, 49): "CHAPTER III - SECTION 5",   # Section 5

        # Chapter IV: Article 50
        (50, 50): "CHAPTER IV - Transparency obligations for providers and deployers of certain AI systems",

        # Chapter V: Articles 51-56
        (51, 56): "CHAPTER V - General-purpose AI models",

        # Chapter VI: Article 57
        (57, 57): "CHAPTER VI - Measures in support of innovation",

        # Chapter VII: Articles 58-64
        (58, 64): "CHAPTER VII - Governance",

        # Chapter VIII: Article 65
        (65, 65): "CHAPTER VIII - EU database for high-risk AI systems",

        # Chapter IX: Articles 66-73
        (66, 73): "CHAPTER IX - Post-market monitoring, information sharing and market surveillance",

        # Chapter X: Articles 74-77
        (74, 77): "CHAPTER X - Codes of conduct and guidelines",

        # Chapter XI: Articles 78-81
        (78, 81): "CHAPTER XI - Delegation of powers and committee procedure",

        # Chapter XII: Articles 82-84
        (82, 84): "CHAPTER XII - Penalties",

        # Chapter XIII: Articles 85-113
        (85, 113): "CHAPTER XIII - Final provisions",
    }

    chunks_to_reprocess = set()

    for article_num in missing_articles:
        # Find which chunk this article belongs to
        for (start, end), chunk_label in article_to_chunk_map.items():
            if start <= article_num <= end:
                chunks_to_reprocess.add(chunk_label)
                break

    return sorted(chunks_to_reprocess)


def get_chunks_to_reprocess() -> List[str]:
    """
    Main function: Detect missing articles and map them to chunks.

    Returns:
        List of chunk labels that need to be re-processed
    """
    missing_articles = get_missing_article_numbers()

    if not missing_articles:
        print("✓ No missing articles detected")
        return []

    print(f"⚠️  Detected {len(missing_articles)} missing articles: {sorted(missing_articles)}")

    chunks = map_articles_to_chunks(missing_articles)

    if chunks:
        print(f"📋 Need to re-process {len(chunks)} chunk(s):")
        for chunk in chunks:
            print(f"   - {chunk}")

    return chunks


if __name__ == "__main__":
    chunks = get_chunks_to_reprocess()
    print(f"\nChunks to re-process: {chunks}")

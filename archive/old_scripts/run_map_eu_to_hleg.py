"""
Map EU AI Act paragraphs to HLEG requirements with rich contextual prompting.

This script:

  1. Selects candidate paragraphs from the EU AI Act:
       - Default: ALL paragraphs in the document (full-corpus mode)
       - Optional filters: chapters, regex patterns, max count
  2. Gathers rich context for each paragraph:
       - Structural headings (chapter, section, article titles)
       - Neighboring paragraphs (previous & next) for context
  3. Calls eu_hleg_mapping_agent (gpt-5-nano) with contextual prompt:
       - Clearly marks TARGET paragraph vs context
       - Receives EuToHlegMapping with HlegLink entries and rationales
  4. Ingests mappings into Neo4j using ingest_eu_hleg_mapping()

CONFIGURATION KNOBS (for testing and tuning):

  - DOCUMENT_ID: EU AI Act document identifier
  - CANDIDATE_REGEX: Optional regex to filter paragraph text (None = all paragraphs)
  - LIMIT_CHAPTERS: Optional list of chapters to process (None = all chapters)
  - MAX_PARAGRAPHS: Optional limit for dry runs (None = process all)
  - MAX_CONCURRENCY: Parallel processing limit (default: 3)
  - MODEL_MAX_TOKENS: Completion token cap per API call
  - DRY_RUN: If True, skip ingestion and only log outputs

TRUSTWORTHINESS:

  - LLM performs semantic alignment decisions with full context
  - Ingestion to Neo4j is deterministic and idempotent
  - Rationales make LLM decisions inspectable and auditable
  - Context-aware prompting improves alignment quality
"""

import asyncio
import re
import time
from typing import List, Optional

from dotenv import load_dotenv

from config.neo4j_config import execute_query, verify_connection
from agent_eu_hleg_mapping import eu_hleg_mapping_agent
from models.eu_hleg_mapping_deps import EuHlegMappingDeps
from ingest_eu_hleg_mapping import ingest_eu_hleg_mapping


# Load env (OPENAI_API_KEY, Neo4j config)
load_dotenv()


# ============================================================================
# CONFIGURATION KNOBS
# ============================================================================

DOCUMENT_ID = "eu_ai_act_2024"

# Candidate selection filters (None = no filter, process all)
CANDIDATE_REGEX: Optional[str] = None  # e.g., r'(?i).*(shall|must|prohibited|risk management).*'
LIMIT_CHAPTERS: Optional[List[str]] = None  # e.g., ['II', 'III', 'IV'] or None for all
MAX_PARAGRAPHS: Optional[int] = None  # e.g., 50 for dry runs, None for full corpus

# Processing controls
MAX_CONCURRENCY = 15  # Parallel processing limit (increased for speed)
MODEL_MAX_TOKENS = 2048  # Completion token cap per API call (reduced for faster responses)

# Dry run mode (skip ingestion, log only)
DRY_RUN = False


# ============================================================================
# Candidate Paragraph Selection with Rich Context
# ============================================================================

def fetch_candidate_paragraphs(document_id: str) -> List[dict]:
    """
    Select candidate EU AI Act paragraphs for mapping with rich context.

    Returns paragraphs with:
      - Structural location: chapter_number, chapter_title, section_number,
        section_title, article_number, article_title, paragraph_index
      - Content: paragraph_text
      - Context: prev_paragraph_text, next_paragraph_text

    Filters applied:
      - LIMIT_CHAPTERS: if set, only include specified chapters
      - CANDIDATE_REGEX: if set, only include paragraphs matching regex
      - MAX_PARAGRAPHS: if set, limit total count
    """
    # Build WHERE clause for filters
    where_clauses = []
    if LIMIT_CHAPTERS:
        chapter_filter = ", ".join([f"'{ch}'" for ch in LIMIT_CHAPTERS])
        where_clauses.append(f"c.number IN [{chapter_filter}]")
    if CANDIDATE_REGEX:
        where_clauses.append(f"p.text =~ '{CANDIDATE_REGEX}'")

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Query to get paragraphs with rich context
    # Handle both structures: Chapter->Article and Chapter->Section->Article
    cypher = f"""
    MATCH (d:Regulation {{document_id: $document_id}})
          -[:HAS_CHAPTER]->(c:Chapter)
    MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
    WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
    OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec:Section)-[:HAS_ARTICLE]->(a)
    {where_clause}

    // Get previous paragraph (if exists)
    OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(prev:Paragraph)
    WHERE prev.number = p.number - 1

    // Get next paragraph (if exists)
    OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(next:Paragraph)
    WHERE next.number = p.number + 1

    RETURN c.number AS chapter_number,
           c.title AS chapter_title,
           sec.number AS section_number,
           sec.title AS section_title,
           a.number AS article_number,
           a.title AS article_title,
           p.number AS paragraph_index,
           p.text AS paragraph_text,
           prev.text AS prev_paragraph_text,
           next.text AS next_paragraph_text
    ORDER BY c.number, COALESCE(sec.number, '0'), a.number, p.number
    """

    if MAX_PARAGRAPHS:
        cypher += f"\nLIMIT {MAX_PARAGRAPHS}"

    records = execute_query(cypher, document_id=document_id)

    results: List[dict] = []
    for rec in records:
        results.append({
            "chapter_number": rec["chapter_number"],
            "chapter_title": rec["chapter_title"],
            "section_number": rec["section_number"],
            "section_title": rec["section_title"],
            "article_number": rec["article_number"],
            "article_title": rec["article_title"],
            "paragraph_index": rec["paragraph_index"],
            "paragraph_text": rec["paragraph_text"],
            "prev_paragraph_text": rec["prev_paragraph_text"],
            "next_paragraph_text": rec["next_paragraph_text"],
        })
    return results


# ============================================================================
# Contextual Prompt Building
# ============================================================================

def build_contextual_prompt(para: dict) -> str:
    """
    Build a rich contextual prompt for the mapping agent.

    Includes:
      - Structural headings (chapter, section, article)
      - TARGET paragraph (the one to label)
      - PREVIOUS and NEXT paragraphs (context only)
    """
    prompt_parts = []

    # Structural context
    prompt_parts.append("STRUCTURAL CONTEXT:")
    prompt_parts.append(f"  Chapter {para['chapter_number']}: {para['chapter_title']}")
    if para['section_number']:
        prompt_parts.append(f"  Section {para['section_number']}: {para['section_title']}")
    prompt_parts.append(f"  Article {para['article_number']}: {para['article_title']}")
    prompt_parts.append(f"  Paragraph {para['paragraph_index']}")
    prompt_parts.append("")

    # Previous paragraph (context only)
    if para['prev_paragraph_text']:
        prompt_parts.append("PREVIOUS PARAGRAPH (context only, do NOT label):")
        prompt_parts.append(f"  {para['prev_paragraph_text']}")
        prompt_parts.append("")

    # Target paragraph (the one to label)
    prompt_parts.append("TARGET PARAGRAPH (classify THIS against HLEG requirements):")
    prompt_parts.append(f"  {para['paragraph_text']}")
    prompt_parts.append("")

    # Next paragraph (context only)
    if para['next_paragraph_text']:
        prompt_parts.append("NEXT PARAGRAPH (context only, do NOT label):")
        prompt_parts.append(f"  {para['next_paragraph_text']}")
        prompt_parts.append("")

    prompt_parts.append("Task: Classify the TARGET paragraph against the seven HLEG requirements of Trustworthy AI.")
    prompt_parts.append("The neighboring paragraphs and structural headings provide context only.")
    prompt_parts.append("Return links ONLY for the TARGET paragraph.")

    return "\n".join(prompt_parts)


# ============================================================================
# Processing Pipeline
# ============================================================================

async def process_one_paragraph(
    para: dict,
    idx: int,
    total: int,
    semaphore: asyncio.Semaphore,
) -> Optional[int]:
    """
    Process one paragraph: call agent, optionally ingest, return link count.

    Args:
        para: Paragraph data with context
        idx: Index of this paragraph (1-based)
        total: Total number of paragraphs
        semaphore: Semaphore to limit concurrency

    Returns:
        Number of links created, or None if failed
    """
    async with semaphore:
        # Build deps
        deps = EuHlegMappingDeps(
            document_id=DOCUMENT_ID,
            chapter_number=para["chapter_number"],
            article_number=str(para["article_number"]),
            paragraph_index=int(para["paragraph_index"]),
        )

        # Build contextual prompt
        prompt = build_contextual_prompt(para)

        # Log progress
        heading = f"Ch {para['chapter_number']}"
        if para['section_number']:
            heading += f", Sec {para['section_number']}"
        heading += f", Art {para['article_number']}, Para {para['paragraph_index']}"
        print(f"[{idx}/{total}] {heading}")

        try:
            # Call agent with max_tokens cap
            result = await eu_hleg_mapping_agent.run(
                prompt,
                deps=deps,
                model_settings={'max_tokens': MODEL_MAX_TOKENS}
            )
            mapping = result.output

            # Show what was found
            num_links = len(mapping.links)
            if num_links > 0:
                print(f"  → Found {num_links} HLEG alignment(s):")
                for link in mapping.links:
                    print(f"     • {link.hleg_requirement_id} (relevance: {link.relevance:.2f})")
            else:
                print(f"  → No alignments found")

            # Ingest (unless dry run)
            if not DRY_RUN:
                ingest_eu_hleg_mapping(mapping)

            return num_links

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None


async def main():
    """
    Entry point: map EU AI Act paragraphs to HLEG requirements.
    """
    start_time = time.time()

    print("=" * 70)
    print("EU→HLEG MAPPING - CONTEXTUAL FULL-CORPUS MODE")
    print("=" * 70)
    print()
    print("Configuration:")
    print(f"  DOCUMENT_ID: {DOCUMENT_ID}")
    print(f"  CANDIDATE_REGEX: {CANDIDATE_REGEX or 'None (all paragraphs)'}")
    print(f"  LIMIT_CHAPTERS: {LIMIT_CHAPTERS or 'None (all chapters)'}")
    print(f"  MAX_PARAGRAPHS: {MAX_PARAGRAPHS or 'None (full corpus)'}")
    print(f"  MAX_CONCURRENCY: {MAX_CONCURRENCY}")
    print(f"  MODEL_MAX_TOKENS: {MODEL_MAX_TOKENS}")
    print(f"  DRY_RUN: {DRY_RUN}")
    print()

    # Verify prerequisites
    print("Prerequisites:")
    print("  ✓ OPENAI_API_KEY in .env file")
    print("  ✓ Neo4j running and populated with:")
    print("      - EU AI Act structure (Regulation/Chapter/Article/Paragraph)")
    print("      - HLEG requirements (HLEGRequirement nodes)")
    print()

    if not verify_connection():
        print("❌ Neo4j connection failed. Check config.neo4j_config.")
        return

    print("✓ Neo4j connection verified.\n")

    # Fetch candidates
    print("Fetching candidate paragraphs...")
    candidates = fetch_candidate_paragraphs(DOCUMENT_ID)
    print(f"Found {len(candidates)} candidate paragraphs.\n")

    if not candidates:
        print("⚠️ No candidates found. Check filters or structural ingestion.")
        return

    # Process with concurrency control
    print("=" * 70)
    print("PROCESSING PARAGRAPHS")
    print("=" * 70)
    print()

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    tasks = [
        process_one_paragraph(para, i, len(candidates), semaphore)
        for i, para in enumerate(candidates, start=1)
    ]

    results = await asyncio.gather(*tasks)

    # Summary statistics
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_processed = len(results)
    total_failures = sum(1 for r in results if r is None)
    total_successes = total_processed - total_failures
    total_links = sum(r for r in results if r is not None)

    print(f"Total paragraphs processed: {total_processed}")
    print(f"Successful: {total_successes}")
    print(f"Failed: {total_failures}")
    print(f"Total alignment links created: {total_links}")

    if DRY_RUN:
        print("\n⚠️ DRY RUN MODE - No data was ingested to Neo4j")
    else:
        print("\n✓ Mappings ingested to Neo4j")

    print()
    print("Verification queries:")
    print("  # Count all alignment relationships:")
    print("  MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)")
    print("  RETURN count(r);")
    print()
    print("  # Sample alignments with details:")
    print("  MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)")
    print("  RETURN p.index, substring(p.text, 0, 100) + '...' AS text,")
    print("         h.name, r.relevance, r.rationale")
    print("  ORDER BY r.relevance DESC")
    print("  LIMIT 10;")
    print()

    # Display elapsed time
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = elapsed_time % 60
    print("=" * 70)
    print(f"⏱️  Total processing time: {minutes}m {seconds:.2f}s")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

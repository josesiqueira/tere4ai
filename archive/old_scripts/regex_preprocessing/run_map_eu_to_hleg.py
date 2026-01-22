#!/usr/bin/env python3
"""
Map EU AI Act Chapter III paragraphs to HLEG requirements AND subtopics.

This script:

  1. Fetches all paragraphs from EU AI Act Chapter III (HIGH-RISK AI SYSTEMS)
  2. Gathers rich context for each paragraph (structural headings, neighbors)
  3. Calls eu_hleg_detailed_mapping_agent with contextual prompt
  4. Ingests mappings into Neo4j (requirement + subtopic relationships)

CONFIGURATION:

  - CHAPTER_NUMBER: Fixed to "III" (High-Risk AI Systems)
  - MAX_PARAGRAPHS: Limit for testing (None = all ~203 paragraphs)
  - MAX_CONCURRENCY: Parallel processing limit
  - DRY_RUN: If True, skip ingestion and only log outputs

TRUSTWORTHINESS:

  - LLM performs semantic alignment with full context
  - Ingestion to Neo4j is deterministic and idempotent
  - Rationales make LLM decisions inspectable
  - Two-level granularity: requirements AND subtopics
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Import from local regex_preprocessing folder
from regex_preprocessing.agent_eu_hleg_mapping import eu_hleg_detailed_mapping_agent
from models.eu_hleg_detailed_mapping import EuHlegDetailedMappingDeps
from regex_preprocessing.ingest_eu_hleg_mapping import (
    ingest_eu_hleg_detailed_mapping,
    clear_existing_mappings,
)

# Load environment variables
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

# Neo4j connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


# ============================================================================
# CONFIGURATION
# ============================================================================

DOCUMENT_ID = "eu_ai_act_2024"
CHAPTER_NUMBER = "III"  # High-Risk AI Systems

# Processing limits
MAX_PARAGRAPHS: Optional[int] = None  # None = all paragraphs, or set to e.g. 10 for testing
MAX_CONCURRENCY = 10  # Parallel processing limit
MODEL_MAX_TOKENS = 2048  # Completion token cap per API call

# Dry run mode
DRY_RUN = False  # Set to True to skip Neo4j ingestion


# ============================================================================
# Neo4j Query Functions
# ============================================================================

def get_driver():
    """Get Neo4j driver instance."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def verify_connection() -> bool:
    """Verify Neo4j connection."""
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run("RETURN 1").single()
        driver.close()
        return True
    except Exception as e:
        print(f"Connection error: {e}")
        return False


def fetch_chapter_iii_paragraphs() -> List[dict]:
    """
    Fetch all paragraphs from Chapter III with rich context.

    Returns paragraphs with:
      - Structural location: chapter_number, chapter_title, section_number,
        section_title, article_number, article_title, paragraph_index
      - Content: paragraph_text
      - Context: prev_paragraph_text, next_paragraph_text
    """
    cypher = """
    MATCH (d:Regulation {document_id: $document_id})
          -[:HAS_CHAPTER]->(c:Chapter {number: $chapter_number})
    MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
    WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
    OPTIONAL MATCH (c)-[:HAS_SECTION]->(sec:Section)-[:HAS_ARTICLE]->(a)

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
    ORDER BY COALESCE(sec.number, 0), a.number, p.number
    """

    driver = get_driver()
    results = []

    try:
        with driver.session() as session:
            records = session.run(
                cypher,
                document_id=DOCUMENT_ID,
                chapter_number=CHAPTER_NUMBER
            )
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
    finally:
        driver.close()

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
        prev_text = para['prev_paragraph_text'][:500]  # Truncate for prompt size
        if len(para['prev_paragraph_text']) > 500:
            prev_text += "..."
        prompt_parts.append(f"  {prev_text}")
        prompt_parts.append("")

    # Target paragraph (the one to label)
    prompt_parts.append("TARGET PARAGRAPH (classify THIS against HLEG requirements and subtopics):")
    prompt_parts.append(f"  {para['paragraph_text']}")
    prompt_parts.append("")

    # Next paragraph (context only)
    if para['next_paragraph_text']:
        prompt_parts.append("NEXT PARAGRAPH (context only, do NOT label):")
        next_text = para['next_paragraph_text'][:500]
        if len(para['next_paragraph_text']) > 500:
            next_text += "..."
        prompt_parts.append(f"  {next_text}")
        prompt_parts.append("")

    prompt_parts.append("Task: Classify the TARGET paragraph against HLEG requirements AND their subtopics.")
    prompt_parts.append("Return requirement_links with subtopic_links where applicable.")
    prompt_parts.append("Neighboring paragraphs provide context only - do NOT label them.")

    return "\n".join(prompt_parts)


# ============================================================================
# Processing Pipeline
# ============================================================================

async def process_one_paragraph(
    para: dict,
    idx: int,
    total: int,
    semaphore: asyncio.Semaphore,
) -> Optional[tuple[int, int]]:
    """
    Process one paragraph: call agent, optionally ingest.

    Returns:
        Tuple of (requirement_links_count, subtopic_links_count), or None if failed
    """
    async with semaphore:
        # Build deps
        deps = EuHlegDetailedMappingDeps(
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
            # Call agent
            result = await eu_hleg_detailed_mapping_agent.run(
                prompt,
                deps=deps,
                model_settings={'max_tokens': MODEL_MAX_TOKENS}
            )
            mapping = result.output

            # Show what was found
            num_reqs = len(mapping.requirement_links)
            num_subs = sum(len(rl.subtopic_links) for rl in mapping.requirement_links)

            if num_reqs > 0:
                print(f"  → Found {num_reqs} requirement(s), {num_subs} subtopic(s):")
                for rl in mapping.requirement_links:
                    print(f"     • {rl.requirement_id} (confidence: {rl.confidence:.2f})")
                    print(f"       Explanation: {rl.explanation[:100]}...")
                    for sl in rl.subtopic_links:
                        print(f"       └─ {sl.subtopic_id} (confidence: {sl.confidence:.2f})")
            else:
                print(f"  → No alignments found")

            # Ingest (unless dry run)
            if not DRY_RUN:
                req_count, sub_count = ingest_eu_hleg_detailed_mapping(mapping)
                return (req_count, sub_count)
            else:
                return (num_reqs, num_subs)

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None


async def main():
    """
    Entry point: map EU AI Act Chapter III to HLEG requirements + subtopics.
    """
    start_time = time.time()

    print("=" * 70)
    print("EU→HLEG DETAILED MAPPING - CHAPTER III")
    print("=" * 70)
    print()
    print("Configuration:")
    print(f"  DOCUMENT_ID: {DOCUMENT_ID}")
    print(f"  CHAPTER_NUMBER: {CHAPTER_NUMBER}")
    print(f"  MAX_PARAGRAPHS: {MAX_PARAGRAPHS or 'None (all paragraphs)'}")
    print(f"  MAX_CONCURRENCY: {MAX_CONCURRENCY}")
    print(f"  MODEL_MAX_TOKENS: {MODEL_MAX_TOKENS}")
    print(f"  DRY_RUN: {DRY_RUN}")
    print()

    # Verify prerequisites
    print("Prerequisites:")
    print("  ✓ OPENAI_API_KEY in .env file")
    print("  ✓ Neo4j running on port 7688 with:")
    print("      - EU AI Act structure (Regulation/Chapter/Article/Paragraph)")
    print("      - HLEG requirements and subtopics")
    print()

    if not verify_connection():
        print("❌ Neo4j connection failed. Check NEO4J_URI and credentials.")
        return

    print("✓ Neo4j connection verified.\n")

    # Fetch candidates
    print("Fetching Chapter III paragraphs...")
    candidates = fetch_chapter_iii_paragraphs()
    print(f"Found {len(candidates)} paragraphs in Chapter III.\n")

    if not candidates:
        print("⚠️ No paragraphs found. Check structural ingestion.")
        return

    # Apply limit if set
    if MAX_PARAGRAPHS:
        candidates = candidates[:MAX_PARAGRAPHS]
        print(f"Limited to {MAX_PARAGRAPHS} paragraphs for this run.\n")

    # Clear existing mappings (unless dry run)
    if not DRY_RUN:
        print("Clearing existing mappings for Chapter III...")
        clear_existing_mappings(CHAPTER_NUMBER)
        print()

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
    total_req_links = sum(r[0] for r in results if r is not None)
    total_sub_links = sum(r[1] for r in results if r is not None)

    print(f"Total paragraphs processed: {total_processed}")
    print(f"Successful: {total_successes}")
    print(f"Failed: {total_failures}")
    print(f"Total requirement links: {total_req_links}")
    print(f"Total subtopic links: {total_sub_links}")

    if DRY_RUN:
        print("\n⚠️ DRY RUN MODE - No data was ingested to Neo4j")
    else:
        print("\n✓ Mappings ingested to Neo4j")

    print()
    print("Verification queries:")
    print("  # Count requirement alignments by requirement:")
    print("  MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)")
    print("  RETURN h.name, count(r) AS alignments ORDER BY alignments DESC;")
    print()
    print("  # Count subtopic alignments:")
    print("  MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_SUBTOPIC]->(s:HLEGSubtopic)")
    print("  RETURN s.label, count(r) AS alignments ORDER BY alignments DESC;")
    print()
    print("  # Sample with both requirement and subtopic links:")
    print("  MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)")
    print("  OPTIONAL MATCH (p)-[rr:ALIGNS_WITH_HLEG_REQUIREMENT]->(req:HLEGRequirement)")
    print("  OPTIONAL MATCH (p)-[rs:ALIGNS_WITH_HLEG_SUBTOPIC]->(sub:HLEGSubtopic)")
    print("  RETURN a.number, p.number,")
    print("         collect(DISTINCT req.name) AS requirements,")
    print("         collect(DISTINCT sub.label) AS subtopics")
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

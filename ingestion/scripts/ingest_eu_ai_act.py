"""
Step 1: Structural Preprocessing of the EU AI Act (Chunked, Parallel)

This script runs the complete preprocessing pipeline for the EU AI Act using
a chunked approach with PARALLEL PROCESSING and large context windows:

1. Reads and merges raw text from eu_ai_act_part_1.txt and eu_ai_act_part_2.txt
2. Splits it deterministically into chunks (recitals, chapters, annexes)
3. Uses gpt-5-nano (400k input / 128k output) to extract structure from each chunk IN PARALLEL
4. Merges all chunks into a single PreprocessedLegalDocument
5. Ingests the structured data into Neo4j deterministically
6. Prints a summary of what was extracted

The chunked preprocessing processes the document in semantically meaningful pieces:
  - One chunk for all recitals (or batches for large recital sets)
  - One chunk per chapter
  - One chunk per annex

PARALLEL PROCESSING: Multiple chunks are processed concurrently to dramatically
speed up the preprocessing. A semaphore limits concurrent API calls to avoid
rate limits.

MODEL CAPABILITIES (gpt-5-nano):
  - Input context: 400k tokens (handles very large chunks)
  - Output context: 128k tokens (handles complex structures like CHAPTER III)

The preprocessing is split into two phases:
  - LLM phase: agent_preprocess_eu_ai_act.py extracts structure from each chunk
  - Deterministic phase: ingest_preprocessed_legal.py writes to Neo4j

This separation ensures:
  - Clear boundaries between AI and deterministic operations
  - Reproducible database writes
  - No hallucinated data in the graph database

Usage:
    python run_preprocess_eu_ai_act.py

Prerequisites:
  - OPENAI_API_KEY in .env file
  - Neo4j running on localhost:7687 (or configured in .env)
  - eu_ai_act_part_1.txt and eu_ai_act_part_2.txt in the data/ directory
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Tuple, List
from collections import OrderedDict

from models.legal_structure import PreprocessedLegalDocument, Chapter, Annex
from models.legal_preprocess import LegalPreprocessDeps
from models.legal_chunks import TextChunk, ChunkKind, ChunkResult
from agent_preprocess_eu_ai_act import preprocess_legal_chunk_agent
from eu_ai_act_splitter import split_eu_ai_act, split_large_chapter_chunk, extract_section_numbers
from ingest_preprocessed_legal import ingest_preprocessed_legal_document
from detect_missing_chunks import get_chunks_to_reprocess
from pydantic_ai import exceptions


# ============================================================================
# Token Estimation and Chunk Size Limits
# ============================================================================

def approx_token_count(text: str) -> int:
    """
    Approximate the number of tokens in a text.

    This uses a very rough heuristic: ~4 characters per token for English
    legal text. This does NOT need to be exact, just conservative enough to
    detect extremely large chunks that risk hitting context limits.

    Args:
        text: The text to count tokens for

    Returns:
        Approximate number of tokens
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def count_articles_in_text(text: str) -> int:
    """
    Count the number of "Article N" patterns in the chunk text.

    This provides a deterministic expected count that we can validate
    against the LLM extraction results.

    Args:
        text: The chunk text to scan for articles

    Returns:
        Number of article headings found (e.g., "Article 1", "Article 40")
    """
    import re
    # Pattern: "Article" followed by a number
    # ^Article\s+\d+ matches lines starting with "Article <number>"
    article_pattern = re.compile(r'^Article\s+(\d+)', re.MULTILINE)
    matches = article_pattern.findall(text)
    return len(matches)


# Max tokens we allow for the *input* (messages) for a single LLM call.
# The gpt-5-nano model has a 400k input context window and 128k output window.
# We use conservative limits to allow for instructions, schema, and completion:
#
# With gpt-5-nano and max_tokens=128000 for output, we budget:
#   - ~350k tokens for input text (very generous)
#   - ~128k tokens for completion (full output capacity)
#   - ~10k tokens for instructions/schema/overhead
#   = ~488k total, well under the 400k input + overhead
MAX_INPUT_TOKENS_PER_CHUNK = 350_000

# Maximum number of concurrent API calls
# Adjust based on your API rate limits and performance
# Increased from 3 to 5 for Phase 1 optimization (faster processing with smaller prompts)
MAX_CONCURRENT_CHUNKS = 5

# ============================================================================
# COVERAGE CHECK CONFIGURATION (Overlapping Window Validation)
# ============================================================================
#
# After primary extraction, optionally run a coverage check using overlapping
# windows to detect and recover missing articles.
#
# How it works:
#   1. Primary extraction completes
#   2. Coverage check scans source text with overlapping windows
#   3. Identifies missing articles by comparing source vs extracted
#   4. Re-runs only the chunks with missing articles, with explicit hints
#   5. Merges recovered articles into final result
#
ENABLE_COVERAGE_CHECK = False  # Disabled in Phase 1 optimization (reduces 5+ unnecessary LLM calls)
COVERAGE_WINDOW_SIZE = 10      # Number of articles per window
COVERAGE_STRIDE = 7            # Articles between window starts (overlap = window - stride)
COVERAGE_CHAPTERS = ["IX"]     # Which chapters to check, or None for all

# ============================================================================
# DEBUG MODE: Reprocess a single chunk for investigation
# ============================================================================
# Set this to a chunk label (e.g., "CHAPTER III - SECTION 5") to only process
# that specific chunk and save the result to JSON for inspection.
# Set to None for normal full-corpus processing.
#
# Usage:
#   CHUNK_LABEL_FILTER = "CHAPTER III - SECTION 5"  # Debug mode
#   CHUNK_LABEL_FILTER = None                        # Normal mode
CHUNK_LABEL_FILTER = None


def read_eu_ai_act_text(file_path_1: Path, file_path_2: Path) -> str:
    """
    Read the full EU AI Act text from two plain-text files and merge them.

    The EU AI Act text has been split into two parts to accommodate editing
    and version control. This function reads both parts and concatenates them
    into a single text.

    Args:
        file_path_1: Path to 'eu_ai_act_part_1.txt'
        file_path_2: Path to 'eu_ai_act_part_2.txt'

    Returns:
        The full merged text as a string.

    Raises:
        FileNotFoundError: if either file is missing
        ValueError: if either file is empty
    """
    # Read part 1
    if not file_path_1.exists():
        raise FileNotFoundError(f"File not found: {file_path_1}")
    text_part1 = file_path_1.read_text(encoding="utf-8")
    if not text_part1.strip():
        raise ValueError(f"Empty text in {file_path_1}")

    # Read part 2
    if not file_path_2.exists():
        raise FileNotFoundError(f"File not found: {file_path_2}")
    text_part2 = file_path_2.read_text(encoding="utf-8")
    if not text_part2.strip():
        raise ValueError(f"Empty text in {file_path_2}")

    # Merge with a single newline separator
    return text_part1 + "\n" + text_part2


async def process_single_chunk(
    chunk: TextChunk,
    idx: int,
    total: int,
    deps: LegalPreprocessDeps,
    semaphore: asyncio.Semaphore,
    missing_article_hints: List[int] = None,
) -> Tuple[int, ChunkResult]:
    """
    Process a single chunk with the LLM agent.

    Uses a semaphore to limit concurrent API calls.

    Args:
        chunk: The text chunk to process
        idx: Index of this chunk (1-based)
        total: Total number of chunks
        deps: Deterministic metadata
        semaphore: Semaphore to limit concurrency
        missing_article_hints: Optional list of article numbers that were missing in previous extraction

    Returns:
        Tuple of (chunk_index, ChunkResult)
    """
    async with semaphore:  # Limit concurrent API calls
        # Log chunk size for debugging and transparency
        est_tokens = approx_token_count(chunk.text)
        print(
            f"[chunk {idx}/{total}] Processing {chunk.kind} {chunk.label} "
            f"({len(chunk.text):,} chars, ~{est_tokens:,} tokens)..."
        )

        # Extract allowed section numbers from chunk text (deterministic)
        # This constrains the LLM to only create sections that actually exist
        allowed_sections = extract_section_numbers(chunk.text)

        # Count expected articles in chunk text (deterministic validation)
        expected_article_count = count_articles_in_text(chunk.text)

        # Build a chunk-specific prompt with section constraints
        prompt = (
            f"You are parsing a {chunk.kind} chunk of the EU AI Act.\n"
            f"Chunk label: {chunk.label}\n\n"
        )

        # Add article count expectation for validation
        if chunk.kind in ["chapter", "section"]:
            if expected_article_count > 0:
                prompt += (
                    f"EXPECTED ARTICLE COUNT: {expected_article_count}\n"
                    f"⚠️ CRITICAL: The text contains exactly {expected_article_count} article(s).\n"
                    f"   You MUST extract ALL {expected_article_count} articles with their complete content.\n"
                    f"   DO NOT skip, merge, or omit any articles.\n"
                    f"   DO NOT stop early - extract ALL articles to the end of the text.\n\n"
                )

        # Add missing article hints if this is a recovery pass
        if missing_article_hints:
            prompt += (
                f"🔍 MISSING ARTICLE RECOVERY:\n"
                f"The following articles were MISSING in the previous extraction: {missing_article_hints}\n"
                f"⚠️⚠️⚠️ CRITICAL: You MUST include these specific articles in your output!\n"
                f"   Scan the text carefully for each of these article numbers.\n"
                f"   If an article number appears in the text, extract it completely.\n"
                f"   Pay special attention to articles near the end of the text.\n\n"
            )

        # Add section constraint information
        if chunk.kind in ["chapter", "section"]:
            if allowed_sections:
                prompt += (
                    f"ALLOWED SECTIONS: {allowed_sections}\n"
                    f"⚠️ CRITICAL: You may ONLY create Section objects with numbers from this list.\n"
                    f"   Any other section numbers (especially high numbers like 19, 41, 65, 75) are ARTICLE numbers, not sections.\n\n"
                )
            else:
                prompt += (
                    f"ALLOWED SECTIONS: [] (NONE)\n"
                    f"⚠️ CRITICAL: This chunk has NO section headings. You MUST set sections = [].\n"
                    f"   All articles attach directly to the chapter. Do NOT invent sections from article numbers.\n\n"
                )

        prompt += (
            f"Below is the full text of this chunk:\n\n"
            f"{chunk.text}"
        )

        # Store original prompt - DO NOT append to it on retries (causes prompt growth)
        original_prompt = prompt

        # Retry logic - reduced to 2 retries (was 5) since prompt is now optimized
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # On retry, use original prompt with a SHORT retry note (not appending)
                if attempt > 0:
                    retry_prompt = (
                        f"{original_prompt}\n\n"
                        f"IMPORTANT: Extract ALL {expected_article_count} articles. Do not stop early."
                    )
                else:
                    retry_prompt = original_prompt

                # Call the chunk-level preprocessing agent
                # Reduced max_tokens from 128k to 64k - sufficient for most chunks
                result = await preprocess_legal_chunk_agent.run(
                    retry_prompt,
                    deps=deps,
                    model_settings={'max_tokens': 64000}
                )
                chunk_result: ChunkResult = result.output

                # Post-validation: Check if extracted article count matches expected
                if chunk.kind in ["chapter", "section"] and expected_article_count > 0:
                    # Count articles in the extracted result
                    extracted_count = 0
                    if chunk_result.kind == "chapter" and chunk_result.chapter is not None:
                        extracted_count = len(chunk_result.chapter.articles) + sum(
                            len(sec.articles) for sec in chunk_result.chapter.sections
                        )
                    elif chunk_result.kind == "section" and chunk_result.section is not None:
                        extracted_count = len(chunk_result.section.articles)

                    # If count doesn't match, log and retry (but don't grow prompt)
                    if extracted_count != expected_article_count:
                        error_msg = (
                            f"Article count mismatch: expected {expected_article_count}, "
                            f"extracted {extracted_count}"
                        )
                        if attempt < max_retries - 1:
                            wait_time = 2
                            print(
                                f"  ⚠️ [{idx}/{total}] {error_msg} "
                                f"(attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s..."
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            # Final attempt failed
                            print(f"  ❌ [{idx}/{total}] {error_msg} after {max_retries} attempts")
                            # Don't raise - return partial result and let self-healing handle it

                # Validate and filter sections based on allowed_sections (post-processing enforcement)
                if chunk_result.kind == "chapter" and chunk_result.chapter is not None:
                    if not allowed_sections:
                        # No sections allowed - force empty
                        if chunk_result.chapter.sections:
                            print(f"  ⚠️ [{idx}/{total}] Filtered {len(chunk_result.chapter.sections)} invented sections (no SECTION headings in text)")
                            chunk_result.chapter.sections = []
                    else:
                        # Filter to only allowed sections
                        original_count = len(chunk_result.chapter.sections)
                        chunk_result.chapter.sections = [
                            sec for sec in chunk_result.chapter.sections
                            if sec.number in allowed_sections
                        ]
                        filtered_count = original_count - len(chunk_result.chapter.sections)
                        if filtered_count > 0:
                            print(f"  ⚠️ [{idx}/{total}] Filtered {filtered_count} invalid section(s) (not in allowed list: {allowed_sections})")

                elif chunk_result.kind == "section" and chunk_result.section is not None:
                    # For section chunks, verify the section number is valid
                    if allowed_sections and chunk_result.section.number not in allowed_sections:
                        print(f"  ⚠️ [{idx}/{total}] Section {chunk_result.section.number} not in allowed list {allowed_sections}, forcing to first allowed")
                        chunk_result.section.number = allowed_sections[0] if allowed_sections else "1"

                # Log what was extracted
                if chunk_result.kind == "recitals":
                    print(f"  → [{idx}/{total}] Extracted {len(chunk_result.recitals)} recitals")
                elif chunk_result.kind == "chapter":
                    if chunk_result.chapter is not None:
                        num_articles = len(chunk_result.chapter.articles) + sum(
                            len(sec.articles) for sec in chunk_result.chapter.sections
                        )
                        print(f"  → [{idx}/{total}] Extracted {num_articles} articles")
                elif chunk_result.kind == "section":
                    if chunk_result.section is not None:
                        num_articles = len(chunk_result.section.articles)
                        print(f"  → [{idx}/{total}] Extracted section with {num_articles} articles")
                elif chunk_result.kind == "annex":
                    print(f"  → [{idx}/{total}] Extracted annex")

                print(f"✓ [{idx}/{total}] Finished {chunk.kind} {chunk.label}")
                return (idx, chunk_result)

            except exceptions.UnexpectedModelBehavior as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s, 32s
                    print(
                        f"  ⚠️ [{idx}/{total}] Validation/output schema error "
                        f"(attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                print(f"❌ [{idx}/{total}] Validation/output schema error: {e}")
                raise
            except Exception as e:
                # Check if this is a retryable error
                error_msg = str(e)
                error_type = type(e).__name__

                is_null_content_error = ("null" in error_msg.lower() and "content" in error_msg.lower())
                is_timeout_error = ("timeout" in error_msg.lower() or "timed out" in error_msg.lower() or
                                   error_type in ["APITimeoutError", "ReadTimeout", "ConnectTimeout"])

                if (is_null_content_error or is_timeout_error) and attempt < max_retries - 1:
                    # Retry with exponential backoff for transient errors
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s, 32s
                    error_label = "Timeout" if is_timeout_error else "Null content"
                    print(f"  ⚠️ [{idx}/{total}] {error_label} error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Final attempt failed or non-retryable error
                    print(f"❌ [{idx}/{total}] Error processing {chunk.kind} {chunk.label}: {e}")
                    raise


async def preprocess_eu_ai_act_by_chunks() -> PreprocessedLegalDocument:
    """
    Run the structural preprocessing agent on the EU AI Act using chunks in parallel.

    This function:
    1. Reads and merges raw text from eu_ai_act_part_1.txt and eu_ai_act_part_2.txt
    2. Splits it deterministically into chunks (recitals, chapters, annexes)
    3. Processes chunks in PARALLEL with gpt-5-nano agent (limited concurrency)
    4. Merges all results into a single PreprocessedLegalDocument
    5. Returns the complete structured document

    Returns:
        PreprocessedLegalDocument with extracted structure

    Raises:
        FileNotFoundError: if either eu_ai_act_part_1.txt or eu_ai_act_part_2.txt is not found
        ValueError: if either file is empty or splitting fails
    """
    # Configuration (deterministic metadata)
    DOCUMENT_ID = "eu_ai_act_2024"
    SOURCE_FILE_1 = "data/eu_ai_act_part_1.txt"
    SOURCE_FILE_2 = "data/eu_ai_act_part_2.txt"
    OFFICIAL_TITLE = (
        "Regulation (EU) 2024/1689 of the European Parliament and of "
        "the Council of 13 June 2024 laying down harmonised rules on "
        "artificial intelligence (Artificial Intelligence Act)"
    )

    # Step 1: Read raw text from both parts
    file_path_1 = Path(SOURCE_FILE_1)
    file_path_2 = Path(SOURCE_FILE_2)
    raw_text = read_eu_ai_act_text(file_path_1, file_path_2)

    # Step 2: Build dependencies (deterministic metadata)
    # Note: source_file lists both parts for traceability
    deps = LegalPreprocessDeps(
        document_id=DOCUMENT_ID,
        source_file=f"{SOURCE_FILE_1}, {SOURCE_FILE_2}",
        jurisdiction="EU",
        instrument_type="Regulation",
    )

    # Step 3: Split into deterministic chunks
    print("Splitting document into chunks...")
    base_chunks = split_eu_ai_act(raw_text)
    if not base_chunks:
        raise ValueError("Splitter returned no chunks for EU AI Act text.")

    print(f"Initial split produced {len(base_chunks)} chunks (recitals/chapters/annexes).")

    # Step 3b: Refine chunks - further split oversized chapter chunks
    print("Checking for oversized chunks and refining...")
    refined_chunks = []
    for chunk in base_chunks:
        est_tokens = approx_token_count(chunk.text)
        if chunk.kind == "chapter" and est_tokens > MAX_INPUT_TOKENS_PER_CHUNK:
            print(
                f"  ⚠️  Chunk '{chunk.label}' is too large (~{est_tokens:,} tokens); "
                f"splitting into smaller subchunks..."
            )
            subchunks = split_large_chapter_chunk(chunk, max_input_tokens=MAX_INPUT_TOKENS_PER_CHUNK)
            refined_chunks.extend(subchunks)
            print(f"     → Split into {len(subchunks)} subchunks")
        else:
            refined_chunks.append(chunk)

    chunks = refined_chunks

    # Step 3c: Apply CHUNK_LABEL_FILTER if in debug mode
    if CHUNK_LABEL_FILTER is not None:
        print(f"\n⚠️  DEBUG MODE: Filtering to only chunk labeled '{CHUNK_LABEL_FILTER}'")
        filtered_chunks = [c for c in chunks if c.label == CHUNK_LABEL_FILTER]
        if not filtered_chunks:
            available_labels = [c.label for c in chunks]
            raise ValueError(
                f"No chunk found with label '{CHUNK_LABEL_FILTER}'.\n"
                f"Available chunk labels:\n" + "\n".join(f"  - {lbl}" for lbl in available_labels[:20])
            )
        chunks = filtered_chunks
        print(f"  → Found matching chunk, processing only 1 chunk in debug mode\n")

    total = len(chunks)
    print(f"\nUsing {total} refined chunks (recitals/chapters/annexes).")
    print(f"Processing chunks in parallel (max {MAX_CONCURRENT_CHUNKS} concurrent)...\n")

    # Step 4: Initialize empty PreprocessedLegalDocument
    preprocessed = PreprocessedLegalDocument(
        document_id=DOCUMENT_ID,
        official_title=OFFICIAL_TITLE,
        short_title="EU AI Act",
        year=2024,
        recitals=[],
        chapters=[],
        annexes=[],
    )

    # Step 5: Process all chunks in parallel with limited concurrency
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

    # Create tasks for all chunks (no hints for primary extraction)
    tasks = [
        process_single_chunk(chunk, idx, total, deps, semaphore, missing_article_hints=None)
        for idx, chunk in enumerate(chunks, start=1)
    ]

    # Wait for all tasks to complete
    print(f"Starting parallel processing of {total} chunks...\n")
    results = await asyncio.gather(*tasks)

    # Step 6: Merge results into final PreprocessedLegalDocument
    # Sort by index to maintain order
    results.sort(key=lambda x: x[0])

    print(f"\nMerging {len(results)} chunk results...")

    # Use OrderedDict to merge chapter subchunks
    # Multiple subchunks for the same chapter (e.g., CHAPTER III sections) should
    # be merged into a single Chapter object
    chapter_map: "OrderedDict[str, Chapter]" = OrderedDict()

    for idx, chunk_result in results:
        if chunk_result.kind == "recitals":
            preprocessed.recitals.extend(chunk_result.recitals)
        elif chunk_result.kind == "chapter":
            if chunk_result.chapter is not None:
                ch = chunk_result.chapter
                key = ch.number  # Use chapter number as key (e.g., "I", "III", "VII")

                if key not in chapter_map:
                    # First time we see this chapter; store it
                    chapter_map[key] = ch
                else:
                    # Merge into existing Chapter:
                    existing = chapter_map[key]
                    # Merge sections (if any)
                    existing.sections.extend(ch.sections)
                    # Merge articles
                    existing.articles.extend(ch.articles)
        elif chunk_result.kind == "section":
            # Section chunks come from split chapters (e.g., CHAPTER III)
            # Extract chapter number from label: "CHAPTER III - SECTION 5"
            if chunk_result.section is not None:
                import re
                label = chunk_result.label
                match = re.search(r'CHAPTER ([IVX]+)', label)
                if not match:
                    print(f"⚠️  Warning: Could not extract chapter number from label '{label}'")
                    continue

                chapter_num = match.group(1)

                # Ensure chapter exists in map
                if chapter_num not in chapter_map:
                    # Create a placeholder chapter
                    from models.legal_structure import Chapter
                    chapter_map[chapter_num] = Chapter(
                        number=chapter_num,
                        title="",  # Will be filled later if chapter chunk arrives
                        sections=[],
                        articles=[],
                    )

                # Add section to chapter
                chapter_map[chapter_num].sections.append(chunk_result.section)
        elif chunk_result.kind == "annex":
            if chunk_result.annex is not None:
                preprocessed.annexes.append(chunk_result.annex)

    # Set chapters from the merged chapter_map in insertion order
    preprocessed.chapters = list(chapter_map.values())

    return preprocessed


async def preprocess_specific_chunks(
    chunk_labels: List[str],
    missing_article_hints: dict = None
) -> None:
    """
    Re-process specific chunks that failed or are incomplete.

    This function:
    1. Splits the document into chunks
    2. Filters to only the specified chunk labels
    3. Re-processes those chunks (with optional hints about missing articles)
    4. Ingests the results into Neo4j (MERGE will update existing data)

    Args:
        chunk_labels: List of chunk labels to re-process (e.g., ["CHAPTER IV - ...", "CHAPTER V - ..."])
        missing_article_hints: Optional dict mapping chunk labels to lists of missing article numbers
                               e.g., {"CHAPTER IX": [86, 87, 88, 89, 90]}
    """
    print(f"\n🔄 Re-processing {len(chunk_labels)} specific chunk(s)...")
    if missing_article_hints:
        print(f"   With hints about missing articles: {missing_article_hints}")
    print("=" * 70)

    # Configuration
    DOCUMENT_ID = "eu_ai_act_2024"
    SOURCE_FILE_1 = "data/eu_ai_act_part_1.txt"
    SOURCE_FILE_2 = "data/eu_ai_act_part_2.txt"
    OFFICIAL_TITLE = (
        "Regulation (EU) 2024/1689 of the European Parliament and of "
        "the Council of 13 June 2024 laying down harmonised rules on "
        "artificial intelligence (Artificial Intelligence Act)"
    )

    # Read raw text
    file_path_1 = Path(SOURCE_FILE_1)
    file_path_2 = Path(SOURCE_FILE_2)
    raw_text = read_eu_ai_act_text(file_path_1, file_path_2)

    # Build dependencies
    deps = LegalPreprocessDeps(
        document_id=DOCUMENT_ID,
        source_file=f"{SOURCE_FILE_1}, {SOURCE_FILE_2}",
        jurisdiction="EU",
        instrument_type="Regulation",
    )

    # Split into chunks
    base_chunks = split_eu_ai_act(raw_text)

    # Refine chunks (split oversized ones)
    refined_chunks = []
    for chunk in base_chunks:
        est_tokens = approx_token_count(chunk.text)
        if chunk.kind == "chapter" and est_tokens > MAX_INPUT_TOKENS_PER_CHUNK:
            subchunks = split_large_chapter_chunk(chunk, max_input_tokens=MAX_INPUT_TOKENS_PER_CHUNK)
            refined_chunks.extend(subchunks)
        else:
            refined_chunks.append(chunk)

    # Filter to only the chunks we want to re-process
    chunks_to_process = []
    for chunk in refined_chunks:
        # Check if this chunk label matches any of the requested labels
        # We do a partial match because labels might have slight variations
        for requested_label in chunk_labels:
            if chunk.label.startswith(requested_label.split(" - ")[0]):  # Match by chapter
                chunks_to_process.append(chunk)
                break

    if not chunks_to_process:
        print("⚠️  Warning: No matching chunks found for the requested labels")
        return

    print(f"Found {len(chunks_to_process)} chunk(s) to re-process:\n")
    for i, chunk in enumerate(chunks_to_process, 1):
        print(f"  {i}. {chunk.label}")
    print()

    # Process chunks
    total = len(chunks_to_process)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

    tasks = []
    for idx, chunk in enumerate(chunks_to_process, start=1):
        # Check if we have hints for this chunk
        hints_for_chunk = None
        if missing_article_hints:
            # Match chunk label (may need fuzzy matching)
            for hint_label, hint_articles in missing_article_hints.items():
                if hint_label in chunk.label or chunk.label.startswith(hint_label):
                    hints_for_chunk = hint_articles
                    break

        tasks.append(
            process_single_chunk(chunk, idx, total, deps, semaphore, hints_for_chunk)
        )

    results = await asyncio.gather(*tasks)

    # Merge and ingest
    results.sort(key=lambda x: x[0])

    preprocessed = PreprocessedLegalDocument(
        document_id=DOCUMENT_ID,
        official_title=OFFICIAL_TITLE,
        short_title="EU AI Act",
        year=2024,
        recitals=[],
        chapters=[],
        annexes=[],
    )

    chapter_map: "OrderedDict[str, Chapter]" = OrderedDict()

    for idx, chunk_result in results:
        if chunk_result.kind == "recitals":
            preprocessed.recitals.extend(chunk_result.recitals)
        elif chunk_result.kind == "chapter":
            if chunk_result.chapter is not None:
                ch = chunk_result.chapter
                key = ch.number
                if key not in chapter_map:
                    chapter_map[key] = ch
                else:
                    existing = chapter_map[key]
                    existing.sections.extend(ch.sections)
                    existing.articles.extend(ch.articles)
        elif chunk_result.kind == "section":
            if chunk_result.section is not None:
                import re
                label = chunk_result.label
                match = re.search(r'CHAPTER ([IVX]+)', label)
                if match:
                    chapter_num = match.group(1)
                    if chapter_num not in chapter_map:
                        from models.legal_structure import Chapter
                        chapter_map[chapter_num] = Chapter(
                            number=chapter_num,
                            title="",
                            sections=[],
                            articles=[],
                        )
                    chapter_map[chapter_num].sections.append(chunk_result.section)
        elif chunk_result.kind == "annex":
            if chunk_result.annex is not None:
                preprocessed.annexes.append(chunk_result.annex)

    preprocessed.chapters = list(chapter_map.values())

    # Ingest to Neo4j (MERGE will update existing data)
    print(f"\n📥 Ingesting re-processed chunks to Neo4j...")
    ingest_preprocessed_legal_document(preprocessed)
    print("✓ Re-processing complete\n")


async def run_coverage_check_and_recover(
    preprocessed: PreprocessedLegalDocument,
    raw_text: str
) -> PreprocessedLegalDocument:
    """
    Run coverage check on specified chapters and recover missing articles.

    Uses overlapping window validation to detect missing articles, then
    re-extracts only the problematic chunks with hints about what's missing.

    Args:
        preprocessed: Result from primary extraction
        raw_text: Full source text

    Returns:
        Enhanced PreprocessedLegalDocument with recovered articles
    """
    if not ENABLE_COVERAGE_CHECK:
        return preprocessed

    print("\n" + "=" * 70)
    print("📊 COVERAGE CHECK - Overlapping Window Validation")
    print("=" * 70)
    print(f"Window size: {COVERAGE_WINDOW_SIZE}, Stride: {COVERAGE_STRIDE}")
    print(f"Checking chapters: {COVERAGE_CHAPTERS if COVERAGE_CHAPTERS else 'All'}\n")

    # Import coverage check utilities
    from validate_structure import (
        coverage_check_chapter,
        extract_articles_from_source
    )

    # Split raw text into chapters
    chapter_pattern = re.compile(
        r'^(CHAPTER ([IVXL]+).*?)(?=^CHAPTER [IVXL]+|^ANNEX|\Z)',
        re.MULTILINE | re.DOTALL | re.IGNORECASE
    )

    chapters_to_check = {}
    for match in chapter_pattern.finditer(raw_text):
        chapter_num = match.group(2)
        chapter_text = match.group(1)

        # Filter by COVERAGE_CHAPTERS if specified
        if COVERAGE_CHAPTERS is None or chapter_num in COVERAGE_CHAPTERS:
            chapters_to_check[chapter_num] = chapter_text

    if not chapters_to_check:
        print("⚠️  No chapters to check")
        return preprocessed

    # Run coverage check on each chapter
    all_missing_articles = {}

    for chapter_num, chapter_text in chapters_to_check.items():
        try:
            result = await coverage_check_chapter(
                chapter_num,
                chapter_text,
                preprocessed,
                window_size=COVERAGE_WINDOW_SIZE,
                stride=COVERAGE_STRIDE
            )

            if result["missing_articles"]:
                all_missing_articles[chapter_num] = result["missing_articles"]
                print(f"\n   ⚠️  Chapter {chapter_num}: {len(result['missing_articles'])} missing articles")
            else:
                print(f"\n   ✅ Chapter {chapter_num}: Complete!")

        except Exception as e:
            print(f"\n   ❌ Coverage check failed for Chapter {chapter_num}: {e}")
            import traceback
            traceback.print_exc()

    # If no missing articles found, we're done
    if not all_missing_articles:
        print("\n✅ Coverage check passed - no missing articles!")
        return preprocessed

    # Re-extract chunks with missing articles
    print("\n" + "=" * 70)
    print("🔄 RE-EXTRACTING CHUNKS WITH MISSING ARTICLES")
    print("=" * 70)

    for chapter_num, missing_nums in all_missing_articles.items():
        print(f"\nChapter {chapter_num}: Re-extracting to recover articles {missing_nums}")

        # Find the chunk label for this chapter
        chunk_label = f"CHAPTER {chapter_num}"

        # Re-run the chunk with hints about missing articles
        await preprocess_specific_chunks(
            [chunk_label],
            missing_article_hints={chunk_label: missing_nums}
        )

    print("\n✅ Coverage check recovery complete!")
    return preprocessed


async def preprocess_with_self_healing(max_retries: int = 10) -> PreprocessedLegalDocument:
    """
    Run preprocessing with automatic self-healing for failed chunks.

    This function:
    1. Runs full preprocessing with enhanced validation (article count matching)
    2. Ingests to Neo4j
    3. Runs coverage check with overlapping windows (if enabled)
    4. Detects missing chunks by analyzing Neo4j data
    5. Re-processes only the failed chunks with smarter prompts
    6. Repeats until complete or max retries reached

    Args:
        max_retries: Maximum number of retry attempts (default: 10)

    Returns:
        PreprocessedLegalDocument with complete structure
    """
    print("\n🔧 SELF-HEALING PREPROCESSING MODE (ENHANCED)")
    print("=" * 70)
    print(f"Enhanced features:")
    print(f"  - Pre-counts articles in chunk text for validation")
    print(f"  - Uses full 128k output tokens for complex extractions")
    print(f"  - Post-validates extracted article counts")
    print(f"  - Retries with enhanced prompts on count mismatches")
    if ENABLE_COVERAGE_CHECK:
        print(f"  - Overlapping window coverage check (window={COVERAGE_WINDOW_SIZE}, stride={COVERAGE_STRIDE})")
    print(f"Maximum retry attempts: {max_retries}\n")

    # Read raw text for coverage check (if needed)
    SOURCE_FILE_1 = "data/eu_ai_act_part_1.txt"
    SOURCE_FILE_2 = "data/eu_ai_act_part_2.txt"
    file_path_1 = Path(SOURCE_FILE_1)
    file_path_2 = Path(SOURCE_FILE_2)
    raw_text = read_eu_ai_act_text(file_path_1, file_path_2)

    # Initial full preprocessing
    print("📋 Phase 1: Initial full preprocessing")
    print("=" * 70)
    preprocessed = await preprocess_eu_ai_act_by_chunks()

    # Ingest to Neo4j
    print("\n📥 Ingesting to Neo4j...")
    from ingest_preprocessed_legal import ingest_preprocessed_legal_document
    ingest_preprocessed_legal_document(preprocessed)

    # Run coverage check if enabled (re-extracts missing articles automatically)
    await run_coverage_check_and_recover(preprocessed, raw_text)

    # Self-healing loop
    for attempt in range(max_retries):
        print(f"\n📋 Phase {attempt + 2}: Verification and self-healing (attempt {attempt + 1}/{max_retries})")
        print("=" * 70)

        # Detect missing chunks
        chunks_to_reprocess = get_chunks_to_reprocess()

        if not chunks_to_reprocess:
            print("✅ No missing chunks detected - preprocessing is complete!")
            break

        print(f"\n⚠️  Found {len(chunks_to_reprocess)} chunk(s) with missing data")
        print("🔄 Attempting to re-process failed chunks...\n")

        # Re-process the failed chunks
        await preprocess_specific_chunks(chunks_to_reprocess)

        # If this was the last retry, show a warning
        if attempt == max_retries - 1:
            print(f"\n⚠️  Warning: Reached maximum retry attempts ({max_retries})")
            print("   Some chunks may still be incomplete")
            chunks_still_missing = get_chunks_to_reprocess()
            if chunks_still_missing:
                print(f"   Still missing: {chunks_still_missing}")

    return preprocessed


async def print_progress_timer(start_time: float):
    """
    Background task that prints elapsed time every 5 minutes.

    Args:
        start_time: Unix timestamp when processing started
    """
    interval_minutes = 5
    interval_seconds = interval_minutes * 60

    while True:
        await asyncio.sleep(interval_seconds)
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        print(f"\n⏱️  {minutes}m {seconds:.0f}s have passed since start...\n")


async def main():
    """
    Main preprocessing workflow (async version).

    Workflow:
    1. Run the chunked preprocessing agent to extract structure from eu_ai_act.txt
    2. Print a summary of what was extracted
    3. Ingest the structured data into Neo4j deterministically
    4. Print final status

    Note: This script is idempotent - you can re-run it safely.
    The Neo4j ingestion uses MERGE, so re-running won't duplicate nodes.
    """
    from datetime import datetime

    start_time = time.time()
    start_datetime = datetime.now()

    print(f"\n🕐 Start time: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nPrerequisites:")
    print("  ✓ OPENAI_API_KEY in .env file")
    print("  ✓ Neo4j running on localhost:7687")
    print("  ✓ eu_ai_act_part_1.txt and eu_ai_act_part_2.txt in project root\n")

    print("=" * 70)
    print("EU AI ACT - STRUCTURAL PREPROCESSING (CHUNKED, PARALLEL)")
    print("=" * 70)
    print()
    print("This script extracts the physical structure of the EU AI Act")
    print("(recitals, chapters, articles, annexes) and ingests it into Neo4j.")
    print()

    # Start background timer task
    timer_task = asyncio.create_task(print_progress_timer(start_time))

    # Step 1: Preprocess with self-healing (automatic retry for failed chunks)
    print("[1/2] Running self-healing structural preprocessing...")
    print("      (Automatically detects and re-processes failed chunks)")
    print()

    try:
        preprocessed = await preprocess_with_self_healing(max_retries=10)
    except FileNotFoundError as e:
        timer_task.cancel()
        print(f"❌ Error: {e}")
        print("   Please ensure both 'eu_ai_act_part_1.txt' and 'eu_ai_act_part_2.txt' exist in the project root.")
        return
    except Exception as e:
        timer_task.cancel()
        print(f"❌ Preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Calculate statistics
    total_articles = 0
    total_paragraphs = 0

    for chapter in preprocessed.chapters:
        total_articles += len(chapter.articles)
        for article in chapter.articles:
            total_paragraphs += len(article.paragraphs)

        for section in chapter.sections:
            total_articles += len(section.articles)
            for article in section.articles:
                total_paragraphs += len(article.paragraphs)

    # Print summary
    print()
    print("=" * 70)
    print("✓ STRUCTURAL PREPROCESSING COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  - Document ID: {preprocessed.document_id}")
    print(f"  - Official title: {preprocessed.official_title[:70]}...")
    print(f"  - Short title: {preprocessed.short_title}")
    print(f"  - Year: {preprocessed.year}")
    print(f"  - Recitals: {len(preprocessed.recitals)}")
    print(f"  - Chapters: {len(preprocessed.chapters)}")
    print(f"  - Articles (total): {total_articles}")
    print(f"  - Paragraphs (total): {total_paragraphs}")
    print(f"  - Annexes: {len(preprocessed.annexes)}")
    print()

    # Show sample of chapters
    if preprocessed.chapters:
        print("Sample chapters:")
        for i, chapter in enumerate(preprocessed.chapters[:5], 1):
            print(f"  {i}. Chapter {chapter.number}: {chapter.title}")
        if len(preprocessed.chapters) > 5:
            print(f"  ... and {len(preprocessed.chapters) - 5} more chapters")
        print()

    # Step 1b: In debug mode, save result to JSON and exit (skip Neo4j ingestion)
    if CHUNK_LABEL_FILTER is not None:
        timer_task.cancel()
        debug_output_path = Path("debug_chunk_result.json")
        print(f"⚠️  DEBUG MODE: Saving result to {debug_output_path}")

        # Convert to JSON-serializable dict
        preprocessed_dict = preprocessed.model_dump(mode='json')

        with open(debug_output_path, 'w', encoding='utf-8') as f:
            json.dump(preprocessed_dict, f, indent=2, ensure_ascii=False)

        print(f"✓ Saved debug output to {debug_output_path}")
        print(f"\nInspect the file to verify Articles 40-49 paragraphs were extracted.")
        print(f"Then set CHUNK_LABEL_FILTER = None and rerun for full ingestion.")
        print()
        return

    # Note: Neo4j ingestion already handled by preprocess_with_self_healing()
    print("\n✓ Preprocessing and ingestion completed with self-healing")

    print()
    print("=" * 70)
    print("✓ PREPROCESSING AND INGESTION COMPLETE")
    print("=" * 70)
    print()
    print("The EU AI Act structure has been extracted and ingested into Neo4j.")
    print("You can now query the graph database to explore the regulation's structure.")
    print()
    print("Example Cypher queries:")
    print("  - Count recitals:")
    print("    MATCH (r:Regulation)-[:HAS_RECITAL]->(rec:Recital)")
    print("    RETURN count(rec)")
    print()
    print("  - List all chapters:")
    print("    MATCH (r:Regulation)-[:HAS_CHAPTER]->(ch:Chapter)")
    print("    RETURN ch.number, ch.title")
    print()
    print("  - Find articles in Chapter I:")
    print("    MATCH (ch:Chapter {number: 'I'})-[:HAS_ARTICLE]->(art:Article)")
    print("    RETURN art.number, art.title")
    print()

    # Cancel the background timer task
    timer_task.cancel()
    try:
        await timer_task
    except asyncio.CancelledError:
        pass

    # Display elapsed time
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = elapsed_time % 60
    print("=" * 70)
    print(f"⏱️  Total processing time: {minutes}m {seconds:.2f}s")
    print("=" * 70)
    print()


if __name__ == "__main__":
    """
    How to use this script:

    1. Ensure prerequisites are met:
       - OPENAI_API_KEY in .env file
       - Neo4j running on localhost:7687 (or configured in .env)
       - eu_ai_act_part_1.txt and eu_ai_act_part_2.txt in the project root

    2. Run this script:
       python run_preprocess_eu_ai_act.py

    The script will:
    - Read and merge the two-part EU AI Act text
    - Split the EU AI Act into chunks (recitals, chapters, annexes)
    - Extract structure from chunks IN PARALLEL using gpt-5-nano
    - Display progress as [chunk X/Y] for each chunk processed
    - Merge all chunks into a complete document
    - Display a summary of what was found
    - Ingest the structure into Neo4j deterministically

    PARALLEL PROCESSING:
    - Processes up to MAX_CONCURRENT_CHUNKS chunks simultaneously
    - Dramatically faster than sequential processing
    - Adjust MAX_CONCURRENT_CHUNKS based on your API rate limits

    MODEL CAPABILITIES (gpt-5-nano):
    - Input: 400k tokens (handles very large chunks)
    - Output: 128k tokens (handles complex structures like CHAPTER III)
    """
    asyncio.run(main())

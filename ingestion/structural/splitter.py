"""
Deterministic Splitter for the EU AI Act

This module provides a function to split the EU AI Act plain text into
semantically meaningful chunks without using any LLM.

The splitter breaks the text into:
  1. One chunk for all recitals (the "Whereas" section)
  2. One chunk per chapter (CHAPTER I, CHAPTER II, etc.)
  3. One chunk per annex (ANNEX I, ANNEX II, etc.)

This deterministic splitting allows the LLM agent to process each chunk
separately, avoiding context length limits while maintaining semantic coherence.

Key principles:
  - No LLM calls - pure regex and string manipulation
  - No data loss - all text must be included in some chunk
  - Clear boundaries - use explicit markers in the regulation text
"""

import re
from typing import List

from models.legal_chunks import TextChunk, ChunkKind


def extract_section_numbers(text: str) -> List[str]:
    """
    Extract section numbers from text by finding SECTION headings.

    This is used to constrain the LLM agent to only create sections that
    actually exist in the text, preventing it from misinterpreting high
    article numbers (like 41, 65) as section numbers.

    Args:
        text: The chunk text to scan for SECTION headings

    Returns:
        List of section number strings (e.g., ['1', '2', '3', '5'])
        Returns empty list if no SECTION headings are found.

    Example:
        >>> text = "SECTION 1\\n\\nTitle\\n\\nSECTION 2\\n\\nAnother"
        >>> extract_section_numbers(text)
        ['1', '2']
    """
    section_pattern = re.compile(r'^SECTION (\d+)', re.MULTILINE)
    matches = section_pattern.findall(text)
    return matches  # Returns list of strings like ['1', '2', '5']


def _split_recitals(recitals_text: str, batch_size: int = 60) -> List[TextChunk]:
    """
    Split the recitals section into smaller batches to avoid context limits.

    The EU AI Act has 180+ recitals which exceeds the 128k token limit.
    This function splits them into batches of ~60 recitals each.

    Args:
        recitals_text: Full text of the recitals section
        batch_size: Number of recitals per batch (default 60)

    Returns:
        List of TextChunk objects for recital batches
    """
    # Pattern to find recital markers: (1), (2), (3), etc.
    recital_pattern = re.compile(r'^\(\d+\)', re.MULTILINE)

    # Find all recital positions
    recital_matches = list(recital_pattern.finditer(recitals_text))

    if not recital_matches:
        # No numbered recitals found, return as single chunk
        return [TextChunk(
            kind="recitals",
            label="RECITALS",
            text=recitals_text
        )]

    chunks: List[TextChunk] = []

    # Split recitals into batches
    for i in range(0, len(recital_matches), batch_size):
        batch_matches = recital_matches[i:i + batch_size]

        # Determine start and end positions
        start_pos = batch_matches[0].start()

        # End position is either the start of the next batch or end of text
        if i + batch_size < len(recital_matches):
            end_pos = recital_matches[i + batch_size].start()
        else:
            end_pos = len(recitals_text)

        batch_text = recitals_text[start_pos:end_pos].strip()

        # Extract recital numbers for the label
        first_num = batch_matches[0].group().strip('()')
        last_match = batch_matches[-1]
        last_num = last_match.group().strip('()')

        chunks.append(TextChunk(
            kind="recitals",
            label=f"RECITALS ({first_num}-{last_num})",
            text=batch_text
        ))

    return chunks


def _split_large_chapter_by_sections(chapter_text: str, chapter_num: str) -> List[TextChunk]:
    """
    Split a large chapter into multiple chunks by sections.

    This is used for chapters like CHAPTER III that are too large to fit in
    the 128k token context window.

    Args:
        chapter_text: The full text of the chapter
        chapter_num: The chapter Roman numeral (e.g., "III")

    Returns:
        List of TextChunk objects, one per section
    """
    # Pattern to find section headings: "SECTION N"
    section_pattern = re.compile(r'^SECTION (\d+)', re.MULTILINE)
    section_matches = list(section_pattern.finditer(chapter_text))

    if not section_matches:
        # No sections found - return the whole chapter as one chunk
        # (This shouldn't happen for CHAPTER III, but handle gracefully)
        chapter_lines = chapter_text.split('\n', 2)
        chapter_label = chapter_lines[0].strip() if chapter_lines else f"CHAPTER {chapter_num}"
        return [TextChunk(
            kind="chapter",
            label=chapter_label,
            text=chapter_text
        )]

    chunks: List[TextChunk] = []

    for i, section_match in enumerate(section_matches):
        section_num = section_match.group(1)
        section_start = section_match.start()

        # Find the end of this section (start of next section or end of chapter)
        if i + 1 < len(section_matches):
            section_end = section_matches[i + 1].start()
        else:
            section_end = len(chapter_text)

        section_text = chapter_text[section_start:section_end].strip()

        # Get the section title (usually on the line after "SECTION N")
        section_lines = section_text.split('\n', 3)
        section_title = ""
        if len(section_lines) >= 2:
            section_title = section_lines[1].strip()

        # Create a label like "CHAPTER III - SECTION 1 - Classification of AI systems as high-risk"
        chunk_label = f"CHAPTER {chapter_num} - SECTION {section_num}"
        if section_title:
            chunk_label += f" - {section_title}"

        chunks.append(TextChunk(
            kind="section",  # Changed from "chapter" to fix Article 41-49 misidentification
            label=chunk_label,
            text=section_text
        ))

    return chunks


def split_large_chapter_chunk(chunk: TextChunk, max_input_tokens: int = 80_000) -> List[TextChunk]:
    """
    If a chapter chunk is too large for a single LLM call, split it into smaller subchunks.

    This function is used AFTER the initial split_eu_ai_act() call, as a second-pass
    refinement to ensure no single chunk exceeds the token budget.

    Strategy:
      1. Prefer splitting by SECTION headings within the chapter.
         For example lines starting with 'SECTION 1', 'SECTION 2', etc.
      2. If no SECTION headings are found, fall back to splitting by 'Article <number>'
         groups (e.g. 5 articles per subchunk).
      3. If even article-level splitting doesn't help, return the original chunk
         (this should be rare with sensible limits).

    The function assumes chunk.kind == 'chapter'.

    Args:
        chunk: A TextChunk with kind='chapter' that may be too large
        max_input_tokens: Maximum number of tokens allowed for the chunk text

    Returns:
        - If the chunk is already small enough, returns [chunk].
        - Otherwise, returns a list of smaller TextChunk objects with
          kind='chapter' and more specific labels indicating the
          section or article range.

    Example:
        >>> large_chunk = TextChunk(kind="chapter", label="CHAPTER III", text="...")
        >>> subchunks = split_large_chapter_chunk(large_chunk)
        >>> [c.label for c in subchunks]
        ['CHAPTER III - SECTION 1', 'CHAPTER III - SECTION 2', ...]
    """
    assert chunk.kind == "chapter", "split_large_chapter_chunk is only for chapter chunks"

    text = chunk.text

    # Quick token estimate (rough heuristic: ~4 chars per token)
    est_tokens = max(1, len(text) // 4)
    if est_tokens <= max_input_tokens:
        # Chunk is already small enough
        return [chunk]

    def _make_chunk(label_suffix: str, subtext: str) -> TextChunk:
        """Helper to create a subchunk with an extended label."""
        new_label = f"{chunk.label} {label_suffix}".strip()
        return TextChunk(
            kind="chapter",
            label=new_label,
            text=subtext.strip(),
        )

    # ========================================================================
    # Strategy 1: Split by SECTION headings
    # ========================================================================
    section_pattern = re.compile(r'^SECTION\s+\d+.*$', re.MULTILINE)
    sections = list(section_pattern.finditer(text))

    subchunks: List[TextChunk] = []

    if sections:
        # Split by SECTION boundaries
        for i, m in enumerate(sections):
            start = m.start()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
            section_text = text[start:end]
            section_heading = m.group(0).strip()
            subchunks.append(_make_chunk(f"- {section_heading}", section_text))
        return subchunks

    # ========================================================================
    # Strategy 2: Fallback - split by Article headings in groups
    # ========================================================================
    article_pattern = re.compile(r'^Article\s+\d+.*$', re.MULTILINE)
    articles = list(article_pattern.finditer(text))

    if not articles:
        # No obvious split points; return original chunk
        # This shouldn't happen for well-formed EU AI Act chapters
        return [chunk]

    GROUP_SIZE = 5  # articles per subchunk
    for i in range(0, len(articles), GROUP_SIZE):
        group = articles[i : i + GROUP_SIZE]
        start = group[0].start()
        # End at the start of the next group, or end of text
        if i + GROUP_SIZE < len(articles):
            end = articles[i + GROUP_SIZE].start()
        else:
            end = len(text)

        subtext = text[start:end]
        first_article = group[0].group(0).strip()
        last_article = group[-1].group(0).strip()
        label_suffix = f"(Articles {first_article} - {last_article})"
        subchunks.append(_make_chunk(label_suffix, subtext))

    # If even the subchunks are too big, we keep them anyway because
    # we have already made them substantially smaller. The calling
    # code can still check approx_token_count if needed.

    # If somehow no subchunks were created, fall back to original chunk.
    return subchunks if subchunks else [chunk]


def split_eu_ai_act(raw_text: str) -> List[TextChunk]:
    """
    Deterministically split the EU AI Act plain text into chunks.

    The function returns a list of TextChunk objects in the order:
      1. One 'recitals' chunk containing the entire 'Whereas' section.
      2. One 'chapter' chunk per chapter (CHAPTER I, II, ...).
      3. One 'annex' chunk per annex (ANNEX I, II, ...).

    It uses simple regex patterns on headings and does NOT call any LLMs.

    Assumptions (based on typical EU regulation layout):
      - Recitals are introduced after a 'Whereas:' or similar heading and before
        the first 'CHAPTER ' heading.
      - Chapters are marked by lines containing 'CHAPTER ' followed
        by a Roman numeral and a title.
      - Annexes are marked by lines containing 'ANNEX ' followed
        by a Roman numeral and a title.

    If some parts cannot be cleanly split, include them in the nearest
    sensible chunk and document the decision in comments; do NOT drop text.

    Args:
        raw_text: The full text of the EU AI Act

    Returns:
        List of TextChunk objects representing the split document

    Raises:
        ValueError: If the text cannot be split into meaningful chunks
    """
    chunks: List[TextChunk] = []

    # ========================================================================
    # Step 1: Find all chapter boundaries
    # ========================================================================
    # Pattern for chapter headings: "CHAPTER" followed by Roman numerals
    # Example: "CHAPTER I", "CHAPTER II", "CHAPTER XIII"
    chapter_pattern = re.compile(
        r'^CHAPTER\s+([IVXLC]+)',
        re.MULTILINE | re.IGNORECASE
    )

    chapter_matches = list(chapter_pattern.finditer(raw_text))

    # ========================================================================
    # Step 2: Find all annex boundaries
    # ========================================================================
    # Pattern for annex headings: "ANNEX" followed by Roman numerals
    # Example: "ANNEX I", "ANNEX II", "ANNEX XIII"
    annex_pattern = re.compile(
        r'^ANNEX\s+([IVXLC]+)',
        re.MULTILINE | re.IGNORECASE
    )

    annex_matches = list(annex_pattern.finditer(raw_text))

    # ========================================================================
    # Step 3: Extract and split the recitals section
    # ========================================================================
    # Recitals are everything before the first chapter
    # Split into multiple chunks to avoid token limits (EU AI Act has 180+ recitals)
    if chapter_matches:
        first_chapter_pos = chapter_matches[0].start()
        recitals_text = raw_text[:first_chapter_pos].strip()

        if recitals_text:
            # Split recitals into batches to avoid context limits
            recital_chunks = _split_recitals(recitals_text)
            chunks.extend(recital_chunks)
    else:
        # No chapters found - this is unusual but handle gracefully
        # Consider the entire text before annexes as recitals
        if annex_matches:
            first_annex_pos = annex_matches[0].start()
            recitals_text = raw_text[:first_annex_pos].strip()
        else:
            recitals_text = raw_text.strip()

        if recitals_text:
            # Split recitals into batches to avoid context limits
            recital_chunks = _split_recitals(recitals_text)
            chunks.extend(recital_chunks)

    # ========================================================================
    # Step 4: Extract each chapter
    # ========================================================================
    # For each chapter, extract text from its heading to the next chapter
    # or the first annex (whichever comes first)
    for i, chapter_match in enumerate(chapter_matches):
        chapter_num = chapter_match.group(1)  # Roman numeral
        chapter_start = chapter_match.start()

        # Find the end of this chapter
        # It ends at the start of the next chapter, or the first annex, or EOF
        if i + 1 < len(chapter_matches):
            # There's another chapter after this one
            chapter_end = chapter_matches[i + 1].start()
        elif annex_matches:
            # No more chapters, but there are annexes
            chapter_end = annex_matches[0].start()
        else:
            # This is the last chapter and there are no annexes
            chapter_end = len(raw_text)

        chapter_text = raw_text[chapter_start:chapter_end].strip()

        # Check if this is CHAPTER III (HIGH-RISK AI SYSTEMS), which is very large
        # and needs to be split by sections to avoid token limits
        if chapter_num == "III":
            # Split CHAPTER III by sections to avoid exceeding 128k token limit
            chapter_section_chunks = _split_large_chapter_by_sections(chapter_text, chapter_num)
            chunks.extend(chapter_section_chunks)
        else:
            # Regular chapter - add as single chunk
            # Extract the chapter title from the first line
            # The title is usually on the same line or next line after "CHAPTER X"
            first_lines = chapter_text.split('\n', 2)
            if len(first_lines) >= 1:
                # First line contains "CHAPTER X [- TITLE]"
                chapter_label = first_lines[0].strip()
            else:
                chapter_label = f"CHAPTER {chapter_num}"

            chunks.append(TextChunk(
                kind="chapter",
                label=chapter_label,
                text=chapter_text
            ))

    # ========================================================================
    # Step 5: Extract each annex
    # ========================================================================
    # For each annex, extract text from its heading to the next annex or EOF
    for i, annex_match in enumerate(annex_matches):
        annex_num = annex_match.group(1)  # Roman numeral
        annex_start = annex_match.start()

        # Find the end of this annex
        # It ends at the start of the next annex or EOF
        if i + 1 < len(annex_matches):
            annex_end = annex_matches[i + 1].start()
        else:
            annex_end = len(raw_text)

        annex_text = raw_text[annex_start:annex_end].strip()

        # Extract the annex title from the first line
        first_lines = annex_text.split('\n', 2)
        if len(first_lines) >= 1:
            annex_label = first_lines[0].strip()
        else:
            annex_label = f"ANNEX {annex_num}"

        chunks.append(TextChunk(
            kind="annex",
            label=annex_label,
            text=annex_text
        ))

    # ========================================================================
    # Step 6: Validation
    # ========================================================================
    if not chunks:
        raise ValueError(
            "Splitter could not identify any chunks (recitals/chapters/annexes) "
            "in the provided text. Please check that the text follows the expected "
            "EU regulation format."
        )

    return chunks


def preview_chunks(chunks: List[TextChunk]) -> None:
    """
    Print a summary of the chunks for debugging.

    Args:
        chunks: List of TextChunk objects to preview
    """
    print(f"\nFound {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks, 1):
        text_preview = chunk.text[:100].replace('\n', ' ')
        print(f"  {i}. {chunk.kind:8s} | {chunk.label:30s} | {len(chunk.text):6d} chars | {text_preview}...")

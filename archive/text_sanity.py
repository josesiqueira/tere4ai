"""
Text Sanity Check Module

This module provides generic text statistics and fingerprinting functions
that can be used for any ingested text (legal documents, AI incidents, transcripts).

Purpose:
  - Transparency: Show basic stats for all ingested texts
  - Completeness checking: Detect if text is unexpectedly small/large
  - Change detection: SHA-256 hash to detect modifications
  - Reproducibility: Same text → same hash

Usage:
  from text_sanity import compute_text_stats, print_text_stats

  stats = compute_text_stats(raw_text, source_type="EU_AI_ACT", source_id="eu_ai_act_2024")
  print_text_stats(stats)
"""

from typing import Optional
from pydantic import BaseModel, Field
import hashlib


# ============================================================================
# Text Statistics Model
# ============================================================================

class TextStats(BaseModel):
    """
    Basic sanity-check statistics for a text blob.

    Can be computed for any ingested text (legal documents, incidents, transcripts).
    Provides transparency and enables completeness validation.
    """
    source_type: str = Field(
        description="High-level type of text, e.g. 'EU_AI_ACT', 'AI_INCIDENT', 'TRANSCRIPT'."
    )
    source_id: str = Field(
        description="Identifier for the text (e.g. 'eu_ai_act_2024', 'incident_0004')."
    )
    char_count: int = Field(
        description="Number of characters in the text."
    )
    word_count: int = Field(
        description="Number of whitespace-separated tokens."
    )
    line_count: int = Field(
        description="Number of newline-separated lines."
    )
    sha256: str = Field(
        description="SHA-256 hex digest of the text (for change detection)."
    )


# ============================================================================
# Statistics Computation
# ============================================================================

def compute_text_stats(text: str, source_type: str, source_id: str) -> TextStats:
    """
    Compute basic stats (chars, words, lines, hash) for any given text.

    This function is deterministic and can be used to verify that the same
    text produces the same statistics across runs.

    Args:
        text: The raw text.
        source_type: A label like 'EU_AI_ACT' or 'AI_INCIDENT'.
        source_id: Unique identifier for this text within that type.

    Returns:
        TextStats instance.

    Example:
        >>> text = "Hello world\\nThis is a test."
        >>> stats = compute_text_stats(text, "TEST", "test_001")
        >>> stats.char_count
        27
        >>> stats.word_count
        6
        >>> stats.line_count
        2
    """
    char_count = len(text)
    # Count lines: number of newlines + 1 (for the last line)
    # Handle empty text edge case
    line_count = text.count("\n") + 1 if text else 0
    word_count = len(text.split())
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return TextStats(
        source_type=source_type,
        source_id=source_id,
        char_count=char_count,
        word_count=word_count,
        line_count=line_count,
        sha256=sha256,
    )


# ============================================================================
# Display Functions
# ============================================================================

def print_text_stats(stats: TextStats) -> None:
    """
    Print text stats in a human-readable form.

    Useful in ingestion scripts to quickly inspect sizes and hashes.

    Args:
        stats: TextStats instance to display.

    Example output:
        Text stats for EU_AI_ACT / eu_ai_act_2024:
          Characters: 586234
          Words:      89456
          Lines:      4782
          SHA-256:    a3b5c7d9e1f3...
    """
    print(f"\nText stats for {stats.source_type} / {stats.source_id}:")
    print(f"  Characters: {stats.char_count:,}")
    print(f"  Words:      {stats.word_count:,}")
    print(f"  Lines:      {stats.line_count:,}")
    print(f"  SHA-256:    {stats.sha256}")

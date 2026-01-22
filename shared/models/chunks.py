"""
Chunk-level Models for Legal Document Processing

This module defines models for processing legal documents in chunks to avoid
LLM context limits. It supports breaking a large document into semantically
meaningful pieces (recitals, chapters, annexes) and processing them individually.

Key components:
  - ChunkKind: Type of chunk (recitals, chapter, annex)
  - TextChunk: Deterministic chunk of raw text (output of splitter)
  - ChunkResult: Pydantic model for LLM agent output per chunk
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from .legal import Recital, Chapter, Annex, Section

# Type definition for chunk kinds
ChunkKind = Literal["recitals", "chapter", "annex", "section"]


@dataclass
class TextChunk:
    """
    A contiguous piece of the EU AI Act text corresponding to either:
      - all recitals,
      - a single chapter,
      - a single section (for large chapters split by sections),
      - a single annex.

    This is produced deterministically by the splitter and consumed
    by the runner, which then calls the LLM agent on each chunk.

    Attributes:
        kind: Type of chunk (recitals, chapter, section, or annex)
        label: Human-readable label (e.g. "RECITALS", "CHAPTER I - SECTION 5", "ANNEX III")
        text: Raw text content for this chunk
    """
    kind: ChunkKind
    label: str        # e.g. "RECITALS", "CHAPTER I", "CHAPTER III - SECTION 5", "ANNEX III"
    text: str         # raw text for this chunk


class ChunkResult(BaseModel):
    """
    Result of preprocessing a single text chunk.

    Exactly one of the fields (recitals, chapter, section, annex) is expected
    to be non-empty / non-None based on 'kind'.

    This is the output model for the chunk-level LLM agent.
    """
    document_id: str = Field(
        description="Document identifier, echoed from deps (e.g. 'eu_ai_act_2024')."
    )
    kind: ChunkKind = Field(
        description="What kind of chunk was parsed: recitals, chapter, section, or annex."
    )
    label: str = Field(
        description="Label of this chunk (e.g. 'RECITALS', 'CHAPTER I', 'ANNEX III')."
    )

    # Only for kind == "recitals"
    recitals: List[Recital] = Field(
        default_factory=list,
        description="List of recitals parsed from this chunk (for kind='recitals')."
    )

    # Only for kind == "chapter"
    chapter: Optional[Chapter] = Field(
        default=None,
        description="Single Chapter parsed from this chunk (for kind='chapter')."
    )

    # Only for kind == "annex"
    annex: Optional[Annex] = Field(
        default=None,
        description="Single Annex parsed from this chunk (for kind='annex')."
    )

    # Only for kind == "section"
    section: Optional[Section] = Field(
        default=None,
        description="Single Section parsed from this chunk (for kind='section')."
    )

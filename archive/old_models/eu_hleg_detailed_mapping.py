"""
Pydantic models for detailed EU AI Act to HLEG mapping with subtopics.

This module defines the output structure for mapping EU AI Act paragraphs
to HLEG requirements AND their subtopics (two-level granularity).

Used by the LLM-based mapping agent in regex_preprocessing/.

TRUSTWORTHINESS PRINCIPLES:

  - The LLM chooses which HLEG requirements AND subtopics are relevant.
  - All location metadata is deterministic (provided by caller).
  - Rationales are REQUIRED for both requirement and subtopic links.
  - Only canonical requirement IDs and subtopic IDs are allowed.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class HlegSubtopicLink(BaseModel):
    """
    Link from an EU paragraph to a specific HLEG subtopic.

    Example:
      - subtopic_id: "human_agency_human_oversight"
      - confidence: 0.85
      - explanation: "This paragraph requires human oversight mechanisms..."
    """
    subtopic_id: str = Field(
        description=(
            "ID of the HLEG subtopic, e.g. 'human_agency_human_oversight'. "
            "Must be one of the canonical subtopic IDs from the HLEG guidelines."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score for this alignment, from 0.0 (low confidence) "
            "to 1.0 (very high confidence). Reflects how certain the agent is "
            "about this subtopic being relevant."
        ),
    )
    explanation: str = Field(
        description=(
            "Clear explanation of WHY this HLEG subtopic is relevant to the "
            "EU paragraph. Must reference specific text from both the paragraph "
            "and the subtopic's focus area."
        )
    )


class HlegRequirementLink(BaseModel):
    """
    Link from an EU paragraph to an HLEG requirement, with optional subtopic links.

    Example:
      - requirement_id: "human_agency_and_oversight"
      - confidence: 0.9
      - explanation: "This paragraph imposes human oversight obligations..."
      - subtopic_links: [HlegSubtopicLink(...), ...]
    """
    requirement_id: str = Field(
        description=(
            "ID of the HLEG requirement, e.g. 'human_agency_and_oversight'. "
            "Must be one of the canonical seven requirement IDs."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score for this alignment, from 0.0 (low confidence) "
            "to 1.0 (very high confidence). Reflects how certain the agent is "
            "about this requirement being relevant to the EU paragraph."
        ),
    )
    explanation: str = Field(
        description=(
            "Clear explanation of WHY this HLEG requirement is relevant to the "
            "EU paragraph. Must reference specific obligations/prohibitions from "
            "the paragraph and how they relate to the requirement's main idea."
        )
    )
    subtopic_links: List[HlegSubtopicLink] = Field(
        default_factory=list,
        description=(
            "Zero or more links to specific subtopics within this requirement. "
            "Only include subtopics that are directly relevant to the paragraph."
        ),
    )


class EuParagraphLocation(BaseModel):
    """
    Deterministic location of an EU AI Act paragraph.

    We use structural location (not invented IDs):
      - document_id: e.g. 'eu_ai_act_2024'
      - chapter_number: e.g. 'III'
      - article_number: e.g. '9'
      - paragraph_index: integer index within the article
    """
    document_id: str = Field(
        description="ID of the EU AI Act document, e.g. 'eu_ai_act_2024'."
    )
    chapter_number: str = Field(
        description="Chapter number as string, e.g. 'III'."
    )
    article_number: str = Field(
        description="Article number as string, e.g. '9'."
    )
    paragraph_index: int = Field(
        description=(
            "Paragraph index inside the article (must match the structural "
            "preprocessing, e.g. 1 for '1.', 2 for '2.', etc.)."
        )
    )


class EuToHlegDetailedMapping(BaseModel):
    """
    Mapping from one EU AI Act paragraph to HLEG requirements AND subtopics.

    This is the OUTPUT of the detailed EU→HLEG mapping agent.

    If 'requirement_links' is empty, it means the agent decided that this
    EU paragraph is not meaningfully aligned with any HLEG requirements.
    """
    location: EuParagraphLocation = Field(
        description="Structural location of the EU paragraph."
    )
    paragraph_text: str = Field(
        description="Full text of the EU paragraph being classified."
    )
    requirement_links: List[HlegRequirementLink] = Field(
        default_factory=list,
        description=(
            "Zero or more links to HLEG requirements, each with "
            "relevance, rationale, and optional subtopic links."
        ),
    )


class EuHlegDetailedMappingDeps(BaseModel):
    """
    Deterministic metadata for a single EU paragraph being mapped.

    All of these values are provided by the caller and must be echoed
    exactly into the output EuParagraphLocation.
    """
    document_id: str = Field(
        description="EU AI Act document id, e.g. 'eu_ai_act_2024'."
    )
    chapter_number: str = Field(
        description="Chapter number as string, e.g. 'III'."
    )
    article_number: str = Field(
        description="Article number as string, e.g. '9'."
    )
    paragraph_index: int = Field(
        description=(
            "Paragraph index inside the article (consistent with structural "
            "preprocessing)."
        )
    )

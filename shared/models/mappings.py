"""
Pydantic models for mapping EU AI Act requirements to HLEG requirements.

This module defines:
  - HlegLink: one link from an EU requirement paragraph to a single
    HLEG requirement, with a relevance score and rationale.
  - EuRequirementLocation: deterministic location of the EU paragraph.
  - EuToHlegMapping: the mapping for one EU paragraph (location + links).

TRUSTWORTHINESS PRINCIPLES:

  - The LLM chooses which HLEG requirements are relevant and provides
    a rationale grounded in both texts.

  - All location metadata (document_id, chapter_number, article_number,
    paragraph_index) is deterministic and provided by the caller.

  - Ingestion into Neo4j is deterministic and idempotent: MERGE on
    Paragraph + HLEGRequirement, MERGE the relationship, SET properties.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class HlegLink(BaseModel):
    """
    One link from an EU requirement paragraph to a single HLEG requirement.

    Example:
      - hleg_requirement_id: "technical_robustness_and_safety"
      - relevance: 0.9
      - rationale: "This paragraph imposes robustness obligations ..."
    """
    hleg_requirement_id: str = Field(
        description=(
            "ID of the HLEG requirement, e.g. 'technical_robustness_and_safety'. "
            "Must be one of the canonical seven requirement IDs."
        )
    )
    relevance: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How strongly this EU paragraph relates to the given HLEG "
            "requirement, from 0.0 (not related) to 1.0 (very strongly related)."
        ),
    )
    rationale: str = Field(
        description=(
            "Short explanation of WHY this HLEG requirement is relevant, "
            "grounded in both the EU paragraph and the HLEG requirement "
            "description."
        )
    )


class EuRequirementLocation(BaseModel):
    """
    Deterministic location of an EU AI Act 'requirement paragraph'.

    We do NOT invent IDs here; we use structural location:
      - document_id: e.g. 'eu_ai_act_2024'
      - chapter_number: e.g. 'III'
      - article_number: e.g. '9'
      - paragraph_index: integer index within the article (1-based or 0-based,
        but must be consistent with the structural ingestion).
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


class EuToHlegMapping(BaseModel):
    """
    Mapping from one EU requirement paragraph to zero or more HLEG
    requirements.

    This is the OUTPUT of the EU→HLEG mapping agent.

    If 'links' is empty, it means the agent decided that this EU paragraph
    is not meaningfully aligned with any of the seven HLEG requirements.
    """
    location: EuRequirementLocation = Field(
        description="Structural location of the EU paragraph."
    )
    paragraph_text: str = Field(
        description="Full text of the EU paragraph being classified."
    )
    links: List[HlegLink] = Field(
        default_factory=list,
        description=(
            "Zero or more links to HLEG requirements, each with "
            "relevance and rationale."
        ),
    )

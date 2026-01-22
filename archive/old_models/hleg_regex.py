"""
Pydantic models for AI HLEG regex-based extraction.

This module defines the structural representation of the AI HLEG
"Ethics Guidelines for Trustworthy AI" as extracted by regex-based
preprocessing (no LLM involved).

These models mirror the structure used by the LLM-based agent approach
(models/ai_hleg.py) but are used specifically for the deterministic
regex extraction pipeline in regex_preprocessing/preprocess_ai_hleg.py.

TRUSTWORTHINESS PRINCIPLES:

  - The seven requirements are a CLOSED, CANONICAL set.
  - All extraction is deterministic (regex-based, no LLM).
  - Models are compatible with Neo4j ingestion.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class HlegSubtopicRegex(BaseModel):
    """
    A subtopic under a requirement (regex extraction).

    Example (under 'Human agency and oversight'):
      - id: "human_agency_human_oversight"
      - label: "Human oversight"
      - description: "Human oversight helps ensuring that an AI system..."
    """
    id: str = Field(
        description="Stable machine identifier for this subtopic."
    )
    label: str = Field(
        description="Short human-readable label (the heading in the guidelines)."
    )
    description: str = Field(
        description="Full text of the subtopic extracted from the guidelines."
    )


class HlegRequirementRegex(BaseModel):
    """
    One of the seven requirements of Trustworthy AI (regex extraction).

    Example:
      - id: "human_agency_and_oversight"
      - order: 1
      - name: "Human agency and oversight"
    """
    id: str = Field(
        description="Stable machine identifier for this requirement."
    )
    order: int = Field(
        description="Canonical order of the requirement (1..7)."
    )
    name: str = Field(
        description="Official name of the requirement."
    )
    short_description: str = Field(
        description="Short summary (1-3 sentences) of the requirement."
    )
    full_text: str = Field(
        description="Substantial excerpt of the requirement's section."
    )
    related_principles: List[str] = Field(
        default_factory=list,
        description="Optional list of HLEG ethical principle IDs."
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Optional keywords for querying/grouping."
    )
    subtopics: List[HlegSubtopicRegex] = Field(
        default_factory=list,
        description="List of subtopics under this requirement."
    )


class HlegDocumentRegex(BaseModel):
    """
    Complete structure of the AI HLEG Ethics Guidelines (regex extraction).

    This is the output of the regex-based preprocessing pipeline.
    """
    document_id: str = Field(
        description="Stable identifier for this HLEG document, e.g. 'ai_hleg_2019'."
    )
    official_title: str = Field(
        description="Full official title of the guidelines."
    )
    short_title: str = Field(
        description="Short title, e.g. 'AI HLEG Ethics Guidelines'."
    )
    year: int = Field(
        description="Year of publication of the guidelines."
    )
    requirements: List[HlegRequirementRegex] = Field(
        default_factory=list,
        description="List of the seven requirements of Trustworthy AI."
    )

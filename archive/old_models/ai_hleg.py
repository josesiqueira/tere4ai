"""
Pydantic Models for AI HLEG "Ethics Guidelines for Trustworthy AI"

This module defines the structural representation of the
seven key requirements of Trustworthy AI from the AI HLEG
guidelines, plus optional RequirementSubtopics under each
requirement.

IMPORTANT TRUSTWORTHINESS PRINCIPLES:

  - The seven requirements are a CLOSED, CANONICAL set.
    The LLM must not invent additional requirements.

  - Each requirement has:
      * a stable machine id (snake_case)
      * canonical name (as in the guidelines)
      * canonical order (1..7)
      * a short description (faithful summary)
      * a full_text field (substantial excerpt from the guidelines)
      * an optional list of RequirementSubtopics

  - RequirementSubtopics are titled sub-sections under a single
    requirement (e.g. "Sustainable and environmentally friendly AI",
    "Social impact", "Society and Democracy" under societal and
    environmental well-being). They are NOT new requirements,
    but aspects/themes of one requirement.

  - This module does NOT contain any logic for mapping incidents,
    EU AI Act obligations, or other semantics. It is purely
    about representing the HLEG structure.

This mirrors the philosophy of the EU AI Act structural models:
we first extract structure in a trustworthy way, and only later
add semantic layers (e.g. risk mapping, incident alignment).
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class HlegRequirementSubtopic(BaseModel):
    """
    A titled subtopic under a single HLEG requirement.

    Example (under 'Societal and environmental well-being'):
      - label: "Sustainable and environmentally friendly AI"
      - description: the full paragraph(s) under that heading.

    These are NOT additional requirements. They are aspects/themes
    of one canonical requirement, useful for more fine-grained
    linking (e.g. to incidents, EU AI Act provisions).
    """
    id: str = Field(
        description=(
            "Stable machine identifier for this subtopic, e.g. "
            "'societal_env_wellbeing_sustainable_ai'. Must be unique "
            "within the document and grounded in the heading."
        )
    )
    label: str = Field(
        description=(
            "Short human-readable label for the subtopic, usually the "
            "titled heading in the guidelines, e.g. "
            "'Sustainable and environmentally friendly AI'."
        )
    )
    description: str = Field(
        description=(
            "Full text of the subtopic (the paragraph(s) under the heading), "
            "cleaned for whitespace but grounded in the original document."
        )
    )


class HlegRequirement(BaseModel):
    """
    One of the seven requirements of Trustworthy AI from the AI HLEG guidelines.

    Example:
      - id: "human_agency_and_oversight"
      - order: 1
      - name: "Human agency and oversight"
    """
    id: str = Field(
        description=(
            "Stable machine identifier for this requirement, "
            "e.g. 'human_agency_and_oversight'. "
            "Must come from a CLOSED, predefined list."
        )
    )
    order: int = Field(
        description="Canonical order of the requirement (1..7)."
    )
    name: str = Field(
        description="Official name of the requirement as used in the guidelines."
    )
    short_description: str = Field(
        description=(
            "Short summary (1–3 sentences) of the requirement, "
            "faithfully derived from the guidelines."
        )
    )
    full_text: str = Field(
        description=(
            "Substantial excerpt of the requirement's section from the guidelines. "
            "Should be grounded in the original text (verbatim or lightly cleaned), "
            "NOT invented."
        )
    )
    related_principles: List[str] = Field(
        default_factory=list,
        description=(
            "Optional list of HLEG ethical principle IDs that underpin this requirement, "
            "e.g. ['respect_for_human_autonomy', 'prevention_of_harm']."
        ),
    )
    tags: List[str] = Field(
        default_factory=list,
        description=(
            "Optional free-form keywords for querying/grouping, "
            "e.g. ['safety', 'robustness', 'non-discrimination']."
        ),
    )
    subtopics: List[HlegRequirementSubtopic] = Field(
        description=(
            "List of titled RequirementSubtopics under this requirement "
            "(may be empty if no subtopics exist). "
            "Examples: 'Sustainable and environmentally friendly AI', "
            "'Social impact', 'Society and Democracy' under "
            "societal and environmental well-being."
        ),
    )


class HlegStructuredDoc(BaseModel):
    """
    Structural representation of the AI HLEG guidelines at the level of
    the seven requirements of Trustworthy AI, plus optional subtopics.

    This is the output of the AI HLEG preprocessing agent.
    It is intentionally minimal: we only capture what we need
    to later connect to EU AI Act obligations and incidents.
    """
    document_id: str = Field(
        description=(
            "Stable identifier for this HLEG document, e.g. 'ai_hleg_2019'. "
            "Provided deterministically by the caller, NOT inferred by the LLM."
        )
    )
    official_title: str = Field(
        description="Full official title of the guidelines."
    )
    short_title: Optional[str] = Field(
        default=None,
        description="Optional short title, e.g. 'AI HLEG Ethics Guidelines'."
    )
    year: int = Field(
        description="Year of publication of the guidelines, e.g. 2019."
    )

    requirements: List[HlegRequirement] = Field(
        default_factory=list,
        description="List of the seven requirements of Trustworthy AI."
    )

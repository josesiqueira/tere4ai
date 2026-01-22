"""
Pydantic Models for Citations and Traceability

This module defines the core citation system for TERE4AI - the foundation
of legal traceability. Every generated requirement must be anchored to
specific legal/ethical sources with exact references.

TRUSTWORTHINESS PRINCIPLES:

  - Citations provide VERIFIABLE references to source documents
  - All quoted text must be grounded in actual document content
  - Relevance scores (for HLEG) enable weighted analysis
  - CitationBundle groups related citations with rationale

This is the core of what makes TERE4AI useful: full traceability from
generated requirements back to EU AI Act articles and HLEG principles.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Set

from pydantic import BaseModel, Field, field_validator


# Canonical HLEG requirement IDs - these are the only valid values
CANONICAL_HLEG_IDS: Set[str] = {
    "human_agency_and_oversight",
    "technical_robustness_and_safety",
    "privacy_and_data_governance",
    "transparency",
    "diversity_non_discrimination_and_fairness",
    "societal_and_environmental_wellbeing",
    "accountability",
}


class Citation(BaseModel):
    """
    A traceable reference to a legal/ethical source document.

    This is THE KEY DATA STRUCTURE for traceability. Every requirement,
    classification, or recommendation must be anchored to Citations.

    Examples:
      - EU AI Act Article 9(1): risk management requirement
      - EU AI Act Recital (29): harm to victims context
      - HLEG Technical Robustness: resilience to attack subtopic
    """

    source: Literal["EU_AI_ACT", "AI_HLEG"] = Field(
        description="Which source document this citation references."
    )
    document_id: str = Field(
        description="Stable document identifier, e.g. 'eu_ai_act_2024' or 'ai_hleg_2019'."
    )

    # Structural location (for EU AI Act)
    chapter: Optional[str] = Field(
        default=None,
        description="Chapter number as string, e.g. 'III'. Only for EU AI Act."
    )
    section: Optional[str] = Field(
        default=None,
        description="Section number within chapter, e.g. '2'. Only for EU AI Act."
    )
    article: Optional[str] = Field(
        default=None,
        description="Article number as string, e.g. '9'. Only for EU AI Act."
    )
    paragraph: Optional[int] = Field(
        default=None,
        description="Paragraph number within article, e.g. 1 for '1.'. Only for EU AI Act."
    )
    point: Optional[str] = Field(
        default=None,
        description="Point marker within paragraph, e.g. 'a'. Only for EU AI Act."
    )
    recital: Optional[int] = Field(
        default=None,
        description="Recital number, e.g. 29 for Recital (29). Only for EU AI Act."
    )
    annex: Optional[str] = Field(
        default=None,
        description="Annex number as string, e.g. 'III'. Only for EU AI Act."
    )
    annex_section: Optional[str] = Field(
        default=None,
        description="Section within annex, e.g. '5(a)'. Only for EU AI Act."
    )

    # For HLEG references
    requirement_id: Optional[str] = Field(
        default=None,
        description=(
            "HLEG requirement ID, e.g. 'technical_robustness_and_safety'. "
            "Must be one of the canonical seven. Only for AI_HLEG source."
        )
    )
    subtopic_id: Optional[str] = Field(
        default=None,
        description=(
            "HLEG subtopic ID within a requirement, e.g. 'resilience_to_attack'. "
            "Only for AI_HLEG source."
        )
    )

    # Content
    reference_text: str = Field(
        description=(
            "Human-readable reference, e.g. 'Article 9(1)' or "
            "'HLEG: Technical Robustness & Safety'."
        )
    )
    quoted_text: str = Field(
        description=(
            "Actual text from the source document. Must be grounded in "
            "the original, not invented."
        )
    )
    relevance_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Relevance score (0.0-1.0) for HLEG mappings. Indicates how "
            "strongly this source relates to the requirement. Optional."
        )
    )

    @field_validator('paragraph', mode='before')
    @classmethod
    def coerce_paragraph_to_int(cls, v):
        """Convert string to int if needed."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                raise ValueError(
                    f"Invalid paragraph number: '{v}' is not a valid integer"
                )
        return v

    @field_validator('recital', mode='before')
    @classmethod
    def coerce_recital_to_int(cls, v):
        """Convert string to int if needed."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                raise ValueError(
                    f"Invalid recital number: '{v}' is not a valid integer"
                )
        return v

    @field_validator('requirement_id')
    @classmethod
    def validate_hleg_requirement_id(cls, v):
        """Validate that requirement_id is one of the canonical seven HLEG IDs."""
        if v is not None and v not in CANONICAL_HLEG_IDS:
            raise ValueError(
                f"Invalid HLEG requirement ID: '{v}'. "
                f"Must be one of: {sorted(CANONICAL_HLEG_IDS)}"
            )
        return v

    def format_reference(self) -> str:
        """
        Generate a formatted reference string.

        Examples:
          - "Article 9(1)(a)"
          - "Recital (29)"
          - "Annex III, Section 5(a)"
          - "HLEG: Technical Robustness & Safety - Resilience to attack"
        """
        if self.source == "EU_AI_ACT":
            if self.recital:
                return f"Recital ({self.recital})"
            if self.annex:
                if self.annex_section:
                    return f"Annex {self.annex}, Section {self.annex_section}"
                return f"Annex {self.annex}"
            if self.article:
                ref = f"Article {self.article}"
                if self.paragraph:
                    ref += f"({self.paragraph})"
                    if self.point:
                        ref += f"({self.point})"
                return ref
            return self.reference_text
        else:  # AI_HLEG
            ref = f"HLEG: {self.reference_text}"
            if self.subtopic_id:
                ref += f" - {self.subtopic_id.replace('_', ' ').title()}"
            return ref


class CitationBundle(BaseModel):
    """
    Collection of citations supporting a single claim or requirement.

    Groups a primary legal basis with supporting citations (recitals,
    HLEG principles, etc.) and provides a rationale for why these
    citations together support the claim.

    Example:
      Primary: Article 9(1) - Risk management requirement
      Supporting:
        - Article 9(2)(a) - Specific risk identification
        - Recital (47) - Context on risk management
        - HLEG Technical Robustness - Ethical grounding
      Rationale: "Article 9 mandates comprehensive risk management..."
    """

    primary: Citation = Field(
        description="The main legal basis - the primary citation for this claim."
    )
    supporting: List[Citation] = Field(
        default_factory=list,
        description=(
            "Additional citations that support or contextualize the primary. "
            "Includes recitals, HLEG mappings, related articles, etc."
        )
    )
    rationale: str = Field(
        description=(
            "Explanation of why these citations together support the claim. "
            "Should connect the legal text to the specific context."
        )
    )

    def all_citations(self) -> List[Citation]:
        """Return all citations (primary + supporting) as a flat list."""
        return [self.primary] + self.supporting

    def count_by_source(self) -> dict[str, int]:
        """Count citations by source document."""
        counts: dict[str, int] = {"EU_AI_ACT": 0, "AI_HLEG": 0}
        for citation in self.all_citations():
            counts[citation.source] += 1
        return counts

    def get_articles_cited(self) -> List[str]:
        """Return list of unique article numbers cited."""
        articles = set()
        for citation in self.all_citations():
            if citation.article:
                articles.add(citation.article)
        return sorted(articles, key=lambda x: int(x) if x.isdigit() else 0)

    def get_hleg_requirements_cited(self) -> List[str]:
        """Return list of unique HLEG requirement IDs cited."""
        requirements = set()
        for citation in self.all_citations():
            if citation.requirement_id:
                requirements.add(citation.requirement_id)
        return sorted(requirements)

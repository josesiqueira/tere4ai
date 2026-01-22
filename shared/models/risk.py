"""
Pydantic Models for Risk Classification

This module defines the risk classification output from the Analysis Agent.
It captures the EU AI Act risk level determination with full legal grounding.

RISK LEVELS (EU AI Act):

  - UNACCEPTABLE: Article 5 prohibited practices - system cannot be developed
  - HIGH: Article 6 + Annex III - full Chapter III requirements apply
  - LIMITED: Article 50 - transparency obligations only
  - MINIMAL: No specific regulatory obligations

TRUSTWORTHINESS PRINCIPLES:

  - Every classification must cite the specific legal basis
  - Article 6(3) exceptions must be explicitly checked for Annex III matches
  - HLEG principles violated/applicable are documented
  - Full reasoning chain is preserved for auditability
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .citations import Citation, CitationBundle


class RiskLevel(str, Enum):
    """
    EU AI Act risk levels.

    These map directly to the regulatory framework:
      - UNACCEPTABLE: Prohibited under Article 5
      - HIGH: Regulated under Chapter III (Articles 8-27)
      - LIMITED: Transparency obligations under Article 50
      - MINIMAL: No specific obligations
    """

    UNACCEPTABLE = "unacceptable"
    HIGH = "high"
    LIMITED = "limited"
    MINIMAL = "minimal"


class AnnexIIICategory(str, Enum):
    """
    High-risk AI system categories from Annex III.

    These are the 8 categories of high-risk AI systems that trigger
    Chapter III obligations (when not exempted by Article 6(3)).
    """

    BIOMETRICS = "1"  # Biometric identification and categorisation
    CRITICAL_INFRASTRUCTURE = "2"  # Critical infrastructure management
    EDUCATION_TRAINING = "3"  # Education and vocational training
    EMPLOYMENT = "4"  # Employment, workers management, self-employment
    ESSENTIAL_SERVICES = "5"  # Access to essential services
    LAW_ENFORCEMENT = "6"  # Law enforcement
    MIGRATION_ASYLUM = "7"  # Migration, asylum, border control
    JUSTICE_DEMOCRACY = "8"  # Administration of justice and democratic processes


class ProhibitedPractice(str, Enum):
    """
    Prohibited AI practices from Article 5.

    These practices are banned outright - systems implementing them
    cannot be legally developed or deployed in the EU.
    """

    SUBLIMINAL_MANIPULATION = "5_1_a"  # Subliminal/manipulative techniques
    EXPLOITATION_VULNERABILITY = "5_1_b"  # Exploiting vulnerabilities
    SOCIAL_SCORING = "5_1_c"  # Social scoring by public authorities
    CRIME_PREDICTION_PROFILING = "5_1_d"  # Individual crime prediction from profiling
    FACIAL_SCRAPING = "5_1_e"  # Untargeted facial image scraping
    EMOTION_INFERENCE_WORKPLACE = "5_1_f"  # Emotion inference in workplace/education
    BIOMETRIC_CATEGORIZATION = "5_1_g"  # Biometric categorization (sensitive attributes)
    REAL_TIME_BIOMETRIC_PUBLIC = "5_1_h"  # Real-time biometric in public spaces (exceptions exist)


class RiskClassification(BaseModel):
    """
    Complete risk classification output from the Analysis Agent.

    This captures:
      - The determined risk level
      - Full legal basis with citations
      - Specific prohibition or Annex III category (if applicable)
      - Article 6(3) exception status (for Annex III matches)
      - HLEG principles that are violated or apply
      - Complete reasoning chain

    For UNACCEPTABLE: No requirements will be generated
    For HIGH: Full Chapter III requirements apply (Articles 8-27)
    For LIMITED: Only Article 50 transparency requirements
    For MINIMAL: General recommendations only
    """

    level: RiskLevel = Field(
        description="The determined risk level for this AI system."
    )

    legal_basis: CitationBundle = Field(
        description=(
            "The legal grounding for this classification. Primary citation is "
            "the main article/annex that triggers this level."
        )
    )

    # For UNACCEPTABLE risk
    prohibited_practice: Optional[ProhibitedPractice] = Field(
        default=None,
        description=(
            "Which Article 5 prohibition applies. Only set when level is UNACCEPTABLE."
        )
    )
    prohibition_details: Optional[str] = Field(
        default=None,
        description=(
            "Specific explanation of which aspect of Article 5 is violated. "
            "Only set when level is UNACCEPTABLE."
        )
    )

    # For HIGH risk
    annex_iii_category: Optional[AnnexIIICategory] = Field(
        default=None,
        description=(
            "Which Annex III category this system falls under. "
            "Only set when level is HIGH."
        )
    )
    annex_iii_subcategory: Optional[str] = Field(
        default=None,
        description=(
            "Specific subcategory within Annex III, e.g. '5(a)' for healthcare triage. "
            "Only set when level is HIGH."
        )
    )
    applicable_articles: List[str] = Field(
        default_factory=list,
        description=(
            "List of Chapter III article numbers that apply. "
            "For HIGH risk: typically Articles 8-27. "
            "For LIMITED: typically just Article 50."
        )
    )
    article_6_3_exception_checked: bool = Field(
        default=False,
        description=(
            "Whether Article 6(3) exception was evaluated. Must be True for "
            "any Annex III match to confirm it wasn't exempted."
        )
    )
    article_6_3_exception_applies: bool = Field(
        default=False,
        description=(
            "Whether Article 6(3) exception actually applies (system is "
            "not high-risk despite Annex III match). If True, level should "
            "be LIMITED or MINIMAL, not HIGH."
        )
    )
    article_6_3_rationale: Optional[str] = Field(
        default=None,
        description=(
            "Explanation of Article 6(3) exception analysis. Required when "
            "article_6_3_exception_checked is True."
        )
    )

    # HLEG alignment
    hleg_implications: List[Citation] = Field(
        default_factory=list,
        description=(
            "HLEG principles that are relevant to this classification. "
            "For UNACCEPTABLE: principles that are violated. "
            "For HIGH/LIMITED: principles that must be addressed."
        )
    )

    # Reasoning
    reasoning: str = Field(
        description=(
            "Complete explanation of how the risk level was determined. "
            "Should trace through the classification logic step by step."
        )
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in this classification (0.0-1.0). Lower values "
            "indicate ambiguity that may require human review."
        )
    )

    def is_prohibited(self) -> bool:
        """Check if this system is prohibited under Article 5."""
        return self.level == RiskLevel.UNACCEPTABLE

    def requires_chapter_iii_compliance(self) -> bool:
        """Check if full Chapter III compliance is required."""
        return self.level == RiskLevel.HIGH

    def requires_transparency_only(self) -> bool:
        """Check if only transparency obligations apply."""
        return self.level == RiskLevel.LIMITED

    def get_applicable_article_range(self) -> str:
        """Get human-readable range of applicable articles."""
        if not self.applicable_articles:
            return "None"
        if len(self.applicable_articles) == 1:
            return f"Article {self.applicable_articles[0]}"
        return f"Articles {self.applicable_articles[0]}-{self.applicable_articles[-1]}"


class RiskClassificationResult(BaseModel):
    """
    Wrapper for risk classification results from MCP tools.

    This is what the classify_risk_level MCP tool returns,
    providing a simpler interface for the agent to use.
    """

    risk_level: RiskLevel = Field(
        description="The determined risk level."
    )
    legal_basis_article: Optional[str] = Field(
        default=None,
        description="Primary article/annex reference, e.g. '5(1)(c)' or 'Annex III, 5(a)'."
    )
    legal_basis_text: str = Field(
        description="Quoted text from the legal basis."
    )
    annex_category: Optional[str] = Field(
        default=None,
        description="Annex III category if applicable."
    )
    article_6_exception: bool = Field(
        default=False,
        description="Whether Article 6(3) exception applies."
    )
    hleg_principles: List[str] = Field(
        default_factory=list,
        description="List of relevant HLEG requirement IDs."
    )
    reasoning: str = Field(
        description="Brief explanation of the classification."
    )

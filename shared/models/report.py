"""
Pydantic Models for Requirements Report

This module defines the complete output of the TERE4AI pipeline -
the RequirementsReport that contains everything needed for the user.

The report includes:
  - Original system description
  - Risk classification with legal basis
  - Generated requirements with citations
  - Coverage analysis
  - Validation results
  - Academic metrics

TRUSTWORTHINESS PRINCIPLES:

  - Complete traceability from input to output
  - All citations are verifiable
  - Coverage metrics are transparent
  - Report is self-contained and exportable
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, computed_field

from .citations import Citation
from .requirements import GeneratedRequirement, ValidationResult
from .risk import RiskClassification, RiskLevel
from .system_description import SystemDescription


class CoverageMatrix(BaseModel):
    """
    Coverage matrix showing which requirements address which sources.

    Maps HLEG principles → requirement IDs and articles → requirement IDs.
    """

    # HLEG principle → list of requirement IDs that address it
    hleg_to_requirements: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping from HLEG requirement IDs to requirement IDs that address them."
    )

    # HLEG subtopic → list of requirement IDs
    subtopic_to_requirements: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping from HLEG subtopic IDs to requirement IDs that address them."
    )

    # EU AI Act article → list of requirement IDs
    article_to_requirements: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping from article numbers to requirement IDs derived from them."
    )

    # Requirement ID → list of articles it derives from
    requirement_to_articles: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping from requirement IDs to their source articles."
    )

    # Requirement ID → list of HLEG principles it addresses
    requirement_to_hleg: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping from requirement IDs to HLEG principles they address."
    )

    def get_uncovered_articles(self, applicable_articles: List[str]) -> List[str]:
        """Get list of applicable articles not covered by any requirement."""
        covered = set(self.article_to_requirements.keys())
        applicable = set(applicable_articles)
        return sorted(applicable - covered, key=lambda x: int(x) if x.isdigit() else 0)

    def get_uncovered_hleg(self) -> List[str]:
        """Get list of HLEG principles not addressed by any requirement."""
        all_hleg = {
            "human_agency_and_oversight",
            "technical_robustness_and_safety",
            "privacy_and_data_governance",
            "transparency",
            "diversity_non_discrimination_and_fairness",
            "societal_and_environmental_wellbeing",
            "accountability",
        }
        covered = set(self.hleg_to_requirements.keys())
        return sorted(all_hleg - covered)


class ReportMetrics(BaseModel):
    """
    Quantitative metrics for academic analysis.

    These metrics support the REFSQ paper's preliminary results.
    """

    # Citation counts
    total_citations: int = Field(
        default=0,
        description="Total number of citations across all requirements."
    )
    eu_ai_act_citations: int = Field(
        default=0,
        description="Number of EU AI Act citations."
    )
    hleg_citations: int = Field(
        default=0,
        description="Number of HLEG citations."
    )
    recital_citations: int = Field(
        default=0,
        description="Number of recital citations."
    )

    # Unique sources
    unique_articles_cited: int = Field(
        default=0,
        description="Number of unique EU AI Act articles cited."
    )
    unique_paragraphs_cited: int = Field(
        default=0,
        description="Number of unique paragraphs cited."
    )
    unique_recitals_cited: int = Field(
        default=0,
        description="Number of unique recitals cited."
    )
    unique_hleg_principles_addressed: int = Field(
        default=0,
        description="Number of unique HLEG principles addressed (max 7)."
    )
    unique_hleg_subtopics_addressed: int = Field(
        default=0,
        description="Number of unique HLEG subtopics addressed."
    )

    # Coverage percentages
    article_coverage_percentage: float = Field(
        default=0.0,
        description="Percentage of applicable articles covered."
    )
    hleg_coverage_percentage: float = Field(
        default=0.0,
        description="Percentage of HLEG principles addressed (out of 7)."
    )

    # Requirement counts
    total_requirements: int = Field(
        default=0,
        description="Total number of generated requirements."
    )
    critical_requirements: int = Field(
        default=0,
        description="Number of critical priority requirements."
    )
    high_requirements: int = Field(
        default=0,
        description="Number of high priority requirements."
    )


class RequirementsReport(BaseModel):
    """
    Complete output of the TERE4AI analysis pipeline.

    This is the final deliverable to the user, containing:
      - Their system description (echoed back)
      - Risk classification with full legal grounding
      - Generated requirements with citations
      - Coverage analysis and validation
      - Academic metrics

    For UNACCEPTABLE risk: requirements list is empty, prohibition is explained
    For HIGH risk: full requirements with Chapter III coverage
    For LIMITED risk: transparency requirements only
    For MINIMAL risk: general recommendations only
    """

    # Metadata
    generated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when this report was generated."
    )
    tere4ai_version: str = Field(
        default="0.1.0",
        description="Version of TERE4AI that generated this report."
    )
    report_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for this report (for export/storage)."
    )

    # Input echo (Optional for error cases where extraction failed)
    system_description: Optional[SystemDescription] = Field(
        default=None,
        description="The structured system description extracted from user input. None if extraction failed."
    )

    # Risk classification (Optional for error cases where classification failed)
    risk_classification: Optional[RiskClassification] = Field(
        default=None,
        description="The determined risk level with full legal grounding. None if classification failed."
    )

    # Generated requirements (empty if UNACCEPTABLE)
    requirements: List[GeneratedRequirement] = Field(
        default_factory=list,
        description=(
            "List of generated requirements. Empty if risk is UNACCEPTABLE. "
            "Full Chapter III requirements for HIGH risk. "
            "Transparency requirements only for LIMITED risk."
        )
    )

    # Validation results
    validation: Optional[ValidationResult] = Field(
        default=None,
        description="Results of requirement validation. None for UNACCEPTABLE risk."
    )

    # Coverage analysis
    coverage_matrix: CoverageMatrix = Field(
        default_factory=CoverageMatrix,
        description="Coverage matrix showing requirement ↔ source mappings."
    )

    # Metrics
    metrics: ReportMetrics = Field(
        default_factory=ReportMetrics,
        description="Quantitative metrics for academic analysis."
    )

    # Processing metadata
    processing_phases: List[str] = Field(
        default_factory=list,
        description="List of RE phases executed (for progress tracking)."
    )
    processing_errors: List[str] = Field(
        default_factory=list,
        description="Any errors encountered during processing."
    )
    processing_warnings: List[str] = Field(
        default_factory=list,
        description="Any warnings encountered during processing."
    )

    @computed_field
    @property
    def is_prohibited(self) -> bool:
        """Check if this system is prohibited."""
        if self.risk_classification is None:
            return False
        return self.risk_classification.level == RiskLevel.UNACCEPTABLE

    @computed_field
    @property
    def has_requirements(self) -> bool:
        """Check if requirements were generated."""
        return len(self.requirements) > 0

    def get_requirements_by_category(self) -> Dict[str, List[GeneratedRequirement]]:
        """Group requirements by category."""
        grouped: Dict[str, List[GeneratedRequirement]] = {}
        for req in self.requirements:
            category = req.category.value
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(req)
        return grouped

    def get_requirements_by_priority(self) -> Dict[str, List[GeneratedRequirement]]:
        """Group requirements by priority."""
        grouped: Dict[str, List[GeneratedRequirement]] = {}
        for req in self.requirements:
            priority = req.priority.value
            if priority not in grouped:
                grouped[priority] = []
            grouped[priority].append(req)
        return grouped

    def get_all_citations(self) -> List[Citation]:
        """Get all citations from all requirements."""
        citations: List[Citation] = []
        for req in self.requirements:
            citations.extend(req.eu_ai_act_citations)
            citations.extend(req.hleg_citations)
            citations.extend(req.supporting_recitals)
        return citations

    def compute_metrics(self) -> None:
        """Compute metrics based on current requirements."""
        all_citations = self.get_all_citations()

        # Citation counts
        self.metrics.total_citations = len(all_citations)
        self.metrics.eu_ai_act_citations = sum(
            1 for c in all_citations if c.source == "EU_AI_ACT" and not c.recital
        )
        self.metrics.hleg_citations = sum(
            1 for c in all_citations if c.source == "AI_HLEG"
        )
        self.metrics.recital_citations = sum(
            1 for c in all_citations if c.recital is not None
        )

        # Unique sources
        articles = set()
        paragraphs = set()
        recitals = set()
        hleg_principles = set()
        hleg_subtopics = set()

        for citation in all_citations:
            if citation.article:
                articles.add(citation.article)
                if citation.paragraph:
                    paragraphs.add(f"{citation.article}.{citation.paragraph}")
            if citation.recital:
                recitals.add(citation.recital)
            if citation.requirement_id:
                hleg_principles.add(citation.requirement_id)
            if citation.subtopic_id:
                hleg_subtopics.add(citation.subtopic_id)

        self.metrics.unique_articles_cited = len(articles)
        self.metrics.unique_paragraphs_cited = len(paragraphs)
        self.metrics.unique_recitals_cited = len(recitals)
        self.metrics.unique_hleg_principles_addressed = len(hleg_principles)
        self.metrics.unique_hleg_subtopics_addressed = len(hleg_subtopics)

        # Coverage percentages
        applicable = len(self.risk_classification.applicable_articles) if self.risk_classification else 0
        if applicable > 0:
            self.metrics.article_coverage_percentage = (
                len(articles) / applicable * 100
            )
        else:
            # No applicable articles means either MINIMAL risk or error
            # If we have citations to articles anyway, that's 100% of "applicable"
            self.metrics.article_coverage_percentage = 100.0 if articles else 0.0

        # HLEG coverage (always 7 principles)
        HLEG_PRINCIPLES_COUNT = 7
        self.metrics.hleg_coverage_percentage = (
            len(hleg_principles) / HLEG_PRINCIPLES_COUNT * 100
        )

        # Requirement counts
        self.metrics.total_requirements = len(self.requirements)
        self.metrics.critical_requirements = sum(
            1 for r in self.requirements if r.priority.value == "critical"
        )
        self.metrics.high_requirements = sum(
            1 for r in self.requirements if r.priority.value == "high"
        )

    def to_summary(self) -> str:
        """Generate a text summary of the report."""
        # Handle optional fields that may be None in error cases
        system_name = "Unknown"
        domain_value = "unknown"
        risk_level = "UNKNOWN"

        if self.system_description:
            system_name = self.system_description.name or "Unnamed"
            domain_value = self.system_description.domain.value if self.system_description.domain else "unknown"

        if self.risk_classification:
            risk_level = self.risk_classification.level.value.upper()

        lines = [
            f"TERE4AI Analysis Report",
            f"Generated: {self.generated_at.isoformat()}",
            f"",
            f"System: {system_name}",
            f"Domain: {domain_value}",
            f"",
            f"Risk Classification: {risk_level}",
        ]

        if self.is_prohibited and self.risk_classification:
            lines.extend([
                f"",
                f"[PROHIBITED] This system is PROHIBITED under the EU AI Act.",
                f"Violation: {self.risk_classification.prohibition_details or 'Article 5'}",
                f"",
                f"No requirements were generated.",
            ])
        elif self.processing_errors:
            lines.extend([
                f"",
                f"[ERROR] Pipeline encountered errors:",
                *[f"  - {err}" for err in self.processing_errors],
            ])
        else:
            lines.extend([
                f"",
                f"Requirements Generated: {len(self.requirements)}",
                f"- Critical: {self.metrics.critical_requirements}",
                f"- High: {self.metrics.high_requirements}",
                f"",
                f"Citations: {self.metrics.total_citations}",
                f"- EU AI Act: {self.metrics.eu_ai_act_citations}",
                f"- HLEG: {self.metrics.hleg_citations}",
                f"- Recitals: {self.metrics.recital_citations}",
                f"",
                f"Coverage:",
                f"- Articles: {self.metrics.article_coverage_percentage:.1f}%",
                f"- HLEG Principles: {self.metrics.hleg_coverage_percentage:.1f}%",
            ])

        return "\n".join(lines)

"""
Incident and Risk Assessment Models

This module defines Pydantic models for AI incidents and their risk assessments
under the EU AI Act. It supports the trustworthy project's goal of grounded,
conservative risk analysis.

Key components:
  - SourceInfo: External database references (e.g., AI Incident Database)
  - AIIncident: Structured incident with direct + derived fields
  - RiskAssessment: EU AI Act risk assessment grounded in specific provisions
  - RiskAssessmentJudgement: Judge's consistency validation

Trustworthiness principles:
  - Conservative: Derived fields are Optional; use None when uncertain
  - Grounded: All risk claims must reference specific EU AI Act provisions
  - Traceable: Source information preserved for all incidents
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, HttpUrl


# ============================================================================
# Source Information
# ============================================================================

class SourceInfo(BaseModel):
    """
    Reference to an external incident source (e.g., AI Incident Database).

    This enables traceability back to the original incident report.
    """
    source_db: str = Field(
        description="Name of the database, e.g. 'AI Incident Database'."
    )
    source_id: str = Field(
        description="ID in that database, e.g. '4' or 'AIID-2016-0004'."
    )
    source_url: Optional[HttpUrl] = Field(
        default=None,
        description="Direct URL to the incident entry, if available."
    )


# ============================================================================
# AI Incident Model
# ============================================================================

class AIIncident(BaseModel):
    """
    Structured incident from AI Incident Database (or similar).

    Some fields map directly to the table-style source; others are
    derived by the preprocessor agent.

    Trustworthiness: Derived fields (system_function, deployment_context, etc.)
    are optional. The agent leaves them as None when uncertain rather than guessing.
    """
    incident_id: str = Field(
        description="Internal ID in this project, e.g. 'incident_0004'."
    )
    source: SourceInfo = Field(
        description="External database reference."
    )

    # ========================================================================
    # Direct fields from AI Incident Database-style input
    # ========================================================================
    title: str = Field(
        description="Short title of the incident."
    )
    description: str = Field(
        description="Full incident description from the source."
    )
    date: Optional[str] = Field(
        default=None,
        description="Incident or report date in YYYY-MM-DD form if possible."
    )
    alleged_deployer: Optional[str] = Field(
        default=None,
        description="Alleged deployer of the AI system."
    )
    alleged_developer: Optional[str] = Field(
        default=None,
        description="Alleged developer of the AI system."
    )
    alleged_harmed_parties: Optional[str] = Field(
        default=None,
        description="Alleged harmed or nearly harmed parties."
    )
    implicated_systems: Optional[str] = Field(
        default=None,
        description="Names of implicated AI systems, if available."
    )

    # ========================================================================
    # Derived / normalized semantics (optional, filled by LLM)
    # ========================================================================
    system_function: Optional[str] = Field(
        default=None,
        description="What the AI system does (e.g. 'autonomous driving', 'content recommendation')."
    )
    deployment_context: Optional[str] = Field(
        default=None,
        description="Sector/use case (e.g. 'transport', 'healthcare', 'social media')."
    )
    affected_individuals: Optional[str] = Field(
        default=None,
        description="Who is affected (e.g. 'children', 'pedestrians', 'employees')."
    )
    harms_observed: Optional[str] = Field(
        default=None,
        description="Short summary of harms/risks (e.g. 'physical injury', 'discrimination')."
    )


# ============================================================================
# Risk Assessment Models
# ============================================================================

# Risk levels under the EU AI Act framework
RiskLevel = Literal["UNACCEPTABLE", "HIGH", "LIMITED", "MINIMAL", "UNCERTAIN"]


class ProvisionRef(BaseModel):
    """
    Reference to a specific EU AI Act provision.

    This enables grounded, traceable legal reasoning by requiring
    all claims to cite specific articles, paragraphs, and points.
    """
    article: int = Field(
        description="Article number, e.g. 5."
    )
    paragraph: Optional[int] = Field(
        default=None,
        description="Paragraph number, if applicable."
    )
    point: Optional[str] = Field(
        default=None,
        description="Lettered point marker, e.g. 'a', if applicable."
    )
    node_id: Optional[str] = Field(
        default=None,
        description="Optional Neo4j node id of the referenced provision."
    )


class PotentialViolation(BaseModel):
    """
    A potential violation of an EU AI Act provision.

    Trustworthiness: Must include explicit rationale grounded in the provision text.
    """
    provision: ProvisionRef
    rationale: str = Field(
        description="Explanation of how this incident may violate this provision."
    )


class RequiredObligation(BaseModel):
    """
    An obligation that should have been followed under the EU AI Act.

    Trustworthiness: Summarizes what compliance would require under this provision.
    """
    provision: ProvisionRef
    obligation_summary: str = Field(
        description="Summary of what the system should comply with under this provision."
    )


class RiskAssessment(BaseModel):
    """
    Legal risk assessment of one incident under the EU AI Act.

    All important claims should reference explicit provisions.

    Trustworthiness principles:
      - Grounded: All violations/obligations cite specific ProvisionRef
      - Conservative: Use UNCERTAIN risk level if provisions are insufficient
      - Traceable: Maintains source reference from original incident
    """
    incident_id: str = Field(
        description="ID of the AIIncident this assessment refers to."
    )
    source: SourceInfo = Field(
        description="Same source reference as the underlying incident."
    )
    assessed_text: str = Field(
        description=(
            "The exact text segment being assessed (usually the incident description)."
        )
    )
    risk_level: RiskLevel = Field(
        description="Overall risk level under the EU AI Act (or UNCERTAIN)."
    )
    potential_violations: List[PotentialViolation] = Field(
        default_factory=list,
        description="Provisions that may be violated, with rationales."
    )
    relevant_obligations: List[RequiredObligation] = Field(
        default_factory=list,
        description="Provisions describing obligations that should have been followed."
    )
    relevant_roles: List[str] = Field(
        default_factory=list,
        description="Likely roles involved (e.g. 'provider', 'deployer')."
    )
    overall_explanation: str = Field(
        description="Narrative explanation connecting assessed_text, risk_level, and provisions."
    )


class RiskAssessmentJudgement(BaseModel):
    """
    Judge agent's view on a RiskAssessment's consistency with the law text.

    This provides quality assurance by having a second agent validate
    that risk assessments are grounded in the actual EU AI Act text.

    Trustworthiness: Helps catch hallucinations, misquotes, or unsupported claims.
    """
    incident_id: str = Field(
        description="ID of the incident this judgement relates to."
    )
    is_consistent: bool = Field(
        description="Whether the assessment is consistent with the provided EU AI Act text."
    )
    score: float = Field(
        description="Confidence score between 0 and 1."
    )
    issues: List[str] = Field(
        default_factory=list,
        description="List of detected issues or inconsistencies."
    )
    corrected_assessment: Optional[RiskAssessment] = Field(
        default=None,
        description="Optional corrected assessment if the judge proposes changes."
    )

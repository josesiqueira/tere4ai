"""
Pydantic Models for AI System Description

This module defines the structured representation of a user's AI system
description, as extracted by the Elicitation Agent.

The Elicitation Agent takes free-text user input and extracts structured
characteristics relevant to EU AI Act risk classification.

EXTRACTION PRIORITIES:

  1. Domain identification (healthcare, finance, education, etc.)
  2. Purpose and intended use
  3. Users and affected persons
  4. Data types and decision types
  5. Risk-relevant flags (biometrics, safety-critical, etc.)

TRUSTWORTHINESS PRINCIPLES:

  - All extracted information traces back to user input
  - Ambiguities are flagged rather than assumed
  - The raw description is always preserved
  - Risk flags are conservative (flag if uncertain)
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SystemDomain(str, Enum):
    """
    Common domains for AI systems in the context of EU AI Act.

    These align with Annex III categories and help guide risk classification.
    """

    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    EMPLOYMENT = "employment"
    FINANCE = "finance"
    LAW_ENFORCEMENT = "law_enforcement"
    JUSTICE = "justice"
    MIGRATION = "migration"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    BIOMETRICS = "biometrics"
    SOCIAL_SERVICES = "social_services"
    TRANSPORT = "transport"
    ENERGY = "energy"
    CONSUMER = "consumer"
    ENTERTAINMENT = "entertainment"
    GENERAL = "general"
    OTHER = "other"


class AutonomyLevel(str, Enum):
    """
    Level of autonomy in AI system decision-making.

    Affects human oversight requirements and risk assessment.
    """

    FULL = "full"  # AI makes final decisions without human review
    PARTIAL = "partial"  # AI recommends, human can override
    ADVISORY = "advisory"  # AI provides information, human decides
    ASSISTIVE = "assistive"  # AI helps human with specific tasks


class DeploymentContext(str, Enum):
    """
    Context in which the AI system is deployed.

    Affects risk assessment and applicable requirements.
    """

    PUBLIC_SECTOR = "public_sector"
    PRIVATE_SECTOR = "private_sector"
    HEALTHCARE_FACILITY = "healthcare_facility"
    EDUCATIONAL_INSTITUTION = "educational_institution"
    WORKPLACE = "workplace"
    PUBLIC_SPACE = "public_space"
    ONLINE_PLATFORM = "online_platform"
    CRITICAL_INFRASTRUCTURE = "critical_infrastructure"
    LAW_ENFORCEMENT = "law_enforcement"
    BORDER_CONTROL = "border_control"
    CONSUMER_PRODUCT = "consumer_product"
    RESEARCH = "research"
    OTHER = "other"


class DataCategory(str, Enum):
    """
    Categories of data processed by the AI system.

    Special categories under GDPR/AI Act require additional protections.
    """

    BIOMETRIC = "biometric"
    HEALTH = "health"
    FINANCIAL = "financial"
    BEHAVIORAL = "behavioral"
    LOCATION = "location"
    COMMUNICATION = "communication"
    SOCIAL = "social"
    EMPLOYMENT = "employment"
    EDUCATIONAL = "educational"
    CRIMINAL = "criminal"
    GENETIC = "genetic"
    POLITICAL = "political"
    RELIGIOUS = "religious"
    SEXUAL_ORIENTATION = "sexual_orientation"
    PERSONAL_IDENTIFIABLE = "personal_identifiable"
    ANONYMIZED = "anonymized"
    SYNTHETIC = "synthetic"
    PUBLIC = "public"
    OTHER = "other"


class DecisionType(str, Enum):
    """
    Types of decisions the AI system makes or influences.

    Affects risk classification and required safeguards.
    """

    ACCESS_DENIAL = "access_denial"  # Denying access to services/opportunities
    RESOURCE_ALLOCATION = "resource_allocation"  # Allocating limited resources
    RANKING = "ranking"  # Ranking or prioritizing individuals
    ASSESSMENT = "assessment"  # Evaluating individuals
    PREDICTION = "prediction"  # Predicting future behavior/outcomes
    RECOMMENDATION = "recommendation"  # Suggesting actions
    CLASSIFICATION = "classification"  # Categorizing individuals
    IDENTIFICATION = "identification"  # Identifying individuals
    CONTENT_GENERATION = "content_generation"  # Generating content
    CONTENT_MODERATION = "content_moderation"  # Moderating content
    AUTOMATION = "automation"  # Automating tasks
    MONITORING = "monitoring"  # Monitoring individuals
    OTHER = "other"


class SystemDescription(BaseModel):
    """
    Structured representation of a user's AI system.

    This is the OUTPUT of the Elicitation Agent, created by extracting
    structured information from the user's free-text description.

    It contains all the characteristics needed for:
      - Risk classification (Analysis Agent)
      - Requirement generation (Specification Agent)
      - Validation (Validation Agent)
    """

    # Original input (always preserved)
    raw_description: str = Field(
        description="The original free-text description provided by the user."
    )

    # Basic identification
    name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the AI system if mentioned, e.g. 'TrustTriage'. "
            "May be None if not specified."
        )
    )
    domain: SystemDomain = Field(
        default=SystemDomain.GENERAL,
        description="Primary domain of the AI system."
    )
    secondary_domains: List[SystemDomain] = Field(
        default_factory=list,
        description="Additional domains if system spans multiple areas."
    )
    purpose: Optional[str] = Field(
        default=None,
        description=(
            "Clear statement of what the system does and why. "
            "Extracted from user description. May be None if not clearly stated."
        )
    )

    # Stakeholders
    intended_users: List[str] = Field(
        default_factory=list,
        description=(
            "Who uses the system (operators/deployers), e.g. "
            "['hospital staff', 'HR managers', 'teachers']."
        )
    )
    affected_persons: List[str] = Field(
        default_factory=list,
        description=(
            "Who is affected by the system's decisions, e.g. "
            "['patients', 'job applicants', 'students']."
        )
    )

    # Technical characteristics
    data_types: List[DataCategory] = Field(
        default_factory=list,
        description="Categories of data the system processes."
    )
    data_types_detail: List[str] = Field(
        default_factory=list,
        description=(
            "Specific data types mentioned, e.g. "
            "['patient vital signs', 'medical history', 'symptoms']."
        )
    )
    decision_types: List[DecisionType] = Field(
        default_factory=list,
        description="Types of decisions the system makes or influences."
    )
    decision_types_detail: List[str] = Field(
        default_factory=list,
        description=(
            "Specific decisions mentioned, e.g. "
            "['triage priority', 'treatment recommendation']."
        )
    )

    # Operational characteristics
    autonomy_level: AutonomyLevel = Field(
        default=AutonomyLevel.ADVISORY,
        description="Level of autonomy in decision-making."
    )
    deployment_context: DeploymentContext = Field(
        default=DeploymentContext.OTHER,
        description="Context in which the system is deployed."
    )
    deployment_scale: Optional[str] = Field(
        default=None,
        description=(
            "Scale of deployment if mentioned, e.g. "
            "'single hospital', 'nationwide', 'global platform'."
        )
    )

    # Risk-relevant flags (conservative - flag if uncertain)
    affects_fundamental_rights: bool = Field(
        default=False,
        description=(
            "Whether the system's decisions affect fundamental rights "
            "(dignity, liberty, equality, privacy, etc.)."
        )
    )
    safety_critical: bool = Field(
        default=False,
        description=(
            "Whether the system operates in a safety-critical context "
            "(healthcare, transport, critical infrastructure)."
        )
    )
    biometric_processing: bool = Field(
        default=False,
        description="Whether the system processes biometric data."
    )
    real_time_biometric: bool = Field(
        default=False,
        description=(
            "Whether the system performs real-time biometric identification "
            "in publicly accessible spaces."
        )
    )
    law_enforcement_use: bool = Field(
        default=False,
        description="Whether the system is intended for law enforcement use."
    )
    critical_infrastructure: bool = Field(
        default=False,
        description=(
            "Whether the system is used in critical infrastructure "
            "(energy, transport, water, digital infrastructure)."
        )
    )
    vulnerable_groups: bool = Field(
        default=False,
        description=(
            "Whether the system affects vulnerable groups "
            "(children, elderly, disabled, economically disadvantaged)."
        )
    )
    emotion_recognition: bool = Field(
        default=False,
        description="Whether the system performs emotion recognition."
    )
    social_scoring: bool = Field(
        default=False,
        description=(
            "Whether the system evaluates or classifies persons based on "
            "social behavior or personality characteristics."
        )
    )
    subliminal_techniques: bool = Field(
        default=False,
        description=(
            "Whether the system uses subliminal techniques to manipulate "
            "behavior in ways the person cannot perceive."
        )
    )

    # Extraction metadata
    extraction_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the accuracy of extraction (0.0-1.0)."
    )
    ambiguities: List[str] = Field(
        default_factory=list,
        description=(
            "List of ambiguities in the description that may need "
            "clarification, e.g. ['unclear if real-time processing']."
        )
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description=(
            "Assumptions made during extraction, e.g. "
            "['assumed EU deployment based on context']."
        )
    )

    def has_prohibited_indicators(self) -> bool:
        """Check if system has indicators of prohibited practices."""
        return any([
            self.social_scoring,
            self.subliminal_techniques,
            self.real_time_biometric and self.law_enforcement_use,
        ])

    def has_high_risk_indicators(self) -> bool:
        """Check if system has indicators of high-risk classification."""
        return any([
            self.safety_critical,
            self.biometric_processing,
            self.law_enforcement_use,
            self.critical_infrastructure,
            self.affects_fundamental_rights,
            self.domain in [
                SystemDomain.HEALTHCARE,
                SystemDomain.EDUCATION,
                SystemDomain.EMPLOYMENT,
                SystemDomain.LAW_ENFORCEMENT,
                SystemDomain.JUSTICE,
                SystemDomain.MIGRATION,
                SystemDomain.CRITICAL_INFRASTRUCTURE,
                SystemDomain.BIOMETRICS,
            ],
        ])

    def to_features_dict(self) -> dict:
        """
        Convert to a dictionary of features for risk classification.

        This is the format expected by the classify_risk_level MCP tool.
        """
        return {
            "domain": self.domain.value,
            "secondary_domains": [d.value for d in self.secondary_domains],
            "purpose": self.purpose or "Not specified",
            "raw_description": self.raw_description,  # For keyword detection
            "intended_users": self.intended_users,
            "affected_persons": self.affected_persons,
            "data_types": [d.value for d in self.data_types],
            "decision_types": [d.value for d in self.decision_types],
            "autonomy_level": self.autonomy_level.value,
            "deployment_context": self.deployment_context.value,
            "affects_fundamental_rights": self.affects_fundamental_rights,
            "safety_critical": self.safety_critical,
            "biometric_processing": self.biometric_processing,
            "real_time_biometric": self.real_time_biometric,
            "law_enforcement_use": self.law_enforcement_use,
            "critical_infrastructure": self.critical_infrastructure,
            "vulnerable_groups": self.vulnerable_groups,
            "emotion_recognition": self.emotion_recognition,
            "social_scoring": self.social_scoring,
            "subliminal_techniques": self.subliminal_techniques,
        }

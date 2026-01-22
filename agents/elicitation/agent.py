"""
TERE4AI Elicitation Agent

This agent extracts structured system descriptions from natural language
user input. It identifies risk-relevant features that will be used by
the Analysis Agent for risk classification.

EXTRACTION STRATEGY:
  - Conservative: Flag risk indicators if uncertain (false positive > false negative)
  - Grounded: Only extract what is stated or clearly implied
  - Complete: Capture all risk-relevant characteristics
  - Traceable: Document ambiguities and assumptions

OUTPUT:
  - SystemDescription Pydantic model with all fields populated
  - Confidence scores and extraction notes
"""

from __future__ import annotations

import json
import os
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from agents.base import AgentConfig, BaseAgent, MCPToolClient
from shared.models import (
    AutonomyLevel,
    DataCategory,
    DecisionType,
    DeploymentContext,
    SystemDescription,
    SystemDomain,
)


class ElicitationInput(BaseModel):
    """Input to the Elicitation Agent."""

    raw_description: str = Field(
        description="Natural language description of the AI system from the user."
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Optional additional context or clarifications."
    )


class ElicitationAgent(BaseAgent[ElicitationInput, SystemDescription]):
    """
    Elicitation Agent - Phase 1 of the RE Pipeline.

    Extracts structured system description from user's natural language input.
    Uses LLM to identify:
      - Domain and purpose
      - Data types processed
      - Decision types made
      - Deployment context
      - Risk-relevant flags (biometric, law enforcement, etc.)
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        mcp_client: Optional[MCPToolClient] = None,
    ):
        super().__init__(config, mcp_client)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Please set it before initializing the ElicitationAgent."
            )
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "elicitation"

    @property
    def phase(self) -> str:
        return "elicitation"

    def _get_system_prompt(self) -> str:
        return """You are the Elicitation Agent for TERE4AI, a Requirements Engineering system for AI Act compliance.

Your task is to extract a structured system description from the user's natural language input.
You must identify all risk-relevant characteristics for EU AI Act classification.

EXTRACTION PRINCIPLES:

1. CONSERVATIVE FLAGGING
   - If you're uncertain whether a risk flag applies, FLAG IT as true
   - False positives are acceptable; false negatives are not
   - The Analysis Agent will make the final determination

2. GROUNDED EXTRACTION
   - Only extract what is stated or clearly implied
   - Do not invent features not mentioned
   - Document assumptions in the 'assumptions' field

3. COMPLETENESS
   - Extract ALL risk-relevant characteristics
   - Consider both explicit statements and implications
   - Think about who uses the system and who is affected

4. AMBIGUITY HANDLING
   - Document any ambiguities in the 'ambiguities' field
   - Make reasonable assumptions and document them
   - Assign appropriate confidence scores

DOMAIN CLASSIFICATION:
Use these domains: healthcare, education, employment, finance, law_enforcement, justice,
migration, critical_infrastructure, biometrics, transportation, social_media,
content_generation, consumer_products, scientific_research, military_defense, general

DATA CATEGORIES (select all that apply):
biometric, health, financial, behavioral, location, communication, criminal, genetic,
political, religious, sexual_orientation, trade_union, social_media, professional,
educational, consumer, technical, public_records, anonymized

DECISION TYPES (select all that apply):
access_denial, resource_allocation, ranking, assessment, prediction, recommendation,
classification, identification, content_generation, automation, monitoring, filtering

DEPLOYMENT CONTEXTS:
public_sector, private_sector, healthcare_facility, educational_institution, workplace,
public_space, online_platform, home, transportation, financial_institution,
law_enforcement_context, border_control

AUTONOMY LEVELS:
- full: System makes decisions without human intervention
- partial: System makes recommendations that humans typically follow
- advisory: System provides advice that humans independently evaluate
- assistive: System supports human decision-making with information

RISK FLAGS (set true if indicated or uncertain):
- affects_fundamental_rights: Impacts rights like privacy, non-discrimination, dignity
- safety_critical: Could cause physical harm or safety risks
- biometric_processing: Processes biometric data (face, fingerprint, voice, etc.)
- real_time_biometric: Real-time biometric identification (not verification)
- law_enforcement_use: Used by or for law enforcement purposes
- critical_infrastructure: Part of critical infrastructure (energy, water, transport)
- vulnerable_groups: Affects children, disabled, elderly, or other vulnerable groups
- emotion_recognition: Infers emotional states from behavior/physiological signals
- social_scoring: Evaluates/classifies people based on social behavior
- subliminal_techniques: Uses techniques below conscious awareness

OUTPUT FORMAT:
Return a JSON object matching the SystemDescription schema exactly.
Include confidence score (0.0-1.0) reflecting extraction certainty.
List any ambiguities and assumptions made."""

    async def run(self, input_data: ElicitationInput) -> SystemDescription:
        """
        Extract SystemDescription from user input.

        Args:
            input_data: Natural language system description

        Returns:
            Structured SystemDescription model
        """
        self._start_trace(
            input_summary=f"Description length: {len(input_data.raw_description)} chars"
        )

        try:
            # Build the user message
            user_message = f"""Extract a structured system description from the following:

SYSTEM DESCRIPTION:
{input_data.raw_description}"""

            if input_data.additional_context:
                user_message += f"""

ADDITIONAL CONTEXT:
{input_data.additional_context}"""

            # Call the LLM
            response = await self._client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
            )

            # Parse the response with null checks
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("LLM returned empty or invalid response")
            content = response.choices[0].message.content
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"LLM returned invalid JSON: {e}") from e

            # Ensure raw_description is preserved
            data["raw_description"] = input_data.raw_description

            # Ensure purpose is provided (fallback to truncated raw description)
            if not data.get("purpose"):
                truncated = input_data.raw_description[:200]
                if len(input_data.raw_description) > 200:
                    truncated += "..."
                data["purpose"] = truncated

            # Convert string enums to enum values
            data = self._convert_enums(data)

            # Create the SystemDescription
            result = SystemDescription(**data)

            self._complete_trace(
                output_summary=f"Domain: {result.domain}, Confidence: {result.extraction_confidence}"
            )

            return result

        except Exception as e:
            self._complete_trace(error=str(e))
            raise

    def _convert_enums(self, data: dict) -> dict:
        """Convert string values to enum values where needed."""
        # Domain
        if "domain" in data and isinstance(data["domain"], str):
            try:
                data["domain"] = SystemDomain(data["domain"])
            except ValueError:
                data["domain"] = SystemDomain.GENERAL

        # Secondary domains
        if "secondary_domains" in data:
            data["secondary_domains"] = [
                SystemDomain(d) if isinstance(d, str) else d
                for d in data.get("secondary_domains", [])
                if d in [e.value for e in SystemDomain]
            ]

        # Data types
        if "data_types" in data:
            data["data_types"] = [
                DataCategory(d) if isinstance(d, str) else d
                for d in data.get("data_types", [])
                if d in [e.value for e in DataCategory]
            ]

        # Decision types
        if "decision_types" in data:
            data["decision_types"] = [
                DecisionType(d) if isinstance(d, str) else d
                for d in data.get("decision_types", [])
                if d in [e.value for e in DecisionType]
            ]

        # Autonomy level
        if "autonomy_level" in data and isinstance(data["autonomy_level"], str):
            try:
                data["autonomy_level"] = AutonomyLevel(data["autonomy_level"])
            except ValueError:
                data["autonomy_level"] = AutonomyLevel.PARTIAL

        # Deployment context
        if "deployment_context" in data and isinstance(data["deployment_context"], str):
            try:
                data["deployment_context"] = DeploymentContext(data["deployment_context"])
            except ValueError:
                data["deployment_context"] = DeploymentContext.PRIVATE_SECTOR

        return data

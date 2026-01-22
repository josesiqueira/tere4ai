"""
Dependency Model for Legal Document Preprocessing

This module defines the input dependencies for the legal preprocessing agent.

Key principle: ALL metadata is deterministic and provided by the caller.
The LLM agent MUST NOT infer or change these values - they are echoed back exactly.

This ensures:
  - No hallucinated document IDs or jurisdictions
  - Reproducible preprocessing given the same inputs
  - Clear separation between deterministic metadata and LLM-extracted structure
"""

from pydantic import BaseModel, Field


class LegalPreprocessDeps(BaseModel):
    """
    Deterministic metadata for legal document preprocessing.

    All of these values are provided by the caller and must be echoed
    back by the agent. The agent MUST NOT infer or change them.
    """
    document_id: str = Field(
        description="Stable identifier for this legal document, e.g. 'eu_ai_act_2024'."
    )
    source_file: str = Field(
        description="Path to the source text file, e.g. 'eu_ai_act.txt'."
    )
    jurisdiction: str = Field(
        default="EU",
        description="Jurisdiction of the legal instrument, default 'EU'."
    )
    instrument_type: str = Field(
        default="Regulation",
        description="Type of legal instrument, e.g. 'Regulation', 'Directive'."
    )

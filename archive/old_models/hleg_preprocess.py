"""
Dependency Model for AI HLEG Preprocessing

This module defines the input dependency model used by the AI HLEG
preprocessing agent.

Key principle: ALL metadata is deterministic and provided by the caller.
The LLM agent MUST NOT infer or change these values.

This mirrors the approach used for the EU AI Act preprocessing.
"""

from pydantic import BaseModel, Field


class HlegPreprocessDeps(BaseModel):
    """
    Deterministic metadata for AI HLEG document preprocessing.

    All of these values are provided by the caller and must be echoed
    back by the agent. The agent MUST NOT infer or change them.
    """
    document_id: str = Field(
        description="Stable identifier for this HLEG document, e.g. 'ai_hleg_2019'."
    )
    source_file: str = Field(
        description="Path to the source text file, e.g. 'data/ai_hleg.txt'."
    )
    jurisdiction: str = Field(
        default="EU",
        description="Jurisdiction of the guidelines, default 'EU'."
    )
    instrument_type: str = Field(
        default="Guidelines",
        description="Type of instrument, e.g. 'Guidelines'."
    )
    year: int = Field(
        default=2019,
        description="Year of publication of the guidelines."
    )

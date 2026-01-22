"""
Dependency model for EU→HLEG mapping agent.

All of these values are deterministic metadata provided by the caller.
The LLM MUST NOT change them. They are echoed into the output
EuRequirementLocation.
"""

from pydantic import BaseModel, Field


class EuHlegMappingDeps(BaseModel):
    """
    Deterministic metadata for a single EU requirement paragraph
    being mapped to HLEG requirements.
    """
    document_id: str = Field(
        description="EU AI Act document id, e.g. 'eu_ai_act_2024'."
    )
    chapter_number: str = Field(
        description="Chapter number as string, e.g. 'III'."
    )
    article_number: str = Field(
        description="Article number as string, e.g. '9'."
    )
    paragraph_index: int = Field(
        description=(
            "Paragraph index inside the article (consistent with structural "
            "preprocessing)."
        )
    )

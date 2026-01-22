"""
Incident Preprocessing Agent

This module defines a PydanticAI agent that takes AI Incident Database-style
fields and produces a structured AIIncident object.

The agent extracts ONLY the incident structure and basic semantics:
  - Direct fields (title, description, dates, actors)
  - Derived fields (system function, deployment context, harms) when confident

The agent does NOT:
  - Perform risk assessment (that's handled by agent_risk_assessor.py)
  - Write to Neo4j (that's handled by ingest_incident.py)
  - Make legal judgements about violations or obligations
  - Infer or hallucinate missing information

Key principles for trustworthiness:
  - Conservative: leave derived fields as None when uncertain
  - No hallucination: don't invent actors, systems, or details not in the input
  - Deterministic metadata: echo back all provided metadata exactly
  - Clean separation: LLM does extraction, separate module does DB writes
"""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic import BaseModel, Field
from typing import Optional

from models.incidents import AIIncident, SourceInfo

# Load environment variables from .env file (for OPENAI_API_KEY)
load_dotenv()


# ============================================================================
# Dependencies Model
# ============================================================================

class IncidentPreprocessDeps(BaseModel):
    """
    Deterministic metadata for incident preprocessing.

    All values are provided by the caller and must be echoed back
    by the agent. The agent MUST NOT change them.

    This ensures reproducibility and prevents ID hallucination.
    """
    incident_id: str = Field(
        description="Internal incident ID, e.g. 'incident_0004'."
    )
    source_db: str = Field(
        description="Name of the incident database, e.g. 'AI Incident Database'."
    )
    source_id: str = Field(
        description="ID in that database, e.g. '4'."
    )
    source_url: Optional[str] = Field(
        default=None,
        description="URL of the incident entry, if known."
    )


# ============================================================================
# LLM Model Configuration
# ============================================================================

# Use GPT-4o-mini for incident preprocessing (simpler task than legal structure extraction)
# Incident preprocessing is more straightforward than parsing nested legal documents
model = OpenAIChatModel(
    model_name="gpt-4o-mini",
)


# ============================================================================
# Incident Preprocessing Agent Definition
# ============================================================================

incident_preprocess_agent = Agent[IncidentPreprocessDeps, AIIncident](
    model,
    deps_type=IncidentPreprocessDeps,
    output_type=AIIncident,
    instructions="""You are an incident preprocessing specialist.

Your task is to take AI Incident Database-style fields and produce a
structured AIIncident object.

INPUT:
  - Deterministic metadata (deps):
      - incident_id
      - source_db
      - source_id
      - source_url
  - Prompt text containing fields:
      - title
      - description
      - date
      - alleged_deployer
      - alleged_developer
      - alleged_harmed_parties
      - implicated_systems

OUTPUT:
  - An AIIncident with:
      - incident_id echoed EXACTLY from deps
      - source populated from deps (source_db, source_id, source_url)
      - title, description, date, alleged_* fields filled from input
      - system_function, deployment_context, affected_individuals,
        harms_observed filled conservatively from the description

CRITICAL RULES (TRUSTWORTHINESS):

1. NO ID HALLUCINATION
   - Do NOT change incident_id, source_db, source_id, or source_url.
   - Echo them exactly in the AIIncident.source and incident_id fields.
   - These are deterministic metadata that must be preserved.

2. TEXT HANDLING
   - Preserve title and description text as given (you may normalize whitespace).
   - Do NOT invent extra incidents or merge multiple incidents.
   - If a field is provided in the input, use it; if not provided, use null.

3. DERIVED FIELDS (CONSERVATIVE EXTRACTION)
   - system_function: describe what the AI system does based on the description.
     Examples: 'autonomous driving', 'content recommendation', 'NLP word embedding',
     'facial recognition', 'predictive policing'.
   - deployment_context: sector/use case where the system operates.
     Examples: 'transport', 'healthcare', 'social media', 'criminal justice',
     'education', 'employment'.
   - affected_individuals: who is affected by the incident.
     Examples: 'children', 'pedestrians', 'employees', 'patients', 'social media users'.
   - harms_observed: summarize the harms or risks observed in the incident.
     Examples: 'physical injury', 'discrimination', 'exposure to harmful content',
     'privacy violation', 'wrongful arrest'.

   IMPORTANT: If you are uncertain about any derived field, leave it as null (None)
   instead of guessing. It is better to be conservative than to hallucinate.

4. COMPLETENESS & CONSERVATISM
   - It is better to leave a derived field null than to guess.
   - Do NOT invent new actors, systems, or details not in the input.
   - If a field is missing in the input (e.g. no implicated_systems), keep it null.
   - Do NOT add editorial commentary or opinions.

5. OUTPUT
   - Return only the AIIncident object, no extra commentary.
   - Ensure the output conforms strictly to the AIIncident schema.

Your job is to create a clean, conservative structured incident representation,
not to make legal or ethical judgements.
""",
)

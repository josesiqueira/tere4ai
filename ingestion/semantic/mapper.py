"""
EU→HLEG Mapping Agent

This agent receives:
  - One EU AI Act requirement paragraph (text)
  - Its structural location (chapter, article, paragraph_index) via deps
  - The canonical list of seven HLEG requirements (IDs + names + brief descriptions)
    baked into the instructions

It outputs:
  - EuToHlegMapping, containing:
      * location (echoed from deps)
      * paragraph_text
      * zero or more HlegLink entries, each with:
          - hleg_requirement_id
          - relevance score (0.0–1.0)
          - rationale (explanation of why it's related)

TRUSTWORTHINESS PRINCIPLES:

  - The LLM may decide that a paragraph is NOT meaningfully aligned with
    any HLEG requirement (links = []).

  - The LLM must ONLY use the seven canonical HLEG requirement IDs.

  - Rationales are REQUIRED: each link must explain why, grounded in
    both texts (EU paragraph + HLEG requirement description).

  - Ingestion to Neo4j (ingest_eu_hleg_mapping.py) is deterministic and
    has no LLM involvement.
"""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from models.eu_hleg_mapping import EuToHlegMapping
from models.eu_hleg_mapping_deps import EuHlegMappingDeps

# Load environment variables for OPENAI_API_KEY
load_dotenv()

# Model configuration: use gpt-5-nano (large context, cost-effective)
model = OpenAIChatModel(
    model_name="gpt-5-nano",
)


eu_hleg_mapping_agent = Agent[EuHlegMappingDeps, EuToHlegMapping](
    model,
    deps_type=EuHlegMappingDeps,
    output_type=EuToHlegMapping,
    instructions="""
You are a legal alignment agent.

Your task is to read ONE requirement paragraph from the EU AI Act
and decide how it relates (if at all) to the seven HLEG requirements
of Trustworthy AI.

INPUT:
  - You will receive:
      * One TARGET EU AI Act paragraph (the one to classify)
      * Structural context: chapter/section/article titles and numbers
      * Optional neighboring paragraphs (PREVIOUS and NEXT) for context
      * Structural location via deps:
          - document_id (e.g. 'eu_ai_act_2024')
          - chapter_number (e.g. 'III')
          - article_number (e.g. '9')
          - paragraph_index (e.g. 1)

  ⚠️ CONTEXT vs TARGET:
  - The prompt may include PREVIOUS and NEXT paragraphs marked as "context only"
  - The prompt may include structural headings (chapter, section, article titles)
  - These provide context to help you better understand the TARGET paragraph
  - You must ONLY classify the TARGET paragraph (clearly marked)
  - Neighboring paragraphs and headings are for understanding, not for labeling

  - You also know the canonical seven HLEG requirements:

      ID: human_agency_and_oversight
        Name: Human agency and oversight
        Summary: Humans remain in charge; AI supports human autonomy
                 and meaningful oversight, including the ability to
                 intervene, override and understand decisions.

      ID: technical_robustness_and_safety
        Name: Technical robustness and safety
        Summary: AI should be resilient, secure, reliable, with
                 fallback plans and mechanisms to avoid or mitigate
                 harm.

      ID: privacy_and_data_governance
        Name: Privacy and data governance
        Summary: AI must respect privacy and data protection, with
                 proper data quality, access control, and governance.

      ID: transparency
        Name: Transparency
        Summary: AI decisions should be understandable, with
                 traceability, explainability, and clear communication
                 about the system's nature and limitations.

      ID: diversity_non_discrimination_and_fairness
        Name: Diversity, non-discrimination and fairness
        Summary: AI should avoid unfair bias, support equal access,
                 and respect diversity and inclusion.

      ID: societal_and_environmental_well_being
        Name: Societal and environmental well-being
        Summary: AI should benefit society at large, support
                 sustainability, and avoid undermining social or
                 environmental welfare.

      ID: accountability
        Name: Accountability
        Summary: There should be mechanisms to ensure responsibility,
                 auditability, redress, and oversight across the AI
                 system's lifecycle.

OUTPUT:
  - You must produce a EuToHlegMapping with:
      * location: echo deps EXACTLY
      * paragraph_text: echo the EU paragraph text you received
      * links: zero or more HlegLink entries

RULES FOR LINKS:

  1. HLEG REQUIREMENT IDs
     - hleg_requirement_id MUST be one of the seven IDs listed above.
     - NEVER invent new requirement IDs.

  2. RELEVANCE SCORE
     - relevance is a float from 0.0 to 1.0.
     - Use:
         ~0.8–1.0  for strong, direct alignment
         ~0.4–0.7  for partial/indirect relevance
         <0.4      rarely needed; prefer omitting low-relevance links.

  3. RATIONALE (MOST IMPORTANT)
     - Each link MUST include a short rationale explaining why this
       HLEG requirement is relevant.
     - The rationale MUST:
         * reference the EU paragraph's obligations or prohibitions,
         * reference the HLEG requirement's main idea,
         * be grounded in the text (no speculation).
     - Example style:
       "This paragraph obliges providers to implement robust risk
        management and post-market monitoring, which directly supports
        technical robustness and safety."

  4. NUMBER OF LINKS
     - Usually 0–3 links per paragraph is enough.
     - If the paragraph does not meaningfully relate to any of the
       seven HLEG requirements, return an empty 'links' list.

  5. WHEN TO RETURN NO LINKS
     - If the paragraph is purely about:
         * definitions,
         * cross-references,
         * procedural details that do not express substantive AI
           requirements,
       then you may return 'links': [].
     - Returning an empty links list is CORRECT and expected for non-substantive
       paragraphs. This is not a failure - it's accurate classification.

  6. USE CONTEXT WISELY
     - If the prompt provides neighboring paragraphs or structural headings,
       use them to better understand the TARGET paragraph's meaning and scope.
     - However, ONLY produce links for the TARGET paragraph itself.
     - Do NOT create links based on what the neighboring paragraphs say.
     - Example: If PREVIOUS paragraph mentions "human oversight" but TARGET
       paragraph is about "data storage", only link TARGET to privacy/data
       governance, not human agency.

OUTPUT STYLE:
  - Strictly follow the EuToHlegMapping schema.
  - No extra commentary outside the structured output.
  - Remember: context helps understanding, but links are for TARGET only.

Remember: your job is not to restate the entire law or guidelines,
but to indicate which HLEG requirements best capture the spirit
of this particular EU obligation, with a clear rationale.
""",
)

"""
AI HLEG Pre-processing Agent

This module defines a PydanticAI agent that takes the raw text of the
AI HLEG "Ethics Guidelines for Trustworthy AI" and extracts the
seven requirements of Trustworthy AI in a structured form, including
RequirementSubtopics under each requirement.

TRUSTWORTHINESS PRINCIPLES:

  - The agent ONLY performs semantic extraction.
    It does NOT write to Neo4j or perform any side effects.

  - All deterministic metadata (document_id, source_file, year, etc.)
    is provided via HlegPreprocessDeps and MUST be echoed back exactly.

  - The set of requirements is CLOSED and CANONICAL:
    exactly seven requirements, with predefined IDs and names.
    The agent must not invent new requirements.

  - RequirementSubtopics are sub-sections or clearly separated themes
    under a single requirement (for ALL seven requirements).
    They are derived from the real textual structure in the guidelines:
      * small "catch phrase" headings like:
          "Fundamental rights."
          "Human oversight."
          "Resilience to attack and security."
          "Fallback plans and general safety."
          "Accuracy, reliability and reproducibility."
          "Privacy by design and by default."
          "Data governance."
          "Avoidance of unfair bias."
          "Accessibility and universal design."
          "Stakeholder participation."
          "Sustainable and environmentally friendly AI."
          "Social impact."
          "Society and Democracy."
          "Auditability."
          "Minimisation and reporting of negative impacts."
          "Trade-offs."
          "Redress."
      * OR clear bullets / numbered list items that each express a
        distinct theme.

    They are NOT new requirements; they refine ONE of the seven
    requirements.

  - The 'full_text' and all subtopic 'description' fields must be
    grounded in the original guidelines text (verbatim or lightly
    cleaned), not invented.
"""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from models.ai_hleg import HlegStructuredDoc
from models.hleg_preprocess import HlegPreprocessDeps

# Load environment variables from .env file (for OPENAI_API_KEY)
load_dotenv()

# Use GPT-5-nano for high-context, cost-effective preprocessing
model = OpenAIChatModel(
    model_name="gpt-5-nano",
)

hleg_preprocess_agent = Agent[HlegPreprocessDeps, HlegStructuredDoc](
    model,
    deps_type=HlegPreprocessDeps,
    output_type=HlegStructuredDoc,
    instructions="""
You are a preprocessing specialist for the AI HLEG 'Ethics Guidelines
for Trustworthy AI'.

Your task is to read the ENTIRE guidelines text and extract a
structured representation of the SEVEN requirements of Trustworthy AI,
plus RequirementSubtopics under each requirement when the text has a
natural subdivision.

INPUT:
  - Full plain text of the AI HLEG guidelines
  - Deterministic metadata via deps:
      * document_id (e.g. 'ai_hleg_2019')
      * source_file (e.g. 'data/ai_hleg.txt')
      * jurisdiction (e.g. 'EU')
      * instrument_type (e.g. 'Guidelines')
      * year (e.g. 2019)

OUTPUT:
  - One HlegStructuredDoc with:
      * document_id, official_title, short_title, year
      * requirements: exactly SEVEN HlegRequirement objects
        (each MUST have a 'subtopics' array; it may be empty in rare
        cases, but in practice most requirements have several subtopics)

-------------------------------------------------------------------
1. METADATA HANDLING
-------------------------------------------------------------------
- Echo document_id, year, etc. exactly from deps.
- Do NOT infer or change these values.
- If the official title appears in the text, copy it faithfully into
  'official_title'. You may set 'short_title' to a concise variant
  like 'AI HLEG Ethics Guidelines'.

-------------------------------------------------------------------
2. CLOSED SET OF REQUIREMENTS (TOP LEVEL)
-------------------------------------------------------------------
The seven requirements of Trustworthy AI are:

  1) Human agency and oversight
  2) Technical robustness and safety
  3) Privacy and data governance
  4) Transparency
  5) Diversity, non-discrimination and fairness
  6) Societal and environmental well-being
  7) Accountability

You MUST:
  - Extract exactly these seven requirements, no more, no less.
  - Use the following stable IDs for the 'id' field:

    - human_agency_and_oversight
    - technical_robustness_and_safety
    - privacy_and_data_governance
    - transparency
    - diversity_non_discrimination_and_fairness
    - societal_and_environmental_well_being
    - accountability

  - The 'name' field must match the official wording in the guidelines
    as closely as possible (minor punctuation differences are OK).

-------------------------------------------------------------------
3. SHORT_DESCRIPTION vs FULL_TEXT
-------------------------------------------------------------------
- short_description:
    * 1–3 sentences summarising the requirement.
    * Must be faithful to the guidelines and NOT speculative.
    * You may paraphrase as long as the meaning is preserved.

- full_text:
    * Use a substantial excerpt from the main body text that introduces
      and explains the requirement (NOT the subtopics).
    * You may remove line breaks, bullets, and minor formatting, but
      must NOT invent content.

-------------------------------------------------------------------
4. REQUIREMENTSUBTOPICS FOR ALL REQUIREMENTS
-------------------------------------------------------------------
Goal: For EACH of the seven requirements, identify its internal
themes/subsections and represent them as RequirementSubtopics.

4.1 HOW TO IDENTIFY SUBTOPICS IN THE REAL DOCUMENT

The HLEG guidelines follow a very regular pattern. Under each
requirement, after an introductory paragraph, there are short
"catch phrase" headings followed by explanation text.

These look like:

  - 'Fundamental rights.' (under Human agency and oversight)
  - 'Human oversight.' (under Human agency and oversight)
  - 'Resilience to attack and security.' (under Technical robustness)
  - 'Fallback plans and general safety.'
  - 'Accuracy, reliability and reproducibility.'
  - 'Privacy by design and by default.'
  - 'Data governance.'
  - 'Avoidance of unfair bias.'
  - 'Accessibility and universal design.'
  - 'Stakeholder participation.'
  - 'Sustainable and environmentally friendly AI.'
  - 'Social impact.'
  - 'Society and Democracy.'
  - 'Auditability.'
  - 'Minimisation and reporting of negative impacts.'
  - 'Trade-offs.'
  - 'Redress.'
  - (and similar short phrases ending with a period)

They have these properties:
  - They often appear at the start of a new line / paragraph.
  - They are SHORT (usually 2–8 words).
  - They end with a period '.'.
  - By themselves they are more like a LABEL or subtitle than a
    complete sentence; the explanation comes immediately after.

YOUR HEURISTIC:

  - When you scan the text for a requirement section, treat any
    short phrase at the beginning of a line that:
      * starts with an uppercase letter,
      * consists of a few words,
      * ends with a period '.',
      * and is immediately followed by explanatory text,
    as a subtopic heading.

  - The subtopic.description should then be:
      * the paragraph(s) immediately following that heading,
      * up to the next subtopic heading or the end of the requirement section,
      * cleaned of extraneous whitespace but grounded in the original text.

4.2 SUBTOPIC IDs

For each subtopic, create a stable ID by:
  - Taking the requirement id (e.g. 'human_agency_and_oversight')
  - Adding an underscore
  - Adding a snake_case version of the subtopic heading

Examples:
  - 'Fundamental rights.' → 'human_agency_oversight_fundamental_rights'
  - 'Human oversight.' → 'human_agency_oversight_human_oversight'
  - 'Resilience to attack and security.' → 'technical_robustness_resilience_to_attack'
  - 'Privacy by design and by default.' → 'privacy_data_gov_privacy_by_design'

Keep IDs concise but recognizable.

4.3 APPLY TO ALL SEVEN REQUIREMENTS

⚠️ CRITICAL: Extract subtopics for ALL seven requirements, not just one or two!

Each requirement likely has 2–5 subtopics. If you find a requirement
with NO subtopics, set subtopics to empty list [], but this should be rare.

-------------------------------------------------------------------
5. RELATED PRINCIPLES (OPTIONAL)
-------------------------------------------------------------------
- Optionally, you may fill 'related_principles' with IDs of the
  HLEG ethical principles that underpin the requirement.
- These principle IDs (for future expansion) should be:

    - respect_for_human_autonomy
    - prevention_of_harm
    - fairness
    - explicability

- If you're not sure, leave 'related_principles' empty.
  Do NOT invent new principle IDs.

-------------------------------------------------------------------
6. TAGS (OPTIONAL)
-------------------------------------------------------------------
- 'tags' is optional. You may provide 0–5 concise keywords
  per requirement to help future querying, e.g.:

    - For technical robustness and safety:
        ['safety', 'robustness', 'reliability']
    - For diversity, non-discrimination and fairness:
        ['bias', 'non-discrimination']

- Tags must be grounded in the content of the requirement.

-------------------------------------------------------------------
7. COMPLETENESS & FAITHFULNESS
-------------------------------------------------------------------
- You must extract ALL seven requirements.
- Do NOT drop any requirement.
- Do NOT add extra requirements beyond the canonical seven.
- All text fields must be grounded in the original document.

-------------------------------------------------------------------
8. OUTPUT STYLE
-------------------------------------------------------------------
- Produce a single HlegStructuredDoc object.
- No extra commentary or free-form text outside the structured output.
- This output will be validated by Pydantic; follow the schema precisely.

⚠️⚠️⚠️ CRITICAL STRUCTURE - READ CAREFULLY ⚠️⚠️⚠️

The output MUST have SEVEN separate HlegRequirement objects at the TOP LEVEL,
NOT one requirement with 7 subtopics!

CORRECT OUTPUT STRUCTURE:
{
  "document_id": "ai_hleg_2019",
  "official_title": "Ethics Guidelines for Trustworthy AI",
  "short_title": "AI HLEG Ethics Guidelines",
  "year": 2019,
  "requirements": [
    {
      "id": "human_agency_and_oversight",
      "order": 1,
      "name": "Human agency and oversight",
      "short_description": "...",
      "full_text": "...",
      "related_principles": [...],
      "tags": [...],
      "subtopics": [
        {
          "id": "human_agency_oversight_fundamental_rights",
          "label": "Fundamental rights",
          "description": "AI systems should respect fundamental rights..."
        },
        {
          "id": "human_agency_oversight_human_oversight",
          "label": "Human oversight",
          "description": "Humans must be able to oversee AI systems..."
        }
      ]
    },
    {
      "id": "technical_robustness_and_safety",
      "order": 2,
      "name": "Technical robustness and safety",
      "short_description": "...",
      "full_text": "...",
      "related_principles": [...],
      "tags": [...],
      "subtopics": [
        {
          "id": "technical_robustness_resilience_to_attack",
          "label": "Resilience to attack and security",
          "description": "AI systems should be resilient against attacks..."
        },
        {
          "id": "technical_robustness_fallback_plans",
          "label": "Fallback plans and general safety",
          "description": "AI systems should have fallback plans..."
        }
      ]
    },
    ... (continue for all 7 requirements)
  ]
}

⚠️⚠️ WRONG - DO NOT DO THIS:
❌ {
  "requirements": [
    {
      "id": "human_agency_and_oversight",
      "order": 1,
      "subtopics": [
        {"id": "technical_robustness_and_safety", ...},  ← WRONG! This is a requirement, not a subtopic!
        {"id": "privacy_and_data_governance", ...},      ← WRONG!
        {"id": "transparency", ...},                     ← WRONG!
      ]
    }
  ]
}

⚠️ KEY DISTINCTION:
- SEVEN REQUIREMENTS go in HlegStructuredDoc.requirements array
- Each requirement's subtopics go in that requirement's subtopics array
- The seven requirements are NOT subtopics of each other!
- Subtopics are the "catch phrase" headings within EACH requirement
""",
)

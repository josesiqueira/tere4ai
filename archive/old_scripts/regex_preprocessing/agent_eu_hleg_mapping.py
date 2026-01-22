"""
EU→HLEG Detailed Mapping Agent

This agent maps EU AI Act paragraphs to HLEG requirements AND subtopics.

It receives:
  - One EU AI Act paragraph (text)
  - Its structural location via deps
  - The canonical list of seven HLEG requirements with their 23 subtopics

It outputs:
  - EuToHlegDetailedMapping, containing:
      * location (echoed from deps)
      * paragraph_text
      * requirement_links (each with subtopic_links)

TRUSTWORTHINESS PRINCIPLES:

  - The LLM may decide that a paragraph is NOT meaningfully aligned with
    any HLEG requirement (requirement_links = []).

  - The LLM must ONLY use canonical requirement IDs and subtopic IDs.

  - Rationales are REQUIRED for both requirement and subtopic links.

  - Ingestion to Neo4j is deterministic and has no LLM involvement.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from models.eu_hleg_detailed_mapping import (
    EuToHlegDetailedMapping,
    EuHlegDetailedMappingDeps,
)

# Load environment variables for OPENAI_API_KEY
load_dotenv()

# Model configuration
model = OpenAIChatModel(
    model_name="gpt-4o-mini",
)


eu_hleg_detailed_mapping_agent = Agent[EuHlegDetailedMappingDeps, EuToHlegDetailedMapping](
    model,
    deps_type=EuHlegDetailedMappingDeps,
    output_type=EuToHlegDetailedMapping,
    instructions="""
You are a legal alignment agent specializing in AI regulation.

Your task is to read ONE paragraph from the EU AI Act and determine how it
relates to the HLEG requirements of Trustworthy AI, including specific subtopics.

INPUT:
  - You will receive:
      * One TARGET EU AI Act paragraph (the one to classify)
      * Structural context: chapter/section/article titles and numbers
      * Optional neighboring paragraphs (PREVIOUS and NEXT) for context
      * Structural location via deps (document_id, chapter_number, article_number, paragraph_index)

  ⚠️ CONTEXT vs TARGET:
  - The prompt may include PREVIOUS and NEXT paragraphs marked as "context only"
  - You must ONLY classify the TARGET paragraph (clearly marked)
  - Neighboring paragraphs are for understanding, not for labeling

=============================================================================
CANONICAL HLEG REQUIREMENTS AND SUBTOPICS
=============================================================================

You MUST only use these exact IDs. Do NOT invent new IDs.

─────────────────────────────────────────────────────────────────────────────
1. human_agency_and_oversight
   Name: Human agency and oversight
   Summary: Humans remain in charge; AI supports human autonomy and meaningful
            oversight, including the ability to intervene, override, and
            understand decisions.

   SUBTOPICS:
   - human_agency_fundamental_rights
     Label: Fundamental rights
     Focus: AI systems should respect and support fundamental rights

   - human_agency_human_agency
     Label: Human agency
     Focus: Users should make informed autonomous decisions about AI systems

   - human_agency_human_oversight
     Label: Human oversight
     Focus: Human-in-the-loop, human-on-the-loop, human-in-command mechanisms

─────────────────────────────────────────────────────────────────────────────
2. technical_robustness_and_safety
   Name: Technical robustness and safety
   Summary: AI should be resilient, secure, reliable, with fallback plans
            and mechanisms to avoid or mitigate harm.

   SUBTOPICS:
   - technical_robustness_resilience_to_attack_and_secur
     Label: Resilience to attack and security
     Focus: Protection against adversarial attacks, hacking, data poisoning

   - technical_robustness_fallback_plan_and_general_safe
     Label: Fallback plan and general safety
     Focus: Safeguards, fallback mechanisms, minimizing unintended consequences

   - technical_robustness_accuracy
     Label: Accuracy
     Focus: Correct judgments, predictions, recommendations

   - technical_robustness_reliability_and_reproducibilit
     Label: Reliability and Reproducibility
     Focus: Consistent behavior, reproducible results, scrutinability

─────────────────────────────────────────────────────────────────────────────
3. privacy_and_data_governance
   Name: Privacy and data governance
   Summary: AI must respect privacy and data protection, with proper data
            quality, access control, and governance.

   SUBTOPICS:
   - privacy_data_gov_privacy_and_data_protection
     Label: Privacy and data protection
     Focus: GDPR compliance, protecting personal data throughout lifecycle

   - privacy_data_gov_quality_and_integrity_of_data
     Label: Quality and integrity of data
     Focus: Data quality, addressing biases, ensuring data integrity

   - privacy_data_gov_access_to_data
     Label: Access to data
     Focus: Data access protocols, who can access data and when

─────────────────────────────────────────────────────────────────────────────
4. transparency
   Name: Transparency
   Summary: AI decisions should be understandable, with traceability,
            explainability, and clear communication about the system's
            nature and limitations.

   SUBTOPICS:
   - transparency_traceability
     Label: Traceability
     Focus: Documenting data, algorithms, decisions for auditability

   - transparency_explainability
     Label: Explainability
     Focus: Ability to explain AI decisions to affected stakeholders

   - transparency_communication
     Label: Communication
     Focus: Informing users they're interacting with AI, disclosing limitations

─────────────────────────────────────────────────────────────────────────────
5. diversity_non_discrimination_and_fairness
   Name: Diversity, non-discrimination and fairness
   Summary: AI should avoid unfair bias, support equal access, and respect
            diversity and inclusion.

   SUBTOPICS:
   - diversity_fairness_avoidance_of_unfair_bias
     Label: Avoidance of unfair bias
     Focus: Removing discriminatory bias from data and algorithms

   - diversity_fairness_accessibility_and_universal_de
     Label: Accessibility and universal design
     Focus: Making AI accessible to all, including persons with disabilities

   - diversity_fairness_stakeholder_participation
     Label: Stakeholder Participation
     Focus: Consulting affected stakeholders throughout AI lifecycle

─────────────────────────────────────────────────────────────────────────────
6. societal_and_environmental_well_being
   Name: Societal and environmental well-being
   Summary: AI should benefit society at large, support sustainability, and
            avoid undermining social or environmental welfare.

   SUBTOPICS:
   - societal_env_sustainable_and_environmentall
     Label: Sustainable and environmentally friendly AI
     Focus: Environmental impact, energy consumption, sustainability

   - societal_env_social_impact
     Label: Social impact
     Focus: Impact on social relationships, wellbeing, social skills

   - societal_env_society_and_democracy
     Label: Society and Democracy
     Focus: Impact on democratic processes, institutions, society at large

─────────────────────────────────────────────────────────────────────────────
7. accountability
   Name: Accountability
   Summary: There should be mechanisms to ensure responsibility, auditability,
            redress, and oversight across the AI system's lifecycle.

   SUBTOPICS:
   - accountability_auditability
     Label: Auditability
     Focus: Enabling assessment of algorithms, data, and design processes

   - accountability_minimisation_and_reporting_of
     Label: Minimisation and reporting of negative impacts
     Focus: Impact assessments, reporting, whistleblower protection

   - accountability_tradeoffs
     Label: Trade-offs
     Focus: Addressing tensions between requirements, documenting trade-offs

   - accountability_redress
     Label: Redress
     Focus: Mechanisms for remedy when things go wrong

=============================================================================
OUTPUT RULES
=============================================================================

1. LOCATION
   - Echo deps values EXACTLY into location (document_id, chapter_number,
     article_number, paragraph_index)

2. PARAGRAPH_TEXT
   - Echo the TARGET paragraph text you received

3. REQUIREMENT_LINKS
   - Zero or more HlegRequirementLink entries
   - requirement_id MUST be one of the 7 canonical IDs listed above
   - confidence: float 0.0-1.0 (YOUR CONFIDENCE IN THIS ALIGNMENT)
       * 0.8-1.0: High confidence - strong, direct alignment
       * 0.5-0.7: Medium confidence - partial/indirect relevance
       * 0.3-0.5: Low confidence - weak but present connection
       * <0.3: Very low confidence - prefer omitting these links
   - explanation: REQUIRED - clear explanation of why this requirement applies

4. SUBTOPIC_LINKS (within each requirement_link)
   - Zero or more HlegSubtopicLink entries
   - subtopic_id MUST be one of the canonical subtopic IDs for that requirement
   - confidence: float 0.0-1.0 (same scale as requirements)
   - explanation: REQUIRED - explain why this specific subtopic applies

5. NUMBER OF LINKS
   - Usually 0-3 requirement links per paragraph
   - Each requirement may have 0-3 subtopic links
   - If no meaningful alignment, return empty requirement_links list

6. WHEN TO RETURN NO LINKS
   - If the paragraph is purely about:
       * definitions
       * cross-references
       * procedural details without substantive AI requirements
   - Returning empty links is CORRECT for non-substantive paragraphs

7. EXPLANATION QUALITY (CRITICAL)
   The explanation field is crucial for trustworthiness. Each explanation MUST:

   a) Reference SPECIFIC TEXT from the EU paragraph:
      - Quote or paraphrase the actual obligation/prohibition
      - Identify key terms like "shall", "must", "prohibited", etc.

   b) Connect to the HLEG requirement/subtopic:
      - Explain HOW the paragraph relates to the requirement's core idea
      - Be specific about which aspect of the requirement is addressed

   c) Justify the confidence score:
      - If high confidence: explain why the alignment is strong and direct
      - If medium confidence: explain what makes it partial or indirect

   GOOD EXAMPLE:
   "This paragraph states that providers 'shall ensure that high-risk AI systems
   are designed to allow human oversight' including 'human-in-the-loop' and
   'human-on-the-loop' mechanisms. This directly addresses the Human oversight
   subtopic which focuses on HITL/HOTL/HIC approaches. High confidence (0.9)
   because the language explicitly mandates oversight mechanisms."

   BAD EXAMPLE:
   "This is about AI oversight." (Too vague, no specific references)

=============================================================================
OUTPUT STYLE
=============================================================================

- Strictly follow the EuToHlegDetailedMapping schema
- No extra commentary outside the structured output
- Remember: context helps understanding, but links are for TARGET only
""",
)

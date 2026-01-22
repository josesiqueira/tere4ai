"""
TERE4AI Specification Agent

This agent generates formal requirements from applicable EU AI Act articles.
Each requirement is anchored to specific legal sources with full traceability.

GENERATION STRATEGY:
  - One or more requirements per article paragraph
  - SHALL/SHOULD/MAY language for requirement types
  - Full citation bundles for each requirement
  - HLEG principle coverage
  - Verification criteria

OUTPUT:
  - List of GeneratedRequirement models
  - Each requirement has citations, HLEG mappings, verification criteria
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from agents.base import AgentConfig, BaseAgent, MCPToolClient
from shared.models import (
    Citation,
    GeneratedRequirement,
    RequirementCategory,
    RequirementPriority,
    RequirementType,
    RiskClassification,
    RiskLevel,
    SystemDescription,
)


@dataclass
class SpecificationInput:
    """Input to the Specification Agent."""

    system_description: SystemDescription
    risk_classification: RiskClassification


class SpecificationOutput(BaseModel):
    """Output from the Specification Agent."""

    requirements: list[GeneratedRequirement] = Field(
        default_factory=list,
        description="List of generated requirements"
    )
    articles_processed: list[int] = Field(
        default_factory=list,
        description="List of article numbers that were processed"
    )
    generation_notes: Optional[str] = Field(
        default=None,
        description="Notes about the generation process"
    )


class SpecificationAgent(BaseAgent[SpecificationInput, SpecificationOutput]):
    """
    Specification Agent - Phase 3 of the RE Pipeline.

    Generates formal requirements from applicable EU AI Act articles:
      1. Gets applicable articles from MCP based on risk level
      2. For each article, fetches full content with HLEG mappings
      3. Uses LLM to generate requirements with proper citations
      4. Ensures HLEG coverage across requirements
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
                "Please set it before initializing the SpecificationAgent."
            )
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "specification"

    @property
    def phase(self) -> str:
        return "specification"

    def _get_system_prompt(self) -> str:
        return """You are the Specification Agent for TERE4AI, a Requirements Engineering system for AI Act compliance.

Your task is to generate formal requirements from EU AI Act articles. Each requirement must be:
1. TRACEABLE - Anchored to specific article paragraphs
2. VERIFIABLE - Has clear verification criteria
3. COMPLETE - Covers the article's obligations
4. HLEG-ALIGNED - Addresses relevant HLEG principles

REQUIREMENT FORMAT:

1. ID: Use format REQ-XXX (e.g., REQ-001, REQ-002)

2. TITLE: Short descriptive title (5-10 words)

3. STATEMENT: Formal requirement text using:
   - SHALL for mandatory requirements
   - SHOULD for recommended requirements
   - MAY for optional requirements
   Example: "The system SHALL implement a documented risk management process..."

4. CATEGORY: One of:
   - risk_management (Article 9)
   - data_governance (Article 10)
   - documentation (Article 11)
   - record_keeping (Article 12)
   - transparency (Article 13)
   - human_oversight (Article 14)
   - accuracy_robustness (Article 15)
   - provider_obligations (Articles 16-22)
   - deployer_obligations (Articles 26-27)
   - transparency_limited (Article 50)
   - general (other)

5. PRIORITY: critical | high | medium | low
   - critical: Safety-related or fundamental rights
   - high: Core compliance requirements
   - medium: Supporting requirements
   - low: Nice-to-have

6. EU AI ACT CITATIONS: List of citations with:
   - article: Article number as string
   - paragraph: Paragraph number (1-based)
   - point: Point letter if applicable (a, b, c, etc.)
   - quoted_text: Exact or close paraphrase from article

7. HLEG CITATIONS: List of HLEG principles with:
   - requirement_id: One of the 7 canonical IDs
   - subtopic_id: Specific subtopic if applicable
   - relevance_score: 0.0-1.0

8. VERIFICATION CRITERIA: List of testable criteria
   Example: ["Risk management documentation exists", "Risks are identified and assessed"]

9. VERIFICATION METHOD: How to verify
   Example: "Documentation review and process audit"

10. RATIONALE: Why this requirement is needed

OUTPUT FORMAT:
Return a JSON object with:
{
  "requirements": [
    {
      "id": "REQ-001",
      "title": "...",
      "statement": "The system SHALL...",
      "category": "risk_management",
      "priority": "high",
      "requirement_type": "mandatory",
      "eu_ai_act_citations": [
        {
          "article": "9",
          "paragraph": 1,
          "point": null,
          "quoted_text": "..."
        }
      ],
      "hleg_citations": [
        {
          "requirement_id": "technical_robustness_and_safety",
          "subtopic_id": "resilience_to_attack",
          "relevance_score": 0.9
        }
      ],
      "verification_criteria": ["..."],
      "verification_method": "...",
      "rationale": "...",
      "context": "..."
    }
  ]
}

HLEG PRINCIPLE IDS (use exactly these):
- human_agency_and_oversight
- technical_robustness_and_safety
- privacy_and_data_governance
- transparency
- diversity_non_discrimination_and_fairness
- societal_and_environmental_wellbeing
- accountability"""

    async def run(self, input_data: SpecificationInput) -> SpecificationOutput:
        """
        Generate requirements from applicable articles.

        Args:
            input_data: System description and risk classification

        Returns:
            SpecificationOutput with generated requirements
        """
        self._start_trace(
            input_summary=f"Risk Level: {input_data.risk_classification.level.value}"
        )

        try:
            # Check if system is prohibited
            if input_data.risk_classification.level == RiskLevel.UNACCEPTABLE:
                self._complete_trace(
                    output_summary="No requirements - system is prohibited"
                )
                return SpecificationOutput(
                    requirements=[],
                    articles_processed=[],
                    generation_notes="System is prohibited under Article 5. No requirements generated."
                )

            # Get applicable articles
            risk_level = input_data.risk_classification.level.value
            annex_category = None
            if input_data.risk_classification.annex_iii_category:
                annex_category = input_data.risk_classification.annex_iii_category.value

            articles = self.mcp.get_applicable_articles(risk_level, annex_category)

            if not articles:
                self._complete_trace(
                    output_summary="No applicable articles"
                )
                return SpecificationOutput(
                    requirements=[],
                    articles_processed=[],
                    generation_notes=f"No specific articles apply for {risk_level} risk level."
                )

            # Generate requirements for each article
            all_requirements: list[GeneratedRequirement] = []
            processed_articles: list[int] = []
            req_counter = 1

            for article in articles:
                article_num = article.get("number")
                if article_num is None:
                    continue

                # Get full article with citations
                article_data = self.mcp.get_article_with_citations(article_num)

                # Generate requirements for this article
                reqs = await self._generate_article_requirements(
                    input_data.system_description,
                    article_data,
                    req_counter
                )

                all_requirements.extend(reqs)
                processed_articles.append(article_num)
                req_counter += len(reqs)

            self._complete_trace(
                output_summary=f"Generated {len(all_requirements)} requirements from {len(processed_articles)} articles"
            )

            return SpecificationOutput(
                requirements=all_requirements,
                articles_processed=processed_articles,
                generation_notes=f"Generated {len(all_requirements)} requirements from {len(processed_articles)} articles."
            )

        except Exception as e:
            self._complete_trace(error=str(e))
            raise

    async def _generate_article_requirements(
        self,
        system_desc: SystemDescription,
        article_data: dict,
        start_id: int
    ) -> list[GeneratedRequirement]:
        """Generate requirements from a single article."""

        article_num = article_data.get("number")
        title = article_data.get("title", f"Article {article_num}")
        paragraphs = article_data.get("paragraphs", [])
        hleg_mappings = article_data.get("hleg_mappings", [])
        category = article_data.get("category", "general")

        # Build article content for prompt
        article_text = ""
        for p in paragraphs:
            if p and p.get("text"):
                idx = p.get("index", 1)
                article_text += f"\n{idx}. {p['text']}"
                points = p.get("points", [])
                for pt in points:
                    if pt and pt.get("text"):
                        article_text += f"\n   ({pt.get('marker', '')}) {pt['text']}"

        user_message = f"""Generate requirements from this EU AI Act article for the following system:

SYSTEM CONTEXT:
- Domain: {system_desc.domain.value if system_desc.domain else 'general'}
- Purpose: {system_desc.purpose}
- Safety Critical: {system_desc.safety_critical}
- Biometric Processing: {system_desc.biometric_processing}

ARTICLE {article_num}: {title}
{article_text}

HLEG MAPPINGS FOR THIS ARTICLE:
{json.dumps(hleg_mappings, indent=2)}

REQUIREMENT CATEGORY: {category}
START ID: REQ-{start_id:03d}

Generate 1-3 requirements that capture the key obligations from this article.
Each requirement must have proper citations back to specific paragraphs."""

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

        # Parse requirements from LLM response
        requirements = []
        for req_data in data.get("requirements", []):
            try:
                req = self._parse_requirement(req_data, article_num)
                requirements.append(req)
            except Exception as e:
                self.logger.warning(f"Failed to parse requirement: {e}")
                continue

        return requirements

    def _parse_requirement(self, data: dict, article_num: int) -> GeneratedRequirement:
        """Parse requirement data into GeneratedRequirement model."""

        # Parse category
        category_str = data.get("category", "general")
        try:
            category = RequirementCategory(category_str)
        except ValueError:
            category = RequirementCategory.GENERAL

        # Parse priority
        priority_str = data.get("priority", "medium")
        try:
            priority = RequirementPriority(priority_str)
        except ValueError:
            priority = RequirementPriority.MEDIUM

        # Parse requirement type
        type_str = data.get("requirement_type", "mandatory")
        try:
            req_type = RequirementType(type_str)
        except ValueError:
            req_type = RequirementType.MANDATORY

        # Build EU AI Act citations as proper Citation objects
        eu_citations = []
        for cit in data.get("eu_ai_act_citations", []):
            article_str = str(cit.get("article", article_num))
            para = cit.get("paragraph")
            point = cit.get("point")
            ref_text = f"Article {article_str}"
            if para:
                ref_text += f"({para})"
                if point:
                    ref_text += f"({point})"
            eu_citations.append(Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article=article_str,
                paragraph=para,
                point=point,
                reference_text=ref_text,
                quoted_text=cit.get("quoted_text", ""),
            ))

        # Build HLEG citations as proper Citation objects
        hleg_citations = []
        hleg_names = {
            "human_agency_and_oversight": "Human Agency and Oversight",
            "technical_robustness_and_safety": "Technical Robustness and Safety",
            "privacy_and_data_governance": "Privacy and Data Governance",
            "transparency": "Transparency",
            "diversity_non_discrimination_and_fairness": "Diversity, Non-discrimination and Fairness",
            "societal_and_environmental_wellbeing": "Societal and Environmental Well-being",
            "accountability": "Accountability",
        }
        for cit in data.get("hleg_citations", []):
            req_id = cit.get("requirement_id")
            if req_id:
                hleg_citations.append(Citation(
                    source="AI_HLEG",
                    document_id="ai_hleg_2019",
                    requirement_id=req_id,
                    subtopic_id=cit.get("subtopic_id"),
                    reference_text=hleg_names.get(req_id, req_id),
                    quoted_text=f"HLEG: {hleg_names.get(req_id, req_id)}",
                    relevance_score=cit.get("relevance_score", 0.8),
                ))

        # Get derived articles
        derived_articles = [str(article_num)]
        for cit in eu_citations:
            if cit.article and cit.article not in derived_articles:
                derived_articles.append(cit.article)

        # Get addressed HLEG principles
        addressed_hleg = list(set(
            cit.requirement_id for cit in hleg_citations if cit.requirement_id
        ))

        return GeneratedRequirement(
            id=data.get("id", "REQ-000"),
            title=data.get("title", "Untitled Requirement"),
            statement=data.get("statement", ""),
            category=category,
            priority=priority,
            requirement_type=req_type,
            eu_ai_act_citations=eu_citations,
            hleg_citations=hleg_citations,
            supporting_recitals=[],
            rationale=data.get("rationale", ""),
            context=data.get("context", ""),
            verification_criteria=data.get("verification_criteria", []),
            verification_method=data.get("verification_method", ""),
            derived_from_articles=derived_articles,
            addresses_hleg_principles=addressed_hleg,
            addresses_hleg_subtopics=list(set(
                cit.subtopic_id for cit in hleg_citations
                if cit.subtopic_id
            )),
        )

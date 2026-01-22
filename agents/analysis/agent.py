"""
TERE4AI Analysis Agent

This agent classifies the risk level of an AI system based on its
SystemDescription. It uses the MCP tools to query the EU AI Act
knowledge graph and determine the appropriate risk classification.

CLASSIFICATION LOGIC:
  1. Check Article 5 prohibited practices (UNACCEPTABLE)
  2. Check Annex III high-risk categories (HIGH)
  3. Check Article 6(3) exception for Annex III matches
  4. Check Article 50 transparency requirements (LIMITED)
  5. Default to MINIMAL

OUTPUT:
  - RiskClassification with full legal grounding
  - CitationBundle for the legal basis
  - HLEG implications
"""

from __future__ import annotations

import json
import os
from typing import Optional

from openai import AsyncOpenAI

from agents.base import AgentConfig, BaseAgent, MCPToolClient
from shared.models import (
    AnnexIIICategory,
    Citation,
    CitationBundle,
    ProhibitedPractice,
    RiskClassification,
    RiskLevel,
    SystemDescription,
)


class AnalysisAgent(BaseAgent[SystemDescription, RiskClassification]):
    """
    Analysis Agent - Phase 2 of the RE Pipeline.

    Takes SystemDescription and determines risk classification using:
      1. MCP classify_risk_level tool for initial classification
      2. LLM reasoning to build complete RiskClassification model
      3. Legal grounding with citations

    If risk level is UNACCEPTABLE, the pipeline stops here.
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
                "Please set it before initializing the AnalysisAgent."
            )
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "analysis"

    @property
    def phase(self) -> str:
        return "analysis"

    def _get_system_prompt(self) -> str:
        return """You are the Analysis Agent for TERE4AI, a Requirements Engineering system for AI Act compliance.

Your task is to analyze the risk classification result from the MCP tool and build a complete
RiskClassification model with proper legal grounding.

You will receive:
1. The SystemDescription (structured input)
2. The MCP tool classification result

Your job is to:
1. Validate the classification makes sense for the system described
2. Build proper Citation and CitationBundle objects for legal grounding
3. Identify HLEG principles that are implicated
4. Provide clear reasoning

LEGAL GROUNDING RULES:

1. PRIMARY CITATION must reference the exact legal source:
   - For UNACCEPTABLE: Article 5(1)(a-h) prohibition
   - For HIGH: Article 6(2) + Annex III category
   - For LIMITED: Article 50
   - For MINIMAL: No specific article

2. SUPPORTING CITATIONS should include:
   - Related recitals that provide context
   - HLEG principles that are implicated
   - Related articles if applicable

3. HLEG IMPLICATIONS:
   - For UNACCEPTABLE: Which principles are VIOLATED
   - For HIGH/LIMITED: Which principles must be ADDRESSED

OUTPUT: Return a JSON object with these fields:
- level: "unacceptable" | "high" | "limited" | "minimal"
- prohibited_practice: For UNACCEPTABLE, e.g. "5_1_a"
- prohibition_details: Explanation if prohibited
- annex_iii_category: For HIGH, e.g. "1" through "8"
- annex_iii_subcategory: e.g. "5(a)" for healthcare
- applicable_articles: List of article numbers as strings
- article_6_3_exception_checked: boolean
- article_6_3_exception_applies: boolean
- article_6_3_rationale: Explanation if checked
- hleg_principles: List of HLEG principle IDs implicated
- reasoning: Complete classification reasoning
- confidence: 0.0-1.0

HLEG PRINCIPLE IDs:
- human_agency_and_oversight
- technical_robustness_and_safety
- privacy_and_data_governance
- transparency
- diversity_non_discrimination_and_fairness
- societal_and_environmental_wellbeing
- accountability"""

    async def run(self, input_data: SystemDescription) -> RiskClassification:
        """
        Classify risk level for the system.

        Args:
            input_data: Structured system description

        Returns:
            RiskClassification with legal grounding
        """
        self._start_trace(
            input_summary=f"Domain: {input_data.domain}, Purpose: {input_data.purpose[:50]}..."
        )

        try:
            # Step 1: Get features dictionary for MCP tool
            features = input_data.to_features_dict()

            # Step 2: Call MCP classify_risk_level tool
            mcp_result = self.mcp.classify_risk_level(features)

            # Step 3: Use LLM to build complete RiskClassification
            result = await self._build_classification(input_data, mcp_result)

            self._complete_trace(
                output_summary=f"Level: {result.level.value}, Confidence: {result.confidence}"
            )

            return result

        except Exception as e:
            self._complete_trace(error=str(e))
            raise

    async def _build_classification(
        self,
        system_desc: SystemDescription,
        mcp_result: dict
    ) -> RiskClassification:
        """Build complete RiskClassification from MCP result."""

        user_message = f"""Analyze this risk classification and build a complete RiskClassification:

SYSTEM DESCRIPTION:
- Domain: {system_desc.domain.value if system_desc.domain else 'general'}
- Purpose: {system_desc.purpose}
- Data Types: {[d.value for d in system_desc.data_types] if system_desc.data_types else []}
- Decision Types: {[d.value for d in system_desc.decision_types] if system_desc.decision_types else []}
- Autonomy Level: {system_desc.autonomy_level.value if system_desc.autonomy_level else 'partial'}
- Affects Fundamental Rights: {system_desc.affects_fundamental_rights}
- Safety Critical: {system_desc.safety_critical}
- Biometric Processing: {system_desc.biometric_processing}
- Real-time Biometric: {system_desc.real_time_biometric}
- Law Enforcement Use: {system_desc.law_enforcement_use}
- Emotion Recognition: {system_desc.emotion_recognition}
- Social Scoring: {system_desc.social_scoring}
- Vulnerable Groups: {system_desc.vulnerable_groups}

MCP CLASSIFICATION RESULT:
{json.dumps(mcp_result, indent=2)}

Build a complete RiskClassification with proper legal grounding."""

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

        # Build the RiskClassification
        return self._create_risk_classification(data, mcp_result)

    def _create_risk_classification(
        self,
        llm_data: dict,
        mcp_result: dict
    ) -> RiskClassification:
        """Create RiskClassification from LLM output and MCP result."""

        # Parse risk level
        level = RiskLevel(mcp_result.get("risk_level", "minimal"))

        # Build primary citation
        primary_citation = self._build_primary_citation(mcp_result, level)

        # Build supporting citations (HLEG)
        supporting_citations = self._build_hleg_citations(
            llm_data.get("hleg_principles", mcp_result.get("hleg_principles", []))
        )

        # Build citation bundle
        legal_basis = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale=llm_data.get("reasoning", mcp_result.get("reasoning", ""))
        )

        # Build HLEG implications
        hleg_implications = self._build_hleg_citations(
            llm_data.get("hleg_principles", mcp_result.get("hleg_principles", []))
        )

        # Parse enums
        prohibited_practice = None
        if level == RiskLevel.UNACCEPTABLE:
            pp_str = llm_data.get("prohibited_practice")
            if pp_str:
                try:
                    prohibited_practice = ProhibitedPractice(pp_str)
                except ValueError:
                    pass

        annex_iii_category = None
        if level == RiskLevel.HIGH:
            annex_str = llm_data.get("annex_iii_category") or mcp_result.get("annex_category")
            if annex_str:
                try:
                    annex_iii_category = AnnexIIICategory(annex_str)
                except ValueError:
                    pass

        # Build applicable articles list
        applicable_articles = []
        if level == RiskLevel.HIGH:
            applicable_articles = [str(i) for i in range(8, 28)]
        elif level == RiskLevel.LIMITED:
            applicable_articles = ["50"]

        return RiskClassification(
            level=level,
            legal_basis=legal_basis,
            prohibited_practice=prohibited_practice,
            prohibition_details=llm_data.get("prohibition_details"),
            annex_iii_category=annex_iii_category,
            annex_iii_subcategory=llm_data.get("annex_iii_subcategory"),
            applicable_articles=applicable_articles,
            article_6_3_exception_checked=llm_data.get("article_6_3_exception_checked", False),
            article_6_3_exception_applies=mcp_result.get("article_6_exception", False),
            article_6_3_rationale=llm_data.get("article_6_3_rationale"),
            hleg_implications=hleg_implications,
            reasoning=llm_data.get("reasoning", mcp_result.get("reasoning", "")),
            confidence=llm_data.get("confidence", 1.0),
        )

    def _build_primary_citation(self, mcp_result: dict, level: RiskLevel) -> Citation:
        """Build the primary citation for the legal basis."""

        legal_basis_article = mcp_result.get("legal_basis_article", "")
        legal_basis_text = mcp_result.get("legal_basis_text", "")

        if level == RiskLevel.UNACCEPTABLE:
            # Parse Article 5(1)(x) format
            article = "5"
            paragraph = 1
            point = None
            if "(" in legal_basis_article:
                parts = legal_basis_article.replace("Article ", "").split("(")
                if len(parts) >= 3:
                    point = parts[2].rstrip(")")

            return Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article=article,
                paragraph=paragraph,
                point=point,
                reference_text=f"Article 5 - Prohibited AI Practices",
                quoted_text=legal_basis_text[:500],
            )

        elif level == RiskLevel.HIGH:
            # Article 6(2) + Annex III
            return Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article="6",
                paragraph=2,
                annex="III",
                annex_section=mcp_result.get("annex_category"),
                reference_text=legal_basis_article or "Article 6(2) + Annex III",
                quoted_text=legal_basis_text[:500],
            )

        elif level == RiskLevel.LIMITED:
            return Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article="50",
                paragraph=1,
                reference_text="Article 50 - Transparency obligations",
                quoted_text=legal_basis_text[:500],
            )

        else:  # MINIMAL
            return Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                reference_text="No specific regulatory requirements",
                quoted_text="System does not fall under specific regulatory categories.",
            )

    def _build_hleg_citations(self, principle_ids: list[str]) -> list[Citation]:
        """Build citations for HLEG principles."""
        hleg_names = {
            "human_agency_and_oversight": "Human Agency and Oversight",
            "technical_robustness_and_safety": "Technical Robustness and Safety",
            "privacy_and_data_governance": "Privacy and Data Governance",
            "transparency": "Transparency",
            "diversity_non_discrimination_and_fairness": "Diversity, Non-discrimination and Fairness",
            "societal_and_environmental_wellbeing": "Societal and Environmental Well-being",
            "accountability": "Accountability",
        }

        citations = []
        for pid in principle_ids:
            if pid in hleg_names:
                citations.append(Citation(
                    source="AI_HLEG",
                    document_id="ai_hleg_2019",
                    requirement_id=pid,
                    reference_text=hleg_names[pid],
                    quoted_text=f"HLEG Requirement: {hleg_names[pid]}",
                    relevance_score=0.8,
                ))

        return citations

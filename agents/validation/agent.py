"""
TERE4AI Validation Agent

This agent validates the completeness, consistency, and traceability of
generated requirements. It ensures adequate coverage of applicable articles
and HLEG principles.

VALIDATION CHECKS:
  1. Article Coverage - Are all applicable articles addressed?
  2. HLEG Coverage - Are relevant HLEG principles covered?
  3. Consistency - Are there conflicts between requirements?
  4. Citation Validity - Are all citations properly formed?

OUTPUT:
  - ValidationResult with coverage metrics and issues
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI

from agents.base import AgentConfig, BaseAgent, MCPToolClient
from shared.models import (
    ConflictDetail,
    GeneratedRequirement,
    InvalidCitationDetail,
    RiskClassification,
    ValidationResult,
)


@dataclass
class ValidationInput:
    """Input to the Validation Agent."""

    requirements: list[GeneratedRequirement]
    risk_classification: RiskClassification
    applicable_articles: list[int]


class ValidationAgent(BaseAgent[ValidationInput, ValidationResult]):
    """
    Validation Agent - Phase 4 of the RE Pipeline.

    Validates requirements for:
      1. Article Coverage (>=80% target)
      2. HLEG Principle Coverage (>=70% target)
      3. Internal Consistency (no conflicts)
      4. Citation Validity (all citations properly formed)
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
                "Please set it before initializing the ValidationAgent."
            )
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return "validation"

    @property
    def phase(self) -> str:
        return "validation"

    def _get_system_prompt(self) -> str:
        return """You are the Validation Agent for TERE4AI, a Requirements Engineering system for AI Act compliance.

Your task is to check requirements for conflicts and suggest improvements.

CONFLICT TYPES:
1. contradiction - Two requirements make incompatible demands
2. redundancy - Two requirements say the same thing
3. overlap - Two requirements partially overlap in scope
4. dependency - One requirement depends on another but doesn't reference it

For each potential conflict, provide:
- requirement_id_1: First requirement ID
- requirement_id_2: Second requirement ID
- conflict_type: One of the types above
- explanation: Why this is a conflict
- suggested_resolution: How to fix it

OUTPUT FORMAT:
{
  "conflicts": [
    {
      "requirement_id_1": "REQ-001",
      "requirement_id_2": "REQ-005",
      "conflict_type": "redundancy",
      "explanation": "Both requirements address the same risk management aspect",
      "suggested_resolution": "Merge into single comprehensive requirement"
    }
  ],
  "recommendations": [
    "Consider adding requirement for Article X paragraph Y",
    "HLEG principle Z lacks specific requirements"
  ]
}"""

    async def run(self, input_data: ValidationInput) -> ValidationResult:
        """
        Validate requirements for completeness and consistency.

        Args:
            input_data: Requirements to validate with context

        Returns:
            ValidationResult with coverage metrics and issues
        """
        self._start_trace(
            input_summary=f"Validating {len(input_data.requirements)} requirements"
        )

        try:
            # Step 1: Calculate article coverage
            article_coverage = self._calculate_article_coverage(
                input_data.requirements,
                input_data.applicable_articles
            )

            # Step 2: Get HLEG coverage from MCP
            hleg_coverage = self._calculate_hleg_coverage(
                input_data.requirements,
                input_data.applicable_articles
            )

            # Step 3: Check for conflicts using LLM
            conflicts = await self._check_conflicts(input_data.requirements)

            # Step 4: Validate citations
            invalid_citations = self._validate_citations(input_data.requirements)

            # Step 5: Build recommendations
            recommendations = self._build_recommendations(
                article_coverage,
                hleg_coverage,
                conflicts,
                invalid_citations
            )

            # Build result
            covered_articles = [str(a) for a in article_coverage["covered"]]
            missing_articles = [str(a) for a in article_coverage["missing"]]
            covered_hleg = list(hleg_coverage["covered"])
            missing_hleg = list(hleg_coverage["missing"])
            covered_subtopics = list(hleg_coverage.get("subtopics", set()))

            # Convert percentages to proportions (0.0-1.0)
            article_cov_pct = article_coverage["percentage"]
            hleg_cov_pct = hleg_coverage["percentage"]
            subtopic_cov_pct = hleg_coverage.get("subtopic_percentage", 0.0)

            result = ValidationResult(
                article_coverage=article_cov_pct / 100.0,
                hleg_coverage=hleg_cov_pct / 100.0,
                subtopic_coverage=subtopic_cov_pct / 100.0,
                covered_articles=covered_articles,
                missing_articles=missing_articles,
                covered_hleg_principles=covered_hleg,
                missing_hleg_principles=missing_hleg,
                covered_subtopics=covered_subtopics,
                has_conflicts=len(conflicts) > 0,
                conflicts=conflicts,
                all_citations_valid=len(invalid_citations) == 0,
                invalid_citations=invalid_citations,
                is_complete=article_cov_pct >= 80.0,
                is_consistent=len(conflicts) == 0,
                is_valid=len(invalid_citations) == 0,
                recommendations=recommendations,
            )

            self._complete_trace(
                output_summary=f"Article: {article_coverage['percentage']:.1f}%, HLEG: {hleg_coverage['percentage']:.1f}%, Conflicts: {len(conflicts)}"
            )

            return result

        except Exception as e:
            self._complete_trace(error=str(e))
            raise

    def _calculate_article_coverage(
        self,
        requirements: list[GeneratedRequirement],
        applicable_articles: list[int]
    ) -> dict:
        """Calculate article coverage from requirements."""

        if not applicable_articles:
            return {
                "covered": set(),
                "missing": set(),
                "percentage": 100.0,
            }

        # Get covered articles from requirements
        covered = set()
        for req in requirements:
            for art in req.derived_from_articles:
                try:
                    covered.add(int(art))
                except (ValueError, TypeError):
                    pass

            for cit in req.eu_ai_act_citations:
                # Handle both Citation objects and dicts for flexibility
                if hasattr(cit, 'article') and cit.article:
                    try:
                        covered.add(int(cit.article))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(cit, dict) and cit.get("article"):
                    try:
                        covered.add(int(cit["article"]))
                    except (ValueError, TypeError):
                        pass

        applicable_set = set(applicable_articles)
        covered_applicable = covered.intersection(applicable_set)
        missing = applicable_set - covered_applicable

        percentage = (len(covered_applicable) / len(applicable_set)) * 100 if applicable_set else 100.0

        return {
            "covered": covered_applicable,
            "missing": missing,
            "percentage": percentage,
        }

    def _calculate_hleg_coverage(
        self,
        requirements: list[GeneratedRequirement],
        applicable_articles: list[int]
    ) -> dict:
        """Calculate HLEG coverage using MCP tool."""

        all_hleg = {
            "human_agency_and_oversight",
            "technical_robustness_and_safety",
            "privacy_and_data_governance",
            "transparency",
            "diversity_non_discrimination_and_fairness",
            "societal_and_environmental_wellbeing",
            "accountability",
        }

        # Get covered HLEG from requirements
        covered_hleg = set()
        covered_subtopics = set()

        for req in requirements:
            for pid in req.addresses_hleg_principles:
                if pid in all_hleg:
                    covered_hleg.add(pid)

            for cit in req.hleg_citations:
                # Handle both Citation objects and dicts
                if hasattr(cit, 'requirement_id'):
                    if cit.requirement_id in all_hleg:
                        covered_hleg.add(cit.requirement_id)
                    if hasattr(cit, 'subtopic_id') and cit.subtopic_id:
                        covered_subtopics.add(cit.subtopic_id)
                elif isinstance(cit, dict):
                    rid = cit.get("requirement_id")
                    if rid in all_hleg:
                        covered_hleg.add(rid)
                    sid = cit.get("subtopic_id")
                    if sid:
                        covered_subtopics.add(sid)

            for st in req.addresses_hleg_subtopics:
                if st:
                    covered_subtopics.add(st)

        # Get expected HLEG from MCP
        try:
            hleg_data = self.mcp.get_hleg_coverage(applicable_articles)
            expected_hleg = set(hleg_data.get("principles", {}).keys())
            expected_subtopics = set()
            for p in hleg_data.get("principles", {}).values():
                for st in p.get("subtopics", []):
                    expected_subtopics.add(st)
        except Exception:
            expected_hleg = all_hleg
            expected_subtopics = set()

        # Use all 7 HLEG principles as baseline if expected is empty
        if not expected_hleg:
            expected_hleg = all_hleg

        missing_hleg = expected_hleg - covered_hleg
        percentage = (len(covered_hleg) / len(expected_hleg)) * 100 if expected_hleg else 100.0

        subtopic_percentage = 0.0
        if expected_subtopics:
            covered_expected = covered_subtopics.intersection(expected_subtopics)
            subtopic_percentage = (len(covered_expected) / len(expected_subtopics)) * 100

        return {
            "covered": covered_hleg,
            "missing": missing_hleg,
            "percentage": percentage,
            "subtopics": covered_subtopics,
            "subtopic_percentage": subtopic_percentage,
        }

    async def _check_conflicts(
        self,
        requirements: list[GeneratedRequirement]
    ) -> list[ConflictDetail]:
        """Use LLM to check for conflicts between requirements."""

        if len(requirements) < 2:
            return []

        # Build requirements summary for LLM
        req_summaries = []
        for req in requirements:
            req_summaries.append({
                "id": req.id,
                "title": req.title,
                "statement": req.statement[:200],
                "category": req.category.value if req.category else "general",
            })

        user_message = f"""Check these requirements for conflicts:

{json.dumps(req_summaries, indent=2)}

Identify any contradictions, redundancies, overlaps, or missing dependencies.
Return your response as JSON with a "conflicts" array. Return empty array if no conflicts found."""

        response = await self._client.chat.completions.create(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=2048,
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

        conflicts = []
        for c in data.get("conflicts", []):
            try:
                conflicts.append(ConflictDetail(
                    requirement_id_1=c.get("requirement_id_1", ""),
                    requirement_id_2=c.get("requirement_id_2", ""),
                    conflict_type=c.get("conflict_type", "overlap"),
                    explanation=c.get("explanation", ""),
                    suggested_resolution=c.get("suggested_resolution"),
                ))
            except Exception:
                continue

        return conflicts

    def _validate_citations(
        self,
        requirements: list[GeneratedRequirement]
    ) -> list[InvalidCitationDetail]:
        """Validate that all citations are properly formed."""

        invalid = []

        valid_hleg_ids = {
            "human_agency_and_oversight",
            "technical_robustness_and_safety",
            "privacy_and_data_governance",
            "transparency",
            "diversity_non_discrimination_and_fairness",
            "societal_and_environmental_wellbeing",
            "accountability",
        }

        for req in requirements:
            # Check EU AI Act citations
            for i, cit in enumerate(req.eu_ai_act_citations):
                # Handle Citation objects
                if hasattr(cit, 'article'):
                    if not cit.article:
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"EU citation {i+1}",
                            citation_type="eu_ai_act",
                            reason="Missing article number",
                        ))
                    if not cit.quoted_text:
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"Article {cit.article or '?'}",
                            citation_type="eu_ai_act",
                            reason="Missing quoted text",
                        ))
                # Handle dicts (legacy)
                elif isinstance(cit, dict):
                    if not cit.get("article"):
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"EU citation {i+1}",
                            citation_type="eu_ai_act",
                            reason="Missing article number",
                        ))
                    if not cit.get("quoted_text"):
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"Article {cit.get('article', '?')}",
                            citation_type="eu_ai_act",
                            reason="Missing quoted text",
                        ))

            # Check HLEG citations
            for i, cit in enumerate(req.hleg_citations):
                # Handle Citation objects
                if hasattr(cit, 'requirement_id'):
                    rid = cit.requirement_id
                    if rid and rid not in valid_hleg_ids:
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"HLEG: {rid}",
                            citation_type="hleg",
                            reason=f"Invalid HLEG requirement ID: {rid}",
                        ))
                # Handle dicts (legacy)
                elif isinstance(cit, dict):
                    rid = cit.get("requirement_id")
                    if rid and rid not in valid_hleg_ids:
                        invalid.append(InvalidCitationDetail(
                            requirement_id=req.id,
                            citation_reference=f"HLEG: {rid}",
                            citation_type="hleg",
                            reason=f"Invalid HLEG requirement ID: {rid}",
                        ))

        return invalid

    def _build_recommendations(
        self,
        article_coverage: dict,
        hleg_coverage: dict,
        conflicts: list[ConflictDetail],
        invalid_citations: list[InvalidCitationDetail]
    ) -> list[str]:
        """Build recommendations based on validation results."""

        recommendations = []

        # Article coverage recommendations
        if article_coverage["percentage"] < 80:
            missing = article_coverage["missing"]
            if missing:
                recommendations.append(
                    f"Add requirements for missing articles: {sorted(missing)}"
                )

        # HLEG coverage recommendations
        if hleg_coverage["percentage"] < 70:
            missing = hleg_coverage["missing"]
            if missing:
                missing_names = [p.replace("_", " ").title() for p in sorted(missing)]
                recommendations.append(
                    f"Add requirements addressing HLEG principles: {missing_names}"
                )

        # Conflict recommendations
        if conflicts:
            recommendations.append(
                f"Resolve {len(conflicts)} identified conflicts between requirements"
            )

        # Citation recommendations
        if invalid_citations:
            recommendations.append(
                f"Fix {len(invalid_citations)} invalid citations"
            )

        # General recommendations
        if not recommendations:
            recommendations.append("Requirements set meets coverage thresholds")

        return recommendations

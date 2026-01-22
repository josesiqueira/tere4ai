"""
TERE4AI Pipeline Orchestrator

This module orchestrates the sequential execution of all four RE agents:
  1. Elicitation - Extract SystemDescription from user input
  2. Analysis - Classify risk level
  3. Specification - Generate requirements (if not prohibited)
  4. Validation - Validate completeness and consistency

The orchestrator produces a final RequirementsReport with all results.

PIPELINE FLOW:
  User Input → Elicitation → Analysis → [Specification → Validation] → Report

If the system is classified as UNACCEPTABLE (prohibited), the pipeline
stops after Analysis and returns a report with no requirements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from uuid import uuid4

from agents.base import AgentConfig, AgentTrace, MCPToolClient
from agents.elicitation import ElicitationAgent, ElicitationInput
from agents.analysis import AnalysisAgent
from agents.specification import SpecificationAgent, SpecificationInput
from agents.validation import ValidationAgent, ValidationInput
from shared.models import (
    CoverageMatrix,
    ReportMetrics,
    RequirementsReport,
    RiskLevel,
    SystemDescription,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of the full RE pipeline execution."""

    report: RequirementsReport
    traces: list[AgentTrace] = field(default_factory=list)
    total_duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


class Orchestrator:
    """
    TERE4AI Pipeline Orchestrator.

    Runs the full Requirements Engineering pipeline:
      Elicitation → Analysis → Specification → Validation → Report

    Usage:
        orchestrator = Orchestrator()
        result = await orchestrator.run("My AI system description...")
        print(result.report.to_summary())
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        mcp_client: Optional[MCPToolClient] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Shared configuration for all agents
            mcp_client: Shared MCP client for all agents
        """
        self.config = config or AgentConfig.from_env()
        self.mcp = mcp_client or MCPToolClient()

        # Initialize all agents with shared config and MCP client
        self.elicitation_agent = ElicitationAgent(self.config, self.mcp)
        self.analysis_agent = AnalysisAgent(self.config, self.mcp)
        self.specification_agent = SpecificationAgent(self.config, self.mcp)
        self.validation_agent = ValidationAgent(self.config, self.mcp)

        self.logger = logging.getLogger("tere4ai.orchestrator")

    async def run(
        self,
        raw_description: str,
        additional_context: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> PipelineResult:
        """
        Run the full RE pipeline.

        Args:
            raw_description: Natural language description of the AI system
            additional_context: Optional additional context
            progress_callback: Optional callback(phase, message) called at each phase transition.
                               Phase is one of: "elicitation", "analysis", "specification", "validation", "complete"

        Returns:
            PipelineResult with report and execution traces
        """
        start_time = datetime.now()
        traces: list[AgentTrace] = []
        processing_phases: list[str] = []
        processing_errors: list[str] = []
        processing_warnings: list[str] = []

        async def notify_progress(phase: str, message: str = ""):
            """Notify progress callback if provided."""
            if progress_callback:
                try:
                    result = progress_callback(phase, message)
                    # Handle both sync and async callbacks
                    if hasattr(result, '__await__'):
                        await result
                except Exception as e:
                    self.logger.warning(f"Progress callback error: {e}")

        self.logger.info("Starting TERE4AI pipeline")

        try:
            # Phase 1: Elicitation
            self.logger.info("Phase 1: Elicitation")
            processing_phases.append("elicitation")
            await notify_progress("elicitation", "Extracting system characteristics...")

            elicitation_input = ElicitationInput(
                raw_description=raw_description,
                additional_context=additional_context
            )
            system_description = await self.elicitation_agent.run(elicitation_input)

            if trace := self.elicitation_agent.get_last_trace():
                traces.append(trace)

            self.logger.info(f"Extracted system description: domain={system_description.domain}")

            # Phase 2: Analysis
            self.logger.info("Phase 2: Analysis")
            processing_phases.append("analysis")
            await notify_progress("analysis", "Classifying risk level...")

            risk_classification = await self.analysis_agent.run(system_description)

            if trace := self.analysis_agent.get_last_trace():
                traces.append(trace)

            self.logger.info(f"Risk classification: {risk_classification.level.value}")

            # Check if system is prohibited
            if risk_classification.level == RiskLevel.UNACCEPTABLE:
                self.logger.warning("System is prohibited - skipping specification and validation")
                processing_warnings.append(
                    f"System is prohibited under {risk_classification.legal_basis.primary.format_reference()}"
                )
                await notify_progress("complete", "System classified as prohibited")

                report = self._build_prohibited_report(
                    system_description,
                    risk_classification,
                    processing_phases,
                    processing_errors,
                    processing_warnings
                )

                end_time = datetime.now()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                return PipelineResult(
                    report=report,
                    traces=traces,
                    total_duration_ms=duration_ms,
                    success=True,
                )

            # Phase 3: Specification
            self.logger.info("Phase 3: Specification")
            processing_phases.append("specification")
            await notify_progress("specification", "Generating requirements...")

            spec_input = SpecificationInput(
                system_description=system_description,
                risk_classification=risk_classification
            )
            spec_output = await self.specification_agent.run(spec_input)

            if trace := self.specification_agent.get_last_trace():
                traces.append(trace)

            self.logger.info(f"Generated {len(spec_output.requirements)} requirements")

            if not spec_output.requirements:
                processing_warnings.append("No requirements generated for this risk level")

            # Phase 4: Validation
            self.logger.info("Phase 4: Validation")
            processing_phases.append("validation")
            await notify_progress("validation", "Validating completeness...")

            validation_input = ValidationInput(
                requirements=spec_output.requirements,
                risk_classification=risk_classification,
                applicable_articles=spec_output.articles_processed
            )
            validation_result = await self.validation_agent.run(validation_input)

            if trace := self.validation_agent.get_last_trace():
                traces.append(trace)

            self.logger.info(
                f"Validation: article_coverage={validation_result.article_coverage:.1f}%, "
                f"hleg_coverage={validation_result.hleg_coverage:.1f}%"
            )

            # Add validation warnings
            if not validation_result.is_complete:
                processing_warnings.append(
                    f"Article coverage ({validation_result.article_coverage * 100:.1f}%) below 80% threshold"
                )
            if validation_result.has_conflicts:
                processing_warnings.append(
                    f"{len(validation_result.conflicts)} conflicts detected between requirements"
                )

            # Notify completion before building report
            await notify_progress("complete", "Finalizing report...")

            # Build final report
            report = self._build_report(
                system_description,
                risk_classification,
                spec_output.requirements,
                validation_result,
                processing_phases,
                processing_errors,
                processing_warnings
            )

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            self.logger.info(f"Pipeline completed in {duration_ms:.1f}ms")

            return PipelineResult(
                report=report,
                traces=traces,
                total_duration_ms=duration_ms,
                success=True,
            )

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            processing_errors.append(str(e))

            end_time = datetime.now()
            duration_ms = (end_time - start_time).total_seconds() * 1000

            # Build error report
            report = RequirementsReport(
                generated_at=datetime.now(),
                tere4ai_version="0.1.0",
                report_id=str(uuid4()),
                system_description=None,
                risk_classification=None,
                requirements=[],
                validation=None,
                coverage_matrix=CoverageMatrix(),
                metrics=ReportMetrics(),
                processing_phases=processing_phases,
                processing_errors=processing_errors,
                processing_warnings=processing_warnings,
            )

            return PipelineResult(
                report=report,
                traces=traces,
                total_duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

    def _build_prohibited_report(
        self,
        system_description: SystemDescription,
        risk_classification,
        processing_phases: list[str],
        processing_errors: list[str],
        processing_warnings: list[str]
    ) -> RequirementsReport:
        """Build report for prohibited systems."""

        return RequirementsReport(
            generated_at=datetime.now(),
            tere4ai_version="0.1.0",
            report_id=str(uuid4()),
            system_description=system_description,
            risk_classification=risk_classification,
            requirements=[],
            validation=None,
            coverage_matrix=CoverageMatrix(),
            metrics=ReportMetrics(),
            processing_phases=processing_phases,
            processing_errors=processing_errors,
            processing_warnings=processing_warnings,
        )

    def _build_report(
        self,
        system_description: SystemDescription,
        risk_classification,
        requirements: list,
        validation_result,
        processing_phases: list[str],
        processing_errors: list[str],
        processing_warnings: list[str]
    ) -> RequirementsReport:
        """Build final report with all results."""

        # Build coverage matrix
        coverage_matrix = self._build_coverage_matrix(requirements)

        # Compute metrics
        metrics = self._compute_metrics(requirements, validation_result)

        return RequirementsReport(
            generated_at=datetime.now(),
            tere4ai_version="0.1.0",
            report_id=str(uuid4()),
            system_description=system_description,
            risk_classification=risk_classification,
            requirements=requirements,
            validation=validation_result,
            coverage_matrix=coverage_matrix,
            metrics=metrics,
            processing_phases=processing_phases,
            processing_errors=processing_errors,
            processing_warnings=processing_warnings,
        )

    def _build_coverage_matrix(self, requirements: list) -> CoverageMatrix:
        """Build coverage matrix from requirements."""

        hleg_to_reqs: dict[str, list[str]] = {}
        subtopic_to_reqs: dict[str, list[str]] = {}
        article_to_reqs: dict[str, list[str]] = {}
        req_to_articles: dict[str, list[str]] = {}
        req_to_hleg: dict[str, list[str]] = {}

        for req in requirements:
            req_id = req.id

            # Article mappings
            articles = []
            for art in req.derived_from_articles:
                art_str = str(art)
                articles.append(art_str)
                if art_str not in article_to_reqs:
                    article_to_reqs[art_str] = []
                article_to_reqs[art_str].append(req_id)

            req_to_articles[req_id] = articles

            # HLEG mappings
            hleg_ids = []
            for pid in req.addresses_hleg_principles:
                hleg_ids.append(pid)
                if pid not in hleg_to_reqs:
                    hleg_to_reqs[pid] = []
                hleg_to_reqs[pid].append(req_id)

            req_to_hleg[req_id] = hleg_ids

            # Subtopic mappings
            for st in req.addresses_hleg_subtopics:
                if st:
                    if st not in subtopic_to_reqs:
                        subtopic_to_reqs[st] = []
                    subtopic_to_reqs[st].append(req_id)

        return CoverageMatrix(
            hleg_to_requirements=hleg_to_reqs,
            subtopic_to_requirements=subtopic_to_reqs,
            article_to_requirements=article_to_reqs,
            requirement_to_articles=req_to_articles,
            requirement_to_hleg=req_to_hleg,
        )

    def _compute_metrics(self, requirements: list, validation_result) -> ReportMetrics:
        """Compute metrics from requirements."""

        total_eu_citations = 0
        total_hleg_citations = 0
        total_recital_citations = 0
        unique_articles = set()
        unique_paragraphs = set()
        unique_hleg = set()
        unique_subtopics = set()
        critical_count = 0
        high_count = 0

        for req in requirements:
            # Count EU citations
            for cit in req.eu_ai_act_citations:
                total_eu_citations += 1
                # Handle Citation objects
                if hasattr(cit, 'article'):
                    if cit.article:
                        unique_articles.add(str(cit.article))
                    if cit.article and cit.paragraph:
                        unique_paragraphs.add(f"{cit.article}({cit.paragraph})")
                elif isinstance(cit, dict):
                    art = cit.get("article")
                    if art:
                        unique_articles.add(str(art))
                    para = cit.get("paragraph")
                    if art and para:
                        unique_paragraphs.add(f"{art}({para})")

            # Count HLEG citations
            for cit in req.hleg_citations:
                total_hleg_citations += 1
                # Handle Citation objects
                if hasattr(cit, 'requirement_id'):
                    if cit.requirement_id:
                        unique_hleg.add(cit.requirement_id)
                    if hasattr(cit, 'subtopic_id') and cit.subtopic_id:
                        unique_subtopics.add(cit.subtopic_id)
                elif isinstance(cit, dict):
                    rid = cit.get("requirement_id")
                    if rid:
                        unique_hleg.add(rid)
                    sid = cit.get("subtopic_id")
                    if sid:
                        unique_subtopics.add(sid)

            # Count recitals
            total_recital_citations += len(req.supporting_recitals)

            # Count priorities
            if req.priority:
                if req.priority.value == "critical":
                    critical_count += 1
                elif req.priority.value == "high":
                    high_count += 1

        # Calculate coverage percentages (ValidationResult uses 0-1, ReportMetrics uses 0-100)
        article_coverage = (validation_result.article_coverage * 100.0) if validation_result else 0.0
        hleg_coverage = (validation_result.hleg_coverage * 100.0) if validation_result else 0.0

        return ReportMetrics(
            total_citations=total_eu_citations + total_hleg_citations + total_recital_citations,
            eu_ai_act_citations=total_eu_citations,
            hleg_citations=total_hleg_citations,
            recital_citations=total_recital_citations,
            unique_articles_cited=len(unique_articles),
            unique_paragraphs_cited=len(unique_paragraphs),
            unique_recitals_cited=0,  # Not tracked separately
            unique_hleg_principles_addressed=len(unique_hleg),
            unique_hleg_subtopics_addressed=len(unique_subtopics),
            article_coverage_percentage=article_coverage,
            hleg_coverage_percentage=hleg_coverage,
            total_requirements=len(requirements),
            critical_requirements=critical_count,
            high_requirements=high_count,
        )

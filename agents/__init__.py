"""
TERE4AI Requirements Engineering Agents

This package contains the four RE phase agents and the pipeline orchestrator:

  1. ElicitationAgent - Extract SystemDescription from user input
  2. AnalysisAgent - Classify risk level using EU AI Act
  3. SpecificationAgent - Generate requirements with citations
  4. ValidationAgent - Validate completeness and consistency

The Orchestrator runs the full pipeline:
  Elicitation → Analysis → Specification → Validation → Report

Usage:
    from tere4ai.agents import Orchestrator

    orchestrator = Orchestrator()
    result = await orchestrator.run("My AI system description...")
    print(result.report.to_summary())
"""

from .base import AgentConfig, AgentTrace, BaseAgent, MCPToolClient
from .elicitation import ElicitationAgent, ElicitationInput
from .analysis import AnalysisAgent
from .specification import SpecificationAgent, SpecificationInput, SpecificationOutput
from .validation import ValidationAgent, ValidationInput
from .orchestrator import Orchestrator, PipelineResult

__all__ = [
    # Base
    "AgentConfig",
    "AgentTrace",
    "BaseAgent",
    "MCPToolClient",
    # Elicitation
    "ElicitationAgent",
    "ElicitationInput",
    # Analysis
    "AnalysisAgent",
    # Specification
    "SpecificationAgent",
    "SpecificationInput",
    "SpecificationOutput",
    # Validation
    "ValidationAgent",
    "ValidationInput",
    # Orchestrator
    "Orchestrator",
    "PipelineResult",
]

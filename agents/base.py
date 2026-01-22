"""
TERE4AI Base Agent Class

This module defines the base agent architecture for TERE4AI's Requirements
Engineering agents. All four RE phase agents inherit from this base.

ARCHITECTURE:
  - Agents are powered by PydanticAI for structured output
  - Each agent has access to MCP tools for knowledge graph queries
  - Agents produce Pydantic models as outputs for type safety
  - Logging and tracing support for academic analysis

RE PHASES:
  1. Elicitation Agent - Extract SystemDescription from user input
  2. Analysis Agent - Classify risk level using MCP tools
  3. Specification Agent - Generate requirements with citations
  4. Validation Agent - Check completeness and consistency
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Type variables for agent input/output
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class AgentConfig:
    """Configuration for RE agents."""

    # LLM settings
    model: str = "gpt-4o"
    temperature: float = 0.1  # Low temperature for deterministic outputs
    max_tokens: int = 4096

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    # Logging
    log_level: str = "INFO"
    trace_enabled: bool = True

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Load configuration from environment variables."""
        return cls(
            model=os.getenv("TERE4AI_MODEL", "gpt-4o"),
            temperature=float(os.getenv("TERE4AI_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("TERE4AI_MAX_TOKENS", "4096")),
            max_retries=int(os.getenv("TERE4AI_MAX_RETRIES", "3")),
            log_level=os.getenv("TERE4AI_LOG_LEVEL", "INFO"),
            trace_enabled=os.getenv("TERE4AI_TRACE_ENABLED", "true").lower() == "true",
        )


@dataclass
class AgentTrace:
    """Trace record for academic analysis."""

    agent_name: str
    phase: str  # RE phase: elicitation, analysis, specification, validation
    started_at: datetime
    completed_at: Optional[datetime] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    mcp_calls: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def duration_ms(self) -> Optional[float]:
        """Get duration in milliseconds."""
        if self.completed_at is None:
            return None
        delta = self.completed_at - self.started_at
        return delta.total_seconds() * 1000


class MCPToolClient:
    """
    Client for calling MCP tools.

    This wraps the MCP server tools to provide a clean interface for agents.
    Tools can be called either via MCP protocol or directly as functions.
    """

    def __init__(self, use_direct_calls: bool = True):
        """
        Initialize MCP tool client.

        Args:
            use_direct_calls: If True, call tool functions directly.
                             If False, use MCP protocol (future).
        """
        self.use_direct_calls = use_direct_calls
        self._call_log: list[dict[str, Any]] = []

    def get_call_log(self) -> list[dict[str, Any]]:
        """Get log of all tool calls for tracing."""
        return self._call_log.copy()

    def clear_call_log(self) -> None:
        """Clear the call log."""
        self._call_log = []

    def classify_risk_level(self, system_features: dict[str, Any]) -> dict[str, Any]:
        """
        Classify risk level from system features.

        Args:
            system_features: Dictionary of system characteristics

        Returns:
            Risk classification result with level, legal basis, and reasoning
        """
        from mcp_server.server import classify_risk_level_impl

        self._call_log.append({
            "tool": "classify_risk_level",
            "timestamp": datetime.now().isoformat(),
            "input": {"system_features": system_features},
        })

        result = classify_risk_level_impl(system_features)

        self._call_log[-1]["output"] = result
        return result

    def get_applicable_articles(
        self,
        risk_level: str,
        annex_category: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """
        Get applicable EU AI Act articles for a risk level.

        Args:
            risk_level: Risk level string
            annex_category: Optional Annex III category

        Returns:
            List of article dictionaries
        """
        from mcp_server.server import get_applicable_articles_impl

        self._call_log.append({
            "tool": "get_applicable_articles",
            "timestamp": datetime.now().isoformat(),
            "input": {"risk_level": risk_level, "annex_category": annex_category},
        })

        result = get_applicable_articles_impl(risk_level, annex_category)

        self._call_log[-1]["output"] = {"count": len(result)}
        return result

    def get_article_with_citations(self, article_number: int) -> dict[str, Any]:
        """
        Get complete article with HLEG mappings and recitals.

        Args:
            article_number: The article number to fetch

        Returns:
            Article bundle with paragraphs, HLEG mappings, recitals
        """
        from mcp_server.server import get_article_with_citations_impl

        self._call_log.append({
            "tool": "get_article_with_citations",
            "timestamp": datetime.now().isoformat(),
            "input": {"article_number": article_number},
        })

        result = get_article_with_citations_impl(article_number)

        self._call_log[-1]["output"] = {
            "article": result.get("number"),
            "paragraphs": len(result.get("paragraphs", [])),
            "hleg_mappings": len(result.get("hleg_mappings", [])),
        }
        return result

    def get_hleg_coverage(self, articles: list[int]) -> dict[str, Any]:
        """
        Get HLEG coverage matrix for articles.

        Args:
            articles: List of article numbers

        Returns:
            Coverage matrix with principles, percentage, uncovered
        """
        from mcp_server.server import get_hleg_coverage_impl

        self._call_log.append({
            "tool": "get_hleg_coverage",
            "timestamp": datetime.now().isoformat(),
            "input": {"articles": articles},
        })

        result = get_hleg_coverage_impl(articles)

        self._call_log[-1]["output"] = {
            "coverage_percentage": result.get("coverage_percentage"),
            "uncovered_count": len(result.get("uncovered_principles", [])),
        }
        return result

    def search_legal_text(
        self,
        query: str,
        filters: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Search across EU AI Act and HLEG.

        Args:
            query: Search query string
            filters: Optional search filters

        Returns:
            Search results with matches
        """
        from mcp_server.server import search_legal_text_impl

        self._call_log.append({
            "tool": "search_legal_text",
            "timestamp": datetime.now().isoformat(),
            "input": {"query": query, "filters": filters},
        })

        result = search_legal_text_impl(query, filters)

        self._call_log[-1]["output"] = {"total_matches": result.get("total_matches", 0)}
        return result


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Base class for TERE4AI Requirements Engineering agents.

    Each RE phase agent inherits from this base and implements:
      - `name`: Agent identifier
      - `phase`: RE phase (elicitation, analysis, specification, validation)
      - `run()`: Main execution method
      - `_get_system_prompt()`: LLM system prompt for this agent

    The base class provides:
      - MCP tool access via `self.mcp`
      - Logging and tracing via `self.trace`
      - Configuration via `self.config`
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        mcp_client: Optional[MCPToolClient] = None,
    ):
        """
        Initialize the agent.

        Args:
            config: Agent configuration (uses defaults if not provided)
            mcp_client: MCP tool client (creates new if not provided)
        """
        self.config = config or AgentConfig.from_env()
        self.mcp = mcp_client or MCPToolClient()
        self._current_trace: Optional[AgentTrace] = None

        # Configure logging for this agent
        self.logger = logging.getLogger(f"tere4ai.agents.{self.name}")
        self.logger.setLevel(getattr(logging, self.config.log_level))

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier (e.g., 'elicitation', 'analysis')."""
        pass

    @property
    @abstractmethod
    def phase(self) -> str:
        """RE phase this agent implements."""
        pass

    @abstractmethod
    async def run(self, input_data: InputT) -> OutputT:
        """
        Execute the agent's main function.

        Args:
            input_data: Input data for this agent

        Returns:
            Output model for this agent
        """
        pass

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Get the system prompt for this agent's LLM calls."""
        pass

    def _start_trace(self, input_summary: Optional[str] = None) -> AgentTrace:
        """Start a new trace for this agent execution."""
        self._current_trace = AgentTrace(
            agent_name=self.name,
            phase=self.phase,
            started_at=datetime.now(),
            input_summary=input_summary,
        )
        self.mcp.clear_call_log()
        self.logger.debug(f"Started trace for {self.name} agent")
        return self._current_trace

    def _complete_trace(
        self,
        output_summary: Optional[str] = None,
        error: Optional[str] = None
    ) -> AgentTrace:
        """Complete the current trace."""
        if self._current_trace is None:
            raise RuntimeError("No active trace to complete")

        self._current_trace.completed_at = datetime.now()
        self._current_trace.output_summary = output_summary
        self._current_trace.mcp_calls = self.mcp.get_call_log()
        self._current_trace.error = error

        duration = self._current_trace.duration_ms()
        self.logger.info(
            f"Completed {self.name} agent in {duration:.1f}ms "
            f"(MCP calls: {len(self._current_trace.mcp_calls)})"
        )

        return self._current_trace

    def get_last_trace(self) -> Optional[AgentTrace]:
        """Get the last execution trace."""
        return self._current_trace

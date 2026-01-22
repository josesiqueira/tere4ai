"""
TERE4AI MCP Server

This package provides the Model Context Protocol server that bridges
RE agents with the Neo4j knowledge graph.

The MCP server provides 5 semantic tools:
  1. classify_risk_level - Determine risk level from system features
  2. get_applicable_articles - Get articles for a risk level
  3. get_article_with_citations - Get full article with HLEG mappings
  4. get_hleg_coverage - Get HLEG coverage matrix
  5. search_legal_text - Semantic search across legal text

Usage:
    # Run as MCP server
    python -m tere4ai.mcp_server.server

    # Or import for programmatic use
    from tere4ai.mcp_server import (
        classify_risk_level,
        get_applicable_articles,
        get_article_with_citations,
        get_hleg_coverage,
        search_legal_text,
    )
"""

from .server import (
    classify_risk_level,
    get_applicable_articles,
    get_article_with_citations,
    get_hleg_coverage,
    mcp,
    search_legal_text,
)

__all__ = [
    "mcp",
    "classify_risk_level",
    "get_applicable_articles",
    "get_article_with_citations",
    "get_hleg_coverage",
    "search_legal_text",
]

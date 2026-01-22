"""
Neo4j Connection Configuration

This is the SINGLE source of truth for Neo4j connection settings.

All other modules must import from here instead of creating their own drivers.
This centralization makes it easy to:
  - Switch to environment variables for credentials
  - Update connection settings in one place
  - Ensure consistent connection handling across the project

Usage:
    from config.neo4j_config import get_neo4j_driver, execute_query

    # Option 1: Get a driver and manage it yourself
    with get_neo4j_driver() as driver:
        result = driver.execute_query("MATCH (n) RETURN count(n)")

    # Option 2: Use the helper (for simple queries)
    records = execute_query("MATCH (n:Document) RETURN n LIMIT 10")
"""

import os
from typing import Any, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# Connection Settings (from environment variables with defaults)
# ============================================================================

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# IMPORTANT: In production, these should ALWAYS come from environment variables.
# Never commit real credentials to version control!


# ============================================================================
# Driver Creation
# ============================================================================

def get_neo4j_driver() -> Driver:
    """
    Create and return a Neo4j driver instance.

    This is the only function that should create Neo4j drivers in this project.
    All other modules should call this function instead of creating drivers directly.

    Returns:
        Neo4j Driver instance connected to the configured database

    Example:
        >>> with get_neo4j_driver() as driver:
        ...     result = driver.execute_query("MATCH (n) RETURN count(n)")
        ...     print(result.records[0][0])
    """
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )


# ============================================================================
# Query Execution Helper
# ============================================================================

def execute_query(cypher: str, **params: Any) -> list:
    """
    Execute a Cypher query and return the records.

    This is a convenience helper for simple queries that don't need
    custom driver management. For more complex use cases (transactions,
    multiple queries, etc.), use get_neo4j_driver() directly.

    Args:
        cypher: The Cypher query string
        **params: Query parameters (passed to driver.execute_query)

    Returns:
        List of records from the query result

    Example:
        >>> records = execute_query(
        ...     "MATCH (r:Regulation {document_id: $doc_id}) RETURN r",
        ...     doc_id="eu_ai_act_2024"
        ... )
        >>> print(records[0]["r"])
    """
    with get_neo4j_driver() as driver:
        result = driver.execute_query(cypher, **params)
        return result.records


# ============================================================================
# Connection Verification (for debugging)
# ============================================================================

def verify_connection() -> bool:
    """
    Verify that we can connect to Neo4j.

    Returns:
        True if connection successful, False otherwise

    Example:
        >>> if verify_connection():
        ...     print("✓ Neo4j connection successful")
    """
    try:
        with get_neo4j_driver() as driver:
            driver.verify_connectivity()
        return True
    except Exception as e:
        print(f"❌ Neo4j connection failed: {e}")
        return False

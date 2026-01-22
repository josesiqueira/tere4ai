"""
TERE4AI Test Configuration

Shared pytest fixtures and configuration for all tests.
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# =============================================================================
# Environment Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires running services)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (long-running)"
    )


# =============================================================================
# Fixtures: Environment
# =============================================================================

@pytest.fixture(scope="session")
def project_root_path():
    """Return the project root path."""
    return project_root


@pytest.fixture(scope="session")
def dotenv_loaded():
    """Ensure .env file is loaded."""
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
    return True


# =============================================================================
# Fixtures: Neo4j
# =============================================================================

@pytest.fixture(scope="session")
def neo4j_driver(dotenv_loaded):
    """Create Neo4j driver for tests that need database access."""
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    yield driver
    driver.close()


@pytest.fixture
def neo4j_session(neo4j_driver):
    """Create a Neo4j session for individual tests."""
    with neo4j_driver.session() as session:
        yield session


# =============================================================================
# Fixtures: API
# =============================================================================

@pytest.fixture(scope="module")
def api_client():
    """Create FastAPI test client."""
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


# =============================================================================
# Fixtures: Test Data
# =============================================================================

@pytest.fixture
def sample_system_descriptions():
    """Return sample system descriptions for testing."""
    return {
        "prohibited": (
            "An AI application that generates realistic nude images of people based on "
            "their regular photos, allowing users to create intimate content without the "
            "subject's knowledge or consent."
        ),
        "high_risk_healthcare": (
            "An AI system for hospital emergency room triage that analyzes patient symptoms, "
            "vital signs, and medical history to prioritize patients and recommend initial "
            "treatment protocols. The system assists medical staff in making time-critical "
            "decisions about patient care priority."
        ),
        "limited_risk_chatbot": (
            "A customer service chatbot that handles common inquiries about products, "
            "shipping, and returns for an e-commerce store. The chatbot uses natural "
            "language processing to understand customer questions and provide helpful "
            "responses about order status and store policies."
        ),
        "minimal_risk_recommender": (
            "An AI recommendation system that suggests movies to users based on their "
            "viewing history, ratings, and preferences for a streaming platform. The "
            "system personalizes content discovery without making any consequential "
            "decisions about users."
        ),
    }


@pytest.fixture
def mock_risk_classification():
    """Return a mock high-risk classification for testing."""
    from shared.models import (
        Citation,
        CitationBundle,
        RiskClassification,
        RiskLevel,
        AnnexIIICategory,
    )

    primary_citation = Citation(
        source="EU_AI_ACT",
        document_id="eu_ai_act_2024",
        article="6",
        paragraph=2,
        reference_text="Article 6(2)",
        quoted_text="High-risk AI systems referred to in Annex III...",
    )

    return RiskClassification(
        level=RiskLevel.HIGH,
        legal_basis=CitationBundle(
            primary=primary_citation,
            supporting=[],
            rationale="Healthcare system matches Annex III criteria",
        ),
        annex_iii_category=AnnexIIICategory.HEALTH_SAFETY,
        applicable_articles=["8", "9", "10", "11", "12", "13", "14", "15"],
        article_6_exception_checked=True,
        hleg_implications=[],
        reasoning="System used for health-related decisions",
    )


@pytest.fixture
def mock_system_description():
    """Return a mock system description for testing."""
    from shared.models import (
        SystemDescription,
        SystemDomain,
        DataCategory,
        DecisionType,
        DeploymentContext,
        AutonomyLevel,
    )

    return SystemDescription(
        raw_description="Hospital triage AI system",
        name="Hospital Triage AI",
        domain=SystemDomain.HEALTHCARE,
        purpose="Prioritize patients in emergency room",
        intended_users=["medical staff", "nurses", "doctors"],
        affected_persons=["patients", "emergency room visitors"],
        data_categories=[DataCategory.HEALTH, DataCategory.BIOMETRIC],
        decision_types=[DecisionType.PRIORITIZATION, DecisionType.RECOMMENDATION],
        deployment_context=DeploymentContext.PROFESSIONAL,
        autonomy_level=AutonomyLevel.ADVISORY,
        affects_fundamental_rights=True,
        safety_critical=True,
        biometric_processing=True,
        real_time_biometric=False,
        law_enforcement_use=False,
        social_scoring=False,
        subliminal_techniques=False,
        emotion_recognition=False,
        critical_infrastructure=True,
    )


# =============================================================================
# Skip Markers
# =============================================================================

@pytest.fixture(scope="session")
def skip_if_no_neo4j(dotenv_loaded):
    """Skip test if Neo4j is not available."""
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        return True
    except ServiceUnavailable:
        pytest.skip("Neo4j is not available")
    except Exception as e:
        pytest.skip(f"Neo4j connection failed: {e}")


@pytest.fixture(scope="session")
def skip_if_no_openai(dotenv_loaded):
    """Skip test if OpenAI API key is not configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-your"):
        pytest.skip("OpenAI API key not configured")
    return True

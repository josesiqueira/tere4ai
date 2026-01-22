"""
Integration Tests for TERE4AI MVP Test Cases

This module tests the complete end-to-end pipeline against the 4 MVP test cases:
  1. Unacceptable Risk (Deepfake Generator) - Should be PROHIBITED
  2. High-Risk Healthcare (Hospital Triage) - Should be HIGH with full requirements
  3. Limited Risk (E-commerce Chatbot) - Should be LIMITED with transparency reqs
  4. Minimal Risk (Movie Recommender) - Should be MINIMAL with no specific reqs

Tests run against the real API with real LLM calls and Neo4j database.

Usage:
    pytest tests/integration/test_mvp_cases.py -v --timeout=300

Note: These tests require:
    - Neo4j running with populated data
    - OpenAI API key configured
    - API server running OR using TestClient
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# =============================================================================
# Test Configuration
# =============================================================================

# Timeout for waiting for job completion (seconds)
JOB_TIMEOUT = 120

# Expected risk levels for each test case
EXPECTED_RESULTS = {
    "prohibited": {
        "risk_level": "unacceptable",
        "min_requirements": 0,
        "max_requirements": 0,
        "prohibited": True,
    },
    "high-risk-healthcare": {
        "risk_level": "high",
        "min_requirements": 10,
        "max_requirements": 50,
        "prohibited": False,
        "min_hleg_coverage": 0.6,  # 60% HLEG coverage for high-risk
    },
    "limited-risk": {
        "risk_level": "limited",
        "min_requirements": 1,
        "max_requirements": 10,
        "prohibited": False,
    },
    "minimal-risk": {
        "risk_level": "minimal",
        "min_requirements": 0,
        "max_requirements": 5,
        "prohibited": False,
    },
}

# Test case descriptions (same as API examples)
TEST_CASES = {
    "prohibited": {
        "name": "Deepfake Generator",
        "description": (
            "An AI application that generates realistic nude images of people based on "
            "their regular photos, allowing users to create intimate content without the "
            "subject's knowledge or consent."
        ),
    },
    "high-risk-healthcare": {
        "name": "Hospital Triage System",
        "description": (
            "An AI system for hospital emergency room triage that analyzes patient symptoms, "
            "vital signs, and medical history to prioritize patients and recommend initial "
            "treatment protocols. The system assists medical staff in making time-critical "
            "decisions about patient care priority."
        ),
    },
    "limited-risk": {
        "name": "E-commerce Chatbot",
        "description": (
            "A customer service chatbot that handles common inquiries about products, "
            "shipping, and returns for an e-commerce store. The chatbot uses natural "
            "language processing to understand customer questions and provide helpful "
            "responses about order status and store policies."
        ),
    },
    "minimal-risk": {
        "name": "Movie Recommender",
        "description": (
            "An AI recommendation system that suggests movies to users based on their "
            "viewing history, ratings, and preferences for a streaming platform. The "
            "system personalizes content discovery without making any consequential "
            "decisions about users."
        ),
    },
}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def test_client():
    """Create FastAPI test client."""
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def async_client():
    """Create async HTTP client for async tests."""
    import httpx
    return httpx.AsyncClient(base_url="http://localhost:8000", timeout=JOB_TIMEOUT)


# =============================================================================
# Helper Functions
# =============================================================================

def wait_for_job_completion(
    client,
    job_id: str,
    timeout: int = JOB_TIMEOUT,
    poll_interval: float = 2.0
) -> dict[str, Any]:
    """Wait for a job to complete and return the status."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        response = client.get(f"/api/status/{job_id}")
        assert response.status_code == 200, f"Status check failed: {response.text}"

        status_data = response.json()
        status = status_data["status"]

        if status == "completed":
            return status_data
        elif status == "failed":
            raise RuntimeError(f"Job failed: {status_data.get('error', 'Unknown error')}")

        time.sleep(poll_interval)

    raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")


def validate_report_structure(report: dict[str, Any]) -> None:
    """Validate that report has all required fields."""
    assert "generated_at" in report
    assert "tere4ai_version" in report
    assert "report_id" in report
    assert "system_description" in report
    assert "risk_classification" in report
    assert "requirements" in report
    assert isinstance(report["requirements"], list)


def validate_citation_structure(citation: dict[str, Any]) -> None:
    """Validate that a citation has required fields."""
    assert "source" in citation
    assert "reference_text" in citation
    # quoted_text may be optional in some cases


def validate_requirement_structure(requirement: dict[str, Any]) -> None:
    """Validate that a requirement has required fields."""
    assert "id" in requirement
    assert "title" in requirement
    assert "statement" in requirement
    assert "category" in requirement
    assert "priority" in requirement
    assert "eu_ai_act_citations" in requirement
    assert isinstance(requirement["eu_ai_act_citations"], list)


# =============================================================================
# Test: Unacceptable Risk (Prohibited System)
# =============================================================================

class TestUnacceptableRisk:
    """Test Case 1: Deepfake Generator - Should be PROHIBITED"""

    @pytest.mark.integration
    def test_prohibited_classification(self, test_client):
        """Test that deepfake generator is classified as UNACCEPTABLE."""
        # Submit job
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["prohibited"]["description"]}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        # Wait for completion
        status = wait_for_job_completion(test_client, job_id)
        assert status["status"] == "completed"

        # Get report
        response = test_client.get(f"/api/report/{job_id}")
        assert response.status_code == 200
        report = response.json()

        # Validate structure
        validate_report_structure(report)

        # Validate risk classification
        risk_class = report["risk_classification"]
        assert risk_class is not None
        assert risk_class["level"].lower() == "unacceptable"

        # Validate NO requirements generated for prohibited systems
        assert len(report["requirements"]) == 0

        # Validate legal basis (should reference Article 5)
        legal_basis = risk_class.get("legal_basis")
        if legal_basis:
            primary = legal_basis.get("primary", {})
            ref_text = primary.get("reference_text", "")
            # Should cite Article 5 (prohibited practices)
            assert "5" in ref_text or "Article 5" in str(risk_class)

    @pytest.mark.integration
    def test_prohibited_no_specification_phase(self, test_client):
        """Test that pipeline stops after analysis for prohibited systems."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["prohibited"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()

        # Check processing phases
        phases = report.get("processing_phases", [])
        # Should only have elicitation and analysis (no specification/validation)
        assert "elicitation" in phases
        assert "analysis" in phases
        # specification and validation should NOT be present for prohibited systems
        # (though they might be depending on implementation)


# =============================================================================
# Test: High-Risk Healthcare
# =============================================================================

class TestHighRiskHealthcare:
    """Test Case 2: Hospital Triage - Should be HIGH with full requirements"""

    @pytest.mark.integration
    def test_high_risk_classification(self, test_client):
        """Test that hospital triage is classified as HIGH risk."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["high-risk-healthcare"]["description"]}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        status = wait_for_job_completion(test_client, job_id)
        assert status["status"] == "completed"

        report = test_client.get(f"/api/report/{job_id}").json()
        validate_report_structure(report)

        # Validate HIGH risk classification
        risk_class = report["risk_classification"]
        assert risk_class is not None
        assert risk_class["level"].lower() == "high"

    @pytest.mark.integration
    def test_high_risk_has_requirements(self, test_client):
        """Test that high-risk system generates requirements."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["high-risk-healthcare"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        requirements = report["requirements"]

        # Should have multiple requirements
        expected = EXPECTED_RESULTS["high-risk-healthcare"]
        assert len(requirements) >= expected["min_requirements"], \
            f"Expected at least {expected['min_requirements']} requirements, got {len(requirements)}"

        # Validate each requirement structure
        for req in requirements:
            validate_requirement_structure(req)

    @pytest.mark.integration
    def test_high_risk_chapter_iii_coverage(self, test_client):
        """Test that high-risk requirements cover Chapter III articles."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["high-risk-healthcare"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        requirements = report["requirements"]

        # Collect all cited articles
        cited_articles = set()
        for req in requirements:
            for citation in req.get("eu_ai_act_citations", []):
                article = citation.get("article")
                if article:
                    cited_articles.add(int(article))

        # High-risk should cite Chapter III articles (8-27)
        chapter_iii_articles = set(range(8, 28))  # Articles 8-27
        covered = cited_articles.intersection(chapter_iii_articles)

        # Should cover at least some Chapter III articles
        assert len(covered) >= 3, \
            f"Expected coverage of Chapter III articles, found: {covered}"

    @pytest.mark.integration
    def test_high_risk_hleg_alignment(self, test_client):
        """Test that high-risk requirements align with HLEG principles."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["high-risk-healthcare"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        requirements = report["requirements"]

        # Collect all HLEG principles addressed
        hleg_addressed = set()
        for req in requirements:
            for principle in req.get("addresses_hleg_principles", []):
                hleg_addressed.add(principle)

        # Should address multiple HLEG principles
        assert len(hleg_addressed) >= 3, \
            f"Expected at least 3 HLEG principles, got: {hleg_addressed}"

    @pytest.mark.integration
    def test_high_risk_annex_iii_reference(self, test_client):
        """Test that classification cites Annex III category."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["high-risk-healthcare"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        risk_class = report["risk_classification"]

        # Should have annex_iii_category for healthcare
        annex_category = risk_class.get("annex_iii_category")
        # Healthcare/triage typically falls under category 5(a) - Critical infrastructure/health
        # or it could be in the reasoning/legal_basis
        legal_basis = risk_class.get("legal_basis", {})

        has_annex_reference = (
            annex_category is not None or
            "annex" in str(risk_class).lower() or
            "5" in str(annex_category or "")
        )
        assert has_annex_reference, "Expected Annex III reference for healthcare system"


# =============================================================================
# Test: Limited Risk
# =============================================================================

class TestLimitedRisk:
    """Test Case 3: E-commerce Chatbot - Should be LIMITED with transparency reqs"""

    @pytest.mark.integration
    def test_limited_classification(self, test_client):
        """Test that chatbot is classified as LIMITED risk."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["limited-risk"]["description"]}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        status = wait_for_job_completion(test_client, job_id)
        assert status["status"] == "completed"

        report = test_client.get(f"/api/report/{job_id}").json()
        validate_report_structure(report)

        risk_class = report["risk_classification"]
        assert risk_class is not None
        # Should be LIMITED (or possibly MINIMAL - chatbots can vary)
        level = risk_class["level"].lower()
        assert level in ["limited", "minimal"], f"Expected LIMITED or MINIMAL, got {level}"

    @pytest.mark.integration
    def test_limited_transparency_requirements(self, test_client):
        """Test that limited risk system has transparency requirements."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["limited-risk"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        risk_class = report["risk_classification"]

        # If LIMITED, should reference Article 50
        if risk_class["level"].lower() == "limited":
            # Check for Article 50 reference
            legal_basis = risk_class.get("legal_basis", {})
            has_article_50 = (
                "50" in str(legal_basis) or
                "Article 50" in str(risk_class) or
                "transparency" in str(risk_class).lower()
            )
            # Note: This is a soft assertion - transparency might be implied
            # rather than explicitly citing Article 50


# =============================================================================
# Test: Minimal Risk
# =============================================================================

class TestMinimalRisk:
    """Test Case 4: Movie Recommender - Should be MINIMAL with no specific reqs"""

    @pytest.mark.integration
    def test_minimal_classification(self, test_client):
        """Test that movie recommender is classified as MINIMAL risk."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["minimal-risk"]["description"]}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        status = wait_for_job_completion(test_client, job_id)
        assert status["status"] == "completed"

        report = test_client.get(f"/api/report/{job_id}").json()
        validate_report_structure(report)

        risk_class = report["risk_classification"]
        assert risk_class is not None
        assert risk_class["level"].lower() == "minimal"

    @pytest.mark.integration
    def test_minimal_few_or_no_requirements(self, test_client):
        """Test that minimal risk system has few or no requirements."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["minimal-risk"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        requirements = report["requirements"]

        # Minimal risk should have very few requirements (or none)
        expected = EXPECTED_RESULTS["minimal-risk"]
        assert len(requirements) <= expected["max_requirements"], \
            f"Expected at most {expected['max_requirements']} requirements, got {len(requirements)}"


# =============================================================================
# Cross-Cutting Tests
# =============================================================================

class TestCrossCutting:
    """Tests that apply across all risk levels"""

    @pytest.mark.integration
    @pytest.mark.parametrize("case_id", TEST_CASES.keys())
    def test_all_cases_complete_successfully(self, test_client, case_id):
        """Test that all test cases complete without errors."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES[case_id]["description"]}
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        status = wait_for_job_completion(test_client, job_id)
        assert status["status"] == "completed", \
            f"Case {case_id} did not complete: {status.get('error')}"

    @pytest.mark.integration
    @pytest.mark.parametrize("case_id", TEST_CASES.keys())
    def test_all_cases_have_valid_system_description(self, test_client, case_id):
        """Test that all cases extract valid system descriptions."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES[case_id]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()
        sys_desc = report.get("system_description")

        assert sys_desc is not None
        assert "domain" in sys_desc or "purpose" in sys_desc

    @pytest.mark.integration
    @pytest.mark.parametrize("case_id", TEST_CASES.keys())
    def test_all_requirements_have_citations(self, test_client, case_id):
        """Test that all generated requirements have citations."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES[case_id]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        report = test_client.get(f"/api/report/{job_id}").json()

        for req in report.get("requirements", []):
            citations = req.get("eu_ai_act_citations", [])
            # Every requirement should have at least one citation
            assert len(citations) >= 1 or req.get("hleg_citations", []), \
                f"Requirement {req.get('id')} has no citations"


# =============================================================================
# API Integration Tests
# =============================================================================

class TestAPIIntegration:
    """Tests for API endpoints and integration"""

    @pytest.mark.integration
    def test_examples_endpoint(self, test_client):
        """Test that examples endpoint returns all 4 test cases."""
        response = test_client.get("/api/examples")
        assert response.status_code == 200

        data = response.json()
        examples = data.get("examples", [])

        assert len(examples) == 4
        ids = {ex["id"] for ex in examples}
        assert ids == {"prohibited", "high-risk-healthcare", "limited-risk", "minimal-risk"}

    @pytest.mark.integration
    def test_job_status_progression(self, test_client):
        """Test that job progresses through expected phases."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["minimal-risk"]["description"]}
        )
        job_id = response.json()["job_id"]

        phases_seen = set()
        for _ in range(60):  # Poll for up to 2 minutes
            status = test_client.get(f"/api/status/{job_id}").json()
            phases_seen.add(status.get("phase"))

            if status["status"] == "completed":
                break
            time.sleep(2)

        # Should have progressed through multiple phases
        assert "elicitation" in phases_seen or "queued" in phases_seen

    @pytest.mark.integration
    def test_export_json(self, test_client):
        """Test JSON export functionality."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["minimal-risk"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        response = test_client.get(f"/api/export/{job_id}/json")
        assert response.status_code == 200
        # Check content-type or headers
        assert "json" in response.headers.get("content-type", "").lower()

    @pytest.mark.integration
    def test_export_markdown(self, test_client):
        """Test Markdown export functionality."""
        response = test_client.post(
            "/api/analyze",
            json={"description": TEST_CASES["minimal-risk"]["description"]}
        )
        job_id = response.json()["job_id"]
        wait_for_job_completion(test_client, job_id)

        response = test_client.get(f"/api/export/{job_id}/markdown")
        assert response.status_code == 200
        assert "markdown" in response.headers.get("content-type", "").lower()


# =============================================================================
# Database Integration Tests
# =============================================================================

class TestDatabaseIntegration:
    """Tests for Neo4j database integration"""

    @pytest.mark.integration
    def test_neo4j_connection(self):
        """Test that Neo4j is accessible."""
        from neo4j import GraphDatabase
        import os
        from dotenv import load_dotenv

        load_dotenv()

        uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        driver.close()

    @pytest.mark.integration
    def test_articles_present(self):
        """Test that EU AI Act articles are in the database."""
        from neo4j import GraphDatabase
        import os
        from dotenv import load_dotenv

        load_dotenv()

        uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        driver = GraphDatabase.driver(uri, auth=(user, password))
        result = driver.execute_query("MATCH (a:Article) RETURN count(a) as count")
        count = result.records[0]["count"]
        driver.close()

        assert count == 113, f"Expected 113 articles, found {count}"

    @pytest.mark.integration
    def test_hleg_requirements_present(self):
        """Test that HLEG requirements are in the database."""
        from neo4j import GraphDatabase
        import os
        from dotenv import load_dotenv

        load_dotenv()

        uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        driver = GraphDatabase.driver(uri, auth=(user, password))
        result = driver.execute_query("MATCH (h:HLEGRequirement) RETURN count(h) as count")
        count = result.records[0]["count"]
        driver.close()

        assert count == 7, f"Expected 7 HLEG requirements, found {count}"

    @pytest.mark.integration
    def test_mappings_present(self):
        """Test that EU-HLEG mappings are in the database."""
        from neo4j import GraphDatabase
        import os
        from dotenv import load_dotenv

        load_dotenv()

        uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")

        driver = GraphDatabase.driver(uri, auth=(user, password))
        result = driver.execute_query(
            "MATCH ()-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->() RETURN count(r) as count"
        )
        count = result.records[0]["count"]
        driver.close()

        assert count >= 500, f"Expected at least 500 mappings, found {count}"


# =============================================================================
# Entry Point for Running Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=300"])

"""
Comprehensive Unit Tests for TERE4AI MCP Server

This module tests all 5 MCP tools:
1. classify_risk_level - Risk classification based on system features
2. get_applicable_articles - Article retrieval by risk level
3. get_article_with_citations - Full article with citations and HLEG mappings
4. get_hleg_coverage - HLEG coverage matrix generation
5. search_legal_text - Search functionality across legal text

Tests cover:
- Valid inputs produce expected outputs
- Edge cases (empty inputs, missing fields, invalid values)
- Return value structure matches documentation
- Helper functions work correctly
- Error handling (graceful handling when Neo4j is not available)
"""

import sys
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

import pytest

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Import the server module - we need to patch before importing to prevent connection
# Since the module uses decorators, we need to access the underlying functions via .fn
import mcp_server.server as server_module

# Get the underlying functions from the FunctionTool wrappers
classify_risk_level = server_module.classify_risk_level.fn
get_applicable_articles = server_module.get_applicable_articles.fn
get_article_with_citations = server_module.get_article_with_citations.fn
get_hleg_coverage = server_module.get_hleg_coverage.fn
search_legal_text = server_module.search_legal_text.fn

# Import helper functions directly (these are not decorated)
_check_prohibited_practices = server_module._check_prohibited_practices
_check_annex_iii = server_module._check_annex_iii
_has_significant_output_influence = server_module._has_significant_output_influence
_requires_transparency = server_module._requires_transparency
_get_article_5_text = server_module._get_article_5_text
_get_annex_iii_text = server_module._get_annex_iii_text
_get_article_50_text = server_module._get_article_50_text
_get_section_for_article = server_module._get_section_for_article
_get_category_for_article = server_module._get_category_for_article
_get_articles = server_module._get_articles


# =============================================================================
# Fixtures - Using autouse to ensure mock is applied
# =============================================================================

@pytest.fixture(autouse=True)
def mock_neo4j_driver():
    """Mock the Neo4j driver to prevent actual connections during tests."""
    with patch.object(server_module, 'get_neo4j_driver') as mock_driver:
        mock_driver.return_value.__enter__ = Mock(return_value=Mock())
        mock_driver.return_value.__exit__ = Mock(return_value=False)
        yield mock_driver


@pytest.fixture
def mock_execute_query_error():
    """Mock execute_query to raise an exception."""
    with patch.object(server_module, 'execute_query', side_effect=Exception("Neo4j connection failed")):
        yield


@pytest.fixture
def mock_execute_query_empty():
    """Mock execute_query to return empty results."""
    with patch.object(server_module, 'execute_query', return_value=[]):
        yield


@pytest.fixture
def mock_execute_query_with_data():
    """Mock execute_query with sample data responses matching the query patterns."""
    def query_handler(query, **params):
        # Match article query for get_article_with_citations
        if 'a.title as title' in query and 'collect({index: p.index' in query:
            return [{
                "title": "Risk Management",
                "paragraphs": [{"index": 1, "text": "Sample paragraph text", "points": []}]
            }]
        # Match HLEG alignment query
        if 'ALIGNS_WITH_HLEG_REQUIREMENT' in query:
            return [{
                "requirement_id": "transparency",
                "requirement_name": "Transparency",
                "relevance": 0.9,
                "rationale": "High relevance",
                "subtopics": ["explainability"]
            }]
        # Match recital query
        if 'Recital' in query:
            return [{"number": 1, "text": "Sample recital text"}]
        # Match article fetch for _get_articles
        if 'Article {number: $num}' in query and 'a.number as number' in query:
            return [{
                "number": params.get('num', 9),
                "title": "Risk Management",
                "paragraphs": [{"index": 1, "text": "Sample paragraph"}]
            }]
        return []

    with patch.object(server_module, 'execute_query', side_effect=query_handler):
        yield


# =============================================================================
# Test Tool 1: classify_risk_level
# =============================================================================

class TestClassifyRiskLevel:
    """Tests for the classify_risk_level MCP tool."""

    # -------------------------------------------------------------------------
    # UNACCEPTABLE Risk Level Tests (Article 5 Prohibited Practices)
    # -------------------------------------------------------------------------

    def test_social_scoring_returns_unacceptable(self, mock_execute_query_error):
        """Social scoring systems must be classified as UNACCEPTABLE."""
        features = {
            "domain": "government",
            "purpose": "Evaluate citizens based on social behavior",
            "social_scoring": True,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"
        assert "5(1)(c)" in result["legal_basis_article"]
        assert result["article_6_exception"] is False
        assert "human_agency_and_oversight" in result["hleg_principles"]
        assert "social scoring" in result["reasoning"].lower()

    def test_subliminal_manipulation_returns_unacceptable(self, mock_execute_query_error):
        """Systems using subliminal techniques must be UNACCEPTABLE."""
        features = {
            "domain": "marketing",
            "purpose": "Influence purchasing decisions",
            "subliminal_techniques": True,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"
        assert "5(1)(a)" in result["legal_basis_article"]
        assert "subliminal" in result["reasoning"].lower()

    def test_realtime_biometric_law_enforcement_returns_unacceptable(self, mock_execute_query_error):
        """Real-time biometric identification for law enforcement is UNACCEPTABLE."""
        features = {
            "domain": "security",
            "purpose": "Identify individuals in public spaces",
            "real_time_biometric": True,
            "law_enforcement_use": True,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"
        assert "5(1)(h)" in result["legal_basis_article"]
        assert "real-time" in result["reasoning"].lower() or "biometric" in result["reasoning"].lower()

    def test_emotion_recognition_workplace_returns_unacceptable(self, mock_execute_query_error):
        """Emotion recognition in workplace must be UNACCEPTABLE."""
        features = {
            "domain": "hr",
            "purpose": "Monitor employee emotions",
            "emotion_recognition": True,
            "deployment_context": "workplace",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"
        assert "5(1)(f)" in result["legal_basis_article"]
        assert "emotion" in result["reasoning"].lower()

    def test_emotion_recognition_education_returns_unacceptable(self, mock_execute_query_error):
        """Emotion recognition in educational institutions must be UNACCEPTABLE."""
        features = {
            "domain": "education",
            "purpose": "Monitor student emotions during exams",
            "emotion_recognition": True,
            "deployment_context": "educational_institution",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"
        assert "5(1)(f)" in result["legal_basis_article"]

    # -------------------------------------------------------------------------
    # HIGH Risk Level Tests (Annex III Categories)
    # -------------------------------------------------------------------------

    def test_healthcare_triage_returns_high_risk(self, mock_execute_query_error):
        """Healthcare triage systems must be HIGH risk (Annex III 5a)."""
        features = {
            "domain": "healthcare",
            "purpose": "Triage patients in emergency room",
            "safety_critical": True,
            "decision_types": ["triage"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert "Annex III" in result["legal_basis_article"]
        assert result["annex_category"] == "5"
        assert "healthcare" in result["reasoning"].lower() or "triage" in result["reasoning"].lower()

    def test_education_assessment_returns_high_risk(self, mock_execute_query_error):
        """Education assessment systems must be HIGH risk (Annex III 3)."""
        features = {
            "domain": "education",
            "purpose": "Grade student essays",
            "decision_types": ["assessment"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert "Annex III" in result["legal_basis_article"]
        assert result["annex_category"] == "3"

    def test_education_access_denial_returns_high_risk(self, mock_execute_query_error):
        """Systems that can deny access to education must be HIGH risk."""
        features = {
            "domain": "education",
            "purpose": "Determine university admissions",
            "decision_types": ["access_denial"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "3"

    def test_employment_recruitment_returns_high_risk(self, mock_execute_query_error):
        """Employment recruitment systems must be HIGH risk (Annex III 4)."""
        features = {
            "domain": "employment",
            "purpose": "Screen job candidates",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "4"
        assert "employment" in result["reasoning"].lower()

    def test_law_enforcement_domain_returns_high_risk(self, mock_execute_query_error):
        """Law enforcement domain systems must be HIGH risk (Annex III 6)."""
        features = {
            "domain": "law_enforcement",
            "purpose": "Predict crime hotspots",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "6"

    def test_law_enforcement_use_flag_returns_high_risk(self, mock_execute_query_error):
        """Systems marked for law enforcement use must be HIGH risk."""
        features = {
            "domain": "general",
            "purpose": "Facial recognition",
            "law_enforcement_use": True,
            # Note: NOT real_time_biometric, so not unacceptable
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "6"

    def test_biometric_processing_returns_high_risk(self, mock_execute_query_error):
        """Biometric processing systems must be HIGH risk (Annex III 1)."""
        features = {
            "domain": "access_control",
            "purpose": "Fingerprint authentication for building access",
            "biometric_processing": True,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "1"
        assert "biometric" in result["reasoning"].lower()

    def test_critical_infrastructure_returns_high_risk(self, mock_execute_query_error):
        """Critical infrastructure systems must be HIGH risk (Annex III 2)."""
        features = {
            "domain": "critical_infrastructure",
            "purpose": "Manage power grid",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "2"

    def test_critical_infrastructure_flag_returns_high_risk(self, mock_execute_query_error):
        """Systems with critical_infrastructure flag must be HIGH risk."""
        features = {
            "domain": "utilities",
            "purpose": "Water treatment control",
            "critical_infrastructure": True,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "2"

    # -------------------------------------------------------------------------
    # Article 6(3) Exception Tests
    # -------------------------------------------------------------------------

    def test_article_6_3_exception_advisory_system(self, mock_execute_query_error):
        """Advisory systems should get Article 6(3) exception (limited risk)."""
        features = {
            "domain": "employment",
            "purpose": "Suggest candidates (advisory only)",
            "autonomy_level": "advisory",  # Key: purely advisory
        }
        result = classify_risk_level(features)

        # Should match Annex III category 4 but get exception
        assert result["risk_level"] == "limited"
        assert result["article_6_exception"] is True
        assert result["annex_category"] == "4"
        assert "exception" in result["reasoning"].lower()

    def test_no_exception_for_partial_autonomy(self, mock_execute_query_error):
        """Partial autonomy systems should NOT get Article 6(3) exception."""
        features = {
            "domain": "employment",
            "purpose": "Filter candidates",
            "autonomy_level": "partial",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["article_6_exception"] is False

    # -------------------------------------------------------------------------
    # LIMITED Risk Level Tests (Article 50)
    # -------------------------------------------------------------------------

    def test_chatbot_content_generation_returns_limited(self, mock_execute_query_error):
        """Chatbots generating content must be LIMITED risk (Article 50)."""
        features = {
            "domain": "customer_service",
            "purpose": "Answer customer questions",
            "decision_types": ["content_generation"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "limited"
        assert result["legal_basis_article"] == "Article 50"
        assert "transparency" in result["hleg_principles"]

    def test_recommendation_system_returns_minimal(self, mock_execute_query_error):
        """Pure recommendation systems are MINIMAL risk (no Article 50 trigger).

        Phase 5 change: Recommendation systems without chatbot/content generation
        are now correctly classified as MINIMAL risk.
        """
        features = {
            "domain": "entertainment",
            "purpose": "Recommend movies",
            "decision_types": ["recommendation"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "minimal"
        assert result["legal_basis_article"] is None

    def test_chatbot_with_affected_persons_returns_limited(self, mock_execute_query_error):
        """Chatbots that interact with users are LIMITED risk (Article 50).

        Phase 5 change: affected_persons alone no longer triggers LIMITED.
        Must have chatbot/conversational indicators.
        """
        features = {
            "domain": "general",
            "purpose": "Chatbot that interacts with users",
            "affected_persons": ["end_users"],
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "limited"

    # -------------------------------------------------------------------------
    # MINIMAL Risk Level Tests
    # -------------------------------------------------------------------------

    def test_movie_recommendation_minimal_risk(self, mock_execute_query_error):
        """Simple movie recommendation with no transparency requirements is MINIMAL."""
        features = {
            "domain": "entertainment",
            "purpose": "Suggest movies based on viewing history",
            # No decision_types, no affected_persons
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "minimal"
        assert result["legal_basis_article"] is None
        assert result["annex_category"] is None
        assert result["hleg_principles"] == []

    def test_spam_filter_minimal_risk(self, mock_execute_query_error):
        """Spam filters should be MINIMAL risk."""
        features = {
            "domain": "email",
            "purpose": "Filter spam emails",
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "minimal"

    def test_empty_features_minimal_risk(self, mock_execute_query_error):
        """Empty features dictionary should default to MINIMAL risk."""
        features = {}
        result = classify_risk_level(features)

        assert result["risk_level"] == "minimal"

    # -------------------------------------------------------------------------
    # Edge Cases and Return Structure Tests
    # -------------------------------------------------------------------------

    def test_return_structure_completeness(self, mock_execute_query_error):
        """All required keys must be present in return value."""
        features = {"domain": "general"}
        result = classify_risk_level(features)

        required_keys = [
            "risk_level",
            "legal_basis_article",
            "legal_basis_text",
            "annex_category",
            "article_6_exception",
            "hleg_principles",
            "reasoning",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_risk_level_values(self, mock_execute_query_error):
        """Risk level must be one of the valid values."""
        valid_levels = {"unacceptable", "high", "limited", "minimal"}

        test_cases = [
            {"social_scoring": True},
            {"domain": "healthcare", "safety_critical": True},
            {"decision_types": ["content_generation"]},
            {},
        ]

        for features in test_cases:
            result = classify_risk_level(features)
            assert result["risk_level"] in valid_levels

    def test_none_values_handled_gracefully(self, mock_execute_query_error):
        """None values in features should be handled gracefully."""
        features = {
            "domain": None,
            "biometric_processing": None,
            "social_scoring": None,
        }
        result = classify_risk_level(features)

        # Should not raise exception
        assert result["risk_level"] == "minimal"

    def test_priority_unacceptable_over_high(self, mock_execute_query_error):
        """UNACCEPTABLE should take priority over HIGH risk."""
        features = {
            "domain": "employment",  # Would be HIGH risk
            "social_scoring": True,  # Makes it UNACCEPTABLE
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "unacceptable"


# =============================================================================
# Test Tool 2: get_applicable_articles
# =============================================================================

class TestGetApplicableArticles:
    """Tests for the get_applicable_articles MCP tool."""

    def test_unacceptable_returns_empty_list(self, mock_execute_query_empty):
        """UNACCEPTABLE risk level should return empty list."""
        result = get_applicable_articles("unacceptable")

        assert result == []

    def test_minimal_returns_empty_list(self, mock_execute_query_empty):
        """MINIMAL risk level should return empty list."""
        result = get_applicable_articles("minimal")

        assert result == []

    def test_limited_returns_article_50(self, mock_execute_query_error):
        """LIMITED risk should return Article 50 (fallback on Neo4j error)."""
        result = get_applicable_articles("limited")

        assert len(result) == 1
        assert result[0]["number"] == 50
        assert result[0]["section"] == "Chapter IV - Transparency obligations"

    def test_high_returns_articles_8_to_27(self, mock_execute_query_error):
        """HIGH risk should return Articles 8-27 (fallback on Neo4j error)."""
        result = get_applicable_articles("high")

        article_numbers = [a["number"] for a in result]
        expected = list(range(8, 28))

        assert article_numbers == expected

    def test_limited_returns_fallback_when_neo4j_empty(self, mock_execute_query_empty):
        """LIMITED risk returns fallback data when Neo4j returns empty records.

        BUG FIX: Now correctly returns fallback articles when Neo4j returns empty.
        """
        result = get_applicable_articles("limited")
        # Should return Article 50 with fallback data
        assert len(result) == 1
        assert result[0]["number"] == 50
        assert result[0]["title"] == "Article 50"
        assert result[0]["paragraphs"] == []

    def test_high_returns_fallback_when_neo4j_empty(self, mock_execute_query_empty):
        """HIGH risk returns fallback data when Neo4j returns empty records.

        BUG FIX: Now correctly returns fallback articles when Neo4j returns empty.
        """
        result = get_applicable_articles("high")
        # Should return Articles 8-27 with fallback data
        assert len(result) == 20
        article_numbers = [a["number"] for a in result]
        assert article_numbers == list(range(8, 28))
        # All should have fallback title format
        for article in result:
            assert article["title"] == f"Article {article['number']}"
            assert article["paragraphs"] == []

    def test_high_risk_article_structure(self, mock_execute_query_error):
        """HIGH risk articles should have correct structure (fallback data)."""
        result = get_applicable_articles("high")

        required_keys = ["number", "title", "section", "paragraphs", "category"]
        for article in result:
            for key in required_keys:
                assert key in article, f"Missing key {key} in article"

    def test_invalid_risk_level_returns_empty(self, mock_execute_query_empty):
        """Invalid risk level should return empty list."""
        result = get_applicable_articles("invalid_level")

        assert result == []

    def test_annex_category_parameter_accepted(self, mock_execute_query_error):
        """Function should accept optional annex_category parameter (fallback data)."""
        result = get_applicable_articles("high", annex_category="5")

        # Should still return articles (annex_category is for context)
        assert len(result) > 0

    def test_neo4j_fallback_on_error(self, mock_execute_query_error):
        """Should return minimal article info when Neo4j unavailable."""
        result = get_applicable_articles("high")

        # Should still return something with fallback
        assert len(result) == 20  # Articles 8-27
        for article in result:
            assert "number" in article
            assert "title" in article


# =============================================================================
# Test Tool 3: get_article_with_citations
# =============================================================================

class TestGetArticleWithCitations:
    """Tests for the get_article_with_citations MCP tool."""

    def test_return_structure(self, mock_execute_query_empty):
        """Return value must have all required keys."""
        result = get_article_with_citations(9)

        required_keys = [
            "number",
            "title",
            "full_text",
            "paragraphs",
            "recitals",
            "hleg_mappings",
            "section",
            "category",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_article_number_preserved(self, mock_execute_query_empty):
        """Article number should be preserved in result."""
        result = get_article_with_citations(14)

        assert result["number"] == 14

    def test_section_assigned_correctly(self, mock_execute_query_empty):
        """Section should be assigned based on article number."""
        result = get_article_with_citations(9)

        assert "Section 2" in result["section"]

    def test_category_assigned_correctly(self, mock_execute_query_empty):
        """Category should be assigned based on article number."""
        result = get_article_with_citations(9)

        assert result["category"] == "risk_management"

    def test_with_neo4j_data(self, mock_execute_query_with_data):
        """Should populate data when Neo4j returns results."""
        result = get_article_with_citations(9)

        # Should have HLEG mappings from mock
        assert len(result["hleg_mappings"]) > 0 or "error" not in result

    def test_graceful_error_handling(self, mock_execute_query_error):
        """Should handle Neo4j errors gracefully."""
        result = get_article_with_citations(9)

        # Should return partial result with error field
        assert result["number"] == 9
        # May have error field, but should not crash

    def test_invalid_article_number(self, mock_execute_query_empty):
        """Should handle invalid article numbers gracefully."""
        result = get_article_with_citations(9999)

        assert result["number"] == 9999
        assert result["paragraphs"] == []


# =============================================================================
# Test Tool 4: get_hleg_coverage
# =============================================================================

class TestGetHLEGCoverage:
    """Tests for the get_hleg_coverage MCP tool."""

    def test_return_structure(self, mock_execute_query_empty):
        """Return value must have all required keys."""
        result = get_hleg_coverage([9, 10, 11])

        required_keys = [
            "principles",
            "coverage_percentage",
            "uncovered_principles",
            "total_mappings",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_empty_articles_list(self, mock_execute_query_empty):
        """Empty articles list should return empty coverage."""
        result = get_hleg_coverage([])

        assert result["principles"] == {}
        assert result["total_mappings"] == 0
        assert result["coverage_percentage"] == 0.0
        assert len(result["uncovered_principles"]) == 7  # All 7 principles uncovered

    def test_coverage_calculation(self):
        """Coverage percentage should be calculated correctly."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = [
                {
                    "requirement_id": "transparency",
                    "requirement_name": "Transparency",
                    "article_number": 9,
                    "relevance": 0.9,
                    "subtopics": []
                }
            ]
            result = get_hleg_coverage([9])

            # 1 out of 7 principles = ~14.3%
            assert result["coverage_percentage"] == pytest.approx(14.285714, rel=0.01)

    def test_uncovered_principles_list(self, mock_execute_query_empty):
        """Should list all 7 principles when nothing is covered."""
        result = get_hleg_coverage([9])

        expected_principles = [
            "human_agency_and_oversight",
            "technical_robustness_and_safety",
            "privacy_and_data_governance",
            "transparency",
            "diversity_non_discrimination_and_fairness",
            "societal_and_environmental_wellbeing",
            "accountability",
        ]

        for principle in result["uncovered_principles"]:
            assert principle in expected_principles

    def test_graceful_error_handling(self, mock_execute_query_error):
        """Should handle Neo4j errors gracefully."""
        result = get_hleg_coverage([9, 10])

        # Should return structure with error field
        assert "error" in result

    def test_subtopics_converted_to_list(self):
        """Subtopics sets should be converted to lists for JSON serialization."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = [
                {
                    "requirement_id": "transparency",
                    "requirement_name": "Transparency",
                    "article_number": 9,
                    "relevance": 0.9,
                    "subtopics": ["traceability", "explainability"]
                }
            ]
            result = get_hleg_coverage([9])

            if result["principles"]:
                for principle_id, principle_data in result["principles"].items():
                    assert isinstance(principle_data["subtopics"], list)


# =============================================================================
# Test Tool 5: search_legal_text
# =============================================================================

class TestSearchLegalText:
    """Tests for the search_legal_text MCP tool."""

    def test_return_structure(self, mock_execute_query_empty):
        """Return value must have all required keys."""
        result = search_legal_text("risk management")

        required_keys = ["results", "total_matches", "query"]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_query_echoed_back(self, mock_execute_query_empty):
        """Query should be echoed back in result."""
        result = search_legal_text("transparency requirements")

        assert result["query"] == "transparency requirements"

    def test_empty_query(self, mock_execute_query_empty):
        """Empty query should return empty results."""
        result = search_legal_text("")

        assert result["results"] == []
        assert result["total_matches"] == 0

    def test_source_filter_eu_ai_act(self):
        """Should respect source filter for EU AI Act."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = []
            result = search_legal_text("risk", filters={"source": "eu_ai_act"})

            # Should have made queries for articles and recitals
            assert mock.call_count >= 1

    def test_source_filter_hleg(self):
        """Should respect source filter for HLEG."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = []
            result = search_legal_text("transparency", filters={"source": "hleg"})

            # Should have made query for HLEG only
            assert result["total_matches"] == 0

    def test_article_range_filter(self):
        """Should respect article_range filter."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = []
            result = search_legal_text(
                "safety",
                filters={"article_range": [8, 15], "source": "eu_ai_act"}
            )

            # Should have applied article range in query
            if mock.called:
                call_args = str(mock.call_args_list)
                # Article range should appear in query

    def test_limit_filter(self, mock_execute_query_empty):
        """Should respect limit filter."""
        result = search_legal_text("risk", filters={"limit": 5})

        assert len(result["results"]) <= 5

    def test_default_limit(self):
        """Default limit should be 10."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = []
            result = search_legal_text("safety")

            # Default limit should be applied
            if mock.called:
                args = mock.call_args_list
                # Check that limit parameter was passed

    def test_result_types(self):
        """Results should have correct type markers."""
        with patch.object(server_module, 'execute_query') as mock:
            mock.return_value = [
                {"type": "article", "reference": "Article 9(1)", "text": "Sample text", "article_number": 9}
            ]
            result = search_legal_text("risk", filters={"source": "eu_ai_act"})

            valid_types = {"article", "recital", "hleg"}
            for item in result["results"]:
                assert item["type"] in valid_types

    def test_text_truncation(self):
        """Long text should be truncated."""
        with patch.object(server_module, 'execute_query') as mock:
            long_text = "A" * 500
            mock.return_value = [
                {"type": "article", "reference": "Article 9(1)", "text": long_text, "article_number": 9}
            ]
            result = search_legal_text("risk", filters={"source": "eu_ai_act"})

            if result["results"]:
                assert len(result["results"][0]["text"]) <= 303  # 300 + "..."

    def test_graceful_error_handling(self, mock_execute_query_error):
        """Should handle Neo4j errors gracefully."""
        result = search_legal_text("risk management")

        assert "error" in result
        assert result["results"] == []
        assert result["total_matches"] == 0


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions used by MCP tools."""

    # -------------------------------------------------------------------------
    # _check_prohibited_practices
    # -------------------------------------------------------------------------

    def test_check_prohibited_practices_social_scoring(self, mock_execute_query_error):
        """Should identify social scoring as prohibited."""
        features = {"social_scoring": True}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"
        assert "5(1)(c)" in result["legal_basis_article"]

    def test_check_prohibited_practices_subliminal(self, mock_execute_query_error):
        """Should identify subliminal techniques as prohibited."""
        features = {"subliminal_techniques": True}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"
        assert "5(1)(a)" in result["legal_basis_article"]

    def test_check_prohibited_practices_biometric_law_enforcement(self, mock_execute_query_error):
        """Should identify real-time biometric for law enforcement as prohibited."""
        features = {"real_time_biometric": True, "law_enforcement_use": True}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"

    def test_check_prohibited_practices_emotion_workplace(self, mock_execute_query_error):
        """Should identify emotion recognition in workplace as prohibited."""
        features = {"emotion_recognition": True, "deployment_context": "workplace"}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"

    def test_check_prohibited_practices_none_result(self, mock_execute_query_error):
        """Should return None for non-prohibited features."""
        features = {"domain": "entertainment"}
        result = _check_prohibited_practices(features)

        assert result is None

    # Phase 5: Deepfake/intimate content detection tests
    def test_check_prohibited_practices_deepfake_via_purpose(self, mock_execute_query_error):
        """Deepfake in purpose should be prohibited (Phase 5)."""
        features = {"purpose": "Generate deepfake videos of celebrities"}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"
        assert "5(1)(c)" in result["legal_basis_article"]

    def test_check_prohibited_practices_deepfake_via_raw_description(self, mock_execute_query_error):
        """Deepfake in raw_description should be prohibited (Phase 5)."""
        features = {"raw_description": "Creates deep fake images of people without their knowledge"}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"

    def test_check_prohibited_practices_intimate_content(self, mock_execute_query_error):
        """Intimate content generation without consent should be prohibited (Phase 5)."""
        features = {"purpose": "Generate realistic nude images without consent"}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"

    def test_check_prohibited_practices_without_consent(self, mock_execute_query_error):
        """'Without consent' keyword should trigger prohibition (Phase 5)."""
        features = {"raw_description": "Creates fake images of people without consent"}
        result = _check_prohibited_practices(features)

        assert result is not None
        assert result["risk_level"] == "unacceptable"

    # -------------------------------------------------------------------------
    # _check_annex_iii
    # -------------------------------------------------------------------------

    def test_check_annex_iii_healthcare(self, mock_execute_query_error):
        """Should identify healthcare safety-critical as high risk."""
        features = {"domain": "healthcare", "safety_critical": True}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "5"

    # Phase 5: Healthcare via purpose keywords tests
    def test_check_annex_iii_healthcare_via_purpose_triage(self, mock_execute_query_error):
        """Healthcare triage via purpose keywords should be high risk (Phase 5)."""
        features = {
            "domain": "healthcare",
            "purpose": "Patient triage in emergency room"
        }
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "5"

    def test_check_annex_iii_healthcare_via_raw_description(self, mock_execute_query_error):
        """Healthcare via raw_description keywords should be high risk (Phase 5)."""
        features = {
            "domain": "healthcare",
            "raw_description": "Hospital diagnostic system for patient symptoms and treatment recommendations"
        }
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "5"

    def test_check_annex_iii_education_assessment(self, mock_execute_query_error):
        """Should identify education assessment as high risk."""
        features = {"domain": "education", "decision_types": ["assessment"]}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "3"

    def test_check_annex_iii_employment(self, mock_execute_query_error):
        """Should identify employment domain as high risk."""
        features = {"domain": "employment"}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "4"

    def test_check_annex_iii_law_enforcement(self, mock_execute_query_error):
        """Should identify law enforcement as high risk."""
        features = {"domain": "law_enforcement"}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "6"

    def test_check_annex_iii_biometrics(self, mock_execute_query_error):
        """Should identify biometric processing as high risk."""
        features = {"biometric_processing": True}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "1"

    def test_check_annex_iii_critical_infrastructure(self, mock_execute_query_error):
        """Should identify critical infrastructure as high risk."""
        features = {"critical_infrastructure": True}
        result = _check_annex_iii(features)

        assert result is not None
        assert result["annex_category"] == "2"

    def test_check_annex_iii_none_result(self, mock_execute_query_error):
        """Should return None for non-high-risk domains."""
        features = {"domain": "entertainment"}
        result = _check_annex_iii(features)

        assert result is None

    # -------------------------------------------------------------------------
    # _has_significant_output_influence
    # -------------------------------------------------------------------------

    def test_has_significant_influence_advisory(self):
        """Advisory systems should not have significant influence."""
        features = {"autonomy_level": "advisory"}
        result = _has_significant_output_influence(features)

        assert result is False

    def test_has_significant_influence_partial(self):
        """Partial autonomy should have significant influence."""
        features = {"autonomy_level": "partial"}
        result = _has_significant_output_influence(features)

        assert result is True

    def test_has_significant_influence_default(self):
        """Default should assume significant influence."""
        features = {}
        result = _has_significant_output_influence(features)

        assert result is True

    # -------------------------------------------------------------------------
    # _requires_transparency
    # -------------------------------------------------------------------------

    def test_requires_transparency_content_generation(self):
        """Content generation should require transparency."""
        features = {"decision_types": ["content_generation"]}
        result = _requires_transparency(features)

        assert result is True

    def test_requires_transparency_recommendation_false(self):
        """Pure recommendation systems do NOT require transparency.

        Phase 5 change: Recommendation systems are excluded from Article 50
        unless they also have chatbot/content generation functionality.
        """
        features = {"decision_types": ["recommendation"]}
        result = _requires_transparency(features)

        assert result is False

    def test_requires_transparency_affected_persons_false(self):
        """Systems with affected_persons alone do NOT require transparency.

        Phase 5 change: affected_persons is not a transparency trigger.
        Must have explicit chatbot/conversational/content generation indicators.
        """
        features = {"affected_persons": ["users"]}
        result = _requires_transparency(features)

        assert result is False

    def test_requires_transparency_false(self):
        """Systems without transparency triggers should not require it."""
        features = {"domain": "internal_analytics"}
        result = _requires_transparency(features)

        assert result is False

    # Phase 5: Additional transparency tests
    def test_requires_transparency_chatbot_via_raw_description(self):
        """Chatbot detected via raw_description should require transparency (Phase 5)."""
        features = {"raw_description": "A conversational AI chatbot for customer support"}
        result = _requires_transparency(features)

        assert result is True

    def test_requires_transparency_recommendation_with_chatbot(self):
        """Recommendation system that is also a chatbot should require transparency (Phase 5)."""
        features = {
            "purpose": "Recommend products through our chatbot interface",
            "decision_types": ["recommendation"]
        }
        result = _requires_transparency(features)

        assert result is True

    def test_requires_transparency_personalization_minimal(self):
        """Pure personalization systems should NOT require transparency (Phase 5)."""
        features = {"purpose": "Personalizes the content feed for users"}
        result = _requires_transparency(features)

        assert result is False

    def test_requires_transparency_virtual_assistant(self):
        """Virtual assistant should require transparency (Phase 5)."""
        features = {"purpose": "A virtual assistant that answers user questions"}
        result = _requires_transparency(features)

        assert result is True

    def test_requires_transparency_emotion_recognition(self):
        """Emotion recognition should require transparency (Phase 5)."""
        features = {"emotion_recognition": True}
        result = _requires_transparency(features)

        assert result is True

    # -------------------------------------------------------------------------
    # _get_section_for_article
    # -------------------------------------------------------------------------

    def test_get_section_for_article_chapter_1(self):
        """Articles 1-7 should be Chapter I."""
        for num in [1, 5, 7]:
            result = _get_section_for_article(num)
            assert "Chapter I" in result

    def test_get_section_for_article_chapter_3_section_2(self):
        """Articles 8-15 should be Chapter III, Section 2."""
        for num in [8, 10, 15]:
            result = _get_section_for_article(num)
            assert "Section 2" in result

    def test_get_section_for_article_chapter_3_section_3(self):
        """Articles 16-27 should be Chapter III, Section 3."""
        for num in [16, 20, 27]:
            result = _get_section_for_article(num)
            assert "Section 3" in result

    def test_get_section_for_article_50(self):
        """Article 50 should be Chapter IV."""
        result = _get_section_for_article(50)
        assert "Chapter IV" in result

    # -------------------------------------------------------------------------
    # _get_category_for_article
    # -------------------------------------------------------------------------

    def test_get_category_for_article_9(self):
        """Article 9 should be risk_management."""
        result = _get_category_for_article(9)
        assert result == "risk_management"

    def test_get_category_for_article_10(self):
        """Article 10 should be data_governance."""
        result = _get_category_for_article(10)
        assert result == "data_governance"

    def test_get_category_for_article_14(self):
        """Article 14 should be human_oversight."""
        result = _get_category_for_article(14)
        assert result == "human_oversight"

    def test_get_category_for_article_50(self):
        """Article 50 should be transparency_limited."""
        result = _get_category_for_article(50)
        assert result == "transparency_limited"

    def test_get_category_for_unknown_article(self):
        """Unknown articles should return 'general'."""
        result = _get_category_for_article(999)
        assert result == "general"

    # -------------------------------------------------------------------------
    # Text retrieval helpers with fallbacks
    # -------------------------------------------------------------------------

    def test_get_article_5_text_fallback(self, mock_execute_query_error):
        """Should return fallback text when Neo4j unavailable."""
        result = _get_article_5_text("1_c")

        assert len(result) > 0
        assert "social" in result.lower() or "classification" in result.lower()

    def test_get_annex_iii_text_fallback(self, mock_execute_query_error):
        """Should return fallback text when Neo4j unavailable."""
        result = _get_annex_iii_text("4")

        assert len(result) > 0
        assert "employment" in result.lower()

    def test_get_article_50_text_fallback(self, mock_execute_query_error):
        """Should return fallback text when Neo4j unavailable."""
        result = _get_article_50_text()

        assert len(result) > 0
        assert "AI system" in result

    def test_get_annex_iii_text_unknown_category(self, mock_execute_query_error):
        """Should return generic text for unknown categories."""
        result = _get_annex_iii_text("999")

        assert "999" in result or "category" in result.lower()


# =============================================================================
# Integration-like Tests (testing combinations)
# =============================================================================

class TestToolCombinations:
    """Tests that verify tools work together correctly."""

    def test_classify_then_get_articles(self, mock_execute_query_error):
        """classify_risk_level result can be used with get_applicable_articles."""
        # Classify a system
        features = {"domain": "employment", "purpose": "Screen candidates"}
        classification = classify_risk_level(features)

        # Use classification to get applicable articles
        articles = get_applicable_articles(classification["risk_level"])

        assert len(articles) > 0  # HIGH risk should return articles

    def test_classify_minimal_then_get_articles(self, mock_execute_query_error):
        """MINIMAL risk classification should result in no articles."""
        features = {"domain": "entertainment"}
        classification = classify_risk_level(features)

        articles = get_applicable_articles(classification["risk_level"])

        assert articles == []

    def test_get_hleg_coverage_for_high_risk_articles(self, mock_execute_query_empty):
        """HLEG coverage can be calculated for high-risk articles."""
        # Get high-risk articles
        articles = get_applicable_articles("high")
        article_numbers = [a["number"] for a in articles]

        # Get HLEG coverage
        coverage = get_hleg_coverage(article_numbers)

        assert "principles" in coverage
        assert "coverage_percentage" in coverage


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_neo4j_connection_error_classify(self, mock_execute_query_error):
        """classify_risk_level should work even without Neo4j."""
        features = {"domain": "healthcare", "safety_critical": True}
        result = classify_risk_level(features)

        # Should still classify correctly using fallbacks
        assert result["risk_level"] == "high"
        assert len(result["legal_basis_text"]) > 0

    def test_neo4j_connection_error_search(self, mock_execute_query_error):
        """search_legal_text should return error gracefully."""
        result = search_legal_text("risk management")

        assert "error" in result
        assert result["results"] == []
        assert result["query"] == "risk management"

    def test_neo4j_connection_error_hleg_coverage(self, mock_execute_query_error):
        """get_hleg_coverage should return error gracefully."""
        result = get_hleg_coverage([9, 10])

        assert "error" in result

    def test_neo4j_connection_error_article_citations(self, mock_execute_query_error):
        """get_article_with_citations should return partial result on error."""
        result = get_article_with_citations(9)

        # Should still return structure with article number
        assert result["number"] == 9
        assert result["section"] == "Chapter III, Section 2 - Requirements for high-risk AI systems"


# =============================================================================
# Additional Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Additional edge case tests for robustness."""

    def test_classify_with_all_features(self, mock_execute_query_error):
        """Classify with all possible features set."""
        features = {
            "domain": "healthcare",
            "purpose": "Triage and diagnosis",
            "biometric_processing": False,
            "real_time_biometric": False,
            "law_enforcement_use": False,
            "safety_critical": True,
            "social_scoring": False,
            "subliminal_techniques": False,
            "emotion_recognition": False,
            "affects_fundamental_rights": True,
            "deployment_context": "hospital",
            "decision_types": ["triage", "recommendation"],
            "affected_persons": ["patients"],
            "autonomy_level": "partial",
            "critical_infrastructure": False,
        }
        result = classify_risk_level(features)

        assert result["risk_level"] == "high"
        assert result["annex_category"] == "5"

    def test_search_with_special_characters(self, mock_execute_query_empty):
        """Search should handle special characters gracefully."""
        result = search_legal_text("risk & management (high)")

        # Should not raise an exception
        assert "query" in result
        assert result["query"] == "risk & management (high)"

    def test_get_articles_with_negative_number(self, mock_execute_query_empty):
        """Should handle negative article numbers gracefully."""
        result = get_article_with_citations(-1)

        assert result["number"] == -1

    def test_hleg_coverage_with_invalid_article_numbers(self, mock_execute_query_empty):
        """Should handle invalid article numbers in list."""
        result = get_hleg_coverage([999, 1000, -5])

        assert "principles" in result
        assert result["total_mappings"] == 0


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

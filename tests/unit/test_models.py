"""
Comprehensive Unit Tests for TERE4AI Phase 1 Pydantic Models

This module contains thorough tests for all Phase 1 models:
- citations.py: Citation, CitationBundle
- risk.py: RiskLevel, RiskClassification, RiskClassificationResult, ProhibitedPractice, AnnexIIICategory
- system_description.py: SystemDescription, SystemDomain, AutonomyLevel, DataCategory, DecisionType, DeploymentContext
- requirements.py: GeneratedRequirement, RequirementCategory, RequirementPriority, RequirementType, ValidationResult
- report.py: RequirementsReport, CoverageMatrix, ReportMetrics

Test coverage includes:
- Basic instantiation with valid data
- Field validators
- Default values
- Optional fields handling None
- Enum values
- Helper methods
- Edge cases (empty lists, boundary values)
- Model serialization/deserialization
- Cross-model integration
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

# Import all models
from shared.models.citations import Citation, CitationBundle
from shared.models.risk import (
    RiskLevel,
    RiskClassification,
    RiskClassificationResult,
    ProhibitedPractice,
    AnnexIIICategory,
)
from shared.models.system_description import (
    SystemDescription,
    SystemDomain,
    AutonomyLevel,
    DataCategory,
    DecisionType,
    DeploymentContext,
)
from shared.models.requirements import (
    GeneratedRequirement,
    RequirementCategory,
    RequirementPriority,
    RequirementType,
    ValidationResult,
)
from shared.models.report import (
    RequirementsReport,
    CoverageMatrix,
    ReportMetrics,
)


# ============================================================================
# CITATIONS.PY TESTS
# ============================================================================

class TestCitation:
    """Tests for the Citation model."""

    def test_basic_eu_ai_act_citation(self):
        """Test basic EU AI Act citation creation."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Risk management system shall be established."
        )
        assert citation.source == "EU_AI_ACT"
        assert citation.document_id == "eu_ai_act_2024"
        assert citation.article == "9"
        assert citation.paragraph == 1
        assert citation.reference_text == "Article 9(1)"

    def test_basic_hleg_citation(self):
        """Test basic HLEG citation creation."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            subtopic_id="resilience_to_attack",
            reference_text="Technical Robustness & Safety",
            quoted_text="AI systems should be resilient to attacks."
        )
        assert citation.source == "AI_HLEG"
        assert citation.requirement_id == "technical_robustness_and_safety"
        assert citation.subtopic_id == "resilience_to_attack"

    def test_citation_with_all_eu_ai_act_fields(self):
        """Test EU AI Act citation with all structural fields."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            chapter="III",
            section="2",
            article="9",
            paragraph=2,
            point="a",
            reference_text="Article 9(2)(a)",
            quoted_text="Test text",
            relevance_score=0.95
        )
        assert citation.chapter == "III"
        assert citation.section == "2"
        assert citation.point == "a"
        assert citation.relevance_score == 0.95

    def test_citation_with_recital(self):
        """Test EU AI Act citation with recital."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            recital=29,
            reference_text="Recital (29)",
            quoted_text="Context about harm to victims."
        )
        assert citation.recital == 29

    def test_citation_with_annex(self):
        """Test EU AI Act citation with annex reference."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            annex="III",
            annex_section="5(a)",
            reference_text="Annex III, Section 5(a)",
            quoted_text="Healthcare triage systems."
        )
        assert citation.annex == "III"
        assert citation.annex_section == "5(a)"

    def test_paragraph_coercion_from_string(self):
        """Test that paragraph field coerces string to int."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph="1",  # String input
            reference_text="Article 9(1)",
            quoted_text="Test text"
        )
        assert citation.paragraph == 1
        assert isinstance(citation.paragraph, int)

    def test_recital_coercion_from_string(self):
        """Test that recital field coerces string to int."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            recital="29",  # String input
            reference_text="Recital (29)",
            quoted_text="Test text"
        )
        assert citation.recital == 29
        assert isinstance(citation.recital, int)

    def test_relevance_score_boundary_zero(self):
        """Test relevance_score at lower boundary (0.0)."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.0
        )
        assert citation.relevance_score == 0.0

    def test_relevance_score_boundary_one(self):
        """Test relevance_score at upper boundary (1.0)."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=1.0
        )
        assert citation.relevance_score == 1.0

    def test_relevance_score_invalid_above_one(self):
        """Test that relevance_score > 1.0 raises validation error."""
        with pytest.raises(ValidationError):
            Citation(
                source="AI_HLEG",
                document_id="ai_hleg_2019",
                reference_text="Test",
                quoted_text="Test",
                relevance_score=1.5
            )

    def test_relevance_score_invalid_below_zero(self):
        """Test that relevance_score < 0.0 raises validation error."""
        with pytest.raises(ValidationError):
            Citation(
                source="AI_HLEG",
                document_id="ai_hleg_2019",
                reference_text="Test",
                quoted_text="Test",
                relevance_score=-0.1
            )

    def test_invalid_source_literal(self):
        """Test that invalid source raises validation error."""
        with pytest.raises(ValidationError):
            Citation(
                source="INVALID_SOURCE",
                document_id="test",
                reference_text="Test",
                quoted_text="Test"
            )

    def test_format_reference_article_only(self):
        """Test format_reference for article-only citation."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            reference_text="Article 9",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Article 9"

    def test_format_reference_article_with_paragraph(self):
        """Test format_reference for article with paragraph."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Article 9(1)"

    def test_format_reference_article_with_paragraph_and_point(self):
        """Test format_reference for article with paragraph and point."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=2,
            point="a",
            reference_text="Article 9(2)(a)",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Article 9(2)(a)"

    def test_format_reference_recital(self):
        """Test format_reference for recital."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            recital=29,
            reference_text="Recital (29)",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Recital (29)"

    def test_format_reference_annex_only(self):
        """Test format_reference for annex only."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            annex="III",
            reference_text="Annex III",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Annex III"

    def test_format_reference_annex_with_section(self):
        """Test format_reference for annex with section."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            annex="III",
            annex_section="5(a)",
            reference_text="Annex III, Section 5(a)",
            quoted_text="Test"
        )
        assert citation.format_reference() == "Annex III, Section 5(a)"

    def test_format_reference_hleg_without_subtopic(self):
        """Test format_reference for HLEG without subtopic."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness & Safety",
            quoted_text="Test"
        )
        assert citation.format_reference() == "HLEG: Technical Robustness & Safety"

    def test_format_reference_hleg_with_subtopic(self):
        """Test format_reference for HLEG with subtopic."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            subtopic_id="resilience_to_attack",
            reference_text="Technical Robustness & Safety",
            quoted_text="Test"
        )
        result = citation.format_reference()
        assert "HLEG: Technical Robustness & Safety" in result
        assert "Resilience To Attack" in result

    def test_format_reference_fallback_to_reference_text(self):
        """Test format_reference fallback when no structural fields set."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text="General reference",
            quoted_text="Test"
        )
        assert citation.format_reference() == "General reference"

    def test_citation_default_values(self):
        """Test that optional fields default to None."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text="Test",
            quoted_text="Test"
        )
        assert citation.chapter is None
        assert citation.section is None
        assert citation.article is None
        assert citation.paragraph is None
        assert citation.point is None
        assert citation.recital is None
        assert citation.annex is None
        assert citation.annex_section is None
        assert citation.requirement_id is None
        assert citation.subtopic_id is None
        assert citation.relevance_score is None

    def test_citation_serialization(self):
        """Test Citation model_dump serialization."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Test text"
        )
        data = citation.model_dump()
        assert data["source"] == "EU_AI_ACT"
        assert data["article"] == "9"
        assert data["paragraph"] == 1

    def test_citation_deserialization(self):
        """Test Citation model_validate deserialization."""
        data = {
            "source": "EU_AI_ACT",
            "document_id": "eu_ai_act_2024",
            "article": "9",
            "paragraph": 1,
            "reference_text": "Article 9(1)",
            "quoted_text": "Test text"
        }
        citation = Citation.model_validate(data)
        assert citation.source == "EU_AI_ACT"
        assert citation.article == "9"
        assert citation.paragraph == 1


class TestCitationBundle:
    """Tests for the CitationBundle model."""

    @pytest.fixture
    def primary_citation(self):
        """Create a primary citation for tests."""
        return Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Risk management system shall be established."
        )

    @pytest.fixture
    def supporting_citations(self):
        """Create supporting citations for tests."""
        return [
            Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article="9",
                paragraph=2,
                point="a",
                reference_text="Article 9(2)(a)",
                quoted_text="Risk identification"
            ),
            Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                recital=47,
                reference_text="Recital (47)",
                quoted_text="Context on risk management"
            ),
            Citation(
                source="AI_HLEG",
                document_id="ai_hleg_2019",
                requirement_id="technical_robustness_and_safety",
                reference_text="Technical Robustness",
                quoted_text="AI systems should be robust."
            )
        ]

    def test_basic_citation_bundle(self, primary_citation):
        """Test basic CitationBundle creation."""
        bundle = CitationBundle(
            primary=primary_citation,
            rationale="Article 9 mandates risk management."
        )
        assert bundle.primary == primary_citation
        assert bundle.supporting == []
        assert bundle.rationale == "Article 9 mandates risk management."

    def test_citation_bundle_with_supporting(self, primary_citation, supporting_citations):
        """Test CitationBundle with supporting citations."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Full rationale here."
        )
        assert len(bundle.supporting) == 3
        assert bundle.supporting[0].article == "9"
        assert bundle.supporting[0].point == "a"

    def test_all_citations_method(self, primary_citation, supporting_citations):
        """Test all_citations returns primary + supporting."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Test"
        )
        all_cites = bundle.all_citations()
        assert len(all_cites) == 4
        assert all_cites[0] == primary_citation
        assert all_cites[1:] == supporting_citations

    def test_all_citations_empty_supporting(self, primary_citation):
        """Test all_citations with no supporting."""
        bundle = CitationBundle(
            primary=primary_citation,
            rationale="Test"
        )
        all_cites = bundle.all_citations()
        assert len(all_cites) == 1
        assert all_cites[0] == primary_citation

    def test_count_by_source(self, primary_citation, supporting_citations):
        """Test count_by_source method."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Test"
        )
        counts = bundle.count_by_source()
        assert counts["EU_AI_ACT"] == 3  # primary + 2 supporting EU AI Act
        assert counts["AI_HLEG"] == 1

    def test_count_by_source_all_eu(self, primary_citation):
        """Test count_by_source with only EU AI Act citations."""
        bundle = CitationBundle(
            primary=primary_citation,
            rationale="Test"
        )
        counts = bundle.count_by_source()
        assert counts["EU_AI_ACT"] == 1
        assert counts["AI_HLEG"] == 0

    def test_get_articles_cited(self, primary_citation, supporting_citations):
        """Test get_articles_cited method."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Test"
        )
        articles = bundle.get_articles_cited()
        assert articles == ["9"]  # Only article 9 has article field set

    def test_get_articles_cited_multiple(self):
        """Test get_articles_cited with multiple articles."""
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            reference_text="Article 9",
            quoted_text="Test"
        )
        supporting = [
            Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article="10",
                reference_text="Article 10",
                quoted_text="Test"
            ),
            Citation(
                source="EU_AI_ACT",
                document_id="eu_ai_act_2024",
                article="8",
                reference_text="Article 8",
                quoted_text="Test"
            )
        ]
        bundle = CitationBundle(
            primary=primary,
            supporting=supporting,
            rationale="Test"
        )
        articles = bundle.get_articles_cited()
        assert articles == ["8", "9", "10"]  # Sorted numerically

    def test_get_hleg_requirements_cited(self, primary_citation, supporting_citations):
        """Test get_hleg_requirements_cited method."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Test"
        )
        hleg = bundle.get_hleg_requirements_cited()
        assert hleg == ["technical_robustness_and_safety"]

    def test_get_hleg_requirements_cited_multiple(self):
        """Test get_hleg_requirements_cited with multiple HLEG principles."""
        primary = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="accountability",
            reference_text="Accountability",
            quoted_text="Test"
        )
        supporting = [
            Citation(
                source="AI_HLEG",
                document_id="ai_hleg_2019",
                requirement_id="transparency",
                reference_text="Transparency",
                quoted_text="Test"
            ),
            Citation(
                source="AI_HLEG",
                document_id="ai_hleg_2019",
                requirement_id="human_agency_and_oversight",
                reference_text="Human Agency",
                quoted_text="Test"
            )
        ]
        bundle = CitationBundle(
            primary=primary,
            supporting=supporting,
            rationale="Test"
        )
        hleg = bundle.get_hleg_requirements_cited()
        assert len(hleg) == 3
        assert "accountability" in hleg
        assert "transparency" in hleg
        assert "human_agency_and_oversight" in hleg

    def test_citation_bundle_serialization(self, primary_citation, supporting_citations):
        """Test CitationBundle model_dump serialization."""
        bundle = CitationBundle(
            primary=primary_citation,
            supporting=supporting_citations,
            rationale="Test rationale"
        )
        data = bundle.model_dump()
        assert data["primary"]["source"] == "EU_AI_ACT"
        assert len(data["supporting"]) == 3
        assert data["rationale"] == "Test rationale"

    def test_citation_bundle_deserialization(self):
        """Test CitationBundle model_validate deserialization."""
        data = {
            "primary": {
                "source": "EU_AI_ACT",
                "document_id": "eu_ai_act_2024",
                "article": "9",
                "reference_text": "Article 9",
                "quoted_text": "Test"
            },
            "supporting": [],
            "rationale": "Test"
        }
        bundle = CitationBundle.model_validate(data)
        assert bundle.primary.article == "9"
        assert bundle.supporting == []


# ============================================================================
# RISK.PY TESTS
# ============================================================================

class TestRiskLevel:
    """Tests for the RiskLevel enum."""

    def test_all_risk_level_values(self):
        """Test all RiskLevel enum values."""
        assert RiskLevel.UNACCEPTABLE.value == "unacceptable"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.LIMITED.value == "limited"
        assert RiskLevel.MINIMAL.value == "minimal"

    def test_risk_level_count(self):
        """Test that there are exactly 4 risk levels."""
        assert len(RiskLevel) == 4

    def test_risk_level_string_comparison(self):
        """Test that RiskLevel can be compared as string."""
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.UNACCEPTABLE == "unacceptable"


class TestAnnexIIICategory:
    """Tests for the AnnexIIICategory enum."""

    def test_all_annex_iii_categories(self):
        """Test all AnnexIIICategory values."""
        assert AnnexIIICategory.BIOMETRICS.value == "1"
        assert AnnexIIICategory.CRITICAL_INFRASTRUCTURE.value == "2"
        assert AnnexIIICategory.EDUCATION_TRAINING.value == "3"
        assert AnnexIIICategory.EMPLOYMENT.value == "4"
        assert AnnexIIICategory.ESSENTIAL_SERVICES.value == "5"
        assert AnnexIIICategory.LAW_ENFORCEMENT.value == "6"
        assert AnnexIIICategory.MIGRATION_ASYLUM.value == "7"
        assert AnnexIIICategory.JUSTICE_DEMOCRACY.value == "8"

    def test_annex_iii_category_count(self):
        """Test that there are exactly 8 Annex III categories."""
        assert len(AnnexIIICategory) == 8


class TestProhibitedPractice:
    """Tests for the ProhibitedPractice enum."""

    def test_all_prohibited_practices(self):
        """Test all ProhibitedPractice values."""
        assert ProhibitedPractice.SUBLIMINAL_MANIPULATION.value == "5_1_a"
        assert ProhibitedPractice.EXPLOITATION_VULNERABILITY.value == "5_1_b"
        assert ProhibitedPractice.SOCIAL_SCORING.value == "5_1_c"
        assert ProhibitedPractice.CRIME_PREDICTION_PROFILING.value == "5_1_d"
        assert ProhibitedPractice.FACIAL_SCRAPING.value == "5_1_e"
        assert ProhibitedPractice.EMOTION_INFERENCE_WORKPLACE.value == "5_1_f"
        assert ProhibitedPractice.BIOMETRIC_CATEGORIZATION.value == "5_1_g"
        assert ProhibitedPractice.REAL_TIME_BIOMETRIC_PUBLIC.value == "5_1_h"

    def test_prohibited_practice_count(self):
        """Test that there are exactly 8 prohibited practices."""
        assert len(ProhibitedPractice) == 8


class TestRiskClassification:
    """Tests for the RiskClassification model."""

    @pytest.fixture
    def minimal_legal_basis(self):
        """Create minimal legal basis for tests."""
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Test"
        )
        return CitationBundle(
            primary=primary,
            rationale="Risk classification rationale"
        )

    def test_basic_high_risk_classification(self, minimal_legal_basis):
        """Test basic HIGH risk classification."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="This system is high risk because..."
        )
        assert classification.level == RiskLevel.HIGH
        assert classification.reasoning == "This system is high risk because..."

    def test_unacceptable_risk_with_prohibition(self, minimal_legal_basis):
        """Test UNACCEPTABLE risk with prohibited practice."""
        classification = RiskClassification(
            level=RiskLevel.UNACCEPTABLE,
            legal_basis=minimal_legal_basis,
            prohibited_practice=ProhibitedPractice.SOCIAL_SCORING,
            prohibition_details="System implements social scoring.",
            reasoning="Prohibited under Article 5(1)(c)"
        )
        assert classification.level == RiskLevel.UNACCEPTABLE
        assert classification.prohibited_practice == ProhibitedPractice.SOCIAL_SCORING
        assert classification.is_prohibited() is True

    def test_high_risk_with_annex_iii(self, minimal_legal_basis):
        """Test HIGH risk with Annex III category."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            annex_iii_category=AnnexIIICategory.ESSENTIAL_SERVICES,
            annex_iii_subcategory="5(a)",
            applicable_articles=["8", "9", "10", "11", "12", "13", "14", "15"],
            article_6_3_exception_checked=True,
            article_6_3_rationale="Not a narrow procedural task.",
            reasoning="Healthcare triage system"
        )
        assert classification.annex_iii_category == AnnexIIICategory.ESSENTIAL_SERVICES
        assert classification.annex_iii_subcategory == "5(a)"
        assert "9" in classification.applicable_articles

    def test_is_prohibited_method(self, minimal_legal_basis):
        """Test is_prohibited helper method."""
        prohibited = RiskClassification(
            level=RiskLevel.UNACCEPTABLE,
            legal_basis=minimal_legal_basis,
            reasoning="Prohibited"
        )
        not_prohibited = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="High risk"
        )
        assert prohibited.is_prohibited() is True
        assert not_prohibited.is_prohibited() is False

    def test_requires_chapter_iii_compliance(self, minimal_legal_basis):
        """Test requires_chapter_iii_compliance helper method."""
        high = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="High"
        )
        limited = RiskClassification(
            level=RiskLevel.LIMITED,
            legal_basis=minimal_legal_basis,
            reasoning="Limited"
        )
        assert high.requires_chapter_iii_compliance() is True
        assert limited.requires_chapter_iii_compliance() is False

    def test_requires_transparency_only(self, minimal_legal_basis):
        """Test requires_transparency_only helper method."""
        limited = RiskClassification(
            level=RiskLevel.LIMITED,
            legal_basis=minimal_legal_basis,
            reasoning="Limited"
        )
        high = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="High"
        )
        assert limited.requires_transparency_only() is True
        assert high.requires_transparency_only() is False

    def test_get_applicable_article_range_none(self, minimal_legal_basis):
        """Test get_applicable_article_range with no articles."""
        classification = RiskClassification(
            level=RiskLevel.MINIMAL,
            legal_basis=minimal_legal_basis,
            applicable_articles=[],
            reasoning="Minimal"
        )
        assert classification.get_applicable_article_range() == "None"

    def test_get_applicable_article_range_single(self, minimal_legal_basis):
        """Test get_applicable_article_range with single article."""
        classification = RiskClassification(
            level=RiskLevel.LIMITED,
            legal_basis=minimal_legal_basis,
            applicable_articles=["50"],
            reasoning="Limited"
        )
        assert classification.get_applicable_article_range() == "Article 50"

    def test_get_applicable_article_range_multiple(self, minimal_legal_basis):
        """Test get_applicable_article_range with multiple articles."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            applicable_articles=["8", "9", "10", "15"],
            reasoning="High"
        )
        assert classification.get_applicable_article_range() == "Articles 8-15"

    def test_confidence_default(self, minimal_legal_basis):
        """Test confidence default value."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="Test"
        )
        assert classification.confidence == 1.0

    def test_confidence_boundary_zero(self, minimal_legal_basis):
        """Test confidence at boundary 0.0."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="Test",
            confidence=0.0
        )
        assert classification.confidence == 0.0

    def test_confidence_boundary_one(self, minimal_legal_basis):
        """Test confidence at boundary 1.0."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="Test",
            confidence=1.0
        )
        assert classification.confidence == 1.0

    def test_confidence_invalid_above_one(self, minimal_legal_basis):
        """Test confidence > 1.0 raises error."""
        with pytest.raises(ValidationError):
            RiskClassification(
                level=RiskLevel.HIGH,
                legal_basis=minimal_legal_basis,
                reasoning="Test",
                confidence=1.5
            )

    def test_confidence_invalid_below_zero(self, minimal_legal_basis):
        """Test confidence < 0.0 raises error."""
        with pytest.raises(ValidationError):
            RiskClassification(
                level=RiskLevel.HIGH,
                legal_basis=minimal_legal_basis,
                reasoning="Test",
                confidence=-0.1
            )

    def test_hleg_implications_default(self, minimal_legal_basis):
        """Test hleg_implications default empty list."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="Test"
        )
        assert classification.hleg_implications == []

    def test_with_hleg_implications(self, minimal_legal_basis):
        """Test with HLEG implications."""
        hleg_citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness",
            quoted_text="Test"
        )
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            hleg_implications=[hleg_citation],
            reasoning="Test"
        )
        assert len(classification.hleg_implications) == 1
        assert classification.hleg_implications[0].requirement_id == "technical_robustness_and_safety"

    def test_risk_classification_serialization(self, minimal_legal_basis):
        """Test RiskClassification serialization."""
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=minimal_legal_basis,
            reasoning="Test"
        )
        data = classification.model_dump()
        assert data["level"] == "high"
        assert "legal_basis" in data

    def test_risk_classification_deserialization(self):
        """Test RiskClassification deserialization."""
        data = {
            "level": "high",
            "legal_basis": {
                "primary": {
                    "source": "EU_AI_ACT",
                    "document_id": "eu_ai_act_2024",
                    "reference_text": "Test",
                    "quoted_text": "Test"
                },
                "supporting": [],
                "rationale": "Test"
            },
            "reasoning": "Test reasoning"
        }
        classification = RiskClassification.model_validate(data)
        assert classification.level == RiskLevel.HIGH


class TestRiskClassificationResult:
    """Tests for the RiskClassificationResult model."""

    def test_basic_risk_classification_result(self):
        """Test basic RiskClassificationResult creation."""
        result = RiskClassificationResult(
            risk_level=RiskLevel.HIGH,
            legal_basis_text="Risk management system shall be established.",
            reasoning="High risk because..."
        )
        assert result.risk_level == RiskLevel.HIGH
        assert result.legal_basis_article is None

    def test_risk_classification_result_with_all_fields(self):
        """Test RiskClassificationResult with all fields."""
        result = RiskClassificationResult(
            risk_level=RiskLevel.HIGH,
            legal_basis_article="Annex III, 5(a)",
            legal_basis_text="Healthcare triage systems.",
            annex_category="5",
            article_6_exception=False,
            hleg_principles=["technical_robustness_and_safety", "accountability"],
            reasoning="Healthcare system falls under Annex III."
        )
        assert result.legal_basis_article == "Annex III, 5(a)"
        assert result.annex_category == "5"
        assert result.article_6_exception is False
        assert len(result.hleg_principles) == 2

    def test_risk_classification_result_defaults(self):
        """Test RiskClassificationResult default values."""
        result = RiskClassificationResult(
            risk_level=RiskLevel.MINIMAL,
            legal_basis_text="No specific obligations.",
            reasoning="Minimal risk system."
        )
        assert result.legal_basis_article is None
        assert result.annex_category is None
        assert result.article_6_exception is False
        assert result.hleg_principles == []


# ============================================================================
# SYSTEM_DESCRIPTION.PY TESTS
# ============================================================================

class TestSystemDomain:
    """Tests for the SystemDomain enum."""

    def test_all_system_domain_values(self):
        """Test all SystemDomain enum values."""
        expected_domains = [
            "healthcare", "education", "employment", "finance",
            "law_enforcement", "justice", "migration", "critical_infrastructure",
            "biometrics", "social_services", "transport", "energy",
            "consumer", "entertainment", "general", "other"
        ]
        actual_domains = [d.value for d in SystemDomain]
        assert sorted(actual_domains) == sorted(expected_domains)

    def test_system_domain_count(self):
        """Test SystemDomain count."""
        assert len(SystemDomain) == 16


class TestAutonomyLevel:
    """Tests for the AutonomyLevel enum."""

    def test_all_autonomy_levels(self):
        """Test all AutonomyLevel values."""
        assert AutonomyLevel.FULL.value == "full"
        assert AutonomyLevel.PARTIAL.value == "partial"
        assert AutonomyLevel.ADVISORY.value == "advisory"
        assert AutonomyLevel.ASSISTIVE.value == "assistive"

    def test_autonomy_level_count(self):
        """Test that there are 4 autonomy levels."""
        assert len(AutonomyLevel) == 4


class TestDeploymentContext:
    """Tests for the DeploymentContext enum."""

    def test_all_deployment_contexts(self):
        """Test all DeploymentContext values."""
        expected = [
            "public_sector", "private_sector", "healthcare_facility",
            "educational_institution", "workplace", "public_space",
            "online_platform", "critical_infrastructure", "law_enforcement",
            "border_control", "consumer_product", "research", "other"
        ]
        actual = [d.value for d in DeploymentContext]
        assert sorted(actual) == sorted(expected)

    def test_deployment_context_count(self):
        """Test DeploymentContext count."""
        assert len(DeploymentContext) == 13


class TestDataCategory:
    """Tests for the DataCategory enum."""

    def test_all_data_categories(self):
        """Test all DataCategory values."""
        expected = [
            "biometric", "health", "financial", "behavioral", "location",
            "communication", "social", "employment", "educational",
            "criminal", "genetic", "political", "religious",
            "sexual_orientation", "personal_identifiable", "anonymized",
            "synthetic", "public", "other"
        ]
        actual = [d.value for d in DataCategory]
        assert sorted(actual) == sorted(expected)

    def test_data_category_count(self):
        """Test DataCategory count."""
        assert len(DataCategory) == 19


class TestDecisionType:
    """Tests for the DecisionType enum."""

    def test_all_decision_types(self):
        """Test all DecisionType values."""
        expected = [
            "access_denial", "resource_allocation", "ranking", "assessment",
            "prediction", "recommendation", "classification", "identification",
            "content_generation", "content_moderation", "automation",
            "monitoring", "other"
        ]
        actual = [d.value for d in DecisionType]
        assert sorted(actual) == sorted(expected)

    def test_decision_type_count(self):
        """Test DecisionType count."""
        assert len(DecisionType) == 13


class TestSystemDescription:
    """Tests for the SystemDescription model."""

    def test_minimal_system_description(self):
        """Test minimal SystemDescription creation."""
        desc = SystemDescription(
            raw_description="A healthcare triage system.",
            purpose="Prioritize emergency room patients."
        )
        assert desc.raw_description == "A healthcare triage system."
        assert desc.purpose == "Prioritize emergency room patients."

    def test_system_description_defaults(self):
        """Test SystemDescription default values."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test purpose"
        )
        assert desc.name is None
        assert desc.domain == SystemDomain.GENERAL
        assert desc.secondary_domains == []
        assert desc.intended_users == []
        assert desc.affected_persons == []
        assert desc.data_types == []
        assert desc.data_types_detail == []
        assert desc.decision_types == []
        assert desc.decision_types_detail == []
        assert desc.autonomy_level == AutonomyLevel.ADVISORY
        assert desc.deployment_context == DeploymentContext.OTHER
        assert desc.deployment_scale is None
        assert desc.affects_fundamental_rights is False
        assert desc.safety_critical is False
        assert desc.biometric_processing is False
        assert desc.real_time_biometric is False
        assert desc.law_enforcement_use is False
        assert desc.critical_infrastructure is False
        assert desc.vulnerable_groups is False
        assert desc.emotion_recognition is False
        assert desc.social_scoring is False
        assert desc.subliminal_techniques is False
        assert desc.extraction_confidence == 1.0
        assert desc.ambiguities == []
        assert desc.assumptions == []

    def test_full_system_description(self):
        """Test SystemDescription with all fields."""
        desc = SystemDescription(
            raw_description="TrustTriage is a healthcare AI system.",
            name="TrustTriage",
            domain=SystemDomain.HEALTHCARE,
            secondary_domains=[SystemDomain.SOCIAL_SERVICES],
            purpose="Emergency room patient triage",
            intended_users=["nurses", "doctors"],
            affected_persons=["patients"],
            data_types=[DataCategory.HEALTH, DataCategory.BIOMETRIC],
            data_types_detail=["vital signs", "medical history"],
            decision_types=[DecisionType.RANKING, DecisionType.ASSESSMENT],
            decision_types_detail=["triage priority"],
            autonomy_level=AutonomyLevel.ADVISORY,
            deployment_context=DeploymentContext.HEALTHCARE_FACILITY,
            deployment_scale="single hospital",
            affects_fundamental_rights=True,
            safety_critical=True,
            biometric_processing=False,
            vulnerable_groups=True,
            extraction_confidence=0.95,
            ambiguities=["unclear if real-time"],
            assumptions=["EU deployment assumed"]
        )
        assert desc.name == "TrustTriage"
        assert desc.domain == SystemDomain.HEALTHCARE
        assert len(desc.data_types) == 2
        assert desc.safety_critical is True

    def test_has_prohibited_indicators_social_scoring(self):
        """Test has_prohibited_indicators with social scoring."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            social_scoring=True
        )
        assert desc.has_prohibited_indicators() is True

    def test_has_prohibited_indicators_subliminal(self):
        """Test has_prohibited_indicators with subliminal techniques."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            subliminal_techniques=True
        )
        assert desc.has_prohibited_indicators() is True

    def test_has_prohibited_indicators_real_time_biometric_law_enforcement(self):
        """Test has_prohibited_indicators with real-time biometric + law enforcement."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            real_time_biometric=True,
            law_enforcement_use=True
        )
        assert desc.has_prohibited_indicators() is True

    def test_has_prohibited_indicators_false(self):
        """Test has_prohibited_indicators returns False for safe system."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test"
        )
        assert desc.has_prohibited_indicators() is False

    def test_has_high_risk_indicators_safety_critical(self):
        """Test has_high_risk_indicators with safety critical."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            safety_critical=True
        )
        assert desc.has_high_risk_indicators() is True

    def test_has_high_risk_indicators_healthcare_domain(self):
        """Test has_high_risk_indicators with healthcare domain."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            domain=SystemDomain.HEALTHCARE
        )
        assert desc.has_high_risk_indicators() is True

    def test_has_high_risk_indicators_biometric(self):
        """Test has_high_risk_indicators with biometric processing."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            biometric_processing=True
        )
        assert desc.has_high_risk_indicators() is True

    def test_has_high_risk_indicators_false(self):
        """Test has_high_risk_indicators returns False for low-risk system."""
        desc = SystemDescription(
            raw_description="Entertainment chatbot",
            purpose="Provide entertainment",
            domain=SystemDomain.ENTERTAINMENT
        )
        assert desc.has_high_risk_indicators() is False

    def test_to_features_dict(self):
        """Test to_features_dict method."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test purpose",
            domain=SystemDomain.HEALTHCARE,
            secondary_domains=[SystemDomain.EDUCATION],
            intended_users=["doctors"],
            affected_persons=["patients"],
            data_types=[DataCategory.HEALTH],
            decision_types=[DecisionType.ASSESSMENT],
            autonomy_level=AutonomyLevel.ADVISORY,
            deployment_context=DeploymentContext.HEALTHCARE_FACILITY,
            safety_critical=True,
            biometric_processing=False
        )
        features = desc.to_features_dict()
        assert features["domain"] == "healthcare"
        assert features["secondary_domains"] == ["education"]
        assert features["purpose"] == "Test purpose"
        assert features["raw_description"] == "Test"  # Phase 5: raw_description for keyword detection
        assert features["safety_critical"] is True
        assert features["biometric_processing"] is False
        assert "health" in features["data_types"]

    def test_extraction_confidence_boundary_zero(self):
        """Test extraction_confidence at boundary 0.0."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            extraction_confidence=0.0
        )
        assert desc.extraction_confidence == 0.0

    def test_extraction_confidence_boundary_one(self):
        """Test extraction_confidence at boundary 1.0."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            extraction_confidence=1.0
        )
        assert desc.extraction_confidence == 1.0

    def test_extraction_confidence_invalid_above_one(self):
        """Test extraction_confidence > 1.0 raises error."""
        with pytest.raises(ValidationError):
            SystemDescription(
                raw_description="Test",
                purpose="Test",
                extraction_confidence=1.5
            )

    def test_extraction_confidence_invalid_below_zero(self):
        """Test extraction_confidence < 0.0 raises error."""
        with pytest.raises(ValidationError):
            SystemDescription(
                raw_description="Test",
                purpose="Test",
                extraction_confidence=-0.1
            )

    def test_system_description_serialization(self):
        """Test SystemDescription serialization."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            domain=SystemDomain.HEALTHCARE,
            safety_critical=True
        )
        data = desc.model_dump()
        assert data["domain"] == "healthcare"
        assert data["safety_critical"] is True

    def test_system_description_deserialization(self):
        """Test SystemDescription deserialization."""
        data = {
            "raw_description": "Test",
            "purpose": "Test purpose",
            "domain": "healthcare",
            "safety_critical": True
        }
        desc = SystemDescription.model_validate(data)
        assert desc.domain == SystemDomain.HEALTHCARE
        assert desc.safety_critical is True


# ============================================================================
# REQUIREMENTS.PY TESTS
# ============================================================================

class TestRequirementCategory:
    """Tests for the RequirementCategory enum."""

    def test_all_requirement_categories(self):
        """Test all RequirementCategory values."""
        expected = [
            "risk_management", "data_governance", "documentation",
            "record_keeping", "transparency", "human_oversight",
            "accuracy_robustness", "provider_obligations", "deployer_obligations",
            "importer_obligations", "distributor_obligations", "product_integration",
            "transparency_limited", "conformity", "general"
        ]
        actual = [c.value for c in RequirementCategory]
        assert sorted(actual) == sorted(expected)

    def test_requirement_category_count(self):
        """Test RequirementCategory count."""
        assert len(RequirementCategory) == 15


class TestRequirementPriority:
    """Tests for the RequirementPriority enum."""

    def test_all_requirement_priorities(self):
        """Test all RequirementPriority values."""
        assert RequirementPriority.CRITICAL.value == "critical"
        assert RequirementPriority.HIGH.value == "high"
        assert RequirementPriority.MEDIUM.value == "medium"
        assert RequirementPriority.LOW.value == "low"

    def test_requirement_priority_count(self):
        """Test RequirementPriority count."""
        assert len(RequirementPriority) == 4


class TestRequirementType:
    """Tests for the RequirementType enum."""

    def test_all_requirement_types(self):
        """Test all RequirementType values."""
        assert RequirementType.MANDATORY.value == "mandatory"
        assert RequirementType.RECOMMENDED.value == "recommended"
        assert RequirementType.OPTIONAL.value == "optional"

    def test_requirement_type_count(self):
        """Test RequirementType count."""
        assert len(RequirementType) == 3


class TestGeneratedRequirement:
    """Tests for the GeneratedRequirement model."""

    def test_minimal_requirement(self):
        """Test minimal GeneratedRequirement creation."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Risk Management System",
            statement="The system SHALL implement risk management.",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.HIGH,
            rationale="Article 9 mandates risk management."
        )
        assert req.id == "REQ-001"
        assert req.title == "Risk Management System"
        assert req.category == RequirementCategory.RISK_MANAGEMENT
        assert req.priority == RequirementPriority.HIGH

    def test_requirement_defaults(self):
        """Test GeneratedRequirement default values."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test statement",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test rationale"
        )
        assert req.requirement_type == RequirementType.MANDATORY
        assert req.eu_ai_act_citations == []
        assert req.hleg_citations == []
        assert req.supporting_recitals == []
        assert req.context is None
        assert req.verification_criteria == []
        assert req.verification_method is None
        assert req.derived_from_articles == []
        assert req.addresses_hleg_principles == []
        assert req.addresses_hleg_subtopics == []
        assert req.parent_requirement_id is None
        assert req.related_requirements == []

    def test_full_requirement(self):
        """Test GeneratedRequirement with all fields."""
        eu_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Risk management system"
        )
        hleg_citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness",
            quoted_text="Test",
            relevance_score=0.95
        )
        recital_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            recital=47,
            reference_text="Recital (47)",
            quoted_text="Context"
        )

        req = GeneratedRequirement(
            id="REQ-001",
            title="Risk Management System",
            statement="The system SHALL implement risk management.",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.CRITICAL,
            requirement_type=RequirementType.MANDATORY,
            eu_ai_act_citations=[eu_citation],
            hleg_citations=[hleg_citation],
            supporting_recitals=[recital_citation],
            rationale="Article 9 mandates risk management.",
            context="Healthcare triage system context.",
            verification_criteria=["Has documented risk assessment", "Implements mitigation"],
            verification_method="documentation audit",
            derived_from_articles=["9"],
            addresses_hleg_principles=["technical_robustness_and_safety"],
            addresses_hleg_subtopics=["resilience_to_attack"],
            parent_requirement_id=None,
            related_requirements=["REQ-002", "REQ-003"]
        )
        assert len(req.eu_ai_act_citations) == 1
        assert len(req.hleg_citations) == 1
        assert len(req.verification_criteria) == 2

    def test_get_primary_article_exists(self):
        """Test get_primary_article when articles exist."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.HIGH,
            rationale="Test",
            derived_from_articles=["9", "10"]
        )
        assert req.get_primary_article() == "9"

    def test_get_primary_article_empty(self):
        """Test get_primary_article when no articles."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test"
        )
        assert req.get_primary_article() is None

    def test_get_citation_count(self):
        """Test get_citation_count method."""
        eu_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            reference_text="Test",
            quoted_text="Test"
        )
        hleg_citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            reference_text="Test",
            quoted_text="Test"
        )
        recital = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            recital=47,
            reference_text="Test",
            quoted_text="Test"
        )
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test",
            eu_ai_act_citations=[eu_citation, eu_citation],
            hleg_citations=[hleg_citation],
            supporting_recitals=[recital, recital, recital]
        )
        assert req.get_citation_count() == 6

    def test_get_citation_count_empty(self):
        """Test get_citation_count with no citations."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test"
        )
        assert req.get_citation_count() == 0

    def test_get_hleg_relevance_summary(self):
        """Test get_hleg_relevance_summary method."""
        hleg1 = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.95
        )
        hleg2 = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="accountability",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.82
        )
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test",
            hleg_citations=[hleg1, hleg2]
        )
        summary = req.get_hleg_relevance_summary()
        assert summary["technical_robustness_and_safety"] == 0.95
        assert summary["accountability"] == 0.82

    def test_get_hleg_relevance_summary_max_score(self):
        """Test get_hleg_relevance_summary takes max score for duplicates."""
        hleg1 = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.80
        )
        hleg2 = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.95
        )
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test",
            hleg_citations=[hleg1, hleg2]
        )
        summary = req.get_hleg_relevance_summary()
        assert summary["technical_robustness_and_safety"] == 0.95

    def test_get_hleg_relevance_summary_empty(self):
        """Test get_hleg_relevance_summary with no HLEG citations."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test"
        )
        summary = req.get_hleg_relevance_summary()
        assert summary == {}

    def test_format_statement(self):
        """Test format_statement method."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="The system SHALL implement X.",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.CRITICAL,
            rationale="Test"
        )
        formatted = req.format_statement()
        assert "[REQ-001]" in formatted
        assert "The system SHALL implement X." in formatted

    def test_requirement_serialization(self):
        """Test GeneratedRequirement serialization."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.HIGH,
            rationale="Test"
        )
        data = req.model_dump()
        assert data["id"] == "REQ-001"
        assert data["category"] == "risk_management"
        assert data["priority"] == "high"

    def test_requirement_deserialization(self):
        """Test GeneratedRequirement deserialization."""
        data = {
            "id": "REQ-001",
            "title": "Test",
            "statement": "Test",
            "category": "risk_management",
            "priority": "high",
            "rationale": "Test"
        }
        req = GeneratedRequirement.model_validate(data)
        assert req.id == "REQ-001"
        assert req.category == RequirementCategory.RISK_MANAGEMENT


class TestValidationResult:
    """Tests for the ValidationResult model."""

    def test_minimal_validation_result(self):
        """Test minimal ValidationResult creation."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.71,
            subtopic_coverage=0.65
        )
        assert result.article_coverage == 0.85
        assert result.hleg_coverage == 0.71
        assert result.subtopic_coverage == 0.65

    def test_validation_result_defaults(self):
        """Test ValidationResult default values."""
        result = ValidationResult(
            article_coverage=0.8,
            hleg_coverage=0.7,
            subtopic_coverage=0.6
        )
        assert result.covered_articles == []
        assert result.missing_articles == []
        assert result.covered_hleg_principles == []
        assert result.missing_hleg_principles == []
        assert result.covered_subtopics == []
        assert result.has_conflicts is False
        assert result.conflicts == []
        assert result.all_citations_valid is True
        assert result.invalid_citations == []
        assert result.is_complete is False
        assert result.is_consistent is True
        assert result.is_valid is True
        assert result.recommendations == []

    def test_full_validation_result(self):
        """Test ValidationResult with all fields."""
        result = ValidationResult(
            article_coverage=0.95,
            hleg_coverage=0.85,
            subtopic_coverage=0.75,
            covered_articles=["8", "9", "10", "11", "12", "13", "14", "15"],
            missing_articles=["16"],
            covered_hleg_principles=["technical_robustness_and_safety", "accountability"],
            missing_hleg_principles=["transparency"],
            covered_subtopics=["resilience_to_attack"],
            has_conflicts=False,
            conflicts=[],
            all_citations_valid=True,
            invalid_citations=[],
            is_complete=True,
            is_consistent=True,
            is_valid=True,
            recommendations=["Consider adding more transparency requirements."]
        )
        assert result.is_complete is True
        assert len(result.covered_articles) == 8

    def test_coverage_boundary_zero(self):
        """Test coverage fields at boundary 0.0."""
        result = ValidationResult(
            article_coverage=0.0,
            hleg_coverage=0.0,
            subtopic_coverage=0.0
        )
        assert result.article_coverage == 0.0
        assert result.hleg_coverage == 0.0
        assert result.subtopic_coverage == 0.0

    def test_coverage_boundary_one(self):
        """Test coverage fields at boundary 1.0."""
        result = ValidationResult(
            article_coverage=1.0,
            hleg_coverage=1.0,
            subtopic_coverage=1.0
        )
        assert result.article_coverage == 1.0
        assert result.hleg_coverage == 1.0
        assert result.subtopic_coverage == 1.0

    def test_coverage_invalid_above_one(self):
        """Test coverage > 1.0 raises error."""
        with pytest.raises(ValidationError):
            ValidationResult(
                article_coverage=1.5,
                hleg_coverage=0.7,
                subtopic_coverage=0.6
            )

    def test_coverage_invalid_below_zero(self):
        """Test coverage < 0.0 raises error."""
        with pytest.raises(ValidationError):
            ValidationResult(
                article_coverage=-0.1,
                hleg_coverage=0.7,
                subtopic_coverage=0.6
            )

    def test_is_acceptable_true(self):
        """Test is_acceptable returns True for good results."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.75,
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=True
        )
        assert result.is_acceptable() is True

    def test_is_acceptable_false_low_article_coverage(self):
        """Test is_acceptable returns False for low article coverage."""
        result = ValidationResult(
            article_coverage=0.75,  # Below 0.8
            hleg_coverage=0.75,
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=True
        )
        assert result.is_acceptable() is False

    def test_is_acceptable_false_low_hleg_coverage(self):
        """Test is_acceptable returns False for low HLEG coverage."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.65,  # Below 0.7
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=True
        )
        assert result.is_acceptable() is False

    def test_is_acceptable_false_inconsistent(self):
        """Test is_acceptable returns False when inconsistent."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.75,
            subtopic_coverage=0.65,
            is_consistent=False,
            is_valid=True
        )
        assert result.is_acceptable() is False

    def test_is_acceptable_false_invalid(self):
        """Test is_acceptable returns False when invalid."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.75,
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=False
        )
        assert result.is_acceptable() is False

    def test_is_acceptable_boundary_article_coverage(self):
        """Test is_acceptable at exactly 0.8 article coverage."""
        result = ValidationResult(
            article_coverage=0.8,  # Exactly 0.8
            hleg_coverage=0.7,
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=True
        )
        assert result.is_acceptable() is True

    def test_is_acceptable_boundary_hleg_coverage(self):
        """Test is_acceptable at exactly 0.7 HLEG coverage."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.7,  # Exactly 0.7
            subtopic_coverage=0.65,
            is_consistent=True,
            is_valid=True
        )
        assert result.is_acceptable() is True

    def test_validation_result_serialization(self):
        """Test ValidationResult serialization."""
        result = ValidationResult(
            article_coverage=0.85,
            hleg_coverage=0.75,
            subtopic_coverage=0.65
        )
        data = result.model_dump()
        assert data["article_coverage"] == 0.85
        assert data["hleg_coverage"] == 0.75

    def test_validation_result_deserialization(self):
        """Test ValidationResult deserialization."""
        data = {
            "article_coverage": 0.85,
            "hleg_coverage": 0.75,
            "subtopic_coverage": 0.65
        }
        result = ValidationResult.model_validate(data)
        assert result.article_coverage == 0.85


# ============================================================================
# REPORT.PY TESTS
# ============================================================================

class TestCoverageMatrix:
    """Tests for the CoverageMatrix model."""

    def test_empty_coverage_matrix(self):
        """Test empty CoverageMatrix creation."""
        matrix = CoverageMatrix()
        assert matrix.hleg_to_requirements == {}
        assert matrix.subtopic_to_requirements == {}
        assert matrix.article_to_requirements == {}
        assert matrix.requirement_to_articles == {}
        assert matrix.requirement_to_hleg == {}

    def test_coverage_matrix_with_data(self):
        """Test CoverageMatrix with data."""
        matrix = CoverageMatrix(
            hleg_to_requirements={
                "technical_robustness_and_safety": ["REQ-001", "REQ-002"],
                "accountability": ["REQ-003"]
            },
            article_to_requirements={
                "9": ["REQ-001", "REQ-002"],
                "10": ["REQ-003"]
            },
            requirement_to_articles={
                "REQ-001": ["9"],
                "REQ-002": ["9"],
                "REQ-003": ["10"]
            }
        )
        assert len(matrix.hleg_to_requirements["technical_robustness_and_safety"]) == 2
        assert matrix.article_to_requirements["9"] == ["REQ-001", "REQ-002"]

    def test_get_uncovered_articles(self):
        """Test get_uncovered_articles method."""
        matrix = CoverageMatrix(
            article_to_requirements={
                "9": ["REQ-001"],
                "10": ["REQ-002"]
            }
        )
        applicable = ["8", "9", "10", "11", "12"]
        uncovered = matrix.get_uncovered_articles(applicable)
        assert uncovered == ["8", "11", "12"]

    def test_get_uncovered_articles_all_covered(self):
        """Test get_uncovered_articles when all covered."""
        matrix = CoverageMatrix(
            article_to_requirements={
                "9": ["REQ-001"],
                "10": ["REQ-002"]
            }
        )
        applicable = ["9", "10"]
        uncovered = matrix.get_uncovered_articles(applicable)
        assert uncovered == []

    def test_get_uncovered_hleg(self):
        """Test get_uncovered_hleg method."""
        matrix = CoverageMatrix(
            hleg_to_requirements={
                "technical_robustness_and_safety": ["REQ-001"],
                "accountability": ["REQ-002"]
            }
        )
        uncovered = matrix.get_uncovered_hleg()
        assert len(uncovered) == 5  # 7 total - 2 covered
        assert "technical_robustness_and_safety" not in uncovered
        assert "accountability" not in uncovered
        assert "transparency" in uncovered

    def test_get_uncovered_hleg_all_covered(self):
        """Test get_uncovered_hleg when all covered."""
        matrix = CoverageMatrix(
            hleg_to_requirements={
                "human_agency_and_oversight": ["REQ-001"],
                "technical_robustness_and_safety": ["REQ-002"],
                "privacy_and_data_governance": ["REQ-003"],
                "transparency": ["REQ-004"],
                "diversity_non_discrimination_and_fairness": ["REQ-005"],
                "societal_and_environmental_wellbeing": ["REQ-006"],
                "accountability": ["REQ-007"]
            }
        )
        uncovered = matrix.get_uncovered_hleg()
        assert uncovered == []

    def test_coverage_matrix_serialization(self):
        """Test CoverageMatrix serialization."""
        matrix = CoverageMatrix(
            hleg_to_requirements={"accountability": ["REQ-001"]}
        )
        data = matrix.model_dump()
        assert data["hleg_to_requirements"] == {"accountability": ["REQ-001"]}


class TestReportMetrics:
    """Tests for the ReportMetrics model."""

    def test_report_metrics_defaults(self):
        """Test ReportMetrics default values."""
        metrics = ReportMetrics()
        assert metrics.total_citations == 0
        assert metrics.eu_ai_act_citations == 0
        assert metrics.hleg_citations == 0
        assert metrics.recital_citations == 0
        assert metrics.unique_articles_cited == 0
        assert metrics.unique_paragraphs_cited == 0
        assert metrics.unique_recitals_cited == 0
        assert metrics.unique_hleg_principles_addressed == 0
        assert metrics.unique_hleg_subtopics_addressed == 0
        assert metrics.article_coverage_percentage == 0.0
        assert metrics.hleg_coverage_percentage == 0.0
        assert metrics.total_requirements == 0
        assert metrics.critical_requirements == 0
        assert metrics.high_requirements == 0

    def test_report_metrics_with_data(self):
        """Test ReportMetrics with data."""
        metrics = ReportMetrics(
            total_citations=50,
            eu_ai_act_citations=35,
            hleg_citations=10,
            recital_citations=5,
            unique_articles_cited=8,
            unique_paragraphs_cited=20,
            unique_recitals_cited=5,
            unique_hleg_principles_addressed=5,
            unique_hleg_subtopics_addressed=15,
            article_coverage_percentage=95.5,
            hleg_coverage_percentage=71.4,
            total_requirements=25,
            critical_requirements=5,
            high_requirements=10
        )
        assert metrics.total_citations == 50
        assert metrics.hleg_coverage_percentage == 71.4

    def test_report_metrics_serialization(self):
        """Test ReportMetrics serialization."""
        metrics = ReportMetrics(total_requirements=10)
        data = metrics.model_dump()
        assert data["total_requirements"] == 10


class TestRequirementsReport:
    """Tests for the RequirementsReport model."""

    @pytest.fixture
    def minimal_system_description(self):
        """Create minimal system description for tests."""
        return SystemDescription(
            raw_description="Healthcare triage system",
            purpose="Prioritize emergency room patients"
        )

    @pytest.fixture
    def minimal_risk_classification(self):
        """Create minimal risk classification for tests."""
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            annex="III",
            annex_section="5(a)",
            reference_text="Annex III, 5(a)",
            quoted_text="Healthcare triage"
        )
        legal_basis = CitationBundle(
            primary=primary,
            rationale="Healthcare triage system under Annex III"
        )
        return RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=legal_basis,
            applicable_articles=["8", "9", "10", "11", "12", "13", "14", "15"],
            reasoning="High risk healthcare system"
        )

    @pytest.fixture
    def sample_requirements(self):
        """Create sample requirements for tests."""
        eu_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Risk management"
        )
        hleg_citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness",
            quoted_text="Test",
            relevance_score=0.9
        )
        return [
            GeneratedRequirement(
                id="REQ-001",
                title="Risk Management",
                statement="SHALL implement risk management",
                category=RequirementCategory.RISK_MANAGEMENT,
                priority=RequirementPriority.CRITICAL,
                rationale="Test",
                eu_ai_act_citations=[eu_citation],
                hleg_citations=[hleg_citation],
                derived_from_articles=["9"],
                addresses_hleg_principles=["technical_robustness_and_safety"]
            ),
            GeneratedRequirement(
                id="REQ-002",
                title="Data Governance",
                statement="SHALL implement data governance",
                category=RequirementCategory.DATA_GOVERNANCE,
                priority=RequirementPriority.HIGH,
                rationale="Test",
                derived_from_articles=["10"]
            )
        ]

    def test_minimal_requirements_report(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test minimal RequirementsReport creation."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        assert report.system_description == minimal_system_description
        assert report.risk_classification == minimal_risk_classification
        assert report.requirements == []
        assert report.tere4ai_version == "0.1.0"

    def test_requirements_report_defaults(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test RequirementsReport default values."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        assert report.report_id is None
        assert report.requirements == []
        assert report.validation is None
        assert isinstance(report.coverage_matrix, CoverageMatrix)
        assert isinstance(report.metrics, ReportMetrics)
        assert report.processing_phases == []
        assert report.processing_errors == []
        assert report.processing_warnings == []

    def test_requirements_report_with_requirements(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test RequirementsReport with requirements."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        assert len(report.requirements) == 2
        assert report.requirements[0].id == "REQ-001"

    def test_is_prohibited_computed_field_true(self, minimal_system_description):
        """Test is_prohibited computed field when True."""
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="5",
            paragraph=1,
            point="c",
            reference_text="Article 5(1)(c)",
            quoted_text="Social scoring"
        )
        legal_basis = CitationBundle(
            primary=primary,
            rationale="Social scoring prohibition"
        )
        classification = RiskClassification(
            level=RiskLevel.UNACCEPTABLE,
            legal_basis=legal_basis,
            prohibited_practice=ProhibitedPractice.SOCIAL_SCORING,
            reasoning="Prohibited"
        )
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=classification
        )
        assert report.is_prohibited is True

    def test_is_prohibited_computed_field_false(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test is_prohibited computed field when False."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        assert report.is_prohibited is False

    def test_has_requirements_computed_field_true(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test has_requirements computed field when True."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        assert report.has_requirements is True

    def test_has_requirements_computed_field_false(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test has_requirements computed field when False."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        assert report.has_requirements is False

    def test_get_requirements_by_category(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test get_requirements_by_category method."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        by_category = report.get_requirements_by_category()
        assert "risk_management" in by_category
        assert "data_governance" in by_category
        assert len(by_category["risk_management"]) == 1

    def test_get_requirements_by_category_empty(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test get_requirements_by_category with no requirements."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        by_category = report.get_requirements_by_category()
        assert by_category == {}

    def test_get_requirements_by_priority(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test get_requirements_by_priority method."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        by_priority = report.get_requirements_by_priority()
        assert "critical" in by_priority
        assert "high" in by_priority
        assert len(by_priority["critical"]) == 1

    def test_get_all_citations(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test get_all_citations method."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        citations = report.get_all_citations()
        assert len(citations) == 2  # 1 EU AI Act + 1 HLEG from first req

    def test_get_all_citations_empty(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test get_all_citations with no requirements."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        citations = report.get_all_citations()
        assert citations == []

    def test_compute_metrics(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test compute_metrics method."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        report.compute_metrics()

        assert report.metrics.total_citations == 2
        assert report.metrics.eu_ai_act_citations == 1
        assert report.metrics.hleg_citations == 1
        assert report.metrics.unique_articles_cited == 1
        assert report.metrics.unique_hleg_principles_addressed == 1
        assert report.metrics.total_requirements == 2
        assert report.metrics.critical_requirements == 1
        assert report.metrics.high_requirements == 1

    def test_compute_metrics_empty(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test compute_metrics with no requirements."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        report.compute_metrics()

        assert report.metrics.total_citations == 0
        assert report.metrics.total_requirements == 0

    def test_to_summary(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test to_summary method."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements
        )
        report.compute_metrics()
        summary = report.to_summary()

        assert "TERE4AI Analysis Report" in summary
        assert "Risk Classification: HIGH" in summary
        assert "Requirements Generated: 2" in summary

    def test_to_summary_prohibited(self, minimal_system_description):
        """Test to_summary for prohibited system."""
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="5",
            reference_text="Article 5",
            quoted_text="Prohibited"
        )
        legal_basis = CitationBundle(
            primary=primary,
            rationale="Prohibited"
        )
        classification = RiskClassification(
            level=RiskLevel.UNACCEPTABLE,
            legal_basis=legal_basis,
            prohibition_details="Social scoring system",
            reasoning="Prohibited"
        )
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=classification
        )
        summary = report.to_summary()

        assert "PROHIBITED" in summary
        assert "No requirements were generated" in summary

    def test_requirements_report_generated_at(
        self, minimal_system_description, minimal_risk_classification
    ):
        """Test generated_at timestamp is set."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification
        )
        assert isinstance(report.generated_at, datetime)

    def test_requirements_report_serialization(
        self,
        minimal_system_description,
        minimal_risk_classification,
        sample_requirements
    ):
        """Test RequirementsReport serialization."""
        report = RequirementsReport(
            system_description=minimal_system_description,
            risk_classification=minimal_risk_classification,
            requirements=sample_requirements,
            report_id="test-report-123"
        )
        data = report.model_dump()

        assert data["report_id"] == "test-report-123"
        assert data["tere4ai_version"] == "0.1.0"
        assert len(data["requirements"]) == 2
        assert data["is_prohibited"] is False
        assert data["has_requirements"] is True

    def test_requirements_report_deserialization(self):
        """Test RequirementsReport deserialization."""
        data = {
            "system_description": {
                "raw_description": "Test",
                "purpose": "Test purpose"
            },
            "risk_classification": {
                "level": "high",
                "legal_basis": {
                    "primary": {
                        "source": "EU_AI_ACT",
                        "document_id": "eu_ai_act_2024",
                        "reference_text": "Test",
                        "quoted_text": "Test"
                    },
                    "supporting": [],
                    "rationale": "Test"
                },
                "reasoning": "Test"
            },
            "requirements": []
        }
        report = RequirementsReport.model_validate(data)
        assert report.risk_classification.level == RiskLevel.HIGH


# ============================================================================
# CROSS-MODEL INTEGRATION TESTS
# ============================================================================

class TestCrossModelIntegration:
    """Tests for cross-model integration scenarios."""

    def test_citation_in_citation_bundle(self):
        """Test Citation properly integrates with CitationBundle."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            reference_text="Article 9",
            quoted_text="Test"
        )
        bundle = CitationBundle(
            primary=citation,
            rationale="Test"
        )
        assert bundle.primary.article == "9"
        assert bundle.all_citations()[0].source == "EU_AI_ACT"

    def test_citation_bundle_in_risk_classification(self):
        """Test CitationBundle properly integrates with RiskClassification."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="5",
            reference_text="Article 5",
            quoted_text="Prohibited"
        )
        bundle = CitationBundle(
            primary=citation,
            rationale="Social scoring prohibition"
        )
        classification = RiskClassification(
            level=RiskLevel.UNACCEPTABLE,
            legal_basis=bundle,
            reasoning="Prohibited"
        )
        assert classification.legal_basis.primary.article == "5"

    def test_citation_in_generated_requirement(self):
        """Test Citation properly integrates with GeneratedRequirement."""
        eu_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            reference_text="Article 9",
            quoted_text="Risk management"
        )
        hleg_citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness",
            quoted_text="Test",
            relevance_score=0.95
        )
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.HIGH,
            rationale="Test",
            eu_ai_act_citations=[eu_citation],
            hleg_citations=[hleg_citation]
        )
        assert req.eu_ai_act_citations[0].article == "9"
        assert req.hleg_citations[0].relevance_score == 0.95

    def test_full_report_integration(self):
        """Test all models integrate properly in RequirementsReport."""
        # System description
        desc = SystemDescription(
            raw_description="Healthcare triage system",
            name="TrustTriage",
            domain=SystemDomain.HEALTHCARE,
            purpose="Prioritize ER patients",
            safety_critical=True
        )

        # Citations
        primary_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            annex="III",
            annex_section="5(a)",
            reference_text="Annex III, 5(a)",
            quoted_text="Healthcare triage"
        )
        hleg_implication = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            requirement_id="technical_robustness_and_safety",
            reference_text="Technical Robustness",
            quoted_text="Safety",
            relevance_score=0.9
        )

        # Legal basis
        legal_basis = CitationBundle(
            primary=primary_citation,
            supporting=[hleg_implication],
            rationale="Healthcare triage under Annex III"
        )

        # Risk classification
        classification = RiskClassification(
            level=RiskLevel.HIGH,
            legal_basis=legal_basis,
            annex_iii_category=AnnexIIICategory.ESSENTIAL_SERVICES,
            annex_iii_subcategory="5(a)",
            applicable_articles=["8", "9", "10", "11", "12", "13", "14", "15"],
            article_6_3_exception_checked=True,
            article_6_3_rationale="Not exempt",
            hleg_implications=[hleg_implication],
            reasoning="High risk healthcare system"
        )

        # Requirements
        req_citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Risk management"
        )
        requirement = GeneratedRequirement(
            id="REQ-001",
            title="Risk Management System",
            statement="SHALL implement risk management",
            category=RequirementCategory.RISK_MANAGEMENT,
            priority=RequirementPriority.CRITICAL,
            rationale="Article 9 requirement",
            eu_ai_act_citations=[req_citation],
            hleg_citations=[hleg_implication],
            derived_from_articles=["9"],
            addresses_hleg_principles=["technical_robustness_and_safety"]
        )

        # Validation
        validation = ValidationResult(
            article_coverage=0.875,
            hleg_coverage=0.71,
            subtopic_coverage=0.65,
            covered_articles=["8", "9", "10", "11", "12", "13", "14"],
            missing_articles=["15"],
            is_complete=False,
            is_consistent=True,
            is_valid=True
        )

        # Coverage matrix
        coverage = CoverageMatrix(
            hleg_to_requirements={"technical_robustness_and_safety": ["REQ-001"]},
            article_to_requirements={"9": ["REQ-001"]},
            requirement_to_articles={"REQ-001": ["9"]},
            requirement_to_hleg={"REQ-001": ["technical_robustness_and_safety"]}
        )

        # Full report
        report = RequirementsReport(
            system_description=desc,
            risk_classification=classification,
            requirements=[requirement],
            validation=validation,
            coverage_matrix=coverage,
            processing_phases=["elicitation", "analysis", "specification", "validation"]
        )

        # Verify integration
        assert report.system_description.domain == SystemDomain.HEALTHCARE
        assert report.risk_classification.level == RiskLevel.HIGH
        assert report.risk_classification.annex_iii_category == AnnexIIICategory.ESSENTIAL_SERVICES
        assert len(report.requirements) == 1
        assert report.requirements[0].category == RequirementCategory.RISK_MANAGEMENT
        assert report.validation.is_acceptable() is True
        assert "9" in report.coverage_matrix.article_to_requirements
        assert report.is_prohibited is False
        assert report.has_requirements is True

        # Compute and verify metrics
        report.compute_metrics()
        assert report.metrics.total_requirements == 1
        assert report.metrics.critical_requirements == 1

        # Verify serialization round-trip
        data = report.model_dump()
        restored = RequirementsReport.model_validate(data)
        assert restored.risk_classification.level == RiskLevel.HIGH
        assert len(restored.requirements) == 1

    def test_risk_classification_result_to_risk_classification(self):
        """Test that RiskClassificationResult can be used with RiskClassification."""
        # Simplified result (from MCP tool)
        result = RiskClassificationResult(
            risk_level=RiskLevel.HIGH,
            legal_basis_article="Annex III, 5(a)",
            legal_basis_text="Healthcare triage systems",
            annex_category="5",
            hleg_principles=["technical_robustness_and_safety"],
            reasoning="High risk healthcare"
        )

        # Should be able to convert to full classification
        assert result.risk_level == RiskLevel.HIGH
        assert result.annex_category == "5"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_lists_in_system_description(self):
        """Test SystemDescription with empty lists."""
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test",
            secondary_domains=[],
            intended_users=[],
            affected_persons=[],
            data_types=[],
            decision_types=[],
            ambiguities=[],
            assumptions=[]
        )
        assert desc.secondary_domains == []
        assert desc.to_features_dict()["secondary_domains"] == []

    def test_empty_lists_in_requirement(self):
        """Test GeneratedRequirement with empty lists."""
        req = GeneratedRequirement(
            id="REQ-001",
            title="Test",
            statement="Test",
            category=RequirementCategory.GENERAL,
            priority=RequirementPriority.LOW,
            rationale="Test",
            eu_ai_act_citations=[],
            hleg_citations=[],
            supporting_recitals=[],
            verification_criteria=[],
            derived_from_articles=[],
            addresses_hleg_principles=[],
            addresses_hleg_subtopics=[],
            related_requirements=[]
        )
        assert req.get_citation_count() == 0
        assert req.get_primary_article() is None

    def test_empty_coverage_matrix_methods(self):
        """Test CoverageMatrix methods with empty data."""
        matrix = CoverageMatrix()
        assert matrix.get_uncovered_articles(["9", "10"]) == ["9", "10"]
        assert len(matrix.get_uncovered_hleg()) == 7

    def test_very_long_strings(self):
        """Test models handle very long strings."""
        long_text = "x" * 10000
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text=long_text,
            quoted_text=long_text
        )
        assert len(citation.reference_text) == 10000
        assert len(citation.quoted_text) == 10000

    def test_special_characters_in_strings(self):
        """Test models handle special characters."""
        special_text = "Test with special chars: <>\"'&\n\t\r"
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text=special_text,
            quoted_text=special_text
        )
        assert citation.reference_text == special_text

    def test_unicode_characters(self):
        """Test models handle unicode."""
        unicode_text = "Test with unicode: \u00e9\u00e8\u00e0\u00f1"
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text=unicode_text,
            quoted_text=unicode_text
        )
        assert citation.reference_text == unicode_text

    def test_relevance_score_precision(self):
        """Test relevance_score handles floating point precision."""
        citation = Citation(
            source="AI_HLEG",
            document_id="ai_hleg_2019",
            reference_text="Test",
            quoted_text="Test",
            relevance_score=0.333333333333333
        )
        assert citation.relevance_score == pytest.approx(0.333333333333333)

    def test_datetime_handling(self):
        """Test RequirementsReport handles datetime properly."""
        specific_time = datetime(2024, 1, 15, 10, 30, 45)
        desc = SystemDescription(
            raw_description="Test",
            purpose="Test"
        )
        primary = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            reference_text="Test",
            quoted_text="Test"
        )
        legal_basis = CitationBundle(
            primary=primary,
            rationale="Test"
        )
        classification = RiskClassification(
            level=RiskLevel.MINIMAL,
            legal_basis=legal_basis,
            reasoning="Test"
        )
        report = RequirementsReport(
            generated_at=specific_time,
            system_description=desc,
            risk_classification=classification
        )
        assert report.generated_at == specific_time

    def test_nested_model_validation(self):
        """Test that nested models are properly validated."""
        # Invalid citation in bundle should raise error
        with pytest.raises(ValidationError):
            CitationBundle(
                primary={
                    "source": "INVALID",  # Invalid source
                    "document_id": "test",
                    "reference_text": "Test",
                    "quoted_text": "Test"
                },
                rationale="Test"
            )

    def test_json_round_trip(self):
        """Test models survive JSON round-trip."""
        citation = Citation(
            source="EU_AI_ACT",
            document_id="eu_ai_act_2024",
            article="9",
            paragraph=1,
            reference_text="Article 9(1)",
            quoted_text="Test"
        )
        # Serialize to JSON
        json_str = citation.model_dump_json()
        # Deserialize from JSON
        restored = Citation.model_validate_json(json_str)
        assert restored.source == citation.source
        assert restored.article == citation.article
        assert restored.paragraph == citation.paragraph


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

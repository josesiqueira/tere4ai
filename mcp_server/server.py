"""
TERE4AI MCP Server

This is the Model Context Protocol server that bridges RE agents with
the Neo4j knowledge graph. It provides 5 semantic tools for querying
EU AI Act and HLEG data.

TOOLS:
  1. classify_risk_level - Determine risk level from system features
  2. get_applicable_articles - Get articles for a risk level
  3. get_article_with_citations - Get full article with HLEG mappings
  4. get_hleg_coverage - Get HLEG coverage matrix
  5. search_legal_text - Semantic search across legal text

The MCP server abstracts away Cypher queries, providing semantic
operations that agents can call without knowing Neo4j internals.

Usage:
    # Run as MCP server
    python -m tere4ai.mcp_server.server

    # Or import for testing
    from tere4ai.mcp_server.server import mcp
"""

import atexit
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from neo4j import GraphDatabase, Driver

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Neo4j connection settings
# NOTE: NEO4J_PASSWORD must be set in environment - no default for security
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
if not NEO4J_PASSWORD:
    logger.warning(
        "NEO4J_PASSWORD not set. Database operations will fail until configured. "
        "Set NEO4J_PASSWORD environment variable."
    )

# Create FastMCP server
mcp = FastMCP(
    name="tere4ai",
    instructions="TERE4AI Knowledge Graph Server - EU AI Act and HLEG requirements",
)

# Singleton Neo4j driver
_driver: Optional[Driver] = None


def get_neo4j_driver() -> Driver:
    """Get Neo4j driver instance (singleton pattern for connection pooling)."""
    global _driver
    if _driver is None:
        logger.info(f"Creating Neo4j driver connection to {NEO4J_URI}")
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
    return _driver


def close_neo4j_driver() -> None:
    """Close the Neo4j driver connection. Called at exit."""
    global _driver
    if _driver is not None:
        logger.info("Closing Neo4j driver connection")
        _driver.close()
        _driver = None


# Register cleanup at exit
atexit.register(close_neo4j_driver)


def execute_query(cypher: str, **params: Any) -> list:
    """Execute a Cypher query and return records."""
    driver = get_neo4j_driver()
    result = driver.execute_query(cypher, **params)
    return result.records


# =============================================================================
# Tool 1: classify_risk_level
# =============================================================================

def classify_risk_level_impl(system_features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify the risk level of an AI system based on its features.

    This tool checks:
    1. Article 5 prohibited practices (returns UNACCEPTABLE)
    2. Annex III high-risk categories (returns HIGH, unless Art 6(3) exception)
    3. Article 50 transparency requirements (returns LIMITED)
    4. Otherwise returns MINIMAL

    Args:
        system_features: Dictionary containing system characteristics:
            - domain: str (healthcare, education, employment, etc.)
            - purpose: str (what the system does)
            - biometric_processing: bool
            - real_time_biometric: bool
            - law_enforcement_use: bool
            - safety_critical: bool
            - social_scoring: bool
            - subliminal_techniques: bool
            - emotion_recognition: bool
            - affects_fundamental_rights: bool

    Returns:
        Dictionary with:
            - risk_level: "unacceptable" | "high" | "limited" | "minimal"
            - legal_basis_article: str (e.g., "5(1)(c)" or "Annex III, 5(a)")
            - legal_basis_text: str (quoted text from source)
            - annex_category: str (if high risk)
            - article_6_exception: bool
            - hleg_principles: list of relevant HLEG IDs
            - reasoning: str
    """
    # Extract features with defaults
    domain = system_features.get("domain", "general")
    biometric = system_features.get("biometric_processing", False)
    real_time_biometric = system_features.get("real_time_biometric", False)
    law_enforcement = system_features.get("law_enforcement_use", False)
    social_scoring = system_features.get("social_scoring", False)
    subliminal = system_features.get("subliminal_techniques", False)
    emotion = system_features.get("emotion_recognition", False)
    safety_critical = system_features.get("safety_critical", False)

    # ---------------------------------------------------------------------
    # Step 1: Check for prohibited practices (Article 5)
    # ---------------------------------------------------------------------
    prohibited_result = _check_prohibited_practices(system_features)
    if prohibited_result:
        return prohibited_result

    # ---------------------------------------------------------------------
    # Step 2: Check for high-risk (Annex III)
    # ---------------------------------------------------------------------
    high_risk_result = _check_annex_iii(system_features)
    if high_risk_result:
        # Check Article 6(3) exception
        if not _has_significant_output_influence(system_features):
            return {
                "risk_level": "limited",
                "legal_basis_article": "Article 6(3)",
                "legal_basis_text": (
                    "The AI system performs a purely accessory function and does not "
                    "materially influence the outcome of the decision."
                ),
                "annex_category": high_risk_result.get("annex_category"),
                "article_6_exception": True,
                "hleg_principles": ["transparency"],
                "reasoning": (
                    "System matches Annex III category but Article 6(3) exception "
                    "applies - system output is not determinative."
                ),
            }
        return high_risk_result

    # ---------------------------------------------------------------------
    # Step 3: Check for limited risk (Article 50 transparency)
    # ---------------------------------------------------------------------
    if _requires_transparency(system_features):
        return {
            "risk_level": "limited",
            "legal_basis_article": "Article 50",
            "legal_basis_text": _get_article_50_text(),
            "annex_category": None,
            "article_6_exception": False,
            "hleg_principles": ["transparency"],
            "reasoning": (
                "System interacts with natural persons or generates synthetic content, "
                "requiring transparency disclosures under Article 50."
            ),
        }

    # ---------------------------------------------------------------------
    # Step 4: Default to minimal risk
    # ---------------------------------------------------------------------
    return {
        "risk_level": "minimal",
        "legal_basis_article": None,
        "legal_basis_text": "No specific regulatory obligations apply.",
        "annex_category": None,
        "article_6_exception": False,
        "hleg_principles": [],
        "reasoning": (
            "System does not fall under prohibited practices, high-risk categories, "
            "or transparency requirements. General AI Act provisions apply."
        ),
    }


def _check_prohibited_practices(features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Check if system matches Article 5 prohibited practices."""

    # Check purpose for prohibited content generation (deepfakes, intimate images)
    purpose = str(features.get("purpose", "")).lower()
    raw_desc = str(features.get("raw_description", "")).lower()

    # Deepfake/intimate content generation - Article 5(1)(c) variant
    prohibited_content_indicators = [
        "nude", "naked", "intimate", "deepfake", "deep fake",
        "fake nude", "realistic nude", "undress", "sexual content",
        "without consent", "non-consensual", "fake image", "fake video",
    ]

    if any(indicator in purpose or indicator in raw_desc for indicator in prohibited_content_indicators):
        return {
            "risk_level": "unacceptable",
            "legal_basis_article": "Article 5(1)(c)",
            "legal_basis_text": (
                "AI systems that deploy subliminal techniques or intentionally manipulative "
                "or deceptive techniques with the objective of materially distorting behaviour "
                "or that generate intimate images without consent are prohibited."
            ),
            "annex_category": None,
            "article_6_exception": False,
            "hleg_principles": [
                "human_agency_and_oversight",
                "privacy_and_data_governance",
                "societal_and_environmental_wellbeing",
            ],
            "reasoning": (
                "System generates intimate/deepfake content without consent, violating "
                "fundamental rights to privacy and dignity, prohibited under Article 5."
            ),
        }

    # Social scoring
    if features.get("social_scoring", False):
        text = _get_article_5_text("1_c")
        return {
            "risk_level": "unacceptable",
            "legal_basis_article": "Article 5(1)(c)",
            "legal_basis_text": text,
            "annex_category": None,
            "article_6_exception": False,
            "hleg_principles": [
                "human_agency_and_oversight",
                "diversity_non_discrimination_and_fairness",
                "societal_and_environmental_wellbeing",
            ],
            "reasoning": (
                "System performs social scoring - evaluating or classifying natural "
                "persons based on social behavior or personality characteristics, "
                "which is prohibited under Article 5(1)(c)."
            ),
        }

    # Subliminal manipulation
    if features.get("subliminal_techniques", False):
        text = _get_article_5_text("1_a")
        return {
            "risk_level": "unacceptable",
            "legal_basis_article": "Article 5(1)(a)",
            "legal_basis_text": text,
            "annex_category": None,
            "article_6_exception": False,
            "hleg_principles": [
                "human_agency_and_oversight",
                "transparency",
            ],
            "reasoning": (
                "System uses subliminal techniques to materially distort behavior "
                "in ways that cause or are likely to cause harm, which is prohibited "
                "under Article 5(1)(a)."
            ),
        }

    # Real-time biometric in public spaces for law enforcement
    if (features.get("real_time_biometric", False) and
        features.get("law_enforcement_use", False)):
        text = _get_article_5_text("1_h")
        return {
            "risk_level": "unacceptable",
            "legal_basis_article": "Article 5(1)(h)",
            "legal_basis_text": text,
            "annex_category": None,
            "article_6_exception": False,
            "hleg_principles": [
                "human_agency_and_oversight",
                "privacy_and_data_governance",
                "diversity_non_discrimination_and_fairness",
            ],
            "reasoning": (
                "System performs real-time remote biometric identification in "
                "publicly accessible spaces for law enforcement purposes, which "
                "is prohibited under Article 5(1)(h) with narrow exceptions."
            ),
        }

    # Emotion recognition in workplace/education
    if features.get("emotion_recognition", False):
        context = features.get("deployment_context", "")
        if context in ["workplace", "educational_institution"]:
            text = _get_article_5_text("1_f")
            return {
                "risk_level": "unacceptable",
                "legal_basis_article": "Article 5(1)(f)",
                "legal_basis_text": text,
                "annex_category": None,
                "article_6_exception": False,
                "hleg_principles": [
                    "human_agency_and_oversight",
                    "privacy_and_data_governance",
                ],
                "reasoning": (
                    "System performs emotion recognition in workplace or educational "
                    "settings, which is prohibited under Article 5(1)(f)."
                ),
            }

    return None


def _check_annex_iii(features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Check if system matches Annex III high-risk categories."""

    domain = features.get("domain", "general")
    purpose = str(features.get("purpose", "")).lower()
    raw_desc = str(features.get("raw_description", "")).lower()

    # Critical infrastructure - Category 2 (check first - explicit flag takes precedence)
    # This must be checked before healthcare to avoid false matches like "water treatment"
    if domain == "critical_infrastructure" or features.get("critical_infrastructure", False):
        return {
            "risk_level": "high",
            "legal_basis_article": "Article 6(2) + Annex III, Section 2",
            "legal_basis_text": _get_annex_iii_text("2"),
            "annex_category": "2",
            "article_6_exception": False,
            "hleg_principles": [
                "technical_robustness_and_safety",
                "human_agency_and_oversight",
                "accountability",
            ],
            "reasoning": (
                "System is a safety component of critical infrastructure "
                "(energy, water, digital, transport), falling under Annex III category 2."
            ),
        }

    # Healthcare - Category 5
    # Includes: triage, diagnosis, treatment (medical), emergency services
    healthcare_indicators = [
        "triage", "diagnos", "medical", "patient", "hospital",
        "clinical", "symptom", "vital sign",
    ]
    # Note: "treatment" and "emergency" removed from general indicators to avoid
    # false matches with non-healthcare systems (e.g., "water treatment")
    is_healthcare_system = (
        domain == "healthcare" or
        any(ind in purpose or ind in raw_desc for ind in healthcare_indicators)
    )

    # For healthcare, also check for medical treatment/emergency specifically
    has_medical_context = any(
        term in purpose or term in raw_desc
        for term in ["medical treatment", "patient treatment", "emergency room", "emergency care", "health"]
    )

    if is_healthcare_system and (features.get("safety_critical", False) or
                                  has_medical_context or
                                  any(ind in purpose or ind in raw_desc
                                      for ind in ["triage", "diagnos"])):
        return {
            "risk_level": "high",
            "legal_basis_article": "Article 6(2) + Annex III, Section 5(a)",
            "legal_basis_text": _get_annex_iii_text("5_a"),
            "annex_category": "5",
            "article_6_exception": False,
            "hleg_principles": [
                "technical_robustness_and_safety",
                "privacy_and_data_governance",
                "human_agency_and_oversight",
                "accountability",
            ],
            "reasoning": (
                "System is intended for use in healthcare as a safety component or "
                "for triage/treatment decisions, falling under Annex III category 5(a)."
            ),
        }

    # Education - Category 3
    if domain == "education":
        if any([
            "assessment" in str(features.get("decision_types", [])),
            "access_denial" in str(features.get("decision_types", [])),
        ]):
            return {
                "risk_level": "high",
                "legal_basis_article": "Article 6(2) + Annex III, Section 3",
                "legal_basis_text": _get_annex_iii_text("3"),
                "annex_category": "3",
                "article_6_exception": False,
                "hleg_principles": [
                    "diversity_non_discrimination_and_fairness",
                    "human_agency_and_oversight",
                    "transparency",
                ],
                "reasoning": (
                    "System is used in education for student assessment or access "
                    "to educational opportunities, falling under Annex III category 3."
                ),
            }

    # Employment - Category 4
    if domain == "employment":
        return {
            "risk_level": "high",
            "legal_basis_article": "Article 6(2) + Annex III, Section 4",
            "legal_basis_text": _get_annex_iii_text("4"),
            "annex_category": "4",
            "article_6_exception": False,
            "hleg_principles": [
                "diversity_non_discrimination_and_fairness",
                "human_agency_and_oversight",
                "transparency",
                "accountability",
            ],
            "reasoning": (
                "System is used in employment context for recruitment, selection, "
                "or worker management, falling under Annex III category 4."
            ),
        }

    # Law enforcement - Category 6
    if domain == "law_enforcement" or features.get("law_enforcement_use", False):
        return {
            "risk_level": "high",
            "legal_basis_article": "Article 6(2) + Annex III, Section 6",
            "legal_basis_text": _get_annex_iii_text("6"),
            "annex_category": "6",
            "article_6_exception": False,
            "hleg_principles": [
                "human_agency_and_oversight",
                "diversity_non_discrimination_and_fairness",
                "accountability",
                "transparency",
            ],
            "reasoning": (
                "System is intended for use by law enforcement authorities, "
                "falling under Annex III category 6."
            ),
        }

    # Biometrics - Category 1
    if features.get("biometric_processing", False):
        return {
            "risk_level": "high",
            "legal_basis_article": "Article 6(2) + Annex III, Section 1",
            "legal_basis_text": _get_annex_iii_text("1"),
            "annex_category": "1",
            "article_6_exception": False,
            "hleg_principles": [
                "privacy_and_data_governance",
                "diversity_non_discrimination_and_fairness",
                "human_agency_and_oversight",
            ],
            "reasoning": (
                "System uses biometric identification or categorization, "
                "falling under Annex III category 1."
            ),
        }

    # Note: Critical infrastructure check is at the top of this function
    # to take precedence over keyword-based matches

    return None


def _has_significant_output_influence(features: Dict[str, Any]) -> bool:
    """Check if system output significantly influences decisions (for Art 6(3) exception)."""
    # Conservative: assume significant unless clearly advisory
    autonomy = features.get("autonomy_level", "partial")
    return autonomy != "advisory"


def _requires_transparency(features: Dict[str, Any]) -> bool:
    """Check if system requires Article 50 transparency disclosures.

    Article 50 transparency applies to:
    1. AI systems intended to directly interact with natural persons (chatbots, virtual assistants)
    2. AI systems generating synthetic content (deepfakes, AI-generated text presented as human)
    3. Emotion recognition systems
    4. Biometric categorization systems

    NOT applicable to:
    - Pure recommendation systems (movies, products, content suggestions)
    - Backend analytics systems
    - Decision support tools that don't directly interact with end users
    """
    decision_types = features.get("decision_types", [])
    purpose = str(features.get("purpose", "")).lower()
    raw_desc = str(features.get("raw_description", "")).lower()

    # Indicator lists (defined once for consistency)
    recommendation_indicators = [
        "recommend", "suggestion", "suggests", "recommender",
        "movie recommend", "product recommend", "content recommend",
        "personalize", "personalizes", "personalization",
    ]
    chatbot_indicators = [
        "chatbot", "chat bot", "conversational", "conversational ai",
        "virtual assistant", "customer service bot",
        "responds to", "answers questions",
    ]

    # Helper to check if any indicator is present
    def has_indicator(indicators: list) -> bool:
        return any(term in purpose or term in raw_desc for term in indicators)

    # Check if this is a pure recommendation system
    is_recommendation_system = (
        "recommendation" in decision_types or
        has_indicator(recommendation_indicators)
    )

    # Pure recommendation systems without conversational UI are minimal risk
    if is_recommendation_system:
        # But if it's ALSO a chatbot, it's limited
        if not has_indicator(chatbot_indicators):
            return False  # Pure recommendation = minimal risk

    # INCLUSIONS: Systems that DO require transparency

    # 1. Content generation (synthetic media, AI-generated text/images/video)
    if "content_generation" in decision_types:
        return True

    # 2. Chatbots and conversational AI (direct interaction with users)
    if has_indicator(chatbot_indicators):
        return True

    # 3. Emotion recognition or biometric categorization
    if features.get("emotion_recognition", False):
        return True

    return False


def _get_article_5_text(subsection: str) -> str:
    """Get Article 5 text from database or fallback."""
    try:
        records = execute_query("""
            MATCH (a:Article {number: 5})-[:HAS_PARAGRAPH]->(p:Paragraph {index: 1})
            RETURN p.text as text
            LIMIT 1
        """)
        if records:
            return records[0]["text"]
    except Exception as e:
        logger.warning(f"Failed to fetch Article 5 text from database: {e}")

    # Fallback texts
    fallbacks = {
        "1_a": (
            "The placing on the market, the putting into service or the use of an AI "
            "system that deploys subliminal techniques beyond a person's consciousness "
            "or purposefully manipulative or deceptive techniques..."
        ),
        "1_c": (
            "The placing on the market, the putting into service or the use of AI "
            "systems for the evaluation or classification of natural persons... based "
            "on their social behaviour or known, inferred or predicted personal or "
            "personality characteristics..."
        ),
        "1_f": (
            "The placing on the market, the putting into service or the use of AI "
            "systems to infer emotions of a natural person in the areas of workplace "
            "and education institutions..."
        ),
        "1_h": (
            "The use of 'real-time' remote biometric identification systems in "
            "publicly accessible spaces for the purposes of law enforcement..."
        ),
    }
    return fallbacks.get(subsection, "Prohibited practice under Article 5.")


def _get_annex_iii_text(category: str) -> str:
    """Get Annex III category text from database or fallback."""
    try:
        records = execute_query("""
            MATCH (a:Annex {number: 'III'})
            RETURN a.raw_text as text
            LIMIT 1
        """)
        if records:
            # Extract relevant section (simplified)
            return f"High-risk AI system under Annex III, category {category}"
    except Exception as e:
        logger.warning(f"Failed to fetch Annex III text from database: {e}")

    fallbacks = {
        "1": "Biometric identification and categorisation of natural persons",
        "2": "Management and operation of critical infrastructure",
        "3": "Education and vocational training",
        "4": "Employment, workers management and access to self-employment",
        "5": "Access to and enjoyment of essential private services and essential public services and benefits",
        "5_a": (
            "AI systems intended to be used as safety components in the management and "
            "operation of critical digital infrastructure, road traffic, or in the supply "
            "of water, gas, heating or electricity; AI systems intended to be used for "
            "triage or for establishing priority in the dispatching of emergency first "
            "response services, including by firefighters and medical aid."
        ),
        "6": "Law enforcement",
    }
    return fallbacks.get(category, f"High-risk category {category}")


def _get_article_50_text() -> str:
    """Get Article 50 transparency text."""
    try:
        records = execute_query("""
            MATCH (a:Article {number: 50})-[:HAS_PARAGRAPH]->(p:Paragraph {index: 1})
            RETURN p.text as text
            LIMIT 1
        """)
        if records:
            return records[0]["text"]
    except Exception as e:
        logger.warning(f"Failed to fetch Article 50 text from database: {e}")

    return (
        "Providers shall ensure that AI systems intended to interact directly with "
        "natural persons are designed and developed in such a way that the natural "
        "persons concerned are informed that they are interacting with an AI system..."
    )


# MCP Tool wrapper for classify_risk_level
@mcp.tool()
def classify_risk_level(system_features: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the risk level of an AI system based on its features."""
    return classify_risk_level_impl(system_features)


# =============================================================================
# Tool 2: get_applicable_articles
# =============================================================================

def get_applicable_articles_impl(
    risk_level: str,
    annex_category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all applicable EU AI Act articles for a given risk level.

    For HIGH risk: Returns Articles 8-27 (Chapter III requirements)
    For LIMITED risk: Returns Article 50 (transparency)
    For MINIMAL/UNACCEPTABLE: Returns empty list

    Args:
        risk_level: "high" | "limited" | "minimal" | "unacceptable"
        annex_category: Optional Annex III category for context

    Returns:
        List of article dictionaries with:
            - number: int
            - title: str
            - section: str (e.g., "Section 2 - Requirements")
            - paragraphs: list of paragraph texts
            - category: str (what type of requirement)
    """
    if risk_level == "unacceptable":
        return []

    if risk_level == "minimal":
        return []

    if risk_level == "limited":
        return _get_articles([50])

    # HIGH risk: Articles 8-27
    if risk_level == "high":
        # Section 2: Technical requirements (8-15)
        # Section 3: Obligations (16-27)
        return _get_articles(list(range(8, 28)))

    return []


def _get_articles(article_numbers: List[int]) -> List[Dict[str, Any]]:
    """Fetch articles from Neo4j."""
    articles = []

    for num in article_numbers:
        try:
            records = execute_query("""
                MATCH (a:Article {number: $num})
                OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
                WITH a, p ORDER BY p.index
                RETURN a.number as number,
                       a.title as title,
                       collect({index: p.index, text: p.text}) as paragraphs
            """, num=num)

            if records:
                record = records[0]
                articles.append({
                    "number": record["number"],
                    "title": record["title"] or f"Article {num}",
                    "section": _get_section_for_article(num),
                    "paragraphs": record["paragraphs"],
                    "category": _get_category_for_article(num),
                })
            else:
                # Neo4j returned empty results - use fallback
                logger.debug(f"No data found for Article {num}, using fallback")
                articles.append({
                    "number": num,
                    "title": f"Article {num}",
                    "section": _get_section_for_article(num),
                    "paragraphs": [],
                    "category": _get_category_for_article(num),
                })
        except Exception as e:
            # Database error - use fallback with minimal info
            logger.warning(f"Failed to fetch Article {num} from database: {e}")
            articles.append({
                "number": num,
                "title": f"Article {num}",
                "section": _get_section_for_article(num),
                "paragraphs": [],
                "category": _get_category_for_article(num),
            })

    return articles


# MCP Tool wrapper for get_applicable_articles
@mcp.tool()
def get_applicable_articles(
    risk_level: str,
    annex_category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all applicable EU AI Act articles for a given risk level."""
    return get_applicable_articles_impl(risk_level, annex_category)


def _get_section_for_article(num: int) -> str:
    """Get the section name for an article number."""
    if num <= 7:
        return "Chapter I - General Provisions"
    if 8 <= num <= 15:
        return "Chapter III, Section 2 - Requirements for high-risk AI systems"
    if 16 <= num <= 27:
        return "Chapter III, Section 3 - Obligations of providers and deployers"
    if 28 <= num <= 39:
        return "Chapter III, Section 4 - Notifying authorities and notified bodies"
    if 40 <= num <= 49:
        return "Chapter III, Section 5 - Standards, conformity assessment"
    if num == 50:
        return "Chapter IV - Transparency obligations"
    return "Other"


def _get_category_for_article(num: int) -> str:
    """Get the requirement category for an article."""
    categories = {
        8: "general_requirements",
        9: "risk_management",
        10: "data_governance",
        11: "documentation",
        12: "record_keeping",
        13: "transparency",
        14: "human_oversight",
        15: "accuracy_robustness",
        16: "provider_obligations",
        17: "provider_obligations",
        18: "provider_obligations",
        19: "provider_obligations",
        20: "provider_obligations",
        21: "provider_obligations",
        22: "provider_obligations",
        23: "importer_obligations",
        24: "distributor_obligations",
        25: "product_integration",
        26: "deployer_obligations",
        27: "deployer_obligations",
        50: "transparency_limited",
    }
    return categories.get(num, "general")


# =============================================================================
# Tool 3: get_article_with_citations
# =============================================================================

def get_article_with_citations_impl(article_number: int) -> Dict[str, Any]:
    """
    Get complete article content with supporting recitals and HLEG mappings.

    This is the main tool for generating requirements - it provides everything
    needed to create a requirement anchored to this article.

    Args:
        article_number: The article number (e.g., 9 for Article 9)

    Returns:
        Dictionary with:
            - number: int
            - title: str
            - full_text: str (all paragraphs combined)
            - paragraphs: list of {index, text, points}
            - recitals: list of {number, text} (supporting recitals)
            - hleg_mappings: list of {requirement_id, requirement_name, relevance, rationale, subtopics}
            - section: str
            - category: str
    """
    result = {
        "number": article_number,
        "title": f"Article {article_number}",
        "full_text": "",
        "paragraphs": [],
        "recitals": [],
        "hleg_mappings": [],
        "section": _get_section_for_article(article_number),
        "category": _get_category_for_article(article_number),
    }

    try:
        # Get article with paragraphs
        records = execute_query("""
            MATCH (a:Article {number: $num})
            OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
            OPTIONAL MATCH (p)-[:HAS_POINT]->(pt:Point)
            WITH a, p, collect({marker: pt.marker, text: pt.text}) as points
            ORDER BY p.index
            RETURN a.title as title,
                   collect({index: p.index, text: p.text, points: points}) as paragraphs
        """, num=article_number)

        if records:
            record = records[0]
            result["title"] = record["title"] or f"Article {article_number}"
            result["paragraphs"] = record["paragraphs"]
            result["full_text"] = "\n\n".join(
                p["text"] for p in record["paragraphs"] if p["text"]
            )

        # Get HLEG mappings for this article's paragraphs
        hleg_records = execute_query("""
            MATCH (a:Article {number: $num})-[:HAS_PARAGRAPH]->(p:Paragraph)
            MATCH (p)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)
            OPTIONAL MATCH (h)-[:HAS_SUBTOPIC]->(s:HLEGRequirementSubtopic)
            RETURN h.id as requirement_id,
                   h.name as requirement_name,
                   r.relevance as relevance,
                   r.rationale as rationale,
                   collect(DISTINCT s.label) as subtopics
        """, num=article_number)

        seen_hleg = set()
        for rec in hleg_records:
            req_id = rec["requirement_id"]
            if req_id not in seen_hleg:
                seen_hleg.add(req_id)
                result["hleg_mappings"].append({
                    "requirement_id": req_id,
                    "requirement_name": rec["requirement_name"],
                    "relevance": rec["relevance"],
                    "rationale": rec["rationale"],
                    "subtopics": rec["subtopics"],
                })

        # Get related recitals (approximate - look for article mentions)
        recital_records = execute_query("""
            MATCH (r:Recital)
            WHERE r.text CONTAINS $article_ref
            RETURN r.number as number, r.text as text
            ORDER BY r.number
            LIMIT 5
        """, article_ref=f"Article {article_number}")

        for rec in recital_records:
            result["recitals"].append({
                "number": rec["number"],
                "text": rec["text"][:500] + "..." if len(rec["text"]) > 500 else rec["text"],
            })

    except Exception as e:
        result["error"] = str(e)

    return result


# MCP Tool wrapper for get_article_with_citations
@mcp.tool()
def get_article_with_citations(article_number: int) -> Dict[str, Any]:
    """Get complete article content with supporting recitals and HLEG mappings."""
    return get_article_with_citations_impl(article_number)


# =============================================================================
# Tool 4: get_hleg_coverage
# =============================================================================

def get_hleg_coverage_impl(articles: List[int]) -> Dict[str, Any]:
    """
    Get HLEG coverage matrix for a set of articles.

    Shows which HLEG principles and subtopics are addressed by
    the given articles, with relevance scores.

    Args:
        articles: List of article numbers to analyze

    Returns:
        Dictionary with:
            - principles: dict mapping requirement_id -> {name, relevance, articles, subtopics}
            - coverage_percentage: float (% of 7 principles covered)
            - uncovered_principles: list of principle IDs not covered
            - total_mappings: int
    """
    result = {
        "principles": {},
        "coverage_percentage": 0.0,
        "uncovered_principles": [],
        "total_mappings": 0,
    }

    all_principles = {
        "human_agency_and_oversight": "Human Agency and Oversight",
        "technical_robustness_and_safety": "Technical Robustness and Safety",
        "privacy_and_data_governance": "Privacy and Data Governance",
        "transparency": "Transparency",
        "diversity_non_discrimination_and_fairness": "Diversity, Non-discrimination and Fairness",
        "societal_and_environmental_wellbeing": "Societal and Environmental Well-being",
        "accountability": "Accountability",
    }

    try:
        # Get all HLEG mappings for the given articles
        records = execute_query("""
            MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
            WHERE a.number IN $articles
            MATCH (p)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)
            OPTIONAL MATCH (h)-[:HAS_SUBTOPIC]->(s:HLEGRequirementSubtopic)
            RETURN h.id as requirement_id,
                   h.name as requirement_name,
                   a.number as article_number,
                   r.relevance as relevance,
                   collect(DISTINCT s.label) as subtopics
        """, articles=articles)

        for rec in records:
            req_id = rec["requirement_id"]
            if req_id not in result["principles"]:
                result["principles"][req_id] = {
                    "name": rec["requirement_name"],
                    "max_relevance": 0.0,
                    "articles": [],
                    "subtopics": set(),
                }

            entry = result["principles"][req_id]
            if rec["article_number"] not in entry["articles"]:
                entry["articles"].append(rec["article_number"])
            if rec["relevance"] and rec["relevance"] > entry["max_relevance"]:
                entry["max_relevance"] = rec["relevance"]
            for st in rec["subtopics"]:
                entry["subtopics"].add(st)

            result["total_mappings"] += 1

        # Convert sets to lists for JSON serialization
        for req_id in result["principles"]:
            result["principles"][req_id]["subtopics"] = list(
                result["principles"][req_id]["subtopics"]
            )

        # Calculate coverage
        covered = set(result["principles"].keys())
        result["coverage_percentage"] = len(covered) / 7 * 100
        result["uncovered_principles"] = [
            pid for pid in all_principles.keys() if pid not in covered
        ]

    except Exception as e:
        result["error"] = str(e)

    return result


# MCP Tool wrapper for get_hleg_coverage
@mcp.tool()
def get_hleg_coverage(articles: List[int]) -> Dict[str, Any]:
    """Get HLEG coverage matrix for a set of articles."""
    return get_hleg_coverage_impl(articles)


# =============================================================================
# Tool 5: search_legal_text
# =============================================================================

def search_legal_text_impl(
    query: str,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Search across EU AI Act articles, recitals, annexes, and HLEG requirements.

    Performs keyword-based search with optional filters.

    Args:
        query: Search query string
        filters: Optional filters:
            - source: "eu_ai_act" | "hleg" | "all"
            - article_range: [start, end] (e.g., [8, 15])
            - chapter: str (e.g., "III")
            - limit: int (max results, default 10)

    Returns:
        Dictionary with:
            - results: list of matches with {type, reference, text, relevance}
            - total_matches: int
            - query: str (echoed back)
    """
    filters = filters or {}
    source = filters.get("source", "all")
    limit = filters.get("limit", 10)
    article_range = filters.get("article_range")

    results = []

    try:
        # Search articles
        if source in ["eu_ai_act", "all"]:
            # Use parameterized query for safety (avoid Cypher injection)
            article_query = """
                MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
                WHERE toLower(p.text) CONTAINS toLower($query)
                  AND ($min_article IS NULL OR a.number >= $min_article)
                  AND ($max_article IS NULL OR a.number <= $max_article)
                RETURN 'article' as type,
                       'Article ' + toString(a.number) + '(' + toString(p.index) + ')' as reference,
                       p.text as text,
                       a.number as article_number
                LIMIT $limit
            """

            records = execute_query(
                article_query,
                query=query,
                limit=limit,
                min_article=article_range[0] if article_range else None,
                max_article=article_range[1] if article_range else None,
            )
            for rec in records:
                results.append({
                    "type": "article",
                    "reference": rec["reference"],
                    "text": rec["text"][:300] + "..." if len(rec["text"]) > 300 else rec["text"],
                    "article_number": rec["article_number"],
                })

        # Search recitals
        if source in ["eu_ai_act", "all"] and len(results) < limit:
            recital_records = execute_query("""
                MATCH (r:Recital)
                WHERE toLower(r.text) CONTAINS toLower($query)
                RETURN 'recital' as type,
                       'Recital (' + toString(r.number) + ')' as reference,
                       r.text as text,
                       r.number as recital_number
                LIMIT $limit
            """, query=query, limit=limit - len(results))

            for rec in recital_records:
                results.append({
                    "type": "recital",
                    "reference": rec["reference"],
                    "text": rec["text"][:300] + "..." if len(rec["text"]) > 300 else rec["text"],
                    "recital_number": rec["recital_number"],
                })

        # Search HLEG
        if source in ["hleg", "all"] and len(results) < limit:
            hleg_records = execute_query("""
                MATCH (h:HLEGRequirement)
                WHERE toLower(h.full_text) CONTAINS toLower($query)
                   OR toLower(h.name) CONTAINS toLower($query)
                RETURN 'hleg' as type,
                       h.name as reference,
                       h.short_description as text,
                       h.id as requirement_id
                LIMIT $limit
            """, query=query, limit=limit - len(results))

            for rec in hleg_records:
                results.append({
                    "type": "hleg",
                    "reference": rec["reference"],
                    "text": rec["text"],
                    "requirement_id": rec["requirement_id"],
                })

    except Exception as e:
        return {
            "results": [],
            "total_matches": 0,
            "query": query,
            "error": str(e),
        }

    return {
        "results": results,
        "total_matches": len(results),
        "query": query,
    }


# MCP Tool wrapper for search_legal_text
@mcp.tool()
def search_legal_text(
    query: str,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Search across EU AI Act and HLEG requirements."""
    return search_legal_text_impl(query, filters)


# =============================================================================
# Main entry point
# =============================================================================

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()

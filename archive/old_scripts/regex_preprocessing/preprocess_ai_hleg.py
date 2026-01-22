#!/usr/bin/env python3
"""
AI HLEG Ethics Guidelines Regex-Based Preprocessor

This script extracts the seven requirements of Trustworthy AI from the
AI HLEG "Ethics Guidelines for Trustworthy AI" using only regex and
deterministic Python operations. No LLMs are used.

Structure extracted:
- Document metadata
- 7 Requirements of Trustworthy AI
- Subtopics under each requirement

All data is ingested into Neo4j for graph-based querying, using the same
database as the EU AI Act preprocessor.
"""

import re
import sys
import os
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import GraphDatabase
from dotenv import load_dotenv

from models.hleg_regex import (
    HlegSubtopicRegex,
    HlegRequirementRegex,
    HlegDocumentRegex,
)

# Load environment variables (local .env takes priority, override existing)
script_dir = Path(__file__).parent
if (script_dir / ".env").exists():
    load_dotenv(script_dir / ".env", override=True)
else:
    load_dotenv(script_dir.parent / ".env")

# Neo4j connection settings
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


# =============================================================================
# Canonical Requirements Definition
# =============================================================================

# The seven requirements are a CLOSED, CANONICAL set
CANONICAL_REQUIREMENTS = [
    {
        "id": "human_agency_and_oversight",
        "order": 1,
        "name": "Human agency and oversight",
        "section_pattern": r"1\.1\s+Human agency and oversight",
        "short_description": "AI systems should support human autonomy and decision-making, allowing for human oversight through mechanisms like human-in-the-loop, human-on-the-loop, or human-in-command approaches.",
        "related_principles": ["respect_for_human_autonomy"],
        "tags": ["autonomy", "oversight", "fundamental-rights"],
        "subtopics": [
            {"label": "Fundamental rights", "pattern": r"Fundamental rights\."},
            {"label": "Human agency", "pattern": r"Human agency\."},
            {"label": "Human oversight", "pattern": r"Human oversight\."},
        ]
    },
    {
        "id": "technical_robustness_and_safety",
        "order": 2,
        "name": "Technical robustness and safety",
        "section_pattern": r"1\.2\s+Technical robustness and safety",
        "short_description": "AI systems should be developed with a preventative approach to risks, ensuring they reliably behave as intended while minimising unintentional harm and preventing unacceptable harm.",
        "related_principles": ["prevention_of_harm"],
        "tags": ["safety", "robustness", "security", "reliability"],
        "subtopics": [
            {"label": "Resilience to attack and security", "pattern": r"Resilience to attack and security\."},
            {"label": "Fallback plan and general safety", "pattern": r"Fallback plan and general safety\."},
            {"label": "Accuracy", "pattern": r"Accuracy\."},
            {"label": "Reliability and Reproducibility", "pattern": r"Reliability and Reproducibility\."},
        ]
    },
    {
        "id": "privacy_and_data_governance",
        "order": 3,
        "name": "Privacy and data governance",
        "section_pattern": r"1\.3\s+Privacy and data governance",
        "short_description": "AI systems must guarantee privacy and data protection throughout the system's entire lifecycle, including adequate data governance covering quality, integrity, and access protocols.",
        "related_principles": ["prevention_of_harm"],
        "tags": ["privacy", "data-protection", "data-governance"],
        "subtopics": [
            {"label": "Privacy and data protection", "pattern": r"Privacy and data protection\."},
            {"label": "Quality and integrity of data", "pattern": r"Quality and integrity of data\."},
            {"label": "Access to data", "pattern": r"Access to data\."},
        ]
    },
    {
        "id": "transparency",
        "order": 4,
        "name": "Transparency",
        "section_pattern": r"1\.4\s+Transparency",
        "short_description": "AI systems should be transparent regarding their data, system processes, and business models, enabling traceability, explainability, and clear communication with users.",
        "related_principles": ["explicability"],
        "tags": ["transparency", "explainability", "traceability"],
        "subtopics": [
            {"label": "Traceability", "pattern": r"Traceability\."},
            {"label": "Explainability", "pattern": r"Explainability\."},
            {"label": "Communication", "pattern": r"Communication\."},
        ]
    },
    {
        "id": "diversity_non_discrimination_and_fairness",
        "order": 5,
        "name": "Diversity, non-discrimination and fairness",
        "section_pattern": r"1\.5\s+Diversity, non-discrimination and fairness",
        "short_description": "AI systems should enable inclusion and diversity throughout their lifecycle, ensuring equal access through inclusive design and equal treatment while avoiding unfair bias.",
        "related_principles": ["fairness"],
        "tags": ["fairness", "non-discrimination", "diversity", "accessibility"],
        "subtopics": [
            {"label": "Avoidance of unfair bias", "pattern": r"Avoidance of unfair bias\."},
            {"label": "Accessibility and universal design", "pattern": r"Accessibility and universal design\."},
            {"label": "Stakeholder Participation", "pattern": r"Stakeholder Participation\."},
        ]
    },
    {
        "id": "societal_and_environmental_well_being",
        "order": 6,
        "name": "Societal and environmental well-being",
        "section_pattern": r"1\.6\s+Societal and environmental well-being",
        "short_description": "AI systems should consider the broader society, other sentient beings, and the environment as stakeholders, encouraging sustainability and ecological responsibility.",
        "related_principles": ["fairness", "prevention_of_harm"],
        "tags": ["sustainability", "environment", "society", "democracy"],
        "subtopics": [
            {"label": "Sustainable and environmentally friendly AI", "pattern": r"Sustainable and environmentally friendly AI\."},
            {"label": "Social impact", "pattern": r"Social impact\."},
            {"label": "Society and Democracy", "pattern": r"Society and Democracy\."},
        ]
    },
    {
        "id": "accountability",
        "order": 7,
        "name": "Accountability",
        "section_pattern": r"1\.7\s+Accountability",
        "short_description": "Mechanisms should be put in place to ensure responsibility and accountability for AI systems and their outcomes, both before and after their development, deployment and use.",
        "related_principles": ["fairness"],
        "tags": ["accountability", "auditability", "redress"],
        "subtopics": [
            {"label": "Auditability", "pattern": r"Auditability\."},
            {"label": "Minimisation and reporting of negative impacts", "pattern": r"Minimisation and reporting of negative impacts\."},
            {"label": "Trade-offs", "pattern": r"Trade-offs\."},
            {"label": "Redress", "pattern": r"Redress\."},
        ]
    },
]


# =============================================================================
# Helper Functions
# =============================================================================

def clean_text(text: str) -> str:
    """Clean and normalize text."""
    # Remove page numbers (standalone digits on their own line)
    text = re.sub(r'^\d+$', '', text, flags=re.MULTILINE)
    # Remove footnote numbers in superscript position
    text = re.sub(r'(?<=[a-z])\d{1,2}(?=\s|\.|\,)', '', text)
    # Remove excessive whitespace while preserving structure
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Clean up spaces
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def create_subtopic_id(requirement_id: str, label: str) -> str:
    """Create a stable ID for a subtopic."""
    # Create a short prefix from the requirement id
    prefix_map = {
        "human_agency_and_oversight": "human_agency",
        "technical_robustness_and_safety": "technical_robustness",
        "privacy_and_data_governance": "privacy_data_gov",
        "transparency": "transparency",
        "diversity_non_discrimination_and_fairness": "diversity_fairness",
        "societal_and_environmental_well_being": "societal_env",
        "accountability": "accountability",
    }
    prefix = prefix_map.get(requirement_id, requirement_id[:20])

    # Convert label to snake_case
    label_snake = label.lower()
    label_snake = re.sub(r'[^\w\s]', '', label_snake)
    label_snake = re.sub(r'\s+', '_', label_snake)
    # Truncate if too long
    if len(label_snake) > 30:
        label_snake = label_snake[:30].rstrip('_')

    return f"{prefix}_{label_snake}"


def read_file(filepath: str) -> str:
    """Read the AI HLEG text file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def find_section_text(text: str, section_pattern: str, next_section_pattern: str | None) -> str:
    """Extract text between two section patterns."""
    start_match = re.search(section_pattern, text)
    if not start_match:
        return ""

    start_pos = start_match.end()

    if next_section_pattern:
        end_match = re.search(next_section_pattern, text[start_pos:])
        if end_match:
            end_pos = start_pos + end_match.start()
        else:
            end_pos = len(text)
    else:
        # For the last section, find the next major section marker
        # Look for "2. Technical and non-technical methods" which ends the requirements
        end_match = re.search(r'2\.\s+Technical and non-technical methods', text[start_pos:])
        if end_match:
            end_pos = start_pos + end_match.start()
        else:
            end_pos = len(text)

    return clean_text(text[start_pos:end_pos])


def extract_subtopic_text(section_text: str, subtopic_pattern: str, all_subtopic_patterns: list[str]) -> str:
    """Extract text for a specific subtopic from within a section."""
    start_match = re.search(subtopic_pattern, section_text)
    if not start_match:
        return ""

    start_pos = start_match.end()

    # Find the nearest next subtopic or end of section
    end_pos = len(section_text)
    for pattern in all_subtopic_patterns:
        if pattern == subtopic_pattern:
            continue
        next_match = re.search(pattern, section_text[start_pos:])
        if next_match:
            candidate_end = start_pos + next_match.start()
            if candidate_end < end_pos:
                end_pos = candidate_end

    return clean_text(section_text[start_pos:end_pos])


# =============================================================================
# Main Parsing Function
# =============================================================================

def parse_ai_hleg(text: str) -> HlegDocumentRegex:
    """Parse the complete AI HLEG document."""

    print("Starting AI HLEG parsing...")

    # Create the main document structure
    doc = HlegDocumentRegex(
        document_id="ai_hleg_2019",
        official_title="Ethics Guidelines for Trustworthy AI",
        short_title="AI HLEG Ethics Guidelines",
        year=2019
    )

    # Process each canonical requirement
    for i, req_def in enumerate(CANONICAL_REQUIREMENTS):
        print(f"  Processing requirement {req_def['order']}: {req_def['name']}")

        # Determine next section pattern
        if i + 1 < len(CANONICAL_REQUIREMENTS):
            next_pattern = CANONICAL_REQUIREMENTS[i + 1]["section_pattern"]
        else:
            next_pattern = None

        # Extract section text
        section_text = find_section_text(text, req_def["section_pattern"], next_pattern)

        # Extract subtopics
        subtopics = []
        all_patterns = [st["pattern"] for st in req_def["subtopics"]]

        for st_def in req_def["subtopics"]:
            st_text = extract_subtopic_text(section_text, st_def["pattern"], all_patterns)
            if st_text:
                subtopic = HlegSubtopicRegex(
                    id=create_subtopic_id(req_def["id"], st_def["label"]),
                    label=st_def["label"],
                    description=st_text
                )
                subtopics.append(subtopic)
                print(f"    - Found subtopic: {st_def['label']}")

        # Create requirement
        requirement = HlegRequirementRegex(
            id=req_def["id"],
            order=req_def["order"],
            name=req_def["name"],
            short_description=req_def["short_description"],
            full_text=section_text[:2000] if len(section_text) > 2000 else section_text,  # Truncate very long text
            related_principles=req_def["related_principles"],
            tags=req_def["tags"],
            subtopics=subtopics
        )
        doc.requirements.append(requirement)

    print(f"\nParsing complete:")
    print(f"  - Requirements: {len(doc.requirements)}")
    total_subtopics = sum(len(r.subtopics) for r in doc.requirements)
    print(f"  - Total subtopics: {total_subtopics}")

    return doc


# =============================================================================
# Neo4j Ingestion
# =============================================================================

class Neo4jIngester:
    """Handles ingestion of parsed AI HLEG data into Neo4j."""

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def create_constraints(self):
        """Create uniqueness constraints for HLEG nodes."""
        constraints = [
            "CREATE CONSTRAINT hleg_id IF NOT EXISTS FOR (h:HLEG) REQUIRE h.document_id IS UNIQUE",
            "CREATE CONSTRAINT hleg_requirement_id IF NOT EXISTS FOR (r:HLEGRequirement) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT hleg_subtopic_id IF NOT EXISTS FOR (s:HLEGSubtopic) REQUIRE s.id IS UNIQUE",
        ]

        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception:
                    # Constraint might already exist
                    pass
        print("HLEG constraints created.")

    def clear_hleg_data(self):
        """Clear existing HLEG data only (preserve EU AI Act data)."""
        with self.driver.session() as session:
            # Delete HLEG subtopics
            session.run("MATCH (s:HLEGSubtopic) DETACH DELETE s")
            # Delete HLEG requirements
            session.run("MATCH (r:HLEGRequirement) DETACH DELETE r")
            # Delete HLEG document node
            session.run("MATCH (h:HLEG) DETACH DELETE h")
        print("Existing HLEG data cleared (EU AI Act data preserved).")

    def ingest(self, doc: HlegDocumentRegex):
        """Ingest the HLEG document into Neo4j."""

        print("\nIngesting HLEG data into Neo4j...")

        with self.driver.session() as session:
            # Create the main HLEG document node
            session.run("""
                MERGE (h:HLEG {document_id: $doc_id})
                SET h.official_title = $official_title,
                    h.short_title = $short_title,
                    h.year = $year
            """,
                doc_id=doc.document_id,
                official_title=doc.official_title,
                short_title=doc.short_title,
                year=doc.year
            )
            print(f"Created HLEG node: {doc.document_id}")

            # Ingest requirements
            for req in doc.requirements:
                self._ingest_requirement(session, doc.document_id, req)

            print(f"Ingested {len(doc.requirements)} requirements")

        print("HLEG ingestion complete!")

    def _ingest_requirement(self, session, doc_id: str, req: HlegRequirementRegex):
        """Ingest a single requirement with its subtopics."""

        # Create requirement node
        session.run("""
            MATCH (h:HLEG {document_id: $doc_id})
            MERGE (r:HLEGRequirement {id: $req_id})
            SET r.order = $order,
                r.name = $name,
                r.short_description = $short_description,
                r.full_text = $full_text,
                r.related_principles = $related_principles,
                r.tags = $tags
            MERGE (h)-[:HAS_REQUIREMENT]->(r)
        """,
            doc_id=doc_id,
            req_id=req.id,
            order=req.order,
            name=req.name,
            short_description=req.short_description,
            full_text=req.full_text,
            related_principles=req.related_principles,
            tags=req.tags
        )

        # Ingest subtopics
        for subtopic in req.subtopics:
            self._ingest_subtopic(session, req.id, subtopic)

    def _ingest_subtopic(self, session, req_id: str, subtopic: HlegSubtopicRegex):
        """Ingest a subtopic under a requirement."""
        session.run("""
            MATCH (r:HLEGRequirement {id: $req_id})
            MERGE (s:HLEGSubtopic {id: $subtopic_id})
            SET s.label = $label,
                s.description = $description
            MERGE (r)-[:HAS_SUBTOPIC]->(s)
        """,
            req_id=req_id,
            subtopic_id=subtopic.id,
            label=subtopic.label,
            description=subtopic.description
        )


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main function to run the AI HLEG preprocessing pipeline."""

    print("=" * 70)
    print("AI HLEG Ethics Guidelines - Regex-Based Preprocessor")
    print("=" * 70)

    # Paths
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    data_file = project_dir / "data" / "ai_hleg.txt"

    # Check if file exists
    if not data_file.exists():
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)

    print(f"\nReading file: {data_file}")

    # Read the file
    text = read_file(str(data_file))
    print(f"File size: {len(text):,} characters, {len(text.splitlines()):,} lines")

    # Parse the document
    doc = parse_ai_hleg(text)

    # Validate: we must have exactly 7 requirements
    if len(doc.requirements) != 7:
        print(f"\nERROR: Expected 7 requirements, got {len(doc.requirements)}")
        sys.exit(1)

    print(f"\nValidation passed: exactly 7 requirements extracted")

    # Ingest into Neo4j
    print(f"\nConnecting to Neo4j at {NEO4J_URI}...")

    ingester = Neo4jIngester(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

    try:
        # Test connection
        with ingester.driver.session() as session:
            result = session.run("RETURN 1")
            result.single()
        print("Connection successful!")

        # Clear existing HLEG data and recreate
        ingester.clear_hleg_data()
        ingester.create_constraints()
        ingester.ingest(doc)

        # Print summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Document: {doc.official_title}")
        print(f"Year: {doc.year}")
        print(f"Requirements: {len(doc.requirements)}")

        # Print requirement details
        print("\nRequirements breakdown:")
        for req in doc.requirements:
            print(f"  {req.order}. {req.name}")
            print(f"     - ID: {req.id}")
            print(f"     - Subtopics: {len(req.subtopics)}")
            for st in req.subtopics:
                print(f"       * {st.label}")

        # Print sample Cypher queries
        print("\n" + "=" * 70)
        print("SAMPLE QUERIES")
        print("=" * 70)
        print("\nView all HLEG requirements:")
        print("  MATCH (h:HLEG)-[:HAS_REQUIREMENT]->(r:HLEGRequirement)")
        print("  RETURN h, r ORDER BY r.order;")
        print("\nView requirements with subtopics:")
        print("  MATCH (h:HLEG)-[:HAS_REQUIREMENT]->(r:HLEGRequirement)-[:HAS_SUBTOPIC]->(s:HLEGSubtopic)")
        print("  RETURN r.name, collect(s.label) AS subtopics ORDER BY r.order;")
        print("\nLink HLEG to EU AI Act (future):")
        print("  MATCH (r:HLEGRequirement), (a:Article)")
        print("  WHERE r.name CONTAINS 'transparency' AND a.title CONTAINS 'transparency'")
        print("  RETURN r.name, a.title;")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ingester.close()

    print("\nDone!")
    return doc


if __name__ == "__main__":
    main()

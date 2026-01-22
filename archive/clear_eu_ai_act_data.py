"""Clear all EU AI Act data from Neo4j before re-ingestion."""

from config.neo4j_config import execute_query, verify_connection

DOCUMENT_ID = "eu_ai_act_2024"

print("=" * 70)
print("CLEAR EU AI ACT DATA FROM NEO4J")
print("=" * 70)
print()

# Verify connection first
if not verify_connection():
    print("❌ Neo4j connection failed. Check config.neo4j_config.")
    exit(1)

print(f"Clearing all data for document: {DOCUMENT_ID}")
print()

# Step 1: Count what we're about to delete
print("Current database contents:")
query = """
MATCH (d:Regulation {document_id: $document_id})
OPTIONAL MATCH (d)-[:HAS_CHAPTER]->(c:Chapter)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(s:Section)
OPTIONAL MATCH (c)-[:HAS_SECTION|HAS_ARTICLE*..2]->(a:Article)
OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
OPTIONAL MATCH (p)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->()
RETURN count(DISTINCT c) AS chapters,
       count(DISTINCT s) AS sections,
       count(DISTINCT a) AS articles,
       count(DISTINCT p) AS paragraphs,
       count(r) AS mappings
"""
result = execute_query(query, document_id=DOCUMENT_ID)
if result:
    stats = result[0]
    print(f"  Chapters: {stats['chapters']}")
    print(f"  Sections: {stats['sections']}")
    print(f"  Articles: {stats['articles']}")
    print(f"  Paragraphs: {stats['paragraphs']}")
    print(f"  HLEG Mappings: {stats['mappings']}")
    print()

    if stats['chapters'] == 0:
        print("⚠️  No data found for this document. Nothing to clear.")
        exit(0)
else:
    print("  No data found.")
    print()
    exit(0)

# Step 2: Confirm deletion
print("⚠️  WARNING: This will delete all EU AI Act data and mappings!")
print("   This action cannot be undone.")
print()
response = input("Type 'yes' to confirm deletion: ")

if response.lower() != 'yes':
    print("❌ Deletion cancelled.")
    exit(0)

print()
print("Deleting data...")

# Step 3: Delete all relationships and nodes for this document
query = """
MATCH (d:Regulation {document_id: $document_id})
OPTIONAL MATCH (d)-[r*]->(n)
DETACH DELETE d, n
"""

try:
    execute_query(query, document_id=DOCUMENT_ID)
    print(f"✓ All data for '{DOCUMENT_ID}' has been cleared from Neo4j")
    print()
    print("Next steps:")
    print("  1. Run: python3 run_preprocess_eu_ai_act.py")
    print("  2. Run: python3 validate_structure.py")
    print("  3. Run: python3 run_map_eu_to_hleg.py")
    print()
except Exception as e:
    print(f"❌ Error deleting data: {e}")
    exit(1)

"""Quick diagnostic script to check Chapter III in Neo4j."""

from config.neo4j_config import execute_query

DOCUMENT_ID = "eu_ai_act_2024"

print("=" * 70)
print("CHAPTER III DIAGNOSTIC")
print("=" * 70)
print()

# 1. Check all chapters
print("1. All chapters in database:")
print("-" * 70)
query1 = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
RETURN c.number AS chapter, c.title
ORDER BY c.number
"""
chapters = execute_query(query1, document_id=DOCUMENT_ID)
for rec in chapters:
    print(f"  Chapter {rec['chapter']}: {rec['title']}")
print()

# 2. Check if Chapter III exists
print("2. Chapter III node:")
print("-" * 70)
query2 = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter {number: 'III'})
RETURN c.number, c.title
"""
ch3 = execute_query(query2, document_id=DOCUMENT_ID)
if ch3:
    print(f"  ✓ Chapter III exists: {ch3[0]['title']}")
else:
    print("  ✗ Chapter III NOT FOUND")
print()

# 3. Check Chapter III articles
print("3. Chapter III articles:")
print("-" * 70)
query3 = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter {number: 'III'})-[:HAS_ARTICLE]->(a:Article)
RETURN a.number AS article, a.title
ORDER BY a.number
"""
articles = execute_query(query3, document_id=DOCUMENT_ID)
if articles:
    for rec in articles:
        print(f"  Article {rec['article']}: {rec['title']}")
else:
    print("  ✗ No articles found in Chapter III")
print()

# 4. Check Chapter III paragraph counts
print("4. Chapter III paragraph counts by article:")
print("-" * 70)
query4 = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter {number: 'III'})-[:HAS_ARTICLE]->(a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
RETURN a.number AS article, count(p) AS paragraphs
ORDER BY a.number
"""
para_counts = execute_query(query4, document_id=DOCUMENT_ID)
if para_counts:
    total = 0
    for rec in para_counts:
        print(f"  Article {rec['article']}: {rec['paragraphs']} paragraphs")
        total += rec['paragraphs']
    print(f"\n  TOTAL Chapter III paragraphs: {total}")
else:
    print("  ✗ No paragraphs found in Chapter III")
print()

print("=" * 70)

"""
Comprehensive Structure Audit for EU AI Act in Neo4j

This script performs a thorough audit of:
1. Database structure completeness
2. Structural patterns and anomalies
3. Orphaned nodes
4. Numbering consistency
5. Chapter-specific structure validation
"""

from config.neo4j_config import execute_query
from collections import defaultdict

DOCUMENT_ID = "eu_ai_act_2024"

print("=" * 80)
print("EU AI ACT STRUCTURE AUDIT")
print("=" * 80)
print()

# ============================================================================
# 1. HIGH-LEVEL OVERVIEW
# ============================================================================

print("1. HIGH-LEVEL OVERVIEW")
print("-" * 80)

# Check Regulation node
query = """
MATCH (d:Regulation {document_id: $document_id})
RETURN d.document_id AS doc_id, d.title AS title
"""
reg = execute_query(query, document_id=DOCUMENT_ID)
if reg:
    print(f"✓ Regulation node found: {reg[0]['title']}")
else:
    print("✗ Regulation node NOT FOUND")
    exit(1)

# Count all node types
query = """
MATCH (d:Regulation {document_id: $document_id})
OPTIONAL MATCH (d)-[:HAS_CHAPTER]->(c:Chapter)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(s:Section)
OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a1:Article)
OPTIONAL MATCH (s)-[:HAS_ARTICLE]->(a2:Article)
OPTIONAL MATCH (a1)-[:HAS_PARAGRAPH]->(p1:Paragraph)
OPTIONAL MATCH (a2)-[:HAS_PARAGRAPH]->(p2:Paragraph)
RETURN count(DISTINCT c) AS chapters,
       count(DISTINCT s) AS sections,
       count(DISTINCT a1) + count(DISTINCT a2) AS articles,
       count(DISTINCT p1) + count(DISTINCT p2) AS paragraphs
"""
counts = execute_query(query, document_id=DOCUMENT_ID)[0]
print(f"  Chapters: {counts['chapters']}")
print(f"  Sections: {counts['sections']}")
print(f"  Articles: {counts['articles']}")
print(f"  Paragraphs: {counts['paragraphs']}")
print()

# ============================================================================
# 2. CHAPTER STRUCTURE PATTERNS
# ============================================================================

print("2. CHAPTER STRUCTURE PATTERNS")
print("-" * 80)

query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
OPTIONAL MATCH (c)-[:HAS_SECTION]->(s:Section)
OPTIONAL MATCH (c)-[:HAS_ARTICLE]->(a_direct:Article)
OPTIONAL MATCH (s)-[:HAS_ARTICLE]->(a_section:Article)
WITH c,
     count(DISTINCT s) AS section_count,
     count(DISTINCT a_direct) AS direct_articles,
     count(DISTINCT a_section) AS section_articles
RETURN c.number AS chapter,
       c.title AS title,
       section_count > 0 AS has_sections,
       direct_articles AS direct_articles,
       section_articles AS articles_via_sections,
       direct_articles + section_articles AS total_articles
ORDER BY c.number
"""
chapters = execute_query(query, document_id=DOCUMENT_ID)

direct_pattern = []
section_pattern = []
mixed_pattern = []

for ch in chapters:
    pattern = ""
    if ch['direct_articles'] > 0 and ch['articles_via_sections'] == 0:
        pattern = "Chapter→Article"
        direct_pattern.append(ch['chapter'])
    elif ch['direct_articles'] == 0 and ch['articles_via_sections'] > 0:
        pattern = "Chapter→Section→Article"
        section_pattern.append(ch['chapter'])
    elif ch['direct_articles'] > 0 and ch['articles_via_sections'] > 0:
        pattern = "MIXED (both patterns!)"
        mixed_pattern.append(ch['chapter'])
    else:
        pattern = "NO ARTICLES"

    print(f"  Ch {ch['chapter']:>3}: {pattern:>30} | "
          f"Direct: {ch['direct_articles']:>2}, Via Section: {ch['articles_via_sections']:>2}, "
          f"Total: {ch['total_articles']:>2}")

print()
print(f"Pattern Summary:")
print(f"  Direct (Ch→Art): {len(direct_pattern)} chapters: {', '.join(direct_pattern)}")
print(f"  Sectioned (Ch→Sec→Art): {len(section_pattern)} chapters: {', '.join(section_pattern)}")
if mixed_pattern:
    print(f"  ⚠️ MIXED patterns: {len(mixed_pattern)} chapters: {', '.join(mixed_pattern)}")
print()

# ============================================================================
# 3. PARAGRAPH COUNTS BY CHAPTER
# ============================================================================

print("3. PARAGRAPH COUNTS BY CHAPTER")
print("-" * 80)

query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
RETURN c.number AS chapter,
       count(DISTINCT a) AS article_count,
       count(p) AS paragraph_count
ORDER BY c.number
"""
para_counts = execute_query(query, document_id=DOCUMENT_ID)

total_paras = 0
for rec in para_counts:
    print(f"  Ch {rec['chapter']:>3}: {rec['article_count']:>3} articles, {rec['paragraph_count']:>4} paragraphs")
    total_paras += rec['paragraph_count']

print(f"\n  TOTAL: {total_paras} paragraphs")
print()

# ============================================================================
# 4. ORPHANED NODES CHECK
# ============================================================================

print("4. ORPHANED NODES CHECK")
print("-" * 80)

# Chapters without articles
query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
WHERE NOT (c)-[:HAS_ARTICLE]->() AND NOT (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->()
RETURN c.number AS chapter, c.title AS title
"""
orphan_chapters = execute_query(query, document_id=DOCUMENT_ID)
if orphan_chapters:
    print(f"⚠️ {len(orphan_chapters)} chapters without articles:")
    for ch in orphan_chapters:
        print(f"    - Chapter {ch['chapter']}: {ch['title']}")
else:
    print("✓ No orphaned chapters")

# Articles without paragraphs
query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
MATCH (a:Article)
WHERE ((c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a))
  AND NOT (a)-[:HAS_PARAGRAPH]->()
RETURN c.number AS chapter, a.number AS article, a.title AS title
ORDER BY c.number, a.number
"""
orphan_articles = execute_query(query, document_id=DOCUMENT_ID)
if orphan_articles:
    print(f"⚠️ {len(orphan_articles)} articles without paragraphs:")
    for art in orphan_articles[:10]:  # Show first 10
        print(f"    - Ch {art['chapter']}, Art {art['article']}: {art['title']}")
    if len(orphan_articles) > 10:
        print(f"    ... and {len(orphan_articles) - 10} more")
else:
    print("✓ No orphaned articles")

# Sections without articles
query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)-[:HAS_SECTION]->(s:Section)
WHERE NOT (s)-[:HAS_ARTICLE]->()
RETURN c.number AS chapter, s.number AS section, s.title AS title
ORDER BY c.number, s.number
"""
orphan_sections = execute_query(query, document_id=DOCUMENT_ID)
if orphan_sections:
    print(f"⚠️ {len(orphan_sections)} sections without articles:")
    for sec in orphan_sections[:10]:
        print(f"    - Ch {sec['chapter']}, Sec {sec['section']}: {sec['title']}")
    if len(orphan_sections) > 10:
        print(f"    ... and {len(orphan_sections) - 10} more")
else:
    print("✓ No orphaned sections")

print()

# ============================================================================
# 5. ARTICLE NUMBERING CONSISTENCY
# ============================================================================

print("5. ARTICLE NUMBERING CONSISTENCY")
print("-" * 80)

query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
MATCH (a:Article)
WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
RETURN c.number AS chapter, collect(DISTINCT a.number) AS article_numbers
ORDER BY c.number
"""
article_nums = execute_query(query, document_id=DOCUMENT_ID)

issues = []
for rec in article_nums:
    nums = sorted([int(n) for n in rec['article_numbers'] if str(n).isdigit()])
    if len(nums) > 1:
        gaps = []
        for i in range(len(nums) - 1):
            if nums[i+1] - nums[i] > 1:
                gaps.append(f"{nums[i]}→{nums[i+1]}")
        if gaps:
            issues.append(f"Ch {rec['chapter']}: gaps in numbering: {', '.join(gaps)}")

if issues:
    print("⚠️ Potential numbering gaps found:")
    for issue in issues[:5]:
        print(f"    {issue}")
else:
    print("✓ No obvious numbering gaps detected")

print()

# ============================================================================
# 6. DUPLICATE DETECTION
# ============================================================================

print("6. DUPLICATE DETECTION")
print("-" * 80)

# Check for duplicate article numbers within same chapter
query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
MATCH (a:Article)
WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
WITH c.number AS chapter, a.number AS article_num, count(a) AS article_count
WHERE article_count > 1
RETURN chapter, article_num, article_count
ORDER BY chapter, article_num
"""
dup_articles = execute_query(query, document_id=DOCUMENT_ID)
if dup_articles:
    print(f"⚠️ {len(dup_articles)} duplicate article numbers found:")
    for dup in dup_articles[:10]:
        print(f"    - Ch {dup['chapter']}, Art {dup['article_num']}: appears {dup['article_count']} times")
else:
    print("✓ No duplicate article numbers within chapters")

# Check for duplicate paragraph indices within same article
query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter)
MATCH (a:Article)-[:HAS_PARAGRAPH]->(p:Paragraph)
WHERE (c)-[:HAS_ARTICLE]->(a) OR (c)-[:HAS_SECTION]->()-[:HAS_ARTICLE]->(a)
WITH c.number AS chapter, a.number AS article, p.index AS para_index, count(p) AS para_count
WHERE para_count > 1
RETURN chapter, article, para_index, para_count
ORDER BY chapter, article, para_index
LIMIT 10
"""
dup_paras = execute_query(query, document_id=DOCUMENT_ID)
if dup_paras:
    print(f"⚠️ Duplicate paragraph indices found:")
    for dup in dup_paras:
        print(f"    - Ch {dup['chapter']}, Art {dup['article']}, Para {dup['para_index']}: appears {dup['para_count']} times")
else:
    print("✓ No duplicate paragraph indices within articles")

print()

# ============================================================================
# 7. CHAPTER III DETAILED ANALYSIS
# ============================================================================

print("7. CHAPTER III DETAILED ANALYSIS (Section-based structure)")
print("-" * 80)

query = """
MATCH (d:Regulation {document_id: $document_id})-[:HAS_CHAPTER]->(c:Chapter {number: 'III'})-[:HAS_SECTION]->(s:Section)
OPTIONAL MATCH (s)-[:HAS_ARTICLE]->(a:Article)
OPTIONAL MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph)
RETURN s.number AS section,
       s.title AS section_title,
       count(DISTINCT a) AS article_count,
       count(p) AS paragraph_count
ORDER BY s.number
"""
ch3_sections = execute_query(query, document_id=DOCUMENT_ID)

print(f"Chapter III has {len(ch3_sections)} sections:")
for sec in ch3_sections:
    print(f"  Section {sec['section']:>2}: {sec['article_count']:>2} articles, {sec['paragraph_count']:>3} paragraphs | {sec['section_title']}")

print()

# ============================================================================
# SUMMARY
# ============================================================================

print("=" * 80)
print("AUDIT SUMMARY")
print("=" * 80)
print(f"✓ Database contains {counts['chapters']} chapters, {counts['articles']} articles, {counts['paragraphs']} paragraphs")
print(f"✓ Found {len(section_pattern)} chapters using Section structure: {', '.join(section_pattern)}")
print(f"✓ Found {len(direct_pattern)} chapters using direct Article structure")
if mixed_pattern:
    print(f"⚠️ Warning: {len(mixed_pattern)} chapters have MIXED structure patterns")
if orphan_chapters or orphan_articles or orphan_sections:
    print(f"⚠️ Warning: Found orphaned nodes (see details above)")
if dup_articles or dup_paras:
    print(f"⚠️ Warning: Found duplicate numbering (see details above)")
print()
print("Next step: Compare against source document to verify completeness")
print("=" * 80)

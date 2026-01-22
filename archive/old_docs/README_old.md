# EU AI Act Structural Preprocessing - Trustworthy LLM System

**PhD Research Project: Trustworthiness in LLM-based Systems**

## Overview

This project implements a **trustworthy preprocessing pipeline** for extracting the structural elements of the EU AI Act (Regulation 2024/1689) and storing them in a Neo4j graph database.

### Key Trustworthiness Principles

1. **Separation of Concerns**: LLM extraction is strictly separated from deterministic operations
2. **No Hallucination**: Only extracts explicitly present structure, never invents content
3. **Deterministic Storage**: Database writes are reproducible and use idempotent operations
4. **Conservative Design**: Minimal dependencies, clear data flow, explicit validation
5. **Transparency**: All steps are logged and traceable

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   TRUSTWORTHY PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. INPUT (Deterministic)                                       │
│     ├─ eu_ai_act_part_1.txt                                    │
│     └─ eu_ai_act_part_2.txt                                    │
│                    ↓                                            │
│  2. SPLITTING (Deterministic - No LLM)                         │
│     ├─ eu_ai_act_splitter.py                                   │
│     └─ Split by regex into semantic chunks                     │
│                    ↓                                            │
│  3. EXTRACTION (LLM Phase - Parallel)                          │
│     ├─ agent_preprocess_eu_ai_act.py                           │
│     ├─ Uses gpt-5-nano with structured output                  │
│     ├─ Processes chunks in parallel (rate-limited)             │
│     └─ Validates output with Pydantic models                   │
│                    ↓                                            │
│  4. MERGING (Deterministic)                                    │
│     └─ Combines chunk results into single document             │
│                    ↓                                            │
│  5. INGESTION (Deterministic - No LLM)                         │
│     ├─ ingest_preprocessed_legal.py                            │
│     ├─ Creates Neo4j graph using MERGE (idempotent)            │
│     └─ No semantic interpretation, only structure              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

### Core Files (Minimal Set)

```
trustworthy_project_v0/
├── README.md                          # This file
├── requirements.txt                   # 3 dependencies only
├── .env                              # API keys (not in repo)
│
├── run_preprocess_eu_ai_act.py       # MAIN ENTRY POINT
│
├── agent_preprocess_eu_ai_act.py     # LLM agent (extraction only)
├── eu_ai_act_splitter.py             # Deterministic text splitting
├── ingest_preprocessed_legal.py      # Deterministic Neo4j writes
│
├── models/
│   ├── legal_structure.py            # Core Pydantic models
│   ├── legal_chunks.py               # Chunk processing models
│   └── legal_preprocess.py           # Agent dependency model
│
├── config/
│   └── neo4j_config.py               # Database connection
│
└── data/
    ├── eu_ai_act_part_1.txt          # Input text (part 1)
    └── eu_ai_act_part_2.txt          # Input text (part 2)
```

## Detailed Steps

### Step 1: Read Input Files (Deterministic)

**File**: `run_preprocess_eu_ai_act.py` - `read_eu_ai_act_text()`

- Reads `eu_ai_act_part_1.txt` and `eu_ai_act_part_2.txt`
- Merges with single newline separator
- Returns raw text string

**Trustworthiness**: Deterministic file I/O, no interpretation

### Step 2: Split into Chunks (Deterministic)

**File**: `eu_ai_act_splitter.py` - `split_eu_ai_act()`

- Uses **regex patterns only** (no LLM) to find:
  - Recitals: `^\(\d+\)` pattern
  - Chapters: `^CHAPTER [IVXLCDM]+` pattern
  - Sections: `^SECTION \d+` pattern
  - Annexes: `^ANNEX [IVXLCDM]+` pattern
- Splits into 34 chunks (3 recital batches, 18 chapters, 13 annexes)
- Each chunk is a `TextChunk` with `kind`, `label`, and `text`

**Trustworthiness**:
- No LLM involved - purely pattern matching
- Reproducible - same input always produces same chunks
- Transparent - regex patterns are explicit
- **Section Constraint Enforcement**: Regex-detected SECTION headings constrain the LLM agent to prevent inventing sections from high article numbers (40+). Sections are validated deterministically before and after LLM processing.

**Debugging Missing Paragraphs**:

If you encounter missing paragraphs for specific articles (e.g., Articles 40-49 in Section 5):

1. **Enable Debug Mode** in `run_preprocess_eu_ai_act.py`:
   ```python
   CHUNK_LABEL_FILTER = "CHAPTER III - SECTION 5"  # Debug specific chunk
   ```

2. **Run Preprocessing**: Only the filtered chunk will be processed
   ```bash
   python run_preprocess_eu_ai_act.py
   ```

3. **Inspect Output**: Check `debug_chunk_result.json` for extracted articles and paragraphs
   ```bash
   # Verify Articles 40-49 exist with paragraphs
   grep -A 5 '"number": 40' debug_chunk_result.json
   ```

4. **Fix and Rerun Full Preprocessing**:
   ```python
   CHUNK_LABEL_FILTER = None  # Disable debug mode
   ```
   ```bash
   python run_preprocess_eu_ai_act.py      # Full ingestion
   python run_map_eu_to_hleg.py            # Remap with updated structure
   ```

5. **Verify in Neo4j**:
   ```cypher
   MATCH (a:Article {number:40})-[:HAS_PARAGRAPH]->(p) RETURN count(p);
   MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->() RETURN count(r);
   ```

### Step 3: Extract Structure with LLM (Parallel)

**File**: `agent_preprocess_eu_ai_act.py` - `preprocess_legal_chunk_agent`

**Model**: gpt-5-nano (400k input / 128k output)

**Input**: Each chunk's raw text + deterministic metadata

**Output**: `ChunkResult` - Pydantic-validated structure containing:
- For recitals: List of `Recital(number, text)`
- For chapters: `Chapter` with nested `Section`, `Article`, `Paragraph`, `Point`
- For annexes: `Annex(number, title, raw_text)`

**Validation**:
- Pydantic models enforce schema
- Field validators coerce types (e.g., int → str for Section.number)
- Agent retries up to 3 times on validation errors
- No hallucination: Instructions explicitly forbid inventing structure

**Parallel Processing**:
- Processes up to 3 chunks concurrently (semaphore-limited)
- Dramatically faster than sequential
- Progress logged: `[chunk X/34]`

**Trustworthiness**:
- LLM only extracts what's present in text
- Structured output validated by Pydantic
- Retries handle transient errors
- No database writes in this phase

### Step 4: Merge Chunks (Deterministic)

**File**: `run_preprocess_eu_ai_act.py` - `preprocess_eu_ai_act_by_chunks()`

- Collects all `ChunkResult` objects
- Merges into single `PreprocessedLegalDocument`:
  - Concatenates recitals from all recital chunks
  - Merges chapter sections (some chapters split across chunks)
  - Appends all annexes
- Sorts to maintain original order

**Trustworthiness**: Simple data aggregation, no LLM

### Step 5: Ingest to Neo4j (Deterministic)

**File**: `ingest_preprocessed_legal.py` - `ingest_preprocessed_legal_document()`

**Graph Schema**:
```cypher
(:Regulation)-[:HAS_RECITAL]->(:Recital)
(:Regulation)-[:HAS_CHAPTER]->(:Chapter)
(:Chapter)-[:HAS_SECTION]->(:Section)
(:Chapter)-[:HAS_ARTICLE]->(:Article)
(:Section)-[:HAS_ARTICLE]->(:Article)
(:Article)-[:HAS_PARAGRAPH]->(:Paragraph)
(:Paragraph)-[:HAS_POINT]->(:Point)
(:Regulation)-[:HAS_ANNEX]->(:Annex)
```

**Operations**: All `MERGE` statements (idempotent)
- Can re-run without duplicating nodes
- Deterministic properties (number, title, text)
- No semantic labels (no risk categories, no actors)

**Trustworthiness**:
- No LLM involved
- Reproducible writes
- Idempotent operations
- Only structural information

### Step 6: Coverage Check (Optional - Overlapping Window Validation)

**File**: `validate_structure.py` - `coverage_check_chapter()`

**Purpose**: Detect and recover missing articles that the primary extraction may have missed, especially in long chapters with many articles.

**How It Works**:

1. **Post-Extraction Validation**: After primary extraction completes, optionally run a coverage check
2. **Overlapping Windows**: Scan source text with overlapping windows (e.g., 10 articles per window, stride of 7 = 3-article overlap)
3. **Lightweight Coverage Agent**: For each window, run a fast LLM call that only identifies article numbers present (not full extraction)
4. **Diff Against Primary**: Compare article numbers found in source vs what was extracted
5. **Targeted Re-Extraction**: Re-run only the chunks with missing articles, with explicit hints about what's missing
6. **Automatic Deduplication**: Neo4j MERGE handles any duplicate articles automatically

**Why This Helps**:
- Overlapping windows catch boundary articles that LLM might miss at chunk edges
- Lightweight coverage check is fast (only article numbers, not full structure)
- Explicit hints ("Extract articles 86, 87, 88...") are more effective than blind retries
- Only processes what failed, not entire corpus
- Addresses cases where LLM stops early or skips articles

**Configuration** (`run_preprocess_eu_ai_act.py`):

```python
# ============================================================================
# COVERAGE CHECK CONFIGURATION (Overlapping Window Validation)
# ============================================================================
ENABLE_COVERAGE_CHECK = False  # Set to True to enable overlap validation
COVERAGE_WINDOW_SIZE = 10      # Number of articles per window
COVERAGE_STRIDE = 7            # Articles between window starts (overlap = window - stride)
COVERAGE_CHAPTERS = ["IX"]     # Which chapters to check, or None for all
```

**Enable for Testing**:

```python
# In run_preprocess_eu_ai_act.py
ENABLE_COVERAGE_CHECK = True   # Enable coverage check
COVERAGE_CHAPTERS = ["IX"]     # Test on Chapter IX first
```

**Expected Output**:

```
======================================================================
📊 COVERAGE CHECK - Overlapping Window Validation
======================================================================
Window size: 10, Stride: 7
Checking chapters: ['IX']

Chapter IX: Scanning 29 articles with overlapping windows...
  Window 1 (Articles 66-75): ✅ All present
  Window 2 (Articles 73-82): ⚠️  Missing: [79, 80]
  Window 3 (Articles 80-89): ⚠️  Missing: [86, 87, 88]
  Window 4 (Articles 87-94): ✅ All present

   ⚠️  Chapter IX: 5 missing articles: [79, 80, 86, 87, 88]

======================================================================
🔄 RE-EXTRACTING CHUNKS WITH MISSING ARTICLES
======================================================================

Chapter IX: Re-extracting to recover articles [79, 80, 86, 87, 88]
[chunk 1/1] Processing chapter CHAPTER IX (with hints: [79, 80, 86, 87, 88])...
🔍 MISSING ARTICLE RECOVERY:
   The following articles were MISSING: [79, 80, 86, 87, 88]
   ⚠️⚠️⚠️ CRITICAL: You MUST include these specific articles!

  → [1/1] Extracted 29 articles (recovered all 5 missing)
✓ [1/1] Finished chapter CHAPTER IX

✅ Coverage check recovery complete!
```

**Verification**:

After coverage check completes, verify all articles are present:

```bash
python validate_structure.py
```

Or check specific chapters in Neo4j:

```cypher
// Check Chapter IX has all 29 articles (Articles 66-94)
MATCH (c:Chapter {number: 'IX'})-[:HAS_SECTION|HAS_ARTICLE*1..2]->(a:Article)
WITH c, collect(DISTINCT a.number) as article_nums
RETURN c.number as chapter,
       size(article_nums) as count,
       article_nums
ORDER BY chapter;

// Find any missing articles in sequence
WITH range(66, 94) as expected
MATCH (c:Chapter {number: 'IX'})-[:HAS_SECTION|HAS_ARTICLE*1..2]->(a:Article)
WITH expected, collect(DISTINCT a.number) as actual
RETURN [x IN expected WHERE NOT x IN actual] as missing_articles;
```

**When to Use**:
- Chapter-level extraction shows missing articles (e.g., Chapter IX: 4/29 articles)
- Post-validation reports coverage < 95%
- Known problematic chapters with many articles
- After fixing extraction bugs, to ensure no regressions

**Trustworthiness**:
- Deterministic source parsing (regex-based article detection)
- Lightweight LLM validation (only article numbers, not content)
- Explicit hints reduce LLM ambiguity
- Idempotent re-ingestion (MERGE handles duplicates)
- Transparent logging of missing articles and recovery

## Data Models

### Core Models (`models/legal_structure.py`)

```python
class Recital(BaseModel):
    number: int
    text: str

class Point(BaseModel):
    marker: str  # "a", "b", "c"
    text: str

class Paragraph(BaseModel):
    index: int  # NOT 'number'!
    text: str   # NOT 'title'!
    points: List[Point]

class Article(BaseModel):
    number: int
    title: str
    paragraphs: List[Paragraph]

class Section(BaseModel):
    number: str  # String! (has validator to coerce int→str)
    title: str
    articles: List[Article]

class Chapter(BaseModel):
    number: str  # Roman numerals (has validator)
    title: str
    sections: List[Section]  # Either sections OR articles
    articles: List[Article]  # Not both!

class Annex(BaseModel):
    number: str  # Roman numerals (has validator)
    title: str
    raw_text: str

class PreprocessedLegalDocument(BaseModel):
    document_id: str
    official_title: str
    short_title: str
    year: int
    recitals: List[Recital]
    chapters: List[Chapter]
    annexes: List[Annex]
```

### Field Validators (Trustworthiness Feature)

```python
@field_validator('number', mode='before')
@classmethod
def coerce_number_to_str(cls, v: Any) -> str:
    """LLM often returns int instead of str - auto-convert"""
    if isinstance(v, int):
        return str(v)
    return v
```

Applied to: `Section.number`, `Chapter.number`, `Annex.number`

**Why**: LLMs sometimes return integers when strings are expected. Instead of failing validation, we auto-coerce. This is more robust while maintaining type safety.

## Running the Pipeline

### Prerequisites

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cat > .env << EOF
OPENAI_API_KEY=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
EOF

# 3. Start Neo4j
# (assumes you have Neo4j installed and running)
```

### Execute

```bash
python run_preprocess_eu_ai_act.py
```

### Expected Output

```
Prerequisites:
  ✓ OPENAI_API_KEY in .env file
  ✓ Neo4j running on localhost:7687
  ✓ eu_ai_act_part_1.txt and eu_ai_act_part_2.txt in project root

[1/2] Running structural preprocessing agent (parallel chunked)...

Splitting document into chunks...
Using 34 refined chunks (recitals/chapters/annexes).
Processing chunks in parallel (max 3 concurrent)...

[chunk 1/34] Processing recitals RECITALS (1-60) (86,239 chars, ~21,559 tokens)...
[chunk 2/34] Processing recitals RECITALS (61-120) (72,291 chars, ~18,072 tokens)...
...
✓ [34/34] Finished annex ANNEX XIII

✓ STRUCTURAL PREPROCESSING COMPLETE

Summary:
  - Document ID: eu_ai_act_2024
  - Recitals: 180
  - Chapters: 13
  - Articles (total): ~180
  - Annexes: 13

[2/2] Ingesting structured data to Neo4j...

✓ PREPROCESSING AND INGESTION COMPLETE
```

## Verifying Results

### Query Neo4j

```cypher
// Count recitals
MATCH (r:Regulation)-[:HAS_RECITAL]->(rec:Recital)
RETURN count(rec)

// List all chapters
MATCH (r:Regulation)-[:HAS_CHAPTER]->(ch:Chapter)
RETURN ch.number, ch.title
ORDER BY ch.number

// Find articles in Chapter III
MATCH (ch:Chapter {number: 'III'})-[:HAS_SECTION]->(:Section)-[:HAS_ARTICLE]->(art:Article)
RETURN art.number, art.title
ORDER BY art.number

// Get article with paragraphs and points
MATCH (art:Article {number: 5})-[:HAS_PARAGRAPH]->(para:Paragraph)
OPTIONAL MATCH (para)-[:HAS_POINT]->(pt:Point)
RETURN art.title, para.index, para.text, collect(pt.marker + ': ' + pt.text) as points
```

## Trustworthiness Guarantees

| Aspect | Guarantee | How Enforced |
|--------|-----------|--------------|
| **No Hallucination** | LLM only extracts what's present | Explicit instructions + validation |
| **Reproducibility** | Same input → same output | Deterministic splitting + idempotent MERGE |
| **Separation** | LLM never touches database | Separate extraction and ingestion phases |
| **Validation** | All data conforms to schema | Pydantic models with validators |
| **Transparency** | All steps logged | Console output shows progress |
| **Minimalism** | Only 3 dependencies | Small attack surface, easy audit |

## For PhD Research

### Key Insights for Trustworthiness

1. **LLM Limitations**:
   - Type confusion (int vs str) → Solved with validators
   - JSON malformation (high max_tokens) → Solved with reasonable limits
   - Hallucination risk → Solved with explicit instructions + validation

2. **Architecture Patterns**:
   - **Phased approach**: Separate LLM from deterministic operations
   - **Idempotent operations**: Use MERGE, not CREATE
   - **Conservative extraction**: "Extract what's there" not "interpret"

3. **Validation Strategy**:
   - Schema validation (Pydantic)
   - Type coercion (field validators)
   - Retry logic (up to 3 attempts)
   - No partial writes (atomic transactions)

4. **Scalability**:
   - Parallel processing (semaphore-limited)
   - Chunked approach (avoids context limits)
   - Progress tracking (user visibility)

## EU→HLEG Mapping (Contextual Full-Corpus Mode)

### Overview

After preprocessing both the EU AI Act and AI HLEG guidelines, this system creates **semantic alignment mappings** between EU AI Act paragraphs and HLEG requirements.

**Key Features:**
- **Full-corpus mode**: Maps ALL paragraphs by default (not just high-impact ones)
- **Rich contextual prompting**: Includes structural headings + neighboring paragraphs
- **Configurable filtering**: Test with subsets before running full corpus
- **Deterministic ingestion**: LLM does semantic mapping, database writes are reproducible
- **Inspectable rationales**: Each mapping includes relevance score + explanation

### Configuration Knobs

Edit `run_map_eu_to_hleg.py` to configure:

```python
# Candidate selection
CANDIDATE_REGEX = None  # Filter by text pattern (e.g., r'(?i).*(shall|must|prohibited).*')
LIMIT_CHAPTERS = None   # Process specific chapters (e.g., ['II', 'III', 'IV'])
MAX_PARAGRAPHS = None   # Limit for dry runs (e.g., 50), None for full corpus

# Processing controls
MAX_CONCURRENCY = 3     # Parallel processing limit
MODEL_MAX_TOKENS = 4096 # Completion token cap

# Testing
DRY_RUN = False         # True = skip ingestion, log only
```

### How It Works

1. **Fetch paragraphs with context**:
   - Structural location: chapter/section/article titles and numbers
   - Target paragraph text
   - Previous paragraph (context)
   - Next paragraph (context)

2. **Build contextual prompt**:
   ```
   STRUCTURAL CONTEXT:
     Chapter III: High-risk AI systems
     Section 2: Requirements for high-risk AI systems
     Article 10: Data and data governance
     Paragraph 3

   PREVIOUS PARAGRAPH (context only):
     [text from paragraph 2]

   TARGET PARAGRAPH (classify THIS):
     [text from paragraph 3]

   NEXT PARAGRAPH (context only):
     [text from paragraph 4]
   ```

3. **LLM classification**:
   - Agent evaluates TARGET paragraph against 7 HLEG requirements
   - Returns 0-3 links with relevance scores (0.0-1.0) and rationales
   - Empty links list is valid (non-substantive paragraphs)

4. **Deterministic ingestion**:
   - Creates `ALIGNS_WITH_HLEG_REQUIREMENT` relationships
   - Stores relevance, rationale, source, timestamp
   - Idempotent (re-running updates existing relationships)

### Running the Mapping

```bash
# Full corpus (all paragraphs)
python run_map_eu_to_hleg.py

# Dry run test (first 50 paragraphs, no ingestion)
# Edit script: MAX_PARAGRAPHS=50, DRY_RUN=True
python run_map_eu_to_hleg.py

# Specific chapters only
# Edit script: LIMIT_CHAPTERS=['II', 'III']
python run_map_eu_to_hleg.py
```

### Verification Queries

**Count total mappings:**
```cypher
MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)
RETURN count(r) as total_mappings;
```

**Sample high-relevance mappings:**
```cypher
MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)
RETURN p.index,
       substring(p.text, 0, 100) + '...' as paragraph,
       h.name as hleg_requirement,
       r.relevance,
       r.rationale
ORDER BY r.relevance DESC
LIMIT 10;
```

**Mappings per HLEG requirement:**
```cypher
MATCH (h:HLEGRequirement)<-[r:ALIGNS_WITH_HLEG_REQUIREMENT]-(p:Paragraph)
RETURN h.name, count(p) as paragraph_count
ORDER BY paragraph_count DESC;
```

**Find paragraphs aligned with multiple requirements:**
```cypher
MATCH (p:Paragraph)-[r:ALIGNS_WITH_HLEG_REQUIREMENT]->(h:HLEGRequirement)
WITH p, count(h) as req_count, collect(h.name) as requirements
WHERE req_count > 1
RETURN p.index, substring(p.text, 0, 80) + '...' as text,
       req_count, requirements
ORDER BY req_count DESC
LIMIT 10;
```

### Graph Schema

```
(Paragraph)-[:ALIGNS_WITH_HLEG_REQUIREMENT {
  relevance: float (0.0-1.0),
  rationale: string,
  source: string,
  mapped_at: datetime,
  paragraph_text_snapshot: string
}]->(HLEGRequirement)
```

### Trustworthiness Principles

1. **LLM for semantic decisions only**: Agent determines which HLEG requirements are relevant
2. **Deterministic ingestion**: Database writes have no LLM involvement
3. **Rationales required**: Every mapping must explain WHY it's relevant
4. **Context-aware but scoped**: Neighboring paragraphs improve understanding, but links are only for TARGET
5. **Inspectable and auditable**: Rationales make LLM decisions transparent for PhD research

## Troubleshooting

### Common Issues

**1. Validation Error: Section.number type mismatch**
- Symptom: `Input should be a valid string [type=string_type, input_value=10, input_type=int]`
- Cause: LLM returns integer instead of string
- Fix: Field validators auto-coerce (already implemented)

**2. JSON Parsing Errors**
- Symptom: `Input should be an object [type=model_type, input_value='number":41,', input_type=str]`
- Cause: max_tokens too high (128k → malformed JSON)
- Fix: Reduced to 32k tokens

**3. Neo4j Connection Error**
- Symptom: `Failed to connect to Neo4j`
- Fix: Check Neo4j is running and credentials in `.env`

## Dependencies

Minimal set of 3 dependencies:

1. **pydantic-ai** (1.20.0): LLM agent framework with structured output
2. **neo4j** (6.0.3): Graph database driver
3. **python-dotenv** (1.2.1): Environment variable loading

## License

Research/Educational Use

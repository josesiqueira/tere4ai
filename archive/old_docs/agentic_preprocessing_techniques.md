# Agentic Preprocessing Techniques

This document catalogs the techniques implemented in the `trustworthy_project_v0` codebase for preprocessing the EU AI Act using an agentic LLM approach. These techniques are designed to maximize extraction accuracy, handle failures gracefully, and ensure trustworthy, reproducible results.

---

## 1. Semantic Chunking

**Location:** `eu_ai_act_splitter.py:279-450`

The document is split into semantically meaningful units rather than arbitrary character/token boundaries:

- **Recitals chunk** - All "Whereas" clauses grouped together
- **Chapter chunks** - One chunk per chapter (CHAPTER I, II, etc.)
- **Annex chunks** - One chunk per annex (ANNEX I, II, etc.)

This ensures the LLM receives coherent legal units with complete context, improving extraction accuracy.

```python
# Pattern-based splitting (no LLM involved)
chapter_pattern = re.compile(r'^CHAPTER\s+([IVXLC]+)', re.MULTILINE | re.IGNORECASE)
annex_pattern = re.compile(r'^ANNEX\s+([IVXLC]+)', re.MULTILINE | re.IGNORECASE)
```

---

## 2. Recital Batching

**Location:** `eu_ai_act_splitter.py:52-108`

The EU AI Act has 180+ recitals, which would exceed context limits. The splitter batches recitals into groups of ~60:

```python
def _split_recitals(recitals_text: str, batch_size: int = 60) -> List[TextChunk]:
    # Pattern to find recital markers: (1), (2), (3), etc.
    recital_pattern = re.compile(r'^\(\d+\)', re.MULTILINE)
```

Each batch becomes a labeled chunk: `RECITALS (1-60)`, `RECITALS (61-120)`, etc.

---

## 3. Section-Level Splitting for Large Chapters

**Location:** `eu_ai_act_splitter.py:111-171`

Chapter III ("High-Risk AI Systems") is too large for a single LLM call. It's automatically split by SECTION headings:

```python
def _split_large_chapter_by_sections(chapter_text: str, chapter_num: str) -> List[TextChunk]:
    section_pattern = re.compile(r'^SECTION (\d+)', re.MULTILINE)
```

This produces chunks like:
- `CHAPTER III - SECTION 1 - Classification of AI systems as high-risk`
- `CHAPTER III - SECTION 2 - Requirements for high-risk AI systems`

---

## 4. Token Estimation

**Location:** `run_preprocess_eu_ai_act.py:67-84`

A simple heuristic estimates token count before processing to detect oversized chunks:

```python
def approx_token_count(text: str) -> int:
    """~4 characters per token for English legal text."""
    return max(1, len(text) // 4)
```

Chunks exceeding `MAX_INPUT_TOKENS_PER_CHUNK` (350,000) are further split before LLM processing.

---

## 5. Parallel Async Processing with Semaphores

**Location:** `run_preprocess_eu_ai_act.py:192-408, 506-517`

Multiple chunks are processed concurrently using Python's `asyncio`:

```python
MAX_CONCURRENT_CHUNKS = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)

async def process_single_chunk(chunk, idx, total, deps, semaphore, ...):
    async with semaphore:  # Limit concurrent API calls
        result = await preprocess_legal_chunk_agent.run(prompt, deps=deps, ...)
```

The semaphore prevents overwhelming the API while maximizing throughput.

---

## 6. Deterministic Article Count Validation

**Location:** `run_preprocess_eu_ai_act.py:86-104, 305-332`

Before calling the LLM, the expected article count is computed deterministically from the source text:

```python
def count_articles_in_text(text: str) -> int:
    article_pattern = re.compile(r'^Article\s+(\d+)', re.MULTILINE)
    matches = article_pattern.findall(text)
    return len(matches)
```

After extraction, the count is validated:

```python
if extracted_count != expected_article_count:
    # Log mismatch and retry with enhanced prompt
```

---

## 7. Section Constraint Extraction

**Location:** `eu_ai_act_splitter.py:27-49`, `run_preprocess_eu_ai_act.py:260-272`

Section numbers are extracted deterministically from the source text to constrain LLM output:

```python
def extract_section_numbers(text: str) -> List[str]:
    section_pattern = re.compile(r'^SECTION (\d+)', re.MULTILINE)
    return section_pattern.findall(text)
```

The LLM prompt includes these constraints:

```
ALLOWED SECTIONS: ['1', '2', '3']
You may ONLY create Section objects with numbers from this list.
```

This prevents the LLM from misinterpreting high article numbers (41, 65) as section numbers.

---

## 8. Post-Processing Section Filtering

**Location:** `run_preprocess_eu_ai_act.py:334-356`

Even with constraints, the LLM might create invalid sections. Post-processing enforces compliance:

```python
if not allowed_sections:
    # No sections allowed - force empty
    chunk_result.chapter.sections = []
else:
    # Filter to only allowed sections
    chunk_result.chapter.sections = [
        sec for sec in chunk_result.chapter.sections
        if sec.number in allowed_sections
    ]
```

---

## 9. Retry Logic with Exponential Backoff

**Location:** `run_preprocess_eu_ai_act.py:282-407`

Transient errors (timeouts, API errors) are handled with exponential backoff:

```python
max_retries = 2
for attempt in range(max_retries):
    try:
        result = await preprocess_legal_chunk_agent.run(...)
    except Exception as e:
        wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s...
        await asyncio.sleep(wait_time)
```

The prompt is NOT appended on retries (to avoid prompt growth), but a short retry note is added.

---

## 10. Self-Healing Pipeline

**Location:** `run_preprocess_eu_ai_act.py:840-915`

After initial extraction, the pipeline automatically detects and re-processes failed chunks:

```python
async def preprocess_with_self_healing(max_retries: int = 10):
    # Initial full preprocessing
    preprocessed = await preprocess_eu_ai_act_by_chunks()

    # Self-healing loop
    for attempt in range(max_retries):
        chunks_to_reprocess = get_chunks_to_reprocess()
        if not chunks_to_reprocess:
            break
        await preprocess_specific_chunks(chunks_to_reprocess)
```

---

## 11. Missing Article Detection via Gap Analysis

**Location:** `detect_missing_chunks.py:12-49`

Missing articles are detected by analyzing gaps in the article number sequence:

```python
def get_missing_article_numbers() -> Set[int]:
    # Query Neo4j for all article numbers
    # Check for gaps in the sequence
    expected_range = set(range(min(nums), max(nums) + 1))
    actual = set(nums)
    gaps = expected_range - actual
```

---

## 12. Article-to-Chunk Mapping

**Location:** `detect_missing_chunks.py:52-122`

Missing articles are mapped back to their source chunks using a static mapping:

```python
article_to_chunk_map = {
    (1, 4): "CHAPTER I - General provisions",
    (5, 5): "CHAPTER II - Prohibited AI practices",
    (6, 7): "CHAPTER III - SECTION 1",
    # ...
}
```

This enables targeted re-processing of only the failed chunks.

---

## 13. Recovery Pass with Explicit Hints

**Location:** `run_preprocess_eu_ai_act.py:249-257`

When re-processing, the prompt includes explicit hints about missing articles:

```python
if missing_article_hints:
    prompt += (
        f"MISSING ARTICLE RECOVERY:\n"
        f"The following articles were MISSING: {missing_article_hints}\n"
        f"You MUST include these specific articles in your output!\n"
    )
```

---

## 14. Overlapping Window Coverage Check

**Location:** `validate_structure.py:334-531`

An optional post-processing validation uses overlapping windows to detect missed articles:

```python
COVERAGE_WINDOW_SIZE = 10  # Articles per window
COVERAGE_STRIDE = 7        # Overlap = window - stride = 3

def generate_overlapping_windows(articles, window_size=10, stride=7):
    """Each article is covered by multiple windows for redundancy."""
```

This sliding window approach ensures no articles slip through the cracks.

---

## 15. Pydantic Schema Validation

**Location:** `agent_preprocess_eu_ai_act.py`, `models/legal_chunks.py`

The LLM output is validated against strict Pydantic schemas:

```python
preprocess_legal_chunk_agent = Agent[LegalPreprocessDeps, ChunkResult](
    model,
    deps_type=LegalPreprocessDeps,
    output_type=ChunkResult,  # Pydantic model with type constraints
    retries=3,
)
```

Type rules are enforced:
- `Article.number` = integer (1, 2, 3)
- `Chapter.number` = string ("I", "II", "III")

---

## 16. Separation of LLM and Deterministic Phases

**Location:** Architecture-wide pattern

The pipeline cleanly separates:
- **LLM Phase:** `agent_preprocess_eu_ai_act.py` - Structure extraction (non-deterministic)
- **Deterministic Phase:** `ingest_preprocessed_legal.py` - Neo4j ingestion (deterministic, uses MERGE)

This ensures:
- Reproducible database writes
- No hallucinated data in the graph
- Clear audit trail

---

## 17. Chunk-Specific Prompt Engineering

**Location:** `run_preprocess_eu_ai_act.py:232-278`

Each chunk receives a tailored prompt with:
- Chunk kind and label
- Expected article count
- Allowed section constraints
- Missing article hints (if recovery pass)

```python
prompt = (
    f"You are parsing a {chunk.kind} chunk of the EU AI Act.\n"
    f"Chunk label: {chunk.label}\n\n"
    f"EXPECTED ARTICLE COUNT: {expected_article_count}\n"
    f"ALLOWED SECTIONS: {allowed_sections}\n"
)
```

---

## 18. Background Progress Timer

**Location:** `run_preprocess_eu_ai_act.py:918-933`

For long-running operations, a background task logs elapsed time:

```python
async def print_progress_timer(start_time: float):
    interval_minutes = 5
    while True:
        await asyncio.sleep(interval_minutes * 60)
        elapsed = time.time() - start_time
        print(f"⏱️  {minutes}m {seconds:.0f}s have passed...")
```

---

## 19. Debug Mode with Chunk Filtering

**Location:** `run_preprocess_eu_ai_act.py:143-152, 477-489`

A debug mode allows re-processing a single chunk for investigation:

```python
CHUNK_LABEL_FILTER = "CHAPTER III - SECTION 5"  # Debug mode
# or
CHUNK_LABEL_FILTER = None  # Normal mode
```

Results are saved to JSON for inspection rather than ingesting to Neo4j.

---

## 20. Idempotent Neo4j Ingestion

**Location:** `ingest_preprocessed_legal.py`

Neo4j ingestion uses MERGE to ensure idempotency:
- Re-running the pipeline won't create duplicates
- Existing nodes/relationships are updated rather than duplicated

---

## Summary Table

| Technique | Purpose | Location |
|-----------|---------|----------|
| Semantic Chunking | Split by logical units (chapters, annexes) | `eu_ai_act_splitter.py` |
| Recital Batching | Handle 180+ recitals | `eu_ai_act_splitter.py:52` |
| Section-Level Splitting | Handle large chapters | `eu_ai_act_splitter.py:111` |
| Token Estimation | Detect oversized chunks | `run_preprocess_eu_ai_act.py:67` |
| Parallel Async + Semaphores | Concurrent processing | `run_preprocess_eu_ai_act.py:506` |
| Article Count Validation | Verify completeness | `run_preprocess_eu_ai_act.py:86` |
| Section Constraints | Prevent hallucinated sections | `eu_ai_act_splitter.py:27` |
| Post-Processing Filtering | Enforce constraints | `run_preprocess_eu_ai_act.py:334` |
| Exponential Backoff | Handle transient errors | `run_preprocess_eu_ai_act.py:282` |
| Self-Healing Pipeline | Automatic retry loop | `run_preprocess_eu_ai_act.py:840` |
| Gap Analysis | Detect missing articles | `detect_missing_chunks.py:12` |
| Article-to-Chunk Mapping | Target re-processing | `detect_missing_chunks.py:52` |
| Recovery Hints | Guide re-extraction | `run_preprocess_eu_ai_act.py:249` |
| Overlapping Windows | Validate coverage | `validate_structure.py:334` |
| Pydantic Validation | Enforce output schema | `agent_preprocess_eu_ai_act.py` |
| LLM/Deterministic Split | Reproducible ingestion | Architecture pattern |
| Prompt Engineering | Chunk-specific prompts | `run_preprocess_eu_ai_act.py:232` |
| Progress Timer | Long-running feedback | `run_preprocess_eu_ai_act.py:918` |
| Debug Mode | Single-chunk testing | `run_preprocess_eu_ai_act.py:143` |
| Idempotent MERGE | Safe re-runs | `ingest_preprocessed_legal.py` |

---

## Key Design Principles

1. **Trustworthiness:** Clear separation between LLM inference and deterministic operations
2. **Resilience:** Multiple layers of validation, retry, and self-healing
3. **Efficiency:** Parallel processing with controlled concurrency
4. **Debuggability:** Progress logging, debug mode, detailed error reporting
5. **Idempotency:** Safe to re-run without creating duplicates

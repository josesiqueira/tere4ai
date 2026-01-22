# EU AI Act Preprocessing Optimization Plan

## Executive Summary

**Current State**: 105+ minutes, ~82% coverage, frequent extraction failures (Chapter IX: 4/24 articles)

**Target State**: <15 minutes, 100% coverage, zero extraction failures

**Root Cause**: Over-engineered prompts, wrong chunking strategy, and recovery mechanisms that compound failures instead of fixing them.

---

## Part 1: Diagnosis - Why Current Approach Fails

### 1.1 The Real Problem with Chapter IX

Chapter IX contains **24 articles** (Articles 72-94). Current extraction consistently returns **1-6 articles**.

**Why?** The 443-line instruction prompt (~8,500 tokens) overwhelms the model's attention. When combined with the actual text (~12k tokens), the model:
- Loses focus on the extraction task
- Stops early (extracts first few articles, then returns)
- Gets confused by redundant instructions (same warning repeated 4+ times)

**Evidence**: Smaller chapters (I, II, IV) extract perfectly. The issue correlates with prompt complexity, not text size.

### 1.2 Cascading Retry Failure

The retry mechanism **makes things worse**:
```
Attempt 1: Prompt = 8.5k + 12k = 20.5k tokens → Extracts 6 articles
Attempt 2: Prompt = 20.5k + retry message → Extracts 4 articles
Attempt 3: Prompt = 21k + retry message → Extracts 1 article
...
```

Each retry appends text, growing the prompt and **reducing** extraction quality.

### 1.3 Recovery Layers That Don't Recover

| Layer | Purpose | Actual Effect |
|-------|---------|---------------|
| Article count validation | Detect missing articles | Triggers retries that fail |
| Enhanced prompt retry | Fix extraction | Makes prompt longer, extraction worse |
| Coverage check | Find missing articles | Correctly identifies 21 missing, then re-extraction fails |
| Self-healing loop | Re-process failed chunks | Same chunk fails again |

**Conclusion**: All recovery mechanisms retry the **same failing approach**. None fix the root cause.

---

## Part 2: What To Remove (Immediate Simplification)

### 2.1 Remove: Dynamic Prompt Mutation
**File**: `run_preprocess_eu_ai_act.py`, lines 320-326

**Current**:
```python
prompt += f"\n⚠️ RETRY ATTEMPT {attempt + 2}..."  # Grows with each retry
```

**Replace with**: Fixed retry prompt (no growth)

**Impact**: Prevents prompt from growing 50k+ tokens over retries

### 2.2 Remove: Redundant Instruction Sections
**File**: `agent_preprocess_eu_ai_act.py`

| Section | Lines | Tokens | Action |
|---------|-------|--------|--------|
| Paragraph/Article confusion warning #1 | 227-241 | 500 | KEEP (once) |
| Paragraph/Article confusion warning #2 | 329-337 | 400 | REMOVE |
| Paragraph/Article confusion warning #3 | 441-502 | 800 | REMOVE |
| 7 complete JSON examples | 340-502 | 3200 | REDUCE to 2 |
| Full document agent (unused) | 60-137 | N/A | REMOVE |

**Expected reduction**: 8,500 → 3,000 tokens (65% reduction)

### 2.3 Remove: Coverage Check (Temporarily)
**File**: `run_preprocess_eu_ai_act.py`

**Why**: Coverage check is redundant if extraction works correctly. It adds 5+ LLM calls per chapter for validation that should happen via deterministic regex.

**Set**: `ENABLE_COVERAGE_CHECK = False`

**Restore when**: Primary extraction achieves 100% consistently

### 2.4 Remove: Multi-Phase Self-Healing
**File**: `run_preprocess_eu_ai_act.py`, lines 883-907

**Current**: 10 phases of retry with Neo4j queries
**Replace**: Single verification pass, then targeted re-extraction

---

## Part 3: New Architecture (Clean Redesign)

### 3.1 Core Principle: Trust Regex, Simplify LLM

**Key Insight**: The EU AI Act has **perfect structure**. Every article starts with "Article N" on its own line. This is deterministic.

**New approach**:
1. **Regex extracts article boundaries** (100% reliable)
2. **LLM only extracts content** within each article (simpler task)
3. **Validation is deterministic** (regex count = extraction count)

### 3.2 New Chunking Strategy: Article-Level Granularity

**Current**: Chapter-level chunks (Chapter IX = 24 articles in one prompt)
**New**: Article-level chunks (each article = one prompt)

```
CURRENT:                          NEW:
┌─────────────────────┐          ┌─────────────────────┐
│ CHAPTER IX          │          │ Article 72          │ → 1 LLM call
│ (24 articles)       │ → 1 call │ Article 73          │ → 1 LLM call
│                     │          │ ...                 │
│ Often fails         │          │ Article 94          │ → 1 LLM call
└─────────────────────┘          └─────────────────────┘
                                  = 24 parallel calls (faster, reliable)
```

**Benefits**:
- Each call is simple (~500-2000 tokens input)
- Parallel processing (all 24 articles simultaneously)
- If one fails, only re-run that one article
- No complex recovery needed

### 3.3 New Prompt Strategy: Minimal Instructions

**Current prompt**: 443 lines, 8,500 tokens of instructions

**New prompt** (target: 50 lines, 800 tokens):

```python
ARTICLE_EXTRACTION_PROMPT = """Extract the structure from this EU AI Act article.

Input: Article text with numbered paragraphs (1., 2., 3.) and lettered points (a), (b), (c).

Output: JSON matching this schema:
{
  "number": <int>,
  "title": "<string>",
  "paragraphs": [
    {
      "index": <int>,
      "text": "<string>",
      "points": [{"marker": "<letter>", "text": "<string>"}]
    }
  ]
}

Rules:
- Extract ALL paragraphs numbered 1., 2., 3., etc.
- Extract ALL points lettered (a), (b), (c), etc.
- Preserve exact text, no summarization.

Article text:
{article_text}
"""
```

**Why this works**:
- Single clear task (one article → one JSON)
- Schema shown once (not 7 times)
- No confusing warnings about Sections/Chapters (we're only extracting articles)

### 3.4 New Parallel Strategy: Batch API or High Concurrency

**Option A: OpenAI Batch API** (50% cost savings)
- Submit all 113 articles as one batch
- 24-hour turnaround (acceptable for preprocessing)
- No rate limiting concerns

**Option B: High Concurrency Async** (faster)
- Increase `MAX_CONCURRENT_CHUNKS` from 3 to 10-15
- Each article is small (~1k tokens), low risk of timeout
- Estimated time: 113 articles / 10 concurrent × 5 sec = ~1 minute for articles

### 3.5 New Validation: Deterministic Only

**Remove**: LLM-based coverage check
**Keep**: Regex-based validation

```python
def validate_extraction(source_text: str, extracted: dict) -> bool:
    # Count articles in source (regex)
    expected = len(re.findall(r'^Article\s+\d+', source_text, re.MULTILINE))

    # Count articles in extraction
    actual = len(extracted['articles'])

    return expected == actual  # 100% deterministic
```

---

## Part 4: Implementation Phases

### Phase 1: Quick Wins (30 minutes implementation, saves 50% time)

1. **Reduce instruction prompt to 3,000 tokens**
   - Remove duplicate warnings
   - Keep 2 examples instead of 7
   - Delete unused full-document agent

2. **Fix retry mechanism**
   - Don't append to prompt
   - Use fixed retry prompt
   - Max 2 retries instead of 5

3. **Disable coverage check**
   - Set `ENABLE_COVERAGE_CHECK = False`
   - Remove 5+ unnecessary LLM calls

4. **Increase concurrency**
   - Change `MAX_CONCURRENT_CHUNKS = 5` (from 3)

**Expected result**: 100+ minutes → 40-50 minutes

### Phase 2: Article-Level Chunking (2-3 hours implementation)

1. **New splitter function**: `split_chapter_into_articles()`
   ```python
   def split_chapter_into_articles(chapter_text: str) -> List[ArticleChunk]:
       # Regex to find "Article N" boundaries
       pattern = r'^(Article\s+(\d+).*?)(?=^Article\s+\d+|\Z)'
       matches = re.findall(pattern, chapter_text, re.MULTILINE | re.DOTALL)
       return [ArticleChunk(number=int(m[1]), text=m[0]) for m in matches]
   ```

2. **New minimal prompt**: 800 tokens (shown above)

3. **New parallel processor**:
   ```python
   async def extract_all_articles(articles: List[ArticleChunk]) -> List[Article]:
       semaphore = asyncio.Semaphore(15)  # High concurrency
       tasks = [extract_single_article(a, semaphore) for a in articles]
       return await asyncio.gather(*tasks)
   ```

4. **Simple assembly**: Combine articles back into chapters

**Expected result**: 40-50 minutes → 5-10 minutes

### Phase 3: Advanced Optimization (Optional, 1 day)

1. **OpenAI Batch API integration**
   - 50% cost reduction
   - Perfect for overnight processing

2. **Prompt compression** (using LLMLingua)
   - Further reduce token usage
   - 70-80% compression on instructions

3. **Caching layer**
   - Cache successful extractions
   - Re-run only failed articles

4. **Model routing**
   - Use smaller model for simple articles
   - Use larger model for complex articles (many paragraphs/points)

**Expected result**: 5-10 minutes → 2-3 minutes + 50% cost reduction

---

## Part 5: Risk Mitigation

### Risk: Article-level splitting misses content between articles

**Mitigation**:
- Chapter title/intro captured separately
- Section headers captured via regex before article splitting
- Final assembly preserves structure

### Risk: High concurrency hits rate limits

**Mitigation**:
- Start with 5 concurrent, increase gradually
- Implement exponential backoff
- Monitor token/minute usage

### Risk: Some articles have unusual structure

**Mitigation**:
- Validation catches extraction errors immediately
- Failed articles retry individually (not whole chapter)
- Manual review queue for persistent failures

---

## Part 6: Success Metrics

| Metric | Current | Phase 1 | Phase 2 | Phase 3 |
|--------|---------|---------|---------|---------|
| Total time | 105+ min | 40-50 min | 5-10 min | 2-3 min |
| Coverage | 82% | 95%+ | 100% | 100% |
| Chapter IX extraction | 4/24 | 20/24 | 24/24 | 24/24 |
| Token usage | ~2M | ~1.5M | ~500k | ~200k |
| LLM calls | ~100+ | ~50 | ~150 (small) | ~150 (batched) |
| Retries needed | Many | Few | Rare | Zero |

---

## Part 7: Recommended Action

**Start with Phase 1** (30 minutes effort):
1. Simplify the instruction prompt
2. Fix retry mechanism
3. Disable coverage check
4. Run again - should achieve ~95% in ~45 minutes

**If Phase 1 achieves 95%+**, proceed to Phase 2 for the full solution.

**If Phase 1 still fails on Chapter IX**, skip directly to Phase 2 (article-level chunking is the real fix).

---

## Summary

The current architecture is fundamentally sound in its separation of concerns (chunking → extraction → ingestion), but suffers from:

1. **Over-engineered prompts** (8,500 tokens of instructions)
2. **Wrong granularity** (chapter-level instead of article-level)
3. **Counter-productive recovery** (retries make things worse)

The solution is **simplification**:
- Shorter prompts (800 tokens)
- Finer chunks (per-article)
- Deterministic validation (regex-based)
- Higher parallelism (10-15 concurrent)

**Expected outcome**: 100% coverage in <15 minutes.

---

## References

- [Best Chunking Strategies for RAG in 2025](https://www.firecrawl.dev/blog/best-chunking-strategies-rag-2025)
- [OpenAI Batch API](https://platform.openai.com/docs/guides/batch)
- [Token Compression: Slash LLM Costs by 80%](https://medium.com/@yashpaddalwar/token-compression-how-to-slash-your-llm-costs-by-80-without-sacrificing-quality-bfd79daf7c7c)
- [Prompt Compression for LLM Optimization](https://machinelearningmastery.com/prompt-compression-for-llm-generation-optimization-and-cost-reduction/)
- [Reduce LLM Costs: Token Optimization Strategies](https://www.glukhov.org/post/2025/11/cost-effective-llm-applications/)
- [How AI Enhances Legal Document Review (ABA 2025)](https://www.americanbar.org/groups/law_practice/resources/law-technology-today/2025/how-ai-enhances-legal-document-review/)

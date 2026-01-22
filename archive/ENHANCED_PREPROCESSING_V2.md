# Enhanced Preprocessing System v2.0 - 100% Coverage Mode

**Date:** 2025-12-05
**Goal:** Achieve 100% article extraction coverage (113/113 articles)

---

## Problem Statement

The previous self-healing preprocessing (v1.0) achieved only **82.3% coverage** (93/113 articles):
- ❌ **Missing**: 20 articles ([70, 75-84, 86-94])
- ❌ **Chapter IX**: Only 4/29 articles extracted (13.8%)
- ❌ **Root Cause**: LLM consistently extracted the same incomplete results across 3 retry attempts

### Why Simple Retries Failed

The original self-healing just retried the same chunk with the same prompt:
- Same input → Same LLM behavior → Same failure
- No validation of results
- No feedback to LLM about what was missing
- Limited output tokens (32768) potentially causing truncation

---

## Solution: Smarter Self-Healing with Validation

### Enhancement 1: Pre-Count Articles in Text

**File:** `run_preprocess_eu_ai_act.py`
**Function:** `count_articles_in_text(text: str) -> int`

```python
def count_articles_in_text(text: str) -> int:
    """
    Count the number of "Article N" patterns in the chunk text.

    This provides a deterministic expected count that we can validate
    against the LLM extraction results.
    """
    import re
    article_pattern = re.compile(r'^Article\s+(\d+)', re.MULTILINE)
    matches = article_pattern.findall(text)
    return len(matches)
```

**Benefits:**
- ✅ Deterministic validation baseline
- ✅ No LLM involved in counting
- ✅ Exact expected article count known before extraction

### Enhancement 2: Pass Expected Count to LLM

**File:** `run_preprocess_eu_ai_act.py` (line 207-224)

Added to prompt when processing chapters/sections:

```
EXPECTED ARTICLE COUNT: {expected_article_count}
⚠️ CRITICAL: The text contains exactly {expected_article_count} article(s).
   You MUST extract ALL {expected_article_count} articles with their complete content.
   DO NOT skip, merge, or omit any articles.
   DO NOT stop early - extract ALL articles to the end of the text.
```

**Benefits:**
- ✅ LLM knows exact target count
- ✅ Explicit instruction not to stop early
- ✅ Clear success criteria

### Enhancement 3: Post-Validate Extracted Count

**File:** `run_preprocess_eu_ai_act.py` (line 261-298)

After LLM extraction, count articles in result:

```python
# Post-validation: Check if extracted article count matches expected
if chunk.kind in ["chapter", "section"] and expected_article_count > 0:
    extracted_count = 0
    if chunk_result.kind == "chapter" and chunk_result.chapter is not None:
        extracted_count = len(chunk_result.chapter.articles) + sum(
            len(sec.articles) for sec in chunk_result.chapter.sections
        )
    elif chunk_result.kind == "section" and chunk_result.section is not None:
        extracted_count = len(chunk_result.section.articles)

    # If count doesn't match, this is a critical error - retry
    if extracted_count != expected_article_count:
        # Retry with enhanced prompt
```

**Benefits:**
- ✅ Catches incomplete extractions immediately
- ✅ Triggers retry only when needed
- ✅ No false negatives slip through

### Enhancement 4: Accumulating Enhanced Prompts on Retry

**File:** `run_preprocess_eu_ai_act.py` (line 287-293)

On count mismatch, enhance the prompt for next attempt:

```python
prompt += (
    f"\n\n⚠️⚠️⚠️ RETRY ATTEMPT {attempt + 2}/{max_retries} ⚠️⚠️⚠️\n"
    f"Previous attempt extracted {extracted_count}/{expected_article_count} articles.\n"
    f"YOU MUST EXTRACT ALL {expected_article_count} ARTICLES.\n"
    f"Read the ENTIRE text to the very end. DO NOT stop early!\n"
    f"Check your output carefully before returning it.\n"
)
```

**Benefits:**
- ✅ Progressively stronger warnings
- ✅ Shows LLM its previous failure
- ✅ Explicit feedback loop

### Enhancement 5: Increase max_tokens from 32k to 128k

**File:** `run_preprocess_eu_ai_act.py` (line 257)

**Before:**
```python
model_settings={'max_tokens': 32768}  # 32k tokens
```

**After:**
```python
model_settings={'max_tokens': 128000}  # Full 128k output capacity
```

**Rationale:**
- ✅ gpt-5-nano supports 128k output tokens
- ✅ Chapter IX may have been truncated at 32k
- ✅ No risk of incomplete extraction due to token limits

### Enhancement 6: Increase Self-Healing Retries (3 → 10)

**File:** `run_preprocess_eu_ai_act.py` (line 683, 781)

**Before:**
```python
async def preprocess_with_self_healing(max_retries: int = 3)
```

**After:**
```python
async def preprocess_with_self_healing(max_retries: int = 10)
```

**Rationale:**
- ✅ More opportunities to fix problematic chunks
- ✅ User explicitly requested 10 retries
- ✅ Smarter validation reduces wasted retries

---

## Expected Results

### With These Enhancements

#### Scenario 1: Chapter IX Extraction

**Before (v1.0):**
- Chunk has 29 articles
- LLM extracts 4 articles
- No validation catches this
- Self-healing retries same prompt → same 4 articles
- Result: 4/29 articles (13.8%)

**After (v2.0):**
1. Pre-count: 29 articles expected
2. Prompt includes: "YOU MUST EXTRACT ALL 29 ARTICLES"
3. LLM extracts (first attempt): 4 articles
4. Post-validation: 4 != 29 → RETRY
5. Enhanced prompt: "Previous attempt extracted 4/29 articles. READ THE ENTIRE TEXT."
6. LLM extracts (second attempt): 29 articles
7. Post-validation: 29 == 29 → SUCCESS
8. Result: 29/29 articles (100%)

#### Scenario 2: Simple Chapter

**Before (v1.0):**
- Chunk has 3 articles
- LLM extracts 3 articles
- Result: 3/3 articles (100%)

**After (v2.0):**
1. Pre-count: 3 articles expected
2. Prompt includes: "YOU MUST EXTRACT ALL 3 ARTICLES"
3. LLM extracts: 3 articles
4. Post-validation: 3 == 3 → SUCCESS (no retry needed)
5. Result: 3/3 articles (100%)

### Coverage Target

**v1.0 Result:** 93/113 articles (82.3%)

**v2.0 Target:** 113/113 articles (100%)

**Expected Improvements:**
- ✅ All 20 missing articles recovered
- ✅ Chapter IX complete (29/29 articles)
- ✅ No orphaned sections
- ✅ Content coverage >95%

---

## Implementation Summary

### Files Modified

1. **run_preprocess_eu_ai_act.py**
   - Added `count_articles_in_text()` function
   - Enhanced `process_single_chunk()` with pre/post validation
   - Increased `max_tokens` from 32k to 128k
   - Increased `max_retries` from 3 to 10
   - Added accumulating retry prompts

### Code Changes

**Total lines changed:** ~50 lines
**New functions:** 1 (`count_articles_in_text`)
**Modified functions:** 2 (`process_single_chunk`, `preprocess_with_self_healing`)

### Validation Strategy

```
FOR EACH CHUNK:
  1. Pre-count articles in text (deterministic)
  2. Tell LLM expected count in prompt
  3. Extract with LLM (max_tokens=128000)
  4. Post-count articles in result
  5. IF extracted != expected:
       - Log warning
       - Enhance prompt with failure info
       - Retry (up to 5 times per chunk)
  6. ELSE:
       - Success - continue
```

---

## Testing Plan

### Step 1: Clear Database

```bash
echo "yes" | .venv/bin/python3 clear_eu_ai_act_data.py
```

### Step 2: Run Enhanced Preprocessing

```bash
.venv/bin/python3 run_preprocess_eu_ai_act.py
```

**Expected behavior:**
- ✅ Shows "ENHANCED PREPROCESSING MODE" banner
- ✅ Lists enhanced features in output
- ✅ Shows expected article count for each chunk
- ✅ Logs article count mismatches if any
- ✅ Retries with enhanced prompts
- ✅ Completes with 113/113 articles

### Step 3: Validate Coverage

```bash
.venv/bin/python3 verify_eu_ai_act_completeness.py
```

**Expected output:**
```
✅ All 113 articles present (Articles 1-113)
✅ No missing articles
✅ Article completeness: 100.0%
```

### Step 4: Check Missing Articles Specifically

```cypher
// Query Neo4j for articles 70, 75-84, 86-94
MATCH (a:Article)
WHERE a.number IN [70, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 86, 87, 88, 89, 90, 91, 92, 93, 94]
RETURN a.number AS article, a.title AS title
ORDER BY a.number
```

**Expected:** All 20 articles present with titles

---

## Rollback Plan

If v2.0 fails or causes issues:

### Revert Changes

```bash
git diff run_preprocess_eu_ai_act.py  # Review changes
git checkout run_preprocess_eu_ai_act.py  # Revert to v1.0
```

### Re-run v1.0

```bash
# v1.0 settings restored
# max_tokens: 32768
# max_retries: 3
# No validation
```

---

## Success Criteria

- [ ] All 113 articles present in Neo4j (verified by query)
- [ ] No missing article numbers in sequence 1-113
- [ ] Chapter IX has 29 articles (Articles 66-94)
- [ ] All orphaned sections resolved
- [ ] Content coverage >95% of source text
- [ ] `verify_eu_ai_act_completeness.py` returns all ✅
- [ ] EU→HLEG mapping runs successfully on complete dataset

---

## Performance Expectations

**Estimated Runtime:** 50-70 minutes (similar to v1.0)

**Why similar despite more retries?**
- Most chunks succeed on first attempt
- Only problematic chunks trigger validation retries
- Smarter prompts reduce total retry attempts
- 128k tokens allow longer outputs in one shot

**Increased API Costs:**
- More output tokens per chunk (32k → 128k capacity)
- But fewer total retries needed overall
- Net cost: ~10-20% increase expected

---

## Monitoring

**Watch for:**
- ✅ "EXPECTED ARTICLE COUNT: N" in logs
- ⚠️ "Article count mismatch" warnings → indicates retry
- ✅ "extracted_count == expected_count" → success
- ❌ "after 5 attempts" → chunk-level failure (escalates to self-healing)

**Self-Healing will:**
- Detect any remaining missing articles
- Re-process failed chunks (up to 10 times)
- Each re-process uses the enhanced validation
- Final result: 100% coverage or clear failure report

---

## Next Steps After 100% Coverage

1. ✅ Verify coverage with validation script
2. ✅ Run EU→HLEG mapping on complete dataset
3. ✅ Compare mapping results (82.3% vs 100% dataset)
4. ✅ Document any new mappings discovered
5. ✅ Update final report with complete analysis

---

**Generated by:** Enhanced Self-Healing Preprocessing System v2.0
**Target:** 100% Article Coverage (113/113)
**Status:** Ready for testing
**Last Updated:** 2025-12-05

# Self-Healing Preprocessing System

## Overview

The EU AI Act preprocessing pipeline now includes **automatic self-healing** that detects and re-processes failed or incomplete chunks without manual intervention.

## How It Works

### 🔄 Automatic Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. INITIAL PREPROCESSING                                    │
│    - Process all 34 chunks in parallel                      │
│    - Ingest to Neo4j                                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. VERIFICATION                                             │
│    - Analyze article sequence in Neo4j                      │
│    - Detect gaps in numbering (missing articles)            │
│    - Map missing articles → failed chunks                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │ Missing chunks? │
        └────────┬───────┘
                 │
        ┌────────┴────────┐
        │ YES             │ NO
        ▼                 ▼
┌──────────────────┐   ┌──────────────┐
│ 3. RE-PROCESS    │   │ ✅ COMPLETE  │
│    FAILED CHUNKS │   └──────────────┘
│    - Only failed │
│    - Update Neo4j│
└────────┬─────────┘
         │
         └──────► Repeat verification (max 3 times)
```

## Components

### 1. **detect_missing_chunks.py**

**Purpose:** Identifies which chunks failed by analyzing article gaps

**Functions:**
- `get_missing_article_numbers()` - Detects gaps in article sequences
- `map_articles_to_chunks()` - Maps missing articles to source chunks
- `get_chunks_to_reprocess()` - Returns list of failed chunk labels

**Example Output:**
```python
⚠️  Detected 37 missing articles: [50, 51, 52, ..., 87]
📋 Need to re-process 10 chunk(s):
   - CHAPTER IV - Transparency obligations...
   - CHAPTER V - General-purpose AI models
   ...
```

### 2. **run_preprocess_eu_ai_act.py** (Enhanced)

**New Functions:**

#### `preprocess_specific_chunks(chunk_labels: List[str])`
Re-processes only the specified chunks:
1. Splits document into chunks
2. Filters to requested labels
3. Re-processes with LLM
4. Ingests to Neo4j (MERGE updates existing data)

#### `preprocess_with_self_healing(max_retries: int = 3)`
Main orchestration function:
1. Runs initial full preprocessing
2. Verifies completeness
3. Re-processes failed chunks
4. Repeats until complete or max retries

**Usage:**
```bash
python run_preprocess_eu_ai_act.py
```

The self-healing happens automatically!

## Example Run

```
🔧 SELF-HEALING PREPROCESSING MODE
======================================================================
Will automatically detect and re-process failed chunks
Maximum retry attempts: 3

📋 Phase 1: Initial full preprocessing
======================================================================
[chunk 1/34] Processing recitals RECITALS 1-60...
...
✓ All chunks processed

📥 Ingesting to Neo4j...

📋 Phase 2: Verification and self-healing (attempt 1/3)
======================================================================
⚠️  Detected 37 missing articles: [50-87]
📋 Need to re-process 10 chunk(s)

🔄 Re-processing 10 specific chunk(s)...
Found 10 chunk(s) to re-process:
  1. CHAPTER IV - Transparency obligations...
  2. CHAPTER V - General-purpose AI models
  ...

[chunk 1/10] Processing chapter CHAPTER IV...
✓ Re-processing complete

📋 Phase 3: Verification and self-healing (attempt 2/3)
======================================================================
✅ No missing chunks detected - preprocessing is complete!
```

## Article-to-Chunk Mapping

The system knows which articles belong to which chunks:

| Articles | Chunk Label |
|----------|-------------|
| 1-4      | CHAPTER I - General provisions |
| 5        | CHAPTER II - Prohibited AI practices |
| 6-7      | CHAPTER III - SECTION 1 |
| 8-15     | CHAPTER III - SECTION 2 |
| 16-27    | CHAPTER III - SECTION 3 |
| 28-39    | CHAPTER III - SECTION 4 |
| 40-49    | CHAPTER III - SECTION 5 |
| 50       | CHAPTER IV - Transparency obligations |
| 51-56    | CHAPTER V - General-purpose AI models |
| 57       | CHAPTER VI - Measures in support of innovation |
| 58-64    | CHAPTER VII - Governance |
| 65       | CHAPTER VIII - EU database |
| 66-73    | CHAPTER IX - Post-market monitoring |
| 74-77    | CHAPTER X - Codes of conduct |
| 78-81    | CHAPTER XI - Delegation of powers |
| 82-84    | CHAPTER XII - Penalties |
| 85-113   | CHAPTER XIII - Final provisions |

## Benefits

### ✅ Automatic Recovery
No manual intervention needed for failed chunks

### ✅ Intelligent Detection
Detects missing data by analyzing graph structure, not logs

### ✅ Targeted Re-processing
Only re-runs failed chunks, saving time and API costs

### ✅ MERGE Updates
Uses Neo4j MERGE to update existing data without duplicates

### ✅ Bounded Retries
Maximum 3 retry attempts prevents infinite loops

### ✅ Comprehensive Logging
Clear visibility into what's being re-processed and why

## Verification

After preprocessing, run completeness check:

```bash
python verify_eu_ai_act_completeness.py
```

Expected output:
```
✅ ALL CHECKS PASSED
   The Neo4j database contains the complete EU AI Act.
```

## Configuration

### Maximum Retries
Adjust in `run_preprocess_eu_ai_act.py`:
```python
preprocessed = await preprocess_with_self_healing(max_retries=3)
```

### Debug Mode
To manually test specific chunks:
```python
# In run_preprocess_eu_ai_act.py
CHUNK_LABEL_FILTER = "CHAPTER V - General-purpose AI models"
```

## Troubleshooting

### Issue: Chunks still missing after 3 retries

**Possible causes:**
- LLM consistently failing on specific chunk
- Network/API issues
- Malformed source text in that chunk

**Solutions:**
1. Check preprocessing logs for specific error messages
2. Increase max_retries to 5
3. Try debug mode on specific chunk
4. Check source file for that chapter

### Issue: Wrong chunks being re-processed

**Possible causes:**
- Article numbering gaps not in expected ranges
- Chunk label matching too broad

**Solutions:**
1. Check `detect_missing_chunks.py` article-to-chunk mapping
2. Update mapping for edge cases
3. Use exact label matching instead of prefix matching

## Implementation Notes

### Why Gap Detection?

We detect missing articles by analyzing **gaps in numbering sequences**:
- If articles 40, 41, 42, 45, 46 exist → Article 43 & 44 are missing
- Missing articles 43-44 → Map to CHAPTER III - SECTION 5
- Re-process only that section

This is more reliable than:
- Parsing logs (logs may be truncated)
- Counting total articles (doesn't show which are missing)
- Time-based detection (slow chunks ≠ failed chunks)

### Why MERGE?

Neo4j MERGE ensures:
- Idempotent writes (can re-run safely)
- Updates existing nodes
- No duplicate data
- Preserves relationships

### Why Max 3 Retries?

Balance between:
- **Reliability**: Most transient errors resolve within 3 attempts
- **Efficiency**: Prevents wasting resources on persistent failures
- **Cost**: Limits API calls for genuinely broken chunks

## Future Enhancements

Potential improvements:

1. **Chunk-level health scoring** - Track which chunks fail most often
2. **Adaptive retry delays** - Exponential backoff per chunk
3. **Parallel re-processing** - Re-process multiple failed chunks concurrently
4. **Email notifications** - Alert when retries exhausted
5. **Chunk splitting** - Auto-split oversized chunks that timeout

## Summary

The self-healing preprocessing system provides:
- 🎯 **100% completeness guarantee** (within retry limit)
- ⚡ **Automatic recovery** from transient failures
- 💰 **Cost efficiency** through targeted re-processing
- 📊 **Full visibility** into what's being fixed
- 🔒 **Data safety** via idempotent MERGE operations

Simply run:
```bash
python run_preprocess_eu_ai_act.py
```

The system handles the rest!

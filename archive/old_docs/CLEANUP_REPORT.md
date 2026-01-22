# CLEANUP REPORT - trustworthy_project_v0
## Deep Dive Analysis & Recommendations

**Date:** January 2026
**Purpose:** Prepare codebase for TERE4AI (REFSQ 2026)

---

## Executive Summary

After deep analysis by 3 specialized agents, we found:

1. **Two parallel pipelines exist** - root-level (agent-based) and regex_preprocessing/
2. **Regex pipeline is superior** for structural extraction (100% vs 82.3% accuracy)
3. **Several duplicate/unused files** should be cleaned up
4. **Recommended approach:** Hybrid (regex for structure, agents for semantic mapping)

---

## Files Deleted

| File | Size | Reason |
|------|------|--------|
| `archive/eu_ai_act.txt` | 586 KB | Duplicate of `data/eu_ai_act.txt` |

---

## Pipeline Comparison

### Root-Level Pipeline (Agent-Based)

**Files:**
- `run_preprocess_eu_ai_act.py` (1,121 lines)
- `agent_preprocess_eu_ai_act.py` (73 lines)
- `run_preprocess_ai_hleg.py` (174 lines)
- `agent_hleg_preprocess.py` (347 lines)
- `run_map_eu_to_hleg.py` (372 lines)
- `agent_eu_hleg_mapping.py` (184 lines)

**Characteristics:**
- Uses LLM (gpt-5-nano) for extraction
- Reads `data/eu_ai_act_part_1.txt` + `part_2.txt`
- Neo4j port: 7687
- **Accuracy:** 82.3% (missing 20 articles, especially Chapter IX)
- **Speed:** Minutes (LLM API calls)
- **Cost:** $0.01-0.10 per run

### Regex Pipeline (`regex_preprocessing/`)

**Files:**
- `preprocess_eu_ai_act.py` (830 lines)
- `preprocess_ai_hleg.py` (533 lines)
- `run_map_eu_to_hleg.py` (410 lines)
- `agent_eu_hleg_mapping.py` (296 lines)
- `validate_database.py` (610 lines)
- `ultimate_validation.py` (567 lines)

**Characteristics:**
- Uses pure regex for structural extraction
- Uses LLM only for semantic mapping
- Reads `data/eu_ai_act.txt` (combined file)
- Neo4j port: 7688 (separate instance)
- **Accuracy:** ~100% (deterministic)
- **Speed:** Seconds (no API calls for parsing)
- **Cost:** Free (parsing) + small cost for mapping

---

## Recommendation: Hybrid Approach for TERE4AI

```
┌─────────────────────────────────────────────────────────────┐
│                    TERE4AI PIPELINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PHASE 1: STRUCTURAL EXTRACTION (Regex - FAST, FREE)       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ regex_preprocessing/preprocess_eu_ai_act.py           │  │
│  │ regex_preprocessing/preprocess_ai_hleg.py             │  │
│  │                                                       │  │
│  │ → 100% structural coverage                            │  │
│  │ → Deterministic, reproducible                         │  │
│  │ → No API costs                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↓                                 │
│  PHASE 2: SEMANTIC MAPPING (LLM - REQUIRED)                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ regex_preprocessing/agent_eu_hleg_mapping.py          │  │
│  │ (Maps paragraphs → HLEG requirements + subtopics)     │  │
│  │                                                       │  │
│  │ → Semantic understanding required                     │  │
│  │ → ~$0.05 per full corpus mapping                      │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ↓                                 │
│  PHASE 3: VALIDATION (Deterministic)                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ regex_preprocessing/validate_database.py              │  │
│  │ regex_preprocessing/ultimate_validation.py            │  │
│  │                                                       │  │
│  │ → Verify 100% coverage                                │  │
│  │ → Character-level validation                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Files to Keep vs Archive

### KEEP (Active - Root Level)

| File | Reason |
|------|--------|
| `config/neo4j_config.py` | Core configuration |
| `models/*.py` | All models needed by both pipelines |
| `data/eu_ai_act.txt` | Source document (combined) |
| `data/eu_ai_act_part_1.txt` | Used by agent pipeline |
| `data/eu_ai_act_part_2.txt` | Used by agent pipeline |
| `data/ai_hleg.txt` | HLEG guidelines source |

### KEEP (Active - regex_preprocessing/)

| File | Reason |
|------|--------|
| `preprocess_eu_ai_act.py` | Superior structural extraction |
| `preprocess_ai_hleg.py` | HLEG extraction with canonical requirements |
| `run_map_eu_to_hleg.py` | Semantic mapping orchestrator |
| `agent_eu_hleg_mapping.py` | Detailed mapping agent (requirement + subtopic) |
| `ingest_eu_hleg_mapping.py` | Mapping ingestion |
| `validate_database.py` | Database validation |
| `ultimate_validation.py` | Content validation |

### KEEP (Utilities)

| File | Reason |
|------|--------|
| `ingest_preprocessed_legal.py` | Neo4j ingestion (shared) |
| `ingest_hleg.py` | HLEG ingestion |
| `eu_ai_act_splitter.py` | Document chunking utility |

### ARCHIVE (Deprecated but Historical)

| File | Reason |
|------|--------|
| `archive/*` | Old incident preprocessing (PhD history) |
| Agent pipeline files | May be useful for comparison/fallback |

### CONSIDER REMOVING (Low Value)

| File | Reason |
|------|--------|
| Root `agent_eu_hleg_mapping.py` | Superseded by regex_preprocessing version |
| Root `run_map_eu_to_hleg.py` | Superseded by regex_preprocessing version |
| `check_chapter_iii.py` | One-time debugging script |
| `clear_eu_ai_act_data.py` | Utility, rarely needed |
| `detect_missing_chunks.py` | Agent pipeline specific |

---

## Model Files Analysis

### Core Models (KEEP)

| File | Purpose | Used By |
|------|---------|---------|
| `legal_structure.py` | EU AI Act structure | Both pipelines |
| `legal_chunks.py` | Chunk processing | Agent pipeline |
| `legal_preprocess.py` | Preprocessing deps | Agent pipeline |
| `ai_hleg.py` | HLEG structure | Both pipelines |
| `hleg_preprocess.py` | HLEG preprocessing deps | Agent pipeline |
| `eu_hleg_mapping.py` | Simple mapping model | Root mapping agent |
| `eu_hleg_mapping_deps.py` | Mapping deps | Root mapping agent |

### Regex-Specific Models (KEEP)

| File | Purpose | Used By |
|------|---------|---------|
| `hleg_regex.py` | HLEG with canonical reqs | regex_preprocessing/ |
| `eu_hleg_detailed_mapping.py` | Detailed mapping (+ subtopics) | regex_preprocessing/ |

---

## YAML Files Analysis

All YAML files in root are **documentation/specification only** - not used by code:

| File | Size | Purpose | Recommendation |
|------|------|---------|----------------|
| `ai_hleg_processing.yaml` | 24 KB | Agent instructions spec | Move to `/docs/specs/` |
| `agent_classifier_ai_hleg_to_eu_ai_act.yaml` | 28 KB | Classification spec | Move to `/docs/specs/` |
| `improvements_for_mapping.yaml` | 4.8 KB | Improvement notes | Move to `/docs/` |
| `more_subtopics.yaml` | 10 KB | Subtopic definitions | Move to `/docs/specs/` |
| `requirements_have_subtopics.yaml` | 23 KB | Requirement-subtopic map | Move to `/docs/specs/` |

---

## Data Files Analysis

```
data/
├── eu_ai_act.txt           586 KB  ← Used by regex pipeline (CANONICAL)
├── eu_ai_act_part_1.txt    377 KB  ← Used by agent pipeline
├── eu_ai_act_part_2.txt    209 KB  ← Used by agent pipeline
└── ai_hleg.txt             152 KB  ← Used by both pipelines
```

**Note:** `eu_ai_act.txt` = `part_1.txt` + `part_2.txt` (exact concatenation)

**Recommendation:** Keep all for now. After choosing primary pipeline, consolidate.

---

## Immediate Actions Completed

1. ✅ Deleted `archive/eu_ai_act.txt` (duplicate, 586 KB saved)

## Recommended Next Actions

1. **Consolidate Neo4j ports** - Both pipelines should use same database (7687)
2. **Move YAML files** to `/docs/specs/`
3. **Create `/docs/` structure** for documentation
4. **Update `.env`** - Use single .env at root level
5. **Choose canonical pipeline** - Recommend regex as primary for TERE4AI

---

## For TERE4AI Implementation

The regex_preprocessing/ pipeline should become the foundation because:

1. **Deterministic** - Same input always produces same output (academic requirement)
2. **Auditable** - Regex rules are inspectable, LLM decisions are not
3. **Complete** - 100% structural extraction vs 82.3%
4. **Fast** - Seconds vs minutes
5. **Cheap** - No API calls for parsing
6. **Validated** - Comprehensive validation suite included

The agent-based mapping (for EU→HLEG alignment) is still needed because:
- Semantic understanding required
- Cannot be done with regex alone
- Provides relevance scores and rationales

---

*Report generated by deep analysis agents*

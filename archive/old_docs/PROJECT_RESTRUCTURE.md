# TERE4AI Project Restructure Plan

**Date:** January 2026
**Purpose:** Transform trustworthy_project_v0 into clean TERE4AI structure for REFSQ 2026

---

## Current State Summary

### Cleanup Completed

| Action | Status |
|--------|--------|
| Deleted `debug_chunk_result.json` | ✅ |
| Deleted `archive/eu_ai_act.txt` (duplicate) | ✅ |
| Moved debug scripts to `archive/` | ✅ |
| Moved outdated docs to `archive/` | ✅ |
| Moved YAML specs to `docs/specs/` | ✅ |
| Fixed `p.index` → `p.number` bug in mapping | ✅ |
| Ran HLEG preprocessing (7 requirements) | ✅ |
| Started EU→HLEG mapping (147+ mappings created) | ✅ |

### Database State

```
Neo4j (port 7687):
├── EU AI Act Structure
│   ├── 1 Regulation node
│   ├── 13 Chapters
│   ├── 16 Sections
│   ├── 113 Articles
│   ├── 519 Paragraphs
│   ├── 375 Points
│   ├── 180 Recitals
│   └── 13 Annexes
│
├── HLEG Requirements
│   └── 7 HLEGRequirement nodes
│
└── Mappings
    └── 147+ ALIGNS_WITH_HLEG_REQUIREMENT relationships
```

---

## Proposed New Structure

```
tere4ai/
│
├── README.md                           # Project overview
├── pyproject.toml                      # Modern Python packaging
├── requirements.txt                    # Dependencies
├── .env.example                        # Environment template
│
├── ingestion/                          # Data preprocessing & ingestion
│   ├── __init__.py
│   ├── structural/                     # Regex-based extraction (preferred)
│   │   ├── __init__.py
│   │   ├── eu_ai_act_extractor.py      # ← from regex_preprocessing/
│   │   ├── hleg_extractor.py           # ← from regex_preprocessing/
│   │   ├── splitter.py                 # ← eu_ai_act_splitter.py
│   │   └── validator.py                # ← validate_structure.py
│   │
│   ├── semantic/                       # LLM-based mapping
│   │   ├── __init__.py
│   │   ├── mapper.py                   # ← agent_eu_hleg_mapping.py
│   │   └── models.py                   # Mapping output models
│   │
│   ├── db/                             # Neo4j persistence
│   │   ├── __init__.py
│   │   ├── connection.py               # ← config/neo4j_config.py
│   │   ├── legal_ingester.py           # ← ingest_preprocessed_legal.py
│   │   ├── hleg_ingester.py            # ← ingest_hleg.py
│   │   └── mapping_ingester.py         # ← ingest_eu_hleg_mapping.py
│   │
│   └── scripts/                        # Entry points
│       ├── ingest_all.py               # Main orchestrator
│       ├── ingest_eu_ai_act.py         # ← run_preprocess_eu_ai_act.py
│       ├── ingest_hleg.py              # ← run_preprocess_ai_hleg.py
│       └── create_mappings.py          # ← run_map_eu_to_hleg.py
│
├── retrieval/                          # Knowledge graph queries (for MCP)
│   ├── __init__.py
│   ├── legal/
│   │   ├── articles.py                 # Get articles, paragraphs
│   │   ├── chapters.py                 # Get chapters, sections
│   │   └── annexes.py                  # Get annexes (Annex III for high-risk)
│   ├── hleg/
│   │   └── requirements.py             # Get HLEG requirements
│   └── mappings/
│       └── alignments.py               # Get EU↔HLEG mappings
│
├── agents/                             # RE-phase agents
│   ├── __init__.py
│   ├── base.py                         # Base agent with MCP access
│   ├── elicitation/                    # Parse system descriptions
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   └── prompts.py
│   ├── analysis/                       # Risk classification
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   └── prompts.py
│   ├── specification/                  # Generate requirements
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   └── prompts.py
│   ├── validation/                     # Validate completeness
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   └── prompts.py
│   └── orchestrator.py                 # Coordinate pipeline
│
├── mcp_server/                         # MCP server for agent access
│   ├── __init__.py
│   ├── server.py                       # FastMCP server
│   └── tools/
│       ├── prohibited.py               # Article 5 queries
│       ├── high_risk.py                # Annex III queries
│       ├── requirements.py             # Chapter III queries
│       └── hleg.py                     # HLEG queries
│
├── api/                                # FastAPI backend
│   ├── __init__.py
│   ├── main.py
│   └── endpoints/
│       ├── analyze.py                  # POST /analyze
│       └── export.py                   # GET /export/{format}
│
├── frontend/                           # Web UI
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
│
├── shared/                             # Shared models
│   ├── __init__.py
│   └── models/
│       ├── legal.py                    # ← models/legal_structure.py
│       ├── hleg.py                     # ← models/ai_hleg.py
│       ├── requirements.py             # Generated requirement models
│       └── citations.py                # Citation models
│
├── data/                               # Source documents
│   ├── eu_ai_act.txt
│   └── ai_hleg.txt
│
├── docs/                               # Documentation
│   ├── specs/                          # YAML specifications
│   └── architecture.md
│
├── tests/                              # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── archive/                            # Deprecated files
    ├── old_scripts/
    └── old_docs/
```

---

## File Migration Map

### Core Pipeline Files

| Current Location | New Location |
|-----------------|--------------|
| `run_preprocess_eu_ai_act.py` | `ingestion/scripts/ingest_eu_ai_act.py` |
| `run_preprocess_ai_hleg.py` | `ingestion/scripts/ingest_hleg.py` |
| `run_map_eu_to_hleg.py` | `ingestion/scripts/create_mappings.py` |
| `eu_ai_act_splitter.py` | `ingestion/structural/splitter.py` |
| `agent_preprocess_eu_ai_act.py` | `ingestion/structural/extractor.py` |
| `agent_hleg_preprocess.py` | `ingestion/structural/hleg_extractor.py` |
| `agent_eu_hleg_mapping.py` | `ingestion/semantic/mapper.py` |

### Database Files

| Current Location | New Location |
|-----------------|--------------|
| `config/neo4j_config.py` | `ingestion/db/connection.py` |
| `ingest_preprocessed_legal.py` | `ingestion/db/legal_ingester.py` |
| `ingest_hleg.py` | `ingestion/db/hleg_ingester.py` |
| `ingest_eu_hleg_mapping.py` | `ingestion/db/mapping_ingester.py` |

### Model Files

| Current Location | New Location |
|-----------------|--------------|
| `models/legal_structure.py` | `shared/models/legal.py` |
| `models/ai_hleg.py` | `shared/models/hleg.py` |
| `models/eu_hleg_mapping.py` | `shared/models/mappings.py` |
| `models/legal_chunks.py` | `shared/models/chunks.py` |

### Utility Files

| Current Location | New Location |
|-----------------|--------------|
| `validate_structure.py` | `ingestion/structural/validator.py` |
| `verify_eu_ai_act_completeness.py` | `ingestion/structural/completeness.py` |
| `detect_missing_chunks.py` | `ingestion/structural/missing_detector.py` |

### Keep as Documentation

| File | Keep in `docs/` |
|------|-----------------|
| `README.md` | Yes (update) |
| `TERE4AI_MVP_TASKS.md` | Yes |
| `agentic_preprocessing_techniques.md` | Yes |
| `CLEANUP_REPORT.md` | Yes |

---

## Next Steps

1. **Create directory structure** (done in `tere4ai/`)
2. **Copy and rename files** according to migration map
3. **Update imports** in all files
4. **Test ingestion pipeline** end-to-end
5. **Implement retrieval layer** for MCP tools
6. **Build MCP server**
7. **Implement RE-phase agents**
8. **Create API endpoints**
9. **Build frontend**

---

## Commands to Execute Restructure

```bash
# Create structure (already done)
mkdir -p tere4ai/{ingestion/{structural,semantic,db,scripts},retrieval/{legal,hleg,mappings},agents/{elicitation,analysis,specification,validation},mcp_server/tools,api/endpoints,shared/models,tests/{unit,integration,fixtures}}

# Copy core files
cp run_preprocess_eu_ai_act.py tere4ai/ingestion/scripts/ingest_eu_ai_act.py
cp run_preprocess_ai_hleg.py tere4ai/ingestion/scripts/ingest_hleg.py
cp run_map_eu_to_hleg.py tere4ai/ingestion/scripts/create_mappings.py
cp eu_ai_act_splitter.py tere4ai/ingestion/structural/splitter.py
cp agent_preprocess_eu_ai_act.py tere4ai/ingestion/structural/extractor.py
cp agent_hleg_preprocess.py tere4ai/ingestion/structural/hleg_extractor.py
cp agent_eu_hleg_mapping.py tere4ai/ingestion/semantic/mapper.py

# Copy DB files
cp config/neo4j_config.py tere4ai/ingestion/db/connection.py
cp ingest_preprocessed_legal.py tere4ai/ingestion/db/legal_ingester.py
cp ingest_hleg.py tere4ai/ingestion/db/hleg_ingester.py
cp ingest_eu_hleg_mapping.py tere4ai/ingestion/db/mapping_ingester.py

# Copy models
cp models/legal_structure.py tere4ai/shared/models/legal.py
cp models/ai_hleg.py tere4ai/shared/models/hleg.py
cp models/eu_hleg_mapping.py tere4ai/shared/models/mappings.py

# Create __init__.py files
find tere4ai -type d -exec touch {}/__init__.py \;

# Copy data
cp -r data tere4ai/

# Copy docs
cp -r docs tere4ai/
```

---

*This document serves as the migration plan from trustworthy_project_v0 to tere4ai*

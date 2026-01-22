# TERE4AI

**Trustworthy Ethical Requirements Engineering for AI**

A tool for generating AI system requirements grounded in the EU AI Act and HLEG Trustworthy AI Guidelines.

## Overview

TERE4AI helps requirements engineers and developers:

1. **Classify AI systems** by risk level according to EU AI Act categories
2. **Generate requirements** aligned with legal obligations
3. **Ground all outputs** with citations to specific legal articles and HLEG principles

## Architecture

```
User Input (AI System Description)
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│                    RE Phase Agents                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ Elicitation │→ │  Analysis   │→ │  Specification  │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│                                           │              │
│                                           ▼              │
│                                    ┌─────────────┐      │
│                                    │ Validation  │      │
│                                    └─────────────┘      │
└──────────────────────┬───────────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
    ┌───────────────┐    ┌────────────────┐
    │  MCP Server   │    │ Requirements   │
    │  (Legal KG)   │    │    Report      │
    └───────────────┘    └────────────────┘
```

## Knowledge Graph

The system uses Neo4j to store:

- **EU AI Act** (113 articles, 519 paragraphs)
- **HLEG Requirements** (7 principles)
- **Mappings** (590 alignments between EU provisions and HLEG)

## Quick Start

```bash
# Install
pip install -e .

# Configure
cp .env.example .env
# Edit .env with Neo4j credentials and OpenAI API key

# Ingest data
python -m tere4ai.ingestion.scripts.ingest_all

# Run API
uvicorn tere4ai.api.main:app --reload
```

## Risk Classification Flow

```
┌─────────────────────────────────────────────────────────┐
│                User System Description                   │
└───────────────────────────┬─────────────────────────────┘
                            ▼
                    ┌───────────────┐
                    │   Analysis    │
                    │    Agent      │
                    └───────┬───────┘
                            │
            ┌───────────────┼───────────────┐
            │               │               │
            ▼               ▼               ▼
    ┌───────────────┐ ┌───────────┐ ┌───────────┐
    │ Unacceptable  │ │ High-Risk │ │ Limited/  │
    │    (Art 5)    │ │(Annex III)│ │  Minimal  │
    └───────┬───────┘ └─────┬─────┘ └─────┬─────┘
            │               │             │
            ▼               ▼             ▼
        ┌───────┐    ┌──────────┐   ┌──────────┐
        │ STOP  │    │ Full RE  │   │ Reduced  │
        │ with  │    │ Pipeline │   │ Pipeline │
        │ cite  │    └──────────┘   └──────────┘
        └───────┘
```

## Project Structure

```
tere4ai/
├── ingestion/          # Data preprocessing & ingestion
│   ├── structural/     # Regex-based extraction
│   ├── semantic/       # LLM-based mapping
│   ├── db/             # Neo4j persistence
│   └── scripts/        # Entry points
├── retrieval/          # Knowledge graph queries
├── agents/             # RE-phase agents
├── mcp_server/         # MCP server for agents
├── api/                # FastAPI backend
├── shared/             # Shared models
├── data/               # Source documents
└── tests/              # Test suite
```

## License

MIT

## Citation

```bibtex
@inproceedings{tere4ai2026,
  title={TERE4AI: Trustworthy Ethical Requirements Engineering for AI},
  booktitle={REFSQ 2026},
  year={2026}
}
```

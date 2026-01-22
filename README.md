# TERE4AI

**Trustworthy Ethical Requirements Engineering for AI**

A tool that generates legally-grounded requirements for AI systems based on the **EU AI Act** and **AI HLEG Trustworthy AI Guidelines**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What It Does

1. **You describe your AI system** in plain English
2. **TERE4AI classifies the risk level** (Unacceptable, High, Limited, Minimal)
3. **Generates requirements** with legal citations to EU AI Act articles and HLEG principles
4. **You get a traceable requirements report** for compliance

```
┌─────────────────────────────────────────────────────────────────┐
│  "An AI system for hospital emergency triage..."                │
└─────────────────────────────────┬───────────────────────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  RISK CLASSIFICATION: HIGH-RISK (Annex III, Section 5a)         │
│                                                                 │
│  REQ-001: Risk Management System                                │
│  ├─ Article 9(1): "A risk management system shall be..."        │
│  └─ HLEG: Technical Robustness & Safety (0.95)                  │
│                                                                 │
│  REQ-002: Data Governance                                       │
│  ├─ Article 10(1): "High-risk AI systems shall be developed..." │
│  └─ HLEG: Privacy & Data Governance (0.91)                      │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/josesiqueira/tere4ai.git
cd tere4ai

# Configure environment
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY

# Start everything
docker-compose up -d

# Run data ingestion (first time only, takes ~5 minutes)
docker-compose --profile ingestion up

# Open in browser
open http://localhost:8000
```

### Option 2: Manual Setup

```bash
# Clone and setup
git clone https://github.com/josesiqueira/tere4ai.git
cd tere4ai
./scripts/setup.sh

# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY and Neo4j credentials

# Start Neo4j (if not using Docker)
# ... start your Neo4j instance ...

# Run data ingestion (first time only)
python -m ingestion.scripts.ingest_all

# Start the API server
uvicorn api.main:app --reload

# Open in browser
open http://localhost:8000
```

## Requirements

- **Python 3.10+**
- **Neo4j 5.x** (included in Docker setup)
- **OpenAI API key** (for LLM-powered agents)

## Architecture

```
User Input (AI System Description)
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│                    RE Phase Agents                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ Elicitation │→ │  Analysis   │→ │  Specification  │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
│         │               │                   │            │
│         ▼               ▼                   ▼            │
│  Extract system   Classify risk    Generate requirements │
│  characteristics  level            with citations        │
│                                           │              │
│                                           ▼              │
│                                    ┌─────────────┐       │
│                                    │ Validation  │       │
│                                    └─────────────┘       │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  Neo4j          │
                  │  Knowledge Graph│
                  │                 │
                  │  • EU AI Act    │
                  │  • HLEG         │
                  │  • 590 mappings │
                  └─────────────────┘
```

### Risk Classification Outcomes

| Risk Level | Result |
|------------|--------|
| **UNACCEPTABLE** | System prohibited (Article 5). Pipeline stops. No requirements. |
| **HIGH** | Full requirements from Articles 8-27, mapped to HLEG principles |
| **LIMITED** | Transparency requirements only (Article 50) |
| **MINIMAL** | Best practice recommendations, no mandatory requirements |

## Knowledge Graph

The Neo4j database contains:

| Content | Count |
|---------|-------|
| EU AI Act Articles | 113 |
| Paragraphs | 519 |
| Points | 375 |
| Recitals | 180 |
| Annexes | 13 |
| HLEG Principles | 7 |
| HLEG Subtopics | 23 |
| **EU ↔ HLEG Mappings** | **590** |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | Submit AI system description |
| `/api/status/{job_id}` | GET | Check processing progress |
| `/api/report/{job_id}` | GET | Get completed report |
| `/api/export/{job_id}/{format}` | GET | Export as `json` or `markdown` |
| `/api/examples` | GET | Get example system descriptions |

### Example API Usage

```bash
# Submit for analysis
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"description": "An AI system for hospital emergency triage..."}'

# Response: {"job_id": "abc123", "status": "pending"}

# Check status
curl http://localhost:8000/api/status/abc123

# Get report when complete
curl http://localhost:8000/api/report/abc123

# Export as markdown
curl http://localhost:8000/api/export/abc123/markdown -o report.md
```

## Project Structure

```
tere4ai/
├── agents/                 # RE-phase agents (4 agents)
│   ├── elicitation/       # Extract system characteristics
│   ├── analysis/          # Classify risk level
│   ├── specification/     # Generate requirements
│   └── validation/        # Validate completeness
├── api/                   # FastAPI backend
│   └── static/            # Web interface (HTML/CSS/JS)
├── mcp_server/            # MCP server (5 semantic tools)
├── shared/models/         # Pydantic data models
├── ingestion/             # Data preprocessing & ingestion
├── data/                  # Source documents (EU AI Act, HLEG)
├── docs/                  # Documentation
└── tests/                 # Test suite
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | - |
| `NEO4J_URI` | Neo4j connection URI | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | - |
| `TERE4AI_HOST` | API server host | `0.0.0.0` |
| `TERE4AI_PORT` | API server port | `8000` |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .
ruff check .
```

## Deployment

### Render (Recommended)

1. Fork this repository
2. Create a [Neo4j Aura](https://neo4j.com/cloud/aura/) free instance
3. Deploy to [Render](https://render.com):
   - Connect GitHub repo
   - Set environment variables
   - Deploy

### Railway

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Docker (Self-hosted)

```bash
docker-compose up -d
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data Models](docs/DATA_MODELS.md)
- [Agent Design](docs/AGENTS.md)
- [MCP Server API](docs/MCP_SERVER_API.md)
- [Example Outputs](docs/EXAMPLE_OUTPUTS.md)
- [Demo Scenarios](docs/DEMO_SCENARIOS.md)

## License

MIT

## Citation

```bibtex
@inproceedings{tere4ai2026,
  title={TERE4AI: Trustworthy Ethical Requirements Engineering for AI},
  author={Siqueira, Jose},
  booktitle={REFSQ 2026},
  year={2026}
}
```

## Acknowledgments

- EU AI Act (Regulation 2024/1689)
- AI HLEG Ethics Guidelines for Trustworthy AI

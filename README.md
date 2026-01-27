# TERE4AI

**Trustworthy Ethical Requirements Engineering for AI**

A tool that generates legally-grounded software requirements for AI systems based on the **EU AI Act** and **AI HLEG Trustworthy AI Guidelines**.

---

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

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/josesiqueira/tere4ai.git
cd tere4ai

cp .env.example .env
nano .env  # Add your OPENAI_API_KEY

docker-compose up -d

# Run data ingestion (first time only)
docker-compose --profile ingestion up

# Open browser
open http://localhost:8000
```

### Option 2: Manual Setup

```bash
git clone https://github.com/josesiqueira/tere4ai.git
cd tere4ai

python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
nano .env  # Add your OPENAI_API_KEY and Neo4j credentials

# Start Neo4j (if not using Docker)
# Run data ingestion (first time only)
python -m ingestion.scripts.ingest_all

# Start the API server
uvicorn api.main:app --reload

open http://localhost:8000
```

---

## Requirements

- **Python 3.10+**
- **Neo4j 5.x** (included in Docker setup)
- **OpenAI API key**

---

## System Architecture

```
User Input (AI System Description)
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    RE Pipeline Agents                         │
│                                                               │
│  ┌─────────────┐   ┌──────────┐   ┌───────────────┐          │
│  │ Elicitation │ → │ Analysis │ → │ Specification │          │
│  └─────────────┘   └──────────┘   └───────────────┘          │
│         │               │                │                    │
│         ▼               ▼                ▼                    │
│   Extract system   Classify risk   Generate requirements     │
│   characteristics  (4 levels)      with citations            │
│                                          │                    │
│                                          ▼                    │
│                                   ┌────────────┐              │
│                                   │ Validation │              │
│                                   └────────────┘              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │     Neo4j       │
                  │ Knowledge Graph │
                  │                 │
                  │ • EU AI Act     │
                  │ • HLEG          │
                  │ • 590 mappings  │
                  └─────────────────┘
```

### Models Used

| Component | Model | Purpose |
|-----------|-------|---------|
| **RE Pipeline Agents** | `gpt-5.2` | Elicitation, Analysis, Specification, Validation |
| **Ingestion Pipeline** | `gpt-5-nano` | Structural extraction, semantic mapping |

### Risk Classification Outcomes

| Risk Level | Result |
|------------|--------|
| **UNACCEPTABLE** | System prohibited (Article 5). Pipeline stops. |
| **HIGH** | Full requirements from Articles 8-27, mapped to HLEG |
| **LIMITED** | Transparency requirements only (Article 50) |
| **MINIMAL** | Best practice recommendations |

---

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

### The 7 HLEG Principles

1. Human Agency and Oversight
2. Technical Robustness and Safety
3. Privacy and Data Governance
4. Transparency
5. Diversity, Non-discrimination and Fairness
6. Societal and Environmental Well-being
7. Accountability

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | Submit AI system description |
| `/api/status/{job_id}` | GET | Check processing progress |
| `/api/report/{job_id}` | GET | Get completed report |
| `/api/export/{job_id}/{format}` | GET | Export as `json` or `markdown` |
| `/api/examples` | GET | Get example system descriptions |

### Example Usage

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

---

## Project Structure

```
tere4ai/
├── agents/                 # RE Pipeline Agents (gpt-5.2)
│   ├── base.py            # Base agent class + AgentConfig
│   ├── orchestrator.py    # Pipeline coordinator
│   ├── elicitation/       # Phase 1: Extract system characteristics
│   ├── analysis/          # Phase 2: Classify risk level
│   ├── specification/     # Phase 3: Generate requirements
│   └── validation/        # Phase 4: Validate completeness
│
├── api/                   # FastAPI backend
│   ├── main.py           # API endpoints
│   └── static/           # Web UI (HTML/CSS/JS)
│
├── mcp_server/           # MCP Server (5 semantic tools)
│   └── server.py         # Tool implementations
│
├── shared/models/        # Pydantic data models
│   ├── system_description.py
│   ├── risk.py
│   ├── requirements.py
│   ├── citations.py
│   └── report.py
│
├── ingestion/            # Data ingestion pipeline (gpt-5-nano)
│   ├── structural/       # EU AI Act + HLEG extraction
│   ├── semantic/         # EU ↔ HLEG mapping
│   ├── db/              # Neo4j writers (deterministic)
│   └── scripts/         # Ingestion orchestration
│
├── data/                 # Source documents
│   ├── eu_ai_act_part_1.txt
│   ├── eu_ai_act_part_2.txt
│   └── ai_hleg.txt
│
└── docs/                 # Detailed documentation
    ├── ARCHITECTURE.md   # Technical deep dive
    ├── AGENTS.md         # Agent design details
    ├── DATA_MODELS.md    # Pydantic model reference
    └── MCP_SERVER_API.md # Tool interface reference
```

---

## Ingestion Pipeline

The knowledge graph is built through a 3-step ingestion process:

```
[1/3] EU AI Act Structural Extraction
      └─ gpt-5-nano extracts articles, paragraphs, points from raw text
      └─ Neo4j write (deterministic)

[2/3] HLEG Guidelines Extraction
      └─ gpt-5-nano extracts 7 principles + subtopics
      └─ Neo4j write (deterministic)

[3/3] Semantic Mapping
      └─ gpt-5-nano maps each EU paragraph to HLEG principles
      └─ Produces relevance scores (0.0-1.0) + rationales
      └─ Neo4j write (deterministic)
```

**Note:** The semantic mappings were generated by LLM and have not been formally validated by legal or ethics domain experts.

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | - |
| `NEO4J_URI` | Neo4j connection URI | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | - |
| `TERE4AI_MODEL` | Override RE agent model | `gpt-5.2` |
| `TERE4AI_TEMPERATURE` | LLM temperature | `0.1` |

---

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

---

## Deployment

### Docker (Self-hosted)
```bash
docker-compose up -d
```

### Railway
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### Render
1. Fork this repository
2. Create a [Neo4j Aura](https://neo4j.com/cloud/aura/) free instance
3. Deploy to [Render](https://render.com) with environment variables

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture details |
| [AGENTS.md](docs/AGENTS.md) | Agent design and prompts |
| [DATA_MODELS.md](docs/DATA_MODELS.md) | Pydantic model reference |
| [MCP_SERVER_API.md](docs/MCP_SERVER_API.md) | MCP tool specifications |

---

## Limitations

- Semantic mappings (EU ↔ HLEG) generated by LLM, not human-validated
- Processing time: ~5 minutes for high-risk systems
- Requires OpenAI API access

---

## License

MIT

---

## Citation

```bibtex
@inproceedings{tere4ai2026,
  title={TERE4AI: Trustworthy Ethical Requirements Engineering for AI},
  author={Siqueira, Jose},
  booktitle={REFSQ 2026},
  year={2026}
}
```

---

## Acknowledgments

- EU AI Act (Regulation 2024/1689)
- AI HLEG Ethics Guidelines for Trustworthy AI

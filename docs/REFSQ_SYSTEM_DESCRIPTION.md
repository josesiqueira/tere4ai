# TERE4AI: Trustworthy Ethical Requirements Engineering for AI

**System Description for REFSQ 2026**

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Requirements Engineering Pipeline](#requirements-engineering-pipeline)
3. [Knowledge Representation and Legal Grounding](#knowledge-representation-and-legal-grounding)

---

## System Architecture

### 1. Overview and Design Principles

TERE4AI (Trustworthy Ethical Requirements Engineering for AI) is a software system designed to generate legally-grounded software requirements for artificial intelligence systems. The system operationalizes regulatory compliance by automating the extraction of formal requirements from the EU AI Act and the AI High-Level Expert Group (HLEG) Trustworthy AI Guidelines. The architecture follows a layered, agent-based design pattern that separates concerns across user interaction, intelligent processing, data retrieval, and knowledge representation. A fundamental design principle underlying the system architecture is the pursuit of *traceability*: every requirement produced by the system can be directly traced to specific articles, paragraphs, and principles within the source legal documents, enabling comprehensive compliance verification and audit trails.

The system implements a formal Requirements Engineering (RE) methodology through four sequential processing phases, each instantiated as an independent intelligent agent. This agent-oriented approach provides several architectural advantages: modularity, testability, and the ability to incorporate domain-specific logic and reasoning at each RE phase. The design leverages contemporary AI techniques—specifically Large Language Models (LLMs) with structured output validation—to bridge the gap between natural language AI system descriptions and formally-specified regulatory requirements.

### 2. Layered Architecture

TERE4AI employs a four-tier architectural pattern that cleanly separates responsibilities across multiple abstraction levels:

**Tier 1: User Interface Layer**

The presentation tier consists of a web-based interface served via FastAPI's static file hosting, complemented by REST API endpoints. The interface enables users to submit natural language descriptions of their AI systems and provides real-time progress feedback through polling-based status updates. The API implements asynchronous job processing with the following endpoints: `POST /api/analyze` (job submission), `GET /api/status/{job_id}` (progress tracking), `GET /api/report/{job_id}` (result retrieval), and `GET /api/export/{job_id}/{format}` (multi-format export). This tier operates independently of the analysis logic, enabling future replacements with alternative interfaces without architectural changes.

**Tier 2: Agent Pipeline Layer**

The core processing logic is distributed across four specialized agents that implement classical RE phases. The Orchestrator component manages sequential execution of the pipeline, with the following flow: (1) Elicitation Agent extracts structured system characteristics from free-form user input; (2) Analysis Agent classifies the system into one of four risk categories based on the EU AI Act's risk taxonomy; (3) Specification Agent generates formal requirements from applicable legal articles; and (4) Validation Agent verifies completeness and consistency of the generated requirements. Each agent operates asynchronously and produces strongly-typed Pydantic models as outputs, enforcing runtime type safety and enabling comprehensive JSON serialization for storage and export. The Orchestrator implements early-termination logic: if the Analysis Agent determines a system is prohibited (UNACCEPTABLE risk level per Article 5), the pipeline terminates immediately and produces a prohibition notice rather than continuing to Specification and Validation phases.

**Tier 3: MCP Server Layer (Semantic Bridge)**

The Model Context Protocol (MCP) server provides a semantic abstraction layer between the agents and the raw knowledge graph. Rather than agents constructing Neo4j Cypher queries directly, they invoke five high-level semantic tools: (1) `classify_risk_level()` performs regulatory risk classification; (2) `get_applicable_articles()` retrieves the set of articles applicable to a risk category; (3) `get_article_with_citations()` fetches a complete article with embedded HLEG mappings; (4) `get_hleg_coverage()` computes the coverage of HLEG principles across selected articles; and (5) `search_legal_text()` performs semantic search across all legal content. This abstraction provides several benefits: agents remain decoupled from database schema changes, tool implementations are independently testable, and query logic is centralized for consistency and performance optimization.

**Tier 4: Data Layer**

The Neo4j graph database serves as the persistent knowledge base, storing the complete EU AI Act (113 articles with 519 paragraphs), the AI HLEG guidelines (7 core principles with 35+ subtopics), and 590 semantic mappings between EU articles and HLEG requirements. Neo4j was selected for its superior performance on semantic queries and relationship traversals compared to relational or document databases. The knowledge graph schema defines entities (Articles, Paragraphs, Points, Recitals, Annexes, HLEGRequirements, HLEGRequirementSubtopics) and relationships (HAS_PARAGRAPH, HAS_POINT, ALIGNS_WITH_HLEG_REQUIREMENT, HAS_SUBTOPIC), enabling efficient pattern matching queries essential for requirement derivation.

### 3. Technology Stack and Justification

The technology selection reflects a balance between academic rigor, production reliability, and development velocity:

| Component | Technology | Justification |
|-----------|------------|---------------|
| Backend Framework | FastAPI + Uvicorn | Native async support, automatic API documentation, Pydantic integration |
| Agent Framework | Pydantic-AI + OpenAI GPT-4o | Structured output validation, deterministic outputs (temperature 0.1) |
| Knowledge Graph | Neo4j 5.x | Superior query performance for hierarchical legal documents |
| Data Validation | Pydantic 2.0+ | Runtime type checking, field-level validation, JSON serialization |
| MCP Server | FastMCP | Standards-aligned semantic tool interface |

### 4. Data Flow: From User Input to Regulatory Report

The complete end-to-end data flow through TERE4AI follows a structured progression:

1. **Elicitation Phase**: User submits natural language description → ElicitationAgent extracts structured `SystemDescription` (domain, purpose, risk flags, data types, decision types)

2. **Analysis Phase**: `SystemDescription` → AnalysisAgent invokes `classify_risk_level()` → Returns `RiskClassification` (UNACCEPTABLE/HIGH/LIMITED/MINIMAL with legal basis)

3. **Specification Phase**: For non-prohibited systems → SpecificationAgent retrieves applicable articles via MCP → Generates `GeneratedRequirement[]` with citations

4. **Validation Phase**: Requirements → ValidationAgent checks coverage and consistency → Returns `ValidationResult` with metrics

5. **Report Generation**: Orchestrator synthesizes all outputs into final `RequirementsReport`

### 5. Integration Pattern: LLM Reasoning with Knowledge Graph Grounding

TERE4AI implements a hybrid reasoning architecture:

- **LLM Role**: Semantic understanding, regulatory reasoning, requirement synthesis, consistency validation
- **Knowledge Graph Role**: Single source of truth for legal content, precomputed semantic mappings, verifiable citations, coverage metrics
- **Tool-Mediated Integration**: MCP server bridges LLMs and knowledge graph through semantic tools, providing abstraction, centralized queries, and clean separation of concerns

---

## Requirements Engineering Pipeline

### Pipeline Overview and Design Principles

TERE4AI operationalizes the Requirements Engineering process through a sequential four-phase pipeline: (1) Elicitation, (2) Analysis, (3) Specification, and (4) Validation. Each phase is implemented as an independent agent that receives structured input, performs domain-specific reasoning via Large Language Models (LLMs), and produces standardized Pydantic models as output.

All agents inherit from a common `BaseAgent` abstract class that provides shared infrastructure: configuration management via `AgentConfig`, access to Model Context Protocol (MCP) tools through `MCPToolClient`, and execution tracing via `AgentTrace`. The `AgentConfig` specifies LLM parameters (model: GPT-4o, temperature: 0.1 for determinism), retry logic with exponential backoff, and logging configuration.

### Phase 1: Elicitation Agent

The Elicitation Agent extracts structured system characteristics from natural language user input.

**Input**: `ElicitationInput` containing raw natural language description and optional context

**Output**: `SystemDescription` with validated fields:
- `domain` (15 categories: healthcare, education, employment, finance, law_enforcement, etc.)
- `purpose`, `intended_users`, `affected_persons`
- `data_types` (19 categories including biometric, health, financial, behavioral)
- `decision_types` (12 types including access_denial, resource_allocation, ranking)
- `autonomy_level` (full, partial, advisory, assistive)
- `deployment_context` (12 contexts)

**Risk Flags Extracted**:
- `affects_fundamental_rights`, `safety_critical`, `biometric_processing`
- `real_time_biometric`, `law_enforcement_use`, `critical_infrastructure`
- `vulnerable_groups`, `emotion_recognition`, `social_scoring`, `subliminal_techniques`

**Strategy**: Conservative flagging (accepts false positives over false negatives), grounded extraction, completeness, and traceability of ambiguities.

### Phase 2: Analysis Agent

The Analysis Agent determines the risk classification based on EU AI Act criteria.

**Input**: `SystemDescription`

**Output**: `RiskClassification` containing:
- `level` (UNACCEPTABLE, HIGH, LIMITED, MINIMAL)
- `legal_basis` (CitationBundle with primary and supporting citations)
- `annex_iii_category` and `applicable_articles` (for HIGH risk)
- `prohibition_details` (for UNACCEPTABLE)
- `hleg_implications` (list of Citation objects)
- `reasoning` and `confidence`

**Classification Logic** (hierarchical decision tree):
1. Check Article 5 for prohibited practices → UNACCEPTABLE
2. Check Annex III high-risk categories → HIGH (unless Article 6(3) exception applies)
3. Check Article 50 transparency requirements → LIMITED
4. Default → MINIMAL

### Phase 3: Specification Agent

The Specification Agent generates formal requirements anchored to applicable EU AI Act articles.

**Input**: `SpecificationInput` (SystemDescription + RiskClassification)

**Output**: `SpecificationOutput` with list of `GeneratedRequirement` objects

**Operation**:
1. Skip if UNACCEPTABLE (return empty list with prohibition note)
2. Retrieve applicable articles via `get_applicable_articles()`
3. For each article, call `get_article_with_citations()` to fetch complete content
4. Generate 1-3 requirements per article using formal SHALL/SHOULD/MAY language

**GeneratedRequirement Structure**:
- ID, title, statement (formal language)
- Category (risk_management, data_governance, transparency, human_oversight, etc.)
- Priority (critical/high/medium/low)
- EU AI Act citations (article, paragraph, point, quoted text)
- HLEG citations (requirement_id, subtopic_id, relevance_score)
- Verification criteria and method
- Traceability links (derived_from_articles, addresses_hleg_principles)

### Phase 4: Validation Agent

The Validation Agent ensures requirements are complete, consistent, and traceable.

**Input**: `ValidationInput` (requirements, risk classification, applicable articles)

**Output**: `ValidationResult` containing:
- Coverage metrics (article_coverage, hleg_coverage, subtopic_coverage)
- Lists of covered/missing articles and principles
- Conflict detection (contradictions, redundancies, overlaps)
- Citation validity checks
- Summary flags (is_complete, is_consistent, is_valid)

**Validation Checks**:
1. **Article Coverage**: ≥80% of applicable articles addressed
2. **HLEG Coverage**: ≥70% of principles addressed
3. **Consistency**: No contradictions or redundancies
4. **Citation Validity**: All citations properly formed with quoted text

### Pipeline Coordination and Early Termination

The `Orchestrator` manages end-to-end execution with early termination for prohibited systems:

```
User Input → Elicitation → Analysis → [UNACCEPTABLE?]
                                          ↓ Yes: Return prohibition notice
                                          ↓ No: Continue
                           → Specification → Validation → Final Report
```

---

## Knowledge Representation and Legal Grounding

### 1. Knowledge Graph Schema

The TERE4AI knowledge graph organizes EU AI Act and HLEG content into hierarchical node structures:

**EU AI Act Structural Layer**:

| Node Type | Description | Count |
|-----------|-------------|-------|
| Recital | "Whereas" clauses explaining context | 180 |
| Chapter | Top-level organization (I-VI) | 6 |
| Section | Intermediate groupings | 16 |
| Article | Numbered provisions | 113 |
| Paragraph | Subdivisions within articles | 519 |
| Point | Lettered sub-points (a, b, c) | 375 |
| Annex | Technical specifications (I-XIII) | 13 |

**HLEG Ethical Principles Layer**:

| Node Type | Description | Count |
|-----------|-------------|-------|
| HLEGRequirement | Seven canonical principles | 7 |
| HLEGRequirementSubtopic | Thematic facets within principles | 23 |

**The Seven HLEG Principles**:
1. Human Agency and Oversight
2. Technical Robustness and Safety
3. Privacy and Data Governance
4. Transparency
5. Diversity, Non-discrimination and Fairness
6. Societal and Environmental Well-being
7. Accountability

### 2. Semantic Mapping: EU AI Act to HLEG Alignment

The semantic mappings between EU AI Act paragraphs and HLEG principles were generated using a Large Language Model (GPT-4) with structured output validation. This LLM-assisted approach enables rapid, consistent mapping across the full regulatory corpus while maintaining auditability through generated rationales.

**Mapping Process**:

For each of the 519 EU AI Act paragraphs, the LLM was prompted with:
- The target paragraph text
- Structural context (chapter number, section title, article title)
- Neighboring paragraphs (previous/next) for contextual understanding

The model produced zero or more alignment links, each containing:
- **Relevance Score** (0.0-1.0): Quantified strength of semantic alignment
- **Rationale**: Natural language explanation of *why* the paragraph relates to the HLEG principle
- **HLEG Requirement ID**: One of the seven canonical principle identifiers

This approach yielded **590 paragraph-to-principle mappings** across the corpus, stored as `ALIGNS_WITH_HLEG_REQUIREMENT` relationships in Neo4j.

**Example**: Article 9 (Risk Management) mappings:
- Technical Robustness and Safety: 0.95 relevance
  - *Rationale*: "Risk management directly supports technical robustness through systematic identification and mitigation of failures"
- Accountability: 0.82 relevance
- Human Agency and Oversight: 0.78 relevance

**Bidirectional Traceability**:
- Forward: Article → HLEG principles addressed
- Reverse: HLEG principle → Articles that contribute

**Advantages of LLM-Assisted Mapping**:
- Scalable: 519 paragraphs mapped automatically vs. weeks of manual work
- Consistent: Same criteria applied uniformly to all paragraphs
- Auditable: Each mapping includes an explanatory rationale
- Reproducible: Deterministic prompting with low temperature (0.1)

**Limitations**:
- Mappings have not been formally validated by legal or ethics domain experts
- Future work includes human expert review to assess mapping quality

### 3. MCP Server: Semantic Interface

Five high-level semantic tools abstract the knowledge graph:

| Tool | Purpose | Used By |
|------|---------|---------|
| `classify_risk_level()` | Determine regulatory risk classification | Analysis Agent |
| `get_applicable_articles()` | Retrieve articles for risk level | Specification Agent |
| `get_article_with_citations()` | Fetch complete article with HLEG mappings | Specification Agent |
| `get_hleg_coverage()` | Compute HLEG principle coverage | Validation Agent |
| `search_legal_text()` | Keyword search across all content | All Agents |

### 4. Citation Model and Legal Traceability

Every requirement is anchored to **Citations**—traceable references to specific source documents.

**Citation Structure**:
```
Citation {
  source: "EU_AI_ACT" | "AI_HLEG"
  article, paragraph, point (for EU AI Act)
  requirement_id, subtopic_id (for HLEG)
  reference_text: "Article 9(1)"
  quoted_text: "A risk management system shall be established..."
  relevance_score: 0.95 (for HLEG)
}
```

**CitationBundle**: Groups primary citation with supporting citations and rationale.

### 5. Knowledge Graph Construction Pipeline

The workflow separates concerns into distinct processing stages:

1. **Structural Extraction** (deterministic): Regex-based parsing of EU AI Act and HLEG documents into hierarchical components (chapters, sections, articles, paragraphs, points)

2. **Graph Population**: Load extracted structure into Neo4j with proper node types and relationships (HAS_CHAPTER, HAS_ARTICLE, HAS_PARAGRAPH, etc.)

3. **Semantic Mapping** (LLM-assisted): For each paragraph, an LLM agent determines alignments with HLEG principles, producing relevance scores and rationales. Results are stored as `ALIGNS_WITH_HLEG_REQUIREMENT` relationships.

4. **Agent Queries**: At runtime, RE agents query pre-computed mappings via MCP tools, retrieving structured results without additional LLM inference on the legal text itself.

5. **Citation Aggregation**: Agents assemble CitationBundles from graph query results, combining article citations with their pre-computed HLEG alignments.

This approach ensures:
- Deterministic, verifiable structural extraction (no LLM involvement)
- Consistent semantic mappings with auditable rationales
- Separation between mapping generation (offline, one-time) and requirement generation (online, per-request)
- Grounded requirement generation anchored to pre-computed legal relationships

---

## Summary

TERE4AI demonstrates how formal Requirements Engineering methodologies can be effectively automated through contemporary AI techniques while maintaining rigorous traceability to legal sources. The architecture combines:

- **Agent-Based RE Implementation**: Four autonomous agents implementing classical RE phases (Elicitation, Analysis, Specification, Validation)
- **Knowledge-Grounded LLM Reasoning**: Hybrid architecture where LLMs generate requirements anchored to pre-computed knowledge graph relationships
- **LLM-Assisted Semantic Mapping**: 590 EU AI Act to HLEG principle mappings generated via structured LLM prompting with rationales for auditability
- **Full Legal Traceability**: Every requirement traced to specific EU AI Act articles and HLEG principles
- **Transparency and Reproducibility**: Comprehensive execution tracing and structured output models

The system processes natural language AI system descriptions and produces compliance requirements in approximately 4-5 minutes for high-risk systems, generating 50+ requirements with 100% article coverage and 100% HLEG principle coverage.

**Limitations and Future Work**: The semantic mappings between EU AI Act and HLEG principles were generated by an LLM and have not been formally validated by legal or ethics domain experts. Future work includes human expert review to assess and refine mapping quality.

---

*Document generated: January 2026*
*Project: TERE4AI - Trustworthy Ethical Requirements Engineering for AI*
*Target venue: REFSQ 2026*

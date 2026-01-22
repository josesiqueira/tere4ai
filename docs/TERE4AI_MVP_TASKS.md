# TERE4AI - MVP Task List
## Trustworthy Ethical Requirements Engineering for AI

**Target:** REFSQ 2026 (Short Paper)
**Goal:** Interactive tool where users input AI system descriptions and receive ethically-anchored requirements grounded in EU AI Act and AI HLEG

**MVP Scope:** Preliminary results demonstrating working system - database screenshots, interface, example generated requirements with citations.

---

## System Overview

### What TERE4AI Does

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TERE4AI SYSTEM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────────────────────────────────────────┐  │
│  │    USER      │    │              AGENT PIPELINE                       │  │
│  │              │    │         (Formal RE Phases)                        │  │
│  │ "An AI for   │    │                                                   │  │
│  │  hospital    │───►│  ELICITATION ─► ANALYSIS ─► SPECIFICATION ─►     │  │
│  │  triage..."  │    │                     │           │         │       │  │
│  │              │    │                     │           │    VALIDATION   │  │
│  └──────────────┘    │                     ▼           ▼         │       │  │
│                      │              ┌─────────────┐    │         │       │  │
│                      │              │ MCP SERVER  │◄───┴─────────┘       │  │
│                      │              │  (Bridge)   │                      │  │
│                      │              └──────┬──────┘                      │  │
│                      └───────────────────────────────────────────────────┘  │
│                                            │                                │
│                                            ▼                                │
│                                   ┌─────────────────┐                      │
│                                   │     NEO4J       │                      │
│                                   │ Knowledge Graph │                      │
│                                   │                 │                      │
│                                   │ • EU AI Act     │                      │
│                                   │ • AI HLEG       │                      │
│                                   │ • Mappings      │                      │
│                                   └─────────────────┘                      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                              OUTPUT                                         │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ RISK CLASSIFICATION: HIGH-RISK (Annex III, 5(a))                   │    │
│  │                                                                     │    │
│  │ REQUIREMENT REQ-001: Risk Management System                        │    │
│  │ ├─ Article 9(1): "A risk management system shall be..."            │    │
│  │ ├─ Article 9(2)(a): "identification and analysis of..."            │    │
│  │ └─ HLEG: Technical Robustness & Safety (0.95)                      │    │
│  │         └─ Subtopic: Resilience to attack                          │    │
│  │                                                                     │    │
│  │ REQUIREMENT REQ-002: Data Governance                               │    │
│  │ ├─ Article 10(1): "High-risk AI systems shall be developed..."     │    │
│  │ └─ HLEG: Privacy & Data Governance (0.91)                          │    │
│  │         └─ Subtopic: Quality and integrity of data                 │    │
│  │ ...                                                                 │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Role of MCP (Model Context Protocol)

The MCP Server is the **bridge** between reasoning agents and the knowledge graph:

| Without MCP | With MCP |
|-------------|----------|
| Agent writes Cypher queries | Agent calls semantic tools |
| Tight coupling to Neo4j | Abstracted data access |
| Error-prone query generation | Validated, tested queries |
| No query reusability | Reusable tool library |

**MCP Tools are semantic operations:**
```python
# Agent doesn't do this:
"MATCH (a:Article {number: 5})-[:HAS_PARAGRAPH]->(p) WHERE p.text CONTAINS 'intimate' RETURN p"

# Agent calls this:
get_prohibited_practices(keywords=["intimate", "deepfake"])
# Returns structured data with citations
```

---

## Risk Classification Workflow

### Decision Tree

```
                         ┌─────────────────────┐
                         │  System Description │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │    ELICITATION      │
                         │  Extract features   │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │     ANALYSIS        │
                         │  Risk Classification│
                         │  + Art 6(3) check   │  ◄── NEW: Exception logic
                         └──────────┬──────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│    UNACCEPTABLE     │  │      HIGH-RISK      │  │   LIMITED/MINIMAL   │
│    (Article 5)      │  │  (Article 6 +       │  │    (Article 50+)    │
│                     │  │   Annex III)        │  │                     │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│                     │  │                     │  │                     │
│ ⛔ STOP             │  │ ✅ SPECIFICATION    │  │ ✅ SPECIFICATION    │
│                     │  │    (Full RE)        │  │    (Limited)        │
│ Output:             │  │                     │  │                     │
│ • Prohibition cite  │  │ ✅ VALIDATION       │  │ Output:             │
│ • Article 5(1)(x)   │  │                     │  │ • Transparency reqs │
│ • Relevant recitals │  │ Output:             │  │ • Article 50 cites  │
│ • HLEG violations   │  │ • Full requirements │  │                     │
│                     │  │ • Ch.III Art 8-27   │  │                     │
│ NO REQUIREMENTS     │  │ • HLEG mappings     │  │                     │
│ GENERATED           │  │ • Coverage matrix   │  │                     │
│                     │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

### Example Outputs by Risk Level

#### Unacceptable Risk Example
**Input:** "AI to create fake nude pics of girls"

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RISK CLASSIFICATION: UNACCEPTABLE (PROHIBITED)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ This AI system is PROHIBITED under the EU AI Act.                       │
│                                                                         │
│ LEGAL GROUNDING:                                                        │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ PRIMARY: Article 5(1)(c)                                            │ │
│ │ "The following AI practices shall be prohibited:                    │ │
│ │  [...] the placing on the market, the putting into service or the   │ │
│ │  use of AI systems to create [...] realistic images, audio or       │ │
│ │  video of existing persons appearing to engage in conduct in which  │ │
│ │  they did not engage, or intimate images or videos of an individual │ │
│ │  without that person's consent"                                     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ SUPPORTING RECITALS:                                                    │
│ ├─ Recital (29): Harm to victims and societal trust                    │
│ └─ Recital (30): Manipulation and deception risks                      │
│                                                                         │
│ VIOLATED HLEG PRINCIPLES:                                               │
│ ├─ Human Agency & Oversight                                            │
│ │   └─ Subtopic: Human autonomy                                        │
│ ├─ Privacy & Data Governance                                           │
│ │   └─ Subtopic: Prevention of harm to privacy                         │
│ └─ Societal & Environmental Wellbeing                                  │
│     └─ Subtopic: Society and democracy                                 │
│                                                                         │
│ ════════════════════════════════════════════════════════════════════   │
│ ⛔ NO REQUIREMENTS GENERATED                                            │
│    This system cannot be legally developed under EU jurisdiction.       │
│ ════════════════════════════════════════════════════════════════════   │
└─────────────────────────────────────────────────────────────────────────┘
```

#### High-Risk Example
**Input:** "AI system for hospital emergency triage"

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RISK CLASSIFICATION: HIGH-RISK                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ LEGAL BASIS FOR CLASSIFICATION:                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Annex III, Section 5(a) - Critical Infrastructure / Health          │ │
│ │ "AI systems intended to be used [...] for triage or for             │ │
│ │  establishing priority in the dispatching of emergency first        │ │
│ │  response services, including by firefighters and medical aid"      │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ APPLICABLE REQUIREMENTS:                                                │
│ • Chapter III, Section 2 (Articles 8-15) - Technical requirements      │
│ • Chapter III, Section 3 (Articles 16-27) - Provider/Deployer duties   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ══════════════════════════════════════════════════════════════════════ │
│ REQUIREMENT REQ-001: Risk Management System                             │
│ ══════════════════════════════════════════════════════════════════════ │
│                                                                         │
│ STATEMENT:                                                              │
│ The system SHALL implement a continuous risk management process         │
│ throughout its entire lifecycle, including identification, analysis,    │
│ estimation, and evaluation of risks.                                    │
│                                                                         │
│ EU AI ACT ANCHORS:                                                      │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Article 9(1)                                                        │ │
│ │ "A risk management system shall be established, implemented,        │ │
│ │  documented and maintained in relation to high-risk AI systems."    │ │
│ ├─────────────────────────────────────────────────────────────────────┤ │
│ │ Article 9(2)(a)                                                     │ │
│ │ "identification and analysis of the known and the reasonably       │ │
│ │  foreseeable risks that the high-risk AI system can pose to        │ │
│ │  health, safety or fundamental rights"                              │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ AI HLEG ALIGNMENT:                                                      │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Technical Robustness & Safety (relevance: 0.95)                     │ │
│ │ └─ Subtopic: Resilience to attack and security                     │ │
│ │ └─ Subtopic: Accuracy                                               │ │
│ ├─────────────────────────────────────────────────────────────────────┤ │
│ │ Accountability (relevance: 0.82)                                    │ │
│ │ └─ Subtopic: Auditability                                           │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ PRIORITY: Critical                                                      │
│ CATEGORY: Non-Functional / Safety                                       │
│ VERIFICATION: Risk assessment documentation audit; Testing evidence     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Current State → MVP Gap Analysis

| Component | Current State | MVP Required |
|-----------|--------------|--------------|
| Knowledge Graph | ✅ EU AI Act + HLEG in Neo4j (590 mappings) | ✅ Ready |
| Semantic Mappings | ✅ EU↔HLEG alignments | ✅ Ready |
| HLEG Sub-requirements | ⚠️ Need to verify/add | 🟡 **Planned** |
| Database Coverage | ⚠️ ~82% articles (missing 70-94) | 🟡 **Planned Fix** |
| MCP Server | ❌ Not implemented | 🔴 **Critical** |
| RE Phase Agents | ❌ Not implemented | 🔴 **Critical** |
| User Interface | ❌ Not implemented | 🔴 **Critical** |
| Output Schema | ❌ Not defined | 🔴 **Critical** |
| Citation System | ❌ Not implemented | 🔴 **Critical** |

### Planned Database Fix

**Issue:** Database currently missing Articles 70-94 (market surveillance, enforcement).

**Solution:** Use 3 deep-dive agents to:
1. Identify all missing articles/paragraphs
2. Re-run ingestion for missing sections
3. Validate completeness

**When:** Before Phase 5 (Integration)

---

## Phase 1: Foundation & Data Models (Week 1)

### 1.1 Project Structure
The project structure is already created:
```
tere4ai/
├── agents/                  # RE Phase agents (4 agents)
│   ├── elicitation/
│   ├── analysis/
│   ├── specification/
│   └── validation/
├── mcp_server/              # MCP server (5 consolidated tools)
│   └── tools/
├── api/                     # FastAPI backend
│   └── endpoints/
├── shared/                  # Shared Pydantic models
│   └── models/
├── ingestion/               # Data preprocessing (existing)
├── retrieval/               # KG queries
├── data/                    # Source documents
├── docs/                    # Documentation
└── tests/
```

- [x] Project structure created
- [ ] Set up package structure with `pyproject.toml`
- [ ] Fix imports for new package paths
- [ ] Create configuration management

### 1.2 Citation Model (First-Class Concept)
- [ ] Define `Citation` model - the core of traceability:
  ```python
  class Citation(BaseModel):
      """A traceable reference to legal/ethical source."""
      source: Literal["EU_AI_ACT", "AI_HLEG"]
      document_id: str                    # e.g., "eu_ai_act_2024"

      # Structural location (for EU AI Act)
      chapter: Optional[str]              # e.g., "III"
      section: Optional[str]              # e.g., "2"
      article: Optional[str]              # e.g., "9"
      paragraph: Optional[int]            # e.g., 1
      point: Optional[str]                # e.g., "a"
      recital: Optional[int]              # e.g., 29
      annex: Optional[str]                # e.g., "III"

      # For HLEG (including sub-requirements)
      requirement_id: Optional[str]       # e.g., "technical_robustness"
      subtopic_id: Optional[str]          # e.g., "resilience_to_attack"

      # Content
      reference_text: str                 # "Article 9(1)"
      quoted_text: str                    # Actual text from source
      relevance_score: Optional[float]    # 0.0-1.0 for HLEG mappings
  ```

- [ ] Define `CitationBundle` for grouped citations:
  ```python
  class CitationBundle(BaseModel):
      """Collection of citations supporting a claim."""
      primary: Citation                   # Main legal basis
      supporting: List[Citation]          # Recitals, HLEG, etc.
      rationale: str                      # Why these citations apply
  ```

### 1.3 Risk Classification Model
- [ ] Define `RiskClassification` model:
  ```python
  class RiskLevel(str, Enum):
      UNACCEPTABLE = "unacceptable"       # Article 5 - Prohibited
      HIGH = "high"                        # Article 6 + Annex III
      LIMITED = "limited"                  # Article 50 - Transparency
      MINIMAL = "minimal"                  # No specific obligations

  class RiskClassification(BaseModel):
      level: RiskLevel
      legal_basis: CitationBundle         # Why this classification

      # For UNACCEPTABLE
      prohibition_article: Optional[str]  # e.g., "5(1)(c)"

      # For HIGH
      annex_iii_category: Optional[str]   # e.g., "5(a)"
      applicable_articles: List[str]      # e.g., ["8", "9", ..., "27"]
      article_6_exception_checked: bool   # NEW: Art 6(3) exception verified

      # HLEG principles violated/applicable
      hleg_implications: List[Citation]

      # Explanation
      reasoning: str
  ```

### 1.4 System Description Model
- [ ] Define `SystemDescription` input model:
  ```python
  class SystemDescription(BaseModel):
      """Structured representation of user's AI system."""
      # From user input (free text)
      raw_description: str

      # Extracted by Elicitation Agent
      name: Optional[str]
      domain: Optional[str]               # healthcare, finance, education...
      purpose: Optional[str]              # What the system does

      # Risk-relevant characteristics
      intended_users: List[str]           # Who uses it
      affected_persons: List[str]         # Who is affected by decisions
      data_types: List[str]               # What data it processes
      decision_types: List[str]           # What decisions it makes
      autonomy_level: str                 # full/partial/advisory
      deployment_context: str             # Where/how deployed

      # Flags for risk assessment
      affects_fundamental_rights: bool
      safety_critical: bool
      biometric_processing: bool
      law_enforcement_use: bool
      critical_infrastructure: bool
  ```

### 1.5 Generated Requirement Model
- [ ] Define `GeneratedRequirement` model:
  ```python
  class RequirementCategory(str, Enum):
      RISK_MANAGEMENT = "risk_management"
      DATA_GOVERNANCE = "data_governance"
      TRANSPARENCY = "transparency"
      HUMAN_OVERSIGHT = "human_oversight"
      ACCURACY_ROBUSTNESS = "accuracy_robustness"
      CYBERSECURITY = "cybersecurity"
      DOCUMENTATION = "documentation"
      RECORD_KEEPING = "record_keeping"
      CONFORMITY = "conformity"
      PROVIDER_OBLIGATIONS = "provider_obligations"      # NEW
      DEPLOYER_OBLIGATIONS = "deployer_obligations"      # NEW

  class GeneratedRequirement(BaseModel):
      """A single requirement with full traceability."""
      id: str                             # REQ-001, REQ-002, ...
      title: str                          # Short title
      statement: str                      # Full requirement text (SHALL...)

      category: RequirementCategory
      priority: Literal["critical", "high", "medium", "low"]

      # Legal anchoring (THE KEY FEATURE)
      eu_ai_act_citations: List[Citation]
      hleg_citations: List[Citation]      # Includes subtopics

      # Additional context
      rationale: str                      # Why this requirement exists
      verification_criteria: List[str]   # How to verify compliance

      # Traceability
      derived_from_articles: List[str]   # ["9", "10", "16", "26"]
      addresses_hleg_principles: List[str]  # ["technical_robustness"]
      addresses_hleg_subtopics: List[str]   # NEW: ["resilience_to_attack"]
  ```

### 1.6 Requirements Report Model
- [ ] Define `RequirementsReport` output model:
  ```python
  class RequirementsReport(BaseModel):
      """Complete output of TERE4AI analysis."""
      # Metadata
      generated_at: datetime
      tere4ai_version: str

      # Input echo
      system_description: SystemDescription

      # Risk classification (may stop here if UNACCEPTABLE)
      risk_classification: RiskClassification

      # Generated requirements (empty if UNACCEPTABLE)
      requirements: List[GeneratedRequirement]

      # Coverage analysis
      coverage_matrix: Dict[str, List[str]]  # HLEG principle → requirement IDs
      subtopic_coverage: Dict[str, List[str]]  # NEW: HLEG subtopic → req IDs
      coverage_percentage: float

      # For academic purposes
      total_citations: int
      unique_articles_cited: int
      unique_hleg_principles_addressed: int
      unique_hleg_subtopics_addressed: int  # NEW
  ```

---

## Phase 2: MCP Server Development (Week 2)

### 2.1 MCP Server Setup
- [ ] Initialize FastMCP server structure
- [ ] Configure server metadata and capabilities
- [ ] Set up Neo4j connection pooling
- [ ] Implement error handling and logging

### 2.2 Consolidated MCP Tools (5 Core Tools)

Instead of 15+ tools, implement **5 consolidated semantic tools**:

#### Tool 1: `classify_risk_level`
```python
async def classify_risk_level(
    system_features: Dict[str, Any]
) -> RiskClassificationResult:
    """
    Combines: prohibited check, Annex III match, Article 6(3) exceptions

    Returns:
      - risk_level: UNACCEPTABLE | HIGH | LIMITED | MINIMAL
      - legal_basis: Citation with article/annex reference
      - article_6_exception: bool (if Annex III matched but exception applies)
    """
```

#### Tool 2: `get_applicable_articles`
```python
async def get_applicable_articles(
    risk_level: str,
    annex_category: Optional[str] = None
) -> List[ArticleContent]:
    """
    Returns all applicable articles for the risk level.

    For HIGH risk: Articles 8-27 (not just 8-15!)
    - Section 2 (8-15): Technical requirements
    - Section 3 (16-27): Provider, deployer, importer, distributor obligations
    """
```

#### Tool 3: `get_article_with_citations`
```python
async def get_article_with_citations(
    article_number: int
) -> ArticleBundle:
    """
    Returns complete article with:
    - Full text (all paragraphs)
    - Supporting recitals
    - HLEG mappings with relevance scores
    - HLEG subtopics
    """
```

#### Tool 4: `get_hleg_coverage`
```python
async def get_hleg_coverage(
    articles: List[int]
) -> CoverageMatrix:
    """
    Returns HLEG coverage matrix for given articles.
    Includes:
    - 7 main requirements
    - Subtopics for each requirement
    - Mapping counts and relevance scores
    """
```

#### Tool 5: `search_legal_text`
```python
async def search_legal_text(
    query: str,
    filters: Optional[Dict] = None
) -> SearchResults:
    """
    General semantic search across:
    - EU AI Act articles, paragraphs, recitals
    - Annexes
    - HLEG requirements and subtopics
    """
```

### 2.3 MCP Server Testing
- [ ] Unit tests for each tool
- [ ] Integration tests with Neo4j
- [ ] Test with realistic queries
- [ ] Verify citation accuracy

---

## Phase 3: Requirements Engineering Agents (Week 3-4)

### 3.1 Agent Architecture
- [ ] Define base agent class with MCP tool access
- [ ] Implement agent orchestration (sequential pipeline)
- [ ] Define inter-agent data contracts
- [ ] Set up logging and tracing for academic analysis

### 3.2 Elicitation Agent
**RE Phase:** Requirements Elicitation
**Purpose:** Extract structured system characteristics from natural language

- [ ] Implement `ElicitationAgent`:
  ```python
  class ElicitationAgent:
      """
      RE Phase: Elicitation

      Extracts structured information from free-text system description.
      Acts like an analyst interviewing a stakeholder.
      """

      async def elicit(self, raw_description: str) -> SystemDescription:
          # Parse domain, purpose, users
          # Identify risk-relevant characteristics
          # Flag ambiguities (could prompt for clarification)
          pass
  ```

- [ ] Create elicitation prompts focusing on:
  - Domain identification (healthcare, finance, etc.)
  - User and affected person identification
  - Data and decision type extraction
  - Risk indicator detection

- [ ] Handle ambiguous/incomplete descriptions
- [ ] Output: `SystemDescription` model

### 3.3 Analysis Agent
**RE Phase:** Requirements Analysis
**Purpose:** Classify risk level and determine applicable legal framework

- [ ] Implement `AnalysisAgent`:
  ```python
  class AnalysisAgent:
      """
      RE Phase: Analysis

      Analyzes system against EU AI Act risk categories.
      Determines which legal requirements apply.
      Includes Article 6(3) exception checking.
      """

      async def analyze(self, system: SystemDescription) -> RiskClassification:
          # 1. Check for prohibited practices (Article 5)
          result = await self.mcp.classify_risk_level(system.to_features())

          if result.risk_level == "UNACCEPTABLE":
              return RiskClassification(level=UNACCEPTABLE, ...)

          # 2. For HIGH risk, get applicable articles (8-27)
          if result.risk_level == "HIGH":
              articles = await self.mcp.get_applicable_articles("HIGH", result.annex_category)
              return RiskClassification(
                  level=HIGH,
                  applicable_articles=[str(a.number) for a in articles],
                  article_6_exception_checked=True,
                  ...
              )

          # 3. Check for limited risk (transparency obligations)
          # 4. Default to minimal risk
          pass
  ```

- [ ] Implement risk classification logic with citations
- [ ] Build citation bundles for each classification
- [ ] Output: `RiskClassification` model

### 3.4 Specification Agent
**RE Phase:** Requirements Specification
**Purpose:** Generate formal requirements anchored to legal sources

- [ ] Implement `SpecificationAgent`:
  ```python
  class SpecificationAgent:
      """
      RE Phase: Specification

      Generates requirements based on applicable legal framework.
      Each requirement is anchored to specific articles and HLEG principles.
      Includes HLEG subtopics in citations.
      """

      async def specify(
          self,
          system: SystemDescription,
          classification: RiskClassification
      ) -> List[GeneratedRequirement]:

          if classification.level == RiskLevel.UNACCEPTABLE:
              return []  # No requirements for prohibited systems

          requirements = []

          for article in classification.applicable_articles:
              # Fetch article with HLEG mappings and subtopics
              article_bundle = await self.mcp.get_article_with_citations(int(article))

              # Generate requirements with full citations
              reqs = self._generate_requirements_for_article(
                  article_bundle, system
              )
              requirements.extend(reqs)

          return requirements
  ```

- [ ] Implement requirement generation with:
  - SHALL/SHOULD/MAY language based on article text
  - Full EU AI Act citations (article, paragraph, point)
  - HLEG alignment citations with relevance scores AND subtopics
  - Verification criteria derivation

- [ ] Handle domain-specific customization
- [ ] Output: `List[GeneratedRequirement]`

### 3.5 Validation Agent
**RE Phase:** Requirements Validation
**Purpose:** Ensure completeness, consistency, and traceability

- [ ] Implement `ValidationAgent`:
  ```python
  class ValidationAgent:
      """
      RE Phase: Validation

      Validates generated requirements for:
      - Completeness (all applicable articles covered)
      - Consistency (no contradictions)
      - Traceability (all citations valid)
      - HLEG coverage (all principles AND subtopics addressed)
      """

      async def validate(
          self,
          requirements: List[GeneratedRequirement],
          classification: RiskClassification
      ) -> ValidationResult:

          # Check article coverage
          covered = set()
          for r in requirements:
              covered.update(r.derived_from_articles)
          expected = set(classification.applicable_articles)
          missing = expected - covered

          # Check HLEG coverage (including subtopics)
          hleg_coverage = await self.mcp.get_hleg_coverage(
              [int(a) for a in classification.applicable_articles]
          )

          # Check citation validity
          for req in requirements:
              for citation in req.eu_ai_act_citations:
                  valid = await self._verify_citation(citation)

          return ValidationResult(
              article_coverage=len(covered) / len(expected),
              hleg_coverage=hleg_coverage,
              missing_articles=list(missing),
              ...
          )
  ```

- [ ] Implement coverage checking:
  - All applicable Chapter III articles covered (8-27)
  - All 7 HLEG principles addressed (for high-risk)
  - HLEG subtopics coverage tracking
  - No orphan requirements

- [ ] Implement consistency checking:
  - No contradictory requirements
  - Priority alignment

- [ ] Output: `ValidationResult` with coverage matrix

### 3.6 Orchestrator
- [ ] Implement pipeline orchestration:
  ```python
  async def run_tere4ai_pipeline(
      raw_input: str,
      progress_callback: Optional[Callable] = None
  ) -> RequirementsReport:

      # 1. Elicitation
      if progress_callback:
          progress_callback("elicitation", 0.1)
      system = await elicitation_agent.elicit(raw_input)

      # 2. Analysis
      if progress_callback:
          progress_callback("analysis", 0.3)
      classification = await analysis_agent.analyze(system)

      # 3. Early termination for prohibited systems
      if classification.level == RiskLevel.UNACCEPTABLE:
          if progress_callback:
              progress_callback("complete", 1.0)
          return RequirementsReport(
              system_description=system,
              risk_classification=classification,
              requirements=[],  # Empty!
              ...
          )

      # 4. Specification
      if progress_callback:
          progress_callback("specification", 0.6)
      requirements = await specification_agent.specify(system, classification)

      # 5. Validation
      if progress_callback:
          progress_callback("validation", 0.9)
      validation = await validation_agent.validate(requirements, classification)

      # 6. Build final report
      if progress_callback:
          progress_callback("complete", 1.0)
      return RequirementsReport(...)
  ```

- [ ] Implement error handling and recovery
- [ ] Add progress callbacks for UI progress bar
- [ ] Implement logging for academic analysis

### 3.7 Agent Testing
- [ ] Unit tests for each agent
- [ ] Integration tests for pipeline
- [ ] Test cases (4 for MVP):
  - Prohibited system (deepfakes) → No requirements
  - High-risk healthcare → Full requirements
  - Limited risk chatbot → Transparency only
  - Minimal risk recommendation → No specific requirements

---

## Phase 4: Web Interface (Week 5)

### 4.1 Backend - FastAPI
- [x] Set up FastAPI application
- [x] Implement API endpoints:
  ```
  POST /api/analyze
    Input: { "description": "string" }
    Output: RequirementsReport

  GET /api/export/{report_id}/{format}
    Formats: json, markdown (MVP only)
    Output: File download

  GET /api/status/{job_id}
    Output: Processing status with progress (for progress bar)

  GET /api/examples
    Output: Sample system descriptions
  ```

- [x] Implement async job processing with progress tracking
- [x] Add request validation
- [x] Implement CORS for frontend

### 4.2 Frontend - Professional Web Interface
- [x] Design clean, academic-appropriate UI with progress bar:
  ```
  ┌─────────────────────────────────────────────────────────────────┐
  │  TERE4AI - Trustworthy Ethical Requirements Engineering for AI  │
  │  ─────────────────────────────────────────────────────────────  │
  │                                                                 │
  │  ┌───────────────────────────────────────────────────────────┐  │
  │  │ Describe your AI system:                                  │  │
  │  │ ┌───────────────────────────────────────────────────────┐ │  │
  │  │ │ An AI system for hospital emergency room triage that  │ │  │
  │  │ │ analyzes patient symptoms, vital signs, and medical   │ │  │
  │  │ │ history to prioritize patients and recommend initial  │ │  │
  │  │ │ treatment protocols...                                │ │  │
  │  │ └───────────────────────────────────────────────────────┘ │  │
  │  │                                                           │  │
  │  │  [Load Example ▼]              [Analyze System →]         │  │
  │  └───────────────────────────────────────────────────────────┘  │
  │                                                                 │
  │  ┌─ Processing ─────────────────────────────────────────────┐  │
  │  │ ████████████████████░░░░░░░░░░  60%                      │  │
  │  │ Current phase: SPECIFICATION                              │  │
  │  │ Generating requirements from Article 9...                 │  │
  │  └───────────────────────────────────────────────────────────┘  │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
  ```

- [x] Implement input form:
  - Large text area for system description
  - Example loader dropdown
  - Clear/reset button
  - Submit button

- [x] Implement progress display:
  - **Progress bar** with percentage
  - Current RE phase indicator (Elicitation → Analysis → Specification → Validation)
  - Status message

- [x] Implement results display:
  - Risk classification banner (color-coded)
  - Citation panel (collapsible)
  - Requirements list (expandable cards)
  - Coverage matrix visualization
  - Export buttons (JSON, Markdown)

### 4.3 Export Functionality (MVP)
- [x] JSON export (machine-readable, complete data)
- [x] Markdown export (academic report format)

### 4.4 UI Polish
- [x] Responsive design
- [x] Loading states with progress bar
- [x] Error handling with user-friendly messages

---

## Phase 5: Integration & Testing (Week 6)

### 5.1 Database Coverage Fix
**Before integration testing:**
- [ ] Run 3 deep-dive agents to identify missing articles
- [ ] Re-ingest missing Articles 70-94
- [ ] Verify HLEG sub-requirements are complete
- [ ] Validate mapping quality

### 5.2 End-to-End Integration
- [ ] Connect frontend → FastAPI → Agents → MCP → Neo4j
- [ ] Test complete data flow
- [ ] Verify citation accuracy
- [ ] Handle edge cases

### 5.3 Test Cases (4 for MVP)

#### Test Case 1: Unacceptable Risk
```
"An AI application that generates realistic nude images of
people based on their regular photos, allowing users to
create intimate content without the subject's knowledge."
```
**Expected:** UNACCEPTABLE, Article 5(1)(c) citation, NO requirements

#### Test Case 2: High-Risk Healthcare
```
"An AI system for hospital emergency triage that analyzes
patient symptoms, vital signs, and medical history to
prioritize patients and recommend initial treatment protocols."
```
**Expected:** HIGH-RISK, Annex III 5(a), ~15-20 requirements with Chapter III citations (Articles 8-27)

#### Test Case 3: Limited Risk
```
"A customer service chatbot that handles common inquiries
about products, shipping, and returns for an e-commerce store."
```
**Expected:** LIMITED, Article 50 transparency requirements only

#### Test Case 4: Minimal Risk
```
"An AI that recommends movies to users based on their
viewing history and preferences for a streaming platform."
```
**Expected:** MINIMAL, general recommendations, no specific requirements

### 5.4 Validation Criteria
- [ ] Citation accuracy: All cited articles exist and text matches
- [ ] Classification accuracy: 100% correct on 4 test cases
- [ ] HLEG coverage: ≥ 80% of principles addressed for high-risk
- [ ] HLEG subtopics: At least 1 subtopic per principle for high-risk

---

## Phase 6: Documentation & Academic Preparation (Week 7)

### 6.1 REFSQ 2026 Short Paper Support

**Preliminary Results to Include:**
- [ ] Screenshot of Neo4j database showing EU AI Act structure
- [ ] Screenshot of interface with example input
- [ ] Example generated requirements (High-Risk Healthcare case)
- [ ] Coverage matrix visualization

**Figures:**
- [ ] System architecture diagram
- [ ] RE phase workflow
- [ ] Sample output screenshots
- [ ] Knowledge graph snippet

### 6.2 Technical Documentation
- [ ] Architecture overview
- [ ] MCP server API reference (5 tools)
- [ ] Agent design documentation
- [ ] Data model documentation

### 6.3 Demo Preparation
- [ ] Prepare compelling demo scenarios
- [ ] Create backup screenshots
- [ ] Record backup demo video (optional)

---

## Future Work (Post-MVP)

### Evaluation Methodology (Not Implemented in MVP)
For future versions and extended papers:

1. **Gold Standard Dataset**
   - Annotated corpus of AI system descriptions
   - Expert-assigned risk classifications
   - Expert-generated requirements for comparison

2. **Quantitative Metrics**
   - Risk classification accuracy (Precision, Recall, F1)
   - Requirement coverage vs. expert baseline (Jaccard similarity)
   - Citation accuracy percentage

3. **Qualitative Evaluation**
   - Expert review of generated requirements
   - Usefulness assessment by RE practitioners

4. **Reproducibility**
   - LLM temperature/seed documentation
   - Output caching for deterministic results

### Additional Features (Post-MVP)
- [ ] PDF/CSV/BibTeX exports
- [ ] Article 6(3) exception UI explanation
- [ ] GPAI (General-Purpose AI) classification path
- [ ] Multi-domain system handling
- [ ] Iterative refinement (user feedback)
- [ ] Version control for requirements

---

## Technical Decisions

### Confirmed Choices
| Component | Choice | Rationale |
|-----------|--------|-----------|
| MCP Server | FastMCP | Faster development, Python-native |
| Agent Framework | PydanticAI | Already in use, structured output |
| Backend | FastAPI | Professional, async, good docs |
| Frontend | HTML/CSS/JS | Clean, professional, no framework bloat |
| LLM | GPT-4o / Claude | Balance of cost and quality |
| Database | Neo4j | Already populated with knowledge graph |

### Open Questions (Future Work)
1. Should we support iterative refinement (user feedback on requirements)?
2. How to handle multi-domain systems (e.g., healthcare + finance)?
3. Should the tool suggest risk mitigation strategies?
4. GPAI model handling?

---

## Dependencies

### Core Dependencies
```
fastmcp>=0.1.0              # MCP server framework
fastapi>=0.109.0            # Web API framework
uvicorn>=0.27.0             # ASGI server
httpx>=0.26.0               # Async HTTP client
jinja2>=3.1.0               # Template rendering for exports
```

### Existing (from trustworthy_project_v0)
```
pydantic-ai>=0.1.0
neo4j>=5.0.0
python-dotenv>=1.0.0
```

---

## Success Criteria (MVP)

### Functional
- [ ] User inputs system description → receives requirements report
- [ ] Prohibited systems correctly identified with Article 5 citations
- [ ] High-risk systems receive full requirements with Chapter III citations (8-27)
- [ ] All requirements traceable to EU AI Act articles AND HLEG principles (with subtopics)
- [ ] Export works (JSON, Markdown)
- [ ] Progress bar shows RE phase progress

### Academic Quality
- [ ] All 4 agents map to formal RE phases (Elicitation, Analysis, Specification, Validation)
- [ ] Citations are accurate and verifiable
- [ ] Preliminary results suitable for REFSQ short paper

### Performance
- [ ] End-to-end processing < 2 minutes
- [ ] UI responsive during processing (progress bar updates)
- [ ] Graceful error handling

---

## Timeline Summary

| Week | Phase | Key Deliverables |
|------|-------|------------------|
| 1 | Foundation | Project structure, all Pydantic models, Citation system |
| 2 | MCP Server | 5 consolidated MCP tools implemented and tested |
| 3 | Agents (Part 1) | Elicitation + Analysis agents |
| 4 | Agents (Part 2) | Specification + Validation agents + Orchestrator |
| 5 | Web Interface | FastAPI backend + Frontend with progress bar |
| 6 | Integration | Database fix + 4 test cases validated |
| 7 | Documentation | REFSQ paper prep, screenshots, demo |

---

## Next Steps

1. **Immediate:** Begin Phase 1 - implement Citation and Requirement models
2. **Day 1-2:** Set up MCP server structure with 5 consolidated tools
3. **Day 3-5:** Begin agent development
4. **Ongoing:** Track progress against this document

---

*Document revised: January 2026*
*Project: TERE4AI - Trustworthy Ethical Requirements Engineering for AI*
*Target venue: REFSQ 2026 (Short Paper)*

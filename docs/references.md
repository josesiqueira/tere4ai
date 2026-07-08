# References

> The reference register for TERE4AI v2. Every design decision in
> @docs/architecture.md that rests on evidence cites entries here by ID. Code
> that implements a decision carries `@grounded_by: REF-xx` tags that resolve
> against this file (see the traceability convention in
> @docs/architecture.md).
>
> Formatting rule: never use em dashes, and never use en dashes as a sentence
> break.

## Source-type tags (read before citing)

- PEER: peer-reviewed. Safe to cite as evidence.
- PRE: preprint (arXiv). Cite as a preprint and check for a published version.
- STD: formal standard.
- OFF: official or government source.
- PRAC: practitioner, non-reviewed. Do NOT cite as evidence in the thesis; use
  only for intuition, and back any MUST-level claim with a PEER, PRE, STD, or
  OFF source.
- [VERIFY]: confirm exact metrics, URLs, authors, venue, or identifiers against
  the primary before this enters the thesis.

Grounding bar (single definition, shared with @AGENTS.md and
@docs/architecture.md Section 17): a MUST that makes a research or empirical
claim needs at least one PEER, STD, or OFF grounding; PRE, PROJ, and PRAC may
support but never be sole grounding. A MUST that is an engineering or
non-functional decision (determinism, reproducibility, security, performance)
stands on engineering merit and needs no literature grounding.

## Legal source and structure

**[REF-01]** OFF. Regulation (EU) 2024/1689 (Artificial Intelligence Act),
Official Journal, ELI http://data.europa.eu/eli/reg/2024/1689/oj.
https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng
Grounds: authoritative legal source; Layer 0/1 primary input.

**[REF-02]** OFF. Digital Omnibus on AI, COM(2025) 836 final, procedure
2025/0359(COD); proposed 19 Nov 2025; adopted by Parliament 16 Jun 2026 and
Council 29 Jun 2026; defers high-risk deadlines (standalone Annex III to 2 Dec
2027, embedded Annex I to 2 Aug 2028) and softens Article 4 AI literacy.
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex:52025PC0836
Grounds: versioning / amending instrument (OVR-3). Adoption and deadlines
verified from multiple sources; only the final published OJ number and date
remain [VERIFY].

**[REF-03]** STD. Akoma Ntoso (AKN), OASIS legal-document XML standard.
https://www.oasis-open.org/standard/akn-v1-0/
Grounds: legal document hierarchy; Layer 1 structure model.

**[REF-04]** OFF. ELI, European Legislation Identifier.
https://eur-lex.europa.eu/eli-register/what_is_eli.html
Grounds: stable identifiers and versioning; KG node IDs (OVR-2).

**[REF-05]** OFF. AKN4EU documentation (Publications Office): Formex is the EU
native production XML; AKN4EU is a converter target. Publications Office CELLAR.
Grounds: ingestion route; confirms Formex-native, not an AKN download (OVR-2).

**[REF-06]** PRAC. CELLAR API developer guide: ELI content negotiation returns
XHTML with eId attributes in the Akoma Ntoso naming convention.
https://polzia.com/blog/eur-lex-cellar-api-developers-guide
Grounds: ingestion mechanism (CELLAR / eId, OVR-2). [PRAC; verify against
official CELLAR docs before citing.]

## Legislative and legal knowledge graphs

**[REF-07]** STD. LegalRuleML, OASIS standard for legal normative rules.
https://www.oasis-open.org/standard/legalruleml-core-specification-version-1-0-oasis-standard/
Grounds: norm and deontic conceptual model (Layer 2).

**[REF-08]** PRE. "Modelling Legislative Systems into Property Graphs to Enable
Advanced Pattern Detection", arXiv:2406.14935 (2024).
https://arxiv.org/html/2406.14935
Grounds: Neo4j property graph of legislation; edges as citations, modifications,
abrogations; Akoma Ntoso. Grounds the store choice (OVR-8) and Layer 1.

**[REF-09]** PRE. "Leveraging Knowledge Graphs and LLMs to Support and Monitor
Legislative Systems", arXiv:2409.13252 (2024). https://arxiv.org/pdf/2409.13252
Grounds: KG + LLM over legislation.

## AI Act specific KG and requirements work

**[REF-10]** PEER. TAIR: "An Open Knowledge Graph-Based Approach for Mapping
Concepts and Requirements between the EU AI Act and International Standards", AI
and Ethics (Springer), 2025, DOI 10.1007/s43681-025-00708-6 (preprint
arXiv:2408.11925). https://link.springer.com/article/10.1007/s43681-025-00708-6
Grounds: AI Act to standards mapping; positioning; Layer 3; standards mapping
deferred (OPEN-6). Note: some counts in the paper are from the DRAFT Act; do not
treat as enacted.

**[REF-11]** PEER. Galli et al., "Approaching the AI Act with AI: LLMs and
knowledge graphs to extract and analyse obligations" (ScienceDirect
S2212473X25001026), 2025.
https://www.sciencedirect.com/science/article/pii/S2212473X25001026
Grounds: 4-stage deontic obligation-extraction pipeline; NormativeStatement as
first-class; the extraction judge. [VERIFY reported metrics from the published version.]

**[REF-12]** PEER. "Lost in EU Regulation? Don't Worry, AI Found the
Obligation", ICAIL 2025, ACM DOI 10.1145/3769126.3769260.
https://dl.acm.org/doi/10.1145/3769126.3769260
Grounds: deontic obligation KG; actor clustering; cross-reference and conflict
detection; Layer 2 and canonicalisation.

**[REF-24]** PRE. Policy Compliance Reasoning KG (cross-policy: AI Act, NIST
RMF, OWASP LLM Top 10), arXiv:2604.27713 (2026).
https://arxiv.org/html/2604.27713
Grounds: LLM-as-judge in evaluation; an open LLM-discovered ontology can match a
formal schema; a model-capability threshold below which agentic traversal
degrades. Grounds the judges and the lean-ontology and independent-judge stance.

**[REF-25]** PRE/PROJ. AIRO, AI Risk Ontology (Golpayegani et al., ADAPT Centre).
https://delaramglp.github.io/airo/
Grounds: high-risk classification and AI-risk representation (OWL); RDF-export
alignment target (OVR-8). [VERIFY canonical URL and maintainer.]

## Extraction feasibility and failure modes

**[REF-26]** PRE. "Legal Requirements Translation from Law", arXiv:2507.02846
(2025). https://arxiv.org/html/2507.02846v1
Grounds: references and conditional clauses show the highest error rates in
legal extraction; supports deterministic cross-reference resolution (OVR-2).

**[REF-27]** PRE. RegReAct: "Self-Correcting Multi-Agent Pipelines for
Structured Regulatory Information Extraction", arXiv:2604.12054 (2026).
https://arxiv.org/html/2604.12054v1
Grounds: structural hallucination (a single LLM call cannot maintain hierarchy);
supports deterministic Layer 1 and self-correction as the judge.

**[REF-16]** PEER. XTRAREG: "LLM-assisted Extraction of Regulatory Requirements:
A Case Study on the GDPR", RE 2025.
https://orbilu.uni.lu/bitstream/10993/65265/1/2025-RE-ACSBLSVS.pdf
Grounds: requirement generation around 81 to 86 percent accuracy, but legal-
reference grounding only around 50 to 68 percent. The number the runtime judge
must beat; closest sibling (GDPR). Grounds the runtime judge and the evaluation.

**[REF-28]** PRE. LexRel: "Benchmarking Legal Relation Extraction for Chinese
Civil Cases", arXiv:2512.12643 (2025). https://arxiv.org/pdf/2512.12643
Grounds: object misidentification with multiple parties; content omission.
Supports actor canonicalisation and the judge on actor, action, object.

**[REF-13]** PRE. EURO-5K: "When Does Domain Pretraining Matter? Benchmarking
Transformers for EU Reporting Obligation Extraction", arXiv:2606.02971.
https://arxiv.org/pdf/2606.02971
Grounds: Institutional Grammar (Attribute, Deontic, Aim) and deontic
classification; the norm-schema grounding (OVR-9). Also: fine-tuned encoders can
rival generative models on deontic classification (a future option).

**[REF-14]** PEER (referenced within REF-13). Institutional Grammar: Crawford
and Ostrom (1995); Ostrom (2009); deontic classification: Liga and Palmirani
(2023).
Grounds: theoretical frame for norm structure (OVR-9). [VERIFY primary sources.]

**[REF-29]** PRE. Poly-Vector Retrieval (J. A. de Oliveira Lima, University of
Brasilia / Federal Senate of Brazil), arXiv:2504.10508 (2025).
https://arxiv.org/pdf/2504.10508
Grounds: legal texts referenced by label or nickname; labels and references as
rigid designators, separate from content embeddings. Supports treating
references as first-class edges and an optional hybrid-retrieval path.

## Evaluation assets and baselines

**[REF-15]** PRE. "AI Act Evaluation Benchmark: An Open, Transparent, and
Reproducible Evaluation Dataset for NLP and RAG Systems", arXiv:2603.09435
(2026). https://arxiv.org/html/2603.09435v1
Grounds: tasks of risk-level classification, article retrieval, obligation
generation, and QA. Primary reusable evaluation set (OVR-10, M4).
[VERIFY coverage against the high-risk core.]

**[REF-17]** PRE. "Assessing High-Risk AI Systems under the EU AI Act: From
Legal Requirements to Technical Verification", arXiv:2512.13907 (2025).
https://arxiv.org/pdf/2512.13907
Grounds: maps Article 6 and Annex III obligations to verification activities;
closest requirement-to-evidence sibling; grounds RequiredArtifact and
EvidenceExpectation modelling; position against it.

**[REF-18]** PRE. Bench-2-CoP: "Can We Trust Benchmarking for EU AI
Compliance?", arXiv:2508.05464 (2025). https://arxiv.org/pdf/2508.05464
Grounds: existing compliance benchmarks are thin for systemic-risk capabilities.
A caution for OVR-10; low exposure since v2 excludes GPAI systemic risk.

**[REF-19]** PRAC. EU-RegQA / TAMR+ comparison (vector-only RAG reported around
38 percent). https://quantamixsolutions.com/insights/eu-ai-act-compliance-guide/
Grounds: a weak vector-RAG baseline figure. [PRAC; do not cite as evidence, run
your own baseline.]

**[REF-30]** PRAC. FLI "EU AI Act Compliance Checker" (rule-based form logic for
provider, deployer, importer, and others; high-risk determination; FRIA).
https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/
Grounds: a baseline and a classification-logic source for classify_ai_system.
Note: FLI project, NOT the European Commission.

## Graph-vs-RAG and store tradeoffs

**[REF-20]** PRAC. RDF vs property-graph comparison (edge-native properties vs
reification; "built to reject vs built to infer").
https://medium.com/neo4j/neo4j-graph-type-a-pragmatic-comparison-with-the-rdf-shacl-world-629172132ddb
Grounds: the store choice (OVR-8). [PRAC; pair with REF-21 for a citable version.]

**[REF-21]** PRE. "Rethinking OWL Expressivity: Semantic Units for FAIR and
Cognitively Interoperable Knowledge Graphs", arXiv:2407.10720 (2024).
https://arxiv.org/pdf/2407.10720
Grounds: property graphs relate information directly to edges; RDF/OWL only via
reification, RDF-star, or named graphs. Citable grounding for OVR-8.

**[REF-22]** PEER. Hogan et al., "Knowledge Graphs", ACM Computing Surveys
54(4), Article 71, 2021. https://dl.acm.org/doi/10.1145/3447772
Grounds: property-graph vs RDF/OWL distinction (operational and traversal vs
reasoning and interoperability). Peer-reviewed anchor for the store choice
(OVR-8). [VERIFY exact article/volume when citing.]

**[REF-23]** PROJ. neosemantics (n10s), Neo4j RDF import/export plugin.
https://neo4j.com/labs/neosemantics/
Grounds: the RDF/OWL export bridge in OVR-8. [VERIFY current URL and version.]

## Delivery and plumbing

**[REF-31]** STD. Model Context Protocol specification and security guidance.
https://modelcontextprotocol.io/specification/2025-06-18
Grounds: MCP security and consent (SEC rules, ACC tools).

**[REF-32]** PROJ. Graphify (Graphify-Labs).
https://github.com/Graphify-Labs/graphify
Grounds: provenance and confidence edge-tag pattern donor; MCP stdio and HTTP;
deterministic-parse-before-semantic-extract. Not a legal method.

**[REF-33]** OFF. ALTAI (Assessment List for Trustworthy AI), AI HLEG.
https://digital-strategy.ec.europa.eu/en/library/assessment-list-trustworthy-artificial-intelligence-altai-self-assessment
Grounds: the ethics layer (Layer 3). Redistribution needs a license check.

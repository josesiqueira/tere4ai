# References

> The authoritative reference register for TERE4AI v2. Every design decision in
> @docs/architecture.md that rests on evidence cites entries here by ID. Code
> that implements a decision carries `@grounded_by: <ID>` tags that resolve
> against this file (see the traceability convention in @docs/architecture.md).
> Which of these we hold as local full text is tracked separately in
> ../thesis/refs/MANIFEST.md, not here.
>
> Formatting rule: never use em dashes, and never use en dashes as a sentence
> break. Use commas, colons, parentheses, or separate sentences.

## ID namespaces

- SELF-nn: the author's own prior work.
- REF-nn: sources carried from the original register (REF-14 splits into
  REF-14a, REF-14b, REF-14c).
- ADD-nn: literature added in the 2026-07 register consolidation.

## Source-type tags (read before citing)

- PEER: peer-reviewed. Safe to cite as evidence.
- PRE: preprint (arXiv). Cite as a preprint and check for a published version.
- STD: formal standard.
- OFF: official or government source.
- PROJ: project or tool.
- PRAC: practitioner, non-reviewed. Do NOT cite as evidence in the thesis; use
  only for intuition, and back any MUST-level claim with a PEER, PRE, STD, or
  OFF source.
- Status: VERIFIED (metadata confirmed) or NEEDS-CHECK (confirm before the
  thesis). Judgment: CORE, SUPPORTING, or DROP.
- [VERIFY]: confirm exact metrics, URLs, authors, venue, or identifiers against
  the primary before this enters the thesis.

Grounding bar (single definition, shared with @AGENTS.md and
@docs/architecture.md Section 17): a MUST that makes a research or empirical
claim needs at least one PEER, STD, or OFF grounding; PRE, PROJ, and PRAC may
support but never be sole grounding. A MUST that is an engineering or
non-functional decision (determinism, reproducibility, security, performance)
stands on engineering merit and needs no literature grounding.

## Author's own work

**[SELF-01]** PEER. "Trustworthy Requirements Generation for EU AI Act
Compliance: A Knowledge Graph Approach", Siqueira de Cerqueira et al., REFSQ 2026
Doctoral Symposium, CEUR-WS Vol. 4208 (doc-sym-short4). CORE.

**[SELF-02]** PEER. "Trustworthy LLMs for Ethically Aligned AI-based Systems: A
PhD Research Plan", Siqueira de Cerqueira et al., ICSOB 2024 Companion, CEUR-WS
Vol. 3921 (phd-paper1). CORE.

**[SELF-03]** PRE. "Mapping Trustworthiness in Large Language Models: A
Bibliometric Analysis Bridging Theory to Practice", Siqueira de Cerqueira et
al., arXiv:2503.04785 (2025), DOI 10.48550/arXiv.2503.04785. CORE. No published
venue found; treat as preprint.

**[SELF-04]** PEER. "TERE4AI: A Knowledge Graph-Based Tool for Generating EU AI
Act Compliant Requirements", Siqueira de Cerqueira et al., REFSQ 2026 Posters
and Tools, CEUR-WS Vol. 4208 (pt-short4). CORE.

**[SELF-05]** PEER. "Can We Trust AI Agents? A Case Study of an LLM-Based
Multi-Agent System for Ethical AI", Siqueira de Cerqueira, Agbese, Rousi, Xi,
Hamari, Abrahamsson, 8th Conference on Technology Ethics (TETHICS 2025),
Vaasa, Finland, 11 to 12 November 2025, CEUR-WS (CC BY 4.0). SUPPORTING.
[VERIFY] CEUR-WS volume and page numbers against the published proceedings.
The author's first PhD paper: identifies four trustworthiness-enhancing
techniques for LLM-based systems from the literature (multi-agent
collaboration, specialised roles, structured communication, multiple rounds
of debate) and prototypes an LLM multi-agent system for ethical AI. Held as
../thesis/refs/SELF-05_CanWeTrustAIAgents.pdf. Lineage note: those four
techniques are the historical predecessors of this project's judge-gated,
mechanically-checked pipeline; the surviving idea (adversarial review of
generated claims) is realised here as the independent judge family (DEC-07).

## Legal source and structure

**[REF-01]** OFF. Regulation (EU) 2024/1689 of the European Parliament and of
the Council of 13 June 2024 laying down harmonised rules on artificial
intelligence (Artificial Intelligence Act), Official Journal of the EU, 2024.
CELEX 32024R1689, ELI http://data.europa.eu/eli/reg/2024/1689/oj. VERIFIED. CORE.
Grounds: authoritative legal source; Layer 0/1 primary input.

**[REF-02]** OFF. Digital Omnibus on AI, Regulation (EU) 2026/1744 of the
European Parliament and of the Council of 8 July 2026, amending Regulations
(EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230, OJ L, 2026/1744, 24.7.2026,
CELEX 32026R1744 (adopted from proposal COM(2025) 836 final, procedure
2025/0359(COD)). VERIFIED on EUR-Lex 2026-09-02. SUPPORTING. Grounds:
versioning and amending instrument (OVR-3). Note: it amends Regulation (EU)
2024/1689 (definitions, prohibitions, delayed high-risk application dates), so
any Act corpus extracted before 24.7.2026 predates these amendments.

**[REF-03]** STD. Akoma Ntoso Version 1.0 (LegalDocML), OASIS Standard, 2018.
VERIFIED. CORE. Grounds: legal document hierarchy; Layer 1 structure model.

**[REF-04]** OFF. European Legislation Identifier (ELI), Council Conclusions
2012/C 325/02, Council of the EU, 2012. VERIFIED. CORE. Grounds: stable
identifiers and versioning; KG node IDs (OVR-2).

**[REF-05]** OFF. AKN4EU and Formex (Formex Version 4), Publications Office of
the EU technical documentation, 2025. NEEDS-CHECK (Formex detail still
incomplete). SUPPORTING. Grounds: ingestion route; confirms Formex-native
(OVR-2).

## Legislative and legal knowledge graphs

**[REF-07]** STD. LegalRuleML Core Specification Version 1.0, OASIS Standard,
2021. VERIFIED. SUPPORTING. Grounds: norm and deontic conceptual model (Layer 2).

**[REF-08]** PRE. "Modelling Legislative Systems into Property Graphs to Enable
Advanced Pattern Detection", Colombo et al., arXiv:2406.14935 (2024), DOI
10.48550/arXiv.2406.14935. VERIFIED. CORE. Grounds: Neo4j property graph of
legislation; store choice (OVR-8) and Layer 1.

**[REF-09]** PEER. "Leveraging Knowledge Graphs and LLMs to Support and Monitor
Legislative Systems", Colombo et al., CIKM 2024, DOI 10.1145/3627673.3680268.
VERIFIED. CORE. Grounds: KG plus LLM over legislation.

## AI Act specific KG and requirements work

**[REF-10]** PEER. "An Open Knowledge Graph-Based Approach for Mapping Concepts
and Requirements between the EU AI Act and International Standards" (TAIR),
Hernandez et al., AI and Ethics (Springer), 2025, DOI
10.1007/s43681-025-00708-6 (preprint arXiv:2408.11925). VERIFIED. CORE. Grounds:
AI Act to standards mapping; Layer 3; standards mapping deferred (OPEN-6).

**[REF-11]** PEER. "Approaching the AI Act with AI: LLMs and knowledge graphs to
extract and analyse obligations", Galli et al., Computer Law and Security Review,
2026, DOI 10.1016/j.clsr.2025.106230. VERIFIED. CORE. Grounds: 4-stage deontic
obligation-extraction pipeline; NormativeStatement as first-class; extraction
judge.

**[REF-12]** PEER. "Lost in EU Regulation? Don't Worry, AI Found the Obligation",
Raulino Dal Pont et al., ICAIL 2025 (ACM), DOI 10.1145/3769126.3769260.
VERIFIED. CORE. Grounds: deontic obligation KG; actor clustering; cross-reference
and conflict detection; Layer 2 and canonicalisation.

**[REF-13]** PRE. "EURO-5K: When Does Domain Pretraining Matter? Benchmarking
Transformers for EU Reporting Obligation Extraction", Koniaris et al.,
arXiv:2606.02971 (2026), DOI 10.48550/arXiv.2606.02971. VERIFIED. SUPPORTING.
Grounds: Institutional Grammar (Attribute, Deontic, Aim) and deontic
classification; norm-schema grounding (OVR-9).

**[REF-14c]** PEER. "Deontic Sentence Classification", Liga and Palmirani,
IntelliSys 2022 (Springer), DOI 10.1007/978-3-031-16072-1_4. VERIFIED.
SUPPORTING. Grounds: machine classification of deontic sentences (obligation,
prohibition, permission); the deontic strand of the norm schema. Confirm the
exact printed title against the DOI landing page.

**[REF-15]** PRE. "AI Act Evaluation Benchmark: An Open, Transparent, and
Reproducible Evaluation Dataset for NLP and RAG Systems", Davvetas et al.,
arXiv:2603.09435 (2026), DOI 10.48550/arXiv.2603.09435. VERIFIED. CORE. Grounds:
risk-level classification, article retrieval, obligation generation, and QA
tasks. Primary reusable evaluation set (OVR-10, M4).

**[REF-16]** PEER. "LLM-assisted Extraction of Regulatory Requirements: A Case
Study on the GDPR" (XTRAREG), Abualhaija et al., IEEE RE 2025, DOI
10.1109/RE63999.2025.00023. VERIFIED. CORE. Grounds: requirement generation
81.8% ACC and 85.7% PRT, legal-reference grounding 68.2% ACC and 50% PRT
(verbatim confirmed). The number the runtime judge must beat; closest sibling
(GDPR).

**[REF-17]** PRE. "Assessing High-Risk AI Systems under the EU AI Act: From
Legal Requirements to Technical Verification", Buscemi et al.,
arXiv:2512.13907 (2025), DOI 10.48550/arXiv.2512.13907. VERIFIED. CORE. Grounds:
maps Article 6 and Annex III obligations to verification activities; closest
requirement-to-evidence sibling.

**[REF-18]** PRE. "Bench-2-CoP: Can We Trust Benchmarking for EU AI Compliance?",
Prandi et al., arXiv:2508.05464 (2025), DOI 10.48550/arXiv.2508.05464. VERIFIED.
SUPPORTING. Grounds: existing compliance benchmarks are thin for systemic-risk
capabilities; caution for OVR-10.

## Extraction feasibility and failure modes

**[REF-26]** PEER. "Legal Requirements Translation from Law", Singhal and Breaux,
IEEE RE 2025, DOI 10.1109/RE63999.2025.00028 (confirmed via DBLP; preprint
arXiv:2507.02846). VERIFIED. CORE. Grounds: references and conditional clauses
show the highest error rates in legal extraction; supports deterministic
cross-reference resolution (OVR-2).

**[REF-27]** PRE. "RegReAct: Self-Correcting Multi-Agent Pipelines for
Structured Regulatory Information Extraction", Ali et al., arXiv:2604.12054
(2026), DOI 10.48550/arXiv.2604.12054. VERIFIED. SUPPORTING. Grounds: structural
hallucination (a single LLM call cannot maintain hierarchy); supports
deterministic Layer 1 and self-correction as the judge.

**[REF-29]** PRE. "Poly-Vector Retrieval: Reference and Content Embeddings for
Legal Documents", de Oliveira Lima, arXiv:2504.10508 (2025), DOI
10.48550/arXiv.2504.10508. VERIFIED. SUPPORTING. Grounds: legal texts referenced
by label or nickname; references as first-class edges and an optional hybrid
retrieval path.

## Evaluation assets and baselines

**[REF-24]** PRE. "Knowledge Graph Representations for LLM-Based Policy
Compliance Reasoning", Baldwin and Ghanavati, arXiv:2604.27713 (2026), DOI
10.48550/arXiv.2604.27713. VERIFIED. CORE. Grounds: LLM-as-judge in evaluation;
an open LLM-discovered ontology can match a formal schema; grounds the judges and
the independent-judge stance.

**[REF-25]** PEER. "AIRO: An Ontology for Representing AI Risk based on the
Proposed EU AI Act and ISO Risk Management Standards", Golpayegani et al.,
Studies on the Semantic Web (IOS Press), 2022, DOI 10.3233/SSW220008. VERIFIED.
CORE. Grounds: high-risk classification and AI-risk representation (OWL); RDF
export alignment target (OVR-8).

## Graph-vs-RAG and store tradeoffs

**[REF-21]** PEER. "Rethinking OWL Expressivity: Semantic Units for FAIR and
Cognitively Interoperable Knowledge Graphs", Vogt, Scientific Data 13, 936
(2026), DOI 10.1038/s41597-026-07588-3 (preprint arXiv:2407.10720). VERIFIED.
SUPPORTING. Grounds: property graphs relate information directly to edges; RDF or
OWL only via reification. Citable grounding for OVR-8.

**[REF-22]** PEER. "Knowledge Graphs", Hogan et al., ACM Computing Surveys
54(4), Article 71, 2021, DOI 10.1145/3447772 (open manifestation
arXiv:2003.02320). VERIFIED. SUPPORTING. Grounds: property-graph vs RDF or OWL
distinction; peer-reviewed anchor for the store choice (OVR-8).

**[REF-23]** PROJ. neosemantics (n10s), Neo4j RDF import and export plugin, Neo4j
Labs. VERIFIED. SUPPORTING. Grounds: the RDF or OWL export bridge in OVR-8.

## Delivery and plumbing

**[REF-30]** PRAC. FLI "EU AI Act Compliance Checker" (rule-based form logic;
high-risk determination; FRIA), Future of Life Institute,
artificialintelligenceact.eu. VERIFIED. SUPPORTING. Grounds: a baseline and a
classification-logic source for classify_ai_system. Not the European Commission.

**[REF-31]** STD. Model Context Protocol specification (revision 2026-07-28;
the spec versions by date and has no semantic version), modelcontextprotocol.io.
VERIFIED (revision confirmed current 2026-09-01). SUPPORTING. Grounds: MCP
security and consent (SEC rules, ACC tools); the core security and trust
principles (user consent, data privacy, tool safety with tool descriptions
treated as untrusted); statelessness (no protocol sessions; cross-call state
only as explicit server-minted handles, which this server does not need);
deterministic tools/list ordering (spec SHOULD). Authorization is OPTIONAL in
the spec and OAuth 2.1 is a SHOULD for HTTP transports; the scoped t4a_ Bearer
keys are a documented deviation (architecture.md Section 8). The served
protocol still negotiates 2025-11-25 pending fastmcp support for 2026-07-28.

**[REF-32]** PROJ. Graphify (Graphify-Labs),
github.com/Graphify-Labs/graphify. VERIFIED. SUPPORTING. Grounds: provenance and
confidence edge-tag pattern donor; deterministic-parse-before-semantic-extract.

**[REF-33]** OFF. Assessment List for Trustworthy AI (ALTAI) for self-assessment,
High-Level Expert Group on AI, European Commission, 2020. VERIFIED. CORE.
Grounds: the ethics layer (Layer 3). Redistribution needs a license check.

## Added literature (2026-07 consolidation)

**[ADD-01]** OFF. Ethics Guidelines for Trustworthy AI, High-Level Expert Group
on AI, European Commission, 2019. VERIFIED. CORE. Grounds: the seven
requirements and four ethical principles; ethics-layer source. Held in
data/snapshots/.

**[ADD-02]** PEER. "Trust in Automation: Designing for Appropriate Reliance",
Lee and See, Human Factors 46(1), 2004, DOI 10.1518/hfes.46.1.50_30392.
VERIFIED. CORE. Grounds: appropriate reliance and calibrated trust, the framing
of the thesis claim.

**[ADD-03]** PEER. "Formalizing Trust in Artificial Intelligence: Prerequisites,
Causes and Goals of Human Trust in AI", Jacovi et al., FAccT 2021, DOI
10.1145/3442188.3445923 (open arXiv:2010.07487). VERIFIED. CORE. Grounds: a
formal account of warranted trust in AI.

**[ADD-04]** PEER. "Trust in Automation: Integrating Empirical Evidence on
Factors That Influence Trust", Hoff and Bashir, Human Factors 57(3), 2015, DOI
10.1177/0018720814547570. VERIFIED. CORE. Grounds: factors shaping trust in
automation.

**[ADD-05]** PEER. "Designing for Responsible Trust in AI Systems: A
Communication Perspective", Liao and Sundar, FAccT 2022, DOI
10.1145/3531146.3533182 (open arXiv:2204.13828). VERIFIED. CORE. Grounds:
trustworthiness cues and responsible trust.

**[ADD-06]** PEER. "Principles alone cannot guarantee ethical AI", Mittelstadt,
Nature Machine Intelligence 1, 2019, DOI 10.1038/s42256-019-0114-4 (open
arXiv:1906.06668). VERIFIED. CORE. Grounds: principles need operationalisation,
the motivation for engineering requirements.

**[ADD-07]** PEER. "From What to How: An Initial Review of Publicly Available AI
Ethics Tools, Methods and Research to Translate Principles into Practices",
Morley et al., Science and Engineering Ethics 26, 2020, DOI
10.1007/s11948-019-00165-5 (open arXiv:1905.06876). VERIFIED. CORE. Grounds:
translating principles into practices.

**[ADD-08]** PEER. "ECCOLA, a Method for Implementing Ethically Aligned AI
Systems", Vakkuri et al., Journal of Systems and Software 182, 2021, DOI
10.1016/j.jss.2021.111067 (open access, CC BY). VERIFIED. CORE. Grounds: a
method for operationalising AI ethics in development.

**[ADD-09]** PEER. "Closing the AI Accountability Gap: Defining an End-to-End
Framework for Internal Algorithmic Auditing", Raji et al., FAccT 2020, DOI
10.1145/3351095.3372873 (open arXiv:2001.00973). VERIFIED. CORE. Grounds:
auditing and accountability framing for evidence and traceability.

**[ADD-10]** PEER. "Towards Regulatory Compliance: Extracting Rights and
Obligations to Align Requirements with Regulations", Breaux et al., IEEE RE 2006.
NEEDS-CHECK (IEEE DOI to confirm). CORE. Grounds: extracting rights and
obligations from regulation, the RE lineage of this work.

**[ADD-11]** PEER. "Analyzing Regulatory Rules for Privacy and Security
Requirements", Breaux et al., IEEE TSE 34(1), 2008, DOI 10.1109/TSE.2007.70746.
VERIFIED. CORE. Grounds: regulatory rules to requirements.

**[ADD-12]** PEER. "GaiusT: Supporting the Extraction of Rights and Obligations
for Regulatory Compliance", Zeni et al., Requirements Engineering 20, 2015, DOI
10.1007/s00766-013-0181-8. VERIFIED. CORE. Grounds: tool-supported obligation
extraction.

**[ADD-13]** PEER. "Automated Extraction of Semantic Legal Metadata using
Natural Language Processing", Sleimi et al., IEEE RE 2018, DOI
10.1109/RE.2018.00022. VERIFIED. CORE. Grounds: semantic legal metadata
extraction.

**[ADD-14]** PEER. "An Analysis of the Requirements Traceability Problem", Gotel
and Finkelstein, IEEE ICRE 1994. VERIFIED. CORE. Grounds: the traceability
problem, foundational to the thesis position.

**[ADD-15]** PEER. "Software Traceability: Trends and Future Directions",
Cleland-Huang et al., FOSE 2014, DOI 10.1145/2593882.2593891. VERIFIED. CORE.
Grounds: modern traceability practice.

**[ADD-16]** PEER. "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena",
Zheng et al., NeurIPS 2023 (arXiv:2306.05685). VERIFIED. CORE. Grounds:
LLM-as-a-judge methodology; the judge design.

**[ADD-17]** PEER. "G-Eval: NLG Evaluation using GPT-4 with Better Human
Alignment", Liu et al., EMNLP 2023, DOI 10.18653/v1/2023.emnlp-main.153.
VERIFIED. SUPPORTING. Grounds: LLM-based evaluation with human alignment.

**[ADD-18]** PEER. "SelfCheckGPT: Zero-Resource Black-Box Hallucination
Detection for Generative LLMs", Manakul et al., EMNLP 2023, DOI
10.18653/v1/2023.emnlp-main.557. VERIFIED. SUPPORTING. Grounds: hallucination
detection; the hallucinated-citation metric.

**[ADD-19]** PEER. "RAGAs: Automated Evaluation of Retrieval Augmented
Generation", Es et al., EACL 2024 Demonstrations, DOI
10.18653/v1/2024.eacl-demo.16. VERIFIED. SUPPORTING. Grounds: RAG evaluation
metrics; grounding and faithfulness measures.

**[ADD-20]** STD. PROV-O: The PROV Ontology, W3C Recommendation, 2013. VERIFIED.
SUPPORTING. Grounds: provenance modelling vocabulary.

**[ADD-21]** STD. Shapes Constraint Language (SHACL), W3C Recommendation, 2017.
VERIFIED. SUPPORTING. Grounds: validation-gate (reject-not-infer) modelling.

**[ADD-22]** OFF. Official EU AI Act Compliance Checker, AI Act Service Desk,
European Commission. VERIFIED. SUPPORTING. Grounds: the official classification
tool as a comparison point.

**[ADD-23]** OFF. EUR-Lex and CELLAR data reuse documentation (API and SPARQL),
Publications Office of the EU. VERIFIED. SUPPORTING. Grounds: authoritative
ingestion and reuse terms (OVR-2).

**[ADD-24]** PEER. "To Be High-Risk, or Not To Be: Semantic Specifications and
Implications of the AI Act's High-Risk AI Applications and Harmonised Standards",
Golpayegani et al., FAccT 2023, DOI 10.1145/3593013.3594050. VERIFIED. CORE.
Grounds: semantic modelling of high-risk classification (OVR-1, DEC-10).

**[ADD-25]** PRE. "GraphCompliance" (knowledge-graph compliance reasoning), Chung
et al., arXiv:2510.26309 (2025), DOI 10.48550/arXiv.2510.26309. VERIFIED. CORE.
Grounds: graph-based compliance reasoning; a recent sibling.

**[ADD-26]** PRE. "RAGulating Compliance", Agarwal et al., arXiv:2508.09893
(2025), also CEUR-WS Vol. 4085. VERIFIED. SUPPORTING. Grounds: retrieval plus
regulation compliance pipeline.

**[ADD-27]** PRE. "PrivComp-KG" (privacy compliance knowledge graph),
arXiv:2404.19744 (2024), also IEEE. NEEDS-CHECK (authors and IEEE venue to
confirm). SUPPORTING. Grounds: privacy compliance KG; a cross-domain sibling.

**[ADD-28]** OFF. Commission guidelines on high-risk AI systems (draft),
European Commission, 2026. VERIFIED. SUPPORTING. Grounds: official high-risk
classification guidance (OVR-1).

## Dropped in the 2026-07 consolidation (do not cite, do not re-add)

These were removed from the register. They are recorded here in plain text (not
as defined IDs) so the decision is auditable and they are not silently
reintroduced.

- REF-06 (was PRAC, CELLAR API developer blog): superseded by ADD-23 (official
  EUR-Lex and CELLAR reuse docs).
- REF-14a (Crawford and Ostrom, "A Grammar of Institutions", APSR 1995, DOI
  10.2307/2082975) and REF-14b (Ostrom, "Understanding Institutional Diversity",
  Princeton University Press, 2005): the Institutional Grammar primaries, dropped
  as out of scope; the deontic strand is retained as REF-14c.
- REF-19 (was PRAC, Quantamix EU AI Act vendor blog): non-citable, replaced by
  running our own baseline.
- REF-20 (was PRAC, Neo4j vs RDF/SHACL developer blog): superseded by the
  peer-reviewed REF-21 and REF-22 for the store choice (OVR-8).
- REF-28 (LexRel, Chinese civil-case legal relation extraction,
  arXiv:2512.12643): out of scope for actor and object canonicalisation; DEC-04
  now grounds on REF-11 and REF-12.

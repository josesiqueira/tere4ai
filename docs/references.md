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
NOT PURSUED 2026-10-08 (Jose): no full text is available through TUNI (Andor); the chapter has 3 citations and passes the bar by peer review (Springer IntelliSys 2022, title as the landing page prints it: "Deontic Sentence Classification Using Tree Kernel Classifiers"); it is cited in no thesis record and stays NOT HELD. If a later chapter wants a deontic classification source, it is cited only after the PDF is obtained.

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
keys are a documented deviation (architecture.md Section 8). The server serves
2026-07-28 and legacy clients (2025-11-25 and earlier) from one process since
fastmcp 4 (tested since 2026-10-02, C3).

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

**[ADD-29]** PEER. "Systematic mapping study on requirements engineering for
regulatory compliance of software systems", Kosenkov, Elahidoost, Gorschek,
Fischbach, Mendez, Unterkalmsteiner, Fucci, Mohanani, Information and Software
Technology 178 (2025) 107622. VERIFIED (read in full 2026-09-01). CORE.
Grounds: the field map (280 studies to 2023-12-31, so pre-LLM); abstractness
of regulations 96/255; tool support gap 28/249 vs methodology 173/249.

**[ADD-30]** PRE. "From Regulation to Requirements: An Automated Requirement
Derivation and Explanation Pipeline", Nair and Anish (TCS), arXiv:2607.04448v1
[cs.SE], 5 Jul 2026, no version of record yet. VERIFIED (read in full
2026-09-02). CORE. Grounds: closest overlap; GPT-5 pipeline deriving
system-agnostic requirements from the full GDPR and EU AI Act clause sets
(F1 0.82/0.78) with a traceability matrix; its outputs never reach a codebase.

**[ADD-31]** PEER. "Addressing Legal Requirements in Requirements Engineering",
Otto and Anton, 15th IEEE RE Conference (RE 2007), pp. 5-14, DOI
10.1109/RE.2007.65. VERIFIED (read in full 2026-09-02; author copy). CORE.
Grounds: the legal-requirements RE survey (38 papers, nine formalisms); "no
final product or working system ever resulted from the research".

**[ADD-32]** PRE. "From Obligation to Specification: A Survey on Validating EU
AI Act Requirements in RE", Lai, Giesselbach, Koch, Allende-Cid,
arXiv:2607.21608v1 [cs.SE], 18 May 2026, no version of record yet. VERIFIED
(read in full 2026-09-02; despite the title it is a 10-interview practitioner
study, not a survey). SUPPORTING. Grounds: practitioner demand side; its
minimum requirement (d) demands explicit uncertainty representation and
conservative recommendations, unimplemented.

**[ADD-33]** PEER. "Regulatory Requirements Compliance in Requirements
Engineering: A Systematic Classification and Analysis", M. Mahmudul Hasan
(NOT Akhigbe; a past error confused them), IJSSOE 6(4), 2016, pp. 22-35
[VERIFY], DOI 10.4018/IJSSOE.2016100102 [VERIFY]. NOT HELD (IGI Global
paywall, no preprint; see thesis refs/paywalled.md); every field [VERIFY]
until the PDF is obtained. SUPPORTING. Grounds: systematic classification of
regulatory-compliance approaches in RE.
DROPPED 2026-10-08 (Jose: a 2016 review of the field's approaches is out of date; "of course it has changed, so this is not good reference"); never obtained, cited nowhere in the thesis records; the current survey of the same ground is ADD-29 (Kosenkov et al., IST 2025). Do not cite, do not acquire.

**[ADD-34]** PEER. "Assessing the Accuracy of Legal Implementation Readiness
Decisions", Massey, Smith, Otto, Anton, IEEE RE 2011, pp. 207-216, DOI
10.1109/RE.2011.6051661 [VERIFY: DOI not printed in the author copy].
VERIFIED (read in full 2026-09-02). CORE. Grounds: humans measured at the
readiness judgment (32 students Fleiss kappa 0.0792, consensus specificity
0.20 vs experts); motivates tool support and defines "legally implementation
ready".

**[ADD-35]** PRE. "Learning When Not to Decide: A Framework for Overcoming
Factual Presumptuousness in AI Adjudication", Afane, Robitschek, Ouyang, Ho,
arXiv:2604.19895, 2026; forthcoming at ICAIL 2026 [VERIFY: ACM DOI and pages
once published]. VERIFIED. CORE. Grounds: direct threat to the
calibrated-abstention claim; an evaluated legal system (SPEC) that withholds
decisions and names missing operative facts; cede or distinguish.

**[ADD-36]** PRE. "LegalBench-RAG: A Benchmark for Retrieval-Augmented
Generation in the Legal Domain", Pipitone and Houir Alami, arXiv:2408.10343,
2024. VERIFIED. CORE. Grounds: exact character-span attribution as the
retrieval unit in legal RAG; bounds the span-provenance story.

**[ADD-37]** PEER. "A Machine Learning Approach for Tracing Regulatory Codes
to Product Specific Requirements", Cleland-Huang, Czauderna, Gibiec,
Emenecker, ICSE 2010, pp. 155-164, DOI 10.1145/1806799.1806825. VERIFIED
(Crossref; full text NOT HELD, ACM paywall, quote nothing until the PDF is in
hand). CORE. Grounds: the classic evaluated regulation-to-requirement
trace-recovery work the last-mile claim positions against.
Reading fixed 2026-10-08 (Jose, on downloading it): a motivating source for the problem (tracing regulatory codes to requirements is an established, evaluated problem since 2010), never a method source ("since it is from 2010 it cannot be used like 'so we used their methods' ... because today in 2026 they are different, but im including"). Jose supplies the version of record through TUNI.
VoR held since 2026-10-08 (ADD-37_RegulatoryCodesTracing.pdf, supplied by Jose through TUNI; the IEEE Xplore manifestation of the ACM/IEEE ICSE 2010 proceedings paper, printed pages 155 to 164, no DOI printed); quote from it (refs/notes/ADD-37.md).

**[ADD-38]** PRE. "R2Code: A Self-Reflective LLM Framework for
Requirements-to-Code Traceability", Wang, Keung, Ma, Mao, Chen, Li,
arXiv:2604.22432, 2026; accepted to IEEE COMPSAC 2026 [VERIFY: final IEEE DOI
once published]. VERIFIED. CORE. Grounds: generic requirement-to-code tracing
is occupied; the last-mile claim cedes it and keeps the legal-origin chain.

**[ADD-39]** PEER. "From Law to Gherkin: A Human-Centred Quasi-Experiment on
the Quality of LLM-Generated Behavioural Specifications from Food-Safety
Regulations", Hassani, Sabetzadeh, Amyot, Information and Software Technology
195 (2026) 108122, DOI 10.1016/j.infsof.2026.108122 (open access). VERIFIED.
CORE. Grounds: closest evaluated regulation-to-specification endpoint short
of code; bounds the last-mile claim from above.

**[ADD-40]** PEER. "Classifier or Prompt: A Case Study on Legal Requirements
Traceability", Etezadi, Abualhaija, Arora, Briand, Empirical Software
Engineering 31(4):85, 2026, DOI 10.1007/s10664-026-10827-1 (VoR paywalled;
arXiv:2502.04916 held as preprint; quote only from the VoR once obtained).
VERIFIED (Crossref). CORE. Grounds: strongest recent empirical
legal-requirements trace-recovery comparison in the LLM era.
VoR held since 2026-10-08 (ADD-40_ClassifierOrPrompt.pdf, supplied by Jose through TUNI; Springer version of record, 47 pages, DOI printed on the first page, published online 2 March 2026); quote from it (refs/notes/ADD-40.md). The ADD-40_ClassifierOrPrompt_PREPRINT.pdf file stays as history and is never quoted.

**[ADD-41]** PEER. "Identification and Visual Representation of Explicit Legal
Definitions, Their Relations and Implicit Actors in Regulatory Documents",
Sai, Rossi, Damaratskaya, Winter, Rinderle-Ma, Computer Law and Security
Review 58 (2025) 106174, DOI 10.1016/j.clsr.2025.106174 (open access).
VERIFIED. CORE. Grounds: closest published basis for actor-aware scoping;
bears on regulator-bound filtering and the actor-resolution audit.

**[ADD-42]** PEER. "Compliance-as-Code for AI-Driven Identity Systems:
Clause-to-Control Traceability and Machine-Readable Evidence", Nweke and Yeng,
IEEE Access 14 (2026) 28258-28281, DOI 10.1109/ACCESS.2026.3665991 (open
access, CC BY 4.0). VERIFIED. CORE. Grounds: clause-to-control-to-evidence
prior art; its endpoint is controls and evidence, not source-code locations.

**[ADD-43]** PEER. "An Empirical Study on LLM-based Classification of
Requirements-related Provisions in Food-safety Regulations", Hassani,
Sabetzadeh, Amyot, Empirical Software Engineering 30(3):72, 2025, DOI
10.1007/s10664-025-10619-z (VoR paywalled; arXiv:2501.14683 held as preprint;
quote only from the VoR once obtained). VERIFIED (DBLP, Crossref). CORE.
Grounds: provision classification by requirements-related concepts, domain
classes rather than an engineering-response taxonomy.

**[ADD-44]** PRE. "Executable Governance for AI: Translating Policies into
Rules Using LLMs", Datla, Vurity, Dash, Ahmad, Adnan, Rafi, arXiv:2512.04408,
2025; accepted to the AAAI-26 AI Governance Workshop [VERIFY: proceedings
citation once available]. VERIFIED. SUPPORTING. Grounds: LLM extraction
coupled with deterministic checks; adjacent to the judge-gated
extraction-audit claim.

**[ADD-45]** PEER. "From Policy to Pipeline: A Governance Framework for AI
Development and Operations Pipelines", Butt, Iqbal, Arshad, IEEE Access 14
(2026) 1373-1397, DOI 10.1109/ACCESS.2025.3647479 (open access, CC BY 4.0;
the 2025 DOI prefix against volume 14 is explained on page 1: published 23
Dec 2025). VERIFIED. CORE. Grounds: GEAP's signed, content-addressed
governance artifacts; bears on the provenance and evidence story. Note: the
triage suspected this citation was fabricated; direct verification 2026-09-02
found it real.

**[ADD-46]** PEER. *Experimentation in Software Engineering*, Wohlin,
Runeson, Höst, Ohlsson, Regnell, Wesslén, Springer, 2012, ISBN
978-3-642-29043-5, DOI 10.1007/978-3-642-29044-2 (book; 3145 citations on
Crossref, 2026-09-26). VERIFIED. CORE. Grounds: the research-method words for
a judge run: "pilot study" and "main run" as a pair (pp. 177 and 195), "trial
run" as a pilot of a whole experiment with people (p. 116), and a study
protocol kept under version control (p. 60).

**[ADD-47]** STD. ACM SIGSOFT Empirical Standards, Registered Reports
supplement, Ralph et al., github.com/acmsigsoft/EmpiricalStandards,
docs/supplements/RegisteredReports.md, commit 554118c (2026-09-17). Community
standard of ACM SIGSOFT, not a formal standards body. VERIFIED. CORE.
Grounds: "study plan" for the record fixed before a study runs, "execute the
plan" for the run, and a pilot study as a source of preliminary data.

**[ADD-48]** STD. ACM SIGSOFT Empirical Standards, Experiments (with Human
Participants), Ralph et al., github.com/acmsigsoft/EmpiricalStandards,
docs/standards/Experiments.md, commit 554118c (2026-09-17). Community
standard of ACM SIGSOFT, not a formal standards body. VERIFIED. SUPPORTING.
Grounds: "pilot studies" for small preliminary studies (footnote 5).

**[ADD-49]** PEER. "Reporting Experiments in Software Engineering",
Jedlitschka, Ciolkowski, Pfahl, in Shull, Singer, Sjøberg (eds.), *Guide to
Advanced Empirical Software Engineering*, Springer, 2008, pp. 201-228, DOI
10.1007/978-1-84800-044-5_8 (book chapter; 206 citations on Crossref,
2026-09-26). Quote only the published chapter: the authors' preliminary
version has different wording. VERIFIED. CORE. Grounds: "the plan or
protocol that is used to perform the experiment" (p. 214) and reporting the
run against the plan (Section 3.8, p. 220).

**[ADD-50]** PEER. "Personal Opinion Surveys", Kitchenham, Pfleeger, in
Shull, Singer, Sjøberg (eds.), *Guide to Advanced Empirical Software
Engineering*, Springer, 2008, pp. 63-92, DOI 10.1007/978-1-84800-044-5_3
(book chapter; 339 citations on Crossref, 2026-09-26). VERIFIED. CORE.
Grounds: a pilot uses the same procedures on a smaller sample to find
problems with how the study will run (p. 78), and is paired with "the main
survey" (p. 89).

**[ADD-51]** PEER. "Guidelines for conducting and reporting case study
research in software engineering", Runeson, Höst, Empirical Software
Engineering 14(2):131-164, 2009, DOI 10.1007/s10664-008-9102-8 (open
access; 2896 citations on Crossref, 2026-09-26). VERIFIED. SUPPORTING.
Grounds: a study protocol kept under version control (p. 141), the original
of the sentence ADD-46 reuses.

**[ADD-52]** PRE. "Guidelines for Empirical Studies in Software Engineering
involving Large Language Models", Baltes, Angermeir, Arora, et al. (22
authors), arXiv:2508.15503, held as version 5 (2026-05-10); the arXiv record
says accepted in Empirical Software Engineering [VERIFY: journal DOI once
published; none found 2026-09-26]. VERIFIED. SUPPORTING. Grounds: a pilot
study to estimate the variability of repeated LLM runs before the study
proper (v5 p. 37).

**[ADD-53]** PEER. "Trust or Escalate: LLM Judges with Provable Guarantees
for Human Agreement", Jung, Brahman, Choi, ICLR 2025 (official proceedings
PDF). VERIFIED. SUPPORTING. Grounds: in LLM-as-a-judge work a "calibration
set" is a small set of human preferences on which a judge's threshold is
chosen (pp. 1 to 3), so "calibration" is not used as the name of a paid run.

**[ADD-54]** STD. ISO/IEC/IEEE 29148:2018, "Systems and software engineering,
Life cycle processes, Requirements engineering", DOI
10.1109/IEEESTD.2018.8559686. VERIFIED 2026-10-01, read in TUNI's licensed
copy. CORE. Grounds: the requirement type of B65 (functional, quality,
process): clause 5.2.8.3 lists six examples of the type attribute,
Functional/Performance, Interface, Process Requirements (including
compliance with national, state or local laws), Quality (Non-Functional)
Requirements, Usability/Quality-in-Use Requirements and Human Factors
Requirements (printed pp. 15 to 16), of which the project uses three
(DEC-19, which does not read the laws sentence as making every legal duty a
process requirement), and clause 3.1.7 defines a constraint as reaching the
process used to develop a system (p. 3).

**[ADD-55]** STD. ISO/IEC/IEEE 24765:2017, "Systems and software
engineering, Vocabulary", DOI 10.1109/IEEESTD.2017.8016712. VERIFIED
2026-10-01, read in TUNI's licensed copy. CORE. Grounds: the definitions of
"functional requirement" (3.1704, p. 195) and "quality requirement" (3.3287,
definition 1, p. 364). Supersedes the mention of 24765 marked "UNVERIFIED by
Claude, paywalled" in thesis/sdd/2026-09-29-B100-board/brief.md.

**[ADD-56]** PEER. "On Non-Functional Requirements", Glinz, 15th IEEE
International Requirements Engineering Conference (RE 2007), pp. 21-26, DOI
10.1109/RE.2007.45 (466 citations on Crossref, 2026-10-01). VERIFIED
2026-10-01, read in TUNI's licensed copy. CORE. Grounds: process requirements
are peers of functional and quality requirements, "distinguished at the root
level and not in a sub-category such as non-functional requirements"
(section 4.2, p. 24).

**[ADD-57]** STD. Guide to the Software Engineering Body of Knowledge
(SWEBOK Guide) V4.0a, IEEE Computer Society, 2024. IEEE Computer Society
guide; its V3.0 was adopted as ISO/IEC TR 19759:2015, V4.0 is not an ISO
document. VERIFIED 2026-10-01. SUPPORTING. Grounds: process (project)
requirements at the root beside product requirements: Software Requirements
KA 1.3 (p. 1-3) and Figure 1.2 (p. 1-4).

**[ADD-58]** OFF. European Commission, Commission Implementing Decision
C(2025) 3871 final, Annexes 1 to 2 (standardisation request on artificial
intelligence), 23.6.2025. VERIFIED 2026-10-01. SUPPORTING. Grounds: the AI
Act's standardisation request separates "requirements applicable to
high-risk AI systems" from "process requirements" (Annex II, section 1, p. 4).

**[ADD-59]** PEER. "Inter-Coder Agreement for Computational Linguistics",
Artstein, Poesio, Computational Linguistics 34(4):555-596, 2008, DOI
10.1162/coli.07-034-R2 (960 citations on Crossref, 2026-10-02). VERIFIED
2026-10-02. CORE. Grounds: observed agreement "on its own it does not yield
values that can be compared across studies" (p. 558), so the annotation
design's "agreed" is labelled raw agreement and never read against kappa
thresholds (spec G D-G40); unit identification as its own reliability
question (p. 582).

**[ADD-60]** PEER. "Inter-annotator Agreement for ERE annotation", Kulick,
Bies, Mott, Proceedings of the 2nd Workshop on EVENTS, ACL 2014, pp. 21-25,
DOI 10.3115/v1/W14-2904 (workshop paper describing a design, no results).
VERIFIED 2026-10-02. SUPPORTING. Grounds: a mapping between mentions "as the
basis for all further evaluation" (p. 22) and an all-components exact match
beside partial mismatch categories (p. 24), the pattern of D-G40.

**[ADD-61]** PEER. "The Unified and Holistic Method Gamma (γ) for
Inter-Annotator Agreement Measure and Alignment", Mathet, Widlöcher,
Métivier, Computational Linguistics 41(3):437-479, 2015, DOI
10.1162/COLI_a_00227. VERIFIED 2026-10-02. CORE. Grounds: the objection that
"measuring and aligning cannot constitute two successive stages" (p. 448,
p. 473), named in D-G40 with its scope (units on a continuum, p. 473) and
kept against by Jose's choice of 2026-09-28.

**[ADD-62]** PEER. "An automated framework for the extraction of semantic
legal metadata from legal texts", Sleimi, Sannier, Sabetzadeh, Briand, Ceci,
Dann, Empirical Software Engineering 26(3), article 43, 2021, DOI
10.1007/s10664-020-09933-5 (the journal extension of ADD-13). Cite the
published version only, never arXiv 2001.11245. VERIFIED 2026-10-02. CORE.
Grounds: inter-annotator agreement counted only "when both annotators
assigned the same metadata type to the same span of text" (p. 16), and a
second annotator on 10% of the statements (p. 30).

**[ADD-63]** PEER. "Learning from Disagreement: A Survey", Uma, Fornaciari,
Hovy, Paun, Plank, Poesio, Journal of Artificial Intelligence Research
72:1385-1470, 2021, DOI 10.1613/jair.1.12752 (open access; 102 citations on
Crossref, 2026-10-02). VERIFIED 2026-10-02. CORE. Grounds: training directly
with soft labels beat aggregated or gold labels on substantial datasets with
many high-quality judgments (p. 1385), the reason the full distribution of
Layer 3 verdicts is kept beside the adjudicated reference (spec G Section 6,
L3-3).

**[ADD-64]** PEER. "Anchoring and Agreement in Syntactic Annotations",
Berzak, Huang, Barbu, Korhonen, Katz, Proceedings of EMNLP 2016, pp.
2215-2224, DOI 10.18653/v1/D16-1239. VERIFIED 2026-10-02. CORE. Grounds: a
"clear anchoring effect" when annotators edit parser output, with
"overestimation of parsing performance" (p. 2215), the reason for the blind
subset (spec G Section 6 step 3, L3-4).

**[ADD-65]** PEER. "Influence of Pre-Annotation on POS-Tagged Corpus
Development", Fort, Sagot, Proceedings of the Fourth Linguistic Annotation
Workshop (LAW IV), ACL 2010, pp. 56-63, aclanthology.org/W10-1807 (no DOI).
VERIFIED 2026-10-02. CORE. Grounds: pre-annotation gives "a gain in quality"
with "biases that should be identified and notified to the annotators"
(p. 62), and contingency tables between annotation and reference (p. 61);
the blind subset and the correction-rate table of spec G Section 6.

**[ADD-66]** PEER. "TextEE: Benchmark, Reevaluation, Reflections, and Future
Challenges in Event Extraction", Huang, Hsu, Parekh, Xie, et al., Findings of
the Association for Computational Linguistics: ACL 2024, pp. 12804-12825, DOI
10.18653/v1/2024.findings-acl.760. Cite the published version, not arXiv
2311.09562. VERIFIED 2026-10-02. SUPPORTING. Grounds: trigger and argument
identification beside classification, each a strict score (p. 12807,
p. 12808), practice evidence for D-G40's strict figure beside per-slot
figures.

**[ADD-67]** STD. ACM SIGSOFT Empirical Standards, Inter-Rater Reliability
and Agreement supplement, Ralph et al., github.com/acmsigsoft/EmpiricalStandards,
docs/supplements/InterRaterReliabilityAndAgreement.md, commit 554118c
(2026-09-17). Community standard of ACM SIGSOFT, not a formal standards
body. VERIFIED 2026-10-02. CORE. Grounds: "IRR/IRA broken down by property
or wave of analysis" as a desirable attribute, and "Calculating multiple
IRR/IRA measures and reporting only the most favourable (p-hacking)" as an
antipattern (D-G40).

**[ADD-68]** STD. ACM SIGSOFT Empirical Standards, Questionnaire Surveys,
Ralph et al., github.com/acmsigsoft/EmpiricalStandards,
docs/standards/QuestionnaireSurveys.md, commit 554118c (2026-09-17).
Community standard of ACM SIGSOFT, not a formal standards body. VERIFIED
2026-10-02. SUPPORTING. Grounds: a survey "describes how responses were
managed/monitored, including contingency actions for non-responses and
drop-outs" and "analyzes response rates" (essential attributes), the
participation counts of spec G D-G53.

**[ADD-69]** STD. The American Association for Public Opinion Research,
"Standard Definitions: Final Dispositions of Case Codes and Outcome Rates for
Surveys", 10th edition, AAPOR, 2023,
aapor.org/wp-content/uploads/2023/05/Standards-Definitions-10th-edition.pdf.
Professional association standard, not a formal standards body. VERIFIED
2026-10-02. SUPPORTING. Grounds: the vocabulary only (spec G D-G53): a
partial interview (code 1.2) and a break-off (code 2.12) are both a
respondent who started and did not finish (p. 10); the project's "abandoned"
covers the two together.

**[ADD-70]** PROJ. nervaluate, MantisAI, github.com/MantisAI/nervaluate,
README.md at commit cde2d1b (2026-03-12). Software package, not a paper.
VERIFIED 2026-10-02. SUPPORTING. Grounds: the strict, exact, partial and type
evaluation schemes stated in its README, practice evidence that a strict
figure is reported beside lenient ones (D-G40); never sole grounding.

**[ADD-71]** PEER. "Deciphering disagreement in the annotation of EU
legislation", van Dijck, Aguilera, Chakravarthy, Artificial Intelligence and
Law 34:191-226, 2026 (published online 2024-11-12), DOI
10.1007/s10506-024-09423-9 (open access, CC BY 4.0). VERIFIED 2026-10-02.
SUPPORTING. Grounds: on EU legislative provisions, agreement levels "vary based
on the stage of measurement (before/after revisions), the nature of the task,
the method of assessment, and the annotator combination", and annotators
"identified multiple valid interpretations" (p. 191); spec G Section 6
reports agreement per task and stage and keeps the spread of verdicts.

**[ADD-72]** PEER. "Factorials Experiments, Covering Arrays, and
Combinatorial Testing", Kacker, Kuhn, Lei, Simos, Mathematics in Computer
Science 15(4):715-739, 2021, DOI 10.1007/s11786-021-00502-7 (6 citations on
Crossref, 11 on Semantic Scholar, 2026-10-02; passes the bar by peer
review). Held as Springer's typeset file posted on NIST's site (issue pages
not printed; pages cited by PDF page). VERIFIED 2026-10-03. CORE. Grounds:
a factor's effect is measured "while the values of the other factors are
fixed", and an interaction is "the difference in the conditional main
effects" (Section 2, PDF p. 3): each step of the ablation ladder is a
conditional effect (thesis sdd/2026-10-03-B104-ablation-design, R1), and the
sixth condition, the runtime judge without the build judge, reports each
judge's contribution on its own (B104 decision 4).

**[ADD-73]** PEER. "The Hitchhiker's Guide to Testing Statistical
Significance in Natural Language Processing", Dror, Baumer, Shlomov,
Reichart, Proceedings of the 56th Annual Meeting of the ACL (Volume 1),
2018, pp. 1383-1392, DOI 10.18653/v1/P18-1128 (557 citations on Semantic
Scholar, 173 on Crossref, 2026-10-02). VERIFIED 2026-10-03. CORE. Grounds:
McNemar's test is "designed for paired nominal observations (binary
labels)" (p. 1387), and testing several hypotheses raises "the probability
of making one or more false claims" (p. 1389): the ablation's analysis uses
McNemar on one paired set of correctness outcomes and a predeclared family
of primary contrasts with a multiplicity correction (B104 R7).

**[ADD-74]** PEER. "Approximate Statistical Tests for Comparing Supervised
Classification Learning Algorithms", Dietterich, Neural Computation
10(7):1895-1923, 1998, DOI 10.1162/089976698300017197 (4180 citations on
Semantic Scholar, 2907 on Crossref, 2026-10-02). VoR paywalled; the author
copy (manuscript of 1997-12-30) is held as _PREPRINT; quote only from the
VoR once obtained, its pages replacing the author copy's. VERIFIED
2026-10-03 (metadata; quotes read in the author copy). SUPPORTING. Grounds:
McNemar's test concerns only "whether an example is classified correctly or
incorrectly", whatever the number of classes (Section 2, author copy p. 6),
and "does not directly measure variability due to the choice of the
training set or the internal randomness" (Section 3.1, author copy p. 7):
the ablation's result is worded for the one frozen build (B104 R2, R7).
VoR held since 2026-10-08 (ADD-74_ApproximateStatisticalTests.pdf, supplied by Jose through TUNI; the MIT Press version of record, 29 pages, its first page printing "Neural Computation 10, 1895-1923 (1998)", neither the issue number nor the DOI printed; an image-only scan with no text layer, so the quotes were re-found by eye on the page images); the quotes are re-anchored with the VoR's pages (refs/notes/ADD-74.md): Section 2 is p. 1901, where the VoR reads "none of the results in this article depend on this assumption, since our only concern will be whether an example is classified correctly or incorrectly" (the author copy read "in this paper"), and Section 3.1 is p. 1903; these replace the author copy's pages 6 and 7 above. The ADD-74_ApproximateStatisticalTests_PREPRINT.pdf author copy stays as history and as the gate's searchable text surrogate only, never quoted.

**[ADD-75]** PEER. "LegalBench: A Collaboratively Built Benchmark for
Measuring Legal Reasoning in Large Language Models", Guha, Nyarko, Ho, Ré,
et al. (40 authors), Advances in Neural Information Processing Systems 36
(NeurIPS 2023), Datasets and Benchmarks Track, pp. 44123-44279, DOI
10.52202/075280-1915 (527 citations on Semantic Scholar, 2026-10-02; 83 on
Crossref, 2026-10-03). VERIFIED 2026-10-03. SUPPORTING. Grounds: a legal
benchmark built where "domain experts take an active and participatory role
in the crafting of evaluation tasks" (Section 1, p. 2): precedent for domain
experts building a legal answer key, here the ablation's hand-made test set,
labelled by two people on every case (B104 decision 2); not a rule on who or
how many.

**[ADD-76]** STD. ACM SIGSOFT Empirical Standards, Benchmarking (of Software
Systems), Ralph et al., github.com/acmsigsoft/EmpiricalStandards,
docs/standards/Benchmarking.md, commit 554118c (2026-09-17). Community
standard of ACM SIGSOFT, not a formal standards body. VERIFIED 2026-10-03.
CORE. Grounds: a benchmark study "discusses the construct validity of the
benchmark" (line 40), "Tailoring the benchmark for a specific method,
technique or tool, which is evaluated with the benchmark" is an antipattern
(line 80), and stability is assessed with "sufficient experiment
repetitions" (line 36): the published REF-15 benchmark is reported as
agreement with its own labels, its 88 disagreements are reported and not
relabelled, and the repetitions are fixed by a pilot (B104 decisions 1 and
3, R5). The closer fit for an automated tool evaluation than ADD-48, whose
scope is experiments with human participants.

**[ADD-77]** PEER. "Analyzing Dataset Annotation Quality Management in the
Wild", Klie, Eckart de Castilho, Gurevych, Computational Linguistics
50(3):817-866, 2024, DOI 10.1162/coli_a_00516 (open access; 99 citations on
Semantic Scholar, 41 on Crossref, 2026-10-03; passes the bar by peer
review). VERIFIED 2026-10-03. CORE. Grounds: the authors' own annotation was
"only annotated by a single author but inspected several times to guarantee
correctness and consistency" (Section 4.4, p. 838), the precedent for the
staffing design with no helpers (thesis sdd/2026-10-01-B107-resourcing,
decision brief revision 3), a literature annotation, not a legal one; and
"at least ≈ 500 instances" for plus or minus 0.05 at an agreement of 0.8,
with no confidence interval for agreement found in the papers analysed
(Section 5.9, p. 848): the reliability set of 100 is a resource-limited
audit reported with its interval.

**[ADD-78]** PEER. "Question Answering for Privacy Policies: Combining
Computational and Legal Perspectives" (PrivacyQA), Ravichander, Black,
Wilson, Norton, Sadeh, Proceedings of EMNLP-IJCNLP 2019, pp. 4947-4958, DOI
10.18653/v1/D19-1500 (Crossref gives pp. 4946-4957, off by one; 166
citations on Semantic Scholar, 65 on Crossref, 2026-10-03). VERIFIED
2026-10-03. SUPPORTING. Grounds: "seven experts with legal training"
answer questions that crowdworkers wrote (Section 3.2, p. 4950), "every
question in the test set is answered by at least two additional experts"
(Section 3.3, p. 4950), and the question writers were not shown the
policies "to avoid inadvertent biases" (Section 3.1, p. 4949): precedent
for separating who writes the hand-made test cases from who answers them
(B107 decision brief revision 3, two and three helpers); an adaptation.

**[ADD-79]** PEER. "Interrater Disagreement Resolution: A Systematic
Procedure to Reach Consensus in Annotation Tasks", Oortwijn, Ossenkoppele,
Betti, Proceedings of the Workshop on Human Evaluation of NLP Systems
(HumEval), 2021, pp. 131-141, aclanthology.org/2021.humeval-1.15 (no DOI;
25 citations on Semantic Scholar, 2026-10-03; peer-reviewed workshop).
VERIFIED 2026-10-03. CORE. Grounds: consensus "should be striven for,
through a systematic procedure for disagreement resolution" (abstract,
p. 131), with "explicit decisions from raters after deliberation" that make
"the conditions of dataset creation clear" (Section 2, p. 133), and a
pre-appointed person or "majority rule" for what stays unresolved
(Section 4.2, p. 136): the adjudication column of the B107 decision brief
revision 3, the initial labels kept and each adjudicated decision recorded
with its reason.

**[ADD-80]** PEER. "Don't Blame the Annotator: Bias Already Starts in the
Annotation Instructions", Parmar, Mishra, Geva, Baral, Proceedings of EACL
2023, pp. 1779-1789, DOI 10.18653/v1/2023.eacl-main.130 (76 citations on
Semantic Scholar, 21 on Crossref, 2026-10-03). VERIFIED 2026-10-03.
SUPPORTING. Grounds: "instruction bias widely exists in NLU benchmarks,
often leading to an overestimation of model performance" (Section 1,
p. 1780); for T5-base on QUOREF, F1 86.7 on the test questions that follow
the instruction patterns against 73.1 on those that do not, a 13.6 point
gap (Table 4, p. 1782, read from the rendered page; three random seeds):
a measured nearby effect in the B107 decision brief's paragraph on the
builder's bias, not a measure of a tool builder's bias.

**[ADD-81]** PEER. "Preregistering NLP research", van Miltenburg, van der
Lee, Krahmer, Proceedings of NAACL-HLT 2021, pp. 613-623, DOI
10.18653/v1/2021.naacl-main.51 (36 citations on Semantic Scholar, 9 on
Crossref, 2026-10-03). VERIFIED 2026-10-03. SUPPORTING. Grounds:
preregistration sites "provide a time stamp; evidence that you indeed made
all the relevant decisions before carrying out the study" (Section 2,
p. 614): the B107 decision brief's mitigation of preregistering the plan,
the staffing branches and the analysis; method support, not a measured
reduction of the builder's bias.

**[ADD-82]** PEER. "Adjudicating LLMs as PropBank Annotators" (title as
printed on p. 112; the Anthology metadata reads "Adjudicators"), Bonn,
Tayyar Madabushi, Hwang, Bonial, Proceedings of the Fifth International
Workshop on Designing Meaning Representations (DMR 2024) at LREC-COLING
2024, pp. 112-123, aclanthology.org/2024.dmr-1.12 (no DOI; 0 citations on
OpenAlex, 2026-10-03; peer-reviewed workshop). VERIFIED 2026-10-03.
SUPPORTING. Grounds: the paper tests models as annotators, not as
adjudicators: it evaluates "the ability of large language models (LLMs) to
provide PropBank semantic role label annotations" (abstract, p. 112), with
"a best result of 48.6% numbered-arg matches overall" on 35 sentences
(pp. 115 and 118) against "the reported PropBank human average of 88.3%"
(p. 113). The B107 decision brief cites it only for this; the rule that a
model never decides a reference label rests on the brief's reasoning and on
ADD-16, not on this paper.
ADD-16, not on this paper.

**[ADD-83]** OFF. Council Regulation (EU) No 216/2013 of 7 March 2013 on the
electronic publication of the Official Journal of the European Union, OJ L 69,
13.3.2013, pp. 1 to 3. CELEX 32013R0216, ELI
http://data.europa.eu/eli/reg/2013/216/oj (the English PDF/A of the Official
Journal, from CELLAR). VERIFIED 2026-10-04. SUPPORTING. Grounds: only the
electronic edition of the Official Journal is authentic, so the consolidated
text of 27.7.2026, which is not an Official Journal publication, is not the
legal text and every Layer 1 unit is checked against the Official Journal
wording (B132, spec G D-G68, architecture.md DEC-23): "Without prejudice to
Article 3, only the Official Journal published in electronic form (hereinafter
'the electronic edition of the Official Journal') shall be authentic and shall
produce legal effects." (Article 1(2), printed page L 69/2).

**[ADD-84]** PEER. "LLM Evaluators Recognize and Favor Their Own
Generations", Panickssery, Bowman, Feng, Advances in Neural Information
Processing Systems 37 (NeurIPS 2024); the camera-ready PDF carries the
NeurIPS 2024 footer and no DOI (passes the bar by peer review).
NEEDS-CHECK 2026-10-08: the proceedings identifier (OpenReview id or
proceedings DOI) is to be confirmed before the thesis cites it. CORE.
Grounds: DEC-07's cross-family rule (OpenAI generator, independent
non-OpenAI judge) and spec F's judge selection: "By fine-tuning LLMs, we
discover a linear correlation between self-recognition capability and the
strength of self-preference bias; using controlled experiments, we show
that the causal explanation resists straightforward confounders" (abstract,
p. 1), and the authors' reading for model-judged benchmarks, "a model's
rating can be inflated simply because it is similar to the evaluator model"
(Section 5.1, p. 8); spec F H2 tests this on the project's data.

**[ADD-85]** PEER. "Justice or Prejudice? Quantifying Biases in
LLM-as-a-Judge", Ye, Wang, Huang, Chen, Zhang, Moniz, Gao, Geyer, Huang,
Chen, Chawla, Zhang, The Thirteenth International Conference on Learning
Representations (ICLR 2025), proceedings PDF ("Published as a conference
paper at ICLR 2025"); ICLR issues no DOI; also arXiv 2410.02736 (passes the
bar by peer review). NEEDS-CHECK 2026-10-08: the OpenReview identifier is
to be confirmed; venue confirmed from the PDF. CORE. Grounds: the bias
taxonomy ("we identify 12 key potential biases", abstract, p. 1); the
capability-effect motivation of spec F H1, "weaker LLMs may exhibit greater
randomness in their judgments, which can undermine the reliability of
judging results" (Section 3, p. 7); and DEC-07, "a significant
self-enhancement bias among LLMs ... the importance of using separate
models for answer generation and evaluation" (Section 4.2, p. 9), with the
warning to "avoid assuming that the most advanced model will always be the
most reliable" (Section 4.2, p. 8), the reason spec F D-F1 selects the
judge by calibration.

**[ADD-86]** PEER. "A survey on LLM-as-a-judge", Gu, Jiang, Shi, Tan, Zhai,
Xu, Li, Shen, Ma, Liu, Wang, Zhang, Lin, Zhang, Ni, Gao, Wang, Guo, The
Innovation 7(6):101253, 2026 (published online 2026-01-09), DOI
10.1016/j.xinn.2025.101253 (open access, CC BY-NC-ND). VERIFIED
2026-10-08 (DOI and venue from the PDF). CORE. Grounds: the
calibrate-against-humans framing of spec F: "agreement with human judgments
... serves as the validation mechanism, quantifying whether LLM evaluations
align with expert annotations through metrics such as Cohen's κ, Spearman
correlation, and percentage agreement" (Results and Discussion, p. 14), and
"the best way to evaluate LLMs is human judgment" (Materials and Methods,
p. 7); and the coverage evidence behind the "to our knowledge" gap claim
(spec F Section 10): its legal-domain coverage lists specialised evaluators
and legal-reasoning benchmarks (Applications, "Law", pp. 21 and 22), no
calibration of a judge against domain specialists on requirements extracted
from a regulation.

**[ADD-87]** PEER. "LLM-as-a-Judge for Software Engineering: Literature
Review, Vision, and the Road Ahead", He, Shi, Zhuo, Treude, Sun, Du, Xing,
Lo, ACM Transactions on Software Engineering and Methodology 35(9), Article
266, September 2026, 30 pages, DOI 10.1145/3797276 (CC BY 4.0). VERIFIED
2026-10-08 (DOI and venue from the PDF). SUPPORTING. Grounds: the
related-work shelf and gap framing of spec F Section 10 from the software
engineering side: "LLM-as-a-Judge research in the SE community is still in
its early stages" (abstract, p. 266:1); the survey "covers four areas:
requirements engineering, coding assistance, software maintenance, and
quality assurance" (Section 4, p. 266:6), where the requirements
engineering studies judge requirements documents, user stories and system
specifications (Table 2, p. 266:6), a different task from grading
requirements extracted from a law against domain specialists.

**[ADD-88]** PEER. "A Coefficient of Agreement for Nominal Scales", Cohen,
Educational and Psychological Measurement 20(1):37-46, 1960, DOI
10.1177/001316446002000104 (SAGE version of record). VERIFIED 2026-10-08
(DOI and venue from the PDF's cover sheet). CORE. Grounds: the kappa
statistic for the categorical HLEG campaign (spec F D-F10's agreement
measures; ADD-86 names it among the validation metrics): "po = the
proportion of units in which the judges agreed", pc the proportion expected
by chance (p. 39), and kappa "is simply the proportion of chance-expected
disagreements which do not occur, or alternatively, it is the proportion of
agreement after chance agreement is removed from consideration" (p. 40),
with the upper limit 1 at perfect agreement (p. 41). The text layer is an
OCR; the Greek kappa reads "x" or "K" in the sidecar.

**[ADD-89]** PEER. "The Earth Mover's Distance as a Metric for Image
Retrieval", Rubner, Tomasi, Guibas, International Journal of Computer
Vision 40(2):99-121, 2000 (Kluwer; the publisher's typeset PDF prints no
DOI). NEEDS-CHECK 2026-10-08: the DOI is to be confirmed from the
publisher's page; venue, volume and pages confirmed from the PDF. CORE.
Grounds: the distribution metric of the rubric campaign (spec F D-F5, earth
mover's distance only for the ordinal rubric scores, with a permutation
null): "The transportation problem is to find the minimal cost that must be
paid to transform one distribution into the other" (Section 1, p. 100),
"the EMD measures the least amount of work needed to fill the holes with
earth" with "a unit of work" as "transporting a unit of earth by a unit of
ground distance" (Section 4, p. 104), and "When used to compare
distributions with the same overall mass, the EMD is a true metric"
(abstract, p. 99; proof in Appendix A, p. 120).

**[ADD-90]** STD. JCGM 100:2008, "Evaluation of measurement data: Guide to
the expression of uncertainty in measurement" (GUM 1995 with minor
corrections), Joint Committee for Guides in Metrology (BIPM, IEC, IFCC,
ILAC, ISO, IUPAC, IUPAP, OIML), first edition September 2008, published
free of charge on the BIPM website. A guide of the standards bodies'
joint committee, tagged STD as the closest tag (it is not a numbered ISO
standard; ISO/IEC Guide 98-3 is its ISO issue). VERIFIED 2026-10-08
(identifier and edition from the PDF). CORE. Grounds: the three-repeats
measurement protocol and the instrument framing of spec F (D-F4,
repeatability measured, never assumed): repeatability is the "closeness of
the agreement between the results of successive measurements of the same
measurand carried out under the same conditions of measurement" (B.2.15,
p. 35); random error is the "result of a measurement minus the mean that
would result from an infinite number of measurements of the same measurand
carried out under repeatability conditions" (B.2.21, p. 37) and systematic
error that mean "minus a true value of the measurand" (B.2.22, p. 37);
random effects "give rise to variations in repeated observations of the
measurand" (3.2.2, p. 5). The repeat spread of the judge is the
experimental standard deviation (4.2.2, p. 10, n minus 1).

**[ADD-91]** PRE. "Play Favorites: A Statistical Method to Measure
Self-Bias in LLM-as-a-Judge", Spiliopoulou, Fogliato, Burnsky, Soliman, Ma,
Horwood, Ballesteros (Amazon Web Services), arXiv 2508.06709v1 [cs.CL],
8 August 2025. VERIFIED 2026-10-08 as a preprint (arXiv identifier from
the PDF); no peer-reviewed version known. SUPPORTING; related work only,
never sole grounding (Jose's ruling 2026-09-16, refs/triage-judge-calibration/TRIAGE.md).
Grounds: the statistical measurement of self-bias and family bias with the
completions' quality held fixed by a third-party reference, related work
for DEC-07's cross-family rule and spec F H2: "These models also display
family-bias; systematically assigning higher ratings to outputs produced by
other models of the same family" (abstract, p. 1); family bias defined as
"a tendency to favor completions from models within the same family"
(Section 1, p. 2). The rule's grounding is ADD-84 and ADD-85.

**[ADD-92]** PEER. "Weighted Kappa: Nominal Scale Agreement with Provision for
Scaled Disagreement or Partial Credit", Cohen, Psychological Bulletin
70(4):213-220, October 1968 (the APA PsycNet PDF of the typeset article; no
DOI printed). NEEDS-CHECK 2026-10-08: the DOI 10.1037/h0026256 named by spec F
is to be confirmed from the publisher's page; author, title, venue, volume,
issue, pages and year confirmed from the PDF's first page. CORE. Grounds: the
quadratic-weighted kappa per rubric dimension, the paired ordinal agreement
measure between the instrument and the specialists, item by item (spec F
D-F10), and D-F21's note that it is kept as a supplementary analysis
conditional on equal spacing (the assumption Section 9 declares once for the
D-F10 measures): weighted kappa "provides for the incorporation of
ratio-scaled degrees of disagreement (or agreement) to each of the cells of
the k X k table of joint nominal scale assignments such that disagreements of
varying gravity (or agreements of varying degree) are weighted accordingly.
Although providing for partial credit, KW is fully chance corrected"
(abstract, p. 213); "The weights assigned are an integral part of how
agreement is defined" (p. 215); "K is the special case of KW where all
disagreements are given the same weight" (p. 218); and, with the
squared-distance weights and the categories scored by their index numbers
("the first category is scored 1, the second is scored 2, etc."), "r is found
identical to the KW above" (p. 218), the equal-step reading behind the
conditional. Fleiss and Cohen 1973 (refs/triage-judge-calibration/, verdict
pending) is the companion that relates the quadratic form to the intraclass
correlation. The text layer is an OCR; kappa reads "K" and weighted kappa "KW"
in the sidecar.

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

- ADD-33 (Hasan 2016, IJSSOE systematic classification of regulatory-compliance approaches): dropped 2026-10-08 by Jose as out of date and never obtained; ADD-29 (Kosenkov et al. 2025) covers the ground.
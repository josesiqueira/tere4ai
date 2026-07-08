# TERE4AI v2 Architecture and Specification

> Authoritative spec for the TERE4AI v2 core. Agent working rules live in
> @AGENTS.md; human context in @USER.md; the browser/web UI visual system in
> @docs/DESIGN.md; the paper reference register in @docs/references.md. Where a
> decision cites `grounded_by: REF-xx`, the citation lives in references.md.
> This document supersedes the earlier control-document drafts.
>
> Formatting rule: never use em dashes, and never use en dashes as a sentence
> break. Use commas, colons, parentheses, or separate sentences.

## 0. Thesis position, caveat, users

- Core position: TERE4AI is not a legal chatbot and not a flat graph of guessed
  connections. It is an evidence-gated compliance support system where every
  answer traces from project context to legal source text, normative
  obligation, required engineering evidence, and optional ethical alignment.
- Legal caveat (MUST hold in all output): TERE4AI provides engineering and
  documentation support. It must not claim to certify EU AI Act compliance and
  must not replace legal review, conformity assessment, or competent-authority
  interpretation.
- Primary user: a technical team, SME, AI engineer, or coding agent building an
  AI system and needing actionable, traceable engineering requirements.
- Novelty (RES-1): existing work maps requirements to standards (REF-10),
  extracts obligations (REF-11, REF-12), or does graph plus LLM-judge QA
  (REF-24). None close the loop to the developer. TERE4AI generates engineering
  requirements and evaluates project evidence inside the coding agent's
  workflow, gated by a build-time and a runtime judge, evaluated for calibrated
  reliance rather than raw accuracy.

## 1. Layered graph model
grounded_by: REF-08, REF-09, REF-24

Explicit layers in one physical store; every node and edge carries a layer and
provenance fields.

- Layer 0 Source corpus: SourceDocument, SourceVersion, SourceFile, SourceSpan, BuildRun.
- Layer 1 Legal structure: Regulation, Chapter, Section, Article, Paragraph, Subparagraph, Point, Annex, AnnexItem, Recital, Definition, CrossReference.
- Layer 2 Normative/compliance: NormativeStatement, Obligation, Prohibition, Permission, Right, Condition, Exception, ActorRole, LifecyclePhase, RequiredArtifact, RequiredProcess, EvidenceExpectation, RiskCategory, ApplicabilityRule, ComplianceControl.
- Layer 3 Ethics and alignment: HLEGRequirement, ALTAIQuestion, EthicalPrinciple, AlignmentAssertion, MappingEvidence, MappingRun, JudgeRun, StandardRequirement, OntologyConcept.
- Layer 4 Runtime project evidence: Project, AISystem, SystemPurpose, DeploymentContext, Provider, Deployer, UserGroup, AffectedPerson, Dataset, Model, TechnicalDocumentation, RiskAssessment, TestReport, LogMechanism, HumanOversightMeasure, MonitoringPlan, IncidentReport, CodeArtifact, EvaluationFinding, BacklogItem.

Recitals are context only. A runtime requirement must cite an operative article,
paragraph, point, or annex item, never a recital.

## 2. Identity and provenance

- Node IDs use an ELI-like convention constructed deterministically by the parser
  from the source structure (see Section 6), for example
  `eu-ai-act:article-9:paragraph-1`, `eu-ai-act:annex-iii:point-5:a`. The served
  manifestations carry no eId attributes (spike-confirmed, Section 6), so IDs are
  derived from parsed structure, not lifted; provenance is EXTRACTED_SOURCE with
  the source span. grounded_by: REF-04
- No edge exists without provenance. Every edge carries: edge_id, edge_type,
  provenance_class, source_span_id or derivation_id, method, confidence,
  review_status, build_id.
- Provenance classes (grounded_by: REF-32): EXTRACTED_SOURCE,
  EXTRACTED_CROSS_REFERENCE, RESOLVED_DETERMINISTIC, LLM_CANDIDATE,
  LLM_JUDGED_ACCEPTED, LLM_JUDGED_REJECTED, HUMAN_REVIEWED_ACCEPTED,
  HUMAN_REVIEWED_REJECTED, AMBIGUOUS_NEEDS_REVIEW.
- Field-level JSON schemas for nodes and edges live in `schema/json_schemas/`
  and are the machine-readable source of truth; this document is the
  human-readable one.

## 3. Normative statements (deontic)
grounded_by: REF-11, REF-12, REF-07, REF-13, REF-14

- An Article is not one requirement. Each extracted norm is a NormativeStatement
  node with, at minimum: norm_id, source_node_id, source_span_id, deontic_type,
  modal, actor_explicit, actor_inferred, actor_inference_source_node_id, action,
  object, target_system_category, condition_ids, exception_ids,
  lifecycle_phase_ids, required_artifact_ids, evidence_expectation_ids,
  extraction_method, extractor_model, confidence, judge_verdict, review_status.
- Schema is grounded in Institutional Grammar (OVR-9): actor maps to Attribute,
  deontic_type and modal map to Deontic, action and object and conditions map to
  Aim. Pull the primary sources (REF-14) before citing.
- Actors are canonicalised (provider, deployer, importer, distributor,
  authorised representative, product manufacturer, and so on). Inferred actors
  record their inference source node (for example provider inferred via Article
  16). grounded_by: REF-28

## 4. Reified alignments
grounded_by: REF-24, REF-21, REF-10

- Do not store `Article --ALIGNS_WITH--> HLEGRequirement` as a truth edge. Store
  an AlignmentAssertion node connected to source norm, target HLEG or ALTAI
  requirement, mapping evidence spans on both sides, a MappingRun, and a
  JudgeRun.
- AlignmentAssertion carries the score dimensions (semantic similarity,
  normative relevance, operational utility, evidence strength, judge
  confidence), a final score, generator and judge model and prompt versions,
  judge verdict, rationale, and review status.
- Relation types: directly_operationalizes, partially_operationalizes, supports,
  related_to, conflicts_with, no_clear_relation.

## 5. Store decision: Neo4j primary plus RDF export
OVR-8. grounded_by: REF-20, REF-21, REF-22, REF-08, REF-25, REF-23

- Operational store: Neo4j (labeled property graph). Rationale: provenance sits
  on every edge, which is native to property graphs and awkward in RDF
  (reification or RDF-star); the task is to reject (validation gates), not to
  infer via OWL reasoning; property-graph legislation pipelines are established.
- RDF/OWL export via neosemantics (n10s) used only for alignment to AIRO and
  TAIR (OWL) and for legal-informatics interoperability artifacts. Do not run a
  triplestore as the primary store in v2.
- Reified AlignmentAssertion nodes port to both models, so this choice does not
  lock out RDF later. Validation is Pydantic plus Cypher constraints; RDF export
  is the interoperability path.

## 6. Build-time pipeline and ingestion
Engineering MUST (determinism and reproducibility, see Section 13);
corroborated by REF-27, REF-26. Structure and identifiers grounded by REF-03,
REF-08, REF-05, REF-06.

Two lanes: deterministic first, LLM-assisted second.

1. acquire and freeze sources (checksum, never LLM memory, never live scraping).
2. parse legal structure deterministically. No LLM in Layer 1 (RegReAct shows
   LLMs hallucinate hierarchy, REF-27).
3. resolve cross-references by rule first; LLM repair only for unresolved or
   ambiguous cases, stored as AMBIGUOUS_NEEDS_REVIEW until judged (references
   and conditionals are the highest-error zone, REF-26).
4. extract normative statements (rules for structure and modals, LLM for deontic
   content, judge for grounding).
5. canonicalise terms and actors.
6. align to HLEG/ALTAI with an LLM, then judge.
7. validate graph, then publish a versioned dump and the MCP contract version.

Ingestion route (OVR-2, spike-confirmed 2026-07-08): the ELI URL
`http://data.europa.eu/eli/reg/2024/1689/oj` resolves only to EUR-Lex HTML and
ignores content negotiation; it does not serve structured XML and carries no eId
attributes. Layer 1 therefore uses two authoritative manifestations, each frozen
by checksum:
(a) EUR-Lex HTML manifestation, for coarse structure: article (`id="art_9"`, 113
    of them), recital (`id="rct_12"`, 180), annex (`id="anx_III"`, 13), and
    paragraph (numeric `id="009.001"`, article.paragraph, about 509). It has no
    point or annex-item anchors. Sufficient for the M1 structural mirror and the
    113 / 180 / 13 acceptance.
(b) Formex 4 (fmx4) manifestation from CELLAR, for point, subparagraph, and
    annex-item granularity, which the HTML lacks and the high-risk core needs.
    Retrieval is not on the ELI path: resolve CELEX 32024R1689 to the CELLAR work
    UUID (dc8116a1-3fe6-11ef-865a-01aa75ed71a1), then fetch the English fmx4
    manifestation. This is a scoped M2 task with its own acceptance test (Article
    5(1)(c) and Annex III point 5(a) individually addressable); fmx4 existence is
    confirmed, retrieving the exact English manifestation is CELLAR plumbing, not
    simple content negotiation.
Node IDs are derived deterministically by the parser from this structure
(Section 2); this Regulation carries no eId attributes to lift. HTML and PDF
renderings are also kept for human verification. Do not plan to download clean
Akoma Ntoso XML; it is not served that way for this Regulation.

## 7. Judges and model configuration
grounded_by: REF-16, REF-24, REF-27

Three judges, kept separate:

- Build-time extraction judge: before a norm is accepted, checks source span
  exists, deontic type is supported by the text, actor is explicit or a valid
  recorded inference, action and object are grounded, conditions and exceptions
  are not dropped, and no recital, guidance, or proposal is treated as binding.
- Build-time mapping judge: before an alignment is accepted, scores it, may
  correct the relation type, and rejects any mapping whose rationale relies on
  concepts absent from both source spans.
- Runtime grounding judge: on every generated requirement, backlog item, or
  evidence evaluation, checks that cited nodes support the claim, that law,
  ethics guideline, guidance, and inferred engineering practice are
  distinguished, that conditions and exceptions are kept, that classification is
  marked uncertain when facts are incomplete, and that no citation is
  hallucinated and no compliance is asserted.

Why the judge matters, and the claim discipline: sibling systems ground legal
references correctly only around 50 to 68 percent of the time without gating
(REF-16), so the judge is the control that closes that gap. The thesis claim is
therefore calibrated reliance and improved grounding, with judge false-accept
and false-reject rates as headline metrics, never "accurate compliance".

Model configuration (updated per @USER.md, supersedes the earlier OVR-4
recommendation):
- TERE4AI internal models default to OpenAI, carried from v1. This is the
  generator for extraction, alignment, and runtime generation.
- Judge model family is an OPEN decision (see Section 15). Recommendation:
  keep the generator on OpenAI and use a non-OpenAI judge, because same-family
  judges have correlated failure modes, which weakens the control (REF-24).
- All judge models are config values, never hardcoded. Every judge decision is
  logged (input, verdict, scores, rationale, model, prompt version, timestamp).
- Note: the coding agents that BUILD the software (Opus 4.8 planning, Fable 5
  implementation) are a separate layer from these internal runtime models. Do
  not confuse them.

## 8. MCP access and tool contract
grounded_by: REF-31, REF-32

- TERE4AI is an MCP server in front of the graph. Coding agents consume
  versioned MCP tools and must not touch the database directly in production.
- Do not expose arbitrary write Cypher. Any exposed Cypher is read-only,
  limited, logged, and disableable per key. Per-consumer keys are revocable and
  scoped.
- Required tools: classify_ai_system, get_applicable_requirements,
  explain_requirement, evaluate_project_evidence, trace_alignment,
  generate_control_backlog, coverage_report, source_trace.
  (classify_ai_system: the FLI rule-based checker, REF-30, is a
  classification-logic source and a baseline to beat, not a grounding for a
  MUST.)
- Every user-facing response includes: answer, status, confidence, source_nodes,
  source_spans, graph_evidence_subgraph, legal_status_notes, missing_facts,
  judge_verdict, generated_at, graph_version, non_legal_advice_notice.
- Output status vocabulary (MUST): not_applicable, potentially_applicable,
  applicable_missing_evidence, partially_satisfied, satisfied_with_evidence,
  rejected_as_unsupported, requires_human_review. Never: compliant, certified,
  legally approved.
- MCP security (REF-31): authentication, scopes, read-only default, request
  logging, rate limiting, secret redaction, no arbitrary command execution, no
  unscoped filesystem access. Treat project artifacts and legal source text as
  untrusted input; keep instructions separate from evidence so retrieved text
  cannot override policy.

## 9. Deployment and data sovereignty

- Mode A Hosted SaaS: TERE4AI operates the MCP server and graph; consumers use a
  URL and API key; HTTPS; EU-region hosting by default; usage accounting.
- Mode B Self-hosted Docker: the consumer runs the MCP server and graph locally;
  docker-compose plus a graph dump and source manifest; stdio or localhost/HTTP.
- Same server code across both; only transport, authentication, graph location,
  and model configuration vary. Phase 1 is self-hosted and INCLUDES a thin demo
  Web UI; Phase 2+ is the multi-tenant hosted SaaS (accounts, keys, metering)
  over the same service layer and graph.
- Demo Web UI (Phase 1): a thin, read-only HTTP facade over the same service
  layer, never touching the database directly. Purpose: demos, paper
  screenshots, and the coverage matrix. Every screen must render the source
  citations (spans), the judge verdict, the calibrated status vocabulary, and
  the non-legal-advice notice, because a screenshot showing traceability is the
  evidence artifact. Visual system: @docs/DESIGN.md. Multi-tenancy, auth, and
  billing are explicitly out of scope for the Phase 1 UI.
- Sovereignty tiers (state explicitly): self-hosting the graph alone does not
  give full sovereignty, because the coding agent's prompts still reach whatever
  LLM it uses. Tier 1 hosted graph plus cloud LLM; Tier 2 self-hosted graph plus
  cloud LLM; Tier 3 self-hosted graph plus local model (strongest, lower model
  quality, experimental in v2, not promised to match cloud quality).

## 10. Scope for v2
OVR-1. grounded_by: REF-17, REF-15

- Layer 1 structural mirror: FULL Act. All chapters and sections, Articles 1 to
  113, Recitals 1 to 180, Annexes I to XIII, with hierarchy and explicit
  cross-references. Deterministic, cheap, and this is the whole picture.
  Acceptance: 113 articles, 180 recitals, 13 annexes; Chapter III Section 2
  holds Articles 8 to 15; Article 6 links Annexes I and III; Article 11 links
  Annex IV; Annex III use cases and Annex IV items individually addressable.
- Layers 2 and 3 deep extraction (v2 core, high-risk build journey only):
  Article 3 (definitions used by classification), Article 5 (prohibited),
  Articles 6 to 7 plus Annex III (classification), Articles 8 to 15 plus Annex
  IV (requirements), Articles 16 to 27 including the Article 27 fundamental-
  rights impact assessment (provider and deployer obligations), Article 50
  (transparency), Articles 72 to 73 (light post-market monitoring), the seven
  HLEG requirements, and ALTAI items where license allows (ethics-layer source:
  REF-33).
- Structural only in v2, deep extraction deferred to v2.1+: Articles 1 to 2 and
  4, 28 to 49, 51 to 71, 74 to 113, and the remaining annexes.
- Deep-extraction acceptance applies only to the v2 core set above, not the
  whole Act.

## 11. Legal versioning
OVR-3. grounded_by: REF-01, REF-02, REF-04

- Sources carry legal_status: in_force, adopted_not_yet_applicable, proposed,
  draft, non_binding, superseded, unknown_needs_review.
- The Digital Omnibus on AI (REF-02) is adopted and changes the in-force text
  and the high-risk dates (standalone Annex III high-risk to at the latest 2
  December 2027; embedded Annex I to 2 August 2028), and softens Article 4 AI
  literacy among others. Model it as a distinct SourceDocument linked to the base
  Act by AMENDS and HAS_VERSION edges. The graph must answer a provision "as
  enacted" versus "as amended", with dates.
- VERSION PIN (decided for M1): pin Regulation (EU) 2024/1689 as the base with
  legal_status in_force. Model the Omnibus (COM(2025) 836) as a separate source
  with legal_status adopted_not_yet_applicable, carrying the deadlines above.
  Adoption and deadlines are verified; only the final published OJ number and
  date remain to confirm at build time. Do not merge Omnibus edits into the base
  text; keep them as an overlay so both versions are answerable.

## 12. Evaluation
OVR-10. grounded_by: REF-15, REF-16, REF-17, REF-18, REF-19, REF-24

- Ablation ladder: plain LLM, vector RAG over Act chunks, graph without judge,
  graph plus build judge, graph plus build and runtime judge.
- Primary dataset: the open AI Act Evaluation Benchmark (REF-15), covering
  classification, article retrieval, obligation generation, and QA. Verify its
  coverage against the high-risk core first.
- Hand-built gold set: around 60 to 80 items on the high-risk core, with a
  second annotator on a 20 to 30 percent subset for inter-rater agreement; report
  the agreement statistic.
- Baselines to beat and position against: XTRAREG-style extraction without a
  graph or judge (REF-16), and the requirement-to-verification mapping of
  REF-17.
- Metrics: structural coverage accuracy, cross-reference resolution accuracy,
  obligation extraction precision and recall, deontic and actor classification
  accuracy, condition and exception recall, mapping precision, judge false-accept
  and false-reject rates, runtime citation completeness, hallucinated citation
  rate, human-review disagreement, developer usefulness.
- Caution: existing compliance benchmarks are thin for systemic risk (REF-18);
  v2 excludes GPAI systemic risk, so exposure is limited.

## 13. Non-functional requirements and acceptance

- Traceability, reproducibility, explainability, and no silent degradation are
  MUST. If the graph, judge, or source trace is unavailable, return a degraded
  status, never confident compliance-like advice.
- A build that fails critical validation is not published. Validation gates
  include: no orphan legal nodes, no source-derived node without a source
  document, no norm without a source span, no accepted alignment without
  evidence spans on both sides, no recital treated as binding, no proposed
  amendment silently replacing the in-force source.
- Observability: log graph version, tool call, latency, token usage, model,
  judge verdict, error state, and tenant key; redact secrets and sensitive
  project text.

## 14. Milestones

- M1 Structural mirror plus versioning plus coverage_report. Deterministic Layer
  1 over the full Act from the frozen EUR-Lex HTML manifestation (Section 6;
  Formex point-depth deferred to M2); Omnibus modelled as an amending
  source; source_trace and coverage_report tools. Demo UI increment: a single
  page rendering the coverage matrix and a browsable Act structure (first
  screenshot artifact).
  Build order for M1: (1) freeze the HTML snapshot and derive the ID scheme from
  its anchors (ingestion spike done, Section 6); (2)
  apply the version pin (Section 11); (3) write schema/json_schemas/ first, since
  Section 2 declares them the machine-readable source of truth; (4) Neo4j plus
  Cypher constraints; (5) the deterministic parser and cross-reference resolver;
  (6) the CI tag-checker that generates docs/traceability.md and fails on a
  missing @implements or an unknown REF id. Write the acceptance fixtures
  (113 / 180 / 13; Chapter III Section 2 equals Articles 8 to 15; Article 6 links
  Annexes I and III; Article 11 links Annex IV) first, as the target.
- M2 High-risk-core normative graph plus reified alignments plus build judges.
  Layers 2 and 3 over the v2 core only. Migrate the existing v1 slice (Articles
  9, 10, 13, 14, 15 and the seven HLEG nodes) into the new judged, reified
  pipeline; keep the old poster query as a regression fixture.
- M3 Runtime tools plus runtime judge. classify_ai_system,
  get_applicable_requirements, evaluate_project_evidence,
  generate_control_backlog, end-to-end audit log. Demo UI increment: the full
  demo flow (describe system, see classification, requirements with citations,
  evidence evaluation, judge verdicts), screenshot-ready for the tool paper.
- M4 Evaluation harness plus gold set plus ablations.
- Deferred to post-thesis / v2.1: GPAI deep extraction, standards mapping (TAIR),
  full-Act deep extraction, the trust/HCI study.

Paper mapping (RES-3): M1 to M3 produce the tool/method paper (RE or SE venue);
M4 produces the empirical ablation paper (empirical SE venue); together they
feed the integrative journal article. A legal-informatics paper (deontic
extraction plus reified alignment) and a trust/HCI calibrated-reliance study are
stretch, not on the critical path.

## 15. Highest-risk components and open decisions

Highest-risk components (evaluate explicitly, do not fold into general numbers):
- Evidence evaluation (does artifact X satisfy requirement Y) is the most novel
  step and the least de-risked by prior work; the siblings do generation and
  mapping, not evidence evaluation, so there is no external accuracy baseline.
- Applying the Omnibus amendments to the base text deterministically is fiddly.
- The end-2026 timeline is tight even scoped; protect M1 to M3, the tool paper,
  and one evaluation paper.

Open decisions:
- OPEN-JUDGE: judge model family. OpenAI-only (simpler, correlated failure
  modes) versus OpenAI generator plus a non-OpenAI judge (stronger trust claim).
  Recommendation: the latter.
- OPEN-VENUE: exact target venue and deadline per planned paper.
- OPEN-LICENSE: server AGPL-3.0-or-later; graph metadata CC BY 4.0 or CC0; EU
  legal text under EU reuse terms (do not claim ownership); ALTAI redistribution
  needs a license check.
- OPEN-STANDARDS: standards mapping (TAIR) deferred to v2.1.

Sources to verify before the thesis (see references.md [VERIFY] tags): the
Omnibus final OJ citation, the Institutional Grammar primaries (REF-14), the
exact XTRAREG and Galli metrics, AIRO's canonical URL, and the AI Act Evaluation
Benchmark coverage.

## 16. Traceability matrix (decision, grounding, defense, verify)

Per decision: grounded_by, a one-sentence viva defense, and verify_in_code
(where an auditor or the agent confirms it was built). Modules carry
`@implements` and `@grounded_by` tags; see Section 17.

- DEC-01: Layer 1 parsed deterministically, no LLM. Engineering MUST (determinism,
  reproducibility, no-silent-degradation, Section 13); corroborated by REF-27, REF-08.
  Defense: the authoritative structure must be deterministic and reproducible;
  LLMs also hallucinate legal hierarchy, so no model touches Layer 1.
  verify: src/parse_legal_structure/ has no model calls; tests assert 113/180/13.
- DEC-02: cross-references resolved by rule first. Engineering MUST (determinism);
  corroborated by REF-26, REF-29.
  Defense: references are exact pointers, so rule resolution is deterministic;
  references and conditionals are also the highest-error zone for LLMs.
  verify: src/resolve_crossrefs/ rule pass plus AMBIGUOUS queue; crossref test.
- DEC-03: NormativeStatement first-class, Institutional Grammar. grounded_by REF-11,
  REF-12, REF-13. Defense: deontic-KG practice; an article holds many norms.
  verify: src/extract_norms/ emits norm nodes; norm_extraction test.
- DEC-04: actor inferred via Article 16, canonicalised. grounded_by REF-28, REF-11.
  Defense: multi-party texts cause object/actor misidentification.
  verify: src/canonicalize/ actor table; actor_inference test.
- DEC-05: reified AlignmentAssertion nodes. grounded_by REF-24, REF-21, REF-10.
  Defense: a mapping is an auditable claim, not law; store-portable.
  verify: src/align_hleg_altai/; query for accepted mapping without evidence returns zero.
- DEC-06: dual/triple judges. grounded_by REF-16, REF-24, REF-27.
  Defense: unjudged legal grounding is only 50 to 68 percent correct.
  verify: src/judge/ three entry points; runtime_grounding test asserts no answer without a verdict.
- DEC-07: OpenAI generator, judge family open (recommend independent). grounded_by REF-24.
  Defense: same-family judge failure modes correlate; user chose OpenAI internals.
  verify: eval/config_evaluated.yaml records generator and judge models.
- DEC-08: calibrated vocabulary, never "compliant". grounded_by REF-16, and the
  legal non-goal (Section 0). Defense: measured grounding limits and the legal
  caveat make any certified-compliance claim unsupportable.
  verify: MCP output enum lacks compliant/certified; no_compliance_claim test.
- DEC-09: Neo4j primary plus RDF export. grounded_by REF-20, REF-21, REF-22, REF-08, REF-25, REF-23.
  Defense: edge-native provenance and a reject-not-infer task fit property graphs.
  verify: graph_store/ uses Neo4j; rdf_export_roundtrip test.
- DEC-10: full structural mirror, deep only on high-risk core. grounded_by REF-17, REF-15.
  Defense: value and benchmarks concentrate on the high-risk regime.
  verify: coverage_report shows full Layer 1, Layer 2/3 only on Section 10 set.
- DEC-11: reuse open benchmark plus sibling baselines. grounded_by REF-15, REF-16, REF-17.
  Defense: an open benchmark covers our tasks; siblings are the baselines.
  verify: eval/ loads REF-15; eval/baselines/ implements vector-RAG and no-judge.
- DEC-12: Omnibus modelled as an amending, versioned source. grounded_by REF-02, REF-04.
  Defense: it is adopted and changes the in-force text and the dates.
  verify: SourceDocument for COM(2025)836 with AMENDS/HAS_VERSION; versioning test.

## 17. Implementation-traceability convention

- Every requirement or decision carries grounded_by (REF ids in references.md)
  and verify_in_code (a path plus a test).
- Every module or function that implements a decision carries in its header:
  `@implements: <decision-id>` and `@grounded_by: REF-xx, REF-yy`.
- `docs/traceability.md` is generated in CI from those tags, never hand-written,
  with columns decision_id, grounded_by, code_paths, test_ids, status
  (implemented, partial, not_started).
- CI fails the build if a Section 16 decision has no `@implements` anywhere, or
  if a `@grounded_by` cites a REF id not in references.md.
- No REF may be cited unless it exists in references.md with a source-type tag.
  Grounding bar (single definition, shared with @AGENTS.md and references.md): a
  MUST that makes a research or empirical claim needs at least one PEER, STD, or
  OFF grounding; PRE, PROJ, and PRAC may support but never be sole grounding. An
  engineering or non-functional MUST stands on engineering merit and needs no
  literature grounding. The CI tag-checker enforces this bar.
- To answer "is decision X built": grep `@implements`, open the cited test, run
  it, report code paths plus test result plus grounding. Report status honestly
  as implemented, partial, or not_started. Never report done on the basis of the
  spec alone.

## 18. Repository layout (target)

```
tere4ai2/
  AGENTS.md  USER.md
  docs/            architecture.md  references.md  DESIGN.md  traceability.md (generated)
  src/tere4ai/     ingest/ parse_legal_structure/ resolve_crossrefs/
                   extract_norms/ canonicalize/ align_hleg_altai/ judge/
                   validate_graph/ graph_store/ mcp_server/ http_facade/ eval/
  web/             Next.js demo UI (thin, read-only; per docs/DESIGN.md)
  schema/          json_schemas/ cypher_constraints/ rdf_export/
  prompts/         extract_norms/ judge_norms/ align_hleg/ judge_alignment/ runtime_grounding/
  data/            sources/ snapshots/ graph_dumps/ review_queue/
  tests/           unit/ integration/ fixtures/ gold/ meta/
  docker-compose.yml  pyproject.toml
```

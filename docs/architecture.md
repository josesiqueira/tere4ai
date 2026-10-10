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
grounded_by: REF-08, REF-09, REF-24, ADD-01

Explicit layers in one physical store; every node and edge carries a layer and
provenance fields. The labels in backticks below are exactly the node labels the
graph store accepts (src/tere4ai/graph_store/store.py, NODE_LABELS), and
tests/unit/test_architecture_layers.py holds this section to that set (rewritten
2026-10-07, DEC-25, from the plan of 2026-07-08, which listed types never built).

- Layer 0 Source corpus: `SourceDocument`, `SourceFile`. `BuildRun` is accepted by the store and the node schema but created by no code: a build is recorded in the dump's build block and in the build record file (DEC-16). Spans are not nodes: each node that cites a source holds its span (file, sha256, offsets).
- Layer 1 Legal structure: `Regulation`, `Chapter`, `Section`, `Article`, `Paragraph`, `Subparagraph`, `Point`, `Annex`, `AnnexItem`, `Recital`, `Definition`, `CrossReference`, and `UnitVersion` (the 2024 wording of a unit the Digital Omnibus changed, DEC-23).
- Layer 2 Normative statements: `NormativeStatement`, `Condition`, `Exception`. The deontic type, the actor, the lifecycle phase and the requirement type are slots of a normative statement, and its required artifacts and evidence expectations are id lists on it (Section 3), not nodes.
- Layer 3 Ethics and alignment: `HLEGRequirement`, `HLEGRequirementSubtopic`, `AlignmentAssertion`, `MappingRun`, `JudgeRun`. ALTAI questions are not in the graph, by decision (ALTAI redistribution still needs its licence check, task C2, Section 15); an assertion's evidence is held as span ids on the assertion.
- Layer 4 Runtime project evidence: not in the graph. A project's facts, evidence and backlog are held by the dashboard's project store and in the MCP tools' answers (Section 8).
- Not built: the plan of 2026-07-08 named further types, none of which was built or is a label the store accepts: SourceVersion and SourceSpan (Layer 0); Obligation, Prohibition, Permission, Right, ActorRole, LifecyclePhase, RequiredArtifact, RequiredProcess, EvidenceExpectation, RiskCategory, ApplicabilityRule and ComplianceControl (Layer 2); ALTAIQuestion, EthicalPrinciple, MappingEvidence, StandardRequirement and OntologyConcept (Layer 3); and twenty Layer 4 types, from Project to BacklogItem.

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
grounded_by: REF-11, REF-12, REF-07, REF-13, REF-14c

- An Article is not one requirement. Each extracted norm is a NormativeStatement
  node with, at minimum: norm_id, source_node_id, source_span_id, deontic_type,
  modal, actor_explicit, actor_inferred, actor_inference_source_node_id, action,
  object, target_system_category, condition_ids, exception_ids,
  lifecycle_phase_ids, required_artifact_ids, evidence_expectation_ids,
  requirement_type, extraction_method, extractor_model, confidence,
  judge_verdict, review_status.
- Requirement type (added 2026-10-01, DEC-19): an obligation or a
  prohibition addressed to an operator in a requirement group carries
  requirement_type, one of functional, quality or process, the types of
  ISO/IEC/IEEE 29148:2018 clause 5.2.8.3 (ADD-54); every other norm carries
  null, shown "not an operator requirement". The type is one more closed
  slot of the norm, one with no Institutional Grammar counterpart. The
  extraction judge records its view of the type without gating on it.
  grounded_by: ADD-54, ADD-55, ADD-56
- Target system category (added 2026-10-03, DEC-21): target_system_category
  names the part of the Act's rules the norm belongs to, by the category
  of AI systems those rules govern: any_ai_system (Chapter I),
  prohibited_ai_practice (Chapter II), high_risk_ai_system (Chapter III,
  Annexes III and IV, Articles 72 and 73) or article_50_ai_system
  (Chapter IV). It does not say which system a single paragraph talks
  about; the addressee stays in the actor fields. A rule sets it from the
  norm's source Article or Annex, never a model; null only for a source
  unit outside the rule table. grounded_by: REF-01
- Schema is grounded in Institutional Grammar (OVR-9): actor (the addressee from norms schema version 2, DEC-27) maps to Attribute,
  deontic_type and modal map to Deontic, action and object and conditions map to
  Aim. Pull the primary sources (REF-14c) before citing.
- The addressee (the Institutional Grammar's Attribute; until B145 the
  "actor") is placed on one value of the Act's parties, the one list
  schema/act_parties.json (37 values: the six AI Act roles of Article
  3(8), 9 authorities, 2 bodies, 9 institutions, 9 persons and 2 values
  that name no single party), and the value is stored on every norm a v5
  run writes (norms schema version 2: addressee_explicit,
  addressee_inferred, addressee_inference_source_node_id, addressee,
  addressee_method, addressee_placement; DEC-27). Inferred addressees
  record their inference source node (for example provider inferred via
  Article 16(a), or via the sentence of the same Article that sets up the
  thing the norm's subject names). grounded_by: REF-11, REF-12
- Requirements of Articles 8 to 15 (added 2026-10-07, DEC-26): a norm of
  Chapter III Section 2 that states or qualifies one of its requirements
  for the high-risk AI system and whose text names no person or body that
  must act has no written actor, the inferred actor provider and the
  Article 16(a) node, eu-ai-act:article-16:paragraph-1:point-a, as its
  inference source, whatever the sentence's subject and whether its verb
  is active or passive. The system's words stay in the norm's source unit
  and span; no slot holds them. A person or body the text names keeps its
  written actor; outside Articles 8 to 15 a thing may still stand as the
  written actor (Article 17's "that system") (until B145; from
  extract_norms v5 a covered thing's duty is the party's that sets it up,
  DEC-27). grounded_by: REF-01, REF-11

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
OVR-8. grounded_by: REF-21, REF-22, REF-08, REF-25, REF-23

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
REF-08, REF-05; the Ethics Guidelines (route (d)) by ADD-01.

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
    point or annex-item anchors. Sufficient for the MILESTONE1 structural mirror and the
    113 / 180 / 13 acceptance.
(b) Formex 4 (fmx4) manifestation from CELLAR, for point, subparagraph, and
    annex-item granularity, which the HTML lacks and the high-risk core needs.
    Retrieval (verified 2026-07-08): GET the CELLAR work URI
    `http://publications.europa.eu/resource/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1`
    with headers `Accept: application/zip;mtype=fmx4` and `Accept-Language: eng`.
    The zip holds the main body (113 ARTICLE with IDENTIFIER attributes, 509
    PARAG, points as NP with NO.P markers) plus one file per annex. Point and
    annex-item markup is confirmed present: Article 5(1) points (a) to (d) with
    nested romanettes, and Annex III point 5(a), both individually addressable.
    The package is frozen under data/snapshots/formex/ with per-file checksums.
(c) Since B132 (2026-10-03), the AI Act in force: EUR-Lex's consolidated text
    of 27 July 2026 in Formex 4 (CELEX 02024R1689-20260727, CELLAR work
    b1730fb2-8f1c-11f1-9262-01aa75ed71a1), from which Layer 1 is parsed, and
    the Formex 4 of the Digital Omnibus, Regulation (EU) 2026/1744 (CELEX
    32026R1744, CELLAR work b459c07f-86fb-11f1-bf5e-01aa75ed71a1), against
    which every unit it amended is checked (Section 11). Retrieval (verified
    2026-10-03): the CELLAR SPARQL endpoint gives each work's fmx4
    manifestation and its item (cdm:resource_legal_id_celex for the CELEX,
    then cdm:expression_belongs_to_work, cdm:expression_uses_language ENG,
    cdm:manifestation_manifests_expression, cdm:manifestation_type and
    cdm:item_belongs_to_manifestation); GET the items
    `http://publications.europa.eu/resource/cellar/b1730fb2-8f1c-11f1-9262-01aa75ed71a1.0001.01/DOC_1`
    and
    `http://publications.europa.eu/resource/cellar/b459c07f-86fb-11f1-bf5e-01aa75ed71a1.0006.02/DOC_1`
    (two zips); the consolidated text's XHTML, kept for EUR-Lex's sentence
    that it "is meant purely as a documentation tool and has no legal
    effect", comes from GET of the consolidated work URI with headers
    `Accept: application/xhtml+xml` and `Accept-Language: eng`. The zips,
    their members and the XHTML are frozen under data/snapshots/ with
    per-file checksums. As for the 2024 files, no fetch script exists: the
    freeze is done once.
(d) Since B143 (2026-10-07, DEC-25), the Ethics Guidelines for Trustworthy AI
    (High-Level Expert Group on Artificial Intelligence, 2019; ADD-01), which
    Layer 3 reads: the Publications Office edition, publication
    d3988569-0434-11ea-8c1f-01aa75ed71a1 (English PDF, ISBN
    978-92-76-11998-2, DOI 10.2759/346720, catalogue number
    KK-02-19-841-EN-N), the only edition with an ISBN, a DOI and a CELLAR
    identifier. No structured manifestation is served: read 2026-10-07, the
    publication record and the CELLAR branch notice of the English expression
    list pdf, pdfx and print only, and the Commission's page offers PDFs only.
    Retrieval (verified 2026-10-07): GET the item
    `http://publications.europa.eu/resource/cellar/d3988569-0434-11ea-8c1f-01aa75ed71a1.0004.03/DOC_1`,
    byte-identical to the PDF frozen under data/snapshots/ on 2026-07-08. As
    for the legal files, no fetch script exists: the freeze is done once. The
    text of Chapter II Section 1 (the seven requirements) is derived from the
    PDF's own tags by `python -m tere4ai.ingest.hleg_text --write`, which
    writes the derived text and its derivation record beside the PDF; every
    Layer 0+1 build checks them against the PDF with a second reader, pypdf
    (checks HLEG_CHECK0 to HLEG_CHECK4, DEC-25), a failure stopping the parse.
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
  Since judge_norms v2 (2026-10-01, DEC-19) it also receives the verbatim
  text of an inferred actor's source unit (DEC-04), and it records whether it
  agrees with the norm's requirement type, and its own type when it does
  not, without that record changing the verdict. Since judge_norms v3
  (2026-10-03, DEC-21) the candidate it receives no longer carries
  target_system_category, which a rule sets after the verdict; its checks
  and verdict values do not change. Since judge_norms v4 (2026-10-07,
  DEC-26) check 3 accepts the provider inferred through Article 16(a)
  (eu-ai-act:article-16:paragraph-1:point-a) for a requirement of Articles
  8 to 15 whose text names no person or body that must act and rejects
  that inference elsewhere, and a point given as the inference source
  reaches the judge with the paragraph that holds it. Since judge_norms v5
  (2026-10-09, DEC-27) its check 3 also accepts an inference resting on
  the set-up rule and rejects, on a unit the set-up table covers, the
  row's thing or a pronoun in addressee_explicit; for a candidate on such
  a unit it receives the unit's set-up rows with the setting-up node's
  text, and its input labels say "Addressee-inference source"; its six
  checks, verdict values and scores do not change.
- Build-time mapping judge: before an alignment is accepted, scores it, may
  correct the relation type, and rejects any mapping whose rationale relies on
  concepts absent from both source spans.
- Runtime grounding judge: on every generated requirement, backlog item, or
  evidence evaluation, checks that cited nodes support the claim, that law,
  ethics guideline, guidance, and inferred engineering practice are
  distinguished, that conditions and exceptions are kept, that classification is
  marked uncertain when facts are incomplete, and that no citation is
  hallucinated and no compliance is asserted. Since runtime_grounding v2
  (2026-10-01, DEC-19) it records its view of each generated control's
  requirement type, which never changes the backlog's verdict.

Why the judge matters, and the claim discipline: sibling systems ground legal
references correctly only around 50 to 68 percent of the time without gating
(REF-16), so the judge is the control that closes that gap. The thesis claim is
therefore calibrated reliance and improved grounding, with judge false-accept
and false-reject rates as headline metrics, never "accurate compliance".

Model configuration (updated per @USER.md, supersedes the earlier OVR-4
recommendation):
- TERE4AI internal models default to OpenAI, carried from v1. This is the
  generator for extraction, alignment, and runtime generation.
- Judge model family (DECIDED 2026-07-08, was OPEN-JUDGE): generator on OpenAI,
  judge on an independent non-OpenAI family (Anthropic Claude), because
  same-family judges have correlated failure modes, which weakens the control
  (REF-24). Both are config values in .env / eval config, never hardcoded.
- All judge models are config values, never hardcoded. Every judge decision is
  logged (input, verdict, scores, rationale, model, prompt version, timestamp).
- The HTTP facade's demo mode (added 2026-10-06, DEC-24): /api/backlog and
  /api/evidence can answer from the generator alone, signed, and a judge
  route judges the kept answer later with a demo judge of the generator's
  own family (TERE4AI_DEMO_JUDGE_MODEL, never the generator's model id),
  every such answer labelled so. The MCP tools and the inline routes keep
  the independent judge above.
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
  legally approved. Scope (decided 2026-07-21, characterization corrected
  2026-07-30): the banned-term ban covers every system-generated text field
  (status, composed answer text, notes, summaries, messages, backlog titles
  and descriptions; a backlog title is model-generated, so it is in scope).
  Two categories of field are exempt, because they carry regulatory content
  rather than a TERE4AI verdict, and only the first is byte-exact. (a)
  Byte-exact quotes-of-record: frozen source span text and verbatim quotes
  lifted from the frozen corpus (the source span text and alignment evidence
  quotes). These are preserved byte-for-byte and must never be altered,
  because that byte-exactness is the traceability guarantee; the Act's own
  sentences say "compliant with the requirements" (Article 8(2), Article 16
  point (a)). (b) Normalized deontic extractions: the norm action and object
  wording (Institutional Grammar, DEC-03) carry the regulator's own
  vocabulary, so they are exempt from the verdict-ban as extracted regulatory
  content, but they are normalized (case-folding, whitespace, elision of long
  inline material) and are NOT claimed to be byte-exact verbatim quotes; the
  byte-exact quote-of-record for a norm is its source span text. Exempt fields
  are structurally marked by their field name (see VERBATIM_QUOTE_FIELDS in
  mcp_server/tools.py) and are never presented as a system verdict.
- MCP security (REF-31, revision 2026-07-28). What the spec itself says:
  authorization is OPTIONAL; over HTTP it recommends OAuth 2.1 with
  audience-bound tokens (SHOULD), and for stdio it directs credentials to the
  environment. Phase 1 deviates deliberately from the OAuth recommendation:
  scoped, revocable t4a_ Bearer keys (keys.py) fit the self-hosted Mode B
  scope; a Phase 2 hosted deployment revisits OAuth conformance. Properties
  the revision demands that this server satisfies structurally: no token
  passthrough (consumer keys are never forwarded; model credentials are
  server-side configuration), statelessness with no state handles, and scope
  minimization (six narrow scopes; paid tools behind their own scopes).
  Engineering MUSTs of this project, corroborated but not mandated by the
  spec: read-only default, request logging, rate limiting, secret redaction,
  no arbitrary command execution, no unscoped filesystem access. Treat project
  artifacts and legal source text as untrusted input; keep instructions
  separate from evidence so retrieved text cannot override policy (engineering
  MUST; the spec's tool-safety principle treats tool descriptions as
  untrusted but no longer carries this exact separation rule).
- MCP revisions and transports (C3, 2026-10-02, REF-31). One process serves
  revision 2026-07-28 and legacy initialize-based clients (2025-11-25 and
  earlier) over stdio and streamable HTTP; both eras are tested with the
  official MCP Python SDK client (tests/unit/test_mcp_protocol_revisions.py).
  The server advertises no MCP logging capability (a middleware in server.py,
  because fastmcp registers logging/setLevel on every server) and keeps its
  diagnostics as Python logging on stderr. The four paid tools share a replay
  window (mcp_server/replay.py): an identical call inside the window gets the
  kept answer and no second model call, so a client retry is not charged
  twice; the kept answers are per process, so two replicas do not share them.
  Client support as reported by the vendors is listed in
  docs/server/index.md.
- The public explanation of the server is docs/server/index.md, its
  drift-prone parts generated from the running server (DEC-22).

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

- Layer 1 structural mirror: FULL Act in force (DEC-23). All chapters and
  sections, the 119 Articles (1 to 113, 4a, 60a and 75a to 75d), Recitals 1
  to 180, Annexes I to XIV, with hierarchy and explicit cross-references.
  Deterministic, cheap, and this is the whole picture. Acceptance: 119
  articles, 180 recitals, 14 annexes (113, 180 and 13 for the Act as
  enacted); Chapter III Section 2
  holds Articles 8 to 15; Article 6 links Annexes I and III; Article 11 links
  Annex IV; Annex III use cases and Annex IV items individually addressable.
- Layers 2 and 3 deep extraction (v2 core, high-risk build journey only):
  Article 3 (definitions used by classification), Article 4a (the
  processing of special categories of personal data for bias detection and
  correction, inserted by the Digital Omnibus with the rule Article 10(5)
  held; B132, data/graph_dumps/core_nodes.txt), Article 5 (prohibited),
  Articles 6 to 7 plus Annex III (classification), Articles 8 to 15 plus Annex
  IV (requirements), Articles 16 to 27 including the Article 27 fundamental-
  rights impact assessment (provider and deployer obligations), Article 50
  (transparency), Articles 72 to 73 (light post-market monitoring), the seven
  HLEG requirements, and ALTAI items where license allows (ethics-layer source:
  REF-33).
- Structural only in v2, deep extraction deferred to v2.1+: Articles 1 to 2 and
  4, 28 to 49, 51 to 71 (60a included), 74 to 113 (75a to 75d included), and
  the remaining annexes (Annex XIV included). Units the Omnibus deleted are
  never extracted. The core holds 424 source units of the Act as amended
  (30 Articles and Annexes; 405 on the 2024 text).
- Deep-extraction acceptance applies only to the v2 core set above, not the
  whole Act.

## 11. Legal versioning
OVR-3. grounded_by: REF-01, REF-02, REF-04

- Sources carry legal_status: in_force, adopted_not_yet_applicable, proposed,
  draft, non_binding, superseded, unknown_needs_review.
- The Digital Omnibus on AI (REF-02) is in force (Regulation (EU) 2026/1744,
  OJ L, 2026/1744, 24.7.2026, in force since 27.7.2026) and changes the base
  text and the high-risk dates (standalone Annex III high-risk to at the
  latest 2 December 2027; embedded Annex I to 2 August 2028). It is a
  distinct SourceDocument linked to the base Act by AMENDS and HAS_VERSION
  edges.
- THE ACT IN FORCE (B132, 2026-10-03, DEC-23; it replaces the version pin
  of MILESTONE1 and the overlay of B59): every build is made from Regulation (EU)
  2024/1689 as amended by Regulation (EU) 2026/1744.
  (1) Layer 1 parses the in-force tree from EUR-Lex's consolidated text of
  27 July 2026 in Formex (CELEX 02024R1689-20260727, Section 6 (c)), one
  file in which every unit, container or leaf, has one span. The file keeps
  deleted wording in place, so an in-force span lists the deleted ranges
  under exclude, and the node's text and resolve_span's answer leave them
  out. Text is taken the same way from every Formex file
  (parse_legal_structure/units.py): quotation marks kept, inline elements
  add no space, footnotes left out. The recitals still come from the 2024
  act's HTML, as consolidated texts leave the preamble out.
  (2) The consolidated text "is meant purely as a documentation tool and
  has no legal effect" (EUR-Lex), and only the electronic edition of the
  Official Journal is authentic and produces legal effects (ADD-83,
  Regulation (EU) No 216/2013, Article 1(2)), so every unit is checked
  before the parse completes (parse_legal_structure/amendments.py): an unchanged unit equals
  the 2024 unit of the same id, Formex against Formex; a replaced or
  inserted unit is in the Omnibus quotation of the point that enacted it; a
  partly amended unit is checked as composed (its marked parts in the
  quotation, the rest equal to its 2024 text); Annex XIV equals the Omnibus
  annex member file; every quotation of the Omnibus's Article 1 is in a
  marked range of its own point; an unchanged or composed container's wording outside its
  units (an annex's opening sentence, the Section headings inside an annex)
  equals its 2024 wording. The consolidated text's 77 change markers (72 Omnibus
  points) are read per unit, written to the reviewed file
  data/amendments/omnibus_markers.json and each checked against the Omnibus
  text, the 2024 tree and the verified inventory docs/omnibus_amendments.md.
  Any other difference stops the parse unless a row of the reviewed
  exception list data/amendments/omnibus_exceptions.json covers it, and a
  row no check needs stops it too. Where a marker and the Omnibus disagree
  the Omnibus decides, through such a row.
  (3) Unchanged and replaced units keep their ids; inserted units take the
  Act's numbers (eu-ai-act:article-4a, eu-ai-act:article-6:paragraph-1a,
  eu-ai-act:article-5:paragraph-1:point-ba, eu-ai-act:annex-xiv); an Article
  number or paragraph index is the Act's label with a sort key. A deleted
  unit stays as a node marked deleted, with every unit inside it, and has no
  text and no span; extraction and cross-reference resolution skip it. Each
  replaced or deleted unit and each composed container keeps its 2024
  wording as a UnitVersion node, its span named with the version date
  (span:010.005@2024-07-12), linked by HAS_VERSION; nothing that walks the
  unit types meets it.
  (4) Layer 0 freezes the Omnibus and the consolidated text in Formex, the
  consolidated text with legal_status non_binding. The Omnibus
  SourceDocument says merged_into_base true with the date and the marker
  list's sha256. The checks run in the parse, which raises on any failure,
  so no dump is written; gate PUBLICATION_GATE6 does not run them again: it verifies that a
  merged Omnibus comes with the build's record of the checks and the same
  marker list digest, which catches a record that is missing or edited. The
  build id is a digest over every frozen legal
  source the parse reads, so a build with the Omnibus and one without it
  never share an id.
  (5) The answers follow the same text (B132's second plan, 2026-10-04):
  classify_ai_system cites Article 5(1) points (ba) and (bb) as their nodes,
  with Article 5(1a) and (1b); a third fact of the Article 6(1) route,
  annex_i_section_b_legislation, names the Annex I section of the product's
  legislation (answer field annex_i_section: A, B or unknown). For Section
  B, under Article 2(2), only Article 6(1), Article 60a and Articles 102 to
  112 shall apply (and Articles 57 to 59 on the condition it states and the
  answer does not decide): with no Annex III
  match no Chapter III requirement and no Article 50 duty is served, and
  the provisions are cited without norms; Article 2(2) limits only what
  that classification brings, so the Annex III rules are still checked and
  a match decides the route, the FRIA and the Article 50 duties; while its
  Annex III facts are unknown the answer requires human review and names
  them. While the section is unknown and the Article 6(1) route alone
  holds, the Chapter III requirements are served and the fact is named.
  Every high_risk answer names the routes that hold (high_risk_routes:
  Article 6(1) with Annex I, Article 6(2) with Annex III), and every
  classification and every served requirement group carries the dates its
  provisions apply from, by those routes (both points of Article 113(c)
  when both hold; the requirement groups of a Section B product on the
  Annex III route, and every provision its classification cites but
  Article 6(1) and Annex I, carry point (c)(i) only, because Article 2(2)
  excludes Chapter III on the Article 6(1) route), from the reviewed table of
  Article 113 as amended (mcp_server/application_dates.py: an Annex dated
  through the Article that brings it into application, a wording the
  Omnibus inserted or replaced no earlier than 27 July 2026, Article 111(4)
  a note on Article 50(2)), as data; every answer names the text it
  follows. The elicitor prompt is v7, the extraction scope holds Article 4a
  (424 core source units), the dev norms and alignments keep only those on
  units unchanged in force, and gates PUBLICATION_GATE3 and PUBLICATION_GATE4 refuse a norm or alignment
  on a deleted unit, as the evaluation harness refuses a test-set item
  citing one.

## 12. Evaluation
OVR-10. grounded_by: REF-15, REF-16, REF-17, REF-18, REF-24

- Ablation ladder: plain LLM, vector RAG over Act chunks, graph without judge,
  graph plus build judge, graph plus build and runtime judge, graph plus
  runtime judge only (six conditions; the sixth added by B126).
- Primary dataset: the open AI Act Evaluation Benchmark (REF-15), covering
  classification, article retrieval, obligation generation, and QA. Verify its
  coverage against the high-risk core first.
- Hand-built gold set: around 60 to 80 items on the high-risk core, each
  labelled by two annotators independently and their disagreements
  adjudicated by a person who did not produce them (spec G Sections 6 and
  10.4); report the agreement before adjudication with a chance-corrected
  statistic. A label comes from the Act, never from the classifier, whose
  answer is what the ablation scores.
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

- MILESTONE1 (DONE 2026-07-08) Structural mirror plus versioning plus coverage_report. Deterministic Layer
  1 over the full Act from the frozen EUR-Lex HTML manifestation (Section 6;
  Formex point-depth deferred to MILESTONE2); Omnibus modelled as an amending
  source; source_trace and coverage_report tools. Demo UI increment: a single
  page rendering the coverage matrix and a browsable Act structure (first
  screenshot artifact).
  Build order for MILESTONE1: (1) freeze the HTML snapshot and derive the ID scheme from
  its anchors (ingestion spike done, Section 6); (2)
  apply the version pin (Section 11); (3) write schema/json_schemas/ first, since
  Section 2 declares them the machine-readable source of truth; (4) Neo4j plus
  Cypher constraints; (5) the deterministic parser and cross-reference resolver;
  (6) the CI tag-checker that generates docs/traceability.md and fails on a
  missing @implements or an unknown REF id. Write the acceptance fixtures
  (113 / 180 / 13; Chapter III Section 2 equals Articles 8 to 15; Article 6 links
  Annexes I and III; Article 11 links Annex IV) first, as the target.
- MILESTONE2 (DONE 2026-07-08; v1-slice migration replaced by regeneration through the
  judged pipeline per user decision, regression fixture from the new graph)
  High-risk-core normative graph plus reified alignments plus build judges.
  Layers 2 and 3 over the v2 core only. Migrate the existing v1 slice (Articles
  9, 10, 13, 14, 15 and the seven HLEG nodes) into the new judged, reified
  pipeline; keep the old poster query as a regression fixture.
- MILESTONE3 (DONE 2026-07-08/09 for the four journey tools, facade, MCP, demo flow;
  explain_requirement and trace_alignment in progress, tasks 41-42)
  Runtime tools plus runtime judge. classify_ai_system,
  get_applicable_requirements, evaluate_project_evidence,
  generate_control_backlog, end-to-end audit log. Demo UI increment: the full
  demo flow (describe system, see classification, requirements with citations,
  evidence evaluation, judge verdicts), screenshot-ready for the tool paper.
- MILESTONE4 (harness DONE, first two live sweeps run 2026-07-08/09; open: full gold
  set authoring, judge FA/FR labeling, full-benchmark run, variance study)
  Evaluation harness plus gold set plus ablations.
- Deferred to post-thesis / v2.1: GPAI deep extraction, standards mapping (TAIR),
  full-Act deep extraction, the trust/HCI study.

Paper mapping (RES-3): MILESTONE1 to MILESTONE3 produce the tool/method paper (RE or SE venue);
MILESTONE4 produces the empirical ablation paper (empirical SE venue); together they
feed the integrative journal article. A legal-informatics paper (deontic
extraction plus reified alignment) and a trust/HCI calibrated-reliance study are
stretch, not on the critical path.

## 15. Highest-risk components and open decisions

Highest-risk components (evaluate explicitly, do not fold into general numbers):
- Evidence evaluation (does artifact X satisfy requirement Y) is the most novel
  step and the least de-risked by prior work; the siblings do generation and
  mapping, not evidence evaluation, so there is no external accuracy baseline.
- Applying the Omnibus amendments to the base text deterministically is fiddly.
- The end-2026 timeline is tight even scoped; protect MILESTONE1 to MILESTONE3, the tool paper,
  and one evaluation paper.

Open decisions:
- OPEN-JUDGE: RESOLVED 2026-07-08. OpenAI generator plus an independent
  non-OpenAI judge (Anthropic Claude); see Section 7.
- OPEN-VENUE: exact target venue and deadline per planned paper.
- OPEN-LICENSE: RESOLVED 2026-07-23. Server and all code AGPL-3.0-or-later
  (LICENSE at the repo root); graph metadata CC BY 4.0
  (data/graph_dumps/LICENSE); EU legal text under EU reuse terms (no ownership
  claimed, quotes byte-exact); ALTAI redistribution still needs its license
  check before the ethics layer ships ALTAI items (task C2).
- OPEN-STANDARDS: standards mapping (TAIR) deferred to v2.1.

Sources to verify before the thesis (see references.md [VERIFY] tags): the
Omnibus final OJ citation, the Institutional Grammar primaries (REF-14c), the
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
  verify: src/parse_legal_structure/ has no model calls; tests assert 119/180/14
  for the Act in force (tests/integration/test_acceptance_in_force.py) and
  113/180/13 for the 2024 parse (tests/integration/test_acceptance_m1.py).
- DEC-02: cross-references resolved by rule first. Engineering MUST (determinism);
  corroborated by REF-26, REF-29.
  Defense: references are exact pointers, so rule resolution is deterministic;
  references and conditionals are also the highest-error zone for LLMs.
  verify: src/resolve_crossrefs/ rule pass plus AMBIGUOUS queue; crossref test.
- DEC-03: NormativeStatement first-class, Institutional Grammar. grounded_by REF-11,
  REF-12, REF-13. Defense: deontic-KG practice; an article holds many norms.
  verify: src/extract_norms/ emits norm nodes; norm_extraction test.
- DEC-04: actor inferred via Article 16, canonicalised. grounded_by REF-11, REF-12.
  Defense: multi-party texts cause object/actor misidentification.
  verify: src/canonicalize/ actor table; actor_inference test.
  Amended 2026-10-09 (B145, DEC-27): the closed table is
  schema/act_parties.json, the Act's parties; src/canonicalize/canonicalizer.py's
  canonicalize_actor reads it through tere4ai.act_parties.place; the 13-value
  table is gone.
- DEC-05: reified AlignmentAssertion nodes. grounded_by REF-24, REF-21, REF-10.
  Defense: a mapping is an auditable claim, not law; store-portable.
  verify: src/align_hleg/; query for accepted mapping without evidence returns zero.
- DEC-06: dual/triple judges. grounded_by REF-16, REF-24, REF-27.
  Defense: unjudged legal grounding is only 50 to 68 percent correct.
  verify: src/judge/ three entry points; runtime_grounding test asserts no answer without a verdict.
- DEC-07: OpenAI generator, independent non-OpenAI judge (decided 2026-07-08).
  grounded_by REF-24.
  Defense: same-family judge failure modes correlate; an independent judge
  family strengthens the control and the thesis claim.
  verify: eval/config_evaluated.yaml records generator and judge models.
- DEC-08: calibrated vocabulary, never "compliant". grounded_by REF-16, and the
  legal non-goal (Section 0). Defense: measured grounding limits and the legal
  caveat make any certified-compliance claim unsupportable.
  Scope (decided 2026-07-21, characterization corrected 2026-07-30): the ban
  covers all system-generated fields, including model-generated backlog
  titles. Exempt fields fall in two categories: (a) byte-exact
  quotes-of-record (frozen source span text and corpus or evidence quotes),
  preserved byte-for-byte because that is the traceability guarantee; and (b)
  normalized deontic extractions (norm action and object, DEC-03), exempt as
  extracted regulatory content carrying the regulator's vocabulary but NOT
  asserted byte-exact. Exempt fields are structurally marked via
  VERBATIM_QUOTE_FIELDS in mcp_server/tools.py and are never presented as a
  system verdict.
  verify: MCP output enum lacks compliant/certified; no_compliance_claim test;
  tests/unit/test_banned_term_scope.py encodes the scoped contract.
- DEC-09: Neo4j primary plus RDF export. grounded_by REF-21, REF-22, REF-08, REF-25, REF-23.
  Defense: edge-native provenance and a reject-not-infer task fit property graphs.
  verify: graph_store/ uses Neo4j; rdf_export_roundtrip test.
- DEC-10: full structural mirror, deep only on high-risk core. grounded_by
  REF-17, REF-15, ADD-24.
  Defense: value and benchmarks concentrate on the high-risk regime.
  verify: coverage_report shows full Layer 1, Layer 2/3 only on Section 10 set.
- DEC-11: reuse open benchmark plus sibling baselines. grounded_by REF-15, REF-16, REF-17.
  Defense: an open benchmark covers our tasks; siblings are the baselines.
  verify: eval/ loads REF-15; src/tere4ai/eval/strategies.py implements the
  vector-RAG and no-judge baseline conditions.
- DEC-12: Omnibus modelled as an amending, versioned source. grounded_by REF-02, REF-04.
  Defense: it is adopted and changes the in-force text and the dates.
  Amended 2026-10-03 (B132, DEC-23): the Omnibus is no longer kept apart
  from the base text. Layer 1 is the Act as amended, and the Omnibus
  SourceDocument records the merge (merged_into_base true, merged_on,
  marker_list_sha256); the parse enforces the checks and gate PUBLICATION_GATE6 verifies
  the build's record of them.
  verify: SourceDocument for COM(2025)836 with AMENDS/HAS_VERSION;
  tests/unit/test_sources.py, tests/unit/test_in_force_build.py.
- DEC-13: feature elicitation splits fact extraction from decision (added
  2026-07-09). Engineering MUST (the trust split of Section 0: the LLM never
  decides classification); corroborated by REF-17, REF-16.
  Defense: free-text inputs need facts extracted before rules can run; the
  elicitor emits only schema-valid facts with textual support, omits unknowns,
  and never outputs a risk category, so the deterministic ladder and its
  missing_facts guard stay the sole decision path. Since prompt v6 (B10,
  2026-10-02) the textual support is checked by code: each fact, true or
  false, keeps only with a quote of at least three words that is found in
  the description as whole words (character identity after collapsing
  whitespace runs, no case folding, a match starting and ending at a word
  boundary); any other fact is dropped and named (the answer's dropped list
  and missing_facts), a field the model sets to null or to an empty list is
  unknown and removed without a dropped entry, and the answer carries each
  kept fact's quote with its offsets. Code checks that the words are there;
  a person judges whether they support the fact.
  verify: src/tere4ai/elicit_features/ never outputs a classification; flags
  without textual support omitted; elicitor.elicit drops an unquoted fact
  (tests/unit/test_elicit_features.py); elicitation-vs-abstention measured in the
  ablation artifacts (eval/results/FULL_RUN_ANALYSIS.md, docs/variance_study.md;
  earlier sweep in eval/results/RUN2_ANALYSIS.md).
- DEC-14: FRIA applicability (Article 27(1)) decided by a deterministic rule,
  never a model (added 2026-07-20). Engineering MUST (the same trust split as
  DEC-13); the rule mirrors the operative sentence of the frozen source text
  (REF-01); corroborated by REF-30, whose rule-based checker also treats FRIA
  applicability as form-decidable.
  Defense: Article 27(1)'s trigger is a closed set of structured facts (the
  Article 6(2) route, the Annex III point 2 exception, the two deployer
  categories, Annex III points 5(b) and (c)), so applicability is
  rule-decidable; only the obligation's applicability is decided, never the
  assessment's content (scope decision 2026-07-20: TERE4AI will not generate
  FRIA content), and unsettled facts yield "unknown" with each missing fact
  named, including a pending Article 6(3) derogation candidacy. The
  application date rides on the block as data (applies_from), never as
  control flow. Amended 2026-10-04 (B132): the date is Article 27's row of
  the reviewed table of Article 113 as amended (application_dates.py,
  point (c)(i)), the table every classification and requirement group
  reads.
  Added 2026-10-02 (B125): on a limited_risk or minimal_risk answer, an
  unknown Annex III fact that could make Article 27(1) apply keeps the
  answer unknown and is named in the block's missing_facts (the point 2
  area is excepted by Article 27(1); other areas whose trigger is the
  deployer count only until the deployer is known to be neither category;
  points 5(b) and 5(c) count for any deployer); the level, the status and
  the envelope's missing_facts do not change. Widened the same day (B125
  final review, R5): the same reading holds on a high_risk answer through
  the Article 6(1) route only or in the point 2 area only, once the point
  5(b) and 5(c) facts are known false.
  verify: src/tere4ai/mcp_server/fria.py (no model imports); classify answers
  carry the fria block and get_applicable_requirements passes it through;
  tests/unit/test_fria.py.

- DEC-15: requirement-to-code traceability for consumer projects, stored in
  the code and generated on demand, never hand-maintained (added 2026-08-24).
  Engineering MUST (traceability and no-silent-degradation, Section 13; the
  same generated-record rule as Section 17); corroborated by ADD-14 (the
  traceability problem) and ADD-15 (trace links decay unless maintained with
  the artifact they describe).
  Defense: a consumer marks code with `@implements: <norm-id>` tags; the link
  lives in the code so it moves with refactors and shows in diffs, and the
  requirement-to-code matrix is generated per call by joining tags against
  the graph, so it cannot drift. Scanning is client-side (the server never
  reads a consumer filesystem, Section 8); the server validates every cited
  id against the judge-accepted set, so tags citing review-queue, rejected,
  or invented ids are reported and never joined, preserving the review
  queue's exclusion guarantee. A trace is a developer claim, not evidence:
  rows say traced or untraced, never an evidence status, and the evidence
  path remains evaluate_project_evidence (DEC-08 ladder).
  verify: src/tere4ai/mcp_server/trace_code.py and src/tere4ai/trace_scan/
  (no model imports); trace_implementation MCP tool in server.py;
  tests/unit/test_trace_code.py.

- DEC-16: every build command writes an execution record; a frozen
  campaign's decisions are materialised once into a reference file;
  publication writes the chain record only after the post-load gates and
  activation is explicit (added 2026-09-19, revised 2026-09-20; spec G
  D-G20, D-G21, D-G27 in the private research repository). Engineering
  MUST (reproducibility, traceability, no silent degradation, Section 13);
  corroborated by ADD-20 (PROV activities link used entities to generated
  entities) and REF-27.
  Defense: a build in progress has no build id, so it is named by a stable
  record id holding one execution record per command attempt (run id, the
  steps covered, start, end, heartbeat, inputs and outputs by digest,
  models, prompt hashes, sampling, usage, counts, one outcome per gate);
  checkpoint lines carry the run id and a resume validates the inputs and
  configuration it inherits; an expired heartbeat is reported as liveness
  unknown, never as failed; the dump slug is an alias resolving to the
  newest record; a published record is frozen and later work continues as
  a descendant. Human decisions enter the graph through
  scripts/materialize_reference.py, which applies a freeze's decisions
  exactly once (apply_decisions then canonicalize_norms) into a new file
  whose build block records the freeze manifest's identity and coverage,
  after checking the manifest against its typed schema, its digest and
  the build the freeze was taken on; the pristine dump is never edited and
  nothing is overwritten. publish_layer23 binds every human-gated layer to
  exactly one freeze manifest, verifies that the alignments were computed
  over the norms file it is given, runs the gates, records the Neo4j
  target as loading, loads, runs the post-load gates, and only then writes
  build_chain_<id>.json (published_at, per-gate outcomes, gating per layer,
  the whole-build label llm-gated or human-adjudicated, or none for an
  intermediate or partial build) and publications/<id>.json; several
  manifests enter the chain id order-independently.
  Publication also gives the build its build number (added 2026-09-27,
  spec G D-G50 in the private research repository): under a numbering lock
  taken after the post-load gates, 1 above every number held by the build
  records, the counter build_records/numbering.json, the publication
  manifests and the chain records of the dump directory, refused when the
  counter is absent and one of them cannot be read; the publication is dated
  under the same lock, and the number is written into the chain record, the
  frozen record and the manifest, never reused and never changed. A chain a
  record already published is refused again even when its chain record or
  manifest is gone. Numbers are per dump directory; the chain records and
  manifests that carry them are tracked, so a lost build_records/ never
  lowers the next number. The builds list row carries the number, the build
  id and manifest_present (derived, beside served).
  BUILD_CHAIN_CURRENT.txt records the latest publication and selects
  nothing; scripts/activate_build.py
  verifies the publication's files and writes the activation pointer; the
  facade (at startup) and the MCP server (once per tool call) load through
  one loader and serve the pointer's build, a drifted file refusing
  service. GET /api/builds and GET /api/builds/{ref} serve the records per
  request, every field marked recorded, derived or unavailable with a
  reason, with an observation time; builds made before this decision are
  synthesised from their artefacts with nothing invented, matched to a
  chain record by their full input set. Contract with the dashboard:
  schema/json_schemas/build_record.schema.json and
  tests/fixtures/build_records/. Tests: tests/unit/test_build_record*.py,
  test_checkpoints.py, test_parse_cli_record.py, test_materialize.py,
  test_publish_layer23.py, test_publication.py, test_present.py,
  test_builds_routes.py, test_build_numbers.py,
  test_write_publication_manifest.py.

- DEC-17: every measurement run of the Evaluate steps E1 (judge error
  rates) and E6 (benchmark, ablations, variance) writes one immutable
  evaluation record, and the July 2026 measurements are presented as
  legacy records that state only what their files state (added
  2026-09-23; spec G D-G33, D-G34, D-G39, D-G44 in the private research
  repository). Engineering MUST (reproducibility, traceability, no silent
  degradation, Section 13); corroborated by ADD-20 (PROV activities link
  used entities to generated entities) and REF-27.
  Defense: a measurement the record cannot tie to the exact files it
  measured cannot be a thesis figure. Each record names the step and the
  kind of act, the command line with key material scrubbed, start and
  end, origin (recorded, legacy) and outcome (completed, partial, failed)
  as two fields, the digests of every file read plus the publication
  observed at start, the models with prompt versions and hashes, the
  sampling and usage, the strategy, metrics and code versions, the
  outputs by digest with an immutable copy of their bytes (the harness
  and the ablation runner overwrite deterministic filenames), and the
  relations to other records (a repeat, a resume, a comparison, the
  sample id of the E1 acts). E1 is three recorded acts: the draw under an
  immutable sample id, refusing to overwrite any existing sheet without
  --force; the label act, recording who labelled each item and when; the
  analysis over the exact labelled bytes, with rates per judge kind and
  pooled, null on an empty denominator, worded "sample estimate",
  unweighted by decision with each stratum's population and sample
  counts beside them (spec G D-G82 (10)). Two free read-only routes
  serve the records grouped by build identity; an
  unreadable file is its own row and an outage is an outage, never an
  empty list. The builds list carries the lineage relationships the
  dashboard joins on, and the units and trace routes carry the judge
  run's completed time and prompt hash where the dump records them.
  Consequence: eval records live under data/graph_dumps/evaluation_records/
  (git-ignored like the build records); the compatibility files keep
  being written where they are; metrics.judge_error_rates returns None
  on an empty denominator (METRICS_VERSION metrics.v2).

- DEC-18: the classification answer says "not known" for a prohibition it
  cannot settle, and a high-risk answer keeps its Article 50 duties (added
  2026-10-01; extended 2026-10-02, B123; thesis tasks B36.1 and B36.2,
  brief sdd/2026-10-01-B36-classifier-answer/brief.md in the private
  research repository). Engineering MUST (no silent degradation, Section
  13; the same missing_facts discipline as DEC-13 and DEC-14); the rules
  mirror the frozen source text (REF-01): Article 5(1) points (a) to (h)
  with their statutory qualifiers, and Article 50(6), under which the
  transparency obligations "shall not affect the requirements and
  obligations set out in Chapter III"; the Omnibus points (ba) and (bb)
  are grounded in the amending source (REF-02, DEC-12), cited as today
  through its SourceDocument with the applies-from date as data.
  Defense: false and unknown do not mean the same thing, and a reader of
  `prohibited: false` beside an unresolved Article 5 fact is told
  something the rules never established. Each Article 5 path is resolved
  on its own: proven (its flag true, for point (h) both
  real_time_remote_biometric_public and law_enforcement_use true, and,
  where the point has an exculpating fact, that fact known and not
  exculpating), ruled out (its flag false, for point (h) either fact
  false; or its exculpating fact known and exculpating), or unresolved (a
  fact it needs is missing). An exculpating fact rules out a path whose
  flag is absent only where it is the statute's complete element: points
  (a) and (b) (causes_significant_harm false), (c)
  (social_score_detrimental_treatment false), (f)
  (emotion_recognition_medical_or_safety true) and (h)
  (rtrb_strictly_necessary_authorised true); the point (d) and (g)
  exception facts do not, because their definitions were wider than the
  Act's exceptions (Codex review of this decision, finding 2) and an
  answer of "no" must not rest on them, and points (e), (ba) and (bb)
  have no exculpating fact. `prohibited` is true when a path is proven,
  null when none is proven and any is unresolved, false only when every
  path is ruled out; the rejected-input answer, where no rule ran, gives
  null. The same resolution decides the existing status lowering and the
  uncertain exit, so an answer never says false beside "unknown
  prohibition-relevant flags". null rather than a string, so a client that
  tests the field for truth reads unknown as "not known to be prohibited",
  never as "prohibited"; a reader still shows null as unknown, never as
  no. The Article 6(1) route is resolved the same way (B123, 2026-10-02;
  spec G D-G59 in the private research repository): proven when
  annex_i_covered_product and third_party_conformity_assessment_required
  are both true, ruled out when either is known false, open otherwise; an
  open route's unknown fact is named in missing_facts on every exit but
  the rejected-input one (the third-party assessment only once the product
  is known to be covered by Annex I), turns the last exit to uncertain
  instead of minimal_or_none, and lowers the Article 50 exit's status; a
  medical or safety component with the Annex I fact unknown holds the
  answer at uncertain only while the route is open.
  "uncertain" is an assessment state (facts the rules need are missing),
  never a legal risk level. The answer carries `transparency_duties` on
  every exit: the Article 50 paragraph nodes whose trigger fact is true,
  listed on every exit except the prohibited and rejected-input ones,
  where it is empty (an empty list means none triggered by a known fact,
  never ruled out). A listed paragraph is triggered, not proven: the
  paragraphs' own exceptions (an interaction obvious to the person,
  assistive editing, uses authorised by law to detect, prevent,
  investigate or prosecute criminal offences in 50(1) and 50(2), uses
  permitted by law to detect, prevent or investigate criminal offences in
  50(3)) and paragraphs 4 and 5 are not decided by the
  rules, and the answer says so in legal_status_notes. The triggers are 50(1)
  interaction with natural persons, 50(2) synthetic content, and 50(3)
  emotion recognition or a biometric categorisation system. Biometric
  categorisation is three facts, one per provision, each defined in the
  schema and the elicitor by the Act's own words (Jose, 2026-10-01):
  biometric_categorisation_system (Article 3(40); the 50(3) trigger), a
  fact for categorisation by sensitive or protected attributes (Annex III
  point 1(b); a high-risk rule beside point 1's others), and the existing
  biometric_categorisation narrowed to the traits Article 5(1)(g) lists.
  The point (d) and (g) exception facts are redefined by the Act's text
  ("directly linked to a criminal activity"; labelling or filtering of
  lawfully acquired biometric datasets, or categorising of biometric data
  in the area of law enforcement), and the elicitor's prompt takes a new
  version (v5). Since v6 (B10, 2026-10-02) the prompt quotes no provision
  by hand: each provision it shows is the node text of the build the call
  is served on, read from the graph at call time after its source span is
  verified against the frozen snapshot, and a provision that does not
  resolve stops the call before any model call. risk_category
  keeps its values: transparency_only stays reserved for Article 50
  without high-risk. An absent Article 50 trigger fact is named in
  missing_facts on the high-risk and minimal exits without changing the
  status or the category (Jose, 2026-10-01: "Keep minimal, name the
  fact"). get_applicable_requirements keeps serving the whole Article 50
  group to every high-risk system: the triggers do not cover every
  paragraph (50(4), 50(5)), so the requirements stay on the conservative
  side and the answer's list is the side triggered by known facts.
  verify: src/tere4ai/mcp_server/classify.py (per-path Article 5
  resolution, _unresolved_article_6_1_facts, transparency_duties);
  tests/unit/test_classify.py (the six cases of the brief, the
  ruled-out-by-exculpating-fact cases and the B123 cases);
  CHANGELOG.md names the contract change.

- DEC-19: every operator obligation or prohibition among the norms, and
  every generated control, carries its requirement type, functional,
  quality or process, the types of ISO/IEC/IEEE 29148:2018 clause
  5.2.8.3; the judges record their view of the type and never gate on it
  (added 2026-10-01; thesis task B65, brief
  sdd/2026-10-01-B65-requirement-type/brief.md revision 3 and its
  rulings file progress.md in the private research repository; thesis
  task B4 folded into the same prompt version). Research claim (the
  thesis reports the Act's obligations and the generated controls by
  type): grounded_by ADD-54 and ADD-55 (STD) and ADD-56 (PEER); ADD-57
  (STD) and ADD-58 (OFF) support; ADD-11 links regulatory rules to
  software requirements.
  The types. One field, requirement_type, holding three of the examples
  of the requirements type attribute in 29148 clause 5.2.8.3 ("Examples
  of the requirements type attribute", printed pp. 15 and 16, ADD-54).
  The clause gives examples, not a closed list; this project uses three:
  functional: "Functional/Performance. Functional requirements describe
  the system or system element functions or tasks to be performed by the
  system." (p. 15); the vocabulary standard defines a functional
  requirement as "1. statement that identifies what results a product or
  process shall produce 2. requirement that specifies a function that a
  system or system component shall perform" (ADD-55, 3.1704, p. 195).
  Here: the AI system or one of its elements shall perform a function or
  produce a result (Article 12(1): the system technically allows the
  automatic recording of events).
  quality: the type 29148 names Quality (Non-Functional) Requirements,
  whose entry reads "Include a number of the 'ilities' in requirements to
  include, for example, transportability, survivability, flexibility,
  portability, reusability, reliability, maintainability and security."
  (p. 16); 24765 defines a quality requirement as a "requirement that a
  software attribute be present in software to satisfy a contract,
  standard, specification, or other formally imposed document" (ADD-55,
  3.3287, definition 1, p. 364). Here: the system or its data shall have
  a property or meet a level (Article 15(1): accuracy, robustness and
  cybersecurity; Article 10(3): data sets that are relevant and
  sufficiently representative). Applying the definition, which speaks of
  "a software attribute" present "in software", to the training,
  validation and testing data is this project's reading beyond the
  source.
  process: "Process Requirements. These are stakeholder, usually
  acquirer or user, requirements imposed through the contract or
  statement of work." (p. 15). Here: the obligation constrains the
  operator's activities, organisation or records rather than the AI
  system or its data, as project requirements "constrain the project
  that constructs the software." (ADD-57, Software Requirements 1.3,
  p. 1-3), extended to the operator's activities after development
  (deployment, use, monitoring, reporting): Article 17's quality
  management system, Article 19's keeping of the logs, Article 72's
  post-market monitoring. The clause's sentence that process
  requirements include compliance with national, "state or local laws,
  including environmental laws, administrative requirements,
  acquirer/supplier relationship requirements and specific work
  directives." (p. 16) is not read as making every legal obligation a
  process requirement: the type follows what the obligation constrains,
  not where it comes from.
  Process is a peer of functional and quality, never a kind of
  non-functional: "As project and process requirements are conceptually
  different from system requirements, they should be distinguished at
  the root level and not in a sub-category such as non-functional
  requirements." (ADD-56, Glinz, section 4.2, p. 24); SWEBOK V4.0a's
  "Figure 1.2. Categories of Software Requirements" (ADD-57, p. 1-4)
  places project requirements beside product requirements at the root.
  The Commission's standardisation request for the Act separates
  "requirements applicable to high-risk AI systems or process
  requirements" (ADD-58, Annex II, section 1, p. 4); it is cited for that
  separation only, since it splits by provision and not obligation by
  obligation as this decision does. 29148's other examples are read as
  follows: interface as functional; usability and human factors as
  quality. On screen: "functional", "quality (non-functional)",
  "process".
  Scope. A norm carries a type when it is an obligation or a prohibition
  whose source unit is in a requirement group
  (src/tere4ai/mcp_server/requirements.py _is_requirement_group: not
  Articles 5 to 7, not the annexes) and whose actor, explicit or inferred
  (DEC-04), is an operator: one of the actorRole values provider,
  deployer, importer, distributor, authorised_representative,
  product_manufacturer, operator_general and unspecified_needs_review
  (norms.schema.json). (Amended 2026-10-09, B145, DEC-27: from
  extract_norms v5 the condition reads the addressee's value of
  schema/act_parties.json: the six AI Act roles and the two sentinels,
  operator_general and unspecified_needs_review; an addressee the list
  cannot place is unsettled and in scope; a norm addressed to an
  authority, a body, an institution or a person carries null. Runs under
  v1 to v4 read the condition as written above, frozen in
  src/tere4ai/extract_norms/scope_first_reading.py, because the scope is
  applied to the candidate before the judge sees it.) A norm carries null, shown "not an operator
  requirement", whatever the extractor proposed, when it is not an
  obligation or a prohibition (a definition, a right, a permission, an
  exemption), when its source unit is outside the requirement groups, or
  when it is addressed to someone who is not an operator: the
  commission, the ai_office, a member_state, a notifying_authority, a
  market_surveillance_authority, a notified_body, or an affected_person. The field is nullable in norms.schema.json, so
  an extractor reply that omits it is never dropped for that reason
  (today a schema failure drops the norm).
  Reading a norm. By the outcome the obligation constrains, not by its
  main verb: obligations that require the system to be designed and
  developed so that an outcome holds (Articles 13(1), 14(1), 15(1)) are
  typed by that outcome, not by the verb. A required level of a function's output is quality when
  the obligation is about the level (Article 15(1)). A duty to draw up,
  keep, update or submit documents or logs is process (Articles 11(1),
  18, 19, 47, 49); a required content of what is delivered with the
  system (the instructions for use, Article 13(2) and 13(3)) is
  functional, a result the product shall produce (24765 3.1704,
  definition 1). A typed norm has exactly one type; an obligation that
  mixes a system function and an operator process takes the type of the
  outcome it mainly constrains, and the annotators' agreement (spec G in
  the private research repository) measures how often that is contested.
  Norms. The extractor proposes the type with the slots; the extraction
  judge records whether it agrees and, when it does not, its own type,
  in two fields beside its verdict. The type never changes acceptance:
  the verdict rests on the six checks of Section 7 as before, so the
  Layer 2 counts and the judge error rates keep measuring what they
  measured, and type agreement is reported apart. The two fields are
  optional for the verdict: a judge reply that omits them or gives an
  invalid value keeps its verdict, and the recorded view is null; on a
  norm whose type the scope set to null the judge records nothing. The
  recorded view is compared with the adjudicated human type of the
  matched norm (the Layer 2 adjudication, spec G in the private research
  repository) and reported beside the judge error rates (E1) as judge
  type agreement: Cohen's kappa and percent agreement over the in-scope
  matched norms. Both prompts carry the
  definitions above and move together to extract_norms v2 and
  judge_norms v2 (they share one version). The same v2 carries thesis
  task B4: the judge's input gains the verbatim text of the
  actor-inference source unit (DEC-04), so an inferred actor is judged
  against the paragraph it came from. The type is stored on the norm,
  loaded into Neo4j, served by get_applicable_requirements,
  explain_requirement and the facade's units list, and carried by the
  human review lists, so the annotators keep, edit or add it as one more
  closed slot.
  Controls. The backlog generator writes each control's own type, never
  copied from the norms it cites: from Article 19's process obligation
  (the provider keeps the logs) come a functional control (the logging
  subsystem retains records for six months) and a quality one (retained
  records resist tampering). The generator's input digest leaves out the
  norms' types, so nothing invites a copy; a control and its norms stay
  linked by norm_ids. _clean_items keeps a control whose type is missing
  or invalid, with null and a note; _group_items merges by norm set as
  today and the merged control keeps the first item's type. The runtime
  judge records its view of each control's type; the backlog's verdict
  does not depend on it. That view is optional in the same way: a reply
  that omits it or gives an invalid value keeps its verdict and records
  null, and on a control whose type is null the judge records nothing.
  It is compared with the specialists' yes or no on "Is the control's
  type right?" and reported beside the runtime judge calibration (E5). generate_backlog and runtime_grounding move
  together to v2; evaluate_project_evidence keeps evaluate_evidence v1
  and runtime_grounding v1, its version no longer shared with the
  backlog's.
  Inspection. Code inspection follows the norm's type: functional and
  quality norms offer it; a process norm offers none and states the
  evidence it needs. Code tags cite norm ids (DEC-15) and no control is
  traced, so neither a process norm nor any control offers inspection. The
  consumer dashboard's hand-made per-article kind is retired in favour of
  this field.
  Defense: the thesis frames the Act's obligations as requirements, so
  the classification it reports must carry the requirements engineering
  standard's definition, not the author's hypothesis the per-article kind
  rested on; the type is set per obligation, not per article, because
  articles mix types (Article 15(1) asks for a quality of the system,
  15(4) for technical and organisational measures that are partly the
  operator's process). Recording the judges' view without gating keeps
  every verdict and every measured judge error rate comparable with the
  checks they had, and makes type agreement a figure of its own.
  verify: schema/json_schemas/norms.schema.json (requirement_type,
  nullable, three values); prompts/extract_norms/v2.md,
  prompts/judge_norms/v2.md, prompts/generate_backlog/v2.md,
  prompts/runtime_grounding/v2.md; src/tere4ai/extract_norms/pipeline.py
  (the field kept, the scope applied, the inference-source text in the
  judge's input), src/tere4ai/graph_store/layer23.py,
  src/tere4ai/mcp_server/requirements.py, explain.py and backlog.py,
  src/tere4ai/judge/runtime_grounding.py; tests/unit/test_extract_norms.py,
  test_get_requirements.py, test_backlog.py, test_runtime_grounding.py
  and test_review_queue.py; CHANGELOG.md names the contract change.

- DEC-20: the classifier's levels and its yes or no field are named as the
  Commission's risk pyramid names them, one name everywhere (added
  2026-10-02; thesis task B118, brief
  sdd/2026-10-02-B118-level-names/brief.md revision 2 and spec G D-G60 in
  the private research repository). Engineering decision (one vocabulary
  between the answer, the screens and the thesis; no rule changes). The
  stored values are unacceptable_risk, high_risk, limited_risk,
  minimal_risk and undetermined (facts missing, not a level; DEC-18),
  replacing prohibited, high_risk, transparency_only, minimal_or_none and
  uncertain; the answer's field prohibited becomes unacceptable_risk
  (true, false, null). Tokens a program reads (risk_category, the field,
  the rationale's rule names) carry the stored value; sentences a person
  reads (the FRIA rationale, the requirements messages, the status lines,
  errors, the tool description) carry the shown name: Unacceptable risk,
  High risk, Limited risk, Minimal risk, "Undetermined: facts missing"
  (src/tere4ai/mcp_server/levels.py LEVEL_NAMES, level_name). Limited risk
  means Article 50 transparency obligations apply and the system is
  neither prohibited nor high-risk on the facts given; the Commission's
  policy page now heads that box "Transparency risk" (the 2021 pyramid
  and practitioner tools say Limited). The benchmark's own labels (REF-15)
  are kept; BENCHMARK_RISK_MAP maps them to the new values. Result files
  written before the rename are read through LEGACY_LEVEL_VALUES only
  when marked so (--legacy-levels), so the July numbers reproduce; fresh
  answers are scored as given; old stored answers are not converted and
  an unknown value renders as not classified. The evaluation's shared
  prompts (eval/strategies.py: the system prompt every model condition
  sends, the item question the plain LLM and vector RAG conditions
  classify from) ask for the new values, a change to a B74 instrument
  made before B74. Defense: a reader met two vocabularies for one thing;
  the pyramid's names are those the Act's readers know.
  verify: src/tere4ai/mcp_server/levels.py (RISK_CATEGORIES, LEVEL_NAMES,
  LEGACY_LEVEL_VALUES, level_name), requirements.py, fria.py,
  report/render.py, eval/harness.py, eval/metrics.py (current_level),
  scripts/ablation_deepdive.py, scripts/variance_report.py and
  scripts/elicitation_error_report.py (the three --legacy-levels
  readers); tests/unit/test_classify.py
  (test_levels_are_the_pyramids_names), test_fria.py,
  test_get_requirements.py, test_report.py; CHANGELOG.md names the
  contract change.

- DEC-21: each norm's target_system_category names the part of the
  Act's rules the norm belongs to, by the category of AI systems those
  rules govern; a rule sets it from the norm's source Article or Annex,
  never a model, under every prompt version (added 2026-10-03; thesis
  task B124, brief sdd/2026-10-02-B124-target-system-category/brief.md
  revision 2, its rulings file progress.md and spec G D-G62 in the
  private research repository). Engineering decision (one closed set
  named after the Act's own scope terms, REF-01; it replaces a label the
  extractor wrote from examples, which grew to twelve values and null in
  the aborted run of 2026-09-01).
  The values: any_ai_system, "AI systems" as Chapter I, "GENERAL
  PROVISIONS", addresses them (Article 4: "Providers and deployers of AI
  systems shall take measures"); prohibited_ai_practice, Chapter II,
  "PROHIBITED AI PRACTICES"; high_risk_ai_system, Chapter III,
  "HIGH-RISK AI SYSTEMS", Annex III, "High-risk AI systems referred to in
  Article 6(2)", Annex IV, "Technical documentation referred to in
  Article 11(1)" with Article 11(1), Article 72 by its title and Article
  73 by its paragraphs 1, 9 and 10; article_50_ai_system, Chapter IV,
  "TRANSPARENCY OBLIGATIONS FOR PROVIDERS AND DEPLOYERS OF CERTAIN AI
  SYSTEMS". The value does not say which system a single paragraph talks
  about: Article 6(4) ("A provider who considers that an AI system
  referred to in Annex III is not high-risk shall document its
  assessment") is a high-risk classification rule, so its norms carry
  high_risk_ai_system; the addressee stays in the actor fields. Article
  3's definitions, those of general-purpose AI models included, are
  general provisions and take any_ai_system.
  The rule: one row per Article or Annex of the extraction scope
  (data/graph_dumps/core_nodes.txt, 30 ids, 424 source units of the Act
  as amended; 405 on the 2024 text; Article 4a joined with Chapter I's
  value under this rule, B132, 2026-10-04), each with
  the Layer 1 wording that decides it; the value is read from the
  Article or Annex segment of source_node_id, not from the Chapter
  edges. The pipeline sets it when it assembles a norm, after the judge.
  Under extract_norms v1 and v2 the extractor still writes a label, which
  the judge reads as before and the norm does not keep; extract_norms v3
  does not ask for it and the v3 judge's candidate does not carry it
  (judge_norms v3 is v2 under a new version line; the two share one
  version; v3 was the default and the version of record in
  eval/config_evaluated.yaml until B144, and DEC-26 makes v4 both). A norm
  on a unit outside the table carries null, counted as
  without_target_system_category in the extraction stats and the
  execution record; extending the scope means adding rows.
  The review apply step sets the rule value on a norm a person adds or
  replaces and refuses one on a unit outside the table. The judge's
  checks and verdict values do not change; the Layer 2 annotators never
  see or set the field; the judge label sheet no longer prints it. Old
  builds are not converted; readers pass the value through and nothing
  branches on it.
  Defense: a field a reader is shown needs a definition and a closed set;
  the Act's own titles give both, and a rule over the source Article
  gives every norm in the scope the same value on every run.
  verify: src/tere4ai/extract_norms/target_system_category.py
  (TARGET_SYSTEM_CATEGORIES, RULE_TABLE, category_for);
  schema/json_schemas/norms.schema.json (targetSystemCategory);
  prompts/extract_norms/v3.md, prompts/judge_norms/v3.md;
  src/tere4ai/extract_norms/pipeline.py and __main__.py,
  src/tere4ai/review_queue/apply.py, scripts/sample_judge_decisions.py;
  tests/unit/test_target_system_category.py (every core unit of the
  Layer 1 dump), test_extract_norms.py, test_extract_norms_cli.py (the
  mock-model command line run), test_review_queue.py,
  test_layer23_schemas.py, test_judge_sampling.py; CHANGELOG.md names the
  contract change.

- DEC-22: the public explanation of the MCP server has one source,
  docs/server/index.md, and its drift-prone parts are generated from the
  running server (added 2026-10-03; thesis task B90, brief
  sdd/2026-10-03-B90-public-source/brief.md revision 2 and spec G D-G65
  in the private research repository). Engineering decision (one text
  for every reader, kept equal to what a client is served; it needs no
  literature grounding, AGENTS.md grounding bar). What a client sees
  is read by starting the server over stdio with the official MCP Python
  SDK client: the connect-time instructions, the tool list (names,
  descriptions, annotations, input fields), and the answers of two free,
  deterministic calls, coverage_report (the notice and the answer
  fields) and classify_ai_system (the example call, made with the
  request the source itself shows). No model keys are passed in the
  server's environment, but a paid tool would read the repository's .env
  when called, so the guard is the client: after the tool list is read,
  every call goes through a wrapper that records it and refuses, before
  sending, any tool that is not one of those two or is not served with
  openWorldHint false. These
  fill marked regions of the source and the tool reference
  docs/server/tools.md; nothing that depends on which build is served
  (a build id, a count, a time) is written. README.md's first screen is
  generated from the marked README part of the source, SKILL.md's
  section on reading every answer from the matching part, and SKILL.md's
  sentence naming the paid tools from the served openWorldHint; the Pages site
  is built from docs/server/ alone, so no page holds a sentence that is
  neither the source nor generated. Free or paid is the served openWorldHint, and the generator
  refuses to run when it, the word PAID in the served description and a
  paid scope in keys.py TOOL_SCOPES disagree for any tool. Tests cover
  the sentences the regions cannot: every served tool name appears in the
  instructions and SKILL.md; no backticked name, and no snake_case word
  written without backticks, in the prose of the source or SKILL.md is
  unknown to the code (one third-party flag is allowed, with its reason);
  no sentence of prose holds a count (a number word one to twenty or
  "dozen", or a digit run that does not cite a provision or a layer and
  is not a version, a decimal or a number with its unit) with tool, tools,
  free or paid within the four words after it, or, for every count but
  "one", the four words before it (a count that refers back to tools
  named in an earlier sentence, "All 12 run over stdio", is not found); the non-legal-advice notice is
  NON_LEGAL_ADVICE_NOTICE word for word wherever it is shown, /llms.txt
  and /.well-known/tere4ai.json included; the source links outside the
  site's own pages by absolute URL only, and holds nothing from the
  private repository. Span
  start and end are stated as code points in the snapshot decoded as
  UTF-8, not bytes. Considered and not taken: hand-written tool sentences
  checked only for names (a second copy the checks cannot compare); a
  `_meta` key for cost (no client reads it, and TOOL_SCOPES already
  records which tools spend money); the in-process tool list alone (it
  skips the transport and the start-up a client goes through); GitHub
  Pages' own Jekyll build from docs/ (it would publish every file there).
  Defense: on 2026-09-26 the instructions named 9 of 11 tools and no
  check noticed, because the check read the tool list and not the
  sentence; a text generated from what is served, with tests on the
  sentences around it, cannot drift that way. Cost if wrong: the
  generator is one script and its regions are comments in Markdown;
  removing it leaves the text as last generated.
  verify: src/tere4ai/server_docs/ (reading the served surface over
  stdio, rendering the regions), scripts/gen_server_docs.py (`--check` in
  CI next to the traceability diff), docs/server/index.md, docs/server/tools.md,
  README.md and SKILL.md (the generated regions), mkdocs.yml and the CI
  docs job (strict build), src/tere4ai/mcp_server/tools.py
  (NON_LEGAL_ADVICE_NOTICE), web/src/lib/notice.ts;
  src/tere4ai/server_docs/prose.py (the names and counts rules on
  prose); tests/unit/test_server_docs.py (names, counts, notice, links,
  the generator's calls, `--check`), test_server_docs_prose.py,
  test_notice_one_source.py, test_span_offsets.py,
  test_duplicate_keys.py; CHANGELOG.md names the change.

- DEC-23: Layer 1 is the AI Act in force, parsed from EUR-Lex's
  consolidated text in Formex and checked unit by unit against the Official
  Journal wording of the act that enacted it, the 2024 wording kept as each
  changed unit's earlier version (added 2026-10-03; thesis task B132, brief
  sdd/2026-10-03-B132-omnibus/brief.md revision 3, its rulings file
  progress.md and spec G D-G68 in the private research repository).
  Engineering decision (determinism, traceability, no silent degradation,
  Section 13) on the legal sources: REF-01 and REF-02 for the texts, REF-04
  (ELI) for naming a version by its date, REF-03 (Akoma Ntoso) for keeping a
  repealed provision's number and a provision's versions, REF-05 for the
  Formex markup.
  The text: one file, in which every unit, container or leaf, has one span;
  the deleted ranges it keeps are excluded from in-force spans and text; one
  text rule for every Formex file; the recitals from the 2024 HTML.
  The checks: an unchanged unit equals the 2024 unit, Formex against
  Formex; a replaced or inserted unit is in the Omnibus quotation of its
  point; a partly amended unit's marked parts are in the quotation and its
  unmarked rest equals its 2024 text; Annex XIV equals the Omnibus annex
  member file; every quotation in the Omnibus's Article 1 is in a marked range of its own point; a container's
  wording outside its units equals its 2024 wording; every marker
  is checked against the Omnibus, the 2024 tree and
  docs/omnibus_amendments.md; any other difference, and any exception row
  no check needs, stops the parse. Where a marker and the Omnibus disagree
  the Omnibus decides through a reviewed row (the Article 3(14a) and (14b)
  insertion is marked as point (14)(b); the Omnibus enacts it in point
  (4)(b)); nine rows (data/amendments/omnibus_exceptions.json), among them
  the double marks the Omnibus prints inside its own quotations, which the
  comparison reads as the Act's single marks only through that row and only
  where a comparison needs it.
  The ids: unchanged and replaced units keep theirs; inserted units take the
  Act's numbers (eu-ai-act:article-4a, eu-ai-act:article-6:paragraph-1a,
  eu-ai-act:article-5:paragraph-1:point-ba, eu-ai-act:annex-xiv,
  eu-ai-act:annex-i:section-b:point-21); an Article number or paragraph
  index is the Act's label, a string, with an integer sort_key; span names
  keep their scheme (span:005.001, span:004a.001). A unit the Omnibus
  deleted (Article 10(5) and its six points, Annex I Section A point 1,
  Annex VIII Section B points 7 and 9, and Article 56(6)'s second
  subparagraph, which the replacing wording no longer has) stays as a node
  with amendment deleted, deleted_by and deleted_from, no text and no span;
  norm extraction and cross-reference resolution skip it.
  The versions: each replaced or deleted unit and each composed container
  keeps its 2024 wording as a UnitVersion node (id
  version:2024-07-12:<unit id>, span <name>@2024-07-12 in the 2024 Formex,
  valid 2024-08-01 to 2026-07-26, legal_status superseded), linked by
  HAS_VERSION, which gate PUBLICATION_GATE1 follows; gate PUBLICATION_GATE2 refuses a span id carried by
  an in-force node and a version node.
  The build: Layer 0 freezes the Omnibus and the consolidated text in
  Formex (the consolidated text non_binding); the build id is a digest over
  every frozen legal source the parse reads. The checks are enforced by the
  parse itself (build_in_force_dump raises AmendmentCheckError, so no dump is
  written); gate PUBLICATION_GATE6 does not re-check the units: it accepts the Omnibus as
  merged only when the dump carries the build's record of the checks and the
  reviewed marker list's digest, so a dump whose record is missing or edited
  is refused. Counts: 119 articles, 571 paragraphs, 91 subparagraphs,
  521 points, 14 annexes, 247 annex items, 180 recitals, 70 definitions,
  515 cross-references; 11 deleted units and 130 earlier versions counted
  apart.
  Defense: the reader is quoted one file whose every unit was proved equal
  to the Official Journal wording that enacted it; composing amended units
  from Omnibus fragments over the 2024 tree cannot give a partly amended
  container one source, and the consolidated text unchecked would rest on a
  documentation tool, one of whose 77 markers is mislabelled.
  Amended 2026-10-04 (B132's second plan; spec G D-G68 (6) and (7)): the
  answers follow the same text. The classifier cites Article 5(1) points
  (ba) and (bb) as their nodes with Article 5(1a) and (1b); a third fact of
  the Article 6(1) route names the Annex I section of the product's
  legislation, the level unchanged under either section; for Section B
  without an Annex III match the requirements are what Article 2(2)
  applies, cited without norms, its condition on Articles 57 to 59 stated
  and not decided, and no Article 50 duty is listed; with an Annex III
  match the Annex III route decides, and while its Annex III facts are
  unknown the answer requires human review; an unknown section on the
  Article 6(1) route alone serves the Chapter III requirements and names
  the fact. Every high_risk answer names the routes that hold, and
  application dates are data by provision, by those routes, from a
  reviewed table quoting Article 113 as amended (an Annex through the
  Article that brings it into application; a wording the Omnibus inserted
  or replaced no earlier than 27 July 2026; Article 111(4) a note on
  Article 50(2)); every answer names the text it follows.
  explain_requirement shows the source unit's earlier version on request,
  or why it has none. The elicitor prompt is v7, the version of record for
  B74; the extraction scope gains Article 4a; gates PUBLICATION_GATE3 and PUBLICATION_GATE4 refuse a norm
  or alignment whose source unit is deleted, and the evaluation harness a
  test-set item that cites one; the pre-B74 dev norms and alignments on
  changed units are dropped.
  verify: src/tere4ai/parse_legal_structure/labels.py, units.py,
  amendments.py, consolidated.py and parser.py (build_layer1);
  src/tere4ai/ingest/sources.py; src/tere4ai/validate_graph/gates.py (PUBLICATION_GATE1,
  PUBLICATION_GATE2, PUBLICATION_GATE3, PUBLICATION_GATE4, PUBLICATION_GATE6); src/tere4ai/mcp_server/spans.py (exclude);
  src/tere4ai/mcp_server/application_dates.py, classify.py, requirements.py,
  explain.py, backlog.py; prompts/elicit_features/v7.md;
  data/amendments/omnibus_markers.json, omnibus_exceptions.json;
  tests/unit/test_labels.py, test_letter_suffixed_numbers.py,
  test_formex_units.py, test_omnibus_markers.py,
  test_omnibus_unit_checks.py, test_in_force_tree.py,
  test_in_force_build.py, test_application_dates.py, test_classify.py,
  test_get_requirements.py, test_validate_graph.py,
  tests/integration/test_acceptance_in_force.py.

- DEC-24: the HTTP facade can run the generator of /api/backlog and
  /api/evidence without the judge and judge the kept answer on a later
  request, with a demo judge of the generator's own family; the MCP
  tools are unchanged and always judged under DEC-07 (added 2026-10-06,
  draft, revised after a Codex review and a second-seat review, 24
  findings; thesis task B138, spec G D-G74 and its rulings S48 to S85 in
  sdd/2026-10-05-B138-repository-evidence/progress.md in the private
  research repository; the owner's words: the judge "as a further, like
  'click here if you want to see the judge results' ... and the
  estimation of cost next to it", the split in the HTTP layer "yse", the
  judge on the click "An OpenAI model"). Engineering decision for the
  dashboard's demonstration of the tools on pasted repositories (cost
  and time in front of an audience); it needs no literature grounding
  (AGENTS.md grounding bar), and it weakens the control DEC-07 grounds
  in REF-24 only where it is labelled.
  The mode: both routes take judge, "inline" (the default, today's
  answer byte for byte) or "on_demand". On demand, the generator and
  the tool's mechanical checks run as today and no judge request is
  made; the answer has status requires_human_review and judge_verdict
  "not_checked" (Section 13: an unjudged generated answer is never
  surfaced under its generator-derived status), keeps every field of the
  inline answer (the assessment or items, notes, counts, prompts, the
  generator's usage) and, when its verdict is "not_checked", a signed
  record; a degraded generator answer is not signed and has nothing to
  judge. The request names the norms build it expects and a caller
  reference (the dashboard's project, repository run and document);
  another loaded build is refused (409) before any model call. Each
  route loads only what it calls: the generator-only mode the
  generator's settings and key, the judge routes the demo judge's and
  the signing key; neither reads the Anthropic judge's settings or key,
  which only the inline mode and the MCP tools need. /api/health reports
  the readiness of each apart (the generator-only mode, the demo judge
  with its declaration, the signing key present or missing, never its
  value). Every refusal before any model call (configuration,
  signature, build, a judge equal to the generator) carries model_called
  false.
  The signed record: the format version "tere4ai.signed_answer.v1", the
  route, a generation id drawn at random (UUID version 4), the caller
  reference, the sorted norm ids, the graph_version and norms_build, the
  generator's model id and prompt (name, version), the judge prompt
  (name, version), the SHA-256 of the untrusted text the generator read,
  and the answer's core as returned. Its bytes: JSON with keys sorted at
  every level, separators "," and ":" without spaces, non-ASCII as
  UTF-8, every field present (null where empty), no floating-point
  number. The signature: HMAC-SHA256 over those bytes under
  TERE4AI_ANSWER_SIGNING_KEY, 64 hexadecimal characters held by the
  facade alone (any other form is a configuration error), compared with
  hmac.compare_digest; test vectors (records, bytes, signatures under a
  test key) in the tests, shared with the dashboard. The facade keeps no
  state and builds its clients per request, so the signature is how a
  judge route knows it judges what the generator wrote, for the caller
  and generation it was written for; without the key, on_demand is a
  configuration error.
  The judge routes: POST /api/evidence/judge (the evidence request's
  fields, the signed record, the signature) and POST /api/backlog/judge
  (norm_ids, system_context, the signed record, the signature). Each
  verifies the signature, refuses a demo judge model equal to the
  record's generator model, checks the loaded build against the record,
  and compares every field sent apart from the record with it (the
  route called with the signed route, the SHA-256 of content or
  system_context with the signed hash, norm_id or the sorted norm_ids
  with the signed ids, artifact_type and artifact_id with the signed
  core), refusing any mismatch with 422 or 409 before any model call;
  it runs ground_check with the judge prompt the record names on the
  answer text built only from the verified signed core and on the
  verified untrusted text, and returns the judge's part only: the
  generation id, the verdict, rationale, run id, model, effort,
  temperature, prompt and usage, for the backlog under a typed prompt
  the cleaned judge_type_views (one entry per signed item, in order,
  DEC-19), the status after the tool's rule (an accepting verdict gives the tool's
  mapped status, any other requires_human_review), and judge_setting
  "demo". A judge request that fails after it was sent answers
  judge_error with requires_human_review and the judge's usage (for
  evidence a behaviour of this route of its own; the inline evidence
  route answers 502). The caller keeps the generator's answer as
  returned and shows the judge's part beside it.
  The demo judge: TERE4AI_DEMO_JUDGE_MODEL, built as an OpenAI client as
  the judge from its declared row in config/model_parameters.json
  (inference backend openai) and its row in config/model_prices.json, which a
  price loader of the judge's configuration reads, refused when either
  row is missing or when it equals TERE4AI_GENERATOR_MODEL or the
  record's generator model. The first model is gpt-6-sol (temperature
  N/A, effort xhigh; JSON mode sent, the owner's 2026-09-30 reading for
  gpt-6-astra extended to gpt-6-sol, not a statement of the gpt-6-sol
  pages; 2.00 and 10.00 USD per million input and output tokens at
  short context, 4.00 and 15.00 above 272,000 input tokens, batch 1.00
  and 5.00; read on OpenAI's GPT-6 guide, the gpt-6-sol model page and
  the pricing page on 2026-10-06, the quotes re-read when the rows are
  written). Every runtime log line the demo judge writes carries
  judge_setting "demo", and scripts/estimate_benchmark_cost.py leaves
  those lines out of its judge figures. The report takes a judge part
  as a session line of its own (tool "judge_on_demand", a Section 8
  envelope whose answer is the judge's part with the judged tool and the
  generation id): report/ingest.py attaches it to the exchange whose
  signed record holds the same generation id, and report/render.py
  shows it beside the unchanged generator answer, the item views beside
  their items, keys evidence answers by generation id so the documents
  of one norm are never reduced to the latest, and prints judge_setting
  in every judge record, so a demo verdict reads "judged by <model>, the
  generator's own family (demo setting)".
  DEC-07 stands for TERE4AI_JUDGE_MODEL (assert_independent_judge still
  refuses an OpenAI-family model there), for the MCP tools and for every
  measurement of the thesis; Section 9's rule that every demo screen
  renders the judge verdict reads, for an on-demand answer, "not checked
  by the judge" until a judge route has answered.
  Considered and not taken: trusting the caller's copy of the answer
  (any client could obtain a judged label on text the generator never
  wrote); keeping answers in the facade by id (state lost at a restart);
  a judge route that rebuilds the whole inline envelope from what the
  caller sends; an OpenAI judge under TERE4AI_JUDGE_MODEL (it would
  change DEC-07 for the MCP tools and the experiment); gpt-6-astra as
  the demo judge (the generator judging itself).
  Defense: the demo shows the tools' answers quickly and the judge only
  when asked, with its cost shown first; the signed record keeps
  "judged" true of exactly what was generated, for whom; the label and
  the log field keep a same-family judge from being read as DEC-07's.
  Cost if wrong: one facade mode, two routes, a report field, a log
  field and two settings to remove; the MCP tools and the inline routes
  never change.
  verify: src/tere4ai/http_facade/app.py (the judge field, the expected
  build, the caller reference, the judge routes, the signed record, each
  route's configuration, /api/health's readiness); mcp_server/
  evidence.py and backlog.py (each tool split into a generator part and
  a judge part, the MCP answers unchanged); judge/config.py (the demo
  judge's loading, refusals and price loader); judge/runtime_grounding.py
  (judge_setting on log lines); extract_norms/model_clients.py;
  report/ingest.py and report/render.py; scripts/estimate_benchmark_cost.py;
  config/model_parameters.json and config/model_prices.json (gpt-6-sol);
  .env.example (TERE4AI_DEMO_JUDGE_MODEL, TERE4AI_ANSWER_SIGNING_KEY);
  tests on mock clients: the inline envelopes byte for byte, the test
  vectors, a forged or stale signature, a judge equal to the signed
  generator and each field sent that differs from the record (route,
  content or system_context, norm ids, artifact fields) refused before
  any request, a judge_on_demand line attached to its generation in the
  report, an unexpected build refused,
  model_called false on every refusal before a request, demo lines left
  out of the estimate.

- DEC-25: Layer 3 reads the Ethics Guidelines for Trustworthy AI (ADD-01)
  from a text derived from their official PDF by a committed command and
  checked against that PDF in every Layer 0+1 build, under a
  SourceDocument of their own, each of the seven requirements given whole
  (added 2026-10-07; thesis task B143, spec G D-G75 and the rulings in
  sdd/2026-10-07-B143-hleg-source/progress.md in the private research
  repository; the owner's words: "this can mean that we have a different
  approach from just me giving you a .txt that is a ctrl c ctrl vo f the
  pdf", and on Section 1 of this file: "we cant have a stale
  architecture.md or untruthful"). Engineering decision (determinism,
  traceability, no silent degradation, Section 13); it needs no literature
  grounding (AGENTS.md grounding bar). Until it, Layer 3 read a plain-text
  copy of the PDF made by hand for TERE4AI v1, checked against nothing:
  each requirement's text stopped at the first page break of its section
  (section 1.2 gave 1,743 of 4,639 characters, so 6 of the 23 subtopics
  could not be quoted), footnotes and page numbers sat inside it, two
  line-end hyphens were lost ("human-in-theloop") and the span of section
  1.7 ran 2,114 characters into the next part of the Guidelines.
  The source: the Publications Office PDF frozen on 2026-07-08, the only
  edition with an ISBN, a DOI and a CELLAR identifier; no structured
  manifestation exists (read 2026-10-07; Section 6 (d)).
  The derivation: `python -m tere4ai.ingest.hleg_text --write` reads the
  PDF through its checksum and writes the text of Chapter II Section 1,
  from "1.1 Human agency and oversight" to "2. Technical and
  non-technical methods to realise Trustworthy AI", exclusive, and a
  derivation record beside it; the rules are listed in the module and in
  the record: the structure tree's order, Note and Figure subtrees
  skipped, artifacts never read, characters below 0.75 times their
  paragraph's median size removed as footnote markers (each the number of
  a footnote on its page), words spaced by pdfplumber's word reading, a
  line-end hyphen kept and joined, a page's last paragraph that reaches
  the margin joined to the next page's first.
  The checks (`tere4ai.ingest.hleg_checks`, inside the parse before any
  node is built, and in the tests), against pypdf as a second reader: HLEG_CHECK0
  the derivation reproduces both files byte for byte; HLEG_CHECK1 every derived
  stretch between markers and joins is in pypdf's text of its page; HLEG_CHECK2
  pypdf's text of the pages, less the derived stretches, leaves only the
  excluded items, which equal a reviewed list item by item, location
  included, and each pass the test of its kind; HLEG_CHECK3 each page's words
  compared in order with pypdf's layout reading, every difference a
  reviewed row bound to its location; HLEG_CHECK4 the seven headings in order, the
  23 subtopic headings opening their paragraphs, no line of only digits.
  A failure raises HlegCheckError naming the check and its first
  differences; the parse writes no new layer1.json and records the failed
  execution; on success the outcome is in the build block (hleg).
  Layer 0 and Layer 3: as spec G D-G75 (4) to (8) state (the
  SourceDocument, the explicit table of source documents, DERIVED_FROM
  from the derived files to the PDF, post-load gate POSTLOAD_GATE5 limited to the
  Layer 2 and 3 edges, each requirement's section body as its
  description, the publisher's headings as subtopics, the pair's sha256
  recorded by the alignment run and checked by publication and by the one
  loader that serves HLEG spans).
  Defense: the quote check proves a quote is in the text it was given;
  this decision proves the text given is the publisher's.
  Cost if wrong: before B74, a derivation and its checks to redo, with no
  model call; after B74, every alignment made and graded again.
  verify: src/tere4ai/ingest/hleg_text.py and hleg_checks.py (the
  derivation, its record and the checks); parse_legal_structure/
  consolidated.py (the checks inside LAYER1_STEP1, the build block's
  hleg entry);
  ingest/sources.py (the SourceDocument, the table, DERIVED_FROM);
  validate_graph/postload.py (POSTLOAD_GATE5) and gates.py (hleg_failures);
  align_hleg/hleg_source.py, hleg_nodes.py, hleg_subtopics.py and
  __main__.py; scripts/publish_layer23.py; http_facade/app.py,
  mcp_server/server.py, explain.py and spans.py (the loader bound to the
  served build); tests/unit/test_hleg_text.py, test_hleg_checks.py,
  test_hleg_nodes.py, test_hleg_subtopics_crosscheck.py,
  test_hleg_serving.py, test_sources.py, test_postload_scope.py,
  test_in_force_build.py, test_parse_cli_record.py, test_align_cli.py,
  test_align_hleg.py, test_publish_layer23.py, test_v1_text_gone.py and
  test_architecture_layers.py; tests/integration/test_postload_gates.py.
- DEC-26: a requirement of Articles 8 to 15 (Chapter III Section 2,
  "Requirements for high-risk AI systems") whose text names no person or
  body that must act is the provider's duty, inferred through Article
  16(a): actor_explicit null, actor_inferred provider,
  actor_inference_source_node_id eu-ai-act:article-16:paragraph-1:point-a
  (added 2026-10-07; thesis task B144, spec G D-G76 and the rulings in
  sdd/2026-10-07-B144-system-subject-duties/progress.md in the private
  research repository; the owner's words, on the extraction rule giving
  such duties to the provider through Article 16(a): "im leaning towards
  a", then "yes a card for it and admited before b74"). grounded_by
  REF-01, REF-11. Article 8(1): "High-risk AI systems shall comply with
  the requirements laid down in this Section"; Article 16(a): "Providers
  of high-risk AI systems shall: (a) ensure that their high-risk AI
  systems are compliant with the requirements set out in Section 2";
  REF-11 (Section 3.3, p. 3): an addressee "must individually or
  collectively possess the capacity to act, such as a natural or legal
  person. Consequently, entities like 'AI systems', 'a process', or
  'adopted measures' cannot serve as addressees of obligations".
  Until it, extract_norms v3 gave a Section 2 duty to the provider only
  when it was stated in the passive voice, with the whole of Article 16
  as its source; a duty whose subject is the system kept the system as
  its written actor, which the role filter (mcp_server/requirements.py,
  _actor_matches) serves to no role, so Article 12(1), "High-risk AI
  systems shall technically allow for the automatic recording of events
  (logs) over the lifetime of the system", reached no provider.
  Which norms: an obligation or prohibition that states one of the
  Section's requirements for the high-risk AI system, and a permission or
  exemption that qualifies one (Article 9(7), 15(4), 14(5)), whatever the
  grammatical subject (the system, a part of it, a thing the Section
  requires of it) and whether the verb is active or passive; never a
  right, nor a norm read as the permission, ability or duty of a
  person the system must enable or inform (Article 14(4)(d) read alone);
  the duty to enable that person is the system's and is covered. A person
  or body the text names as the one that acts keeps its written actor
  (the Commission, notified bodies, SMEs and SMCs, providers); a person named
  only inside what a requirement must ensure is not its actor (Article
  14(5)'s measures, which must ensure that no decision is taken "by the
  deployer" unless verified, are the provider's).
  Outside Articles 8 to 15 extract_norms v3's rule stands. No slot is
  added: the system's words stay in the norm's source unit and span.
  extract_norms v4 states the rule with worked examples (Article 12(1),
  the Article 14(4) paragraph beside its point (d), Article 15(4));
  judge_norms v4's check 3 accepts that inference for a unit of Articles
  8 to 15 and rejects it outside them, where the text names the person
  who acts, for a norm read as an enabled person's own permission or
  ability, and the system in actor_explicit there; from v4 on a point
  given as the inference source reaches the judge with the paragraph that
  holds it, and the E1 label sheet shows the same text. v4 is the default and the version of
  record (eval/config_evaluated.yaml), so B74 extracts with it; v1 to v3
  stay runnable with the input they had. The extraction command stores
  two checks in the execution's counts: the accepted norms of Articles 8
  to 15 the provider is not served, and an audit of every norm of
  Articles 8 to 15 in four groups (rule applied, written party, outside
  the rule, against the representation), with the norms outside Articles
  8 to 15 that cite point (a). Reporting effects, disclosed and not
  corrected: the canonicalization moves a covered norm from
  actors_unresolved to actors_resolved, the near-duplicate report
  compares it inside its Article's provider block, and the digests given
  to models name provider as its actor; B74's figures are the first that
  count.
  This is the project's reading of Article 16(a), not the only one:
  REF-11 (Section 3.3, p. 4) reads the addressee of Article 14's "the
  oversight measures shall be commensurate with the risks" as the
  deployer. The reading is recorded on every norm with its source,
  checked by the judge and open to the annotators of LAYER2_STEP3 (the
  dashboard's annotation guideline v3).
  Defense: who must act decides who is told; the Act makes the provider
  answer for every Section 2 requirement whatever the sentence's
  subject, and the reading lives in the norm, where the judge checks it,
  the build record audits it and the annotators can correct it.
  Cost if wrong: before B74, two prompt versions, a judge input, two
  counts and a guideline version to redo, with no model call; after B74,
  a Section 2 norm the Act gives to someone else without naming them is
  served to the provider until LAYER2_STEP3 corrects it.
  verify: prompts/extract_norms/v4.md and prompts/judge_norms/v4.md;
  src/tere4ai/extract_norms/pipeline.py (DEFAULT_PROMPT_VERSION,
  judge_inference_block), actor_audit.py and __main__.py;
  scripts/sample_judge_decisions.py and scripts/estimate_benchmark_cost.py
  (the same inference text as the judge); eval/config_evaluated.yaml;
  tests/unit/test_norms_prompts_v4.py, test_extract_norms.py,
  test_judge_sampling.py, test_actor_audit.py (Layer 1's Section 2
  included), test_extract_norms_cli.py and test_section_2_provider_rule.py
  (the mock-model command line run, the requirements tool and the facade
  over its output); docs/benchmark_cost_estimate.md is regenerated with v4;
  CHANGELOG.md names the contract change.
  Amended 2026-10-09 (B145, DEC-27): outside Articles 8 to 15 a thing a
  sentence of the same Article makes a named party set up no longer
  stands as the written actor under extract_norms v5; it is that party's
  (DEC-27). Inside Articles 8 to 15 this decision stands unchanged.
- DEC-27: the Act's parties are one fixed list, every norm's addressee is
  placed on one value of it and the value is stored, and outside Articles
  8 to 15 a duty whose subject is a thing a sentence of the same Article
  makes a named party set up is that party's (added 2026-10-09; thesis
  task B145, spec G D-G80 and the rulings in
  sdd/2026-10-09-B145-act-roles/progress.md in the private research
  repository; the owner's words: "This should be normalized with the
  legal text and the provides be a fixed list that can't change").
  grounded_by REF-11. Article 3(8): "‘operator’ means a provider, product
  manufacturer, deployer, authorised representative, importer or
  distributor;"; REF-11 (Section 3.3, p. 3): "The addressee must
  individually or collectively possess the capacity to act, such as a
  natural or legal person."
  The list: schema/act_parties.json, 37 values by kind (role 6, the AI
  Act roles of Article 3(8) in its order; authority 9; body 2; institution
  9; person 9; sentinel 2), each with its Act term, its ground node, its
  Definition node where Article 3 defines it, the Act's other wordings
  placed on it with their grounds, and the values a request may name and
  still be served it (Article 3(47) and 3(48), one way). Written by hand
  and tested against layer1.json. src/tere4ai/act_parties.py places a
  written addressee on one value (full name, then the parties in the
  governing part, then the head; never a substring), reads a norm's
  addressee in either norms schema version, and serves a norm to a
  request when the values are equal, by also_served_to, or when the norm
  is addressed to operators in general and the request names an AI Act
  role.
  The set-up rule: outside Articles 8 to 15, a norm whose grammatical
  subject is a thing is the duty of the party that a sentence of the same
  Article makes set up, draw up, produce or carry that thing, when the
  subject refers to it (by its name, by another name the Article gives
  it, by "that", "this", "such" or "those", or by "referred to in
  paragraph N"), to a part of it, a copy of it, its implementation or the
  time set for it; never across Articles; one norm per party when two
  parties set it up. The extractor reads one unit, so the setting-up
  sentence of another paragraph reaches it as a row of a closed table
  (src/tere4ai/extract_norms/set_up_rule.py, 26 paragraph units of the
  core of B74 and the rows outside it), printed into extract_norms v5 for
  the core; the cases left alone are listed with their reasons. A point
  read alone that yields a norm under the rule takes as its source the
  paragraph that holds the setting-up sentence, never the point (R107);
  Article 22(3)'s points are not covered (their party is the authorised
  representative the paragraph's first sentence names, with node 22(3)).
  judge_norms v5 receives a covered unit's rows and checks the inference
  against the setting-up text; its check 3 accepts the set-up case (R107).
  The stored value is written by code when the norm is written after the
  verdict, so no judge input changes by it; a v5 run writes norms schema
  version 2 (schema/json_schemas/norms.v2.schema.json); version 1
  (norms.schema.json) is never edited and every reader reads either
  version through tere4ai.act_parties; the facade and the MCP server load
  a version 1 file into version 2's names in memory. A human norm added to
  a version 2 file is validated against norms.v2.schema.json (all 37
  values), a version 1 file keeps its version 1 check (R100). The
  normaliser leaves a phrase unplaced when a party is coordinated after an
  "of ... AI systems/models" descriptor (R98), and "european" is one of
  its head modifiers, with "national", "eu" and "union" (R99). Two party
  terms joined by "and" or "or", whatever words stand between them ("the
  provider or, where applicable, the deployer"), leave the phrase unplaced
  as well (R116), and the build record's count of norms on a covered unit
  whose written addressee is the row's thing counts judge-accepted norms
  only (R117). The served
  requirements entry names the value and the written words, and the
  argument is addressee (actor is refused). The extraction's build record
  holds schema/act_parties.json as an input with its digest and four
  counts: the norms per value, the written addressees the list could not
  place, the norms resting on the set-up rule, and the norms on a covered
  unit whose written addressee is the row's thing. The digests that pass a
  norm's party to other instruments' models keep the key "actor" and their
  content. The prompts are extract_norms v5 (24,863 characters) and
  judge_norms v5 (11,851 characters).
  Defense: one list read by every step, placed by deterministic code and
  checked against the Act's text, where fifteen lists disagreed; the
  set-up rule follows the Act's own back references within the Article
  that makes them, and the reading lives on the norm, where the judge
  checks it, the build record counts it and the annotators can correct
  it. Cost if wrong: before B74, a list, a normaliser, a rule table, two
  prompt versions, a judge input and four counts to redo, with no model
  call; after B74, a misplaced value or a misread back reference is
  listed by the counts and corrected in LAYER2_STEP3.
  verify: schema/act_parties.json; schema/json_schemas/norms.v2.schema.json;
  src/tere4ai/act_parties.py; src/tere4ai/extract_norms/set_up_rule.py,
  scope_first_reading.py, requirement_type.py, pipeline.py, actor_audit.py
  and __main__.py; src/tere4ai/mcp_server/requirements.py, explain.py,
  trace_code.py, server.py; src/tere4ai/http_facade/app.py;
  src/tere4ai/graph_store/publication.py and layer23.py;
  prompts/extract_norms/v5.md, prompts/judge_norms/v5.md,
  prompts/requirement_type/scope_v2.md; eval/config_evaluated.yaml;
  tests/unit/test_act_parties.py, test_norms_schema_v2.py,
  test_addressee_readers.py, test_served_addressee.py, test_set_up_rule.py,
  test_norms_prompts_v5.py, test_extract_norms_v5.py,
  test_addressee_counts.py, test_b145_mock_run.py (the mock-model command
  line run, the requirements tool and the facade over its output) and
  test_party_names_guard.py; docs/benchmark_cost_estimate.md is
  regenerated with v5; CHANGELOG.md names the contract change.

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
                   extract_norms/ canonicalize/ align_hleg/ judge/
                   validate_graph/ graph_store/ mcp_server/ http_facade/ eval/
  web/             Next.js demo UI (thin, read-only; per docs/DESIGN.md)
  schema/          json_schemas/ cypher_constraints/ rdf_export/
  prompts/         extract_norms/ judge_norms/ align_hleg/ judge_alignment/ runtime_grounding/
  data/            sources/ snapshots/ graph_dumps/ review_queue/
  tests/           unit/ integration/ fixtures/ gold/ meta/
  docker-compose.yml  pyproject.toml
```

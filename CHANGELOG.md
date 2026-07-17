# Changelog

All notable changes to TERE4AI v2. Format loosely follows Keep a Changelog;
versions are git tags. Dates are build dates (Europe/Helsinki).

## [Unreleased]

### Graph and pipeline
- Reified CrossReference nodes (426) with HAS_CROSS_REFERENCE and
  RESOLVES_TO edges; "Article 6(2)"-style citations resolve to
  paragraph-level targets where the node exists (104 of 476).
- Canonicalize step implemented (DEC-04): actors map onto the closed role
  table by deterministic rules (unresolved strings are reported, never
  guessed); each distinct condition/exception wording becomes one shared
  Condition/Exception node (364 + 27 live) with per-norm ids and
  HAS_CONDITION/HAS_EXCEPTION edges.
- RDF export bridge via n10s (DEC-09): the judged Layer 2/3 subgraph as
  N-Triples with RDF-star edge properties mapped to standard reification;
  rdflib roundtrip and full-norm-coverage integration tests.

### Runtime tools
- Section 8 envelope contract: the mandatory response-field set is now a
  named constant (SECTION_8_ENVELOPE_FIELDS) and a cross-cutting test fires
  every envelope-returning facade endpoint across all classification tiers,
  asserting the complete field set, a calibrated status (never a compliance
  claim), and the non-legal-advice notice on every response. Catches drift
  at the honesty boundary that per-endpoint tests can miss.
- Classification depth: the Article 6(1) embedded-product route (Annex I
  plus third-party conformity assessment) and the real Article 6(3)
  second-subparagraph conditions with the profiling override; four new
  feature flags and elicitor prompt v2.
- Batch evidence mode: one artifact against every judge-accepted norm of an
  article, one envelope with per-norm results and worst-case aggregation
  (MCP tool evaluate_project_evidence_batch).
- Backlog grouping: identical-norm-set items merge into one control;
  mechanical priority reads conditions (conditional obligations are should).
- Fresh-clone reproducibility: the dump-dependent facade tests (envelope
  contract, facade/MCP parity, HTTP facade) now skip cleanly when the
  published graph dumps are absent instead of failing (31 failures on a
  dumpless checkout before; the guard checks the same dump location the
  facade resolves), and the README documents how dumps are obtained.
- Remote MCP transport (streamable HTTP) behind TERE4AI_MCP_TRANSPORT=http,
  gated by scoped, revocable t4a_ API keys with body-free usage metering
  (scripts/manage_mcp_keys.py).

### Evaluation and evidence
- Full REF-15 benchmark frozen (339 scenarios + 137 QA, sha256-verified)
  and a dry-run cost estimator for the full-benchmark gate
  (docs/benchmark_cost_estimate.md).
- Full-benchmark ablation run (task 27, cost approved): 486 items through
  the five-condition ladder with prompt-v2 elicited features, 0 errors;
  plain LLM 207/339 with zero checkable citations vs graph 144/339 with
  0.45 article-level citation completeness and 0.000 hallucinated
  citations; artifacts eval/results/ablation_full_*, analysis
  eval/results/FULL_RUN_ANALYSIS.md, generated matrices
  docs/ablation_deepdive_full.md, full-run paper figure and table.
- Provider-reported token usage accounting: model clients accumulate real
  usage, every ablation checkpoint unit records its exact delta, the
  summary aggregates spend (measured judge cost 9.63 USD vs the 5.33 USD
  dry-run quote; band exceeded, lesson recorded in the analysis).
- Repeat-run variance study (task 60, cost approved): a full second ladder
  over the same items and frozen features; graph conditions flipped 0 of
  345 labels (deterministic classification confirmed, citation Jaccard
  0.95 to 0.97) while plain LLM flipped 43 and vector RAG 51; generated
  report docs/variance_study.md, tooling scripts/variance_report.py.
- Graph strategies: AnnexItem-level retrieval for retrieval items and
  operative-text passages with node-id citations for QA items.
- Prompt A/B as ablation conditions (graph_full@vN) and one consolidated,
  secret-scrubbing audit-log module across the three judge logs.
- Adversarial evidence corpus (12 fixtures, 4 attack classes) with a
  computed security report (docs/SECURITY_EVAL.md).
- Gold-set expansion tooling: 70 graph-drafted candidates with
  deterministic second-annotator assignment and a kappa CLI.

### UI and delivery
- Demo UI: /review human-review-queue page, one-click scenario presets,
  envelope JSON export, audit permalink, dark-mode and accessibility pass.
- Phase 2 design doc (multi-tenancy, key scopes, metering) and Rahti
  deployment manifests.

## [2.0.0-alpha.1] - 2026-07-10

First tagged pre-release: the complete evidence-gated pipeline, runtime
tools, evaluation harness, and reference register, built 2026-07-08 to
2026-07-10.

### Graph and pipeline
- Deterministic Layer 1 mirror of the full EU AI Act (Regulation 2024/1689)
  from frozen, checksummed EUR-Lex HTML and Formex 4 manifestations: 113
  articles, 180 recitals, 13 annexes, plus Definitions (68), Subparagraphs
  (63), verified recital CONTEXT_FOR links, and the Digital Omnibus modelled
  as an amending source (DEC-01, DEC-02, DEC-12).
- Judged Layer 2/3: 434 NormativeStatements (339 judge-accepted) and 620
  reified AlignmentAssertions (475 accepted) with independent-family judges
  (OpenAI generator, Anthropic judge; DEC-03, DEC-05, DEC-06, DEC-07).
- Publication gating (Section 13) plus post-load database gates P1..P5, and
  a build reproducibility chain: every published node and edge carries a
  build_id embedding sha256 checksums of the exact input artifacts.
- Norm near-duplicate hygiene report (rule-based, human-decided).

### Runtime
- All eight Section 8 MCP tools, including deterministic classify_ai_system
  (the LLM never decides risk; DEC-13 feature elicitation splits fact
  extraction from decision), evidence evaluation, control backlog,
  explain_requirement, trace_alignment, coverage_report, source_trace.
- FastAPI HTTP facade with the same envelope (calibrated status vocabulary,
  never "compliant"; DEC-08), agent-discovery endpoints, and a thin
  read-only Next.js demo UI. Mode B docker-compose packaging.

### Evaluation
- M4 harness with the five-condition ablation ladder; two live sweeps on the
  gold seed plus REF-15 benchmark sample. Run 2 headline: graph conditions
  18/32 on free text with 4 honest abstentions and 0.38 citation
  completeness versus plain LLM 24/32 with zero checkable citations.
- FA/FR labeling sheet (50 stratified judge decisions), kappa module,
  elicitation error analysis feeding a classification-ladder fix.

### References
- Authoritative register (SELF/REF/ADD namespaces) with source-type tags,
  DOIs, and status; full-text corpus of 42 papers under data/refs with a
  queryable literature knowledge graph; CI traceability gate over
  @implements / @grounded_by tags.

### Published dumps (sha256, first 16 hex)
- layer1.json d5071560ecca4fd7
- norms_core.json eedbf701f84c0831
- alignments_core.json 68166d93d6a30cd7
- build chain: build-3b753e5e9297+chain-3982bf3d85d4
  (data/graph_dumps/build_chain_3982bf3d85d4.json)

### Known limitations
- Full-benchmark ablation (339 scenarios + 137 QA) and repeat-run variance
  study are pending (cost-gated); gold-set expansion and FA/FR labeling
  await human annotation; RDF export (DEC-09) is Neo4j-only so far; the
  Omnibus final OJ text is not yet published, so its consolidated provisions
  are not ingested.

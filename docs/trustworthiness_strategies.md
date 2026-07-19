# Trustworthiness-enhancing strategies in TERE4AI v2

> One place answering, for every trust-enhancing strategy actually
> implemented in this codebase: (a) its name, (b) the citation grounding it
> as trust-enhancing, drawn ONLY from the register docs/references.md and
> the held texts in data/refs/ (or, where no literature grounds it, the
> explicit engineering rationale, which the project's grounding bar permits
> for engineering MUSTs), and (c) how to see it implemented: code, pinning
> test, and a way to watch it work. Every file:line was verified on
> 2026-07-19 against the current tree (HEAD at the commit adding this file).
>
> Formatting rule: never use em dashes, and never use en dashes as a
> sentence break.
>
> Register note: the author's earlier papers SELF-01 to SELF-04 are the
> lineage of these strategies (see the final section). A fifth self
> reference (the author's first PhD paper, containing early
> trustworthiness-enhancing strategies such as multi-round debate, role
> assignment, and structured conversation) is pending: the file supplied as
> data/refs/paper6.pdf was empty (0 bytes) and could not be read or
> registered. When a readable copy lands it becomes SELF-05, with the
> honest framing that several of its strategies are historical: superseded
> by judge-gated pipelines and agent harnesses, of which this codebase is
> the successor.

## How to read the grounding column

Per the shared grounding bar (AGENTS.md, architecture.md Section 17,
references.md): an empirical claim needs at least one PEER, STD, or OFF
source; PRE, PROJ, and PRAC may support but never stand alone; an
engineering or non-functional MUST stands on engineering merit and needs
no literature grounding. Where a strategy is grounded on engineering
merit, this document says so explicitly instead of inventing a citation.

## A. Deterministic foundations (the LLM never decides what the law is)

### 1. Deterministic risk classification
- Grounding: REF-30 (FLI compliance checker, PRAC: rule-based classification
  logic source and baseline, never sole grounding), ADD-24 (PEER, semantic
  modelling of high-risk classification), REF-26 (PEER: conditionals and
  references are the top LLM error zone, so the decision must not be an LLM),
  REF-01 (OFF, the legal rules themselves). Determinism itself is an
  engineering MUST (architecture.md Section 13).
- Implementation: src/tere4ai/mcp_server/classify.py:297 (rule ladder,
  L345-692; imports contain no model client).
- Tests: tests/unit/test_classify.py:410 (same input, same output), :422
  (source-level no-model-import guard), scenario tests per tier.
- See it: POST /api/classify; the envelope's answer.rationale names the exact
  rule that fired; docs/variance_study.md records 0/345 repeat-run label flips.

### 2. Fact elicitation split from decision (DEC-13)
- Grounding: REF-17 (PRE), REF-16 (PEER: extraction accuracy limits motivate
  keeping extraction away from the decision).
- Implementation: src/tere4ai/elicit_features/elicitor.py:31-42 (_clean strips
  any model-emitted risk field via schema allow-listing), :59-81 (retry then
  honest None).
- Tests: tests/unit/test_elicit_features.py:25, :41.
- See it: elicited feature JSON never contains a risk category; classification
  always re-runs the deterministic ladder.

### 3. Deterministic Layer 1 and rule-first cross-references (DEC-01, DEC-02)
- Grounding: REF-27 (PRE: LLMs hallucinate legal hierarchy), REF-26 (PEER),
  REF-08 (PRE, legislation as property graph); determinism is an engineering
  MUST.
- Implementation: src/tere4ai/parse_legal_structure/ (no model imports),
  src/tere4ai/resolve_crossrefs/resolver.py:232-390 (rule pass; unresolved
  items queue for humans, LLM repair deliberately unimplemented).
- Tests: tests/integration/test_acceptance_m1.py (113/180/13, determinism,
  no-model-calls), tests/unit/test_crossref_reification.py:108.
- See it: rebuild layer1.json from the frozen snapshot; the build id is the
  sha256 of the input.

## B. Judge gating (generated content never surfaces unexamined)

### 4. Build-time extraction judge
- Grounding: ADD-16 (PEER, LLM-as-judge methodology), REF-24 (PRE,
  judge-in-evaluation and independence stance), REF-11 (PEER, extraction
  judge in an obligation pipeline), REF-16 (PEER: 68.2 percent unjudged
  grounding accuracy is the number the judge exists to beat).
- Implementation: src/tere4ai/extract_norms/pipeline.py:326-337 (per-candidate
  judging), :397 (only an accepting verdict yields an accepted norm),
  :230-242 (unusable judge output falls back to needs_human_review, never
  accepted).
- Tests: tests/unit/test_extract_norms.py:180, :248, :265.
- See it: jq '.stats.verdicts' data/graph_dumps/norms_core.json
  (339 accepted / 54 rejected / 41 review).

### 5. Build-time mapping judge with mechanical quote gate
- Grounding: ADD-16, REF-24 as above; REF-10 (PEER, mapping sibling);
  quote verification grounded by ADD-18 (PEER, hallucination detection) and
  ADD-19 (PEER, faithfulness metrics).
- Implementation: src/tere4ai/align_hleg_altai/pipeline.py:308-341 (verbatim
  quote gate BEFORE the judge; failures logged as mechanical:quote_check and
  never judged), :345-357 (verdict gate, relation-type correction against the
  closed set).
- Tests: tests/unit/test_align_hleg.py:200, :228, :250, :263, :274.
- See it: judge_diagram.svg lane 2; alignment stats in
  data/graph_dumps/alignments_core.json.

### 6. Runtime grounding judge on every paid answer
- Grounding: ADD-16, ADD-18, REF-16, REF-24, REF-31 (STD, tool security).
- Implementation: src/tere4ai/judge/runtime_grounding.py:94-161 (ground_check;
  verdict whitelist; fallback never accepts); consumed at
  src/tere4ai/mcp_server/evidence.py:228-246 and backlog.py:303-324 (any
  non-accepting verdict forces requires_human_review at confidence 0.0).
- Tests: tests/unit/test_runtime_grounding.py:102, :114;
  tests/unit/test_evidence.py:161.
- See it: every paid envelope carries judge_verdict; reject paths carry the
  judge rationale.

### 7. Independent judge model family (DEC-07)
- Grounding: REF-24 (PRE: same-family judges have correlated failure modes).
  Note for the thesis: this grounding is preprint-only, so state the decision
  as engineering conservatism corroborated by REF-24, not as an empirically
  proven claim.
- Implementation: src/tere4ai/judge/config.py:79-83 (rejects an OpenAI-family
  judge model, fails fast), separate SDKs and API keys in
  src/tere4ai/extract_norms/model_clients.py:35, :80; config of record
  eval/config_evaluated.yaml enforced by eval/harness.py:117-137.
- Tests: tests/unit/test_model_config.py:22, :32, :40.
- See it: set TERE4AI_JUDGE_MODEL=gpt-anything and the loader refuses to start.

### 8. Mechanical verbatim-quote verification (non-LLM, survives a fooled judge)
- Grounding: ADD-18 (PEER, hallucination detection), ADD-19 (PEER), REF-16.
- Implementation: src/tere4ai/mcp_server/evidence.py:196-212 (fabricated
  quotes dropped; a quote-bearing assessment with zero surviving quotes
  downgrades to cannot_assess); align_hleg_altai/pipeline.py:82-86.
- Tests: tests/unit/test_adversarial_evidence.py:99 (quotes drop even when the
  scripted judge is fooled), :113; tests/unit/test_evidence.py:136, :150.
- See it: envelope answer.dropped_quotes.

### 9. Citation allow-lists (cite only what exists)
- Grounding: ADD-18, ADD-19, REF-16.
- Implementation: src/tere4ai/mcp_server/backlog.py:179-188 (items citing
  unknown norm ids dropped and counted); requirements.py:163-190 (only nodes
  present in the graph are cited; missing ones surface in missing_facts);
  classify.py:280-294 (unresolvable node ids withheld, never emitted).
- Tests: tests/unit/test_backlog.py:135, :151; tests/unit/test_eval_metrics.py:112.
- See it: measured hallucinated-citation rate at most 1 in about 4,380 checked
  citations per condition (eval/results/FULL_RUN_ANALYSIS.md).

## C. Provenance, traceability, reproducibility

### 10. Span-level provenance over sha256-frozen sources
- Grounding: ADD-20 (STD, PROV-O), ADD-14 and ADD-15 (PEER, the traceability
  problem and practice), REF-27.
- Implementation: src/tere4ai/parse_legal_structure/parser.py:97-110, :226-238;
  span resolution re-verifies the snapshot checksum before slicing
  (src/tere4ai/mcp_server/spans.py:88-92).
- Tests: tests/unit/test_mcp_tools.py:211, :226; the census
  tests/unit/test_norm_span_census.py resolves EVERY accepted norm's span.
- See it: any envelope's source_spans carries snapshot_sha256 plus byte offsets.

### 11. Provenance class on every edge
- Grounding: REF-32 (PROJ, the provenance edge-tag pattern donor), ADD-20.
- Implementation: schema/json_schemas/edges.schema.json:7, :32-56 (closed
  9-value enum; provenance-free edges are schema-invalid); writers in
  ingest/sources.py:48, graph_store/layer23.py:126-137,
  resolve_crossrefs/resolver.py:259.
- Tests: tests/unit/test_layer23_graph.py:59; tests/unit/test_sources.py:28.
- See it: all 3459 Layer 1 edges carry provenance_class (verified by audit).

### 12. Reified AlignmentAssertions (auditable claims, not truth edges) (DEC-05)
- Grounding: REF-21 (PEER, edge-information tradeoff), REF-10 (PEER), REF-24.
- Implementation: align_hleg_altai/pipeline.py:391-409;
  graph_store/layer23.py:204-275 (no direct norm-to-HLEG edge exists);
  gate G4 validate_graph/gates.py:112-119.
- Tests: tests/unit/test_align_hleg.py:150; tests/unit/test_validate_graph.py:40.
- See it: POST /api/trace renders the assertion with evidence spans both sides.

### 13. Build reproducibility chain (content-derived build ids)
- Grounding: engineering MUST (Section 13); corroborated by REF-27 and ADD-20.
- Implementation: src/tere4ai/graph_store/build_chain.py:41-94;
  parser.py:238 (build id equals sha256 of the snapshot, truncated).
- Tests: tests/unit/test_build_chain.py; the standing gate
  tests/unit/test_published_build_chain.py (dumps on disk must match exactly
  one recorded chain; a tampered dump fails).
- See it: every envelope's graph_version; build_chain_*.json in
  data/graph_dumps/.

### 14. Validation gates, reject-not-infer, failing builds unpublished
- Grounding: ADD-21 (STD, SHACL validation modelling), REF-27, REF-26.
- Implementation: src/tere4ai/validate_graph/gates.py:56-143 (G1-G6),
  postload.py:65-110 (P1-P5); publish blocked on failure
  (scripts/publish_layer23.py:77-83, :169-173).
- Tests: tests/unit/test_validate_graph.py; tests/integration/test_postload_gates.py.
- See it: python scripts/publish_layer23.py --gates-only.

### 15. Repo-wide traceability enforcement (tags resolve or CI fails)
- Grounding: ADD-14 and ADD-15 (PEER); enforcement is engineering.
- Implementation: scripts/check_traceability.py:235-321 (unknown-ref,
  unknown-dec, missing-implements, dash gates); docs/traceability.md is
  generated, never hand-edited.
- Tests: tests/meta/test_traceability.py:131 (a bogus REF-99 fails the build).
- See it: .venv/bin/python scripts/check_traceability.py.

### 16. Version-pinned legal sources with amendment overlay (DEC-12)
- Grounding: REF-01, REF-02, REF-04 (all OFF).
- Implementation: src/tere4ai/ingest/sources.py:66-110 (base in_force,
  Omnibus adopted_not_yet_applicable, AMENDS and HAS_VERSION edges, never
  merged); gate G6 gates.py:126-141.
- Tests: tests/unit/test_sources.py:10, :32.
- See it: the coverage page's sources card with legal_status badges.

## D. Calibrated communication (the system tells you how much to trust it)

### 17. Closed calibrated status vocabulary, never "compliant" (DEC-08)
- Grounding: ADD-02 (PEER, Lee and See: appropriate reliance requires outputs
  that invite calibrated, not maximal, trust), ADD-03 (PEER, Jacovi et al.:
  warranted trust), ADD-05 (PEER, trustworthiness cues), REF-16 (the measured
  grounding ceiling that makes a compliance claim unsupportable).
- Implementation: src/tere4ai/mcp_server/tools.py:22-30 (7 values);
  make_envelope raises on anything else (:92-93).
- Tests: tests/unit/test_envelope_contract.py (every endpoint, every tier);
  tests/unit/test_mcp_tools.py:149.
- See it: no envelope can say compliant; try to find one.

### 18. Explicit abstention: missing_facts, unknown never false
- Grounding: ADD-02 (calibrated trust requires admitting ignorance), REF-30;
  mechanics stand on engineering merit.
- Implementation: classify.py:337-343 (absence is never false), :551-562
  (unknowns force requires_human_review at confidence 0.5).
- Tests: tests/unit/test_classify.py:185, :197, :329, :362.
- See it: POST /api/classify with only a description; count the missing_facts.

### 19. Non-legal-advice notice on every response
- Grounding: ADD-05 (communicating system limits is a trust cue); primarily
  the legal non-goal of Section 0 (engineering and ethics merit).
- Implementation: tools.py:54-58, unconditionally attached in make_envelope.
- Tests: envelope contract suite; UI renders it in the global footer.
- See it: every single envelope, plus /.well-known/tere4ai.json.

### 20. Surfaced not-expert-validated caveat on ethics mappings
- Grounding: REF-33 (OFF, ALTAI licensing and validity caveats), ADD-05;
  also a USER.md guardrail.
- Implementation: src/tere4ai/mcp_server/explain.py:29-34 (constant), emitted
  in explain (:235, :253) and trace (trace.py:151, :188).
- Tests: tests/unit/test_explain_trace_spans.py.
- See it: POST /api/trace; the caveat is in answer and legal_status_notes.

### 21. Degraded-mode honesty (no silent degradation)
- Grounding: engineering MUST (Section 13); ADD-03 supports the framing
  (warranted trust requires visible failure).
- Implementation: tools.py:110-118 (dump_unavailable_envelope, confidence 0.0);
  evidence.py:113-131 (judge_verdict not_run is distinct from a real verdict);
  facade 503 paths.
- Tests: tests/unit/test_http_facade.py:260, :280; demonstrated live in the
  2026-07-17 audit with an empty dump dir.
- See it: move the dumps away and call /api/health.

## E. Security posture

### 22. Untrusted-input fencing (evidence is data, never instructions)
- Grounding: REF-31 (STD, MCP security: keep instructions separate from
  retrieved content).
- Implementation: evidence.py:78-108 (fence markers);
  runtime_grounding.py:50-51, :75-91; prompt trust-boundary block in
  prompts/evaluate_evidence/v1.md.
- Tests: tests/unit/test_runtime_grounding.py:122; tests/unit/test_evidence.py:196.
- See it: submit "Ignore previous instructions..." as evidence; the answer
  degrades to requires_human_review.

### 23. Adversarial red-team corpus
- Grounding: REF-31, REF-16; security engineering merit.
- Implementation: tests/fixtures/adversarial_evidence.json (12 fixtures,
  4 attack classes) driven through the real evidence path.
- Tests: tests/unit/test_adversarial_evidence.py (including fooled-judge
  survival properties).
- See it: .venv/bin/python scripts/adversarial_evidence_report.py writes
  docs/SECURITY_EVAL.md.

### 24. Scoped revocable API keys; 25. rate limiting; 26. read-only tool surface
- Grounding: REF-31 (STD) for all three; engineering MUSTs of Section 8.
- Implementation: keys.py:86-137, :190-215 (salted hashes, constant-time
  compare, revocation, per-tool scopes); http_facade/app.py:186-205 (429 with
  Retry-After); server.py:56-58 (readOnlyHint on every tool, no write surface,
  no DB in the served path).
- Tests: tests/unit/test_mcp_keys.py; tests/unit/test_facade_hardening.py:50.
- See it: scripts/manage_mcp_keys.py; hit /api/health past the limit.

### 27. Audit logging with secret redaction and body-free metering
- Grounding: ADD-09 (PEER, end-to-end internal auditing), REF-31.
- Implementation: judge/audit_log.py:33-56 (recursive scrub of key-shaped
  material); runtime logs store hashes, never prompt text; facade and key
  metering are body-free by design.
- Tests: tests/unit/test_facade_hardening.py:34; tests/unit/test_mcp_keys.py:99;
  tests/unit/test_runtime_grounding.py:146.
- See it: data/review_queue/*_log.jsonl; scripts/consolidated_audit.py.

## F. Human oversight

### 28. requires_human_review plus the human review queue
- Grounding: ADD-09 (audit with who/when/why record); REF-24, REF-32 lineage.
- Implementation: review_queue/queue.py:92-169 (three pools),
  :183-212 (decisions demand rationale and reviewer identity);
  apply.py:37-65 (HUMAN_REVIEWED_* provenance, dumps never edited in place).
- Tests: tests/unit/test_review_queue.py:307, :334, :347.
- See it: the /review page (41 norms, 145 alignments, 102 crossrefs pending);
  scripts/review_cli.py.

### 29. Closed vocabularies everywhere (tiers, 7 HLEG principles, actor roles)
- Grounding: ADD-01 and REF-33 (OFF, the closed HLEG source set), REF-11 and
  REF-12 (PEER, actor canonicalisation lineage), ADD-24.
- Implementation: classify.py:248-254; hleg_nodes.py:29-71 (exactly seven,
  hard raise); canonicalize/canonicalizer.py:30-82 (unresolved actors are
  reported, never guessed).
- Tests: tests/unit/test_hleg_nodes.py:16; tests/unit/test_canonicalize.py:30.
- See it: schema validation fails on any invented category.

## G. Measurement (trust claims are measured, not asserted)

### 30. Ablation ladder with hallucination and completeness metrics (DEC-11)
- Grounding: REF-15 (PRE, the benchmark), REF-16 (PEER, baseline to beat),
  ADD-18 and ADD-19 (PEER, metric design).
- Implementation: src/tere4ai/eval/metrics.py:91-150; strategies.py:48-54.
- Tests: tests/unit/test_eval_metrics.py:85, :112.
- See it: eval/results/ablation_full_summary.json;
  eval/results/FULL_RUN_ANALYSIS.md.

### 31. Repeat-run variance measurement
- Grounding: REF-15, REF-16.
- Implementation: scripts/variance_report.py:67-165 (flip rate, citation
  Jaccard, determinism check).
- Tests: tests/unit/test_variance_report.py.
- See it: docs/variance_study.md (graph 0/345 flips vs plain LLM 43, vector
  RAG 51).

### 32. Judge FA/FR instrumentation and inter-annotator agreement
- Grounding: ADD-16 (agreement with humans is the judge-validity criterion),
  ADD-17 (PEER, human alignment of LLM evaluation), REF-16.
- Implementation: eval/metrics.py:153-206 (abstention never counted as FA or
  FR); scripts/sample_judge_decisions.py (deterministic stratified blind
  sheet); eval/agreement.py:47-66 (Cohen's kappa).
- Tests: tests/unit/test_eval_metrics.py:133; tests/unit/test_judge_sampling.py;
  tests/unit/test_agreement.py.
- HONEST STATUS: instrumented, unmeasured. The 50-decision sheet has zero
  human labels (task 25) and the second-annotator pass is pending (task 26).
  These are the thesis keystone measurements only the author can produce.

### 33. Cost gating before paid runs
- Grounding: engineering merit (spend control, honest token accounting);
  REF-15 tagged.
- Implementation: scripts/estimate_benchmark_cost.py:73-118 (dry run through
  the real strategy code; prices only from env, never invented).
- Tests: tests/unit/test_benchmark_cost_estimator.py.
- See it: docs/benchmark_cost_estimate.md, including the recorded
  estimate-vs-actual miss (5.33 quoted, 9.63 measured) kept as a lesson.

## The author's own lineage (SELF papers)

- SELF-01 (PEER, REFSQ 2026 Doctoral Symposium): trustworthy requirements
  generation for EU AI Act compliance via a knowledge graph; the direct
  ancestor of strategies 1, 3, 10-12.
- SELF-02 (PEER, ICSOB 2024): the PhD research plan on trustworthy LLMs for
  ethically aligned systems; frames the whole inventory.
- SELF-03 (PRE, arXiv:2503.04785): bibliometric map of LLM trustworthiness;
  supplies the trust-dimension vocabulary (support only, never sole
  grounding).
- SELF-04 (PEER, REFSQ 2026 Posters and Tools): TERE4AI as a tool; the
  published claim this codebase stays traceable to.
- SELF-05 (pending): the author's first PhD paper with early
  trustworthiness-enhancing strategies (multi-round debate, roles,
  structured conversation). Awaiting a readable PDF (the supplied file was
  empty); to be registered with the honest framing that those strategies are
  the historical layer this project's judge-gated, mechanically-checked
  pipeline supersedes, while the underlying idea (adversarial review of
  generated claims) survives here as the independent judge family.

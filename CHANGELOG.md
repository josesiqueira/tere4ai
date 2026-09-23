# Changelog

All notable changes to TERE4AI v2. Format loosely follows Keep a Changelog;
versions are git tags. Dates are build dates (Europe/Helsinki).

## [Unreleased]

### Evaluation records, the E1 acts, GET /api/evaluations, list lineage, judge run fields (2026-09-23, B77 plan 3a)
- DEC-17: one immutable evaluation record per measurement run of E1 and
  E6 (`src/tere4ai/eval/evaluation_record.py`), written by the ablation
  runner, the eval harness, the variance report and the judge-decision
  sampler; origin and outcome as two fields; identity by file digests plus
  the observed publication; outputs copied immutably; the July 2026
  measurements presented as legacy records that state only what their
  files state (`present_evaluation.py`).
- E1 as three recorded acts: the draw under an immutable sample id with
  any-sheet overwrite protection; `--label` and `--label-file` with `--by`,
  recording actor and time per item; `--compute` refusing an unattributed
  label, rates per judge kind and pooled, null on an empty denominator
  (`metrics.judge_error_rates`, METRICS_VERSION metrics.v2).
- The draw over an active publication whose manifest lacks a role refuses
  with a sentence and exit code 2 unless `--norms`, `--alignments` or
  `--layer1` names the file directly.
- `GET /api/evaluations` and `GET /api/evaluations/{ref}`: free, read per
  request, grouped by build identity, an unreadable file its own row, an
  outage a 503 never an empty list; the schema and fifteen fixtures under
  `tests/fixtures/evaluation_records/` are the dashboard's contract.
- The builds list rows carry `lineage` (inherited-from record ids per
  step, consumed freezes with the consuming step; spec G D-G44); the
  build record fixtures regenerated.
- `GET /api/units` candidates and traced assertions (the MCP trace tool,
  `/api/trace`, `/api/trace/batch`) carry the judge run's `completed_at`
  and `prompt_sha256`, null where the dump lacks it (spec G D-G39).
- `data/graph_dumps/evaluation_records/` joins the artefact policy
  (git-ignored).

### Judge model: claude-opus-5-5 (2026-09-23)
- `TERE4AI_JUDGE_MODEL` names Claude Opus 5.5 (`claude-opus-5-5`, listed by
  the Models API, created 2026-09-21) in `.env.example`, `docker-compose.yml`
  and the Rahti deployment; the local `.env` follows. No client change: the
  judge client sends no thinking or tool_choice parameter, learns a rejected
  temperature once and caps output at 16000 tokens, all of which Opus 5.5
  accepts. Recorded: Opus 5.5 cannot disable thinking and its provider
  default effort is medium where Opus 5's was high; the client sets no
  effort, so the provider default runs (spec F D-F16, D-F17). The B74
  extraction of 2026-09-16 (judged by claude-opus-5) stays on disk as
  history; the graph is rebuilt from Layer 0 with the current models
  (thesis HISTORY 2026-09-23).

### Vocabulary: `align_hleg` and the `inherited` step state (2026-09-23)
- The Layer 3 command is `python -m tere4ai.align_hleg`, renamed from
  `align_hleg_altai`. The graph aligns norms with the seven HLEG
  requirements only: ALTAI items were planned behind a licence check that
  never cleared and were never emitted, so the old name promised something
  the build does not do. ALTAI stays a future option (thesis, 2026-09-23).
  Build records store the new command name; no record on disk carried the
  old one, and checkpoint paths derive from the output path, so the B74
  resume is unaffected.
- The step state `done_shared` is renamed `inherited` in the build record
  contract (schema, the six fixtures, `GET /api/builds`): the build did not
  run the step and uses the artefact a lineage record produced, which the
  reason names by record id, resolved by the artefact digest, not by
  position in the chain.

### Build records, materialisation, publication and activation (2026-09-22, B77 plan 2a)
- Build records for every pipeline command with validated resume;
  `scripts/materialize_reference.py`; publication after the post-load gates
  with per-layer gating, per-gate outcomes, freeze manifests in the chain id
  and a Neo4j target state; explicit activation (`scripts/activate_build.py`)
  with one loader for the facade and the MCP server; `GET /api/builds` and
  `GET /api/builds/{ref}` with a JSON schema and fixtures for the dashboard
  (DEC-16, B77 plan 2a). `publish_layer23 --decisions` retired.

### Human review decisions (2026-09-17, B77 plan 1)
- The decisions file gains two new decision kinds, `replace` and `add`, each
  carrying a human-written norm in `payload` (a required `actor_explicit`
  key, nullable, plus the other norm slots): `replace` overwrites the slot
  fields of an existing norm named by `queue_id` but refuses to move it to
  another `source_node_id` or `source_span_id` (reject plus add is the way
  to re-attribute a norm), `add` appends a brand new norm whose id is
  `queue_id`; `apply_decisions` stamps both with `extraction_method: "human"`,
  `extractor_model: "human:<reviewer>"`, `confidence: 1.0`, `judge_verdict`
  and `review_status` `"accepted"`, and `judge_run_id: None`. A payload that
  sets `actor_inferred` to any non-null value, the `"unspecified_needs_review"`
  sentinel included, must also carry `actor_inference_source_node_id`,
  mirroring the norms schema's conditional rule with no carve-out.
- New provenance class `HUMAN_AUTHORED` in `schema/json_schemas/edges.schema.json`,
  recorded in `human_review.provenance` for both new decision kinds.
- `GET /api/units` (Task 1, B77 plan 1) serves every core source unit with
  all candidate norms and judge runs.
- Every human norm is validated before it is accepted, whoever produced the
  decisions file: the payload checks live in `validate_human_payload`, which
  `record_decision`, `load_decisions` (every entry) and `apply_decisions`
  (every `replace` and `add`) all call, and `apply_decisions` validates the
  completed norm against `schema/json_schemas/norms.schema.json`, raising
  with the norm id and the failing field instead of publishing it.
- A `replace` takes its actor triple (`actor_explicit`, `actor_inferred`,
  `actor_inference_source_node_id`) from the payload alone: a key the human
  omits becomes null rather than inheriting the model's inferred actor onto
  a norm recorded as `HUMAN_AUTHORED`.
- The clause ids follow the human's text: `replace` and `add` reset
  `condition_ids` and `exception_ids`, and `scripts/publish_layer23.py` runs
  `canonicalize_norms` over the applied norms payload, so `HAS_CONDITION`
  and `HAS_EXCEPTION` are re-materialised from the human's `conditions` and
  `exceptions` wording (a removed condition loses its edge, an added one
  gains its clause node).

### Diagrams (2026-09-17)
- Diagram files carry the date they were produced: the 2026-07-19
  architecture diagram and the 2026-07-20 judge diagram keep their content
  under dated names (`tere4ai_v2_architecture_2026-07-19.svg/.png`,
  `judge_diagram_2026-07-20.svg/.png`); each generator has a `DIAGRAM_DATE`
  and writes `<name>_<date>.svg`, so an older dated file is history, never
  a test failure. The web page and the mermaid companions point at the dated
  names.
- New architecture diagram, `tere4ai_v2_architecture_2026-09-17`: the
  browser consumer is the tere4ai-dashboard with four views (Build,
  Evaluate, Use, Research); the demo web UI is no longer drawn as the
  product surface (retained in `web/` for the MCP demo recording and
  screenshots); the served build id carries the publication chain and the
  model ids are gpt-6-astra and claude-opus-5 (B74).
- Evaluate is drawn as its own phase (specialist grading, judge calibration
  B68, judge error rates H1, benchmark and ablations) feeding decisions
  back to the human review queue once closing rules are set; the review
  queue box states what the code does today and the agreed direction.
- To follow, with the four-views design: a separate evaluation diagram and
  a new judge diagram (the 2026-07-20 one predates B74 and B68).
- Status is stated on the diagram (AGENTS.md honesty rule): every view and
  Evaluate item is marked built, designed, run or pending, and the credit
  line says that designed items are intent as of the diagram date, not
  shipped code; docs/traceability.md states what is implemented. The
  architecture test requires those marks.

### Models and build identity (2026-09-16, B74)
- Production models moved to `gpt-6-astra` (generator) and `claude-opus-5`
  (judge); both ids verified against the providers' live model lists on
  2026-09-16. Defaults updated in `.env.example`, `docker-compose.yml` and
  `deploy/rahti/deployment-facade.yaml`. The evaluation records under
  `eval/` keep naming the models they were measured with.
- Model clients: a rejected `temperature: 0` is learned once per client
  instead of costing one refused request per call (gpt-6-astra answers 400
  for it; the anthropic SDK 1.x no longer accepts the keyword). JSON mode
  survives a temperature rejection on the generator. Each client reports
  `.sampling` as "0", "provider default (rejected by the model)", "mixed"
  or "no replies", and both build entry points record it, the provider
  token usage and a timestamp in the dump's `build` record
  (`extraction_sampling`, `extraction_usage`, `extracted_at`;
  `alignment_sampling`, `alignment_usage`, `aligned_at`).
- The judge's output cap is 16000 tokens (was 2048): current Claude models
  think before answering and the thinking counts against `max_tokens`.
- Served build id. The facade's `/api/health` (`graph_version`,
  `norms_build`) and every envelope from both transports now carry the
  chained id `<snapshot build>+chain-<12hex>` that `publish_layer23`
  stamps on the published graph, recomputed over the exact dump files
  served. Before, only the legal snapshot hash was reported, which does
  not change when the norms are re-extracted, so a rebuild was
  indistinguishable from the build it replaced and a dashboard campaign
  pinned to the old build could be graded on the new one.
  `tere4ai.graph_store.build_chain.served_build_id` and
  `stamp_served_build` implement it; a directory without published norms
  keeps the bare snapshot id.

### Repository (2026-08-28)
- Repository split. The research record moved to a separate private repository:
  the task board, design plans and specs, research inputs, the audit journal and
  its dated reports, the agent session briefs, the reference corpus, and the
  paper artifacts with their bundler. This repository keeps the tool, its
  documentation, its evaluation harness, its measured results and its
  screenshots. A clone with no sibling installs, tests and passes CI unchanged;
  verified on a fresh clone (644 passed, 12 skipped, ruff clean, both gates
  green, web build succeeds).
- `docs/DEMO.md` no longer contains absolute home paths; sibling checkouts are
  referenced relatively.
- `scripts/make_paper_artifacts.py` writes to `build/paper_artifacts` by default
  (gitignored) instead of `docs/paper_artifacts`.
- `USER.md` reduced to domain guardrails and writing conventions. The filename
  is unchanged deliberately: five files under `src/` cite it as normative.
- `hooks/pre-commit` added (opt in with `git config core.hooksPath hooks`). It
  is a maintainer aid and degrades to a no-op for anyone else.

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
- Facade-wide UTF-8 encodability guard (B63, 2026-09-09). An escaped lone
  UTF-16 surrogate such as {"session_jsonl": "\ud800"} is legal JSON that
  parses to a Python str no UTF-8 encoder accepts; it passed Pydantic and
  crashed the response encoder, or the error-detail encoder, as an uncaught
  UnicodeEncodeError, a raw 500 on eight of the nine POST routes. Same class
  as the NaN/Infinity hole closed earlier. Every facade request model now
  inherits a before-validator that walks the raw body (top-level strings,
  lists, free dicts and their keys) and rejects the first unencodable string
  with a 422; the validation-error handler sanitizes unencodable strings in
  the echoed input the way it already sanitized non-finite floats, so the
  422 itself is always encodable. Twelve attack cases (one or two per route,
  surrogate at top level, in a list, in a nested dict) and one regression
  for legitimate non-ASCII text (accents, an astral emoji) in
  tests/unit/test_http_facade.py. Surfaced by the B45 plan 1 final review;
  pre-existing, not a regression.
- MCP coverage_report parity with the facade (B62, 2026-09-09). The MCP
  wrapper called the coverage function with the dump alone, so layer 2 and
  layer 3 read count 0 and not_started over MCP while GET /api/coverage,
  which passes the judged norms and alignments payloads, reported the real
  counts with verdict breakdowns. The wrapper now passes both payloads like
  the neighbouring tools, and a parity case in
  tests/unit/test_facade_mcp_parity.py goes through the wrapper itself so
  the two surfaces cannot drift again. Pre-existing since the facade route
  landed, surfaced by the B45 plan 1 final review.
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
- Two standing integrity gates codify what previous audits verified by
  hand: the published dumps must match exactly one recorded build-chain
  checksum record (a tampered dump fails the gate), and a citation census
  resolves every judge-accepted norm's source span through the production
  resolver to checksum-verified, non-empty source text (339 norms over
  155 unique spans, about one second).
- Missing-context fixes (audit findings F2 to F4): get_applicable_requirements
  now surfaces each norm's exceptions (carve-outs were silently dropped for
  37 accepted norms; a census test guards it); the feature elicitor prompt
  v3 embeds the binding Article 3 definitions verbatim from the graph for
  every legally-defined flag term (drift-guarded against the dump); and the
  runtime grounding judge's cited-norm digest now includes the norm's
  verbatim source text, matching what the generator it gates already sees.
- Judge provenance and independence: every generator and judge event and
  every JudgeRun records prompt_sha256 (in-place prompt edits are detectable
  and tied to their decisions); the config loader rejects a judge equal to
  the generator, and all four judged pipelines refuse the same client object
  as both generator and judge.
- docs/TASKS.md: the tracked task board, split into human-required,
  agent-next, and externally-blocked work.
- FRIA applicability as a deterministic rule (DEC-14): classify_ai_system
  answers now carry a fria block deciding whether the Article 27(1)
  fundamental rights impact assessment obligation applies (applies,
  does_not_apply, unknown), from the Article 6(2) route, the Annex III
  point 2 exception, the new point 5(b)/(c) sub-flags
  (creditworthiness_evaluation, life_health_insurance_risk_pricing), and
  the new structured deployer facts (body governed by public law, private
  entity providing public services). Unsettled facts are named, never
  guessed; a system matching both the excepted point 2 area and a 5(b)/(c)
  trigger is routed to human review; get_applicable_requirements passes
  the block through next to the article-27 obligations. Only applicability
  is decided, never the assessment's content.
- DEC-14 hardening (same day, scope decision recorded: TERE4AI detects
  whether a FRIA is required and will not generate FRIA content): a pending
  Article 6(3) derogation candidacy now blocks the FRIA decision (unknown,
  naming the pending human review) instead of letting a deployer trigger
  force "applies" past an unsettled Article 6(2) status; and every fria
  block carries applies_from as data, never control flow (2 December 2027
  for standalone Annex III obligations per the Digital Omnibus, status
  adopted_not_yet_applicable, final OJ reference pending, checked
  2026-07-20: Parliament 16 June and Council 29 June 2026 approvals, OJ
  publication imminent).
- Remote MCP transport (streamable HTTP) behind TERE4AI_MCP_TRANSPORT=http,
  gated by scoped, revocable t4a_ API keys with body-free usage metering
  (scripts/manage_mcp_keys.py).

### Audit fixes (2026-07-20 full-system audit)
- Classifier unknown-fact discipline (D1): unknown Annex III high-risk flags
  are now surfaced in missing_facts and block a confident minimal_or_none
  verdict, mirroring the prohibition flags; a genuine high-risk system
  described without the exact flag is no longer cleared as "not regulated" at
  confidence 1.0. Domain is Unicode-normalised (D8) so an invisible or
  homoglyph character cannot silently make a known domain read as
  out-of-scope.
- Article 5 exculpating-fact model (D2): the prohibition flags no longer
  collapse the statute's qualifiers and exceptions; each qualified point
  carries an exculpating fact, so a lawful system (a medical/safety emotion
  system, a fact-based investigator-support tool) is not marked prohibited at
  confidence 1.0, and an unknown exception fact routes to human review.
- FRIA correctness (D5/D6/D7): the point-2 exception is scoped to the area,
  not the whole system, so a multi-area public-body system keeps its
  obligation; an unsettled classification or a pending Article 6(3) derogation
  degrades the FRIA block to unknown instead of a confident applies.
- Runtime integrity and honesty (D3/D4/D9): the server verifies the served
  dumps against a recorded build chain at startup (hard-fail behind
  TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY=1); the evidence and backlog tools
  resolve each norm's verbatim source_text before the model so the grounding
  judge can detect paraphrase drift in production; empty content degrades to a
  Section 8 envelope instead of raising.
- Hardening: FRIA rule model-free guard test and served-envelope guard;
  mechanical quote-check JudgeRun now carries a content hash of its own logic;
  degraded envelopes name files, not absolute server paths; SKILL.md, llms.txt
  and trustworthiness_strategies.md advertise the FRIA block; the SELF-05
  registration contradiction is fixed.

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

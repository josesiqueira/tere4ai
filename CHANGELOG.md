# Changelog

All notable changes to TERE4AI v2. Format loosely follows Keep a Changelog;
versions are git tags. Dates are build dates (Europe/Helsinki).

## [Unreleased]

### C3: both MCP revisions supported, tested and documented
- fastmcp 4.0.10, pinned `fastmcp>=4.0.10,<4.1` (was `>=2.0`, 4.0.3
  installed); the suite passes unchanged on it. The server advertises no
  MCP logging capability in either revision and answers
  logging/setLevel with method not found (a `_NoMcpLogging` middleware
  in server.py, through fastmcp's public Middleware hooks: fastmcp
  registers a setLevel handler on every server and offers no option to
  leave it out); diagnostics stay Python logging on stderr. New
  tests/unit/test_mcp_protocol_revisions.py starts the server over stdio
  and over streamable HTTP (a free localhost port, a key from a
  temporary key store) and drives it with the official MCP Python SDK
  client in mode "legacy" (negotiates 2025-11-25) and mode "2026-07-28":
  tools/list serves every scoped tool alphabetically, coverage_report
  answers, the initialize and server/discover results carry no logging
  capability; a source scan finds no MCP log call in src.
- The four paid tools (evaluate_project_evidence,
  evaluate_project_evidence_batch, generate_control_backlog,
  elicit_features) are not paid twice for an identical call (new
  src/tere4ai/mcp_server/replay.py, C3 ruling R3). The key is the SHA-256
  of the caller (the key id the key middleware verified, else "local"),
  the tool, the arguments as canonical JSON, the served build id and the
  model parameters hash. An answer the models produced is kept in process
  memory for TERE4AI_MCP_REPLAY_WINDOW_SECONDS (default 600; 0 keeps
  nothing; an unusable value stops the server at start); an identical
  call inside the window, or one made while the first is running, gets
  that answer with the note "this answer repeats the answer to an
  identical call made at <UTC time>; no new model call was made" in
  legal_status_notes. Refusals before the model call, degraded answers
  (refused, judge not run or judge error, an elicitation without an
  answer, a batch with such a norm) and exceptions are never kept, so a
  retry after a failure pays again. At most 256 answers, oldest dropped,
  per process. `_paid_clients_or_envelope` now returns `PaidClients`
  (generator, judge, model_parameters_sha256), and ScopedKeyMiddleware
  sets the caller for the call. New tests/unit/test_mcp_replay.py.
- Documentation: the README section "MCP revisions and clients" names the
  supported revisions (2026-07-28 and legacy, both transports), the absent
  MCP logging capability, the replay window and its per-process limit, the
  one tested client (official MCP Python SDK, mcp 2.2.0) and a table of
  client support as the vendors' public sources reported it on 2026-09-30
  (not tested here). REF-31 and architecture.md Section 8 state the dual era
  and SKILL.md no longer names a revision.
- Final review fixes. A repeated paid answer sets every usage count under
  answer.usage (and under each batch result's answer.usage) to 0, and when
  the answer carries usage (today the backlog's) its note ends "no new
  model call was made, so its usage counts are 0; the first call's usage is
  in the answer it returned", so a client that adds up usage counts the
  first call once. A window of 0 turns the replay
  off (no store, no wait for an identical running call). The window is
  aged by time.monotonic(); the UTC wall time only dates the note. The
  protocol tests assert the logging/setLevel refusal over HTTP too, write
  the HTTP server's stderr to a file whose tail is in every start failure,
  count the server ready only once it says it listens on the port, and
  start it once more on a new port when it exits with address in use. The
  dev extras pin `mcp>=2.2,<2.3`, the SDK client the protocol tests use.
  The README's client table is headed as the research input's report, not
  checked or tested here.

### The elicitor quotes the Act from the graph and the description for every fact, and is an MCP tool (B10, DEC-13, DEC-18)
- New module `tere4ai.elicit_features.provisions`: a prompt template names
  a provision as `{{provision:<node id>}}`, and rendering prints it as
  `[<node id>] <text>`, the node's own `text` in the served build's dump,
  after the node's span has been verified against its snapshot checksum
  (the raw Formex XML or EUR-Lex HTML slice is never printed). An unknown
  node, a node without text, a node without a span, or a span that fails
  verification raises `ProvisionUnresolved`, naming the node, the build id
  and the reason. `fact_provisions` reads the fact-to-provision table from
  the template's "## Facts and their provisions" section. Nothing calls it
  yet.
- New prompt `prompts/elicit_features/v6.md`: v5's role, field list,
  binding rules 1 to 5, consistency rules and Omnibus block (now headed as
  verbatim from the amending act, the base graph having no node for points
  (ba) and (bb)), with every hand-pasted or paraphrased provision replaced
  by a placeholder under "## Facts and their provisions": 58 nodes, every
  schema flag but the two Omnibus facts with at least one, the Article 5
  and Annex III flags quoting the classifier's own point. The reply becomes
  `{"features": {...}, "quotes": {...}}`, a quote of at least three words
  from the description for every fact, true or false, with a worked
  example. The default prompt stays v5 until the elicitor can render v6
  (Task 3); v1 to v5 are unchanged.
- New entry point `tere4ai.elicit_features.elicit(description, generator,
  *, dump, snapshots_dir, prompt_version)` returning an `Elicitation`
  (features, quotes, dropped, notes, prompt). The template is rendered over
  the served build's dump first; a provision that does not resolve returns
  no features and the note "definition <id> does not resolve in <build>:
  <reason>; no model call made", with no generator call. A v6 fact is kept
  only with a quote of at least three words found in the description
  (whitespace runs collapsed, no case folding), its start and end in code
  points of the original description, first occurrence; every other fact
  is removed and named in dropped ("no quote", "quote shorter than three
  words", "quote not in the description"). The prompt record names the
  template's SHA-256, the rendered prompt's SHA-256, the provisions and the
  build. DEFAULT_PROMPT_VERSION is now v6. `elicit_features` stays as a
  wrapper over `elicit` for the facade and the benchmark script until they
  move (Tasks 4 and 5): without a dump it serves the build load_active
  reads from data/graph_dumps, and it names each dropped fact in its notes.
- The elicitation envelope (`tere4ai.mcp_server.elicit.elicit_envelope`) takes
  the served build's dump and snapshots dir and calls `elicit`: the answer
  becomes {"features", "quotes", "dropped", "notes", "prompt"} and
  graph_version is the dump's build. missing_facts names every flag not
  elicited and every dropped fact once ("flags.x dropped: quote not in the
  description" in place of "flag not elicited: x"); when a provision does not
  resolve it carries the "definition <id> does not resolve" line.
  legal_status_notes adds that code checked the quoted words are in the
  description and a person judges whether they support the fact. A failed
  elicitation still answers null.
- POST /api/elicit passes the build it serves; the response gains the answer
  fields with no other change. New MCP tool `elicit_features(description)`
  (PAID, one generator call, no judge) over the active build per call, with
  the facade's 30-character floor (`MIN_DESCRIPTION_CHARS`, now read by both),
  degrading without a dump, on an empty or short description, or on missing
  model configuration, before any model client is built. New key scope
  `elicit_paid` (ruling R11) in SCOPES, TOOL_SCOPES and the key manager;
  docs/PHASE2_DESIGN.md Section 3 (six scopes), SKILL.md's tool list and the
  server instructions name the tool.
- `scripts/elicit_benchmark_features.py` elicits with `elicit` over the build
  `load_active` serves and renders the prompt once before the first item
  (new `render_prompt`, the prompt and record `elicit` uses; a build that does
  not load or a provision that does not resolve exits 2 before any client is
  built). Each checkpoint entry gains "quotes", "dropped" and "prompt"; the
  output gains "prompt" (one record: prompt, version, template and rendered
  hashes, provisions, build), "quotes_by_item" and "dropped_by_item" beside
  the unchanged "features_by_item" and "prompt_version". A rerun over entries
  of another prompt version, template, rendered prompt or build (or entries
  without a prompt record) is refused with exit 2, as one under other models
  is. The `elicit_features` wrapper is deleted: its last callers were this
  script and four tests, which now call `elicit`. `scripts/run_ablations.py`
  names the elicitor's prompt in the E6 record's prompt_versions
  (`"elicit_features": {"version", "template_sha256"}`, from the facts file's
  "prompt"; a facts file from before B10 gives its prompt_version and a null
  hash) when it reads the facts file, beside each strategy's models.
  `scripts/estimate_benchmark_cost.py` counts the default prompt rendered over
  data/graph_dumps/layer1.json (no model call); docs/benchmark_cost_estimate.md
  is regenerated (the rendered v6 prompt is about 40,700 characters against
  v5's 14,200, so the elicitation row rises from 210,602 to 3,475,257 input
  tokens). docs/architecture.md DEC-13 and DEC-18 say that the provisions are
  read from the graph at call time and each fact needs its quote; README lists
  `elicit_features` among the paid tools and /api/elicit among the paid
  endpoints.
- Final review fixes: a v6 field the model sets to null or to an empty list
  (and a deployer key set to null) states no fact, so it is removed as
  unknown, needs no quote and is not named in dropped (a null deployer key no
  longer fails the schema and costs a retry). A quote is found only on word
  boundaries: the character before and after the match, where there is one,
  is not a letter or digit, and a later occurrence is searched when the first
  cuts a word ("ank scores loan" is not in "bank scores loan"). The E6
  record's `"elicit_features"` entry adds `rendered_sha256` and
  `graph_version` from the facts file's "prompt" (null for a file from before
  B10). `scripts/estimate_benchmark_cost.py` counts an elicitation reply as
  its features plus its quotes when the facts file has `quotes_by_item`;
  without them it counts features only and docs/benchmark_cost_estimate.md
  says so (regenerated, figures unchanged).

### Every operator obligation and every generated control carries its requirement type (B65, B4, DEC-19)
- Contract change: norms.schema.json gains `requirement_type` (functional,
  quality or process, three of the examples of ISO/IEC/IEEE 29148:2018
  clause 5.2.8.3, ADD-54) and the extraction judge's recorded view of it,
  `judge_type_agrees` and `judge_requirement_type`. All three are optional
  and nullable: an extractor reply that omits the type or gives another
  value keeps the norm with null, never drops it.
- The definitions of the three types, the reading rules and the scope have
  one source each, prompts/requirement_type/definitions.md and scope.md,
  which the v2 prompts carry byte for byte and the dashboard pins its copy
  against.
- The scope is applied in code: a norm keeps its type only when it is an
  obligation or a prohibition, its source unit is outside Articles 5 to 7
  and the annexes, and its actor, explicit or inferred, is an operator;
  every other norm carries null, read "not an operator requirement",
  whatever the extractor proposed. An in-scope norm the extractor left
  untyped reads "no type" and is counted in the extraction stats
  (`untyped_in_scope`) and the execution record's counts. An annotator's or
  the adjudicator's type stands as given.
- Prompts extract_norms v2 and judge_norms v2 (one shared version, now the
  default of `extract_norms` and `python -m tere4ai.extract_norms`) carry
  that text. The judge records whether it agrees with the type and, when it
  does not, its own type; the type never changes the verdict, and a reply
  without that view keeps its verdict and records null. A run under the v1
  prompts feeds its judges what it always did and writes no type field.
- Thesis task B4, a change of the extraction judge as an instrument: from
  judge_norms v2 the judge's input carries the verbatim text of the
  actor-inference source (DEC-04), the whole Article for an Article id such
  as `eu-ai-act:article-16`, for the actor check only, so an inferred actor
  is judged against the provision it rests on. The E1 label sheet shows the
  labeller the same text (`actor_inference_source`).
- Contract change: get_applicable_requirements entries, the
  explain_requirement deontic block and the facade's `/api/units`
  candidates carry `requirement_type` when the norm carries it; a norm from
  a build before DEC-19 gains no key. The units candidate's `judge` block
  carries the judge's recorded view on the same rule. The type, the view
  and the judge run's view are stored in Neo4j.
- Human review: a replace or add payload must carry `requirement_type`
  (one of the three or null); a human norm clears the model judge's view.
  The queue digest, the near-duplicate pairs and report, the E1 label
  sheet (the type as judged content, the judge's view in the folded judge
  block, and the rule that the type never decides accept or reject) and
  the demo UI's review queue view show the type.
- Contract change: under generate_backlog v2 and runtime_grounding v2, now
  the backlog's default, items carry their own `requirement_type` (null
  with a note when the generator gave none or an invalid one), and the
  answer carries `judge_type_views`, the runtime judge's view of each
  item's type in item order, which never changes the backlog's verdict.
  Neither digest carries the norms' types, nor does the ablation's. Merged
  items keep the first item's type, and a different type is named in the
  note. A v1 backlog keeps its old input and output.
- evaluate_project_evidence and its batch keep evaluate_evidence v1 and
  runtime_grounding v1 (`GENERATOR_PROMPT_VERSION`, `JUDGE_PROMPT_VERSION`
  and a new `judge_prompt_version` parameter); their version is no longer
  the backlog's. The report shows each requirement's and each control's
  requirement type, the explain record's, and the judge's view of a
  control's type.
- data/graph_dumps/norms_core.json predates DEC-19 and is not converted
  (everything before B74 is disposable); B74 extracts and generates with
  the v2 prompts.

### A high-risk answer keeps its Article 50 duties; biometric categorisation is three facts (B36.2, DEC-18)
- `classify_ai_system`'s answer gains `transparency_duties`, always present:
  the Article 50 paragraph node ids whose trigger fact is true
  (`eu-ai-act:article-50:paragraph-1` interaction with natural persons,
  `paragraph-2` synthetic content, `paragraph-3` emotion recognition or a
  biometric categorisation system). It lists them on every answer except
  the prohibited and the rejected-input ones, where it is empty, so a
  high-risk answer now names its Article 50 duties (Article 50(6)). An
  empty list means none is triggered by a known fact, never ruled out. A
  listed paragraph is triggered, not proven: legal_status_notes says the
  paragraphs' own exceptions and paragraphs 4 and 5 are not decided by the
  rules. Contract change: a client that shows the classification shows the
  list worded "triggered". `risk_category` keeps its values;
  `transparency_only` still means Article 50 without high-risk.
- An absent Article 50 trigger fact is named in missing_facts on the
  high-risk and minimal answers; status, confidence and category do not
  change.
- Two new facts in system_features.schema.json:
  `biometric_categorisation_system` (Article 3(40), the Article 50(3)
  trigger) and `biometric_categorisation_sensitive_or_protected_attributes`
  (Annex III point 1(b), high-risk beside point 1's other uses). Like
  every Annex III fact the second one blocks a confident minimal answer
  while it is absent, so a feature set written before this change
  classifies uncertain where it classified minimal until the fact is
  given. The gold seed settles both as false in every item that
  enumerates its flags; no gold verdict changed.
- `biometric_categorisation` now means exactly the Article 5(1)(g) traits,
  and the point (d) and (g) exception facts are defined by the Act's words
  (schema descriptions and rationale text). They still never settle an
  absent Article 5 flag.
- The elicitor prompt is v5 (prompts/elicit_features/v5.md), one default
  (`DEFAULT_PROMPT_VERSION`) for `elicit_features`, the facade's
  `/api/elicit` and scripts/elicit_benchmark_features.py (its default was
  v2); v4 is kept for the records that name it. v5 also names the two
  Omnibus prohibition facts (points (ba) and (bb)), quoting the amending
  act, so an elicitation can now settle them.
- `get_applicable_requirements` is unchanged: a high-risk system is still
  served the whole Article 50 group.

### The classification says "unknown" when an Article 5 fact is missing (B36.1, DEC-18)
- `classify_ai_system`'s `prohibited` field is now `true`, `false` or
  `null`. `null` means unknown: no prohibition is proven and at least one
  Article 5 path cannot be settled because a fact is missing. `false` now
  means every Article 5 path is ruled out. Before, the field was `false`
  on every answer that was not prohibited. Contract change: a client that
  shows the field must show `null` as unknown, never as false.
- Each Article 5 point is resolved on its own. An absent flag is no longer
  reported as missing when another known fact already rules its point out:
  significant harm known false for points (a) and (b), the detrimental
  treatment known false for (c), the medical or safety exception known true
  for (f), and for (h) no law-enforcement use or the strict-necessity
  carve-out. The status lowering and the uncertain exit read the same
  resolution, so some answers move from uncertain to the exit their other
  facts give.
- `real_time_remote_biometric_public` is reported as an unknown Annex III
  fact when its Article 5 path is ruled out, so it still blocks a confident
  minimal answer.
- The rejected-input answer gives `prohibited: null`.
- `get_applicable_requirements` explains an uncertain classification by
  its cause: an unknown Article 5 fact, or (with every Article 5 path ruled
  out) an unknown high-risk fact.
- The HTML report, `scripts/make_compliance.py`, `scripts/make_prohibition.py`
  and the demo `/assess` page show `unknown` for a null `prohibited`.
- "uncertain" is an assessment state, not a legal risk level.

### The backlog answer names its two prompts (B99.7a, spec F D-F35 (1))
- `generate_control_backlog`'s answer gains six fields beside each role's
  model, effort and temperature: `generator_prompt` (`generate_backlog`),
  `generator_prompt_version`, `generator_prompt_sha256`, `judge_prompt`
  (`runtime_grounding`), `judge_prompt_version` and `judge_prompt_sha256`,
  the SHA-256 of the prompt file's text as the audit log records it. Every
  answer that carries the spend carries them, a degraded one included; a
  judged answer takes the judge's hash from its judge run, and a judge
  prompt file that cannot be read is named with `judge_prompt_sha256` null
  (the judge then does not run). Answers stored before keep what they
  carry.

### Requests rejected before processing counted apart (B99.1a, spec F D-F32)
- A seventh per-role count, `requests_rejected_before_processing`, counts the
  attempts the provider answered with HTTP 400, 401, 403, 404, 413, 422 or 429
  (`REJECTED_BEFORE_PROCESSING_STATUSES` in
  `src/tere4ai/extract_norms/model_clients.py`), which the providers are
  taken not to bill (spec F D-F26 (e): Anthropic's billing guidance; for
  OpenAI inferred, no invoice checked). It is a subset of `requests_refused`, which keeps counting every HTTP
  error status, and each such attempt stays in `requests_sent`. A 400 naming a
  declared parameter and a retried 429 count here; 408, 409, 499, any 5xx, a
  timeout, a lost connection and an interrupt never do.
- The count travels wherever the other counts do: the execution records of
  extract_norms and align_hleg, the evaluation records, the per-role summary
  of `scripts/run_ablations.py` (a unit checkpointed without it leaves only
  that count out for its role) and the backlog answer's usage.
- `build_record.schema.json` `role_usage` gains it as an optional
  non-negative integer; the schema stays `build_record.v1`. The mock record
  `resumed_align.json` carries it and `requests_refused` on both attempts;
  the resumed attempt's generator met one 429, retried, so it now reads 3
  requests sent (2 before), 1 refused and 1 rejected before processing.
  Records made before keep what they carry.

### Declared model parameters and the terminal retry policy (B99, spec F D-F29, D-F30)
- Each model's temperature, effort and JSON mode are declared in
  `config/model_parameters.json`, keyed by model id; the table selects nothing
  (`.env` names the models). A configured model with no row, a row of the
  other provider, a row without its documentation page and read day, or a
  malformed row is refused at configuration load with `ConfigurationError` (a
  `ModelConfigError`), naming every problem at once.
  `TERE4AI_GENERATOR_EFFORT` and `TERE4AI_JUDGE_EFFORT` are no longer read and
  are refused while set; they left `.env.example`, `docker-compose.yml` and
  the Rahti deployment, and the image copies `config/`. The execution record's
  `models` carries the declared values and `model_parameters_sha256`, so a
  resume under an edited row is refused by name, and a checkpoint written
  before this change cannot be resumed. The two committed rows (`gpt-6-astra`,
  `claude-opus-5-5`) were read from the providers' documentation on 2026-09-28
  and each names the page it was read from; the values match what the code and
  the B74 records had shown. An uncommitted edit of the table marks an
  evaluation record's code version dirty.
- The generator and judge clients send each model's declared temperature,
  effort and JSON mode on every request and never learn: a parameter declared
  N/A is never sent, and a declared one that the provider refuses with a 400
  (counted in `requests_sent` and `requests_refused`) or the SDK refuses
  before sending (not counted) raises `DeclaredParameterRefused`, a
  configuration error naming the model, the parameter and the table. The
  clients report `temperature`, `effort` and `json_mode` as declared;
  `sampling` stays the name of the declared temperature. The learned words
  of records made before this change are kept as stored.
- The model clients take a retry policy from their caller (`retry_policy=`,
  spec F D-F30). `SERVICE_POLICY`, the default, is exactly today's two retries
  at 1 and 4 s with a Retry-After in seconds capped at 60 s. `TERMINAL_POLICY`
  retries 408, 409, 429 other than a quota refusal (`insufficient_quota`), any
  5xx, a timeout or a lost connection after pauses of 10, 30, 90, 270 and 600
  s (a Retry-After, read in seconds, as a date or as retry-after-ms, lengthens
  a pause up to 600 s), prints one alert line on standard error before each
  pause (`ALERT <UTC time> <provider>:<model>: <status or error>; attempt <n>
  of 6 failed; next attempt in <s> s`, the pause in whole seconds rounded up),
  and after the sixth attempt raises `ProviderUnavailable` ("provider
  unavailable after 6 attempts: <status or error>"); every other 4xx and an
  SDK error before sending stop at once as `ProviderRefused` ("provider
  refused the request: <status or error>"). Every attempt counts in
  `requests_sent`.
- `python -m tere4ai.extract_norms` and `python -m tere4ai.align_hleg` build
  their clients with the terminal policy. A provider stop ends the execution
  failed with "provider unavailable after 6 attempts: <status or error>",
  keeps the checkpoint, prints the resume command and exits 3; a refused
  declared parameter ends it failed with the configuration error and exits
  4. The execution's `sampling` carries the declared temperature per role
  (under `generator` and `judge` as before, and under `generator_temperature`
  and `judge_temperature`), both declared efforts and the generator's JSON
  mode, from the start.
- `scripts/run_ablations.py` builds its clients with the terminal policy. A
  provider stop, a provider refusal or a refused declaration raised inside a
  strategy is never recorded as an item error: a stop ends the evaluation
  record partial with the reason and exits 3; a provider refusal ends it
  failed and exits 5; both keep the checkpoint and print the next command
  (a new record when no unit was checkpointed); a refused declaration ends
  it failed and exits 4. A provider refusal names the item it stopped on.
  The record's `sampling` carries the declared values, the judge-role keys
  null when no judge client was built.
  `scripts/elicit_benchmark_features.py` runs under the terminal policy
  too: a stop exits 3 and a refusal naming the item exits 5, both keeping
  the checkpoint and printing the command whose rerun resumes it. The
  evaluation harness re-raises a refused declared parameter, ending its
  record failed after the first item that meets it, and stores the
  declared sampling. A static test pins that only the four terminal
  commands name the terminal policy and only the two scripts name the
  provider refusal.
- Every JudgeRun carries `judge_temperature`, the judge's declared
  temperature ("not applicable (mechanical gate)" for the quote check, B84
  ruling R12), added to the JudgeRun branch of `alignments.schema.json` with
  `judge_effort` as string properties that are not required; the schema
  version is unchanged and every existing dump stays valid. The Neo4j
  JudgeRun node, `/api/units` (`judge.temperature`) and `trace_alignment`
  (`judge_run.judge_temperature`, null for an older dump) carry it; the
  backlog answer names `generator_temperature` and `judge_temperature`, the
  evidence answer `judge_temperature`, the eval strategies'
  models `judge_temperature` and, on every strategy, the generator's
  declared `generator_effort` and `generator_temperature`.
- `GET /api/health` reports `runtime_judge` as the model id with its
  declared `effort` and `temperature` from `config/model_parameters.json`,
  read on every poll, and `declaration_error` (null, or the refusal
  sentence with both values null when the table does not declare the
  model or a retired effort variable is set).
- `build_record.schema.json` documents an execution's declared `models` and
  `sampling` keys (string or null, none required, version unchanged, every
  older record valid; the sampling carries the declared temperature under
  `generator_temperature` and `judge_temperature` too); the regenerated mock
  data carry one execution of the declared shape (`intermediate_build.json`,
  `run4align000`). The dashboard recopies the contract as its first commit.
- A resume of `scripts/run_ablations.py` under another declaration is refused
  and exits 2, naming the keys that differ ("used different models:
  model_parameters_sha256"): the resumed record's `models` are compared with
  the loaded ones (a record made before `model_parameters_sha256` existed
  differs too), and each checkpointed unit now names the digest, so a
  `--resume-unrecorded` resume refuses units of another digest or of none
  (written before it existed, ruling P6).
  `scripts/elicit_benchmark_features.py` writes the declaration (`models`, the
  public model configuration) into each checkpoint entry and into
  `benchmark_features.json`, loads the configuration once, and refuses (exit
  2) a rerun over entries of another declaration. A row's
  `documentation.read_on` must be written YYYY-MM-DD (a week date is refused)
  and its `url` must name a host, and a `ModelConfig` whose rows name another
  model or provider than its role is refused.

### Build numbers (B94)
- A published build gets a build number (spec G D-G50): the build record
  store issues 1 above the largest number held by `build_records/numbering.json`,
  the build records, `publications/*.json` and `build_chain_*.json` (a
  temporary file is never counted), under a numbering lock, and refuses,
  naming the files and how to unblock, when the counter is absent and one of
  them cannot be read. `set_publication` refuses a number another record
  holds. A test fails when two committed chain records or manifests of
  `data/graph_dumps/` carry one number.
- Every presented publication carries `build_number` (null, with the reason
  "published before build numbers (B94)", for one published before; a legacy
  row takes the number of the chain record it matches); the presented record
  and the builds list row carry `manifest_present` beside `served`, derived,
  never stored; the list row's publication carries `build_id` and
  `build_number`. The schema change is additive and the version strings stay
  v1; the mock data files were regenerated.
- `scripts/publish_layer23.py` refuses, before any record is touched, a chain
  a record already published (even with its chain record or manifest gone)
  and a numbering it cannot issue; it reserves the build number after the
  post-load gates, dates the publication under the same lock, validates the
  publication and its manifest with it and writes it into the chain record,
  the frozen record and `publications/<chain>.json`, with the counter right
  after the record; a publication refused before the record is frozen uses no
  number; a failure after it says the build is published and never offers to
  remove the chain record. It prints `published Build N: <build id>, record
  <record id>, published_at <time>`; `scripts/activate_build.py` prints the
  number beside the full build id.
- DEC-16, README and the restore runbook describe the build number; nothing
  is published into `data/graph_dumps/` before the B74 re-run.
- Final review fixes: publish checks the chain record, the manifest and
  the publishing record again under the numbering lock after the
  reservation, so a chain published from another record during the load is
  refused and one chain never carries two numbers; a failure after the
  record is frozen is printed on the terminal with what is not written and
  the new `scripts/write_publication_manifest.py <chain_id> [--pointer]`,
  which writes a missing manifest and pointer from the chain record and the
  frozen record, never with a new number and never touching Neo4j; a retry
  tells a missing manifest apart from a published one; an interrupt right
  after the freeze keeps the chain record. The store names a chain whose
  chain record and manifest carry different numbers, calls a malformed
  counter "absent or unreadable" and never lowers the counter. The restore
  runbook's rebuild from source is for a chain not yet published; a
  published chain's lost Neo4j comes from its volume dump until publish can
  reload one (B97 item 10).

### Before the humans (2026-09-26, B81, B97)
- The label act refuses (exit code 2, before any record or write) a
  decision id named more than once in one act, by `--label` and a
  `--label-file` row or by two rows; distinct ids from both flags combine
  in one act. The later label used to replace the earlier one silently
  (B81 item 11).
- The sampler's draw, label act and `--compute` each hold the lock file
  `<sheet>.lock` (named from the resolved path) from their first read of
  the sheet to their record's finish; a second act waits, says so on
  stderr, then reads the first act's bytes. Two concurrent label acts used
  to read the same sheet, and the later write dropped the other's labels
  while both records said completed. A label act or `--compute` on a
  missing sheet is refused before the lock (B81 item 2).
- The draw and the label act write their new bytes to a temp file, keep
  the record's copy from it and finish the record before the bytes replace
  the sheet, so a copy or finish that fails (or an interrupt before the
  finish) leaves the sheet as the act found it and the next act chains on
  the last completed one. A replace that fails after the finish says so on
  stderr with the `cp` that puts the record's copy in place; when only the
  reading copy failed, the line names it, with the `cp` of the draw's
  Markdown copy or, after a label act, that the next label act rewrites
  it. The refusals of the label act and of `--compute` over sheet bytes
  no recorded act wrote name that `cp` for the last recorded act. A
  failed act used to leave bytes no completed act wrote, and every later
  act was refused with no way out short of a `--force` re-draw. A new
  sheet's instructions name the label act instead of asking for labels
  typed into the JSON (B81 item 34).
- `publish_layer23` refuses (exit code 1, nothing recorded) a `--manifest`
  that does not exist or lies outside the dump dir before it resolves the
  build record. A typo'd manifest used to skip the early double-publish
  check, so a published record continued as a descendant and its alias
  moved before the evidence step refused (B97 item 3).
- `publish_layer23 --gates-only` on a published record runs the evidence
  step and the gates and records nothing: no execution on the frozen
  record, no descendant, the alias stays. The restore runbook's check used
  to create a descendant record holding only that check and move the
  build's alias to it (B97 item 2).
- `generate_control_backlog`: a grounding judge that sent a request and
  raised now answers with `judge_verdict` `judge_error` (it read `not_run`
  although the judge ran; a judge step that raises before any request
  stays `not_run`); a generator that raises after its retries answers
  degraded (`requires_human_review`, `refused`, the spend of the requests
  it sent, `judge_verdict` `not_run`) where `/api/backlog` answered 502
  and the spend was lost (B97 item 5).
- The eval harness and `scripts/run_ablations.py` read each strategy's
  models after its items ran: the harness once after every strategy, for
  the artifact and a live record's finish; the runner at each finish, the
  failed one now recording `prompt_versions` and `prompt_sha256` too. The
  models used to be read before the first reply, so graph_full's judge
  effort read "no replies" after the judge had answered (Codex review of
  73b8baa..782f26a).
- Final review fix wave (B98): a publish of a published record runs the
  evidence steps before it makes a descendant, so a manifest in the dump
  dir that does not verify is refused with nothing recorded and the alias
  left in place, and a retry after a later refusal continues in the open
  descendant instead of adding another. The sampler resolves `--sheet`
  and `--sheet-md` once, so a symbolic link keeps naming the sheet it
  pointed at; `--compute` stages `error_rates.json` and keeps the record's
  copy from its own temp file, then replaces, as the other two acts do. A
  degraded backlog answer names `judge_model` and `judge_effort` beside
  its usage. A resumed ablation record notes each strategy that ran no
  unit and names the record it resumes. The degraded-mode strategy cites
  the `judge_error` emitter (`backlog.py`) and its tests.

### The cost of the graded material (2026-09-26, B91, spec F D-F26 (g))
- The generator and judge clients count, per role and beside `calls`,
  `input_tokens` and `output_tokens`, the requests they sent
  (`requests_sent`, including a request that raised after the SDK was
  called, an interrupt included) and the replies whose usage block carried
  both token figures (`replies_with_usage`). A parameter rejection the
  client learns from is not a request sent. A total whose `requests_sent`
  exceeds its `replies_with_usage` is incomplete.
- The extraction and alignment build records and manifests carry the two
  counts through the same clients; `build_record.schema.json` documents
  them as `role_usage` (optional, so older records still validate). The
  ablation summary sums them and drops them for a role when any unit lacks
  them, and for every role when a unit carries no usage block at all.
- Both SDK clients are built with `max_retries=0`, so every request the
  providers see is counted; the clients retry a 408, 409, 429, 5xx or a
  connection error themselves, at most twice, waiting `retry-after` (at
  most 60 s) or 1 s then 4 s, each attempt a request sent (spec F D-F26
  (e) and (g), ruling R3).
- `generate_control_backlog` (MCP and `/api/backlog`) answers with
  `generator_model`, `generator_effort` and `usage` (`generator` and
  `judge`, each the five counts for this call only, `null` for a client
  without a usage record) beside `judge_model` and `judge_effort`; a
  degraded answer after the generator request carries them too, a refusal
  before any request does not.
- A parameter rejection is learned only from a 400 or an error without a
  status that is not a connection error; a retryable error (408, 409, 429,
  5xx, connection) whose message names `temperature`, `response_format`,
  `reasoning_effort` or the effort is retried and the parameter stays for
  the run, where before it was dropped for the run (final review A5).
- A sixth per-role count, `requests_refused`, counts the failed attempts
  the provider answered with an HTTP error status (a retried 429 or 5xx
  included), as opposed to a connection error, a timeout or an interrupt,
  which may have been billed; `requests_sent` keeps counting every attempt.
  It reaches the build records, the manifests, the evaluation records and
  the backlog answer through the same clients; `build_record.schema.json`
  documents it in `role_usage` (optional), and the ablation summary drops
  it for a role when any unit lacks it. The build record mock data is
  unchanged, and the dashboard's display rule is not changed here (final
  review A3).
- A grounding judge that raises after the generator answered no longer
  turns `generate_control_backlog` into an error (a 502 on `/api/backlog`)
  that loses the generator's spend: the answer is degraded
  (`requires_human_review`), names the failure, and carries the generator
  model, effort and both roles' usage (final review A4).

### Pre-B74 run safety (2026-09-26, B79, B81, B78)
- `extract_norms` and `align_hleg` beat the execution's heartbeat every 60 s
  on a background thread while the model calls run
  (`graph_store.build_record.Heartbeat`), so a group or batch longer than
  the 300 s expiry no longer reads "liveness unknown" on the Build page
  (B79 item 4). A failing beat stops the thread with one stderr line and
  never stops the run.
- A Ctrl-C (or any `BaseException`) during `extract_norms` or `align_hleg`
  ends the execution `failed` with the usage and completed keys so far and
  keeps the checkpoint; before, the execution stayed `running` and the
  spend was lost (B79 item 22). A failed execution also records the
  sampling and effort outcomes so far, where it kept the start value "no
  replies" before.
- A published build record is frozen for every execution but the run that
  published it (the run id `set_publication` received): a heartbeat or an
  end from any other execution, a second publish included, is refused
  (`FrozenRecordError`), so a run still going when its record was
  published can no longer rewrite it. `publish_layer23` refuses, before any
  gate or load, a record with a live running execution, checks again just
  before it declares Neo4j available, and `set_publication` checks a third
  time under the lock (`LiveExecutionError`), with Neo4j marked unavailable
  whenever the publication is refused after the load; a running execution
  whose heartbeat expired (a killed process) does not block, and the
  publish execution beats its own heartbeat every 60 s while it runs, so a
  publish longer than the expiry still blocks a second one (B79 item 15).
- An evaluation record of `run_ablations` or the harness keeps, when the run
  fails or is interrupted, the items completed so far and the usage spent
  so far. A record's `usage` is its own invocation's spend; a resume no
  longer repeats its predecessor's, so summing records is the real total
  (the summary file still sums every checkpointed unit). The runner's
  record counts `units_run` (B81 item 4).
- `code_version` (the `config.code_version` of every evaluation record)
  ends in `-dirty` when `src/`, `prompts/`, `schema/`, `scripts/` or
  `pyproject.toml` hold uncommitted changes or untracked files; run outputs
  never make it dirty (B81 item 5).
- `EvaluationRecordStore.begin` and `finish` validate the record against
  `evaluation_record.schema.json` before writing it: a malformed field is
  refused before a paid run starts, or at its end with the record left
  running so the failure path can still end it (B81 item 7).
- `python -m tere4ai.eval.harness --repeat-of <record id>` records the run
  it repeats, refusing (exit code 2) an id the store does not hold; both
  writers refuse `--repeat-of` with `--no-record` (B81 items 19 and 10).
- The per-item `error` strings in the harness's results artifact and the
  runner's checkpoint name files, never paths (B81 item 24).
- `scripts/run_ablations.py` no longer defaults to the July files: an
  omitted `--checkpoint` or `--summary` lands in
  `eval/results/runs/<record id>/`, a fresh directory per run, so a default
  invocation runs instead of refusing and can never resume or rewrite
  another run's files; a `--no-record` run must name both paths (B81 item
  20).
- A replace decision that leaves out `conditions`, `exceptions` or
  `lifecycle_phase_ids` now yields empty lists instead of keeping the
  model's text on a norm stamped `HUMAN_AUTHORED`; every slot of a human
  norm comes from the human's payload (B78 item 12).
- `set_publication` records the publishing run under the record lock,
  before the write, so a beat of the publish's own heartbeat landing just
  after the write no longer reads the record as frozen against it and no
  longer prints a false "heartbeat stopped" line (final review F1).
- When `set_publication` refuses (or anything else raises before it
  returns), `publish_layer23` removes the chain file it had just written,
  so the next publish of the same inputs runs instead of reading "already
  published as chain X; activate it" for a chain that was never published
  (final review F2).
- `publish_layer23` computes the chain id and refuses inputs already
  published before a published record continues as a descendant, so a
  mistaken second publish no longer creates a descendant record or moves
  the alias to it; the refusal records no execution (final review A6).
- `code_version` prints one stderr line when git fails or times out inside
  a checkout, where it returned `null` silently before; outside a checkout
  it stays silent (final review F3).
- `extract_norms` and `align_hleg` refuse to start (exit code 2), before
  any model call, while another execution of the same command on the same
  record is live, naming it and the rule that a killed run stops blocking
  300 s after its last heartbeat; before, a `--resume` next to a live first
  run was accepted and both paid for every remaining unit (final review
  A1).
- A SIGTERM or SIGHUP (a closed terminal, a dropped ssh session) during
  `extract_norms`, `align_hleg` or `publish_layer23` raises
  `KeyboardInterrupt` (`graph_store.build_record.signals_as_interrupt`,
  the previous handlers restored when the command returns), so the
  execution ends `failed` with the usage and effort so far and the error
  names the signal; before, it stayed `running` with `usage` null for
  good. Each finished group or batch also writes the usage so far onto the
  running execution through the per-unit heartbeat (`heartbeat(...,
  usage=...)`, additive), so a SIGKILL loses at most the unit in flight
  (final review A2).
- `signals_as_interrupt` leaves a signal whose handler is `SIG_IGN`
  untouched, so a run started with `nohup` (SIGHUP ignored) still survives
  a closed terminal; a SIGTERM or SIGHUP at its default handler is still
  turned into `KeyboardInterrupt` (re-review of final review A2).

### Effort as part of the instrument (2026-09-24, B84, spec F D-F22)
- `TERE4AI_GENERATOR_EFFORT` and `TERE4AI_JUDGE_EFFORT` are required config
  values from the closed vocabulary `EFFORT_LEVELS` (`low, medium, high,
  xhigh, max`, `src/tere4ai/judge/config.py`), carried on `ModelConfig` as
  `generator_effort` and `judge_effort`. No silent fallback: a missing or
  unrecognised value fails fast, the same discipline as the model ids.
- The generator sends `reasoning_effort` and the judge sends
  `output_config: {"effort": ...}`; each client learns a rejection once for
  its lifetime, the same discipline B74 already applied to temperature, and
  reports the outcome in one vocabulary: the level itself when every reply
  carried it, `not applicable (rejected by the model)` when every reply was
  sent without it after a rejection, `mixed`, `no replies`, or `not
  configured` for a client built without a config.
- The extraction and alignment manifests, the build record executions, every
  JudgeRun record and graph node, the tool envelopes (`trace_alignment`,
  `/api/units`, `/api/trace`), and the facade health answer all carry the
  requested and applied effort alongside the model id, never separately.
- `deploy/rahti/deployment-facade.yaml` and `docker-compose.yml` carry
  `TERE4AI_GENERATOR_EFFORT` and `TERE4AI_JUDGE_EFFORT` beside the model id
  entries (default `xhigh`); `eval/README.md` lists both among the
  variables a live run needs.

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
- Codex review fix wave (G1 to G8): a record binds to a publication only
  when `verify_dumps_against_chain` accepts the served bytes; a checkpoint
  resumes only the record its `<checkpoint>.record` sidecar names; the
  harness copies its own artifact bytes, never the shared path's; a label
  act refuses a sheet whose bytes are not the last recorded act's output;
  a record file that is not UTF-8 is an unreadable row; the detail route
  answers 404 on an unreadable copy; the runner records the features cache
  only when read; the variance comparison names the gold seed.

### Judge model: claude-opus-5-5 (2026-09-23)
- `TERE4AI_JUDGE_MODEL` names Claude Opus 5.5 (`claude-opus-5-5`, listed by
  the Models API, created 2026-09-21) in `.env.example`, `docker-compose.yml`
  and the Rahti deployment; the local `.env` follows. No client change: the
  judge client sends no thinking or tool_choice parameter, learns a rejected
  temperature once and caps output at 16000 tokens, all of which Opus 5.5
  accepts. Recorded: Opus 5.5 cannot disable thinking and its provider
  default effort is medium where Opus 5's was high; the client sets no
  effort, so the provider default runs (spec F D-F16, D-F17) (superseded by
  B84, 2026-09-24: the clients send the configured effort). The B74
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

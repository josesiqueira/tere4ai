# Changelog

All notable changes to TERE4AI v2. Format loosely follows Keep a Changelog;
versions are git tags. Dates are build dates (Europe/Helsinki).

## [Unreleased]

### B132: the graph and the answers follow the AI Act as amended by the Digital Omnibus (2026-10-04)
- Layer 1 is Regulation (EU) 2024/1689 as amended by Regulation (EU)
  2026/1744, parsed from EUR-Lex's consolidated text of 27 July 2026 in
  Formex and checked unit by unit against the Official Journal wording
  (DEC-23; architecture.md Sections 6 and 11): 119 articles, 571
  paragraphs, 91 subparagraphs, 521 points, 14 annexes, 247 annex items,
  180 recitals, 70 definitions, 515 cross-references; 11 deleted units and
  130 earlier versions counted apart. Layer 0 freezes the Omnibus and the
  consolidated text in Formex (the consolidated text non_binding).
- Node contract (nodes.schema.json): an Article `number` and a paragraph
  `index` are the Act's label, a string ("4a"), with an integer `sort_key`
  (4a gives 401); every unit carries `enacted_by` ("Regulation (EU)
  2024/1689", an Omnibus point, or "composed") and `amendment` (unchanged,
  replaced, inserted, composed or deleted); a deleted unit keeps its id
  with `deleted_by` and `deleted_from`, no text and no span; each changed
  unit's 2024 wording is a `UnitVersion` node (id
  `version:2024-07-12:<unit id>`, span `<name>@2024-07-12`) linked by
  `HAS_VERSION`. An in-force span may list deleted ranges under `exclude`,
  which `resolve_span` leaves out of its text. The build id is a digest
  over every frozen legal source the parse reads.
- coverage_report expects the counts of the Act in force when the Omnibus
  is merged (119 articles, 14 annexes) and reports `actual.deleted_units`;
  source_trace answers a deleted unit with the note naming the Omnibus
  point that deleted it; the elicitor renders a deleted provision as that
  note.
- get_applicable_requirements skips a norm whose source unit is deleted;
  its summary gains `deleted_source_skipped` and `deleted_source_note`.
- classify_ai_system: Article 5(1) points (ba) and (bb) are cited as their
  nodes with Article 5(1a) and (1b) (`ARTICLE_5_SCOPING_PARAGRAPHS`);
  `OMNIBUS_SOURCE_ID`, `OMNIBUS_ARTICLE_5_APPLIES_FROM` and
  `OMNIBUS_ARTICLE_5_POINT_BY_FLAG` are removed. A new fact,
  `annex_i_section_b_legislation`, names the Annex I section of an
  Article 6(1) system's product legislation; the answer gains
  `annex_i_section` ("A", "B", "unknown", or null off that route),
  `high_risk_routes` (every high-risk route that holds, "article_6_1" and
  "article_6_2", so a system on both routes is dated by both points of
  Article 113(c) even when the Article 6(1) route decided),
  `application_dates` (one entry per cited provision: date, meaning,
  source, basis node, verbatim wording, notes) and `legal_text`. The note
  that the amending text is not yet modelled and the Article 6(1) Omnibus
  note are removed. A Section B system cites Article 2(2) and lists no
  Article 50 duty (Article 2(2) applies none of Article 50); a Section B
  product whose facts also match an Annex III category takes the Annex III
  route (annex_iii_category set, annex_i_section "B", the FRIA and Article
  50 as for an Annex III system), and the answer says the product's
  Section B legislation also classifies it under Article 6(1), and every
  provision it cites but Article 6(1) and Annex I is dated by point (c)(i)
  only (Article 2(2) excludes the rest of Chapter III on the product route,
  R45); a Section B system whose Annex III facts are unknown requires human
  review. The
  unknown-section note and the missing fact `annex_i_section_b_legislation`
  appear only when the Article 6(1) route alone holds, never beside an
  Annex III match (R44).
- New `src/tere4ai/mcp_server/application_dates.py`: the reviewed table of
  Article 113 as amended, provision by provision (an Annex dated through
  the Article that brings it into application, Annex I through Article
  6(1), Annex III through Article 6(2), Annex IV through Article 11(1),
  each entry naming it in `applies_through`; a wording the Omnibus inserted
  or replaced applies no earlier than 27 July 2026; Article 111(4) a note
  on Article 50(2); a unit the Omnibus deleted gets no date); the FRIA block's `applies_from` is Article 27's row of
  it (point (c)(i)), its source text changed.
- get_applicable_requirements: a Section B system with no Annex III match
  is served no Chapter III requirement and no Article 50 obligation; the
  answer cites what Article 2(2) applies (`article_2_2`,
  its condition on Articles 57 to 59 with `condition_decided` false) with
  `application_dates` keyed by provision; while its Annex III facts are
  unknown the answer names them, says the Chapter III requirements do not
  apply unless an Annex III point applies, and requires human review. The
  provisional note of a Section B product on the Annex III route says an
  Article 6(3) derogation would bring the Article 2(2) answer back, and
  its Chapter III requirement groups carry only point (c)(i)'s date,
  because Article 2(2) excludes Chapter III on the Article 6(1) route for a
  Section B product (R43). While the section is unknown and the Article
  6(1) route alone holds (no Annex III match), the Chapter III requirements
  are served, the fact is named in missing_facts and Article 2(2) in
  legal_status_notes (R44). Every served group carries its
  dates in `application_dates` (keyed by group); every answer carries
  `legal_text`.
- `schema/json_schemas/system_features.schema.json`: the new flag; the
  descriptions of medical_or_safety_component, annex_i_covered_product and
  third_party_conformity_assessment_required quote Article 6(1a) to (1c)
  and the replaced Article 3(14); points (ba) and (bb) quote their nodes.
- Prompt `prompts/elicit_features/v7.md`, the default and the version of
  record for B74: the amended Annex I points (Section A 2 to 12, Section B
  13 to 21), points (ba) and (bb) with Article 5(1a) and (1b) as nodes,
  Article 6(1a) to (1c), and the Annex I section fact; v6 is kept for the
  records that name it.
- explain_requirement takes `earlier_version` (MCP tool and POST
  /api/explain): the source unit's 2024 wording, or why it has none
  (`reason`: inserted, unchanged or source_unavailable); a norm on a deleted unit is explained with the deleted
  note and requires human review. generate_control_backlog refuses a norm
  on a deleted unit before any model call (MCP: not_applicable with
  `refused_norm_ids`; POST /api/backlog: 422).
- Gates G3 and G4 refuse a norm, and an alignment of a norm, whose source
  unit is deleted; the evaluation harness refuses a test-set item that
  cites one (`deleted_unit_citations`). The hand-made test set cites no
  changed unit.
- The extraction scope (`data/graph_dumps/core_nodes.txt`) gains
  eu-ai-act:article-4a, with Chapter I's target_system_category: 424 core
  source units (405 on the 2024 text).
- The pre-B74 dev dumps drop the 60 norms on units the Omnibus changed,
  their judge runs and the 98 alignments of those norms (stats
  `b132_dropped`) and the 45 Condition and Exception records only those
  norms referenced; republished as chain 89db919fab52; the demo sessions are
  re-recorded on it by the new `scripts/rerecord_demo_sessions.py`.
- The modules that implement these answers carry `@implements: DEC-23`
  (classify, requirements, explain, backlog, fria, server, the facade, the
  harness, the elicitor, target_system_category), so docs/traceability.md
  lists them under DEC-23.
- The web demo's flag panel and presets carry the new fact, and its
  backlog grouping keeps Article 4a apart from Article 4
  (`web/src/lib/articleGroups.ts`).

### B122: every fact of the features schema in the Act's words (2026-10-03)
- The 25 flags of `schema/json_schemas/system_features.schema.json` that
  had no description now have one, and the six that named a provision
  without quoting it quote it: each names its provision, quotes the Act's
  words and says how the classifier reads the fact, as DEC-18 did for the
  newer facts. The two Digital Omnibus prohibitions keep their
  descriptions, which cite the amending act (no node in the graph).
- `tests/unit/test_features_schema_descriptions.py` fails on a flag with no
  description or no provision, and on any quoted passage that is not the
  text of a node of the Layer 1 dump.
- The schema's digest changes; the elicitor reads the schema for flag
  names and validation only, so its prompt does not change.

### B121: the alignment run records its generator's effort (2026-10-03)
- The HLEG alignment pipeline's MappingRun records `generator_effort` and
  `generator_temperature` (spec F D-F22, D-F29), as its JudgeRun records
  the judge's; `alignments.schema.json` declares both.
- Contract change: `trace_alignment`'s `mapping_run` carries
  `generator_effort` and `generator_temperature`, null for a dump made
  before this change. The session report's mapping run line shows the
  effort beside the model id.
- The same for the extraction generator: a norms dump's build block
  records `extraction_temperature` beside `extraction_effort`, and
  contract change, `/api/units` candidates and `explain_requirement`'s
  `extraction` block carry `extractor_effort` and `extractor_temperature`
  (null for a dump made before this change and for a norm a person wrote).

### B128: the hand-made test set gets two labels on every case (2026-10-03)
- `eval/gold/ANNOTATION_PROTOCOL.md`: two annotators label every case
  independently, agreement is computed before adjudication with a
  chance-corrected statistic, and disagreements are adjudicated by a
  person who did not produce them (spec G Sections 6 and 10.4, in the
  private research repository). A label comes from the Act, never from the
  classifier: the rule that seed classification labels agree with the
  classifier, and its test, are removed.
- `eval/gold/gold_seed.json`: `second_annotator` is replaced by `labels`
  (empty until labelled) and `adjudication` (null); `gold` and
  `gold_citations` stay the harness's fields.
- `scripts/draft_gold_candidates.py`: drafts carry no label (classification
  drafts no longer call the classifier, question drafts no longer take
  their answer from the extracted norms), ids are numbered so they do not
  name the answer, and the second-annotator draw and `--subset-seed` are
  removed.

### B90: one public source explaining the MCP server (2026-10-03)
- The web demo shows the non-legal-advice notice from one module,
  `web/src/lib/notice.ts`, which mirrors `NON_LEGAL_ADVICE_NOTICE` in
  `src/tere4ai/mcp_server/tools.py` (a test keeps them equal). The
  landing page, the demo layout (sidebar and mobile footer), /assess and
  /how-it-works import it; the demo layout's shorter mobile header line
  is removed, so the notice has one wording. /how-it-works says
  alignments, states which proposals an independent judge checks (norms,
  alignments, evidence, backlog items) and that the elicitor's proposed
  facts are checked by code and confirmed by a person. The landing page
  says "Keys unlock the paid tools." with no count.
- The facade's /llms.txt header and /.well-known/tere4ai.json serve
  `NON_LEGAL_ADVICE_NOTICE` (the header said "Not legal advice; never
  claims compliance."). SKILL.md carries the notice word for word.
- The resolve_span and source_trace descriptions state that start and end
  count Unicode code points in the snapshot decoded as UTF-8, not bytes,
  and that sha256 is over the file's bytes; trace_alignment's says
  alignment runs and alignments. spans.py, docs/DESIGN.md and
  docs/trustworthiness_strategies.md say code point offsets.
- USER.md describes the MCP server a coding agent calls; a prohibited
  system gets only the Article 5 prohibition citation and a message.
- New `src/tere4ai/server_docs/prose.py` (DEC-22): the prose of a Markdown
  or .tsx file, sentences, the count rule (a count with tool, tools, free
  or paid within four words after it, or before it for every count but
  "one") and the names rule (backticked names and snake_case words of the
  plain prose).
- Tests: test_server_docs_prose.py, test_notice_one_source.py,
  test_span_offsets.py.
- Duplicate keys in one JSON object are measured, not changed: the server
  reads the last of a repeated key and refuses nothing, over MCP (stdio,
  the tool arguments) and on the facade (the body of POST /api/classify);
  docs/server/index.md says so. Test: test_duplicate_keys.py.
- New `docs/server/index.md` (DEC-22): the explanation of the MCP server
  in one text. Its README part (definition, who it is for, wiring, one
  call, the tools, what it is not) is generated into the README's first
  screen (below); after it come how to read every answer, paid calls and
  the replay window, MCP revisions and clients, span offsets (code points
  of the decoded snapshot, checksum over the bytes), duplicate keys (the
  last of a repeated key is read on both surfaces, nothing is refused),
  the instructions the server sends and a link to the tool reference.
  Six regions (notice, example, tools, fields, statuses, instructions) are
  written empty, for the generator to fill from the running server. The
  example request is written once, in the source.
- The definition no longer says that judges gate every proposal: the rule
  ladder alone decides the level, and the elicitor's proposed facts are
  checked by code and confirmed by a person, not by a judge. PRODUCT.md
  takes the same sentence.
- README Status and PRODUCT.md's proof points carry no judged-layer count,
  test count or tool count (coverage_report serves the counts of the
  served build); PRODUCT.md drops the pre-B74 label-flip result.
- SKILL.md names trace_implementation, with its guidance.
- coverage_report's and explain_requirement's served descriptions open
  with one plain sentence, which the generated tool table shows (ruling
  R1); the rest of each description is unchanged.
- Test: test_server_docs_source.py (sections, regions, the request block).
- New `scripts/gen_server_docs.py` and `src/tere4ai/server_docs/session.py`
  and `render.py` (DEC-22): the script reads the example request from
  docs/server/index.md, starts the MCP server over stdio with the official
  MCP Python SDK client (dev extra, mcp 2.2) and no model keys, reads the
  instructions and the tool list, calls only coverage_report and
  classify_ai_system, and writes the source's six regions, the tool
  reference `docs/server/tools.md` (each tool's whole served description,
  annotations and input fields), the README part into README.md and the
  reading part into SKILL.md. `--sessions` writes docs/server/sessions.md
  from the recorded sessions (each with the build and day of its first
  line); `--check` writes nothing and exits 1 naming each file that would
  change. It refuses to run when a tool's openWorldHint, the word PAID in
  its description and its scope in TOOL_SCOPES disagree. Nothing that
  depends on the served build is written (no graph_version, no count, no
  time).
- README.md's first screen and SKILL.md's section on reading every answer
  are now generated from docs/server/index.md: edit the source, then run
  the script. The README shows the tool table from the served descriptions
  with its computed count line, the example answer without a build id,
  and no longer says "byte offsets"; the replay window and the MCP
  revisions and clients moved to the full text, linked from the README.
  SKILL.md lists all twelve answer fields.
- CI's python job runs `python scripts/gen_server_docs.py --check` after
  the traceability diff.
- `prose.link_problems`: in docs/server pages a relative link may only
  name tools.md, sessions.md or sessions/<key>.html, and only outside the
  README part; images are absolute URLs; nothing names the private
  research repository.
- The protocol and duplicate-key tests take the server environment from
  `tere4ai.server_docs.session.server_env`.
- Tests: test_server_docs.py (the generated files current, the calls made,
  free or paid agreement, SKILL.md names every tool, backticked names
  known, no counts in prose, the notice, the link rule, nothing build
  specific, `--check` on an edited region, a changed surface and a
  changed request, the sessions page).
- New `mkdocs.yml` and `scripts/build_site.sh` (DEC-22): Material for
  MkDocs 9.7.7 (ruling R3, pinned in the new `docs` extra) builds the site
  from docs/server alone into `_site/` in strict mode, so a relative link
  to a missing page fails the build. No nav: the pages are found from the
  folder, and the sessions page joins the site only once
  docs/server/sessions.md exists (the script then copies the recorded
  sessions from web/public/mcp-demo/ beside it).
- CI's new `docs` job installs only mkdocs-material and builds the site on
  every push and pull request. Nothing is published: there is no deploy
  step and no pages permission.
- `.gitignore` keeps the built site and the copied sessions out of git.
- docs/architecture.md Section 8 names docs/server/index.md as the public
  explanation of the server (DEC-22), and the client support list as kept
  there, no longer in the README.
- Final review fixes: the generator refuses, before sending, any call to
  a tool that is not coverage_report or classify_ai_system or is not
  served with openWorldHint false (`session.guard_calls`; a paid tool
  would read .env, so the keys left out of the server's environment are
  not the guard). SKILL.md's sentence naming the paid tools is generated
  from the served openWorldHint, and its tool list carries no hand-written
  cost mark. The count rule also reads the four words before a count
  (not for "one"); the names rule also reads snake_case words written
  without backticks. The resolve_span, trace_alignment and coverage_report
  descriptions and the server's instructions drop "SourceSpan", "reified"
  and the milestone labels M1 and M3. The README says which clients take
  the config block and that only the official MCP Python SDK client is
  tested; its maintainer sections name no id of the private research
  repository. CI's docs job reads the mkdocs-material pin from the `docs`
  extra.

### B126: the ablation's sixth condition and the measures for each answer key apart (2026-10-03)
- New strategy `graph_runtime_judge`, appended last to `STRATEGY_NAMES`
  (the five keep their order): condition 3 (`graph_no_judge`, every
  extracted norm offered, the build judge ignored) plus the runtime
  grounding judge of `graph_full` (unverifiable citations withheld,
  verdict attached, a non-accepted answer degraded to
  requires_human_review). It takes the `@vN` prompt-version suffix and
  refuses to build without a judge client, as `graph_full` does.
- `strategies.uses_runtime_judge(name)` is the one answer to whether a
  condition calls the runtime judge. The harness builds the judge, and
  the evaluation record keeps the runtime judge's prompt hash, for every
  such condition, no longer only for a name equal to `graph_full`.
- `scripts/variance_report.py` checks the sixth condition's labels for
  determinism with the other graph conditions;
  `scripts/make_paper_artifacts.py` labels it "graph + runtime judge only"
  and draws a row only for a condition the summary holds, so the July
  figures and tables are unchanged; `scripts/estimate_benchmark_cost.py`
  counts its output with the observed answer sizes of `graph_no_judge`,
  since run 2 did not run it, and says so in the report.
- `scripts/run_ablations.py` adds `by_answer_key` to each strategy's
  summary: every measure for the hand-made legal test set (`hand_made`,
  items `gold:`) and the published benchmark (`benchmark`, items `bench:`)
  apart: classification correct, total, accuracy (null when the key has
  no labelled classification item) and abstained (no answer, or
  undetermined where the label is a level: on a case labelled
  undetermined it is the right answer, ruling R4); citation completeness
  by exact node id (null when the key has nothing to cite, spec G D-G33);
  the hallucinated citation rate over that key's answers
  with the citations emitted and the vacuous note at zero; and, for the
  benchmark, the article-level citation completeness. A case without an
  answer counts as wrong. The pooled keys are unchanged, kept for the
  readers of the July summaries (ruling R3).

### B124: each norm's target_system_category is set by rule from its Article (2026-10-03)
- Contract change: `explain_requirement`'s `deontic` block carries
  `target_system_category` as one of `any_ai_system`,
  `prohibited_ai_practice`, `high_risk_ai_system`, `article_50_ai_system`:
  the part of the Act's rules the norm belongs to, named by the category of
  AI systems those rules govern (DEC-21), set by a rule from the norm's
  source Article or Annex, never by a model. It was a free label the
  extractor wrote (`high_risk`, `prohibited_practice`, `any` or null in the
  build of 2026-07-08). A norm on a source unit outside the rule table
  carries null. A build extracted before this change is not converted and
  shows its stored label. The backlog generator and the runtime grounding
  judge receive the value in their norm digests, as before.
- `schema/json_schemas/norms.schema.json` enumerates the four values
  (`$defs.targetSystemCategory`), null allowed; any other string fails
  validation in the extraction pipeline and the review apply step, the two
  places that validate norms.
- Prompts extract_norms v3 and judge_norms v3 (one shared version, now the
  default of `extract_norms` and `python -m tere4ai.extract_norms`, and the
  version of record in `eval/config_evaluated.yaml`): extract_norms v3 no
  longer asks for the field and the judge's candidate no longer carries it;
  judge_norms v3 is v2 under a new version line. Under v1 and v2 the
  extractor still writes a label, which the judge reads as before and the
  norm does not keep.
- The extraction stats and the execution record's counts carry
  `without_target_system_category`, the norms on a source unit outside the
  rule table.
- The review apply step sets the rule value on a norm a person adds or
  replaces and refuses one on a source unit outside the rule table, naming
  the unit.
- The judge label sheet (`scripts/sample_judge_decisions.py`) no longer
  prints the field, which was never a judge criterion
  (`eval/gold/ANNOTATION_PROTOCOL.md`); the sheet drawn in 2026-07 stays as
  drawn.

### B125: the FRIA block reads the unknown Annex III facts (2026-10-02)
- Contract change: on a `limited_risk` or `minimal_risk` answer the `fria`
  block is `unknown`, not `does_not_apply`, while an Annex III fact absent
  from the input could make the system high-risk under Article 6(2) and so
  bring Article 27(1) in; each such fact is named in the fria block's
  `missing_facts`. The point 2 area (excepted by Article 27(1)) never counts,
  and the other areas stop counting once the deployer is known to be neither
  a public-law body nor a private entity providing public services (points
  5(b) and 5(c) count for any deployer). The level, the status and the
  envelope's `missing_facts` do not change. The shopbot-transparency test
  session is re-recorded for its first answer.
- The same reading on a `high_risk` answer with no Annex III point matched
  (the Article 6(1) route only) or with only the point 2 area matched: once
  the point 5(b) and 5(c) facts are known false, an unknown Annex III fact of
  another area keeps the `fria` block `unknown` unless the deployer is known
  to be neither category, and is named with the same line (final review,
  R5).
- When no unknown Annex III fact can make Article 27(1) apply, the
  `does_not_apply` rationale says which reason holds: the point 2 area, the
  deployer known to be neither category, or both (it said both every time).
- The shopbot-transparency test session's second call is re-recorded with the
  first call's new answer as its input.
- On those two `high_risk` answers, while a point 5(b) or 5(c) fact is still
  unknown, the other unknown Annex III facts that could trigger are named
  beside it, so a fact that decides once 5(b) and 5(c) turn out false is
  never left out (re-review N1).

### B118: the levels take the pyramid's names (2026-10-02)
- Contract change: `classify_ai_system`'s `risk_category` is one of
  `unacceptable_risk`, `high_risk`, `limited_risk`, `minimal_risk`,
  `undetermined` (were `prohibited`, `high_risk`, `transparency_only`,
  `minimal_or_none`, `uncertain`); the answer's field `prohibited` is now
  `unacceptable_risk`; the rationale's rule names follow. Sentences
  (the FRIA rationale, requirements messages, status lines, the tool
  description) show Unacceptable risk, High risk, Limited risk, Minimal
  risk, "Undetermined: facts missing". An answer from before the rename
  sent back to `get_applicable_requirements` is refused
  (not_applicable, confidence 0), not mapped.
- The evaluation maps the benchmark's labels to the new values; result
  files from before the rename are read through one table only when marked
  so (`--legacy-levels` on `scripts/ablation_deepdive.py`,
  `variance_report.py` and `elicitation_error_report.py`), so their
  numbers reproduce; fresh answers are scored as given; the evaluation
  prompts ask for the new values.
- The MCP demo recordings, index and pages are regenerated (free,
  deterministic tools only); the recorder's four titled systems now give
  every fact the rules read, so each session answers its titled level.

### B123: the Article 6(1) route resolved like an Article 5 path (2026-10-02)
- `classify_ai_system` names an unknown `annex_i_covered_product` in
  `missing_facts` on every exit but the rejected-input one, and an unknown
  `third_party_conformity_assessment_required` beside a true Annex I fact
  on the prohibited exit too. While the route is open the last exit gives
  uncertain instead of minimal_or_none (and the FRIA block unknown instead
  of does_not_apply), and the Article 50 exit is requires_human_review.
  A third-party assessment known false rules the route out whatever the
  Annex I fact is. Contract change: a fact set that left both facts out
  and answered minimal_or_none, not_applicable now answers uncertain,
  requires_human_review. On the 339 stored benchmark fact sets no level
  or status changes; 318 answers gain the missing-fact line.
- eval/gold/gold_seed.json: gold:cls-03 to cls-05 give both Article 6(1)
  facts as false, as their scenarios intend; no gold answer changes.

### B102: review leftovers of B78 to B97 (2026-10-02)
- `extract_norms` and `align_hleg` choose their build record without
  writing, refuse a live run, an overwrite or a stale checkpoint, build
  their clients, and only then create the record, just before the
  execution starts: a refused run or a client that fails to build leaves no
  record and moves no alias (B79 item 10).
- The argv a build record keeps also redacts the value of a flag whose
  name mentions password, passwd, credential or auth, beside key, token
  and secret (`--author` is redacted too, on the safe side) (B79 item 8).
- `BuildRecordStore.finish_execution` raises `RecordError` (was
  `ValueError`) on a status other than done or failed, and
  `create_record` reads the alias index before it writes the record, so an
  unreadable index is refused before a record file exists (B79 item 17).
- A reason shown on `/api/builds` or in an evaluation record shortens only
  a token that looks like a path (a leading separator, a drive letter,
  `~`, `./`, `../`, or two or more separators) to its file name, so a
  reason such as "L2.1/L2.2" reaches the reader whole (B79 item 3).
- The build record presenter gives a synthesised record the reasons that
  follow from its command (a command that calls no model) and the reason
  for its `parse_record_id`; a matching chain record without a build id
  says "a chain record matches, but neither it nor the norms file names a
  build id" instead of "no chain record matches the current artefacts";
  counts whose values are all null read unavailable; the dump digest
  cache keeps one entry per file (B79 item 24). The two legacy build
  record mock data files are regenerated.
- `build_record.schema.json`: `progress.source` is the enum `record`,
  `checkpoint` (was any string) (B79 item 16).
- `publish_layer23` refuses (exit code 1) a `--dump`, `--norms` or
  `--alignments` outside the dump dir before anything is loaded, as it
  refused a `--manifest` there: publication names its inputs by file
  under that directory (B79 item 7).
- `scripts/materialize_reference.py` refuses a missing `--pristine`,
  `--decisions` or `--manifest` before any is read (a missing `--pristine`
  was a traceback), reads the payload kind from the list it holds and
  refuses a payload holding neither a norms nor an assertions list (B79
  item 20).
- The build chain check names a publication manifest as
  `publications/<chain id>.json` and the chain record by its file name,
  and refuses a manifest or chain record whose JSON root is not an object
  or whose bytes are not UTF-8, where it raised (B79 item 21, B81 item 38).
- The MCP server's startup integrity check also runs when an activation
  pointer exists without a `layer1.json`, since the activated publication
  may name its Layer 1 file otherwise (B79 item 23).
- An E1 evaluation record (the draw, the labelling, the analysis) presents
  its null `models`, `prompt_versions`, `prompt_sha256`, `sampling` and
  `usage` as "not applicable: no model is called" (B81 item 3); the three
  E1 mock data files are regenerated.
- A schema refusal of an evaluation record keeps its JSON-pointer location
  whole; only the message is path-shortened (B81 item 21).
- The eval harness and `scripts/run_ablations.py` resolve `--repeat-of`
  through a read-only store, so a refused `--repeat-of` leaves no
  `evaluation_records/` behind (B81 item 10).
- The runtime judge prompt hash is recorded only for a `graph_full`
  strategy whose models report `judge_prompt_version`; the strategy name
  alone no longer counts as a runtime judge call (B81 item 23).
- The eval harness keeps the temp file when the final replace of its
  results file fails, and the error names it and the move that puts it in
  place (B81 item 35).
- A failure finish of an evaluation record that validation refuses is
  retried once with the error alone and the refusal named, so the record
  ends failed and never stays running (`evaluation_record.end_failed`,
  used by the harness and `run_ablations`) (B97 item 9).
- New evaluation record mock data: a legacy comparison linking two legacy
  runs (`e6_legacy_comparison.json`) and the second legacy run
  (`e6_legacy_variance_summary.json`), both in `list.json` (B81 item 16
  (c)). The mock data regenerate.py fails naming the pinned list (`CLOCK`,
  `FIXED_IDS`) a run outgrows, and refuses a file name written twice (B81
  item 12).
- The MCP session report prints the judge's effort on the backlog's judge
  record and on each `trace_alignment` judge run line, beside the judge
  model; a judge run recorded without an effort shows none (B84 item 1).
- Every model log event names the effort beside the model: the
  extraction, alignment, backlog and evidence generators, and the
  extraction, alignment and runtime grounding judges each write their
  client's declared effort ("not configured" for a client that declares
  none), and the alignment mechanical gate writes "not applicable
  (mechanical gate)" (B84 item 1).
- The sampler's label act and `--compute` refuse (exit code 2, the sheet
  untouched) when the evaluation records cannot be listed, naming the
  reason, where an unlistable directory was a traceback (B81 item 39).

### B70: the facade image for hosting the experiment
- The Dockerfile's core target (the facade image) runs uvicorn with
  --no-server-header, as user 1001 in group 0 (OpenShift's arbitrary user
  id runs it too), with data/review_queue writable by group 0 and the dumps
  read-only; the request log path stays TERE4AI_REQUEST_LOG (the hosted
  deployment sets /dev/stdout). The build-time Layer 1 parse now writes to
  a scratch directory: it used to rewrite data/graph_dumps/layer1.json with
  a new built_at, so the image served another chain id than the dump it
  was built from (build-3b753e5e9297+chain-5cd54648b7fd instead of
  +chain-7442562dce5c), and it refuses to run once a publication names the
  file. New scripts/served_build_id.py prints the build id the facade
  serves (load_active); the image build runs it with --expect
  "$TERE4AI_SERVED_BUILD_ID", fails on a different id, keeps the id in
  /app/SERVED_BUILD_ID and labels the image tere4ai.served_build_id with
  the build argument. New .dockerignore keeps .env files, .venv,
  node_modules, caches, .git, the request logs, checkpoints, work files,
  lock files, layer23.nt and the benchmark payload out of the build
  context, and keeps the served files, the chain and publication files and
  the build and evaluation records /api/builds and /api/evaluations read.
  Tests: tests/unit/test_container_image.py.

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
- `role_usage` also types the three counts records already carried
  (`calls`, `input_tokens`, `output_tokens`) as non-negative integers; a
  record with another value no longer validates.
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

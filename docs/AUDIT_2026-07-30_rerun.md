# Adversarial audit of the live demo, 2026-07-30 (re-run)

> Second same-day pass of the repeatable adversarial audit (docs/AUDIT_RUNBOOK.md),
> run after the morning audit (docs/AUDIT_2026-07-30.md) shipped its fixes. Four
> independent read-only passes against a live stack started deliberately WITHOUT
> model API keys, so the paid paths could only degrade and no paid call could fire
> (none did). Every headline finding was reproduced by the coordinator before any
> fix, and each fix was verified against the live stack after a server restart.
>
> Formatting rule: never use em dashes; never use en dashes as a sentence break.

## Method

- Stack under test: facade on port 8008 (keyless, TERE4AI_DEMO_SESSIONS_DIR set to
  tests/fixtures/demo_sessions), web UI on port 3111, published dump
  build-3b753e5e9297, chain id 4a98820a5915.
- Baseline before attack: main clean at 0b6035c, full suite 594 passed and 11
  skipped, ruff clean, traceability and web-copy honesty gates green.
- Pass A, facade protocol abuse: about 300 hostile HTTP requests (type confusion,
  oversized and hostile-unicode payloads, path traversal in several encodings,
  method and content-type confusion, batch cap probing, 50-way concurrency,
  error-hygiene scanning).
- Pass B, browser red team (headless): all five pages at 1440 and 375 widths plus
  dark mode, hunting state bleed, races, injection, caveat presence, keyboard
  reachability, and rendered-versus-raw discrepancies.
- Pass C, honesty-contract audit: the DEC-08 and DEC-13 contracts attacked from
  the outside over 620 live envelopes, 143 spans byte-compared to the frozen
  snapshot, and 1050 quote-field values compared to the snapshot bytes.
- Pass D, demo-script fidelity: docs/DEMO.md walked literally in both run modes,
  every fallback artifact opened, the fresh-clone question retested.

## What held under attack (verified, not assumed)

- No paid endpoint ever returned a 200 with model content. Every paid path
  (/api/elicit, /api/evidence, /api/backlog) degraded to 503 or a clean 4xx,
  including when driven with a real norm id that reaches the paid client builder.
- All ten known-fixed defects from the morning audit held (staleness-bleed guard,
  permalink reload no-revert, Article 27 FRIA rendered verbatim on /assess, HLEG
  caveat on /review, mobile top-bar non-legal notice, prohibited status on its own
  labelled line, keyless env-var copy behind an opt-in disclosure, and the rest).
- Injection inert: XSS, RTL override, zero-width, emoji, and 10k-character
  descriptions all rendered as literal text (the description is context-only, only
  base64 in the permalink hash), no script execution, no layout overflow.
- Determinism: 50 concurrent classifications byte-identical apart from timestamps.
- Error hygiene across roughly 300 hostile bodies: no leaked filesystem paths, no
  tracebacks, no module names, every status inside the calibrated vocabulary.
- Path traversal blocked in every encoding attempted; method and content-type
  abuse produced clean 405s and 422s.
- Span integrity: 143 of 143 spans char-exact against the snapshot and MANIFEST;
  DEC-08 vocabulary clean across 620 envelopes (every banned-term occurrence sat
  inside an exempt field, never a system verdict); deterministic path imports zero
  model SDKs; coverage tiles show judge-accepted counts (339 norms, 475
  alignments); served chain id equals BUILD_CHAIN_CURRENT.txt.

## Defects found and fixed (all with tests, gates green after each)

- FIXED C1 (correctness, high) requirements.py: an unsettled classification could
  be laundered into certainty. Feeding a requires_human_review classification
  (confidence 0.5, a prohibition-relevant fact unknown) into
  get_applicable_requirements returned status applicable_missing_evidence at
  confidence 1.0 with empty missing_facts and 277 requirements, erasing the
  abstention. This is the exact classify to requirements chaining that llms.txt
  documents. Fix: the requirements envelope now defers to the classifier's own
  determination. When the upstream status is requires_human_review or the risk
  category is uncertain, it preserves that status, the upstream confidence, and
  the upstream missing_facts, lists the requirements as provisional (answer
  provisional true plus a provisional_note), and never upgrades the certainty. A
  settled high_risk (confidence 1.0, no missing facts) is unchanged. Note: the
  first implementation keyed unsettled off the mere presence of missing facts,
  which over-fired on a confident classification whose only unknowns were further
  Annex III categories (the deterministic ladder returns potentially_applicable at
  confidence 1.0 there). The rule was narrowed to the classifier status and the
  uncertain category, verified against live output in both directions.
- FIXED C1 UI (correctness) web/src/app/assess/page.tsx: the assess page rendered
  the propagated status and confidence but dropped the requirements envelope
  provisional flag and provisional_note. A provisional caution now renders the
  note verbatim when answer.provisional is true, so the demo-facing screen no
  longer hides why the requirements are provisional.
- FIXED C8 (contract) http_facade/app.py: GET /api/span and POST /api/trace/batch
  did not carry the Section 8 envelope keys (non_legal_advice_notice, status,
  graph_version). Both now carry them, reusing the same envelope builder the MCP
  server uses, while /api/span keeps its flat span fields for existing consumers.
- FIXED C6 (honesty) export_ui_data.py and web landing page: the coverage
  "pending human review" tile showed only the cross-reference count (102). It now
  shows the true total pending review, 288, computed server-side from the build
  artifact (41 judged norms plus 145 HLEG alignments plus 102 cross-references),
  with the breakdown in the page copy.
- FIXED C7 (honesty) web landing page: the coverage caption claimed the
  publication chain was "verified at server startup", which the demo facade never
  does (only the MCP server verifies). It now states the chain is recorded by the
  build and shown from the served build artifact. A guard test bans the old
  phrase.
- FIXED C5 (honesty) classify.py: schema-invalid input returned status
  not_applicable, a substantive in-scope verdict a consumer could misread. It now
  returns rejected_as_unsupported (refused, not assessed). A well-formed
  out-of-scope system still returns not_applicable.
- FIXED C2 (DEC-08 hole) tools.py: the field name "title" was in
  VERBATIM_QUOTE_FIELDS, so the banned-term strip skipped model-generated backlog
  titles. Investigation confirmed no legitimate verbatim quote is keyed "title"
  (frozen source headings surface only through the exempt excerpt and text
  fields), so "title" was removed from the exempt set. Model-generated backlog
  titles are now scanned.
- FIXED C3 (spec accuracy) architecture.md Section 8 and DEC-08, plus tools.py
  comments: the spec called the norm action and object fields "verbatim quoted
  source text ... never altered ... byte-exact", but they are normalized deontic
  extractions (case-folding, whitespace, elision), not byte-exact quotes. The two
  exempt categories are now distinguished: (a) byte-exact quotes-of-record (source
  span text and corpus or evidence quotes), preserved byte-for-byte; and (b)
  normalized deontic extractions, exempt from the verdict-ban as extracted
  regulatory content but NOT asserted byte-exact. No extracted data changed; the
  byte-exact quote-of-record for a norm is its source span text.
- FIXED (trivial) favicon.ico 404 on every page: a minimal favicon was added at
  web/public/favicon.ico.

## Open items, recorded not silently dropped

- C4 (declined this round, tracked): answer.prohibited is hardcoded false even
  when the risk is undetermined (risk_category null or uncertain). This is contra
  DEC-13's "unknown never coerced to false". No over-claim is made elsewhere. The
  user chose to leave it for a later decision on the prohibited field's semantics.
- Malformed or wrong-shape permalink is silently discarded to a blank form with no
  message (a small no-silent-degradation gap). A valid permalink restores and
  reclassifies correctly. Pasting a permalink into an already-open tab does not
  restore, because the app reads the permalink on mount, not on hashchange.
- A very long description balloons the permalink URL (carried over from the
  morning audit).
- No request-body size cap on the facade, so responses amplify roughly 2 to 3x.
  app.py explicitly defers gateway hardening to Phase 2, and the endpoint is
  loopback-only and rate-limited, so this is out-of-scope-by-design for Phase 1.
- The Server: uvicorn banner is disclosed on every response (framework
  disclosure, cosmetic for a loopback demo).

## Provenance

Full per-pass findings with reproduction steps and screenshots were written to the
gitignored scratch redteam directory; the material facts are summarized here,
which is the durable record. Suite after all fixes: 603 passed, 11 skipped, with
ruff, traceability, and the web-copy honesty gate green. Live re-verification after
a facade restart confirmed C1 (both directions), C5 (both directions), C8, C6, and
C7 against the running stack.

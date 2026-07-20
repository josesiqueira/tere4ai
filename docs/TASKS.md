# TERE4AI v2 task board

> The single tracked source of truth for open work, split by WHO can do it.
> Survives any session clear: it lives in git, alongside the operational
> journal (docs/live_audit_log.md, gitignored) and the generated matrix
> (docs/traceability.md). Update this file when a task closes; keep entries
> short and point at the artifact that carries the detail.
>
> Formatting rule: never use em dashes, and never use en dashes as a
> sentence break.
>
> Last updated: 2026-07-20 (session: judge hardenings, SELF-05, diagrams,
> FRIA applicability rule DEC-14).

## A. Human-required (only Jose can do these)

| # | Task | Where / how | Why it matters | Est. |
|---|---|---|---|---|
| H1 | Judge FA/FR labeling (ledger task 25) | Read eval/gold/judge_label_sheet.md (50 blind-sampled judge decisions), fill human_label for each in judge_label_sheet.json, then run scripts/sample_judge_decisions.py --compute | THE thesis keystone: "the judge closes the grounding gap" has no measured artifact until this exists. FA = judge accepted something wrong (dangerous); FR = judge rejected something fine | 4 to 8 h |
| H2 | Gold-set second-annotator pass (task 26) | eval/gold/draft_candidates.json (70 drafts, 18 assigned to annotator B per ANNOTATION_PROTOCOL.md); compute kappa with eval/agreement.py | The promised inter-rater statistic has no artifact; blocks the ablation paper | 1 to 2 h + coordination |
| H3 | The 88-item Article 50 annotation pass | ANNOTATION_PROTOCOL.md priority set (gold minimal_or_none vs predicted transparency_only cell) | Decides whether the 144-vs-207 accuracy gap reads as "graph loses" or "benchmark taxonomy disputed, adjudicated here" | 3 to 5 h |
| H4 | Adjudicate the 41 needs_human_review norms | scripts/review_cli.py list / decide; decisions republish with HUMAN_REVIEWED provenance | Human-loop evidence for the journal paper; also 145 pending alignments and 102 crossrefs in the same queue | 2 to 3 h |
| H5 | Sign off the 3 elicitation over-classifications (task 74) | eval/results/ELICITATION_ERRORS.md verdicts | RQ5 polish | 30 min |
| H6 | Decisions: target venue + deadline (OPEN-VENUE), license (OPEN-LICENSE, no LICENSE file exists), git remote yes/no (CI has never run; this machine is the only copy of the repo) | USER.md open decisions; architecture.md Section 15 | OPEN-VENUE drives all scheduling; the remote decision is also the backup question | about 1 h |
| H7 | Verify SELF-05 CEUR-WS volume and pages when proceedings publish | docs/references.md [VERIFY] tag on SELF-05 | Register hygiene | 10 min |
| H8 | Approve or decline the PAID judge re-passes: F1 (re-judge the 65 Article 16 actor-inference norms with the inference-source text in the judge input) and F5 (re-run alignment with full HLEG descriptions) | See docs/live_audit_log.md 2026-07-20 entry; reference point: a full judge sweep costs about 9.6 USD, these are smaller | F1 is the highest-correctness open judge issue; code fix can land free, the dump only updates after a paid pass | decision only |
| H9 | CLOSED 2026-07-20 by Jose's decision: TERE4AI will NOT generate FRIA content; its scope is detecting whether a FRIA is required (DEC-14) and serving the Article 27 obligations verbatim. No content phase, no source gathering needed | Decision recorded in architecture.md DEC-14 and CHANGELOG | closed |

## B. Agent next (free, no approval needed beyond a go)

| # | Task | Sketch | Est. |
|---|---|---|---|
| B1 | DONE 2026-07-20: F2 exceptions surfaced in get_applicable_requirements | See commit history | done |
| B2 | DONE 2026-07-20: F3 Article 3 definitions in the elicitor prompt (v3) | See commit history | done |
| B3 | DONE 2026-07-20: F4 norm source_text in the runtime grounding judge digest | See commit history | done |
| B4 | F1 code half: include actor-inference-source text in the extraction judge input + prompt check update (landing on dumps needs H8 approval for the paid re-pass) | Audit fix sketch in docs/live_audit_log.md 2026-07-20; touches extract_norms/pipeline.py _judge_user_message + prompts/judge_norms (new version v2) | 1 to 2 h |
| B5 | Determinism-leak guards from the 2026-07-19 audit: log marker + test for the silent temperature-retry fallback in model_clients.py; sha256 re-verification in tools._excerpt (source_trace); extend the no-model-import guard to explain/trace/spans/tools; MCP-layer config-of-record check | Each is small and separable | 2 to 3 h total |
| B6 | Push to a remote and watch the first CI run (after H6 remote decision) | .github/workflows/ci.yml exists, never executed | 30 min |
| B7 | Task 68 extension: live adversarial judge run over the 12 fixtures (PAID, quote first, single-digit USD) | scripts/adversarial_evidence_report.py has the offline half | approval + 1 h |
| B8 | Optional hygiene: anchored committed-secret scan gate (proposed 2026-07-12); dark-mode toggle drift vs DESIGN.md; UI facade URL env override | Low priority, demo-scoped | 1 to 2 h each |
| B9 | DONE 2026-07-20 (ledger task 85, hardened same day per Jose's spec review): FRIA applicability rule (DEC-14). classify answers carry a fria block (applies / does_not_apply / unknown) from Article 27(1) facts; new schema facts creditworthiness_evaluation, life_health_insurance_risk_pricing, deployer.*; requirements pass it through; a pending Article 6(3) derogation blocks the decision; applies_from (2027-12-02, Omnibus) rides as data | src/tere4ai/mcp_server/fria.py; tests/unit/test_fria.py | done |
| B10 | Elicitor prompt v4: teach the elicitor the two new FRIA-relevant flags with the verbatim Annex III point 5(b)/(c) texts from the dump (same pattern as the v3 Article 3 definitions); deployer.* facts stay direct-input only, a system description cannot settle who deploys it | Code change is free; affects only future PAID elicitation runs | 1 h |
| B11 | AUDIT D1 (top safety fix): surface unknown Annex III flags in missing_facts and refuse confidence 1.0 on a minimal_or_none verdict when Annex-III-relevant flags are absent and the domain is non-canonical. Mirror the prohibition-flag treatment | docs/AUDIT_2026-07-20.md D1; classify.py PROHIBITION_RELEVANT_FLAGS + minimal path | 2 to 3 h |
| B12 | AUDIT D2: make the dropped Article 5 qualifiers/exceptions expressible (7 of 8 points) so a lawful safety/human-support system is not marked prohibited at confidence 1.0; degrade + route to review when a prohibition flag is true but its exception facts are unknown | docs/AUDIT_2026-07-20.md D2; classify.py ARTICLE_5_* + schema | 3 to 5 h |
| B13 | AUDIT D5/D6/D7 (FRIA correctness): pass the unsettled-prohibition signal and the 6(3) candidacy into the FRIA rule so it degrades to unknown; fix the point-2 multi-area exception to scope to the area, not the whole system; drop the D8 Unicode-normalise on domain | docs/AUDIT_2026-07-20.md D5-D8; fria.py + classify.py | 3 to 4 h |
| B14 | AUDIT D4 (F6, honesty): wire the runtime evidence/backlog tools to resolve each cited norm's verbatim source text at serve time and add the verbatim-wording instruction to prompts/runtime_grounding/v1.md, so the F4 fix is actually live in production | docs/AUDIT_2026-07-20.md D4; evidence.py, backlog.py, server.py | 2 to 3 h |
| B15 | AUDIT D3 (runtime integrity): recompute the build-chain (or a dump-level checksum) against the matching build_chain_*.json at dump load, so a tampered dump is refused at runtime, not only in CI; optionally re-assert G4 and JudgeRun existence at serve time | docs/AUDIT_2026-07-20.md D3; server.py _read_dump | 3 to 4 h |
| B16 | AUDIT weaknesses batch (each small): W6 fria.py model-free guard test (do first); W7 fria-in-envelope guard; W5 advertise FRIA + batch tool in SKILL.md/llms.txt; W8 fix the SELF-05 self-contradiction + list FRIA in trustworthiness_strategies.md; W2 prompt_sha256 on the mechanical JudgeRun; W4 strip absolute paths from degraded envelopes; W11 build_chain latest marker | docs/AUDIT_2026-07-20.md weaknesses | 4 to 6 h total |

## C. Blocked externally

| # | Task | Blocked on |
|---|---|---|
| C1 | Omnibus provisions ingestion (task 34) + re-run of affected extraction; also reconfirm the FRIA applies_from date (fria.py FRIA_APPLIES_FROM) against the OJ text | Final OJ text publication (REF-02 [VERIFY]). Status checked 2026-07-20: Parliament approved 16 June 2026, Council 29 June 2026, OJ publication imminent |
| C2 | ALTAI items in the ethics layer | Redistribution license check (OPEN-LICENSE) |

## Where the context lives (for a fresh session)

- This file: the open work, by owner.
- docs/live_audit_log.md (gitignored): the operational journal, one entry per
  session batch, including the 5 missing-context findings (F1 to F5) of
  2026-07-20 with counts and fix sketches.
- docs/trustworthiness_strategies.md: the 33-strategy register (strategy,
  grounding, traceability).
- docs/THESIS_MAP.md: RQ to artifact mapping. docs/traceability.md: generated
  DEC matrix. CHANGELOG.md: what shipped.
- Diagrams: tere4ai_v2_architecture.svg/png and judge_diagram.svg/png, both
  regenerated deterministically by scripts/make_*_diagram.py, guard-tested.
- git log: every batch has a self-contained commit message with evidence.

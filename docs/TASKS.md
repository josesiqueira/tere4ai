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
| B11 | DONE 2026-07-20 (commit e9fa338): AUDIT D1+D8. Unknown Annex III flags surfaced, confident minimal blocked when they are absent; domain Unicode-normalised | classify.py; tests | done |
| B12 | DONE 2026-07-20 (commit ee21342): AUDIT D2. Article 5 exculpating-fact model; lawful safety/human-support systems no longer confidently prohibited; unknown exception fact routes to review | classify.py + schema; RUN2 scenario 76 reconciled | done |
| B13 | DONE 2026-07-20 (commit 87bc5fc): AUDIT D5/D6/D7. FRIA point-2 exception scoped to the area (multi-area fix), unsettled classification and dual-route 6(3) candidacy degrade to unknown | fria.py + classify.py; tests | done |
| B14 | DONE 2026-07-20 (commit 446c556): AUDIT D4/F6. Evidence/backlog tools resolve verbatim source_text at serve time; runtime_grounding prompt check 0 added | server.py, backlog.py, prompt; tests | done |
| B15 | DONE 2026-07-20 (commit 446c556): AUDIT D3. verify_dumps_against_chain runs at server startup (hard-fail behind TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY=1); tamper test proves it | build_chain.py, server.py; tests | done |
| B16 | DONE 2026-07-20 (commit 6c6d464): AUDIT weaknesses W2/W4/W5/W6/W7/W8 (see commit) | multiple; tests | done |
| B17 | DONE 2026-07-21 (commit 9ec2397): W1. _llm_provenance maps verdict faithfully (accepted/rejected/needs_review/unjudged); build-time change, applies on next republish, serving unaffected | graph_store/layer23.py; tests | done |
| B18 | DONE 2026-07-21 (commit e45b3dd): W3. high_risk requirements scoped to the obligation regime (Articles 8 to 27, 50 where triggered, 72 to 73); Article 5 prohibitions and Annex classification rows no longer served as requirements (339 -> 277) | requirements.py; tests | done |
| B25 | ELICITOR harm/exception facts (surfaced by the D1/D2 benchmark-delta analysis, docs/AUDIT_2026-07-20.md): teach the elicitor prompt (v4) to set causes_significant_harm and the other Article 5 exculpating facts when the text supports them, so a genuinely harmful manipulation/exploitation system resolves back to prohibited instead of abstaining to requires_human_review. Free code change; affects future PAID elicitation runs. Pairs with B10 | prompts/elicit_features | 1 to 2 h |
| B19 | DONE 2026-07-21 (commit a1c0c39): W11 build-chain current marker (data/graph_dumps/BUILD_CHAIN_CURRENT.txt) | done |
| B21 | DONE 2026-07-21 (commit fb0b3c2, ULTRACODE re-check find): source_trace returned the WRONG legal text for every HTML-manifestation node (519 paragraphs + 180 recitals, incl. Articles 9/10/13/50) because _excerpt used read_text (universal-newline translation) instead of byte-decoding; now delegates to resolve_span (byte-correct, checksum-verified, path-guarded). A Section 8 traceability tool was showing wrong provenance | src/tere4ai/mcp_server/tools.py; tests | done |
| B22 | DONE 2026-07-21 (commit a1c0c39): verify_dumps_against_chain now cross-checks recorded per-input checksums against live files (re-check defense-in-depth) | build_chain.py | done |
| B23 | DONE 2026-07-21 (commit cd1464c): second ultracode ran (3 agents completed). source_trace VERIFIED correct on a 222-node live sweep, 0 mismatches, path-escape safe; D2 held both directions; D4 confirmed live end to end. It FOUND a regression from the D5 FRIA fix (the two early does_not_apply returns treated unknown 5(b)/5(c) as false -> confident wrong does_not_apply), now fixed, plus a docstring misattribution and a batch-guard gap, both fixed. Five judge-improvement ideas overlapped B24 | fria.py, tools.py, evidence.py; tests | done |
| B24 | DONE 2026-07-21: judge-improvement IDEAS documented (docs/AUDIT_2026-07-20.md "Judge-improvement ideas"): adversarial multi-vote on high-stakes verdicts, perspective-diverse verification, score calibration via H1 labels, abstention-rate monitoring, prompt-version A/B re-judge sampling. Each names its plug point and cost. No code change decided; pairs with H1 | docs/AUDIT_2026-07-20.md | analysis done |
| B20 | POST-AUDIT (paid, Jose approval): re-run the full ablation so the frozen benchmark numbers reflect the D1/D2 behavior. FREE HALF DONE 2026-07-21 (docs/AUDIT_2026-07-20.md "D1/D2 benchmark-delta analysis"): of 32 sampled items, 10 shifted, ALL from a confident "prohibited" to a requires_human_review abstention (designed calibrated behavior, not a regression; the elicitor did not set the harm/exception facts, see B25). The paid re-run would report the refreshed headline accuracy with this abstention behavior; do it after B25 so the elicitor sets the facts first | eval/results, docs/THESIS_MAP.md | approval + run |

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

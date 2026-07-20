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
> Last updated: 2026-07-20 (session: judge hardenings, SELF-05, diagrams).

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

## C. Blocked externally

| # | Task | Blocked on |
|---|---|---|
| C1 | Omnibus provisions ingestion (task 34) + re-run of affected extraction | Final OJ text publication (REF-02 [VERIFY]) |
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

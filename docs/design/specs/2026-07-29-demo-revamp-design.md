# Demo revamp design (approved 2026-07-29)

> Venue-neutral public demo of TERE4AI v2. Replaces the REFSQ-specific demo
> framing. Approved by Jose 2026-07-29 after a structured design discussion.
> Formatting rule: never use em dashes; never use en dashes as a sentence
> break.

## Purpose and audiences

The demo proves one claim: TERE4AI is a useful, trustworthy MCP server for
coding agents working under the EU AI Act. Every element serves traceability
(answers trace to law), calibration (the system knows when not to answer),
or agent usefulness (machine-actionable envelopes). Audiences: conference
talks (projector, scripted), thesis defense and academic panels (drill-down
depth), industry practitioners (agent workflow front and center). No
unattended self-serve deployment in scope.

## Input modalities

1. Freestyle description (audience-participation beat): manual tri-state
   fact panel, plus automatic mode: one paid elicitor call fills the panel
   from a typed description. Facts stay editable; the free deterministic
   ladder alone classifies (DEC-13).
2. Replay: recorded MCP sessions from the real development of the four
   example projects (examples/1-minimalrisk-spamguard through
   4-unacceptablerisk-moodwatch). Session files are the true development
   history, not synthetic demo data.
3. Live agent: a coding agent (Claude Code or another MCP harness) driving
   the real MCP server against an example repo pinned at stage-0 (naive
   scaffold). The replay of the same example is the rehearsed fallback.
4. GitHub repo links (INCREMENT 2, committed, not forgotten): paste a repo
   URL; a demo-harness agent clones and reads it and proposes the 34 facts,
   each with a supporting quote from the repo; proposals land in the fact
   panel as editable, visibly marked values; the deterministic ladder
   decides. Both a curated pre-tested repo list and arbitrary URLs accepted
   live. Lives in the agent layer, never inside TERE4AI core: repos are
   untrusted input (architecture.md Section 8), and repo reading is the
   consumer agent's job. Enters docs/TASKS.md as its own row when
   increment 1 implementation starts.

## UI structure

Left sidebar navigation (modern, professional, clean; DESIGN.md already
defines sidebar tokens, unused until now). Implementation MUST use the
impeccable frontend skill plus DESIGN.md; all copy obeys the no-em-dash
rule and the DEC-08 scoped banned-term contract.

Pages:

- Coverage (home): stat tiles (113 articles, 180 recitals, 13 annexes, 434
  norms of which 339 judge-accepted, 475 accepted alignments, 426
  crossrefs), graph version and build-chain hash, existing coverage matrix.
- Assess (centerpiece): four example presets (SpamGuard, ShopBot,
  CredScore, MoodWatch plus MoodWatch-safety-variant); fact panel with
  provenance marking (manual vs elicited; elicited values expose their
  supporting quote; always editable); "elicit from description" button
  (paid, one call); interactive evidence subgraph beside the
  classification and each requirement group; requirements board; backlog.
- Agent: session replay, split view (raw JSON request/envelope left,
  rendered meaning right), step-through controls, session picker. Live
  mode runs in a terminal beside this page.
- How it works: architecture and judge diagrams (both deterministically
  regenerated, guard-tested), trust-split story, calibrated vocabulary
  legend, non-legal-advice framing.
- Review: existing page, cosmetics only.

## Requirements board

Requirements grouped by calibrated status: satisfied_with_evidence,
partially_satisfied, applicable_missing_evidence (the to-be-done column),
rejected_as_unsupported, requires_human_review. Fed from recorded sessions
in replay mode or live paid evidence evaluations. Hard guard: labels are
the vocabulary terms with plain-language subtitles; never "fulfilled",
never checkmark-equals-compliant iconography; the scoped banned-term test
covers the board's static strings.

## Backend changes (thin, facade-level, envelope-disciplined)

- POST /api/elicit: wraps the existing elicitor. Paid, guarded exactly like
  the other paid tools, degrades to an envelope without keys, structurally
  cannot return a risk category. Recorded deviation (final review of Plan A,
  2026-07-29): the envelope carries features plus elicitation notes; PER-FACT
  supporting quotes are deferred to increment 2 (the schema has no support
  field and the elicitor strips unknown fields, so quotes need a schema
  extension that lands with the GitHub modality, which requires them anyway).
  Until then the UI marks elicited values as elicited and shows the
  elicitation notes; it must NOT render a per-fact quote affordance.
- GET /api/demo/sessions and /api/demo/sessions/{id}: read-only serving of
  session JSONL files from a directory named by an env var
  (TERE4AI_DEMO_SESSIONS_DIR), path-guarded like source_trace, disableable.
- No other backend change: the subgraph and the board render from data
  already carried by envelopes.

## Session recording format

JSONL, one exchange per line: {seq, ts, tool, request, envelope, repo_ref}.
The example consumer scripts append to
examples/<n>/artifacts/sessions/<date>-<label>.jsonl from now on, so real
example development produces demo content as a side effect. A parity test
replays a recorded session against the live tools on the same dump and
asserts byte-equal envelopes (replay honesty).

## Evidence subgraph component

Small force-layout component from a self-contained npm dependency (no CDN;
the demo must run offline). Nodes colored by layer with DESIGN.md tokens.
Click opens the cited node's verbatim text via source_trace. Renders
whatever graph_evidence_subgraph the envelope carries.

## Demo document rewrite

docs/DEMO.md becomes venue-neutral: a 7-minute talk script, a 20-minute
panel script with drill-down pointers (judge logs, review queue, build
chain), a live-agent setup checklist (keys, MCP config, curated repo list
placeholder for increment 2), and a fallback matrix where every live step
names its replay or screenshot fallback. REFSQ references elsewhere
(references.md citations, USER.md, TASKS.md history) are legitimate and
stay.

## Testing and honesty guards

- Facade tests for both new endpoints: envelope contract, paid-guard
  without keys, path-escape attempts on the sessions dir, scoped
  banned-term scan.
- Replay parity test (byte-equal envelopes).
- tsc --noEmit and next build clean; full Python suite plus ruff,
  traceability, hygiene, and dash gates green.
- Fresh screenshots into docs/screenshots/ as demo fallback artifacts.
- Existing caveats render on every new view: HLEG mappings LLM-generated
  and not expert-validated; non-legal-advice notice; calibrated vocabulary.

## Out of scope

Guided tour overlay; full graph explorer; FR/NFR/organizational facet
(B28, awaiting its own design discussion); multi-tenant or self-serve
hosting; any change to classification, judge, or graph logic.

# TERE4AI v2 demo script

Venue-neutral walkthrough of the shipped stack: coverage matrix, one-click
classification presets, the evidence subgraph, the requirements board, and
agent session replay. Every live step below names a fallback (a recorded
session or an existing screenshot) so the talk survives a dead network or a
missing key. See the Fallback matrix at the end for the full list.

## Setup

Two ways to run the stack. Either gets you the facade on port 8008 and the
web UI on port 3111.

**Docker (recommended for a live room):**

```bash
cp .env.example .env       # OPENAI_API_KEY and ANTHROPIC_API_KEY are optional
docker compose --profile demo up -d
# facade http://localhost:8008, web http://localhost:3111
```

**Dev mode (recommended for iterating on the demo itself):**

```bash
TERE4AI_DEMO_SESSIONS_DIR=examples/1-minimalrisk-spamguard/artifacts/sessions \
  .venv/bin/python -m uvicorn --factory tere4ai.http_facade.app:create_app --port 8008
cd web && npm run dev -- -p 3111
```

`TERE4AI_DEMO_SESSIONS_DIR` enables the agent replay page (`/agent`); without
it the page renders an explicit "session replay is not enabled" card, never
a blank one. Point it at any example's `artifacts/sessions` directory; the
path above is the one recorded for this script.

Keys are optional. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` unlock the paid
evidence-evaluation call (Article 9(1) style checks against pasted project
text) and the elicit mode (free-text description to structured facts).
Coverage, classification, requirements, the evidence subgraph, and the
requirements board all work fully without any key: the deterministic ladder
never calls a model.

Sanity check: `curl localhost:8008/api/health` returns the graph version.

## The 7-minute talk

1. **Coverage** (1 min). Open `http://localhost:3111`. Point at the stat
   tiles (article, recital, and annex counts against the frozen source), the
   judged Layer 2/3 counts with verdicts, and the publication chain id in the
   footnote, served by the facade and verified at server startup, not
   computed client side. Expand a chapter to show the browsable structure.
   Fallback: `docs/screenshots/coverage_light.png` or
   `docs/screenshots/m2-coverage-with-judged-layers.png`.
2. **Five presets, ascending severity** (3 min). Go to `/assess`. Click
   through the five preset buttons in order and classify each one:
   - `spamguard`: minimal_or_none, no prohibition or Annex III flag applies.
   - `shopbot`: transparency_only via Article 50 (it talks to people and
     generates text, but does not profile, score, or decide about them).
   - `credscore`: high_risk via Annex III point 5(b), FRIA applies. This is
     the one to slow down on: load requirements next and open the evidence
     subgraph (see step 3).
   - `moodwatch`: prohibited via Article 5(1)(f). Workplace emotion
     recognition with the medical or safety exception explicitly ruled out
     by the scenario text, so the ladder prohibits with no exception to
     resolve.
   - `moodwatch-safety`: same workplace emotion recognition, but the
     deploying company now claims a driver fatigue safety purpose. TERE4AI
     cannot verify that claim from a description alone, so the exception
     fact is left unknown rather than assumed true or false. The ladder
     declines to confidently prohibit or confidently clear the system: the
     classification card still shows a risk category from the ladder
     (high_risk was observed in testing) alongside status
     requires_human_review. Say this plainly: that pairing is the point,
     not a bug. It is calibrated abstention, the system refusing to guess an
     exculpating fact into existence just because a description asserts a
     safety purpose.
   Fallback: `docs/screenshots/demo-assess-credscore.png` or
   `docs/screenshots/assess_result_light.png`.
3. **Evidence subgraph on credscore** (2 min). With credscore still loaded,
   click "Load requirements", expand an article group (Article 9 or Article
   27 read well), and toggle "Show evidence graph". Walk the force-directed
   layout: norm nodes, HLEG nodes, the alignment edges between them, solid
   for an accepted judge verdict and dashed for anything else. Click a node
   to pull its verbatim source span inline, never a modal. This is the
   traceability claim rendered as a picture: every requirement traces to a
   legal source span and, where an alignment exists, to an HLEG principle.
   Fallback: `docs/screenshots/demo-assess-subgraph.png`.
4. **Close on the agent replay page** (1 min). Go to `/agent` and step
   through the recorded SpamGuard exchange: the raw request and envelope
   side by side with the rendered meaning (tool, status, judge verdict,
   confidence, missing facts). This is the same envelope shape a coding
   agent receives over MCP; the web UI adds nothing the agent does not
   already have. Say the closing line here: engineering support, not
   compliance certification, and every claim on screen traces to a source
   span or a recorded call.
   Fallback: `docs/screenshots/demo-agent-replay.png`.

## The 20-minute panel cut

Everything in the 7-minute talk, plus:

- **How it works** (2 min). Open `/how-it-works` for the pipeline diagrams:
  the layered graph model, the deterministic-first build pipeline, and where
  each of the three judges sits (build-time extraction judge, build-time
  mapping judge, runtime grounding judge). Use this to answer "where could
  this go wrong" before anyone asks it.
  Fallback: `docs/screenshots/demo-how-it-works.png`.
- **Judge drill-down** (2 min). For "what if the judge is wrong": open
  `docs/live_audit_log.md`, a running journal of live audits against the
  actual published graph (edge provenance, orphan checks, span coverage,
  accepted-alignment evidence), each entry showing hypotheses, evidence, and
  a verdict. Then open `/review` for the disclosed human-review queue: every
  norm the extraction judge marked needs_human_review, plus pending
  cross-reference and alignment counts. Adjudication runs from
  `scripts/review_cli.py` (list, show, decide, stats); decisions accumulate
  separately from the graph dumps and apply at the next publish, so the
  queue is disclosed, never hidden or silently auto-resolved.
  Fallback: `docs/screenshots/review_light.png`.
- **Requirements board with a live evidence call** (2 min). Back on
  `/assess` with credscore loaded and requirements fetched, scroll to
  "Requirements by evidence status": five fixed columns
  (applicable_missing_evidence, partially_satisfied, satisfied_with_evidence,
  rejected_as_unsupported, requires_human_review), styled identically with no
  green checkmark for a "good" column, because the calibrated vocabulary is
  a status, not a grade. If keys are present, expand the Article 9(1) risk
  management norm, paste two sentences of a synthetic risk plan, and
  evaluate live: read the verdict card aloud, including the judge rationale
  and any gap it preserves rather than papers over. Without keys, describe
  the board from its current state (everything sits in
  applicable_missing_evidence until an evaluation runs) and fall back to the
  screenshot.
  Fallback: `docs/screenshots/demo-assess-board.png`.
- **Elicit mode on an audience-supplied description** (2 min, needs keys).
  On `/assess`, ask the audience for one sentence describing a fictional AI
  system, paste it into the free-text panel instead of a preset, and run
  elicitation. Every filled control gets an amber "elicited" chip; nothing
  is invented for a fact the description does not support, so most runs
  leave several flags at unknown. Classify from there exactly as with a
  preset. Without keys, describe the flow using one of the shipped presets
  and note that presets are the offline stand-in for exactly this
  interaction: they only fill the form, the deterministic ladder still runs
  live.
  Fallback: `docs/screenshots/demo-assess-credscore.png` (a filled form,
  the closest static approximation).

## Live agent mode

For a room that wants to see a real coding agent consume TERE4AI over MCP
rather than the web UI.

Checklist before starting:

- Keys set in `.env` if the agent's own requirements or evidence calls
  should hit the live models rather than a cached session.
- The MCP server reachable over stdio (Mode B, trusted workstation; no key
  required for local stdio, per architecture.md Section 8).

MCP config snippet, for a coding agent's stdio server list:

```json
{
  "mcpServers": {
    "tere4ai": {
      "command": ".venv/bin/python",
      "args": ["-m", "tere4ai.mcp_server.server"],
      "cwd": "/path/to/tere4ai2"
    }
  }
}
```

Then walk the same loop the `examples/` consumer apps followed: write the
product's plain-English description and facts first, before touching
TERE4AI, so elicitation is tested against honest input; classify via the MCP
tools and record the envelope verbatim; fetch applicable requirements with
citations and HLEG alignments; build against them; evaluate real project
evidence; record lessons learned, defects, and surprising verdicts rather
than papering over them. The four `examples/` folders
(`1-minimalrisk-spamguard`, `2-limitedrisk-shopbot`, `3-highrisk-credscore`,
`4-unacceptablerisk-moodwatch`) are the worked instances of this loop, one
per risk tier, each built as a true external MCP consumer, never importing
TERE4AI code directly.

Curated-repo input (an agent cloning a repository, proposing the 34 facts
each with a supporting quote, landing them editable in the fact panel) is
committed but not yet shipped: it is increment 2 of this demo revamp,
tracked as backlog item B31 in `docs/TASKS.md`, and lives in the agent layer
rather than TERE4AI core, since a repository is untrusted input. Name it as
a placeholder if asked; do not demo it as if it exists.

Fallback if MCP tooling cannot be wired up live: replay a recorded session
from `/agent` instead (see step 4 of the 7-minute talk) and narrate the
tool calls a coding agent would make in the same order.

## Fallback matrix

Every live step above, with the fallback if it cannot run.

| Live step | Fallback |
| --- | --- |
| Coverage tiles and chain id | `docs/screenshots/coverage_light.png`, `docs/screenshots/m2-coverage-with-judged-layers.png` |
| Five presets, classification | `docs/screenshots/demo-assess-credscore.png`, `docs/screenshots/assess_result_light.png`, `docs/screenshots/m3-demo-classification.png` |
| Evidence subgraph on credscore | `docs/screenshots/demo-assess-subgraph.png` |
| Agent replay (SpamGuard exchange) | `docs/screenshots/demo-agent-replay.png` |
| How it works diagrams | `docs/screenshots/demo-how-it-works.png` |
| Judge drill-down (`docs/live_audit_log.md`, `/review`) | `docs/screenshots/review_light.png`, `docs/live_audit_log.md` itself (a static file, always available) |
| Requirements board, live evidence call | `docs/screenshots/demo-assess-board.png`, `docs/screenshots/m3-demo-evidence-verdict.png` |
| Elicit mode on an audience description | `docs/screenshots/demo-assess-credscore.png` (preset form as the closest static stand-in) |
| Live agent mode over MCP stdio | `/agent` session replay, narrated |

## Questions to expect

- "What if the judge is wrong?": the false-accept and false-reject
  measurement protocol (`eval/gold/ANNOTATION_PROTOCOL.md`), the disclosed
  review queue (`/review`, `scripts/review_cli.py`), and the calibrated
  status vocabulary that never says compliant or certified.
- "Why not just ask an LLM directly?": the ablation table comparing plain
  LLM, vector RAG, and the graph-plus-judge conditions
  (`eval/results/RUN2_ANALYSIS.md`), where the graph condition trades some
  raw accuracy for checkable citations and honest abstentions instead of
  confident wrong answers.
- "Is this legal advice?": no. The non-legal-advice notice renders on every
  screen (Section 0 caveat in `docs/architecture.md`), the status vocabulary
  is closed by contract, and `tests/unit/test_web_copy_honesty.py` fails the
  build if a banned claim term appears anywhere in the served copy.
- "What is moodwatch-safety actually showing me?": a system whose evidence
  is deliberately incomplete gets a risk category from the ladder and an
  abstaining status side by side, not a forced verdict. That combination is
  the calibrated-abstention behavior working as designed, not a display bug.

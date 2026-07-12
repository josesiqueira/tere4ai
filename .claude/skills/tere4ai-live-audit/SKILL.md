---
name: tere4ai-live-audit
description: >
  Periodic scientific live audit of the running TERE4AI system. Fire a live
  test against the actual running facade and graph, verify what works and
  what does not with evidence, and ONLY when a change is genuinely warranted
  and fully verifiable, implement one small, gated, traceable improvement.
  The default and most common outcome is "verified healthy, no change made."
  Use for the recurring live-audit loop, or on demand when asked to "fire a
  live test of tere4ai and check what is working / improve something." This
  skill never fabricates findings, never commits without every gate green,
  and never deviates from the PhD's purpose (evidence-gated EU AI Act
  compliance support with deterministic risk classification).
---

# TERE4AI live audit (scientific, trustworthy, bounded)

You are auditing a doctoral research system whose entire value is
correctness, traceability, and honesty (see AGENTS.md, USER.md,
docs/architecture.md). Activity is not the goal. Truth is. A run that
verifies the system is healthy and changes nothing is a SUCCESS, and it is
the expected common case. Manufacturing a "fix" or a fake improvement to
look productive is the single worst thing you can do here; it is scientific
misconduct in miniature. Do not do it.

## Prime directive

Follow the scientific method, not a to-do impulse:
observe -> hypothesize -> test against ground truth -> validate or refute
with evidence -> report honestly -> act only if the evidence demands it.

The bar for making any change: you can state, with verified evidence, a
specific defect or a specific, spec-sanctioned improvement; you can fix it
in a small, self-contained, reversible change; and every gate passes. If
any of those is not true, you report and stop without changing code.

## Hard invariants (never violate, no exception)

1. Ground truth over assumption. Verify every claim against the code, the
   graph dump, the JSON schema, or the legal source text before asserting
   it. This session's own history shows the trap: several "bugs" were just
   envelope-shape misreads. Read the actual output structure; never guess a
   key or a field.
2. Honesty over activity. If nothing is wrong and nothing is warranted, say
   exactly that and end the run. Never invent a problem to justify a change.
3. Stay on the PhD's axis. Only work that serves evidence-gated EU AI Act
   compliance support. The LLM never decides risk classification. The
   status vocabulary is closed and never says "compliant"/"certified". Risk
   tiers and HLEG principles are closed sets; never invent categories. No
   feature the architecture (docs/architecture.md) does not sanction. No
   scope creep.
4. Traceability or it does not ship. Any new or changed module that
   implements a decision carries `@implements: <DEC-id>` and
   `@grounded_by: <REF-id(s)>`. Cite only references that exist in
   docs/references.md. Never invent a citation, metric, or identifier.
5. Gates are absolute. Before any commit, ALL of these must pass; if any
   fails, revert the change and report, do not "fix forward" under time
   pressure:
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/ruff check src/ tests/ scripts/`
   - `.venv/bin/python scripts/check_traceability.py`
   - `.venv/bin/python scripts/check_release_hygiene.py`
   - em/en-dash scan on every file you touched (must find none):
     `grep -rnP '\x{2014}|\x{2013}' <files>`
6. Writing style is a hard rule everywhere (code, comments, commits, docs):
   never an em dash, never an en dash as a sentence break. Commas, colons,
   parentheses, "to" for ranges.
7. Bounded blast radius. One small change per run at most. Never touch
   `.env` or print secrets. Never make destructive or schema-bypassing
   changes. If a change is more than a focused edit plus its test, it is
   too big for this loop: write it up as a proposal and stop.
8. Cost discipline. The loop runs on the FREE deterministic paths by
   default (classify, explain, trace, span, requirements, coverage, health,
   discovery). Do NOT run paid bulk work from this loop: never the full
   ablation, the benchmark run, elicitation, or the variance study. A
   single paid model call is allowed only if it is the only way to verify a
   specific defect and the cost is a few cents; otherwise use the offline
   FakeClient path that the tests already use.
9. No churn. Read the audit journal and recent git log first (below). If
   the last few runs already covered an area or already concluded "healthy,
   no change", do not repeat that work; either probe a different surface or
   conclude quickly.

## Procedure

### 0. Orient (cheap, always)
- `cd /home/jose/Documents/Trustworthy/tere4ai2`.
- Read the tail of the journal `docs/live_audit_log.md` (create it if
  absent) to see what recent runs found and did, so this run does not
  repeat them.
- `git status --short` and `git log --oneline -5`. If the tree is dirty
  from an unrelated edit, do not touch it; report and stop.
- Confirm the facade is reachable: `curl -s http://localhost:8008/api/health`.
  If it is down, try to start it once
  (`.venv/bin/uvicorn tere4ai.http_facade.app:app --port 8008`, background)
  and the web UI if useful; if it will not come up, record that as the
  finding and stop (an unreachable system IS the audit result, not a
  failure of the run).

### 1. Live test (evidence gathering, free)
Rotate the focus across runs so coverage broadens over time. Pick ONE
surface per run from, e.g.: classify across all tiers; requirements /
explain / trace / span envelope correctness; discovery + llms.txt +
agent-readiness; MCP-vs-facade parity; graph integrity (node/edge counts,
provenance on every edge, no orphans); the review queue counts; adversarial
evidence fixtures; schema validity of a dump. Pull real IDs and real schema
field names from the graph before sending requests. Capture the ACTUAL
response structure; do not assume it.

### 2. Analyze (the scientific step)
For each observation, decide honestly: is this (a) correct behavior, (b)
correct-by-design but surprising, (c) a real defect, or (d) a genuine,
spec-sanctioned improvement opportunity? Write down the evidence for the
verdict. Distinguish a real finding from your own misreading; when in
doubt, it is your misreading until proven otherwise. Ambiguity that turns
on a legal or design judgment call is NOT yours to resolve in this loop:
record it as a proposal for Jose and move on.

### 3. Decide
- If everything is correct: journal it and STOP. This is the good outcome.
- If you found a real, small, verifiable defect OR a small spec-sanctioned
  improvement (like the Section 8 envelope-contract test): proceed to 4.
- If you found something real but large, legal/semantic, or requiring a
  human decision: journal it as a clearly-written proposal and STOP. Do not
  implement it.

### 4. Implement (rarely, carefully)
On a working branch if the repo is on its default branch. Make the smallest
correct change. Add or update a test that would fail without the change and
passes with it, and prove it has teeth (confirm it fails on the pre-change
code). Keep comments to real constraints only. Add traceability tags if you
touched a decision-bearing module.

### 5. Verify (mandatory before commit)
Run every gate in invariant 5. If all green, commit with a precise message
that states the evidence, the change, and the gate results. Update
CHANGELOG.md [Unreleased] if the change is user-visible. Run
`graphify update .` after a code change. If any gate is red, `git restore`
/ discard the change and journal the attempt honestly as reverted.

### 6. Report and journal (always)
Append one entry to `docs/live_audit_log.md` (gitignored operational trail;
one block per run) with: timestamp, surface probed, hypothesis, evidence,
verdict (healthy / proposal / change made / reverted), and any commit hash.
Then produce a short final message: what you checked, what you found, what
you did (usually "nothing, verified healthy"), and any proposal for Jose.
Lead with the outcome.

## What is a legitimate change vs forbidden busywork

Legitimate (rare): a demonstrable defect with a failing-then-passing test;
a missing test for an existing honesty/traceability invariant; a genuine
correctness or robustness gap the architecture already calls for; a
documentation error that misstates verified behavior.

Forbidden: cosmetic churn; renames/reformatting for their own sake;
speculative features; changing deterministic classification logic or the
status vocabulary or the reference register without an explicit Jose
decision; "improvements" you cannot back with a passing, teeth-proven test;
anything whose main effect is to produce a commit.

## Stop conditions

Stop and report (do not change code) when: the tree is already dirty; the
system is unreachable; the only findings are legal/semantic judgment calls;
you cannot make a change small and reversible; any gate is red; or you have
no verified, warranted work. "No change this run" is the expected result on
most runs. That is the loop working correctly.

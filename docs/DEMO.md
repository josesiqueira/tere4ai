# REFSQ demo walkthrough

Total time ~7 minutes. Everything below is scripted against the shipped
stack; the fallback for every step is a screenshot in docs/screenshots/.

## Setup (before the session)

```bash
cp .env.example .env       # add OPENAI_API_KEY and ANTHROPIC_API_KEY for step 4
docker compose --profile demo up -d
# facade http://localhost:8008, web http://localhost:3111
```

Sanity: `curl localhost:8008/api/health` shows the graph version. If the demo
machine has no keys, steps 1 to 3 still work fully (deterministic and free);
step 4 falls back to the screenshot.

## Script

1. Coverage (1 min): open http://localhost:3111. Point at the coverage
   matrix: full Act mirrored, judged Layer 2/3 counts with verdicts, the
   snapshot checksum, the notice. Expand Chapter III.
   Fallback: m2-coverage-with-judged-layers.png.
2. Classification (2 min): /assess, load the hospital-triage scenario.
   Classify: high_risk via the real Annex III point 5 node, status
   potentially_applicable, judge line "not_applicable_deterministic"
   (the audience should hear: no model made this decision). Then flip a
   prohibition flag to unknown and re-run: missing_facts appears and the
   status drops to requires_human_review; the system refuses to guess.
   Fallback: m3-demo-classification.png.
3. Requirements (1 min): load requirements: 339 judge-accepted norms in 27
   article groups, each row a deontic decomposition with its span chip; the
   41-item review queue is disclosed, not hidden.
4. Evidence (2 min, PAID, one call pair): expand the Article 9(1) risk
   management norm, paste the two-sentence synthetic risk plan, evaluate.
   Read the verdict card aloud: partially_satisfied, the surviving verbatim
   quotes, the gaps, and the judge rationale explicitly preserving the
   "in relation to high-risk AI systems" condition as a gap. This is the
   evidence-gated loop in one screen.
   Fallback: m3-demo-evidence-verdict.png.
5. Close (1 min): the notice at the bottom (engineering support, not
   compliance certification), and the audit trail: every model call in
   data/review_queue/*.jsonl, every decision id in docs/traceability.md.

## Questions to expect

- "What if the judge is wrong?": FA/FR measurement protocol
  (eval/gold/ANNOTATION_PROTOCOL.md), review queue, calibrated vocabulary.
- "Why not just ask GPT?": the ablation table: 24/32 free-text accuracy with
  ZERO checkable citations vs 18/32 + 4 honest abstentions with 0.38
  citation completeness (eval/results/RUN2_ANALYSIS.md).
- "Is this legal advice?": no; Section 0 caveat, enforced in the vocabulary
  (no compliant/certified anywhere) and tested (no_compliance_claim tests).

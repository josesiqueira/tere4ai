# Demo crib sheet: RE/SE audience, demo-only session

> One page to keep open on a second screen while demoing. The script itself
> is docs/DEMO.md; this is what to say when the room asks questions instead
> of watching a linear talk.
>
> Formatting rule: never use em dashes; never use en dashes as a sentence break.

## The frame, in one sentence

TERE4AI answers EU AI Act questions with evidence rather than opinions: a
deterministic parser mirrors the frozen legal text, language models only
propose norms, mappings, and facts, independent judges gate every proposal,
and a fixed rule ladder alone assigns the risk tier. No model can override
the rules, which is why the same input always gives the same answer.

## Where everything lives

| Ask | Click |
|---|---|
| Structural coverage, judged counts, review queue | `/` |
| Any risk tier, rule trace, FRIA | `/assess`, preset buttons, Classify |
| Requirements with citations and HLEG chips | `/assess`, Load requirements |
| Traceability as a picture, verbatim spans | expand an article, Show evidence graph, click a node |
| Pipeline and where the three judges sit | `/how-it-works` |
| The disclosed human queue | `/review` |
| The envelope an MCP client receives | `/agent` |

## Numbers you can stand behind

Live, from the running build (`build-3b753e5e9297`, chain `4a98820a5915`):
113 articles, 180 recitals, 13 annexes, 339 judge-accepted norms, 475
accepted HLEG alignments, and 288 items awaiting a human (41 norms, 145
alignments, 102 cross-references). CredScore yields 277 requirements across
23 articles.

Ablation, 486 items, config of record gpt-5.2 generator and claude-opus-4-8
judges, run 2026-07-10/11 (eval/results/FULL_RUN_ANALYSIS.md):

| Strategy | Classified of 339 | Abstained | Selective acc | Citation completeness |
|---|---|---|---|---|
| plain_llm | 207 | 47 | 0.714 | 0.00, zero checkable |
| vector_rag | 206 | 69 | 0.766 | 0.06 |
| graph (all three) | 144 | 31 | 0.476 | 0.45 |

Hallucinated citations: at most 1 in roughly 4,380 checked per condition
(graph_build_judge 1/4,376, the other two 0), so the claim is "at most one,
caught by the checker", never "exactly zero".

Repeat-run variance (docs/variance_study.md): graph 0/345 label flips,
citation Jaccard 0.953 to 0.966; plain_llm 43/345 (0.125); vector_rag 51/345
(0.148).

## Claim discipline (say it this way, not that way)

- NEVER quote plain_llm's higher label count without its zero checkable
  citations in the same breath. The graph scores lower on raw labels
  precisely because it abstains and cites.
- The headline is judge false-accept/false-reject and calibrated reliance,
  never "accurate compliance".
- The ablation predates the D1/D2 safe-abstention change. Of 32 sampled
  items, 10 shifted from a confident "prohibited" to an abstention, so the
  current build abstains MORE than the table shows. The paid re-run is
  tracked as B20. Say this before someone finds it.
- EU to HLEG mappings are LLM-generated and not expert-validated. The UI
  says so under every chips row; say it out loud too.
- The tool supports engineering and documentation. It does not certify
  compliance and does not replace legal review.

## Questions this audience asks

**"How do you know the extracted norms are right?"** They are judged, and the
judging is disclosed: 442 candidates became 339 accepted, 54 rejected, 41
sent to human review. Show `/review`: those 41 are excluded from every
runtime answer until a person adjudicates them. Negative controls hold too
(Article 3 definitions rejected, Annex IV yields zero norms).

**"What is your baseline?"** The ablation table above. Lead with the variance
study, because label accuracy invites a taxonomy argument while 0 flips
versus 43 flips does not.

**"Is this not just a rule engine plus retrieval?"** For the decision, yes,
deliberately. That is the contribution, not an omission. The model proposes
facts and mappings, the judges gate them, and the ladder decides alone.
Show the rule trace on any preset: that line is the entire decision.

**"What happens when the model is wrong?"** Three containments: it cannot
touch the classification at all; its proposals are judge-gated; and unknown
facts lower the status rather than being coerced to false. Demo the
driver-fatigue variant.

**"Is it reproducible?"** 0/345 label flips across repeat runs, frozen
checksummed snapshots, a publication chain id shown on the coverage page,
and a config of record that gates live runs.

**"How complete are the citations?"** 0.45 at article level. Do not round it
up. The point is that it is measurable and checkable at all, which the
0.00 column is not.

**"Where does it fail?"** Be first to say it. The dominant error cell is 88
of 100 gold minimal items predicted transparency_only, which is a label
taxonomy disagreement (the elicited facts say it talks to people, so the
ladder asserts Article 50 duties while the benchmark labels overall risk as
minimal). Then prohibited/high_risk boundary confusion (22 and 16 items) and
transparency_only recall of 0.34.

**"What does the Act changing do to this?"** The Digital Omnibus is tracked
as adopted_not_yet_applicable, and answers carry legal status notes; the
FRIA block names 2027-12-02 for standalone Annex III obligations.

**"Can I try my own system?"** Yes. Either set the facts by hand, or paste a
description and elicit. Expect an abstention: prose rarely settles 34
closed-world facts, and saying so before you click turns the abstention into
the point.

## If something breaks

Servers: facade `TERE4AI_DEMO_SESSIONS_DIR=tests/fixtures/demo_sessions
.venv/bin/python -m uvicorn --factory tere4ai.http_facade.app:create_app
--port 8008`, then `cd web && npm run dev -- --port 3111`. Never run
`npm run build` while the dev server is running.

Paid buttons (Elicit, Generate backlog, Evaluate evidence) need keys in
.env. Without them they show an honest "needs model API keys" notice, which
is a fine thing to be seen. Every classification, requirement, citation, and
span works with no keys at all.

Every step of docs/DEMO.md names a screenshot fallback under
docs/screenshots/, and all of them exist.

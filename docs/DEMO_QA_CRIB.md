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
| The envelope an MCP client receives, all four tiers | `/agent`, pick a session, step with the arrows |
| Which obligations have nothing behind them | `trace_implementation` over MCP plus the client-side scanner (not a web click; run from the consumer project) |

## Numbers you can stand behind

Live, from the running build (`build-3b753e5e9297`, chain `4a98820a5915`):
113 articles, 180 recitals, 13 annexes, 339 judge-accepted norms, 475
accepted HLEG alignments, and 288 items awaiting a human (41 norms, 145
alignments, 102 cross-references). CredScore yields 277 requirements across
23 articles.

Trace numbers, verified live over stdio: ShopBot has 13 applicable norms, 1
traced (chat.py), 12 untraced, and 1 tag rejected because the Article 50(1)
disclosure norm sits in the human review queue. That rejection is the
review-queue exclusion guarantee working end to end.

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

## Per-tier beat notes

**High-risk beat closing line.** "The same traceability matrix runs here: 277
rows, every one untraced today, which is the honest size of the project you
just discovered."

**Minimal-risk beat.** Zero requirements means zero from the v2 high-risk
core; Article 4 AI literacy and the general provisions sit outside the
deterministic check, and the server's own message says so. The abstention
flip is worth showing on purpose: omit one under-supported fact and the
ladder returns requires_human_review at 0.5, naming the missing facts.

**Prohibited beat.** Never promise "violated principles": the payload carries
the prohibition citation and message only (B34a). Strongest line: "Every
system today got a backlog. This one gets zero, and zero is the answer."

## The replay page, if the MCP claim gets pressed

`/agent` serves four recorded sessions, one per tier, each recorded by
driving the real MCP server over stdio as an external client. Two exchanges
each: classify, then requirements. The counts match what the assess page
produces live (ShopBot 13, CredScore 277, MoodWatch 0), and a test replays
every recorded session against the current build, so a drifted fixture fails
CI rather than misleading a room. Say that: the page is not a video, it is a
transcript that is re-verified on every test run.

Stronger card now: the live skeletons at demo-systems/ and the free trace
tool beat the replay page as the answer when this claim gets pressed; drive
one skeleton live over stdio if the room wants proof. Replay remains the
fallback.

## Showing the graph in Neo4j Browser

Open **http://localhost:7475**. Not 7474: that port belongs to the legacy v1
container still running on this machine, and it holds a different graph.
Inside the browser, connect URL `bolt://localhost:7688`, user `neo4j`,
password `NEO4J_PASSWORD` from .env. The container is `tere4ai2_neo4j`
(`docker compose up -d neo4j` if it is not running).

Loaded: 4,694 nodes. 113 Article, 180 Recital, 217 AnnexItem, 519 Paragraph,
467 Point, 434 NormativeStatement, 620 AlignmentAssertion, 1,078 JudgeRun,
426 CrossReference. The verdict counts match the UI exactly: 339 accepted
norms, 54 rejected, 41 needing human review; 475 accepted alignments, 145
rejected. Showing the same numbers in the store and in the web UI is worth
doing deliberately.

Ten demo queries, all executed and verified against this instance, are in
`_queries.cypher` at the repo root (gitignored, local only). Query 3 is the
one to project: it draws Article 9 down to its derived norms as a graph.
Query 5 shows a reified alignment with the judge's five scores, which is the
answer to "how do you know the mapping is any good". Query 7 shows the review
queue existing in the store, not just in the UI.

Trap worth knowing: `Article.number` is an **int**, not a string, so a
quoted value silently returns zero rows rather than erroring. Norms hang off
both Paragraph and Point nodes, so a paragraph-only pattern misses some.

Honesty point if asked whether that store is what the demo serves: the demo
facade reads the frozen JSON dumps, and Neo4j was loaded from those same
dumps, which is why every count matches. But the store holds no BuildRun
node, so it cannot show you its own build id next to the
`build-3b753e5e9297` the facade reports. The correspondence is by
construction and by matching counts, not by a checksum you can point at in
the browser. Say that rather than implying a verification that is not there.

Do not republish the graph before the demo: the saved fallback artifacts
carry graph_version build-3b753e5e9297 and must keep matching the live
server.

## If something breaks

Servers, in two terminals from the repo root:

```
TERE4AI_DEMO_SESSIONS_DIR=tests/fixtures/demo_sessions .venv/bin/python -m uvicorn --factory tere4ai.http_facade.app:create_app --port 8008
cd web && npm run build && npm run start -- --port 3111
```

Use the production build for a live room, not `npm run dev`. Dev mode
compiles each route on first visit, so the first click to a page stalls for
seconds in front of the audience, and it paints a Next.js dev-tools badge in
the corner of the projected screen. The production build serves every page in
under 15 ms with no badge. Never run `npm run build` while a dev server is
running on the same directory: it clobbers `.next` and the running server
starts 404ing its own assets.

Theme: the UI follows the operating system via `prefers-color-scheme` and has
no in-app toggle, so set the OS to light or dark BEFORE presenting. Both
render correctly, including the evidence graph, but you cannot switch once
you are on stage.

Paid buttons (Elicit, Generate backlog, Evaluate evidence) need keys in
.env. Without them they show an honest "needs model API keys" notice, which
is a fine thing to be seen. Every classification, requirement, citation, and
span works with no keys at all.

The backlog beat no longer depends on network: the saved artifact (a 30.6 s
run, judge accepted, 6 controls from 10 Article 9 norms) is the plan of
record, and live generation is the encore. If the artifact's sharpest audit
question comes up: control 2's description spans Article 9(2)(a) and (b)
content while citing only the 9(2)(a) norm, because the 9(2)(b) extraction is
build-time rejected and thus outside the closed input set, which the judge
endorsed.

Every step of docs/DEMO.md names a screenshot fallback under
docs/screenshots/, and all of them exist.

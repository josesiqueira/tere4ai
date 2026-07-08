# Gold Set Annotation Protocol (M4)

Implements the hand-built gold set of docs/architecture.md Section 12.
Formatting rule: never use em dashes, and never use en dashes as a sentence
break.

## Target

- 60 to 80 items in total, all on the v2 high-risk core (Section 10 scope:
  Articles 3, 5, 6 to 7 plus Annex III, 8 to 15 plus Annex IV, 16 to 27,
  50, 72 to 73, plus the seven HLEG requirements).
- The 10 items in `gold_seed.json` are the seed; they were authored by one
  annotator ("seed") and verified mechanically (every cited node id exists
  in the published Layer 1 dump; every classification item agrees with the
  deterministic classifier). They still need the second-annotator pass
  below before any agreement statistic is reported.

## Item kinds and label definitions

Every item carries: `id`, `kind`, the task input, `gold`, `gold_citations`
(node ids that MUST exist in `data/graph_dumps/layer1.json`), `author`,
`second_annotator` (null until annotated).

1. `classification`: input is a structured `system_features` object
   (schema/json_schemas/system_features.schema.json). Gold label is
   `risk_category`, one of the closed set: `prohibited`, `high_risk`,
   `transparency_only`, `minimal_or_none`, `uncertain`. Rules:
   - `uncertain` is the correct label whenever a prohibition-relevant fact
     is unknown and could change the outcome; annotators never assume an
     absent flag is false.
   - Article 6(3) derogation candidates stay `high_risk` with
     `article_6_3_exception_candidate: true`; the derogation is never
     applied by annotation.
   - `gold_citations` are the operative nodes that justify the label (an
     Article 5 point, an Annex III item plus Article 6(2), an Article 50
     paragraph). `minimal_or_none` and `uncertain` items have an empty
     list and are excluded from citation completeness.
2. `retrieval`: input is a `question` asking which provision covers a
   described situation. Gold is the single most precise node id (for
   example the AnnexItem `eu-ai-act:annex-iii:point-5:a`, not its parent).
   A coarser ancestor may be recorded in the item note as acceptable, but
   the gold id is the precise one.
3. `qa`: input is a `question` answerable from the operative article text
   alone (never from a recital and never from outside knowledge). Gold is
   `answer_text` written from the source text, plus the article node id as
   the gold citation.

## Second annotator and agreement

- A second annotator independently labels a randomly selected 20 to 30
  percent subset (at 60 to 80 items: 15 to 24 items), stratified by kind.
  Selection is by seeded random draw over item ids so it is reproducible;
  record the seed in this file when drawn.
- The second annotator sees the task input only, never the first
  annotator's gold or notes.
- Agreement is computed per kind and reported in the paper:
  - classification: Cohen's kappa over the five risk categories.
  - retrieval: exact node-id agreement rate (plus agreement at article
    level as a secondary number).
  - qa: citation agreement (exact node id) and answer agreement judged by
    a third pass discussion; free-text answers are reconciled, not scored
    by string match.
- Disagreements are resolved by discussion against the frozen source text;
  the resolution and rationale are recorded in the item's `note`. Items
  that stay contested are marked `contested: true` and excluded from
  headline metrics (reported separately).

## Judge false-accept / false-reject gold labels

The judge FA/FR metrics (metrics.judge_error_rates) need gold accept and
reject labels on JUDGED artifacts, which are norms and alignment
assertions, not the eval items above. Assignment:

- Sample judged NormativeStatements from the build artifact
  (`data/graph_dumps/norms_core.json`), stratified by judge verdict
  (accepted, rejected, needs_human_review) so both error directions are
  measurable.
- For each sampled norm the annotator reads the source span text and
  labels `accept` if ALL of the extraction-judge criteria hold
  (architecture.md Section 7): the span exists, the deontic type is
  supported by the text, the actor is explicit or a valid recorded
  inference, action and object are grounded, and conditions and
  exceptions are not dropped. Any single failure means `reject`.
- The annotator never sees the judge verdict while labelling.
- false accept: judge accepted, gold says reject. false reject: judge
  rejected, gold says accept. A judge `needs_human_review` verdict is an
  abstention: it is counted and reported but is neither FA nor FR,
  because routing to a human is the designed degradation path.
- The same second-annotator subset and agreement reporting apply to these
  labels.

# Gold Set Annotation Protocol (M4)

Implements the hand-built gold set of docs/architecture.md Section 12.
Formatting rule: never use em dashes, and never use en dashes as a sentence
break.

## Target

- 60 to 80 items in total, all on the v2 high-risk core (architecture.md
  Section 10: Articles 3, 4a, 5, 6 to 7 plus Annex III, 8 to 15 plus
  Annex IV, 16 to 27, 50, 72 to 73, plus the seven HLEG requirements;
  Article 4a joined the core with the Digital Omnibus, B132).
- The 10 items in `gold_seed.json` are the seed; they were authored by one
  annotator ("seed") and verified mechanically (every cited node id exists
  in the published Layer 1 dump). Their `gold` is that one annotator's
  label: they still need the two independent labels and the adjudication
  below before any of them enters the answer key.
- A label comes from the Act's text, never from TERE4AI: the classifier's
  answer, the extracted norms and every condition's output are what the
  ablation scores (spec G Section 10.4), so a label that had to agree with
  them would agree by construction with the system it scores. A case a
  careful reader labels high risk and the classifier limited risk is a
  finding, and it stays in the test set.

## Item kinds and label definitions

Every item carries: `id`, `kind`, the task input, `author` (who wrote the
case), `labels` (the two independent labels, each with `annotator`, `gold`,
`gold_citations` and `note`; empty until labelled), `adjudication` (null
when the two labels agree, otherwise the `adjudicator`, the chosen label
and the `rationale`), and `gold` and `gold_citations`, the reference the
harness scores against: the agreed label, or the adjudicated one. Every
cited node id MUST exist in `data/graph_dumps/layer1.json`.

1. `classification`: input is a structured `system_features` object
   (schema/json_schemas/system_features.schema.json). Gold label is
   `risk_category`, one of the closed set: `unacceptable_risk`, `high_risk`,
   `limited_risk`, `minimal_risk`, `undetermined`. Rules:
   - `undetermined` is the correct label whenever a prohibition-relevant fact
     is unknown and could change the outcome; annotators never assume an
     absent flag is false.
   - Article 6(3) derogation candidates stay `high_risk` with
     `article_6_3_exception_candidate: true`; the derogation is never
     applied by annotation.
   - `gold_citations` are the operative nodes that justify the label (an
     Article 5 point, an Annex III item plus Article 6(2), an Article 50
     paragraph). `minimal_risk` and `undetermined` items have an empty
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

## Two labels on every case, then adjudication

Spec G Section 10.4 (B104, decision 2) and Section 6, steps 4 and 5.

- Two annotators label every case independently. Each sees the task input
  only: never the other annotator's label, never the case writer's
  intended answer, never TERE4AI's answer or any condition's output.
- Agreement is computed per kind on the two independent labels, before
  any adjudication, and reported with a chance-corrected statistic beside
  the raw agreement, because raw agreement on its own cannot be compared
  across studies (ADD-59):
  - classification: Cohen's kappa over the five risk categories.
  - retrieval: exact node-id agreement rate (plus agreement at article
    level as a secondary number).
  - qa: citation agreement (exact node id); free-text answers are not
    scored by string match, and their differences go to adjudication.
- Disagreements are adjudicated by a person who did not produce the
  disagreeing labels, blind to who chose what, against the source text of
  the source baseline, with the rationale recorded in the item's `adjudication`. There is
  no discussion between the two annotators and no majority vote. Items
  the adjudicator cannot settle against the source text are marked
  `contested: true` and excluded from headline metrics (reported
  separately).
- Who the two annotators and the adjudicator are is decided in B77.O1
  (spec G D-G-open-1); spec G Section 10.5 lists the designs for each
  number of helpers and the claim and limitation of each. Until then the
  roles are undecided.

## Judge false-accept / false-reject gold labels

The judge FA/FR metrics (metrics.judge_error_rates) need gold accept and
reject labels on JUDGED artifacts, which are norms and alignment
assertions, not the eval items above. Assignment:

- Sample judged NormativeStatements from the build artifact
  (`data/graph_dumps/norms_core.json`), stratified by judge verdict
  (accepted, rejected, needs_human_review) so both error directions are
  measurable.
- Note (2026-10-07, B148): data/graph_dumps/norms_core.json is the July 2026
  dump; B74 writes its norms under its own record slug, and which file, sample
  and stratification E1 draws on the B74 build is card B150's.
- For each sampled norm the annotator reads the source span text and
  labels `accept` if ALL of the extraction-judge criteria hold
  (architecture.md Section 7): the span exists, the deontic type is
  supported by the text, the actor is explicit or a valid recorded
  inference, action and object are grounded, and conditions and
  exceptions are not dropped. Any single failure means `reject`. The
  requirement type, where the sheet shows it, is not one of these
  criteria and never decides `accept` or `reject` (DEC-19); the
  extraction judge's view of it is compared with the adjudicated human
  type apart, as judge type agreement. The norm's target_system_category
  is not a criterion either: a rule sets it from the norm's source Article
  or Annex (DEC-21), so sheets drawn since B124 do not show it, and where
  the 2026-07 sheet shows it, it decides nothing. Where the sheet shows the
  actor-inference source text, it is the text the judge received, there
  for the actor criterion.
- The annotator never sees the judge verdict while labelling.
- false accept: judge accepted, gold says reject. false reject: judge
  rejected, gold says accept. A judge `needs_human_review` verdict is an
  abstention: it is counted and reported but is neither FA nor FR,
  because routing to a human is the designed degradation path.
- These labels are E1's, made by the owner blind to the verdict (spec G
  Section 10.1); the two-label rule above binds the test set's cases, not
  these labels.

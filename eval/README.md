# eval/ : M4 Evaluation Harness

Evaluation assets for the M4 milestone (docs/architecture.md Sections 12
and 14, DEC-11). Code lives in `src/tere4ai/eval/` (harness.py,
strategies.py, metrics.py); this directory holds the config of record, the
gold data, and the results artifacts.

Formatting rule: never use em dashes, and never use en dashes as a
sentence break.

## Contents

- `config_evaluated.yaml`: the model configuration of record (DEC-07). A
  live eval run refuses to start unless the loaded model config matches
  this file exactly on generator and judge model.
- `gold/gold_seed.json`: 10 hand-authored seed items on the high-risk core
  (6 classification including the Article 6(3) candidate and the
  unknown-flags edge case, 2 retrieval, 2 QA). Every `gold_citations` id
  was verified to exist in `data/graph_dumps/layer1.json` and every
  classification item was verified against the deterministic
  `classify_ai_system` before the file was written.
- `gold/ANNOTATION_PROTOCOL.md`: how the seed grows to the 60 to 80 item
  gold set, the second-annotator procedure (20 to 30 percent subset,
  agreement statistic), and how judge FA/FR gold labels are assigned.
- `gold/benchmark_sample.json`: a frozen 47-item sample of the REF-15
  benchmark (see below), with full provenance.
- `results/`: results artifacts written by the harness. Names are
  deterministic (graph build id plus a digest of the strategy set), never
  timestamped, so a re-run of the same configuration overwrites the same
  file.

## REF-15 benchmark: FOUND and verified (2026-07-08)

The dataset behind "AI Act Evaluation Benchmark: An Open, Transparent, and
Reproducible Evaluation Dataset for NLP and RAG Systems" (arXiv:2603.09435,
Davvetas, Papademas, Ziouvelou, Karkaletsis) exists and is public:

- Repository: https://github.com/davidath/ai-act-evaluation-benchmark
- Files: `scenarios.json` (339 scenario items) and `qa_pairs.json`
  (137 QA items). Dataset license: CC BY 4.0 (scripts: Apache 2.0).
- Scenario item format: `role`, `intended_use`, `system_type`,
  `input_data`, `domain`, `related_articles` (article numbers),
  `obligations` (free-text list), `risk_level` (prohibited 70, high-risk
  86, limited 84, minimal 99).
- QA item format: `question`, `answer`, `relevant_article` (one number).

`gold/benchmark_sample.json` freezes a deterministic sample (first 8
scenarios per risk level in file order plus the first 15 QA pairs, 47
items) verbatim, with the source file sha256 checksums and retrieval date
in its `provenance` block. `harness.load_benchmark_items` parses this real
format. The references.md [VERIFY] tag on REF-15 can be considered
resolved for existence and format; the exact published metrics still need
checking against the paper before citation.

### Coverage against the high-risk core (measured over the full files)

Measured on the full 339 scenarios (`related_articles`) and 137 QA pairs,
not the sample:

- Well covered: Articles 5 (137 scenario refs), 6 (222), 9 to 15 (each 26
  to 149), 16 to 22, 26, 27 (109), 50 (242), 72 (70), 73 (72). QA pairs
  additionally touch Articles 3, 8 to 31 and others at 1 to 7 items each.
- Gaps relevant to us: Article 7 (Annex III amendment power) has ZERO
  references in either file; Articles 23 to 25 are nearly absent from
  scenarios. Citations are at ARTICLE granularity only: the benchmark
  never cites paragraphs, points, or annex items, so it cannot measure
  our sub-article citation precision; the hand-built gold set does that.
- Scenario descriptions are free text. Mapping them into our structured
  `system_features` schema is annotation work; the loader therefore keeps
  them as `system_text` with `system_features: null`, and the graph
  strategies honestly return `uncertain` for such items until the mapping
  is annotated. Do not let any code guess that mapping.

## The ablation ladder (Section 12)

Five conditions, uniform interface, in `src/tere4ai/eval/strategies.py`:

1. `plain_llm`: generator only; the prompt holds the question only.
2. `vector_rag`: naive in-process TF-IDF retrieval over Layer 1 node texts
   (paragraphs, points, annex items, recitals), top-k passages as context.
   This is deliberately the weak baseline. Practitioner write-ups report
   around 38 percent for vector-only RAG, but that figure is non-citable
   (the source was dropped from the register in the 2026-07 consolidation):
   we never quote it as evidence and run our own baseline instead.
3. `graph_no_judge`: deterministic classification plus norm context with
   the build judge IGNORED (accepted, rejected, and needs_human_review
   norms are all offered).
4. `graph_build_judge`: as 3, but only judge-accepted norms are offered.
5. `graph_full`: as 4, plus the runtime grounding judge gating every
   generated answer (unverifiable citations withheld, verdict attached,
   non-accepted answers degraded to requires_human_review).

Metrics (`src/tere4ai/eval/metrics.py`): risk classification accuracy,
citation completeness, hallucinated citation rate, judge false-accept and
false-reject rates, P/R/F1 helpers.

## Running offline (default, no model calls)

Offline is the default everywhere; no code path calls a model unless both
gates below are set. The CLI smoke run uses a clearly labelled offline
stub client whose output can never be mistaken for a model answer:

    .venv/bin/python -m tere4ai.eval.harness --strategies plain_llm,graph_build_judge

Unit tests inject `FakeClient` (scripted) and never touch a network:

    .venv/bin/python -m pytest tests/unit/test_eval_metrics.py tests/unit/test_eval_harness.py -q

## Running live (costs money)

A live run requires ALL of:

1. the explicit `--live` flag (or `run_eval(..., live=True)`),
2. the environment gate `TERE4AI_LIVE_TESTS=1`,
3. a fully configured `.env` (TERE4AI_GENERATOR_MODEL, TERE4AI_JUDGE_MODEL,
   OPENAI_API_KEY, ANTHROPIC_API_KEY), and
4. the loaded config matching `eval/config_evaluated.yaml` exactly on
   generator and judge model (DEC-07 config guard; the run raises
   EvalConfigMismatch otherwise and writes nothing).

    TERE4AI_LIVE_TESTS=1 .venv/bin/python -m tere4ai.eval.harness --live

Cost note: one full ladder over the 10 seed items is roughly 10 items x 5
strategies = 50 generator calls plus 10 runtime-judge calls; over the
benchmark sample add 47 x 5 more. Budget accordingly and prefer strategy
subsets while iterating.

## Honesty rules for this directory

- Never fabricate benchmark results, metrics, or dataset items. The
  benchmark sample is verbatim from the source repository, checksummed.
- Results artifacts record the exact models used; offline artifacts are
  labelled `"mode": "offline"` and contain stub or fake text only.
- The EU-to-HLEG mappings consumed anywhere in evaluation are
  LLM-generated and not expert-validated; surface that caveat when
  reporting.

## Run 2 findings (2026-07-09)

Elicited features (DEC-13) plus requirements-citation wiring changed the
ladder: graph strategies went from blanket abstention (0/32) to 18/32
correct on free-text scenarios with abstentions down to 4, and checkable
citation completeness rose from 0.02 to 0.38 while plain_llm still emits
zero checkable citations. Of the 14 remaining mismatches, 7 are
minimal-vs-Article-50 taxonomy disagreements (arguably our classifier is
the more Act-faithful reading), 4 are honest abstentions, 3 are real
over-classifications traced to elicited flags (see
results/ELICITATION_ERRORS.md once generated). Full analysis:
results/RUN2_ANALYSIS.md. Treat single-run deltas of a few items as within
provider variance until the repeat-run study (task 60) bounds it.

## Full-benchmark run findings (2026-07-10/11, task 27)

The full REF-15 run (all 339 scenarios + 137 QA pairs + 10 gold seed,
prompt v2 elicitation, 0 errors over 2,926 model calls) confirms the run-2
pattern at 10x scale: plain_llm 207/339 with zero checkable citations vs
the graph ladder 144/339 with 0.45 article-level citation completeness and
a measured 0.000 hallucinated-citation rate over ~4,380 emitted citations.
The dominant graph loss is one cell: 88 gold-minimal items predicted
transparency_only (the Article 50 taxonomy disagreement from run 2, now
the priority annotation set). Measured spend exceeded the dry-run
estimate: judge 9.63 USD vs the 5.33 USD quote (band exceeded; chars/4
under-counts legal text). Full analysis: results/FULL_RUN_ANALYSIS.md;
generated matrices: ../docs/ablation_deepdive_full.md; artifacts:
results/ablation_full_checkpoint.jsonl and ablation_full_summary.json.

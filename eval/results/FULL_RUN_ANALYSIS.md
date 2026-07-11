# Full-benchmark ablation analysis (task #27)

Date: 2026-07-10/11. Config of record: gpt-5.2 generator, claude-opus-4-8
judges (eval/config_evaluated.yaml). Items: 486 (10 gold seed + all 339
REF-15 scenarios + all 137 REF-15 QA pairs), payload built by
scripts/build_full_benchmark_payload.py from the sha256-verified frozen
files. Scenario features: machine-elicited with prompt v2, 339/339
succeeded, 0 failures (eval/gold/benchmark_features_full.json). Artifacts:
ablation_full_checkpoint.jsonl (245 units, 0 item errors),
ablation_full_summary.json, docs/ablation_deepdive_full.md (generated).
The run-2 sample artifacts (ablation_checkpoint.jsonl, prompt v1) are
untouched and remain the run-2 record.

## Headline (all numbers from ablation_full_summary.json and the deep-dive)

| Strategy | Seed cls | Benchmark cls (of 339) | Abstained | Selective acc | Article-level citation completeness | Hallucinated citations |
|---|---|---|---|---|---|---|
| plain_llm | 6/6 | 207 | 47 | 0.714 | 0.00 (zero checkable) | 0 emitted |
| vector_rag | 5/6 | 206 | 69 | 0.766 | 0.06 | 0.000 |
| graph_no_judge | 6/6 | 144 | 31 | 0.476 | 0.45 | 0.000 |
| graph_build_judge | 6/6 | 144 | 31 | 0.476 | 0.45 | 0.000 |
| graph_full | 6/6 | 144 | 31 | 0.476 | 0.45 | 0.000 |

The run-2 pattern holds at 10x scale: the plain LLM wins raw benchmark
accuracy but cites nothing checkable; the graph ladder answers with
citations whose article-level completeness is 0.45 and whose hallucination
rate is exactly zero across 4,372 to 4,392 emitted citations per condition.
The three graph conditions are identical on classification because the
deterministic ladder decides (DEC-13); the judges gate grounding, not the
risk label.

## Where the graph ladder loses accuracy (deep-dive matrices)

The single dominant error cell is gold minimal_or_none predicted as
transparency_only: 88 of the 100 minimal items. This is the same
label-taxonomy disagreement flagged in run 2 (RUN2_ANALYSIS.md): the
elicited facts say the system interacts with natural persons or generates
synthetic content, so the ladder asserts Article 50 transparency duties,
while the benchmark labels overall risk as minimal. Whether these are
errors or defensible readings is annotation work, not something this
report may decide; they are the priority set for the annotation protocol.

Removing that one cell from both sides for intuition only (not a reported
metric): the remaining graph accuracy would be 150/257 = 0.58 vs plain_llm
213/345 = 0.62. The real gaps to fix are prohibited/high_risk boundary
confusion (22 prohibited items predicted high_risk, 16 high_risk items
predicted prohibited) and transparency_only recall (0.34).

plain_llm shows the mirror-image weakness: transparency_only recall 0.12,
with 27 of 85 transparency items called minimal. The benchmark's
limited/minimal boundary is hard for every condition; it is where a human
annotation pass adds the most value.

## Measured spend vs the pre-run estimate (docs/benchmark_cost_estimate.md)

Provider-reported usage, summed over checkpoint units by the runner
(usage_provider_reported in ablation_full_summary.json):

| Role | Calls | Input tokens | Output tokens |
|---|---|---|---|
| generator (gpt-5.2), ladder only | 2,430 | 1,956,709 | 416,969 |
| judge (claude-opus-4-8) | 496 | 1,184,012 | 148,546 |

- Judge cost at the estimator's cached 5.00/25.00 USD per MTok: **9.63
  USD**, vs the estimate of 5.33 USD (band 4.00 to 6.67). The estimate's
  +/-25 percent band was exceeded: measured judge input was 1.67x and
  output 2.08x the dry-run figures. Plausible causes, stated as
  hypotheses: the chars/4 heuristic under-counts real tokenization of
  legal text, and full-benchmark answers (which the judge reads) ran
  longer than the run-2 sizes the estimate extrapolated from.
- Generator ladder tokens: 1,956,709 in / 416,969 out, vs the dry-run
  ladder-only figures (estimate minus its elicitation row) of 1,534,535
  in / 189,750 out; input landed just above the +25 percent band, output
  at 2.2x. Elicitation ran in a separate process started before usage
  tracking landed, so its spend is not provider-recorded here; the
  estimate put it at 210,602 in / 56,629 out (339 calls). gpt-5.2 pricing
  is not recorded in this repo; price via TERE4AI_PRICE_GPT52_IN/_OUT.
- Lesson recorded for future gates: treat chars/4 dry-run numbers as a
  floor, not a midpoint, and prefer a small live pilot (one batch per
  condition) to calibrate output sizes before quoting a band.

## Consequence for task #60 (repeat-run variance)

The variance study was not started under the original approval because
the measured cost exceeded that estimate. Jose approved the re-quoted
cost (about 9.6 USD judge side plus about 2.4M generator tokens per
repeat) on 2026-07-11 and the repeat ran the same day: measured judge
spend 9.74 USD (497 calls, 1,189,403 in / 151,682 out), generator 2,430
calls, 1,956,709 in / 412,358 out, 0 errors. Results:
docs/variance_study.md (generated) and ablation_variance_summary.json.
Headline: the graph conditions flipped 0 of 345 labels between runs
(deterministic classification empirically confirmed) with citation-set
Jaccard 0.95 to 0.97, while plain_llm flipped 43 of 345 (12.5 percent,
accuracy 0.617 to 0.652) and vector_rag 51 (14.8 percent). Single-run
LLM-baseline deltas of about a dozen items are therefore within
run-to-run noise, which bounds every cross-strategy comparison in this
file.

## Caveats

- Scenario features are machine-elicited (provenance llm_elicited, prompt
  v2); human-verified features per eval/gold/ANNOTATION_PROTOCOL.md
  supersede them.
- Provider-side nondeterminism at temperature 0 is now measured (#60,
  docs/variance_study.md): LLM-baseline flip rates of 12 to 15 percent
  mean few-item deltas (for example vector_rag 206 vs plain_llm 207)
  are noise, not differences; the graph conditions reproduce exactly.
- Benchmark citation gold is article-level obligation lists; 0.45 is
  completeness against those lists, not sub-article granularity.

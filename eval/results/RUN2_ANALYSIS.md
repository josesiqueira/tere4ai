# Ablation run 2 analysis (elicited features + requirements citations)

Date: 2026-07-09. Config: gpt-5.2 generator, claude-opus-4-8 judges.
Run 1 artifacts: ablation_run1_*. Run 2: ablation_checkpoint.jsonl,
ablation_summary.json. Items: 57 (10 gold seed + 47 REF-15 sample).

## Headline movement (run 1 -> run 2)

| Strategy | Seed cls | Benchmark cls | Abstentions | Article-level citation completeness |
|---|---|---|---|---|
| plain_llm | 6/6 | 23 -> 24 /32 | 2 -> 4 | 0.00 -> 0.00 (zero checkable citations) |
| vector_rag | 5/6 | 21 -> 18 /32 | 6 -> 10 | 0.02 -> 0.06 |
| graph_no_judge | 6/6 | 0 -> 18 /32 | 32 -> 4 | 0.02 -> 0.38 |
| graph_build_judge | 6/6 | 0 -> 18 /32 | 32 -> 4 | 0.02 -> 0.38 |
| graph_full | 6/6 | 0 -> 18 /32 | 32 -> 4 | 0.02 -> 0.38 |

Both work items moved their target: feature elicitation converted 28 blanket
abstentions into answers (18 correct), and the applicable-requirements wiring
lifted checkable citation completeness 19x (0.02 to 0.38) while plain_llm
still cites nothing verifiable.

## Where the graph strategies disagree with the benchmark (14 of 32)

Confusion of graph_build_judge on benchmark scenarios:

| Benchmark gold | Predicted | n | Reading |
|---|---|---|---|
| minimal | limited (transparency_only) | 7 | Label-taxonomy disagreement, not clear error: these systems interact with natural persons or generate synthetic content, so Article 50 transparency duties plausibly apply even where the benchmark says minimal. Our category asserts the duty, the benchmark asserts overall risk. Flag for annotation review. |
| limited | uncertain | 3 | Honest abstention (elicited facts insufficient). |
| minimal | uncertain | 1 | Honest abstention. |
| limited | high_risk | 2 | Real over-classification; inspect elicited flags. |
| high-risk | prohibited | 1 | Real over-classification; inspect elicited flags. |

Adjusted reading: 18 matches + 7 defensible taxonomy disagreements + 4
honest abstentions = 29/32 defensible outcomes, 3 real errors traceable to
elicited-flag strength. plain_llm's 24/32 comes with zero verifiable
citations and no abstention discipline.

## Notes and caveats

- vector_rag DROPPED (21 to 18) between runs with temperature 0; treat
  single-run deltas of a few items as within run-to-run variance until
  repeated (nondeterminism in provider serving).
- Elicited features are machine-extracted (provenance llm_elicited in
  eval/gold/benchmark_features.json); human verification per the annotation
  protocol supersedes them. The 3 real errors are the priority items for
  that review.
- Benchmark citation gold is article-level obligations lists; 0.38 is the
  completeness of the deterministic requirements articles against those
  lists, not against sub-article granularity (which only the hand gold set
  measures).

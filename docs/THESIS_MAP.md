# Thesis map: research questions to artifacts

Every claim in the writing phase starts from an artifact in this repo, never
from memory. Rows cite the generating command or file; numbers are never
hand-typed into the papers (task 59 generates the tables).

| Research question | Claim shape | Artifact / evidence | Status |
|---|---|---|---|
| RQ1 Can the Act be mirrored deterministically at citation granularity? | 113/180/13 articles/recitals/annexes, 467 points, 217 annex items, spans checksum-anchored | `python -m tere4ai.parse_legal_structure`; tests/integration/test_acceptance_m1.py, test_acceptance_formex.py; §13 gates in the build | DONE |
| RQ2 Does judging change what enters the graph? | 442 candidates -> 339 accepted / 54 rejected / 41 review (norms); 636 judge runs -> 620 published assertions: 475 accepted / 145 review (alignments); negative controls (Article 3 definitions rejected, Annex IV zero norms) | data/graph_dumps/norms_core.json, alignments_core.json; audit logs in data/review_queue/ | DONE (FA/FR labeling pending, tasks 25/56) |
| RQ3 Are the regenerated mappings semantically faithful? | Every v1-slice article's dominant HLEG target is the canonical one | tests/integration/test_v1_slice_regression.py; fixture tests/fixtures/v1_slice_expectations.json | DONE |
| RQ4 What does the judge ladder buy at runtime? | Full benchmark (486 items): plain LLM 207/339 labels with zero checkable citations vs graph 144/339 (31 abstentions) with 0.45 article-level citation completeness (1,581 to 1,583 of 3,487) and at most 1 hallucinated citation in ~4,380 checked per condition (vector RAG: 0.06 completeness); repeat-run variance: graph 0/345 label flips (citation Jaccard 0.95 to 0.97) vs plain LLM 43/345 and vector RAG 51/345 | eval/results/ablation_full_summary.json, FULL_RUN_ANALYSIS.md, docs/variance_study.md, docs/ablation_deepdive_full.md | Sweeps DONE (tasks 27 and 60 closed 2026-07-10/11); judge FA/FR labeling (task 25) remains |
| RQ5 Can facts-vs-decision be split for free text? | DEC-13: elicitation converts 28 abstentions into 18 correct + 4 abstentions with the deterministic ladder still deciding | eval/gold/benchmark_features.json (provenance llm_elicited); RUN2_ANALYSIS.md; DEC-13 in §16 | DONE (3 real errors under review, task 74) |
| RQ6 Does evidence evaluation hold against adversarial input? | Mechanical quote gate + runtime judge; injection lands requires_human_review | tests/unit/test_evidence.py injection cases; live verdict in docs/screenshots/m3-demo-evidence-verdict.png | DONE (corpus extension task 68) |
| RQ7 Is the whole chain reproducible? | Frozen checksummed sources; deterministic parses; config-of-record gating; generated traceability | data/snapshots/MANIFEST.json; eval/config_evaluated.yaml; docs/traceability.md (generated); CI stale-matrix check | DONE (task 48 tightens the chain) |

## Claim discipline reminders (Section 7)

- Headline metrics are judge false-accept/false-reject and calibrated
  reliance, never "accurate compliance".
- The 7 minimal-vs-Article-50 disagreements are reported as benchmark-label
  disagreement, not model accuracy.
- plain_llm's benchmark score is always reported WITH its zero checkable
  citations; never as a bare accuracy comparison.

## Paper mapping (architecture.md §14)

- Tool/method paper: RQ1-RQ3 + RQ6 artifacts, M1-M3 screenshots.
- Empirical ablation paper: RQ4-RQ5, after task 25 closes (tasks 27 and 60
  closed 2026-07-10/11).
- Integrative journal: all of the above plus the review-queue human loop.

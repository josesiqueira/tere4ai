# Thesis map: research questions to artifacts

Every claim in the writing phase starts from an artifact in this repo, never
from memory. Rows cite the generating command or file; numbers are never
hand-typed into the papers (task 59 generates the tables).

| Research question | Claim shape | Artifact / evidence | Status |
|---|---|---|---|
| RQ1 Can the Act be mirrored deterministically at citation granularity? | 113/180/13 articles/recitals/annexes, 467 points, 217 annex items, spans checksum-anchored | `python -m tere4ai.parse_legal_structure`; tests/integration/test_acceptance_m1.py, test_acceptance_formex.py; §13 gates in the build | DONE |
| RQ2 Does judging change what enters the graph? | 442 candidates -> 339 accepted / 54 rejected / 41 review (norms); 636 -> 475 / 145 (alignments); negative controls (Article 3 definitions rejected, Annex IV zero norms) | data/graph_dumps/norms_core.json, alignments_core.json; audit logs in data/review_queue/ | DONE (FA/FR labeling pending, tasks 25/56) |
| RQ3 Are the regenerated mappings semantically faithful? | Every v1-slice article's dominant HLEG target is the canonical one | tests/integration/test_v1_slice_regression.py; fixture tests/fixtures/v1_slice_expectations.json | DONE |
| RQ4 What does the judge ladder buy at runtime? | Ablation ladder: citations 0 (plain LLM) vs 0.38 completeness (graph); 29/32 defensible outcomes vs 24/32 unverifiable; abstention discipline | eval/results/ablation_run1_summary.json, ablation_summary.json, RUN2_ANALYSIS.md | 2 sweeps DONE (variance study task 60, full benchmark task 27 pending) |
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
- Empirical ablation paper: RQ4-RQ5, after tasks 25/27/60 close.
- Integrative journal: all of the above plus the review-queue human loop.

# Reference full text (local only)

Drop the full text of cited papers here so the agent can read and verify them
when a task needs it. Full-text files (`*.pdf`, `*.html`, `*.txt`) are
gitignored: many are paywalled or have redistribution limits (see OPEN-LICENSE
in @docs/architecture.md). This README and any hand-written notes are tracked.

## Naming convention

One file per reference, named by its register ID so it resolves against
@docs/references.md and the `@grounded_by: REF-xx` tags in code:

```
REF-10_TAIR.pdf
REF-11_Galli_obligations.pdf
REF-16_XTRAREG.pdf
```

The `REF-xx` prefix is what matters; the rest is a human-readable hint.

## Priority to provide (highest value first)

Peer-reviewed and paywalled (agent CANNOT fetch these on demand):
- REF-10 (TAIR, Springer), REF-11 (Galli, ScienceDirect),
  REF-12 (Lost in EU Regulation, ACM ICAIL), REF-22 (Hogan, ACM CSUR).

Carry a [VERIFY] tag (exact metrics/authors/venue must be confirmed):
- REF-11, REF-14 (Institutional Grammar primaries), REF-16 (XTRAREG; free
  orbilu PDF exists), REF-22, REF-25 (AIRO).

arXiv preprints (agent can WebFetch on demand, local copy optional for fidelity):
- REF-08, 09, 13, 15, 17, 18, 21, 24, 26, 27, 28, 29.

Web-stable OFF/STD/legal sources (skip; fetch on demand):
- REF-01 (already snapshotted), REF-03, 04, 05, 07, 31, 33.

## After adding files

Run graphify over this folder to index the papers so lookups are a query, not a
full-PDF read:

```
graphify data/refs
graphify query "what grounding accuracy does REF-16 report"
```

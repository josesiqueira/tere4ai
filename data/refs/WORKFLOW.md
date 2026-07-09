# Reference papers: token-efficient, citation-safe workflow

How to keep the full papers here without paying full-text token cost on every
lookup, and without ever letting a paraphrase become a thesis citation.

## The three tiers (cheapest and fuzziest first)

1. **graphify (the index).** A lossy, paraphrased map: which paper, which
   concept, how they connect. A `graphify query` over this folder costs about
   1.7k tokens versus roughly 123k to read the PDFs raw. Use it for recall and
   navigation only.
2. **Full text on disk (ground truth).** The `REF-xx_*.txt` sidecars (and the
   PDFs). Opened only for a verbatim quote or an exact metric, and only the
   relevant slice.
3. **rtk (compresses reaching tier 2).** `rtk rg "<phrase>" data/refs` returns
   grouped, line-anchored hits so you locate the one paragraph instead of
   full-reading. Note: rtk does NOT shrink a paper you read in full; its win is
   cheap search and precise pinpointing.

## The one hard rule (grounding safety)

The graph node label is an LLM paraphrase. The graph confirms `source_location`
for code but stores `null` for paper nodes, and it holds no verbatim text. So:

> The graph and the wiki may tell you WHERE a claim lives and ROUGHLY what it
> says. Any number, quote, or claim that enters the thesis or a `@grounded_by`
> justification MUST be pulled verbatim from the `REF-xx` full text. A graph
> paraphrase is never a citation.

This is exactly how the `[VERIFY]` tags in @docs/references.md get reconciled:
open the full text, confirm the metric, quote it.

## Source-version priority (peer review first)

Per @docs/references.md grounding bar and @USER.md: a research or empirical MUST
needs a PEER, STD, or OFF grounding. Preprints (PRE) may support but never be
sole grounding. Therefore, when acquiring a paper:

1. Get the **official published version** first (journal, conference
   proceedings). Name it `REF-xx_<hint>.pdf`.
2. If only a preprint (arXiv) is obtainable, download it but rename it
   `REF-xx_<hint>_PREPRINT.pdf` and note it in `MANIFEST.md` so it is never
   mistaken for the version of record.
3. If the published version is paywalled and undownloadable, record the DOI and
   venue in `MANIFEST.md` and flag that institutional access is needed. Do not
   silently substitute the preprint as if it were the published text.

## Adding a paper

1. Drop the PDF in this folder as `REF-xx_<hint>.pdf` (or `_PREPRINT.pdf`).
2. Run the helper (makes text sidecars, rebuilds the refs graph + wiki):
   ```
   bash scripts/refs_reindex.sh
   ```
3. Query instead of re-reading:
   ```
   graphify data/refs                       # (first time; helper does this)
   graphify query "what grounding accuracy does REF-16 report"
   rtk rg "grounding" data/refs/REF-16_XTRAREG.txt   # then quote the exact line
   ```

## Files here

- `REF-xx_*.pdf` / `.txt` / `.html`  gitignored (paywall + licensing).
- `MANIFEST.md`                        tracked: what was acquired, version status.
- `README.md`, `WORKFLOW.md`           tracked.

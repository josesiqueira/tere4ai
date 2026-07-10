# Reference full-text acquisition manifest

Updated 2026-07-10 after the version-of-record (VoR) upgrade pass. Full-text
files (*.pdf, *.txt) are gitignored; this manifest is tracked. Citations live in
@docs/references.md. What still needs a human download is in paywalled.md.
Naming rule: a _PREPRINT suffix means the file is an arXiv (or author) preprint,
never cite it as the version of record.

## Held: published version of record (26 papers)

REF-09 (CIKM 2024, ACM VoR), REF-10 (TAIR, Springer AI and Ethics 5:4463-4474,
OA), REF-16 (XTRAREG, IEEE RE 2025, orbilu OA; verbatim confirmed: generation
81.8% ACC / 85.7% PRT, grounding 68.2% ACC / 50% PRT), REF-21 (Scientific Data
13:936, CC BY), REF-22 (ACM CSUR 54(4):71; file is the open arXiv manifestation,
cite the CSUR DOI), REF-25 (AIRO, SSW/IOS 2022, CC BY via Zenodo),
SELF-01 (CEUR Vol-4208 doc-sym-short4), SELF-02 (CEUR Vol-3921 phd-paper1),
SELF-04 (CEUR Vol-4208 pt-short4),
ADD-03 (FAccT 2021, ACM OA), ADD-05 (FAccT 2022, ACM OA), ADD-07 (SEE 2020,
Springer CC BY), ADD-08 (JSS 182, CC BY via JYX self-archive), ADD-09 (FAccT
2020, ACM OA), ADD-10 (RE 2006; open NCSU TR-2006-6, same title), ADD-11 (TSE
2008, CMU author copy), ADD-12 (RE journal 2015, author copy), ADD-13 (RE 2018,
orbilu), ADD-14 (ICRE 1994, author copy), ADD-15 (FOSE 2014, author copy),
ADD-16 (NeurIPS 2023 proceedings PDF), ADD-17 (EMNLP 2023, ACL), ADD-18 (EMNLP
2023, ACL), ADD-19 (EACL 2024 Demo, ACL), ADD-24 (FAccT 2023, DORAS open copy),
ADD-26 (CEUR Vol-4085 paper14).

## Held: preprint, flagged _PREPRINT

- Preprint-only, no VoR found: REF-08, REF-13, REF-15, REF-17, REF-18, REF-24,
  REF-27, REF-29, SELF-03, ADD-25, ADD-27.
- ADD-06_PrinciplesAlone_PREPRINT.pdf is retained ONLY as the searchable text
  surrogate for the image-only Nature VoR (see below); cite the Nature DOI.

## Held: added by the user 2026-07-10 (published VoR)

- REF-11 (REF-11_ApproachingAIAct.pdf, Computer Law and Security Review 60
  (2026) 106230) and REF-12 (REF-12_LostInEURegulation.pdf, ICAIL 2025).
- ADD-02 (ADD-02_TrustInAutomation.pdf, Human Factors 2004). Image-only scan,
  no text layer: no .txt sidecar, quote from the PDF manually.
- ADD-04 (ADD-04_TrustFactors.pdf, Human Factors 2015, full text).
- ADD-06 (ADD-06_PrinciplesAlone.pdf, Nature MI 2019 VoR). Image-only; the
  arXiv preprint pair provides the searchable text.
- REF-26 (REF-26_LegalReqTranslation.pdf, IEEE RE 2025 VoR, DOI
  10.1109/RE63999.2025.00028 printed on page; preprint pair deleted).
- REF-14b (Ostrom book) held for background only; stays DROPPED from the
  citation register.

## Not held (see paywalled.md)

REF-14c only.

## Held elsewhere in the repo

REF-01 (EU AI Act) and ADD-01 (HLEG Ethics Guidelines 2019): data/snapshots/.

## Web-stable, no local PDF needed

REF-02, REF-03, REF-04, REF-05, REF-07, REF-23, REF-30, REF-31, REF-32, REF-33,
ADD-20 (PROV-O), ADD-21 (SHACL), ADD-22, ADD-23, ADD-28.

## Rebuild the search index after adding or replacing files

```
bash scripts/refs_reindex.sh
```

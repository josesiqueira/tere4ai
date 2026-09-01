# Digital Omnibus on AI: verified amendment inventory for Regulation (EU) 2024/1689

Generated 2026-09-02 for task B59.

- Source of truth: frozen snapshot `data/snapshots/digital_omnibus_ai_32026R1744_eurlex_html_2026-09-02.html` (Regulation (EU) 2026/1744, CELEX 32026R1744, ELI http://data.europa.eu/eli/reg/2026/1744/oj).
- sha256 (recomputed, matches `data/snapshots/MANIFEST.json`): `3af13427fe45ef448f22b8ee4f2ad16a3142ccc3a1995e78b0d422ce28cd4137`
- Method: HTML tags stripped and non-breaking spaces (U+00A0) normalised to plain spaces with a small Python extractor; the inventory was built from the extracted text. Every verbatim quote below was re-found by exact substring search in the NBSP-normalised extracted text; each fenced quote carries its verification result. Quotes keep their original characters (curly quotes, hyphens); none of the quoted passages contains an em dash.
- Purpose: an inventory for engineering use (graph overlay and classifier updates). It is not legal advice.

Structure: Article 1 of the Omnibus amends Regulation (EU) 2024/1689 in 43 numbered points. Articles 2 and 3 amend other regulations (out of scope, one line each at the end). Article 4 is entry into force.

Operation counts across the 43 points, counted at the lettered sub-operation level (a point without letters counts as one operation): 44 replacements, 25 insertions or additions, 3 deletions, 72 operations total.

## Article 3 definitions

- Point (4)(a): Article 3, point (14) replaced (the text says "amended as follows" and supplies full new wording). "Safety component" definition now adds a clarifying sentence: a component fulfils a safety function where its intended purpose is to prevent or mitigate risks to health and safety of persons or property. This narrows the reading that fed Article 6(1) classification.
- Point (4)(b): Article 3, points (14a) and (14b) inserted. New defined terms: "micro, small and medium-sized enterprise" or "SME" (per Recommendation 2003/361/EC) and "small mid-cap enterprise" or "SMC" (per Recommendation (EU) 2025/1099).
- Not touched: the definitions of "provider" (Article 3, point (3)) and "deployer" (Article 3, point (4)) are unchanged.

## Article 4 (and new Article 4a)

- Point (5): Article 4 replaced. AI literacy obligation softened: providers and deployers must "take measures to support" AI literacy, with an explicit sentence that no specific literacy level of any individual must be guaranteed; Commission and Member States must support compliance (practical examples on the single information platform); the Board adopts recommendations.
- Point (6): Article 4a inserted. New legal basis to exceptionally process special categories of personal data for bias detection and correction: paragraph 1 for providers of high-risk AI systems (conditions (a) to (f): necessity, re-use limits and pseudonymisation, access controls, no transfer to other parties, deletion once bias corrected, documented reasons); paragraph 2 extends the option to providers and deployers of other AI systems and models and deployers of high-risk systems, without creating any obligation to do bias correction.

## Article 5 prohibitions (special depth, full verbatim)

- Point (7)(a): in Article 5(1), first subparagraph, two new prohibition points (ba) and (bb) inserted.
- Point (7)(b): new interpretive paragraphs 1a and 1b inserted into Article 5.

New point (ba): prohibition of AI systems generating or manipulating non-consensual intimate material of identifiable persons.

```
(ba) the placing on the market, the putting into service or the use of an AI system that generates or manipulates realistic images, videos, audio or similar material of an identifiable natural person’s intimate parts, or of an identifiable natural person engaged in sexually explicit activities, without that person’s freely-given, specific, informed, unambiguous and explicit consent for that generation or manipulation;
```
Verification: exact match in normalised snapshot text, 1 hit (body text following the "(ba)" marker).

New point (bb): prohibition of AI systems generating or manipulating child sexual abuse material (by reference to Directive 2011/93/EU).

```
(bb) the placing on the market, the putting into service or the use of an AI system that generates or manipulates material or performance within the meaning of Article 2, points (c) and (e), of Directive 2011/93/EU, except where a “without right” defence applies under national law;
```
Verification: exact match in normalised snapshot text, 1 hit (body text following the "(bb)" marker).

New Article 5(1a), scoping when the two prohibitions bite for placing on the market or putting into service versus use:

```
1a. For the purposes of paragraph 1, first subparagraph, points (ba) and (bb):
(a) the placing on the market or putting into service of an AI system that generates or manipulates the material or performance referred to in paragraph 1, first subparagraph, point (ba) or (bb) is only prohibited where:
(i) that generation or manipulation is the intended purpose of the AI system; or
(ii) the system’s design, training, architecture, capabilities or user-facing functionalities make that generation or manipulation a reasonably foreseeable and reproducible outcome, without requiring significant technical modification, and the system does not have reasonable and adequate technical safety measures and other safeguards to reliably prevent that generation or manipulation, taking into account reasonably foreseeable misuse, and to correct observed or reported misuse;
(b) the use of an AI system that generates or manipulates the material or performance referred to in paragraph 1, first subparagraph, points (ba) and (bb) is only prohibited where the deployer uses the system for the purpose of generating or manipulating such material or performance.
```
Verification: each of the five text segments (intro, (a), (a)(i), (a)(ii), (b)) matched exactly in the normalised snapshot text, 1 hit each. The letter and roman markers on their own lines reflect the snapshot layout.

New Article 5(1b), carve-out on what counts as manipulation for point (ba):

```
1b. For the purposes of paragraph 1, first subparagraph, point (ba), an AI system that manipulates material in a way that does not increase the exposure of any depicted intimate parts or alter the nature of any depicted sexually explicit activities shall not constitute manipulation.
```
Verification: exact match in normalised snapshot text, 1 hit.

No existing Article 5(1) prohibition (points (a) to (h) as enacted) is reworded by the Omnibus; the only Article 5 changes are the insertions above. Note for the classifier: the expected two additions (non-consensual intimate material, child sexual abuse material) are confirmed against the text, and both carry the Article 5(1a)/(1b) scoping rules and a deferred application date (2 December 2026, see the application dates section).

## Article 6 and Annexes (high-risk classification)

- Point (8): in Article 6, paragraphs 1a, 1b and 1c inserted. 1a: AI systems solely used for non-safety related aspects of user assistance, performance optimisation, service efficiency, automation or convenience or quality control do not qualify as safety components. 1b: notwithstanding 1a, systems whose failure or malfunctioning would endanger health and safety do qualify. 1c: a product required to undergo third-party conformity assessment solely due to risks other than health and safety (for example radio spectrum or electromagnetic interference) does not fulfil the Article 6(1), point (b) condition. Net effect: narrows the population of Article 6(1) high-risk systems.
- Point (41)(a): Annex I, Section A, point 1 deleted (the Machinery Directive 2006/42/EC entry).
- Point (41)(b): Annex I, Section B, point 21 added (Regulation (EU) 2023/1230, the Machinery Regulation). Net effect of (41): machinery moves from Section A to Section B of Annex I, so machinery-embedded AI is governed via the sectoral machinery framework and only the limited provisions in Article 2(2) apply under the AI Act.
- Point (42): Annex VIII, Section B, points 7 and 9 deleted (registration information items removed).
- Point (43): new Annex XIV added: list of codes, categories and corresponding types of AI systems that scope the designation of notified bodies under Article 30 (product codes AIP, biometric codes AIB, technology codes AIH including generative AI and "Agentic AI").
- Annex III itself (the list of high-risk areas) is NOT amended by any point.

Related scope changes recorded under "Other": Article 2(2) replaced (Section B systems: only Article 6(1), Article 60a and Articles 102 to 112 apply) and new Article 2(13) (delegated acts may limit Articles 9 to 15 and 17 to 25 requirements where Section A legislation gives equivalent protection, to be adopted by 2 August 2027).

## Chapter III obligations (Articles 8 to 49)

- Point (9)(a): Article 10(1) replaced. Data governance quality criteria apply to systems that "make use of techniques involving the training of AI models" and now cross-reference Article 4a(1), and apply "whenever such data sets are used".
- Point (9)(b): Article 10(5) deleted (the old special-category-data provision, superseded by new Article 4a).
- Point (9)(c): Article 10(6) replaced. For non-training systems the data requirements (and Article 4a(1)) apply only to testing data sets.
- Point (10): Article 11(1), second subparagraph replaced. SMEs, start-ups and SMCs may provide Annex IV technical documentation in a simplified manner via a mandatory Commission form; notified bodies must accept the form.
- Point (11): Article 17(2) replaced. Quality management system implementation proportionate to organisation size, now naming SMEs, start-ups and SMCs.
- Point (12)(a): Article 25(2) replaced. When a new provider takes over under Article 25(1), the initial provider is no longer considered the provider; its cooperation duty is spelled out (technical documentation, known limitations and failure modes, targeted technical access), with the existing opt-out where the initial provider excluded high-risk conversion.
- Point (12)(b): Article 25(4), first subparagraph replaced. The written-agreement duty for third-party suppliers now covers AI systems, AI models, tools, services, components or processes and requires "reasonably expected" technical access based on the state of the art; free and open-source suppliers (other than GPAI models) stay excluded.
- Point (13)(a): Article 27(4) replaced. Fundamental rights impact assessment may cross-reference or incorporate the GDPR or Directive (EU) 2016/680 data protection impact assessment.
- Point (13)(b): Article 27(5) replaced. AI Office must provide a questionnaire template, including an automated tool, supporting those cross-references.
- Point (14): Article 28, paragraphs 8 and 9 added. Single application and unified assessment procedure for conformity assessment bodies seeking designation under both the AI Act and Section A Union harmonisation legislation.
- Point (15): Article 29(4) replaced. Notified bodies designated under other legislation may reuse documents and certificates; single application routed via the sectoral notifying authority; duty to keep documentation updated.
- Point (16): Article 30(2) replaced. Notification uses the new Annex XIV code list; Commission empowered to amend Annex XIV by delegated act.
- Point (17): Article 40(2), subparagraph added. Commission must request European standardisation deliverables enabling joint compliance and presumption of conformity across the AI Act and Annex I legislation.
- Point (18): Article 42, paragraph 3 added. Cyber Resilience Act (Regulation (EU) 2024/2847) compliance under its Article 12(1) gives deemed compliance with the AI Act Article 15 cybersecurity requirements.
- Point (19): Article 43(3) replaced. Conformity assessment for Section A products runs through the sectoral procedure; sectoral notified bodies may assess AI Act Section 2 requirements (with designation under the AI Act required by 28 January 2028); manufacturers keep self-assessment options where the sectoral law offers them with harmonised standards; systems covered by both Section A and Annex III follow the sectoral procedure.

## Article 50 transparency

- Point (20): Article 50(7) replaced. Only the codes-of-practice machinery changes: the Commission encourages Union-level codes of practice for detection, marking and labelling of artificially generated or manipulated content, assesses their adequacy taking utmost account of the Board's opinion under the Article 56(6) procedure, and may adopt an implementing act with common rules if a code is inadequate. The substantive transparency duties in Article 50(1) to (6) are not amended.
- Related transitional (point (39)(b), quoted in the application dates section): providers of synthetic-content generators placed on the market before 2 August 2026 get until 2 December 2026 to comply with Article 50(2).

## Governance, sandboxes, AI Office, enforcement

- Point (21): Article 56(6) replaced. Commission and Board monitoring of GPAI codes of practice; Commission publishes its adequacy assessment.
- Point (22)(a): Article 57(1), first subparagraph replaced. At least one national AI regulatory sandbox operational by 2 August 2027 (previously 2 August 2026); joint establishment allowed; Commission may provide technical support.
- Point (22)(b): Article 57(3) replaced. EDPS may (no longer only "may also") establish a sandbox for Union institutions.
- Point (22)(c): Article 57(3a) inserted. The AI Office may establish a Union-level sandbox for AI systems under Article 75(1), with priority access for SMEs, start-ups and SMCs.
- Point (22)(d): Article 57(5) replaced. Sandboxes described as controlled environments covering development, training, testing and validation, and may include supervised real-world testing; sandbox plan incorporates the Article 60 and 60a plans.
- Point (22)(e): Article 57(9), point (e) replaced. Market access facilitation now names SMEs, start-ups and SMCs.
- Point (22)(f): Article 57(10) replaced. Association of data protection and other competent authorities with sandbox operation, extended to authorities providing or supporting access to data.
- Point (22)(g): Article 57(14) replaced. Coordination now includes the AI Office alongside national authorities and the EDPS.
- Point (23)(a): Article 58(1), introductory part replaced. Commission adopts implementing acts (framed around avoiding fragmentation) on sandbox arrangements.
- Point (23)(b): Article 58(1), point (d) added. Implementing acts also cover sandbox governance, data protection authority involvement, and national and Union coordination.
- Point (24)(a): Article 60(1), first subparagraph replaced. Real-world testing outside sandboxes framed for Annex III systems and Section A products, without prejudice to Article 5 prohibitions.
- Point (24)(b): Article 60(2) replaced. Same scope extension (Annex III or Section A) for testing before placing on the market.
- Point (25): Article 60a inserted. Member States may allow real-world testing of high-risk AI in Section B products under national frameworks notified to the Commission, with mandatory testing plans, Article 60 safeguards applied mutatis mutandis, governance and accountability arrangements, and a high level of protection of health, safety and fundamental rights.
- Point (26): Article 63(1) replaced. Simplified quality management system elements now open to all SMEs including start-ups (no longer only microenterprises), unless they have partner or linked enterprises; Commission develops guidelines.
- Point (27): Article 64, paragraph 3 added. AI Office must be allocated adequate resources for its enforcement duties.
- Point (28): Article 69(2) replaced. Member States "may be required" to pay fees for scientific panel expert advice at Commission-equivalent rates.
- Point (29): Article 70(8) replaced. National guidance to SMEs, start-ups and SMCs, with consultation of authorities under other Union law where relevant.
- Point (30): Article 72(3) replaced. Post-market monitoring plan is part of Annex IV technical documentation; Commission adopts guidance including a template by 2 September 2027 (replacing the implementing-act-plus-template mechanism).
- Point (31)(a): Article 75 heading replaced ("Market surveillance and control of AI systems and mutual assistance").
- Point (31)(b): Article 75(1) replaced. The AI Office becomes exclusively competent for supervision and enforcement over: (a) AI systems built on GPAI models where model and system come from the same provider or undertaking (with carve-outs for Annex I products, Annex III point 2 systems, law enforcement, border and financial cases under Article 74(6), and administration of justice under Annex III point 8), and (b) AI systems constituting or integrated into designated very large online platforms or search engines under the DSA. Applies to providers, and to deployers only when they are the provider or in the same undertaking.
- Point (31)(c): Article 75, paragraphs 1a to 1e inserted. Serious incident reporting to the AI Office, mutual assistance duties, market surveillance assistance for actions touching public authority data, prior notification before restrictive decisions, and AI Office responsibility for third-party conformity assessments of the systems in its remit (performed via notified bodies, fees on the provider).
- Point (31)(d): Article 75, paragraph 2a inserted. Market surveillance authorities may refer suspected infringements to the AI Office, which must respond within four months.
- Point (32): Articles 75a, 75b, 75c and 75d inserted. 75a: AI Office investigation powers (information requests, remote and on-site inspections including sealing premises, judicial authorisation route, assistance by national authorities, external experts). 75b: binding commitments decisions. 75c: non-compliance decisions, fines under Article 99(3) to (7) applied mutatis mutandis, periodic penalty payments up to 5 percent of average daily income or worldwide daily turnover, unlimited Court of Justice jurisdiction, five-year limitation periods. 75d: rights of defence, access to file, publication of decisions.
- Point (33): Article 76(1), subparagraph added. For Article 60a testing, references to market surveillance authorities and to Article 60 are read as the Section B authority and Article 60a.
- Point (34)(a): Article 77 heading replaced ("Powers of authorities protecting fundamental rights and cooperation with market surveillance authorities").
- Point (34)(b): Article 77(1) replaced. Fundamental rights authorities request documentation from the market surveillance authority (no longer directly under this provision), in accessible language and machine-readable format.
- Point (34)(c): Article 77, paragraphs 1a and 1b inserted. The market surveillance authority must grant that access (requesting it from provider or deployer where necessary) and both sides owe mutual assistance and information exchange.
- Point (35): Article 95(4) replaced. Codes of conduct: attention to SMEs, start-ups and SMCs (adds the AI Office and SMCs).
- Point (36)(a): Article 96(1), point (a) replaced. Commission guidelines cover Articles 8 to 15, 25 and 26 (adds Article 25).
- Point (36)(b): Article 96(1), point (g) added. Guidelines on complementarity with Section A legislation (Articles 8(2), 9(10), 17(3)) to be published by 1 August 2027.
- Point (36)(c): Article 96(1), second subparagraph replaced. Board involvement; attention to SMEs, start-ups, SMCs, local public authorities and affected sectors.
- Point (37)(a): Article 97, paragraphs 2 and 3 replaced. Delegation of power extended to the new empowerments (Article 2(13) and Article 30(2), five years from 27 July 2026) and made revocable.
- Point (37)(b): Article 97(6) replaced. Objection procedure covers the new empowerments.
- Point (38)(a): Article 99(1) replaced. National penalty regimes may include warnings and non-monetary measures; Commission guidelines must be taken into account; SME, start-up and SMC viability considered.
- Point (38)(b): Article 99(4), point (da) inserted. Fines for infringing the Article 25(2) and (4) obligations of providers and operators.
- Point (38)(c): Article 99, paragraph 6a inserted. For SMCs, fines capped at the lower of the percentage or the fixed amount (extending the SME rule).

## Application dates and transitional provisions (special depth, full verbatim)

- Point (39)(a): Article 111(2) replaced. Legacy high-risk systems placed on the market before the Chapter III application date are covered only upon significant design changes, now expressly without prejudice to Article 5 as applied under Article 113, third paragraph, point (a); public-authority systems must comply by 2 August 2030.
- Point (39)(b): Article 111(4) added. Transitional Article 50(2) compliance date for pre-existing synthetic content generators:

```
4. Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video or text content, that have been placed on the market before 2 August 2026 shall take the necessary steps in order to comply with Article 50(2) by 2 December 2026.
```
Verification: exact match in normalised snapshot text, 1 hit.

- Point (40)(a): Article 113, third paragraph, point (a) replaced. The new Article 5 prohibitions apply from 2 December 2026:

```
(a) Chapters I and II shall apply from 2 February 2025, with the exception of Article 5(1), first subparagraph, points (ba) and (bb), and Article 5(1a) and (1b) which shall apply from 2 December 2026;
```
Verification: exact match in normalised snapshot text, 1 hit (body text following the "(a)" marker).

- Point (40)(b): Article 113, third paragraph, point (c) replaced. This is the operative postponement of the high-risk regime (previously 2 August 2026 for the Chapter III framework, subject to the enacted Article 113 scheme):

```
(c) Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply from:
(i) 2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III; and
(ii) 2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I;
```
Verification: the intro line and points (i) and (ii) each matched exactly in the normalised snapshot text, 1 hit each.

- Point (40)(c): Article 113, third paragraph, point (d) added:

```
(d) Articles 102 to 110 shall apply from 27 July 2026.
```
Verification: exact match in normalised snapshot text, 1 hit (body text following the "(d)" marker).

## Entry into force of the Omnibus itself (special depth, full verbatim)

Article 4 of Regulation (EU) 2026/1744 ("Entry into force and application"):

```
This Regulation shall enter into force on the third day following that of its publication in the Official Journal of the European Union.
```
Verification: exact match in normalised snapshot text, 1 hit. (In the raw HTML this sentence contains an internal `<span class="oj-italic">` around the Official Journal name, so the raw-HTML search matches only after tag stripping; all other quotes above also matched the raw NBSP-normalised HTML directly or after whitespace-run collapsing.)

The regulation was done at Strasbourg on 8 July 2026 and published in the OJ; there is no separate deferred application date in Article 4 itself. Deferred application of individual amendments is handled inside the amended Article 113 of the base act, quoted above.

## Explicit answers for classifier engineering

1. Does anything amend Article 6, Annex III's list of high-risk areas, or Annex I in ways that change which systems are high-risk, beyond the dates? Yes. Article 6 gains paragraphs 1a, 1b and 1c (point (8)) narrowing the safety-component route, the Article 3(14) safety-component definition is tightened (point (4)(a)), and Annex I moves machinery from Section A to Section B (point (41)), which removes machinery from the full Article 6(1) regime. Annex III's list of high-risk areas is untouched.
2. Does anything change Article 50 transparency duties? Only marginally. Article 50(7) is replaced (codes of practice adequacy assessment and a possible implementing act); the duties in Article 50(1) to (6) are unchanged. New Article 111(4) gives pre-2 August 2026 synthetic content generators until 2 December 2026 to comply with Article 50(2).
3. Does anything change who counts as provider or deployer (Article 3 definitions relevant to classification)? No. The provider and deployer definitions are untouched. Adjacent changes: Article 25(2) restates when the initial provider ceases to be the provider and adds cooperation duties, and the new SME and SMC definitions (points (14a), (14b)) drive proportionality reliefs, not role classification.

## Out of scope for this inventory

- Omnibus Article 2 amends Regulation (EU) 2018/1139 (civil aviation): seven points adding paragraphs to Articles 27, 31, 32, 36, 39, 50 and 53 so aviation delegated and implementing acts take the AI Act Chapter III, Section 2 requirements into account. Out of scope here.
- Omnibus Article 3 amends Regulation (EU) 2023/1230 (machinery): three points (Articles 8, 20 and 47) requiring delegated acts to mirror AI Act high-risk requirements in Annex III of the Machinery Regulation by 2 August 2028 and giving presumption of conformity via AI Act harmonised standards in the interim. Out of scope here.

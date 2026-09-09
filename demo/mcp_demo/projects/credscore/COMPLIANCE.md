# CredScore, EU AI Act obligation map

Generated from live TERE4AI MCP answers. Nothing below is legal advice; see the notice at the end, which is the server's own wording.

- graph version: `build-3b753e5e9297`
- classified at: 2026-08-25T06:37:33.299831+00:00
- requirements fetched at: 2026-08-25T06:37:33.355306+00:00

## Classification

- risk category: **high_risk**
- prohibited: False
- Annex III category: `eu-ai-act:annex-iii:point-5`
- envelope status: `potentially_applicable`, confidence 1.0
- Article 6(3) exception candidate: False

Rule trace returned by the server:

- rule high_risk: flag essential_services_access matches Annex III category 'essential private and public services' (eu-ai-act:annex-iii:point-5), high-risk under Article 6(2)

Cited nodes:

- `eu-ai-act:annex-iii:point-5`
- `eu-ai-act:article-6:paragraph-2`

## Article 27 fundamental rights impact assessment

- applicability: **applies**
- Article 27(1) trigger: creditworthiness_evaluation is true (evaluate the creditworthiness of natural persons or establish their credit score (Annex III point 5(b))); the FRIA obligation covers deployers of these systems regardless of deployer type
- the assessment must be performed 'Prior to deploying a high-risk AI system referred to in Article 6(2)' (Article 27(1))
- applies from 2027-12-02 (`adopted_not_yet_applicable`, source REF-02: Digital Omnibus on AI (COM(2025) 836); final Official Journal (OJ) citation pending)

## Scope of the backlog

- judge-accepted requirements in scope: **277**
- returned in this fetch: 277
- articles touched: 23
- norms still in the human review queue, never served: 36
- calibrated status carried by every row below: `applicable_missing_evidence`

That status is the honest one for a codebase that has submitted no artifacts. The obligation applies and no evidence has been offered for it yet. Nothing here says satisfied, compliant, or certified.

| article | accepted | in review queue |
| --- | ---: | ---: |
| article-8 | 4 | 0 |
| article-9 | 19 | 3 |
| article-10 | 20 | 5 |
| article-11 | 9 | 0 |
| article-12 | 6 | 0 |
| article-13 | 17 | 2 |
| article-14 | 14 | 5 |
| article-15 | 10 | 0 |
| article-16 | 25 | 1 |
| article-17 | 18 | 4 |
| article-18 | 7 | 0 |
| article-19 | 3 | 0 |
| article-20 | 5 | 0 |
| article-21 | 2 | 0 |
| article-22 | 11 | 2 |
| article-23 | 13 | 0 |
| article-24 | 12 | 0 |
| article-25 | 11 | 1 |
| article-26 | 26 | 5 |
| article-27 | 9 | 2 |
| article-50 | 13 | 1 |
| article-72 | 6 | 2 |
| article-73 | 17 | 3 |

## Obligations by article

### article-8 (4 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-8:paragraph-1:n1` | obligation | high-risk ai systems | shall | comply with | the requirements laid down in this Section | `span:008.001` |
| `norm:eu-ai-act:article-8:paragraph-1:n2` | obligation | unspecified_needs_review | shall | take into account | the risk management system referred to in Article 9 | `span:008.001` |
| `norm:eu-ai-act:article-8:paragraph-2:n1` | obligation | providers | shall | be responsible for ensuring | that their product is fully compliant with all applicable requirements under applicable Union harmonisation legislation | `span:008.002` |
| `norm:eu-ai-act:article-8:paragraph-2:n2` | permission | providers | shall | have a choice of integrating, as appropriate | the necessary testing and reporting processes, information and documentation they provide with regard to their product into documentation and procedures that already exist and are required under the Union harmonisation legislation listed in Section A of Annex I | `span:008.002` |

### article-9 (19 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-9:paragraph-1:n1` | obligation | provider | shall | be established, implemented, documented and maintained | a risk management system | `span:009.001` |
| `norm:eu-ai-act:article-9:paragraph-2:n2` | obligation | unspecified_needs_review | shall | comprise | the identification and analysis of the known and the reasonably foreseeable risks that the high-risk AI system can pose to health, safety or fundamental rights | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n4` | obligation | unspecified_needs_review | shall | comprise | the evaluation of other risks possibly arising, based on the analysis of data gathered from the post-market monitoring system referred to in Article 72 | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n5` | obligation | unspecified_needs_review | shall | comprise | the adoption of appropriate and targeted risk management measures designed to address the risks identified pursuant to point (a) | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-5:n1` | obligation | provider | shall | be such that the relevant residual risk associated with each hazard, as well as the overall residual risk of the high-risk AI systems is judged to be acceptable | the risk management measures referred to in paragraph 2, point (d) | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n2` | obligation | provider | shall | ensure elimination or reduction of risks identified and evaluated pursuant to paragraph 2 in as far as technically feasible through adequate design and development | risks identified and evaluated pursuant to paragraph 2 | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n3` | obligation | provider | shall | ensure implementation of adequate mitigation and control measures addressing risks that cannot be eliminated | adequate mitigation and control measures | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n4` | obligation | provider | shall | ensure provision of information required pursuant to Article 13 and, where appropriate, training | information required pursuant to Article 13 and, where appropriate, training to deployers | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n5` | obligation | provider | shall | give due consideration | the technical knowledge, experience, education, the training to be expected by the deployer, and the presumable context in which the system is intended to be used | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-6:n1` | obligation | provider | shall | be tested | high-risk AI systems | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-6:n2` | obligation | provider | shall | ensure | that high-risk AI systems perform consistently for their intended purpose | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-6:n3` | obligation | provider | shall | ensure | that high-risk AI systems are in compliance with the requirements set out in this Section | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-7:n1` | permission | unspecified_needs_review | may | include | testing in real-world conditions | `span:009.007` |
| `norm:eu-ai-act:article-9:paragraph-8:n1` | obligation | provider | shall | be performed | the testing of high-risk AI systems | `span:009.008` |
| `norm:eu-ai-act:article-9:paragraph-8:n2` | obligation | provider | shall | be carried out against | prior defined metrics and probabilistic thresholds that are appropriate to the intended purpose of the high-risk AI system | `span:009.008` |
| `norm:eu-ai-act:article-9:paragraph-9:n1` | obligation | providers | shall | give consideration to whether | in view of its intended purpose the high-risk AI system is likely to have an adverse impact on persons under the age of 18 and, as appropriate, other vulnerable groups | `span:009.009` |
| `norm:eu-ai-act:article-9:paragraph-10:n1` | permission | providers of high-risk ai systems that are subject to requirements regarding internal risk management processes under other relevant provisions of union law | may | be part of, or combined with | the risk management procedures established pursuant to that law | `span:009.010` |
| `norm:eu-ai-act:article-9:paragraph-5:point-a:n1` | obligation | provider | other_explicit | eliminate or reduce | risks identified and evaluated pursuant to paragraph 2 | `span:fmx:art_009.parag_005.np_a` |
| `norm:eu-ai-act:article-9:paragraph-5:point-b:n1` | obligation | provider | other_explicit | implement | adequate mitigation and control measures addressing risks that cannot be eliminated | `span:fmx:art_009.parag_005.np_b` |

### article-10 (20 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-10:paragraph-1:n1` | obligation | provider | shall | be developed on the basis of | training, validation and testing data sets that meet the quality criteria referred to in paragraphs 2 to 5 | `span:010.001` |
| `norm:eu-ai-act:article-10:paragraph-2:n1` | obligation | provider | shall | be subject to | data governance and management practices appropriate for the intended purpose of the high-risk AI system | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n8` | obligation | provider | shall | concern | appropriate measures to detect, prevent and mitigate possible biases identified according to point (f) | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n9` | obligation | provider | shall | concern | the identification of relevant data gaps or shortcomings that prevent compliance with this Regulation, and how those gaps and shortcomings can be addressed | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-3:n5` | obligation | unspecified_needs_review | shall | have | the appropriate statistical properties | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-5:n1` | permission | the providers of such systems | may | process | special categories of personal data | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n2` | obligation | provider | must | ensure | the bias detection and correction cannot be effectively fulfilled by processing other data, including synthetic or anonymised data | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n3` | obligation | provider | must | subject | the special categories of personal data to technical limitations on the re-use of the personal data, and state-of-the-art security and privacy-preserving measures, including pseudonymisation | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n4` | obligation | provider | must | subject | the special categories of personal data to measures to ensure that the personal data processed are secured, protected, subject to suitable safeguards, including strict controls and documentation of the access, to avoid misuse and ensure that only authorised persons have access to those personal data with appropriate confidentiality obligations | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n5` | prohibition | provider | other_explicit | transmit, transfer or otherwise allow to be accessed | the special categories of personal data by other parties | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n6` | obligation | provider | other_explicit | delete | the special categories of personal data | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-5:n7` | obligation | provider | must | include | the reasons why the processing of special categories of personal data was strictly necessary to detect and correct biases, and why that objective could not be achieved by processing other data | `span:010.005` |
| `norm:eu-ai-act:article-10:paragraph-6:n1` | exemption | unspecified_needs_review | other_explicit | apply | paragraphs 2 to 5 | `span:010.006` |
| `norm:eu-ai-act:article-10:paragraph-5:point-c:n2` | obligation | provider | other_explicit | ensure | that the personal data processed are protected | `span:fmx:art_010.parag_005.np_c` |
| `norm:eu-ai-act:article-10:paragraph-5:point-c:n3` | obligation | provider | other_explicit | ensure | that the personal data processed are subject to suitable safeguards, including strict controls and documentation of the access | `span:fmx:art_010.parag_005.np_c` |
| `norm:eu-ai-act:article-10:paragraph-5:point-c:n5` | obligation | provider | other_explicit | ensure | that only authorised persons have access to those personal data with appropriate confidentiality obligations | `span:fmx:art_010.parag_005.np_c` |
| `norm:eu-ai-act:article-10:paragraph-5:point-d:n1` | prohibition | unspecified_needs_review | other_explicit | transmit | the special categories of personal data | `span:fmx:art_010.parag_005.np_d` |
| `norm:eu-ai-act:article-10:paragraph-5:point-d:n2` | prohibition | unspecified_needs_review | other_explicit | transfer | the special categories of personal data | `span:fmx:art_010.parag_005.np_d` |
| `norm:eu-ai-act:article-10:paragraph-5:point-e:n1` | obligation | unspecified_needs_review | other_explicit | are deleted | the special categories of personal data | `span:fmx:art_010.parag_005.np_e` |
| `norm:eu-ai-act:article-10:paragraph-5:point-f:n1` | obligation | unspecified_needs_review | other_explicit | include | the reasons why the processing of special categories of personal data was strictly necessary to detect and correct biases, and why that objective could not be achieved by processing other data | `span:fmx:art_010.parag_005.np_f` |

### article-11 (9 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-11:paragraph-1:n1` | obligation | provider | shall | draw up | the technical documentation of a high-risk AI system | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n2` | obligation | provider | shall | keep up-to date | the technical documentation | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n3` | obligation | provider | shall | draw up | the technical documentation | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n4` | obligation | provider | shall | contain | at a minimum, the elements set out in Annex IV | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n5` | permission | smes, including start-ups | may | provide | the elements of the technical documentation specified in Annex IV in a simplified manner | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n6` | obligation | the commission | shall | establish | a simplified technical documentation form targeted at the needs of small and microenterprises | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n7` | obligation | an sme, including a start-up | shall | use | the form referred to in this paragraph | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n8` | obligation | notified bodies | shall | accept | the form | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-2:n1` | obligation | provider | shall | be drawn up | a single set of technical documentation containing all the information set out in paragraph 1, as well as the information required under those legal acts | `span:011.002` |

### article-12 (6 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-12:paragraph-1:n1` | obligation | high-risk ai systems | shall | technically allow for the automatic recording | events (logs) over the lifetime of the system | `span:012.001` |
| `norm:eu-ai-act:article-12:paragraph-2:n1` | obligation | unspecified_needs_review | shall | enable the recording | events relevant for (a) identifying situations that may result in the high-risk AI system presenting a risk within the meaning of Article 79(1) or in a substantial modification; (b) facilitating the post-market monitoring referred to in Article 72; and (c) monitoring the operation of high-risk AI systems referred to in Article 26(5) | `span:012.002` |
| `norm:eu-ai-act:article-12:paragraph-3:n1` | obligation | provider | shall | provide | logging capabilities that provide, at a minimum, recording of the period of each use of the system (start date and time and end date and time of each use) | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n2` | obligation | provider | shall | provide | logging capabilities that provide, at a minimum, the reference database against which input data has been checked by the system | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n3` | obligation | provider | shall | provide | logging capabilities that provide, at a minimum, the input data for which the search has led to a match | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n4` | obligation | provider | shall | provide | logging capabilities that provide, at a minimum, the identification of the natural persons involved in the verification of the results, as referred to in Article 14(5) | `span:012.003` |

### article-13 (17 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-13:paragraph-1:n1` | obligation | provider | shall | design and develop | high-risk AI systems in such a way as to ensure that their operation is sufficiently transparent | `span:013.001` |
| `norm:eu-ai-act:article-13:paragraph-1:n2` | obligation | provider | shall | ensure | an appropriate type and degree of transparency | `span:013.001` |
| `norm:eu-ai-act:article-13:paragraph-2:n1` | obligation | provider | shall | be accompanied | instructions for use in an appropriate digital format or otherwise | `span:013.002` |
| `norm:eu-ai-act:article-13:paragraph-3:n2` | obligation | unspecified_needs_review | shall | contain | the identity and the contact details of the provider and, where applicable, of its authorised representative | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n3` | obligation | unspecified_needs_review | shall | contain | the characteristics, capabilities and limitations of performance of the high-risk AI system | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n5` | obligation | unspecified_needs_review | shall | contain | the level of accuracy, including its metrics, robustness and cybersecurity referred to in Article 15 against which the high-risk AI system has been tested and validated and which can be expected, and any known and foreseeable circumstances that may have an impact on that expected level of accuracy, robustness and cybersecurity | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n7` | obligation | unspecified_needs_review | shall | contain | any known or foreseeable circumstance, related to the use of the high-risk AI system in accordance with its intended purpose or under conditions of reasonably foreseeable misuse, which may lead to risks to the health and safety or fundamental rights referred to in Article 9(2) | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n8` | obligation | unspecified_needs_review | shall | contain | the technical capabilities and characteristics of the high-risk AI system to provide information that is relevant to explain its output | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n9` | obligation | unspecified_needs_review | shall | contain | its performance regarding specific persons or groups of persons on which the system is intended to be used | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n10` | obligation | unspecified_needs_review | shall | contain | specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n11` | obligation | unspecified_needs_review | shall | contain | information to enable deployers to interpret the output of the high-risk AI system and use it appropriately | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n12` | obligation | unspecified_needs_review | shall | contain | the changes to the high-risk AI system and its performance which have been pre-determined by the provider at the moment of the initial conformity assessment, if any | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n13` | obligation | unspecified_needs_review | shall | contain | the human oversight measures referred to in Article 14, including the technical measures put in place to facilitate the interpretation of the outputs of the high-risk AI systems by the deployers | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n14` | obligation | unspecified_needs_review | shall | contain | the computational and hardware resources needed, the expected lifetime of the high-risk AI system and any necessary maintenance and care measures, including their frequency, to ensure the proper functioning of that AI system, including as regards software updates | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n15` | obligation | unspecified_needs_review | shall | contain | a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs in accordance with Article 12 | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:point-b:point-vi:n1` | obligation | provider | other_explicit | provide | when appropriate, specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used | `span:fmx:art_013.parag_003.np_b.np_vi` |
| `norm:eu-ai-act:article-13:paragraph-3:point-f:n1` | obligation | provider | other_explicit | provide | a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs in accordance with Article 12 | `span:fmx:art_013.parag_003.np_f` |

### article-14 (14 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-14:paragraph-1:n1` | obligation | provider | shall | be designed and developed | high-risk AI systems | `span:014.001` |
| `norm:eu-ai-act:article-14:paragraph-2:n1` | obligation | unspecified_needs_review | shall | aim to prevent or minimise | the risks to health, safety or fundamental rights | `span:014.002` |
| `norm:eu-ai-act:article-14:paragraph-3:n1` | obligation | unspecified_needs_review | shall | be commensurate | the oversight measures | `span:014.003` |
| `norm:eu-ai-act:article-14:paragraph-3:n2` | obligation | unspecified_needs_review | shall | be ensured | the oversight measures | `span:014.003` |
| `norm:eu-ai-act:article-14:paragraph-3:n4` | obligation | the provider | shall | identify | measures | `span:014.003` |
| `norm:eu-ai-act:article-14:paragraph-4:n1` | obligation | provider | shall | be provided | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled, as appropriate and proportionate, to properly understand the relevant capacities and limitations of the high-risk AI system and be able to duly monitor its operation, including in view of detecting and addressing anomalies, dysfunctions and unexpected performance | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n2` | obligation | provider | shall | be provided | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled, as appropriate and proportionate, to remain aware of the possible tendency of automatically relying or over-relying on the output produced by a high-risk AI system (automation bias), in particular for high-risk AI systems used to provide information or recommendations for decisions to be taken by natural persons | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n3` | obligation | provider | shall | be provided | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled, as appropriate and proportionate, to correctly interpret the high-risk AI system’s output, taking into account, for example, the interpretation tools and methods available | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n4` | obligation | provider | shall | be provided | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled, as appropriate and proportionate, to decide, in any particular situation, not to use the high-risk AI system or to otherwise disregard, override or reverse the output of the high-risk AI system | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n5` | obligation | provider | shall | be provided | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled, as appropriate and proportionate, to intervene in the operation of the high-risk AI system or interrupt the system through a ‘stop’ button or a similar procedure that allows the system to come to a halt in a safe state | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-5:n2` | prohibition | the deployer | other_explicit | take | any action or decision on the basis of the identification resulting from the system | `span:014.005` |
| `norm:eu-ai-act:article-14:paragraph-5:n3` | exemption | the requirement for a separate verification by at least two natural persons | shall_not | apply | to high-risk AI systems used for the purposes of law enforcement, migration, border control or asylum | `span:014.005` |
| `norm:eu-ai-act:article-14:paragraph-3:point-a:n1` | obligation | provider | other_explicit | identify and build | measures | `span:fmx:art_014.parag_003.np_a` |
| `norm:eu-ai-act:article-14:paragraph-4:point-b:n1` | obligation | unspecified_needs_review | other_explicit | remain aware | the possible tendency of automatically relying or over-relying on the output produced by a high-risk AI system (automation bias) | `span:fmx:art_014.parag_004.np_b` |

### article-15 (10 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-15:paragraph-1:n1` | obligation | provider | shall | be designed and developed | high-risk AI systems | `span:015.001` |
| `norm:eu-ai-act:article-15:paragraph-2:n1` | obligation | the commission | shall | encourage | the development of benchmarks and measurement methodologies | `span:015.002` |
| `norm:eu-ai-act:article-15:paragraph-3:n1` | obligation | provider | shall | be declared | the levels of accuracy and the relevant accuracy metrics of high-risk AI systems | `span:015.003` |
| `norm:eu-ai-act:article-15:paragraph-4:n1` | obligation | unspecified_needs_review | shall | be | as resilient as possible regarding errors, faults or inconsistencies that may occur within the system or the environment in which the system operates | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n2` | obligation | unspecified_needs_review | shall | be taken | technical and organisational measures | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n5` | obligation | unspecified_needs_review | shall | be developed | in such a way as to eliminate or reduce as far as possible the risk of possibly biased outputs influencing input for future operations (feedback loops) | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n6` | obligation | unspecified_needs_review | shall | be developed | in such a way as to ensure that any such feedback loops are duly addressed with appropriate mitigation measures | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-5:n1` | obligation | provider | shall | be resilient | against attempts by unauthorised third parties to alter their use, outputs or performance by exploiting system vulnerabilities | `span:015.005` |
| `norm:eu-ai-act:article-15:paragraph-5:n2` | obligation | provider | shall | be appropriate | the technical solutions aiming to ensure the cybersecurity of high-risk AI systems | `span:015.005` |
| `norm:eu-ai-act:article-15:paragraph-5:n3` | obligation | provider | shall | include | measures to prevent, detect, respond to, resolve and control for attacks trying to manipulate the training data set (data poisoning), or pre-trained components used in training (model poisoning), inputs designed to cause the AI model to make a mistake (adversarial examples or model evasion), confidentiality attacks or model flaws | `span:015.005` |

### article-16 (25 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-16:paragraph-1:n1` | obligation | providers of high-risk ai systems | shall | ensure | that their high-risk AI systems are compliant with the requirements set out in Section 2 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n2` | obligation | providers of high-risk ai systems | shall | indicate | on the high-risk AI system or, where that is not possible, on its packaging or its accompanying documentation, as applicable, their name, registered trade name or registered trade mark, the address at which they can be contacted | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n3` | obligation | providers of high-risk ai systems | shall | have | a quality management system in place which complies with Article 17 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n4` | obligation | providers of high-risk ai systems | shall | keep | the documentation referred to in Article 18 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n5` | obligation | providers of high-risk ai systems | shall | keep | the logs automatically generated by their high-risk AI systems as referred to in Article 19 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n6` | obligation | providers of high-risk ai systems | shall | ensure | that the high-risk AI system undergoes the relevant conformity assessment procedure as referred to in Article 43 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n7` | obligation | providers of high-risk ai systems | shall | draw up | an EU declaration of conformity in accordance with Article 47 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n8` | obligation | providers of high-risk ai systems | shall | affix | the CE marking to the high-risk AI system or, where that is not possible, on its packaging or its accompanying documentation, to indicate conformity with this Regulation, in accordance with Article 48 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n9` | obligation | providers of high-risk ai systems | shall | comply with | the registration obligations referred to in Article 49(1) | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n10` | obligation | providers of high-risk ai systems | shall | take | the necessary corrective actions | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n11` | obligation | providers of high-risk ai systems | shall | provide | information as required in Article 20 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n12` | obligation | providers of high-risk ai systems | shall | demonstrate | the conformity of the high-risk AI system with the requirements set out in Section 2 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n13` | obligation | providers of high-risk ai systems | shall | ensure | that the high-risk AI system complies with accessibility requirements in accordance with Directives (EU) 2016/2102 and (EU) 2019/882 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:point-a:n1` | obligation | provider | other_explicit | ensure | that their high-risk AI systems are compliant with the requirements set out in Section 2 | `span:fmx:art_016.np_a` |
| `norm:eu-ai-act:article-16:paragraph-1:point-b:n1` | obligation | provider | other_explicit | indicate | their name, registered trade name or registered trade mark, the address at which they can be contacted | `span:fmx:art_016.np_b` |
| `norm:eu-ai-act:article-16:paragraph-1:point-c:n1` | obligation | provider | other_explicit | have in place | a quality management system | `span:fmx:art_016.np_c` |
| `norm:eu-ai-act:article-16:paragraph-1:point-d:n1` | obligation | provider | other_explicit | keep | the documentation referred to in Article 18 | `span:fmx:art_016.np_d` |
| `norm:eu-ai-act:article-16:paragraph-1:point-e:n1` | obligation | provider | other_explicit | keep | the logs automatically generated by their high-risk AI systems | `span:fmx:art_016.np_e` |
| `norm:eu-ai-act:article-16:paragraph-1:point-f:n1` | obligation | provider | other_explicit | ensure | that the high-risk AI system undergoes the relevant conformity assessment procedure as referred to in Article 43 | `span:fmx:art_016.np_f` |
| `norm:eu-ai-act:article-16:paragraph-1:point-g:n1` | obligation | provider | other_explicit | draw up | an EU declaration of conformity | `span:fmx:art_016.np_g` |
| `norm:eu-ai-act:article-16:paragraph-1:point-i:n1` | obligation | provider | other_explicit | comply with | the registration obligations referred to in Article 49(1) | `span:fmx:art_016.np_i` |
| `norm:eu-ai-act:article-16:paragraph-1:point-j:n1` | obligation | provider | other_explicit | take | the necessary corrective actions | `span:fmx:art_016.np_j` |
| `norm:eu-ai-act:article-16:paragraph-1:point-j:n2` | obligation | provider | other_explicit | provide | information as required in Article 20 | `span:fmx:art_016.np_j` |
| `norm:eu-ai-act:article-16:paragraph-1:point-k:n1` | obligation | provider | other_explicit | demonstrate | the conformity of the high-risk AI system with the requirements set out in Section 2 | `span:fmx:art_016.np_k` |
| `norm:eu-ai-act:article-16:paragraph-1:point-l:n1` | obligation | provider | other_explicit | ensure | that the high-risk AI system complies with accessibility requirements | `span:fmx:art_016.np_l` |

### article-17 (18 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-17:paragraph-1:n1` | obligation | providers of high-risk ai systems | shall | put in place | a quality management system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n2` | obligation | that system | shall | be documented | in a systematic and orderly manner in the form of written policies, procedures and instructions | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n4` | obligation | that system | shall | include | techniques, procedures and systematic actions to be used for the design, design control and design verification of the high-risk AI system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n5` | obligation | that system | shall | include | techniques, procedures and systematic actions to be used for the development, quality control and quality assurance of the high-risk AI system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n6` | obligation | that system | shall | include | examination, test and validation procedures to be carried out before, during and after the development of the high-risk AI system, and the frequency with which they have to be carried out | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n9` | obligation | that system | shall | include | systems and procedures for data management, including data acquisition, data collection, data analysis, data labelling, data storage, data filtration, data mining, data aggregation, data retention and any other operation regarding the data | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n11` | obligation | that system | shall | include | the setting-up, implementation and maintenance of a post-market monitoring system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n12` | obligation | that system | shall | include | procedures related to the reporting of a serious incident | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n13` | obligation | that system | shall | include | the handling of communication with national competent authorities, other relevant authorities, including those providing or supporting the access to data, notified bodies, other operators, customers or other interested parties | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n14` | obligation | that system | shall | include | systems and procedures for record-keeping of all relevant documentation and information | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n15` | obligation | that system | shall | include | resource management, including security-of-supply related measures | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n16` | obligation | that system | shall | include | an accountability framework setting out the responsibilities of the management and other staff with regard to all the aspects listed in this paragraph | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-2:n1` | obligation | unspecified_needs_review | shall | be proportionate | the implementation of the aspects referred to in paragraph 1 | `span:017.002` |
| `norm:eu-ai-act:article-17:paragraph-2:n2` | obligation | providers | shall | respect | the degree of rigour and the level of protection required to ensure the compliance of their high-risk AI systems with this Regulation | `span:017.002` |
| `norm:eu-ai-act:article-17:paragraph-3:n1` | permission | providers of high-risk ai systems that are subject to obligations regarding quality management systems or an equivalent function under relevant sectoral union law | may | include | the aspects listed in paragraph 1 as part of the quality management systems pursuant to that law | `span:017.003` |
| `norm:eu-ai-act:article-17:paragraph-4:n1` | exemption | provider | shall | be deemed to be fulfilled by complying | the obligation to put in place a quality management system | `span:017.004` |
| `norm:eu-ai-act:article-17:paragraph-1:point-h:n1` | obligation | unspecified_needs_review | other_explicit | set up, implement and maintain | a post-market monitoring system | `span:fmx:art_017.parag_001.np_h` |
| `norm:eu-ai-act:article-17:paragraph-1:point-i:n1` | obligation | provider | other_explicit | establish and maintain | procedures related to the reporting of a serious incident | `span:fmx:art_017.parag_001.np_i` |

### article-18 (7 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-18:paragraph-1:n1` | obligation | the provider | shall | keep at the disposal | the technical documentation referred to in Article 11 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n2` | obligation | the provider | shall | keep at the disposal | the documentation concerning the quality management system referred to in Article 17 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n3` | obligation | the provider | shall | keep at the disposal | the documentation concerning the changes approved by notified bodies | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n4` | obligation | the provider | shall | keep at the disposal | the decisions and other documents issued by the notified bodies | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n5` | obligation | the provider | shall | keep at the disposal | the EU declaration of conformity referred to in Article 47 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-2:n1` | obligation | each member state | shall | determine | conditions under which the documentation referred to in paragraph 1 remains at the disposal of the national competent authorities for the period indicated in that paragraph | `span:018.002` |
| `norm:eu-ai-act:article-18:paragraph-3:n1` | obligation | providers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under union financial services law | shall | maintain | the technical documentation as part of the documentation kept under the relevant Union financial services law | `span:018.003` |

### article-19 (3 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-19:paragraph-1:n1` | obligation | providers of high-risk ai systems | shall | keep | the logs referred to in Article 12(1), automatically generated by their high-risk AI systems | `span:019.001` |
| `norm:eu-ai-act:article-19:paragraph-1:n2` | obligation | provider | shall | be kept | the logs | `span:019.001` |
| `norm:eu-ai-act:article-19:paragraph-2:n1` | obligation | providers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under union financial services law | shall | maintain | the logs automatically generated by their high-risk ai systems | `span:019.002` |

### article-20 (5 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-20:paragraph-1:n1` | obligation | providers of high-risk ai systems | shall | take | the necessary corrective actions to bring that system into conformity, to withdraw it, to disable it, or to recall it | `span:020.001` |
| `norm:eu-ai-act:article-20:paragraph-1:n2` | obligation | they | shall | inform | the distributors of the high-risk ai system concerned and, where applicable, the deployers, the authorised representative and importers | `span:020.001` |
| `norm:eu-ai-act:article-20:paragraph-2:n1` | obligation | the provider | shall | immediately investigate | the causes | `span:020.002` |
| `norm:eu-ai-act:article-20:paragraph-2:n2` | obligation | the provider | shall | inform | the market surveillance authorities competent for the high-risk AI system concerned | `span:020.002` |
| `norm:eu-ai-act:article-20:paragraph-2:n3` | obligation | the provider | shall | inform | the notified body that issued a certificate for that high-risk AI system in accordance with Article 44 | `span:020.002` |

### article-21 (2 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-21:paragraph-1:n1` | obligation | providers of high-risk ai systems | shall | provide | that authority all the information and documentation necessary to demonstrate the conformity of the high-risk ai system with the requirements set out in section 2 | `span:021.001` |
| `norm:eu-ai-act:article-21:paragraph-2:n1` | obligation | providers | shall | give | the requesting competent authority, as applicable, access to the automatically generated logs of the high-risk AI system referred to in Article 12(1) | `span:021.002` |

### article-22 (11 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-22:paragraph-1:n1` | obligation | providers established in third countries | shall | appoint | an authorised representative which is established in the Union | `span:022.001` |
| `norm:eu-ai-act:article-22:paragraph-2:n1` | obligation | the provider | shall | enable | its authorised representative to perform the tasks specified in the mandate received from the provider | `span:022.002` |
| `norm:eu-ai-act:article-22:paragraph-3:n1` | obligation | the authorised representative | shall | perform | the tasks specified in the mandate received from the provider | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n2` | obligation | it | shall | provide | a copy of the mandate to the market surveillance authorities | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n4` | obligation | the mandate | shall | empower | the authorised representative to be addressed, in addition to or instead of the provider, by the competent authorities, on all issues related to ensuring compliance with this Regulation | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-4:n1` | obligation | the authorised representative | shall | terminate | the mandate | `span:022.004` |
| `norm:eu-ai-act:article-22:paragraph-3:point-a:n1` | obligation | unspecified_needs_review | other_explicit | verify | that the EU declaration of conformity referred to in Article 47 and the technical documentation referred to in Article 11 have been drawn up and that an appropriate conformity assessment procedure has been carried out by the provider | `span:fmx:art_022.parag_003.np_a` |
| `norm:eu-ai-act:article-22:paragraph-3:point-b:n1` | obligation | authorised_representative | other_explicit | keep at the disposal | the contact details of the provider that appointed the authorised representative, a copy of the EU declaration of conformity referred to in Article 47, the technical documentation and, if applicable, the certificate issued by the notified body | `span:fmx:art_022.parag_003.np_b` |
| `norm:eu-ai-act:article-22:paragraph-3:point-c:n1` | obligation | unspecified_needs_review | other_explicit | provide | a competent authority, upon a reasoned request, with all the information and documentation, including that referred to in point (b) of this subparagraph, necessary to demonstrate the conformity of a high-risk AI system with the requirements set out in Section 2, including access to the logs, as referred to in Article 12(1), automatically generated by the high-risk AI system | `span:fmx:art_022.parag_003.np_c` |
| `norm:eu-ai-act:article-22:paragraph-3:point-d:n1` | obligation | authorised_representative | other_explicit | cooperate | with competent authorities in any action the latter take in relation to the high-risk AI system | `span:fmx:art_022.parag_003.np_d` |
| `norm:eu-ai-act:article-22:paragraph-3:point-e:n1` | obligation | authorised_representative | other_explicit | comply with | the registration obligations referred to in Article 49(1) | `span:fmx:art_022.parag_003.np_e` |

### article-23 (13 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-23:paragraph-1:n1` | obligation | importers | shall | ensure | that the system is in conformity with this Regulation | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n2` | obligation | importers | shall | verify | that the relevant conformity assessment procedure referred to in Article 43 has been carried out by the provider of the high-risk AI system | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n3` | obligation | importers | shall | verify | that the provider has drawn up the technical documentation in accordance with Article 11 and Annex IV | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n4` | obligation | importers | shall | verify | that the system bears the required CE marking and is accompanied by the EU declaration of conformity referred to in Article 47 and instructions for use | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n5` | obligation | importers | shall | verify | that the provider has appointed an authorised representative in accordance with Article 22(1) | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-2:n1` | prohibition | an importer | shall_not | place | the system on the market | `span:023.002` |
| `norm:eu-ai-act:article-23:paragraph-2:n2` | obligation | the importer | shall | inform | the provider of the system, the authorised representative and the market surveillance authorities | `span:023.002` |
| `norm:eu-ai-act:article-23:paragraph-3:n1` | obligation | importers | shall | indicate | their name, registered trade name or registered trade mark, and the address at which they can be contacted | `span:023.003` |
| `norm:eu-ai-act:article-23:paragraph-4:n1` | obligation | importers | shall | ensure | that, while a high-risk AI system is under their responsibility, storage or transport conditions, where applicable, do not jeopardise its compliance with the requirements set out in Section 2 | `span:023.004` |
| `norm:eu-ai-act:article-23:paragraph-5:n1` | obligation | importers | shall | keep | a copy of the certificate issued by the notified body, where applicable, of the instructions for use, and of the EU declaration of conformity referred to in Article 47 | `span:023.005` |
| `norm:eu-ai-act:article-23:paragraph-6:n1` | obligation | importers | shall | provide | the relevant competent authorities with all the necessary information and documentation, including that referred to in paragraph 5, to demonstrate the conformity of a high-risk ai system with the requirements set out in section 2 in a language which can be easily understood by them | `span:023.006` |
| `norm:eu-ai-act:article-23:paragraph-6:n2` | obligation | they | shall | ensure | that the technical documentation can be made available to those authorities | `span:023.006` |
| `norm:eu-ai-act:article-23:paragraph-7:n1` | obligation | importers | shall | cooperate | with the relevant competent authorities in any action those authorities take | `span:023.007` |

### article-24 (12 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-24:paragraph-1:n1` | obligation | distributors | shall | verify | that it bears the required CE marking | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n2` | obligation | distributors | shall | verify | that it is accompanied by a copy of the EU declaration of conformity referred to in Article 47 | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n3` | obligation | distributors | shall | verify | that it is accompanied by instructions for use | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n4` | obligation | distributors | shall | verify | that the provider and the importer of that system, as applicable, have complied with their respective obligations as laid down in Article 16, points (b) and (c) and Article 23(3) | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-2:n1` | prohibition | a distributor | shall_not | make available | the high-risk AI system on the market | `span:024.002` |
| `norm:eu-ai-act:article-24:paragraph-2:n2` | obligation | the distributor | shall | inform | the provider or the importer of the system, as applicable, to that effect | `span:024.002` |
| `norm:eu-ai-act:article-24:paragraph-3:n1` | obligation | distributors | shall | ensure | that storage or transport conditions, where applicable, do not jeopardise the compliance of the system with the requirements set out in Section 2 | `span:024.003` |
| `norm:eu-ai-act:article-24:paragraph-4:n1` | obligation | a distributor that considers or has reason to consider, on the basis of the information in its possession | shall | take | the corrective actions necessary to bring that system into conformity with those requirements, to withdraw it or recall it | `span:024.004` |
| `norm:eu-ai-act:article-24:paragraph-4:n2` | obligation | a distributor that considers or has reason to consider, on the basis of the information in its possession | shall | ensure | that the provider, the importer or any relevant operator, as appropriate, takes those corrective actions | `span:024.004` |
| `norm:eu-ai-act:article-24:paragraph-4:n3` | obligation | the distributor | shall | immediately inform | the provider or importer of the system and the authorities competent for the high-risk AI system concerned | `span:024.004` |
| `norm:eu-ai-act:article-24:paragraph-5:n1` | obligation | distributors of a high-risk ai system | shall | provide | that authority with all the information and documentation regarding their actions pursuant to paragraphs 1 to 4 necessary to demonstrate the conformity of that system with the requirements set out in Section 2 | `span:024.005` |
| `norm:eu-ai-act:article-24:paragraph-6:n1` | obligation | distributors | shall | cooperate | with the relevant competent authorities in any action those authorities take | `span:024.006` |

### article-25 (11 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-25:paragraph-1:n1` | obligation | any distributor, importer, deployer or other third-party | shall | be considered | a provider of a high-risk ai system for the purposes of this regulation | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-1:n2` | obligation | any distributor, importer, deployer or other third-party | shall | be subject to | the obligations of the provider under article 16 | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-2:n1` | obligation | that initial provider | shall | closely cooperate | with new providers | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n2` | obligation | that initial provider | shall | make available | the necessary information | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n3` | obligation | that initial provider | shall | provide | the reasonably expected technical access and other assistance | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-3:n1` | obligation | the product manufacturer | shall | be considered to be | the provider of the high-risk AI system | `span:025.003` |
| `norm:eu-ai-act:article-25:paragraph-3:n2` | obligation | the product manufacturer | shall | be subject to | the obligations under Article 16 | `span:025.003` |
| `norm:eu-ai-act:article-25:paragraph-4:n1` | obligation | the provider of a high-risk ai system and the third party that supplies an ai system, tools, services, components, or processes that are used or integrated in a high-risk ai system | shall | specify | the necessary information, capabilities, technical access and other assistance | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n2` | exemption | unspecified_needs_review | shall_not | apply | this paragraph | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n3` | permission | the ai office | may | develop and recommend | voluntary model terms for contracts between providers of high-risk ai systems and third parties that supply tools, services, components or processes that are used for or integrated into high-risk ai systems | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n4` | obligation | the ai office | shall | take into account | possible contractual requirements applicable in specific sectors or business cases | `span:025.004` |

### article-26 (26 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-26:paragraph-1:n1` | obligation | deployers of high-risk ai systems | shall | take | appropriate technical and organisational measures | `span:026.001` |
| `norm:eu-ai-act:article-26:paragraph-2:n1` | obligation | deployers | shall | assign | human oversight to natural persons who have the necessary competence, training and authority, as well as the necessary support | `span:026.002` |
| `norm:eu-ai-act:article-26:paragraph-4:n1` | obligation | that deployer | shall | ensure | that input data is relevant and sufficiently representative in view of the intended purpose of the high-risk AI system | `span:026.004` |
| `norm:eu-ai-act:article-26:paragraph-5:n1` | obligation | deployers | shall | monitor | the operation of the high-risk AI system | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n2` | obligation | deployers | shall | inform | providers | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n4` | obligation | they | shall | suspend | the use of that system | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n5` | obligation | they | shall | inform | first the provider, and then the importer or distributor and the relevant market surveillance authorities of that incident | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-6:n1` | obligation | deployers of high-risk ai systems | shall | keep | the logs automatically generated by that high-risk AI system | `span:026.006` |
| `norm:eu-ai-act:article-26:paragraph-6:n2` | obligation | deployers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under Union financial services law | shall | maintain | the logs as part of the documentation kept pursuant to the relevant Union financial service law | `span:026.006` |
| `norm:eu-ai-act:article-26:paragraph-7:n1` | obligation | deployers who are employers | shall | inform | workers’ representatives and the affected workers that they will be subject to the use of the high-risk AI system | `span:026.007` |
| `norm:eu-ai-act:article-26:paragraph-8:n1` | obligation | deployers of high-risk ai systems that are public authorities, or union institutions, bodies, offices or agencies | shall | comply with | the registration obligations referred to in Article 49 | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-8:n2` | prohibition | such deployers | shall_not | use | that system | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-8:n3` | obligation | such deployers | shall | inform | the provider or the distributor | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-9:n1` | obligation | deployers of high-risk ai systems | shall | use | the information provided under Article 13 of this Regulation | `span:026.009` |
| `norm:eu-ai-act:article-26:paragraph-10:n1` | obligation | the deployer of a high-risk ai system for post-remote biometric identification | shall | request | an authorisation ... by a judicial authority or an administrative authority whose decision is binding and subject to judicial review, for the use of that system | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n3` | obligation | unspecified_needs_review | shall | be stopped | the use of the post-remote biometric identification system linked to that requested authorisation | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n4` | obligation | unspecified_needs_review | shall | be deleted | the personal data linked to the use of the high-risk ai system for which the authorisation was requested | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n5` | prohibition | unspecified_needs_review | shall | be used | such high-risk ai system for post-remote biometric identification for law enforcement purposes in an untargeted way | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n6` | obligation | unspecified_needs_review | shall | be ensured | that no decision that produces an adverse legal effect on a person may be taken by the law enforcement authorities based solely on the output of such post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n7` | prohibition | the law enforcement authorities | may | take | a decision that produces an adverse legal effect on a person based solely on the output of such post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n8` | obligation | each use of such high-risk ai systems | shall | be documented | in the relevant police file | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n9` | obligation | each use of such high-risk ai systems | shall | be made available | to the relevant market surveillance authority and the national data protection authority upon request | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n10` | obligation | deployers | shall | submit | annual reports to the relevant market surveillance and national data protection authorities on their use of post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n12` | permission | member states | may | introduce | more restrictive laws on the use of post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-11:n1` | obligation | deployers of high-risk ai systems referred to in annex iii that make decisions or assist in making decisions related to natural persons | shall | inform | the natural persons that they are subject to the use of the high-risk ai system | `span:026.011` |
| `norm:eu-ai-act:article-26:paragraph-12:n1` | obligation | deployers | shall | cooperate | with the relevant competent authorities | `span:026.012` |

### article-27 (9 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-27:paragraph-1:n1` | obligation | deployers that are bodies governed by public law, or are private entities providing public services, and deployers of high-risk ai systems referred to in points 5 (b) and (c) of annex iii | shall | perform | an assessment of the impact on fundamental rights that the use of such system may produce | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n5` | obligation | deployers | shall | perform | an assessment consisting of the specific risks of harm likely to have an impact on the categories of natural persons or groups of persons identified pursuant to point (c) of this paragraph | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-2:n2` | permission | the deployer | may | rely on | previously conducted fundamental rights impact assessments or existing impact assessments carried out by provider | `span:027.002` |
| `norm:eu-ai-act:article-27:paragraph-2:n3` | obligation | the deployer | shall | take | the necessary steps to update the information | `span:027.002` |
| `norm:eu-ai-act:article-27:paragraph-3:n1` | obligation | the deployer | shall | notify | the market surveillance authority of its results | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-3:n2` | obligation | the deployer | shall | submit | the filled-out template referred to in paragraph 5 of this Article as part of the notification | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-3:n3` | exemption | deployers | may | be exempt | from that obligation to notify | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-4:n1` | obligation | unspecified_needs_review | shall | complement | that data protection impact assessment | `span:027.004` |
| `norm:eu-ai-act:article-27:paragraph-5:n1` | obligation | the ai office | shall | develop | a template for a questionnaire | `span:027.005` |

### article-50 (13 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-50:paragraph-1:n2` | exemption | provider | shall | not apply | this obligation | `span:050.001` |
| `norm:eu-ai-act:article-50:paragraph-2:n1` | obligation | providers of ai systems, including general-purpose ai systems, generating synthetic audio, image, video or text content | shall | ensure | that the outputs of the ai system are marked in a machine-readable format and detectable as artificially generated or manipulated | `span:050.002` |
| `norm:eu-ai-act:article-50:paragraph-2:n2` | obligation | providers | shall | ensure | their technical solutions are effective, interoperable, robust and reliable | `span:050.002` |
| `norm:eu-ai-act:article-50:paragraph-3:n1` | obligation | deployers of an emotion recognition system or a biometric categorisation system | shall | inform | the natural persons exposed thereto of the operation of the system | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-3:n2` | obligation | deployers of an emotion recognition system or a biometric categorisation system | shall | process | the personal data in accordance with Regulations (EU) 2016/679 and (EU) 2018/1725 and Directive (EU) 2016/680, as applicable | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-3:n3` | exemption | unspecified_needs_review | shall | not apply | this obligation | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-4:n2` | obligation | deployers | other_explicit | limit the transparency obligations set out in this paragraph to disclosure | the existence of such generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-4:n3` | obligation | deployers of an ai system that generates or manipulates text which is published with the purpose of informing the public on matters of public interest | shall | disclose | that the text has been artificially generated or manipulated | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-5:n1` | obligation | unspecified_needs_review | shall | be provided | the information referred to in paragraphs 1 to 4 | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-5:n2` | obligation | unspecified_needs_review | shall | conform to | the applicable accessibility requirements | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-7:n1` | obligation | the ai office | shall | encourage and facilitate the drawing up | codes of practice at union level | `span:050.007` |
| `norm:eu-ai-act:article-50:paragraph-7:n2` | permission | the commission | may | adopt implementing acts | implementing acts to approve those codes of practice | `span:050.007` |
| `norm:eu-ai-act:article-50:paragraph-7:n3` | permission | the commission | may | adopt an implementing act specifying | common rules for the implementation of those obligations | `span:050.007` |

### article-72 (6 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-72:paragraph-1:n1` | obligation | providers | shall | establish and document | a post-market monitoring system | `span:072.001` |
| `norm:eu-ai-act:article-72:paragraph-3:n1` | obligation | unspecified_needs_review | shall | be based on | a post-market monitoring plan | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-3:n2` | obligation | unspecified_needs_review | shall | be part of | the technical documentation referred to in Annex IV | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-3:n3` | obligation | the commission | shall | adopt | an implementing act laying down detailed provisions establishing a template for the post-market monitoring plan and the list of elements to be included in the plan | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-4:n1` | permission | providers | shall | have a choice of integrating, as appropriate, the necessary elements described in paragraphs 1, 2 and 3 using the template referred in paragraph 3 | systems and plans already existing under that legislation | `span:072.004` |
| `norm:eu-ai-act:article-72:paragraph-4:n2` | permission | providers | shall | have a choice of integrating, as appropriate, the necessary elements described in paragraphs 1, 2 and 3 using the template referred in paragraph 3 | systems and plans already existing under that legislation | `span:072.004` |

### article-73 (17 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-73:paragraph-1:n1` | obligation | providers of high-risk ai systems placed on the union market | shall | report | any serious incident | `span:073.001` |
| `norm:eu-ai-act:article-73:paragraph-2:n1` | obligation | unspecified_needs_review | shall | be made | the report referred to in paragraph 1 | `span:073.002` |
| `norm:eu-ai-act:article-73:paragraph-4:n2` | obligation | the provider | shall | provide | the report | `span:073.004` |
| `norm:eu-ai-act:article-73:paragraph-4:n3` | obligation | the deployer | shall | provide | the report | `span:073.004` |
| `norm:eu-ai-act:article-73:paragraph-5:n1` | permission | the provider | may | submit | an initial report that is incomplete | `span:073.005` |
| `norm:eu-ai-act:article-73:paragraph-5:n2` | permission | the deployer | may | submit | an initial report that is incomplete | `span:073.005` |
| `norm:eu-ai-act:article-73:paragraph-6:n1` | obligation | the provider | shall | perform | the necessary investigations in relation to the serious incident and the AI system concerned | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n4` | obligation | the provider | shall | cooperate | with the competent authorities | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n6` | prohibition | the provider | shall_not | perform | any investigation which involves altering the AI system concerned in a way which may affect any subsequent evaluation of the causes of the incident | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-7:n1` | obligation | the relevant market surveillance authority | shall | inform | the national public authorities or bodies referred to in Article 77(1) | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-7:n2` | obligation | the Commission | shall | develop | dedicated guidance to facilitate compliance with the obligations set out in paragraph 1 of this Article | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-8:n1` | obligation | the market surveillance authority | shall | take | appropriate measures | `span:073.008` |
| `norm:eu-ai-act:article-73:paragraph-8:n2` | obligation | the market surveillance authority | shall | follow | the notification procedures | `span:073.008` |
| `norm:eu-ai-act:article-73:paragraph-9:n1` | obligation | unspecified_needs_review | shall | be limited | the notification of serious incidents | `span:073.009` |
| `norm:eu-ai-act:article-73:paragraph-10:n1` | obligation | unspecified_needs_review | shall | be limited | the notification of serious incidents to those referred to in Article 3, point (49)(c) of this Regulation | `span:073.010` |
| `norm:eu-ai-act:article-73:paragraph-10:n2` | obligation | unspecified_needs_review | shall | be made | the notification of serious incidents to the national competent authority chosen for that purpose by the Member States where the incident occurred | `span:073.010` |
| `norm:eu-ai-act:article-73:paragraph-11:n1` | obligation | national competent authorities | shall | immediately notify | the Commission of any serious incident | `span:073.011` |

## Facts that could not be settled from the README

The server reported no missing facts: every prohibition-relevant and Annex III relevant flag was answered. That is not the same as every fact being stated outright in the README. The flags below were set by inference from what it does say, and each one is open to challenge.

| flag | set to | why |
| --- | --- | --- |
| `flags.essential_services_access` | true | the README calls consumer credit an essential private service provided by the deployer |
| `flags.supports_human_assessment_on_verifiable_facts` | false | the service issues a score and a recommendation, not a check of verifiable facts, so the Article 6(3) carve-out was not claimed |
| `flags.preparatory_or_narrow_procedural_task` | false | scoring an application is the substantive assessment, not a preparatory or narrow procedural step |
| `flags.improves_previous_human_activity` | false | the README does not describe the service as improving an already completed human activity |
| `flags.detects_patterns_without_replacing_human_assessment` | false | the recommendation feeds the loan officer's decision directly, so it was not treated as pattern detection outside the assessment |
| `flags.annex_i_covered_product` | false | the README describes a standalone service, not a safety component of an Annex I product |
| `flags.third_party_conformity_assessment_required` | false | not stated in the README; it follows from the conformity route, which is not settled here |
| `deployer.private_entity_providing_public_services` | true | the README says the deployer is a private company providing an essential private service |

Facts the README does not settle at all, and which this document does not assert:

- whether the provider has a quality management system in place (Article 17)
- whether training, validation and testing data sets exist and how they were governed (Article 10)
- whether the service is already placed on the market or still in development (Articles 16, 43, 49)
- whether the deployer is a financial institution under Union financial services law (Article 26(6))
- the conformity assessment route and whether a notified body is involved (Article 43)

## Notice

> TERE4AI provides engineering and documentation support. It does not certify EU AI Act compliance and does not replace legal review, conformity assessment, or competent-authority interpretation.

This document maps obligations. It does not implement, satisfy, or discharge any of them, and it is not a conformity assessment.

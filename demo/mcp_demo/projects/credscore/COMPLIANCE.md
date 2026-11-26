# CredScore, EU AI Act obligation map

Generated from live TERE4AI MCP answers. Nothing below is legal advice; see the notice at the end, which is the server's own wording.

- graph version: `build-bab25bf2e5d6+chain-24ea1a5ab6ca`
- classified at: 2026-11-26T21:06:27.163562+00:00
- requirements fetched at: 2026-11-26T21:06:27.668598+00:00

## Classification

- risk category: **high_risk**
- unacceptable risk: no
- Annex III category: `eu-ai-act:annex-iii:point-5`
- envelope status: `potentially_applicable`, confidence 1.0
- Article 6(3) exception candidate: False

Rule trace returned by the server:

- rule high_risk: flag creditworthiness_evaluation matches Annex III category 'essential private and public services' (eu-ai-act:annex-iii:point-5), high-risk under Article 6(2)

Cited nodes:

- `eu-ai-act:annex-iii:point-5`
- `eu-ai-act:article-6:paragraph-2`
- `eu-ai-act:annex-iii:point-5:b`

## Article 27 fundamental rights impact assessment

- applicability: **applies**
- Article 27(1) trigger: creditworthiness_evaluation is true (evaluate the creditworthiness of natural persons or establish their credit score (Annex III point 5(b))); the FRIA obligation covers deployers of these systems regardless of deployer type
- the assessment must be performed 'Prior to deploying a high-risk AI system referred to in Article 6(2)' (Article 27(1))
- applies from 2027-12-02 (`in_force`, source Article 113, third paragraph, point (c)(i), of Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744 (OJ L, 2026/1744, 24.7.2026))

## Scope of the tailored requirements

- judge-accepted requirements in scope: **336**
- returned in this fetch: 336
- articles touched: 24
- norms still in the human review queue, never served: 16
- calibrated status carried by every row below: `applicable_missing_evidence`

That status is the honest one for a codebase that has submitted no artifacts. The obligation applies and no evidence has been offered for it yet. Nothing here says satisfied, compliant, or certified.

| article | accepted | in review queue |
| --- | ---: | ---: |
| article-4a | 4 | 5 |
| article-8 | 4 | 0 |
| article-9 | 24 | 0 |
| article-10 | 18 | 0 |
| article-11 | 10 | 0 |
| article-12 | 8 | 0 |
| article-13 | 20 | 0 |
| article-14 | 12 | 0 |
| article-15 | 13 | 0 |
| article-16 | 13 | 9 |
| article-17 | 24 | 0 |
| article-18 | 7 | 0 |
| article-19 | 2 | 0 |
| article-20 | 5 | 1 |
| article-21 | 3 | 0 |
| article-22 | 24 | 0 |
| article-23 | 15 | 0 |
| article-24 | 12 | 0 |
| article-25 | 19 | 0 |
| article-26 | 29 | 1 |
| article-27 | 17 | 0 |
| article-50 | 21 | 0 |
| article-72 | 10 | 0 |
| article-73 | 22 | 0 |

## Obligations by article

### article-4a (4 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-4a:paragraph-1:n1` | permission | providers of such systems | may | exceptionally process | special categories of personal data | `span:004a.001` |
| `norm:eu-ai-act:article-4a:paragraph-2:n1` | permission | Providers | may | exceptionally process | special categories of personal data | `span:004a.002` |
| `norm:eu-ai-act:article-4a:paragraph-2:n2` | permission | deployers of other AI systems and models | may | exceptionally process | special categories of personal data | `span:004a.002` |
| `norm:eu-ai-act:article-4a:paragraph-2:n3` | permission | deployers of high-risk AI systems | may | exceptionally process | special categories of personal data | `span:004a.002` |

### article-8 (4 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-8:paragraph-1:n1` | obligation | provider | shall | comply with | the requirements laid down in this Section | `span:008.001` |
| `norm:eu-ai-act:article-8:paragraph-1:n2` | obligation | provider | shall | take into account | The risk management system referred to in Article 9 | `span:008.001` |
| `norm:eu-ai-act:article-8:paragraph-2:n1` | obligation | providers | shall | be responsible for ensuring | that their product is fully compliant with all applicable requirements under applicable Union harmonisation legislation | `span:008.002` |
| `norm:eu-ai-act:article-8:paragraph-2:n2` | right | providers | shall | have a choice of integrating | the necessary testing and reporting processes, information and documentation they provide with regard to their product into documentation and procedures that already exist and are required under the Union harmonisation legislation listed in Section A of Annex I | `span:008.002` |

### article-9 (24 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-9:paragraph-1:n1` | obligation | provider | shall | establish, implement, document and maintain | a risk management system | `span:009.001` |
| `norm:eu-ai-act:article-9:paragraph-2:n1` | obligation | provider | shall | plan and run | the risk management system as a continuous iterative process | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n2` | obligation | provider | shall | regularly and systematically review and update | the risk management system | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n3` | obligation | provider | shall | identify and analyse | the known and the reasonably foreseeable risks that the high-risk AI system can pose to health, safety or fundamental rights | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n4` | obligation | provider | shall | estimate and evaluate | the risks that may emerge | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n5` | obligation | provider | shall | evaluate | other risks possibly arising | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-2:n6` | obligation | provider | shall | adopt | appropriate and targeted risk management measures designed to address the risks identified pursuant to point (a) | `span:009.002` |
| `norm:eu-ai-act:article-9:paragraph-3:n1` | obligation | provider | shall | concern only | those risks which may be reasonably mitigated or eliminated through the development or design of the high-risk AI system, or the provision of adequate technical information | `span:009.003` |
| `norm:eu-ai-act:article-9:paragraph-4:n1` | obligation | provider | shall | give due consideration to | the effects and possible interaction resulting from the combined application of the requirements set out in this Section | `span:009.004` |
| `norm:eu-ai-act:article-9:paragraph-5:n1` | obligation | provider | shall | be such that the relevant residual risk associated with each hazard, as well as the overall residual risk of the high-risk AI systems is judged to be acceptable | the risk management measures referred to in paragraph 2, point (d) | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n2` | obligation | provider | shall | ensure | elimination or reduction of risks identified and evaluated pursuant to paragraph 2 through adequate design and development of the high-risk AI system | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n3` | obligation | provider | shall | ensure | implementation of adequate mitigation and control measures addressing risks that cannot be eliminated | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n4` | obligation | provider | shall | ensure | provision of information required pursuant to Article 13 | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n5` | obligation | provider | shall | ensure | provision of training to deployers | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:n6` | obligation | provider | shall | give due consideration to | the technical knowledge, experience, education, the training to be expected by the deployer, and the presumable context in which the system is intended to be used | `span:009.005` |
| `norm:eu-ai-act:article-9:paragraph-5:point-c:n1` | obligation | provider | other_explicit | provide | information required pursuant to Article 13 | `span:fmx:art_009.parag_005.np_c` |
| `norm:eu-ai-act:article-9:paragraph-5:point-c:n2` | obligation | provider | other_explicit | provide | training to deployers | `span:fmx:art_009.parag_005.np_c` |
| `norm:eu-ai-act:article-9:paragraph-6:n1` | obligation | provider | shall | test | high-risk AI systems | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-6:n2` | obligation | provider | shall | ensure through testing | that high-risk AI systems perform consistently | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-6:n3` | obligation | provider | shall | ensure through testing | that high-risk AI systems are in compliance with the requirements set out in this Section | `span:009.006` |
| `norm:eu-ai-act:article-9:paragraph-7:n1` | permission | provider | may | include | testing in real-world conditions | `span:009.007` |
| `norm:eu-ai-act:article-9:paragraph-8:n1` | obligation | provider | shall | perform | the testing of high-risk AI systems | `span:009.008` |
| `norm:eu-ai-act:article-9:paragraph-8:n2` | obligation | provider | shall | carry out | testing | `span:009.008` |
| `norm:eu-ai-act:article-9:paragraph-9:n1` | obligation | providers | shall | give consideration to | whether the high-risk AI system is likely to have an adverse impact on persons under the age of 18 and, as appropriate, other vulnerable groups | `span:009.009` |

### article-10 (18 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-10:paragraph-1:n1` | obligation | provider | shall | be developed on the basis of | training, validation and testing data sets that meet the quality criteria referred to in paragraphs 2, 3 and 4 of this Article and in Article 4a(1) | `span:010.001` |
| `norm:eu-ai-act:article-10:paragraph-2:n1` | obligation | provider | shall | subject | training, validation and testing data sets to data governance and management practices appropriate for the intended purpose of the high-risk AI system | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n2` | obligation | provider | shall | concern in particular | the relevant design choices | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n3` | obligation | provider | shall | concern in particular | data collection processes and the origin of data | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n4` | obligation | provider | shall | concern in particular | the original purpose of the data collection | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n5` | obligation | provider | shall | concern in particular | relevant data-preparation processing operations, such as annotation, labelling, cleaning, updating, enrichment and aggregation | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n6` | obligation | provider | shall | concern in particular | the formulation of assumptions | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n7` | obligation | provider | shall | concern in particular | an assessment of the availability, quantity and suitability of the data sets that are needed | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n8` | obligation | provider | shall | concern in particular | examination in view of possible biases that are likely to affect the health and safety of persons, have a negative impact on fundamental rights or lead to discrimination prohibited under Union law | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n9` | obligation | provider | shall | concern in particular | appropriate measures to detect, prevent and mitigate possible biases identified according to point (f) | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-2:n10` | obligation | provider | shall | concern in particular | the identification of relevant data gaps or shortcomings that prevent compliance with this Regulation, and how those gaps and shortcomings can be addressed | `span:010.002` |
| `norm:eu-ai-act:article-10:paragraph-3:n1` | obligation | provider | shall | be relevant | training, validation and testing data sets | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-3:n2` | obligation | provider | shall | be sufficiently representative | training, validation and testing data sets | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-3:n3` | obligation | provider | shall | be free of errors | training, validation and testing data sets | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-3:n4` | obligation | provider | shall | be complete | training, validation and testing data sets | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-3:n5` | obligation | provider | shall | have | the appropriate statistical properties | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-3:n6` | permission | provider | may | meet | those characteristics of the data sets | `span:010.003` |
| `norm:eu-ai-act:article-10:paragraph-4:n1` | obligation | provider | shall | take into account | the characteristics or elements that are particular to the specific geographical, contextual, behavioural or functional setting within which the high-risk AI system is intended to be used | `span:010.004` |

### article-11 (10 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-11:paragraph-1:n1` | obligation | provider | shall | draw up | the technical documentation of a high-risk AI system | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n2` | obligation | provider | shall | keep up-to date | the technical documentation of a high-risk AI system | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n3` | obligation | provider | shall | draw up | the technical documentation | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n5` | obligation | provider | shall | contain | the elements set out in Annex IV | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n6` | permission | SMEs, including start-ups, and SMCs | may | provide | the elements of the technical documentation specified in Annex IV | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n7` | obligation | the Commission | shall | establish | a simplified technical documentation form targeted at the needs of SMEs, including start-ups, and SMCs | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n8` | obligation | an SME, including a start-up, or an SMC | shall | use | the form referred to in this paragraph | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-1:n9` | obligation | Notified bodies | shall | accept | the form | `span:011.001` |
| `norm:eu-ai-act:article-11:paragraph-2:n1` | obligation | provider | shall | draw up | a single set of technical documentation containing all the information set out in paragraph 1, as well as the information required under those legal acts | `span:011.002` |
| `norm:eu-ai-act:article-11:paragraph-3:n1` | permission | The Commission | other_explicit | adopt | delegated acts | `span:011.003` |

### article-12 (8 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-12:paragraph-1:n1` | obligation | provider | shall | technically allow for | the automatic recording of events (logs) | `span:012.001` |
| `norm:eu-ai-act:article-12:paragraph-2:n1` | obligation | provider | shall | enable | the recording of events relevant for identifying situations that may result in the high-risk AI system presenting a risk within the meaning of Article 79(1) or in a substantial modification | `span:012.002` |
| `norm:eu-ai-act:article-12:paragraph-2:n2` | obligation | provider | shall | enable | the recording of events relevant for facilitating the post-market monitoring referred to in Article 72 | `span:012.002` |
| `norm:eu-ai-act:article-12:paragraph-2:n3` | obligation | provider | shall | enable | the recording of events relevant for monitoring the operation of high-risk AI systems referred to in Article 26(5) | `span:012.002` |
| `norm:eu-ai-act:article-12:paragraph-3:n1` | obligation | provider | shall | provide | recording of the period of each use of the system (start date and time and end date and time of each use) | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n2` | obligation | provider | shall | provide | the reference database against which input data has been checked by the system | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n3` | obligation | provider | shall | provide | the input data for which the search has led to a match | `span:012.003` |
| `norm:eu-ai-act:article-12:paragraph-3:n4` | obligation | provider | shall | provide | the identification of the natural persons involved in the verification of the results, as referred to in Article 14(5) | `span:012.003` |

### article-13 (20 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-13:paragraph-1:n1` | obligation | provider | shall | design and develop | high-risk AI systems | `span:013.001` |
| `norm:eu-ai-act:article-13:paragraph-1:n2` | obligation | provider | shall | ensure | an appropriate type and degree of transparency | `span:013.001` |
| `norm:eu-ai-act:article-13:paragraph-2:n1` | obligation | provider | shall | be accompanied by | instructions for use in an appropriate digital format or otherwise that include concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers | `span:013.002` |
| `norm:eu-ai-act:article-13:paragraph-3:n1` | obligation | provider | shall | contain at least | the identity and the contact details of the provider | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n2` | obligation | provider | shall | contain at least | the identity and the contact details of its authorised representative | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n3` | obligation | provider | shall | contain at least | the characteristics, capabilities and limitations of performance of the high-risk AI system | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n4` | obligation | provider | shall | contain at least | its intended purpose | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n5` | obligation | provider | shall | contain at least | the level of accuracy, including its metrics, robustness and cybersecurity referred to in Article 15 against which the high-risk AI system has been tested and validated and which can be expected | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n6` | obligation | provider | shall | contain at least | any known and foreseeable circumstances that may have an impact on that expected level of accuracy, robustness and cybersecurity | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n7` | obligation | provider | shall | contain at least | any known or foreseeable circumstance which may lead to risks to the health and safety or fundamental rights referred to in Article 9(2) | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n8` | obligation | provider | shall | contain at least | the technical capabilities and characteristics of the high-risk AI system to provide information that is relevant to explain its output | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n9` | obligation | provider | shall | contain at least | its performance regarding specific persons or groups of persons on which the system is intended to be used | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n10` | obligation | provider | shall | contain at least | specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n11` | obligation | provider | shall | contain at least | information to enable deployers to interpret the output of the high-risk AI system and use it appropriately | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n12` | obligation | provider | shall | contain at least | the changes to the high-risk AI system and its performance which have been pre-determined by the provider at the moment of the initial conformity assessment | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n13` | obligation | provider | shall | contain at least | the human oversight measures referred to in Article 14, including the technical measures put in place to facilitate the interpretation of the outputs of the high-risk AI systems by the deployers | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n14` | obligation | provider | shall | contain at least | the computational and hardware resources needed | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n15` | obligation | provider | shall | contain at least | the expected lifetime of the high-risk AI system | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n16` | obligation | provider | shall | contain at least | any necessary maintenance and care measures, including their frequency, to ensure the proper functioning of that AI system, including as regards software updates | `span:013.003` |
| `norm:eu-ai-act:article-13:paragraph-3:n17` | obligation | provider | shall | contain at least | a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs in accordance with Article 12 | `span:013.003` |

### article-14 (12 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-14:paragraph-1:n1` | obligation | provider | shall | design and develop | high-risk AI systems in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons | `span:014.001` |
| `norm:eu-ai-act:article-14:paragraph-2:n1` | obligation | provider | shall | aim to prevent or minimise | the risks to health, safety or fundamental rights | `span:014.002` |
| `norm:eu-ai-act:article-14:paragraph-3:n1` | obligation | provider | shall | be commensurate with | the risks, level of autonomy and context of use of the high-risk AI system | `span:014.003` |
| `norm:eu-ai-act:article-14:paragraph-3:n2` | obligation | provider | shall | ensure | the oversight measures | `span:014.003` |
| `norm:eu-ai-act:article-14:paragraph-4:n1` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to properly understand the relevant capacities and limitations of the high-risk AI system | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n2` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to duly monitor its operation | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n3` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to remain aware of the possible tendency of automatically relying or over-relying on the output produced by a high-risk AI system (automation bias) | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n4` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to correctly interpret the high-risk AI system’s output | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n5` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to decide not to use the high-risk AI system or to otherwise disregard, override or reverse the output of the high-risk AI system | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-4:n6` | obligation | provider | shall | provide | the high-risk AI system to the deployer in such a way that natural persons to whom human oversight is assigned are enabled to intervene in the operation of the high-risk AI system or interrupt the system through a ‘stop’ button or a similar procedure that allows the system to come to a halt in a safe state | `span:014.004` |
| `norm:eu-ai-act:article-14:paragraph-5:n1` | obligation | provider | shall | ensure through the measures referred to in paragraph 3 of this Article | that, in addition, no action or decision is taken by the deployer on the basis of the identification resulting from the system | `span:014.005` |
| `norm:eu-ai-act:article-14:paragraph-5:n2` | exemption | provider | shall_not | apply | the requirement for a separate verification by at least two natural persons | `span:014.005` |

### article-15 (13 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-15:paragraph-1:n1` | obligation | provider | shall | be designed and developed in such a way that they achieve | an appropriate level of accuracy, robustness, and cybersecurity | `span:015.001` |
| `norm:eu-ai-act:article-15:paragraph-1:n2` | obligation | provider | shall | be designed and developed in such a way that they perform consistently | in respect of accuracy, robustness, and cybersecurity | `span:015.001` |
| `norm:eu-ai-act:article-15:paragraph-2:n1` | obligation | the Commission | shall | encourage | the development of benchmarks and measurement methodologies | `span:015.002` |
| `norm:eu-ai-act:article-15:paragraph-3:n1` | obligation | provider | shall | declare | the levels of accuracy and the relevant accuracy metrics of high-risk AI systems | `span:015.003` |
| `norm:eu-ai-act:article-15:paragraph-4:n1` | obligation | provider | shall | be as resilient as possible regarding | errors, faults or inconsistencies that may occur within the system or the environment in which the system operates | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n2` | obligation | provider | shall | take | Technical and organisational measures | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n3` | permission | provider | may | achieve through technical redundancy solutions | The robustness of high-risk AI systems | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n4` | permission | provider | may | include in technical redundancy solutions | backup or fail-safe plans | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n5` | obligation | provider | shall | be developed in such a way as to eliminate or reduce as far as possible | the risk of possibly biased outputs influencing input for future operations (feedback loops) | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-4:n6` | obligation | provider | shall | be developed in such a way as to ensure | that any such feedback loops are duly addressed with appropriate mitigation measures | `span:015.004` |
| `norm:eu-ai-act:article-15:paragraph-5:n1` | obligation | provider | shall | be resilient against attempts by unauthorised third parties to alter their use, outputs or performance by exploiting system vulnerabilities | high-risk AI systems | `span:015.005` |
| `norm:eu-ai-act:article-15:paragraph-5:n2` | obligation | provider | shall | be appropriate to the relevant circumstances and the risks | the technical solutions aiming to ensure the cybersecurity of high-risk AI systems | `span:015.005` |
| `norm:eu-ai-act:article-15:paragraph-5:n3` | obligation | provider | shall | include | measures to prevent, detect, respond to, resolve and control for attacks trying to manipulate the training data set (data poisoning), or pre-trained components used in training (model poisoning), inputs designed to cause the AI model to make a mistake (adversarial examples or model evasion), confidentiality attacks or model flaws | `span:015.005` |

### article-16 (13 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-16:paragraph-1:n1` | obligation | Providers of high-risk AI systems | shall | ensure | that their high-risk AI systems are compliant with the requirements set out in Section 2 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n2` | obligation | Providers of high-risk AI systems | shall | indicate | their name, registered trade name or registered trade mark, the address at which they can be contacted | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n3` | obligation | Providers of high-risk AI systems | shall | have | a quality management system in place which complies with Article 17 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n4` | obligation | Providers of high-risk AI systems | shall | keep | the documentation referred to in Article 18 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n5` | obligation | Providers of high-risk AI systems | shall | keep | the logs automatically generated by their high-risk AI systems as referred to in Article 19 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n6` | obligation | Providers of high-risk AI systems | shall | ensure | that the high-risk AI system undergoes the relevant conformity assessment procedure as referred to in Article 43 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n7` | obligation | Providers of high-risk AI systems | shall | draw up | an EU declaration of conformity | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n8` | obligation | Providers of high-risk AI systems | shall | affix | the CE marking | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n9` | obligation | Providers of high-risk AI systems | shall | comply with | the registration obligations referred to in Article 49(1) | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n10` | obligation | Providers of high-risk AI systems | shall | take | the necessary corrective actions | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n11` | obligation | Providers of high-risk AI systems | shall | provide | information | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n12` | obligation | Providers of high-risk AI systems | shall | demonstrate | the conformity of the high-risk AI system with the requirements set out in Section 2 | `span:art_16:body` |
| `norm:eu-ai-act:article-16:paragraph-1:n13` | obligation | Providers of high-risk AI systems | shall | ensure | that the high-risk AI system complies with accessibility requirements | `span:art_16:body` |

### article-17 (24 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-17:paragraph-1:n1` | obligation | Providers of high-risk AI systems | shall | put in place | a quality management system that ensures compliance with this Regulation | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n2` | obligation | provider | shall | document | the quality management system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n3` | obligation | provider | shall | include at least | a strategy for regulatory compliance, including compliance with conformity assessment procedures and procedures for the management of modifications to the high-risk AI system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n4` | obligation | provider | shall | include at least | techniques, procedures and systematic actions to be used for the design, design control and design verification of the high-risk AI system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n5` | obligation | provider | shall | include at least | techniques, procedures and systematic actions to be used for the development, quality control and quality assurance of the high-risk AI system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n6` | obligation | provider | shall | include at least | examination, test and validation procedures to be carried out before, during and after the development of the high-risk AI system, and the frequency with which they have to be carried out | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n7` | obligation | provider | shall | include at least | technical specifications, including standards, to be applied | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n8` | obligation | provider | shall | include at least | the means to be used to ensure that the high-risk AI system complies with those requirements | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n9` | obligation | provider | shall | include at least | systems and procedures for data management, including data acquisition, data collection, data analysis, data labelling, data storage, data filtration, data mining, data aggregation, data retention and any other operation regarding the data that is performed before and for the purpose of the placing on the market or the putting into service of high-risk AI systems | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n10` | obligation | provider | shall | include at least | the risk management system referred to in Article 9 | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n11` | obligation | provider | shall | include at least | the setting-up, implementation and maintenance of a post-market monitoring system | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n12` | obligation | provider | shall | include at least | procedures related to the reporting of a serious incident | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n13` | obligation | provider | shall | include at least | the handling of communication with national competent authorities, other relevant authorities, including those providing or supporting the access to data, notified bodies, other operators, customers or other interested parties | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n14` | obligation | provider | shall | include at least | systems and procedures for record-keeping of all relevant documentation and information | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n15` | obligation | provider | shall | include at least | resource management, including security-of-supply related measures | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:n16` | obligation | provider | shall | include at least | an accountability framework setting out the responsibilities of the management and other staff with regard to all the aspects listed in this paragraph | `span:017.001` |
| `norm:eu-ai-act:article-17:paragraph-1:point-f:n1` | obligation | provider | other_explicit | include | systems and procedures for data management, including data acquisition, data collection, data analysis, data labelling, data storage, data filtration, data mining, data aggregation, data retention and any other operation regarding the data | `span:fmx:art_017.parag_001.np_f` |
| `norm:eu-ai-act:article-17:paragraph-1:point-h:n1` | obligation | provider | other_explicit | set up, implement and maintain | a post-market monitoring system | `span:fmx:art_017.parag_001.np_h` |
| `norm:eu-ai-act:article-17:paragraph-1:point-j:n1` | obligation | provider | other_explicit | handle | communication with national competent authorities, other relevant authorities, including those providing or supporting the access to data, notified bodies, other operators, customers or other interested parties | `span:fmx:art_017.parag_001.np_j` |
| `norm:eu-ai-act:article-17:paragraph-1:point-m:n1` | obligation | provider | other_explicit | set out in an accountability framework | the responsibilities of the management and other staff | `span:fmx:art_017.parag_001.np_m` |
| `norm:eu-ai-act:article-17:paragraph-2:n2` | obligation | Providers | shall | respect | the degree of rigour and the level of protection required to ensure the compliance of their high-risk AI systems with this Regulation | `span:017.002` |
| `norm:eu-ai-act:article-17:paragraph-3:n1` | permission | Providers of high-risk AI systems | may | include | the aspects listed in paragraph 1 as part of the quality management systems pursuant to that law | `span:017.003` |
| `norm:eu-ai-act:article-17:paragraph-4:n1` | exemption | providers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under Union financial services law | shall | be deemed to be fulfilled | the obligation to put in place a quality management system | `span:017.004` |
| `norm:eu-ai-act:article-17:paragraph-4:n2` | obligation | providers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under Union financial services law | shall | take into account | any harmonised standards referred to in Article 40 | `span:017.004` |

### article-18 (7 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-18:paragraph-1:n1` | obligation | The provider | shall | keep at the disposal of the national competent authorities | the technical documentation referred to in Article 11 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n2` | obligation | The provider | shall | keep at the disposal of the national competent authorities | the documentation concerning the quality management system referred to in Article 17 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n3` | obligation | The provider | shall | keep at the disposal of the national competent authorities | the documentation concerning the changes approved by notified bodies | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n4` | obligation | The provider | shall | keep at the disposal of the national competent authorities | the decisions and other documents issued by the notified bodies | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-1:n5` | obligation | The provider | shall | keep at the disposal of the national competent authorities | the EU declaration of conformity referred to in Article 47 | `span:018.001` |
| `norm:eu-ai-act:article-18:paragraph-2:n1` | obligation | Each Member State | shall | determine | conditions under which the documentation referred to in paragraph 1 remains at the disposal of the national competent authorities for the period indicated in that paragraph | `span:018.002` |
| `norm:eu-ai-act:article-18:paragraph-3:n1` | obligation | Providers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under Union financial services law | shall | maintain | the technical documentation | `span:018.003` |

### article-19 (2 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-19:paragraph-1:n1` | obligation | Providers of high-risk AI systems | shall | keep | the logs referred to in Article 12(1), automatically generated by their high-risk AI systems | `span:019.001` |
| `norm:eu-ai-act:article-19:paragraph-2:n1` | obligation | Providers that are financial institutions | shall | maintain | the logs automatically generated by their high-risk AI systems | `span:019.002` |

### article-20 (5 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-20:paragraph-1:n1` | obligation | Providers of high-risk AI systems | shall | immediately take | the necessary corrective actions to bring that system into conformity, to withdraw it, to disable it, or to recall it | `span:020.001` |
| `norm:eu-ai-act:article-20:paragraph-1:n2` | obligation | Providers of high-risk AI systems | shall | inform accordingly | the distributors of the high-risk AI system concerned | `span:020.001` |
| `norm:eu-ai-act:article-20:paragraph-1:n3` | obligation | Providers of high-risk AI systems | shall | inform accordingly | the deployers, the authorised representative and importers | `span:020.001` |
| `norm:eu-ai-act:article-20:paragraph-2:n1` | obligation | the provider | shall | immediately investigate | the causes | `span:020.002` |
| `norm:eu-ai-act:article-20:paragraph-2:n3` | obligation | the provider | shall | immediately inform | the notified body that issued a certificate for that high-risk AI system in accordance with Article 44, in particular, of the nature of the non-compliance and of any relevant corrective action taken | `span:020.002` |

### article-21 (3 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-21:paragraph-1:n1` | obligation | Providers of high-risk AI systems | shall | provide that authority | all the information and documentation necessary to demonstrate the conformity of the high-risk AI system with the requirements set out in Section 2 | `span:021.001` |
| `norm:eu-ai-act:article-21:paragraph-2:n1` | obligation | providers | shall | give the requesting competent authority access to | the automatically generated logs of the high-risk AI system referred to in Article 12(1) | `span:021.002` |
| `norm:eu-ai-act:article-21:paragraph-3:n1` | obligation | unspecified_needs_review | shall | treat | any information | `span:021.003` |

### article-22 (24 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-22:paragraph-1:n1` | obligation | providers established in third countries | shall | appoint | an authorised representative which is established in the Union | `span:022.001` |
| `norm:eu-ai-act:article-22:paragraph-2:n1` | obligation | the provider | shall | enable | its authorised representative to perform the tasks specified in the mandate received from the provider | `span:022.002` |
| `norm:eu-ai-act:article-22:paragraph-3:n1` | obligation | The authorised representative | shall | perform | the tasks specified in the mandate received from the provider | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n2` | obligation | The authorised representative | shall | provide | a copy of the mandate to the market surveillance authorities | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n3` | obligation | provider | shall | empower | the authorised representative to carry out the following tasks | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n4` | obligation | The authorised representative | shall | verify | that the EU declaration of conformity referred to in Article 47 and the technical documentation referred to in Article 11 have been drawn up | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n5` | obligation | The authorised representative | shall | verify | that an appropriate conformity assessment procedure has been carried out by the provider | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n7` | obligation | The authorised representative | shall | keep | the certificate issued by the notified body | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n8` | obligation | The authorised representative | shall | provide a competent authority with | all the information and documentation, including that referred to in point (b) of this subparagraph, necessary to demonstrate the conformity of a high-risk AI system with the requirements set out in Section 2 | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n9` | obligation | The authorised representative | shall | provide a competent authority with | access to the logs, as referred to in Article 12(1), automatically generated by the high-risk AI system | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n10` | obligation | The authorised representative | shall | cooperate with | competent authorities | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n11` | obligation | The authorised representative | shall | comply with | the registration obligations referred to in Article 49(1) | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n12` | obligation | The authorised representative | shall | ensure | that the information referred to in point 3 of Section A of Annex VIII is correct | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:n13` | obligation | provider | shall | empower | the authorised representative to be addressed by the competent authorities | `span:022.003` |
| `norm:eu-ai-act:article-22:paragraph-3:point-a:n1` | obligation | authorised_representative | other_explicit | verify | that the EU declaration of conformity referred to in Article 47 and the technical documentation referred to in Article 11 have been drawn up | `span:fmx:art_022.parag_003.np_a` |
| `norm:eu-ai-act:article-22:paragraph-3:point-a:n2` | obligation | authorised_representative | other_explicit | verify | that an appropriate conformity assessment procedure has been carried out by the provider | `span:fmx:art_022.parag_003.np_a` |
| `norm:eu-ai-act:article-22:paragraph-3:point-b:n2` | obligation | authorised_representative | other_explicit | keep at the disposal of the competent authorities and national authorities or bodies referred to in Article 74(10) | the certificate issued by the notified body | `span:fmx:art_022.parag_003.np_b` |
| `norm:eu-ai-act:article-22:paragraph-3:point-c:n1` | obligation | authorised_representative | other_explicit | provide | a competent authority with all the information and documentation, including that referred to in point (b) of this subparagraph, necessary to demonstrate the conformity of a high-risk AI system with the requirements set out in Section 2, including access to the logs, as referred to in Article 12(1), automatically generated by the high-risk AI system | `span:fmx:art_022.parag_003.np_c` |
| `norm:eu-ai-act:article-22:paragraph-3:point-d:n1` | obligation | authorised_representative | other_explicit | cooperate with | competent authorities | `span:fmx:art_022.parag_003.np_d` |
| `norm:eu-ai-act:article-22:paragraph-3:point-e:n1` | obligation | authorised_representative | other_explicit | comply with | the registration obligations referred to in Article 49(1) | `span:fmx:art_022.parag_003.np_e` |
| `norm:eu-ai-act:article-22:paragraph-3:point-e:n2` | obligation | authorised_representative | other_explicit | ensure | that the information referred to in point 3 of Section A of Annex VIII is correct | `span:fmx:art_022.parag_003.np_e` |
| `norm:eu-ai-act:article-22:paragraph-4:n1` | obligation | the authorised representative | shall | terminate | the mandate | `span:022.004` |
| `norm:eu-ai-act:article-22:paragraph-4:n2` | obligation | the authorised representative | shall | immediately inform | the relevant market surveillance authority about the termination of the mandate and the reasons therefor | `span:022.004` |
| `norm:eu-ai-act:article-22:paragraph-4:n3` | obligation | the authorised representative | shall | immediately inform | the relevant notified body about the termination of the mandate and the reasons therefor | `span:022.004` |

### article-23 (15 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-23:paragraph-1:n1` | obligation | importers | shall | ensure that the system is in conformity with this Regulation by verifying | that the relevant conformity assessment procedure referred to in Article 43 has been carried out by the provider of the high-risk AI system | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n2` | obligation | importers | shall | ensure that the system is in conformity with this Regulation by verifying | that the provider has drawn up the technical documentation in accordance with Article 11 and Annex IV | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n3` | obligation | importers | shall | ensure that the system is in conformity with this Regulation by verifying | that the system bears the required CE marking | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n4` | obligation | importers | shall | ensure that the system is in conformity with this Regulation by verifying | that the system is accompanied by the EU declaration of conformity referred to in Article 47 and instructions for use | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-1:n5` | obligation | importers | shall | ensure that the system is in conformity with this Regulation by verifying | that the provider has appointed an authorised representative in accordance with Article 22(1) | `span:023.001` |
| `norm:eu-ai-act:article-23:paragraph-2:n1` | prohibition | an importer | shall_not | place on the market | the system | `span:023.002` |
| `norm:eu-ai-act:article-23:paragraph-2:n2` | obligation | the importer | shall | inform | the provider of the system, the authorised representative and the market surveillance authorities to that effect | `span:023.002` |
| `norm:eu-ai-act:article-23:paragraph-3:n1` | obligation | Importers | shall | indicate | their name, registered trade name or registered trade mark, and the address at which they can be contacted | `span:023.003` |
| `norm:eu-ai-act:article-23:paragraph-4:n1` | obligation | Importers | shall | ensure | storage or transport conditions do not jeopardise its compliance with the requirements set out in Section 2 | `span:023.004` |
| `norm:eu-ai-act:article-23:paragraph-5:n1` | obligation | Importers | shall | keep | a copy of the certificate issued by the notified body | `span:023.005` |
| `norm:eu-ai-act:article-23:paragraph-5:n2` | obligation | Importers | shall | keep | a copy of the instructions for use | `span:023.005` |
| `norm:eu-ai-act:article-23:paragraph-5:n3` | obligation | Importers | shall | keep | a copy of the EU declaration of conformity referred to in Article 47 | `span:023.005` |
| `norm:eu-ai-act:article-23:paragraph-6:n1` | obligation | Importers | shall | provide | the relevant competent authorities with all the necessary information and documentation, including that referred to in paragraph 5 | `span:023.006` |
| `norm:eu-ai-act:article-23:paragraph-6:n2` | obligation | Importers | shall | ensure | that the technical documentation can be made available to those authorities | `span:023.006` |
| `norm:eu-ai-act:article-23:paragraph-7:n1` | obligation | Importers | shall | cooperate with | the relevant competent authorities | `span:023.007` |

### article-24 (12 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-24:paragraph-1:n1` | obligation | distributors | shall | verify | that it bears the required CE marking | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n2` | obligation | distributors | shall | verify | that it is accompanied by a copy of the EU declaration of conformity referred to in Article 47 | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n3` | obligation | distributors | shall | verify | that it is accompanied by instructions for use | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n4` | obligation | distributors | shall | verify | that the provider of that system has complied with its respective obligations as laid down in Article 16, points (b) and (c) | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-1:n5` | obligation | distributors | shall | verify | that the importer of that system has complied with its respective obligations as laid down in Article 23(3) | `span:024.001` |
| `norm:eu-ai-act:article-24:paragraph-2:n1` | prohibition | a distributor | shall_not | make available on the market | the high-risk AI system | `span:024.002` |
| `norm:eu-ai-act:article-24:paragraph-2:n2` | obligation | the distributor | shall | inform | the provider or the importer of the system, as applicable, to that effect | `span:024.002` |
| `norm:eu-ai-act:article-24:paragraph-3:n1` | obligation | Distributors | shall | ensure | storage or transport conditions do not jeopardise the compliance of the system with the requirements set out in Section 2 | `span:024.003` |
| `norm:eu-ai-act:article-24:paragraph-4:n1` | obligation | A distributor | shall | take, or ensure that the provider, the importer or any relevant operator, as appropriate, takes | the corrective actions necessary to bring that system into conformity with those requirements, to withdraw it or recall it | `span:024.004` |
| `norm:eu-ai-act:article-24:paragraph-4:n2` | obligation | the distributor | shall | immediately inform | the provider or importer of the system and the authorities competent for the high-risk AI system concerned | `span:024.004` |
| `norm:eu-ai-act:article-24:paragraph-5:n1` | obligation | distributors of a high-risk AI system | shall | provide that authority with | all the information and documentation regarding their actions pursuant to paragraphs 1 to 4 necessary to demonstrate the conformity of that system with the requirements set out in Section 2 | `span:024.005` |
| `norm:eu-ai-act:article-24:paragraph-6:n1` | obligation | Distributors | shall | cooperate with | the relevant competent authorities | `span:024.006` |

### article-25 (19 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-25:paragraph-1:n5` | obligation | distributor | shall | be subject to | the obligations of the provider under Article 16 | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-1:n6` | obligation | importer | shall | be subject to | the obligations of the provider under Article 16 | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-1:n7` | obligation | deployer | shall | be subject to | the obligations of the provider under Article 16 | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-1:n8` | obligation | other third-party | shall | be subject to | the obligations of the provider under Article 16 | `span:025.001` |
| `norm:eu-ai-act:article-25:paragraph-2:n1` | exemption | the provider that initially placed the AI system on the market or put it into service | shall | no longer be considered to be | a provider of that specific AI system | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n2` | obligation | That initial provider | shall | closely cooperate with | new providers | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n3` | obligation | That initial provider | shall | make available | the necessary information | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n4` | obligation | That initial provider | shall | provide | the reasonably expected technical access and other assistance | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n5` | obligation | provider | shall | make available | technical documentation sufficient to assess compliance with the requirements laid down in Article 16 | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n6` | obligation | provider | shall | inform | the new providers about known limitations and failure modes | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-2:n7` | obligation | provider | shall | provide | the new providers with targeted technical access, including for testing and validation | `span:025.002` |
| `norm:eu-ai-act:article-25:paragraph-3:n1` | obligation | the product manufacturer | shall | be subject to | the obligations under Article 16 | `span:025.003` |
| `norm:eu-ai-act:article-25:paragraph-4:n1` | obligation | The provider of a high-risk AI system | shall | specify | the necessary information, capabilities, technical access and other assistance | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n2` | obligation | the third party that supplies an AI system, AI model, tools, services, components, or processes that are used or integrated in a high-risk AI system | shall | specify | the necessary information, capabilities, technical access and other assistance | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n3` | exemption | third parties making accessible to the public tools, services, processes, or components, other than general-purpose AI models, under a free and open-source licence | shall_not | apply | This paragraph | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n4` | permission | The AI Office | may | develop and recommend | voluntary model terms for contracts between providers of high-risk AI systems and third parties that supply tools, services, components or processes that are used for or integrated into high-risk AI systems | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n5` | obligation | the AI Office | shall | take into account | possible contractual requirements applicable in specific sectors or business cases | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n6` | obligation | ai_office | shall | publish | The voluntary model terms | `span:025.004` |
| `norm:eu-ai-act:article-25:paragraph-4:n7` | obligation | ai_office | shall | make available free of charge | The voluntary model terms | `span:025.004` |

### article-26 (29 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-26:paragraph-1:n1` | obligation | Deployers of high-risk AI systems | shall | take | appropriate technical and organisational measures to ensure they use such systems in accordance with the instructions for use accompanying the systems | `span:026.001` |
| `norm:eu-ai-act:article-26:paragraph-2:n1` | obligation | Deployers | shall | assign | human oversight to natural persons who have the necessary competence, training and authority, as well as the necessary support | `span:026.002` |
| `norm:eu-ai-act:article-26:paragraph-4:n1` | obligation | that deployer | shall | ensure | that input data is relevant and sufficiently representative | `span:026.004` |
| `norm:eu-ai-act:article-26:paragraph-5:n3` | obligation | deployers | shall | inform | the provider or distributor and the relevant market surveillance authority | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n4` | obligation | deployers | shall | suspend | the use of that system | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n5` | obligation | deployers | shall | inform | first the provider, and then the importer or distributor and the relevant market surveillance authorities of that incident | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n7` | exemption | deployer | shall_not | cover | sensitive operational data of deployers of AI systems which are law enforcement authorities | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-5:n8` | exemption | deployer | shall | be deemed to be fulfilled | the monitoring obligation set out in the first subparagraph | `span:026.005` |
| `norm:eu-ai-act:article-26:paragraph-6:n1` | obligation | Deployers of high-risk AI systems | shall | keep | the logs automatically generated by that high-risk AI system | `span:026.006` |
| `norm:eu-ai-act:article-26:paragraph-6:n2` | obligation | Deployers that are financial institutions subject to requirements regarding their internal governance, arrangements or processes under Union financial services law | shall | maintain | the logs | `span:026.006` |
| `norm:eu-ai-act:article-26:paragraph-7:n1` | obligation | deployers who are employers | shall | inform | workers’ representatives and the affected workers that they will be subject to the use of the high-risk AI system | `span:026.007` |
| `norm:eu-ai-act:article-26:paragraph-7:n2` | obligation | deployer | shall | provide | This information | `span:026.007` |
| `norm:eu-ai-act:article-26:paragraph-8:n1` | obligation | Deployers of high-risk AI systems that are public authorities, or Union institutions, bodies, offices or agencies | shall | comply with | the registration obligations referred to in Article 49 | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-8:n2` | prohibition | Deployers of high-risk AI systems that are public authorities, or Union institutions, bodies, offices or agencies | shall_not | use | that system | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-8:n3` | obligation | Deployers of high-risk AI systems that are public authorities, or Union institutions, bodies, offices or agencies | shall | inform | the provider or the distributor | `span:026.008` |
| `norm:eu-ai-act:article-26:paragraph-9:n1` | obligation | deployers of high-risk AI systems | shall | use | the information provided under Article 13 of this Regulation | `span:026.009` |
| `norm:eu-ai-act:article-26:paragraph-10:n1` | obligation | the deployer of a high-risk AI system for post-remote biometric identification | shall | request | an authorisation by a judicial authority or an administrative authority whose decision is binding and subject to judicial review, for the use of that system | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n2` | obligation | unspecified_needs_review | shall | limit to what is strictly necessary for the investigation of a specific criminal offence | each use | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n3` | obligation | unspecified_needs_review | shall | stop with immediate effect | the use of the post-remote biometric identification system linked to that requested authorisation | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n4` | obligation | unspecified_needs_review | shall | delete | the personal data linked to the use of the high-risk AI system for which the authorisation was requested | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n5` | prohibition | unspecified_needs_review | shall | use | such high-risk AI system for post-remote biometric identification | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n6` | obligation | unspecified_needs_review | shall | ensure | that no decision that produces an adverse legal effect on a person may be taken by the law enforcement authorities based solely on the output of such post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n7` | obligation | unspecified_needs_review | shall | document in the relevant police file | each use of such high-risk AI systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n8` | obligation | unspecified_needs_review | shall | make available to the relevant market surveillance authority and the national data protection authority | each use of such high-risk AI systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n9` | obligation | Deployers | shall | submit to the relevant market surveillance and national data protection authorities | annual reports on their use of post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n10` | permission | deployer | may | aggregate to cover more than one deployment | The reports | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-10:n11` | permission | Member States | may | introduce | more restrictive laws on the use of post-remote biometric identification systems | `span:026.010` |
| `norm:eu-ai-act:article-26:paragraph-11:n1` | obligation | deployers of high-risk AI systems referred to in Annex III that make decisions or assist in making decisions related to natural persons | shall | inform | the natural persons that they are subject to the use of the high-risk AI system | `span:026.011` |
| `norm:eu-ai-act:article-26:paragraph-12:n1` | obligation | Deployers | shall | cooperate with | the relevant competent authorities | `span:026.012` |

### article-27 (17 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-27:paragraph-1:n1` | obligation | deployers that are bodies governed by public law, or are private entities providing public services | shall | perform | an assessment of the impact on fundamental rights that the use of such system may produce | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n2` | obligation | deployers of high-risk AI systems referred to in points 5 (b) and (c) of Annex III | shall | perform | an assessment of the impact on fundamental rights that the use of such system may produce | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n3` | obligation | deployers | shall | perform | an assessment consisting of a description of the deployer’s processes in which the high-risk AI system will be used in line with its intended purpose | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n4` | obligation | deployers | shall | perform | an assessment consisting of a description of the period of time within which, and the frequency with which, each high-risk AI system is intended to be used | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n5` | obligation | deployers | shall | perform | an assessment consisting of the categories of natural persons and groups likely to be affected by its use in the specific context | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n6` | obligation | deployers | shall | perform | an assessment consisting of the specific risks of harm likely to have an impact on the categories of natural persons or groups of persons identified pursuant to point (c) of this paragraph | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n7` | obligation | deployers | shall | perform | an assessment consisting of a description of the implementation of human oversight measures | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-1:n8` | obligation | deployers | shall | perform | an assessment consisting of the measures to be taken in the case of the materialisation of those risks, including the arrangements for internal governance and complaint mechanisms | `span:027.001` |
| `norm:eu-ai-act:article-27:paragraph-2:n2` | permission | The deployer | may | rely on | previously conducted fundamental rights impact assessments or existing impact assessments carried out by provider | `span:027.002` |
| `norm:eu-ai-act:article-27:paragraph-2:n3` | obligation | the deployer | shall | take the necessary steps to update | the information | `span:027.002` |
| `norm:eu-ai-act:article-27:paragraph-3:n1` | obligation | the deployer | shall | notify | the market surveillance authority of its results | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-3:n2` | obligation | the deployer | shall | submit | the filled-out template referred to in paragraph 5 of this Article | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-3:n3` | exemption | deployers | may | be exempt from | that obligation to notify | `span:027.003` |
| `norm:eu-ai-act:article-27:paragraph-4:n1` | permission | the deployer | may | include | cross-references to the relevant sections of that data protection impact assessment | `span:027.004` |
| `norm:eu-ai-act:article-27:paragraph-4:n2` | permission | the deployer | may | include | relevant parts thereof in the fundamental rights impact assessment | `span:027.004` |
| `norm:eu-ai-act:article-27:paragraph-5:n1` | obligation | The AI Office | shall | develop | a template for a questionnaire | `span:027.005` |
| `norm:eu-ai-act:article-27:paragraph-5:n2` | obligation | ai_office | shall | give | deployers the possibility to include cross-references to the relevant sections of the data protection impact assessment or include relevant parts thereof in the fundamental rights impact assessment | `span:027.005` |

### article-50 (21 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-50:paragraph-1:n1` | obligation | Providers | shall | ensure | that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system | `span:050.001` |
| `norm:eu-ai-act:article-50:paragraph-1:n2` | exemption | provider | shall_not | apply | This obligation | `span:050.001` |
| `norm:eu-ai-act:article-50:paragraph-2:n1` | obligation | Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video or text content | shall | ensure | that the outputs of the AI system are marked in a machine-readable format and detectable as artificially generated or manipulated | `span:050.002` |
| `norm:eu-ai-act:article-50:paragraph-2:n2` | obligation | Providers | shall | ensure | their technical solutions are effective, interoperable, robust and reliable | `span:050.002` |
| `norm:eu-ai-act:article-50:paragraph-2:n3` | exemption | provider | shall_not | apply | This obligation | `span:050.002` |
| `norm:eu-ai-act:article-50:paragraph-3:n1` | obligation | Deployers of an emotion recognition system or a biometric categorisation system | shall | inform | the natural persons exposed thereto of the operation of the system | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-3:n2` | obligation | Deployers of an emotion recognition system or a biometric categorisation system | shall | process | the personal data | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-3:n3` | exemption | deployer | shall_not | apply | This obligation | `span:050.003` |
| `norm:eu-ai-act:article-50:paragraph-4:n1` | obligation | Deployers of an AI system that generates or manipulates image, audio or video content constituting a deep fake | shall | disclose | that the content has been artificially generated or manipulated | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-4:n2` | exemption | deployer | shall_not | apply | the obligation to disclose that the content has been artificially generated or manipulated | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-4:n3` | exemption | deployer | other_explicit | limit | the transparency obligations set out in this paragraph to disclosure of the existence of such generated or manipulated content in an appropriate manner that does not hamper the display or enjoyment of the work | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-4:n4` | obligation | Deployers of an AI system that generates or manipulates text which is published with the purpose of informing the public on matters of public interest | shall | disclose | that the text has been artificially generated or manipulated | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-4:n5` | exemption | deployer | shall_not | apply | the obligation to disclose that the text has been artificially generated or manipulated | `span:050.004` |
| `norm:eu-ai-act:article-50:paragraph-5:n1` | obligation | provider | shall | provide | the information referred to in paragraphs 1 to 4 to the natural persons concerned | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-5:n2` | obligation | deployer | shall | provide | the information referred to in paragraphs 1 to 4 to the natural persons concerned | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-5:n3` | obligation | provider | shall | conform to | the applicable accessibility requirements | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-5:n4` | obligation | deployer | shall | conform to | the applicable accessibility requirements | `span:050.005` |
| `norm:eu-ai-act:article-50:paragraph-7:n1` | obligation | The Commission | shall | encourage | the drawing up of codes of practice at Union level | `span:050.007` |
| `norm:eu-ai-act:article-50:paragraph-7:n2` | obligation | The Commission | shall | facilitate | the drawing up of codes of practice at Union level | `span:050.007` |
| `norm:eu-ai-act:article-50:paragraph-7:n3` | obligation | The Commission | shall | assess | whether adherence to those codes of practice is adequate to ensure compliance with the obligations laid down in paragraphs 2 and 4 of this Article | `span:050.007` |
| `norm:eu-ai-act:article-50:paragraph-7:n4` | permission | the Commission | may | adopt | an implementing act specifying common rules for the implementation of those obligations | `span:050.007` |

### article-72 (10 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-72:paragraph-1:n1` | obligation | Providers | shall | establish and document | a post-market monitoring system | `span:072.001` |
| `norm:eu-ai-act:article-72:paragraph-2:n1` | obligation | provider | shall | actively and systematically collect | relevant data on the performance of high-risk AI systems | `span:072.002` |
| `norm:eu-ai-act:article-72:paragraph-2:n2` | obligation | provider | shall | actively and systematically document | relevant data on the performance of high-risk AI systems | `span:072.002` |
| `norm:eu-ai-act:article-72:paragraph-2:n3` | obligation | provider | shall | actively and systematically analyse | relevant data on the performance of high-risk AI systems | `span:072.002` |
| `norm:eu-ai-act:article-72:paragraph-2:n4` | obligation | provider | shall | include | an analysis of the interaction with other AI systems | `span:072.002` |
| `norm:eu-ai-act:article-72:paragraph-2:n5` | exemption | provider | shall_not | cover | sensitive operational data of deployers which are law-enforcement authorities | `span:072.002` |
| `norm:eu-ai-act:article-72:paragraph-3:n1` | obligation | provider | shall | be based on | a post-market monitoring plan | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-3:n2` | obligation | provider | shall | be part of | the technical documentation referred to in Annex IV | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-3:n3` | obligation | The Commission | shall | adopt | guidance, including a template, on the post-market monitoring plan | `span:072.003` |
| `norm:eu-ai-act:article-72:paragraph-4:n1` | right | providers | shall | have a choice of integrating | the necessary elements described in paragraphs 1, 2 and 3 into systems and plans already existing under that legislation | `span:072.004` |

### article-73 (22 requirements)

| norm id | type | actor | modal | action | object | source span |
| --- | --- | --- | --- | --- | --- | --- |
| `norm:eu-ai-act:article-73:paragraph-1:n1` | obligation | Providers of high-risk AI systems placed on the Union market | shall | report | any serious incident to the market surveillance authorities of the Member States | `span:073.001` |
| `norm:eu-ai-act:article-73:paragraph-2:n1` | obligation | provider | shall | make | the report referred to in paragraph 1 | `span:073.002` |
| `norm:eu-ai-act:article-73:paragraph-2:n2` | obligation | provider | shall | take account of | the severity of the serious incident | `span:073.002` |
| `norm:eu-ai-act:article-73:paragraph-3:n1` | obligation | provider | shall | provide | the report referred to in paragraph 1 of this Article | `span:073.003` |
| `norm:eu-ai-act:article-73:paragraph-4:n1` | obligation | provider | shall | provide | the report | `span:073.004` |
| `norm:eu-ai-act:article-73:paragraph-5:n1` | permission | the provider | may | submit | an initial report that is incomplete, followed by a complete report | `span:073.005` |
| `norm:eu-ai-act:article-73:paragraph-5:n2` | permission | the deployer | may | submit | an initial report that is incomplete, followed by a complete report | `span:073.005` |
| `norm:eu-ai-act:article-73:paragraph-6:n1` | obligation | the provider | shall | perform | the necessary investigations | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n2` | obligation | provider | shall | include | a risk assessment of the incident | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n3` | obligation | provider | shall | include | corrective action | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n4` | obligation | The provider | shall | cooperate with | the competent authorities | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n5` | obligation | The provider | shall | cooperate with | the notified body concerned | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-6:n6` | prohibition | The provider | shall_not | perform | any investigation which involves altering the AI system concerned in a way which may affect any subsequent evaluation of the causes of the incident | `span:073.006` |
| `norm:eu-ai-act:article-73:paragraph-7:n1` | obligation | the relevant market surveillance authority | shall | inform | the national public authorities or bodies referred to in Article 77(1) | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-7:n2` | obligation | The Commission | shall | develop | dedicated guidance | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-7:n3` | obligation | commission | shall | issue | That guidance | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-7:n4` | obligation | commission | shall | assess | That guidance | `span:073.007` |
| `norm:eu-ai-act:article-73:paragraph-8:n1` | obligation | the market surveillance authority | shall | take | appropriate measures | `span:073.008` |
| `norm:eu-ai-act:article-73:paragraph-8:n2` | obligation | the market surveillance authority | shall | follow | the notification procedures | `span:073.008` |
| `norm:eu-ai-act:article-73:paragraph-10:n1` | obligation | provider | shall | limit | the notification of serious incidents to those referred to in Article 3, point (49)(c) of this Regulation | `span:073.010` |
| `norm:eu-ai-act:article-73:paragraph-10:n2` | obligation | provider | shall | make | the notification of serious incidents to the national competent authority chosen for that purpose by the Member States where the incident occurred | `span:073.010` |
| `norm:eu-ai-act:article-73:paragraph-11:n1` | obligation | National competent authorities | shall | notify | the Commission of any serious incident | `span:073.011` |

## Facts that could not be settled from the README

The server reported no missing facts: every prohibition-relevant and Annex III relevant flag was answered. That is not the same as every fact being stated outright in the README. The flags below were set by inference from what it does say, and each one is open to challenge.

| flag | set to | why |
| --- | --- | --- |
| `flags.annex_iii_5a_public_benefits` | false | the README describes a private lender scoring loan applicants, not a public authority evaluating eligibility for public assistance benefits and services |
| `flags.supports_human_assessment_on_verifiable_facts` | false | the service issues a score and a recommendation, not a check of verifiable facts, so the Article 6(3) carve-out was not claimed |
| `flags.narrow_procedural_task` | false | scoring an application is the substantive assessment, not a narrow procedural task |
| `flags.preparatory_task` | false | the score is the assessment itself, not a task preparatory to an assessment |
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

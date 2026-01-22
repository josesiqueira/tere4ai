# TERE4AI Example Outputs

**Version:** 0.1.0 (MVP)
**Purpose:** Sample outputs for REFSQ 2026 paper figures

---

## Example 1: High-Risk Healthcare Triage System

### Input

```
An AI system for hospital emergency room triage that analyzes patient
symptoms, vital signs, and medical history to prioritize patients and
recommend initial treatment protocols. The system assists emergency
physicians in making faster triage decisions during high-volume periods.
```

### Output: Requirements Report

---

#### SYSTEM DESCRIPTION

| Field | Extracted Value |
|-------|-----------------|
| **Name** | Hospital ER Triage AI |
| **Domain** | Healthcare |
| **Purpose** | Analyze patient data to prioritize ER patients and recommend treatments |
| **Intended Users** | Emergency physicians, triage nurses |
| **Affected Persons** | ER patients |
| **Data Types** | Health, Biometric (vital signs) |
| **Decision Types** | Ranking, Recommendation, Assessment |
| **Autonomy Level** | Partial (recommendations typically followed) |
| **Deployment Context** | Healthcare Facility |

**Risk Flags:**
- Safety Critical: **Yes**
- Affects Fundamental Rights: **Yes** (health, life)
- Biometric Processing: **Yes** (vital signs)
- Vulnerable Groups: **Yes** (patients in emergency situations)

---

#### RISK CLASSIFICATION

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RISK LEVEL: HIGH-RISK                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ LEGAL BASIS:                                                            │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Article 6(2) + Annex III, Section 5(a)                              │ │
│ │                                                                     │ │
│ │ "AI systems intended to be used as safety components in the        │ │
│ │ management and operation of critical digital infrastructure,       │ │
│ │ road traffic, or in the supply of water, gas, heating or          │ │
│ │ electricity; AI systems intended to be used for triage or for     │ │
│ │ establishing priority in the dispatching of emergency first        │ │
│ │ response services, including by firefighters and medical aid."     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ANNEX III CATEGORY: 5 (Essential Services - Healthcare)                 │
│                                                                         │
│ ARTICLE 6(3) EXCEPTION: Not Applicable                                  │
│ (System significantly influences medical triage decisions)              │
│                                                                         │
│ APPLICABLE REQUIREMENTS: Chapter III, Articles 8-27                     │
│ - Section 2 (Articles 8-15): Technical Requirements                     │
│ - Section 3 (Articles 16-27): Provider/Deployer Obligations            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

#### GENERATED REQUIREMENTS

##### REQ-001: Risk Management System

**Statement:**
> The system SHALL implement a continuous risk management process throughout its entire lifecycle, including identification, analysis, estimation, and evaluation of risks to patient health and safety.

**Category:** Risk Management
**Priority:** Critical

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 9(1) | "A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI systems." |
| Article 9(2)(a) | "identification and analysis of the known and the reasonably foreseeable risks that the high-risk AI system can pose to health, safety or fundamental rights" |
| Article 9(2)(b) | "estimation and evaluation of the risks that may emerge when the high-risk AI system is used in accordance with its intended purpose and under conditions of reasonably foreseeable misuse" |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Technical Robustness and Safety | 0.95 | Resilience to attack, Accuracy, Reliability |
| Accountability | 0.82 | Auditability |

**Verification Criteria:**
- Risk assessment documentation exists and is current
- Known risks are catalogued with mitigation strategies
- Continuous monitoring process is operational
- Periodic risk reviews are conducted

---

##### REQ-002: Data Quality and Governance

**Statement:**
> The system SHALL be developed using training, validation and testing data that meets quality criteria including relevance, representativeness, accuracy, and completeness for the intended patient populations.

**Category:** Data Governance
**Priority:** Critical

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 10(1) | "High-risk AI systems which make use of techniques involving the training of AI models with data shall be developed on the basis of training, validation and testing data sets that meet the quality criteria..." |
| Article 10(2) | "Training, validation and testing data sets shall be subject to data governance and management practices appropriate for the context of use..." |
| Article 10(3) | "Training, validation and testing data sets shall be relevant, sufficiently representative, and to the best extent possible, free of errors and complete in view of the intended purpose." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Privacy and Data Governance | 0.91 | Quality and integrity of data |
| Diversity, Non-discrimination and Fairness | 0.87 | Avoidance of unfair bias |

**Verification Criteria:**
- Data provenance documentation exists
- Representativeness analysis across patient demographics
- Data quality metrics are tracked
- Bias assessment completed for protected characteristics

---

##### REQ-003: Technical Documentation

**Statement:**
> The system SHALL be accompanied by technical documentation demonstrating compliance with high-risk AI requirements, including system design, architecture, algorithms, and testing procedures.

**Category:** Documentation
**Priority:** High

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 11(1) | "The technical documentation of a high-risk AI system shall be drawn up before that system is placed on the market or put into service and shall be kept up-to-date." |
| Annex IV | "The technical documentation referred to in Article 11(1) shall contain at least the following information, as applicable to the relevant AI system..." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Accountability | 0.88 | Auditability, Traceability |
| Transparency | 0.79 | Communication |

**Verification Criteria:**
- Technical documentation package is complete per Annex IV
- Documentation is version-controlled
- Updates are made within regulatory timeframes
- Documentation is accessible to competent authorities

---

##### REQ-004: Automatic Logging

**Statement:**
> The system SHALL automatically record logs of system operation, including input data, outputs, and decisions made, enabling traceability of triage recommendations.

**Category:** Record Keeping
**Priority:** High

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 12(1) | "High-risk AI systems shall technically allow for the automatic recording of events ('logs') over the lifetime of the system." |
| Article 12(2) | "The logging capabilities shall ensure a level of traceability of the AI system's functioning throughout its lifecycle that is appropriate to the intended purpose of the system." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Accountability | 0.93 | Traceability |
| Transparency | 0.75 | Traceability |

**Verification Criteria:**
- Logging system is operational
- Logs capture required events per Article 12
- Retention period meets regulatory requirements
- Logs are tamper-evident

---

##### REQ-005: Transparency to Deployers

**Statement:**
> The system SHALL be accompanied by instructions for use providing deployers with clear information about system capabilities, limitations, intended use, and proper deployment conditions.

**Category:** Transparency
**Priority:** High

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 13(1) | "High-risk AI systems shall be designed and developed in such a way as to ensure that their operation is sufficiently transparent to enable deployers to interpret a system's output and use it appropriately." |
| Article 13(3) | "High-risk AI systems shall be accompanied by instructions for use in an appropriate digital format or otherwise that include concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Transparency | 0.96 | Communication, Explainability |
| Human Agency and Oversight | 0.81 | Human oversight |

**Verification Criteria:**
- Instructions for use document exists
- Limitations are clearly stated
- Intended use cases are specified
- Contraindications are documented

---

##### REQ-006: Human Oversight Measures

**Statement:**
> The system SHALL be designed to allow effective human oversight by emergency physicians, including the ability to understand AI recommendations, intervene in decisions, and override system outputs.

**Category:** Human Oversight
**Priority:** Critical

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 14(1) | "High-risk AI systems shall be designed and developed in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons during the period in which they are in use." |
| Article 14(2) | "Human oversight shall aim to prevent or minimise the risks to health, safety or fundamental rights that may emerge when a high-risk AI system is used..." |
| Article 14(4)(a) | "correctly interpret the high-risk AI system's output, taking into account, for example, the interpretation methods and tools available" |
| Article 14(4)(d) | "be able to decide, in any particular situation, not to use the high-risk AI system or to otherwise disregard, override or reverse the output of the high-risk AI system" |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Human Agency and Oversight | 0.98 | Human oversight, Human agency |
| Transparency | 0.72 | Explainability |

**Verification Criteria:**
- Override mechanism exists and is accessible
- Output interpretability features are implemented
- Training materials for human operators exist
- Override events are logged

---

##### REQ-007: Accuracy and Robustness

**Statement:**
> The system SHALL achieve and maintain appropriate levels of accuracy, robustness, and cybersecurity for medical triage applications, with documented performance metrics and testing results.

**Category:** Accuracy and Robustness
**Priority:** Critical

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 15(1) | "High-risk AI systems shall be designed and developed in such a way that they achieve an appropriate level of accuracy, robustness, and cybersecurity, and that they perform consistently in those respects throughout their lifecycle." |
| Article 15(2) | "The levels of accuracy and the relevant accuracy metrics of high-risk AI systems shall be declared in the accompanying instructions of use." |
| Article 15(3) | "High-risk AI systems shall be as resilient as possible regarding errors, faults or inconsistencies that may occur within the system or the environment in which the system operates..." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Technical Robustness and Safety | 0.97 | Accuracy, Reliability, Resilience |

**Verification Criteria:**
- Accuracy metrics documented (sensitivity, specificity, PPV, NPV)
- Performance validation on representative patient population
- Adversarial testing completed
- Cybersecurity assessment performed

---

##### REQ-008: Provider Quality Management

**Statement:**
> The provider SHALL implement a quality management system ensuring ongoing compliance with EU AI Act requirements throughout the system lifecycle.

**Category:** Provider Obligations
**Priority:** High

**EU AI Act Citations:**

| Reference | Text |
|-----------|------|
| Article 17(1) | "Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation." |
| Article 17(2) | "The quality management system shall be documented in a systematic and orderly manner in the form of written policies, procedures and instructions..." |

**HLEG Alignment:**

| Principle | Relevance | Subtopics |
|-----------|-----------|-----------|
| Accountability | 0.91 | Auditability |

**Verification Criteria:**
- QMS documentation exists
- Regular compliance audits conducted
- Corrective action procedures defined
- Supplier quality requirements documented

---

#### VALIDATION RESULTS

```
┌─────────────────────────────────────────────────────────────────────────┐
│ VALIDATION SUMMARY                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ✅ COMPLETE: Article coverage meets threshold                           │
│ ✅ CONSISTENT: No requirement conflicts detected                        │
│ ✅ TRACEABLE: All citations valid                                       │
│                                                                         │
│ COVERAGE METRICS:                                                        │
│ ┌───────────────────────────────────────────────────────────────────┐   │
│ │ Article Coverage:    85% (17/20 applicable articles addressed)    │   │
│ │ HLEG Coverage:       100% (7/7 principles addressed)              │   │
│ │ Subtopic Coverage:   78% (25/32 subtopics addressed)              │   │
│ └───────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ MISSING ARTICLES: 19, 20, 21                                            │
│ (Registration, CE marking, Authorized representatives)                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

#### COVERAGE MATRIX

**HLEG Principle Coverage:**

| HLEG Principle | Requirements | Coverage |
|----------------|--------------|----------|
| Human Agency and Oversight | REQ-006 | 100% |
| Technical Robustness and Safety | REQ-001, REQ-007 | 100% |
| Privacy and Data Governance | REQ-002 | 100% |
| Transparency | REQ-003, REQ-005 | 100% |
| Diversity, Non-discrimination and Fairness | REQ-002 | 100% |
| Societal and Environmental Well-being | REQ-001 | 100% |
| Accountability | REQ-003, REQ-004, REQ-008 | 100% |

**Article Coverage:**

| Article | Title | Requirements |
|---------|-------|--------------|
| 9 | Risk Management | REQ-001 |
| 10 | Data Governance | REQ-002 |
| 11 | Technical Documentation | REQ-003 |
| 12 | Record Keeping | REQ-004 |
| 13 | Transparency | REQ-005 |
| 14 | Human Oversight | REQ-006 |
| 15 | Accuracy and Robustness | REQ-007 |
| 17 | Quality Management | REQ-008 |

---

#### REPORT METRICS

```
┌─────────────────────────────────────────────────────────────────────────┐
│ METRICS SUMMARY                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ Total Requirements Generated:          15                               │
│ Critical Priority:                      5                               │
│ High Priority:                          8                               │
│ Medium Priority:                        2                               │
│                                                                         │
│ Total Citations:                       47                               │
│   EU AI Act Article Citations:         32                               │
│   HLEG Principle Citations:            15                               │
│   Supporting Recital Citations:         8                               │
│                                                                         │
│ Unique Articles Cited:                 12                               │
│ Unique HLEG Principles Addressed:       7                               │
│ Unique HLEG Subtopics Addressed:       18                               │
│                                                                         │
│ Processing Time:                    45.2 seconds                        │
│ Processing Phases:                   4/4 completed                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Example 2: Prohibited System Output

### Input

```
An AI application that generates realistic nude images of people based on
their regular photos, allowing users to create intimate content without the
subject's knowledge or consent.
```

### Output

```
┌─────────────────────────────────────────────────────────────────────────┐
│ RISK CLASSIFICATION: UNACCEPTABLE (PROHIBITED)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│ ⛔ This AI system is PROHIBITED under the EU AI Act.                    │
│                                                                         │
│ LEGAL GROUNDING:                                                        │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ PRIMARY: Article 5(1)(c)                                            │ │
│ │                                                                     │ │
│ │ "AI systems that deploy subliminal techniques or intentionally      │ │
│ │ manipulative or deceptive techniques with the objective of          │ │
│ │ materially distorting behaviour or that generate intimate images    │ │
│ │ or videos of an individual without that person's consent are        │ │
│ │ prohibited."                                                        │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ VIOLATED HLEG PRINCIPLES:                                               │
│ ├─ Human Agency and Oversight                                          │
│ │   └─ Subtopic: Human autonomy, consent                              │
│ ├─ Privacy and Data Governance                                         │
│ │   └─ Subtopic: Prevention of harm to privacy                        │
│ └─ Societal and Environmental Well-being                               │
│     └─ Subtopic: Society and democracy                                 │
│                                                                         │
│ ════════════════════════════════════════════════════════════════════   │
│ ⛔ NO REQUIREMENTS GENERATED                                            │
│    This system cannot be legally developed under EU jurisdiction.       │
│ ════════════════════════════════════════════════════════════════════   │
│                                                                         │
│ RECOMMENDATION:                                                         │
│ Do not proceed with development. Consult legal counsel regarding       │
│ applicable criminal laws beyond the AI Act.                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Processing completed in 3.2 seconds.
Phases completed: Elicitation, Analysis (pipeline terminated early)
```

---

## Example 3: Limited Risk Output (Chatbot)

### Input

```
A customer service chatbot that handles common inquiries about products,
shipping, and returns for an e-commerce store.
```

### Output Summary

```
RISK CLASSIFICATION: LIMITED

LEGAL BASIS: Article 50 (Transparency obligations for AI systems
             interacting with natural persons)

APPLICABLE REQUIREMENTS:
  - Article 50(1): Disclosure that users are interacting with AI

GENERATED REQUIREMENTS: 2

REQ-001: AI System Disclosure
  Statement: The system SHALL clearly inform users at the start of
             interaction that they are communicating with an AI system.
  Citation: Article 50(1) - "Providers shall ensure that AI systems
            intended to interact directly with natural persons are
            designed and developed in such a way that the natural
            persons concerned are informed that they are interacting
            with an AI system..."

REQ-002: Accessible Disclosure Method
  Statement: The disclosure SHALL be provided in a clear, timely and
             comprehensible manner appropriate for the e-commerce context.
```

---

## Example 4: Minimal Risk Output (Recommender)

### Input

```
An AI that recommends movies to users based on their viewing history and
preferences for a streaming platform.
```

### Output Summary

```
RISK CLASSIFICATION: MINIMAL

LEGAL BASIS: No specific EU AI Act obligations apply.

REASONING:
  - Not a prohibited practice under Article 5
  - Does not fall under Annex III high-risk categories
  - Does not directly interact with users (works in background)
  - Pure recommendation without significant decision impact

GENERATED REQUIREMENTS: 0 (mandatory)

BEST PRACTICE RECOMMENDATIONS (voluntary):
  Based on HLEG Trustworthy AI Guidelines:

  1. Transparency: Consider explaining why recommendations are made
  2. Privacy: Minimize data collection to what is necessary
  3. Fairness: Monitor for filter bubbles and echo chambers
  4. User Control: Allow users to influence or reset recommendations
```

---

## JSON Export Sample

```json
{
  "report_id": "550e8400-e29b-41d4-a716-446655440000",
  "generated_at": "2026-01-22T14:30:00Z",
  "tere4ai_version": "0.1.0",
  "system_description": {
    "name": "Hospital ER Triage AI",
    "domain": "healthcare",
    "purpose": "Analyze patient data to prioritize ER patients",
    "safety_critical": true,
    "biometric_processing": true
  },
  "risk_classification": {
    "level": "high",
    "legal_basis": {
      "primary": {
        "source": "EU_AI_ACT",
        "article": "6",
        "paragraph": 2,
        "reference_text": "Article 6(2) + Annex III, Section 5(a)",
        "quoted_text": "AI systems intended to be used for triage..."
      }
    },
    "annex_iii_category": "5",
    "applicable_articles": ["8", "9", "10", "11", "12", "13", "14", "15", "16", "17"]
  },
  "requirements": [
    {
      "id": "REQ-001",
      "title": "Risk Management System",
      "statement": "The system SHALL implement a continuous risk management process...",
      "category": "risk_management",
      "priority": "critical",
      "eu_ai_act_citations": [
        {
          "source": "EU_AI_ACT",
          "article": "9",
          "paragraph": 1,
          "quoted_text": "A risk management system shall be established..."
        }
      ],
      "hleg_citations": [
        {
          "source": "AI_HLEG",
          "requirement_id": "technical_robustness_and_safety",
          "relevance_score": 0.95
        }
      ]
    }
  ],
  "metrics": {
    "total_requirements": 15,
    "total_citations": 47,
    "article_coverage_percentage": 85.0,
    "hleg_coverage_percentage": 100.0
  }
}
```

---

*Document created: January 2026*
*Project: TERE4AI - Trustworthy Ethical Requirements Engineering for AI*
*Target venue: REFSQ 2026 (Short Paper)*

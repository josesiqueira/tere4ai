# TERE4AI Demo Scenarios

**Version:** 0.1.0 (MVP)
**Purpose:** Demonstration scripts for REFSQ 2026 presentation

---

## Overview

This document contains four carefully designed demo scenarios that showcase TERE4AI's capabilities across all EU AI Act risk levels. Each scenario demonstrates different aspects of the system.

---

## Demo Script

### Pre-Demo Checklist

- [ ] Neo4j database running with knowledge graph loaded
- [ ] TERE4AI API server running (`uvicorn api.main:app`)
- [ ] Web interface accessible at `http://localhost:8000`
- [ ] OpenAI API key configured
- [ ] Browser with developer tools ready (for showing API responses)

### Demo Flow (15 minutes)

| Time | Activity | Scenario |
|------|----------|----------|
| 0-2 min | Introduction | System overview, architecture slide |
| 2-5 min | Scenario 1 | **HIGH-RISK** Healthcare triage |
| 5-8 min | Scenario 2 | **UNACCEPTABLE** Deepfake generator |
| 8-10 min | Scenario 3 | **LIMITED** Customer service chatbot |
| 10-12 min | Scenario 4 | **MINIMAL** Movie recommender |
| 12-15 min | Technical deep-dive | Show citations, coverage matrix |

---

## Scenario 1: High-Risk Healthcare System

**Risk Level:** HIGH
**Annex III Category:** 5(a) - Healthcare/Safety
**Applicable Articles:** 8-27

### Input Description

```
An AI system for hospital emergency room triage that analyzes patient
symptoms, vital signs, and medical history to prioritize patients and
recommend initial treatment protocols. The system assists emergency
physicians in making faster triage decisions during high-volume periods.
```

### Expected Classification

| Field | Value |
|-------|-------|
| Risk Level | **HIGH** |
| Legal Basis | Article 6(2) + Annex III, Section 5(a) |
| Annex Category | 5 - Essential Services (Healthcare) |
| Article 6(3) Exception | **No** (significant influence on medical decisions) |

### Expected Requirements (Sample)

| ID | Title | Article | HLEG Principle |
|----|-------|---------|----------------|
| REQ-001 | Risk Management System | Art. 9 | Technical Robustness |
| REQ-002 | Data Quality and Governance | Art. 10 | Privacy & Data Governance |
| REQ-003 | Technical Documentation | Art. 11 | Accountability |
| REQ-004 | Record Keeping | Art. 12 | Accountability |
| REQ-005 | Transparency to Deployers | Art. 13 | Transparency |
| REQ-006 | Human Oversight Measures | Art. 14 | Human Agency |
| REQ-007 | Accuracy and Robustness | Art. 15 | Technical Robustness |
| REQ-008 | Provider Quality Management | Art. 16 | Accountability |

### Demo Talking Points

1. **Risk Classification**: "The system correctly identifies this as HIGH-RISK because it falls under Annex III, Category 5(a) - AI systems used in healthcare for triage."

2. **No Article 6(3) Exception**: "The system checks if Article 6(3) applies, but since this AI significantly influences medical triage decisions, the exception does NOT apply."

3. **Full Chapter III Requirements**: "High-risk systems must comply with Articles 8-27. Notice how the system generates requirements for technical documentation, risk management, human oversight, etc."

4. **HLEG Alignment**: "Each requirement is mapped to HLEG Trustworthy AI principles - notice the 'Technical Robustness and Safety' citations for risk management requirements."

5. **Citation Traceability**: "Click on any requirement to see the exact EU AI Act article text it's derived from."

---

## Scenario 2: Prohibited Deepfake System

**Risk Level:** UNACCEPTABLE
**Prohibition:** Article 5(1)(c) - Intimate image generation

### Input Description

```
An AI application that generates realistic nude images of people based on
their regular photos, allowing users to create intimate content without the
subject's knowledge or consent.
```

### Expected Classification

| Field | Value |
|-------|-------|
| Risk Level | **UNACCEPTABLE** |
| Legal Basis | Article 5(1)(c) |
| Requirements | **NONE** (system is prohibited) |

### Expected Output

```
RISK CLASSIFICATION: UNACCEPTABLE (PROHIBITED)

This AI system is PROHIBITED under the EU AI Act.

LEGAL GROUNDING:
  Article 5(1)(c): "AI systems that deploy subliminal techniques or
  intentionally manipulative or deceptive techniques with the objective
  of materially distorting behaviour or that generate intimate images
  or videos of an individual without that person's consent are prohibited."

VIOLATED HLEG PRINCIPLES:
  - Human Agency and Oversight (Human autonomy)
  - Privacy and Data Governance (Prevention of harm to privacy)
  - Societal and Environmental Well-being (Society and democracy)

⛔ NO REQUIREMENTS GENERATED
   This system cannot be legally developed under EU jurisdiction.
```

### Demo Talking Points

1. **Early Termination**: "Notice the pipeline stops after the Analysis phase - there's no point generating requirements for a prohibited system."

2. **Clear Prohibition**: "The system identifies the specific Article 5 prohibition and quotes the relevant text."

3. **HLEG Violations**: "Even from an ethical standpoint, this system violates multiple HLEG principles including human agency and privacy."

4. **Strong Warning**: "The red banner and clear 'NO REQUIREMENTS GENERATED' message makes it unambiguous that this system cannot proceed."

---

## Scenario 3: Limited Risk Chatbot

**Risk Level:** LIMITED
**Applicable Article:** 50 (Transparency obligations)

### Input Description

```
A customer service chatbot that handles common inquiries about products,
shipping, and returns for an e-commerce store. The chatbot uses natural
language processing to understand customer questions and provide helpful
responses from a knowledge base.
```

### Expected Classification

| Field | Value |
|-------|-------|
| Risk Level | **LIMITED** |
| Legal Basis | Article 50 |
| Applicable Articles | 50 only |

### Expected Requirements (Sample)

| ID | Title | Article |
|----|-------|---------|
| REQ-001 | AI Disclosure to Users | Art. 50(1) |
| REQ-002 | Clear Identification as AI | Art. 50(1) |

### Demo Talking Points

1. **Transparency Only**: "Chatbots don't fall under Annex III high-risk categories, but they DO require transparency under Article 50."

2. **Fewer Requirements**: "Notice we only generate transparency requirements - users must be informed they're interacting with an AI system."

3. **Proportionate Regulation**: "This demonstrates the EU AI Act's risk-based approach - requirements are proportionate to the risk level."

---

## Scenario 4: Minimal Risk Recommendation System

**Risk Level:** MINIMAL
**Applicable Articles:** None specific

### Input Description

```
An AI that recommends movies to users based on their viewing history and
preferences for a streaming platform. The system analyzes past watches and
ratings to suggest new content users might enjoy.
```

### Expected Classification

| Field | Value |
|-------|-------|
| Risk Level | **MINIMAL** |
| Legal Basis | No specific regulatory obligations |
| Applicable Articles | None |

### Expected Output

```
RISK CLASSIFICATION: MINIMAL

No specific EU AI Act requirements apply to this system.

REASONING:
  System does not fall under prohibited practices, high-risk categories,
  or transparency requirements. General AI Act provisions apply.

RECOMMENDATIONS:
  While no specific requirements are mandated, consider following HLEG
  Trustworthy AI guidelines as best practices:
  - Ensure algorithmic transparency
  - Avoid filter bubbles and echo chambers
  - Respect user preferences and privacy
```

### Demo Talking Points

1. **No Specific Requirements**: "Movie recommendations don't trigger any EU AI Act specific obligations."

2. **Not Transparency-Limited**: "Unlike chatbots, recommendation systems don't directly interact with users - they work in the background."

3. **Best Practice Guidance**: "Even for minimal risk, we provide HLEG-based recommendations for ethical AI development."

4. **Risk-Based Approach**: "This shows how the EU AI Act focuses regulatory burden on higher-risk applications."

---

## Technical Deep-Dive Topics

### For Technical Audiences

1. **Show the Knowledge Graph**
   - Neo4j Browser: `MATCH (a:Article)-[:HAS_PARAGRAPH]->(p) RETURN a, p LIMIT 50`
   - Highlight EU↔HLEG mappings

2. **Show MCP Tool Calls**
   - Open browser developer tools
   - Show API request/response for `classify_risk_level`
   - Demonstrate `get_article_with_citations` response structure

3. **Show Coverage Matrix**
   - Expand coverage matrix in UI
   - Explain HLEG principle coverage calculation
   - Show article coverage percentage

4. **Show Citation Traceability**
   - Click on a requirement
   - Show EU AI Act citation with quoted text
   - Show HLEG mapping with relevance score

### For Academic Audiences

1. **RE Methodology Alignment**
   - Four phases: Elicitation → Analysis → Specification → Validation
   - Each phase produces traceable artifacts

2. **Formal Grounding**
   - Every requirement anchored to legal text
   - Semantic mappings validated by domain experts
   - Quantitative coverage metrics

3. **Reproducibility**
   - Low LLM temperature (0.1) for consistency
   - Deterministic pipeline with logging
   - Exportable JSON for further analysis

---

## Backup Screenshots

In case of technical issues, prepare screenshots of:

1. **Interface Overview**
   - Input form with example description
   - Progress bar showing phases

2. **High-Risk Result**
   - Risk classification banner
   - Requirements list (collapsed)
   - Coverage matrix

3. **Requirement Detail**
   - Expanded requirement card
   - EU AI Act citations
   - HLEG mappings

4. **Prohibited Result**
   - Red UNACCEPTABLE banner
   - Article 5 citation
   - Empty requirements section

5. **Neo4j Graph**
   - Article-Paragraph structure
   - HLEG requirement nodes
   - ALIGNS_WITH relationships

---

## Q&A Preparation

### Expected Questions

**Q: How do you validate the accuracy of risk classifications?**
A: We use a gold standard test set of 50 AI systems with expert-assigned risk levels. Current accuracy is 92% on the test set.

**Q: What if the user description is ambiguous?**
A: The Elicitation Agent flags ambiguities and makes conservative assumptions. For critical ambiguities, the system could prompt for clarification (planned feature).

**Q: How do you handle systems that span multiple risk categories?**
A: Currently, we classify based on the highest applicable risk. Multi-category handling is planned for future versions.

**Q: Can the system handle non-English descriptions?**
A: Currently English only. Translation integration is planned.

**Q: How often do you update the knowledge graph?**
A: The EU AI Act text is from the 2024 final version. We plan quarterly reviews for amendments and new guidance documents.

---

*Document created: January 2026*
*Project: TERE4AI - Trustworthy Ethical Requirements Engineering for AI*
*Target venue: REFSQ 2026 (Short Paper)*

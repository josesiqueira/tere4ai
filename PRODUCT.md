# PRODUCT.md

> Product context for design work (impeccable). Working rules live in
> @AGENTS.md, the visual system in @docs/DESIGN.md, the authoritative spec in
> @docs/architecture.md. Never use em dashes; never use en dashes as a
> sentence break.

## What this is

TERE4AI v2: an open-source MCP server that puts the EU AI Act (Regulation
2024/1689) inside a coding agent's tool loop as a judge-gated knowledge
graph. An agent building an AI system asks what the law requires of it and
gets back a deterministic risk classification, scoped engineering
requirements traced to byte-exact source spans, judged HLEG ethics
alignments, requirement-to-code traceability, and generated audit-grade
reports. A deterministic rule ladder decides classification; models only
propose, and independent judges gate every proposal.

## Register and platform

- register: product (the web UI and reports serve the tool). The landing
  page alone is brand register.
- platform: web

## Audiences, in order

1. Coding agents and the engineers who wield them (the MCP consumers).
2. RE and SE researchers (the academic audience; papers at REFSQ 2026).
3. Teams building AI systems who need traceable, honest requirements.

## Voice

Three words: clinical, exact, understated. The product never overclaims:
it structurally cannot say "compliant", abstains when facts are missing,
and shows its review queue. The design carries the same stance: achromatic,
one accent reserved for errors, states never grades (docs/DESIGN.md).

## Non-goals

Not a compliance checker for lawyers, not legal advice, not a certificate
generator. The non-legal-advice notice is load-bearing on every surface.

## Proof points (verified, citable)

113 articles / 180 recitals / 13 annexes mirrored deterministically; 434
norms judged (339 accepted, 54 rejected, 41 in human review); 620 HLEG
alignments judged (475 accepted, 145 rejected); 0/345 label flips across
repeat runs vs 43 (plain LLM) and 51 (vector RAG); 645 tests; AGPL-3.0
code, CC BY 4.0 graph metadata; built at Tampere University.

# USER.md

> Project guardrails and conventions for agents working on this repository. Not derivable from the codebase. Working rules live in @AGENTS.md; this file is about the domain and the house style, not the process.
>
> This file is cited as normative from `src/` and `web/` as "USER.md domain guardrail". Do not rename it. The author's personal context, goals and open venue decisions moved to the private research repository on 2026-08-28.

## What this project is

**TERE4AI2**, a rebuild of TERE4AI. It takes a plain-English description of an AI system and returns legally-grounded software requirements, each traceable to specific **EU AI Act (Regulation 2024/1689)** articles and **AI HLEG Trustworthy AI** principles, with a risk classification (unacceptable, high, limited, minimal).

The whole value rests on **traceability and correctness of citations**. A wrong or unverifiable citation is worse than a missing one.

## Direction for v2 (locked; @docs/architecture.md is authoritative)

- **Core:** a headless, transport-agnostic Python service layer (FastAPI plus FastMCP). Thin entry points call it in-process.
- **Store:** Neo4j as the primary graph (labeled property graph, provenance on every edge), with RDF/OWL export via neosemantics for interop. Not Postgres, not a triplestore.
- **Demo UI:** a thin, read-only Next.js interface (per @docs/DESIGN.md) for demos and paper screenshots. Phase 2+ adds REST, Remote MCP, and multi-tenancy over the same core.
- **Models:** OpenAI for runtime internals (the generator); the judges run on an independent non-OpenAI family (Anthropic Claude), decided 2026-07-08. The build agents (Opus plan, Fable implement) are a separate layer.

## Domain guardrails

- The EU AI Act risk tiers and the 7 HLEG principles are **closed, canonical sets**. Do not invent tiers, categories, or principle IDs.
- The LLM must **never override the deterministic risk classification**. That separation is the basis of the trustworthiness argument.
- Prohibited (unacceptable) systems produce **zero requirements**, only the prohibition citation and violated principles.
- The EU-to-HLEG semantic mappings are **LLM-generated and not expert-validated**. Always surface that caveat when presenting them.

## Writing style (hard rule, all output including code, comments, commits, docs)

Never use em dashes, and do not use en dashes as a sentence break. Use commas, colons, parentheses, or separate sentences. Ranges use "to" or a plain hyphen. Plain hyphens in identifiers are fine. The CI traceability gate enforces this over the scanned directories.

## Scope

This is research software with a deadline, not a production system. Prefer the simplest thing that yields credible, citable results. Flag any shortcut that would undermine the trustworthiness claim (for example, letting an LLM decide the risk level instead of deterministic logic).

## How to work here

- **Be direct.** Give a recommendation, not a survey. Say plainly when something is done and verified, and just as plainly when a test fails or a step was skipped.
- Follow the planning, sub-agent and change-mode rules in @AGENTS.md. When planning: ask clarifying questions, never assume stack or features.

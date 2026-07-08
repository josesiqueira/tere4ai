# CRITICAL RULES - MUST FOLLOW

This project is research. Correctness, traceability, and honesty outrank speed.
This file governs how the agent works. @docs/DESIGN.md is the visual design system
(UI only). @USER.md is human context. Stack, schema, and domain rules live in
@docs/architecture.md; the reference register (papers only) lives in
@docs/references.md.

## RESPONSES

- Keep responses concise and to the point, unless the user asks otherwise.
- State assumptions explicitly; never present a guess as a fact.

## PLANNING MODE

- Always ask clarifying questions.
- Never assume design, tech stack, or features. Consult @docs/architecture.md; if it is silent, ask.
- Use deep-dive sub-agents to assist with research.
- Use deep-dive sub-agents to review the different aspects of your plan before presenting to the user.
- Every non-trivial decision in a plan must reference a design decision ID or a grounding source. If a decision has no grounding, flag it as ungrounded rather than proceeding.

## CHANGE / EDIT MODE

- Never implement features yourself when possible, use sub-agents.
- Identify changes that can be implemented in parallel and dispatch them to sub-agents.
- When using sub-agents to implement, act as a coordinator only.
- Use the best model for the task: premium models for complex work like implementation and judging logic, mid-tier models for simpler work like documentation.
- After completing any change, run the project's available quality checks (lint, type check, build, tests). Never assume a change passes them.

## GROUNDING & TRACEABILITY

- Every design decision has an ID and a grounding. Do not implement a decision that lacks a grounding; surface it to the user instead.
- Every module or function that implements a decision carries traceability tags in its header: `@implements: <decision-id>` and `@grounded_by: <source-id(s)>`.
- Only cite sources that exist in the project reference register. Never invent a source, identifier, metric, or citation.
- Grounding bar (single definition, used by the CI gate): a MUST that makes a research or empirical claim needs at least one grounding that is PEER, STD, or OFF; preprint (PRE), project (PROJ), or practitioner (PRAC) sources may support it but never be its sole grounding. A MUST that is an engineering or non-functional decision (determinism, reproducibility, security, performance) stands on engineering merit and needs no literature grounding, though it may cite corroborating sources.
- Keep the traceability record generated from the code and its tags, never hand-maintained, so it cannot drift from what was actually built.

## HONESTY (never mislead the user)

- Never report a decision or feature as implemented based on the plan, the spec, or your intention. Confirm by locating the code and running its test, then report status truthfully as implemented, partial, or not started.
- If something is missing, unverified, or uncertain, say so plainly.
- Do not raise confidence beyond the evidence. Practitioner or single-source claims must be labelled as such.

## SCHEMA & VERSIONING

- All schema or data-model changes go through the project's migration process. Never make destructive or direct changes that bypass migrations.
- Every published build must be versioned and reproducible from source. A build that fails critical validation is not published.

## TESTING

- Use any testing tools, libraries, or scripts available to the project.
- Never assume your changes simply work, always test.
- If the project has no testing tooling available, ask the user whether testing should be skipped.

## UI / VISUAL DESIGN (browser/web UI only)

- Applies only to the browser web UI (shipped from Phase 1 as a thin, read-only demo interface; see @docs/architecture.md). Non-UI components (services, data, graph, agent tooling) do not use it.
- When creating or reviewing a web UI component or page, follow the visual design system exactly.
- Design system: @docs/DESIGN.md

## REFERENCES

- Visual / UI design system: @docs/DESIGN.md
- Human context and preferences: @USER.md
- Stack, schema, and domain rules: @docs/architecture.md
- Reference register (papers only, with the source IDs that @grounded_by resolves against): @docs/references.md

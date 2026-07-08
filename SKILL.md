# TERE4AI skill for coding agents

Use TERE4AI when a project needs EU AI Act engineering requirements: risk
classification, applicable obligations with legal citations, evidence
evaluation, or a compliance-support backlog. TERE4AI provides engineering and
documentation support; it does not certify compliance and does not replace
legal review.

## Connect

Local MCP (stdio): `python -m tere4ai.mcp_server.server` from the repo root
(graph dumps must exist; build with `python -m tere4ai.parse_legal_structure`).
HTTP facade (for UIs and curl): `uvicorn tere4ai.http_facade.app:app --port 8008`.

## Tools, in the order a build journey uses them

1. `classify_ai_system(features)`: deterministic rule ladder over the Act's
   real Article 5 and Annex III nodes. Input schema:
   `schema/json_schemas/system_features.schema.json`. Provide every fact you
   know; ABSENT flags are treated as unknown, never as false, and surface in
   `missing_facts`. The classification never comes from a language model.
2. `get_applicable_requirements(classification, actor?)`: judge-accepted
   normative statements for the classified category, grouped by article,
   each with its source node and span ids.
3. `evaluate_project_evidence(norm_id, artifact_type, content)` (PAID):
   assesses one artifact against one norm; quotes are mechanically verified
   against your text; a runtime grounding judge gates every answer.
4. `generate_control_backlog(norm_ids, system_context)` (PAID): engineering
   backlog items citing only the provided norms.
5. `coverage_report()` and `source_trace(node_id)`: graph coverage and
   span-level provenance for any node id.

## Read every response the same way

Every envelope carries: `answer`, `status` (closed vocabulary:
not_applicable, potentially_applicable, applicable_missing_evidence,
partially_satisfied, satisfied_with_evidence, rejected_as_unsupported,
requires_human_review), `source_nodes`, `source_spans`, `judge_verdict`,
`missing_facts`, `graph_version`, `non_legal_advice_notice`.

Rules for consuming agents:
- Treat `requires_human_review` as a stop: surface it to the human, do not
  proceed as if it were an approval.
- Never paraphrase a status upward (partially_satisfied is not satisfied).
- Fill `missing_facts` and re-ask instead of guessing.
- Cite `source_nodes` ids verbatim when relaying legal grounding.

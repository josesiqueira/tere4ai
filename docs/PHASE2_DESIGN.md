# PHASE2_DESIGN.md: hosted SaaS (Mode A) design

> STATUS: Phase 2 PROPOSAL. Nothing in this document is implemented. Phase 1
> (self-hosted Mode B, the demo web UI, the MCP tools, the judged pipeline) is
> what exists in the repository today; everything below is a design seed for
> the multi-tenant hosted deployment described in docs/architecture.md
> Section 9 ("Phase 2+ is the multi-tenant hosted SaaS (accounts, keys,
> metering) over the same service layer and graph"). Where this document says
> "the platform does X", read "the platform is designed to do X".
>
> Companion artifact: deploy/rahti/ holds the matching Kubernetes/OpenShift
> manifest seeds for CSC Rahti. They are equally unapplied and untested.
>
> Formatting rule (CI-enforced): never use em dashes, and never use en dashes
> as a sentence break. Use commas, colons, parentheses, or separate sentences.

## 1. Scope and grounding

- Deployment mode: Mode A Hosted SaaS per architecture.md Section 9: "TERE4AI
  operates the MCP server and graph; consumers use a URL and API key; HTTPS;
  EU-region hosting by default; usage accounting."
- Security posture: architecture.md Section 8 (MCP security, grounded_by
  REF-31): authentication, scopes, read-only default, request logging, rate
  limiting, secret redaction, revocable per-consumer keys, no arbitrary write
  Cypher, untrusted-input handling for project artifacts.
- Redaction and observability: architecture.md Section 13 (log tool call,
  latency, token usage, model, judge verdict, tenant key; redact secrets and
  sensitive project text).
- Hosting target: CSC Rahti (OpenShift), an EU (Finland) research cloud, which
  satisfies the "EU-region hosting by default" requirement of Section 9.
- What stays identical to Phase 1: architecture.md Section 9 states "Same
  server code across both; only transport, authentication, graph location, and
  model configuration vary." This document holds that line: the service layer,
  the graph build pipeline, and the judges do not change.

## 2. Multi-tenancy model

A tenant is a research group or a company. The model is deliberately simple,
because the shared asset (the legal knowledge graph) is not tenant data.

- Shared, read-only graph: one published, versioned graph build (Layer 0/1
  dumps plus the judged norms and alignments payloads) serves ALL tenants.
  The graph is derived from public sources (the EU AI Act, REF-01; HLEG/ALTAI,
  REF-33 and ADD-01) and contains no tenant input, so sharing it read-only
  leaks nothing between tenants. Tenants never write to the graph; graph
  publication remains a build-time, validation-gated event (Section 13).
- Strictly isolated tenant data: everything a tenant sends or generates at
  runtime is tenant-scoped and never visible to another tenant:
  - evidence text and system descriptions submitted to /api/classify,
    /api/evidence, /api/backlog (treated as untrusted input per Section 8);
  - runtime logs, judge verdicts, and audit trails for that tenant's calls;
  - metering counters and key metadata.
  Isolation is enforced in the key store and log partitioning (per-tenant
  prefixes or per-tenant tables), not by per-tenant deployments. Per-tenant
  Neo4j instances are explicitly NOT part of this design: the graph is shared
  and read-only, so there is nothing tenant-specific to isolate at the store.
- Tenant to key relation: one tenant owns one or more API keys. Keys, not
  tenants, carry scopes, so a tenant can hold a broad key for its CI agent and
  a narrow read-only key for a student.

Honesty note: none of this isolation exists today. Phase 1 has no tenants, no
keys, and a single body-free request log (src/tere4ai/http_facade/app.py).

## 3. API keys, scopes, and endpoint mapping

Five scopes, matching Section 8's "per-consumer keys are revocable and scoped"
(REF-31) and the read-only-by-default rule:

| Scope | Meaning | Cost class |
| --- | --- | --- |
| read_graph | read the published graph: structure, norms, alignments, spans | free, deterministic |
| classify | run the deterministic classifier | free, deterministic |
| evidence_paid | evidence evaluation (OpenAI generator plus Anthropic judge) | paid model calls |
| backlog_paid | control-backlog generation (paid model calls) | paid model calls |
| admin | key management, metering readout, tenant administration | platform-internal |

Mapping of every existing endpoint and MCP tool to a scope:

| Endpoint (facade) | MCP tool | Scope |
| --- | --- | --- |
| GET /api/health | (none) | none: unauthenticated, used by the readiness probe |
| GET /llms.txt, GET /.well-known/tere4ai.json | (none) | none: public discovery metadata |
| POST /api/classify | classify_ai_system | classify |
| POST /api/requirements | get_applicable_requirements | read_graph |
| POST /api/explain | explain_requirement | read_graph |
| POST /api/trace | trace_alignment | read_graph |
| GET /api/span/{span_id} | source_trace | read_graph |
| (build-time report) | coverage_report | read_graph |
| POST /api/evidence | evaluate_project_evidence | evidence_paid |
| POST /api/backlog | generate_control_backlog | backlog_paid |
| (new in Phase 2) | (none) | admin: create/revoke keys, read metering aggregates |

Notes:
- The paid split follows the facade contract as implemented: /api/evidence and
  /api/backlog are the only endpoints that perform paid model calls, and they
  already mark responses with the X-TERE4AI-Paid-Call header
  (src/tere4ai/http_facade/app.py). The scope boundary reuses that boundary.
- read_graph and classify are separate scopes even though both are free and
  deterministic, because classify accepts tenant system descriptions (untrusted
  input worth gating separately) while read_graph never accepts tenant content
  beyond graph identifiers.
- There is no write scope of any kind. Section 8: no arbitrary write Cypher;
  any exposed Cypher is read-only, limited, logged, and disableable per key.

Key mechanics (proposed):
- Format: `t4a_<key_id>_<secret>`. The server stores only the key_id, the
  tenant id, the scope set, a created/revoked timestamp, and a salted hash of
  the secret. The plaintext secret is shown once at creation and never stored
  or logged (Section 13 secret redaction).
- Revocation: a key row is marked revoked; every request does a key-store
  lookup, so revocation takes effect on the next request. This satisfies
  Section 8's "revocable per key", including disabling a key's scopes without
  deleting its metering history.
- Rotation: issue the replacement key first, then revoke the old one after a
  grace window (proposed default 7 days) during which both work. Rotation is a
  tenant-initiated admin operation; there is no silent server-side rotation.
- Rate limiting moves from Phase 1's per-client-IP fixed window
  (TERE4AI_RATE_LIMIT_PER_MINUTE) to per-key limits, with lower default limits
  on the paid scopes.

## 4. Metering and usage accounting

Section 9 requires "usage accounting" for Mode A; Section 13 requires token
usage and tenant key in the observability record while redacting sensitive
project text. Proposed design:

- Per-key counters, incremented in the auth middleware and the paid-call path:
  - calls per endpoint (all scopes);
  - paid model tokens (prompt and completion, per model) for evidence_paid and
    backlog_paid calls. The X-TERE4AI-Paid-Call header already marks exactly
    the responses that must carry token accounting, so the metering hook keys
    off the same code path that sets that header.
- Daily aggregation: raw per-request counter events are rolled up into daily
  per-key, per-endpoint aggregates; raw events are dropped after aggregation
  (proposed retention: 30 days for raw, indefinitely for daily aggregates).
- No request bodies stored, ever. Phase 1's facade request log is already
  body-free by design because bodies can carry project evidence text (Section
  13 redaction; see the header comment in src/tere4ai/http_facade/app.py).
  Phase 2 metering keeps that rule: counters and token counts only, plus the
  metadata Section 13 lists (graph version, tool, latency, model, judge
  verdict, error state, tenant key id). Never the evidence text, never the
  generated requirements.
- Metering readout: an admin-scoped endpoint returning a tenant's own daily
  aggregates. Cross-tenant readout is platform-operator only.

## 5. EU hosting on CSC Rahti (OpenShift)

- Target platform: CSC Rahti 2 (OpenShift/Kubernetes), operated by CSC in
  Finland, so the default deployment region is inside the EU as Section 9
  Mode A requires. Rahti is a natural fit for research software from a Finnish
  university and is the assumed target of the deploy/rahti/ manifest seeds.
- Topology (see deploy/rahti/README.md for the file-level mapping):
  - facade Deployment: the existing core image (Dockerfile target `core`),
    serving the HTTP facade and MCP transport on port 8008, readiness-probed
    on /api/health;
  - web Deployment: the existing Next.js demo UI image (Dockerfile target
    `web`) on port 3111;
  - Neo4j StatefulSet with a PVC for /data, reachable only inside the
    namespace (no Route), mirroring the loopback-only binding of
    docker-compose.yml;
  - one public OpenShift Route to the facade with TLS edge termination;
  - a NetworkPolicy restricting traffic to web to facade to Neo4j only.
- Honest architecture note: the Phase 1 facade serves from versioned offline
  graph dumps baked into the image and does not query Neo4j at runtime. The
  Neo4j StatefulSet seed exists because architecture.md Sections 5 and 8 place
  the MCP server in front of the live graph; whether Phase 2 serves runtime
  reads from Neo4j or keeps the dump-serving model is an open question
  (Section 9 of this document). The manifests support both.

### Data sovereignty tiers, restated

Restating Section 9 so hosted-tenant expectations are honest:

- Tier 1: hosted graph plus cloud LLM. This is Mode A. Tenant evidence text
  sent to /api/evidence and /api/backlog reaches the cloud model providers
  (OpenAI generator, Anthropic judge, Section 7), which are not EU-controlled.
  EU hosting of the graph and facade does NOT make the paid endpoints
  EU-contained, and the platform must say so in its discovery metadata.
- Tier 2: self-hosted graph plus cloud LLM (Mode B today).
- Tier 3: self-hosted graph plus local model: strongest sovereignty, lower
  model quality, experimental in v2, not promised to match cloud quality.

A tenant needing Tier 2 or 3 should be pointed to Mode B (docker-compose),
which stays fully supported; Mode A does not replace it.

### Out of scope for Phase 2

- Billing UI and payment processing: metering produces the numbers; invoicing
  is manual or external.
- SSO / OIDC / institutional login: tenants are provisioned manually by the
  operator; authentication is API keys only.
- Per-tenant graph customisation or tenant writes to the graph.
- Multi-region or non-EU hosting.

## 6. Migration path from Phase 1

What changes (new or modified code):

- Auth middleware: a new facade middleware that resolves the API key header
  (proposed: `Authorization: Bearer t4a_...`), checks revocation and scope
  against the key store, and rejects with a clean JSON 401/403 envelope. It
  slots in next to the existing rate-limit middleware in
  src/tere4ai/http_facade/app.py.
- Key store: a new small component (proposed: a single-file SQLite or a
  Postgres-compatible table set on a PVC) holding tenants, keys (hashed),
  scopes, and metering counters. This is the only new stateful component.
- Config: new environment variables for the key-store location and the
  auth-enforcement switch. Auth enforcement is OFF by default so Mode B and
  local demo behaviour are unchanged; the Rahti deployment turns it on.
- Rate limiting: per-key instead of per-client-IP when auth is on.
- Request log: gains the key id field (Section 13 already lists tenant key in
  the observability record); stays body-free.
- CORS: the facade's Phase 1 allowlist (localhost:3111 only) becomes the
  hosted web origin.

What does NOT change:

- The service layer and MCP tools (src/tere4ai/mcp_server/): same pure
  functions, same envelope, same calibrated status vocabulary (DEC-08).
- The graph, its build pipeline, its validation gates, and its versioned dumps.
- The judges and model configuration (Section 7, DEC-07: OpenAI generator,
  independent Anthropic judge).
- The evaluation harness and gold sets.
- Mode B: docker-compose self-hosting keeps working with auth off, exactly as
  in Phase 1.

## 7. Risks and open questions

- OPEN-LICENSE is unresolved (architecture.md Section 15) and it gates hosting
  more than it gated self-hosting. The working position is server code under
  AGPL-3.0-or-later, graph metadata under CC BY 4.0 or CC0, EU legal text
  under the EU reuse terms (ADD-23; do not claim ownership of the Act text,
  REF-01), and ALTAI redistribution pending a license check (REF-33). Until
  this is decided, the hosted service must not be offered beyond research
  collaborators, because serving ALTAI-derived nodes to third parties may
  exceed what the ALTAI license allows.
- Prompt injection through tenant evidence: Section 8 (REF-31) already
  requires treating project artifacts as untrusted input and keeping
  instructions separate from evidence. Multi-tenancy raises the stakes
  (a hostile tenant probing the shared platform), but not the mechanism; the
  existing separation must be re-verified under hosted load, not redesigned.
- Shared upstream model keys: paid calls run on the platform's OpenAI and
  Anthropic keys, so per-key metering and rate limits are also the abuse
  control for the platform's model spend. A metering bug is a financial bug.
- Key-store availability: the key store becomes a runtime dependency of every
  authenticated request. Per Section 13 (no silent degradation), a key-store
  outage must produce a clean 503, never an auth bypass.
- Rahti specifics are unverified: quotas, storage classes, Route TLS options,
  and NetworkPolicy behaviour on Rahti have not been tested by this project.
  The deploy/rahti/ manifests are seeds written from OpenShift documentation
  knowledge, not from a working deployment.
- Open question, graph serving: keep the Phase 1 dump-serving facade (simple,
  immutable, cache-friendly) or move runtime reads to Neo4j (needed for richer
  traversals)? The manifests provision Neo4j either way; the decision is
  deferred to the first Phase 2 implementation task.
- Open question, MCP transport: whether Remote MCP for coding agents shares
  the facade Route or gets its own Route and key scope presentation. Same
  scopes either way (Section 8 requires scoped keys for MCP consumers).
- Open question, tenant data retention: how long evidence-derived verdicts and
  audit logs are kept per tenant, and the deletion story when a tenant leaves.

## 8. Acceptance sketch (for the future implementation task)

Not tests that exist; the acceptance bar the implementation must meet:

- A request without a key reaches only /api/health, /llms.txt, and
  /.well-known/tere4ai.json.
- A key with read_graph only gets 403 on /api/classify, /api/evidence,
  /api/backlog.
- A revoked key fails on the next request.
- A paid call increments the token counters for exactly that key, and the
  stored record contains no request body text.
- Turning auth off reproduces Phase 1 behaviour bit for bit (Mode B parity).

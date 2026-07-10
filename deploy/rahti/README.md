# deploy/rahti: Phase 2 manifest seeds (PROPOSAL, UNTESTED)

> HONESTY NOTICE. These manifests are Phase 2 DESIGN SEEDS. They have never
> been applied to any cluster, including CSC Rahti. No image referenced here
> has been built or pushed, no Route exists, no PVC has been provisioned, and
> nothing has been smoke-tested. They encode the deployment topology proposed
> in docs/PHASE2_DESIGN.md so the future implementation task starts from a
> reviewed baseline instead of a blank page. Phase 1 remains self-hosted via
> docker-compose.yml (architecture.md Section 9, Mode B).

## What this is

Kubernetes/OpenShift manifests targeting CSC Rahti (OpenShift), the proposed
EU hosting platform for Mode A Hosted SaaS (architecture.md Section 9;
docs/PHASE2_DESIGN.md Section 5). Kustomize layout, applied (in Phase 2, after
testing) with `oc apply -k deploy/rahti/`.

## Mapping to PHASE2_DESIGN.md

| File | Contents | Design section |
| --- | --- | --- |
| kustomization.yaml | resource list, namespace placeholder, labels | Section 5 |
| deployment-facade.yaml | core image, env from Secret, resource limits, readiness probe on /api/health | Sections 5, 6 |
| deployment-web.yaml | demo/SaaS web UI, port 3111, facade URL wiring seed | Section 5, open question in Section 7 |
| statefulset-neo4j.yaml | community neo4j:5, PVC for /data, internal only | Section 5 (open question: dump-serving vs live graph) |
| services.yaml | ClusterIP services; Neo4j gets no Route (loopback equivalent) | Section 5 |
| route-facade.yaml | the single public HTTPS entry, TLS edge termination | Section 5 (Mode A: URL plus API key over HTTPS) |
| secret.example.yaml | placeholder-only Secret shape (model keys, Neo4j password, key-store pepper) | Sections 3, 6 |
| networkpolicy.yaml | web to facade to neo4j only, plus router ingress | Section 5; architecture.md Section 8 (no direct DB access) |

## Design rules the manifests encode

- One public entry point: only the facade has a Route, with TLS edge
  termination and an HTTP-to-HTTPS redirect (Mode A requires HTTPS,
  architecture.md Section 9).
- The database is never exposed: Neo4j has a ClusterIP-only Service and a
  NetworkPolicy admitting only facade pods, mirroring the loopback-only
  bindings in docker-compose.yml and Section 8's rule that consumers must not
  touch the database directly (REF-31).
- Readiness equals graph availability: the readiness probe uses /api/health,
  which returns 503 when the graph dumps failed to load, so a degraded pod is
  never routed to (no silent degradation, architecture.md Section 13).
- Secrets stay out of git: secret.example.yaml carries obviously fake
  placeholders, is excluded from kustomization.yaml, and the real secret is
  created out of band.

## Known unknowns (must be resolved before first apply)

- No image exists at the placeholder references; the Dockerfile targets have
  not been built for or pushed to any registry reachable from Rahti.
- Rahti's restricted SCC (arbitrary UID) is untested for both the core image
  and the official neo4j image.
- Resource requests/limits are unvalidated guesses.
- The router namespaceSelector in networkpolicy.yaml follows stock
  OpenShift 4 labels and needs verification on Rahti.
- The web UI Route and the browser-to-facade wiring are an open question
  (docs/PHASE2_DESIGN.md Section 7).
- Auth, key store, and metering (docs/PHASE2_DESIGN.md Sections 3 and 4) are
  not implemented in the code these manifests would deploy.

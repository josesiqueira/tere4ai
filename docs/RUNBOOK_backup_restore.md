# Runbook: graph volume backup and restore

Scope: the local Mode B stack (docker-compose.yml), container
`tere4ai2_neo4j`, named volumes `tere4ai2_neo4j_data` and
`tere4ai2_neo4j_logs`, Neo4j 5 Community.

## First principle: the database is a derived artifact

The graph in Neo4j is fully rebuildable from tracked, checksummed inputs
(architecture.md Section 13; the build chain of #48). The authoritative
backup is therefore the repository itself: data/snapshots (frozen sources),
data/graph_dumps (layer1.json, norms_core.json, alignments_core.json, the
build_chain record), and data/review_queue/decisions.json. Volume backups
below are a convenience (faster than re-publishing, and they preserve any ad
hoc additions), never the source of truth.

## Rebuild from source (the canonical restore)

```bash
docker compose up -d neo4j
.venv/bin/python -m tere4ai.parse_legal_structure          # regenerate layer1 dump if absent
.venv/bin/python scripts/load_layer1.py                    # constraints + Layer 0/1 (idempotent MERGE)
.venv/bin/python scripts/publish_layer23.py \
    --norms data/graph_dumps/norms_core.json \
    --alignments data/graph_dumps/alignments_core.json
```

The publish step runs the Section 13 gates before loading and the post-load
gates P1..P5 after (#49); a restore that fails either is not a restore.
Verify the chain id printed matches the tracked build_chain record.

## Volume backup (offline dump, Community edition)

Neo4j Community requires the database stopped for a consistent dump:

```bash
mkdir -p backups
docker compose stop neo4j
docker run --rm \
  -v tere4ai2_neo4j_data:/data \
  -v "$(pwd)/backups":/backups \
  neo4j:5 neo4j-admin database dump neo4j --to-path=/backups
docker compose start neo4j
ls -lh backups/neo4j.dump
```

Name the artifact with the build id so it stays traceable:

```bash
mv backups/neo4j.dump "backups/neo4j_$(date +%Y%m%d)_build-3b753e5e9297+chain-3982bf3d85d4.dump"
```

## Volume restore

```bash
docker compose stop neo4j
docker run --rm \
  -v tere4ai2_neo4j_data:/data \
  -v "$(pwd)/backups":/backups \
  neo4j:5 neo4j-admin database load neo4j \
    --from-path=/backups --overwrite-destination=true
docker compose start neo4j
```

`--overwrite-destination` is destructive to the current volume contents;
take a fresh dump first if in doubt. The loaded dump file must be named
`neo4j.dump` inside the mounted path (rename before loading if you stamped
the filename).

## Verify after any restore

```bash
curl -s localhost:8008/api/health          # graph_version matches the expected build id
.venv/bin/python scripts/publish_layer23.py \
    --norms data/graph_dumps/norms_core.json \
    --alignments data/graph_dumps/alignments_core.json --gates-only
NEO4J_URI=bolt://localhost:7688 NEO4J_USER=neo4j NEO4J_PASSWORD=... \
    .venv/bin/python -m pytest tests/integration/test_postload_gates.py -q
```

All three must pass before the restored database is treated as published.

## Raw volume tarball (last resort)

Filesystem-level copy; only valid when the container is stopped:

```bash
docker compose stop neo4j
docker run --rm -v tere4ai2_neo4j_data:/data -v "$(pwd)/backups":/b \
  alpine tar czf /b/neo4j_data_volume.tar.gz -C /data .
docker compose start neo4j
```

Restore by untarring into a fresh volume the same way (tar xzf, then start).
Prefer neo4j-admin dumps: they are version-checked and portable across
hosts; tarballs are not.

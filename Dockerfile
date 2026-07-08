# TERE4AI v2 core image: facade + MCP server + pipeline CLIs (Mode B, §9)
FROM python:3.12-slim AS core

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY schema ./schema
COPY prompts ./prompts
COPY scripts ./scripts
COPY data/snapshots ./data/snapshots
# the judged Layer 2/3 dumps ship with the Mode B image (architecture.md
# Section 9: "docker-compose plus a graph dump and source manifest")
COPY data/graph_dumps ./data/graph_dumps
COPY SKILL.md ./

RUN pip install --no-cache-dir -e .

# deterministic rebuild of Layer 1 at image build time (idempotent; verifies
# the frozen snapshot checksums) plus the UI data export
RUN mkdir -p web/public \
    && python -m tere4ai.parse_legal_structure \
    && python scripts/export_ui_data.py

EXPOSE 8008
CMD ["uvicorn", "tere4ai.http_facade.app:app", "--host", "0.0.0.0", "--port", "8008"]

# web build stage: the thin demo UI, with the exported UI data baked in
FROM node:22-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
COPY --from=core /app/web/public/ui_data.json ./public/ui_data.json
RUN npm run build

FROM node:22-slim AS web
WORKDIR /web
COPY --from=webbuild /web/.next/standalone ./
COPY --from=webbuild /web/.next/static ./.next/static
COPY --from=webbuild /web/public ./public
EXPOSE 3111
ENV PORT=3111
CMD ["node", "server.js"]

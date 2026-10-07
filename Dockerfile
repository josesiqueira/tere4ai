# TERE4AI v2 core image: facade + MCP server + pipeline CLIs (Mode B, §9)
FROM python:3.12-slim AS core

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY schema ./schema
COPY config ./config
COPY prompts ./prompts
COPY scripts ./scripts
COPY data/snapshots ./data/snapshots
# B132 and B143: the parse reads the reviewed Omnibus marker list and
# exception rows and the amendment inventory (parse_legal_structure/amendments.py)
COPY data/amendments ./data/amendments
COPY docs/omnibus_amendments.md ./docs/omnibus_amendments.md
# the judged Layer 2/3 dumps ship with the Mode B image (architecture.md
# Section 9: "docker-compose plus a graph dump and source manifest")
COPY data/graph_dumps ./data/graph_dumps
COPY SKILL.md ./

# deterministic rebuild of Layer 1 at image build time (verifies the frozen
# snapshot checksums and the Section 13 gates) plus the UI data export. B70:
# the rebuild goes to a scratch directory and is discarded: a parse stamps a
# new built_at, so writing data/graph_dumps/layer1.json would change the
# served chain id, and it refuses once a publication names that file. The
# image serves the copied dumps unchanged.
# B143 (DEC-25): the parse checks the HLEG text against the Guidelines' PDF,
# which needs the hleg extra (pdfplumber, pypdf); the served image does not
# carry it, so it is installed and removed in the one step that parses.
RUN pip install --no-cache-dir -e ".[hleg]" \
    && mkdir -p web/public \
    && python -m tere4ai.parse_legal_structure --dump-dir /tmp/layer1-check \
    && rm -rf /tmp/layer1-check \
    && python scripts/export_ui_data.py \
    && pip uninstall -y pdfplumber pdfminer.six pypdf pypdfium2

# B70: the served build id, read from the copied dumps by the facade's own
# loader. A label takes only a build argument, so the release script passes
# the id and this step fails the build when the files serve another one; an
# empty argument leaves the label empty. SERVED_BUILD_ID keeps the id inside
# the image either way.
ARG TERE4AI_SERVED_BUILD_ID=""
RUN python scripts/served_build_id.py --expect "$TERE4AI_SERVED_BUILD_ID" > SERVED_BUILD_ID
LABEL tere4ai.served_build_id="$TERE4AI_SERVED_BUILD_ID"

# B70: a non-root user in group 0, so OpenShift's arbitrary user id (always
# in group 0) runs the image too. The dumps are readable by everyone and
# writable by nobody at run time; data/review_queue, where the request log
# goes by default (TERE4AI_REQUEST_LOG, /dev/stdout when hosted), is
# writable by group 0.
RUN useradd --uid 1001 --gid 0 --no-create-home --home-dir /app tere4ai \
    && chmod -R a+rX,go-w data/graph_dumps \
    && mkdir -p data/review_queue \
    && chgrp -R 0 data/review_queue \
    && chmod -R g=u data/review_queue
USER 1001:0

EXPOSE 8008
CMD ["uvicorn", "tere4ai.http_facade.app:app", "--host", "0.0.0.0", "--port", "8008", "--no-server-header"]

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

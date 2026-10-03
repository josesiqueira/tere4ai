#!/usr/bin/env bash
# Build the public site of the MCP server from docs/server (DEC-22) in
# strict mode: a warning, such as a relative link to a missing page, fails
# the build. The recorded sessions join the site only when
# docs/server/sessions.md exists (scripts/gen_server_docs.py --sessions).
# Usage: bash scripts/build_site.sh (PYTHON names the interpreter; the
# default is python). Output: _site/, never committed.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python}
if [ -f docs/server/sessions.md ]; then
  mkdir -p docs/server/sessions
  cp web/public/mcp-demo/*.html docs/server/sessions/
fi
"$PY" -m mkdocs build --strict

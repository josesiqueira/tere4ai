#!/usr/bin/env bash
# Reindex the reference-paper corpus in data/refs:
#   1. make a plain-text sidecar (REF-xx_*.txt) for every PDF, so verbatim
#      retrieval is line-anchored and rtk-rg searchable (PDFs do not grep well),
#   2. rebuild the graphify knowledge graph + wiki over data/refs,
# so a lookup becomes a cheap graph query plus a targeted rtk rg, never a
# full-PDF re-read.
#
# Usage:  bash scripts/refs_reindex.sh
# Idempotent: skips a sidecar whose .txt is newer than its .pdf.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REFS_DIR="$REPO_ROOT/data/refs"

if [ ! -d "$REFS_DIR" ]; then
  echo "no data/refs directory; nothing to index" >&2
  exit 0
fi

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "pdftotext not found (install poppler-utils)" >&2
  exit 1
fi

made=0 skipped=0
shopt -s nullglob
for pdf in "$REFS_DIR"/*.pdf; do
  txt="${pdf%.pdf}.txt"
  if [ -f "$txt" ] && [ "$txt" -nt "$pdf" ]; then
    skipped=$((skipped+1))
    continue
  fi
  # -layout keeps tables/columns readable so quoted numbers survive
  pdftotext -layout "$pdf" "$txt"
  echo "  text sidecar: $(basename "$txt")"
  made=$((made+1))
done
echo "sidecars: $made made, $skipped up-to-date"

# Rebuild the dedicated reference graph (separate from the code graph so
# literature queries carry no source-code noise). --wiki adds a middle tier:
# one Markdown article per concept cluster, richer than the graph, cheaper
# than the PDF.
if command -v graphify >/dev/null 2>&1; then
  echo "rebuilding graphify index over data/refs ..."
  ( cd "$REFS_DIR" && graphify . --wiki --update 2>/dev/null || graphify . --wiki )
  echo "refs graph at data/refs/graphify-out/"
else
  echo "graphify not on PATH; skipped graph rebuild" >&2
fi

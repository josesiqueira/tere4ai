"""Export the demo UI data file from the service layer.

@implements: DEC-10 (partial: M1 structural coverage view only)
@grounded_by: REF-17, REF-15

The demo web UI is a thin, read-only facade over the same service layer
(docs/architecture.md Section 9). This script calls coverage_report exactly
as the MCP tool does and serializes the browsable Act structure from the
versioned dump; the UI renders that JSON and never touches the database.

Usage: .venv/bin/python scripts/export_ui_data.py
Writes: web/public/ui_data.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.mcp_server.tools import coverage_report  # noqa: E402

DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
OUT_PATH = ROOT / "web" / "public" / "ui_data.json"


def build_structure(dump: dict) -> dict:
    nodes = {n["id"]: n for n in dump["nodes"]}
    children: dict[str, list[str]] = {}
    for e in dump["edges"]:
        if e["edge_type"] in {"HAS_CHAPTER", "HAS_SECTION", "HAS_ARTICLE", "HAS_ANNEX"}:
            children.setdefault(e["from"], []).append(e["to"])

    def article_entry(aid: str) -> dict:
        a = nodes[aid]
        return {
            "id": aid,
            "number": a["number"],
            "title": a.get("title", ""),
            "anchor": (a.get("source_span") or {}).get("anchor", ""),
        }

    chapters = []
    for cid in children.get("eu-ai-act", []):
        c = nodes.get(cid)
        if not c or c["type"] != "Chapter":
            continue
        sections = []
        direct_articles = []
        for kid in children.get(cid, []):
            k = nodes[kid]
            if k["type"] == "Section":
                sections.append(
                    {
                        "id": kid,
                        "number": k["number"],
                        "title": k.get("title", ""),
                        "articles": [
                            article_entry(x)
                            for x in children.get(kid, [])
                            if nodes[x]["type"] == "Article"
                        ],
                    }
                )
            elif k["type"] == "Article":
                direct_articles.append(article_entry(kid))
        sections.sort(key=lambda s: s["number"])
        for s in sections:
            s["articles"].sort(key=lambda a: a["number"])
        direct_articles.sort(key=lambda a: a["number"])
        chapters.append(
            {
                "id": cid,
                "number": c["number"],
                "title": c.get("title", ""),
                "sections": sections,
                "articles": direct_articles,
            }
        )

    roman_order = {c["number"]: i for i, c in enumerate(chapters)}
    del roman_order  # chapters already in document order from the parser

    def roman_value(r: str) -> int:
        vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
        total = 0
        for i, ch in enumerate(r):
            v = vals[ch]
            total += -v if i + 1 < len(r) and vals[r[i + 1]] > v else v
        return total

    annexes = sorted(
        (
            {
                "id": n["id"],
                "number": n["number"],
                "title": n.get("title", ""),
                "anchor": (n.get("source_span") or {}).get("anchor", ""),
            }
            for n in dump["nodes"]
            if n["type"] == "Annex"
        ),
        key=lambda a: roman_value(a["number"]),
    )

    recitals = sum(1 for n in dump["nodes"] if n["type"] == "Recital")
    return {"chapters": chapters, "annexes": annexes, "recital_count": recitals}


def main() -> None:
    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    payload = {
        "coverage": coverage_report(dump),
        "structure": build_structure(dump),
        "build": dump["build"],
        "review_queue_count": len(dump.get("review_queue", [])),
        "sources": [
            {
                "id": n["id"],
                "title": n.get("title", ""),
                "legal_status": n.get("legal_status", ""),
            }
            for n in dump["nodes"]
            if n["type"] == "SourceDocument"
        ],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

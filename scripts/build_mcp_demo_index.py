#!/usr/bin/env python3
"""Build the summary index the web MCP demo page reads.

@implements: DEC-08, DEC-15
@grounded_by: ADD-14, ADD-15

Reads the recorded sessions written by scripts/record_mcp_demo.py and emits
web/public/mcp-demo/index.json. Every figure in the output is copied out of
a recorded envelope; nothing here recomputes, rounds, or asserts anything the
server did not answer. The page renders these numbers, so a hand-typed claim
can never reach the UI.

The code index is the recorded requirement-to-code matrix read the other way
round: for each file that carries an `@implements` tag the server accepted,
which norms it claims, at which line. Tags the server refused are carried
with the server's own refusal reason, never dropped.

Usage:
    python scripts/build_mcp_demo_index.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "demo" / "mcp_demo" / "sessions"
OUT = ROOT / "web" / "public" / "mcp-demo" / "index.json"

# Display order and the one-line framing for each recorded system. The label
# and blurb are editorial; every number beside them comes from an envelope.
SYSTEMS: list[dict[str, str]] = [
    {
        "key": "minimalrisk",
        "product": "SpamGuard",
        "label": "Minimal risk",
        "blurb": (
            "An email spam and phishing filter. The useful answer is the "
            "negative one: no high-risk apparatus to build, on the record."
        ),
    },
    {
        "key": "limitedrisk",
        "product": "ShopBot",
        "label": "Limited risk",
        "blurb": (
            "A webshop support assistant. Transparency duties under Article "
            "50, one gap closed in code and tagged, one tag the server "
            "refuses because the norm behind it is still in human review."
        ),
    },
    {
        "key": "highrisk",
        "product": "CredScore",
        "label": "High risk",
        "blurb": (
            "A creditworthiness scorer. Annex III point 5, the Article 27 "
            "impact assessment duty attaches, and the backlog is larger than "
            "the sprint anyone had planned."
        ),
    },
    {
        "key": "unacceptablerisk",
        "product": "MoodWatch",
        "label": "Unacceptable risk",
        "blurb": (
            "Workplace emotion inference. Article 5(1)(f) bans the practice, "
            "so the answer carries zero requirements and one citation."
        ),
    },
    {
        "key": "abstention",
        "product": "MoodWatch driver fatigue variant",
        "label": "Abstention",
        "blurb": (
            "The same engine with the medical or safety exception left "
            "unknown. The ladder refuses to settle the tier and names the "
            "single fact that would."
        ),
    },
]


def _read_session(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _last(records: list[dict[str, Any]], tool: str) -> dict[str, Any] | None:
    found = [r for r in records if r["tool"] == tool]
    return found[-1] if found else None


def _norm_texts(requirements: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """norm_id -> its recorded deontic fields, for joining onto matrix rows."""
    if requirements is None:
        return {}
    answer = requirements["envelope"].get("answer") or {}
    by_article = answer.get("requirements_by_article")
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(by_article, dict):
        return out
    for norms in by_article.values():
        if not isinstance(norms, list):
            continue
        for norm in norms:
            if isinstance(norm, dict) and isinstance(norm.get("norm_id"), str):
                out[norm["norm_id"]] = {
                    "modal": norm.get("modal"),
                    "action": norm.get("action"),
                    "object": norm.get("object"),
                    "actor": norm.get("actor"),
                    "article": norm.get("source_node_id"),
                }
    return out


def _code_index(matrix_answer: dict[str, Any], texts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The matrix inverted: one entry per tagged file, with its claims."""
    files: dict[str, list[dict[str, Any]]] = {}
    for row in matrix_answer.get("matrix") or []:
        if not isinstance(row, dict) or row.get("trace_status") != "traced":
            continue
        norm_id = row.get("norm_id")
        text = texts.get(str(norm_id), {})
        for loc in row.get("trace_locations") or []:
            path = loc.get("path")
            if not isinstance(path, str):
                continue
            files.setdefault(path, []).append(
                {
                    "line": loc.get("line"),
                    "norm_id": norm_id,
                    "article": row.get("article"),
                    "source_span_id": row.get("source_span_id"),
                    "accepted": True,
                    "modal": text.get("modal"),
                    "action": text.get("action"),
                    "object": text.get("object"),
                    "hleg_alignments": row.get("hleg_alignments") or [],
                }
            )
    for tag in matrix_answer.get("invalid_tags") or []:
        if not isinstance(tag, dict):
            continue
        path = tag.get("path")
        if not isinstance(path, str):
            continue
        files.setdefault(path, []).append(
            {
                "line": tag.get("line"),
                "norm_id": tag.get("norm_id"),
                "article": None,
                "source_span_id": None,
                "accepted": False,
                "refusal_reason": tag.get("reason"),
                "modal": None,
                "action": None,
                "object": None,
                "hleg_alignments": [],
            }
        )
    return [
        {"path": path, "claims": sorted(claims, key=lambda c: (c["line"] or 0))}
        for path, claims in sorted(files.items())
    ]


def build(sessions_dir: Path) -> dict[str, Any]:
    systems: list[dict[str, Any]] = []
    graph_versions: list[str] = []
    for spec in SYSTEMS:
        path = sessions_dir / f"{spec['key']}.jsonl"
        if not path.is_file():
            print(f"missing recorded session: {path}", file=sys.stderr)
            raise SystemExit(2)
        records = _read_session(path)
        classify = _last(records, "classify_ai_system")
        requirements = _last(records, "get_applicable_requirements")
        matrix = _last(records, "trace_implementation")
        assert classify is not None, f"{path}: no classify_ai_system exchange"

        classify_env = classify["envelope"]
        classify_answer = classify_env.get("answer") or {}
        req_answer = (requirements or {}).get("envelope", {}).get("answer") or {}
        req_summary = req_answer.get("summary") if isinstance(req_answer.get("summary"), dict) else {}
        by_article = req_answer.get("requirements_by_article")
        matrix_answer = (matrix or {}).get("envelope", {}).get("answer") or {}

        for record in records:
            version = record["envelope"].get("graph_version")
            if isinstance(version, str):
                graph_versions.append(version)

        systems.append(
            {
                **spec,
                "report": f"/mcp-demo/{spec['key']}.html",
                "session_file": path.name,
                "exchanges": [
                    {
                        "seq": r["seq"],
                        "tool": r["tool"],
                        "status": r["envelope"].get("status"),
                    }
                    for r in records
                ],
                "classification": {
                    "risk_category": classify_answer.get("risk_category"),
                    "prohibited": classify_answer.get("prohibited"),
                    "status": classify_env.get("status"),
                    "confidence": classify_env.get("confidence"),
                    "rationale": classify_answer.get("rationale") or [],
                    "source_nodes": classify_env.get("source_nodes") or [],
                    "missing_facts": classify_env.get("missing_facts") or [],
                    "fria": (classify_answer.get("fria") or {}).get("applicability"),
                },
                "requirements": {
                    "returned": req_summary.get("returned"),
                    "total_accepted_in_scope": req_summary.get("total_accepted_in_scope"),
                    "needs_human_review_total": req_summary.get("needs_human_review_total"),
                    "articles": len(by_article) if isinstance(by_article, dict) else 0,
                    "message": req_answer.get("message"),
                    "per_article": req_summary.get("per_article") or {},
                },
                "trace": (
                    {
                        "applicable_norms": (matrix_answer.get("summary") or {}).get("applicable_norms"),
                        "traced": (matrix_answer.get("summary") or {}).get("traced"),
                        "untraced": (matrix_answer.get("summary") or {}).get("untraced"),
                        "invalid_tags": (matrix_answer.get("summary") or {}).get("invalid_tags"),
                        "tag_convention": matrix_answer.get("tag_convention"),
                        "trace_note": matrix_answer.get("trace_note"),
                        "code_index": _code_index(matrix_answer, _norm_texts(requirements)),
                    }
                    if matrix is not None
                    else None
                ),
                "repo_ref": next((r.get("repo_ref") for r in records if r.get("repo_ref")), None),
            }
        )

    notice = None
    first_session = _read_session(sessions_dir / f"{SYSTEMS[0]['key']}.jsonl")
    for record in first_session:
        candidate = record["envelope"].get("non_legal_advice_notice")
        if isinstance(candidate, str):
            notice = candidate
            break

    return {
        "graph_versions": sorted(set(graph_versions)),
        "non_legal_advice_notice": notice,
        "systems": systems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions-dir", default=str(SESSIONS))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    payload = build(Path(args.sessions_dir))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

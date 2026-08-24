"""Implementation traceability: judge-accepted norms joined to code locations.

@implements: DEC-15
@grounded_by: ADD-14, ADD-15

Closes the requirement-to-code loop for consumer projects. A consumer marks
code with tags of the form `@implements: norm:eu-ai-act:...` (one norm id per
tag; the reference scanner is tere4ai.trace_scan). This module joins those tag
records against the published graph:

- requirement -> code: for every judge-accepted norm applicable to the
  classified system, the locations claiming to implement it, or `untraced`.
- code -> requirement: for every tag record, the norm it cites resolved to
  its provision, source span, and judge-accepted HLEG alignments, or a named
  rejection when the cited id is unknown or not judge-accepted.

Honesty rules, deliberate and load-bearing:
- A tag is a developer CLAIM of implementation, never evidence. Rows say
  `traced` or `untraced`; the evidence path stays evaluate_project_evidence
  and the calibrated ladder (DEC-08). Nothing here raises an evidence status.
- Only judge-accepted norm ids count. A tag citing a norm in the human review
  queue, a rejected norm, or an id that does not exist is reported in
  `invalid_tags` with the reason, and is never joined into the matrix. This
  keeps the review queue's exclusion guarantee intact end to end.
- The matrix is generated from the tags and the graph on every call, never
  stored, so it cannot drift from the code (the Section 17 convention,
  extended from design decisions to norms).

The server never reads the consumer's filesystem (Section 8: no unscoped
filesystem access). Scanning happens client-side; this module receives plain
tag records: {"norm_id": str, "path": str, "line": int}.
"""

from __future__ import annotations

from typing import Any

from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT
from tere4ai.mcp_server.requirements import get_applicable_requirements
from tere4ai.mcp_server.tools import make_envelope

TAG_CONVENTION = "@implements: <norm-id>"


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))

_TRACE_NOTE = (
    "A trace is a developer claim that code implements a norm, recorded as an "
    f"`{TAG_CONVENTION}` tag at the cited location. It is not evidence and "
    "does not change any evidence status; submit artifacts through "
    "evaluate_project_evidence to move a norm up the calibrated ladder."
)


def _accepted_norms_by_id(norms_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        n["norm_id"]: n
        for n in norms_payload.get("norms", [])
        if n.get("judge_verdict") == "accepted" and n.get("review_status") == "accepted"
    }


def _norm_status(norms_payload: dict[str, Any], norm_id: str) -> str | None:
    """Why a cited id is not joinable, or None when it is judge-accepted."""
    for n in norms_payload.get("norms", []):
        if n.get("norm_id") == norm_id:
            if n.get("judge_verdict") == "accepted" and n.get("review_status") == "accepted":
                return None
            return (
                f"norm exists but is not judge-accepted (judge_verdict="
                f"{n.get('judge_verdict')}, review_status={n.get('review_status')}); "
                "norms awaiting or failing review are excluded from runtime answers"
            )
    return "no norm with this id exists in the published graph"


def _accepted_alignments(
    alignments_payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """source_norm_id -> its judge-accepted HLEG alignments, minimal fields."""
    out: dict[str, list[dict[str, Any]]] = {}
    for a in alignments_payload.get("assertions", []):
        if a.get("judge_verdict") != "accepted":
            continue
        out.setdefault(a.get("source_norm_id"), []).append(
            {
                "target_id": a.get("target_id"),
                "relation_type": a.get("relation_type"),
                "final_score": a.get("final_score"),
                "assertion_id": a.get("id"),
            }
        )
    return out


def _validate_tag_records(tags: Any) -> str | None:
    """Structural validation; returns a human-readable problem or None."""
    if not isinstance(tags, list):
        return f"'tags' must be a list of tag records; got {type(tags).__name__}"
    for i, t in enumerate(tags):
        if not isinstance(t, dict):
            return f"tags[{i}] must be an object; got {type(t).__name__}"
        if not isinstance(t.get("norm_id"), str) or not t["norm_id"].strip():
            return f"tags[{i}].norm_id must be a non-empty string"
        if not isinstance(t.get("path"), str) or not t["path"].strip():
            return f"tags[{i}].path must be a non-empty string"
        line = t.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            return f"tags[{i}].line must be a positive integer"
    return None


def trace_implementation(
    classification_answer: dict[str, Any],
    tags: Any,
    norms_payload: dict[str, Any],
    alignments_payload: dict[str, Any],
    dump: dict[str, Any],
    actor: str | None = None,
) -> dict[str, Any]:
    """Coverage matrix between applicable judge-accepted norms and tag records.

    classification_answer is the classify_ai_system envelope (or bare answer),
    exactly as get_applicable_requirements takes it; the applicable set is
    computed by that same engine, so this tool can never claim a norm
    applicable that the requirements path would not serve.
    """
    graph_version = _graph_version(dump)

    problem = _validate_tag_records(tags)
    if problem is not None:
        return make_envelope(
            answer=None,
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[problem],
        )

    req_env = get_applicable_requirements(
        classification_answer, norms_payload, dump, actor=actor
    )
    req_answer = req_env.get("answer") or {}
    by_article = req_answer.get("requirements_by_article") or {}

    accepted = _accepted_norms_by_id(norms_payload)
    alignments = _accepted_alignments(alignments_payload)

    # code -> requirement: validate every tag against the accepted set.
    valid_tags: list[dict[str, Any]] = []
    invalid_tags: list[dict[str, Any]] = []
    for t in tags:
        reason = _norm_status(norms_payload, t["norm_id"])
        record = {"norm_id": t["norm_id"], "path": t["path"], "line": t["line"]}
        if reason is None:
            valid_tags.append(record)
        else:
            invalid_tags.append({**record, "reason": reason})

    locations_by_norm: dict[str, list[dict[str, Any]]] = {}
    for t in valid_tags:
        locations_by_norm.setdefault(t["norm_id"], []).append(
            {"path": t["path"], "line": t["line"]}
        )

    # requirement -> code: one row per applicable accepted norm.
    rows: list[dict[str, Any]] = []
    applicable_ids: set[str] = set()
    for article, norms in by_article.items():
        for n in norms:
            norm_id = n.get("norm_id")
            if not norm_id or norm_id not in accepted:
                continue
            applicable_ids.add(norm_id)
            locations = locations_by_norm.get(norm_id, [])
            rows.append(
                {
                    "norm_id": norm_id,
                    "article": article,
                    "source_node_id": n.get("source_node_id"),
                    "source_span_id": n.get("source_span_id"),
                    "actor": n.get("actor_inferred") or n.get("actor_explicit"),
                    "hleg_alignments": alignments.get(norm_id, []),
                    "trace_locations": locations,
                    "trace_status": "traced" if locations else "untraced",
                }
            )

    # Valid tags citing accepted norms that are NOT applicable to this
    # classification: real norms, but out of scope for this system. Reported,
    # never folded into the matrix.
    out_of_scope = [t for t in valid_tags if t["norm_id"] not in applicable_ids]

    traced = sum(1 for r in rows if r["trace_status"] == "traced")
    answer = {
        "tool": "trace_implementation",
        "tag_convention": TAG_CONVENTION,
        "matrix": rows,
        "summary": {
            "applicable_norms": len(rows),
            "traced": traced,
            "untraced": len(rows) - traced,
            "invalid_tags": len(invalid_tags),
            "out_of_scope_tags": len(out_of_scope),
        },
        "invalid_tags": invalid_tags,
        "out_of_scope_tags": out_of_scope,
        "trace_note": _TRACE_NOTE,
        "hleg_caveat": HLEG_MAPPING_CAVEAT,
    }
    # The envelope status mirrors the requirements engine's own verdict for
    # this classification: traces never raise it (a claim is not evidence),
    # and an unsettled classification stays unsettled here too.
    return make_envelope(
        answer=answer,
        status=req_env.get("status", "requires_human_review"),
        graph_version=graph_version,
        confidence=req_env.get("confidence", 0.0),
        source_nodes=req_env.get("source_nodes"),
        missing_facts=req_env.get("missing_facts"),
    )

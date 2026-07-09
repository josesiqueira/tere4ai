"""Section 8 required tool: trace_alignment as a pure, deterministic function.

Renders EU AI Act to HLEG alignments as their full reified chains, never as
bare edges (DEC-05 storage discipline carried into presentation): every
assertion is shown with its relation type, score dimensions, final score,
build-time judge verdict and rationale, the MappingRun (generator model and
prompt version), the JudgeRun (judge model and rationale), and the evidence
span ids on BOTH sides. The queried id may be a norm_id (all assertions from
that norm) or an HLEG requirement id (all assertions targeting it). Assembly
is structural over the judged alignments build artifact; no model is called,
so the envelope judge_verdict is not_applicable_deterministic while each
assertion carries its own build-time verdict.

@implements: DEC-08
@grounded_by: REF-17, REF-16
"""

from __future__ import annotations

from typing import Any

from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT
from tere4ai.mcp_server.tools import make_envelope


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _index_runs(alignments_payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        run["id"]: run
        for run in alignments_payload.get(key, [])
        if isinstance(run, dict) and "id" in run
    }


def _render_assertion(
    assertion: dict[str, Any],
    mapping_runs: dict[str, dict[str, Any]],
    judge_runs: dict[str, dict[str, Any]],
    missing_facts: list[str],
) -> dict[str, Any]:
    """One assertion as its full reified chain, never a bare edge."""
    mapping_run = mapping_runs.get(str(assertion.get("mapping_run_id")))
    judge_run = judge_runs.get(str(assertion.get("judge_run_id")))
    if mapping_run is None:
        missing_facts.append(
            f"mapping_run '{assertion.get('mapping_run_id')}' of assertion "
            f"'{assertion.get('id')}' is not present in the alignments payload"
        )
    if judge_run is None:
        missing_facts.append(
            f"judge_run '{assertion.get('judge_run_id')}' of assertion "
            f"'{assertion.get('id')}' is not present in the alignments payload"
        )
    return {
        "assertion_id": assertion.get("id"),
        "source_norm_id": assertion.get("source_norm_id"),
        "target_id": assertion.get("target_id"),
        "relation_type": assertion.get("relation_type"),
        "scores": dict(assertion.get("scores") or {}),
        "final_score": assertion.get("final_score"),
        "judge_verdict": assertion.get("judge_verdict"),
        "rationale": assertion.get("rationale"),
        "review_status": assertion.get("review_status"),
        "evidence": {
            "source_evidence_span_ids": list(assertion.get("source_evidence_span_ids", [])),
            "target_evidence_span_ids": list(assertion.get("target_evidence_span_ids", [])),
            "source_quote": assertion.get("source_quote"),
            "target_quote": assertion.get("target_quote"),
        },
        "mapping_run": {
            "id": (mapping_run or {}).get("id", assertion.get("mapping_run_id")),
            "generator_model": (mapping_run or {}).get("generator_model"),
            "prompt_version": (mapping_run or {}).get("prompt_version"),
        },
        "judge_run": {
            "id": (judge_run or {}).get("id", assertion.get("judge_run_id")),
            "judge_model": (judge_run or {}).get("judge_model"),
            "prompt_version": (judge_run or {}).get("prompt_version"),
            "verdict": (judge_run or {}).get("verdict"),
            "rationale": (judge_run or {}).get("rationale"),
            "corrected_relation_type": (judge_run or {}).get("corrected_relation_type"),
        },
    }


def trace_alignment(
    id: str,  # noqa: A002 - the Section 8 tool contract names this parameter id
    alignments_payload: dict[str, Any],
    dump: dict[str, Any],
) -> dict[str, Any]:
    """All reified alignment chains for a norm_id or an HLEG requirement id.

    A norm_id selects every assertion made FROM that norm; an HLEG id
    (hleg:...) selects every assertion TARGETING it. An id matching neither
    side returns status not_applicable with missing_facts, never an
    exception. Non-accepted assertions are included with their verdicts;
    hiding rejections would misstate the evidence.
    """
    graph_version = _graph_version(dump)
    assertions = [
        a for a in alignments_payload.get("assertions", []) if isinstance(a, dict)
    ]

    as_source = [a for a in assertions if a.get("source_norm_id") == id]
    as_target = [a for a in assertions if a.get("target_id") == id]
    if as_source:
        mode, selected = "norm", as_source
    elif as_target:
        mode, selected = "hleg_target", as_target
    else:
        return make_envelope(
            answer={"id": id, "found": False},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"id '{id}' matches no assertion source_norm_id and no assertion "
                f"target_id in the alignments payload (build "
                f"{alignments_payload.get('build', {}).get('build_id', 'unknown')})"
            ],
        )

    mapping_runs = _index_runs(alignments_payload, "mapping_runs")
    judge_runs = _index_runs(alignments_payload, "judge_runs")
    missing_facts: list[str] = []
    rendered = [
        _render_assertion(a, mapping_runs, judge_runs, missing_facts) for a in selected
    ]
    accepted = [r for r in rendered if r["judge_verdict"] == "accepted"]

    # Evidence span stubs for the envelope, both sides, deduplicated in order.
    span_ids: list[str] = []
    for r in rendered:
        for side in ("source_evidence_span_ids", "target_evidence_span_ids"):
            for span_id in r["evidence"][side]:
                if span_id not in span_ids:
                    span_ids.append(span_id)

    node_index = {
        n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n
    }
    answer = {
        "id": id,
        "found": True,
        "mode": mode,
        "assertion_count": len(rendered),
        "accepted_count": len(accepted),
        "caveat": HLEG_MAPPING_CAVEAT,
        "assertions": rendered,
        "alignments_build_id": str(
            alignments_payload.get("build", {}).get("build_id", "unknown")
        ),
    }

    return make_envelope(
        answer=answer,
        status="satisfied_with_evidence" if not missing_facts else "requires_human_review",
        graph_version=graph_version,
        confidence=1.0 if not missing_facts else 0.5,
        source_nodes=[
            n
            for n in dict.fromkeys(str(a.get("source_norm_id", "")) for a in selected)
            if n in node_index
        ],
        source_spans=[{"span_id": s} for s in span_ids],
        graph_evidence_subgraph={
            "nodes": list(
                dict.fromkeys(
                    [id]
                    + [str(a.get("source_norm_id")) for a in selected]
                    + [str(a.get("target_id")) for a in selected]
                )
            ),
            "edges": [
                {
                    "from": r["source_norm_id"],
                    "via_assertion": r["assertion_id"],
                    "to": r["target_id"],
                    "relation_type": r["relation_type"],
                    "judge_verdict": r["judge_verdict"],
                }
                for r in rendered
            ],
        },
        legal_status_notes=[HLEG_MAPPING_CAVEAT],
        missing_facts=missing_facts,
    )

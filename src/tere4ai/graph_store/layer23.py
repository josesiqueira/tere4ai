"""Adapter: norms and alignment results into graph nodes and edges.

@implements: DEC-03 (partial: persistence), DEC-05 (partial: persistence)
@grounded_by: REF-11, REF-24

Converts the extraction pipeline output ({norms, judge_runs, stats}) and the
alignment pipeline output ({assertions, mapping_runs, judge_runs, stats})
into the generic nodes-plus-edges shape that GraphStore.load_dump writes.

Provenance rules (architecture.md Section 2) hold here too: every edge
carries a provenance class and a derivation id. A norm's DERIVED_FROM edge is
LLM_JUDGED_ACCEPTED only when the extraction judge accepted it, otherwise
LLM_CANDIDATE. Reified alignment structure per Section 4: the assertion node
links to the source norm, the target HLEG requirement, its MappingRun, and
its JudgeRun; there is no direct norm-to-HLEG truth edge.
"""

from __future__ import annotations

from typing import Any

_NORM_SCALAR_FIELDS = (
    "deontic_type",
    "modal",
    "actor_explicit",
    "actor_inferred",
    "actor_inference_source_node_id",
    "action",
    "object",
    "target_system_category",
    "source_node_id",
    "source_span_id",
    "extraction_method",
    "extractor_model",
    "extractor_prompt_version",
    "confidence",
    "judge_verdict",
    "judge_run_id",
    "review_status",
)


def _edge(
    edge_id: str,
    edge_type: str,
    from_id: str,
    to_id: str,
    provenance_class: str,
    derivation_id: str,
    method: str,
    build_id: str,
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "from": from_id,
        "to": to_id,
        "provenance_class": provenance_class,
        "derivation_id": derivation_id,
        "method": method,
        "confidence": 1.0,
        "review_status": "auto_accepted",
        "build_id": build_id,
    }


def _judge_run_node(run: dict[str, Any]) -> dict[str, Any]:
    node = {"id": run["id"], "layer": 3, "type": "JudgeRun"}
    for k in (
        "judge_kind",
        "judge_model",
        "prompt_version",
        "verdict",
        "rationale",
        "started_at",
        "completed_at",
        "build_id",
    ):
        if run.get(k) is not None:
            node[k] = run[k]
    scores = run.get("scores") or {}
    for k, v in scores.items():
        node[f"score_{k}"] = v
    return node


def norms_to_graph(norms_result: dict[str, Any], build_id: str | None = None) -> dict[str, Any]:
    """Norms pipeline output -> {nodes, edges} for GraphStore.load_dump."""
    build_id = build_id or "layer2-adhoc"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for run in norms_result.get("judge_runs", []):
        nodes.append(_judge_run_node(run))

    for norm in norms_result.get("norms", []):
        node: dict[str, Any] = {"id": norm["norm_id"], "layer": 2, "type": "NormativeStatement"}
        for k in _NORM_SCALAR_FIELDS:
            if norm.get(k) is not None:
                node[k] = norm[k]
        for k in ("condition_ids", "exception_ids", "lifecycle_phase_ids"):
            if norm.get(k):
                node[k] = norm[k]
        # inline condition/exception text lists from the generator, if present
        for k in ("conditions", "exceptions"):
            if norm.get(k):
                node[k] = [str(x) for x in norm[k]]
        nodes.append(node)

        accepted = norm.get("judge_verdict") == "accepted"
        edges.append(
            _edge(
                f"edge:{norm['norm_id']}:derived",
                "DERIVED_FROM",
                norm["norm_id"],
                norm["source_node_id"],
                "LLM_JUDGED_ACCEPTED" if accepted else "LLM_CANDIDATE",
                norm.get("judge_run_id") or f"derivation:{norm['norm_id']}",
                norm.get("extraction_method", "llm_extract_v1"),
                build_id,
            )
        )
        if norm.get("judge_run_id"):
            edges.append(
                _edge(
                    f"edge:{norm['norm_id']}:judged",
                    "JUDGED_BY",
                    norm["norm_id"],
                    norm["judge_run_id"],
                    "EXTRACTED_SOURCE",
                    norm["judge_run_id"],
                    "judge_link",
                    build_id,
                )
            )
    return {"nodes": nodes, "edges": edges}


def alignments_to_graph(
    align_result: dict[str, Any],
    hleg_nodes: list[dict[str, Any]],
    build_id: str | None = None,
) -> dict[str, Any]:
    """Alignment pipeline output -> {nodes, edges}; includes the HLEG targets."""
    build_id = build_id or "layer3-adhoc"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for h in hleg_nodes:
        node = {k: v for k, v in h.items() if k != "source_span"}
        span = h.get("source_span") or {}
        for k, v in span.items():
            node[f"span_{k}"] = v
        nodes.append(node)

    for run in align_result.get("mapping_runs", []):
        node = {"id": run["id"], "layer": 3, "type": "MappingRun"}
        node.update({k: v for k, v in run.items() if k not in {"id", "type", "layer"}})
        nodes.append(node)
    for run in align_result.get("judge_runs", []):
        nodes.append(_judge_run_node(run))

    for a in align_result.get("assertions", []):
        node = {"id": a["id"], "layer": 3, "type": "AlignmentAssertion"}
        for k in (
            "relation_type",
            "final_score",
            "judge_verdict",
            "review_status",
            "rationale",
            "source_norm_id",
            "target_id",
            "mapping_run_id",
            "judge_run_id",
        ):
            if a.get(k) is not None:
                node[k] = a[k]
        node["source_evidence_span_ids"] = a.get("source_evidence_span_ids", [])
        node["target_evidence_span_ids"] = a.get("target_evidence_span_ids", [])
        for k, v in (a.get("scores") or {}).items():
            node[f"score_{k}"] = v
        nodes.append(node)

        accepted = a.get("judge_verdict") == "accepted"
        prov = "LLM_JUDGED_ACCEPTED" if accepted else "LLM_CANDIDATE"
        edges.append(
            _edge(
                f"edge:{a['id']}:of",
                "ASSERTS_ALIGNMENT_OF",
                a["id"],
                a["source_norm_id"],
                prov,
                a["judge_run_id"],
                "alignment_link",
                build_id,
            )
        )
        edges.append(
            _edge(
                f"edge:{a['id']}:to",
                "ASSERTS_ALIGNMENT_TO",
                a["id"],
                a["target_id"],
                prov,
                a["judge_run_id"],
                "alignment_link",
                build_id,
            )
        )
        edges.append(
            _edge(
                f"edge:{a['id']}:run",
                "PRODUCED_BY_MAPPING_RUN",
                a["id"],
                a["mapping_run_id"],
                "EXTRACTED_SOURCE",
                a["mapping_run_id"],
                "alignment_link",
                build_id,
            )
        )
        edges.append(
            _edge(
                f"edge:{a['id']}:judged",
                "JUDGED_BY",
                a["id"],
                a["judge_run_id"],
                "EXTRACTED_SOURCE",
                a["judge_run_id"],
                "judge_link",
                build_id,
            )
        )
    return {"nodes": nodes, "edges": edges}

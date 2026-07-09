"""Section 8 required tool: explain_requirement as a pure, deterministic function.

Explains ONE NormativeStatement from the judged Layer 2 build artifact: its
deontic decomposition (actor, modal, action, object, conditions, exceptions),
the full text of its source unit resolved in the Layer 0+1 dump, the Article
3 definitions whose terms literally occur in the norm's action or object
(best-effort word-boundary match over the definition terms), its accepted
HLEG alignment targets with relation types and final scores, and a span
trace (span ids plus snapshot files). Assembly is structural over already
judged data; no model is called, so the envelope judge_verdict is
not_applicable_deterministic while the norm's own build-time judge verdict
and review status are reported prominently inside the answer. Non-accepted
norms are still explainable; their review status downgrades the envelope
status to requires_human_review, never silently.

@implements: DEC-08
@grounded_by: REF-17, REF-16
"""

from __future__ import annotations

import re
from typing import Any

from tere4ai.mcp_server.tools import make_envelope

ARTICLE_3_PREFIX = "eu-ai-act:article-3:"

# The EU-to-HLEG mappings are LLM-generated and judged, not expert-validated;
# this caveat must surface whenever they are presented (@USER.md guardrail).
HLEG_MAPPING_CAVEAT = (
    "EU AI Act to HLEG alignments are LLM-generated and LLM-judged, not "
    "expert-validated; treat them as auditable claims, not settled mappings."
)

_QUOTE_CHARS = "'\"‘’“”"


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _definition_term(text: str) -> str | None:
    """The defined term of an Article 3 point: the text before ' means ',
    stripped of any surrounding quote characters. Best effort; None when the
    point does not follow the 'term means definition' shape."""
    head, sep, _ = text.partition(" means ")
    if not sep:
        return None
    term = head.strip().strip(_QUOTE_CHARS).strip()
    return term or None


def _matched_definitions(
    norm: dict[str, Any], dump: dict[str, Any]
) -> list[dict[str, Any]]:
    """Article 3 point nodes whose defined term literally occurs in the
    norm's action or object (case-insensitive, word-boundary match)."""
    haystack = f"{norm.get('action') or ''} {norm.get('object') or ''}".lower()
    matched: list[dict[str, Any]] = []
    for node in dump.get("nodes", []):
        if node.get("type") != "Point" or not str(node.get("id", "")).startswith(
            ARTICLE_3_PREFIX
        ):
            continue
        term = _definition_term(str(node.get("text") or ""))
        if term is None:
            continue
        if re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", haystack):
            matched.append(
                {
                    "definition_node_id": node["id"],
                    "term": term,
                    "text": node.get("text"),
                }
            )
    return matched


def _accepted_alignments(
    norm_id: str, alignments_payload: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    accepted: list[dict[str, Any]] = []
    non_accepted = 0
    for assertion in alignments_payload.get("assertions", []):
        if assertion.get("source_norm_id") != norm_id:
            continue
        if assertion.get("judge_verdict") == "accepted":
            accepted.append(
                {
                    "assertion_id": assertion.get("id"),
                    "target_id": assertion.get("target_id"),
                    "relation_type": assertion.get("relation_type"),
                    "final_score": assertion.get("final_score"),
                    "source_evidence_span_ids": list(
                        assertion.get("source_evidence_span_ids", [])
                    ),
                    "target_evidence_span_ids": list(
                        assertion.get("target_evidence_span_ids", [])
                    ),
                }
            )
        else:
            non_accepted += 1
    return accepted, non_accepted


def _hleg_nodes() -> list[dict[str, Any]]:
    """The seven HLEG requirement nodes (deterministic, checksum-verified
    builder); empty when the frozen HLEG text is unavailable or drifted."""
    try:
        from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes

        return build_hleg_nodes()
    except Exception:  # noqa: BLE001 - degrade to dump-only span files
        return []


def explain_requirement(
    norm_id: str,
    dump: dict[str, Any],
    norms_payload: dict[str, Any],
    alignments_payload: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic explanation of one norm from the judged build artifacts.

    An unknown norm_id returns status not_applicable with missing_facts,
    never an exception. A norm whose build-time judge verdict is not
    accepted is still explained, with its review status stated prominently
    and the envelope status set to requires_human_review.
    """
    graph_version = _graph_version(dump)
    norm = next(
        (
            n
            for n in norms_payload.get("norms", [])
            if isinstance(n, dict) and n.get("norm_id") == norm_id
        ),
        None,
    )
    if norm is None:
        return make_envelope(
            answer={"norm_id": norm_id, "found": False},
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"norm_id '{norm_id}' is not present in the judged norms payload "
                f"(build {norms_payload.get('build', {}).get('build_id', 'unknown')})"
            ],
        )

    missing_facts: list[str] = []
    node_index = {
        n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n
    }

    # Source unit: full text resolved via source_node_id in the Layer 0+1 dump.
    source_node_id = str(norm.get("source_node_id", ""))
    source_node = node_index.get(source_node_id)
    source_span = (source_node or {}).get("source_span")
    if source_node is None:
        missing_facts.append(
            f"source node '{source_node_id}' of norm '{norm_id}' is not present "
            "in the graph dump; the source text cannot be rendered"
        )

    definitions = _matched_definitions(norm, dump)
    accepted, non_accepted = _accepted_alignments(norm_id, alignments_payload)

    # Span trace: the norm's own source span plus the evidence spans of its
    # accepted alignments, each with the snapshot file when resolvable. HLEG
    # target spans live outside the Layer 0+1 dump; their snapshot file comes
    # from the deterministic HLEG node builder when the frozen text is
    # available, else stays None (degraded, never an exception).
    span_files: dict[str, str | None] = {}
    for node in list(dump.get("nodes", [])) + _hleg_nodes():
        span = node.get("source_span") if isinstance(node, dict) else None
        if isinstance(span, dict) and span.get("span_id"):
            span_files[span["span_id"]] = span.get("snapshot_file")
    span_ids: list[str] = []
    for span_id in [norm.get("source_span_id")] + [
        s for a in accepted for side in ("source_evidence_span_ids", "target_evidence_span_ids")
        for s in a[side]
    ]:
        if isinstance(span_id, str) and span_id not in span_ids:
            span_ids.append(span_id)
    span_trace = [
        {"span_id": s, "snapshot_file": span_files.get(s)} for s in span_ids
    ]

    review_status = norm.get("review_status")
    build_judge_verdict = norm.get("judge_verdict")
    is_accepted = build_judge_verdict == "accepted"
    review_note = (
        "This norm is judge-accepted."
        if is_accepted
        else (
            f"CAUTION: this norm is NOT judge-accepted (build-time judge verdict "
            f"'{build_judge_verdict}', review status '{review_status}'). It is "
            "explained for transparency but is never returned as a requirement."
        )
    )

    answer = {
        "norm_id": norm_id,
        "found": True,
        "review_status": review_status,
        "build_judge_verdict": build_judge_verdict,
        "review_note": review_note,
        "deontic": {
            "deontic_type": norm.get("deontic_type"),
            "modal": norm.get("modal"),
            "actor": {
                "explicit": norm.get("actor_explicit"),
                "inferred": norm.get("actor_inferred"),
                "inference_source_node_id": norm.get("actor_inference_source_node_id"),
            },
            "action": norm.get("action"),
            "object": norm.get("object"),
            "conditions": list(norm.get("conditions") or []),
            "exceptions": list(norm.get("exceptions") or []),
            "target_system_category": norm.get("target_system_category"),
            "lifecycle_phase_ids": list(norm.get("lifecycle_phase_ids") or []),
        },
        "source": {
            "node_id": source_node_id,
            "type": (source_node or {}).get("type"),
            "text": (source_node or {}).get("text"),
        },
        "article_3_definitions": definitions,
        "hleg_alignments": {
            "accepted": accepted,
            "non_accepted_count": non_accepted,
            "caveat": HLEG_MAPPING_CAVEAT,
        },
        "span_trace": span_trace,
        "extraction": {
            "extraction_method": norm.get("extraction_method"),
            "extractor_model": norm.get("extractor_model"),
            "extractor_prompt_version": norm.get("extractor_prompt_version"),
            "confidence": norm.get("confidence"),
        },
    }

    source_nodes = [n for n in [source_node_id] if n in node_index] + [
        d["definition_node_id"] for d in definitions
    ]
    source_spans: list[dict[str, Any]] = []
    if isinstance(source_span, dict):
        source_spans.append(source_span)

    legal_status_notes = [HLEG_MAPPING_CAVEAT] if (accepted or non_accepted) else []
    if not is_accepted:
        legal_status_notes.append(review_note)

    return make_envelope(
        answer=answer,
        status="satisfied_with_evidence"
        if is_accepted and not missing_facts
        else "requires_human_review",
        graph_version=graph_version,
        confidence=1.0 if is_accepted else 0.5,
        source_nodes=source_nodes,
        source_spans=source_spans,
        graph_evidence_subgraph={
            "nodes": [norm_id, *source_nodes, *[a["target_id"] for a in accepted]],
            "edges": [
                {
                    "from": norm_id,
                    "via_assertion": a["assertion_id"],
                    "to": a["target_id"],
                    "relation_type": a["relation_type"],
                }
                for a in accepted
            ],
        },
        legal_status_notes=legal_status_notes,
        missing_facts=missing_facts,
    )

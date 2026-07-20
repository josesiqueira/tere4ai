"""M2 alignment pipeline: norms to HLEG requirements, with the mapping judge.

@implements: DEC-05, DEC-06 (partial: mapping judge)
@grounded_by: REF-24, REF-21, REF-10, REF-16

A mapping is an auditable claim, not law (architecture.md Section 4). Nothing
here stores a truth edge: every mapping is a reified AlignmentAssertion tied
to a MappingRun and a JudgeRun, with evidence spans on BOTH sides. The
generator (OpenAI family) proposes 0 to 3 candidate alignments per norm
against the closed set of seven HLEG requirements; the independent mapping
judge (Claude family) gates each candidate per Section 7. Hard invariants
enforced here:

- Only judge-accepted input norms are aligned; others are skipped and counted.
- Mechanical quote check, never trusted to models: source_quote must occur in
  the norm's source text and target_quote in the HLEG description
  (whitespace-normalised). A failing candidate never reaches the judge; it is
  recorded rejected in a JudgeRun-shaped record with judge_model
  "mechanical:quote_check".
- An assertion is accepted only on an accepting judge verdict, and never
  without evidence span ids on both sides (alignments.schema.json enforces
  minItems 1; invalid assertions are recorded and dropped).
- The judge may correct the relation type; corrected_relation_type overrides
  the proposed one.
- Every generator and judge call is logged to
  data/review_queue/alignment_log.jsonl (model id, prompt version, input
  hash, verdict and rationale for judge calls). Never API keys, never full
  prompts.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.extract_norms.model_clients import ModelClient
from tere4ai.extract_norms.pipeline import (
    REPO_ROOT,
    _call_json_with_retry,
    _fallback_judge_result,
    _input_hash,
    _judge_scores,
    _log_event,
    _now,
    load_prompt,
    prompt_sha256,
)
from tere4ai.judge.config import require_independent_clients

ALIGNMENTS_SCHEMA_PATH = REPO_ROOT / "schema" / "json_schemas" / "alignments.schema.json"
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "review_queue" / "alignment_log.jsonl"

MECHANICAL_JUDGE_MODEL = "mechanical:quote_check"
MAX_CANDIDATES_PER_NORM = 3

# Relation types the generator may propose. no_clear_relation is never
# proposed: it is expressed by omitting the pair (Section 4).
PROPOSABLE_RELATION_TYPES = (
    "directly_operationalizes",
    "partially_operationalizes",
    "supports",
    "related_to",
    "conflicts_with",
)
RELATION_TYPES = (*PROPOSABLE_RELATION_TYPES, "no_clear_relation")

_WHITESPACE = re.compile(r"\s+")


def _alignments_validator() -> Draft202012Validator:
    schema = json.loads(ALIGNMENTS_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _mechanical_gate_sha256() -> str:
    """Content hash of the mechanical quote-check logic (audit W2).

    The mechanical gate has no prompt, but its JudgeRuns still deserve the
    same tamper-evidence as the LLM judges: hash the source of the gate's
    two functions so a silent edit to the whitespace normalisation or the
    substring check is detectable on the records it produced.
    """
    import inspect

    return prompt_sha256(
        inspect.getsource(_normalise_ws) + inspect.getsource(_quote_found)
    )


def _normalise_ws(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _quote_found(quote: Any, text: str) -> bool:
    """Whitespace-normalised substring check; never trusted to a model."""
    if not isinstance(quote, str) or not quote.strip():
        return False
    return _normalise_ws(quote) in _normalise_ws(text)


def _id_suffix(prefixed_id: str) -> str:
    """Strip the leading namespace, e.g. norm:x:y -> x:y, hleg:z -> z."""
    return prefixed_id.split(":", 1)[1] if ":" in prefixed_id else prefixed_id


def _generator_user_message(norm: dict[str, Any], hleg_nodes: list[dict[str, Any]]) -> str:
    lines = [
        f"Norm id: {norm['norm_id']}",
        f"Deontic type: {norm['deontic_type']}",
        f"Actor: {norm.get('actor_explicit') or norm.get('actor_inferred') or 'unspecified'}",
        f"Action: {norm['action']}",
        f"Object: {norm['object']}",
        f"Conditions: {json.dumps(norm.get('conditions') or [], ensure_ascii=False)}",
        f"Exceptions: {json.dumps(norm.get('exceptions') or [], ensure_ascii=False)}",
        "Verbatim legal source text of the norm:",
        norm["source_text"],
        "",
        "The seven HLEG requirements (closed set, quote target_quote from the description):",
    ]
    for node in hleg_nodes:
        lines.append(f"--- {node['id']} ({node['name']}) ---")
        lines.append(node["description"])
    return "\n".join(lines)


def _judge_user_message(
    norm: dict[str, Any], target: dict[str, Any], candidate: dict[str, Any]
) -> str:
    return (
        f"Norm id: {norm['norm_id']}\n"
        f"Verbatim legal source text of the norm:\n{norm['source_text']}\n\n"
        f"Target HLEG requirement: {target['id']} ({target['name']})\n"
        f"HLEG requirement description:\n{target['description']}\n\n"
        f"Candidate alignment (JSON):\n{json.dumps(candidate, ensure_ascii=False, indent=1)}"
    )


def _zero_scores() -> dict[str, float]:
    return {
        "semantic_similarity": 0.0,
        "normative_relevance": 0.0,
        "operational_utility": 0.0,
        "evidence_strength": 0.0,
        "judge_confidence": 0.0,
    }


def _mechanical_judge_run(
    judge_run_id: str,
    prompt_version: str,
    build_id: str,
    started_at: str,
) -> dict[str, Any]:
    """JudgeRun-shaped record for a candidate that failed the quote check.

    No model call happened: the mechanical check saves the cost and keeps the
    audit trail (a rejected verdict with an explicit mechanical judge_model).
    """
    return {
        "id": judge_run_id,
        "type": "JudgeRun",
        "layer": 3,
        "judge_kind": "mapping",
        "judge_model": MECHANICAL_JUDGE_MODEL,
        "prompt_version": prompt_version,
        "prompt_sha256": _mechanical_gate_sha256(),
        "verdict": "rejected",
        "scores": _zero_scores(),
        "rationale": "quote not found in source",
        "corrected_relation_type": None,
        "review_status": "rejected",
        "started_at": started_at,
        "completed_at": _now(),
        "build_id": build_id,
    }


def align_norms(
    norms: list[dict[str, Any]],
    hleg_nodes: list[dict[str, Any]],
    generator: ModelClient,
    judge: ModelClient,
    prompt_version: str = "v1",
    log_path: Path | None = None,
    build_id: str = "adhoc",
) -> dict[str, Any]:
    """Run the judged alignment of accepted norms against the HLEG nodes.

    Each norm dict must carry, besides its norms.schema.json fields, a
    "source_text" field with the verbatim text of its source unit (the CLI
    resolves it from the layer1 dump via source_node_id). Returns
    {"assertions": [...], "mapping_runs": [...], "judge_runs": [...],
    "stats": {...}}. Assertions conform to the AlignmentAssertion shape in
    alignments.schema.json; invalid ones are recorded in stats and dropped.
    """
    require_independent_clients(generator, judge)
    log_path = log_path or DEFAULT_LOG_PATH
    align_prompt = load_prompt("align_hleg", prompt_version)
    judge_prompt = load_prompt("judge_alignment", prompt_version)
    align_prompt_sha256 = prompt_sha256(align_prompt)
    judge_prompt_sha256 = prompt_sha256(judge_prompt)
    validator = _alignments_validator()
    hleg_by_id = {node["id"]: node for node in hleg_nodes}

    mapping_run = {
        "id": f"mappingrun:{uuid.uuid4().hex[:12]}",
        "type": "MappingRun",
        "layer": 3,
        "generator_model": generator.model,
        "prompt_version": prompt_version,
        "prompt_sha256": align_prompt_sha256,
        "started_at": _now(),
        "build_id": build_id,
    }

    assertions: list[dict[str, Any]] = []
    judge_runs: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "norms_total": len(norms),
        "norms_skipped_not_accepted": 0,
        "norms_failed": [],
        "zero_alignment_norms": 0,
        "candidates": 0,
        "mechanical_rejects": [],
        "invalid_candidates": [],
        "invalid_assertions": [],
        "verdicts": {"accepted": 0, "rejected": 0, "needs_human_review": 0},
    }

    for norm in norms:
        norm_id = norm.get("norm_id", "norm:unknown")
        if norm.get("judge_verdict") != "accepted":
            # Only judge-accepted norms are aligned (Section 7 gating).
            stats["norms_skipped_not_accepted"] += 1
            continue
        source_text = norm.get("source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            stats["norms_failed"].append({"norm_id": norm_id, "reason": "missing source_text"})
            continue
        if not norm.get("source_span_id"):
            stats["norms_failed"].append({"norm_id": norm_id, "reason": "missing source_span_id"})
            continue

        gen_user = _generator_user_message(norm, hleg_nodes)
        parsed, error = _call_json_with_retry(generator, align_prompt, gen_user)
        _log_event(
            log_path,
            {
                "timestamp": _now(),
                "direction": "generator",
                "norm_id": norm_id,
                "model": generator.model,
                "prompt_version": prompt_version,
                "prompt_sha256": align_prompt_sha256,
                "input_sha256": _input_hash(gen_user),
                "parse_ok": parsed is not None,
                "error": error,
            },
        )
        if parsed is None:
            stats["norms_failed"].append({"norm_id": norm_id, "reason": error})
            continue

        candidates = parsed.get("alignments")
        if not isinstance(candidates, list):
            stats["norms_failed"].append(
                {"norm_id": norm_id, "reason": "generator JSON lacks an 'alignments' list"}
            )
            continue
        if not candidates:
            # Zero alignments is a valid answer: no_clear_relation is the
            # default and a mapping is never forced (Section 4).
            stats["zero_alignment_norms"] += 1
            continue
        if len(candidates) > MAX_CANDIDATES_PER_NORM:
            stats["invalid_candidates"].append(
                {
                    "norm_id": norm_id,
                    "reason": f"generator proposed {len(candidates)} candidates; "
                    f"kept the first {MAX_CANDIDATES_PER_NORM}",
                }
            )
            candidates = candidates[:MAX_CANDIDATES_PER_NORM]

        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                stats["invalid_candidates"].append(
                    {"norm_id": norm_id, "reason": "candidate is not a JSON object"}
                )
                continue
            target_id = candidate.get("target_id")
            target = hleg_by_id.get(target_id)
            if target is None:
                # The seven-requirement set is closed; an unknown target id
                # is an invented requirement and never enters the graph.
                stats["invalid_candidates"].append(
                    {"norm_id": norm_id, "reason": f"unknown target_id: {target_id!r}"}
                )
                continue
            proposed_relation = candidate.get("relation_type")
            if proposed_relation not in PROPOSABLE_RELATION_TYPES:
                stats["invalid_candidates"].append(
                    {
                        "norm_id": norm_id,
                        "target_id": target_id,
                        "reason": f"invalid relation_type: {proposed_relation!r}",
                    }
                )
                continue
            target_span_id = (target.get("source_span") or {}).get("span_id")
            if not target_span_id:
                stats["invalid_candidates"].append(
                    {
                        "norm_id": norm_id,
                        "target_id": target_id,
                        "reason": "target HLEG node has no source span",
                    }
                )
                continue

            stats["candidates"] += 1
            norm_suffix = _id_suffix(norm_id)
            target_suffix = _id_suffix(target_id)
            judge_run_id = f"judgerun:mapping:{norm_suffix}:{target_suffix}:c{index}"

            source_quote_ok = _quote_found(candidate.get("source_quote"), source_text)
            target_quote_ok = _quote_found(candidate.get("target_quote"), target["description"])
            if not (source_quote_ok and target_quote_ok):
                # Mechanical rejection: no judge call, no assertion. The
                # JudgeRun-shaped record keeps the audit trail.
                started_at = _now()
                judge_runs.append(
                    _mechanical_judge_run(judge_run_id, prompt_version, build_id, started_at)
                )
                stats["mechanical_rejects"].append(
                    {
                        "norm_id": norm_id,
                        "target_id": target_id,
                        "source_quote_found": source_quote_ok,
                        "target_quote_found": target_quote_ok,
                    }
                )
                _log_event(
                    log_path,
                    {
                        "timestamp": _now(),
                        "direction": "mechanical",
                        "norm_id": norm_id,
                        "target_id": target_id,
                        "model": MECHANICAL_JUDGE_MODEL,
                        "prompt_version": prompt_version,
                        "input_sha256": _input_hash(
                            json.dumps(candidate, ensure_ascii=False, sort_keys=True)
                        ),
                        "verdict": "rejected",
                        "rationale": "quote not found in source",
                    },
                )
                continue

            judge_user = _judge_user_message(norm, target, candidate)
            judge_started = _now()
            judged, judge_error = _call_json_with_retry(judge, judge_prompt, judge_user)
            if judged is None or judged.get("verdict") not in (
                "accepted",
                "rejected",
                "needs_human_review",
            ):
                judged = _fallback_judge_result(judge_error or "missing or invalid verdict")
            verdict = judged["verdict"]
            scores = _judge_scores(judged)
            rationale = str(judged.get("rationale") or "no rationale returned")
            corrected = judged.get("corrected_relation_type")
            if corrected not in RELATION_TYPES:
                corrected = None

            _log_event(
                log_path,
                {
                    "timestamp": _now(),
                    "direction": "judge",
                    "norm_id": norm_id,
                    "target_id": target_id,
                    "model": judge.model,
                    "prompt_version": prompt_version,
                    "prompt_sha256": judge_prompt_sha256,
                    "input_sha256": _input_hash(judge_user),
                    "verdict": verdict,
                    "corrected_relation_type": corrected,
                    "rationale": rationale,
                },
            )

            judge_run = {
                "id": judge_run_id,
                "type": "JudgeRun",
                "layer": 3,
                "judge_kind": "mapping",
                "judge_model": judge.model,
                "prompt_version": prompt_version,
                "prompt_sha256": judge_prompt_sha256,
                "verdict": verdict,
                "scores": scores,
                "rationale": rationale,
                "corrected_relation_type": corrected,
                "started_at": judge_started,
                "completed_at": _now(),
                "build_id": build_id,
            }

            assertion = {
                "id": f"align:{norm_suffix}:{target_suffix}:{index}",
                "type": "AlignmentAssertion",
                "layer": 3,
                "source_norm_id": norm_id,
                "target_id": target_id,
                "relation_type": corrected or proposed_relation,
                "source_evidence_span_ids": [norm["source_span_id"]],
                "target_evidence_span_ids": [target_span_id],
                "source_quote": candidate.get("source_quote"),
                "target_quote": candidate.get("target_quote"),
                "scores": scores,
                "final_score": sum(scores.values()) / len(scores),
                "mapping_run_id": mapping_run["id"],
                "judge_run_id": judge_run_id,
                "judge_verdict": verdict,
                "rationale": rationale,
                "review_status": "accepted" if verdict == "accepted" else "needs_review",
            }

            errors = sorted(validator.iter_errors(assertion), key=lambda e: list(e.path))
            if errors:
                stats["invalid_assertions"].append(
                    {
                        "norm_id": norm_id,
                        "target_id": target_id,
                        "assertion_id": assertion["id"],
                        "errors": [err.message for err in errors[:5]],
                    }
                )
                # The judge decision stays logged and kept (Section 7), but
                # the invalid assertion never enters the output.
                judge_runs.append(judge_run)
                continue

            stats["verdicts"][verdict] += 1
            judge_runs.append(judge_run)
            assertions.append(assertion)

    mapping_run["completed_at"] = _now()
    return {
        "assertions": assertions,
        "mapping_runs": [mapping_run],
        "judge_runs": judge_runs,
        "stats": stats,
    }

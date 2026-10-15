"""MILESTONE2 alignment pipeline: norms to HLEG requirements, with the mapping judge.

@implements: DEC-05, DEC-06 (partial: mapping judge)
@implements: DEC-28 (partial: the v2 generator input, the reply guard, the kept candidate fields and the spread)
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
  the proposed one, which the assertion keeps as proposed_relation_type with
  the generator's rationale (DEC-28).
- Every generator and judge call is logged to
  data/review_queue/alignment_log.jsonl (model id, prompt version, input
  hash, verdict and rationale for judge calls). Never API keys, never full
  prompts.
- B164 (spec F D-F30 as amended 2026-10-12): with max_in_flight above 1 the
  norms' model calls run on worker threads, at most max_in_flight norms at
  once (tere4ai.parallel_calls); each norm's request is built from that norm
  alone, and the assertions, judge runs and stats (the spread counts
  included) are assembled in the norms' order in the calling thread, which
  also validates every assertion, so the result equals a run with one call at
  a time; the log lines come in the order the calls finish.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.act_parties import actor_slots_for_digests, slots_of
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
from tere4ai.parallel_calls import run_in_flight

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

# DEC-28 (spec G D-G86 (1), G2): a v1 run keeps the generator input v1 had,
# its party labelled "Actor:", and v1's handling of the judge's reply, so the
# version names one instrument. From v2 on the label is "Addressee:" (spec G
# D-G80's word) and a no_clear_relation correction with any verdict but
# "rejected" is unusable (CHANGE3).
_PROMPTS_WITH_ACTOR_LABEL = frozenset({"v1"})
_PROMPTS_TAKING_ANY_CORRECTION = frozenset({"v1"})

# The prompt version align_hleg and judge_alignment share (DEC-28: v2 is the
# version of record for B74; v1 is the July build's, never edited).
# 2026-10-15 (B174): judge_alignment v3 is v2 plus a paragraph stating that
# the legal text is the Act as amended by the Digital Omnibus, in force;
# align_hleg v3 is byte-identical to v2 under the new version line. v3 is the
# default and the version of record, and every v1-only gate above treats it
# as v2.
DEFAULT_PROMPT_VERSION = "v3"

# spec G D-G86 (5), R13: the spread across the requirements, as found.
SPREAD_KEYS = (
    "assertions_by_requirement",
    "accepted_by_requirement",
    "pairs_by_requirement",
    "accepted_pairs_by_requirement",
)

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


def _generator_user_message(
    norm: dict[str, Any], hleg_nodes: list[dict[str, Any]], *, prompt_version: str
) -> str:
    if prompt_version in _PROMPTS_WITH_ACTOR_LABEL:
        # brief R50 (B145): v1's input reads the party through the digests' helper
        slots = actor_slots_for_digests(norm)
        party = f"Actor: {slots['actor_explicit'] or slots['actor_inferred'] or 'unspecified'}"
    else:
        explicit, inferred, _source = slots_of(norm)
        party = f"Addressee: {explicit or inferred or 'unspecified'}"
    lines = [
        f"Norm id: {norm['norm_id']}",
        f"Deontic type: {norm['deontic_type']}",
        party,
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


def judge_texts(norm: dict[str, Any], target: dict[str, Any]) -> dict[str, str]:
    """The texts the alignment judge's message holds, as it holds them: the
    norm's verbatim source text and the target requirement's name and
    description. The E1 label sheet shows the same (spec G D-G86 (4) (d))."""
    return {
        "norm_source_text": norm["source_text"],
        "hleg_requirement": f"{target['id']} ({target['name']})",
        "hleg_description": target["description"],
    }


def _judge_user_message(
    norm: dict[str, Any], target: dict[str, Any], candidate: dict[str, Any]
) -> str:
    texts = judge_texts(norm, target)
    return (
        f"Norm id: {norm['norm_id']}\n"
        f"Verbatim legal source text of the norm:\n{texts['norm_source_text']}\n\n"
        f"Target HLEG requirement: {texts['hleg_requirement']}\n"
        f"HLEG requirement description:\n{texts['hleg_description']}\n\n"
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


def _count_spread(
    stats: dict[str, Any], seen: dict[str, set[tuple[str, str]]], norm_id: str, target_id: str, accepted: bool
) -> None:
    """One assertion into the four per-requirement counts (R13). A norm and
    requirement pair counts once among the pairs, however many quote pairs
    support it (a requirement proposed twice for one norm, rule 5). The command
    recounts the spread from the merged assertions (`spread_of`), so a batch
    kept without these counts still counts."""
    stats["assertions_by_requirement"][target_id] += 1
    if accepted:
        stats["accepted_by_requirement"][target_id] += 1
    for key, pairs, counted in (("pairs_by_requirement", seen["pairs"], True),
                                ("accepted_pairs_by_requirement", seen["accepted_pairs"], accepted)):
        if counted and (norm_id, target_id) not in pairs:
            pairs.add((norm_id, target_id))
            stats[key][target_id] += 1


def spread_of(assertions: list[dict[str, Any]], requirement_ids: list[str]) -> dict[str, dict[str, int]]:
    """The four per-requirement counts (R13), recounted from assertions: the
    command's merge calls it so a batch kept before B163 (no counts) still counts."""
    counts = {key: {rid: 0 for rid in requirement_ids} for key in SPREAD_KEYS}
    pairs: set[tuple[Any, str]] = set()
    accepted_pairs: set[tuple[Any, str]] = set()
    for assertion in assertions:
        target_id = assertion.get("target_id")
        if target_id not in counts["assertions_by_requirement"]:
            continue
        pair = (assertion.get("source_norm_id"), target_id)
        accepted = assertion.get("judge_verdict") == "accepted"
        counts["assertions_by_requirement"][target_id] += 1
        if accepted:
            counts["accepted_by_requirement"][target_id] += 1
        for key, seen, counted in (("pairs_by_requirement", pairs, True),
                                   ("accepted_pairs_by_requirement", accepted_pairs, accepted)):
            if counted and pair not in seen:
                seen.add(pair)
                counts[key][target_id] += 1
    return counts


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
        "judge_effort": "not applicable (mechanical gate)",
        # B84 ruling R12 stands under spec F D-F29: no model, no temperature
        "judge_temperature": "not applicable (mechanical gate)",
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


def alignment_candidate_of(assertion: dict[str, Any]) -> dict[str, Any]:
    """The candidate a stored assertion stands for, rebuilt as the five keys of
    the align_hleg v2 output shape in its order, the relation type as the
    generator claimed it (B173 R4). An assertion kept before DEC-28 has no
    claimed type, so its message cannot be rebuilt and the call is refused."""
    if not assertion.get("proposed_relation_type"):
        raise ValueError(
            f"assertion {assertion.get('id')} has no proposed_relation_type (kept before DEC-28); "
            "its candidate cannot be rebuilt"
        )
    return {
        "target_id": assertion.get("target_id"),
        "relation_type": assertion["proposed_relation_type"],
        "source_quote": assertion.get("source_quote"),
        "target_quote": assertion.get("target_quote"),
        "rationale": assertion.get("generator_rationale"),
    }


def quote_check(
    norm: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    *,
    prompt_version: str,
    log_path: Path,
    build_id: str,
    judge_run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The mechanical quote check of one candidate: None when both quotes are
    found; otherwise the logged JudgeRun-shaped rejection and the reject
    record, with no judge call."""
    source_quote_ok = _quote_found(candidate.get("source_quote"), norm["source_text"])
    target_quote_ok = _quote_found(candidate.get("target_quote"), target["description"])
    if source_quote_ok and target_quote_ok:
        return None
    norm_id = norm.get("norm_id", "norm:unknown")
    started_at = _now()
    mechanical = _mechanical_judge_run(judge_run_id, prompt_version, build_id, started_at)
    reject = {
        "norm_id": norm_id,
        "target_id": candidate.get("target_id"),
        "source_quote_found": source_quote_ok,
        "target_quote_found": target_quote_ok,
    }
    _log_event(
        log_path,
        {
            "timestamp": _now(),
            "direction": "mechanical",
            "norm_id": norm_id,
            "target_id": candidate.get("target_id"),
            "model": MECHANICAL_JUDGE_MODEL,
            "effort": "not applicable (mechanical gate)",
            "prompt_version": prompt_version,
            "input_sha256": _input_hash(json.dumps(candidate, ensure_ascii=False, sort_keys=True)),
            "verdict": "rejected",
            "rationale": "quote not found in source",
        },
    )
    return mechanical, reject


def judge_alignment(
    norm: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    judge: ModelClient,
    judge_prompt: str,
    judge_prompt_sha256: str,
    *,
    prompt_version: str,
    log_path: Path,
    build_id: str,
    judge_run_id: str,
) -> dict[str, Any]:
    """One alignment judge call on one candidate, with one retry on unparseable
    JSON, the human-review fallback on an unusable reply and the v2 guard on a
    no_clear_relation correction; logs the call. Returns the judge run."""
    norm_id = norm.get("norm_id", "norm:unknown")
    judge_user = _judge_user_message(norm, target, candidate)
    judge_started = _now()
    judged, judge_error = _call_json_with_retry(judge, judge_prompt, judge_user)
    if judged is None or judged.get("verdict") not in (
        "accepted",
        "rejected",
        "needs_human_review",
    ):
        judged = _fallback_judge_result(judge_error or "missing or invalid verdict")
    elif (
        prompt_version not in _PROMPTS_TAKING_ANY_CORRECTION
        and judged.get("corrected_relation_type") == "no_clear_relation"
        and judged["verdict"] != "rejected"
    ):
        # CHANGE3 (R3): only a rejection may carry no_clear_relation;
        # the judge's own verdict and rationale go into the reason (G13)
        judged = _fallback_judge_result(
            f"verdict {judged['verdict']!r} with corrected_relation_type no_clear_relation, "
            "which only a rejection may carry (judge_alignment checks 3 and 4); the judge's "
            f"rationale: {judged.get('rationale') or 'no rationale returned'}"
        )
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
            "target_id": candidate.get("target_id"),
            "model": judge.model,
            "effort": getattr(judge, "effort", "not configured"),
            "prompt_version": prompt_version,
            "prompt_sha256": judge_prompt_sha256,
            "input_sha256": _input_hash(judge_user),
            "verdict": verdict,
            "corrected_relation_type": corrected,
            "rationale": rationale,
        },
    )

    return {
        "id": judge_run_id,
        "type": "JudgeRun",
        "layer": 3,
        "judge_kind": "mapping",
        "judge_model": judge.model,
        "judge_effort": getattr(judge, "effort", "not configured"),
        "judge_temperature": getattr(judge, "temperature", "not configured"),
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


def assertion_of(
    norm: dict[str, Any],
    target: dict[str, Any],
    candidate: dict[str, Any],
    judge_run: dict[str, Any],
    *,
    index: int,
    mapping_run_id: str,
    target_span_id: str,
) -> dict[str, Any]:
    """The AlignmentAssertion of one judged candidate: the judge's correction
    overrides the claimed relation type, which the assertion keeps (DEC-28)."""
    norm_id = norm.get("norm_id", "norm:unknown")
    target_id = target["id"]
    norm_suffix = _id_suffix(norm_id)
    target_suffix = _id_suffix(target_id)
    proposed_relation = candidate.get("relation_type")
    scores = judge_run["scores"]
    return {
        "id": f"align:{norm_suffix}:{target_suffix}:{index}",
        "type": "AlignmentAssertion",
        "layer": 3,
        "source_norm_id": norm_id,
        "target_id": target_id,
        "relation_type": judge_run["corrected_relation_type"] or proposed_relation,
        "source_evidence_span_ids": [norm["source_span_id"]],
        "target_evidence_span_ids": [target_span_id],
        "source_quote": candidate.get("source_quote"),
        "target_quote": candidate.get("target_quote"),
        "scores": scores,
        "final_score": sum(scores.values()) / len(scores),
        "mapping_run_id": mapping_run_id,
        "judge_run_id": judge_run["id"],
        "judge_verdict": judge_run["verdict"],
        "rationale": judge_run["rationale"],
        # CHANGE10 (R11, R25): the candidate as the generator claimed it
        "proposed_relation_type": proposed_relation,
        "generator_rationale": (
            candidate.get("rationale") if isinstance(candidate.get("rationale"), str) else None
        ),
        "review_status": "accepted" if judge_run["verdict"] == "accepted" else "needs_review",
    }


def align_norms(
    norms: list[dict[str, Any]],
    hleg_nodes: list[dict[str, Any]],
    generator: ModelClient,
    judge: ModelClient,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    log_path: Path | None = None,
    build_id: str = "adhoc",
    max_in_flight: int = 1,
) -> dict[str, Any]:
    """Run the judged alignment of accepted norms against the HLEG nodes.

    Each norm dict must carry, besides its norms.schema.json fields, a
    "source_text" field with the verbatim text of its source unit (the CLI
    resolves it from the layer1 dump via source_node_id). Returns
    {"assertions": [...], "mapping_runs": [...], "judge_runs": [...],
    "stats": {...}}. Assertions conform to the AlignmentAssertion shape in
    alignments.schema.json; invalid ones are recorded in stats and dropped.
    max_in_flight bounds the norms whose calls run at once (B164); 1, the
    default, runs them one after the other in the calling thread.
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
        # B121 (spec F D-F22, D-F29): the effort and the declared temperature
        # beside the model id, as the judge run records its own
        "generator_effort": getattr(generator, "effort", "not configured"),
        "generator_temperature": getattr(generator, "temperature", "not configured"),
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
        **{key: {node["id"]: 0 for node in hleg_nodes} for key in SPREAD_KEYS},
    }
    seen: dict[str, set[tuple[str, str]]] = {"pairs": set(), "accepted_pairs": set()}

    def norm_events(norm: dict[str, Any]) -> list[tuple[Any, ...]]:
        """B164: one norm's model calls and what they gave, in the candidates'
        order. Runs on a worker thread when max_in_flight > 1; reads the run's
        prompts and the HLEG nodes, and writes only the log (append_event takes
        a lock)."""
        events: list[tuple[Any, ...]] = []
        norm_id = norm.get("norm_id", "norm:unknown")
        if norm.get("judge_verdict") != "accepted":
            # Only judge-accepted norms are aligned (Section 7 gating).
            return [("skipped",)]
        source_text = norm.get("source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            return [("failed", {"norm_id": norm_id, "reason": "missing source_text"})]
        if not norm.get("source_span_id"):
            return [("failed", {"norm_id": norm_id, "reason": "missing source_span_id"})]

        gen_user = _generator_user_message(norm, hleg_nodes, prompt_version=prompt_version)
        parsed, error = _call_json_with_retry(generator, align_prompt, gen_user)
        _log_event(
            log_path,
            {
                "timestamp": _now(),
                "direction": "generator",
                "norm_id": norm_id,
                "model": generator.model,
                "effort": getattr(generator, "effort", "not configured"),
                "prompt_version": prompt_version,
                "prompt_sha256": align_prompt_sha256,
                "input_sha256": _input_hash(gen_user),
                "parse_ok": parsed is not None,
                "error": error,
            },
        )
        if parsed is None:
            return [("failed", {"norm_id": norm_id, "reason": error})]

        candidates = parsed.get("alignments")
        if not isinstance(candidates, list):
            return [("failed", {"norm_id": norm_id, "reason": "generator JSON lacks an 'alignments' list"})]
        if not candidates:
            # Zero alignments is a valid answer: no_clear_relation is the
            # default and a mapping is never forced (Section 4).
            return [("zero",)]
        if len(candidates) > MAX_CANDIDATES_PER_NORM:
            events.append(
                (
                    "invalid",
                    {
                        "norm_id": norm_id,
                        "reason": f"generator proposed {len(candidates)} candidates; "
                        f"kept the first {MAX_CANDIDATES_PER_NORM}",
                    },
                )
            )
            candidates = candidates[:MAX_CANDIDATES_PER_NORM]

        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                events.append(("invalid", {"norm_id": norm_id, "reason": "candidate is not a JSON object"}))
                continue
            target_id = candidate.get("target_id")
            target = hleg_by_id.get(target_id)
            if target is None:
                # The seven-requirement set is closed; an unknown target id
                # is an invented requirement and never enters the graph.
                events.append(("invalid", {"norm_id": norm_id, "reason": f"unknown target_id: {target_id!r}"}))
                continue
            proposed_relation = candidate.get("relation_type")
            if proposed_relation not in PROPOSABLE_RELATION_TYPES:
                events.append(
                    (
                        "invalid",
                        {"norm_id": norm_id, "target_id": target_id, "reason": f"invalid relation_type: {proposed_relation!r}"},
                    )
                )
                continue
            target_span_id = (target.get("source_span") or {}).get("span_id")
            if not target_span_id:
                events.append(
                    (
                        "invalid",
                        {"norm_id": norm_id, "target_id": target_id, "reason": "target HLEG node has no source span"},
                    )
                )
                continue

            norm_suffix = _id_suffix(norm_id)
            target_suffix = _id_suffix(target_id)
            judge_run_id = f"judgerun:mapping:{norm_suffix}:{target_suffix}:c{index}"

            checked = quote_check(
                norm, target, candidate,
                prompt_version=prompt_version, log_path=log_path, build_id=build_id, judge_run_id=judge_run_id,
            )
            if checked is not None:
                # Mechanical rejection: no judge call, no assertion. The
                # JudgeRun-shaped record keeps the audit trail.
                events.append(("mechanical", *checked))
                continue

            judge_run = judge_alignment(
                norm, target, candidate, judge, judge_prompt, judge_prompt_sha256,
                prompt_version=prompt_version, log_path=log_path, build_id=build_id, judge_run_id=judge_run_id,
            )
            assertion = assertion_of(
                norm, target, candidate, judge_run,
                index=index, mapping_run_id=mapping_run["id"], target_span_id=target_span_id,
            )
            events.append(("judged", assertion, judge_run))
        return events

    for events in run_in_flight(norms, norm_events, max_in_flight=max_in_flight):
        for event in events:
            kind = event[0]
            if kind == "skipped":
                stats["norms_skipped_not_accepted"] += 1
            elif kind == "failed":
                stats["norms_failed"].append(event[1])
            elif kind == "zero":
                stats["zero_alignment_norms"] += 1
            elif kind == "invalid":
                stats["invalid_candidates"].append(event[1])
            elif kind == "mechanical":
                # Mechanical rejection: no judge call, no assertion. The
                # JudgeRun-shaped record keeps the audit trail.
                stats["candidates"] += 1
                judge_runs.append(event[1])
                stats["mechanical_rejects"].append(event[2])
            else:
                _judged, assertion, judge_run = event
                stats["candidates"] += 1
                errors = sorted(validator.iter_errors(assertion), key=lambda e: list(e.path))
                if errors:
                    stats["invalid_assertions"].append(
                        {
                            "norm_id": assertion["source_norm_id"],
                            "target_id": assertion["target_id"],
                            "assertion_id": assertion["id"],
                            "errors": [err.message for err in errors[:5]],
                        }
                    )
                    # The judge decision stays logged and kept (Section 7), but
                    # the invalid assertion never enters the output.
                    judge_runs.append(judge_run)
                    continue
                verdict = assertion["judge_verdict"]
                stats["verdicts"][verdict] += 1
                _count_spread(stats, seen, assertion["source_norm_id"], assertion["target_id"], verdict == "accepted")
                judge_runs.append(judge_run)
                assertions.append(assertion)

    mapping_run["completed_at"] = _now()
    return {
        "assertions": assertions,
        "mapping_runs": [mapping_run],
        "judge_runs": judge_runs,
        "stats": stats,
    }

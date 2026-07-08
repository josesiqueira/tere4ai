"""M2 norm-extraction pipeline: generator plus build-time extraction judge.

@implements: DEC-03, DEC-06 (partial: extraction judge only)
@grounded_by: REF-11, REF-12, REF-13, REF-16, REF-24

An Article is not one requirement: each extracted norm is a NormativeStatement
(architecture.md Section 3, Institutional Grammar). The generator (OpenAI
family) proposes candidate norms from ONE source unit at a time; the
independent extraction judge (Claude family) gates each candidate per
Section 7 before it may be accepted. Hard invariants enforced here:

- Recitals are NEVER extraction sources (Section 1); a recital id raises.
- No norm leaves this module without a source_span_id and a judge verdict;
  review_status is "accepted" only when the judge accepted.
- Every generator and judge call is logged to
  data/review_queue/extraction_log.jsonl (model id, prompt version, input
  hash, verdict and rationale for judge calls). Never API keys, never full
  prompts.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.extract_norms.model_clients import ModelClient

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
NORMS_SCHEMA_PATH = REPO_ROOT / "schema" / "json_schemas" / "norms.schema.json"
DEFAULT_LOG_PATH = REPO_ROOT / "data" / "review_queue" / "extraction_log.jsonl"
DEFAULT_DUMP_PATH = REPO_ROOT / "data" / "graph_dumps" / "layer1.json"

EXTRACTION_METHOD = "llm_extract_v1"

# Node types that carry extractable operative text (Layer 1, Section 6).
SOURCE_UNIT_TYPES = ("Paragraph", "Point", "AnnexItem")
# Container types that expand to their source units.
CONTAINER_TYPES = ("Article", "Annex", "Section", "Chapter", "Regulation")

_NORM_CANDIDATE_FIELDS = (
    "deontic_type",
    "modal",
    "actor_explicit",
    "actor_inferred",
    "actor_inference_source_node_id",
    "action",
    "object",
    "target_system_category",
    "conditions",
    "exceptions",
    "lifecycle_phase_ids",
)


def load_prompt(kind: str, version: str) -> str:
    """Load a versioned system prompt, e.g. prompts/extract_norms/v1.md."""
    path = PROMPTS_DIR / kind / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _norm_validator() -> Draft202012Validator:
    schema = json.loads(NORMS_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _log_event(log_path: Path, event: dict[str, Any]) -> None:
    """Append one JSON line to the extraction log. Never key material."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a model response into a JSON object, tolerating code fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _index_nodes(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in dump["nodes"]}


def _article_context_title(node_id: str, nodes: dict[str, dict[str, Any]]) -> str:
    """Title of the closest Article or Annex ancestor, for generator context."""
    parts = node_id.split(":")
    for depth in range(len(parts), 0, -1):
        ancestor = nodes.get(":".join(parts[:depth]))
        if ancestor is not None and ancestor.get("type") in ("Article", "Annex"):
            label = ancestor["type"]
            number = ancestor.get("number", "")
            title = ancestor.get("title", "")
            return f"{label} {number}: {title}".strip()
    return ""


def expand_source_units(dump: dict[str, Any], node_ids: list[str]) -> list[dict[str, Any]]:
    """Expand the given ids into extraction source units, in dump order.

    A source unit is a Paragraph, Point, or AnnexItem with verbatim text and
    a source span. Container ids (Article, Annex, ...) expand to their
    descendant source units. Recitals are never extraction sources (Section 1)
    and raise ValueError immediately.
    """
    nodes = _index_nodes(dump)
    wanted: dict[str, bool] = {}
    for node_id in node_ids:
        if ":recital-" in node_id:
            raise ValueError(f"recitals are never extraction sources: {node_id}")
        node = nodes.get(node_id)
        if node is None:
            raise ValueError(f"unknown node id: {node_id}")
        if node.get("type") == "Recital":
            raise ValueError(f"recitals are never extraction sources: {node_id}")
        if node.get("type") in SOURCE_UNIT_TYPES:
            wanted[node_id] = True
        elif node.get("type") in CONTAINER_TYPES:
            wanted[node_id] = False  # marker: expand by prefix
        else:
            raise ValueError(
                f"node {node_id} has type {node.get('type')}, which is neither "
                f"a source unit ({', '.join(SOURCE_UNIT_TYPES)}) nor an expandable container"
            )

    prefixes = [node_id for node_id, direct in wanted.items() if not direct]
    direct_ids = {node_id for node_id, direct in wanted.items() if direct}

    units: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node in dump["nodes"]:
        node_id = node["id"]
        if node.get("type") not in SOURCE_UNIT_TYPES:
            continue
        in_scope = node_id in direct_ids or any(
            node_id.startswith(prefix + ":") for prefix in prefixes
        )
        if not in_scope or node_id in seen:
            continue
        seen.add(node_id)
        units.append(
            {
                "node_id": node_id,
                "node_type": node["type"],
                "text": node.get("text", ""),
                "span_id": (node.get("source_span") or {}).get("span_id"),
                "article_context": _article_context_title(node_id, nodes),
            }
        )
    return units


def _generator_user_message(unit: dict[str, Any]) -> str:
    return (
        f"Source unit node id: {unit['node_id']}\n"
        f"Context (orientation only): {unit['article_context']}\n"
        f"Verbatim source text:\n{unit['text']}"
    )


def _judge_user_message(unit: dict[str, Any], candidate: dict[str, Any]) -> str:
    return (
        f"Source unit node id: {unit['node_id']}\n"
        f"Verbatim source text:\n{unit['text']}\n\n"
        f"Candidate norm (JSON):\n{json.dumps(candidate, ensure_ascii=False, indent=1)}"
    )


def _call_json_with_retry(
    client: ModelClient,
    system: str,
    user: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Call a client expecting JSON; retry once on parse failure.

    Returns (parsed, error). error is None on success; parsed is None on
    final failure.
    """
    last_error = ""
    for _attempt in range(2):
        raw = client.complete(system, user)
        try:
            return _parse_json_object(raw), None
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = f"unparseable model JSON: {exc}"
    return None, last_error


def _judge_scores(parsed: dict[str, Any]) -> dict[str, float]:
    scores = parsed.get("scores") or {}
    keys = (
        "semantic_similarity",
        "normative_relevance",
        "operational_utility",
        "evidence_strength",
        "judge_confidence",
    )
    clean: dict[str, float] = {}
    for key in keys:
        value = scores.get(key, 0.0)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        clean[key] = min(1.0, max(0.0, value))
    return clean


def _fallback_judge_result(reason: str) -> dict[str, Any]:
    """Judge output when the judge response was unusable: never accepted."""
    return {
        "verdict": "needs_human_review",
        "scores": {
            "semantic_similarity": 0.0,
            "normative_relevance": 0.0,
            "operational_utility": 0.0,
            "evidence_strength": 0.0,
            "judge_confidence": 0.0,
        },
        "rationale": f"judge response unusable, defaulting to human review: {reason}",
    }


def extract_norms(
    dump: dict[str, Any],
    node_ids: list[str],
    generator: ModelClient,
    judge: ModelClient,
    prompt_version: str = "v1",
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Run the judged extraction over the given node ids.

    Returns {"norms": [...], "judge_runs": [...], "stats": {...}}. Norms
    conform to schema/json_schemas/norms.schema.json; judge_runs conform to
    the JudgeRun shape in alignments.schema.json with judge_kind
    "extraction". Failures are recorded in stats, never raised mid-batch
    (except the recital guard and unknown ids, which fail fast).
    """
    log_path = log_path or DEFAULT_LOG_PATH
    extract_prompt = load_prompt("extract_norms", prompt_version)
    judge_prompt = load_prompt("judge_norms", prompt_version)
    validator = _norm_validator()
    build_id = dump.get("build", {}).get("build_id", "build-unknown")

    units = expand_source_units(dump, node_ids)

    norms: list[dict[str, Any]] = []
    judge_runs: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "source_units": len(units),
        "nodes_failed": [],
        "candidates": 0,
        "invalid_norms": [],
        "verdicts": {"accepted": 0, "rejected": 0, "needs_human_review": 0},
    }

    for unit in units:
        node_id = unit["node_id"]
        if not unit["span_id"]:
            # A norm without a source span must never exist (Section 13).
            stats["nodes_failed"].append({"node_id": node_id, "reason": "missing source_span"})
            continue
        if not unit["text"].strip():
            stats["nodes_failed"].append({"node_id": node_id, "reason": "empty text"})
            continue

        gen_user = _generator_user_message(unit)
        parsed, error = _call_json_with_retry(generator, extract_prompt, gen_user)
        _log_event(
            log_path,
            {
                "timestamp": _now(),
                "direction": "generator",
                "node_id": node_id,
                "model": generator.model,
                "prompt_version": prompt_version,
                "input_sha256": _input_hash(gen_user),
                "parse_ok": parsed is not None,
                "error": error,
            },
        )
        if parsed is None:
            stats["nodes_failed"].append({"node_id": node_id, "reason": error})
            continue

        candidates = parsed.get("norms", [])
        if not isinstance(candidates, list):
            stats["nodes_failed"].append(
                {"node_id": node_id, "reason": "generator JSON lacks a 'norms' list"}
            )
            continue

        for index, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                stats["invalid_norms"].append(
                    {"node_id": node_id, "reason": "candidate is not a JSON object"}
                )
                continue
            stats["candidates"] += 1
            candidate = {
                key: candidate.get(key) for key in _NORM_CANDIDATE_FIELDS if key in candidate
            }

            judge_user = _judge_user_message(unit, candidate)
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

            _log_event(
                log_path,
                {
                    "timestamp": _now(),
                    "direction": "judge",
                    "node_id": node_id,
                    "model": judge.model,
                    "prompt_version": prompt_version,
                    "input_sha256": _input_hash(judge_user),
                    "verdict": verdict,
                    "rationale": rationale,
                },
            )

            norm_id = f"norm:{node_id}:n{index}"
            judge_run_id = f"judgerun:extraction:{node_id}:n{index}"
            judge_run = {
                "id": judge_run_id,
                "type": "JudgeRun",
                "layer": 3,
                "judge_kind": "extraction",
                "judge_model": judge.model,
                "prompt_version": prompt_version,
                "verdict": verdict,
                "scores": scores,
                "rationale": rationale,
                "started_at": judge_started,
                "completed_at": _now(),
                "build_id": build_id,
            }

            norm = {
                "norm_id": norm_id,
                "layer": 2,
                "type": "NormativeStatement",
                "source_node_id": node_id,
                "source_span_id": unit["span_id"],
                "deontic_type": candidate.get("deontic_type"),
                "modal": candidate.get("modal"),
                "actor_explicit": candidate.get("actor_explicit"),
                "actor_inferred": candidate.get("actor_inferred"),
                "actor_inference_source_node_id": candidate.get(
                    "actor_inference_source_node_id"
                ),
                "action": candidate.get("action"),
                "object": candidate.get("object"),
                "target_system_category": candidate.get("target_system_category"),
                "conditions": candidate.get("conditions") or [],
                "exceptions": candidate.get("exceptions") or [],
                "condition_ids": [],
                "exception_ids": [],
                "lifecycle_phase_ids": candidate.get("lifecycle_phase_ids") or [],
                "extraction_method": EXTRACTION_METHOD,
                "extractor_model": generator.model,
                "extractor_prompt_version": prompt_version,
                "confidence": scores["evidence_strength"],
                "judge_verdict": verdict,
                "judge_run_id": judge_run_id,
                "review_status": "accepted" if verdict == "accepted" else "needs_review",
            }

            errors = sorted(validator.iter_errors(norm), key=lambda e: list(e.path))
            if errors:
                stats["invalid_norms"].append(
                    {
                        "node_id": node_id,
                        "norm_id": norm_id,
                        "errors": [error.message for error in errors[:5]],
                    }
                )
                # The judge decision is still logged and kept (Section 7),
                # but the invalid norm never enters the output.
                judge_runs.append(judge_run)
                continue

            stats["verdicts"][verdict] += 1
            judge_runs.append(judge_run)
            norms.append(norm)

    return {"norms": norms, "judge_runs": judge_runs, "stats": stats}

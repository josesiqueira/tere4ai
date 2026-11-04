"""Ingestion of recorded sessions and loose envelopes for the report.

@implements: DEC-08, DEC-15
@implements: DEC-24
@implements: DEC-30
@grounded_by: ADD-14, ADD-15

Session JSONL contract (verified against the live server): one JSON object
per line with keys seq (int), ts (str), tool (str), request (object),
envelope (object), repo_ref (null or str). A line that fails json.loads or
misses a required key becomes a ProblemCard and ingestion continues; a
non-monotonic or duplicate seq is flagged in the report header, never fatal.

A loose --envelope file is a bare Section 8 envelope. Its tool is taken from
answer.tool when present, otherwise fingerprinted from the answer shape; its
timestamp is the envelope's own generated_at; its request is rendered as
"not recorded". It is appended after the highest recorded seq.

DEC-24 (spec G D-G74 (8), rulings S81, S82): a session line of tool
"judge_on_demand" carries a demo judge's part (its answer names the judged
tool and the generation id); it is attached to the exchange whose signed
record (answer.signed_record) holds the same generation id, in seq order,
and a line with no such exchange stays unattached, to be shown apart.

DEC-30 (B181, ruling R6): a session line or a loose envelope recorded before
the rename names the tool generate_control_backlog and carries the answer
keys items, dropped_items and merged_items. tailored_requirements_of_record
is the one reader of those old words in the report: it maps them to
generate_tailored_requirements, tailored_requirements,
dropped_tailored_requirements and merged_tailored_requirements on a copy,
before the envelope is checked or fingerprinted, never changes its input and
keeps the new key when an answer carries both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.backlog import OLD_TOOL_NAME, TOOL_NAME
from tere4ai.mcp_server.tools import SECTION_8_ENVELOPE_FIELDS, STATUS_VOCABULARY

_REQUIRED_LINE_KEYS = ("seq", "ts", "tool", "request", "envelope")
_EXCERPT_CHARS = 240


@dataclass
class Exchange:
    """One recorded (or synthesized) tool exchange, ready to render."""

    seq: int
    ts: str
    tool: str
    request: dict[str, Any] | None  # None means "not recorded" (loose envelope)
    envelope: dict[str, Any]
    source: str  # file name the record came from
    repo_ref: str | None = None
    origin: str = "session"  # "session" or "loose"
    conformance_flags: list[str] = field(default_factory=list)
    order: int = 0  # global ingest order; tie-break for equal seq
    # DEC-24: the judge_on_demand exchanges that judged this one, seq order.
    judge_parts: list[Exchange] = field(default_factory=list)


@dataclass
class ProblemCard:
    """A record that could not be rendered as an exchange. Never dropped."""

    source: str
    position: str  # human-readable position, e.g. "line 3"
    seq: int | None
    claimed_tool: str | None
    errors: list[str]
    raw_excerpt: str


@dataclass
class IngestResult:
    exchanges: list[Exchange]
    problems: list[ProblemCard]
    source_names: list[str]
    header_flags: list[str]
    # DEC-24: judge parts whose generation is not in the input.
    unattached_judge_parts: list[Exchange] = field(default_factory=list)


JUDGE_ON_DEMAND = "judge_on_demand"

# DEC-30 (R6): the answer keys of a generation recorded before B181, each with
# its new name.
TAILORED_REQUIREMENT_KEYS_OF_RECORD: dict[str, str] = {
    "items": "tailored_requirements",
    "dropped_items": "dropped_tailored_requirements",
    "merged_items": "merged_tailored_requirements",
}


def tool_of_record(tool: str) -> str:
    """DEC-30 (R6): the tool name a record carries, the old name of the
    generation read as generate_tailored_requirements; any other unchanged."""
    return TOOL_NAME if tool == OLD_TOOL_NAME else tool


def tailored_requirements_of_record(answer: Any) -> Any:
    """DEC-30 (R6): a copy of a recorded answer under the new words.

    Each old key moves to its new name in its own place when the new key is
    absent; an old key beside its new one is dropped and the new one kept;
    answer.tool reads generate_tailored_requirements when it is the old
    name; every other key is as it is. The input is never changed, and an
    answer that is not an object is returned as it is.
    """
    if not isinstance(answer, dict):
        return answer
    out: dict[str, Any] = {}
    for key, value in answer.items():
        new_key = TAILORED_REQUIREMENT_KEYS_OF_RECORD.get(key)
        if new_key is None:
            out[key] = tool_of_record(value) if key == "tool" and isinstance(value, str) else value
        elif new_key not in answer:
            out[new_key] = value
    return out


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def differences(before: Any, after: Any, path: str = "answer") -> list[str]:
    """Every path where two JSON trees differ: a key present on one side
    only, a value that differs, a list of another length. The rewrite script
    for kept files (R11) uses it to prove its result equal to its input
    apart from the renamed keys and values."""

    def child(key: Any) -> str:
        return f"{path}.{key}" if path else str(key)

    if isinstance(before, dict) and isinstance(after, dict):
        found: list[str] = []
        for key in before:
            if key not in after:
                found.append(f"{child(key)}: before only")
            else:
                found.extend(differences(before[key], after[key], child(key)))
        found.extend(f"{child(key)}: after only" for key in after if key not in before)
        return found
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [f"{path}: a list of {len(before)} entries before, {len(after)} after"]
        found = []
        for position, (old, new) in enumerate(zip(before, after)):
            found.extend(differences(old, new, f"{path}[{position}]"))
        return found
    if type(before) is not type(after) or before != after:
        return [f"{path} from {_short(before)} to {_short(after)}"]
    return []


def _envelope_of_record(envelope: Any) -> Any:
    """DEC-30 (R6): a copy of an envelope whose answer went through
    tailored_requirements_of_record; anything else as it is."""
    if isinstance(envelope, dict) and isinstance(envelope.get("answer"), dict):
        return {**envelope, "answer": tailored_requirements_of_record(envelope["answer"])}
    return envelope


def generation_id_of(ex: Exchange) -> str | None:
    """DEC-24: the generation id a judge part names, or the one an exchange's
    signed record holds; None for every other exchange."""
    answer = ex.envelope.get("answer")
    if not isinstance(answer, dict):
        return None
    if ex.tool == JUDGE_ON_DEMAND:
        value = answer.get("generation_id")
    else:
        record = answer.get("signed_record")
        value = record.get("generation_id") if isinstance(record, dict) else None
    return value if isinstance(value, str) and value else None


def attach_judge_parts(exchanges: list[Exchange]) -> list[Exchange]:
    """Attach each judge_on_demand exchange to the exchange whose signed
    record holds its generation id; returns the ones with no such exchange."""
    generations: dict[str, Exchange] = {}
    for ex in exchanges:
        gid = generation_id_of(ex)
        if ex.tool != JUDGE_ON_DEMAND and gid is not None:
            generations.setdefault(gid, ex)
    unattached: list[Exchange] = []
    for ex in sorted((e for e in exchanges if e.tool == JUDGE_ON_DEMAND), key=lambda e: (e.seq, e.order)):
        target = generations.get(generation_id_of(ex) or "")
        if target is None:
            unattached.append(ex)
        else:
            target.judge_parts.append(ex)
    return unattached


# Answer-shape fingerprints for loose envelopes, checked in this order.
_FINGERPRINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("risk_category", "unacceptable_risk"), "classify_ai_system"),
    (("requirements_by_article",), "get_applicable_requirements"),
    (("assertions",), "trace_alignment"),
    (("deontic",), "explain_requirement"),
    (("matrix", "tag_convention"), "trace_implementation"),
    (("tailored_requirements", "judge_rationale"), TOOL_NAME),
    (("assessment", "quotes"), "evaluate_project_evidence"),
    (("span_id", "text"), "resolve_span"),
)


def fingerprint_tool(envelope: dict[str, Any]) -> str | None:
    """Tool name for a loose envelope: answer.tool, else the answer shape."""
    answer = envelope.get("answer")
    if not isinstance(answer, dict):
        return None
    tool = answer.get("tool")
    if isinstance(tool, str) and tool:
        return tool
    for keys, name in _FINGERPRINTS:
        if all(k in answer for k in keys):
            return name
    return None


def check_envelope(envelope: Any) -> tuple[bool, list[str], list[str]]:
    """Validate an envelope against the Section 8 contract.

    Returns (renderable, fatal_errors, conformance_flags). An envelope stays
    renderable when answer and status survive; missing keys then become a
    non-conformance flag rendered on the card, and nothing is dropped.
    """
    if not isinstance(envelope, dict):
        return False, [f"envelope must be an object; got {type(envelope).__name__}"], []
    missing = sorted(SECTION_8_ENVELOPE_FIELDS - envelope.keys())
    extra = sorted(envelope.keys() - SECTION_8_ENVELOPE_FIELDS)
    if "answer" in missing or "status" in missing:
        return False, [
            "non-conformant envelope: missing " + ", ".join(missing)
        ], []
    flags: list[str] = []
    if missing:
        flags.append("non-conformant envelope: missing " + ", ".join(missing))
    if extra:
        flags.append("non-conformant envelope: unexpected keys " + ", ".join(extra))
    status = envelope.get("status")
    if status not in STATUS_VOCABULARY:
        flags.append(
            f"non-conformant envelope: status {status!r} is not in the "
            "calibrated 7-value vocabulary"
        )
    if envelope.get("answer") is None and status != "requires_human_review":
        flags.append(
            "non-conformant envelope: answer is null but status is not "
            "requires_human_review"
        )
    return True, [], flags


def _excerpt(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > _EXCERPT_CHARS:
        return raw[:_EXCERPT_CHARS] + " [truncated]"
    return raw


def _ingest_session_line(
    obj: Any, name: str, lineno: int, raw: str, order: int
) -> Exchange | ProblemCard:
    if not isinstance(obj, dict):
        return ProblemCard(
            source=name,
            position=f"line {lineno}",
            seq=None,
            claimed_tool=None,
            errors=[f"line is not a JSON object (got {type(obj).__name__})"],
            raw_excerpt=_excerpt(raw),
        )
    errors: list[str] = []
    for key in _REQUIRED_LINE_KEYS:
        if key not in obj:
            errors.append(f"missing key '{key}'")
    seq = obj.get("seq")
    if "seq" not in errors and "seq" in obj and (
        not isinstance(seq, int) or isinstance(seq, bool)
    ):
        errors.append(f"seq must be an integer; got {type(seq).__name__}")
        seq = None
    if "ts" in obj and not isinstance(obj["ts"], str):
        errors.append("ts must be a string")
    if "tool" in obj and not isinstance(obj["tool"], str):
        errors.append("tool must be a string")
    if "request" in obj and not isinstance(obj["request"], dict):
        errors.append("request must be an object")
    if "envelope" in obj and not isinstance(obj["envelope"], dict):
        errors.append("envelope must be an object")
    claimed_tool = obj.get("tool") if isinstance(obj.get("tool"), str) else None
    if errors:
        return ProblemCard(
            source=name,
            position=f"line {lineno}",
            seq=seq if isinstance(seq, int) and not isinstance(seq, bool) else None,
            claimed_tool=claimed_tool,
            errors=errors,
            raw_excerpt=_excerpt(raw),
        )
    renderable, fatal, flags = check_envelope(obj["envelope"])
    if not renderable:
        return ProblemCard(
            source=name,
            position=f"line {lineno}",
            seq=obj["seq"],
            claimed_tool=claimed_tool,
            errors=fatal,
            raw_excerpt=_excerpt(raw),
        )
    repo_ref = obj.get("repo_ref")
    # DEC-30 (R6): a generation or a judge part recorded under the old words
    # is read through the one reader; the recorded line is not changed.
    tool = tool_of_record(obj["tool"])
    envelope = obj["envelope"]
    if obj["tool"] in (OLD_TOOL_NAME, TOOL_NAME, JUDGE_ON_DEMAND):
        envelope = _envelope_of_record(envelope)
    return Exchange(
        seq=obj["seq"],
        ts=obj["ts"],
        tool=tool,
        request=obj["request"],
        envelope=envelope,
        source=name,
        repo_ref=repo_ref if isinstance(repo_ref, str) else None,
        origin="session",
        conformance_flags=flags,
        order=order,
    )


def ingest_inputs(
    session_paths: list[str | Path],
    envelope_paths: list[str | Path] | tuple[str | Path, ...] = (),
) -> IngestResult:
    """Read session JSONL files and loose envelopes into an IngestResult.

    Sort order: by seq, ties by file order. Loose envelopes are appended
    after the highest recorded seq, in argument order.
    """
    exchanges: list[Exchange] = []
    problems: list[ProblemCard] = []
    header_flags: list[str] = []
    source_names: list[str] = []
    order = 0

    for path in session_paths:
        p = Path(path)
        name = p.name
        source_names.append(name)
        text = p.read_text(encoding="utf-8")
        prev_seq: int | None = None
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                obj: Any = json.loads(raw)
            except json.JSONDecodeError as exc:
                problems.append(
                    ProblemCard(
                        source=name,
                        position=f"line {lineno}",
                        seq=None,
                        claimed_tool=None,
                        errors=[f"invalid JSON: {exc}"],
                        raw_excerpt=_excerpt(raw),
                    )
                )
                continue
            record = _ingest_session_line(obj, name, lineno, raw, order)
            if isinstance(record, ProblemCard):
                problems.append(record)
                continue
            if prev_seq is not None and record.seq <= prev_seq:
                header_flags.append(
                    f"{name}: seq {record.seq} at line {lineno} does not "
                    f"increase after seq {prev_seq}"
                )
            prev_seq = record.seq if prev_seq is None else max(prev_seq, record.seq)
            exchanges.append(record)
            order += 1

    max_seq = max((e.seq for e in exchanges), default=0)
    for path in envelope_paths:
        p = Path(path)
        name = p.name
        source_names.append(name)
        raw_text = p.read_text(encoding="utf-8")
        try:
            envelope: Any = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            problems.append(
                ProblemCard(
                    source=name,
                    position="loose envelope file",
                    seq=None,
                    claimed_tool=None,
                    errors=[f"invalid JSON: {exc}"],
                    raw_excerpt=_excerpt(raw_text),
                )
            )
            continue
        # DEC-30 (R6): the old answer keys are mapped before the envelope is
        # checked and fingerprinted.
        envelope = _envelope_of_record(envelope)
        renderable, fatal, flags = check_envelope(envelope)
        if not renderable:
            problems.append(
                ProblemCard(
                    source=name,
                    position="loose envelope file",
                    seq=None,
                    claimed_tool=None,
                    errors=fatal,
                    raw_excerpt=_excerpt(raw_text),
                )
            )
            continue
        tool = fingerprint_tool(envelope)
        if tool is None:
            problems.append(
                ProblemCard(
                    source=name,
                    position="loose envelope file",
                    seq=None,
                    claimed_tool=None,
                    errors=[
                        "cannot fingerprint a tool from the answer shape; "
                        "the envelope is recorded as a problem, not dropped"
                    ],
                    raw_excerpt=_excerpt(raw_text),
                )
            )
            continue
        max_seq += 1
        generated_at = envelope.get("generated_at")
        exchanges.append(
            Exchange(
                seq=max_seq,
                ts=str(generated_at) if generated_at is not None else "",
                tool=tool,
                request=None,
                envelope=envelope,
                source=name,
                repo_ref=None,
                origin="loose",
                conformance_flags=flags,
                order=order,
            )
        )
        order += 1

    seen: dict[int, list[str]] = {}
    for e in exchanges:
        seen.setdefault(e.seq, []).append(e.source)
    for seq_value in sorted(seen):
        sources = seen[seq_value]
        if len(sources) > 1:
            header_flags.append(
                f"duplicate seq {seq_value} across records ({', '.join(sources)})"
            )

    exchanges.sort(key=lambda e: (e.seq, e.order))
    return IngestResult(
        exchanges=exchanges,
        problems=problems,
        source_names=source_names,
        header_flags=header_flags,
        unattached_judge_parts=attach_judge_parts(exchanges),
    )

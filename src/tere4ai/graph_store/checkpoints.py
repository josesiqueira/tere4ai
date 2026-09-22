"""Checkpoint files: one JSON line per completed work key, each carrying the run id.

@implements: DEC-16
@grounded_by: REF-27, ADD-20

D-G20: progress is counted from validated unique keys of the attempt's own
lineage; a resume is a new run that names the run it inherits from and
refuses a checkpoint written under other inputs or another configuration;
lines without a run id predate the record and are inherited only on an
explicit flag. A damaged tail (a crash mid-write) is truncated before
anything is appended; damage anywhere else is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tere4ai.graph_store.build_record import BuildRecordStore


class CheckpointError(RuntimeError):
    pass


class StaleCheckpointError(CheckpointError):
    pass


class IncompatibleCheckpointError(CheckpointError):
    pass


@dataclass
class CheckpointRead:
    entries: list[dict[str, Any]] = field(default_factory=list)
    legacy_keys: list[str] = field(default_factory=list)
    skipped_tail: int = 0
    corrupt_middle: bool = False


@dataclass
class ResumePlan:
    entries_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    inherited_keys: list[str] = field(default_factory=list)
    inherited_from: str | None = None
    resumes_run_id: str | None = None
    repaired_tail_bytes: int = 0


def _valid(line: str, key_field: str, result_keys: tuple[str, ...]) -> dict[str, Any] | None:
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(entry, dict) or key_field not in entry:
        return None
    result = entry.get("result")
    if not isinstance(result, dict) or any(k not in result for k in result_keys):
        return None
    return entry


def read_checkpoint(path: Path, key_field: str, result_keys: tuple[str, ...]) -> CheckpointRead:
    out = CheckpointRead()
    if not path.is_file():
        return out
    raw = path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for index, line in enumerate(lines):
        entry = _valid(line, key_field, result_keys)
        last = index == len(lines) - 1
        if entry is None:
            if last:
                out.skipped_tail += 1
            else:
                out.corrupt_middle = True
            continue
        out.entries.append(entry)
        if "run_id" not in entry:
            out.legacy_keys.append(entry[key_field])
    return out


def repair_tail(path: Path, key_field: str, result_keys: tuple[str, ...]) -> int:
    """Truncate a damaged last line (unparsable or shape-invalid). Refuses damage
    that is not at the tail."""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    trailing_newline = text.endswith("\n")
    if trailing_newline:
        lines.pop()
    keep = 0
    for index, line in enumerate(lines):
        if _valid(line, key_field, result_keys) is not None:
            keep = index + 1
        elif index != len(lines) - 1:
            raise CheckpointError(f"{path.name}: damage at line {index + 1} is not confined to the tail")
    good = "".join(line + "\n" for line in lines[:keep]).encode("utf-8")
    removed = len(raw) - len(good)
    if removed:
        path.write_bytes(good)
    return removed


def unique_results(entries: list[dict[str, Any]], key_field: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        out[entry[key_field]] = entry
    return out


def _digests(inputs: list[dict[str, Any]]) -> dict[str, str]:
    return {i["role"]: i["sha256"] for i in inputs}


def prepare_resume(path: Path, key_field: str, result_keys: tuple[str, ...], *, resume: bool, accept_legacy: bool,
                   store: BuildRecordStore, record_id: str | None, expected_config: dict[str, Any],
                   expected_inputs: list[dict[str, Any]], expected_models: dict[str, Any] | None = None,
                   expected_prompt_sha256: dict[str, Any] | None = None) -> ResumePlan:
    """Plan a resume from the checkpoint, refusing lines written under another
    configuration, other input digests, other models or other prompt texts
    (sampling is recorded per execution, not compared)."""
    plan = ResumePlan()
    if not path.is_file() or path.stat().st_size == 0:
        return plan
    if not resume:
        raise StaleCheckpointError(
            f"{path.name} exists from an earlier attempt; pass --resume to continue it or move it away"
        )
    plan.repaired_tail_bytes = repair_tail(path, key_field, result_keys)
    read = read_checkpoint(path, key_field, result_keys)
    if read.corrupt_middle:
        raise CheckpointError(f"{path.name}: damaged lines before the tail; refusing to resume")
    run_ids = [e["run_id"] for e in read.entries if "run_id" in e]
    if read.legacy_keys and not accept_legacy:
        raise IncompatibleCheckpointError(
            f"{path.name} has lines without a run id; pass --accept-legacy-checkpoint to inherit them"
        )
    known: dict[str, dict[str, Any]] = {}
    if record_id is not None:
        known = {ex["run_id"]: ex for ex in store.read(record_id)["executions"]}
    for run_id in dict.fromkeys(run_ids):
        ex = known.get(run_id)
        if ex is None:
            raise IncompatibleCheckpointError(f"{path.name} belongs to run {run_id} which this record does not know")
        if ex.get("config") != expected_config:
            differing = sorted(k for k in set(ex.get("config", {})) | set(expected_config)
                               if ex.get("config", {}).get(k) != expected_config.get(k))
            raise IncompatibleCheckpointError(f"{path.name}: run {run_id} used a different config: {', '.join(differing)}")
        theirs, ours = _digests(ex.get("inputs", [])), _digests(expected_inputs)
        differing = sorted(r for r in set(theirs) | set(ours) if theirs.get(r) != ours.get(r))
        if differing:
            raise IncompatibleCheckpointError(f"{path.name}: run {run_id} used different inputs: {', '.join(differing)}")
        for name, expected in (("models", expected_models), ("prompt_sha256", expected_prompt_sha256)):
            recorded = ex.get(name)
            if recorded != expected:
                if isinstance(recorded, dict) and isinstance(expected, dict):
                    keys = sorted(k for k in set(recorded) | set(expected) if recorded.get(k) != expected.get(k))
                else:
                    keys = ["recorded" if recorded is not None else "not recorded"]
                raise IncompatibleCheckpointError(
                    f"{path.name}: run {run_id} used different {name}: {', '.join(keys)}"
                )
    plan.entries_by_key = unique_results(read.entries, key_field)
    plan.inherited_keys = list(plan.entries_by_key)
    plan.resumes_run_id = run_ids[-1] if run_ids else None
    plan.inherited_from = plan.resumes_run_id or ("legacy" if read.legacy_keys else None)
    return plan


def progress(execution: dict[str, Any], checkpoint_path: Path, key_field: str,
             result_keys: tuple[str, ...]) -> dict[str, Any]:
    inherited = list(execution.get("inherited_keys") or [])
    if checkpoint_path.is_file():
        read = read_checkpoint(checkpoint_path, key_field, result_keys)
        run_id = execution.get("run_id")
        if run_id is None:
            mine = [e[key_field] for e in read.entries]
        else:
            mine = [e[key_field] for e in read.entries if e.get("run_id") == run_id]
            if execution.get("inherited_from") == "legacy":
                mine += read.legacy_keys
        completed = len(set(inherited) | set(mine))
        source = "checkpoint"
    else:
        completed = len(set(inherited) | set(execution.get("completed_keys") or []))
        source = "record"
    return {
        "completed": completed, "expected_total": execution.get("expected_total"),
        "work_unit": execution.get("work_unit"), "inherited": len(inherited), "source": source,
    }

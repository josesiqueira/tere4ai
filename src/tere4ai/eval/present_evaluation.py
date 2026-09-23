"""Presenter, list projection and legacy synthesis of evaluation records.

@implements: DEC-17
@grounded_by: REF-27, ADD-20

Every presented field carries a provenance (recorded, derived, unavailable
with a reason); an output copy is verified by digest; a legacy record states
only what its files state (spec G D-G33, D-G34).

The July judge label sheet is pinned to its bytes (JULY_SHEET_DIGEST) like
the July summaries: a sheet with other bytes is either a recorded draw
(its sample.record_id resolves; the draw's record lists it) or an
unrecorded draw, which is the owner's choice and is not listed at all.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from tere4ai.eval.evaluation_record import (
    SCHEMA_VERSION,
    EvaluationRecordError,
    EvaluationRecordStore,
)
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.present import exception_reason, provenance_of

ORDER_SENTENCE = ("groups by the newest started_at in the group, newest first; inside a group newest "
                  "started_at first; records without a date last, by record id; the group with no build "
                  "identity last")
NOT_RECORDED = "not recorded"
NOT_RECORDED_LEGACY = "not recorded: the file states none"
# (summary, checkpoint, analysis file, the exact phrase the analysis states, the date recorded, a note,
#  the sha256 of the July summary: the July bytes this phrase dates)
LEGACY_E6 = (
    ("ablation_run1_summary.json", "ablation_run1_checkpoint.jsonl", "RUN2_ANALYSIS.md", None, None, "",
     "2b32643e4d92f528fddbac4bc3fe128fb17728b70263d25667b80105fcf728e1"),
    ("ablation_summary.json", "ablation_checkpoint.jsonl", "RUN2_ANALYSIS.md", "Date: 2026-07-09", "2026-07-09", "",
     "5ce6a643017b9dd99f1eacc849e85358fc7faea2cc928e482a7782f933ce4b33"),
    ("ablation_full_summary.json", "ablation_full_checkpoint.jsonl", "FULL_RUN_ANALYSIS.md", "Date: 2026-07-10/11",
     "2026-07-10", "; the first day recorded as the start",
     "b3bf6ef838fc6cef921448ba59a37037d63afe59202cc50104b1c7cba982f754"),
    ("ablation_variance_summary.json", "ablation_variance_checkpoint.jsonl", "FULL_RUN_ANALYSIS.md", "on 2026-07-11",
     "2026-07-11", "", "38a7682b396a286d3a010e45b56e7ee5f25100c60302307f186c31ed9e53b16f"),
)
JULY_DIGESTS = {row[0]: row[6] for row in LEGACY_E6}
# the sha256 of the four tracked July checkpoints: the July bytes, never rewritten
JULY_CHECKPOINT_DIGESTS = {
    "ablation_run1_checkpoint.jsonl": "7a4fb16e3880f3c45df1e22b9987ffe504d61e1bba2ca15d646a074d1a6309b6",
    "ablation_checkpoint.jsonl": "11d114d51e35b3f06c7a4fead8f5dcfffb6ffa4f2e1414f8464c3c618dec9180",
    "ablation_full_checkpoint.jsonl": "de7d7c1f7211a5c247caf8d2d8ee22f3568b96b9148dee7647df2c4ca5a79c40",
    "ablation_variance_checkpoint.jsonl": "43f9c2a12f5590cd17b2dcfb241d9e0e62dbc4e4b6debac0d4433be06a3d5825",
}
# the sha256 of eval/gold/judge_label_sheet.json as drawn in July: the July bytes, never rewritten
JULY_SHEET_DIGEST = "a2c5e190bf97b7fe631e61ec7a6315d500734eeba6c5dbf596a56fae84f0c909"
NOT_JULY_BYTES = "not recorded: the file's bytes are not the July bytes this phrase dates"
NO_DATE = "not recorded: no analysis file states a date for this summary"
LEGACY_STUDY = "variance_study.md"
LEGACY_SHEET = "judge_label_sheet.json"
_STUDY_HEADER_RE = re.compile(r"from (\S+\.jsonl) \(run A\) and (\S+\.jsonl) \(run B\)")
_NOT_A_VALUE = ("not recorded", "not applicable")


def _legacy_id(path: Path) -> str:
    return "legacy-" + sha256_of_file(path)[:12]


def _legacy_id_of_name(name: str) -> str:
    return "legacy-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def unreadable_row(record_id: str, reason: str) -> dict[str, Any]:
    return {"record_id": record_id, "kind": None, "step": None, "origin": None, "command": None, "started_at": None,
            "ended_at": None, "status": None, "build_key": "unknown", "build_kind": "unknown", "models": None,
            "counts": {}, "unreadable": True, "reason": reason}


def _copy_state(store: EvaluationRecordStore, output: dict[str, Any]) -> tuple[str, str | None]:
    if output.get("copy") is None:
        return "not_kept", "legacy: the file on disk is the record"
    path = store.dir / output["copy"]
    if not path.is_file():
        return "missing", f"copy file absent: {output['copy']}"
    if sha256_of_file(path) != output["sha256"]:
        return "drifted", "copy digest differs from the recorded output digest"
    return "present", None


def present_evaluation(record: dict[str, Any], store: EvaluationRecordStore, now: datetime) -> dict[str, Any]:
    rec = dict(record)
    stored_reasons: dict[str, str] = rec.pop("_reasons", {})
    synthesised = rec.get("origin") == "legacy"
    outputs = []
    for output in rec.get("outputs", []):
        state, reason = _copy_state(store, output)
        outputs.append({**output, "copy_state": state, "copy_reason": reason})
    rec["outputs"] = outputs
    null_reasons = dict(stored_reasons)
    outcome = rec.get("outcome")
    if outcome and outcome.get("status") == "running":
        null_reasons.setdefault("ended_at", "running: no end recorded")
    if (rec.get("config") or {}).get("mode") == "offline":
        null_reasons.setdefault("models", "offline: no live model was called")
        for key in ("prompt_versions", "prompt_sha256", "sampling", "usage"):
            null_reasons.setdefault(key, "not applicable: no live model was called")
    if rec.get("kind") == "comparison":
        for key in ("models", "prompt_versions", "prompt_sha256", "sampling", "usage", "item_selection_sha256"):
            null_reasons.setdefault(key, "not applicable: a comparison calls no model")
    if rec.get("command") == "run_ablations":
        null_reasons.setdefault("prompt_sha256", "not recorded: the ablation runner reads no prompt hash")
    provenance, reasons = provenance_of(
        {k: v for k, v in rec.items() if k not in ("outputs",)}, derived_keys=set(), synthesised=synthesised,
        reason_null=NOT_RECORDED_LEGACY if synthesised else NOT_RECORDED, null_reasons=null_reasons)
    for key, reason in stored_reasons.items():
        if key not in provenance:
            continue
        if reason.startswith(_NOT_A_VALUE):
            provenance[key], reasons[key] = "unavailable", reason  # a container whose fact is null (R17)
        elif rec.get(key) is not None:
            provenance[key], reasons[key] = "derived", reason
    provenance["outputs"] = "derived" if synthesised else "recorded"
    rec.update({"observed_at": now.isoformat(), "synthesised": synthesised, "provenance": provenance,
                "reasons": reasons})
    return rec


def summary_of(presented: dict[str, Any]) -> dict[str, Any]:
    build = presented.get("build") or {}
    if (build.get("publication") or {}).get("build_id"):
        key, kind = build["publication"]["build_id"], "publication"
    elif build.get("base_build_id"):
        key, kind = build["base_build_id"], "base"
    else:
        key, kind = "unknown", "unknown"
    outcome = presented.get("outcome")
    return {"record_id": presented["record_id"], "kind": presented["kind"], "step": presented["step"],
            "origin": presented["origin"], "command": presented["command"], "started_at": presented.get("started_at"),
            "ended_at": presented.get("ended_at"), "status": outcome["status"] if outcome else None,
            "build_key": key, "build_kind": kind, "models": presented.get("models"),
            "counts": dict(presented.get("counts") or {}), "unreadable": False, "reason": None}


def _row_key(row: dict[str, Any]) -> tuple[int, str, str]:
    started = row.get("started_at")
    return (1, "", row["record_id"]) if started is None else (0, _descending(started), row["record_id"])


def _descending(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(c)) for c in value)


def group_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        g = groups.setdefault(row["build_key"], {"build_key": row["build_key"], "build_kind": row["build_kind"],
                                                  "records": []})
        g["records"].append(row)
    for g in groups.values():
        g["records"].sort(key=_row_key)

    def group_key(g: dict[str, Any]) -> tuple[int, str, str]:
        if g["build_key"] == "unknown":
            return (2, "", "")
        dated = [r["started_at"] for r in g["records"] if r.get("started_at")]
        return (0, _descending(max(dated)), g["build_key"]) if dated else (1, "", g["build_key"])

    return sorted(groups.values(), key=group_key)


def _empty_legacy(record_id: str, kind: str, step: str, command: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "record_id": record_id, "kind": kind, "step": step, "origin": "legacy",
            "command": command, "argv": [], "started_at": None, "ended_at": None, "outcome": None,
            "build": {"base_build_id": None, "publication": None, "publication_reason": None}, "inputs": [],
            "item_selection_sha256": None, "models": None, "prompt_versions": None, "prompt_sha256": None,
            "sampling": None, "usage": None, "config": {}, "counts": {}, "outputs": [],
            "relations": {"repeat_of": None, "resumes_record_id": None, "compares": [], "sample_id": None,
                          "labelling_record_ids": []}, "notes": [], "_reasons": {}}


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: the JSON root is not an object")
    return data


def _states(results: Path, analysis: str, phrase: str | None) -> bool:
    path = results / analysis
    try:
        return phrase is not None and path.is_file() and phrase in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _legacy_run(results: Path, summary: str, checkpoint: str, analysis: str, phrase: str | None, date: str | None,
                note: str, dated_digest: str | None) -> dict[str, Any]:
    path = results / summary
    data = _read_json(path)
    rec = _empty_legacy(_legacy_id(path), "run", "E6", "run_ablations")
    rec["outputs"].append({"role": "summary", "file": summary, "sha256": sha256_of_file(path), "copy": None})
    if (results / checkpoint).is_file():
        rec["outputs"].append({"role": "checkpoint", "file": checkpoint, "sha256": sha256_of_file(results / checkpoint),
                               "copy": None})
    if not _states(results, analysis, phrase):
        rec["_reasons"]["started_at"] = NO_DATE
    elif rec["outputs"][0]["sha256"] != dated_digest:
        # a recorded run rewrote the compatibility file: the phrase dates other bytes
        rec["_reasons"]["started_at"] = NOT_JULY_BYTES
    else:
        rec["started_at"] = date
        rec["_reasons"]["started_at"] = f"date stated by eval/results/{analysis} ({phrase}){note}"
    rec["_reasons"]["build"] = "not recorded: the summary and its checkpoint carry no build id"
    rec["_reasons"]["outcome"] = "not recorded: the summary states no outcome"
    rec["_reasons"]["relations"] = "not recorded: the summary names no other run"
    config = data.get("config") or {}
    if config.get("generator_model") or config.get("judge_model"):
        rec["models"] = {"generator_model": config.get("generator_model"), "judge_model": config.get("judge_model")}
        missing = [label for key, label in (("generator_model", "generator model"), ("judge_model", "judge model"))
                   if not config.get(key)]
        if missing:
            rec["_reasons"]["models"] = f"derived: the summary names no {missing[0]}"
    strategies = sorted((data.get("strategies") or {}).keys())
    if strategies:
        rec["config"] = {"strategies": strategies}
    else:
        rec["_reasons"]["config"] = "not recorded: the summary names no strategy"
    if isinstance(data.get("items_total"), int):
        rec["counts"]["items_total"] = data["items_total"]
    usage = (data.get("usage_provider_reported") or {}).get("by_role")
    if usage:
        rec["usage"] = usage
    return rec


def _legacy_comparison(root: Path, runs_by_checkpoint: dict[str, str]) -> dict[str, Any]:
    path = root / "docs" / LEGACY_STUDY
    rec = _empty_legacy(_legacy_id(path), "comparison", "E6", "variance_report")
    rec["outputs"].append({"role": "study", "file": LEGACY_STUDY, "sha256": sha256_of_file(path), "copy": None})
    header = _STUDY_HEADER_RE.search(path.read_text(encoding="utf-8"))
    run_a = runs_by_checkpoint.get(header.group(1)) if header else None
    run_b = runs_by_checkpoint.get(header.group(2)) if header else None
    if run_a and run_b:
        rec["relations"]["compares"] = [run_a, run_b]
        rec["_reasons"]["relations"] = (f"derived: the study's header names {header.group(1)} (run A) and "
                                        f"{header.group(2)} (run B)")
    else:
        rec["_reasons"]["relations"] = "not recorded: the study's header names no checkpoint this synthesis knows"
    rec["_reasons"].update({"started_at": "not recorded: the study states no date",
                            "build": "not recorded: the study carries no build id",
                            "outcome": "not recorded: the study states no outcome",
                            "models": "not applicable: a comparison calls no model"})
    return rec


def _legacy_sheet(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    rec = _empty_legacy(_legacy_id(path), "sample", "E1", "sample_judge_decisions")
    rec["outputs"].append({"role": "sheet_json", "file": LEGACY_SHEET, "sha256": sha256_of_file(path), "copy": None})
    base = (data.get("builds") or {}).get("norms_core")
    rec["build"]["base_build_id"] = str(base) if base else None
    rec["_reasons"]["build"] = ("derived: the sheet names its base build" if base
                                else "not recorded: the sheet names no build")
    items = data.get("items") or []
    rec["counts"] = {"items": len(items), "labelled": sum(1 for it in items if it.get("human_label") is not None)}
    judge_models = {(it.get("judge_run") or {}).get("judge_model") for it in items}
    if len(judge_models) == 1 and None not in judge_models:
        rec["models"] = {"judge_model": judge_models.pop()}
        rec["_reasons"]["models"] = "derived: the one judge model every item of the sheet names"
    else:
        rec["_reasons"]["models"] = "not recorded: the sheet names several judge models or none"
    sample_id = (data.get("sample") or {}).get("sample_id")
    rec["relations"]["sample_id"] = sample_id
    rec["_reasons"]["relations"] = ("derived: the sheet carries its sample id" if sample_id
                                    else "not recorded: the sheet predates sample ids")
    rec["_reasons"].update({"started_at": "not recorded: the sheet states no date",
                            "outcome": "not recorded: the sheet states no outcome"})
    return rec


def _recorded_output(store: EvaluationRecordStore | None, path: Path) -> bool:
    """True when a recorded run wrote these bytes: the compatibility file is not legacy (R13).

    An unreadable file falls through to its own unreadable row; a store that
    cannot be listed propagates (the route answers 503), never hides a record."""
    if store is None:
        return False
    try:
        digest = sha256_of_file(path)
    except OSError:
        return False
    return store.find_by_output_digest(digest) is not None


def _recorded_sheet(store: EvaluationRecordStore | None, path: Path) -> bool:
    if store is None:
        return False
    try:
        record_id = (_read_json(path).get("sample") or {}).get("record_id")
        return bool(record_id) and store.read(str(record_id)) is not None
    except (OSError, ValueError, EvaluationRecordError):
        return False


def _july_sheet(path: Path, dated_digests: dict[str, str]) -> bool:
    """True when the sheet's bytes are the pinned July bytes (or the caller's
    dated_digests entry for the sheet); an unreadable sheet stays a candidate
    so it is reported as its own unreadable row."""
    try:
        return sha256_of_file(path) == dated_digests.get(LEGACY_SHEET, JULY_SHEET_DIGEST)
    except OSError:
        return True


def synthesise_legacy_evaluations(root: Path | str, store: EvaluationRecordStore | None = None,
                                  dated_digests: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Legacy records for the July 2026 files that exist under root and that no
    recorded run wrote; read-only. A stated date applies only to the bytes
    dated_digests names for the file (default: the July digests); the sheet
    is the July sample only when its bytes are the pinned ones (or the
    dated_digests entry for judge_label_sheet.json)."""
    dated_digests = JULY_DIGESTS if dated_digests is None else dated_digests
    root = Path(root)
    results = root / "eval" / "results"
    records: list[dict[str, Any]] = []
    runs_by_checkpoint: dict[str, str] = {}
    for summary, checkpoint, analysis, phrase, date, note, _ in LEGACY_E6:
        path = results / summary
        if not path.is_file() or _recorded_output(store, path):
            continue
        try:
            rec = _legacy_run(results, summary, checkpoint, analysis, phrase, date, note,
                              dated_digests.get(summary))
        except Exception as exc:  # noqa: BLE001 - reported as the file's row, never raised out of the list
            try:
                record_id = _legacy_id(path)
            except OSError:
                record_id = _legacy_id_of_name(summary)
            records.append(unreadable_row(record_id, exception_reason(exc)))
            continue
        runs_by_checkpoint[checkpoint] = rec["record_id"]
        records.append(rec)
    study = root / "docs" / LEGACY_STUDY
    if study.is_file() and not _recorded_output(store, study):
        try:
            records.append(_legacy_comparison(root, runs_by_checkpoint))
        except Exception as exc:  # noqa: BLE001
            try:
                record_id = _legacy_id(study)
            except OSError:
                record_id = _legacy_id_of_name(LEGACY_STUDY)
            records.append(unreadable_row(record_id, exception_reason(exc)))
    sheet = root / "eval" / "gold" / LEGACY_SHEET
    if sheet.is_file() and not _recorded_sheet(store, sheet) and _july_sheet(sheet, dated_digests):
        try:
            records.append(_legacy_sheet(sheet))
        except Exception as exc:  # noqa: BLE001
            try:
                record_id = _legacy_id(sheet)
            except OSError:
                record_id = _legacy_id_of_name(LEGACY_SHEET)
            records.append(unreadable_row(record_id, exception_reason(exc)))
    return records

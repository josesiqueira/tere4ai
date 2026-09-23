"""Evaluation records: one immutable record per measurement run of E1 and E6.

@implements: DEC-17
@grounded_by: REF-27, ADD-20

One JSON file per record under data/graph_dumps/evaluation_records/, the
output bytes copied under evaluation_records/<record id>/, a file lock per
write, atomic writes, schema validation on read (spec G D-G33). Origin and
outcome are two fields; identity is the digests of the files measured plus
the publication observed at start; nothing is guessed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import atomic_write_json, scrub_argv
from tere4ai.graph_store.present import _PATH_RE
from tere4ai.graph_store.publication import active_manifest, manifest_path

RECORDS_DIRNAME = "evaluation_records"
SCHEMA_VERSION = "evaluation_record.v1"
KINDS = ("run", "comparison", "sample", "labelling", "analysis")
STEPS = ("E1", "E6")
STATUSES = ("running", "completed", "partial", "failed")
RECORD_FILE_STEM = re.compile(r"^(?:[0-9a-f]{12}|legacy-[0-9a-f]{12})$")
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "json_schemas" / "evaluation_record.schema.json"


class EvaluationRecordError(RuntimeError):
    """A record could not be written, read or resolved; the reason says why."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@lru_cache(maxsize=1)
def _stored_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/$defs/stored_record", "$defs": schema["$defs"]})


def reduce_paths(text: str) -> str:
    """Every path in text reduced to its file name (the rule of
    graph_store.present.exception_reason): a record or a route names what
    could not be read, never where."""
    return _PATH_RE.sub(r"\1", text)


def file_ref(role: str, path: Path | str) -> dict[str, Any]:
    """{"role", "file", "sha256"} of an input or output file; the name only, never the path."""
    return {"role": role, "file": Path(path).name, "sha256": sha256_of_file(path)}


def digest_of_ids(ids: list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def code_version(root: Path | str) -> str | None:
    """The checkout's commit, twelve hex characters, or None outside a git checkout."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=str(root), capture_output=True,
                             text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if re.fullmatch(r"[0-9a-f]{12}", sha) else None


def observe_publication(dump_dir: Path | str) -> tuple[dict[str, Any] | None, str | None]:
    """The activated publication as (ref, None), or (None, reason). Read once, never cached."""
    dump_dir = Path(dump_dir)
    pointer = dump_dir / "ACTIVE_MANIFEST.json"
    if not pointer.is_file():
        return None, "no ACTIVE_MANIFEST.json: the facade serves the legacy files"
    try:
        chain_id = str(json.loads(pointer.read_text(encoding="utf-8")).get("chain_id"))
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        return None, f"ACTIVE_MANIFEST.json unreadable: {type(exc).__name__}"
    manifest = active_manifest(dump_dir)
    if manifest is None:
        return None, f"no readable publication manifest for chain {chain_id}"
    path = manifest_path(dump_dir, chain_id)
    return {"manifest_file": str(path.relative_to(dump_dir)), "sha256": sha256_of_file(path),
            "build_id": str(manifest.get("build_id"))}, None


def served_input_paths(dump_dir: Path | str) -> dict[str, Path]:
    """The files the facade serves, by role: the active manifest's files, else the legacy names."""
    dump_dir = Path(dump_dir)
    manifest = active_manifest(dump_dir) if (dump_dir / "ACTIVE_MANIFEST.json").is_file() else None
    if manifest is None:
        return {"layer1_dump": dump_dir / "layer1.json", "norms": dump_dir / "norms_core.json",
                "alignments": dump_dir / "alignments_core.json"}
    files = manifest.get("files") or {}
    return {role: dump_dir / files[role] for role in ("layer1_dump", "norms", "alignments") if files.get(role)}


def _empty_relations() -> dict[str, Any]:
    return {"repeat_of": None, "resumes_record_id": None, "compares": [], "sample_id": None,
            "labelling_record_ids": []}


class EvaluationRecordStore:
    def __init__(self, dump_dir: Path | str, *, create: bool = True) -> None:
        self.dir = Path(dump_dir) / RECORDS_DIRNAME
        self.create = create
        if create:
            self.dir.mkdir(parents=True, exist_ok=True)

    # ---- locking and files
    @contextmanager
    def _locked(self, name: str):
        if not self.create:
            raise EvaluationRecordError("read-only store: no writes")
        lock_path = self.dir / f"{name}.lock"
        with open(lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _path(self, record_id: str) -> Path:
        return self.dir / f"{record_id}.json"

    def _read_raw(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationRecordError(reduce_paths(f"{path.name}: not readable JSON: {exc}")) from exc
        errors = sorted(_stored_validator().iter_errors(data), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "the record"
            raise EvaluationRecordError(reduce_paths(f"{path.name}: {first.message} at {where}"))
        return data

    def read(self, record_id: str) -> dict[str, Any]:
        path = self._path(record_id)
        if not path.is_file():
            raise EvaluationRecordError(f"no evaluation record {record_id}")
        return self._read_raw(path)

    def list_records(self) -> list[dict[str, Any]]:
        if not self.dir.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        # os.scandir, not glob: a directory that cannot be listed raises OSError
        # to the caller (the route answers 503), never an empty list (R19).
        with os.scandir(self.dir) as entries:
            paths = sorted(Path(e.path) for e in entries if e.is_file() and e.name.endswith(".json"))
        for path in paths:
            if not RECORD_FILE_STEM.match(path.stem):
                continue
            try:
                rows.append(self._read_raw(path))
            except EvaluationRecordError as exc:
                rows.append({"record_id": path.stem, "unreadable": True, "reason": str(exc)})
        return rows

    def _finished_newest_first(self) -> list[dict[str, Any]]:
        rows = [r for r in self.list_records() if not r.get("unreadable") and r.get("ended_at")]
        return sorted(rows, key=lambda r: (r["ended_at"], r["record_id"]), reverse=True)

    def find_by_output_file(self, name: str) -> str | None:
        for r in self._finished_newest_first():
            if any(o["file"] == name for o in r["outputs"]):
                return r["record_id"]
        return None

    def find_by_checkpoint_file(self, name: str) -> str | None:
        """The record a resume of the checkpoint file `name` continues.

        The newest readable record (by started_at, any status: running and
        failed included) whose config names the checkpoint file at begin,
        else the newest finished record with an output of that file name,
        else None."""
        rows = [r for r in self.list_records()
                if not r.get("unreadable") and (r.get("config") or {}).get("checkpoint_file") == name]
        if rows:
            return max(rows, key=lambda r: (r["started_at"], r["record_id"]))["record_id"]
        return self.find_by_output_file(name)

    def find_by_output_digest(self, sha256: str) -> str | None:
        for r in self._finished_newest_first():
            if any(o["sha256"] == sha256 for o in r["outputs"]):
                return r["record_id"]
        return None

    def find_by_input_digest(self, sha256: str) -> str | None:
        for r in self._finished_newest_first():
            if any(i["sha256"] == sha256 for i in r["inputs"]):
                return r["record_id"]
        return None

    # ---- writes
    def begin(self, *, kind: str, step: str, command: str, argv: list[str], inputs: list[dict[str, Any]],
              build: dict[str, Any], models: dict[str, Any] | None = None,
              prompt_versions: dict[str, Any] | None = None, prompt_sha256: dict[str, Any] | None = None,
              sampling: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
              item_selection: list[str] | None = None, intended_items: list[str] | tuple[str, ...] = (),
              relations: dict[str, Any] | None = None, counts: dict[str, Any] | None = None,
              checkpoint_file: str | None = None) -> str:
        if kind not in KINDS or step not in STEPS:
            raise EvaluationRecordError(f"unknown kind {kind!r} or step {step!r}")
        record_id = _new_id()
        record = {
            "schema_version": SCHEMA_VERSION, "record_id": record_id, "kind": kind, "step": step,
            "origin": "recorded", "command": command, "argv": scrub_argv(list(argv)), "started_at": _now(),
            "ended_at": None,
            "outcome": {"status": "running", "intended_items": list(intended_items), "completed_items": [],
                        "error": None},
            "build": dict(build), "inputs": list(inputs),
            "item_selection_sha256": digest_of_ids(list(item_selection)) if item_selection is not None else None,
            "models": models, "prompt_versions": prompt_versions, "prompt_sha256": prompt_sha256,
            "sampling": sampling, "usage": None,
            "config": {**(config or {}), **({"checkpoint_file": checkpoint_file} if checkpoint_file else {})},
            "counts": dict(counts or {}),
            "outputs": [], "relations": {**_empty_relations(), **(relations or {})}, "notes": [],
        }
        with self._locked(record_id):
            atomic_write_json(self._path(record_id), record)
        return record_id

    def keep_output(self, record_id: str, role: str, path: Path | str) -> dict[str, Any]:
        """Copy the output's bytes under the record's directory; the copy is never overwritten.

        The existence check and the copy happen under the record's lock, and the
        copy itself lands via a unique temp file plus os.replace, so a reader
        never observes a partial copy and two concurrent callers for the same
        record and role never race past the "already exists" refusal.
        """
        if not self.create:
            raise EvaluationRecordError("read-only store: no writes")
        src = Path(path)
        target_dir = self.dir / record_id
        target_dir.mkdir(exist_ok=True)
        target = target_dir / f"{role}{src.suffix}"
        with self._locked(record_id):
            if target.exists():
                raise EvaluationRecordError(f"output copy exists: {target.relative_to(self.dir)}")
            fd, tmp = tempfile.mkstemp(prefix="tmp", dir=str(target_dir))
            try:
                os.close(fd)
                shutil.copyfile(src, tmp)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        ref = file_ref(role, src)
        ref["copy"] = str(target.relative_to(self.dir))
        return ref

    def finish(self, record_id: str, *, status: str, completed_items: list[str] | tuple[str, ...] = (),
               intended_items: list[str] | None = None, error: str | None = None,
               outputs: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
               usage: dict[str, Any] | None = None, counts: dict[str, Any] | None = None,
               notes: list[str] | tuple[str, ...] = (), models: dict[str, Any] | None = None,
               prompt_versions: dict[str, Any] | None = None, sampling: dict[str, Any] | None = None,
               relations: dict[str, Any] | None = None) -> None:
        if status not in STATUSES or status == "running":
            raise EvaluationRecordError(f"finish status must be completed, partial or failed, not {status!r}")
        with self._locked(record_id):
            record = self.read(record_id)
            if record["ended_at"] is not None:
                raise EvaluationRecordError(f"evaluation record {record_id} already ended")
            record["ended_at"] = _now()
            record["outcome"].update({"status": status, "completed_items": list(completed_items), "error": error})
            if intended_items is not None:
                record["outcome"]["intended_items"] = list(intended_items)
            record["outputs"] = list(outputs)
            if usage is not None:
                record["usage"] = usage
            if models is not None:
                record["models"] = models
            if prompt_versions is not None:
                record["prompt_versions"] = prompt_versions
            if sampling is not None:
                record["sampling"] = sampling
            if counts:
                record["counts"].update(counts)
            if relations:
                record["relations"].update(relations)
            record["notes"] = list(notes)
            atomic_write_json(self._path(record_id), record)

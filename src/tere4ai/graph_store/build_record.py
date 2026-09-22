"""Build record: one file per build assembly, one execution record per command attempt.

@implements: DEC-16
@grounded_by: REF-27, ADD-20

Spec G Section 2 and D-G20: a build in progress has no build id; it is
named by a stable record id, the dump slug is an alias that resolves to
the newest record carrying it, and every command attempt is an execution
with its own run id. A record with a publication is frozen: later work on
the same alias creates a descendant record (parent_record_id). Writes hold
a file lock and go through a unique temporary file; reads validate the
shape against schema/json_schemas/build_record.schema.json. Nothing here
is guessed: a field the command did not record stays null.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

RECORDS_DIRNAME = "build_records"
ALIASES_FILENAME = "aliases.json"
SCHEMA_VERSION = "build_record.v1"
HEARTBEAT_EXPIRY_SECONDS = 300
STEP_IDS = ("L0.1", "L1.1", "L2.1", "L2.2", "L2.3", "L2.4", "L3.1", "L3.2", "L3.3", "L3.4", "L3.5", "P.1", "P.2")
_REDACT_MARKERS = ("key", "token", "secret")
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "json_schemas" / "build_record.schema.json"


class RecordError(RuntimeError):
    pass


class FrozenRecordError(RecordError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@lru_cache(maxsize=1)
def _stored_record_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/$defs/stored_record", "$defs": schema["$defs"]})


def scrub_argv(argv: list[str]) -> list[str]:
    """Redact the value of any flag whose name mentions key, token or secret."""
    out: list[str] = []
    redact_next = False
    for arg in argv:
        if redact_next:
            out.append("<redacted>")
            redact_next = False
            continue
        name = arg.split("=", 1)[0].lower()
        sensitive = arg.startswith("-") and any(m in name for m in _REDACT_MARKERS)
        if sensitive and "=" in arg:
            out.append(f"{arg.split('=', 1)[0]}=<redacted>")
        elif sensitive:
            out.append(arg)
            redact_next = True
        else:
            out.append(arg)
    return out


def liveness(execution: dict[str, Any], now: datetime) -> str:
    """live, unknown (running but no fresh heartbeat) or ended. Never failed: a
    killed process records nothing, so an expired heartbeat is not evidence."""
    if execution.get("status") != "running":
        return "ended"
    beat = execution.get("heartbeat_at")
    if not beat:
        return "unknown"
    age = (now - datetime.fromisoformat(beat)).total_seconds()
    return "live" if age <= HEARTBEAT_EXPIRY_SECONDS else "unknown"


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write payload to path atomically: a unique temp file in the same
    directory, then os.replace. A reader never observes a partial write."""
    fd, tmp = tempfile.mkstemp(prefix="tmp", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _empty_execution(run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id, "command": "", "covers_steps": [], "status": "running", "started_at": _now(),
        "ended_at": None, "heartbeat_at": _now(), "argv": [], "resumes_run_id": None, "inputs": [],
        "outputs": [], "config": {}, "models": None, "prompt_sha256": None, "sampling": None, "usage": None,
        "checkpoint_file": None, "work_unit": None, "expected_total": None, "inherited_keys": [],
        "inherited_from": None, "completed_keys": [], "counts": {}, "gates": [], "work_failures": None,
        "error": None,
    }


class BuildRecordStore:
    def __init__(self, dump_dir: Path | str, *, create: bool = True) -> None:
        self.dir = Path(dump_dir) / RECORDS_DIRNAME
        self.create = create
        if create:
            self.dir.mkdir(parents=True, exist_ok=True)

    # ---- locking and files
    @contextmanager
    def _locked(self, name: str):
        if not self.create:
            raise RecordError("read-only store: no writes")
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
            raise RecordError(f"{path.name}: not readable JSON: {exc}") from exc
        errors = sorted(_stored_record_validator().iter_errors(data), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "the record"
            raise RecordError(f"{path.name}: {first.message} at {where}")
        return data

    def read(self, record_id: str) -> dict[str, Any]:
        path = self._path(record_id)
        if not path.is_file():
            raise RecordError(f"no build record {record_id}")
        return self._read_raw(path)

    def _write(self, record: dict[str, Any]) -> None:
        atomic_write_json(self._path(record["record_id"]), record)

    def _aliases(self) -> dict[str, str]:
        p = self.dir / ALIASES_FILENAME
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise RecordError(f"alias index {p} is unreadable: {exc}") from exc
        return data if isinstance(data, dict) else {}

    # ---- queries
    def resolve(self, ref: str) -> str | None:
        if self._path(ref).is_file():
            return ref
        return self._aliases().get(ref)

    def list_records(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.dir.is_dir():
            return out
        for p in sorted(self.dir.glob("*.json")):
            if p.name == ALIASES_FILENAME:
                continue
            try:
                out.append(self._read_raw(p))
            except RecordError as exc:
                out.append({"record_id": p.stem, "unreadable": True, "reason": str(exc)})
        return out

    def _valid_records_newest_first(self) -> list[dict[str, Any]]:
        valid = [r for r in self.list_records() if not r.get("unreadable")]
        return sorted(valid, key=lambda r: r.get("created_at") or "", reverse=True)

    def find_by_output_digest(self, digest: str) -> str | None:
        for record in self._valid_records_newest_first():
            for ex in record["executions"]:
                if any(o.get("sha256") == digest for o in ex.get("outputs", [])):
                    return record["record_id"]
        return None

    def find_parse_record(self, layer1_digest: str) -> str | None:
        for record in self._valid_records_newest_first():
            for ex in record["executions"]:
                if ex.get("command") == "parse_legal_structure" and any(
                    o.get("role") == "layer1_dump" and o.get("sha256") == layer1_digest for o in ex.get("outputs", [])
                ):
                    return record["record_id"]
        return None

    def is_frozen(self, record_id: str) -> bool:
        return self.read(record_id)["publication"] is not None

    # ---- writes
    def create_record(self, alias: str, base_build_id: str | None, layer1_digest: str | None,
                      parent_record_id: str | None = None) -> str:
        record_id = _new_id()
        record = {
            "schema_version": SCHEMA_VERSION, "record_id": record_id, "aliases": [alias],
            "parent_record_id": parent_record_id, "base_build_id": base_build_id, "created_at": _now(),
            "layer1_digest": layer1_digest, "executions": [], "publication": None,
        }
        with self._locked("aliases"):
            self._write(record)
            aliases = self._aliases()
            aliases[alias] = record_id
            atomic_write_json(self.dir / ALIASES_FILENAME, aliases)
        return record_id

    def _update(self, record_id: str, mutate) -> None:
        with self._locked(record_id):
            record = self.read(record_id)
            mutate(record)
            self._write(record)

    def _execution(self, record: dict[str, Any], run_id: str) -> dict[str, Any]:
        for ex in record["executions"]:
            if ex["run_id"] == run_id:
                return ex
        raise RecordError(f"no execution {run_id!r} in record {record['record_id']!r}")

    def start_execution(self, record_id: str, *, command: str, covers_steps: list[str], argv: list[str],
                        inputs: list[dict[str, Any]], config: dict[str, Any], expected_total: int | None,
                        work_unit: str | None, checkpoint_file: str | None, resumes_run_id: str | None = None,
                        inherited_keys: list[str] | None = None, inherited_from: str | None = None,
                        models=None, prompt_sha256=None, sampling=None) -> str:
        run_id = _new_id()

        def mutate(record):
            if record["publication"] is not None:
                raise FrozenRecordError(
                    f"record {record_id} is published as {record['publication']['chain_id']}; start a descendant"
                )
            ex = _empty_execution(run_id)
            ex.update({
                "command": command, "covers_steps": list(covers_steps), "argv": scrub_argv(list(argv)),
                "inputs": list(inputs), "config": dict(config), "expected_total": expected_total,
                "work_unit": work_unit, "checkpoint_file": checkpoint_file, "resumes_run_id": resumes_run_id,
                "inherited_keys": list(inherited_keys or []), "inherited_from": inherited_from,
                "models": models, "prompt_sha256": prompt_sha256, "sampling": sampling,
            })
            record["executions"].append(ex)

        self._update(record_id, mutate)
        return run_id

    def heartbeat(self, record_id: str, run_id: str) -> None:
        self._update(record_id, lambda r: self._execution(r, run_id).__setitem__("heartbeat_at", _now()))

    def finish_execution(self, record_id: str, run_id: str, *, status: str, outputs=None, counts=None, usage=None,
                         models=None, prompt_sha256=None, sampling=None, gates=None, completed_keys=None,
                         work_failures=None, error: str | None = None) -> None:
        if status not in ("done", "failed"):
            raise ValueError(f"status must be done or failed, got {status!r}")

        def mutate(record):
            ex = self._execution(record, run_id)
            ex["status"] = status
            ex["ended_at"] = _now()
            for key, value in (("outputs", outputs), ("counts", counts), ("usage", usage), ("models", models),
                               ("prompt_sha256", prompt_sha256), ("sampling", sampling), ("gates", gates),
                               ("completed_keys", completed_keys), ("work_failures", work_failures)):
                if value is not None:
                    ex[key] = value
            ex["error"] = error

        self._update(record_id, mutate)

    def set_publication(self, record_id: str, publication: dict[str, Any]) -> None:
        def mutate(record):
            if record["publication"] is not None:
                raise FrozenRecordError(f"record {record_id} already published as {record['publication']['chain_id']}")
            record["publication"] = publication

        self._update(record_id, mutate)

    def set_base_build_id(self, record_id: str, base: str) -> None:
        self._update(record_id, lambda r: r.__setitem__("base_build_id", base))

    def set_layer1_digest(self, record_id: str, digest: str) -> None:
        self._update(record_id, lambda r: r.__setitem__("layer1_digest", digest))

    def add_alias(self, record_id: str, alias: str) -> None:
        """Add alias to the record and the alias index. The two locks are taken
        sequentially, record first, then aliases: never held nested."""
        self._update(record_id, lambda r: r["aliases"].append(alias) if alias not in r["aliases"] else None)
        with self._locked("aliases"):
            aliases = self._aliases()
            aliases[alias] = record_id
            atomic_write_json(self.dir / ALIASES_FILENAME, aliases)


def select_record(store: BuildRecordStore, ref: str, base_build_id: str | None,
                  layer1_digest: str | None) -> tuple[str, str | None]:
    """Reuse an open record built on the same Layer 1; otherwise continue as a
    descendant (D-G20): a published record is frozen, and a record built on
    another layer1.json is another assembly. Returns the record id and a
    message to print, or None when nothing needs to be said. Shared by every
    recording command (extract_norms, align_hleg_altai) so the rule and its
    message stay in one place."""
    existing = store.resolve(ref)
    if existing is None:
        return store.create_record(ref, base_build_id, layer1_digest), None
    record = store.read(existing)
    same_layer1 = record["layer1_digest"] in (None, layer1_digest)
    if record["publication"] is None and same_layer1:
        return existing, None
    why = "is published" if record["publication"] is not None else "was built on another Layer 1"
    child = store.create_record(ref, base_build_id, layer1_digest, parent_record_id=existing)
    return child, f"record {existing} {why}; continuing as descendant {child}"


def relative_to_dump_dir(path: Path, dump_dir: Path) -> str:
    """Path relative to dump_dir when it lies under it, else the absolute path.
    The presenter later resolves dump_dir / this value."""
    try:
        return str(path.relative_to(dump_dir))
    except ValueError:
        return str(path)


def gate_entries(failures: list[str], names: tuple[str, ...], stats: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per named gate: ok unless a failure string carries its prefix."""
    entries = []
    rendered_stats = ", ".join(f"{k}={v}" for k, v in sorted(stats.items()))
    for name in names:
        mine = [f for f in failures if f.startswith(f"{name} ")]
        entries.append({"name": name, "ok": not mine, "detail": "; ".join(mine)})
    if rendered_stats:
        for entry in reversed(entries):
            if entry["ok"]:
                entry["detail"] = rendered_stats
                break
    return entries

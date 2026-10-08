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
import re
import signal
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

RECORDS_DIRNAME = "build_records"
ALIASES_FILENAME = "aliases.json"
NUMBERING_FILENAME = "numbering.json"
# The files that carry a build number beside the records (spec G D-G50); a
# stem that is not a chain id (a tmp*.json of atomic_write_json, mid-write or
# left by a killed process) is never one of them.
NUMBERED_GLOBS = (("build_chain_*.json", re.compile(r"^build_chain_[0-9a-f]{12}$")),
                  ("publications/*.json", re.compile(r"^[0-9a-f]{12}$")))
NUMBERING_UNBLOCK = ("repair or move each file aside, or write build_records/numbering.json as "
                     '{"last_number": N} with N at least the highest number those files held')
SCHEMA_VERSION = "build_record.v2"
HEARTBEAT_EXPIRY_SECONDS = 300
# The step ids in full words (B155): a capital letter and a number meant two
# things, so each id names its layer or the publication and its step.
STEP_IDS = ("LAYER0_STEP1", "LAYER1_STEP1", "LAYER2_STEP1", "LAYER2_STEP2", "LAYER2_STEP3", "LAYER2_STEP4",
            "LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3", "LAYER3_STEP4", "LAYER3_STEP5",
            "PUBLICATION_STEP1", "PUBLICATION_STEP2")
_REDACT_MARKERS = ("key", "token", "secret", "password", "passwd", "credential", "auth")
RECORD_FILE_STEM = re.compile(r"^(?:[0-9a-f]{12}|legacy-.+)$")
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "json_schemas" / "build_record.schema.json"

# B79 item 4: a paid run beats on a clock, not per unit of work, since one
# group or batch at a high effort can outlast the expiry; a fifth of it
# leaves room for a slow disk or a held lock.
HEARTBEAT_INTERVAL_SECONDS = 60


class RecordError(RuntimeError):
    pass


class FrozenRecordError(RecordError):
    pass


class LiveExecutionError(RecordError):
    """A publication was asked for while another execution of the record is live."""


class NumberingError(RecordError):
    """A build number cannot be issued safely (spec G D-G50): a file that may
    hold the highest number cannot be read while the counter is absent, or
    another record already holds the number."""


def _number_in(payload: Any) -> int | None:
    """The build_number a record, a chain record or a manifest carries, or None."""
    if not isinstance(payload, dict):
        return None
    holder = payload.get("publication") if "publication" in payload else payload
    number = holder.get("build_number") if isinstance(holder, dict) else None
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def numbered_files(dump_dir: Path | str) -> tuple[dict[str, int], list[str]]:
    """Every chain record and publication manifest of the dump directory that
    carries a build number (spec G D-G50), as {relative path: number}, and the
    relative paths that could not be read. A file whose stem is not a chain id
    is skipped."""
    dump_dir = Path(dump_dir)
    numbers: dict[str, int] = {}
    unreadable: list[str] = []
    for pattern, stem in NUMBERED_GLOBS:
        for path in sorted(dump_dir.glob(pattern)):
            if not stem.match(path.stem):
                continue
            rel = str(path.relative_to(dump_dir))
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                unreadable.append(rel)
                continue
            number = _number_in(payload)
            if number is not None:
                numbers[rel] = number
    return numbers, unreadable


def duplicate_build_numbers(dump_dir: Path | str) -> list[str]:
    """One line per build number that two chain records or two manifests
    carry for different chains (spec G D-G50, review M7), and one line per
    chain whose chain record and manifest carry different numbers (final
    review B-P3-1): a chain record and its own manifest carry the same number
    by design."""
    numbers, _ = numbered_files(dump_dir)
    by_number: dict[int, set[str]] = {}
    by_chain: dict[str, set[int]] = {}
    for rel, number in numbers.items():
        chain = Path(rel).stem.removeprefix("build_chain_")
        by_number.setdefault(number, set()).add(chain)
        by_chain.setdefault(chain, set()).add(number)
    lines = [f"Build {n} is carried by chains {', '.join(sorted(chains))}"
             for n, chains in sorted(by_number.items()) if len(chains) > 1]
    lines += [f"chain {chain} carries Builds {', '.join(str(n) for n in sorted(held))}"
              for chain, held in sorted(by_chain.items()) if len(held) > 1]
    return lines


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@lru_cache(maxsize=1)
def _stored_record_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/$defs/stored_record", "$defs": schema["$defs"]})


def scrub_argv(argv: list[str]) -> list[str]:
    """Redact the value of any flag whose name mentions key, token, secret,
    password, passwd, credential or auth (B79 item 8; "auth" also catches a
    flag such as --author, which errs on the safe side)."""
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


def _late_write_refusal(record: dict[str, Any], ex: dict[str, Any], publisher: str | None) -> str | None:
    """Why a write to this execution is refused, or None. A published record is
    frozen (spec G D-G20, D-G21, B79 item 15); only the publishing run (the run
    id this store object passed to set_publication) may still end."""
    publication = record["publication"]
    if publication is None or ex["run_id"] == publisher:
        return None
    return (f"record {record['record_id']} was published as chain {publication['chain_id']} while execution "
            f"{ex['run_id']} ({ex['command']}) was running; nothing more is written to it, and this run's "
            "output file and checkpoint stay on disk")


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
        # record id to the run id this store object published it with (B79
        # item 15): the schema allows no new key on an execution, and only
        # the publishing process holds this object.
        self._published_by: dict[str, str] = {}
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
        # Checked before the schema, so an old record is named by its version
        # (B155: the step ids became full words in build_record.v2); a file
        # with no version falls through to the schema and its own message.
        version = data.get("schema_version") if isinstance(data, dict) else None
        if version is not None and version != SCHEMA_VERSION:
            raise RecordError(
                f"build record {path.name} has schema_version {version!r}; this store reads {SCHEMA_VERSION} "
                "(pre-B74 records are disposable; rewrite them with scripts/rename_build_record_steps.py)")
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
            # Only names a record can have: a temp file of atomic_write_json
            # (tmp*.json), mid-write or left by a killed process, never is one.
            if not RECORD_FILE_STEM.match(p.stem):
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

    # ---- build numbers (spec G D-G50)
    def _counter(self) -> int | None:
        """The high-water mark in numbering.json; None when the file is absent
        or unreadable (binary garbage included)."""
        try:
            data = json.loads((self.dir / NUMBERING_FILENAME).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        value = data.get("last_number") if isinstance(data, dict) else None
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def next_build_number(self) -> int:
        """1 above the largest number held by the counter, the build records,
        the publication manifests and the chain records of the dump directory.
        Refused (NumberingError, naming the files and how to unblock) when the
        counter is absent and a record, manifest or chain record cannot be
        read, since the unread file may hold the highest number."""
        counter = self._counter()
        records = self.list_records()
        bad_records = [f"{RECORDS_DIRNAME}/{r['record_id']}.json" for r in records if r.get("unreadable")]
        files, bad_files = numbered_files(self.dir.parent)
        if counter is None and (bad_records or bad_files):
            raise NumberingError(f"the build number counter {RECORDS_DIRNAME}/{NUMBERING_FILENAME} is absent or unreadable "
                                 "and these files cannot be read, so the next "
                                 f"number is unknown: {', '.join(bad_records + bad_files)}; {NUMBERING_UNBLOCK}")
        held = [counter or 0, *files.values()]
        held += [n for r in records if not r.get("unreadable") and (n := _number_in(r)) is not None]
        return max(held) + 1

    @contextmanager
    def reserve_build_number(self):
        """Hold the numbering lock and yield the next build number. The
        publish command holds it from before the publication is built until
        its last write, so two publications never get one number and the
        number order is the recorded order of publication."""
        with self.numbering_lock():
            yield self.next_build_number()

    @contextmanager
    def numbering_lock(self):
        """The numbering lock alone (spec G D-G50): every writer of a chain
        record, a publication manifest or a build number holds it, so a check
        made under it is exact."""
        with self._locked("numbering"):
            yield

    def record_build_number(self, number: int) -> str | None:
        """Write the counter as soon as the record is frozen; never raises (the
        maximum over the records, manifests and chain records repairs a lost
        write) and never lowers it (final review A-M8). Returns the failure as
        one line, or None."""
        try:
            atomic_write_json(self.dir / NUMBERING_FILENAME, {"last_number": max(self._counter() or 0, number)})
        except OSError as exc:
            return f"the build number counter was not written ({exc}); the next publication reads the number from the records"
        return None

    def publisher_of(self, chain_id: str) -> dict[str, Any] | None:
        """The readable record whose publication carries this chain id, or
        None (spec G D-G50, review I2): a chain is published once, whatever
        files around it were lost or removed."""
        for record in self.list_records():
            if not record.get("unreadable") and (record.get("publication") or {}).get("chain_id") == chain_id:
                return record
        return None

    def is_frozen(self, record_id: str) -> bool:
        return self.read(record_id)["publication"] is not None

    def _live_others(self, record: dict[str, Any], excluding: str | None = None) -> list[dict[str, Any]]:
        now = datetime.fromisoformat(_now())
        return [ex for ex in record["executions"]
                if ex["run_id"] != excluding and liveness(ex, now) == "live"]

    def live_executions(self, record_id: str) -> list[dict[str, Any]]:
        """Executions of the record whose heartbeat is fresh (a publish command
        asks before it starts its own execution, so nothing is excluded)."""
        return self._live_others(self.read(record_id))

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
            # the index first (B79 item 17): an unreadable index refuses before
            # the record file exists, so no unaliased record is left behind
            aliases = self._aliases()
            self._write(record)
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
        unknown = [step for step in covers_steps if step not in STEP_IDS]
        if unknown:
            raise RecordError(
                f"record {record_id}: covers_steps names {', '.join(repr(s) for s in unknown)}, "
                f"which is not a build step id (known: {', '.join(STEP_IDS)})"
            )
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

    def heartbeat(self, record_id: str, run_id: str, *, usage: dict[str, Any] | None = None) -> None:
        """Beat the execution's heartbeat. With usage, also write the usage per
        role so far onto the running execution (final review A2 (b)): a hard
        kill (SIGKILL) then loses at most the unit in flight's spend. A beat
        without usage keeps the last one written."""
        def mutate(record):
            ex = self._execution(record, run_id)
            refusal = _late_write_refusal(record, ex, self._published_by.get(record_id))
            if refusal:
                raise FrozenRecordError(refusal)
            ex["heartbeat_at"] = _now()
            if usage is not None:
                ex["usage"] = usage

        self._update(record_id, mutate)

    def finish_execution(self, record_id: str, run_id: str, *, status: str, outputs=None, counts=None, usage=None,
                         models=None, prompt_sha256=None, sampling=None, gates=None, completed_keys=None,
                         work_failures=None, error: str | None = None) -> None:
        if status not in ("done", "failed"):
            raise RecordError(f"status must be done or failed, got {status!r}")

        def mutate(record):
            ex = self._execution(record, run_id)
            refusal = _late_write_refusal(record, ex, self._published_by.get(record_id))
            if refusal:
                raise FrozenRecordError(refusal)
            ex["status"] = status
            ex["ended_at"] = _now()
            for key, value in (("outputs", outputs), ("counts", counts), ("usage", usage), ("models", models),
                               ("prompt_sha256", prompt_sha256), ("sampling", sampling), ("gates", gates),
                               ("completed_keys", completed_keys), ("work_failures", work_failures)):
                if value is not None:
                    ex[key] = value
            ex["error"] = error

        self._update(record_id, mutate)

    def set_publication(self, record_id: str, publication: dict[str, Any], *, run_id: str | None = None) -> None:
        """Freeze the record (D-G20). Refused under the record lock while an
        execution other than run_id is live (B79 item 15); under the same lock this
        store object remembers run_id as the publisher, the one execution
        still allowed to end. With no run_id nothing is excluded and no
        execution may write after the publication."""
        def mutate(record):
            if record["publication"] is not None:
                raise FrozenRecordError(f"record {record_id} already published as {record['publication']['chain_id']}")
            number = publication.get("build_number")
            if number is not None:
                holders = [r["record_id"] for r in self.list_records()
                           if not r.get("unreadable") and r["record_id"] != record_id and _number_in(r) == number]
                if holders:
                    raise NumberingError(f"build number {number} is already held by record {', '.join(holders)}")
            live = self._live_others(record, excluding=run_id)
            if live:
                named = ", ".join(f"{ex['run_id']} ({ex['command']}, heartbeat {ex['heartbeat_at']})" for ex in live)
                raise LiveExecutionError(f"record {record_id} has a live running execution: {named}; "
                                         "wait for it to end or stop it before publishing")
            record["publication"] = publication
            # Remembered under the lock, before the write (final review F1): a
            # beat of the publishing run landing right after the lock is
            # released must already see its run as the publisher. A failed
            # write leaves the record unpublished, so the entry then allows
            # nothing a live record would refuse.
            if run_id is not None:
                self._published_by[record_id] = run_id

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


@contextmanager
def signals_as_interrupt():
    """Turn SIGTERM and SIGHUP into KeyboardInterrupt for the block (final
    review A2 (a)): a closed terminal or a dropped ssh session then ends a
    command through its interrupt path, which records the execution failed
    with its usage and effort, instead of killing it with the execution left
    running and its usage null. The previous handlers come back after the
    block. A signal whose handler is SIG_IGN (a run started with nohup has
    SIGHUP ignored) or was not installed from Python stays untouched, so the
    run survives a closed terminal as its operator asked. Outside the main
    thread no handler can be installed; that is said on stderr and the block
    runs without them."""
    def interrupt(signum, frame):
        raise KeyboardInterrupt(f"signal {signal.Signals(signum).name}")

    previous: dict[int, Any] = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGHUP):
            current = signal.getsignal(sig)
            if current is signal.SIG_IGN or current is None:
                continue
            previous[sig] = signal.signal(sig, interrupt)
    except ValueError as exc:
        print(f"SIGTERM and SIGHUP stay unhandled: {exc}", file=sys.stderr)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


class Heartbeat:
    """Beat an execution's heartbeat_at every interval seconds on a daemon
    thread while the block runs (spec G D-G20: liveness is the process being
    alive, not a unit finishing). A beat that fails stops the thread with one
    line on stderr and never raises into the run; the reader then sees
    liveness unknown, which is the truth."""

    def __init__(self, store: BuildRecordStore, record_id: str, run_id: str,
                 interval: float | None = None) -> None:
        self.store, self.record_id, self.run_id = store, record_id, run_id
        self.interval = HEARTBEAT_INTERVAL_SECONDS if interval is None else interval
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{run_id}", daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.store.heartbeat(self.record_id, self.run_id)
            except (RecordError, OSError) as exc:
                self.error = str(exc)
                print(f"heartbeat stopped: {exc}", file=sys.stderr)
                return

    def __enter__(self) -> Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join()


def live_run_refusal(store: BuildRecordStore, record_id: str, command: str) -> str | None:
    """Why a new run of command on the record is refused, or None (final review
    A1): while another execution of the same command is live, a second run
    (a --resume included) would pay again for every unit the first one still
    has to do. Named as publish names its refusal, with the expiry rule."""
    live = [ex for ex in store.live_executions(record_id) if ex["command"] == command]
    if not live:
        return None
    named = ", ".join(f"{ex['run_id']} ({ex['command']}, heartbeat {ex['heartbeat_at']})" for ex in live)
    return (f"record {record_id} has a live running execution: {named}; wait for it to end or stop it "
            f"(a killed run stops blocking {HEARTBEAT_EXPIRY_SECONDS} s after its last heartbeat)")


@dataclass(frozen=True)
class RecordChoice:
    """Which record a recording command works in, decided without writing
    (B79 item 10). record_id names an existing record to reuse; None means a
    record is still to be created under ref, as a descendant of
    parent_record_id when that is set. continues says why a descendant
    continues another record ("record X is published")."""

    ref: str
    base_build_id: str | None
    layer1_digest: str | None
    record_id: str | None = None
    parent_record_id: str | None = None
    continues: str | None = None

    @property
    def message(self) -> str | None:
        """What to say before the record is created, or None when nothing
        needs to be said."""
        if self.continues is None:
            return None
        if self.record_id is not None:
            return f"{self.continues}; continuing in descendant {self.record_id}"
        return f"{self.continues}; continuing as a new descendant"


def choose_record(store: BuildRecordStore, ref: str, base_build_id: str | None,
                  layer1_digest: str | None) -> RecordChoice:
    """Reuse an open record built on the same Layer 1; otherwise continue as a
    descendant (D-G20): a published record is frozen, and a record built on
    another layer1.json is another assembly. An open descendant already
    continuing that record is reused before a new one is made. Reads only:
    a command runs its refusals before create_chosen_record, so a refused run
    leaves no record and moves no alias (B79 item 10)."""
    existing = store.resolve(ref)
    if existing is None:
        return RecordChoice(ref, base_build_id, layer1_digest)
    record = store.read(existing)
    same_layer1 = record["layer1_digest"] in (None, layer1_digest)
    if record["publication"] is None and same_layer1:
        return RecordChoice(ref, base_build_id, layer1_digest, record_id=existing)
    why = "is published" if record["publication"] is not None else "was built on another Layer 1"
    continues = f"record {existing} {why}"
    # An open descendant of that record under the same alias and Layer 1
    # already continues it (an earlier attempt): reuse it, so a resume finds
    # the run ids its checkpoint names and no attempt leaves an orphan.
    for candidate in store._valid_records_newest_first():
        if (candidate["parent_record_id"] == existing and ref in candidate["aliases"]
                and candidate["publication"] is None and candidate["layer1_digest"] in (None, layer1_digest)):
            return RecordChoice(ref, base_build_id, layer1_digest, record_id=candidate["record_id"],
                                parent_record_id=existing, continues=continues)
    return RecordChoice(ref, base_build_id, layer1_digest, parent_record_id=existing, continues=continues)


def create_chosen_record(store: BuildRecordStore, choice: RecordChoice) -> tuple[str, str | None]:
    """The record id of the choice, creating the record when the choice names
    none, and the message to print (None when nothing needs to be said)."""
    if choice.record_id is not None:
        return choice.record_id, choice.message
    record_id = store.create_record(choice.ref, choice.base_build_id, choice.layer1_digest,
                                    parent_record_id=choice.parent_record_id)
    message = f"{choice.continues}; continuing as descendant {record_id}" if choice.continues else None
    return record_id, message


def select_record(store: BuildRecordStore, ref: str, base_build_id: str | None,
                  layer1_digest: str | None) -> tuple[str, str | None]:
    """choose_record then create_chosen_record in one call, for a command
    with no refusal between the two (publish_layer23 runs its own before it
    selects). Returns the record id and a message to print, or None when
    nothing needs to be said."""
    return create_chosen_record(store, choose_record(store, ref, base_build_id, layer1_digest))


def existing_artefact_digest(path: Path) -> str | None:
    """The digest of an existing non-empty file, else None. An empty file is
    the zero-cost writability probe a command leaves behind, not an artefact."""
    from tere4ai.graph_store.build_chain import sha256_of_file

    if not path.is_file() or path.stat().st_size == 0:
        return None
    return sha256_of_file(path)


def published_artefact_owner(store: BuildRecordStore, dump_dir: Path | str, digest: str) -> str | None:
    """Who publishes the artefact with this digest: an output of a frozen
    (published) record, or an input a publications/*.json names. None when
    no published build names it."""
    for record in store.list_records():
        if record.get("unreadable") or record.get("publication") is None:
            continue
        for ex in record["executions"]:
            if any(o.get("sha256") == digest for o in ex.get("outputs", [])):
                return f"an output of record {record['record_id']}, published as chain {record['publication']['chain_id']}"
    for path in sorted((Path(dump_dir) / "publications").glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(manifest, dict) and any(isinstance(i, dict) and i.get("sha256") == digest
                                              for i in manifest.get("inputs") or []):
            return f"an input of publication {manifest.get('chain_id') or path.stem}"
    return None


def relative_to_dump_dir(path: Path, dump_dir: Path) -> str:
    """Path relative to dump_dir when it lies under it, else the absolute path.
    Both are resolved first, so a relative --out beside an absolute
    --dump-dir (or the reverse) is compared as the same file system place.
    The presenter later resolves dump_dir / this value."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path(dump_dir).resolve()))
    except ValueError:
        return str(resolved)


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

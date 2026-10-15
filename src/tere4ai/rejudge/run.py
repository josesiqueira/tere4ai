"""The execution lifecycle every rejudge subcommand shares: the refusals before a
record is written, and the end of an execution that stops.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

The rules are those extract_norms and align_hleg follow (B173 R12; those
commands are not changed by this card): nothing in a published build is
edited in place (exit 1); a run never starts beside a live rejudge run of
either subcommand on the same record (exit 2; final review: the cost stop
sums the record's executions, which two live runs would each read without
the other's spend) or over a checkpoint it cannot inherit (exit 2); a
stopped execution always ends failed with its usage, and the command that
continues it is printed: exit 3 when the inference backend stayed
unavailable (spec F D-F30), 4 on a configuration error (spec F D-F29), 5 at
the cost stop (R10); a refusal of the inference backend and an interrupt
print it too and are raised again; any other exception ends it failed and
is raised again (B79 item 22).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from tere4ai.extract_norms.model_clients import (
    USAGE_KEYS,
    InferenceBackendRefused,
    InferenceBackendUnavailable,
)
from tere4ai.graph_store.build_record import (
    HEARTBEAT_EXPIRY_SECONDS,
    BuildRecordStore,
    RecordChoice,
    RecordError,
    choose_record,
    existing_artefact_digest,
    published_artefact_owner,
)
from tere4ai.graph_store.checkpoints import (
    CheckpointError,
    ResumePlan,
    prepare_resume,
    resume_command,
)
from tere4ai.judge.config import ModelConfigError
from tere4ai.rejudge.cost import CostStop

PROGRAM = ".venv/bin/python -m tere4ai.rejudge"
COMMAND_PREFIX = "rejudge_"
T = TypeVar("T")


class Refusal(Exception):
    """A run refused before any record is written: the exit code and the line
    printed on stderr."""

    def __init__(self, code: int, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def refuse(message: str, code: int = 2) -> Refusal:
    """A refusal to start, worded as every rejudge refusal is."""
    return Refusal(code, f"refusing to start: {message}")


def effort_of(client: object) -> str:
    """The effort the client applied (B84, spec F D-F22); "unknown" for a stub without the record."""
    return str(getattr(client, "effort", "unknown"))


def usage_of(client: object | None) -> dict:
    """Token counts the inference backend reported over this run; empty for a stub."""
    return dict(getattr(client, "usage", None) or {})


def zero_usage() -> dict[str, int]:
    """The usage of a model component that made no call (R5: no generator at Layer 2)."""
    return dict.fromkeys(USAGE_KEYS, 0)


def choose_output_record(store: BuildRecordStore, out_dir: Path, out_path: Path, *, alias: str,
                         base_build_id: str | None, layer1_digest: str) -> RecordChoice:
    """The record the run will write, chosen without writing it (B79 item 10),
    after the refusals of the output and the record: out_path names a published
    artefact (exit 1), a live rejudge execution of either subcommand runs on
    the record (exit 2, live_rejudge_refusal),
    the record continues a published one and out_path already holds a file
    (exit 1). Touches out_path once no live run refuses the record, the
    zero-cost writability probe of extract_norms. Raises Refusal."""
    existing = existing_artefact_digest(out_path)
    owner = published_artefact_owner(store, out_dir, existing) if existing else None
    if owner:
        raise Refusal(1, f"refusing to overwrite {out_path.name}: it is {owner}; choose another --name")
    choice = choose_record(store, alias, base_build_id, layer1_digest)
    live = live_rejudge_refusal(store, choice.record_id) if choice.record_id else None
    if live:
        raise refuse(live)
    out_path.touch()
    if choice.message and existing:
        raise Refusal(1, f"refusing to overwrite {out_path.name}: {choice.message}, and the file belongs to the "
                         "record it continues; choose another --name")
    return choice


def live_rejudge_refusal(store: BuildRecordStore, record_id: str) -> str | None:
    """Why a rejudge run on the record is refused, or None: an execution of
    either rejudge subcommand is live on it (final review: an `alignments` run
    beside a live `norms` run would read a norms file still being made, and
    each run's cost stop would miss the other's spend). Worded as
    build_record.live_run_refusal words its refusal, which stays per command
    for the sibling commands."""
    live = [ex for ex in store.live_executions(record_id) if str(ex.get("command")).startswith(COMMAND_PREFIX)]
    if not live:
        return None
    named = ", ".join(f"{ex['run_id']} ({ex['command']}, heartbeat {ex['heartbeat_at']})" for ex in live)
    return (f"record {record_id} has a live running execution: {named}; wait for it to end or stop it "
            f"(a killed run stops blocking {HEARTBEAT_EXPIRY_SECONDS} s after its last heartbeat)")


def plan_resume(checkpoint_path: Path, key_field: str, result_keys: tuple[str, ...], *, resume: bool,
                store: BuildRecordStore, choice: RecordChoice, config: dict[str, Any],
                inputs: list[dict[str, Any]], models: dict[str, Any], prompts: dict[str, Any]) -> ResumePlan:
    """prepare_resume for the chosen record, a refused checkpoint raised as a
    Refusal (exit 2); lines without a run id are never inherited."""
    try:
        plan = prepare_resume(checkpoint_path, key_field, result_keys, resume=resume, accept_legacy=False,
                              store=store, record_id=choice.record_id, expected_config=config,
                              expected_inputs=inputs, expected_models=models, expected_prompt_sha256=prompts)
    except CheckpointError as exc:
        raise refuse(str(exc)) from None
    if plan.inherited_keys:
        print(f"resume: {len(plan.inherited_keys)} {key_field}(s) inherited from {plan.inherited_from}")
    return plan


@dataclass
class Execution:
    """A started execution and what its end needs: the usage and sampling so
    far (read when it ends), the work keys completed by this run, the
    checkpoint and the arguments a resume repeats."""

    store: BuildRecordStore
    record_id: str
    run_id: str
    checkpoint_path: Path
    run_argv: list[str]
    expected_total: int
    inherited: int
    work_unit: str
    usage: Callable[[], dict]
    sampling: Callable[[], dict]
    completed: list[str] = field(default_factory=list)

    def end_failed(self, error: str) -> None:
        """End the execution failed with its usage; a record that refuses the
        write is said on stderr and the original error stays the one reported
        (B79 item 15)."""
        try:
            self.store.finish_execution(self.record_id, self.run_id, status="failed", usage=self.usage(),
                                        completed_keys=self.completed, sampling=self.sampling(), error=error)
        except RecordError as record_exc:
            print(f"the failure could not be recorded: {record_exc}", file=sys.stderr)

    def print_resume(self, note: str = "") -> None:
        print(f"the checkpoint {self.checkpoint_path.name} is kept ({self.inherited + len(self.completed)} of "
              f"{self.expected_total} {self.work_unit} done); continue with{note}:", file=sys.stderr)
        print(f"  {resume_command(PROGRAM, self.run_argv)}", file=sys.stderr)

    def run(self, work: Callable[[], T]) -> tuple[int, T | None]:
        """(0, work()) when the work ends; otherwise the execution ends failed
        and the exit code comes back: 5 at the cost stop and 3 when the
        inference backend stayed unavailable, each with the resume command; 4
        on a configuration error. A refusal of the inference backend and an
        interrupt (SIGTERM and SIGHUP included, signals_as_interrupt) print
        the resume command too and are raised again; any other exception is
        raised again after the execution is ended."""
        try:
            return 0, work()
        except CostStop as exc:
            self.end_failed(str(exc))
            print(f"stopped: {exc}", file=sys.stderr)
            self.print_resume(" (raise --cost-stop to go on)")
            return 5, None
        except InferenceBackendUnavailable as exc:
            self.end_failed(str(exc))
            print(f"stopped: {exc}", file=sys.stderr)
            self.print_resume()
            return 3, None
        except (InferenceBackendRefused, KeyboardInterrupt) as exc:
            # a request no retry fixes, or the operator's stop: the groups or
            # batches done are in the checkpoint, so the run can continue
            self.end_failed(f"{type(exc).__name__}: {exc}")
            print(f"stopped: {exc or type(exc).__name__}", file=sys.stderr)
            self.print_resume()
            raise
        except ModelConfigError as exc:
            # a declared parameter the inference backend refused, or a price row missing
            self.end_failed(str(exc))
            print(f"stopped: {exc}", file=sys.stderr)
            return 4, None
        except BaseException as exc:  # an interrupt too: the execution never stays running
            self.end_failed(f"{type(exc).__name__}: {exc}")
            raise

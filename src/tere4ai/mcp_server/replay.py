"""Replay window for the paid MCP tools: an identical call is not paid twice.

@grounded_by: REF-31

An engineering MUST against architecture.md Section 8 (paid tools reach
external model APIs) and Section 13 (no silent degradation), like
keys.py; it implements no DEC of its own, so it carries no @implements
tag. Why (C3 ruling R3): the 2026-07-28 MCP revision removed SSE redelivery,
so a client whose stream drops sends the same request again, and each of
the four paid tools (evaluate_project_evidence,
evaluate_project_evidence_batch, generate_control_backlog,
elicit_features) would pay its model calls twice. Failure mechanics are
the coordinator's to decide; this module is that decision.

The key of a call is the SHA-256 of canonical JSON (sorted keys) holding
the caller, the tool name, the tool's arguments, the served build id and
the model parameters hash (load_model_config's public dict,
model_parameters_sha256). The caller is the key id of the t4a_ key the
ScopedKeyMiddleware verified for this call (keys.py sets CALLER), else
"local" (stdio without a key). The raw key never enters the hash input or
a log line; the arguments enter only the hash.

Which answers are kept (the exact rule). The guard wraps only the model
part of a tool: server.py calls ReplayStore.run after the dump was read,
the arguments were checked and the paid clients were built. So a refusal
before the model call (an invalid argument, empty content, an unknown
norm, a missing dump, a model configuration error) never reaches the
store and costs nothing. Of what run computes, an answer is kept only
when is_kept_answer holds: the envelope's answer is an object (an
elicitation that failed has none), it is not a refusal (answer.refused is
true on every degraded envelope of evidence.py and backlog.py), the
envelope's judge_verdict is neither "not_run" (no judged answer exists)
nor "judge_error" (the judge request raised), and, for the batch, no
per-norm result is refused or has one of those two verdicts. An exception
(a provider failure after the client's retries) is never kept; it reaches
the caller unchanged. A judged answer is kept whatever the verdict
(accepted, rejected or needs_human_review, which is also what the runtime
judge records when its reply cannot be read): the models answered and
were paid.

A kept answer is held in process memory for the window
(TERE4AI_MCP_REPLAY_WINDOW_SECONDS, default 600; 0 keeps nothing). An
identical call inside the window gets a copy of it with one line appended
to legal_status_notes: "this answer repeats the answer to an identical
call made at <UTC time>; no new model call was made", the time being the
first call's completion in ISO 8601 to the second with a Z. An identical
call while the first is running waits for it and gets its answer the same
way; if the first fails, the waiting call makes its own model call, as a
retry after a failure does. The store holds at most 256 answers (the
oldest is dropped) and lives in one process: two replicas do not share it.

Threads: fastmcp 4.0.10 runs a synchronous tool in a worker thread
(anyio.to_thread.run_sync, which copies the context, so CALLER set by the
middleware is visible there), so the store uses a threading lock and a
threading Event per running call.
"""

from __future__ import annotations

import contextvars
import copy
import hashlib
import json
import logging
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

WINDOW_ENV = "TERE4AI_MCP_REPLAY_WINDOW_SECONDS"
DEFAULT_WINDOW_SECONDS = 600
MAX_ENTRIES = 256
LOCAL_CALLER = "local"
NOTE = (
    "this answer repeats the answer to an identical call made at {time}; "
    "no new model call was made"
)

# Verdicts an envelope carries when no judged answer exists (evidence.py
# JUDGE_NOT_RUN and JUDGE_ERROR, which backlog.py reuses).
_FAILED_VERDICTS = frozenset({"not_run", "judge_error"})

# The key id of the key ScopedKeyMiddleware verified for the current call;
# None without the middleware (stdio), read as "local".
CALLER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tere4ai_mcp_caller", default=None
)

_log = logging.getLogger("tere4ai.mcp_server")


def current_caller() -> str:
    return CALLER.get() or LOCAL_CALLER


def window_seconds() -> float:
    """The replay window from the environment; a value that is not a finite,
    non-negative number of seconds is refused by name."""
    raw = os.environ.get(WINDOW_ENV)
    if raw is None:
        return float(DEFAULT_WINDOW_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{WINDOW_ENV} must be a non-negative number of seconds; got {raw!r}"
        )
    return value


def replay_key(
    *,
    caller: str,
    tool: str,
    arguments: dict[str, Any],
    build: str,
    model_parameters_sha256: str,
) -> str:
    material = {
        "caller": caller,
        "tool": tool,
        "arguments": arguments,
        "build": build,
        "model_parameters_sha256": model_parameters_sha256,
    }
    canonical = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _failed(answer: Any, verdict: Any) -> bool:
    return verdict in _FAILED_VERDICTS or (
        isinstance(answer, dict) and answer.get("refused") is True
    )


def is_kept_answer(envelope: Any) -> bool:
    """True when the envelope is an answer the models produced (module docstring)."""
    if not isinstance(envelope, dict):
        return False
    answer = envelope.get("answer")
    if not isinstance(answer, dict) or _failed(answer, envelope.get("judge_verdict")):
        return False
    results = answer.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict) or _failed(
                result.get("answer"), result.get("judge_verdict")
            ):
                return False
    return True


def _utc_second(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class _Kept:
    envelope: dict[str, Any]
    completed: datetime


class ReplayStore:
    """The per-process store of kept answers and running calls.

    window_seconds None reads TERE4AI_MCP_REPLAY_WINDOW_SECONDS on every
    call. clock returns the current time (UTC); on_wait is called when a
    call starts waiting for an identical running one (tests use both).
    """

    def __init__(
        self,
        *,
        window_seconds: float | None = None,
        max_entries: int = MAX_ENTRIES,
        clock: Callable[[], datetime] | None = None,
        on_wait: Callable[[], None] | None = None,
    ) -> None:
        self._window = window_seconds
        self._max_entries = max_entries
        self._clock = clock or (lambda: datetime.now(UTC))
        self._on_wait = on_wait
        self._lock = threading.Lock()
        self._kept: OrderedDict[str, _Kept] = OrderedDict()
        self._running: dict[str, threading.Event] = {}

    def __len__(self) -> int:
        with self._lock:
            return len(self._kept)

    def clear(self) -> None:
        with self._lock:
            self._kept.clear()

    def _window_seconds(self) -> float:
        return window_seconds() if self._window is None else float(self._window)

    def _fresh(self, key: str, now: datetime, window: float) -> _Kept | None:
        kept = self._kept.get(key)
        if kept is None:
            return None
        if (now - kept.completed).total_seconds() < window:
            return kept
        del self._kept[key]
        return None

    def run(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        build: str,
        model_parameters_sha256: str,
        compute: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """compute() unless an identical call's answer is kept or running."""
        window = self._window_seconds()
        key = replay_key(
            caller=current_caller(),
            tool=tool,
            arguments=arguments,
            build=build,
            model_parameters_sha256=model_parameters_sha256,
        )
        while True:
            with self._lock:
                kept = self._fresh(key, self._clock(), window)
                if kept is not None:
                    return self._repeat(tool, kept)
                running = self._running.get(key)
                if running is None:
                    running = self._running[key] = threading.Event()
                    break
            if self._on_wait is not None:
                self._on_wait()
            running.wait()
        try:
            envelope = compute()
            if window > 0 and is_kept_answer(envelope):
                completed = self._clock()
                with self._lock:
                    self._kept[key] = _Kept(copy.deepcopy(envelope), completed)
                    self._kept.move_to_end(key)
                    while len(self._kept) > self._max_entries:
                        self._kept.popitem(last=False)
            return envelope
        finally:
            with self._lock:
                del self._running[key]
            running.set()

    @staticmethod
    def _repeat(tool: str, kept: _Kept) -> dict[str, Any]:
        envelope = copy.deepcopy(kept.envelope)
        notes = list(envelope.get("legal_status_notes") or [])
        notes.append(NOTE.format(time=_utc_second(kept.completed)))
        envelope["legal_status_notes"] = notes
        _log.info("%s: identical call inside the replay window; no new model call", tool)
        return envelope

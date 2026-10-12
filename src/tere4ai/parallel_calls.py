"""Model calls sent a few at a time, results kept in the source order (B164).

The paid terminal runs (extract_norms, align_hleg, scripts/run_ablations.py
and scripts/elicit_benchmark_features.py) run the items of each checkpointed
unit through run_in_flight. Each item's model calls are built from that item
alone and made one after the other, so the prompts are the ones a run with
one call at a time sends (spec F D-F30 as amended 2026-10-12). The rules,
for every max_in_flight:

- items start in their order; a new one starts only while fewer than
  max_in_flight run and fewer than 2 x max_in_flight are started and not yet
  handed on, so a call in a long pause holds the run at that point;
- on_result(index, result) runs in the calling thread, in index order, for
  every item that finished without an exception; the returned list holds the
  results in the items' order;
- an exception in an item stops the starting of new items; the items in
  flight are waited for and their results handed on; then the exception of
  the earliest failing item in the items' order is raised;
- a first interrupt (KeyboardInterrupt in the calling thread, which SIGTERM
  and SIGHUP become under signals_as_interrupt) also stops the starting,
  says so on standard error, waits for the items in flight, hands their
  results on and is raised; a second interrupt while waiting is raised at
  once, naming the calls left in flight, which are not counted.

max_in_flight 1 is the loop each runner had before B164: the items run in
the calling thread, one after the other, with no thread at all.

Each item runs on a daemon thread of its own, not on a
concurrent.futures.ThreadPoolExecutor: the executor's workers are joined when
the interpreter exits (Python 3.9 on), so after a second interrupt the
process could not end while a call waits out a pause of up to 600 s (ruling R1).
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_MAX_IN_FLIGHT = 8
MAX_IN_FLIGHT_CEILING = 16
_RANGE = f"an integer from 1 to {MAX_IN_FLIGHT_CEILING}"


def max_in_flight_value(text: str) -> int:
    """The argparse type of --max-in-flight: an integer from 1 to MAX_IN_FLIGHT_CEILING."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--max-in-flight must be {_RANGE}, got {text!r}") from None
    if not 1 <= value <= MAX_IN_FLIGHT_CEILING:
        raise argparse.ArgumentTypeError(f"--max-in-flight must be {_RANGE}, got {value}")
    return value


def add_max_in_flight_argument(parser: argparse.ArgumentParser) -> None:
    """The one setting every paid terminal run takes. The default is read when
    the parser is built, so the unit suite can pin it (tests/unit/conftest.py)."""
    default = DEFAULT_MAX_IN_FLIGHT
    parser.add_argument(
        "--max-in-flight", type=max_in_flight_value, default=default,
        help=f"model calls sent at once, 1 to {MAX_IN_FLIGHT_CEILING} (default {default}); "
             "1 sends them one at a time",
    )


def run_in_flight(items: Sequence[T], work: Callable[[T], R], *, max_in_flight: int,
                  on_result: Callable[[int, R], None] | None = None) -> list[R]:
    """[work(item) for item in items], with at most max_in_flight running at
    once and on_result called in the items' order (the module docstring has
    the rules)."""
    if (isinstance(max_in_flight, bool) or not isinstance(max_in_flight, int)
            or not 1 <= max_in_flight <= MAX_IN_FLIGHT_CEILING):
        raise ValueError(f"max_in_flight must be {_RANGE}, got {max_in_flight!r}")
    if max_in_flight == 1:
        results: list[R] = []
        for index, item in enumerate(items):
            result = work(item)
            results.append(result)
            if on_result is not None:
                on_result(index, result)
        return results
    return _run_on_threads(list(items), work, max_in_flight, on_result)


def _run_on_threads(items: list[Any], work: Callable[[Any], Any], limit: int,
                    on_result: Callable[[int, Any], None] | None) -> list[Any]:
    finished: queue.SimpleQueue[tuple[int, bool, Any]] = queue.SimpleQueue()
    waiting: dict[int, tuple[bool, Any]] = {}
    results: list[Any] = [None] * len(items)
    started = handed = running = 0
    stopped = False
    failure: tuple[int, BaseException] | None = None

    def run_one(index: int) -> None:
        try:
            finished.put((index, True, work(items[index])))
        except BaseException as exc:  # handed to the calling thread, which raises it
            finished.put((index, False, exc))

    def receive() -> None:
        nonlocal running, stopped
        index, ok, value = finished.get()
        running -= 1
        waiting[index] = (ok, value)
        if not ok:
            stopped = True

    def hand_on() -> None:
        nonlocal handed, failure
        while handed in waiting:
            index = handed
            ok, value = waiting.pop(index)
            handed += 1
            if ok:
                results[index] = value
                if on_result is not None:
                    on_result(index, value)
            elif failure is None:
                failure = (index, value)

    def wait_for_running() -> None:
        try:
            while running:
                receive()
        except KeyboardInterrupt as again:
            raise KeyboardInterrupt(
                f"{running} call(s) in flight were not waited for and are not counted") from again

    try:
        while True:
            while (not stopped and started < len(items) and running < limit
                   and started - handed < 2 * limit):
                threading.Thread(target=run_one, args=(started,), name=f"model-call-{started}",
                                 daemon=True).start()
                started += 1
                running += 1
            if running == 0:
                break
            receive()
            hand_on()
    except KeyboardInterrupt:
        stopped = True
        if running:
            print(f"interrupted: waiting for {running} model call(s) in flight to return; interrupt again "
                  "to stop at once (the calls then in flight are not counted)", file=sys.stderr, flush=True)
        wait_for_running()
        hand_on()
        raise
    except BaseException:
        stopped = True
        wait_for_running()
        raise
    if failure is not None:
        raise failure[1]
    return results

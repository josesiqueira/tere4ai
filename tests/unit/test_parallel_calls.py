"""B164 (spec F D-F30 as amended 2026-10-12): run_in_flight sends at most
max_in_flight items at once and hands every result on in the items' order;
the pieces several calls in flight share are made safe. Offline: the work
functions sleep or wait on events; no model, no network."""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import sys
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tere4ai import parallel_calls
from tere4ai.extract_norms.model_clients import (
    SERVICE_POLICY,
    FakeClient,
    OpenAIGenerator,
    _new_usage,
)
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.checkpoints import IncompatibleCheckpointError, prepare_resume
from tere4ai.judge import audit_log
from tere4ai.parallel_calls import run_in_flight


class _Probe:
    """Counts the items running at once and the threads they ran on."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = 0
        self.most = 0
        self.threads: set[str] = set()

    def enter(self):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
            self.threads.add(threading.current_thread().name)

    def leave(self):
        with self.lock:
            self.running -= 1


def _later_ones_first(probe, n, unit=0.002):
    """Work whose later items finish first: item i sleeps (n - i) units."""
    def work(index):
        probe.enter()
        time.sleep((n - index) * unit)
        probe.leave()
        return f"result-{index}"
    return work


def test_setting_1_runs_every_item_in_the_calling_thread_in_order():
    probe = _Probe()
    handed = []
    results = run_in_flight(list(range(5)), _later_ones_first(probe, 5), max_in_flight=1,
                            on_result=lambda i, r: handed.append((i, r)))
    assert results == [f"result-{i}" for i in range(5)]
    assert handed == [(i, f"result-{i}") for i in range(5)]
    assert probe.most == 1 and probe.threads == {threading.current_thread().name}


def test_eight_in_flight_return_and_hand_on_in_the_items_order():
    probe = _Probe()
    handed = []
    results = run_in_flight(list(range(20)), _later_ones_first(probe, 20), max_in_flight=8,
                            on_result=lambda i, r: handed.append(i))
    assert results == [f"result-{i}" for i in range(20)]
    assert handed == list(range(20))
    assert 1 < probe.most <= 8
    assert threading.current_thread().name not in probe.threads


def test_no_more_than_twice_the_setting_start_before_the_first_is_handed_on():
    """Review Focus 5: item 0 waits until item 3 has started; with 2 in flight, 2 x 2 = 4
    items may be started and not handed on, so item 4 starts only after item 0 is handed on."""
    release = threading.Event()
    lock = threading.Lock()
    started = []
    seen = []

    def work(index):
        with lock:
            started.append(index)
        if index == 0:
            assert release.wait(timeout=5), "item 3 never started"
            time.sleep(0.05)  # time for a fifth item to start, were it allowed to
            with lock:
                seen.append(max(started))
            return 0
        if index == 3:
            release.set()
        return index

    assert run_in_flight(list(range(8)), work, max_in_flight=2) == list(range(8))
    assert seen == [3]


def test_a_failure_stops_new_starts_hands_on_the_others_and_raises_the_earliest_items_error():
    started, handed = [], []
    lock = threading.Lock()

    def work(index):
        with lock:
            started.append(index)
        if index == 2:
            time.sleep(0.05)
            raise ValueError("item 2")
        if index == 3:
            raise ValueError("item 3")  # fails first in time
        time.sleep(0.01)
        return index

    with pytest.raises(ValueError, match="^item 2$"):
        run_in_flight(list(range(40)), work, max_in_flight=4, on_result=lambda i, r: handed.append(i))
    assert handed == sorted(handed) and 2 not in handed and 3 not in handed
    assert set(handed) == set(started) - {2, 3}
    assert len(started) <= 8


def test_an_error_in_on_result_waits_for_the_calls_in_flight_and_is_raised():
    probe = _Probe()

    def work(index):
        probe.enter()
        time.sleep(0.01)
        probe.leave()
        return index

    def on_result(index, result):
        if index == 0:
            raise OSError("checkpoint not writable")

    with pytest.raises(OSError, match="checkpoint not writable"):
        run_in_flight(list(range(10)), work, max_in_flight=4, on_result=on_result)
    assert probe.running == 0


def _interrupt_when_started(count, go, delays=(0.0,)):
    """A thread that waits until `count` items are running, sends SIGINT once per delay,
    then lets the items go; returns the thread and a `running` counter for the work."""
    lock = threading.Lock()
    state = {"n": 0}
    all_started = threading.Event()

    def entered():
        with lock:
            state["n"] += 1
            if state["n"] == count:
                all_started.set()

    def killer():
        all_started.wait(timeout=5)
        for delay in delays:
            time.sleep(delay)
            os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.2)
        go.set()

    return threading.Thread(target=killer, daemon=True), entered


def test_a_first_interrupt_waits_for_the_calls_in_flight_and_hands_them_on(capsys):
    handed = []
    go = threading.Event()
    killer, entered = _interrupt_when_started(4, go)

    def work(index):
        entered()
        go.wait(timeout=5)
        return index

    killer.start()
    try:
        with pytest.raises(KeyboardInterrupt):
            run_in_flight(list(range(20)), work, max_in_flight=4, on_result=lambda i, r: handed.append(i))
    finally:
        go.set()
        killer.join()
    assert handed == [0, 1, 2, 3]
    assert ("interrupted: waiting for 4 model call(s) in flight to return; interrupt again to stop at once "
            "(the calls then in flight are not counted)\n") in capsys.readouterr().err


def test_a_second_interrupt_stops_at_once_and_names_the_calls_left_in_flight():
    go = threading.Event()
    killer, entered = _interrupt_when_started(4, go, delays=(0.0, 0.1))

    def work(index):
        entered()
        go.wait(timeout=5)
        return index

    killer.start()
    try:
        with pytest.raises(KeyboardInterrupt,
                           match=r"^4 call\(s\) in flight were not waited for and are not counted$"):
            run_in_flight(list(range(8)), work, max_in_flight=4)
    finally:
        go.set()
        killer.join()


def test_an_interrupt_right_after_a_finished_item_is_dequeued_does_not_hang_the_wait(monkeypatch):
    """The window between the queue handing an item over and the caller noting it."""
    class Cutting(queue.SimpleQueue):
        cut = False

        def get(self, *args, **kwargs):
            item = super().get(*args, **kwargs)
            if not Cutting.cut:
                Cutting.cut = True
                raise KeyboardInterrupt
            return item

    monkeypatch.setattr(parallel_calls.queue, "SimpleQueue", Cutting)
    handed = []

    def work(index):
        time.sleep(0.02)
        return index

    with pytest.raises(KeyboardInterrupt):
        run_in_flight(list(range(8)), work, max_in_flight=4, on_result=lambda i, r: handed.append(i))
    assert handed and handed == list(range(len(handed)))


def test_an_interrupt_inside_on_result_hands_no_later_item_on():
    handed = []

    def on_result(index, result):
        handed.append(index)
        if index == 1:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_in_flight(list(range(8)), lambda i: (time.sleep(0.01), i)[1], max_in_flight=4, on_result=on_result)
    assert handed == [0, 1]


def test_an_interrupt_while_a_thread_is_starting_leaves_no_call_unaccounted(monkeypatch, capsys):
    """Final review F1: a real SIGINT lands inside Thread.start() of item 2 while the new
    thread's bootstrap is still delayed, so the thread is not yet alive. The pool may not
    return while that thread can still make its call: every call made is handed on."""
    ran, handed = [], []
    lock = threading.Lock()
    bootstrap = threading.Thread._bootstrap

    def slow_bootstrap(self):
        if self.name == "model-call-2":
            os.kill(os.getpid(), signal.SIGINT)  # the caller is now waiting inside start()
            time.sleep(0.3)
        bootstrap(self)

    monkeypatch.setattr(threading.Thread, "_bootstrap", slow_bootstrap)

    def work(index):
        with lock:
            ran.append(index)
        time.sleep(0.05)
        return index

    with pytest.raises(KeyboardInterrupt):
        run_in_flight(list(range(8)), work, max_in_flight=4, on_result=lambda i, r: handed.append(i))
    time.sleep(0.6)  # past the delayed bootstrap: a thread left behind would have run by now
    assert sorted(ran) == handed == [0, 1]
    assert "interrupted: waiting for 2 model call(s) in flight to return" in capsys.readouterr().err


def test_a_later_items_on_result_error_does_not_hide_an_earlier_items_failure():
    """Final review F3: item 0's call fails, item 1's checkpoint write fails; the earliest
    failure in the items' order is the one raised, as one at a time would raise it."""
    item_1_done = threading.Event()

    class Unavailable(Exception):
        pass

    def work(index):
        if index == 0:
            assert item_1_done.wait(timeout=5)
            raise Unavailable("inference backend unavailable after 6 attempts: HTTP 529")
        if index == 1:
            item_1_done.set()
        return index

    def on_result(index, result):
        if index == 1:
            raise OSError("checkpoint not writable")

    for limit in (1, 2, 8):
        item_1_done.clear()
        if limit == 1:
            item_1_done.set()
        with pytest.raises(Unavailable, match="HTTP 529"):
            run_in_flight(list(range(4)), work, max_in_flight=limit, on_result=on_result)


@pytest.mark.parametrize("limit", [1, 2, 8, 16])
def test_instant_work_over_more_than_twice_the_setting_items_is_never_cut_short(limit):
    """Every call can finish before the loop looks again; no item may be skipped. Setting 1
    runs the sequential branch of run_in_flight (R1), which has no thread loop; 2, 8 and 16
    run the thread loop."""
    items = list(range(40))
    for _ in range(200):
        handed = []
        results = run_in_flight(items, lambda i: i * 2, max_in_flight=limit, on_result=lambda i, r: handed.append(i))
        assert results == [i * 2 for i in items]
        assert handed == items


@pytest.mark.parametrize("limit", [2, 8])
def test_instant_work_with_a_failing_item_raises_the_earliest_error(limit):
    def work(index):
        if index in (7, 9):
            raise ValueError(f"item {index}")
        return index

    for _ in range(200):
        with pytest.raises(ValueError, match="^item 7$"):
            run_in_flight(list(range(40)), work, max_in_flight=limit)


@pytest.mark.parametrize("value", [0, 17, -1, True, 2.0, "8"])
def test_a_setting_outside_1_to_16_is_refused(value):
    with pytest.raises(ValueError, match="max_in_flight must be an integer from 1 to 16"):
        run_in_flight([1], lambda x: x, max_in_flight=value)


def _parser():
    parser = argparse.ArgumentParser()
    parallel_calls.add_max_in_flight_argument(parser)
    return parser


@pytest.mark.default_max_in_flight
def test_the_flag_defaults_to_eight_and_takes_1_to_16():
    assert parallel_calls.DEFAULT_MAX_IN_FLIGHT == 8 and parallel_calls.MAX_IN_FLIGHT_CEILING == 16
    assert _parser().parse_args([]).max_in_flight == 8
    assert _parser().parse_args(["--max-in-flight", "1"]).max_in_flight == 1
    assert _parser().parse_args(["--max-in-flight", "16"]).max_in_flight == 16
    for bad in ("0", "17", "eight"):
        with pytest.raises(SystemExit):
            _parser().parse_args(["--max-in-flight", bad])


def test_the_unit_suite_runs_the_commands_at_one_call_in_flight():
    """R9: tests/unit/conftest.py pins the default unless a test is marked."""
    assert _parser().parse_args([]).max_in_flight == 1


# ---- the pieces several calls in flight share (R10)

class _Status(Exception):
    status_code = 500


def _stub_generator():
    gen = OpenAIGenerator.__new__(OpenAIGenerator)
    gen.model = "stub-generator"
    gen.usage = _new_usage()
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2,
                              completion_tokens_details=SimpleNamespace(reasoning_tokens=1)))
    gen._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply)))
    return gen


def test_every_usage_count_is_written_under_the_clients_lock():
    gen = _stub_generator()
    lock = threading.Lock()

    class Guarded(dict):
        def __setitem__(self, key, value):
            assert lock.locked(), f"usage[{key!r}] written without the lock"
            super().__setitem__(key, value)

    gen._usage_lock = lock
    gen.usage = Guarded(_new_usage())
    failures = [_Status("overloaded")]
    reply = gen._client.chat.completions.create()

    def create(**kwargs):
        if failures:
            raise failures.pop()
        return reply

    gen._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    gen._retry_policy = SERVICE_POLICY
    gen._wait = lambda seconds: None
    assert gen.complete("s", "u") == "{}"
    assert (gen.usage["calls"], gen.usage["requests_sent"], gen.usage["requests_refused"],
            gen.usage["input_tokens"], gen.usage["reasoning_tokens"]) == (1, 2, 1, 3, 1)


def test_eight_threads_count_every_reply():
    gen = _stub_generator()
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=lambda: [gen.complete("s", "u") for _ in range(500)]) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(old)
    assert gen.usage == {"calls": 4000, "input_tokens": 12000, "output_tokens": 8000, "requests_sent": 4000,
                         "replies_with_usage": 4000, "requests_refused": 0,
                         "requests_rejected_before_processing": 0, "reasoning_tokens": 4000,
                         "replies_with_reasoning": 4000}


def test_an_alert_line_is_one_write(monkeypatch):
    writes = []
    monkeypatch.setattr(sys, "stderr", SimpleNamespace(write=writes.append, flush=lambda: None))
    gen = _stub_generator()
    gen._now = lambda: datetime(2026, 10, 12, tzinfo=UTC)
    gen._alert(_Status("overloaded"), 1, 6, 10.0)
    assert writes == ["ALERT 2026-10-12T00:00:00.000Z openai:stub-generator: HTTP 500: overloaded; "
                      "attempt 1 of 6 failed; next attempt in 10 s\n"]


def test_a_fake_clients_call_runs_under_its_lock():
    fake = FakeClient({"k": "reply"})
    lock = threading.Lock()

    class Guarded(list):
        def append(self, value):
            assert lock.locked(), "FakeClient recorded a call without its lock"
            super().append(value)

    fake._lock = lock
    fake.calls = Guarded()
    assert fake.complete("s", "k") == "reply" and fake.calls == [("s", "k")]


def test_an_audit_line_is_written_under_the_shared_lock(monkeypatch):
    written = []

    class Writer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, text):
            assert audit_log._APPEND_LOCK.locked(), "an audit line written without the lock"
            written.append(text)

    log_path = SimpleNamespace(parent=SimpleNamespace(mkdir=lambda **kw: None),
                               open=lambda mode, encoding: Writer())
    audit_log.append_event(log_path, {"verdict": "accepted", "rationale": "sk-abcdefghijkl"})
    assert [json.loads(line) for line in written] == [{"verdict": "accepted", "rationale": "[REDACTED]"}]


# ---- the resume rule (R8)

def _stopped_run(tmp_path, config):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "build-b", None)
    run = store.start_execution(rid, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[],
                                inputs=[], config=config, expected_total=1, work_unit="groups",
                                checkpoint_file="c.checkpoint.jsonl")
    store.finish_execution(rid, run, status="failed", error="inference backend unavailable after 6 attempts: HTTP 529")
    ckpt = tmp_path / "c.checkpoint.jsonl"
    ckpt.write_text(json.dumps({"run_id": run, "group": "eu-ai-act:article-9",
                                "result": {"norms": [], "judge_runs": [], "stats": {}}}) + "\n")
    return store, rid, ckpt


def _plan(store, rid, ckpt, config):
    return prepare_resume(ckpt, "group", ("norms", "judge_runs", "stats"), resume=True, accept_legacy=False,
                          store=store, record_id=rid, expected_config=config, expected_inputs=[])


def test_a_resume_may_change_the_calls_in_flight_and_nothing_else(tmp_path):
    """Review Focus 2."""
    nodes = ["eu-ai-act:article-9"]
    store, rid, ckpt = _stopped_run(tmp_path / "a", {"prompt_version": "v5", "nodes": nodes, "max_in_flight": 8})
    assert _plan(store, rid, ckpt, {"prompt_version": "v5", "nodes": nodes, "max_in_flight": 2}).inherited_keys == nodes
    with pytest.raises(IncompatibleCheckpointError, match="used a different config: prompt_version$"):
        _plan(store, rid, ckpt, {"prompt_version": "v4", "nodes": nodes, "max_in_flight": 8})
    # a run recorded before B164 carries no such key
    store, rid, ckpt = _stopped_run(tmp_path / "b", {"prompt_version": "v5", "nodes": nodes})
    assert _plan(store, rid, ckpt, {"prompt_version": "v5", "nodes": nodes, "max_in_flight": 8}).inherited_keys == nodes

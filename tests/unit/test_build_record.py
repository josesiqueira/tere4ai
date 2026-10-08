"""Build record store (D-G20): one record per assembly, one execution per attempt, frozen after publication."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tere4ai.graph_store import build_record
from tere4ai.graph_store.build_record import (
    HEARTBEAT_EXPIRY_SECONDS,
    SCHEMA_VERSION,
    BuildRecordStore,
    FrozenRecordError,
    Heartbeat,
    LiveExecutionError,
    RecordError,
    choose_record,
    create_chosen_record,
    gate_entries,
    liveness,
    relative_to_dump_dir,
    scrub_argv,
    select_record,
)


def _start(store, rid, **over):
    kw = dict(command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=["--nodes", "x"], inputs=[],
              config={"prompt_version": "v1"}, expected_total=3, work_unit="groups", checkpoint_file="norms_t.checkpoint.jsonl")
    kw.update(over)
    return store.start_execution(rid, **kw)


def test_create_record_indexes_alias_and_validates_on_read(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.b74", "build-3b753e5e9297", "abc")
    record = store.read(rid)
    assert record["schema_version"] == SCHEMA_VERSION and record["aliases"] == ["core.b74"]
    assert record["parent_record_id"] is None and record["executions"] == [] and record["publication"] is None
    assert store.resolve("core.b74") == rid and store.resolve(rid) == rid and store.resolve("nope") is None


def test_corrupted_alias_index_raises_instead_of_being_overwritten(tmp_path):
    store = BuildRecordStore(tmp_path)
    (tmp_path / "build_records" / "aliases.json").write_text("{", encoding="utf-8")
    with pytest.raises(RecordError):
        store.resolve("x")
    with pytest.raises(RecordError):
        store.create_record("x", None, None)
    assert (tmp_path / "build_records" / "aliases.json").read_text(encoding="utf-8") == "{"
    # B79 item 17: the index is read before the record is written, so no unaliased record file is left
    assert sorted(p.name for p in (tmp_path / "build_records").glob("*.json")) == ["aliases.json"]


def test_finish_execution_refuses_an_unknown_status_with_a_record_error(tmp_path):
    """B79 item 17: the same error class as the module's other guards."""
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", None, None)
    run = _start(store, rid)
    with pytest.raises(RecordError, match="status must be done or failed"):
        store.finish_execution(rid, run, status="x")
    assert store.read(rid)["executions"][0]["status"] == "running"


def test_descendant_takes_the_alias_and_parent_keeps_history(tmp_path):
    store = BuildRecordStore(tmp_path)
    parent = store.create_record("core", "b", "abc")
    child = store.create_record("core.reference", "b", "abc", parent_record_id=parent)
    assert store.read(child)["parent_record_id"] == parent
    again = store.create_record("core", "b", "abc", parent_record_id=parent)
    assert store.resolve("core") == again, "the index maps an alias to the newest record carrying it"
    assert store.read(parent)["aliases"] == ["core"], "the parent keeps its alias as history"


def test_execution_lifecycle_and_lookups(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    run = _start(store, rid, models={"generator_model": "g"}, prompt_sha256={"generator": "p", "judge": "q"})
    ex = store.read(rid)["executions"][0]
    assert ex["run_id"] == run and ex["status"] == "running" and ex["models"] == {"generator_model": "g"}
    assert ex["checkpoint_file"] == "norms_t.checkpoint.jsonl" and ex["inherited_keys"] == [] and ex["inherited_from"] is None
    store.heartbeat(rid, run)
    store.finish_execution(rid, run, status="done", counts={"candidates": 5}, completed_keys=["a", "b", "c"],
                           outputs=[{"role": "norms", "file": "norms_t.json", "sha256": "d" * 64}],
                           work_failures={"nodes_failed": 1, "norms_failed": 0})
    ex = store.read(rid)["executions"][0]
    assert ex["status"] == "done" and ex["ended_at"] and ex["work_failures"] == {"nodes_failed": 1, "norms_failed": 0}
    assert store.find_by_output_digest("d" * 64) == rid and store.find_by_output_digest("e" * 64) is None


def test_find_parse_record_matches_only_parse_outputs(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("parse-1", None, None)
    run = _start(store, rid, command="parse_legal_structure", covers_steps=["LAYER0_STEP1", "LAYER1_STEP1"], expected_total=None,
                 work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=[{"role": "layer1_dump", "file": "layer1.json", "sha256": "L" * 64}])
    other = store.create_record("x", None, "L" * 64)
    assert store.find_parse_record("L" * 64) == rid and store.find_parse_record("M" * 64) is None
    assert other != rid


def test_frozen_record_refuses_new_work_and_second_publication(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    store.set_publication(rid, {"chain_id": "7442562dce5c", "build_id": "b+chain-7442562dce5c", "published_at": "t",
                               "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                               "postload_gates": [], "manifests": []})
    assert store.is_frozen(rid)
    with pytest.raises(FrozenRecordError):
        _start(store, rid)
    with pytest.raises(FrozenRecordError):
        store.set_publication(rid, {"chain_id": "x"})


def test_failed_execution_keeps_error_and_partial_usage(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    run = _start(store, rid)
    store.finish_execution(rid, run, status="failed", error="usage limit reached", usage={"generator": {"calls": 3}})
    ex = store.read(rid)["executions"][0]
    assert ex["status"] == "failed" and ex["error"] == "usage limit reached" and ex["usage"] == {"generator": {"calls": 3}}


def test_invalid_file_is_reported_not_raised_in_list_and_raised_on_read(tmp_path):
    store = BuildRecordStore(tmp_path)
    store.create_record("t", "b", None)
    (tmp_path / "build_records" / "0000000b0000.json").write_text("{not json", encoding="utf-8")
    # no schema_version: the record falls through to the schema check, which names the fault
    (tmp_path / "build_records" / "00000005a0e0.json").write_text(json.dumps({"record_id": "x"}), encoding="utf-8")
    listed = {r["record_id"]: r for r in store.list_records()}
    assert listed["0000000b0000"]["unreadable"] and "JSON" in listed["0000000b0000"]["reason"]
    assert listed["00000005a0e0"]["unreadable"] and "is a required property" in listed["00000005a0e0"]["reason"]
    with pytest.raises(RecordError):
        store.read("00000005a0e0")
    assert not list((tmp_path / "build_records").glob("tmp*"))


def test_read_only_store_never_creates_or_writes(tmp_path):
    ro = BuildRecordStore(tmp_path / "nowhere", create=False)
    assert not (tmp_path / "nowhere").exists()
    assert ro.list_records() == [] and ro.resolve("x") is None
    with pytest.raises(RecordError):
        ro.create_record("x", None, None)


def test_concurrent_heartbeats_lose_no_update(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    runs = [_start(store, rid) for _ in range(4)]

    def beat(run):
        for _ in range(20):
            store.heartbeat(rid, run)

    threads = [threading.Thread(target=beat, args=(r,)) for r in runs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [e["run_id"] for e in store.read(rid)["executions"]] == runs


def test_scrub_argv_redacts_key_material():
    argv = ["--nodes", "a", "--api-key", "sk-live", "--token=abc", "--out", "x.json"]
    assert scrub_argv(argv) == ["--nodes", "a", "--api-key", "<redacted>", "--token=<redacted>", "--out", "x.json"]
    # B79 item 8: password, passwd, credential and auth flags too
    argv = ["--neo4j-password", "x", "--db-passwd=x", "--credential", "x", "--auth-header", "x", "--out", "y.json"]
    assert scrub_argv(argv) == ["--neo4j-password", "<redacted>", "--db-passwd=<redacted>", "--credential", "<redacted>",
                                "--auth-header", "<redacted>", "--out", "y.json"]


def test_liveness_unknown_after_expiry_never_failed():
    now = datetime.now(UTC)
    fresh = {"status": "running", "heartbeat_at": now.isoformat()}
    stale = {"status": "running", "heartbeat_at": (now - timedelta(seconds=HEARTBEAT_EXPIRY_SECONDS + 1)).isoformat()}
    assert liveness(fresh, now) == "live" and liveness(stale, now) == "unknown"
    assert liveness({"status": "running", "heartbeat_at": None}, now) == "unknown"
    assert liveness({"status": "done", "heartbeat_at": stale["heartbeat_at"]}, now) == "ended"


def test_add_alias_indexes_and_records(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("parse-20260919T100000", None, None)
    store.add_alias(rid, "layer1-abcdefabcdef")
    assert store.resolve("layer1-abcdefabcdef") == rid and store.read(rid)["aliases"] == ["parse-20260919T100000", "layer1-abcdefabcdef"]


def test_gate_entries_one_per_gate():
    entries = gate_entries(["PUBLICATION_GATE1 orphan legal node: x", "PUBLICATION_GATE1 plus 3 more orphans",
                            "PUBLICATION_GATE6 base act missing"],
                           ("PUBLICATION_GATE1", "PUBLICATION_GATE2", "PUBLICATION_GATE3", "PUBLICATION_GATE4",
                            "PUBLICATION_GATE5", "PUBLICATION_GATE6"), {"layer1_nodes": 2})
    by = {e["name"]: e for e in entries}
    assert by["PUBLICATION_GATE1"] == {"name": "PUBLICATION_GATE1", "ok": False,
                                       "detail": "PUBLICATION_GATE1 orphan legal node: x; PUBLICATION_GATE1 plus 3 more orphans"}
    assert by["PUBLICATION_GATE2"]["ok"] and by["PUBLICATION_GATE6"]["ok"] is False and len(entries) == 6
    assert gate_entries([], ("POSTLOAD_GATE1", "POSTLOAD_GATE2"), {"db_norms": 3})[-1]["detail"] == "db_norms=3"


def test_a_failure_string_with_an_old_gate_name_is_not_matched_to_a_gate():
    # Review Focus 1: a string that still starts with "G1 " belongs to no gate and would hide a failure
    entries = gate_entries(["G1 orphan legal node: x"], ("PUBLICATION_GATE1",), {})
    assert entries == [{"name": "PUBLICATION_GATE1", "ok": True, "detail": ""}]


def test_select_record_creates_reuses_or_continues_as_descendant(tmp_path):
    store = BuildRecordStore(tmp_path)

    # a new ref creates a record and prints nothing
    rid, message = select_record(store, "core", "build-b", "L" * 64)
    assert message is None and store.resolve("core") == rid
    assert store.read(rid)["layer1_digest"] == "L" * 64 and store.read(rid)["base_build_id"] == "build-b"

    # a compatible record (same digest, not published) is reused
    again, message = select_record(store, "core", "build-b", "L" * 64)
    assert again == rid and message is None

    # a record with no recorded layer1_digest yet is reused whatever digest this run has
    store2 = BuildRecordStore(tmp_path / "unset")
    open_rid = store2.create_record("open", "build-b", None)
    reused, message = select_record(store2, "open", "build-b", "K" * 64)
    assert reused == open_rid and message is None

    # a frozen record continues as a descendant, with the exact message text
    store.set_publication(rid, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                               "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                               "postload_gates": [], "manifests": []})
    child, message = select_record(store, "core", "build-b", "L" * 64)
    assert child != rid and store.read(child)["parent_record_id"] == rid
    assert message == f"record {rid} is published; continuing as descendant {child}"
    assert store.resolve("core") == child

    # a record built on another Layer 1 also continues as a descendant
    other_rid, _ = select_record(store, "other", "build-b", "M" * 64)
    grandchild, message = select_record(store, "other", "build-b", "N" * 64)
    assert grandchild != other_rid and store.read(grandchild)["parent_record_id"] == other_rid
    assert message == f"record {other_rid} was built on another Layer 1; continuing as descendant {grandchild}"


def test_relative_to_dump_dir_relative_under_and_absolute_outside(tmp_path):
    dump_dir = tmp_path / "dumps"
    dump_dir.mkdir()
    under = dump_dir / "norms_test.json"
    assert relative_to_dump_dir(under, dump_dir) == "norms_test.json"

    outside = tmp_path / "elsewhere" / "norms_test.json"
    assert relative_to_dump_dir(outside, dump_dir) == str(outside.resolve())


def test_relative_to_dump_dir_resolves_mixed_relative_and_absolute_paths(tmp_path, monkeypatch):
    dump_dir = tmp_path / "dumps"
    dump_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    assert relative_to_dump_dir(Path("dumps/norms_test.json"), dump_dir.resolve()) == "norms_test.json"
    assert relative_to_dump_dir(dump_dir.resolve() / "x.json", Path("dumps")) == "x.json"
    outside = relative_to_dump_dir(Path("elsewhere/norms_test.json"), dump_dir.resolve())
    assert outside == str((tmp_path / "elsewhere" / "norms_test.json").resolve()) and Path(outside).is_absolute()


def test_select_record_reuses_the_open_descendant_of_a_frozen_record(tmp_path):
    store = BuildRecordStore(tmp_path)
    parent = store.create_record("core", "build-b", "L" * 64)
    store.set_publication(parent, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                                   "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                                   "postload_gates": [], "manifests": []})
    child, message = select_record(store, parent, "build-b", "L" * 64)
    assert message == f"record {parent} is published; continuing as descendant {child}"
    again, message = select_record(store, parent, "build-b", "L" * 64)
    assert again == child and message == f"record {parent} is published; continuing in descendant {child}"
    assert [r["record_id"] for r in store.list_records() if r.get("parent_record_id") == parent] == [child]
    other, _ = select_record(store, parent, "build-b", "M" * 64)
    assert other != child, "a descendant on another Layer 1 is another assembly"


def test_choose_record_writes_nothing_and_create_chosen_record_makes_the_choice(tmp_path):
    """B79 item 10 (R29): the read-only decision and the create step that select_record composes."""
    store = BuildRecordStore(tmp_path)

    def files():
        return sorted(p.name for p in (tmp_path / "build_records").glob("*.json"))

    fresh = choose_record(store, "core", "build-b", "L" * 64)
    assert fresh.record_id is None and fresh.parent_record_id is None and fresh.message is None and files() == []
    rid, message = create_chosen_record(store, fresh)
    assert message is None and store.resolve("core") == rid and store.read(rid)["layer1_digest"] == "L" * 64
    assert choose_record(store, "core", "build-b", "L" * 64).record_id == rid
    store.set_publication(rid, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                                "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                                "postload_gates": [], "manifests": []})
    before = files()
    descendant = choose_record(store, "core", "build-b", "L" * 64)
    assert descendant.record_id is None and descendant.parent_record_id == rid
    assert descendant.message == f"record {rid} is published; continuing as a new descendant"
    assert files() == before and store.resolve("core") == rid, "nothing written, the alias not moved"
    child, message = create_chosen_record(store, descendant)
    assert message == f"record {rid} is published; continuing as descendant {child}"
    assert store.read(child)["parent_record_id"] == rid and store.resolve("core") == child


def test_list_records_skips_files_that_are_not_records(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    records = tmp_path / "build_records"
    (records / "tmpab_12xyz.json").write_text((records / f"{rid}.json").read_text(), encoding="utf-8")
    (records / "tmp0123456789.json").write_text("{partial", encoding="utf-8")
    (records / "notes.json").write_text("{}", encoding="utf-8")
    assert [r["record_id"] for r in store.list_records()] == [rid], "a temp file mid-write is never a record"


def test_the_heartbeat_thread_beats_while_the_work_runs_and_stops_after(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    run = _start(store, rid)
    first = store.read(rid)["executions"][0]["heartbeat_at"]
    with Heartbeat(store, rid, run, interval=0.05) as beat:
        time.sleep(0.3)
    during = store.read(rid)["executions"][0]["heartbeat_at"]
    assert during > first and beat.error is None
    time.sleep(0.2)
    assert store.read(rid)["executions"][0]["heartbeat_at"] == during, "no beat after the block"


def test_a_failing_beat_stops_the_thread_and_never_raises_into_the_run(tmp_path, capsys):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    with Heartbeat(store, rid, "no-such-run", interval=0.05) as beat:
        time.sleep(0.2)
    assert beat.error and "no-such-run" in beat.error
    assert "heartbeat stopped" in capsys.readouterr().err


PUB = {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
       "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
       "postload_gates": [], "manifests": []}


def test_publication_is_refused_while_another_execution_is_live(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    running = _start(store, rid)
    with pytest.raises(LiveExecutionError, match=running):
        store.set_publication(rid, PUB)
    assert store.read(rid)["publication"] is None


def test_the_publishing_execution_itself_never_blocks_its_publication(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    publish = _start(store, rid, command="publish_layer23", covers_steps=["PUBLICATION_STEP1", "PUBLICATION_STEP2"], expected_total=None,
                     work_unit=None, checkpoint_file=None)
    store.set_publication(rid, PUB, run_id=publish)
    store.finish_execution(rid, publish, status="done")
    assert store.read(rid)["executions"][0]["status"] == "done"


def test_a_second_live_publish_blocks_and_may_not_write_after_the_first_published(tmp_path):
    """Review fix C1: the exemption is the publishing run, not every execution covering PUBLICATION_STEP2."""
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    kw = dict(command="publish_layer23", covers_steps=["PUBLICATION_STEP1", "PUBLICATION_STEP2"], expected_total=None, work_unit=None,
              checkpoint_file=None)
    first, second = _start(store, rid, **kw), _start(store, rid, **kw)
    assert {ex["run_id"] for ex in store.live_executions(rid)} == {first, second}
    with pytest.raises(LiveExecutionError, match=second):
        store.set_publication(rid, PUB, run_id=first)
    store.finish_execution(rid, second, status="failed", error="stopped")
    store.set_publication(rid, PUB, run_id=first)
    with pytest.raises(FrozenRecordError, match=first):
        BuildRecordStore(tmp_path).finish_execution(rid, first, status="done")  # another store object
    store.finish_execution(rid, first, status="done")


def test_publication_proceeds_over_a_running_execution_whose_heartbeat_expired(tmp_path, monkeypatch):
    """A killed process leaves running forever; after the expiry it no longer blocks,
    and a late write from it is refused (Review Focus 4)."""
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    monkeypatch.setattr(build_record, "_now", lambda: "2026-01-01T00:00:00+00:00")
    stale = _start(store, rid)
    monkeypatch.undo()
    store.set_publication(rid, PUB)
    with pytest.raises(FrozenRecordError, match=stale):
        store.heartbeat(rid, stale)
    with pytest.raises(FrozenRecordError, match=stale):
        store.finish_execution(rid, stale, status="done", usage={"generator": {"calls": 9}})
    ex = store.read(rid)["executions"][0]
    assert ex["status"] == "running" and ex["usage"] is None, "nothing written to the frozen record"


def test_a_beat_right_after_the_publication_write_is_allowed_for_the_publisher(tmp_path, monkeypatch):
    """Final review F1: the publisher is remembered under the record lock, so a
    heartbeat that lands between the lock release and set_publication's
    return never reads the record as frozen against its own run."""
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    publish = _start(store, rid, command="publish_layer23", covers_steps=["PUBLICATION_STEP1", "PUBLICATION_STEP2"], expected_total=None,
                     work_unit=None, checkpoint_file=None)
    original = store._update
    beats: list[str] = []

    def update_then_beat(record_id, mutate):
        original(record_id, mutate)
        if not beats and store.read(record_id)["publication"] is not None:
            beats.append(publish)
            store.heartbeat(record_id, publish)  # the heartbeat thread, in the window

    monkeypatch.setattr(store, "_update", update_then_beat)
    store.set_publication(rid, PUB, run_id=publish)
    monkeypatch.undo()
    store.finish_execution(rid, publish, status="done")


def test_a_heartbeat_may_carry_the_usage_so_far_on_a_running_execution(tmp_path):
    """Final review A2 (b): a hard kill loses at most the unit in flight's usage."""
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    run = _start(store, rid)
    store.heartbeat(rid, run)
    assert store.read(rid)["executions"][0]["usage"] is None, "a plain beat writes no usage"
    spent = {"generator": {"calls": 1, "input_tokens": 10, "output_tokens": 5}, "judge": {}}
    store.heartbeat(rid, run, usage=spent)
    ex = store.read(rid)["executions"][0]
    assert ex["status"] == "running" and ex["usage"] == spent
    store.heartbeat(rid, run)
    assert store.read(rid)["executions"][0]["usage"] == spent, "a plain beat keeps the last usage"


def test_signals_as_interrupt_raises_keyboard_interrupt_and_restores_the_handlers():
    """Final review A2 (a): a SIGTERM or SIGHUP ends a command through its interrupt path."""
    import os
    import signal

    got: list[int] = []

    def guard(signum, frame):
        got.append(signum)

    before = {sig: signal.signal(sig, guard) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with pytest.raises(KeyboardInterrupt, match=signal.Signals(sig).name):
                with build_record.signals_as_interrupt():
                    os.kill(os.getpid(), sig)
                    time.sleep(1)
            assert signal.getsignal(sig) is guard, "the previous handler is back"
        assert got == []
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)


def test_a_signal_ignored_by_nohup_stays_ignored():
    """Re-review: a run started with nohup has SIGHUP at SIG_IGN; the context must
    not turn a closed terminal into an interrupt. SIGTERM at SIG_DFL is still replaced."""
    import signal

    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        with build_record.signals_as_interrupt():
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert callable(signal.getsignal(signal.SIGTERM))
            assert signal.getsignal(signal.SIGTERM) not in (signal.SIG_DFL, signal.SIG_IGN)
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)

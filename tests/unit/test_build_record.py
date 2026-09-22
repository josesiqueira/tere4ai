"""Build record store (D-G20): one record per assembly, one execution per attempt, frozen after publication."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from tere4ai.graph_store.build_record import (
    HEARTBEAT_EXPIRY_SECONDS,
    SCHEMA_VERSION,
    BuildRecordStore,
    FrozenRecordError,
    RecordError,
    liveness,
    scrub_argv,
)


def _start(store, rid, **over):
    kw = dict(command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=["--nodes", "x"], inputs=[],
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
    run = _start(store, rid, command="parse_legal_structure", covers_steps=["L0.1", "L1.1"], expected_total=None,
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
    (tmp_path / "build_records" / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "build_records" / "shape.json").write_text(json.dumps({"record_id": "shape"}), encoding="utf-8")
    listed = {r["record_id"]: r for r in store.list_records()}
    assert listed["broken"]["unreadable"] and "JSON" in listed["broken"]["reason"]
    assert listed["shape"]["unreadable"] and "is a required property" in listed["shape"]["reason"]
    with pytest.raises(RecordError):
        store.read("shape")
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


def test_liveness_unknown_after_expiry_never_failed():
    now = datetime.now(UTC)
    fresh = {"status": "running", "heartbeat_at": now.isoformat()}
    stale = {"status": "running", "heartbeat_at": (now - timedelta(seconds=HEARTBEAT_EXPIRY_SECONDS + 1)).isoformat()}
    assert liveness(fresh, now) == "live" and liveness(stale, now) == "unknown"
    assert liveness({"status": "running", "heartbeat_at": None}, now) == "unknown"
    assert liveness({"status": "done", "heartbeat_at": stale["heartbeat_at"]}, now) == "ended"

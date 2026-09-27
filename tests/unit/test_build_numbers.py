"""Build numbers (spec G D-G50, B94): given at publication under a numbering
lock, never reused, never changed, readable when the build records are lost."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    NumberingError,
    duplicate_build_numbers,
    numbered_files,
)

ROOT = Path(__file__).resolve().parents[2]
PUB = {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
       "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [], "postload_gates": [],
       "manifests": []}


def test_the_counter_absent_and_a_file_unreadable_is_refused_by_name(tmp_path):
    store = BuildRecordStore(tmp_path)
    assert store.next_build_number() == 1
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "abcabcabcabc.json").write_text("{not json")
    with pytest.raises(NumberingError, match=r"publications/abcabcabcabc\.json.*numbering\.json"):
        store.next_build_number()
    (store.dir / "numbering.json").write_text(json.dumps({"last_number": 4}))
    assert store.next_build_number() == 5


def test_a_temporary_file_is_not_a_manifest_and_a_binary_counter_reads_as_absent(tmp_path):
    store = BuildRecordStore(tmp_path)
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "tmpab12cd.json").write_text("{bad")
    (tmp_path / "build_chain_tmp.json").write_text("{bad")
    assert numbered_files(tmp_path) == ({}, [])
    assert store.next_build_number() == 1
    (store.dir / "numbering.json").write_bytes(b"\xff\xfe\x00garbage")
    assert store.next_build_number() == 1


def test_the_next_number_is_above_every_record_manifest_and_chain_record(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("a", "b", None)
    store.set_publication(rid, {**PUB, "build_number": 2})
    assert store.next_build_number() == 3
    (tmp_path / "build_chain_dddddddddddd.json").write_text(json.dumps({"chain_id": "d" * 12, "build_number": 7}))
    assert store.next_build_number() == 8
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "eeeeeeeeeeee.json").write_text(json.dumps({"chain_id": "e" * 12, "build_number": 9}))
    assert store.next_build_number() == 10


def test_a_number_held_by_another_record_is_refused(tmp_path):
    store = BuildRecordStore(tmp_path)
    a = store.create_record("a", "b", None)
    b = store.create_record("b", "b", None)
    store.set_publication(a, {**PUB, "build_number": 1})
    with pytest.raises(NumberingError, match="already held by record"):
        store.set_publication(b, {**PUB, "chain_id": "d" * 12, "build_number": 1})
    store.set_publication(b, {**PUB, "chain_id": "d" * 12})  # no number: accepted as before (R3)
    assert store.publisher_of("d" * 12)["record_id"] == b and store.publisher_of("f" * 12) is None


def test_the_counter_write_never_raises(tmp_path, monkeypatch):
    store = BuildRecordStore(tmp_path)
    assert store.record_build_number(3) is None
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 3}

    def refuse(path, payload):
        raise OSError("read-only file system")

    monkeypatch.setattr("tere4ai.graph_store.build_record.atomic_write_json", refuse)
    note = store.record_build_number(4)
    assert note is not None and "not written" in note


def _reserve(dump_dir: str, queue) -> None:
    store = BuildRecordStore(dump_dir)
    with store.reserve_build_number() as number:
        rid = store.create_record(f"r{number}", "b", None)
        store.set_publication(rid, {**PUB, "chain_id": f"{number:012d}", "build_number": number})
        store.record_build_number(number)
    queue.put(number)


def test_two_processes_get_two_consecutive_numbers(tmp_path):
    BuildRecordStore(tmp_path)
    ctx = multiprocessing.get_context("fork")  # explicit: Python 3.14 defaults Linux to forkserver
    queue = ctx.Queue()
    procs = [ctx.Process(target=_reserve, args=(str(tmp_path), queue)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    # a child that raised (a number issued twice) exits non-zero: named here,
    # not as a queue timeout
    assert [p.exitcode for p in procs] == [0, 0]
    assert sorted(queue.get(timeout=5) for _ in procs) == [1, 2]


def test_duplicates_in_one_directory_are_named(tmp_path):
    for chain in ("aaaaaaaaaaaa", "bbbbbbbbbbbb"):
        (tmp_path / f"build_chain_{chain}.json").write_text(json.dumps({"chain_id": chain, "build_number": 3}))
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "aaaaaaaaaaaa.json").write_text(json.dumps({"chain_id": "a" * 12, "build_number": 3}))
    assert duplicate_build_numbers(tmp_path) == ["Build 3 is carried by chains aaaaaaaaaaaa, bbbbbbbbbbbb"]


def test_the_committed_dump_directory_carries_no_number_twice():
    # Spec G D-G50 (review M7, R8): a manifest committed from a second
    # checkout that collides with this checkout's numbers fails here.
    dump_dir = ROOT / "data" / "graph_dumps"
    _, unreadable = numbered_files(dump_dir)
    assert not unreadable, unreadable
    assert duplicate_build_numbers(dump_dir) == []

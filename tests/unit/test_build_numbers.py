"""Build numbers (spec G D-G50, B94): given at publication under a numbering
lock, never reused, never changed, readable when the build records are lost."""

from __future__ import annotations

import json
import multiprocessing
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.test_publish_layer23 import _fakes, _files, _publish

from tere4ai.graph_store.build_chain import build_chain, sha256_of_file
from tere4ai.graph_store.build_record import (
    BuildRecordStore,
    LiveExecutionError,
    NumberingError,
    duplicate_build_numbers,
    numbered_files,
)
from tere4ai.graph_store.present import present_record, summary_of, synthesise_legacy_records

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


def test_a_record_published_before_numbers_presents_null_with_its_reason(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("old", "b", None)
    store.set_publication(rid, PUB)
    presented = present_record(store.read(rid), tmp_path, datetime.now(UTC), None, store)
    assert presented["publication"]["build_number"] is None
    assert presented["reasons"]["publication.build_number"] == "published before build numbers (B94)"
    assert (presented["manifest_present"], presented["provenance"]["manifest_present"]) == (False, "derived")
    row = summary_of(presented)
    assert row["publication"]["build_number"] is None and row["publication"]["build_id"] == PUB["build_id"]
    assert row["manifest_present"] is False
    assert "build_number" not in store.read(rid)["publication"]  # the stored file is never rewritten


def test_a_numbered_record_presents_its_number_on_the_list_row(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("new", "b", None)
    store.set_publication(rid, {**PUB, "build_number": 4})
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / f"{'c' * 12}.json").write_text("{}")
    presented = present_record(store.read(rid), tmp_path, datetime.now(UTC), "c" * 12, store)
    assert "publication.build_number" not in presented["reasons"]
    row = summary_of(presented)
    assert row["publication"] == {"chain_id": "c" * 12, "build_id": PUB["build_id"], "build_number": 4,
                                  "label": "llm-gated", "published_at": "t"}
    assert (row["served"], row["manifest_present"]) == (True, True)


def test_a_legacy_row_takes_the_number_of_the_chain_it_matches(tmp_path):
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    norms = tmp_path / "norms_core.json"
    norms.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": []}))
    chain = build_chain(layer1, norms)
    (tmp_path / f"build_chain_{chain['chain_id']}.json").write_text(json.dumps({**chain, "build_number": 6}))
    legacy = synthesise_legacy_records(tmp_path)
    assert [r["publication"]["build_number"] for r in legacy] == [6]
    (tmp_path / f"build_chain_{chain['chain_id']}.json").write_text(json.dumps(chain))
    presented = present_record(synthesise_legacy_records(tmp_path)[0], tmp_path, datetime.now(UTC), None, None)
    assert presented["publication"]["build_number"] is None
    assert presented["reasons"]["publication.build_number"] == "published before build numbers (B94)"


def _publish_once(tmp_path, monkeypatch, variant: str):
    """One LLM-gated publication: the norms file differs per variant, so
    each call is a new chain and a new record in the same dump dir."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    payload = json.loads(norms.read_text())
    payload["variant"] = variant
    norms.write_text(json.dumps(payload))
    run = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[],
                                config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done",
                           outputs=[{"role": "norms", "file": norms.name, "sha256": sha256_of_file(norms)}])
    align = json.loads(alignments.read_text())
    align["build"]["alignment_input_sha256"] = sha256_of_file(norms)
    alignments.write_text(json.dumps(align))
    _fakes(monkeypatch, cli)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                   "--dump-dir", str(tmp_path)])
    return rc, store, rid


def test_publications_are_numbered_one_two_in_order_and_everywhere(tmp_path, monkeypatch, capsys):
    rc1, store, rid1 = _publish_once(tmp_path, monkeypatch, "one")
    rc2, _, rid2 = _publish_once(tmp_path, monkeypatch, "two")
    assert (rc1, rc2) == (0, 0)
    first, second = store.read(rid1)["publication"], store.read(rid2)["publication"]
    assert (first["build_number"], second["build_number"]) == (1, 2)
    assert first["published_at"] < second["published_at"]
    chain = json.loads((tmp_path / f"build_chain_{second['chain_id']}.json").read_text())
    manifest = json.loads((tmp_path / "publications" / f"{second['chain_id']}.json").read_text())
    assert chain["build_number"] == manifest["build_number"] == 2
    assert json.loads((tmp_path / "build_records" / "numbering.json").read_text()) == {"last_number": 2}
    row = summary_of(present_record(store.read(rid2), tmp_path, datetime.now(UTC), None, store))
    assert (row["publication"]["build_number"], row["manifest_present"]) == (2, True)
    assert f"published Build 2: {second['build_id']}, record {rid2}" in capsys.readouterr().out


def test_a_refused_publication_uses_no_number(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli, postload_ok=False)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                     "--dump-dir", str(tmp_path)]) == 1
    assert store.next_build_number() == 1
    _fakes(monkeypatch, cli)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                     "--dump-dir", str(tmp_path)]) == 0
    assert store.read(rid)["publication"]["build_number"] == 1


def test_a_refusal_after_the_reservation_uses_no_number(tmp_path, monkeypatch):
    # review I4: set_publication refused after the chain record is written
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    argv = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    real = BuildRecordStore.set_publication

    def refuse(self, record_id, publication, *, run_id=None):
        raise LiveExecutionError("an execution became live")

    monkeypatch.setattr(BuildRecordStore, "set_publication", refuse)
    with pytest.raises(LiveExecutionError):
        cli.main(argv)
    assert not list(tmp_path.glob("build_chain_*.json"))
    assert store.next_build_number() == 1
    monkeypatch.setattr(BuildRecordStore, "set_publication", real)
    assert cli.main(argv) == 0
    assert store.read(rid)["publication"]["build_number"] == 1


def test_a_numbering_refusal_leaves_the_published_record_and_its_alias(tmp_path, monkeypatch, capsys):
    # review I1: refused before select_record, so no descendant and no alias move
    rc, store, rid = _publish_once(tmp_path, monkeypatch, "one")
    assert rc == 0 and store.resolve("core") == rid
    (store.dir / "numbering.json").unlink()
    (tmp_path / "publications" / "ffffffffffff.json").write_text("{bad")
    cli = _publish()
    layer1, norms, alignments = tmp_path / "layer1.json", tmp_path / "norms_core.json", tmp_path / "alignments_core.json"
    align = json.loads(alignments.read_text())
    align["assertions"] = [{"changed": True}]
    alignments.write_text(json.dumps(align))
    _fakes(monkeypatch, cli)
    records_before = sorted(r["record_id"] for r in store.list_records())
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                     "--dump-dir", str(tmp_path)]) == 1
    assert "publications/ffffffffffff.json" in capsys.readouterr().err
    assert store.resolve("core") == rid
    assert sorted(r["record_id"] for r in store.list_records()) == records_before


def test_a_failed_manifest_write_keeps_the_number_and_never_offers_removing_the_chain(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    argv = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    real = cli.atomic_write_json

    def failing(path, payload):
        if Path(path).parent.name == "publications":
            raise OSError("disk full")
        real(path, payload)

    monkeypatch.setattr(cli, "atomic_write_json", failing)
    with pytest.raises(OSError):
        cli.main(argv)
    record = store.read(rid)
    assert record["publication"]["build_number"] == 1
    error = record["executions"][-1]["error"]
    assert "is published as Build 1" in error and "never remove the chain record" in error and "clean up by hand" not in error
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 1}
    assert not list((tmp_path / "publications").glob("*.json"))
    row = summary_of(present_record(record, tmp_path, datetime.now(UTC), None, store))
    assert (row["publication"]["build_number"], row["manifest_present"]) == (1, False)
    # review I2: the chain record removed anyway, the same inputs are refused
    monkeypatch.setattr(cli, "atomic_write_json", real)
    next(tmp_path.glob("build_chain_*.json")).unlink()
    assert cli.main(argv) == 1
    assert [r["publication"]["build_number"] for r in store.list_records() if r.get("publication")] == [1]


def test_lost_build_records_never_lower_the_next_number_and_legacy_rows_keep_theirs(tmp_path, monkeypatch):
    _publish_once(tmp_path, monkeypatch, "one")
    _publish_once(tmp_path, monkeypatch, "two")
    shutil.rmtree(tmp_path / "build_records")
    assert BuildRecordStore(tmp_path).next_build_number() == 3
    legacy = synthesise_legacy_records(tmp_path)
    numbers = [r["publication"]["build_number"] for r in legacy if r.get("publication")]
    assert numbers == [2]  # the chain whose inputs are the artefacts present now


def test_activate_prints_the_number_beside_the_full_id(tmp_path, monkeypatch, capsys):
    import importlib.util
    _publish_once(tmp_path, monkeypatch, "one")
    chain_id = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())["chain_id"]
    spec = importlib.util.spec_from_file_location("activate_b94", ROOT / "scripts" / "activate_build.py")
    activate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(activate)
    capsys.readouterr()
    assert activate.main([chain_id, "--dump-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("activated Build 1 (build-b+chain-") and out.rstrip().endswith("; restart the facade to serve it")


def test_one_chain_carrying_two_numbers_is_named(tmp_path):
    # final review B-P3-1: a chain record and its own manifest that disagree
    # give one chain two numbers, which the R8 test must fail on
    (tmp_path / "build_chain_aaaaaaaaaaaa.json").write_text(json.dumps({"chain_id": "a" * 12, "build_number": 2}))
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "aaaaaaaaaaaa.json").write_text(json.dumps({"chain_id": "a" * 12, "build_number": 1}))
    assert duplicate_build_numbers(tmp_path) == ["chain aaaaaaaaaaaa carries Builds 1, 2"]


def test_a_malformed_counter_is_called_absent_or_unreadable(tmp_path):
    # final review B-P3-2: the file is on disk, so "absent" alone misleads
    store = BuildRecordStore(tmp_path)
    (store.dir / "numbering.json").write_text(json.dumps({"last_number": "7"}))
    (tmp_path / "build_chain_bbbbbbbbbbbb.json").write_text("{bad")
    with pytest.raises(NumberingError, match=r"numbering\.json is absent or unreadable and these files"):
        store.next_build_number()


def test_an_unreadable_build_record_with_no_counter_is_refused_by_name(tmp_path):
    # final review A-M6: the branch the B74 re-run relies on when a record
    # file is damaged and the counter is lost with it
    store = BuildRecordStore(tmp_path)
    (store.dir / "abcdefabcdef.json").write_text("{bad")
    with pytest.raises(NumberingError, match=r"build_records/abcdefabcdef\.json"):
        store.next_build_number()
    (store.dir / "numbering.json").write_text(json.dumps({"last_number": 3}))
    assert store.next_build_number() == 4


def test_the_counter_never_goes_down(tmp_path):
    # final review A-M8: a lower number written after a higher one keeps the higher
    store = BuildRecordStore(tmp_path)
    assert store.record_build_number(5) is None
    assert store.record_build_number(3) is None
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 5}

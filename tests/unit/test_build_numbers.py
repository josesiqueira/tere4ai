"""Build numbers (spec G D-G50, B94): given at publication under a numbering
lock, never reused, never changed, readable when the build records are lost."""

from __future__ import annotations

import json
import multiprocessing
import shutil
import sys
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
from tere4ai.graph_store.publication import read_target_state

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
    run = store.start_execution(rid, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[],
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


def test_a_failed_manifest_write_keeps_the_number_and_never_offers_removing_the_chain(tmp_path, monkeypatch, capsys):
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
    capsys.readouterr()
    assert cli.main(argv) == 1
    # final review A-M5, A-M4: the refusal is the one by record, never "activate it with"
    err = capsys.readouterr().err
    assert f"(Build 1) by record {rid}" in err and "activate it with" not in err
    assert "both its chain record and its publication manifest are missing" in err
    # re-review ruling 3: the message names steps the operator can run
    chain_id = record["publication"]["chain_id"]
    assert (f"restore both from git (they are tracked), then run scripts/write_publication_manifest.py {chain_id} "
            f"--dump-dir {tmp_path} --pointer if the manifest is still missing") in err
    assert "write them from the record" not in err
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


def _argv(tmp_path, layer1, norms, alignments):
    return ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]


def test_one_chain_published_from_two_records_at_once_gets_one_number(tmp_path, monkeypatch, capsys):
    # final review B-P2-1: A publishes the same inputs from another record
    # while B sits in its post-load gates; the checks repeated under the
    # numbering lock refuse B, so the chain keeps Build 1 everywhere
    from tests.unit.test_publish_layer23 import _Report

    layer1, norms, alignments, store, rid_x = _files(tmp_path)
    rid_y = store.create_record("other", "build-b", None)
    argv = _argv(tmp_path, layer1, norms, alignments)
    a, b = _publish(), _publish()
    _fakes(monkeypatch, a)
    _fakes(monkeypatch, b)
    rc_a = []

    def b_postload(driver, build_id, expected_norms, expected_assertions=None):
        rc_a.append(a.main(argv + ["--record", rid_x]))
        return _Report([], {"db_norms": 0})

    monkeypatch.setattr(b, "validate_postload", b_postload)
    capsys.readouterr()
    rc_b = b.main(argv + ["--record", rid_y])
    assert (rc_a, rc_b) == ([0], 1)
    chain_id = store.read(rid_x)["publication"]["chain_id"]
    assert f"already published as chain {chain_id} (Build 1) by record {rid_x}" in capsys.readouterr().err
    assert store.read(rid_x)["publication"]["build_number"] == 1 and store.read(rid_y)["publication"] is None
    chain = json.loads((tmp_path / f"build_chain_{chain_id}.json").read_text())
    manifest = json.loads((tmp_path / "publications" / f"{chain_id}.json").read_text())
    assert (chain["build_number"], chain["record_id"], manifest["build_number"]) == (1, rid_x, 1)
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 1}
    assert store.next_build_number() == 2 and duplicate_build_numbers(tmp_path) == []
    assert store.read(rid_y)["executions"][-1]["status"] == "failed"
    # re-review ruling 1: B loaded the same build id A published and its
    # post-load gates passed, so the target stays available for that build
    target = read_target_state(tmp_path)
    assert (target["state"], target["build_id"], target["reason"]) == (
        "available", store.read(rid_x)["publication"]["build_id"], None)


def test_a_chain_record_no_record_published_under_the_lock_marks_the_target_unavailable(tmp_path, monkeypatch, capsys):
    # re-review ruling 1, the other case: a chain record appears during the
    # load and no build record publishes it, so Neo4j holds no published build
    from tests.unit.test_publish_layer23 import _Report

    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    chain_id = build_chain(layer1, norms, alignments_path=alignments)["chain_id"]

    def postload(driver, build_id, expected_norms, expected_assertions=None):
        (tmp_path / f"build_chain_{chain_id}.json").write_text(json.dumps({"chain_id": chain_id}))
        return _Report([], {"db_norms": 0})

    monkeypatch.setattr(cli, "validate_postload", postload)
    assert cli.main(_argv(tmp_path, layer1, norms, alignments)) == 1
    target = read_target_state(tmp_path)
    assert target["state"] == "unavailable"
    assert f"already published as chain {chain_id} while this run loaded it" in target["reason"]
    assert store.read(rid)["publication"] is None


def _failing_write(monkeypatch, cli, target: str):
    real_json, real_pointer = cli.atomic_write_json, cli.write_current_pointer

    def json_write(path, payload):
        if target == "manifest" and Path(path).parent.name == "publications":
            raise OSError("disk full")
        real_json(path, payload)

    def pointer_write(dump_dir, chain_id):
        if target == "pointer":
            raise OSError("disk full")
        return real_pointer(dump_dir, chain_id)

    monkeypatch.setattr(cli, "atomic_write_json", json_write)
    monkeypatch.setattr(cli, "write_current_pointer", pointer_write)


def test_a_failure_after_the_freeze_is_said_on_the_terminal_with_the_repair_command(tmp_path, monkeypatch, capsys):
    # final review B-P2-2 (a), A-M2, A-M9: the terminal carries the message,
    # which names what is not written and the command that writes it
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    _failing_write(monkeypatch, cli, "manifest")
    capsys.readouterr()
    with pytest.raises(OSError):
        cli.main(_argv(tmp_path, layer1, norms, alignments))
    chain_id = store.read(rid)["publication"]["chain_id"]
    err = capsys.readouterr().err
    assert f"record {rid} is published as Build 1, chain {chain_id}" in err
    assert f"not written: publications/{chain_id}.json, BUILD_CHAIN_CURRENT.txt" in err
    assert f"scripts/write_publication_manifest.py {chain_id} --dump-dir {tmp_path} --pointer" in err
    assert "never remove the chain record" in err


def test_a_failed_pointer_write_names_only_the_pointer(tmp_path, monkeypatch, capsys):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    _failing_write(monkeypatch, cli, "pointer")
    capsys.readouterr()
    with pytest.raises(OSError):
        cli.main(_argv(tmp_path, layer1, norms, alignments))
    err = capsys.readouterr().err
    assert "not written: BUILD_CHAIN_CURRENT.txt;" in err and "not written: publications/" not in err


def test_the_retry_after_a_missing_manifest_names_the_repair_not_activation(tmp_path, monkeypatch, capsys):
    # final review B-P2-2 (b): the early check tells a missing manifest apart
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    argv = _argv(tmp_path, layer1, norms, alignments)
    real = cli.atomic_write_json
    _failing_write(monkeypatch, cli, "manifest")
    with pytest.raises(OSError):
        cli.main(argv)
    monkeypatch.setattr(cli, "atomic_write_json", real)
    chain_id = store.read(rid)["publication"]["chain_id"]
    capsys.readouterr()
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert (f"chain {chain_id} is published (record {rid}, Build 1) but its publication manifest is missing: "
            f"write it with scripts/write_publication_manifest.py {chain_id} --dump-dir {tmp_path} --pointer") in err
    assert "activate it with" not in err
    # a chain record that no build record published (a pre-B94 artefact)
    (tmp_path / "build_chain_aaaaaaaaaaaa.json").write_text(json.dumps({"chain_id": "a" * 12}))
    monkeypatch.setattr(cli, "build_chain", lambda *a, **k: {"chain_id": "a" * 12, "inputs": []})
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert "build_chain_aaaaaaaaaaaa.json exists, but no publication manifest and no build record" in err
    assert "activate it with" not in err


def test_an_interrupt_right_after_the_freeze_keeps_the_chain_record(tmp_path, monkeypatch, capsys):
    # final review A-M1: set_publication returned, then the interrupt; the
    # record is frozen, so its chain record stays and the message says so
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    real = BuildRecordStore.set_publication

    def then_interrupt(self, record_id, publication, *, run_id=None):
        real(self, record_id, publication, run_id=run_id)
        raise KeyboardInterrupt

    monkeypatch.setattr(BuildRecordStore, "set_publication", then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        cli.main(_argv(tmp_path, layer1, norms, alignments))
    chain_id = store.read(rid)["publication"]["chain_id"]
    assert (tmp_path / f"build_chain_{chain_id}.json").is_file()
    error = store.read(rid)["executions"][-1]["error"]
    assert "is published as Build 1" in error and "clean up by hand" not in error
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 1}
    # re-review N1: the build is published, so the target stays available
    target = read_target_state(tmp_path)
    assert (target["state"], target["build_id"]) == ("available", store.read(rid)["publication"]["build_id"])


def _lines_after_the_freeze(cli) -> list[int]:
    """The statement lines of publish from the one after set_publication to
    the first write after the record is frozen (the manifest path)."""
    lines = Path(cli.__file__).read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "store.set_publication(record_id, publication" in line)
    end = next(i for i in range(start, len(lines)) if lines[i].strip().startswith("mpath = "))
    return [i + 1 for i in range(start + 1, end + 1) if lines[i].strip() and not lines[i].strip().startswith("#")]


@pytest.mark.parametrize("offset", range(6))
def test_an_interrupt_on_any_line_after_the_freeze_never_offers_cleanup(tmp_path, monkeypatch, capsys, offset):
    # re-review N1: an interrupt on each line between set_publication and the
    # manifest write (frozen = True included) finds the record published: the
    # chain record stays, the counter is written, the target stays available,
    # and the message never says "clean up by hand"
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    lines = _lines_after_the_freeze(cli)
    assert len(lines) == 6, lines
    line = lines[offset]
    code_file = str(Path(cli.__file__))

    def tracer(frame, event, arg):
        if frame.f_code.co_name != "_main" or frame.f_code.co_filename != code_file:
            return None

        def local(frame, event, arg):
            if event == "line" and frame.f_lineno == line:
                sys.settrace(None)
                raise KeyboardInterrupt
            return local
        return local

    sys.settrace(tracer)
    try:
        with pytest.raises(KeyboardInterrupt):
            cli.main(_argv(tmp_path, layer1, norms, alignments))
    finally:
        sys.settrace(None)
    record = store.read(rid)
    assert record["publication"]["build_number"] == 1
    assert (tmp_path / f"build_chain_{record['publication']['chain_id']}.json").is_file()
    error = record["executions"][-1]["error"]
    assert "is published as Build 1" in error and "clean up by hand" not in error
    assert error.count(f"record {rid} publication block") == 1
    assert json.loads((store.dir / "numbering.json").read_text()) == {"last_number": 1}
    target = read_target_state(tmp_path)
    assert (target["state"], target["build_id"]) == ("available", record["publication"]["build_id"])


def test_a_lost_counter_note_reaches_the_failure_message(tmp_path, monkeypatch, capsys):
    # final review A-M3: a failed counter write followed by a failed manifest write
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    monkeypatch.setattr(BuildRecordStore, "record_build_number", lambda self, number: "the counter was not written (x)")
    _failing_write(monkeypatch, cli, "manifest")
    with pytest.raises(OSError):
        cli.main(_argv(tmp_path, layer1, norms, alignments))
    assert "the counter was not written (x)" in store.read(rid)["executions"][-1]["error"]

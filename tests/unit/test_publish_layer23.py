"""publish_layer23: evidence first, gates, load, post-load gates, then the chain record (D-G21, D-G27)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import read_target_state

ROOT = Path(__file__).resolve().parents[2]


def _publish():
    spec = importlib.util.spec_from_file_location("publish_layer23_plan2a", ROOT / "scripts" / "publish_layer23.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Report:
    def __init__(self, failures, stats=None):
        self.failures, self.stats = failures, stats or {}

    @property
    def passed(self):
        return not self.failures


def _files(tmp_path, *, reference=None, align_input=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    norms_payload = {"build": {"build_id": "build-b"}, "norms": [], "judge_runs": []}
    if reference:
        norms_payload["build"]["reference"] = reference
    norms = tmp_path / ("norms_core.reference.json" if reference else "norms_core.json")
    norms.write_text(json.dumps(norms_payload))
    build = {"build_id": "build-b"}
    if align_input:
        build["alignment_input_sha256"] = sha256_of_file(norms)
    alignments = tmp_path / "alignments_core.json"
    alignments.write_text(json.dumps({"build": build, "assertions": [], "mapping_runs": [], "judge_runs": []}))
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.reference" if reference else "core", "build-b", sha256_of_file(layer1))
    run = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                                expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=[{"role": "norms", "file": norms.name, "sha256": sha256_of_file(norms)}])
    return layer1, norms, alignments, store, rid


def _fakes(monkeypatch, cli, *, gates_ok=True, postload_ok=True, load_raises=False, seen=None):
    monkeypatch.setattr(cli, "validate_build", lambda dump, norms=None, alignments=None: _Report([] if gates_ok else ["G3 norm without source span: x"], {"layer1_nodes": 0}))
    monkeypatch.setattr(cli, "norms_to_graph", lambda payload, build_id: {"nodes": [], "edges": []})
    monkeypatch.setattr(cli, "alignments_to_graph", lambda payload, hleg, build_id: {"nodes": [], "edges": []})
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda: [])
    monkeypatch.setattr(cli, "build_hleg_subtopics", lambda build_id: {"nodes": [], "edges": [], "skipped": []})

    class FakeStore:
        def load_dump(self, dump, driver):
            if seen is not None:
                seen.append(("load", sorted(p.name for p in Path(dump["build"]["_dir"]).glob("build_chain_*.json")) if "_dir" in dump["build"] else None))
            if load_raises:
                raise RuntimeError("bolt connection refused")
            return {"node:X": 1, "edge:Y": 2}

    class FakeDriver:
        closed = False

        def close(self):
            FakeDriver.closed = True

    monkeypatch.setattr(cli, "GraphStore", FakeStore)

    def fake_postload(driver, build_id, expected_norms, expected_assertions=None):
        if seen is not None:
            seen.append(("postload", build_id))
        return _Report([] if postload_ok else ["P1 db_norms 0 != 1"], {"db_norms": 0})

    monkeypatch.setattr(cli, "validate_postload", fake_postload)
    monkeypatch.setitem(sys.modules, "neo4j", types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda uri, auth: FakeDriver())))
    return FakeDriver


def test_chain_record_and_pointer_only_after_postload_gates_pass(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    driver = _fakes(monkeypatch, cli, postload_ok=False)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 1 and not list(tmp_path.glob("build_chain_*.json")) and not (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists()
    assert not (tmp_path / "publications").exists()
    assert read_target_state(tmp_path)["state"] == "unavailable" and "P1" in read_target_state(tmp_path)["reason"]
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and "P1" in ex["error"] and ex["covers_steps"] == ["P.1", "P.2"]
    assert [g["ok"] for g in ex["gates"]] == [True] * 6 + [False, True, True, True, True] and driver.closed
    assert store.read(rid)["publication"] is None

    _fakes(monkeypatch, cli, postload_ok=True)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 0
    chain = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())
    assert chain["published_at"] and chain["gating"] == {"layer2": "llm", "layer3": "llm"} and chain["label"] == "llm-gated"
    assert len(chain["gates"]) == 6 and len(chain["postload_gates"]) == 5 and chain["record_id"] == rid
    assert (tmp_path / "BUILD_CHAIN_CURRENT.txt").read_text().strip() == chain["chain_id"]
    manifest = json.loads((tmp_path / "publications" / f"{chain['chain_id']}.json").read_text())
    assert manifest["schema_version"] == "publication.v1" and manifest["files"]["norms"] == "norms_core.json"
    assert read_target_state(tmp_path)["state"] == "available"
    assert store.read(rid)["publication"]["chain_id"] == chain["chain_id"] and store.is_frozen(rid)


def test_publication_artifacts_do_not_exist_while_loading(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    observed = {}

    def fake_postload(driver, build_id, expected_norms, expected_assertions=None):
        observed["chains"] = list(tmp_path.glob("build_chain_*.json"))
        observed["state"] = read_target_state(tmp_path)["state"]
        observed["manifests"] = list(tmp_path.glob("publications/*"))
        observed["pointer"] = (tmp_path / "BUILD_CHAIN_CURRENT.txt").read_text() if (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists() else None
        observed["publication"] = store.read(rid)["publication"]
        return _Report([])

    _fakes(monkeypatch, cli)
    monkeypatch.setattr(cli, "validate_postload", fake_postload)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]) == 0
    assert observed["chains"] == [] and observed["state"] == "loading"
    assert observed["manifests"] == [] and observed["pointer"] is None and observed["publication"] is None


def test_load_exception_marks_target_unavailable_and_closes_driver(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    driver = _fakes(monkeypatch, cli, load_raises=True)
    with pytest.raises(RuntimeError):
        cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert read_target_state(tmp_path)["state"] == "unavailable" and driver.closed
    assert store.read(rid)["executions"][-1]["status"] == "failed"


def test_gate_failure_records_per_gate_and_gates_only_covers_p1(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli, gates_ok=False)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]) == 1
    ex = store.read(rid)["executions"][-1]
    assert ex["gates"][2] == {"name": "G3", "ok": False, "detail": "G3 norm without source span: x"} and ex["gates"][0]["ok"]
    _fakes(monkeypatch, cli)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--dump-dir", str(tmp_path), "--gates-only"]) == 0
    ex = store.read(rid)["executions"][-1]
    assert ex["covers_steps"] == ["P.1"] and ex["status"] == "done" and store.read(rid)["publication"] is None


def test_alignment_input_digest_is_mandatory_for_reference_norms_and_checked_always(tmp_path, monkeypatch, capsys):
    cli = _publish()
    ref = {"kind": "norms", "layer": 2, "source_sha256": "s" * 64, "source_build_id": "b", "decisions_sha256": "d" * 64,
           "campaign_id": "c", "freeze_id": "f1", "campaign_type": "layer2_annotation", "stage": "production", "round": None,
           "units_in_scope": 1, "units_adjudicated": 1, "units_undecided": 0, "scope_core_nodes": [], "decisions_applied": 1,
           "materialized_at": "t"}
    layer1, norms, alignments, store, rid = _files(tmp_path, reference=ref, align_input=False)
    _fakes(monkeypatch, cli)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 1 and "no input digest" in capsys.readouterr().err
    layer1, norms, alignments, store, rid = _files(tmp_path / "b", align_input=True)
    norms.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "changed": 1}))
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path / "b"), "--record", rid])
    assert rc == 1 and "different norms file" in capsys.readouterr().err


def test_human_layer_needs_its_bound_manifest_and_label_needs_production_scope(tmp_path, monkeypatch, capsys):
    cli = _publish()
    ref = {"kind": "norms", "layer": 2, "source_sha256": "s" * 64, "source_build_id": "build-b+chain-000000000000",
           "decisions_sha256": "d" * 64, "campaign_id": "c", "freeze_id": "f1", "campaign_type": "layer2_annotation",
           "stage": "production", "round": None, "units_in_scope": 1, "units_adjudicated": 1, "units_undecided": 0,
           "scope_core_nodes": ["eu-ai-act:article-9"], "decisions_applied": 1, "materialized_at": "t"}
    layer1, norms, alignments, store, rid = _files(tmp_path, reference=ref)
    (tmp_path / "core_nodes.txt").write_text("eu-ai-act:article-9")
    _fakes(monkeypatch, cli)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 1 and "manifest" in capsys.readouterr().err, "a human-gated layer without its freeze manifest is refused"
    manifest = {"schema_version": "freeze_manifest.v1", "campaign_type": "layer2_annotation", "campaign_id": "c", "freeze_id": "f1",
                "stage": "production", "round": None, "pinned_build_id": "build-b+chain-000000000000", "guideline_version": "v1",
                "scope_core_nodes": ["eu-ai-act:article-9"], "units_in_scope": 1, "units_adjudicated": 1, "units_undecided": 0,
                "rows_included": ["r"], "decisions_sha256": "d" * 64, "frozen_at": "t"}
    mpath = tmp_path / "freeze-f1.json"
    mpath.write_text(json.dumps(manifest))
    outside = tmp_path.parent / "freeze-elsewhere.json"
    outside.write_text(json.dumps(manifest))
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--manifest", str(outside), "--dump-dir", str(tmp_path)])
    assert rc == 1 and "copy the freeze manifest" in capsys.readouterr().err
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--manifest", str(mpath), "--dump-dir", str(tmp_path)])
    assert rc == 0
    chain = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())
    assert chain["gating"] == {"layer2": "human", "layer3": "llm"} and chain["label"] is None
    assert [i["role"] for i in chain["inputs"]] == ["layer1_dump", "norms", "alignments", "freeze_manifest"]
    assert chain["manifests"][0]["freeze_id"] == "f1" and chain["manifests"][0]["layer"] == 2
    other = {**manifest, "freeze_id": "f9", "decisions_sha256": "e" * 64}
    (tmp_path / "freeze-f9.json").write_text(json.dumps(other))
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--manifest", str(tmp_path / "freeze-f9.json"), "--dump-dir", str(tmp_path)])
    assert rc == 1 and "f9" in capsys.readouterr().err, "an unrelated manifest is refused"
    assert store.read(rid)["publication"]["chain_id"] == chain["chain_id"], "the first publication is untouched"
    descendants = [r for r in store.list_records() if r.get("parent_record_id") == rid]
    assert len(descendants) == 1 and descendants[0]["executions"][-1]["status"] == "failed", "the refused attempt ran on a descendant"


def test_decisions_flag_is_retired_and_unknown_norms_file_needs_record(tmp_path, monkeypatch, capsys):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    assert cli.main(["--dump", str(layer1), "--norms", str(norms), "--decisions", str(tmp_path / "d.json")]) == 2
    assert "materialize_reference" in capsys.readouterr().err
    stray = tmp_path / "norms_stray.json"
    # differs from norms_core.json by content: an identical file would carry the record's output digest
    stray.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "stray": 1}))
    _fakes(monkeypatch, cli)
    assert cli.main(["--dump", str(layer1), "--norms", str(stray), "--dump-dir", str(tmp_path), "--gates-only"]) == 1
    assert "pass --record" in capsys.readouterr().err


def test_exception_before_the_load_records_failed_and_leaves_no_target_state(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)

    def boom(payload, build_id):
        raise ValueError("bad norm payload")

    monkeypatch.setattr(cli, "norms_to_graph", boom)
    with pytest.raises(ValueError):
        cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and "bad norm payload" in ex["error"] and len(ex["gates"]) == 6
    assert read_target_state(tmp_path) is None and not list(tmp_path.glob("build_chain_*.json"))


def test_schema_invalid_publication_records_failed_and_writes_nothing(tmp_path, monkeypatch, capsys):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    monkeypatch.setattr(cli, "gating_of", lambda n, a: {"layer2": "robot", "layer3": "llm"})
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 1 and "does not validate" in capsys.readouterr().err
    assert not list(tmp_path.glob("build_chain_*.json")) and not (tmp_path / "publications").exists()
    assert not (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists() and store.read(rid)["publication"] is None
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and len(ex["gates"]) == 11

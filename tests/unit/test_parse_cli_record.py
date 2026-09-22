"""The parse command writes an execution record covering L0.1 and L1.1 (D-G20)."""

from __future__ import annotations

import json

import pytest

from tere4ai.graph_store.build_record import BuildRecordStore


def _manifest(tmp_path, files=1):
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(json.dumps({"snapshots": [{"file": f"a{i}.html", "sha256": "0" * 64} for i in range(files)]}))
    return manifest


class _Report:
    def __init__(self, failures, stats):
        self.failures, self.stats = failures, stats

    @property
    def passed(self):
        return not self.failures


def _setup(monkeypatch, cli, tmp_path, report, dump=None):
    dump = dump or {"build": {"build_id": "build-abc", "snapshots": [{"file": "a0.html", "sha256": "0" * 64}]},
                    "nodes": [{"id": "n1", "type": "Article"}, {"id": "n2", "type": "Recital"}], "edges": [],
                    "review_queue": [{"item_id": "q1"}]}
    monkeypatch.setattr(cli, "build_layer1", lambda out_path, manifest_path: dump)
    monkeypatch.setattr(cli, "resolve", lambda d: d)
    monkeypatch.setattr(cli, "validate_build", lambda d: report)
    monkeypatch.setattr(cli, "DEFAULT_OUT_PATH", tmp_path / "layer1.json")


def test_parse_records_manifest_counts_gates_and_digest(tmp_path, monkeypatch):
    import tere4ai.parse_legal_structure.__main__ as cli

    manifest = _manifest(tmp_path)
    _setup(monkeypatch, cli, tmp_path, _Report([], {"layer1_nodes": 2, "orphans": 0}))
    rc = cli.main(["--dump-dir", str(tmp_path), "--manifest", str(manifest)])
    assert rc == 0 and (tmp_path / "layer1.json").is_file()
    store = BuildRecordStore(tmp_path)
    record = store.list_records()[0]
    ex = record["executions"][0]
    assert ex["command"] == "parse_legal_structure" and ex["covers_steps"] == ["L0.1", "L1.1"] and ex["status"] == "done"
    assert ex["counts"]["nodes_by_type"] == {"Article": 1, "Recital": 1} and ex["counts"]["review_queue"] == 1
    assert ex["counts"]["manifest_files"] == [{"file": "a0.html", "sha256": "0" * 64}] and ex["counts"]["manifest_files_count"] == 1
    assert [g["name"] for g in ex["gates"]] == ["G1", "G2", "G3", "G4", "G5", "G6"] and all(g["ok"] for g in ex["gates"])
    digest = ex["outputs"][0]["sha256"]
    assert ex["outputs"][0]["role"] == "layer1_dump" and len(digest) == 64
    assert record["layer1_digest"] == digest and record["base_build_id"] == "build-abc"
    assert record["aliases"][0].startswith("parse-") and record["aliases"][1] == f"layer1-{digest[:12]}"
    assert store.find_parse_record(digest) == record["record_id"]
    assert ex["inputs"][0]["role"] == "manifest"


def test_parse_gate_failure_records_failed_execution_with_per_gate_detail(tmp_path, monkeypatch):
    import tere4ai.parse_legal_structure.__main__ as cli

    manifest = _manifest(tmp_path, 0)
    _setup(monkeypatch, cli, tmp_path, _Report(["G1 orphan legal node: n9"], {}))
    rc = cli.main(["--dump-dir", str(tmp_path), "--manifest", str(manifest)])
    assert rc == 1 and not (tmp_path / "layer1.json").exists()
    ex = BuildRecordStore(tmp_path).list_records()[0]["executions"][0]
    assert ex["status"] == "failed" and "G1" in ex["error"]
    assert ex["gates"][0] == {"name": "G1", "ok": False, "detail": "G1 orphan legal node: n9"} and ex["gates"][1]["ok"]


def test_parse_exception_in_final_write_is_recorded(tmp_path, monkeypatch):
    import tere4ai.parse_legal_structure.__main__ as cli

    manifest = _manifest(tmp_path)
    _setup(monkeypatch, cli, tmp_path, _Report([], {}))
    real_write = cli.Path.write_text

    def boom(self, *a, **k):
        if self.name == "layer1.json":
            raise OSError("disk full")
        return real_write(self, *a, **k)

    monkeypatch.setattr(cli.Path, "write_text", boom)
    with pytest.raises(OSError):
        cli.main(["--dump-dir", str(tmp_path), "--manifest", str(manifest)])
    ex = BuildRecordStore(tmp_path).list_records()[0]["executions"][0]
    assert ex["status"] == "failed" and "disk full" in ex["error"]

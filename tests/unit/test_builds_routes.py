"""GET /api/builds and /api/builds/{ref}: the build record through the facade (D-G19, D-G25)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import tere4ai.http_facade.app as facade
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import set_target_state

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "build_record.schema.json").read_text())


def _validator(definition):
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


def _legacy_dumps(tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "stats": {}}))
    (tmp_path / "alignments_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "assertions": []}))


def test_list_and_detail_validate_and_carry_liveness_progress_and_target(tmp_path):
    _legacy_dumps(tmp_path)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.b74", "build-b", "x")
    run = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1", "L3.2", "L3.3"], argv=["--norms", "n"],
        inputs=[], config={"batch_size": 20}, expected_total=26, work_unit="batches",
        checkpoint_file="alignments_core.b74.checkpoint.jsonl")
    (tmp_path / "alignments_core.b74.checkpoint.jsonl").write_text("".join(
        json.dumps({"run_id": run, "batch": f"batch:{i}:n", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n"
        for i in range(0, 300, 20)))
    (tmp_path / "build_records" / "broken.json").write_text("{", encoding="utf-8")
    set_target_state(tmp_path, state="available", build_id="b", uri="bolt://x", reason=None)
    with TestClient(facade.create_app(tmp_path)) as client:
        listed = client.get("/api/builds").json()
        assert not list(_validator("builds_list").iter_errors(listed))
        assert listed["publication_target"]["state"] == "available" and listed["observed_at"]
        by = {b["record_id"]: b for b in listed["builds"]}
        assert by[rid]["steps"]["L3.1"] == "running" and by[rid]["served"] is False and by[rid]["synthesised"] is False
        assert by["broken"]["unreadable"] and by["broken"]["reason"]
        assert by["legacy-core"]["synthesised"] and by["legacy-core"]["steps"]["P.1"] == "not_recorded"
        detail = client.get("/api/builds/core.b74").json()
        assert not list(_validator("presented_record").iter_errors(detail))
        ex = detail["executions"][0]
        assert ex["liveness"] == "live" and ex["progress"]["completed"] == 15 and ex["progress"]["expected_total"] == 26
        assert ex["provenance"]["models"] == "unavailable"
        legacy = client.get("/api/builds/legacy-core").json()
        assert legacy["synthesised"] and not list(_validator("presented_record").iter_errors(legacy))
        assert client.get("/api/builds/core").json()["record_id"] == "legacy-core", "a bare legacy slug resolves too"
        assert client.get("/api/builds/nope").status_code == 404
        assert client.get("/api/builds/a%20b").status_code == 422, "a decoded space fails the reference pattern"
        assert client.get("/api/builds/..%2Fetc").status_code == 404, "the router never matches a slash inside the segment"
        inventory = client.get("/.well-known/tere4ai.json").json()["endpoints"]
        assert inventory["builds"] == {"method": "GET", "path": "/api/builds", "paid": False}
        assert "/api/builds" in client.get("/llms.txt").text


def test_routes_read_per_request_and_never_create_the_records_directory(tmp_path):
    _legacy_dumps(tmp_path)
    with TestClient(facade.create_app(tmp_path)) as client:
        first = client.get("/api/builds").json()
        assert not (tmp_path / "build_records").exists(), "a read-only route creates nothing"
        store = BuildRecordStore(tmp_path)
        rid = store.create_record("core.b75", "build-b", None)
        second = client.get("/api/builds").json()
        assert rid in {b["record_id"] for b in second["builds"]} and rid not in {b["record_id"] for b in first["builds"]}

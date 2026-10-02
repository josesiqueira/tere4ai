"""GET /api/builds and /api/builds/{ref}: the build record through the facade (D-G19, D-G25)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import tere4ai.http_facade.app as facade
from tere4ai.graph_store.build_chain import build_chain
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import activate, set_target_state, write_publication_manifest

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
    run = store.start_execution(rid, command="align_hleg", covers_steps=["L3.1", "L3.2", "L3.3"], argv=["--norms", "n"],
        inputs=[], config={"batch_size": 20}, expected_total=26, work_unit="batches",
        checkpoint_file="alignments_core.b74.checkpoint.jsonl")
    (tmp_path / "alignments_core.b74.checkpoint.jsonl").write_text("".join(
        json.dumps({"run_id": run, "batch": f"batch:{i}:n", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n"
        for i in range(0, 300, 20)))
    (tmp_path / "build_records" / "0000000b0000.json").write_text("{", encoding="utf-8")
    set_target_state(tmp_path, state="available", build_id="b", uri="bolt://x", reason=None)
    with TestClient(facade.create_app(tmp_path)) as client:
        listed = client.get("/api/builds").json()
        assert not list(_validator("builds_list").iter_errors(listed))
        assert listed["publication_target"]["state"] == "available" and listed["observed_at"]
        by = {b["record_id"]: b for b in listed["builds"]}
        assert by[rid]["steps"]["L3.1"] == "running" and by[rid]["served"] is False and by[rid]["synthesised"] is False
        assert by["0000000b0000"]["unreadable"] and by["0000000b0000"]["reason"]
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


def test_one_unreadable_artefact_or_record_never_fails_the_list(tmp_path):
    _legacy_dumps(tmp_path)
    (tmp_path / "norms_x.json").mkdir()  # unreadable as a file whatever the user running the suite
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.b75", "build-b", None)
    store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                          expected_total=1, work_unit="groups", checkpoint_file=None)
    path = tmp_path / "build_records" / f"{rid}.json"
    record = json.loads(path.read_text())
    record["executions"][0]["heartbeat_at"] = "not a timestamp"
    path.write_text(json.dumps(record))
    with TestClient(facade.create_app(tmp_path)) as client:
        response = client.get("/api/builds")
        assert response.status_code == 200
        listed = response.json()
        assert not list(_validator("builds_list").iter_errors(listed))
        by = {b["record_id"]: b for b in listed["builds"]}
        assert by["legacy-x"]["unreadable"] and "norms_x.json" in by["legacy-x"]["reason"]
        assert str(tmp_path) not in by["legacy-x"]["reason"], "the reason names the file, never its path"
        assert by[rid]["unreadable"] and "not a timestamp" in by[rid]["reason"]
        assert by["legacy-core"]["unreadable"] is False and by["legacy-core"]["steps"]["L2.1"] == "done"
        assert client.get("/api/builds/legacy-x").status_code == 404
        assert client.get(f"/api/builds/{rid}").status_code == 404


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_a_build_detail_error_names_the_build_and_the_reason_never_a_server_path(tmp_path):
    # B81 item 17: the OS error of an unreadable record carries its absolute path
    _legacy_dumps(tmp_path)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.b75", "build-b", None)
    path = tmp_path / "build_records" / f"{rid}.json"
    path.chmod(0)
    try:
        with TestClient(facade.create_app(tmp_path)) as client:
            response = client.get(f"/api/builds/{rid}")
    finally:
        path.chmod(0o644)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error.startswith(f"build record {rid} is unreadable: ") and "Permission denied" in error
    assert str(tmp_path) not in error and f"{rid}.json" in error, "the reason names the file, never its path"


def test_an_unreadable_alias_index_is_a_404_with_its_reason_never_a_500_or_a_path(tmp_path):
    _legacy_dumps(tmp_path)
    (tmp_path / "build_records").mkdir()
    (tmp_path / "build_records" / "aliases.json").write_text("{", encoding="utf-8")
    with TestClient(facade.create_app(tmp_path)) as client:
        response = client.get("/api/builds/core.b75")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error.startswith("build record core.b75 is unreadable: ") and "aliases.json" in error
    assert str(tmp_path) not in error


def test_the_build_routes_keep_serving_while_the_graph_load_is_refused(tmp_path):
    # B79 item 25: a drifted activated build refuses the graph (load_error),
    # and the build routes, which never read the graph, still answer
    _legacy_dumps(tmp_path)
    chain = build_chain(tmp_path / "layer1.json", tmp_path / "norms_core.json",
                        alignments_path=tmp_path / "alignments_core.json")
    publication = {"chain_id": chain["chain_id"], "build_id": "build-b+chain-" + chain["chain_id"], "published_at": "t",
                   "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                   "postload_gates": [], "manifests": []}
    write_publication_manifest(tmp_path, publication, record_id="r", inputs=chain["inputs"],
                               files={"layer1_dump": "layer1.json", "norms": "norms_core.json",
                                      "alignments": "alignments_core.json"})
    activate(tmp_path, chain["chain_id"])
    rid = BuildRecordStore(tmp_path).create_record("core.b75", "build-b", None)
    (tmp_path / "norms_core.json").write_text("{}")
    with TestClient(facade.create_app(tmp_path)) as client:
        assert client.app.state.load_error
        assert client.get("/api/health").status_code == 503
        response = client.get("/api/builds")
        assert response.status_code == 200
        listed = response.json()
        assert not list(_validator("builds_list").iter_errors(listed))
        assert listed["served_chain_id"] is None
        assert {rid, "legacy-core"} <= {b["record_id"] for b in listed["builds"]}
        for ref in (rid, "legacy-core"):
            detail = client.get(f"/api/builds/{ref}")
            assert detail.status_code == 200, ref
            assert not list(_validator("presented_record").iter_errors(detail.json()))

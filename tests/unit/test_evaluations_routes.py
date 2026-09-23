"""GET /api/evaluations and /api/evaluations/{ref}: the evaluation records through the facade (D-G33, DEC-17).

DEC-17 fix wave: no absolute path leaks through a stored error or an unreadable row."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import tere4ai.http_facade.app as facade
from tere4ai.eval.evaluation_record import EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "evaluation_record.schema.json").read_text())


def _validator(definition):
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


def _legacy_dumps(tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "stats": {}}))
    (tmp_path / "alignments_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "assertions": []}))


def _eval_root(tmp_path):
    root = tmp_path / "root"
    (root / "eval" / "results").mkdir(parents=True)
    (root / "eval" / "gold").mkdir()
    # The July-2026 pinning (present_evaluation.JULY_DIGESTS) dates a stated
    # phrase only when the summary's bytes are the exact July bytes it names;
    # this checkout's real eval/results/ablation_summary.json IS those bytes
    # (its config carries generator_model gpt-5.2, judge_model claude-opus-4-8,
    # items_total 57, matching the values a hand-typed stub would otherwise
    # assert), so the fixture copies it rather than re-typing a stub whose
    # digest would read as a rewritten compatibility file (NOT_JULY_BYTES).
    shutil.copyfile(ROOT / "eval" / "results" / "ablation_summary.json",
                    root / "eval" / "results" / "ablation_summary.json")
    (root / "eval" / "results" / "RUN2_ANALYSIS.md").write_text("Date: 2026-07-09.\n")
    return root


def test_list_and_detail_validate_and_carry_recorded_legacy_and_unreadable_rows(tmp_path):
    _legacy_dumps(tmp_path)
    root = _eval_root(tmp_path)
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[],
                      build={"base_build_id": "build-b", "publication": None, "publication_reason": "x"},
                      intended_items=["i1"])
    (store.dir / "0000000b0000.json").write_text("{", encoding="utf-8")
    with TestClient(facade.create_app(tmp_path, eval_root=root)) as client:
        listed = client.get("/api/evaluations").json()
        assert not list(_validator("evaluations_list").iter_errors(listed))
        assert listed["served_build_id"].startswith("build-b") and listed["observed_at"] and "records without a date" in listed["order"]
        rows = {r["record_id"]: r for g in listed["groups"] for r in g["records"]}
        assert rows[rid]["status"] == "running" and rows[rid]["build_key"] == "build-b"
        assert rows["0000000b0000"]["unreadable"] and rows["0000000b0000"]["reason"]
        legacy = [r for r in rows.values() if r["origin"] == "legacy"]
        assert len(legacy) == 1 and legacy[0]["started_at"] == "2026-07-09" and legacy[0]["build_key"] == "unknown"
        assert [g["build_key"] for g in listed["groups"]][-1] == "unknown"
        detail = client.get(f"/api/evaluations/{rid}").json()
        assert not list(_validator("presented_record").iter_errors(detail))
        assert detail["outcome"]["status"] == "running" and detail["observed_at"]
        legacy_detail = client.get(f"/api/evaluations/{legacy[0]['record_id']}").json()
        assert legacy_detail["synthesised"] and not list(_validator("presented_record").iter_errors(legacy_detail))
        assert client.get("/api/evaluations/0000000b0000").status_code == 404
        assert "not readable" in client.get("/api/evaluations/0000000b0000").json()["error"]
        assert client.get("/api/evaluations/nope").status_code == 422, "a ref outside the id syntax is refused"
        assert client.get("/api/evaluations/000000000000").status_code == 404
        assert client.get("/api/evaluations/..%2Fetc").status_code in (404, 422)
        inventory = client.get("/.well-known/tere4ai.json").json()["endpoints"]
        assert inventory["evaluations"] == {"method": "GET", "path": "/api/evaluations", "paid": False}
        assert inventory["evaluation"]["path"] == "/api/evaluations/{ref}"
        assert "GET /api/evaluations" in client.get("/llms.txt").text


def test_list_survives_an_unreadable_record_and_a_missing_copy(tmp_path):
    _legacy_dumps(tmp_path)
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[],
                      build={"base_build_id": "build-b", "publication": None, "publication_reason": "x"})
    out = tmp_path / "ablation_summary.json"
    out.write_text("{}")
    ref = store.keep_output(rid, "summary", out)
    store.finish(rid, status="completed", outputs=[ref])
    (store.dir / ref["copy"]).unlink()
    (store.dir / "0000000c0000.json").write_text(json.dumps({"schema_version": "evaluation_record.v1"}))
    with TestClient(facade.create_app(tmp_path, eval_root=tmp_path / "empty")) as client:
        listed = client.get("/api/evaluations").json()
        rows = {r["record_id"]: r for g in listed["groups"] for r in g["records"]}
        assert rows[rid]["status"] == "completed" and rows["0000000c0000"]["unreadable"]
        detail = client.get(f"/api/evaluations/{rid}").json()
        assert detail["outputs"][0]["copy_state"] == "missing"


def test_an_unlistable_store_is_an_outage_not_an_empty_list(tmp_path, monkeypatch):
    _legacy_dumps(tmp_path)

    def boom(self):
        raise OSError("disk gone")
    monkeypatch.setattr(EvaluationRecordStore, "list_records", boom)
    with TestClient(facade.create_app(tmp_path, eval_root=tmp_path / "empty")) as client:
        r = client.get("/api/evaluations")
        assert r.status_code == 503 and "evaluation records unavailable" in r.json()["error"]


def test_no_records_directory_yields_the_legacy_rows_only(tmp_path):
    _legacy_dumps(tmp_path)
    root = _eval_root(tmp_path)
    with TestClient(facade.create_app(tmp_path, eval_root=root)) as client:
        listed = client.get("/api/evaluations").json()
        assert [r["origin"] for g in listed["groups"] for r in g["records"]] == ["legacy"]
        assert not (tmp_path / "evaluation_records").exists(), "a read never creates the directory"


def test_a_stored_error_carrying_an_absolute_path_is_presented_with_the_file_name_only(tmp_path):
    _legacy_dumps(tmp_path)
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[],
                      build={"base_build_id": "build-b", "publication": None, "publication_reason": "x"})
    deep = tmp_path / "very" / "deep" / "ablation_summary.json"
    store.finish(rid, status="failed", error=f"FileNotFoundError: [Errno 2] No such file or directory: '{deep}'")
    with TestClient(facade.create_app(tmp_path, eval_root=_eval_root(tmp_path))) as client:
        detail = client.get(f"/api/evaluations/{rid}").json()
    assert detail["outcome"]["error"] == ("FileNotFoundError: [Errno 2] No such file or directory: "
                                          "'ablation_summary.json'")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_record_under_a_deep_path_names_the_file_only(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    _legacy_dumps(deep)
    store = EvaluationRecordStore(deep)
    bad = store.dir / "00000000000c.json"
    bad.write_text("{}", encoding="utf-8")
    bad.chmod(0)
    try:
        with TestClient(facade.create_app(deep, eval_root=_eval_root(tmp_path))) as client:
            rows = {r["record_id"]: r for g in client.get("/api/evaluations").json()["groups"] for r in g["records"]}
            detail = client.get("/api/evaluations/00000000000c")
    finally:
        bad.chmod(0o644)
    reason = rows["00000000000c"]["reason"]
    assert "00000000000c.json" in reason and str(tmp_path) not in reason and "/" not in reason
    assert detail.status_code == 404 and str(tmp_path) not in detail.json()["error"]

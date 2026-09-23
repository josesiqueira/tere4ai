"""The evaluation presenter, the list projection and the legacy synthesis (D-G33, D-G34, DEC-17)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from tere4ai.eval import present_evaluation as pe
from tere4ai.eval.evaluation_record import EvaluationRecordStore, sha256_of_file

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "evaluation_record.schema.json").read_text())
NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _validator(definition):
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


def _build(base="build-b"):
    return {"base_build_id": base, "publication": None, "publication_reason": "no pointer"}


def _run(store, tmp_path, **kw):
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[], build=_build(),
                      intended_items=["i1"], **kw)
    out = tmp_path / "ablation_summary.json"
    out.write_text("{}")
    ref = store.keep_output(rid, "summary", out)
    store.finish(rid, status="completed", completed_items=["i1"], outputs=[ref])
    return rid


def test_presenter_reports_a_never_finished_record_as_running_with_its_start(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="eval_harness", argv=[], inputs=[], build=_build())
    p = pe.present_evaluation(store.read(rid), store, NOW)
    assert not list(_validator("presented_record").iter_errors(p))
    assert p["outcome"]["status"] == "running" and p["started_at"] and p["ended_at"] is None
    assert p["provenance"]["ended_at"] == "unavailable" and p["reasons"]["ended_at"] == "running: no end recorded"
    assert p["observed_at"] == NOW.isoformat() and p["synthesised"] is False
    assert pe.summary_of(p)["status"] == "running"


def test_presenter_marks_missing_and_drifted_copies(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = _run(store, tmp_path)
    rec = store.read(rid)
    (store.dir / rec["outputs"][0]["copy"]).write_text("{ }")
    p = pe.present_evaluation(rec, store, NOW)
    assert p["outputs"][0]["copy_state"] == "drifted" and "differs" in p["outputs"][0]["copy_reason"]
    assert p["outcome"]["status"] == "completed", "a lost copy never rewrites the outcome"
    (store.dir / rec["outputs"][0]["copy"]).unlink()
    p = pe.present_evaluation(rec, store, NOW)
    assert p["outputs"][0]["copy_state"] == "missing" and p["outputs"][0]["copy_reason"].startswith("copy file absent")
    rid2 = _run(store, tmp_path)
    p2 = pe.present_evaluation(store.read(rid2), store, NOW)
    assert p2["outputs"][0]["copy_state"] == "present" and p2["outputs"][0]["copy_reason"] is None
    assert p2["provenance"]["prompt_sha256"] == "unavailable" and "prompt hash" in p2["reasons"]["prompt_sha256"]


def test_summary_and_grouping_follow_the_stated_order(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    a = _run(store, tmp_path)
    b = _run(store, tmp_path)
    presented = [pe.present_evaluation(store.read(r), store, NOW) for r in (a, b)]
    presented[1]["build"] = {"base_build_id": "build-b", "publication": {"manifest_file": "p", "sha256": "0" * 64,
                                                                        "build_id": "build-b+chain-x"},
                             "publication_reason": None}
    legacy = {**presented[0], "record_id": "legacy-000000000001", "origin": "legacy", "started_at": None,
              "ended_at": None, "outcome": None, "build": {"base_build_id": None, "publication": None,
                                                           "publication_reason": None}}
    rows = [pe.summary_of(p) for p in (presented[0], presented[1], legacy)] + [pe.unreadable_row("0000000b0000", "bad")]
    assert rows[1]["build_key"] == "build-b+chain-x" and rows[1]["build_kind"] == "publication"
    assert rows[2]["build_key"] == "unknown" and rows[2]["status"] is None
    assert rows[3]["unreadable"] and rows[3]["build_kind"] == "unknown" and rows[3]["kind"] is None
    groups = pe.group_summaries(rows)
    assert [g["build_key"] for g in groups][-1] == "unknown"
    assert {g["build_key"] for g in groups} == {"build-b", "build-b+chain-x", "unknown"}
    unknown = groups[-1]["records"]
    assert [r["record_id"] for r in unknown] == ["0000000b0000", "legacy-000000000001"], "no date: by id, last"
    assert "records without a date last" in pe.ORDER_SENTENCE
    assert not list(_validator("evaluations_list").iter_errors(
        {"schema_version": "evaluations_list.v1", "observed_at": NOW.isoformat(), "served_build_id": None,
         "order": pe.ORDER_SENTENCE, "groups": groups}))


def _legacy_root(tmp_path, with_dates=True):
    results = tmp_path / "eval" / "results"
    results.mkdir(parents=True)
    gold = tmp_path / "eval" / "gold"
    gold.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    cfg = {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}
    strategies = {"plain_llm": {"errors": 0}}
    for name, n in (("ablation_run1_summary.json", 57), ("ablation_summary.json", 57), ("ablation_full_summary.json", 486),
                    ("ablation_variance_summary.json", 486)):
        # the "run" key keeps the four files distinct: legacy ids are content digests (R-P3)
        (results / name).write_text(json.dumps({"run": name, "config": cfg, "items_total": n, "strategies": strategies,
                                                 **({"usage_provider_reported": {"by_role": {}}} if n == 486 else {})}))
    for name in ("ablation_full_checkpoint.jsonl", "ablation_variance_checkpoint.jsonl"):
        (results / name).write_text('{"unit": "u", "strategy": "plain_llm", "results": {}}\n')
    if with_dates:
        (results / "RUN2_ANALYSIS.md").write_text("# run 2\nDate: 2026-07-09. Config: x\nRun 1 artifacts: ablation_run1_*.\n")
        (results / "FULL_RUN_ANALYSIS.md").write_text("# full\nDate: 2026-07-10/11. Config of record: x\nrepeat) on 2026-07-11 and\n")
    (docs / "variance_study.md").write_text("# study\n\n> Generated by scripts/variance_report.py from ablation_full_checkpoint.jsonl (run A) and ablation_variance_checkpoint.jsonl (run B);\n")
    (gold / "judge_label_sheet.json").write_text(json.dumps({"builds": {"norms_core": "build-3b753e5e9297"},
                                                             "items": [{"decision_id": "d1", "human_label": None, "judge_run": {"judge_model": "claude-opus-4-8"}},
                                                                       {"decision_id": "d2", "human_label": "accept", "judge_run": {"judge_model": "claude-opus-4-8"}}]}))
    return tmp_path


def test_legacy_synthesis_states_only_what_the_files_state(tmp_path):
    root = _legacy_root(tmp_path)
    records = pe.synthesise_legacy_evaluations(root)
    by_file = {r["outputs"][0]["file"]: r for r in records if not r.get("unreadable") and r["kind"] == "run"}
    assert set(by_file) == {"ablation_run1_summary.json", "ablation_summary.json", "ablation_full_summary.json",
                            "ablation_variance_summary.json"}
    run1 = by_file["ablation_run1_summary.json"]
    assert run1["record_id"] == "legacy-" + sha256_of_file(root / "eval" / "results" / "ablation_run1_summary.json")[:12]
    assert run1["origin"] == "legacy" and run1["outcome"] is None and run1["started_at"] is None, "no file dates run 1"
    assert run1["build"]["base_build_id"] is None and run1["models"] == {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}
    assert run1["counts"] == {"items_total": 57} and run1["config"]["strategies"] == ["plain_llm"]
    run2 = by_file["ablation_summary.json"]
    assert run2["started_at"] == "2026-07-09"
    assert by_file["ablation_variance_summary.json"]["started_at"] == "2026-07-11"
    assert by_file["ablation_full_summary.json"]["started_at"] == "2026-07-10"
    assert [o["file"] for o in by_file["ablation_full_summary.json"]["outputs"]] == ["ablation_full_summary.json", "ablation_full_checkpoint.jsonl"]
    (comparison,) = [r for r in records if not r.get("unreadable") and r["kind"] == "comparison"]
    assert comparison["relations"]["compares"] == [by_file["ablation_full_summary.json"]["record_id"],
                                                   by_file["ablation_variance_summary.json"]["record_id"]]
    (sheet,) = [r for r in records if not r.get("unreadable") and r["kind"] == "sample"]
    assert sheet["build"]["base_build_id"] == "build-3b753e5e9297" and sheet["counts"] == {"items": 2, "labelled": 1}
    assert sheet["relations"]["sample_id"] is None and sheet["models"] == {"judge_model": "claude-opus-4-8"}
    store = EvaluationRecordStore(tmp_path / "dumps")
    for r in records:
        p = pe.present_evaluation(r, store, NOW)
        assert not list(_validator("presented_record").iter_errors(p)), p["record_id"]
        assert p["synthesised"] and p["provenance"]["outcome"] == "unavailable"
        assert all(o["copy_state"] == "not_kept" for o in p["outputs"])
    p2 = pe.present_evaluation(run2, store, NOW)
    assert p2["provenance"]["started_at"] == "derived"
    assert p2["reasons"]["started_at"].startswith("date stated by eval/results/RUN2_ANALYSIS.md (Date: 2026-07-09")
    assert p2["provenance"]["build"] == "unavailable" and p2["reasons"]["build"].startswith("not recorded: the summary")
    p1 = pe.present_evaluation(run1, store, NOW)
    assert p1["provenance"]["started_at"] == "unavailable"
    psheet = pe.present_evaluation(sheet, store, NOW)
    assert psheet["provenance"]["relations"] == "unavailable" and psheet["reasons"]["relations"].startswith("not recorded")


def test_legacy_synthesis_skips_the_outputs_of_recorded_runs(tmp_path):
    root = _legacy_root(tmp_path)
    store = EvaluationRecordStore(tmp_path / "dumps")
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[], build=_build())
    ref = store.keep_output(rid, "summary", root / "eval" / "results" / "ablation_summary.json")
    store.finish(rid, status="completed", outputs=[ref])
    sheet_path = root / "eval" / "gold" / "judge_label_sheet.json"
    sheet = json.loads(sheet_path.read_text())
    sheet["sample"] = {"sample_id": "sample-000000000000", "record_id": rid}
    sheet_path.write_text(json.dumps(sheet))
    files = {r["outputs"][0]["file"] for r in pe.synthesise_legacy_evaluations(root, store) if not r.get("unreadable")}
    assert "ablation_summary.json" not in files and "judge_label_sheet.json" not in files, "recorded outputs are not legacy"
    assert "ablation_run1_summary.json" in files


def test_legacy_synthesis_without_dates_and_with_a_malformed_file(tmp_path):
    root = _legacy_root(tmp_path, with_dates=False)
    (root / "eval" / "results" / "ablation_summary.json").write_text("{")
    records = pe.synthesise_legacy_evaluations(root)
    bad = [r for r in records if r.get("unreadable")]
    assert len(bad) == 1 and "JSONDecodeError" in bad[0]["reason"] and bad[0]["record_id"].startswith("legacy-")
    good = [r for r in records if not r.get("unreadable") and r["kind"] == "run"]
    assert len(good) == 3 and all(r["started_at"] is None for r in good)
    store = EvaluationRecordStore(tmp_path / "dumps")
    p = pe.present_evaluation(good[0], store, NOW)
    assert p["reasons"]["started_at"] == "not recorded: no analysis file states a date for this summary"


def test_legacy_synthesis_over_the_real_checkout_names_the_july_files():
    records = pe.synthesise_legacy_evaluations(ROOT)
    files = {o["file"] for r in records if not r.get("unreadable") for o in r["outputs"]}
    assert {"ablation_run1_summary.json", "ablation_summary.json", "ablation_full_summary.json",
            "ablation_variance_summary.json", "variance_study.md", "judge_label_sheet.json"} <= files
    runs = {r["outputs"][0]["file"]: r for r in records if not r.get("unreadable") and r["kind"] == "run"}
    assert runs["ablation_run1_summary.json"]["started_at"] is None and runs["ablation_summary.json"]["started_at"] == "2026-07-09"
    assert runs["ablation_full_summary.json"]["started_at"] == "2026-07-10"
    assert runs["ablation_variance_summary.json"]["started_at"] == "2026-07-11"
    assert runs["ablation_full_summary.json"]["models"] == {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}
    (comparison,) = [r for r in records if not r.get("unreadable") and r["kind"] == "comparison"]
    assert comparison["relations"]["compares"] == [runs["ablation_full_summary.json"]["record_id"],
                                                   runs["ablation_variance_summary.json"]["record_id"]]
    (sheet,) = [r for r in records if not r.get("unreadable") and r["kind"] == "sample"]
    assert sheet["counts"] == {"items": 50, "labelled": 0}

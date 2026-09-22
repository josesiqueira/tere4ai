"""Checkpoint lines carry a run id; a resume validates what it inherits (D-G20)."""

from __future__ import annotations

import json

import pytest

from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.checkpoints import (
    CheckpointError,
    IncompatibleCheckpointError,
    StaleCheckpointError,
    prepare_resume,
    progress,
    read_checkpoint,
    repair_tail,
    unique_results,
)

RESULT = {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}
KEYS = ("assertions", "mapping_runs", "judge_runs", "stats")


def _line(key, run_id="r1", result=RESULT):
    d = {"batch": key, "result": result}
    if run_id:
        d["run_id"] = run_id
    return json.dumps(d)


def test_read_separates_legacy_and_flags_tail_versus_middle(tmp_path):
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", None) + "\n" + _line("b1") + "\n" + '{"run_id": "r1", "batch": "b2', encoding="utf-8")
    r = read_checkpoint(ck, "batch", KEYS)
    assert [e["batch"] for e in r.entries] == ["b0", "b1"] and r.legacy_keys == ["b0"]
    assert r.skipped_tail == 1 and r.corrupt_middle is False
    ck.write_text(_line("b0") + "\n" + "garbage\n" + _line("b1") + "\n", encoding="utf-8")
    assert read_checkpoint(ck, "batch", KEYS).corrupt_middle is True
    ck.write_text(json.dumps({"run_id": "r1", "batch": "b0", "result": {"assertions": []}}) + "\n", encoding="utf-8")
    assert read_checkpoint(ck, "batch", KEYS).entries == [], "a result lacking a required key is not valid"


def test_repair_tail_truncates_only_a_damaged_last_line(tmp_path):
    ck = tmp_path / "x.checkpoint.jsonl"
    good = _line("b0") + "\n" + _line("b1") + "\n"
    ck.write_text(good + '{"run_id": "r1", "batch": "b2"', encoding="utf-8")
    removed = repair_tail(ck, "batch", KEYS)
    assert removed > 0 and ck.read_text(encoding="utf-8") == good
    ck.write_text(good + json.dumps({"run_id": "r1", "batch": "b2", "result": {"assertions": []}}) + "\n", encoding="utf-8")
    assert repair_tail(ck, "batch", KEYS) > 0 and ck.read_text(encoding="utf-8") == good, "a shape-invalid last line is a tail too"
    ck.write_text(_line("b0") + "\n" + "garbage\n" + _line("b1") + "\n", encoding="utf-8")
    with pytest.raises(CheckpointError, match="not confined"):
        repair_tail(ck, "batch", KEYS)


def test_unique_results_newest_wins():
    entries = [{"batch": "a", "result": {"n": 1}}, {"batch": "b", "result": {"n": 2}}, {"batch": "a", "result": {"n": 3}}]
    assert unique_results(entries, "batch") == {"a": {"batch": "a", "result": {"n": 3}}, "b": {"batch": "b", "result": {"n": 2}}}


def _record_with_run(tmp_path, config, inputs, run_id_holder):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    run = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1"], argv=[], inputs=inputs,
                                config=config, expected_total=3, work_unit="batches", checkpoint_file="x.checkpoint.jsonl")
    run_id_holder.append(run)
    return store, rid


def test_prepare_resume_refuses_stale_without_resume_and_validates_compatibility(tmp_path):
    holder: list[str] = []
    cfg = {"prompt_version": "v1", "batch_size": 2}
    inputs = [{"role": "norms", "file": "n.json", "sha256": "n" * 64}]
    store, rid = _record_with_run(tmp_path, cfg, inputs, holder)
    run = holder[0]
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", run) + "\n", encoding="utf-8")
    with pytest.raises(StaleCheckpointError):
        prepare_resume(ck, "batch", KEYS, resume=False, accept_legacy=False, store=store, record_id=rid,
                       expected_config=cfg, expected_inputs=inputs)
    plan = prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                          expected_config=cfg, expected_inputs=inputs)
    assert plan.inherited_keys == ["b0"] and plan.resumes_run_id == run and plan.inherited_from == run
    with pytest.raises(IncompatibleCheckpointError, match="batch_size"):
        prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                       expected_config={"prompt_version": "v1", "batch_size": 5}, expected_inputs=inputs)
    with pytest.raises(IncompatibleCheckpointError, match="norms"):
        prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                       expected_config=cfg, expected_inputs=[{"role": "norms", "file": "n.json", "sha256": "m" * 64}])
    ck.write_text(_line("b0", "unknown00000") + "\n", encoding="utf-8")
    with pytest.raises(IncompatibleCheckpointError, match="does not know"):
        prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                       expected_config=cfg, expected_inputs=inputs)


def test_prepare_resume_legacy_lines_need_explicit_acceptance(tmp_path):
    holder: list[str] = []
    store, rid = _record_with_run(tmp_path, {}, [], holder)
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", None) + "\n" + _line("b1", None) + "\n", encoding="utf-8")
    with pytest.raises(IncompatibleCheckpointError, match="accept-legacy"):
        prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                       expected_config={}, expected_inputs=[])
    plan = prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=True, store=store, record_id=rid,
                          expected_config={}, expected_inputs=[])
    assert plan.inherited_keys == ["b0", "b1"] and plan.inherited_from == "legacy" and plan.resumes_run_id is None


def test_prepare_resume_repairs_tail_and_reports_bytes(tmp_path):
    holder: list[str] = []
    store, rid = _record_with_run(tmp_path, {}, [], holder)
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", holder[0]) + "\n" + '{"run_id": "', encoding="utf-8")
    plan = prepare_resume(ck, "batch", KEYS, resume=True, accept_legacy=False, store=store, record_id=rid,
                          expected_config={}, expected_inputs=[])
    assert plan.repaired_tail_bytes == len('{"run_id": "') and ck.read_text().endswith("\n")


def test_progress_is_attempt_specific(tmp_path):
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", "old") + "\n" + _line("b1", "new") + "\n" + _line("b1", "new") + "\n", encoding="utf-8")
    old = {"run_id": "old", "inherited_keys": [], "inherited_from": None, "completed_keys": [], "expected_total": 3, "work_unit": "batches"}
    new = {"run_id": "new", "inherited_keys": ["b0"], "inherited_from": "old", "completed_keys": [], "expected_total": 3, "work_unit": "batches"}
    assert progress(old, ck, "batch", KEYS)["completed"] == 1, "the earlier attempt does not acquire later work"
    assert progress(new, ck, "batch", KEYS) == {"completed": 2, "expected_total": 3, "work_unit": "batches", "inherited": 1, "source": "checkpoint"}
    legacy = {"run_id": None, "inherited_keys": ["b0", "b1"], "inherited_from": "legacy", "completed_keys": [], "expected_total": None, "work_unit": "batches"}
    assert progress(legacy, ck, "batch", KEYS)["completed"] == 2
    ck.unlink()
    new["completed_keys"] = ["b1", "b2"]
    assert progress(new, ck, "batch", KEYS) == {"completed": 3, "expected_total": 3, "work_unit": "batches", "inherited": 1, "source": "record"}


def test_prepare_resume_refuses_other_models_or_prompts(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("t", "b", None)
    models = {"generator_model": "g", "judge_model": "j"}
    prompts = {"generator": "1" * 64, "judge": "2" * 64}
    run = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1"], argv=[], inputs=[], config={},
                                expected_total=1, work_unit="batches", checkpoint_file="x.checkpoint.jsonl",
                                models=models, prompt_sha256=prompts)
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", run) + "\n", encoding="utf-8")
    common = {"resume": True, "accept_legacy": False, "store": store, "record_id": rid, "expected_config": {},
              "expected_inputs": []}
    plan = prepare_resume(ck, "batch", KEYS, expected_models=models, expected_prompt_sha256=prompts, **common)
    assert plan.resumes_run_id == run
    with pytest.raises(IncompatibleCheckpointError, match="models: judge_model"):
        prepare_resume(ck, "batch", KEYS, expected_models={**models, "judge_model": "j2"},
                       expected_prompt_sha256=prompts, **common)
    with pytest.raises(IncompatibleCheckpointError, match="prompt_sha256: generator"):
        prepare_resume(ck, "batch", KEYS, expected_models=models,
                       expected_prompt_sha256={**prompts, "generator": "3" * 64}, **common)


def test_progress_of_an_ended_execution_comes_from_its_record(tmp_path):
    ck = tmp_path / "x.checkpoint.jsonl"
    ck.write_text(_line("b0", "later") + "\n", encoding="utf-8")  # a later run reused the path
    done = {"run_id": "early", "status": "done", "inherited_keys": [], "inherited_from": None,
            "completed_keys": ["b0", "b1", "b2"], "expected_total": 3, "work_unit": "batches"}
    assert progress(done, ck, "batch", KEYS) == {"completed": 3, "expected_total": 3, "work_unit": "batches",
                                                 "inherited": 0, "source": "record"}
    failed = {**done, "status": "failed", "completed_keys": ["b0"], "inherited_keys": ["a0"]}
    assert progress(failed, ck, "batch", KEYS)["completed"] == 2 and progress(failed, ck, "batch", KEYS)["source"] == "record"
    running = {**done, "status": "running", "run_id": "later", "completed_keys": []}
    assert progress(running, ck, "batch", KEYS)["source"] == "checkpoint"

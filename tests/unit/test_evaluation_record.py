"""The evaluation record store (D-G33, DEC-17): begin, finish, copies, locks, lookups, read-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tere4ai.eval import evaluation_record as er
from tere4ai.eval.evaluation_record import EvaluationRecordError, EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "evaluation_record.schema.json").read_text())


def _validator(definition):
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


def _inputs(tmp_path):
    a = tmp_path / "layer1.json"
    a.write_text('{"build": {"build_id": "build-b"}}')
    return [er.file_ref("layer1_dump", a)]


def test_begin_writes_a_running_record_that_validates(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=["--summary", "s.json", "--key", "sk-secret"],
                      inputs=_inputs(tmp_path), build={"base_build_id": "build-b", "publication": None,
                                                        "publication_reason": "no pointer"},
                      models={"generator_model": "g", "judge_model": "j"}, config={"strategies": ["plain_llm"]},
                      item_selection=["i1", "i2"], intended_items=["i1", "i2"])
    assert er.RECORD_FILE_STEM.match(rid)
    rec = store.read(rid)
    assert not list(_validator("stored_record").iter_errors(rec))
    assert rec["outcome"] == {"status": "running", "intended_items": ["i1", "i2"], "completed_items": [], "error": None}
    assert rec["ended_at"] is None and rec["argv"][-1] != "sk-secret", "argv is scrubbed"
    assert rec["item_selection_sha256"] == er.digest_of_ids(["i1", "i2"])
    assert rec["relations"] == {"repeat_of": None, "resumes_record_id": None, "compares": [], "sample_id": None,
                                "labelling_record_ids": []}


def test_finish_records_outcome_outputs_and_usage_and_is_final(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[],
                      build={"base_build_id": None, "publication": None, "publication_reason": "x"},
                      intended_items=["i1", "i2"])
    out = tmp_path / "ablation_summary.json"
    out.write_text("{}")
    ref = store.keep_output(rid, "summary", out)
    assert ref["copy"] == f"{rid}/summary.json" and (store.dir / ref["copy"]).read_text() == "{}"
    store.finish(rid, status="partial", completed_items=["i1"], intended_items=["i1", "i2", "i3"], outputs=[ref],
                 usage={"generator": {"calls": 1}}, counts={"items_total": 2}, notes=["n"])
    rec = store.read(rid)
    assert rec["outcome"]["status"] == "partial" and rec["outcome"]["completed_items"] == ["i1"]
    assert rec["outcome"]["intended_items"] == ["i1", "i2", "i3"], "finish may replace the intended set"
    assert rec["ended_at"] is not None and rec["outputs"] == [ref] and rec["usage"] == {"generator": {"calls": 1}}
    with pytest.raises(EvaluationRecordError, match="already ended"):
        store.finish(rid, status="completed")
    with pytest.raises(EvaluationRecordError, match="exists"):
        store.keep_output(rid, "summary", out)


def test_keep_output_leaves_no_temp_file_and_still_refuses_a_second_copy(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="x", argv=[], inputs=[],
                      build={"base_build_id": None, "publication": None, "publication_reason": None})
    out = tmp_path / "ablation_summary.json"
    out.write_text("{}")
    store.keep_output(rid, "summary", out)
    record_dir = store.dir / rid
    assert not [p.name for p in record_dir.iterdir() if p.name.startswith("tmp")]
    with pytest.raises(EvaluationRecordError, match="exists"):
        store.keep_output(rid, "summary", out)


def test_finish_rejects_an_unknown_status_and_an_unknown_record(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="sample", step="E1", command="sample_judge_decisions", argv=[], inputs=[],
                      build={"base_build_id": "b", "publication": None, "publication_reason": None})
    with pytest.raises(EvaluationRecordError, match="status"):
        store.finish(rid, status="running")
    with pytest.raises(EvaluationRecordError, match="no evaluation record"):
        store.read("000000000000")


def test_read_only_store_never_creates_and_never_writes(tmp_path):
    store = EvaluationRecordStore(tmp_path, create=False)
    assert not (tmp_path / "evaluation_records").exists()
    assert store.list_records() == []
    with pytest.raises(EvaluationRecordError, match="read-only"):
        store.begin(kind="run", step="E6", command="x", argv=[], inputs=[],
                    build={"base_build_id": None, "publication": None, "publication_reason": None})


def test_list_marks_unreadable_and_invalid_records_without_dropping_the_list(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="x", argv=[], inputs=[],
                      build={"base_build_id": None, "publication": None, "publication_reason": None})
    (store.dir / "0000000b0000.json").write_text("{", encoding="utf-8")
    (store.dir / "0000000c0000.json").write_text(json.dumps({"schema_version": "evaluation_record.v1"}))
    (store.dir / "notarecord.json").write_text("{}")
    rows = {r["record_id"]: r for r in store.list_records()}
    assert set(rows) == {rid, "0000000b0000", "0000000c0000"}
    assert rows["0000000b0000"]["unreadable"] and "not readable JSON" in rows["0000000b0000"]["reason"]
    assert rows["0000000c0000"]["unreadable"] and "required" in rows["0000000c0000"]["reason"]


def test_lookups_by_output_file_digest_and_input_digest(tmp_path):
    store = EvaluationRecordStore(tmp_path)
    src = tmp_path / "layer1.json"
    src.write_text("x")
    inp = er.file_ref("layer1_dump", src)
    rid1 = store.begin(kind="run", step="E6", command="x", argv=[], inputs=[inp],
                       build={"base_build_id": None, "publication": None, "publication_reason": None})
    out = tmp_path / "ablation_checkpoint.jsonl"
    out.write_text("l1\n")
    ref1 = store.keep_output(rid1, "checkpoint", out)
    store.finish(rid1, status="completed", outputs=[ref1])
    rid2 = store.begin(kind="run", step="E6", command="x", argv=[], inputs=[],
                       build={"base_build_id": None, "publication": None, "publication_reason": None})
    assert store.find_by_output_file("ablation_checkpoint.jsonl") == rid1, "a running record never answers"
    assert store.find_by_output_digest(ref1["sha256"]) == rid1
    assert store.find_by_input_digest(inp["sha256"]) == rid1
    assert store.find_by_output_file("nope") is None
    store.finish(rid2, status="failed", error="boom")


def test_observe_publication_and_served_paths_follow_the_pointer_or_the_legacy_names(tmp_path):
    pub, reason = er.observe_publication(tmp_path)
    assert pub is None and reason.startswith("no ACTIVE_MANIFEST.json")
    assert er.served_input_paths(tmp_path) == {"layer1_dump": tmp_path / "layer1.json", "norms": tmp_path / "norms_core.json",
                                               "alignments": tmp_path / "alignments_core.json"}
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-abc.json").write_text(json.dumps(
        {"build_id": "build-b+chain-abc", "files": {"layer1_dump": "layer1.json", "norms": "norms_core.reference.json"}}))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-abc"}))
    pub, reason = er.observe_publication(tmp_path)
    assert reason is None and pub["build_id"] == "build-b+chain-abc" and pub["manifest_file"].endswith("chain-abc.json")
    assert pub["sha256"] == er.sha256_of_file(tmp_path / "publications" / "chain-abc.json")
    assert er.served_input_paths(tmp_path) == {"layer1_dump": tmp_path / "layer1.json",
                                               "norms": tmp_path / "norms_core.reference.json"}


def test_code_version_is_a_short_sha_or_none(tmp_path):
    assert er.code_version(tmp_path) is None
    assert len(er.code_version(ROOT) or "") == 12


def test_two_processes_cannot_interleave_a_finish(tmp_path):
    import multiprocessing as mp

    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="x", argv=[], inputs=[],
                      build={"base_build_id": None, "publication": None, "publication_reason": None})

    def worker(path, record_id, note, q):
        s = EvaluationRecordStore(path)
        try:
            s.finish(record_id, status="completed", notes=[note])
            q.put("ok")
        except EvaluationRecordError as exc:
            q.put(str(exc))

    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(tmp_path, rid, f"n{i}", q)) for i in range(2)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    results = sorted(q.get() for _ in ps)
    assert results[0] != "ok" and results[1] == "ok", "exactly one finish wins under the lock"

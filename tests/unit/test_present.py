"""The presenter and the legacy synthesis: provenance per field, steps, nothing invented (D-G25)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tere4ai.graph_store.build_chain import build_chain, sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import (
    present_record,
    step_states,
    summary_of,
    synthesise_legacy_records,
)

NOW = datetime(2026, 9, 19, tzinfo=UTC)


def test_steps_prefer_the_newest_execution_and_share_the_parse(tmp_path):
    store = BuildRecordStore(tmp_path)
    parse = store.create_record("parse-x", None, None)
    run = store.start_execution(parse, command="parse_legal_structure", covers_steps=["L0.1", "L1.1"], argv=[], inputs=[],
                                config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(parse, run, status="done", outputs=[{"role": "layer1_dump", "file": "layer1.json", "sha256": "L" * 64}])
    rid = store.create_record("core", "b", "L" * 64)
    first = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                                  expected_total=2, work_unit="groups", checkpoint_file="norms_core.checkpoint.jsonl")
    store.finish_execution(rid, first, status="failed", error="x")
    second = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                                   expected_total=2, work_unit="groups", checkpoint_file="norms_core.checkpoint.jsonl",
                                   resumes_run_id=first, inherited_from=first)
    steps, depends, parse_id = step_states(store.read(rid), store, tmp_path)
    assert steps["L2.1"] == "running" and steps["L0.1"] == "done_shared" and parse_id == parse
    assert steps["L3.1"] == "not_started"
    assert depends["L3.1"] == "running"
    assert "L1.1" not in depends, "a shared parse step is done, not pending"
    assert steps["P.1"] == "not_started" and depends["P.1"] == "not_started"
    store.finish_execution(rid, second, status="done")
    assert step_states(store.read(rid), store, tmp_path)[0]["L2.2"] == "done"


def test_done_needs_the_artefact_with_the_recorded_digest(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    out = tmp_path / "norms_core.json"
    out.write_text("{}")
    run = store.start_execution(rid, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                                expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=[{"role": "norms", "file": "norms_core.json", "sha256": sha256_of_file(out)}])
    reasons: dict = {}
    assert step_states(store.read(rid), store, tmp_path, reasons)[0]["L2.2"] == "done" and not reasons
    out.write_text('{"edited": true}')
    steps = step_states(store.read(rid), store, tmp_path, reasons)[0]
    assert steps["L2.1"] == steps["L2.2"] == "failed"
    assert reasons["L2.2"] == "artefact norms_core.json drifted from the recorded digest"
    out.unlink()
    p = present_record(store.read(rid), tmp_path, NOW, None, store)
    assert p["steps"]["L2.1"] == "failed" and p["reasons"]["L2.1"] == "artefact norms_core.json missing"


def test_present_marks_recorded_unavailable_and_derived(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    run = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1", "L3.2", "L3.3"], argv=["--norms", "n"],
                                inputs=[], config={"batch_size": 20}, expected_total=26, work_unit="batches",
                                checkpoint_file="alignments_core.checkpoint.jsonl")
    ck = tmp_path / "alignments_core.checkpoint.jsonl"
    ck.write_text("".join(json.dumps({"run_id": run, "batch": f"batch:{i}:n", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n" for i in range(0, 300, 20)))
    p = present_record(store.read(rid), tmp_path, NOW, None, store)
    ex = p["executions"][0]
    assert ex["liveness"] in ("live", "unknown") and ex["progress"]["completed"] == 15 and ex["progress"]["source"] == "checkpoint"
    assert ex["provenance"]["argv"] == "recorded" and ex["provenance"]["models"] == "unavailable"
    assert ex["reasons"]["models"] == "not recorded by the command" and ex["provenance"]["progress"] == "derived"
    assert p["provenance"]["steps"] == "derived" and p["provenance"]["layer1_digest"] == "unavailable"
    assert p["served"] is False and p["synthesised"] is False and p["steps"]["L3.1"] == "running"
    assert all(p["reasons"].get(k) for k, v in p["provenance"].items() if v == "unavailable"), "every null carries a reason"
    s = summary_of(p)
    assert s["record_id"] == rid and s["steps"]["L3.1"] == "running" and s["publication"] is None and s["unreadable"] is False


def test_legacy_synthesis_matches_the_full_input_set_and_invents_nothing(tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [{"id": "n", "type": "Article"}], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({
        "build": {"build_id": "build-b", "extraction_models": {"generator_model": "g", "judge_model": "j"}, "prompt_version": "v1"},
        "norms": [], "judge_runs": [{"prompt_sha256": "abc"}],
        "stats": {"source_units": 405, "candidates": 442, "verdicts": {"accepted": 339}, "nodes_failed": [], "invalid_norms": []}}))
    (tmp_path / "alignments_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "assertions": [], "stats": {"norms_total": 1}}))
    (tmp_path / "norms_core.b74.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": [], "stats": {}}))
    (tmp_path / "alignments_core.b74.json").write_bytes(b"")
    (tmp_path / "alignments_core.b74.checkpoint.jsonl").write_text("".join(json.dumps({"batch": f"batch:{i}:n", "result": {}}) + "\n" for i in range(0, 300, 20)))
    full = build_chain(tmp_path / "layer1.json", tmp_path / "norms_core.json", alignments_path=tmp_path / "alignments_core.json")
    (tmp_path / f"build_chain_{full['chain_id']}.json").write_text(json.dumps({"build_id": "build-b+chain-" + full["chain_id"], **full}))
    partial = build_chain(tmp_path / "layer1.json", tmp_path / "norms_core.json")
    (tmp_path / f"build_chain_{partial['chain_id']}.json").write_text(json.dumps({"build_id": "build-b+chain-" + partial["chain_id"], **partial}))

    records = {r["aliases"][0]: r for r in synthesise_legacy_records(tmp_path)}
    assert not (tmp_path / "build_records").exists(), "the synthesis never creates the store"
    core = records["core"]
    assert core["record_id"] == "legacy-core" and core["synthesised"] and core["created_at"] is None
    assert core["publication"]["chain_id"] == full["chain_id"], "the record matching every present artefact, not the newest filename"
    assert core["publication"]["published_at"] is None and core["publication"]["gating"] == {"layer2": "llm", "layer3": "llm"}
    assert core["publication"]["gates"] is None and core["publication"]["postload_gates"] is None
    assert core["reasons"]["publication.gates"] == "not recorded before DEC-16"
    ex = next(e for e in core["executions"] if e["command"] == "extract_norms")
    assert ex["run_id"] is None and ex["models"] == {"generator_model": "g", "judge_model": "j"} and ex["usage"] is None
    assert ex["prompt_sha256"] == {"generator": None, "judge": "abc"} and ex["counts"]["candidates"] == 442
    b74 = records["core.b74"]
    align = next(e for e in b74["executions"] if e["command"] == "align_hleg_altai")
    assert align["status"] == "running" and align["heartbeat_at"] is None and align["inherited_from"] == "legacy"
    assert len(align["inherited_keys"]) == 15 and align["expected_total"] is None and b74["publication"] is None
    p = present_record(b74, tmp_path, NOW, full["chain_id"], None)
    ex = next(e for e in p["executions"] if e["command"] == "align_hleg_altai")
    assert ex["liveness"] == "unknown" and ex["progress"] == {"completed": 15, "expected_total": None, "work_unit": "batches", "inherited": 15, "source": "checkpoint"}
    assert ex["provenance"]["run_id"] == "unavailable" and ex["reasons"]["run_id"] == "not recorded before DEC-16"
    assert ex["provenance"]["inherited_keys"] == "derived" and p["steps"]["P.1"] == "not_recorded"
    assert p["provenance"]["publication"] == "unavailable" and "no chain record" in p["reasons"]["publication"]
    pc = present_record(core, tmp_path, NOW, full["chain_id"], None)
    assert pc["served"] is True and pc["provenance"]["publication"] == "derived"
    assert present_record(core, tmp_path, NOW, "000000000000", None)["served"] is False


def test_unreadable_artefact_yields_not_recorded_with_a_reason(tmp_path):
    (tmp_path / "layer1.json").write_text("{broken")
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "norms": [], "judge_runs": [], "stats": {}}))
    record = synthesise_legacy_records(tmp_path)[0]
    assert all(e["command"] != "parse_legal_structure" for e in record["executions"])
    p = present_record(record, tmp_path, NOW, None, None)
    assert p["steps"]["L1.1"] == "not_recorded" and "unreadable" in p["reasons"]["L1.1"]


def test_a_stored_alias_suppresses_the_legacy_synthesis(tmp_path):
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "norms": [], "judge_runs": [], "stats": {}}))
    BuildRecordStore(tmp_path).create_record("core", "b", None)
    assert synthesise_legacy_records(tmp_path) == []

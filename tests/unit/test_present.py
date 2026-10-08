"""The presenter and the legacy synthesis: provenance per field, steps, nothing invented (D-G25, DEC-17)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from tere4ai.graph_store import present
from tere4ai.graph_store.build_chain import build_chain, sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import (
    exception_reason,
    lineage_of,
    present_record,
    step_states,
    summary_of,
    synthesise_legacy_records,
)

NOW = datetime(2026, 9, 19, tzinfo=UTC)


def test_steps_prefer_the_newest_execution_and_share_the_parse(tmp_path):
    store = BuildRecordStore(tmp_path)
    (tmp_path / "layer1.json").write_text("{}")
    layer1_digest = sha256_of_file(tmp_path / "layer1.json")
    parse = store.create_record("parse-x", None, None)
    run = store.start_execution(parse, command="parse_legal_structure", covers_steps=["LAYER0_STEP1", "LAYER1_STEP1"], argv=[], inputs=[],
                                config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(parse, run, status="done", outputs=[{"role": "layer1_dump", "file": "layer1.json", "sha256": layer1_digest}])
    rid = store.create_record("core", "b", layer1_digest)
    first = store.start_execution(rid, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[], config={},
                                  expected_total=2, work_unit="groups", checkpoint_file="norms_core.checkpoint.jsonl")
    store.finish_execution(rid, first, status="failed", error="x")
    second = store.start_execution(rid, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[], config={},
                                   expected_total=2, work_unit="groups", checkpoint_file="norms_core.checkpoint.jsonl",
                                   resumes_run_id=first, inherited_from=first)
    steps, depends, parse_id = step_states(store.read(rid), store, tmp_path)
    assert steps["LAYER2_STEP1"] == "running" and steps["LAYER0_STEP1"] == "inherited" and parse_id == parse
    assert steps["LAYER3_STEP1"] == "not_started"
    assert depends["LAYER3_STEP1"] == "running"
    assert "LAYER1_STEP1" not in depends, "a shared parse step is done, not pending"
    assert steps["PUBLICATION_STEP1"] == "not_started" and depends["PUBLICATION_STEP1"] == "not_started"
    store.finish_execution(rid, second, status="done")
    assert step_states(store.read(rid), store, tmp_path)[0]["LAYER2_STEP2"] == "done"


def test_done_needs_the_artefact_with_the_recorded_digest(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    out = tmp_path / "norms_core.json"
    out.write_text("{}")
    run = store.start_execution(rid, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[], config={},
                                expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=[{"role": "norms", "file": "norms_core.json", "sha256": sha256_of_file(out)}])
    reasons: dict = {}
    assert step_states(store.read(rid), store, tmp_path, reasons)[0]["LAYER2_STEP2"] == "done" and not reasons
    out.write_text('{"edited": true}')
    steps = step_states(store.read(rid), store, tmp_path, reasons)[0]
    assert steps["LAYER2_STEP1"] == steps["LAYER2_STEP2"] == "failed"
    assert reasons["LAYER2_STEP2"] == "artefact norms_core.json drifted from the recorded digest"
    out.unlink()
    p = present_record(store.read(rid), tmp_path, NOW, None, store)
    assert p["steps"]["LAYER2_STEP1"] == "failed" and p["reasons"]["LAYER2_STEP1"] == "artefact norms_core.json missing"


def test_present_marks_recorded_unavailable_and_derived(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    run = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=["--norms", "n"],
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
    assert p["served"] is False and p["synthesised"] is False and p["steps"]["LAYER3_STEP1"] == "running"
    assert all(p["reasons"].get(k) for k, v in p["provenance"].items() if v == "unavailable"), "every null carries a reason"
    s = summary_of(p)
    assert s["record_id"] == rid and s["steps"]["LAYER3_STEP1"] == "running" and s["publication"] is None and s["unreadable"] is False


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
    assert core["reasons"]["publication.published_at"] == core["reasons"]["publication.label"] == "not recorded before DEC-16"
    ex = next(e for e in core["executions"] if e["command"] == "extract_norms")
    assert ex["run_id"] is None and ex["models"] == {"generator_model": "g", "judge_model": "j"} and ex["usage"] is None
    assert ex["prompt_sha256"] == {"generator": None, "judge": "abc"} and ex["counts"]["candidates"] == 442
    b74 = records["core.b74"]
    align = next(e for e in b74["executions"] if e["command"] == "align_hleg")
    assert align["status"] == "running" and align["heartbeat_at"] is None and align["inherited_from"] == "legacy"
    assert len(align["inherited_keys"]) == 15 and align["expected_total"] is None and b74["publication"] is None
    p = present_record(b74, tmp_path, NOW, full["chain_id"], None)
    ex = next(e for e in p["executions"] if e["command"] == "align_hleg")
    assert ex["liveness"] == "unknown" and ex["progress"] == {"completed": 15, "expected_total": None, "work_unit": "batches", "inherited": 15, "source": "checkpoint"}
    assert ex["provenance"]["run_id"] == "unavailable" and ex["reasons"]["run_id"] == "not recorded before DEC-16"
    assert ex["provenance"]["inherited_keys"] == "derived" and p["steps"]["PUBLICATION_STEP1"] == "not_recorded"
    assert p["provenance"]["publication"] == "unavailable" and "no chain record" in p["reasons"]["publication"]
    pc = present_record(core, tmp_path, NOW, full["chain_id"], None)
    assert pc["served"] is True and pc["provenance"]["publication"] == "derived"
    assert pc["steps"]["PUBLICATION_STEP2"] == "not_recorded" and pc["steps"]["PUBLICATION_STEP1"] == "not_recorded", "a legacy chain record proves no recorded gate"
    assert pc["reasons"]["PUBLICATION_STEP1"] == ("a legacy chain record was written only after G1 to G6 passed; "
                                    "per-gate outcomes were not recorded before DEC-16")
    assert pc["reasons"]["PUBLICATION_STEP2"] == ("the chain record predates the load; load and post-load gates "
                                    "were not recorded before DEC-16")
    assert p["steps"]["PUBLICATION_STEP2"] == "not_recorded" and p["steps"]["PUBLICATION_STEP1"] == "not_recorded"
    assert present_record(core, tmp_path, NOW, "000000000000", None)["served"] is False


def test_derived_execution_carries_effort_beside_sampling(tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({
        "build": {"build_id": "build-b",
                  "extraction_models": {"generator_model": "g", "judge_model": "j",
                                        "generator_effort": "xhigh", "judge_effort": "xhigh"},
                  "extraction_sampling": {"generator": "0", "judge": "0"},
                  "extraction_effort": {"generator": "xhigh", "judge": "not applicable (rejected by the model)"},
                  "prompt_version": "v1"},
        "norms": [], "judge_runs": [],
        "stats": {"source_units": 0, "candidates": 0, "verdicts": {}, "nodes_failed": [], "invalid_norms": []}}))
    records = synthesise_legacy_records(tmp_path)
    core = next(r for r in records if r["aliases"][0] == "core")
    ex = next(e for e in core["executions"] if e["command"] == "extract_norms")
    assert ex["models"] == {"generator_model": "g", "judge_model": "j",
                            "generator_effort": "xhigh", "judge_effort": "xhigh"}
    assert ex["sampling"] == {"generator": "0", "judge": "0",
                              "generator_effort": "xhigh", "judge_effort": "not applicable (rejected by the model)"}


def test_derived_execution_builds_sampling_from_effort_alone_when_sampling_is_absent(tmp_path):
    """B84 fix wave G8: extraction_effort present with no extraction_sampling
    (present.py:515-523 _sampling_with_effort) must still surface the effort,
    never silently drop it because the sibling sampling dict is missing."""
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({
        "build": {"build_id": "build-b",
                  "extraction_models": {"generator_model": "g", "judge_model": "j"},
                  "extraction_effort": {"generator": "xhigh", "judge": "not applicable (rejected by the model)"},
                  "prompt_version": "v1"},
        "norms": [], "judge_runs": [],
        "stats": {"source_units": 0, "candidates": 0, "verdicts": {}, "nodes_failed": [], "invalid_norms": []}}))
    records = synthesise_legacy_records(tmp_path)
    core = next(r for r in records if r["aliases"][0] == "core")
    ex = next(e for e in core["executions"] if e["command"] == "extract_norms")
    assert ex["sampling"] == {
        "generator_effort": "xhigh",
        "judge_effort": "not applicable (rejected by the model)",
    }


def test_unreadable_artefact_yields_not_recorded_with_a_reason(tmp_path):
    (tmp_path / "layer1.json").write_text("{broken")
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "norms": [], "judge_runs": [], "stats": {}}))
    record = synthesise_legacy_records(tmp_path)[0]
    assert all(e["command"] != "parse_legal_structure" for e in record["executions"])
    p = present_record(record, tmp_path, NOW, None, None)
    assert p["steps"]["LAYER1_STEP1"] == "not_recorded" and "unreadable" in p["reasons"]["LAYER1_STEP1"]


def test_a_stored_alias_suppresses_the_legacy_synthesis(tmp_path):
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "norms": [], "judge_runs": [], "stats": {}}))
    BuildRecordStore(tmp_path).create_record("core", "b", None)
    assert synthesise_legacy_records(tmp_path) == []


PUB = {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
       "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [], "postload_gates": [],
       "manifests": []}


def _done(store, rid, command, steps, outputs, inputs=()):
    run = store.start_execution(rid, command=command, covers_steps=steps, argv=[], inputs=list(inputs), config={},
                                expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done", outputs=outputs)


def _out(tmp_path, name, role, text):
    (tmp_path / name).write_text(text)
    return {"role": role, "file": name, "sha256": sha256_of_file(tmp_path / name)}


def test_lineage_steps_are_inherited_only_while_the_ancestor_artefact_stands(tmp_path):
    store = BuildRecordStore(tmp_path)
    layer1 = _out(tmp_path, "layer1.json", "layer1_dump", "{}")
    parent = store.create_record("core", "b", layer1["sha256"])
    _done(store, parent, "parse_legal_structure", ["LAYER0_STEP1", "LAYER1_STEP1"], [layer1])
    norms = _out(tmp_path, "norms_core.json", "norms", '{"norms": []}')
    _done(store, parent, "extract_norms", ["LAYER2_STEP1", "LAYER2_STEP2"], [norms])
    store.set_publication(parent, PUB)
    child = store.create_record("core.reference", "b", layer1["sha256"], parent_record_id=parent)
    ref = _out(tmp_path, "norms_core.reference.json", "norms_reference", '{"norms": [1]}')
    _done(store, child, "materialize_reference", ["LAYER2_STEP4"], [ref], inputs=[{**norms, "role": "norms"}])
    align = _out(tmp_path, "alignments_core.reference.json", "alignments", '{"assertions": []}')
    _done(store, child, "align_hleg", ["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], [align], inputs=[{**ref, "role": "norms"}])

    reasons: dict = {}
    steps, depends, parse_id = step_states(store.read(child), store, tmp_path, reasons)
    assert [steps[s] for s in ("LAYER0_STEP1", "LAYER1_STEP1", "LAYER2_STEP1", "LAYER2_STEP2")] == ["inherited"] * 4 and parse_id == parent
    assert all(reasons[s] == f"done in record {parent}" for s in ("LAYER0_STEP1", "LAYER1_STEP1", "LAYER2_STEP1", "LAYER2_STEP2"))
    assert steps["LAYER2_STEP4"] == steps["LAYER3_STEP3"] == "done" and steps["LAYER2_STEP3"] == "not_started"
    assert steps["PUBLICATION_STEP1"] == steps["PUBLICATION_STEP2"] == "not_started", "a publication is never inherited"
    assert depends["PUBLICATION_STEP1"] == "done" and depends["PUBLICATION_STEP2"] == "not_started" and depends["LAYER2_STEP3"] == "inherited"

    (tmp_path / "norms_core.json").unlink()
    reasons = {}
    steps = step_states(store.read(child), store, tmp_path, reasons)[0]
    assert steps["LAYER2_STEP1"] == steps["LAYER2_STEP2"] == "failed" and reasons["LAYER2_STEP1"] == "artefact norms_core.json missing"

    # parent_record_id alone: a descendant that has done nothing yet
    empty = store.create_record("core.next", "b", layer1["sha256"], parent_record_id=parent)
    reasons = {}
    steps = step_states(store.read(empty), store, tmp_path, reasons)[0]
    assert steps["LAYER1_STEP1"] == "inherited" and steps["LAYER2_STEP1"] == "failed" and steps["LAYER3_STEP1"] == "not_started"


def test_an_input_without_a_producing_record_is_not_recorded(tmp_path):
    store = BuildRecordStore(tmp_path)
    (tmp_path / "layer1.json").write_text("{}")
    norms = _out(tmp_path, "norms_core.b74.json", "norms", '{"norms": []}')
    rid = store.create_record("core.b74", "b", sha256_of_file(tmp_path / "layer1.json"))
    run = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=[],
                                inputs=[norms], config={}, expected_total=26, work_unit="batches", checkpoint_file=None)
    assert run
    reasons: dict = {}
    steps, _, parse_id = step_states(store.read(rid), store, tmp_path, reasons)
    assert steps["LAYER2_STEP1"] == steps["LAYER2_STEP2"] == steps["LAYER0_STEP1"] == steps["LAYER1_STEP1"] == "not_recorded" and parse_id is None
    assert reasons["LAYER2_STEP1"] == reasons["LAYER0_STEP1"] == "produced before DEC-16"
    assert steps["LAYER3_STEP1"] == "running" and steps["LAYER2_STEP3"] == "not_started"


def test_a_malformed_legacy_payload_yields_no_execution_and_a_reason(tmp_path):
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "stats": {}}))
    (tmp_path / "alignments_core.json").write_text(json.dumps({"build": {"build_id": "b"}, "assertions": "none"}))
    record = synthesise_legacy_records(tmp_path)[0]
    assert record["executions"] == []
    p = present_record(record, tmp_path, NOW, None, None)
    assert p["steps"]["LAYER2_STEP1"] == p["steps"]["LAYER3_STEP1"] == "not_recorded"
    assert p["reasons"]["LAYER2_STEP2"] == "artefact malformed: norms_core.json"
    assert p["reasons"]["LAYER3_STEP3"] == "artefact malformed: alignments_core.json"


def test_lineage_of_names_inherited_records_and_consumed_freezes():
    presented = {
        "record_id": "r2", "aliases": [], "base_build_id": "b", "created_at": "t", "synthesised": False,
        "steps": {"LAYER0_STEP1": "inherited", "LAYER1_STEP1": "inherited", "LAYER2_STEP1": "inherited", "LAYER2_STEP2": "inherited", "LAYER2_STEP3": "done",
                  "LAYER2_STEP4": "done", "LAYER3_STEP1": "done", "LAYER3_STEP2": "done", "LAYER3_STEP3": "done", "LAYER3_STEP4": "none", "LAYER3_STEP5": "none",
                  "PUBLICATION_STEP1": "done", "PUBLICATION_STEP2": "done"},
        "reasons": {"LAYER0_STEP1": "done in record r1", "LAYER1_STEP1": "done in record r1", "LAYER2_STEP1": "done in record r1",
                    "LAYER2_STEP2": "unexpected wording"},
        "executions": [{"command": "materialize_reference", "status": "done", "covers_steps": ["LAYER2_STEP4"],
                        "inputs": [{"role": "freeze_manifest", "file": "m.json", "sha256": "7" * 64}]}],
        "publication": {"chain_id": "c", "label": None, "published_at": "t",
                        "manifests": [{"campaign_id": "camp", "freeze_id": "fz", "campaign_type": "layer2_annotation",
                                       "stage": "production", "decisions_sha256": "8" * 64, "layer": 2}]},
        "served": False,
    }
    lineage = lineage_of(presented)
    assert lineage["inherited_from"] == {"LAYER0_STEP1": "r1", "LAYER1_STEP1": "r1", "LAYER2_STEP1": "r1", "LAYER2_STEP2": None}
    assert lineage["consumed_freezes"] == [{"campaign_id": "camp", "freeze_id": "fz", "campaign_type": "layer2_annotation",
                                            "stage": "production", "layer": 2, "step": "LAYER2_STEP4", "manifest_sha256": None}]
    presented["publication"] = None
    assert lineage_of(presented)["consumed_freezes"] == [{"campaign_id": None, "freeze_id": None, "campaign_type": None,
                                                          "stage": None, "layer": None, "step": "LAYER2_STEP4",
                                                          "manifest_sha256": "7" * 64}]
    row = summary_of(presented)
    assert row["lineage"]["inherited_from"]["LAYER0_STEP1"] == "r1"
    assert summary_of({"record_id": "x", "unreadable": True, "reason": "r"})["lineage"] is None


def test_lineage_of_reads_consumed_freezes_from_a_real_publication(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core", "b", None)
    publication = {
        "chain_id": "c1", "build_id": "b+chain-c1", "published_at": "t",
        "gating": {"layer2": "human", "layer3": "llm"}, "label": "human-adjudicated",
        "gates": [], "postload_gates": [],
        "manifests": [{"campaign_id": "camp", "freeze_id": "fz", "campaign_type": "layer2_annotation",
                      "stage": "production", "decisions_sha256": "9" * 64, "layer": 2}],
    }
    store.set_publication(rid, publication)
    presented = present_record(store.read(rid), tmp_path, NOW, None, store)
    assert summary_of(presented)["lineage"]["consumed_freezes"] == [
        {"campaign_id": "camp", "freeze_id": "fz", "campaign_type": "layer2_annotation", "stage": "production",
         "layer": 2, "step": "LAYER2_STEP4", "manifest_sha256": None}]


# ---- B102 task 3 (B79 items 3 and 24)


def test_exception_reason_shortens_only_tokens_that_look_like_paths():
    assert "LAYER2_STEP1/LAYER2_STEP2" in exception_reason(ValueError("LAYER2_STEP1/LAYER2_STEP2 differ"))
    # B155: the step ids carry no dot now; a pair of them with one separator still reaches the reader whole
    assert exception_reason(ValueError("LAYER2_STEP1/LAYER2_STEP2 differ")) == (
        "ValueError: LAYER2_STEP1/LAYER2_STEP2 differ")
    reason = exception_reason(OSError("cannot read /tmp/a/b/norms.json"))
    assert "norms.json" in reason and "/tmp" not in reason
    assert exception_reason(OSError("cannot read C:\\x\\y.json")) == "OSError: cannot read y.json"
    assert exception_reason(OSError("cannot read data/graph_dumps/norms.json")) == "OSError: cannot read norms.json"
    assert exception_reason(OSError("cannot read ./norms.json or ~/norms.json")) == (
        "OSError: cannot read norms.json or norms.json")


def _legacy_core(tmp_path, stats=None, build=True):
    payload = {"norms": [], "judge_runs": []}
    if build:
        payload["build"] = {"build_id": "build-b"}
    if stats is not None:
        payload["stats"] = stats
    (tmp_path / "layer1.json").write_text(json.dumps({"nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps(payload))


def test_a_synthesised_record_gives_the_reasons_that_hold_whatever_was_recorded(tmp_path):
    _legacy_core(tmp_path, stats={"source_units": 1, "candidates": 1, "verdicts": {}})
    record = synthesise_legacy_records(tmp_path)[0]
    p = present_record(record, tmp_path, NOW, None, None)
    extract = next(e for e in p["executions"] if e["command"] == "extract_norms")
    assert extract["progress"] is None and extract["reasons"]["progress"] != "not recorded before DEC-16"
    assert extract["reasons"]["progress"] == "no checkpoint file recorded"
    assert extract["reasons"]["run_id"] == "not recorded before DEC-16", "what the record never held stays legacy"
    parse = next(e for e in p["executions"] if e["command"] == "parse_legal_structure")
    assert parse["reasons"]["models"] == "the command calls no model"
    assert parse["reasons"]["progress"] == "the command has no work units"
    assert p["parse_record_id"] is None and p["reasons"]["parse_record_id"] == "the record holds its own parse execution"


def test_a_matched_chain_without_a_build_id_has_its_own_reason(tmp_path):
    _legacy_core(tmp_path, build=False)
    chain = build_chain(tmp_path / "layer1.json", tmp_path / "norms_core.json")
    (tmp_path / f"build_chain_{chain['chain_id']}.json").write_text(json.dumps(chain))
    record = synthesise_legacy_records(tmp_path)[0]
    assert record["publication"] is None and record["base_build_id"] is None
    assert record["reasons"]["publication"] == "a chain record matches, but neither it nor the norms file names a build id"
    (tmp_path / f"build_chain_{chain['chain_id']}.json").unlink()
    assert synthesise_legacy_records(tmp_path)[0]["reasons"]["publication"] == (
        "no chain record matches the current artefacts")


def test_the_digest_cache_keeps_one_entry_per_path(tmp_path, monkeypatch):
    monkeypatch.setattr(present, "_DIGEST_CACHE", {})
    path = tmp_path / "norms_core.json"
    for i in range(3):
        path.write_text("x" * (i + 1))
        os.utime(path, ns=(1_000_000_000 * (i + 1), 1_000_000_000 * (i + 1)))
        assert present._digest(path) == sha256_of_file(path)
    assert len(present._DIGEST_CACHE) == 1


def test_a_counts_map_of_nulls_is_unavailable(tmp_path):
    _legacy_core(tmp_path)  # no stats block: every count reads null
    record = synthesise_legacy_records(tmp_path)[0]
    p = present_record(record, tmp_path, NOW, None, None)
    extract = next(e for e in p["executions"] if e["command"] == "extract_norms")
    assert set(extract["counts"].values()) == {None}
    assert extract["provenance"]["counts"] == "unavailable"
    assert extract["reasons"]["counts"] == "not recorded before DEC-16"


def test_a_materialise_execution_makes_l3_1_wait_on_l2_4(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.reference", "b", None)
    ref = _out(tmp_path, "norms_core.reference.json", "norms_reference", '{"norms": []}')
    run = store.start_execution(rid, command="materialize_reference", covers_steps=["LAYER2_STEP4"], argv=[], inputs=[],
                                config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    steps, depends, _ = step_states(store.read(rid), store, tmp_path)
    assert steps["LAYER2_STEP4"] == "running" and steps["LAYER3_STEP1"] == "not_started"
    assert depends["LAYER3_STEP1"] == steps["LAYER2_STEP4"] == "running", "LAYER3_STEP1 waits on LAYER2_STEP4, not on LAYER2_STEP2"
    store.finish_execution(rid, run, status="done", outputs=[ref])
    steps, depends, _ = step_states(store.read(rid), store, tmp_path)
    assert depends["LAYER3_STEP1"] == steps["LAYER2_STEP4"] == "done"


def test_a_legacy_checkpoint_with_a_damaged_middle_line_says_so(tmp_path):
    _legacy_core(tmp_path)
    lines = [json.dumps({"batch": f"batch:{i}:n", "result": {}}) for i in range(0, 60, 20)]
    lines.insert(1, "{damaged")
    (tmp_path / "alignments_core.checkpoint.jsonl").write_text("\n".join(lines) + "\n")
    record = synthesise_legacy_records(tmp_path)[0]
    p = present_record(record, tmp_path, NOW, None, None)
    assert p["steps"]["LAYER3_STEP1"] == "running"
    assert p["reasons"]["LAYER3_STEP1"].endswith("corrupt lines in the middle were skipped")

"""publish_layer23: evidence first, gates, load, post-load gates, then the chain record (D-G21, D-G27)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import read_target_state
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE
from tere4ai.review_queue.materialize import already_materialised

PAIR = load_pair()
LISTED = [{"id": f"srcfile:{TEXT_FILE}", "layer": 0, "type": "SourceFile", "file": TEXT_FILE, "sha256": PAIR.text_sha256},
          {"id": f"srcfile:{RECORD_FILE}", "layer": 0, "type": "SourceFile", "file": RECORD_FILE, "sha256": PAIR.record_sha256}]

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


def _files(tmp_path, *, reference=None, align_input=True, judge_runs=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    norms_payload = {"build": {"build_id": "build-b"}, "norms": [], "judge_runs": judge_runs or []}
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


def _fakes(monkeypatch, cli, *, gates_ok=True, postload_ok=True, load_raises=False, seen=None,
           real_norms_to_graph=False, capture=None):
    monkeypatch.setattr(cli, "validate_build", lambda dump, norms=None, alignments=None: _Report([] if gates_ok else ["G3 norm without source span: x"], {"layer1_nodes": 0}))
    if not real_norms_to_graph:
        monkeypatch.setattr(cli, "norms_to_graph", lambda payload, build_id: {"nodes": [], "edges": []})
    monkeypatch.setattr(cli, "alignments_to_graph", lambda payload, hleg, build_id: {"nodes": [], "edges": []})
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda pair=None: [])
    monkeypatch.setattr(cli, "build_hleg_subtopics", lambda build_id: {"nodes": [], "edges": [], "skipped": []})

    class FakeStore:
        def load_dump(self, dump, driver):
            if seen is not None:
                seen.append(("load", None))
            if capture is not None:
                capture.append(dump)
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


def test_published_judge_run_node_carries_the_judge_effort(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path, judge_runs=[{
        "id": "judgerun:x:1",
        "type": "JudgeRun",
        "layer": 3,
        "judge_kind": "extraction",
        "judge_model": "claude-test",
        "judge_effort": "high",
        "judge_temperature": "N/A",
        "prompt_version": "v1",
        "verdict": "accepted",
        "rationale": "grounded",
        "started_at": "t",
        "completed_at": "t",
        "build_id": "build-b",
        "scores": {"evidence_strength": 0.9},
    }])
    captured = []
    _fakes(monkeypatch, cli, real_norms_to_graph=True, capture=captured)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    assert rc == 0
    dump = captured[0]
    judge_run_node = next(n for n in dump["nodes"] if n["type"] == "JudgeRun")
    assert judge_run_node["judge_effort"] == "high"
    assert judge_run_node["judge_temperature"] == "N/A"


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
    # Changed by B98 seat B P2-1: the evidence steps now run before a
    # published record continues as a descendant, so the refused attempt
    # makes no descendant and the alias stays on the published record.
    assert not [r for r in store.list_records() if r.get("parent_record_id") == rid], "no descendant record"
    assert store.resolve("core.reference") == rid


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
    target = read_target_state(tmp_path)
    assert target["state"] == "unavailable" and "does not validate" in target["reason"], "never available unpublished"


NORM = {
    "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1", "layer": 2, "type": "NormativeStatement",
    "source_node_id": "eu-ai-act:article-9:paragraph-1", "source_span_id": "span:x", "deontic_type": "obligation",
    "modal": "shall", "actor_explicit": "providers", "actor_inferred": None, "actor_inference_source_node_id": None,
    "action": "establish", "object": "a risk management system", "conditions": [], "exceptions": [],
    "condition_ids": [], "exception_ids": [], "lifecycle_phase_ids": [], "extraction_method": "llm_extract_v1",
    "extractor_model": "g", "extractor_prompt_version": "v1", "confidence": 0.9, "judge_verdict": "accepted",
    "judge_run_id": "judgerun:x", "review_status": "accepted", "source_text": "t",
}
PINNED = "build-b+chain-000000000000"


def _script(name):
    spec = importlib.util.spec_from_file_location(f"{name}_w3", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _align_fakes(monkeypatch, cli):
    def fake_align(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        return {"assertions": [{"id": f"align:{c['norm_id']}"} for c in chunk], "mapping_runs": [], "judge_runs": [],
                "stats": {"norms_total": len(chunk), "verdicts": {"accepted": len(chunk)}, "mechanical_rejects": []}}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j"}

    class FakeClient:
        sampling = "0"
        temperature = "0"
        json_mode = "sent"
        usage = {"calls": 1, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(cli, "align_norms", fake_align)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    # B99 (spec F D-F30): the command builds its clients with the terminal policy, a keyword the fakes accept
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kwargs: FakeClient())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kwargs: FakeClient())
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda pair=None: [])
    monkeypatch.setattr(cli, "load_prompt", lambda kind, version: f"{kind}-{version}")


def test_the_readme_intermediate_build_publishes_human_then_llm(tmp_path, monkeypatch):
    """Materialise the norms, align over the reference file, publish with the one Layer 2 manifest."""
    import tere4ai.align_hleg.__main__ as align_cli

    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": LISTED, "edges": []}))
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({NORM["norm_id"]: {"decision": "reject", "rationale": "not a norm",
                                                       "reviewer": "adj", "decided_at": "t"}}))
    freeze = tmp_path / "freeze-f1.json"
    freeze.write_text(json.dumps({
        "schema_version": "freeze_manifest.v1", "campaign_type": "layer2_annotation", "campaign_id": "c1",
        "freeze_id": "f1", "stage": "production", "round": None, "pinned_build_id": PINNED, "guideline_version": "v1",
        "scope_core_nodes": ["eu-ai-act:article-9"], "units_in_scope": 1, "units_adjudicated": 1, "units_undecided": 0,
        "rows_included": ["row1"], "decisions_sha256": sha256_of_file(decisions), "frozen_at": "t"}))
    assert _script("materialize_reference").main(["--pristine", str(pristine), "--decisions", str(decisions),
                                                  "--manifest", str(freeze), "--source-build-id", PINNED]) == 0
    reference = tmp_path / "norms_core.reference.json"
    _align_fakes(monkeypatch, align_cli)
    aligned = tmp_path / "alignments_core.reference.json"
    assert align_cli.main(["--norms", str(reference), "--dump", str(layer1), "--out", str(aligned)]) == 0
    build = json.loads(aligned.read_text())["build"]
    assert "reference" not in build and build["norms_reference"]["freeze_id"] == "f1"
    assert not already_materialised(json.loads(aligned.read_text())), "the alignments carry no decision of their own"

    cli = _publish()
    _fakes(monkeypatch, cli)
    rc = cli.main(["--dump", str(layer1), "--norms", str(reference), "--alignments", str(aligned),
                   "--manifest", str(freeze), "--dump-dir", str(tmp_path)])
    assert rc == 0
    chain = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())
    assert chain["gating"] == {"layer2": "human", "layer3": "llm"} and chain["label"] is None
    assert [m["freeze_id"] for m in chain["manifests"]] == ["f1"]


def test_republishing_identical_inputs_is_refused_and_history_kept(tmp_path, monkeypatch, capsys):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    assert cli.main(args) == 0
    chain_path = next(tmp_path.glob("build_chain_*.json"))
    chain_id = json.loads(chain_path.read_text())["chain_id"]
    before = (chain_path.read_bytes(), (tmp_path / "publications" / f"{chain_id}.json").read_bytes())
    seen: list = []
    _fakes(monkeypatch, cli, seen=seen)
    assert cli.main(args) == 1
    message = f"already published as chain {chain_id}; activate it with scripts/activate_build.py {chain_id}"
    assert message in capsys.readouterr().err and not [s for s in seen if s[0] == "load"], "refused before the load"
    assert (chain_path.read_bytes(), (tmp_path / "publications" / f"{chain_id}.json").read_bytes()) == before
    # Changed by final review A6: the refusal now comes before a descendant is
    # made, so no child record (and no failed execution on one) exists.
    assert not [r for r in store.list_records() if r.get("parent_record_id") == rid]
    assert read_target_state(tmp_path)["state"] == "available", "the target state of the first publication stands"


def test_an_interrupt_during_the_load_leaves_the_target_unavailable_and_the_execution_failed(tmp_path, monkeypatch):
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    driver = _fakes(monkeypatch, cli)

    class InterruptedStore:
        def load_dump(self, dump, driver):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "GraphStore", InterruptedStore)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)])
    target = read_target_state(tmp_path)
    assert target["state"] == "unavailable" and "KeyboardInterrupt" in target["reason"] and driver.closed
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and "KeyboardInterrupt" in ex["error"]


def test_publish_refuses_before_any_gate_while_an_execution_of_the_record_is_live(tmp_path, monkeypatch, capsys):
    """B79 item 15: the refusal comes before the load, never after Neo4j holds the build."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    live = store.start_execution(rid, command="align_hleg", covers_steps=["L3.1", "L3.2", "L3.3"], argv=[],
                                 inputs=[], config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    seen: list = []
    _fakes(monkeypatch, cli, seen=seen)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                   "--dump-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 1 and live in err and "stops blocking 300 s after its last heartbeat" in err
    assert seen == [] and not list(tmp_path.glob("build_chain_*.json"))
    assert store.read(rid)["publication"] is None
    assert [e["command"] for e in store.read(rid)["executions"]] == ["extract_norms", "align_hleg"], "no publish execution"


def test_an_execution_started_during_the_load_leaves_neo4j_unavailable_and_nothing_published(tmp_path, monkeypatch):
    """Review fix C2: a refusal after the load never leaves the target available for an unpublished build."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    loader = cli.GraphStore

    class StartsAnotherRun(loader):
        def load_dump(self, dump, driver):
            store.start_execution(rid, command="align_hleg", covers_steps=["L3.1", "L3.2", "L3.3"], argv=[],
                                  inputs=[], config={}, expected_total=None, work_unit=None, checkpoint_file=None)
            return super().load_dump(dump, driver)

    monkeypatch.setattr(cli, "GraphStore", StartsAnotherRun)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                   "--dump-dir", str(tmp_path)])
    assert rc == 1 and read_target_state(tmp_path)["state"] == "unavailable"
    assert "became live after the first check" in read_target_state(tmp_path)["reason"]
    assert store.read(rid)["publication"] is None and not list(tmp_path.glob("build_chain_*.json"))


def test_a_publish_that_outlasts_the_heartbeat_expiry_stays_live(tmp_path, monkeypatch, capsys):
    """B79 item 15 (task review): the publish execution beats while it runs, so a
    second publish of the same record still sees it live after the 300 s expiry
    and its own beats stay allowed after the publication. A pinned clock stands
    in for the elapsed time; the only wait is for one beat of a 0.01 s interval."""
    import threading
    from datetime import UTC, datetime, timedelta

    from tere4ai.graph_store import build_record

    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    clock = {"now": datetime(2026, 9, 26, 12, 0, tzinfo=UTC)}
    monkeypatch.setattr(build_record, "_now", lambda: clock["now"].isoformat())
    monkeypatch.setattr(build_record, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    beat = threading.Event()
    real_heartbeat = BuildRecordStore.heartbeat

    def heartbeat(self, record_id, run_id):
        real_heartbeat(self, record_id, run_id)
        beat.set()

    monkeypatch.setattr(BuildRecordStore, "heartbeat", heartbeat)
    seen_live: list = []
    loader = cli.GraphStore

    class OutlastsTheExpiry(loader):
        def load_dump(self, dump, driver):
            clock["now"] += timedelta(seconds=build_record.HEARTBEAT_EXPIRY_SECONDS + 100)
            beat.clear()
            beat.wait(timeout=2)
            seen_live.extend(ex["command"] for ex in BuildRecordStore(tmp_path).live_executions(rid))
            return super().load_dump(dump, driver)

    monkeypatch.setattr(cli, "GraphStore", OutlastsTheExpiry)
    rc = cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                   "--dump-dir", str(tmp_path)])
    assert rc == 0 and seen_live == ["publish_layer23"]
    assert "heartbeat stopped" not in capsys.readouterr().err
    assert store.read(rid)["executions"][-1]["status"] == "done"


def test_a_refused_set_publication_removes_this_runs_chain_file_so_a_retry_publishes(tmp_path, monkeypatch, capsys):
    """Final review F2: the chain file is written before set_publication; when the
    locked check refuses, the file goes, so the next publish is not told the
    inputs were already published."""
    from tere4ai.graph_store.build_record import LiveExecutionError

    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]

    def refuse(self, record_id, publication, *, run_id=None):
        raise LiveExecutionError(f"record {record_id} has a live running execution: x (align_hleg, heartbeat t)")

    monkeypatch.setattr(BuildRecordStore, "set_publication", refuse)
    with pytest.raises(LiveExecutionError):
        cli.main(args)
    assert not list(tmp_path.glob("build_chain_*.json")), "this run's chain file is removed"
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and "clean up by hand" not in ex["error"]
    assert read_target_state(tmp_path)["state"] == "unavailable"
    monkeypatch.undo()
    _fakes(monkeypatch, cli)
    capsys.readouterr()
    assert cli.main(args) == 0, capsys.readouterr().err
    assert store.read(rid)["publication"] is not None


def test_publishing_twice_is_refused_before_a_descendant_is_made_or_the_alias_moves(tmp_path, monkeypatch, capsys):
    """Final review A6: the chain is computed and checked before a published
    record continues as a descendant, so a mistaken second publish leaves the
    records and the alias index as they were."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    assert cli.main(args) == 0
    chain_id = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())["chain_id"]
    records_before = sorted(r["record_id"] for r in store.list_records())
    capsys.readouterr()
    assert cli.main(args) == 1
    assert f"already published as chain {chain_id}" in capsys.readouterr().err
    assert sorted(r["record_id"] for r in store.list_records()) == records_before, "no descendant record"
    assert store.resolve("core") == rid, "the alias still names the published record"


def test_a_sigterm_during_the_load_ends_the_publish_failed_and_neo4j_unavailable(tmp_path, monkeypatch):
    """Final review A2 (a): a closed terminal takes the interrupt path, never leaves the target loading."""
    import os
    import signal
    import time

    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)

    class TerminatedStore:
        def load_dump(self, dump, driver):
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(1)
            return {"node:X": 1}

    monkeypatch.setattr(cli, "GraphStore", TerminatedStore)
    got: list[int] = []

    def guard(signum, frame):
        got.append(signum)

    before = {sig: signal.signal(sig, guard) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        with pytest.raises(KeyboardInterrupt):
            cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                      "--dump-dir", str(tmp_path)])
        assert signal.getsignal(signal.SIGTERM) is guard
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)
    assert got == []
    assert read_target_state(tmp_path)["state"] == "unavailable"
    ex = store.read(rid)["executions"][-1]
    assert ex["status"] == "failed" and "SIGTERM" in ex["error"]


def test_a_missing_or_misplaced_manifest_is_refused_before_the_record_is_touched(tmp_path, monkeypatch, capsys):
    """B97 item 3: a typo'd --manifest used to skip the early double-publish
    check, so a published record continued as a descendant and the alias
    moved before the evidence step refused."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    assert cli.main(args) == 0
    records_before = sorted(r["record_id"] for r in store.list_records())
    record_before = store.read(rid)
    typo = tmp_path / "freze-f1.json"
    (tmp_path / "elsewhere").mkdir()
    outside = tmp_path / "elsewhere" / "freeze-f1.json"
    outside.write_text("{}")
    capsys.readouterr()
    assert cli.main([*args, "--manifest", str(typo)]) == 1
    assert f"NOT published: freeze manifest not found: {typo}" in capsys.readouterr().err
    assert cli.main([*args, "--manifest", str(outside)]) == 1
    assert f"copy the freeze manifest {outside.name} into {tmp_path} first" in capsys.readouterr().err
    assert sorted(r["record_id"] for r in store.list_records()) == records_before, "no descendant record"
    assert store.resolve("core") == rid and store.read(rid) == record_before


def test_gates_only_on_a_published_record_checks_the_gates_and_records_nothing(tmp_path, monkeypatch, capsys):
    """B97 item 2: docs/RUNBOOK_backup_restore.md runs --gates-only on the
    published record after a restore; it used to create a descendant record
    and move the alias to it."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    assert cli.main(args) == 0
    chain_id = store.read(rid)["publication"]["chain_id"]
    records_before = sorted(r["record_id"] for r in store.list_records())
    record_before = store.read(rid)
    capsys.readouterr()
    assert cli.main([*args, "--gates-only"]) == 0
    captured = capsys.readouterr()
    assert (f"record {rid} is published as {chain_id}; checking the gates only: nothing is recorded, "
            "no descendant is made and the alias stays") in captured.out
    assert "gates: PASS" in captured.out
    _fakes(monkeypatch, cli, gates_ok=False)
    assert cli.main([*args, "--gates-only"]) == 1, "a failing gate still fails the check"
    assert "NOT published: critical validation failed" in capsys.readouterr().err
    assert sorted(r["record_id"] for r in store.list_records()) == records_before, "no descendant record"
    assert store.resolve("core") == rid and store.read(rid) == record_before, "the published record is untouched"


def test_a_manifest_that_does_not_verify_is_refused_before_a_descendant_is_made(tmp_path, monkeypatch, capsys):
    """B98 seat B P2-1: a manifest in the dump dir that does not verify used
    to be refused only after a published record continued as a descendant
    and the alias moved to it; each retry added one more descendant. The
    evidence steps only read files, so they now run before the record is
    touched."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    args = ["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments), "--dump-dir", str(tmp_path)]
    assert cli.main(args) == 0
    records_before = sorted(r["record_id"] for r in store.list_records())
    record_before = store.read(rid)
    bad = tmp_path / "freeze-bad.json"
    bad.write_text("{}")
    capsys.readouterr()
    for _ in range(2):
        assert cli.main([*args, "--manifest", str(bad)]) == 1
        captured = capsys.readouterr()
        assert "NOT published: freeze manifest campaign_type None" in captured.err
        assert "descendant" not in captured.out
    assert sorted(r["record_id"] for r in store.list_records()) == records_before, "no descendant record"
    assert store.resolve("core") == rid and store.read(rid) == record_before, "the published record keeps the alias"


def test_a_refused_publish_of_a_published_record_reuses_its_open_descendant(tmp_path, monkeypatch, capsys):
    """B98 seat B P2-1: a publish refused after the descendant is made (here
    by a critical gate) leaves one open descendant; the retry continues in
    it instead of making another."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    base = ["--dump", str(layer1), "--norms", str(norms), "--dump-dir", str(tmp_path)]
    assert cli.main(base) == 0
    _fakes(monkeypatch, cli, gates_ok=False)
    with_alignments = [*base, "--alignments", str(alignments)]
    capsys.readouterr()
    assert cli.main(with_alignments) == 1
    first = [r for r in store.list_records() if r.get("parent_record_id") == rid]
    assert len(first) == 1
    child = first[0]["record_id"]
    assert f"continuing as descendant {child}" in capsys.readouterr().out
    assert cli.main(with_alignments) == 1
    assert f"continuing in open record {child}" in capsys.readouterr().out
    descendants = [r for r in store.list_records() if r.get("parent_record_id") == rid]
    assert [r["record_id"] for r in descendants] == [child], "the retry made no second descendant"
    assert [ex["status"] for ex in store.read(child)["executions"]] == ["failed", "failed"]
    assert store.resolve("core") == child


def test_a_republish_does_not_land_in_a_descendant_holding_a_different_norms_extraction(tmp_path, monkeypatch, capsys):
    """B98 final re-review, New Breakage 1: select_record's first branch reused
    whatever open record the alias named, checking only that it was open and
    on the same Layer 1, not that it descended from the record being
    published or held no other norms extraction. Publish P with N1; an
    extract_norms run in descendant D records N2; a republish of N1 must not
    publish into D, which the alias core still names."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    base = ["--dump", str(layer1), "--norms", str(norms), "--dump-dir", str(tmp_path)]
    assert cli.main(base) == 0
    parent = store.read(rid)
    other_norms = tmp_path / "norms_other.json"
    other_norms.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [{"different": True}]}))
    descendant = store.create_record("core", parent["base_build_id"], parent["layer1_digest"], parent_record_id=rid)
    run = store.start_execution(descendant, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[],
                                inputs=[], config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(descendant, run, status="done",
                           outputs=[{"role": "norms", "file": other_norms.name, "sha256": sha256_of_file(other_norms)}])
    assert store.resolve("core") == descendant, "extract_norms moved the alias to the descendant"
    capsys.readouterr()
    with_alignments = [*base, "--alignments", str(alignments)]
    assert cli.main(with_alignments) == 0
    out = capsys.readouterr().out
    assert f"continuing in open record {descendant}" not in out, "N1 must not publish into D"
    assert [ex["command"] for ex in store.read(descendant)["executions"]] == ["extract_norms"], (
        "D keeps only its own extraction, no publish execution"
    )
    assert store.read(descendant)["publication"] is None, "D stays unpublished"
    new_descendants = [r for r in store.list_records()
                       if r.get("parent_record_id") == rid and r["record_id"] != descendant]
    assert len(new_descendants) == 1, "the republish makes its own descendant"
    child = new_descendants[0]["record_id"]
    assert f"continuing as descendant {child}" in out
    assert store.read(child)["publication"] is not None
    assert store.resolve("core") == child, "the alias now names the republish's own descendant"


def test_an_input_outside_the_dump_dir_is_refused_before_any_load(tmp_path, monkeypatch, capsys):
    """B79 item 7: publication names its inputs by file under the dump dir, so
    a --dump, --norms or --alignments elsewhere gave a manifest that could not
    be activated, and only after a full load. It is refused before the record
    is resolved."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    executions_before = store.read(rid)["executions"]
    (tmp_path / "other").mkdir()
    for flag, inside in (("--dump", layer1), ("--alignments", alignments)):
        outside = tmp_path / "other" / inside.name
        outside.write_bytes(inside.read_bytes())
        given = {"--dump": layer1, "--alignments": alignments, flag: outside}
        seen: list = []
        _fakes(monkeypatch, cli, seen=seen)
        rc = cli.main(["--dump", str(given["--dump"]), "--norms", str(norms), "--alignments", str(given["--alignments"]),
                       "--dump-dir", str(tmp_path)])
        err = capsys.readouterr().err
        assert rc == 1 and f"{outside.name} into {tmp_path} first" in err
        assert "publication names its inputs by file under that directory" in err
        assert seen == [], "the load never ran"
        assert not list(tmp_path.glob("build_chain_*.json")) and not (tmp_path / "publications").exists()
        assert store.read(rid)["executions"] == executions_before, "no execution was recorded"

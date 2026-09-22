"""Regression tests for the alignment CLI checkpointing (same failure class
as the lost 2026-07-08 extraction run)."""

import json

from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore


def _norms_file(tmp_path, n=3, name="norms_test.json"):
    norms = [{"norm_id": f"norm:eu-ai-act:article-9:paragraph-1:n{i}", "source_node_id": "eu-ai-act:article-9:paragraph-1",
              "deontic_type": "obligation", "action": "a", "object": "o", "judge_verdict": "accepted", "source_text": "t"}
             for i in range(n)]
    p = tmp_path / name
    p.write_text(json.dumps({"build": {"build_id": "b"}, "norms": norms}))
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {}, "nodes": [], "edges": []}))
    return p, layer1, norms


def _fakes(monkeypatch, cli, batches):
    def fake_align(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        batches.append(len(chunk))
        return {"assertions": [{"id": f"align:{c['norm_id']}"} for c in chunk], "mapping_runs": [], "judge_runs": [],
                "stats": {"norms_total": len(chunk), "verdicts": {"accepted": len(chunk)}, "mechanical_rejects": [],
                          "norms_failed": []}}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j"}

    class FakeClient:
        sampling = "0"
        usage = {"calls": 1, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(cli, "align_norms", fake_align)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg: FakeClient())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg: FakeClient())
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda: [])
    monkeypatch.setattr(cli, "load_prompt", lambda kind, version: f"{kind}-{version}")


def test_checkpoint_resume_skips_done_batches(tmp_path, monkeypatch):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    inputs = [{"role": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)},
              {"role": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)}]
    prev = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1", "L3.2", "L3.3"], argv=[],
                                 inputs=inputs, config={"prompt_version": "v1", "batch_size": 2}, expected_total=2,
                                 work_unit="batches", checkpoint_file="alignments_test.checkpoint.jsonl",
                                 models={"generator_model": "g", "judge_model": "j"},
                                 prompt_sha256={"generator": cli.prompt_sha256("align_hleg-v1"),
                                                "judge": cli.prompt_sha256("judge_alignment-v1")})
    ckpt = out.with_suffix(".checkpoint.jsonl")
    ckpt.write_text(json.dumps({"run_id": prev, "batch": f"batch:0:{norms[0]['norm_id']}", "result": {
        "assertions": [{"id": "align:pre1"}, {"id": "align:pre2"}], "mapping_runs": [], "judge_runs": [],
        "stats": {"norms_total": 2, "verdicts": {"accepted": 2}}}}) + "\n")
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume", "--batch-size", "2"])
    assert rc == 0 and batches == [1]
    result = json.loads(out.read_text())
    assert len(result["assertions"]) == 3 and result["stats"]["norms_total"] == 3 and not ckpt.exists()
    assert result["build"]["alignment_input_sha256"] == sha256_of_file(norms_path)
    ex = store.read(rid)["executions"][1]
    assert ex["resumes_run_id"] == prev and len(ex["inherited_keys"]) == 1 and len(ex["completed_keys"]) == 1


def test_align_records_execution_with_batch_total_and_inputs(tmp_path, monkeypatch):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"])
    assert rc == 0 and batches == [2, 1]
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][0]
    assert ex["covers_steps"] == ["L3.1", "L3.2", "L3.3"] and ex["expected_total"] == 2 and ex["config"]["batch_size"] == 2
    assert {i["role"] for i in ex["inputs"]} == {"norms", "layer1_dump"} and ex["counts"]["mechanical_rejects_count"] == 0
    assert ex["work_failures"] == {"nodes_failed": 0, "norms_failed": 0} and ex["prompt_sha256"]["judge"]


def test_align_over_a_materialised_file_joins_that_files_record(tmp_path, monkeypatch):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2, name="norms_core.reference.json")
    out = tmp_path / "alignments_core.reference.json"
    _fakes(monkeypatch, cli, [])
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.reference", "b", None)
    run = store.start_execution(rid, command="materialize_reference", covers_steps=["L2.4"], argv=[], inputs=[], config={},
                                expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done",
                           outputs=[{"role": "norms_reference", "file": norms_path.name, "sha256": sha256_of_file(norms_path)}])
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)])
    assert rc == 0
    assert [e["command"] for e in store.read(rid)["executions"]] == ["materialize_reference", "align_hleg_altai"]


def test_align_stale_checkpoint_exit_2(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"batch": "b", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)]) == 2
    assert "--resume" in capsys.readouterr().err


def test_align_never_overwrites_an_input_of_a_publication(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    dumps = tmp_path / "data" / "graph_dumps"
    (dumps / "publications").mkdir(parents=True)
    out = dumps / "alignments_test.json"
    out.write_text('{"assertions": ["published"]}')
    before = out.read_bytes()
    (dumps / "publications" / "c1.json").write_text(json.dumps(
        {"chain_id": "c1", "inputs": [{"role": "alignments", "file": out.name, "sha256": sha256_of_file(out)}]}))
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1)]) == 1
    err = capsys.readouterr().err
    assert "publication c1" in err and "--out" in err and batches == [] and out.read_bytes() == before


def test_resume_over_a_published_producer_continues_in_the_same_descendant(tmp_path, monkeypatch):
    import pytest

    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    producer = store.create_record("test", "b", sha256_of_file(layer1))
    run = store.start_execution(producer, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[],
                                config={}, expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(producer, run, status="done",
                           outputs=[{"role": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)}])
    store.set_publication(producer, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                                     "gating": {"layer2": "llm", "layer3": "absent"}, "label": None, "gates": [],
                                     "postload_gates": [], "manifests": []})
    inner = cli.align_norms

    def flaky(chunk, *a, **k):
        if len(batches) == 1:
            batches.append(-1)
            raise RuntimeError("usage limit reached")
        return inner(chunk, *a, **k)

    monkeypatch.setattr(cli, "align_norms", flaky)
    args = ["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"]
    with pytest.raises(RuntimeError):
        cli.main(args)
    assert cli.main(args + ["--resume"]) == 0
    children = [r for r in store.list_records() if r.get("parent_record_id") == producer]
    assert len(children) == 1 and [e["status"] for e in children[0]["executions"]] == ["failed", "done"]
    assert children[0]["executions"][1]["resumes_run_id"] == children[0]["executions"][0]["run_id"]



def test_align_resume_refuses_a_checkpoint_of_other_models(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    inputs = [{"role": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)},
              {"role": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)}]
    prev = store.start_execution(rid, command="align_hleg_altai", covers_steps=["L3.1", "L3.2", "L3.3"], argv=[],
                                 inputs=inputs, config={"prompt_version": "v1", "batch_size": 2}, expected_total=2,
                                 work_unit="batches", checkpoint_file="alignments_test.checkpoint.jsonl",
                                 models={"generator_model": "g-old", "judge_model": "j"},
                                 prompt_sha256={"generator": cli.prompt_sha256("align_hleg-v1"),
                                                "judge": cli.prompt_sha256("judge_alignment-v1")})
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"run_id": prev, "batch": f"batch:0:{norms[0]['norm_id']}", "result": {
        "assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume", "--batch-size", "2"])
    assert rc == 2 and "different models: generator_model" in capsys.readouterr().err and batches == []

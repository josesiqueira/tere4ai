"""Regression tests for the alignment CLI checkpointing (same failure class
as the lost 2026-07-08 extraction run)."""

import json

import pytest

from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE

PAIR = load_pair()


def _hleg_source_files():
    return [{"id": f"srcfile:{TEXT_FILE}", "layer": 0, "type": "SourceFile", "file": TEXT_FILE, "sha256": PAIR.text_sha256},
            {"id": f"srcfile:{RECORD_FILE}", "layer": 0, "type": "SourceFile", "file": RECORD_FILE,
             "sha256": PAIR.record_sha256}]


def _hleg_inputs():
    return [{"input_kind": "hleg_text", "file": TEXT_FILE, "sha256": PAIR.text_sha256},
            {"input_kind": "hleg_derivation_record", "file": RECORD_FILE, "sha256": PAIR.record_sha256}]


def _norms_file(tmp_path, n=3, name="norms_test.json"):
    norms = [{"norm_id": f"norm:eu-ai-act:article-9:paragraph-1:n{i}", "source_node_id": "eu-ai-act:article-9:paragraph-1",
              "deontic_type": "obligation", "action": "a", "object": "o", "judge_verdict": "accepted", "source_text": "t"}
             for i in range(n)]
    p = tmp_path / name
    p.write_text(json.dumps({"build": {"build_id": "b"}, "norms": norms}))
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {}, "nodes": _hleg_source_files(), "edges": []}))
    return p, layer1, norms


def _first_execution(tmp_path):
    store = BuildRecordStore(tmp_path)
    return store.read(store.resolve("test"))["executions"][0]


def _fakes(monkeypatch, cli, batches):
    def fake_align(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        batches.append(len(chunk))
        return {"assertions": [{"id": f"align:{c['norm_id']}"} for c in chunk], "mapping_runs": [], "judge_runs": [],
                "stats": {"norms_total": len(chunk), "verdicts": {"accepted": len(chunk)}, "mechanical_rejects": [],
                          "norms_failed": []}}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"}

    class FakeClient:
        sampling = "0"
        temperature = "0"
        effort = "xhigh"
        json_mode = "sent"
        usage = {"calls": 1, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(cli, "align_norms", fake_align)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    # B99 (spec F D-F30): the command chooses the terminal policy
    policies: list = []
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or FakeClient())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or FakeClient())
    monkeypatch.setattr(cli, "_TEST_POLICIES", policies, raising=False)
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda pair=None: [])
    monkeypatch.setattr(cli, "load_prompt", lambda kind, version: f"{kind}-{version}")


def test_checkpoint_resume_skips_done_batches(tmp_path, monkeypatch):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    inputs = [{"input_kind": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)},
              {"input_kind": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)},
              *_hleg_inputs()]
    prev = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=[],
                                 inputs=inputs, config={"prompt_version": "v1", "batch_size": 2}, expected_total=2,
                                 work_unit="batches", checkpoint_file="alignments_test.checkpoint.jsonl",
                                 models={"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"},
                                 prompt_sha256={"generator": cli.prompt_sha256("align_hleg-v1"),
                                                "judge": cli.prompt_sha256("judge_alignment-v1")})
    # Changed by final review A1: a resume is refused while the run it resumes
    # is live, so the prior attempt ends failed here as an interrupted run does.
    store.finish_execution(rid, prev, status="failed", error="KeyboardInterrupt: ")
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
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"])
    assert rc == 0 and batches == [2, 1]
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][0]
    assert ex["covers_steps"] == ["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"] and ex["expected_total"] == 2 and ex["config"]["batch_size"] == 2
    assert {i["input_kind"] for i in ex["inputs"]} == {"norms", "layer1_dump", "hleg_text", "hleg_derivation_record"} and ex["counts"]["mechanical_rejects_count"] == 0
    assert ex["work_failures"] == {"nodes_failed": 0, "norms_failed": 0} and ex["prompt_sha256"]["judge"]
    assert ex["counts"]["norms_total"] == 3 and ex["counts"]["candidates"] is None, "a count the stats lack is null"
    assert ex["counts"]["norms_skipped_not_accepted"] is None and ex["counts"]["zero_alignment_norms"] is None
    # B99 (spec F D-F29): the declared temperature under <role>_temperature and the declared JSON mode are recorded too
    assert ex["sampling"] == {"generator": "0", "judge": "0", "generator_temperature": "0", "judge_temperature": "0",
                              "generator_effort": "xhigh", "judge_effort": "xhigh", "generator_json_mode": "sent"}
    out_payload = json.loads(out.read_text())
    assert out_payload["build"]["alignment_effort"] == {"generator": "xhigh", "judge": "xhigh"}


def test_align_over_a_materialised_file_joins_that_files_record(tmp_path, monkeypatch):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2, name="norms_core.reference.json")
    out = tmp_path / "alignments_core.reference.json"
    _fakes(monkeypatch, cli, [])
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("core.reference", "b", None)
    run = store.start_execution(rid, command="materialize_reference", covers_steps=["LAYER2_STEP4"], argv=[], inputs=[], config={},
                                expected_total=None, work_unit=None, checkpoint_file=None)
    store.finish_execution(rid, run, status="done",
                           outputs=[{"output_kind": "norms_reference", "file": norms_path.name, "sha256": sha256_of_file(norms_path)}])
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)])
    assert rc == 0
    assert [e["command"] for e in store.read(rid)["executions"]] == ["materialize_reference", "align_hleg"]


def test_align_stale_checkpoint_exit_2(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"batch": "b", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)]) == 2
    assert "--resume" in capsys.readouterr().err
    # B79 item 10: a refused run leaves no record and no alias
    assert BuildRecordStore(tmp_path).list_records() == []
    aliases = tmp_path / "build_records" / "aliases.json"
    assert not aliases.is_file() or "test" not in json.loads(aliases.read_text(encoding="utf-8"))


def test_a_refusal_over_a_published_record_creates_no_descendant(tmp_path, monkeypatch, capsys):
    """B79 item 10: the stale checkpoint is refused before the descendant is made."""
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    old = store.create_record("test", "b", sha256_of_file(layer1))
    store.set_publication(old, {"chain_id": "c" * 12, "build_id": "b+chain-" + "c" * 12, "published_at": "t",
                                "gating": {"layer2": "llm", "layer3": "absent"}, "label": None, "gates": [],
                                "postload_gates": [], "manifests": []})
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"batch": "b", "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)]) == 2
    assert "--resume" in capsys.readouterr().err and batches == []
    assert [r["record_id"] for r in store.list_records()] == [old] and store.resolve("test") == old


def test_a_client_that_fails_to_build_leaves_no_record(tmp_path, monkeypatch):
    """B79 item 10: the record is created only after the model clients and the HLEG nodes are built."""
    import pytest

    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)

    def no_client(cfg, **kw):
        raise RuntimeError("the judge client could not be built")

    monkeypatch.setattr(cli, "AnthropicJudge", no_client)
    with pytest.raises(RuntimeError, match="could not be built"):
        cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)])
    assert batches == []
    assert BuildRecordStore(tmp_path).list_records() == []
    aliases = tmp_path / "build_records" / "aliases.json"
    assert not aliases.is_file() or "test" not in json.loads(aliases.read_text(encoding="utf-8"))


def test_align_never_overwrites_an_input_of_a_publication(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg.__main__ as cli

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
        {"chain_id": "c1", "inputs": [{"input_kind": "alignments", "file": out.name, "sha256": sha256_of_file(out)}]}))
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1)]) == 1
    err = capsys.readouterr().err
    assert "publication c1" in err and "--out" in err and batches == [] and out.read_bytes() == before


def test_resume_over_a_published_producer_continues_in_the_same_descendant(tmp_path, monkeypatch):
    import pytest

    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    producer = store.create_record("test", "b", sha256_of_file(layer1))
    run = store.start_execution(producer, command="extract_norms", covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[],
                                config={}, expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(producer, run, status="done",
                           outputs=[{"output_kind": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)}])
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
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    inputs = [{"input_kind": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)},
              {"input_kind": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)},
              *_hleg_inputs()]
    prev = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=[],
                                 inputs=inputs, config={"prompt_version": "v1", "batch_size": 2}, expected_total=2,
                                 work_unit="batches", checkpoint_file="alignments_test.checkpoint.jsonl",
                                 models={"generator_model": "g-old", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"},
                                 prompt_sha256={"generator": cli.prompt_sha256("align_hleg-v1"),
                                                "judge": cli.prompt_sha256("judge_alignment-v1")})
    # Changed by final review A1: a resume is refused while the run it resumes
    # is live, so the prior attempt ends failed here as an interrupted run does.
    store.finish_execution(rid, prev, status="failed", error="KeyboardInterrupt: ")
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"run_id": prev, "batch": f"batch:0:{norms[0]['norm_id']}", "result": {
        "assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume", "--batch-size", "2"])
    assert rc == 2 and "different models: generator_model" in capsys.readouterr().err and batches == []


def test_ctrl_c_ends_the_align_execution_failed_with_the_spend_so_far(tmp_path, monkeypatch):
    """B79 item 22: a KeyboardInterrupt is not an Exception; the record must still end."""
    import pytest

    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    inner = cli.align_norms

    def interrupted(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        if chunk[0]["norm_id"].endswith(":n2"):
            raise KeyboardInterrupt
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id)

    monkeypatch.setattr(cli, "align_norms", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"])
    store = BuildRecordStore(tmp_path)
    ex = store.read(store.resolve("test"))["executions"][0]
    assert ex["status"] == "failed" and ex["error"] == "KeyboardInterrupt: " and ex["ended_at"]
    assert ex["completed_keys"] == [f"batch:0:{norms[0]['norm_id']}"] and ex["usage"]["generator"]["calls"] == 1
    # review fix F2: the failed attempt records what the clients applied, not the start value
    # B99 (spec F D-F29): the declared temperature under <role>_temperature and the declared JSON mode are recorded too
    assert ex["sampling"] == {"generator": "0", "judge": "0", "generator_temperature": "0", "judge_temperature": "0",
                              "generator_effort": "xhigh", "judge_effort": "xhigh", "generator_json_mode": "sent"}
    assert out.with_suffix(".checkpoint.jsonl").is_file(), "the checkpoint stays for resume"


def test_a_long_batch_keeps_the_execution_live(tmp_path, monkeypatch):
    """B79 item 4: a batch longer than the expiry must not read liveness unknown."""
    import time

    import tere4ai.align_hleg.__main__ as cli
    from tere4ai.graph_store import build_record

    monkeypatch.setattr(build_record, "HEARTBEAT_INTERVAL_SECONDS", 0.05)
    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    inner = cli.align_norms
    beats: list[str] = []

    def slow(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        store = BuildRecordStore(tmp_path)
        rid = store.resolve("test")
        beats.append(store.read(rid)["executions"][0]["heartbeat_at"])
        time.sleep(0.3)
        beats.append(store.read(rid)["executions"][0]["heartbeat_at"])
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id)

    monkeypatch.setattr(cli, "align_norms", slow)
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)]) == 0
    assert beats[1] > beats[0], "the heartbeat advanced inside one batch"


def test_a_resume_is_refused_while_the_first_align_run_is_live(tmp_path, monkeypatch, capsys):
    """Final review A1: two live runs of one record would both pay for every remaining batch."""
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    first = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=[],
                                  inputs=[], config={}, expected_total=2, work_unit="batches", checkpoint_file=None)
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume"])
    err = capsys.readouterr().err
    assert rc == 2 and first in err and "300 s after its last heartbeat" in err and batches == []
    assert [e["run_id"] for e in store.read(rid)["executions"]] == [first], "no second execution started"


def test_a_sighup_ends_the_align_execution_failed_and_each_batch_writes_the_usage_so_far(tmp_path, monkeypatch):
    """Final review A2: a SIGHUP takes the interrupt path (a); each finished batch
    leaves the usage so far on the running execution (b)."""
    import os
    import signal
    import time

    import pytest

    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    inner = cli.align_norms
    seen: list[dict] = []

    def hung_up(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        if chunk[0]["norm_id"].endswith(":n2"):
            store = BuildRecordStore(tmp_path)
            seen.append(store.read(store.resolve("test"))["executions"][0])
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(1)
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id)

    monkeypatch.setattr(cli, "align_norms", hung_up)
    got: list[int] = []

    def guard(signum, frame):
        got.append(signum)

    before = {sig: signal.signal(sig, guard) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        with pytest.raises(KeyboardInterrupt):
            cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"])
        assert signal.getsignal(signal.SIGHUP) is guard and signal.getsignal(signal.SIGTERM) is guard
    finally:
        for sig, handler in before.items():
            signal.signal(sig, handler)
    assert got == []
    assert seen[0]["status"] == "running" and seen[0]["usage"]["generator"]["calls"] == 1
    ex = _first_execution(tmp_path)
    assert ex["status"] == "failed" and "SIGHUP" in ex["error"] and ex["usage"]["judge"]["calls"] == 1


def test_a_provider_stop_ends_the_align_execution_failed_and_prints_the_resume(tmp_path, monkeypatch, capsys):
    """B99 (spec F D-F30)."""
    import tere4ai.align_hleg.__main__ as cli
    from tere4ai.extract_norms.model_clients import TERMINAL_POLICY, ProviderUnavailable

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    batches: list[int] = []
    _fakes(monkeypatch, cli, batches)
    inner = cli.align_norms

    def stop_on_the_second_batch(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        if chunk[0]["norm_id"].endswith(":n2"):
            raise ProviderUnavailable(6, "APIConnectionError: Connection error.")
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id)

    monkeypatch.setattr(cli, "align_norms", stop_on_the_second_batch)
    argv = ["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"]
    assert cli.main(argv) == 3
    assert cli._TEST_POLICIES == [TERMINAL_POLICY, TERMINAL_POLICY]
    store = BuildRecordStore(tmp_path)
    (ex,) = store.read(store.resolve("test"))["executions"]
    assert ex["status"] == "failed"
    assert ex["error"] == "provider unavailable after 6 attempts: APIConnectionError: Connection error."
    assert out.with_suffix(".checkpoint.jsonl").is_file()
    err = capsys.readouterr().err
    assert "(1 of 2 batches done); continue with:" in err
    assert "  .venv/bin/python -m tere4ai.align_hleg --norms " in err and err.rstrip().endswith("--resume")


def test_a_refused_declared_parameter_ends_the_align_execution_failed_and_exits_4(tmp_path, monkeypatch, capsys):
    """B99 (spec F D-F29) final review: a declared parameter the provider
    refused stops the run with the configuration error; the checkpoint of
    the batches done stays and no resume command is printed (the row is
    corrected first)."""
    import tere4ai.align_hleg.__main__ as cli
    from tere4ai.judge.config import DeclaredParameterRefused

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    inner = cli.align_norms

    def refuse_on_the_second_batch(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        if chunk[0]["norm_id"].endswith(":n2"):
            raise DeclaredParameterRefused("anthropic", "j", "effort", "xhigh", "HTTP 400: effort unsupported")
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id)

    monkeypatch.setattr(cli, "align_norms", refuse_on_the_second_batch)
    argv = ["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--batch-size", "2"]
    assert cli.main(argv) == 4
    reason = ("configuration error: anthropic:j refused the declared effort xhigh (HTTP 400: effort unsupported); "
              "correct its row in config/model_parameters.json")
    store = BuildRecordStore(tmp_path)
    (ex,) = store.read(store.resolve("test"))["executions"]
    assert ex["status"] == "failed" and ex["error"] == reason
    # the output is only the placeholder the command claims its path with
    assert out.with_suffix(".checkpoint.jsonl").is_file() and out.read_bytes() == b""
    err = capsys.readouterr().err
    assert f"stopped: {reason}" in err and "continue with:" not in err


def test_the_run_records_the_hleg_text_and_record_it_aligned_on(tmp_path, monkeypatch):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    assert cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out)]) == 0
    ex = _first_execution(tmp_path)
    assert [i for i in ex["inputs"] if i["input_kind"].startswith("hleg_")] == _hleg_inputs()
    build = json.loads(out.read_text())["build"]
    assert (build["hleg_text_sha256"], build["hleg_derivation_record_sha256"]) == (PAIR.text_sha256, PAIR.record_sha256)


@pytest.mark.parametrize("flag", [[], ["--accept-legacy-checkpoint"]])
def test_checkpoint_lines_without_a_run_id_are_refused_with_or_without_the_flag(tmp_path, monkeypatch, capsys, flag):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"batch": f"batch:0:{norms[0]['norm_id']}", "result": {
        "assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume", *flag])
    err = capsys.readouterr().err
    assert rc == 2 and "alignments_test.checkpoint.jsonl" in err and "without a run id" in err
    assert "never inherits them" in err and cli._TEST_POLICIES == [], "refused before any client is built"
    assert not BuildRecordStore(tmp_path).list_records(), "a refused run leaves no record"


@pytest.mark.parametrize("changed", [0, 1])  # review M6: the text, then the record
def test_a_resume_across_two_hleg_texts_is_refused(tmp_path, monkeypatch, capsys, changed):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, norms = _norms_file(tmp_path, 3)
    out = tmp_path / "alignments_test.json"
    _fakes(monkeypatch, cli, [])
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("test", "b", None)
    other_text = [{**i, "sha256": "0" * 64} if k == changed else i for k, i in enumerate(_hleg_inputs())]
    inputs = [{"input_kind": "norms", "file": norms_path.name, "sha256": sha256_of_file(norms_path)},
              {"input_kind": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)}, *other_text]
    prev = store.start_execution(rid, command="align_hleg", covers_steps=["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], argv=[], inputs=inputs,
                                 config={"prompt_version": "v1", "batch_size": 20}, expected_total=1, work_unit="batches",
                                 checkpoint_file="alignments_test.checkpoint.jsonl",
                                 models={"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh",
                                         "judge_effort": "xhigh"},
                                 prompt_sha256={"generator": cli.prompt_sha256("align_hleg-v1"),
                                                "judge": cli.prompt_sha256("judge_alignment-v1")})
    store.finish_execution(rid, prev, status="failed", error="KeyboardInterrupt: ")
    out.with_suffix(".checkpoint.jsonl").write_text(json.dumps({"run_id": prev, "batch": f"batch:0:{norms[0]['norm_id']}",
        "result": {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}}) + "\n")
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--resume"])
    kind = ("hleg_text", "hleg_derivation_record")[changed]
    assert rc == 2 and f"used different inputs: {kind}" in capsys.readouterr().err


def test_a_layer1_dump_that_does_not_list_the_pair_is_refused_before_any_client(tmp_path, monkeypatch, capsys):
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    layer1.write_text(json.dumps({"build": {}, "nodes": [], "edges": []}))
    _fakes(monkeypatch, cli, [])
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(tmp_path / "alignments_test.json")])
    err = capsys.readouterr().err
    assert rc == 2 and f"{TEXT_FILE} not at all" in err and cli._TEST_POLICIES == []


def test_a_record_that_is_not_a_json_object_is_refused_by_the_command(tmp_path, monkeypatch, capsys):
    """Final review F2 (M1): the command reports the refusal as its other refusals, no traceback."""
    import hashlib

    import tere4ai.align_hleg.__main__ as cli
    from tere4ai.align_hleg.hleg_source import read_pair

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    folder = tmp_path / "hleg"
    folder.mkdir()
    (folder / TEXT_FILE).write_bytes(b"text")
    (folder / RECORD_FILE).write_text("[1, 2]", encoding="utf-8")
    expected = {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in (TEXT_FILE, RECORD_FILE)}
    _fakes(monkeypatch, cli, [])
    monkeypatch.setattr(cli, "load_pair", lambda: read_pair(folder, expected))
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(tmp_path / "alignments_test.json")])
    err = capsys.readouterr().err
    assert rc == 2 and "refusing to start" in err and "not a JSON object" in err and cli._TEST_POLICIES == []


def test_a_layer1_dump_node_that_is_not_an_object_is_refused_by_the_command(tmp_path, monkeypatch, capsys):
    """Final review F2 (M1): listed_pair's refusal on a dump node is reported, not raised."""
    import tere4ai.align_hleg.__main__ as cli

    norms_path, layer1, _ = _norms_file(tmp_path, 2)
    layer1.write_text(json.dumps({"build": {}, "nodes": [None, *_hleg_source_files()], "edges": []}))
    _fakes(monkeypatch, cli, [])
    rc = cli.main(["--norms", str(norms_path), "--dump", str(layer1), "--out", str(tmp_path / "alignments_test.json")])
    err = capsys.readouterr().err
    assert rc == 2 and "refusing to start" in err and "not a JSON object" in err and cli._TEST_POLICIES == []

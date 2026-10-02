"""scripts/run_ablations.py writes one evaluation record per run (D-G33, E6, DEC-17).

Also DEC-17's guards: an unrecorded checkpoint is never resumed by default,
the July files are never written, and a resume names its failed predecessor.
"""

from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path

import pytest

from tere4ai.eval import harness
from tere4ai.eval.evaluation_record import EvaluationRecordStore
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    ProviderRefused,
    ProviderUnavailable,
)
from tere4ai.judge.config import DeclaredParameterRefused

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("run_ablations", ROOT / "scripts" / "run_ablations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Client:
    """A model client double: usage and sampling like the real ones, canned replies."""

    # B91: the double counts like the real clients (final review A3: the
    # sixth count, requests_refused, too; spec F D-F32: the seventh,
    # requests_rejected_before_processing)
    def __init__(self, reply, sampling="stub"):
        self.reply, self.sampling = reply, sampling
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "requests_sent": 0,
                      "replies_with_usage": 0, "requests_refused": 0,
                      "requests_rejected_before_processing": 0}

    def complete(self, *args, **kwargs):
        self.usage["requests_sent"] += 1
        self.usage["calls"] += 1
        self.usage["replies_with_usage"] += 1
        self.usage["input_tokens"] += 3
        self.usage["output_tokens"] += 1
        return self.reply


def _dumps(tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (tmp_path / "norms_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": []}))


@pytest.fixture
def runner(monkeypatch, tmp_path):
    mod = _load()
    _dumps(tmp_path)
    items = [{"id": "gold:cls-01", "prompt": "p", "gold": "high"}, {"id": "gold:cls-02", "prompt": "p", "gold": "high"}]
    monkeypatch.setattr(mod, "load_items", lambda b, f: items)
    monkeypatch.setattr(mod.harness, "_require_live_gate", lambda: None)
    monkeypatch.setattr(mod.harness, "guard_live_config", lambda: type("C", (), {"as_public_dict": staticmethod(
        lambda: {"generator_model": "g", "judge_model": "j"})})())
    monkeypatch.setattr(mod.strategies, "STRATEGY_NAMES", ["plain_llm"])
    calls = {}

    # B99 (spec F D-F29, D-F30): the runner chooses the terminal policy, and a strategy can raise the stop or a refusal
    def fake_build(name, **kw):
        if calls.get("raise"):
            raise RuntimeError("provider refused")  # at build time: a per-item raise is caught by the runner (R5)

        def strategy(item):
            if calls.get("interrupt_on") == item["id"]:
                raise KeyboardInterrupt
            if calls.get("raise_on") == item["id"]:
                raise OSError("cannot read /home/someone/private/x.json")
            if calls.get("error_on") == item["id"]:
                return {"answer_text": "", "citations": [], "risk_category": None, "error": "bad item"}
            if calls.get("unavailable_on") == item["id"]:
                raise ProviderUnavailable(6, "HTTP 529")
            if calls.get("provider_refused_on") == item["id"]:
                raise ProviderRefused("HTTP 429")
            if calls.get("refused_on") == item["id"]:
                raise DeclaredParameterRefused("openai", "g", "effort", "xhigh", "HTTP 400: effort unsupported")
            kw["generator"].complete()
            return {"answer_text": "x", "citations": [], "risk_category": "high"}
        strategy.models = {"generator": "g", "judge": "j", "judge_prompt_version": "v1"}
        return strategy

    monkeypatch.setattr(mod.strategies, "build_strategy", fake_build)
    policies: list = []
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: policies.append(kw.get("retry_policy"))
                        or _Client("x", "temperature=0"), raising=False)
    monkeypatch.setattr(mod, "AnthropicJudge", lambda cfg, **kw: policies.append(kw.get("retry_policy"))
                        or _Client("y", "provider default"), raising=False)
    calls["policies"] = policies
    monkeypatch.setattr(mod, "load_model_config", lambda: object(), raising=False)
    monkeypatch.setattr(mod, "RESULTS_DIR", tmp_path / "results")
    mod._TEST_CALLS = calls
    return mod


def _argv(tmp_path, *extra):
    return ["--dump-dir", str(tmp_path), "--checkpoint", str(tmp_path / "results" / "ablation_checkpoint.jsonl"),
            "--summary", str(tmp_path / "results" / "ablation_summary.json"), *extra]


def test_a_completed_run_writes_a_record_with_inputs_outputs_usage_and_copies(runner, tmp_path):
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (rec,) = [r for r in store.list_records() if not r.get("unreadable")]
    assert rec["kind"] == "run" and rec["step"] == "E6" and rec["command"] == "run_ablations"
    assert rec["outcome"]["status"] == "completed" and rec["outcome"]["completed_items"] == ["gold:cls-01", "gold:cls-02"]
    assert {i["role"] for i in rec["inputs"]} == {"layer1_dump", "norms", "benchmark", "gold_seed", "features"}
    assert rec["build"]["base_build_id"] == "build-b" and rec["build"]["publication"] is None
    assert rec["models"] == {"generator_model": "g", "judge_model": "j"}
    # B99 (spec F D-F29): the evaluation record carries the declared sampling (review T-M7); the double has only sampling
    assert rec["sampling"] == {"generator": "temperature=0", "judge": "provider default",
                               "generator_temperature": "unknown", "judge_temperature": "unknown",
                               "generator_effort": "unknown", "judge_effort": "unknown",
                               "generator_json_mode": "unknown"}
    assert rec["usage"]["generator"]["calls"] == 2 and rec["config"]["metrics_version"] == "metrics.v2"
    # B10: the run reads the repository's facts file, so prompt_versions also
    # names the elicitor's prompt (its own test below); the strategy's entry is unchanged
    assert rec["prompt_versions"]["plain_llm"] == {"generator": "g", "judge": "j", "judge_prompt_version": "v1"}
    assert rec["config"]["mode"] == "live" and rec["config"]["strategies"] == ["plain_llm"]
    roles = {o["role"]: o for o in rec["outputs"]}
    assert set(roles) == {"summary", "checkpoint"}
    assert (store.dir / roles["summary"]["copy"]).read_bytes() == (tmp_path / "results" / "ablation_summary.json").read_bytes()
    assert rec["counts"]["items_total"] == 2 and rec["counts"]["items_with_errors"] == 0


def test_an_item_error_makes_the_run_partial(runner, tmp_path):
    runner._TEST_CALLS["error_on"] = "gold:cls-02"
    assert runner.main(_argv(tmp_path)) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "partial" and rec["outcome"]["completed_items"] == ["gold:cls-01"]
    assert rec["counts"]["items_with_errors"] == 1


def test_a_raising_sweep_records_a_failed_run_and_reraises(runner, tmp_path):
    runner._TEST_CALLS["raise"] = True
    with pytest.raises(RuntimeError, match="provider refused"):
        runner.main(_argv(tmp_path))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed" and "provider refused" in rec["outcome"]["error"]
    assert rec["ended_at"] and rec["outputs"] == []


def test_a_resumed_run_names_its_predecessor_or_says_none_does(runner, tmp_path):
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    assert runner.main(_argv(tmp_path)) == 0
    second = [r for r in store.list_records() if r["record_id"] != first["record_id"]][0]
    assert second["relations"]["resumes_record_id"] == first["record_id"]
    assert any(i["role"] == "checkpoint_resumed" for i in second["inputs"])
    assert second["counts"]["units_resumed"] == 1
    # a checkpoint no record names: resumed only with the explicit flag
    (tmp_path / "results" / "orphan.jsonl").write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": {}}) + "\n")
    assert runner.main(_argv(tmp_path, "--checkpoint", str(tmp_path / "results" / "orphan.jsonl"),
                             "--resume-unrecorded")) == 0
    third = max(store.list_records(), key=lambda r: r["started_at"])
    assert third["relations"]["resumes_record_id"] is None
    assert "resumed from a checkpoint no record names" in third["notes"]


def test_a_failure_finish_refused_by_validation_still_ends_the_record_failed(runner, tmp_path, monkeypatch):
    # B97 item 9 (Task 8): the record never stays running; B102 final review: the retry drops only the
    # client-built fields, so the items that finished and the notes survive
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    runner._TEST_CALLS["interrupt_on"] = "gold:cls-02"
    monkeypatch.setattr(runner, "_own_usage", lambda generator, judge: ["not", "an", "object"])
    with pytest.raises(KeyboardInterrupt):  # no features file, so the record carries a note
        runner.main(_argv(tmp_path, "--features", str(tmp_path / "no_features.json")))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed" and rec["ended_at"]
    assert rec["outcome"]["error"].startswith("KeyboardInterrupt: ; the full failure record was refused: "
                                              "refusing to finish: ")
    assert "at usage" in rec["outcome"]["error"] and rec["usage"] is None
    assert rec["outcome"]["completed_items"] == ["gold:cls-01"]
    assert rec["notes"] == ["no elicited-features cache was read"]


def test_a_provider_stop_whose_finish_is_refused_stays_partial(runner, tmp_path, monkeypatch):
    # B102 final review: the retry keeps the status the runner chose, so a resumable stop is not read as failed
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    runner._TEST_CALLS["unavailable_on"] = "gold:cls-02"
    monkeypatch.setattr(runner, "_own_usage", lambda generator, judge: ["not", "an", "object"])
    assert runner.main(_argv(tmp_path)) == 3
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "partial" and rec["ended_at"] and rec["usage"] is None
    assert rec["outcome"]["completed_items"] == ["gold:cls-01"]
    assert "the full failure record was refused: refusing to finish: " in rec["outcome"]["error"]


def test_repeat_of_must_resolve_and_no_record_writes_nothing(runner, tmp_path, capsys):
    assert runner.main(_argv(tmp_path, "--repeat-of", "000000000000")) == 2
    assert "no evaluation record 000000000000" in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists(), "a refused --repeat-of creates no store (B81 item 10)"
    assert runner.main(_argv(tmp_path, "--no-record")) == 0
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == []
    assert runner.main(_argv(tmp_path, "--resume-unrecorded")) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert runner.main(_argv(tmp_path, "--repeat-of", rec["record_id"], "--checkpoint",
                             str(tmp_path / "results" / "ckpt2.jsonl"))) == 0
    repeat = max(EvaluationRecordStore(tmp_path, create=False).list_records(), key=lambda r: r["started_at"])
    assert repeat["relations"]["repeat_of"] == rec["record_id"]


def test_a_checkpointed_item_error_names_the_file_never_the_path(runner, tmp_path):
    runner._TEST_CALLS["raise_on"] = "gold:cls-02"
    assert runner.main(_argv(tmp_path)) == 0
    line = json.loads((tmp_path / "results" / "ablation_checkpoint.jsonl").read_text().splitlines()[0])
    assert line["results"]["gold:cls-02"]["error"] == "OSError: cannot read x.json"


def test_repeat_of_with_no_record_is_refused(runner, tmp_path, capsys):
    """B81 item 10, first half: the relation would be recorded nowhere."""
    assert runner.main(_argv(tmp_path, "--no-record", "--repeat-of", "0123456789ab")) == 2
    assert "--repeat-of" in capsys.readouterr().out


def test_a_refused_live_gate_records_nothing(runner, monkeypatch, tmp_path):
    def refuse():
        raise harness.LiveGateError("gate")
    monkeypatch.setattr(runner.harness, "_require_live_gate", refuse)
    with pytest.raises(harness.LiveGateError):
        runner.main(_argv(tmp_path))
    assert not (tmp_path / "evaluation_records").exists()


def _july(name: str) -> bytes:
    return (ROOT / "eval" / "results" / name).read_bytes()


# B81 item 20: the defaults no longer name the July files; an explicit July
# path is still refused
def test_a_default_run_writes_a_fresh_directory_and_never_touches_the_july_files(runner, tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    july = results / "ablation_checkpoint.jsonl"
    july.write_bytes(_july("ablation_checkpoint.jsonl"))
    assert runner.main(["--dump-dir", str(tmp_path)]) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    run_dir = results / "runs" / rec["record_id"]
    assert (run_dir / "ablation_checkpoint.jsonl").is_file() and (run_dir / "ablation_summary.json").is_file()
    assert (run_dir / "ablation_checkpoint.jsonl.record").is_file(), "the sidecar sits beside its checkpoint"
    assert rec["config"]["checkpoint_file"] == "ablation_checkpoint.jsonl"
    assert july.read_bytes() == _july("ablation_checkpoint.jsonl")
    # a second default run is fresh: it resumes nothing
    assert runner.main(["--dump-dir", str(tmp_path)]) == 0
    second = next(r for r in EvaluationRecordStore(tmp_path, create=False).list_records()
                  if r["record_id"] != rec["record_id"])
    assert second["relations"]["resumes_record_id"] is None and second["counts"]["units_resumed"] == 0


def test_an_explicit_july_checkpoint_path_is_still_refused(runner, tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    ckpt = results / "ablation_checkpoint.jsonl"
    ckpt.write_bytes(_july("ablation_checkpoint.jsonl"))
    for extra in ((), ("--resume-unrecorded",)):
        assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(ckpt), *extra]) == 2
        assert f"refusing to write {ckpt}: its bytes are the July 2026 measurement" in capsys.readouterr().out
    assert ckpt.read_bytes() == _july("ablation_checkpoint.jsonl")


def test_a_no_record_run_must_name_both_paths(runner, tmp_path, capsys):
    assert runner.main(["--dump-dir", str(tmp_path), "--no-record"]) == 2
    assert "pass --checkpoint and --summary" in capsys.readouterr().out
    assert not (tmp_path / "results" / "runs").exists()


def test_a_summary_target_holding_the_july_bytes_refuses(runner, tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    summary = results / "ablation_summary.json"
    summary.write_bytes(_july("ablation_full_summary.json"))
    argv = ["--dump-dir", str(tmp_path), "--checkpoint", str(results / "fresh.jsonl"), "--summary", str(summary)]
    for extra in ((), ("--no-record",)):
        assert runner.main([*argv, *extra]) == 2
        assert f"refusing to write {summary}: its bytes are the July 2026 measurement" in capsys.readouterr().out
    assert summary.read_bytes() == _july("ablation_full_summary.json")
    assert not (results / "fresh.jsonl").exists()


def test_an_unrecorded_checkpoint_is_resumed_only_with_the_flag(runner, tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    orphan = results / "orphan.jsonl"
    orphan.write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": {}}) + "\n")
    argv = _argv(tmp_path, "--checkpoint", str(orphan))
    for extra in ((), ("--no-record",)):
        assert runner.main([*argv, *extra]) == 2
        assert (f"refusing to resume {orphan}: no evaluation record names it; pass --resume-unrecorded to resume "
                "it anyway (the note is recorded) or --checkpoint with a fresh path") in capsys.readouterr().out
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == []
    assert runner.main([*argv, "--resume-unrecorded"]) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["relations"]["resumes_record_id"] is None
    # Changed by B98 seat B P3-5: a strategy whose every unit was resumed
    # now carries a note naming where its models are recorded.
    assert rec["notes"] == ["resumed from a checkpoint no record names",
                            "plain_llm: every unit resumed, none run by this invocation; the models that produced "
                            "its results are named in no record (the checkpoint no record names)"]
    assert rec["config"]["checkpoint_file"] == "orphan.jsonl"


def test_a_resume_after_a_failed_run_names_the_failed_record(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner.strategies, "STRATEGY_NAMES", ["plain_llm", "vector_rag"])
    real_build = runner.strategies.build_strategy

    def failing_second(name, **kw):
        if name == "vector_rag" and runner._TEST_CALLS.get("fail_second"):
            raise RuntimeError("provider refused")
        return real_build(name, **kw)
    monkeypatch.setattr(runner.strategies, "build_strategy", failing_second)
    runner._TEST_CALLS["fail_second"] = True
    with pytest.raises(RuntimeError, match="provider refused"):
        runner.main(_argv(tmp_path))
    store = EvaluationRecordStore(tmp_path, create=False)
    (failed,) = store.list_records()
    assert failed["outcome"]["status"] == "failed" and failed["outputs"] == []
    assert (tmp_path / "results" / "ablation_checkpoint.jsonl").read_text().count("\n") == 1
    runner._TEST_CALLS["fail_second"] = False
    assert runner.main(_argv(tmp_path)) == 0
    resumed = [r for r in store.list_records() if r["record_id"] != failed["record_id"]][0]
    assert resumed["relations"]["resumes_record_id"] == failed["record_id"]
    # Changed by B98 seat B P3-5: a strategy whose every unit was resumed
    # now carries a note naming where its models are recorded.
    assert resumed["notes"] == ["plain_llm: every unit resumed, none run by this invocation; the models that "
                                f"produced its results are named in record {failed['record_id']}"]
    assert resumed["counts"]["units_resumed"] == 1


def _publish_only_layer1(tmp_path):
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-xyz.json").write_text(json.dumps({
        "build_id": "build-xyz", "files": {"layer1_dump": "layer1.json"}}))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-xyz"}))


def test_a_manifest_lacking_a_role_refuses_with_a_sentence(runner, tmp_path, capsys):
    _publish_only_layer1(tmp_path)
    assert runner.main(_argv(tmp_path)) == 2
    assert "refusing to run: the active publication names no norms file" in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists()


def test_a_run_with_graph_full_records_the_runtime_judge_prompt_hash(runner, monkeypatch, tmp_path):
    from tere4ai.judge.runtime_grounding import load_prompt, prompt_sha256
    monkeypatch.setattr(runner.strategies, "STRATEGY_NAMES", ["plain_llm", "graph_full"])
    assert runner.main(_argv(tmp_path)) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["prompt_sha256"] == {"runtime_grounding": prompt_sha256(load_prompt("runtime_grounding", "v1"))}


def test_a_dump_whose_build_names_no_id_records_none_never_the_string(runner, tmp_path):
    (tmp_path / "layer1.json").write_text(json.dumps({"build": {"note": "no id"}, "nodes": [], "edges": []}))
    assert runner.main(_argv(tmp_path)) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["build"]["base_build_id"] is None


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".record")


def test_a_recording_run_writes_the_checkpoint_sidecar_and_a_no_record_run_writes_none(runner, tmp_path):
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert runner.main(_argv(tmp_path)) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert json.loads(_sidecar(ckpt).read_text()) == {"record_id": rec["record_id"],
                                                       "checkpoint_file": "ablation_checkpoint.jsonl"}
    assert not list(ckpt.parent.glob("tmp*")), "the sidecar lands atomically, no temp file left"
    fresh = tmp_path / "results" / "unrecorded.jsonl"
    assert runner.main(_argv(tmp_path, "--no-record", "--checkpoint", str(fresh))) == 0
    assert fresh.is_file() and not _sidecar(fresh).exists()


def test_a_resume_with_a_matching_sidecar_names_its_record_and_takes_the_sidecar_over(runner, tmp_path):
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    assert runner.main(_argv(tmp_path)) == 0
    second = [r for r in store.list_records() if r["record_id"] != first["record_id"]][0]
    assert second["relations"]["resumes_record_id"] == first["record_id"]
    assert json.loads(_sidecar(ckpt).read_text())["record_id"] == second["record_id"], "the newest record owns it"


@pytest.mark.parametrize("case", ["missing", "unreadable", "other_file"])
def test_a_sidecar_the_store_cannot_confirm_refuses_the_resume_and_records_nothing(runner, tmp_path, capsys,
                                                                                    case):
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    rid = first["record_id"]
    if case == "missing":
        rid = "000000000000"
        _sidecar(ckpt).write_text(json.dumps({"record_id": rid, "checkpoint_file": ckpt.name}))
        why = "which this store does not hold"
    elif case == "unreadable":
        (store.dir / f"{rid}.json").write_text("{not json")
        why = "which this store cannot read"
    else:
        record_path = store.dir / f"{rid}.json"
        data = json.loads(record_path.read_text())
        data["config"]["checkpoint_file"] = "another.jsonl"
        record_path.write_text(json.dumps(data))
        why = "which names the checkpoint file another.jsonl"
    capsys.readouterr()
    for extra in ((), ("--resume-unrecorded",), ("--no-record",)):
        assert runner.main(_argv(tmp_path, *extra)) == 2
        out = capsys.readouterr().out
        assert f"refusing to resume {ckpt}: its sidecar names evaluation record {rid}, {why}" in out
        assert out.rstrip().endswith(f"remove the sidecar {ckpt.name}.record to resume it as a checkpoint "
                                     "no record names (--resume-unrecorded)"), "the way out (G2b)"
    assert len(store.list_records()) == 1, "no record written"


@pytest.mark.parametrize("case", ["not_json", "bad_record_id", "other_checkpoint"])
def test_a_sidecar_that_refuses_by_itself_refuses_the_resume_and_records_nothing(runner, tmp_path, capsys, case):
    # B81 item 36: the two refusals that come from the sidecar itself, before any store lookup
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    if case == "not_json":
        _sidecar(ckpt).write_text("{not json")
        why = f"its sidecar {ckpt.name}.record is not readable"
    elif case == "bad_record_id":
        _sidecar(ckpt).write_text(json.dumps({"record_id": "../x", "checkpoint_file": ckpt.name}))
        why = f"its sidecar {ckpt.name}.record is not readable"
    else:
        _sidecar(ckpt).write_text(json.dumps({"record_id": first["record_id"], "checkpoint_file": "other.jsonl"}))
        why = f"its sidecar {ckpt.name}.record names the checkpoint file other.jsonl"
    capsys.readouterr()
    for extra in ((), ("--resume-unrecorded",), ("--no-record",)):
        assert runner.main(_argv(tmp_path, *extra)) == 2
        out = capsys.readouterr().out
        assert f"refusing to resume {ckpt}: {why}" in out
        assert out.rstrip().endswith(f"remove the sidecar {ckpt.name}.record to resume it as a checkpoint "
                                     "no record names (--resume-unrecorded)"), "the way out (G2b)"
    assert len(store.list_records()) == 1, "no record written"


def test_a_recorded_checkpoint_whose_sidecar_is_gone_is_resumed_only_with_the_flag(runner, tmp_path, capsys):
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert runner.main(_argv(tmp_path)) == 0
    _sidecar(ckpt).unlink()
    capsys.readouterr()
    assert runner.main(_argv(tmp_path)) == 2
    assert f"refusing to resume {ckpt}: no evaluation record names it" in capsys.readouterr().out
    assert runner.main(_argv(tmp_path, "--resume-unrecorded")) == 0
    newest = max(EvaluationRecordStore(tmp_path, create=False).list_records(), key=lambda r: r["started_at"])
    assert newest["relations"]["resumes_record_id"] is None
    # Changed by B98 seat B P3-5: a strategy whose every unit was resumed
    # now carries a note naming where its models are recorded.
    assert newest["notes"] == ["resumed from a checkpoint no record names",
                               "plain_llm: every unit resumed, none run by this invocation; the models that "
                               "produced its results are named in no record (the checkpoint no record names)"]


def test_two_checkpoints_with_one_basename_in_two_directories_never_resolve_to_each_other(runner, tmp_path):
    a = tmp_path / "results" / "a" / "ablation_checkpoint.jsonl"
    b = tmp_path / "results" / "b" / "ablation_checkpoint.jsonl"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    store = EvaluationRecordStore(tmp_path, create=False)
    assert runner.main(_argv(tmp_path, "--checkpoint", str(a))) == 0
    (rec_a,) = store.list_records()
    assert runner.main(_argv(tmp_path, "--checkpoint", str(b))) == 0
    (rec_b,) = [r for r in store.list_records() if r["record_id"] != rec_a["record_id"]]
    seen = {rec_a["record_id"], rec_b["record_id"]}
    assert runner.main(_argv(tmp_path, "--checkpoint", str(a))) == 0
    (resumed_a,) = [r for r in store.list_records() if r["record_id"] not in seen]
    assert resumed_a["relations"]["resumes_record_id"] == rec_a["record_id"], "never the newer b record"
    seen.add(resumed_a["record_id"])
    assert runner.main(_argv(tmp_path, "--checkpoint", str(b))) == 0
    (resumed_b,) = [r for r in store.list_records() if r["record_id"] not in seen]
    assert resumed_b["relations"]["resumes_record_id"] == rec_b["record_id"]


def test_the_features_cache_is_recorded_only_when_the_run_read_one(runner, tmp_path):
    assert runner.main(_argv(tmp_path, "--features", str(tmp_path / "no_such_features.json"))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert "features" not in {i["role"] for i in rec["inputs"]}
    assert rec["notes"] == ["no elicited-features cache was read"]
    assert rec["outcome"]["status"] == "completed"
    default = tmp_path / "second"
    default.mkdir()
    _dumps(default)
    assert runner.main(["--dump-dir", str(default), "--checkpoint", str(default / "c.jsonl"),
                        "--summary", str(default / "s.json")]) == 0
    (rec2,) = EvaluationRecordStore(default, create=False).list_records()
    features = [i for i in rec2["inputs"] if i["role"] == "features"]
    assert len(features) == 1 and features[0]["file"] == "benchmark_features.json"
    assert "no elicited-features cache was read" not in rec2["notes"]


def _facts(tmp_path, **header):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps({"provenance": "llm_elicited", **header,
                                "features_by_item": {"bench:1": {"flags": {}}}}))
    return path


ELICITOR_PROMPT = {"prompt": "elicit_features", "version": "v6", "template_sha256": "a" * 64,
                   "rendered_sha256": "b" * 64, "provisions": ["eu-ai-act:definition:profiling"],
                   "graph_version": "build-b"}


def test_the_record_names_the_elicitors_prompt_from_the_facts_file(runner, tmp_path):
    """B10: the E6 record's prompt_versions names the elicitor's prompt
    (version, template hash, rendered hash and build) from the facts file it
    read, beside each strategy's models."""
    facts = _facts(tmp_path, prompt_version="v6", prompt=ELICITOR_PROMPT)
    assert runner.main(_argv(tmp_path, "--features", str(facts))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    # B10: final review, the rendered hash and the build join the version and template hash
    assert rec["prompt_versions"] == {
        "plain_llm": {"generator": "g", "judge": "j", "judge_prompt_version": "v1"},
        "elicit_features": {"version": "v6", "template_sha256": "a" * 64,
                            "rendered_sha256": "b" * 64, "graph_version": "build-b"},
    }


def test_a_stopped_run_keeps_the_elicitors_prompt_in_its_record(runner, tmp_path):
    """B10: the entry is written when the run begins, so a partial record names it too."""
    runner._TEST_CALLS["unavailable_on"] = "gold:cls-02"
    facts = _facts(tmp_path, prompt_version="v6", prompt=ELICITOR_PROMPT)
    assert runner.main(_argv(tmp_path, "--features", str(facts))) == 3
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "partial"
    # B10: final review, the rendered hash and the build are in the entry too
    assert rec["prompt_versions"]["elicit_features"] == {
        "version": "v6", "template_sha256": "a" * 64,
        "rendered_sha256": "b" * 64, "graph_version": "build-b"}


def test_a_facts_file_from_before_b10_names_its_version_and_no_template_hash(runner, tmp_path):
    facts = _facts(tmp_path, prompt_version="v1")
    assert runner.main(_argv(tmp_path, "--features", str(facts))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    # B10: final review, a file from before B10 has no rendered hash or build either
    assert rec["prompt_versions"]["elicit_features"] == {
        "version": "v1", "template_sha256": None, "rendered_sha256": None, "graph_version": None}


def test_without_a_facts_file_the_record_names_no_elicitor_prompt(runner, tmp_path):
    assert runner.main(_argv(tmp_path, "--features", str(tmp_path / "no_such_features.json"))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert "elicit_features" not in rec["prompt_versions"]


def test_a_run_that_fails_before_any_strategy_keeps_prompt_versions_none_without_a_facts_file(runner, tmp_path):
    runner._TEST_CALLS["raise"] = True
    with pytest.raises(RuntimeError):
        runner.main(_argv(tmp_path, "--features", str(tmp_path / "no_such_features.json")))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed" and rec["prompt_versions"] is None


def test_the_summary_sums_the_two_counts_and_drops_them_when_a_unit_lacks_them(runner, tmp_path):
    assert runner.main(_argv(tmp_path)) == 0
    summary = json.loads((tmp_path / "results" / "ablation_summary.json").read_text())
    by_role = summary["usage_provider_reported"]["by_role"]
    assert by_role["generator"]["requests_sent"] == 2 and by_role["generator"]["replies_with_usage"] == 2
    # a checkpoint unit written before B91 carries no counts: the aggregate cannot know them
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    lines = [json.loads(line) for line in ckpt.read_text().splitlines()]
    for entry in lines:
        for role in entry["usage"].values():
            role.pop("requests_sent", None)
            role.pop("replies_with_usage", None)
    old = tmp_path / "results" / "old_checkpoint.jsonl"
    old.write_text("".join(json.dumps(e) + "\n" for e in lines))
    assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(old), "--summary",
                        str(tmp_path / "results" / "old_summary.json"), "--resume-unrecorded"]) == 0
    old_by_role = json.loads((tmp_path / "results" / "old_summary.json").read_text())[
        "usage_provider_reported"]["by_role"]
    assert "requests_sent" not in old_by_role["generator"] and old_by_role["generator"]["calls"] == 2
    # spec F D-F32: the subsets of requests_sent go with it
    assert "requests_refused" not in old_by_role["generator"]
    assert "requests_rejected_before_processing" not in old_by_role["generator"]


def test_a_unit_without_any_usage_drops_the_counts_too(runner, monkeypatch, tmp_path):
    """Review fix C4: a unit checkpointed before usage tracking leaves the whole
    aggregate incomplete, so no role may keep counts that read complete (R5)."""
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    assert runner.main(_argv(tmp_path)) == 0
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    lines = [json.loads(line) for line in ckpt.read_text().splitlines()]
    del lines[0]["usage"]
    mixed = tmp_path / "results" / "mixed_checkpoint.jsonl"
    mixed.write_text("".join(json.dumps(e) + "\n" for e in lines))
    assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(mixed), "--summary",
                        str(tmp_path / "results" / "mixed_summary.json"), "--resume-unrecorded"]) == 0
    usage = json.loads((tmp_path / "results" / "mixed_summary.json").read_text())["usage_provider_reported"]
    assert usage["units_without_usage"] == 1 and "requests_sent" not in usage["by_role"]["generator"]
    assert "requests_rejected_before_processing" not in usage["by_role"]["generator"]


def test_a_resumed_record_counts_only_its_own_spend(runner, tmp_path):
    """B81 item 4: summing the records of a run and its resume must equal the real spend."""
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    assert runner.main(_argv(tmp_path)) == 0
    second = next(r for r in store.list_records() if r["record_id"] != first["record_id"])
    assert first["usage"]["generator"]["calls"] == 2
    assert second["usage"]["generator"]["calls"] == 0 and second["counts"]["units_run"] == 0


def test_an_interrupted_sweep_keeps_the_completed_items_and_the_spend(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    runner._TEST_CALLS["interrupt_on"] = "gold:cls-02"
    with pytest.raises(KeyboardInterrupt):
        runner.main(_argv(tmp_path))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed" and rec["outcome"]["error"] == "KeyboardInterrupt: "
    assert rec["outcome"]["completed_items"] == ["gold:cls-01"]
    assert rec["usage"]["generator"]["calls"] == 1 and rec["counts"]["units_run"] == 1


def test_the_summary_sums_requests_refused_and_drops_only_it_when_a_unit_lacks_it(runner, monkeypatch, tmp_path):
    """Final review A3: a unit checkpointed before requests_refused existed leaves
    that count unknown for its role; the two B91 counts it does carry stay."""
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    assert runner.main(_argv(tmp_path)) == 0
    summary = json.loads((tmp_path / "results" / "ablation_summary.json").read_text())
    assert summary["usage_provider_reported"]["by_role"]["generator"]["requests_refused"] == 0
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    lines = [json.loads(line) for line in ckpt.read_text().splitlines()]
    for role in lines[0]["usage"].values():
        role.pop("requests_refused", None)
    older = tmp_path / "results" / "b91_checkpoint.jsonl"
    older.write_text("".join(json.dumps(e) + "\n" for e in lines))
    assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(older), "--summary",
                        str(tmp_path / "results" / "b91_summary.json"), "--resume-unrecorded"]) == 0
    by_role = json.loads((tmp_path / "results" / "b91_summary.json").read_text())["usage_provider_reported"]["by_role"]
    assert "requests_refused" not in by_role["generator"] and by_role["generator"]["requests_sent"] == 2
    # the seventh count is a subset of requests_refused, so it goes with it
    assert "requests_rejected_before_processing" not in by_role["generator"]


def test_the_summary_sums_the_rejected_count_and_drops_only_it_when_a_unit_lacks_it(runner, monkeypatch, tmp_path):
    """Spec F D-F32: a unit checkpointed before requests_rejected_before_processing
    existed leaves that count unknown for its role; the six counts it does carry
    stay."""
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    assert runner.main(_argv(tmp_path)) == 0
    summary = json.loads((tmp_path / "results" / "ablation_summary.json").read_text())
    assert summary["usage_provider_reported"]["by_role"]["generator"]["requests_rejected_before_processing"] == 0
    ckpt = tmp_path / "results" / "ablation_checkpoint.jsonl"
    lines = [json.loads(line) for line in ckpt.read_text().splitlines()]
    # each unit's generator met one 429 and retried it: the summary sums the units
    for entry in lines:
        generator = entry["usage"]["generator"]
        generator["requests_sent"] += 1
        generator["requests_refused"] += 1
        generator["requests_rejected_before_processing"] += 1
    rejected = tmp_path / "results" / "rejected_checkpoint.jsonl"
    rejected.write_text("".join(json.dumps(e) + "\n" for e in lines))
    assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(rejected), "--summary",
                        str(tmp_path / "results" / "rejected_summary.json"), "--resume-unrecorded"]) == 0
    summed = json.loads((tmp_path / "results" / "rejected_summary.json").read_text())[
        "usage_provider_reported"]["by_role"]["generator"]
    assert len(lines) == 2
    assert (summed["requests_sent"], summed["requests_refused"], summed["requests_rejected_before_processing"]) == (4, 2, 2)
    lines = [json.loads(line) for line in ckpt.read_text().splitlines()]
    for role in lines[0]["usage"].values():
        role.pop("requests_rejected_before_processing", None)
    older = tmp_path / "results" / "a3_checkpoint.jsonl"
    older.write_text("".join(json.dumps(e) + "\n" for e in lines))
    assert runner.main(["--dump-dir", str(tmp_path), "--checkpoint", str(older), "--summary",
                        str(tmp_path / "results" / "a3_summary.json"), "--resume-unrecorded"]) == 0
    by_role = json.loads((tmp_path / "results" / "a3_summary.json").read_text())["usage_provider_reported"]["by_role"]
    assert "requests_rejected_before_processing" not in by_role["generator"]
    assert by_role["generator"]["requests_refused"] == 0 and by_role["generator"]["requests_sent"] == 2


# Review I3 (Codex review of 73b8baa..782f26a, the sibling writer): the models
# are read after the replies, on the completed and on the failed path


class _EffortStrategy:
    """graph_full's shape: its models read the judge's effort, known only once the judge has answered."""

    def __init__(self, judge, interrupt_on=None):
        self.judge, self.interrupt_on = judge, interrupt_on

    @property
    def models(self):
        return {"judge": "j", "judge_effort": "high" if self.judge.usage["calls"] else "no replies",
                "judge_prompt_version": "v1"}

    def __call__(self, item):
        if item["id"] == self.interrupt_on:
            raise KeyboardInterrupt
        self.judge.complete()
        return {"answer_text": "x", "citations": [], "risk_category": "high"}


@pytest.mark.parametrize("interrupt_on", [None, "gold:cls-02"])
def test_the_record_names_the_judge_effort_after_the_replies(runner, monkeypatch, tmp_path, interrupt_on):
    monkeypatch.setattr(runner.strategies, "build_strategy",
                        lambda name, **kw: _EffortStrategy(kw["judge"], interrupt_on))
    if interrupt_on is None:
        assert runner.main(_argv(tmp_path)) == 0
    else:
        with pytest.raises(KeyboardInterrupt):
            runner.main(_argv(tmp_path))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == ("completed" if interrupt_on is None else "failed")
    assert rec["prompt_versions"]["plain_llm"]["judge_effort"] == "high"


def test_a_fully_resumed_strategy_is_noted_with_the_record_that_ran_it(runner, monkeypatch, tmp_path):
    """B98 seat B P3-5: a strategy whose every unit was resumed makes no
    reply in this invocation, so its judge reads "no replies" beside
    metrics another invocation produced; the record says so and names the
    record the resume continues."""
    monkeypatch.setattr(runner.strategies, "build_strategy", lambda name, **kw: _EffortStrategy(kw["judge"]))
    assert runner.main(_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (first,) = store.list_records()
    assert not [n for n in first["notes"] if "every unit resumed" in n]
    assert runner.main(_argv(tmp_path)) == 0
    second = next(r for r in store.list_records() if r["record_id"] != first["record_id"])
    assert second["prompt_versions"]["plain_llm"]["judge_effort"] == "no replies"
    assert (f"plain_llm: every unit resumed, none run by this invocation; the models that produced its "
            f"results are named in record {first['record_id']}") in second["notes"]


def test_a_fresh_run_over_an_empty_item_list_notes_nothing_resumed(runner, monkeypatch, tmp_path):
    """B98 final re-review, New Breakage 3: with no items, batches is empty
    and no strategy ever enters `ran`, but a fresh run (no checkpoint) never
    resumed anything either; the note used to name every built strategy as
    fully resumed although nothing was."""
    monkeypatch.setattr(runner, "load_items", lambda b, f: [])
    assert runner.main(_argv(tmp_path)) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["notes"] == []


# B99 (spec F D-F30): the sixth failed attempt stops the run, and a refusal no
# retry fixes stops it at once; the record ends with the reason, never an item
# error, and the next command is printed.


def test_a_provider_stop_ends_the_record_partial_never_as_an_item_error(runner, tmp_path, capsys):
    runner._TEST_CALLS["unavailable_on"] = "gold:cls-02"
    argv = _argv(tmp_path)
    assert runner.main(argv) == 3
    assert runner._TEST_CALLS["policies"] == [TERMINAL_POLICY, TERMINAL_POLICY]
    store = EvaluationRecordStore(tmp_path, create=False)
    (rec,) = [r for r in store.list_records() if not r.get("unreadable")]
    assert rec["outcome"]["status"] == "partial"
    assert rec["outcome"]["error"] == "provider unavailable after 6 attempts: HTTP 529"
    assert rec["outcome"]["completed_items"] == [] and rec["outputs"] == []
    assert rec["usage"]["generator"]["calls"] == 1, "the item that answered before the stop keeps its spend"
    assert rec["sampling"]["generator"] == "temperature=0"
    assert not (tmp_path / "results" / "ablation_summary.json").exists()
    assert (tmp_path / "results" / "ablation_checkpoint.jsonl").exists()
    err = capsys.readouterr().err
    assert "stopped: provider unavailable after 6 attempts: HTTP 529" in err
    # review T-M6: no unit was checkpointed, so the next run cannot name this record
    assert "no unit was checkpointed, so this starts a new record that names none; run again with:" in err
    assert "  TERE4AI_LIVE_TESTS=1 .venv/bin/python scripts/run_ablations.py " + shlex.join(argv) in err


def test_a_stop_after_a_checkpointed_unit_prints_continue_with(runner, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    runner._TEST_CALLS["unavailable_on"] = "gold:cls-02"
    assert runner.main(_argv(tmp_path)) == 3
    assert "is kept (1 unit(s) done); continue with:" in capsys.readouterr().err


def test_a_quota_refusal_stops_the_sweep_never_as_an_item_error(runner, tmp_path, capsys):
    """Review T-I1, ruling P21: a failure no retry fixes stops the run at once;
    B101 ruling S5: the reason names the item, which is fixed before the
    resume, never skipped."""
    runner._TEST_CALLS["provider_refused_on"] = "gold:cls-01"
    argv = _argv(tmp_path)
    assert runner.main(argv) == 5
    store = EvaluationRecordStore(tmp_path, create=False)
    (rec,) = [r for r in store.list_records() if not r.get("unreadable")]
    assert rec["outcome"]["status"] == "failed"
    assert rec["outcome"]["error"] == "provider refused the request: HTTP 429 (item gold:cls-01)"
    assert rec["outcome"]["completed_items"] == [] and rec["usage"]["generator"]["calls"] == 0
    assert not (tmp_path / "results" / "ablation_summary.json").exists()
    err = capsys.readouterr().err
    assert "stopped: provider refused the request: HTTP 429 (item gold:cls-01)" in err
    assert "  TERE4AI_LIVE_TESTS=1 .venv/bin/python scripts/run_ablations.py " + shlex.join(argv) in err


def test_the_resume_line_adds_the_checkpoint_when_the_run_named_none(runner, tmp_path):
    path = tmp_path / "results" / "runs" / "r1" / "ablation_checkpoint.jsonl"
    assert runner._resume_line(["--dump-dir", "d"], path) == (
        f"TERE4AI_LIVE_TESTS=1 .venv/bin/python scripts/run_ablations.py --dump-dir d --checkpoint {path}")
    assert runner._resume_line(["--checkpoint=x.jsonl"], path).endswith("run_ablations.py --checkpoint=x.jsonl")


def test_a_refused_declaration_ends_the_record_failed_and_exits_4(runner, tmp_path, capsys):
    runner._TEST_CALLS["refused_on"] = "gold:cls-01"
    assert runner.main(_argv(tmp_path)) == 4
    store = EvaluationRecordStore(tmp_path, create=False)
    (rec,) = [r for r in store.list_records() if not r.get("unreadable")]
    assert rec["outcome"]["status"] == "failed"
    assert rec["outcome"]["error"] == ("configuration error: openai:g refused the declared effort xhigh "
                                       "(HTTP 400: effort unsupported); correct its row in config/model_parameters.json")
    assert "stopped: configuration error: openai:g refused" in capsys.readouterr().err


def test_a_judge_that_cannot_be_built_leaves_the_judge_sampling_null(runner, monkeypatch, tmp_path):
    """B99 (spec F D-F29), Task 5 review: the generator was built, the judge
    constructor raised; the failed record's judge-role sampling keys are null."""
    def no_judge(cfg, **kw):
        raise RuntimeError("judge unavailable")
    monkeypatch.setattr(runner, "AnthropicJudge", no_judge)
    with pytest.raises(RuntimeError, match="judge unavailable"):
        runner.main(_argv(tmp_path))
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed"
    assert rec["sampling"]["generator"] == "temperature=0"
    assert (rec["sampling"]["judge"], rec["sampling"]["judge_temperature"], rec["sampling"]["judge_effort"]) == (
        None, None, None)


# B99 (spec F D-F29) final review I1: a resume never continues under another
# declaration; the record's models and the checkpoint entries name the digest.


def _declared_config(monkeypatch, runner, tmp_path, effort):
    """The runner reads a real ModelConfig from a mock table whose generator
    row declares effort, as the live gate would."""
    from tests.fixtures.model_parameters import declared, write_table

    from tere4ai.judge.config import load_model_config
    path = write_table(tmp_path / "model_parameters.json", declared("gpt-mock", "openai", effort=effort),
                       declared("claude-mock", "anthropic"))
    env = {"TERE4AI_GENERATOR_MODEL": "gpt-mock", "TERE4AI_JUDGE_MODEL": "claude-mock",
           "OPENAI_API_KEY": "sk-fake", "ANTHROPIC_API_KEY": "sk-ant-fake"}
    monkeypatch.setattr(runner.harness, "guard_live_config", lambda: load_model_config(env, parameters_path=path))
    return load_model_config(env, parameters_path=path).model_parameters_sha256


def test_a_resume_under_an_edited_row_is_refused_by_name(runner, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    digest = _declared_config(monkeypatch, runner, tmp_path, "xhigh")
    runner._TEST_CALLS["unavailable_on"] = "gold:cls-02"
    assert runner.main(_argv(tmp_path)) == 3
    err = capsys.readouterr().err
    assert "is kept (1 unit(s) done); continue with:" in err
    checkpoint = tmp_path / "results" / "ablation_checkpoint.jsonl"
    (entry,) = [json.loads(line) for line in checkpoint.read_text().splitlines()]
    assert entry["model_parameters_sha256"] == digest
    (stopped,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    # the operator lowers the effort to get through the overload, then runs the printed command
    _declared_config(monkeypatch, runner, tmp_path, "high")
    runner._TEST_CALLS["unavailable_on"] = None
    printed = err.split("continue with:\n", 1)[1].splitlines()[0]
    resume_argv = shlex.split(printed)[3:]
    assert runner.main(resume_argv) == 2
    out = capsys.readouterr().out
    assert (f"refusing to resume {checkpoint}: evaluation record {stopped['record_id']} used different models: "
            "generator_effort, model_parameters_sha256; restore the row in config/model_parameters.json to "
            "resume it, or pass --checkpoint with a fresh path to start again") in out
    assert [r["record_id"] for r in EvaluationRecordStore(tmp_path, create=False).list_records()] == [
        stopped["record_id"]]
    # restored, the same command resumes it
    _declared_config(monkeypatch, runner, tmp_path, "xhigh")
    assert runner.main(resume_argv) == 0


def test_a_resumed_record_made_before_the_digest_is_refused(runner, monkeypatch, tmp_path, capsys):
    assert runner.main(_argv(tmp_path)) == 0  # the double's models carry no digest, as before B99
    (first,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    _declared_config(monkeypatch, runner, tmp_path, "xhigh")
    assert runner.main(_argv(tmp_path)) == 2
    out = capsys.readouterr().out
    assert f"evaluation record {first['record_id']} used different models: " in out
    assert "model_parameters_sha256" in out


def test_an_unrecorded_resume_refuses_entries_of_another_digest(runner, monkeypatch, tmp_path, capsys):
    digest = _declared_config(monkeypatch, runner, tmp_path, "xhigh")
    results = tmp_path / "results"
    results.mkdir()
    orphan = results / "orphan.jsonl"
    orphan.write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": {},
                                  "model_parameters_sha256": "0" * 64}) + "\n")
    argv = _argv(tmp_path, "--checkpoint", str(orphan), "--resume-unrecorded")
    refusal = (f"refusing to resume {orphan}: a checkpointed unit was run under different models: "
               "model_parameters_sha256; restore the row in config/model_parameters.json to resume it, or pass "
               "--checkpoint with a fresh path to start again")
    assert runner.main(argv) == 2
    assert refusal in capsys.readouterr().out
    # ruling P6 (fix wave re-review N2): a unit written before the digest existed is refused too
    orphan.write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": {}}) + "\n")
    assert runner.main(argv) == 2
    assert refusal in capsys.readouterr().out
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == []
    orphan.write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": {},
                                  "model_parameters_sha256": digest}) + "\n")
    assert runner.main(argv) == 0

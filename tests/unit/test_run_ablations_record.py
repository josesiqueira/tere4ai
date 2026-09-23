"""scripts/run_ablations.py writes one evaluation record per run (D-G33, E6, DEC-17).

Also DEC-17's guards: an unrecorded checkpoint is never resumed by default,
the July files are never written, and a resume names its failed predecessor.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tere4ai.eval import harness
from tere4ai.eval.evaluation_record import EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("run_ablations", ROOT / "scripts" / "run_ablations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Client:
    """A model client double: usage and sampling like the real ones, canned replies."""

    def __init__(self, reply, sampling="stub"):
        self.reply, self.sampling = reply, sampling
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0}

    def complete(self, *args, **kwargs):
        self.usage["calls"] += 1
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

    def fake_build(name, **kw):
        if calls.get("raise"):
            raise RuntimeError("provider refused")  # at build time: a per-item raise is caught by the runner (R5)

        def strategy(item):
            if calls.get("error_on") == item["id"]:
                return {"answer_text": "", "citations": [], "risk_category": None, "error": "bad item"}
            kw["generator"].complete()
            return {"answer_text": "x", "citations": [], "risk_category": "high"}
        strategy.models = {"generator": "g", "judge": "j", "judge_prompt_version": "v1"}
        return strategy

    monkeypatch.setattr(mod.strategies, "build_strategy", fake_build)
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg: _Client("x", "temperature=0"), raising=False)
    monkeypatch.setattr(mod, "AnthropicJudge", lambda cfg: _Client("y", "provider default"), raising=False)
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
    assert rec["sampling"] == {"generator": "temperature=0", "judge": "provider default"}
    assert rec["usage"]["generator"]["calls"] == 2 and rec["config"]["metrics_version"] == "metrics.v2"
    assert rec["prompt_versions"] == {"plain_llm": {"generator": "g", "judge": "j", "judge_prompt_version": "v1"}}
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


def test_repeat_of_must_resolve_and_no_record_writes_nothing(runner, tmp_path, capsys):
    assert runner.main(_argv(tmp_path, "--repeat-of", "000000000000")) == 2
    assert "no evaluation record 000000000000" in capsys.readouterr().out
    assert runner.main(_argv(tmp_path, "--no-record")) == 0
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == []
    assert runner.main(_argv(tmp_path, "--resume-unrecorded")) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert runner.main(_argv(tmp_path, "--repeat-of", rec["record_id"], "--checkpoint",
                             str(tmp_path / "results" / "ckpt2.jsonl"))) == 0
    repeat = max(EvaluationRecordStore(tmp_path, create=False).list_records(), key=lambda r: r["started_at"])
    assert repeat["relations"]["repeat_of"] == rec["record_id"]


def test_a_refused_live_gate_records_nothing(runner, monkeypatch, tmp_path):
    def refuse():
        raise harness.LiveGateError("gate")
    monkeypatch.setattr(runner.harness, "_require_live_gate", refuse)
    with pytest.raises(harness.LiveGateError):
        runner.main(_argv(tmp_path))
    assert not (tmp_path / "evaluation_records").exists()


def _july(name: str) -> bytes:
    return (ROOT / "eval" / "results" / name).read_bytes()


def test_a_default_path_resume_over_the_july_checkpoint_bytes_refuses_and_records_nothing(runner, monkeypatch,
                                                                                         tmp_path, capsys):
    results = tmp_path / "results"
    results.mkdir()
    ckpt, summary = results / "ablation_checkpoint.jsonl", results / "ablation_summary.json"
    ckpt.write_bytes(_july("ablation_checkpoint.jsonl"))
    monkeypatch.setattr(runner, "CHECKPOINT", ckpt)
    monkeypatch.setattr(runner, "SUMMARY", summary)
    for extra in ((), ("--resume-unrecorded",), ("--no-record",)):
        assert runner.main(["--dump-dir", str(tmp_path), *extra]) == 2
        assert (f"refusing to write {ckpt}: its bytes are the July 2026 measurement; pass --summary or "
                "--checkpoint with another path") in capsys.readouterr().out
    assert ckpt.read_bytes() == _july("ablation_checkpoint.jsonl") and not summary.exists()
    assert not (tmp_path / "evaluation_records").exists() or EvaluationRecordStore(
        tmp_path, create=False).list_records() == []


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
    assert rec["notes"] == ["resumed from a checkpoint no record names"]
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
    assert resumed["notes"] == [] and resumed["counts"]["units_resumed"] == 1


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

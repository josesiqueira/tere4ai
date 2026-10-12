"""B164: E6 with a unit's items in flight writes the summary and the checkpoint of one
at a time, and each unit's usage stays the usage of its own calls. Offline: the
strategies are replaced by ones that call a real OpenAIGenerator over a stub transport
(its counts go through the client's lock) and answer later items first."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

from tere4ai.eval.evaluation_record import EvaluationRecordStore
from tere4ai.extract_norms.model_clients import OpenAIGenerator, _new_usage

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [{"id": f"gold:cls-{n:02d}", "prompt": "p", "gold": "high"} for n in range(1, 24)]


def _stub(model):
    client = OpenAIGenerator.__new__(OpenAIGenerator)
    client.model, client.usage = model, _new_usage()

    def create(**kwargs):
        item_id = kwargs["messages"][1]["content"]
        time.sleep(0.002 * (24 - int(item_id[-2:])))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"answer {item_id}"))],
                               usage=SimpleNamespace(prompt_tokens=len(item_id), completion_tokens=2))

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client


def _runner(monkeypatch, run_dir):
    spec = importlib.util.spec_from_file_location("run_ablations", ROOT / "scripts" / "run_ablations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (run_dir / "layer1.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "nodes": [], "edges": []}))
    (run_dir / "norms_core.json").write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [], "judge_runs": []}))
    monkeypatch.setattr(mod, "load_items", lambda b, f: [dict(i) for i in ITEMS])
    monkeypatch.setattr(mod.harness, "_require_live_gate", lambda: None)
    monkeypatch.setattr(mod.harness, "guard_live_config", lambda: type("C", (), {"as_public_dict": staticmethod(
        lambda: {"generator_model": "g", "judge_model": "j"})})())
    monkeypatch.setattr(mod.strategies, "STRATEGY_NAMES", ["plain_llm", "vector_rag"])

    def build(name, **kw):
        def strategy(item):
            if item["id"] == "gold:cls-07" and name == "vector_rag":
                raise ValueError("a malformed answer")  # an item's error, recorded, never a stop
            return {"answer_text": kw["generator"].complete("s", item["id"]), "citations": [], "risk_category": "high"}
        strategy.models = {"generator": "g"}
        return strategy

    monkeypatch.setattr(mod.strategies, "build_strategy", build)
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: _stub("g"))
    monkeypatch.setattr(mod, "AnthropicJudge", lambda cfg, **kw: _stub("j"))
    monkeypatch.setattr(mod, "load_model_config", lambda: object())
    monkeypatch.setattr(mod, "RESULTS_DIR", run_dir / "results")
    return mod


def test_eight_in_flight_write_the_summary_and_checkpoint_of_one_at_a_time(tmp_path, monkeypatch, capsys):
    runs = {}
    for setting in (1, 8):
        run_dir = tmp_path / f"at-{setting}"
        run_dir.mkdir()
        mod = _runner(monkeypatch, run_dir)
        results = run_dir / "results"
        argv = ["--dump-dir", str(run_dir), "--checkpoint", str(results / "ablation_checkpoint.jsonl"),
                "--summary", str(results / "ablation_summary.json"), "--features", str(run_dir / "no_features.json"),
                "--max-in-flight", str(setting)]
        assert mod.main(argv) == 0
        assert f"calls in flight: at most {setting} (--max-in-flight)\n" in capsys.readouterr().out
        (record,) = [r for r in EvaluationRecordStore(run_dir, create=False).list_records() if not r.get("unreadable")]
        runs[setting] = ((results / "ablation_summary.json").read_bytes(),
                         (results / "ablation_checkpoint.jsonl").read_bytes(), record)
    (summary1, checkpoint1, record1), (summary8, checkpoint8, record8) = runs[1], runs[8]
    assert summary8 == summary1 and checkpoint8 == checkpoint1
    units = [json.loads(line) for line in checkpoint1.decode().splitlines()]
    assert [u["unit"] for u in units] == [f"{s}:batch{b}" for s in ("plain_llm", "vector_rag") for b in range(3)]
    assert [u["usage"]["generator"]["calls"] for u in units] == [10, 10, 3, 9, 10, 3]
    assert list(units[3]["results"]) == [i["id"] for i in ITEMS[:10]] and "error" in units[3]["results"]["gold:cls-07"]
    assert (record1["config"]["max_in_flight"], record8["config"]["max_in_flight"]) == (1, 8)
    for key in ("usage", "counts"):
        assert record8[key] == record1[key], key
    assert record8["outcome"]["completed_items"] == record1["outcome"]["completed_items"]

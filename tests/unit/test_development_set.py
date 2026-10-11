"""The development set of spec G D-G84 (5): REF-15 items outside the frozen sample (B150).

The first two tests read the frozen benchmark files of data/snapshots/benchmark
and the frozen sample; the rest use mock payloads.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from tests.unit.test_run_ablations_record import runner  # noqa: F401,F811

from tere4ai.eval import harness
from tere4ai.eval.evaluation_record import EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_sha():
    return hashlib.sha256(harness.BENCHMARK_SAMPLE_PATH.read_bytes()).hexdigest()


def test_the_development_set_is_every_ref15_item_outside_the_frozen_sample():
    full = _script("build_full_benchmark_payload").build_payload()
    sample = json.loads(harness.BENCHMARK_SAMPLE_PATH.read_text(encoding="utf-8"))
    dev = harness.development_payload(full, sample, _sample_sha())
    assert (len(dev["scenarios"]), len(dev["qa_pairs"])) == (339 - 32, 137 - 15)
    taken = {s["benchmark_index"] for s in sample["scenarios"]}
    assert not taken & {s["benchmark_index"] for s in dev["scenarios"]}
    assert not {q["benchmark_index"] for q in sample["qa_pairs"]} & {q["benchmark_index"] for q in dev["qa_pairs"]}
    assert dev["development_set"] == {"rule": harness.DEVELOPMENT_RULE, "sample_file": "benchmark_sample.json",
                                      "sample_sha256": _sample_sha(), "scenarios": 307, "qa_pairs": 122}


def test_the_payload_script_writes_the_development_set(tmp_path):
    out = tmp_path / "development_payload.json"
    assert _script("build_full_benchmark_payload").main(["--development-set", "--out", str(out)]) == 0
    items = harness.load_development_items(out)
    assert len(items) == 307 + 122 and all(i["id"].startswith("bench:") for i in items)


def _dev_file(tmp_path, sha=None):
    payload = {"development_set": {"rule": "mock", "sample_file": "benchmark_sample.json",
                                   "sample_sha256": sha or _sample_sha(), "scenarios": 1, "qa_pairs": 1},
               "scenarios": [{"role": "Provider", "intended_use": "u", "system_type": "t", "input_data": "d",
                              "domain": "x", "risk_level": "high-risk", "related_articles": [6],
                              "obligations": [], "benchmark_index": 200}],
               "qa_pairs": [{"question": "q", "answer": "a", "relevant_article": 10, "benchmark_index": 300}]}
    path = tmp_path / "development_payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_payload_that_is_not_the_development_set_is_refused(tmp_path):
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"scenarios": [], "qa_pairs": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a development set payload"):
        harness.load_development_items(plain)
    with pytest.raises(ValueError, match="another frozen sample"):
        harness.load_development_items(_dev_file(tmp_path, sha="0" * 64))


def _feats(tmp_path, by_item):
    path = tmp_path / "development_features.json"
    path.write_text(json.dumps({"features_by_item": by_item}), encoding="utf-8")
    return path


def _argv(tmp_path, tag, *extra):
    return ["--dump-dir", str(tmp_path), "--checkpoint", str(tmp_path / "results" / f"{tag}.jsonl"),
            "--summary", str(tmp_path / "results" / f"{tag}.json"), *extra]


def test_a_development_run_without_every_scenarios_facts_is_refused(runner, tmp_path, capsys):  # noqa: F811
    dev = _dev_file(tmp_path)
    code = runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(tmp_path / "missing.json")))
    assert code == 2 and "missing.json is missing" in capsys.readouterr().out
    code = runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(_feats(tmp_path, {}))))
    assert code == 2 and "lacks 1 development scenario" in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists()


def test_a_development_run_reads_only_the_development_set(runner, tmp_path):  # noqa: F811
    dev = _dev_file(tmp_path)
    feats = _feats(tmp_path, {"bench:scenario:200": {"description": "d", "flags": {}}})
    assert runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(feats))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["config"]["item_set"] == "development"
    assert rec["outcome"]["intended_items"] == ["bench:scenario:200", "bench:qa:300"]
    assert {i["input_kind"] for i in rec["inputs"]} == {"layer1_dump", "norms", "benchmark", "features", "e6_declaration"}


def test_a_main_run_cannot_repeat_a_development_run(runner, tmp_path, capsys):  # noqa: F811
    dev = _dev_file(tmp_path)
    feats = _feats(tmp_path, {"bench:scenario:200": {"description": "d", "flags": {}}})
    assert runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(feats))) == 0
    (first,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    capsys.readouterr()
    assert runner.main(_argv(tmp_path, "main", "--repeat-of", first["record_id"])) == 2
    assert "item_set" in capsys.readouterr().out


def test_a_main_run_on_the_development_payload_is_refused(runner, tmp_path, capsys):  # noqa: F811
    # final review, Task 4 minor: a main run given the development set would be labelled item_set "main";
    # the real load_items refuses the payload before any record or model call
    runner.load_items = _script("run_ablations").load_items
    dev = _dev_file(tmp_path)
    assert runner.main(_argv(tmp_path, "main", "--benchmark", str(dev))) == 2
    out = capsys.readouterr().out
    assert "development_payload.json is a development set payload" in out and "--development-set" in out
    assert not (tmp_path / "evaluation_records").exists()
    # the frozen sample still loads
    items = runner.load_items(None, tmp_path / "no_features.json")
    assert any(i["id"].startswith("bench:") for i in items) and any(i["id"].startswith("gold:") for i in items)

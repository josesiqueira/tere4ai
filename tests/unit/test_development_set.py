"""The development set of spec G D-G84 (5): REF-15 items outside the frozen sample (B150),
and the pilot run's sample drawn from it (B150 Q10, B161).

The first three tests read the frozen benchmark files of data/snapshots/benchmark
and the frozen sample; the rest use mock payloads.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest
from tests.unit.test_run_ablations_record import runner  # noqa: F401,F811

from tere4ai.eval import harness
from tere4ai.eval.ablation_declaration import load_declaration, pilot_draw
from tere4ai.eval.evaluation_record import EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_sha():
    return hashlib.sha256(harness.BENCHMARK_SAMPLE_PATH.read_bytes()).hexdigest()


DRAW = pilot_draw(load_declaration())


def test_the_pilot_sample_is_drawn_from_outside_the_frozen_sample_with_its_composition():
    full = _script("build_full_benchmark_payload").build_payload()
    sample = json.loads(harness.BENCHMARK_SAMPLE_PATH.read_text(encoding="utf-8"))
    dev = harness.development_payload(full, sample, _sample_sha(), DRAW)
    assert (len(dev["scenarios"]), len(dev["qa_pairs"])) == (32, 15)
    assert Counter(s["risk_level"] for s in dev["scenarios"]) == {
        "prohibited": 8, "high-risk": 8, "limited": 8, "minimal": 8}
    assert not {s["benchmark_index"] for s in sample["scenarios"]} & {s["benchmark_index"] for s in dev["scenarios"]}
    assert not {q["benchmark_index"] for q in sample["qa_pairs"]} & {q["benchmark_index"] for q in dev["qa_pairs"]}
    block = dev["development_set"]
    assert block["draw"] == DRAW and block["drawn_from"] == {"scenarios": 307, "qa_pairs": 122}
    assert (block["scenarios"], block["qa_pairs"]) == (32, 15)
    assert block["benchmark_indexes"]["scenarios"] == sorted(s["benchmark_index"] for s in dev["scenarios"])
    assert block["rule"] == harness.DEVELOPMENT_RULE and block["pilot_sample"] == harness.PILOT_SAMPLE_RULE
    assert harness.development_payload(full, sample, _sample_sha(), DRAW) == dev  # the seed fixes the draw
    other = harness.development_payload(full, sample, _sample_sha(), {**DRAW, "seed": 1})
    assert other["development_set"]["benchmark_indexes"] != block["benchmark_indexes"]


# The declared pilot sample (B161 final review Minor 2): the 47 indexes the
# declaration's draw gives on the tracked benchmark files, written out here so
# that a change to the sampling code (the level loop, a pool's order, the use of
# rng.sample) fails this test instead of moving the declared sample silently.
DECLARED_SCENARIOS = [19, 21, 25, 40, 44, 46, 64, 69, 86, 88, 91, 112, 131, 142, 143, 149,
                      177, 178, 182, 196, 209, 220, 226, 239, 248, 251, 275, 276, 281, 313, 318, 335]
DECLARED_QA_PAIRS = [23, 31, 35, 36, 46, 49, 56, 60, 98, 106, 108, 111, 123, 124, 131]


def test_the_pilot_sample_drawn_from_the_tracked_files_is_the_declared_one():
    full = _script("build_full_benchmark_payload").build_payload()
    sample = json.loads(harness.BENCHMARK_SAMPLE_PATH.read_text(encoding="utf-8"))
    dev = harness.development_payload(full, sample, _sample_sha(), DRAW)
    assert DRAW == {"seed": 20261011, "scenarios_per_risk_level": 8, "qa_pairs": 15}
    drawn = dev["development_set"]["benchmark_indexes"]
    assert drawn == {"scenarios": DECLARED_SCENARIOS, "qa_pairs": DECLARED_QA_PAIRS}
    assert harness.PILOT_SAMPLE_INDEXES == drawn
    assert [s["benchmark_index"] for s in dev["scenarios"]] == DECLARED_SCENARIOS
    assert [q["benchmark_index"] for q in dev["qa_pairs"]] == DECLARED_QA_PAIRS


def test_a_payload_recording_other_indexes_than_the_declared_sample_is_refused(tmp_path):
    # the payload is self-consistent (its items are the indexes its block records)
    # and carries the declaration's draw, but one drawn index differs from the
    # declared pilot sample's
    full = _script("build_full_benchmark_payload").build_payload()
    sample = json.loads(harness.BENCHMARK_SAMPLE_PATH.read_text(encoding="utf-8"))
    dev = harness.development_payload(full, sample, _sample_sha(), DRAW)
    taken = {s["benchmark_index"] for s in sample["scenarios"]} | set(DECLARED_SCENARIOS)
    swap = next(s for s in full["scenarios"]
                if s["benchmark_index"] not in taken and s["risk_level"] == dev["scenarios"][0]["risk_level"])
    dev["scenarios"][0] = swap
    dev["scenarios"].sort(key=lambda s: s["benchmark_index"])
    dev["development_set"]["benchmark_indexes"]["scenarios"] = [s["benchmark_index"] for s in dev["scenarios"]]
    path = tmp_path / "development_payload.json"
    path.write_text(json.dumps(dev), encoding="utf-8")
    with pytest.raises(ValueError, match="other indexes than the declared pilot sample's"):
        harness.load_development_items(path, draw=DRAW)
    path.write_text(json.dumps(harness.development_payload(full, sample, _sample_sha(), DRAW)), encoding="utf-8")
    assert len(harness.load_development_items(path, draw=DRAW)) == 47


def test_the_payload_script_writes_the_pilot_sample(tmp_path):
    out = tmp_path / "development_payload.json"
    assert _script("build_full_benchmark_payload").main(["--development-set", "--out", str(out)]) == 0
    items = harness.load_development_items(out, draw=DRAW)
    assert len(items) == 32 + 15 and all(i["id"].startswith("bench:") for i in items)


def test_a_frozen_sample_of_another_composition_is_refused():
    full = _script("build_full_benchmark_payload").build_payload()
    sample = json.loads(harness.BENCHMARK_SAMPLE_PATH.read_text(encoding="utf-8"))
    sample["scenarios"] = sample["scenarios"][1:]  # 7 scenarios in one risk level
    with pytest.raises(ValueError, match="composition"):
        harness.development_payload(full, sample, _sample_sha(), DRAW)


def test_a_payload_drawn_otherwise_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not the declaration's pilot sample"):
        harness.load_development_items(_dev_file(tmp_path, draw={**DRAW, "seed": 1}), draw=DRAW)
    old = _dev_file(tmp_path, draw=None)  # the rule before B161 recorded no draw
    with pytest.raises(ValueError, match="not the declaration's pilot sample"):
        harness.load_development_items(old, draw=DRAW)


@pytest.fixture
def mock_pilot_indexes(monkeypatch):
    """The mock payload's drawn indexes stand for the declared pilot sample's."""
    monkeypatch.setattr(harness, "PILOT_SAMPLE_INDEXES", {"scenarios": [200], "qa_pairs": [300]})


def _dev_file(tmp_path, sha=None, draw=DRAW):
    payload = {"development_set": {"rule": "mock", "sample_file": "benchmark_sample.json",
                                   "sample_sha256": sha or _sample_sha(), "scenarios": 1, "qa_pairs": 1},
               "scenarios": [{"role": "Provider", "intended_use": "u", "system_type": "t", "input_data": "d",
                              "domain": "x", "risk_level": "high-risk", "related_articles": [6],
                              "obligations": [], "benchmark_index": 200}],
               "qa_pairs": [{"question": "q", "answer": "a", "relevant_article": 10, "benchmark_index": 300}]}
    if draw is not None:  # a payload drawn by development_payload records the draw and the drawn indexes
        payload["development_set"]["draw"] = draw
        payload["development_set"]["benchmark_indexes"] = {"scenarios": [200], "qa_pairs": [300]}
    path = tmp_path / "development_payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_payload_whose_items_are_not_the_drawn_ones_is_refused(tmp_path, mock_pilot_indexes):
    # the draw block is right, the items are not the indexes it records
    path = _dev_file(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scenarios"][0]["benchmark_index"] = 201
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="not the drawn ones"):
        harness.load_development_items(path, draw=DRAW)


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


def test_a_development_run_without_every_scenarios_facts_is_refused(runner, tmp_path, capsys, mock_pilot_indexes):  # noqa: F811
    dev = _dev_file(tmp_path)
    code = runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(tmp_path / "missing.json")))
    assert code == 2 and "missing.json is missing" in capsys.readouterr().out
    code = runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(_feats(tmp_path, {}))))
    assert code == 2 and "lacks 1 development scenario" in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists()


@pytest.mark.parametrize("draw", [{**DRAW, "seed": 1}, None], ids=["another_seed", "no_draw"])
def test_a_development_run_on_a_payload_drawn_otherwise_is_refused(runner, tmp_path, capsys, draw):  # noqa: F811
    dev = _dev_file(tmp_path, draw=draw)
    feats = _feats(tmp_path, {"bench:scenario:200": {"description": "d", "flags": {}}})
    code = runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(feats)))
    assert code == 2 and "not the declaration's pilot sample" in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists()


def test_a_development_run_reads_only_the_development_set(runner, tmp_path, mock_pilot_indexes):  # noqa: F811
    dev = _dev_file(tmp_path)
    feats = _feats(tmp_path, {"bench:scenario:200": {"description": "d", "flags": {}}})
    assert runner.main(_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                             "--features", str(feats))) == 0
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["config"]["item_set"] == "development"
    assert rec["outcome"]["intended_items"] == ["bench:scenario:200", "bench:qa:300"]
    assert {i["input_kind"] for i in rec["inputs"]} == {"layer1_dump", "norms", "benchmark", "features", "e6_declaration"}


def test_a_main_run_cannot_repeat_a_development_run(runner, tmp_path, capsys, mock_pilot_indexes):  # noqa: F811
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

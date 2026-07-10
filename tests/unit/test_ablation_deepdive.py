"""Deep-dive analysis tests (#28 tooling): matrices, PRF, abstention."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "ablation_deepdive", ROOT / "scripts" / "ablation_deepdive.py"
)
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)

GOLD = {"i1": "high_risk", "i2": "high_risk", "i3": "minimal_or_none", "i4": "prohibited"}
RESULTS = {
    "i1": {"risk_category": "high_risk"},        # correct, committed
    "i2": {"risk_category": "uncertain"},        # abstained
    "i3": {"risk_category": "high_risk"},        # wrong, committed
    "i4": {"risk_category": None},               # no prediction = abstained
    "qa1": {"risk_category": None},              # not in gold: ignored
}


def test_matrix_and_abstention_math():
    a = dd.analyse_strategy(RESULTS, GOLD)
    assert a["scored_items"] == 4
    assert a["matrix"]["high_risk"]["high_risk"] == 1
    assert a["matrix"]["high_risk"]["uncertain"] == 1
    assert a["matrix"]["minimal_or_none"]["high_risk"] == 1
    assert a["matrix"]["prohibited"]["no_prediction"] == 1
    ab = a["abstention"]
    assert ab["abstained"] == 2 and ab["committed"] == 2
    assert ab["selective_accuracy"] == 0.5
    assert a["overall_accuracy"] == 0.25


def test_per_class_prf():
    a = dd.analyse_strategy(RESULTS, GOLD)
    high = a["per_class"]["high_risk"]
    # tp=1 (i1), fp=1 (i3 predicted high_risk), fn=1 (i2 abstained).
    assert high["support"] == 2
    assert high["precision"] == 0.5
    assert high["recall"] == 0.5


def test_loads_both_artifact_and_checkpoint_formats(tmp_path):
    artifact = tmp_path / "results.json"
    artifact.write_text(
        json.dumps({"results": {"s1": {"items": {"i1": {"risk_category": "high_risk"}}}}})
    )
    checkpoint = tmp_path / "ckpt.jsonl"
    checkpoint.write_text(
        json.dumps({"strategy": "s1", "results": {"i1": {"risk_category": "high_risk"}}})
        + "\n"
    )
    assert dd.load_results(artifact) == dd.load_results(checkpoint)


RUN2 = ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
SUMMARY = ROOT / "eval" / "results" / "ablation_summary.json"


@pytest.mark.skipif(
    not (RUN2.is_file() and SUMMARY.is_file()), reason="run-2 artifacts not present"
)
def test_reconciles_with_the_official_run2_summary():
    gold = dd.gold_risk_by_item()
    per_strategy = dd.load_results(RUN2)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    for name, block in summary["strategies"].items():
        official = block["risk_accuracy_overall"]
        computed = dd.analyse_strategy(per_strategy[name], gold)
        assert computed["scored_items"] == official["total"], name
        assert computed["overall_accuracy"] == pytest.approx(official["accuracy"]), name

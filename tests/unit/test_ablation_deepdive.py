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

GOLD = {"i1": "high_risk", "i2": "high_risk", "i3": "minimal_risk", "i4": "unacceptable_risk"}
RESULTS = {
    "i1": {"risk_category": "high_risk"},        # correct, committed
    "i2": {"risk_category": "undetermined"},        # abstained
    "i3": {"risk_category": "high_risk"},        # wrong, committed
    "i4": {"risk_category": None},               # no prediction = abstained
    "qa1": {"risk_category": None},              # not in gold: ignored
}


def test_matrix_and_abstention_math():
    a = dd.analyse_strategy(RESULTS, GOLD)
    assert a["scored_items"] == 4
    assert a["matrix"]["high_risk"]["high_risk"] == 1
    assert a["matrix"]["high_risk"]["undetermined"] == 1
    assert a["matrix"]["minimal_risk"]["high_risk"] == 1
    assert a["matrix"]["unacceptable_risk"]["no_prediction"] == 1
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
        computed = dd.analyse_strategy(per_strategy[name], gold, legacy_levels=True)
        assert computed["scored_items"] == official["total"], name
        assert computed["overall_accuracy"] == pytest.approx(official["accuracy"]), name


def test_july_checkpoint_values_are_read_through_the_translation_table():
    # B118 (DEC-20, R6): a result file written before the rename carries the old
    # values; the numbers it reproduces must not change.
    old = {
        "i1": {"risk_category": "high_risk"},
        "i2": {"risk_category": "uncertain"},
        "i3": {"risk_category": "transparency_only"},
        "i4": {"risk_category": "prohibited"},
    }
    gold = {"i1": "high_risk", "i2": "high_risk", "i3": "limited_risk", "i4": "unacceptable_risk"}
    a = dd.analyse_strategy(old, gold, legacy_levels=True)
    assert a["matrix"]["high_risk"]["undetermined"] == 1
    assert a["matrix"]["limited_risk"]["limited_risk"] == 1
    assert a["matrix"]["unacceptable_risk"]["unacceptable_risk"] == 1
    assert a["overall_accuracy"] == 3 / 4
    assert a["abstention"]["abstained"] == 1


def test_without_the_legacy_option_an_old_value_is_refused_not_translated():
    # DEC-20: a file with old values is never read as given and never
    # translated on its own: the reader refuses and names the option.
    old = {"i1": {"risk_category": "transparency_only"}, "i2": {"risk_category": "uncertain"}}
    gold = {"i1": "limited_risk", "i2": "high_risk"}
    with pytest.raises(dd.LegacyLevelError, match="--legacy-levels"):
        dd.analyse_strategy(old, gold)


def _write_old_checkpoint(tmp_path):
    ckpt = tmp_path / "old.jsonl"
    ckpt.write_text(
        json.dumps({"strategy": "s1", "results": {"i1": {"risk_category": "prohibited"}}}) + "\n"
    )
    return ckpt


def test_main_refuses_an_old_checkpoint_without_the_flag(tmp_path, capsys, monkeypatch):
    # DEC-20
    monkeypatch.setattr(dd, "gold_risk_by_item", lambda path=None: {"i1": "unacceptable_risk"})
    out = tmp_path / "out.md"
    rc = dd.main(["--results", str(_write_old_checkpoint(tmp_path)), "--out", str(out)])
    assert rc != 0
    err = capsys.readouterr().err
    assert "prohibited" in err
    assert "this file was written before the B118 rename; run with --legacy-levels" in err
    assert not out.exists()


@pytest.mark.skipif(not RUN2.is_file(), reason="run-2 artifacts not present")
def test_main_refuses_the_july_checkpoint_without_the_flag_and_reads_it_with_it(tmp_path, capsys):
    # DEC-20: the committed July numbers come out only with the flag
    out = tmp_path / "out.md"
    assert dd.main(["--results", str(RUN2), "--out", str(out)]) != 0
    assert not out.exists()
    capsys.readouterr()
    assert dd.main(["--results", str(RUN2), "--out", str(out), "--legacy-levels"]) == 0
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    printed = capsys.readouterr().out
    for name, block in summary["strategies"].items():
        acc = block["risk_accuracy_overall"]["accuracy"]
        assert f"{name}: acc {acc:.3f}" in printed

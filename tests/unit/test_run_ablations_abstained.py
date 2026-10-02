"""run_ablations counts an undetermined prediction as abstained (B118)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "run_ablations_abstained", ROOT / "scripts" / "run_ablations.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_undetermined_and_missing_predictions_are_abstained():
    assert mod.is_abstained("undetermined")
    assert mod.is_abstained(None)
    assert not mod.is_abstained("high_risk")
    assert not mod.is_abstained("limited_risk")


def test_an_old_value_is_not_translated_on_a_fresh_answer():
    assert not mod.is_abstained("uncertain")


# The summary path: the abstained count is built there from the answers as
# given; going back to an inline tuple or to a translation would fail this.
from tests.unit.test_run_ablations_record import _argv, runner  # noqa: E402,F401


def test_the_summary_counts_only_undetermined_and_none_and_scores_old_values_as_wrong(
    runner, tmp_path  # noqa: F811
):
    import json

    answers = {
        "bench:scenario:1": "undetermined",
        "bench:scenario:2": "uncertain",  # an old value: not an abstention
        "bench:scenario:3": "transparency_only",  # an old value: not correct
        "bench:scenario:4": None,
        "bench:scenario:5": "high_risk",
    }
    items = [
        {"id": i, "kind": "classification", "gold": {"risk_category": "high_risk"}}
        for i in answers
    ]
    runner.load_items = lambda b, f: items

    def fake_build(name, **kw):
        def strategy(item):
            kw["generator"].complete()
            return {"answer_text": "x", "citations": [], "risk_category": answers[item["id"]]}

        strategy.models = {"generator": "g", "judge": "j", "judge_prompt_version": "v1"}
        return strategy

    runner.strategies.build_strategy = fake_build
    assert runner.main(_argv(tmp_path)) == 0
    summary = json.loads((tmp_path / "results" / "ablation_summary.json").read_text())
    block = summary["strategies"]["plain_llm"]["benchmark_freetext_classification"]
    assert block["abstained"] == 2  # "undetermined" and None
    assert block["correct"] == 1  # only the current value "high_risk"

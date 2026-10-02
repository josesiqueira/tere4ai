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


def test_a_july_checkpoint_uncertain_is_still_abstained():
    assert mod.is_abstained("uncertain")

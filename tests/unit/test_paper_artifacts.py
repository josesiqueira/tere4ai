"""Paper artifact generator tests (#58/#59): computed, complete, deterministic."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "make_paper_artifacts", ROOT / "scripts" / "make_paper_artifacts.py"
)
mpa = importlib.util.module_from_spec(_spec)
sys.modules["make_paper_artifacts"] = mpa
_spec.loader.exec_module(mpa)


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("artifacts")
    assert mpa.main(["--out", str(out)]) == 0
    return out


def test_all_expected_outputs_exist(generated):
    expected = {
        "fig_ablation_ladder.png", "fig_ablation_ladder.svg",
        "fig_run1_run2.png", "fig_run1_run2.svg",
        "fig_judge_funnel.png", "fig_judge_funnel.svg",
        "fig_graph_census.png", "fig_graph_census.svg",
        "tab_ablation.tex", "tab_census.tex", "tab_judges.tex",
        "MANIFEST.json",
    }
    if mpa.FULL.exists():  # full-benchmark outputs appear once the #27 run lands
        expected |= {
            "fig_ablation_ladder_full.png",
            "fig_ablation_ladder_full.svg",
            "tab_ablation_full.tex",
        }
    assert {p.name for p in generated.iterdir()} == expected


def test_table_numbers_match_source_artifacts(generated):
    run2 = json.loads((ROOT / "eval/results/ablation_summary.json").read_text())
    tex = (generated / "tab_ablation.tex").read_text()
    for name in mpa.STRATEGY_LABELS:
        bench = run2["strategies"][name]["benchmark_freetext_classification"]
        assert f"& {bench['correct']} &" in tex
    norms = json.loads((ROOT / "data/graph_dumps/norms_core.json").read_text())
    judges = (generated / "tab_judges.tex").read_text()
    assert f"& {len(norms['norms'])} &" in judges


def test_manifest_covers_all_inputs_and_outputs(generated):
    manifest = json.loads((generated / "MANIFEST.json").read_text())
    full = 1 if mpa.FULL.exists() else 0
    assert len(manifest["inputs"]) == len(mpa.INPUTS) + full
    for digest in manifest["inputs"].values():
        assert len(digest) == 64
    assert len(manifest["outputs"]) == 11 + 3 * full


def test_no_forbidden_dashes_in_tex(generated):
    # Escapes, not literals: the repo dash gate scans test sources too.
    em_dash, en_dash = "\u2014", "\u2013"
    for tex in generated.glob("*.tex"):
        text = tex.read_text(encoding="utf-8")
        assert em_dash not in text and en_dash not in text


def test_tex_outputs_are_deterministic(generated, tmp_path):
    assert mpa.main(["--out", str(tmp_path)]) == 0
    names = ["tab_ablation.tex", "tab_census.tex", "tab_judges.tex"]
    if mpa.FULL.exists():
        names.append("tab_ablation_full.tex")
    for name in names:
        assert (tmp_path / name).read_text() == (generated / name).read_text()

"""Unit tests for scripts/sample_judge_decisions.py and
scripts/elicitation_error_report.py.

Covers DEC-11 (evaluation support: judge FA/FR labelling sample and the
run 2 elicitation error report). The sampling tests run on small synthetic payloads (hermetic) plus the real
published artifacts for the determinism and stratum-count checks; the error
report tests run only against the real artifacts and skip when those are
absent. No model, no network, anywhere.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

NORMS_PATH = REPO_ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = REPO_ROOT / "data" / "graph_dumps" / "alignments_core.json"
LAYER1_PATH = REPO_ROOT / "data" / "graph_dumps" / "layer1.json"
CHECKPOINT_PATH = REPO_ROOT / "eval" / "results" / "ablation_checkpoint.jsonl"
FEATURES_PATH = REPO_ROOT / "eval" / "gold" / "benchmark_features.json"
BENCHMARK_PATH = REPO_ROOT / "eval" / "gold" / "benchmark_sample.json"

REAL_DUMPS_PRESENT = all(p.is_file() for p in (NORMS_PATH, ALIGNMENTS_PATH, LAYER1_PATH))
REAL_RUN2_PRESENT = all(
    p.is_file() for p in (CHECKPOINT_PATH, FEATURES_PATH, BENCHMARK_PATH, LAYER1_PATH)
)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sampling = _load_script("sample_judge_decisions")


# Synthetic payloads --------------------------------------------------------


def _norm(i: int, verdict: str) -> tuple[dict, dict]:
    norm_id = f"norm:test:{i}"
    run_id = f"judgerun:extraction:test:{i}"
    norm = {
        "norm_id": norm_id,
        "source_node_id": f"node:{i}",
        "source_span_id": f"span:{i}",
        "deontic_type": "obligation",
        "modal": "shall",
        "actor_explicit": "provider",
        "action": "do",
        "object": "thing",
        "conditions": [],
        "exceptions": [],
        "judge_verdict": verdict,
        "judge_run_id": run_id,
    }
    run = {"id": run_id, "judge_kind": "extraction", "verdict": verdict, "rationale": "r"}
    return norm, run


def _assertion(i: int, verdict: str) -> tuple[dict, dict]:
    run_id = f"judgerun:mapping:test:{i}"
    assertion = {
        "id": f"align:test:{i}",
        "source_norm_id": f"norm:test:{i % 3}",
        "target_id": "hleg:transparency",
        "relation_type": "supports",
        "source_quote": "sq",
        "target_quote": "tq",
        "judge_verdict": verdict,
        "judge_run_id": run_id,
    }
    run = {"id": run_id, "judge_kind": "mapping", "verdict": verdict, "rationale": "r"}
    return assertion, run


def _synthetic_payloads(
    extraction: dict[str, int], mapping: dict[str, int]
) -> tuple[dict, dict, dict]:
    norms, norm_runs, assertions, map_runs = [], [], [], []
    i = 0
    for verdict, count in extraction.items():
        for _ in range(count):
            n, r = _norm(i, verdict)
            norms.append(n)
            norm_runs.append(r)
            i += 1
    j = 0
    for verdict, count in mapping.items():
        for _ in range(count):
            a, r = _assertion(j, verdict)
            assertions.append(a)
            map_runs.append(r)
            j += 1
    norms_payload = {"build": {"build_id": "b-test"}, "norms": norms, "judge_runs": norm_runs}
    alignments_payload = {
        "build": {"build_id": "b-test"},
        "assertions": assertions,
        "judge_runs": map_runs,
    }
    layer1_payload = {
        "build": {"build_id": "b-test"},
        "nodes": [{"id": f"node:{k}", "text": f"text of node {k}"} for k in range(i)],
    }
    return norms_payload, alignments_payload, layer1_payload


# Allocation ----------------------------------------------------------------


def test_allocation_minimum_per_nonempty_stratum_and_exact_total():
    # Quotas: a = 20*100/108 = 18.52, b = c = 20*4/108 = 0.74. Floors with
    # the minimum of 3: a=18, b=3, c=3, sum 24 > 20, so 4 items are trimmed
    # from a (the only stratum above its minimum): a=14.
    sizes = {("e", "a"): 100, ("e", "b"): 4, ("m", "c"): 4}
    alloc = sampling.allocate_stratified(sizes, total=20, minimum=3)
    assert alloc == {("e", "a"): 14, ("e", "b"): 3, ("m", "c"): 3}
    assert sum(alloc.values()) == 20


def test_allocation_caps_at_stratum_size():
    # A stratum smaller than the minimum contributes everything it has.
    sizes = {("e", "a"): 30, ("e", "b"): 2}
    alloc = sampling.allocate_stratified(sizes, total=10, minimum=3)
    assert alloc[("e", "b")] == 2
    assert sum(alloc.values()) == 10


def test_allocation_refuses_population_smaller_than_total():
    with pytest.raises(ValueError, match="smaller than the sample"):
        sampling.allocate_stratified({("e", "a"): 5}, total=10, minimum=3)


def test_allocation_empty_strata_are_ignored():
    sizes = {("e", "a"): 10, ("e", "b"): 0}
    alloc = sampling.allocate_stratified(sizes, total=5, minimum=3)
    assert ("e", "b") not in alloc


# Sheet building on synthetic data ------------------------------------------


def test_sheet_sampling_is_hash_ordered_and_meets_minimums():
    payloads = _synthetic_payloads(
        extraction={"accepted": 30, "rejected": 5, "needs_human_review": 4},
        mapping={"accepted": 20, "rejected": 6},
    )
    sheet = sampling.build_sheet(*payloads, total=20, minimum=3)
    assert sheet["sampling"]["total"] == 20
    by_stratum: dict[tuple[str, str], list[str]] = {}
    for item in sheet["items"]:
        key = (item["stratum"]["judge_kind"], item["stratum"]["verdict"])
        by_stratum.setdefault(key, []).append(item["decision_id"])
        assert item["human_label"] is None
        assert item["human_rationale"] is None
    strata = {(s["judge_kind"], s["verdict"]): s for s in sheet["sampling"]["strata"]}
    for key, ids in by_stratum.items():
        stratum = strata[key]
        assert len(ids) == stratum["sampled"]
        assert stratum["sampled"] >= min(3, stratum["population"])
        # The chosen ids are exactly the first k of the population under
        # sha256-of-id ordering (content-hash seeding, no random module).
        prefix = "judgerun:extraction:test:" if key[0] == "extraction" else "judgerun:mapping:test:"
        population = [
            r["id"]
            for payload in payloads[:2]
            for r in payload.get("judge_runs", [])
            if r["id"].startswith(prefix) and r["verdict"] == key[1]
        ]
        expected = sorted(
            population, key=lambda i: hashlib.sha256(i.encode("utf-8")).hexdigest()
        )[: stratum["sampled"]]
        assert ids == expected


def test_sheet_extraction_items_carry_norm_fields_and_source_excerpt():
    payloads = _synthetic_payloads(extraction={"accepted": 4}, mapping={"accepted": 4})
    sheet = sampling.build_sheet(*payloads, total=8, minimum=3)
    extraction_items = [
        i for i in sheet["items"] if i["stratum"]["judge_kind"] == "extraction"
    ]
    mapping_items = [i for i in sheet["items"] if i["stratum"]["judge_kind"] == "mapping"]
    assert extraction_items and mapping_items
    ex = extraction_items[0]
    assert ex["judged_content"]["deontic_type"] == "obligation"
    assert ex["source_excerpt"]["text"].startswith("text of node")
    mp = mapping_items[0]
    assert mp["judged_content"]["source_quote"] == "sq"
    assert mp["judged_content"]["target_quote"] == "tq"
    # The mapping item resolves its source excerpt through the source norm.
    assert mp["source_excerpt"]["node_id"].startswith("node:")


# Determinism and strata on the real artifacts ------------------------------


@pytest.mark.skipif(not REAL_DUMPS_PRESENT, reason="published graph dumps not present")
def test_real_sampling_is_deterministic_across_two_runs():
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    sheet_1 = sampling.build_sheet(load(NORMS_PATH), load(ALIGNMENTS_PATH), load(LAYER1_PATH))
    sheet_2 = sampling.build_sheet(load(NORMS_PATH), load(ALIGNMENTS_PATH), load(LAYER1_PATH))
    assert sheet_1 == sheet_2
    assert json.dumps(sheet_1, sort_keys=True) == json.dumps(sheet_2, sort_keys=True)


@pytest.mark.skipif(not REAL_DUMPS_PRESENT, reason="published graph dumps not present")
def test_real_sampling_totals_and_stratum_minimums():
    def load(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    sheet = sampling.build_sheet(load(NORMS_PATH), load(ALIGNMENTS_PATH), load(LAYER1_PATH))
    assert sheet["sampling"]["total"] == 50
    assert len(sheet["items"]) == 50
    kinds = {s["judge_kind"] for s in sheet["sampling"]["strata"]}
    assert kinds == {"extraction", "mapping"}
    for stratum in sheet["sampling"]["strata"]:
        assert stratum["population"] > 0
        assert stratum["sampled"] >= min(3, stratum["population"])
        assert stratum["sampled"] <= stratum["population"]


# Compute mode ---------------------------------------------------------------


def _mini_sheet(labels: list[str | None], verdicts: list[str]) -> dict:
    return {
        "items": [
            {
                "decision_id": f"judgerun:test:{i}",
                "judge_run": {"verdict": verdicts[i]},
                "human_label": labels[i],
                "human_rationale": None if labels[i] is None else "because",
            }
            for i in range(len(labels))
        ]
    }


def test_compute_refuses_while_any_human_label_is_null():
    sheet = _mini_sheet(["accept", None, None], ["accepted", "accepted", "rejected"])
    with pytest.raises(ValueError, match="2 of 3 items"):
        sampling.compute_error_rates(sheet)


def test_compute_refuses_invalid_label_values():
    sheet = _mini_sheet(["accept", "maybe"], ["accepted", "rejected"])
    with pytest.raises(ValueError, match="must be one of"):
        sampling.compute_error_rates(sheet)


def test_compute_fa_fr_hand_computed():
    # 5 items: verdicts (accepted, accepted, rejected, rejected, needs_human_review)
    # gold     (accept,   reject,   accept,   reject,   accept)
    # false accept: item 1 (accepted vs gold reject) -> 1 of 2 gold-reject = 0.5
    # false reject: item 2 (rejected vs gold accept) -> 1 of 3 gold-accept = 1/3
    # item 4 abstains (needs_human_review), neither FA nor FR.
    sheet = _mini_sheet(
        ["accept", "reject", "accept", "reject", "accept"],
        ["accepted", "accepted", "rejected", "rejected", "needs_human_review"],
    )
    rates = sampling.compute_error_rates(sheet)
    assert rates["false_accept_rate"] == pytest.approx(0.5)
    assert rates["false_reject_rate"] == pytest.approx(1 / 3)
    assert rates["counts"]["abstained"] == 1
    assert rates["counts"]["scored"] == 5


def test_main_compute_exit_code_2_on_unlabelled_sheet(tmp_path: Path, capsys):
    sheet_path = tmp_path / "sheet.json"
    sheet_path.write_text(
        json.dumps(_mini_sheet(["accept", None], ["accepted", "accepted"])),
        encoding="utf-8",
    )
    rc = sampling.main(["--compute", "--sheet", str(sheet_path)])
    assert rc == 2
    assert "refusing to compute" in capsys.readouterr().out


def test_main_refuses_to_overwrite_a_labelled_sheet(tmp_path: Path, capsys):
    sheet_path = tmp_path / "sheet.json"
    sheet_path.write_text(
        json.dumps(_mini_sheet(["accept"], ["accepted"])), encoding="utf-8"
    )
    rc = sampling.main(["--sheet", str(sheet_path)])
    assert rc == 1
    assert "refusing to overwrite" in capsys.readouterr().out


# Elicitation error report (piece 74) ----------------------------------------


@pytest.mark.skipif(not REAL_RUN2_PRESENT, reason="run 2 artifacts not present")
def test_error_report_finds_exactly_the_three_run2_items(tmp_path: Path):
    report_mod = _load_script("elicitation_error_report")
    results = report_mod.load_strategy_results(CHECKPOINT_PATH, report_mod.STRATEGY)
    from tere4ai.eval.harness import load_benchmark_items

    found = report_mod.find_over_classified(results, load_benchmark_items())
    found_ids = sorted(e["item"]["id"] for e in found)
    assert found_ids == [
        "bench:scenario:159",
        "bench:scenario:161",
        "bench:scenario:76",
    ]
    # 2 limited (transparency_only) -> high_risk, 1 high-risk -> prohibited,
    # matching the RUN2_ANALYSIS.md confusion cells.
    patterns = sorted((e["gold"], e["predicted"]) for e in found)
    assert patterns == [
        ("high_risk", "prohibited"),
        ("transparency_only", "high_risk"),
        ("transparency_only", "high_risk"),
    ]

    # The full report builds against the real artifacts: every verbatim
    # quote, trigger, and counterfactual is verified inside build_report.
    out = tmp_path / "ELICITATION_ERRORS.md"
    rc = report_mod.main(["--out", str(out)])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    for item_id in found_ids:
        assert f"## {item_id}" in text
    assert "flag:predictive_policing_profiling" in text
    assert "domain:critical_infrastructure" in text
    assert "domain:education" in text

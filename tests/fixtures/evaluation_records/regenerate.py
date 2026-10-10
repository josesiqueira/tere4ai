"""Regenerate the evaluation record contract mock data from mock inputs.

@implements: DEC-17
@grounded_by: REF-27, ADD-20

The seventeen mock data files handed to the dashboard (plan 3b, B102) are
the presenter's real output over deterministic mock runs and legacy files:
record ids and timestamps are pinned, every file is written with fixed
bytes, and the byte-stability test in
tests/unit/test_evaluation_record_contract.py fails when the presenter and
the committed mock data part ways.

Run from the repo root: python -m tests.fixtures.evaluation_records.regenerate
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tere4ai.eval import evaluation_record
from tere4ai.eval.evaluation_record import EvaluationRecordStore, sha256_of_file
from tere4ai.eval.present_evaluation import (
    ORDER_SENTENCE,
    group_summaries,
    present_evaluation,
    summary_of,
    synthesise_legacy_evaluations,
)

FIXTURE_DIR = Path(__file__).resolve().parent
# after the last clock tick (2026-09-25T13:00): no record is observed before it started
NOW = datetime(2026, 9, 26, tzinfo=UTC)
FIXED_IDS = ["e6a000000001", "e6a000000002", "e6a000000003", "e6c000000001", "e6d000000001", "e6e000000001",
             "e6f000000001", "e6b000000001", "e6b000000002", "e1a000000001", "e1b000000001", "e1c000000001"]
CLOCK = [f"2026-09-{20 + i // 4:02d}T{10 + i % 4:02d}:00:00+00:00" for i in range(len(FIXED_IDS) * 2)]
PUBLICATION = {"manifest_file": "publications/chain-x.json", "sha256": "1" * 64, "build_id": "build-b+chain-x"}
SAMPLE_ID = "sample-a1b2c3d4e5f6"
# one mock data name per kind of legacy record the presenter synthesises; a legacy
# run is named by its summary file, since the legacy root holds two runs
LEGACY_NAMES = {"sample": "e1_legacy_sheet", "comparison": "e6_legacy_comparison"}
LEGACY_RUN_NAMES = {"ablation_run1_summary.json": "e6_legacy_summary",
                    "ablation_variance_summary.json": "e6_legacy_variance_summary"}


def _dumps(obj: Any) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def _ticker(values: list[str], what: str) -> Callable[[], str]:
    """The next pinned value on each call; one call past the list names the list to extend."""
    it = iter(values)

    def tick() -> str:
        try:
            return next(it)
        except StopIteration:
            raise RuntimeError(f"the pinned {what} list has {len(values)} entries; add one to {what}") from None

    return tick


def _legacy_name(rec: dict[str, Any]) -> str:
    """The mock data name of a legacy record: a run by its summary file, any other kind by its kind."""
    if rec["kind"] == "run":
        summary = rec["outputs"][0]["file"]
        if summary not in LEGACY_RUN_NAMES:
            raise KeyError(f"no mock data file name for the legacy run of {summary}; add one to LEGACY_RUN_NAMES")
        return LEGACY_RUN_NAMES[summary]
    if rec["kind"] not in LEGACY_NAMES:
        raise KeyError(f"no mock data file name for a legacy record of kind {rec['kind']!r}; add one to LEGACY_NAMES")
    return LEGACY_NAMES[rec["kind"]]


def _write(out_dir: Path, name: str, obj: Any, written: list[Path]) -> None:
    """Write one mock data file; a name written twice in one run is refused, never overwritten."""
    path = out_dir / f"{name}.json"
    if path in written:
        raise RuntimeError(f"{path.name} would be written twice; give each record its own name")
    path.write_text(_dumps(obj), encoding="utf-8")
    written.append(path)


@contextmanager
def _pinned(fixed_ids: list[str], clock: list[str]):
    """Pin the store's id and clock generators, and restore them whatever happens:
    the byte-stability test calls main() inside pytest (R2)."""
    originals = evaluation_record._new_id, evaluation_record._now
    evaluation_record._new_id = _ticker(fixed_ids, "FIXED_IDS")  # type: ignore[assignment]
    evaluation_record._now = _ticker(clock, "CLOCK")  # type: ignore[assignment]
    try:
        yield
    finally:
        evaluation_record._new_id, evaluation_record._now = originals


def _build(base: str, publication: dict | None) -> dict[str, Any]:
    return {"base_build_id": base, "publication": publication,
            "publication_reason": None if publication else "no ACTIVE_MANIFEST.json: the facade serves the legacy files"}


def _inputs(tmp: Path) -> list[dict[str, Any]]:
    refs = []
    for kind, name, digest in (("layer1_dump", "layer1.json", "a"), ("norms", "norms_core.json", "b"),
                               ("benchmark", "benchmark_sample.json", "c"), ("gold_seed", "gold_seed.json", "d"),
                               ("features", "benchmark_features.json", "e")):
        refs.append({"input_kind": kind, "file": name, "sha256": digest * 64})
    return refs


def _e6_run(store: EvaluationRecordStore, tmp: Path, base: str, publication: dict | None, *, relations=None,
            status="completed", completed=("gold:cls-01", "gold:cls-02"), counts=None, inputs=None,
            keep=True, error=None) -> str:
    tmp.mkdir(parents=True, exist_ok=True)  # each run writes into its own directory (R3)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=["--summary", "ablation_summary.json"],
                      inputs=inputs or _inputs(tmp), build=_build(base, publication),
                      models={"generator_model": "g", "judge_model": "j"},
                      prompt_versions={"generator": "v1", "judge": "v1"},
                      sampling={"generator": "temperature=0", "judge": "API default"},
                      config={"strategies": ["plain_llm"], "metrics_version": "metrics.v2",
                              "code_version": "0000000000ab", "mode": "live"},
                      item_selection=["gold:cls-01", "gold:cls-02"], intended_items=["gold:cls-01", "gold:cls-02"],
                      relations=relations)
    outputs = []
    if keep:
        (tmp / "ablation_summary.json").write_text('{"strategies": {}}\n')
        (tmp / "ablation_checkpoint.jsonl").write_text('{"unit": "plain_llm:batch0"}\n')
        outputs = [store.keep_output(rid, "summary", tmp / "ablation_summary.json"),
                   store.keep_output(rid, "checkpoint", tmp / "ablation_checkpoint.jsonl")]
    store.finish(rid, status=status, completed_items=list(completed), outputs=outputs, error=error,
                 usage={"generator": {"calls": 2, "input_tokens": 10, "output_tokens": 4},
                        "judge": {"calls": 1, "input_tokens": 5, "output_tokens": 2}} if keep else None,
                 counts=counts or {"items_total": 2, "units_without_usage": 0, "items_with_errors": 0})
    return rid


def _legacy_root(tmp: Path) -> Path:
    results = tmp / "eval" / "results"
    results.mkdir(parents=True)
    (tmp / "eval" / "gold").mkdir()
    (tmp / "docs").mkdir()
    (results / "ablation_run1_summary.json").write_text(_dumps({
        "config": {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}, "items_total": 57,
        "strategies": {n: {} for n in ("plain_llm", "vector_rag", "graph_no_judge", "graph_build_judge", "graph_full")}}))
    # a second legacy run, the repeat the legacy study compares run 1 with (B81 item 16 (c))
    (results / "ablation_variance_summary.json").write_text(_dumps({
        "config": {"generator_model": "gpt-5.2", "judge_model": "claude-opus-4-8"}, "items_total": 57,
        "strategies": {"plain_llm": {}, "graph_full": {}}}))
    (results / "ablation_variance_checkpoint.jsonl").write_text('{"unit": "plain_llm:batch0"}\n')
    (tmp / "docs" / "variance_study.md").write_text(
        "# Variance study\n\n> Generated by scripts/variance_report.py from ablation_run1_checkpoint.jsonl (run A) and "
        "ablation_variance_checkpoint.jsonl (run B);\n")
    (tmp / "eval" / "gold" / "judge_label_sheet.json").write_text(_dumps({
        "builds": {"norms_core": "build-3b753e5e9297"},
        "items": [{"decision_id": f"d{i}", "human_label": None, "judge_run": {"judge_model": "claude-opus-4-8"}}
                  for i in range(50)]}))
    return tmp


def main(out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or FIXTURE_DIR
    written: list[Path] = []
    with _pinned(FIXED_IDS, CLOCK), tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        store = EvaluationRecordStore(tmp / "dumps")
        run1 = _e6_run(store, tmp, "build-b", PUBLICATION)
        run2 = _e6_run(store, tmp / "r2", "build-b", PUBLICATION, relations={"repeat_of": run1})
        run3 = _e6_run(store, tmp / "r3", "build-c", None)
        cmp_id = store.begin(kind="comparison", step="E6", command="variance_report", argv=["--run-a", "a", "--run-b", "b"],
                             inputs=[{"input_kind": "run_a", "file": "ablation_checkpoint.jsonl", "sha256": "1" * 64},
                                     {"input_kind": "run_b", "file": "ablation_checkpoint.jsonl", "sha256": "2" * 64},
                                     {"input_kind": "benchmark", "file": "benchmark_sample.json", "sha256": "c" * 64}],
                             build=_build("build-b", PUBLICATION), config={"code_version": "0000000000ab"},
                             relations={"compares": [run1, None]})
        (tmp / "variance_study.md").write_text("# study\n")
        store.finish(cmp_id, status="completed", completed_items=["gold:cls-01", "gold:cls-02"],
                     intended_items=["gold:cls-01", "gold:cls-02"],
                     outputs=[store.keep_output(cmp_id, "study", tmp / "variance_study.md")],
                     counts={"common_items": 2, "label_flips": 0}, notes=["run_b is named by no record"])
        offline = store.begin(kind="run", step="E6", command="eval_harness", argv=["--strategies", "plain_llm"],
                              inputs=[{"input_kind": "layer1_dump", "file": "(in memory)", "sha256": "a" * 64},
                                      {"input_kind": "norms", "file": "(in memory)", "sha256": "b" * 64},
                                      {"input_kind": "gold_seed", "file": "gold_seed.json", "sha256": "d" * 64}],
                              build=_build("build-b", PUBLICATION),
                              config={"mode": "offline", "note": "no live model was called", "strategies": ["plain_llm"],
                                      "metrics_version": "metrics.v2", "code_version": "0000000000ab"},
                              item_selection=["gold:cls-01"], intended_items=["gold:cls-01"])
        (tmp / "eval_build-b_deadbeef.json").write_text("{}\n")
        store.finish(offline, status="completed", completed_items=["gold:cls-01"],
                     outputs=[store.keep_output(offline, "artifact", tmp / "eval_build-b_deadbeef.json")],
                     counts={"items_total": 1, "items_with_errors": 0})
        partial = _e6_run(store, tmp / "r4", "build-b", PUBLICATION, status="partial", completed=("gold:cls-01",),
                          counts={"items_total": 2, "units_without_usage": 0, "items_with_errors": 1})
        failed = _e6_run(store, tmp / "r5", "build-b", PUBLICATION, status="failed", completed=(), keep=False,
                         error="RuntimeError: inference backend refused the request", counts={"items_total": 2})
        resumed = _e6_run(store, tmp / "r6", "build-b", PUBLICATION,
                          relations={"resumes_record_id": run1},
                          inputs=_inputs(tmp) + [{"input_kind": "checkpoint_resumed", "file": "ablation_checkpoint.jsonl",
                                                  "sha256": "f" * 64}],
                          counts={"items_total": 2, "units_resumed": 1, "units_without_usage": 0, "items_with_errors": 0})
        copymiss = _e6_run(store, tmp / "r7", "build-b", PUBLICATION)
        rec = store.read(copymiss)
        (store.dir / rec["outputs"][0]["copy"]).unlink()
        (store.dir / rec["outputs"][1]["copy"]).write_text("drifted\n")
        sample = store.begin(kind="sample", step="E1", command="sample_judge_decisions",
                             argv=["--sheet", "judge_label_sheet.json"],
                             inputs=[{"input_kind": "norms", "file": "norms_core.json", "sha256": "b" * 64},
                                     {"input_kind": "alignments", "file": "alignments_core.json", "sha256": "9" * 64},
                                     {"input_kind": "layer1_dump", "file": "layer1.json", "sha256": "a" * 64}],
                             build=_build("build-b", PUBLICATION),
                             config={"total": 50, "minimum": 3, "code_version": "0000000000ab",
                                     "strata": [{"judge_kind": "extraction", "verdict": "accepted", "population": 4, "sampled": 2}]},
                             relations={"sample_id": SAMPLE_ID}, intended_items=["jr-1", "jr-2"])
        (tmp / "judge_label_sheet.json").write_text("{}\n")
        (tmp / "judge_label_sheet.md").write_text("# sheet\n")
        store.finish(sample, status="completed", completed_items=["jr-1", "jr-2"],
                     outputs=[store.keep_output(sample, "sheet_json", tmp / "judge_label_sheet.json"),
                              store.keep_output(sample, "sheet_md", tmp / "judge_label_sheet.md")],
                     counts={"population": 4, "sampled": 2, "unjoinable": 0})
        label = store.begin(kind="labelling", step="E1", command="sample_judge_decisions",
                            argv=["--label", "jr-1", "accept", "--by", "Jose"],
                            inputs=[{"input_kind": "sheet_before", "file": "judge_label_sheet.json", "sha256": "3" * 64}],
                            build=_build("build-b", PUBLICATION),
                            config={"by": "Jose", "labels": {"jr-1": "accept", "jr-2": "reject"}, "forced": []},
                            relations={"sample_id": SAMPLE_ID}, intended_items=["jr-1", "jr-2"])
        (tmp / "l").mkdir()
        (tmp / "l" / "judge_label_sheet.json").write_text('{"labelled": true}\n')
        store.finish(label, status="completed", completed_items=["jr-1", "jr-2"],
                     outputs=[store.keep_output(label, "sheet_after", tmp / "l" / "judge_label_sheet.json")],
                     counts={"labelled_now": 2, "labelled_total": 2, "items": 2})
        analysis = store.begin(kind="analysis", step="E1", command="sample_judge_decisions", argv=["--compute"],
                               inputs=[{"input_kind": "sheet_labelled", "file": "judge_label_sheet.json", "sha256": "4" * 64}],
                               build=_build("build-b", PUBLICATION), config={"metrics_version": "metrics.v2"},
                               relations={"sample_id": SAMPLE_ID, "labelling_record_ids": [label]},
                               intended_items=["jr-1", "jr-2"])
        (tmp / "error_rates.json").write_text('{"pooled": {}}\n')
        store.finish(analysis, status="completed", completed_items=["jr-1", "jr-2"],
                     outputs=[store.keep_output(analysis, "error_rates", tmp / "error_rates.json")],
                     counts={"scored": 2, "abstained": 0, "gold_accept": 1, "gold_reject": 1},
                     notes=["sample estimate: population weighting is not designed"])
        names = {run1: "e6_run", run2: "e6_run_repeat", run3: "e6_run_other_build", cmp_id: "e6_comparison",
                 offline: "e6_offline", partial: "e6_partial", failed: "e6_failed", resumed: "e6_resumed",
                 copymiss: "e6_copy_missing", sample: "e1_sample", label: "e1_labelling", analysis: "e1_analysis"}
        presented = {rid: present_evaluation(store.read(rid), store, NOW) for rid in names}
        legacy_root = _legacy_root(tmp / "legacy")
        summary = legacy_root / "eval" / "results" / "ablation_run1_summary.json"
        # the synthetic summary's own digest; no analysis file dates run 1, so it stays undated
        sheet = legacy_root / "eval" / "gold" / "judge_label_sheet.json"
        # the synthetic sheet's own digest stands in for the pinned July sheet digest
        legacy = synthesise_legacy_evaluations(legacy_root, store,
                                               dated_digests={summary.name: sha256_of_file(summary),
                                                              sheet.name: sha256_of_file(sheet)})
        legacy_presented = [present_evaluation(r, store, NOW) for r in legacy]
        for rid, name in names.items():
            _write(out_dir, name, presented[rid], written)
        for rec in legacy_presented:
            _write(out_dir, _legacy_name(rec), rec, written)
        rows = [summary_of(p) for p in presented.values()] + [summary_of(p) for p in legacy_presented]
        listed = {"schema_version": "evaluations_list.v1", "observed_at": NOW.isoformat(),
                  "served_build_id": "build-b+chain-x", "order": ORDER_SENTENCE, "groups": group_summaries(rows)}
        _write(out_dir, "list", listed, written)
    return written


if __name__ == "__main__":
    for p in main():
        print(p)

"""Unit tests for scripts/sample_judge_decisions.py and
scripts/elicitation_error_report.py.

Covers DEC-11 (evaluation support: judge FA/FR labelling sample and the
run 2 elicitation error report) and DEC-17 (the E1 draw act: an immutable
sample id, any-sheet overwrite protection, a sample record). The sampling
tests run on small synthetic payloads (hermetic) plus the real published
artifacts for the determinism and stratum-count checks; the error report
tests run only against the real artifacts and skip when those are absent.
No model, no network, anywhere.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tere4ai.eval import present_evaluation as pe
from tere4ai.eval.evaluation_record import EvaluationRecordStore

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
                "labelled_by": None if labels[i] is None else "tester",
                "labelled_at": None if labels[i] is None else "2026-01-01T00:00:00+00:00",
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
    rates = sampling.compute_error_rates(sheet)["pooled"]
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


# The E1 draw act (DEC-17): an immutable sample id, any-sheet overwrite
# protection, a sample record --------------------------------------------


def _payloads():
    """Norms, alignments and layer1 payloads with 80 joinable decisions: main() always draws TOTAL_SAMPLE (50)
    and allocate_stratified refuses a smaller population."""
    payloads = _synthetic_payloads(extraction={"accepted": 30, "rejected": 12, "needs_human_review": 8},
                                   mapping={"accepted": 20, "rejected": 10})
    return payloads  # the three payloads in the order build_sheet takes them; unpack as line 155 does


def _write_payloads(tmp_path):
    norms, alignments, layer1 = _payloads()
    (tmp_path / "norms_core.json").write_text(json.dumps(norms))
    (tmp_path / "alignments_core.json").write_text(json.dumps(alignments))
    (tmp_path / "layer1.json").write_text(json.dumps(layer1))


def _draw_argv(tmp_path, *extra):
    return ["--dump-dir", str(tmp_path), "--sheet", str(tmp_path / "sheet.json"),
            "--sheet-md", str(tmp_path / "sheet.md"), *extra]


def test_draw_refuses_any_existing_sheet_without_force(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    first = json.loads((tmp_path / "sheet.json").read_text())
    assert sampling.main(_draw_argv(tmp_path)) == 1
    assert "a sheet exists (0 of" in capsys.readouterr().out
    assert json.loads((tmp_path / "sheet.json").read_text()) == first, "an unlabelled sheet is protected too"
    assert sampling.main(_draw_argv(tmp_path, "--force")) == 0
    assert json.loads((tmp_path / "sheet.json").read_text())["sample"]["sample_id"] != first["sample"]["sample_id"]


def test_draw_binds_the_sample_to_the_observed_publication_or_the_base_id(tmp_path):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    store = EvaluationRecordStore(tmp_path, create=False)
    rec = store.read(sheet["sample"]["record_id"])
    assert rec["kind"] == "sample" and rec["relations"]["sample_id"] == sheet["sample"]["sample_id"]
    assert rec["build"]["publication"] is None and rec["build"]["publication_reason"].startswith("no ACTIVE_MANIFEST")
    assert rec["build"]["base_build_id"] == sheet["builds"]["norms_core"]
    assert sheet["sample"]["build"] == rec["build"]
    assert rec["outcome"]["completed_items"] == [it["decision_id"] for it in sheet["items"]]
    assert {i["role"] for i in rec["inputs"]} == {"norms", "alignments", "layer1_dump"}
    assert {o["role"] for o in rec["outputs"]} == {"sheet_json", "sheet_md"}
    assert (store.dir / [o for o in rec["outputs"] if o["role"] == "sheet_json"][0]["copy"]).read_bytes() == (tmp_path / "sheet.json").read_bytes()
    assert rec["counts"]["sampled"] == len(sheet["items"]) and rec["counts"]["unjoinable"] == 0
    assert rec["config"]["strata"] == sheet["sampling"]["strata"] and rec["config"]["population"] == sheet["sampling"]["population"]
    # a publication, once activated, is what the sample binds to
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-abc.json").write_text(json.dumps({
        "build_id": "build-b+chain-abc",
        "files": {"layer1_dump": "layer1.json", "norms": "norms_core.json", "alignments": "alignments_core.json"},
    }))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-abc"}))
    assert sampling.main(_draw_argv(tmp_path, "--force")) == 0
    sheet2 = json.loads((tmp_path / "sheet.json").read_text())
    assert sheet2["sample"]["build"]["publication"]["build_id"] == "build-b+chain-abc"


def test_draw_refuses_when_the_active_publication_names_no_norms_file(tmp_path, capsys):
    _write_payloads(tmp_path)
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-xyz.json").write_text(json.dumps({
        "build_id": "build-xyz",
        "files": {"layer1_dump": "layer1.json"},
    }))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-xyz"}))
    rc = sampling.main(_draw_argv(tmp_path))
    assert rc == 2
    assert "names no norms file" in capsys.readouterr().out
    assert not (tmp_path / "sheet.json").exists()
    assert not (tmp_path / "evaluation_records").exists()
    rc = sampling.main(_draw_argv(
        tmp_path, "--norms", str(tmp_path / "norms_core.json"),
        "--alignments", str(tmp_path / "alignments_core.json"),
    ))
    assert rc == 0
    assert (tmp_path / "sheet.json").exists()


def test_a_draw_with_an_explicit_input_file_binds_to_no_publication(tmp_path):
    _write_payloads(tmp_path)
    (tmp_path / "publications").mkdir()
    (tmp_path / "publications" / "chain-abc.json").write_text(json.dumps({
        "build_id": "build-b+chain-abc",
        "files": {"layer1_dump": "layer1.json", "norms": "norms_core.json", "alignments": "alignments_core.json"},
    }))
    (tmp_path / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": "chain-abc"}))
    assert sampling.main(_draw_argv(tmp_path, "--norms", str(tmp_path / "norms_core.json"))) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    rec = EvaluationRecordStore(tmp_path, create=False).read(sheet["sample"]["record_id"])
    assert rec["build"]["publication"] is None
    assert rec["build"]["publication_reason"] == "explicit input files given; the run did not read the served publication"
    assert sheet["sample"]["build"] == rec["build"]


def test_draw_with_no_record_writes_a_sheet_without_a_record_id(tmp_path):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path, "--no-record")) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    assert sheet["sample"]["record_id"] is None and sheet["sample"]["sample_id"].startswith("sample-")
    assert not (tmp_path / "evaluation_records").exists()


def test_a_no_record_draws_sheet_is_not_synthesised_as_the_july_legacy_sample(tmp_path):
    _write_payloads(tmp_path)
    gold = tmp_path / "root" / "eval" / "gold"
    gold.mkdir(parents=True)
    argv = ["--dump-dir", str(tmp_path), "--sheet", str(gold / "judge_label_sheet.json"),
            "--sheet-md", str(gold / "judge_label_sheet.md"), "--no-record"]
    assert sampling.main(argv) == 0
    records = pe.synthesise_legacy_evaluations(tmp_path / "root", EvaluationRecordStore(tmp_path, create=False))
    assert records == [], "an unrecorded draw is not the July sample, and is not listed"


def test_the_label_act_refuses_a_sheet_without_a_sample_block(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    del sheet["sample"]
    (tmp_path / "sheet.json").write_text(json.dumps(sheet))
    before = (tmp_path / "sheet.json").read_bytes(), (tmp_path / "sheet.md").read_bytes()
    records_before = EvaluationRecordStore(tmp_path, create=False).list_records()
    first = sheet["items"][0]["decision_id"]
    assert sampling.main(_draw_argv(tmp_path, "--label", first, "accept", "--by", "jose")) == 2
    assert (f"refusing to label {tmp_path / 'sheet.json'}: it was not drawn through a recorded draw "
            "(no sample block); draw a recorded sample first") in capsys.readouterr().out
    assert ((tmp_path / "sheet.json").read_bytes(), (tmp_path / "sheet.md").read_bytes()) == before
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == records_before


def test_draw_cleans_up_the_temp_file_and_fails_the_record_when_the_sheet_write_raises(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    real_replace = sampling.os.replace

    def _boom(src, dst, *args, **kwargs):
        # Only the sheet write fails: the record store's own atomic writes
        # (begin, then finish in the except branch) must still land.
        if Path(dst) == tmp_path / "sheet.json":
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(sampling.os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path))
    assert not (tmp_path / "sheet.json").exists()
    assert list(tmp_path.glob("tmp*")) == []
    store = EvaluationRecordStore(tmp_path, create=False)
    records = store.list_records()
    assert len(records) == 1
    assert records[0]["outcome"]["status"] == "failed"
    assert "disk full" in records[0]["outcome"]["error"]


def test_draw_fails_the_record_when_keep_output_raises_after_the_sheet_write(tmp_path, monkeypatch):
    _write_payloads(tmp_path)

    def boom(self, record_id, role, path):
        raise OSError("copy refused")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", boom)
    with pytest.raises(OSError, match="copy refused"):
        sampling.main(_draw_argv(tmp_path))
    assert (tmp_path / "sheet.json").is_file(), "the compatibility file was written"
    (rec,) = EvaluationRecordStore(tmp_path, create=False).list_records()
    assert rec["outcome"]["status"] == "failed" and "copy refused" in rec["outcome"]["error"]


# The E1 label and compute acts (DEC-17): actor and time per item, an
# analysis record with rates per judge kind and pooled -----------------


def test_label_act_records_actor_time_and_a_labelling_record(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    first = sheet["items"][0]["decision_id"]
    assert sampling.main(_draw_argv(tmp_path, "--label", first, "accept")) == 2, "--by is required"
    assert sampling.main(
        _draw_argv(tmp_path, "--label", first, "accept", "--by", "Jose", "--rationale", "clear")
    ) == 0
    after = json.loads((tmp_path / "sheet.json").read_text())
    item = after["items"][0]
    assert item["human_label"] == "accept" and item["human_rationale"] == "clear"
    assert item["labelled_by"] == "Jose" and item["labelled_at"]
    store = EvaluationRecordStore(tmp_path, create=False)
    rec = [r for r in store.list_records() if r["kind"] == "labelling"][0]
    assert rec["config"] == {"by": "Jose", "labels": {first: "accept"}, "forced": []}
    assert rec["relations"]["sample_id"] == sheet["sample"]["sample_id"]
    assert rec["counts"] == {"labelled_now": 1, "labelled_total": 1, "items": len(sheet["items"])}
    assert [i["role"] for i in rec["inputs"]] == ["sheet_before"]
    assert [o["role"] for o in rec["outputs"]] == ["sheet_after"]
    assert sampling.main(_draw_argv(tmp_path, "--label", first, "reject", "--by", "Ana")) == 1
    assert "refusing to relabel" in capsys.readouterr().out
    assert json.loads((tmp_path / "sheet.json").read_text())["items"][0]["human_label"] == "accept"
    assert sampling.main(
        _draw_argv(tmp_path, "--label", first, "reject", "--by", "Ana", "--force")
    ) == 0
    forced = max((r for r in store.list_records() if r["kind"] == "labelling"), key=lambda r: r["ended_at"])
    assert forced["config"]["forced"] == [first]
    assert sampling.main(_draw_argv(tmp_path, "--label", "nope", "accept", "--by", "Jose")) == 2
    assert sampling.main(
        _draw_argv(tmp_path, "--label", first, "maybe", "--by", "Jose", "--force")
    ) == 2


def test_label_file_labels_many_in_one_record(tmp_path):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    ids = [it["decision_id"] for it in sheet["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},accept,ok\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose")) == 0
    rec = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "labelling"][0]
    assert rec["counts"]["labelled_now"] == len(ids) and rec["outcome"]["completed_items"] == ids


def test_compute_refuses_a_label_without_actor_or_time(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    for it in sheet["items"]:
        it["human_label"] = "accept"  # typed by hand, no actor, no time
    (tmp_path / "sheet.json").write_text(json.dumps(sheet))
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 2
    assert "without an actor or a time" in capsys.readouterr().out
    assert not [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "analysis"]


def test_compute_reports_null_on_an_empty_denominator_and_never_zero(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    ids = [it["decision_id"] for it in sheet["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},accept,\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose")) == 0
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 0
    out = capsys.readouterr().out
    assert "false_accept_rate: null (no gold-reject item scored)" in out
    assert "0.0000 (0 of 0" not in out
    store = EvaluationRecordStore(tmp_path, create=False)
    rec = [r for r in store.list_records() if r["kind"] == "analysis"][0]
    rates = json.loads((store.dir / rec["outputs"][0]["copy"]).read_text())
    assert rates["pooled"]["false_accept_rate"] is None and rates["metrics_version"] == "metrics.v2"
    assert set(rates["by_kind"]) <= {"extraction", "alignment"}, "the sheet's 'mapping' kind is reported as alignment"
    assert rec["relations"]["sample_id"] == sheet["sample"]["sample_id"]
    labelling = [r for r in store.list_records() if r["kind"] == "labelling"]
    assert rec["relations"]["labelling_record_ids"] == [r["record_id"] for r in labelling]
    assert rec["notes"] == ["sample estimate: population weighting is not designed"]
    assert rec["counts"]["scored"] == len(ids) and rec["counts"]["abstained"] >= 3, (
        "the minimum per stratum draws abstentions"
    )
    assert rec["outcome"]["intended_items"] == ids and rec["outcome"]["completed_items"] == ids


# Fix round 1: failure-guarded writers for the label and compute acts, and a
# validated --label-file ------------------------------------------------


def test_label_act_fails_the_record_when_the_sheet_write_raises(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    first = sheet["items"][0]["decision_id"]
    real_replace = sampling.os.replace

    def _boom(src, dst, *args, **kwargs):
        # Only the sheet write fails: the store's own atomic writes (begin,
        # then finish in the except branch) must still land.
        if Path(dst) == tmp_path / "sheet.json":
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(sampling.os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path, "--label", first, "accept", "--by", "Jose"))
    store = EvaluationRecordStore(tmp_path, create=False)
    labelling = [r for r in store.list_records() if r["kind"] == "labelling"]
    assert len(labelling) == 1
    assert labelling[0]["outcome"]["status"] == "failed"
    assert "disk full" in labelling[0]["outcome"]["error"]


def test_compute_fails_the_record_when_the_error_rates_write_raises(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    ids = [it["decision_id"] for it in sheet["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},accept,\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose")) == 0
    real_replace = sampling.os.replace
    rates_path = tmp_path / "error_rates.json"

    def _boom(src, dst, *args, **kwargs):
        # Only the error_rates write fails: the store's own atomic writes
        # (begin, then finish in the except branch) must still land.
        if Path(dst) == rates_path:
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(sampling.os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path, "--compute"))
    store = EvaluationRecordStore(tmp_path, create=False)
    analysis = [r for r in store.list_records() if r["kind"] == "analysis"]
    assert len(analysis) == 1
    assert analysis[0]["outcome"]["status"] == "failed"
    assert "disk full" in analysis[0]["outcome"]["error"]


def test_label_file_refuses_a_missing_file_or_missing_columns(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    missing = tmp_path / "nope.csv"
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(missing), "--by", "Jose")) == 2
    assert "label file not found" in capsys.readouterr().out
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("id,label\n1,accept\n")
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(bad_csv), "--by", "Jose")) == 2
    assert "must have the columns decision_id and human_label" in capsys.readouterr().out
    store = EvaluationRecordStore(tmp_path, create=False)
    assert not [r for r in store.list_records() if r["kind"] == "labelling"]
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    assert all(it["human_label"] is None for it in sheet["items"])

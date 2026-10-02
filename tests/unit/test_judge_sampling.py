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
import shutil
import sys
import threading
from pathlib import Path

import pytest

from tere4ai.eval import present_evaluation as pe
from tere4ai.eval.evaluation_record import EvaluationRecordError, EvaluationRecordStore
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.pipeline import extract_norms
from tere4ai.graph_store.build_chain import build_chain

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


def test_the_e1_sheet_shows_the_type_and_folds_the_judges_view():
    """DEC-19 (the E1 sheet shows the type and the judge's view): the
    extractor's type is judged content, a null reads by the scope ("no
    type" inside, "not an operator requirement" outside, ruling 53), the
    judge's view sits in the folded judge block, and a build before DEC-19
    shows neither."""
    norms, alignments, layer1 = _synthetic_payloads(extraction={"accepted": 4}, mapping={})
    norms["norms"][0].update(requirement_type="quality")
    norms["judge_runs"][0].update(judge_type_agrees=False, judge_requirement_type="functional")
    norms["norms"][1].update(requirement_type=None)
    norms["judge_runs"][1].update(judge_type_agrees=None, judge_requirement_type=None)
    norms["norms"][3].update(requirement_type=None, deontic_type="permission")
    sheet = sampling.build_sheet(norms, alignments, layer1, total=4, minimum=4)
    items = {i["decision_id"]: i for i in sheet["items"]}
    typed = items[norms["judge_runs"][0]["id"]]
    assert typed["judged_content"]["requirement_type"] == "quality"
    assert (typed["judge_run"]["judge_type_agrees"], typed["judge_run"]["judge_requirement_type"]) == (False, "functional")
    untouched = items[norms["judge_runs"][2]["id"]]
    assert "requirement_type" not in untouched["judged_content"]
    assert "judge_type_agrees" not in untouched["judge_run"]
    md = sampling.render_sheet_md(sheet)
    assert md.count("- requirement_type: quality") == 1
    assert md.count("- requirement_type: no type") == 1  # in scope, untyped (ruling 53)
    assert md.count("- requirement_type: not an operator requirement") == 1
    folded = md.split("<details>")[1:]
    assert any("requirement type view: disagrees, the judge's type is functional" in block for block in folded)
    assert any("requirement type view: none recorded" in block for block in folded)
    assert "never decides accept or reject (DEC-19)" in sheet["labelling_rule"]


def _span(anchor: str) -> dict:
    return {"span_id": f"span:{anchor}", "snapshot_file": "fake.html", "snapshot_sha256": "0" * 64,
            "start": 0, "end": 10, "anchor": anchor}


B4_UNIT = "eu-ai-act:article-12:paragraph-1"
B4_DUMP = {
    "build": {"build_id": "b-test"},
    "nodes": [
        {"id": "eu-ai-act:article-12", "type": "Article", "number": 12, "title": "Record-keeping",
         "source_span": _span("art_12")},
        {"id": B4_UNIT, "type": "Paragraph", "text": "1. High-risk AI systems shall allow logging.",
         "source_span": _span("012.001")},
        {"id": "eu-ai-act:article-16", "type": "Article", "number": 16, "title": "Obligations of providers",
         "source_span": _span("art_16")},
        {"id": "eu-ai-act:article-16:paragraph-1", "type": "Paragraph",
         "text": "Providers of high-risk AI systems shall ensure the logging.", "source_span": _span("016.001")},
    ],
    "edges": [],
}
B4_GENERATOR = json.dumps({"norms": [{
    "deontic_type": "obligation", "modal": "shall", "actor_explicit": None, "actor_inferred": "provider",
    "actor_inference_source_node_id": "eu-ai-act:article-16", "action": "allow", "object": "logging",
    "conditions": [], "exceptions": [], "lifecycle_phase_ids": [], "requirement_type": "functional"}]})
B4_JUDGE = json.dumps({"verdict": "accepted", "scores": {}, "rationale": "Article 16 assigns it."})


def _b4_sheet(tmp_path, prompt_version):
    generator = FakeClient({B4_UNIT: B4_GENERATOR}, model="fake-generator")
    judge = FakeClient({B4_UNIT: B4_JUDGE}, model="fake-judge")
    result = extract_norms(B4_DUMP, [B4_UNIT], generator, judge, prompt_version=prompt_version,
                           log_path=tmp_path / f"log-{prompt_version}.jsonl")
    payload = {"build": {"build_id": "b-test"}, **result}
    sheet = sampling.build_sheet(payload, {"assertions": [], "judge_runs": []}, B4_DUMP, total=1, minimum=1)
    return sheet, judge.calls[0][1]


def test_the_e1_sheet_shows_the_inference_source_text_the_judge_received(tmp_path):
    """B4 (Jose, 2026-10-01: "Show the same text (Recommended)"): the
    labeller and the v2 judge read the same actor-inference source text."""
    sheet, judge_input = _b4_sheet(tmp_path, "v2")
    (item,) = sheet["items"]
    text = item["actor_inference_source"]
    assert text.startswith("Actor-inference source: eu-ai-act:article-16 (Article)")
    assert "Providers of high-risk AI systems shall ensure the logging." in text
    assert f"{text}\n\nCandidate norm (JSON):" in judge_input
    md = sampling.render_sheet_md(sheet)
    assert "### Actor-inference source (as the judge received it)" in md
    assert "> [eu-ai-act:article-16:paragraph-1] Providers of high-risk AI systems shall ensure the logging." in md


def test_a_v1_judge_run_gets_no_inference_text_on_the_sheet(tmp_path):
    """judge_norms v1 never received the text, so the sheet of a v1 run does
    not show it either: gold and judge keep reading the same material."""
    sheet, judge_input = _b4_sheet(tmp_path, "v1")
    assert "actor_inference_source" not in sheet["items"][0]
    assert "Actor-inference source" not in judge_input


def test_a_judge_run_with_no_prompt_version_is_treated_as_v1(tmp_path):
    """A run recorded before prompt versions existed read no inference text."""
    generator = FakeClient({B4_UNIT: B4_GENERATOR}, model="fake-generator")
    judge = FakeClient({B4_UNIT: B4_JUDGE}, model="fake-judge")
    result = extract_norms(B4_DUMP, [B4_UNIT], generator, judge, prompt_version="v2",
                           log_path=tmp_path / "log-none.jsonl")
    for run in result["judge_runs"]:
        run.pop("prompt_version", None)
    payload = {"build": {"build_id": "b-test"}, **result}
    sheet = sampling.build_sheet(payload, {"assertions": [], "judge_runs": []}, B4_DUMP, total=1, minimum=1)
    assert "actor_inference_source" not in sheet["items"][0]


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


def _publish(dump_dir, files, base="build-b"):
    """A real publication over the files as they are (G1): the manifest names their digests."""
    chain = build_chain(dump_dir / files["layer1_dump"], dump_dir / files["norms"],
                        alignments_path=dump_dir / files["alignments"] if files.get("alignments") else None)
    chain_id = chain["chain_id"]
    (dump_dir / "publications").mkdir(exist_ok=True)
    (dump_dir / "publications" / f"{chain_id}.json").write_text(json.dumps(
        {"build_id": f"{base}+chain-{chain_id}", "chain_id": chain_id, "files": files, "inputs": chain["inputs"]}))
    (dump_dir / "ACTIVE_MANIFEST.json").write_text(json.dumps({"chain_id": chain_id}))
    return chain_id


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
    chain_id = _publish(tmp_path, {"layer1_dump": "layer1.json", "norms": "norms_core.json",
                                   "alignments": "alignments_core.json"})
    assert sampling.main(_draw_argv(tmp_path, "--force")) == 0
    sheet2 = json.loads((tmp_path / "sheet.json").read_text())
    assert sheet2["sample"]["build"]["publication"]["build_id"] == f"build-b+chain-{chain_id}"


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


def test_draw_completes_the_record_and_names_the_copy_when_the_sheet_replace_raises(tmp_path, monkeypatch, capsys):
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
    # Changed by B81 item 34 (record, then replace): the record completes
    # before the sheet takes its bytes, so a failed replace leaves a
    # completed record with its copy, and stderr names the cp that puts it
    # in place.
    assert records[0]["outcome"]["status"] == "completed"
    copy = store.dir / [o for o in records[0]["outputs"] if o["role"] == "sheet_json"][0]["copy"]
    assert f"put the record's copy in place: cp {copy} {tmp_path / 'sheet.json'}" in capsys.readouterr().err


def test_draw_fails_the_record_and_writes_no_sheet_when_keep_output_raises(tmp_path, monkeypatch):
    _write_payloads(tmp_path)

    def boom(self, record_id, role, path, **kwargs):  # B81 item 34: the draw now passes name=
        raise OSError("copy refused")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", boom)
    with pytest.raises(OSError, match="copy refused"):
        sampling.main(_draw_argv(tmp_path))
    # Changed by B81 item 34 (record, then replace): the sheet takes its bytes
    # only after the record completed, so a failed copy writes no sheet.
    assert not (tmp_path / "sheet.json").exists() and list(tmp_path.glob("tmp*")) == []
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


def test_an_unlistable_store_is_a_refusal_in_the_label_act_and_in_compute(tmp_path, monkeypatch, capsys):
    """B81 item 39: an OSError from list_records is a refusal with exit code
    2, never a traceback, and the sheet is left as it was."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = _label_all(tmp_path)
    before = (tmp_path / "sheet.json").read_bytes()

    def unlistable(self):
        raise PermissionError(13, "Permission denied", str(self.dir))
    monkeypatch.setattr(EvaluationRecordStore, "list_records", unlistable)
    capsys.readouterr()
    sheet = tmp_path / "sheet.json"
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "reject", "--by", "Ana", "--force")) == 2
    assert f"refusing to label {sheet}: the evaluation records cannot be listed (" in capsys.readouterr().out
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 2
    assert "refusing to compute: the evaluation records cannot be listed (" in capsys.readouterr().out
    assert (tmp_path / "sheet.json").read_bytes() == before


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


def test_label_act_completes_the_record_and_keeps_the_sheet_when_the_sheet_replace_raises(tmp_path, monkeypatch):
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
    # Changed by B81 item 34 (record, then replace): the record completed
    # before the replace failed; the sheet keeps the draw's bytes and the
    # record's copy holds the label (the item 34 tests cover the way on).
    assert labelling[0]["outcome"]["status"] == "completed"
    assert json.loads((tmp_path / "sheet.json").read_text())["items"][0]["human_label"] is None


def test_compute_completes_the_record_and_names_the_cp_when_the_error_rates_replace_fails(tmp_path, monkeypatch, capsys):
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
    # Changed by B98 seat B P3-2: --compute now stages the rates, keeps the
    # record's copy from the staged file and finishes before the replace, as
    # the draw and the label act do; a replace that fails after the finish
    # leaves the record completed and names the cp that puts its copy in place.
    assert analysis[0]["outcome"]["status"] == "completed"
    copy = store.dir / analysis[0]["outputs"][0]["copy"]
    err = capsys.readouterr().err
    assert f"{rates_path} did not take its bytes (OSError: disk full)" in err and f"cp {copy} {rates_path}" in err
    assert not rates_path.exists() and not list(tmp_path.glob("tmp*.json")), "the staged file is removed"


def test_compute_fails_the_record_when_its_copy_fails_and_writes_no_rates_file(tmp_path, monkeypatch):
    """B98 seat B P3-2: a copy or finish that fails leaves error_rates.json as
    the act found it (here absent) and the record failed."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},accept,\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose")) == 0
    real_keep = EvaluationRecordStore.keep_output

    def failing_keep(self, record_id, role, path, **kwargs):
        if role == "error_rates":
            raise OSError("disk full")
        return real_keep(self, record_id, role, path, **kwargs)

    monkeypatch.setattr(EvaluationRecordStore, "keep_output", failing_keep)
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path, "--compute"))
    analysis = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "analysis"]
    assert [a["outcome"]["status"] for a in analysis] == ["failed"] and "disk full" in analysis[0]["outcome"]["error"]
    assert not (tmp_path / "error_rates.json").exists() and not list(tmp_path.glob("tmp*.json"))


def test_compute_keeps_its_own_rates_when_another_run_rewrites_the_shared_rates_file(tmp_path, monkeypatch):
    """B98 seat B P3-2: two sheets in one directory share error_rates.json
    but not a lock; the record's copy comes from this run's staged file, so
    another run rewriting error_rates.json between the write and the copy
    cannot put its rates under this sheet's record."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},accept,\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose")) == 0
    rates_path = tmp_path / "error_rates.json"
    real_keep = EvaluationRecordStore.keep_output

    def other_run_writes_first(self, record_id, role, path, **kwargs):
        if role == "error_rates":
            rates_path.write_text('{"other": "sheet"}\n')
        return real_keep(self, record_id, role, path, **kwargs)

    monkeypatch.setattr(EvaluationRecordStore, "keep_output", other_run_writes_first)
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (analysis,) = [r for r in store.list_records() if r["kind"] == "analysis"]
    (out,) = analysis["outputs"]
    kept = json.loads((store.dir / out["copy"]).read_text())
    assert "other" not in kept and "pooled" in kept, "the record keeps this sheet's rates"
    assert out["file"] == "error_rates.json"
    assert json.loads(rates_path.read_text()) == kept, "this run's rates take the file's place after the finish"


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


# Fix wave F7: --compute reads the bytes the last label act wrote -----------


def _label_all(tmp_path, label="accept"):
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    ids = [it["decision_id"] for it in sheet["items"]]
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text("decision_id,human_label,human_rationale\n" + "".join(f"{i},{label},\n" for i in ids))
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(csv_path), "--by", "Jose", "--force")) == 0
    return ids


def test_compute_refuses_a_sheet_hand_edited_after_the_last_label_act(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    _label_all(tmp_path)
    store = EvaluationRecordStore(tmp_path, create=False)
    (label_rec,) = [r for r in store.list_records() if r["kind"] == "labelling"]
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    sheet["items"][0]["human_label"] = "reject"  # a hand edit that keeps labelled_by and labelled_at
    (tmp_path / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n")
    capsys.readouterr()
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 2
    assert ("refusing to compute: the sheet's bytes are not the bytes the last label act wrote "
            f"({label_rec['record_id']}); label through --label or --label-file") in capsys.readouterr().out
    assert not [r for r in store.list_records() if r["kind"] == "analysis"]


def test_compute_lists_only_completed_label_acts_and_notes_a_sheet_no_act_names(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    _label_all(tmp_path)
    store = EvaluationRecordStore(tmp_path, create=False)
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    real_keep = EvaluationRecordStore.keep_output

    # Changed by B81 item 34 (record, then replace): a failed sheet replace now
    # comes after a completed record, so the failed act is made by a refused copy
    def _boom(self, record_id, role, path, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", _boom)
    with pytest.raises(OSError):
        _label_all(tmp_path, "reject")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", real_keep)
    assert sampling.main(_draw_argv(tmp_path, "--compute")) == 0
    completed = [r["record_id"] for r in store.list_records()
                 if r["kind"] == "labelling" and r["outcome"]["status"] == "completed"]
    (analysis,) = [r for r in store.list_records() if r["kind"] == "analysis"]
    assert analysis["relations"]["labelling_record_ids"] == completed and len(completed) == 1
    # the same labelled bytes on another store (copied here): computed, with the note
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n")
    assert sampling.main(["--dump-dir", str(other), "--sheet", str(other / "sheet.json"),
                          "--sheet-md", str(other / "sheet.md"), "--compute"]) == 0
    (copied,) = EvaluationRecordStore(other, create=False).list_records()
    assert "no labelling record on this store names the sheet's bytes" in copied["notes"]
    assert copied["relations"]["labelling_record_ids"] == []


# Codex fix wave G4: a label act reads only the bytes the last recorded act wrote


def test_a_label_act_chains_on_the_draw_then_on_the_previous_label_act(tmp_path):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose")) == 0
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "reject", "--by", "Jose")) == 0
    labelling = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "labelling"]
    assert len(labelling) == 2


def test_a_label_act_refuses_a_sheet_hand_edited_after_the_draw_and_records_nothing(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    store = EvaluationRecordStore(tmp_path, create=False)
    (draw,) = store.list_records()
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    sheet["items"][1]["human_label"] = "reject"  # a hand edit riding into the next label act
    (tmp_path / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1) + "\n")
    before = (tmp_path / "sheet.json").read_bytes()
    capsys.readouterr()
    for extra in ((), ("--no-record",)):
        assert sampling.main(_draw_argv(tmp_path, "--label", sheet["items"][0]["decision_id"], "accept",
                                        "--by", "Jose", *extra)) == 2
        assert (f"refusing to label {tmp_path / 'sheet.json'}: its bytes are not the bytes the last recorded "
                f"act wrote ({draw['record_id']})") in capsys.readouterr().out
    assert (tmp_path / "sheet.json").read_bytes() == before
    assert store.list_records() == [draw]


def test_a_label_act_refuses_a_sheet_whose_sample_no_record_names(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path, "--no-record")) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    sample_id = sheet["sample"]["sample_id"]
    capsys.readouterr()
    for extra in ((), ("--no-record",)):
        assert sampling.main(_draw_argv(tmp_path, "--label", sheet["items"][0]["decision_id"], "accept",
                                        "--by", "Jose", *extra)) == 2
        assert (f"refusing to label {tmp_path / 'sheet.json'}: no recorded draw or label act names sample "
                f"{sample_id} on this store") in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists() or EvaluationRecordStore(
        tmp_path, create=False).list_records() == []


def test_an_unrecorded_label_act_breaks_the_chain_for_the_next_recorded_one(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose", "--no-record")) == 0
    capsys.readouterr()
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "accept", "--by", "Jose")) == 2
    assert "its bytes are not the bytes the last recorded act wrote" in capsys.readouterr().out


# B81 item 11: an id named twice in one act is refused, never silently overridden


def test_an_id_named_twice_in_one_act_is_refused_and_nothing_is_written(tmp_path, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    before = (tmp_path / "sheet.json").read_bytes(), (tmp_path / "sheet.md").read_bytes()
    records_before = EvaluationRecordStore(tmp_path, create=False).list_records()
    both = tmp_path / "both.csv"
    both.write_text(f"decision_id,human_label,human_rationale\n{ids[0]},reject,no\n{ids[1]},accept,ok\n")
    capsys.readouterr()
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--label-file", str(both),
                                    "--by", "Jose")) == 2
    assert f"decision ids named more than once in this act (by --label and a --label-file row, or by two rows): " \
           f"{[ids[0]]}" in capsys.readouterr().out
    rows = tmp_path / "rows.csv"
    # an exact duplicate row is refused too: two concatenated files, one of them stale
    rows.write_text(f"decision_id,human_label,human_rationale\n{ids[1]},accept,ok\n{ids[1]},accept,ok\n")
    assert sampling.main(_draw_argv(tmp_path, "--label-file", str(rows), "--by", "Jose")) == 2
    assert f"{[ids[1]]}" in capsys.readouterr().out
    assert ((tmp_path / "sheet.json").read_bytes(), (tmp_path / "sheet.md").read_bytes()) == before
    assert EvaluationRecordStore(tmp_path, create=False).list_records() == records_before
    # distinct ids combine in one act, one record
    distinct = tmp_path / "distinct.csv"
    distinct.write_text(f"decision_id,human_label,human_rationale\n{ids[0]},reject,no\n{ids[1]},accept,ok\n")
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[2], "accept", "--label-file", str(distinct),
                                    "--by", "Jose")) == 0
    labels = {it["decision_id"]: it["human_label"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]}
    assert (labels[ids[0]], labels[ids[1]], labels[ids[2]]) == ("reject", "accept", "accept")
    (rec,) = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "labelling"]
    assert rec["config"]["labels"] == {ids[2]: "accept", ids[0]: "reject", ids[1]: "accept"}


# B81 item 2: one act at a time per sheet, so two label acts never lose a label


@pytest.mark.parametrize("same_id", [False, True])
def test_two_concurrent_label_acts_keep_both_labels(tmp_path, monkeypatch, capsys, same_id):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    inside, release = threading.Event(), threading.Event()
    real_begin = EvaluationRecordStore.begin

    def paused_begin(self, **kwargs):
        # the first act stops inside its read-modify-write, after reading the sheet
        record_id = real_begin(self, **kwargs)
        if kwargs["kind"] == "labelling" and kwargs["config"]["labels"] == {ids[0]: "accept"}:
            inside.set()
            release.wait(10)
        return record_id

    monkeypatch.setattr(EvaluationRecordStore, "begin", paused_begin)
    codes: dict[str, int] = {}
    first = threading.Thread(target=lambda: codes.__setitem__(
        "first", sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))))
    target = ids[0] if same_id else ids[1]
    second = threading.Thread(target=lambda: codes.__setitem__(
        "second", sampling.main(_draw_argv(tmp_path, "--label", target, "reject", "--by", "Ana"))))
    first.start()
    assert inside.wait(10)
    second.start()
    try:
        second.join(0.5)
        assert second.is_alive(), "the second act waits while the first holds the sheet"
    finally:
        release.set()
    first.join(10)
    second.join(10)
    labels = {it["decision_id"]: it["human_label"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]}
    acts = sorted((r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "labelling"),
                  key=lambda r: r["ended_at"])
    captured = capsys.readouterr()
    assert "waiting for it to end" in captured.err
    if same_id:
        # the second act reads the first act's label and refuses to replace it without --force
        assert codes == {"first": 0, "second": 1} and "refusing to relabel" in captured.out
        assert labels[ids[0]] == "accept" and [a["outcome"]["status"] for a in acts] == ["completed"]
        return
    assert codes == {"first": 0, "second": 0}
    assert (labels[ids[0]], labels[ids[1]]) == ("accept", "reject"), "neither act lost the other's label"
    assert [a["outcome"]["status"] for a in acts] == ["completed", "completed"]
    assert acts[1]["inputs"][0]["sha256"] == acts[0]["outputs"][0]["sha256"], "the second read what the first wrote"


def test_a_label_act_through_a_symbolic_link_writes_the_sheet_it_names(tmp_path, capsys):
    """B98 seat B P3-1: --sheet and --sheet-md are resolved once, so a link
    and its target take one lock and the replace writes the target, not the
    link; before, the first act replaced the link with a regular file and
    the two paths held two sheets from then on."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    link, link_md = tmp_path / "link.json", tmp_path / "link.md"
    link.symlink_to("sheet.json")
    link_md.symlink_to("sheet.md")
    through_link = ["--dump-dir", str(tmp_path), "--sheet", str(link), "--sheet-md", str(link_md)]
    md_before = (tmp_path / "sheet.md").read_text()
    assert sampling.main([*through_link, "--label", ids[0], "accept", "--by", "Jose"]) == 0
    assert link.is_symlink() and link_md.is_symlink(), "the links still point at the sheet"
    labels = {it["decision_id"]: it["human_label"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]}
    assert labels[ids[0]] == "accept", "the label landed in the sheet the link names"
    assert (tmp_path / "sheet.md").read_text() != md_before, "the reading copy the link names was rewritten"
    capsys.readouterr()
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "reject", "--by", "Ana")) == 0, capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.glob("*.lock")) == ["sheet.json.lock"]


def test_a_label_act_or_compute_on_a_missing_sheet_creates_no_directory_and_no_lock(tmp_path, capsys):
    missing = tmp_path / "no_such_dir" / "sheet.json"
    for extra in (("--label", "d1", "accept", "--by", "Jose"), ("--compute",)):
        assert sampling.main(["--dump-dir", str(tmp_path), "--sheet", str(missing),
                              "--sheet-md", str(tmp_path / "no_such_dir" / "sheet.md"), *extra]) == 2
        assert f"no sheet at {missing}: draw one first, or pass --sheet" in capsys.readouterr().out
    assert not (tmp_path / "no_such_dir").exists()


# B81 item 34: the record completes before the sheet takes its bytes, and a
# refusal over unrecorded bytes names the recorded copy to put in place


def _sheet_bytes(tmp_path):
    return (tmp_path / "sheet.json").read_bytes(), (tmp_path / "sheet.md").read_bytes()


def test_a_label_act_whose_output_copy_fails_leaves_the_sheet_as_it_found_it(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    before = _sheet_bytes(tmp_path)
    real_keep = EvaluationRecordStore.keep_output

    def refuse_copy(self, record_id, role, path, **kwargs):
        if role == "sheet_after":
            raise OSError("copy refused")
        return real_keep(self, record_id, role, path, **kwargs)

    monkeypatch.setattr(EvaluationRecordStore, "keep_output", refuse_copy)
    with pytest.raises(OSError, match="copy refused"):
        sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))
    assert _sheet_bytes(tmp_path) == before, "the sheet and its reading copy are as the act found them"
    assert list(tmp_path.glob("tmp*")) == []
    (failed,) = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r["kind"] == "labelling"]
    assert failed["outcome"]["status"] == "failed" and "copy refused" in failed["outcome"]["error"]
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", real_keep)
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose")) == 0, (
        "the next act chains on the draw, no --force re-draw needed")


def test_a_label_act_whose_finish_is_refused_leaves_the_sheet_as_it_found_it(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    before = _sheet_bytes(tmp_path)
    real_finish = EvaluationRecordStore.finish

    def refuse_completed(self, record_id, *, status, **kwargs):
        if status == "completed":
            raise EvaluationRecordError("refusing to finish: disk quota")
        return real_finish(self, record_id, status=status, **kwargs)

    monkeypatch.setattr(EvaluationRecordStore, "finish", refuse_completed)
    with pytest.raises(EvaluationRecordError, match="disk quota"):
        sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))
    assert _sheet_bytes(tmp_path) == before
    monkeypatch.setattr(EvaluationRecordStore, "finish", real_finish)
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose")) == 0


def test_a_failed_replace_after_the_record_completed_keeps_the_labels_through_the_named_copy(
        tmp_path, monkeypatch, capsys):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    real_replace = sampling.os.replace

    def sheet_replace_fails(src, dst, *args, **kwargs):
        if Path(dst) == tmp_path / "sheet.json":
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(sampling.os, "replace", sheet_replace_fails)
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))
    store = EvaluationRecordStore(tmp_path, create=False)
    (act,) = [r for r in store.list_records() if r["kind"] == "labelling"]
    copy = store.dir / act["outputs"][0]["copy"]
    assert act["outcome"]["status"] == "completed"
    assert f"put the record's copy in place: cp {copy} {tmp_path / 'sheet.json'}" in capsys.readouterr().err
    monkeypatch.setattr(sampling.os, "replace", real_replace)
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "accept", "--by", "Jose")) == 2
    out = capsys.readouterr().out
    assert f"to go on from that act, put its recorded copy in place: cp {copy} {tmp_path / 'sheet.json'}" in out
    assert "labels typed into the sheet by hand are not kept: put them in a --label-file CSV first" in out
    shutil.copyfile(copy, tmp_path / "sheet.json")
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "accept", "--by", "Jose")) == 0
    labels = {it["decision_id"]: it["human_label"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]}
    assert (labels[ids[0]], labels[ids[1]]) == ("accept", "accept"), "the failed replace's label was kept"


def test_a_failed_label_act_leaves_no_reading_copy_where_there_was_none(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    (tmp_path / "sheet.md").unlink()
    before = (tmp_path / "sheet.json").read_bytes()

    def refuse_copy(self, record_id, role, path, **kwargs):
        raise OSError("copy refused")

    monkeypatch.setattr(EvaluationRecordStore, "keep_output", refuse_copy)
    with pytest.raises(OSError, match="copy refused"):
        sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))
    assert (tmp_path / "sheet.json").read_bytes() == before
    assert not (tmp_path / "sheet.md").exists(), "no reading copy showing the failed act's labels"


def test_a_forced_draw_that_fails_leaves_the_labelled_sheet_in_place(tmp_path, monkeypatch):
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose")) == 0
    before = _sheet_bytes(tmp_path)

    def refuse_copy(self, record_id, role, path, **kwargs):
        raise OSError("copy refused")

    monkeypatch.setattr(EvaluationRecordStore, "keep_output", refuse_copy)
    with pytest.raises(OSError, match="copy refused"):
        sampling.main(_draw_argv(tmp_path, "--force"))
    assert _sheet_bytes(tmp_path) == before
    monkeypatch.undo()
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "reject", "--by", "Jose")) == 0


def test_the_sheet_tells_the_labeller_to_label_through_the_label_act(tmp_path):
    """B81 item 34 review I2: the sheet used to ask for labels typed into the
    JSON, which the chain check refuses and the named cp would drop."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    md = (tmp_path / "sheet.md").read_text()
    assert "--label-file <csv> --by <name>" in sheet["purpose"] and "Fill human_label" not in sheet["purpose"]
    assert "--label-file <csv>" in md and "fill in judge_label_sheet.json" not in md
    assert "never edit judge_label_sheet.json by hand" in md
    assert "- human_label (accept | reject): record it with --label or --label-file" in md


def _reading_copy_replace_fails(monkeypatch, md_path):
    real_replace = sampling.os.replace

    def fail(src, dst, *args, **kwargs):
        if Path(dst) == md_path:
            raise OSError("disk full")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(sampling.os, "replace", fail)


def test_a_draw_whose_reading_copy_replace_fails_names_the_markdown_copy(tmp_path, monkeypatch, capsys):
    """B81 item 34 fix round 1: the sheet took its bytes, only the reading
    copy did not, so the line names the reading copy and its recorded copy."""
    _write_payloads(tmp_path)
    _reading_copy_replace_fails(monkeypatch, tmp_path / "sheet.md")
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path))
    store = EvaluationRecordStore(tmp_path, create=False)
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "completed"
    md_copy = store.dir / [o for o in rec["outputs"] if o["role"] == "sheet_md"][0]["copy"]
    json_copy = store.dir / [o for o in rec["outputs"] if o["role"] == "sheet_json"][0]["copy"]
    assert (tmp_path / "sheet.json").read_bytes() == json_copy.read_bytes(), "the sheet took its bytes"
    assert not (tmp_path / "sheet.md").exists() and list(tmp_path.glob("tmp*")) == []
    err = capsys.readouterr().err
    assert f"put the record's Markdown copy in place: cp {md_copy} {tmp_path / 'sheet.md'}" in err
    assert "did not take its bytes" in err and f"{tmp_path / 'sheet.json'} did not take" not in err


def test_a_label_act_whose_reading_copy_replace_fails_says_the_next_act_rewrites_it(tmp_path, monkeypatch, capsys):
    """B81 item 34 fix round 1: the label act keeps no Markdown copy, so the
    line says the next label act rewrites the reading copy; the chain holds."""
    _write_payloads(tmp_path)
    assert sampling.main(_draw_argv(tmp_path)) == 0
    ids = [it["decision_id"] for it in json.loads((tmp_path / "sheet.json").read_text())["items"]]
    md_before = (tmp_path / "sheet.md").read_bytes()
    _reading_copy_replace_fails(monkeypatch, tmp_path / "sheet.md")
    with pytest.raises(OSError, match="disk full"):
        sampling.main(_draw_argv(tmp_path, "--label", ids[0], "accept", "--by", "Jose"))
    err = capsys.readouterr().err
    assert f"the reading copy {tmp_path / 'sheet.md'} did not take its bytes" in err
    assert "the next label act rewrites the reading copy" in err and "cp " not in err
    assert (tmp_path / "sheet.md").read_bytes() == md_before
    monkeypatch.undo()
    assert sampling.main(_draw_argv(tmp_path, "--label", ids[1], "accept", "--by", "Jose")) == 0
    assert "- human_label: accept" in (tmp_path / "sheet.md").read_text()

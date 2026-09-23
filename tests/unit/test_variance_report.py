"""Variance report tests (#60, DEC-17): flips, citation Jaccard, determinism check.

DEC-17: the comparison record names runs by digest only, binds to no
publication, and ends failed on any exception from begin to finish."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tere4ai.eval.evaluation_record import EvaluationRecordStore

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "variance_report", ROOT / "scripts" / "variance_report.py"
)
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)

GOLD = {"c1": "high_risk", "c2": "minimal_or_none", "c3": "prohibited"}
RUN_A = {
    "c1": {"risk_category": "high_risk", "citations": ["eu-ai-act:article-6"]},
    "c2": {"risk_category": "minimal_or_none", "citations": []},
    "c3": {"risk_category": "uncertain", "citations": []},
    "q1": {"risk_category": None, "answer_text": "same", "citations": ["eu-ai-act:article-13"]},
    "q2": {"risk_category": None, "answer_text": "alpha", "citations": []},
}
RUN_B = {
    "c1": {"risk_category": "high_risk", "citations": ["eu-ai-act:article-6"]},
    "c2": {"risk_category": "transparency_only", "citations": []},  # flip
    "c3": {"risk_category": None, "citations": []},  # uncertain -> no_prediction: flip
    "q1": {"risk_category": None, "answer_text": "same", "citations": ["eu-ai-act:article-13"]},
    "q2": {"risk_category": None, "answer_text": "beta", "citations": []},
}


def test_flip_counting_includes_abstention_form_changes():
    c = vr.compare_strategy(RUN_A, RUN_B, GOLD)
    assert c["labelled_items"] == 3
    assert c["label_flips"] == 2
    flipped = {f["item"]: (f["run_a"], f["run_b"]) for f in c["flip_details"]}
    assert flipped["c2"] == ("minimal_or_none", "transparency_only")
    assert flipped["c3"] == ("uncertain", "no_prediction")


def test_citation_jaccard_and_qa_identity():
    c = vr.compare_strategy(RUN_A, RUN_B, GOLD)
    # only c1 and q1 emitted citations; both sets identical -> mean 1.0
    assert c["citing_items"] == 2
    assert c["citation_jaccard_mean"] == 1.0
    assert c["qa_items"] == 2 and c["qa_answer_identical"] == 1


def test_jaccard_of_disjoint_and_empty_sets():
    assert vr._jaccard(set(), set()) == 1.0
    assert vr._jaccard({"a"}, {"b"}) == 0.0
    assert vr._jaccard({"a", "b"}, {"b", "c"}) == 1 / 3


def test_determinism_check_flags_graph_flips():
    comparisons = {
        "graph_full": vr.compare_strategy(RUN_A, RUN_B, GOLD),
        "plain_llm": vr.compare_strategy(RUN_A, RUN_A, GOLD),
    }
    text = vr.render_markdown(Path("a.jsonl"), Path("b.jsonl"), comparisons)
    assert "DETERMINISM CHECK FAILED" in text
    assert "graph_full" in text


def test_determinism_check_passes_on_identical_graph_runs():
    comparisons = {"graph_full": vr.compare_strategy(RUN_A, RUN_A, GOLD)}
    text = vr.render_markdown(Path("a.jsonl"), Path("b.jsonl"), comparisons)
    assert "flipped 0 labels" in text
    assert "DETERMINISM CHECK FAILED" not in text


def _checkpoint(path, results_by_item):
    path.write_text(json.dumps({"unit": "plain_llm:batch0", "strategy": "plain_llm", "results": results_by_item}) + "\n")


def test_main_records_a_comparison_naming_the_runs_it_can_resolve(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    r = {"i1": {"risk_category": "high", "citations": [], "answer_text": "x"}, "i2": {"risk_category": "high", "citations": [], "answer_text": "y"}}
    _checkpoint(a, r)
    _checkpoint(b, {**r, "i2": {**r["i2"], "risk_category": "low"}})
    bench = tmp_path / "bench.json"
    bench.write_text(json.dumps({"scenarios": [], "qa": []}))
    store = EvaluationRecordStore(tmp_path)
    rid = store.begin(kind="run", step="E6", command="run_ablations", argv=[], inputs=[],
                      build={"base_build_id": None, "publication": None, "publication_reason": None})
    store.finish(rid, status="completed", outputs=[store.keep_output(rid, "checkpoint", a)])
    out = tmp_path / "study.md"
    assert vr.main(["--run-a", str(a), "--run-b", str(b), "--benchmark", str(bench), "--out", str(out),
                    "--dump-dir", str(tmp_path)]) == 0
    rec = [x for x in store.list_records() if x["kind"] == "comparison"][0]
    assert rec["relations"]["compares"] == [rid, None] and "run_b is named by no record" in rec["notes"]
    assert {i["role"] for i in rec["inputs"]} == {"run_a", "run_b", "benchmark"}
    assert rec["outcome"]["status"] == "completed" and rec["outcome"]["completed_items"] == ["i1", "i2"]
    assert rec["counts"]["common_items"] == 2 and rec["counts"]["label_flips"] == 0, "flips count gold items only (R7)"
    (study,) = rec["outputs"]
    assert study["role"] == "study" and (store.dir / study["copy"]).read_bytes() == out.read_bytes()
    assert rec["models"] is None
    assert rec["build"]["publication"] is None
    assert rec["build"]["publication_reason"] == "a comparison reads run files, not the served build"


def test_main_removes_the_temp_file_when_the_markdown_write_fails(tmp_path, monkeypatch):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    r = {"i1": {"risk_category": "high", "citations": [], "answer_text": "x"}}
    _checkpoint(a, r)
    _checkpoint(b, r)
    bench = tmp_path / "bench.json"
    bench.write_text(json.dumps({"scenarios": [], "qa": []}))
    store = EvaluationRecordStore(tmp_path)
    out = tmp_path / "study.md"

    real_replace = vr.os.replace

    def boom(src, dst):
        if Path(dst) == out:
            raise RuntimeError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(vr.os, "replace", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        vr.main(["--run-a", str(a), "--run-b", str(b), "--benchmark", str(bench), "--out", str(out),
                "--dump-dir", str(tmp_path)])

    assert not [p for p in tmp_path.iterdir() if p.name.startswith("tmp") and p.suffix == ".md"]
    rec = [x for x in store.list_records() if x["kind"] == "comparison"][0]
    assert rec["outcome"]["status"] == "failed"
    assert "disk full" in rec["outcome"]["error"]


def test_a_failing_keep_output_after_the_study_write_fails_the_record(tmp_path, monkeypatch):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    r = {"i1": {"risk_category": "high", "citations": [], "answer_text": "x"}}
    _checkpoint(a, r)
    _checkpoint(b, r)
    bench = tmp_path / "bench.json"
    bench.write_text(json.dumps({"scenarios": [], "qa": []}))
    store = EvaluationRecordStore(tmp_path)
    out = tmp_path / "study.md"

    def boom(self, record_id, role, path):
        raise OSError("copy refused")
    monkeypatch.setattr(EvaluationRecordStore, "keep_output", boom)
    with pytest.raises(OSError, match="copy refused"):
        vr.main(["--run-a", str(a), "--run-b", str(b), "--benchmark", str(bench), "--out", str(out),
                 "--dump-dir", str(tmp_path)])
    assert out.is_file(), "the compatibility file was written"
    (rec,) = store.list_records()
    assert rec["outcome"]["status"] == "failed" and "copy refused" in rec["outcome"]["error"]

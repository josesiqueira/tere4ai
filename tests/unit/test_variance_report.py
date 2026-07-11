"""Variance report tests (#60): flips, citation Jaccard, determinism check."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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

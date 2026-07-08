"""Unit tests for the M4 evaluation metrics (pure functions, synthetic data).

Every expected value below is hand-computed from the synthetic counts; no
model, no network, no real results file.
"""

import pytest

from tere4ai.eval.metrics import (
    citation_completeness,
    f1,
    hallucinated_citation_rate,
    judge_error_rates,
    precision,
    prf1,
    recall,
    risk_classification_accuracy,
)

# P / R / F1 helpers ----------------------------------------------------------


def test_precision_recall_f1_exact_values():
    # tp=3, fp=1, fn=2: p = 3/4, r = 3/5, f1 = 2*0.75*0.6 / 1.35 = 2/3.
    assert precision(3, 1) == 0.75
    assert recall(3, 2) == 0.6
    assert f1(3, 1, 2) == pytest.approx(2 / 3)
    assert prf1(3, 1, 2) == {
        "precision": 0.75,
        "recall": 0.6,
        "f1": pytest.approx(2 / 3),
    }


def test_prf1_zero_denominators_are_zero_not_error():
    assert precision(0, 0) == 0.0
    assert recall(0, 0) == 0.0
    assert f1(0, 0, 0) == 0.0


# Risk classification accuracy ------------------------------------------------

GOLD_ITEMS = [
    {"id": "i1", "kind": "classification", "gold": {"risk_category": "prohibited"},
     "gold_citations": ["n:a"]},
    {"id": "i2", "kind": "classification", "gold": {"risk_category": "high_risk"},
     "gold_citations": ["n:b", "n:c"]},
    {"id": "i3", "kind": "classification", "gold": {"risk_category": "minimal_or_none"},
     "gold_citations": []},
    {"id": "i4", "kind": "qa", "gold": {"answer_text": "x"}, "gold_citations": ["n:d"]},
]


def test_risk_classification_accuracy_exact():
    results = {
        "i1": {"risk_category": "prohibited"},   # correct
        "i2": {"risk_category": "minimal_or_none"},  # wrong
        "i3": {"risk_category": "minimal_or_none"},  # correct
        "i4": {"risk_category": "high_risk"},    # qa item: never scored
    }
    out = risk_classification_accuracy(results, GOLD_ITEMS)
    assert out["correct"] == 2
    assert out["total"] == 3
    assert out["accuracy"] == pytest.approx(2 / 3)
    assert out["mismatches"] == [
        {"id": "i2", "gold": "high_risk", "predicted": "minimal_or_none"}
    ]


def test_unanswered_classification_counts_as_wrong_not_skipped():
    out = risk_classification_accuracy({}, GOLD_ITEMS)
    assert out["total"] == 3
    assert out["correct"] == 0
    assert out["accuracy"] == 0.0


def test_accuracy_with_no_classification_items_is_zero_total():
    out = risk_classification_accuracy({}, [GOLD_ITEMS[3]])
    assert out == {"correct": 0, "total": 0, "accuracy": 0.0, "mismatches": []}


# Citation completeness -------------------------------------------------------


def test_citation_completeness_macro_and_micro():
    results = {
        "i1": {"citations": ["n:a", "n:z"]},        # 1/1
        "i2": {"citations": ["n:b"]},               # 1/2
        "i3": {"citations": ["n:whatever"]},        # gold empty: excluded
        "i4": {"citations": []},                    # 0/1
    }
    out = citation_completeness(results, GOLD_ITEMS)
    assert out["per_item"] == {"i1": 1.0, "i2": 0.5, "i4": 0.0}
    assert out["macro_completeness"] == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    assert out["micro"] == {
        "found": 2,
        "required": 4,
        "completeness": pytest.approx(0.5),
    }


def test_citation_completeness_no_required_citations():
    out = citation_completeness({}, [GOLD_ITEMS[2]])
    assert out["macro_completeness"] == 0.0
    assert out["micro"]["required"] == 0
    assert out["per_item"] == {}


# Hallucinated citation rate --------------------------------------------------


def test_hallucinated_citation_rate_exact():
    results = {
        "i1": {"citations": ["n:a", "n:fake1"]},
        "i2": {"citations": ["n:b", "n:b"]},  # duplicate within item counted once
        "i3": {"citations": ["n:fake2"]},
    }
    out = hallucinated_citation_rate(results, graph_node_ids={"n:a", "n:b", "n:c"})
    assert out["cited"] == 4
    assert out["hallucinated"] == 2
    assert out["rate"] == pytest.approx(0.5)
    assert sorted(out["hallucinated_ids"]) == ["n:fake1", "n:fake2"]


def test_hallucinated_citation_rate_no_citations():
    out = hallucinated_citation_rate({"i1": {"citations": []}}, {"n:a"})
    assert out == {"hallucinated": 0, "cited": 0, "rate": 0.0, "hallucinated_ids": []}


# Judge false-accept / false-reject rates -------------------------------------


def test_judge_error_rates_exact():
    gold = {"n1": "accept", "n2": "accept", "n3": "accept", "n4": "reject", "n5": "reject"}
    verdicts = {
        "n1": "accepted",            # true accept
        "n2": "rejected",            # FALSE REJECT
        "n3": "needs_human_review",  # abstention: neither FA nor FR
        "n4": "accepted",            # FALSE ACCEPT
        "n5": "rejected",            # true reject
        "n6": "accepted",            # no gold label: not scored
    }
    out = judge_error_rates(verdicts, gold)
    assert out["false_accept_rate"] == pytest.approx(1 / 2)
    assert out["false_reject_rate"] == pytest.approx(1 / 3)
    assert out["counts"] == {
        "false_accepts": 1,
        "false_rejects": 1,
        "gold_accept": 3,
        "gold_reject": 2,
        "abstained": 1,
        "scored": 5,
    }
    assert out["false_accept_ids"] == ["n4"]
    assert out["false_reject_ids"] == ["n2"]
    assert out["abstained_ids"] == ["n3"]


def test_judge_error_rates_empty_and_invalid_gold():
    out = judge_error_rates({}, {})
    assert out["false_accept_rate"] == 0.0
    assert out["false_reject_rate"] == 0.0
    assert out["counts"]["scored"] == 0
    with pytest.raises(ValueError):
        judge_error_rates({"n1": "accepted"}, {"n1": "maybe"})

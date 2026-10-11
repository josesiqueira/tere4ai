"""E6's declared analysis, its pure functions (spec G D-G84, B150).

Covers DEC-11. Every expected value is computed by hand in the comment
beside it; the bootstrap is checked by its properties and its seed.
"""

from __future__ import annotations

import pytest

from tere4ai.eval.ablation_analysis import (
    AnalysisError,
    case_outcome,
    majority,
    mcnemar_exact_p,
    outcome_table,
    paired_contrast,
    percentile_interval,
    seeded_rng,
)

ART = "eu-ai-act:article-"


def _cls(i, label):
    return {"id": i, "kind": "classification", "gold": {"risk_category": label}, "gold_citations": []}


def _qa(i, key):
    return {"id": i, "kind": "qa", "gold": {"answer_text": "a"}, "gold_citations": list(key)}


def _ret(i, key):
    return {"id": i, "kind": "retrieval", "gold": {"node_id": key[0]}, "gold_citations": list(key)}


def _ans(cites=(), level=None):
    return {"answer_text": "x", "citations": list(cites), "risk_category": level}


def test_a_classification_case_is_right_when_the_level_equals_the_label():
    item = _cls("gold:cls-1", "high_risk")
    assert case_outcome(item, _ans(level="high_risk")) is True
    assert case_outcome(item, _ans(level="undetermined")) is False  # an abstention on a labelled level
    assert case_outcome(item, _ans(level=None)) is False
    assert case_outcome(item, None) is False  # no answer
    assert case_outcome(item, {"error": "RuntimeError: x", "answer_text": "", "citations": []}) is False
    assert case_outcome(_cls("gold:cls-2", "undetermined"), _ans(level="undetermined")) is True


def test_a_question_case_whose_key_is_an_article_credits_a_node_inside_it():
    item = _qa("gold:qa-1", [ART + "9"])
    assert case_outcome(item, _ans([ART + "9"])) is True
    assert case_outcome(item, _ans([ART + "9:paragraph-1"])) is True
    assert case_outcome(item, _ans([ART + "9:paragraph-1:point-a"])) is True
    assert case_outcome(item, _ans([ART + "90:paragraph-1"])) is False  # article-9 never credits article-90
    assert case_outcome(_qa("gold:qa-2", [ART + "1"]), _ans([ART + "10:paragraph-1"])) is False
    assert case_outcome(item, _ans([])) is False


def test_a_question_case_whose_key_is_not_an_article_is_matched_exactly():
    item = _qa("gold:qa-3", [ART + "9:paragraph-1"])
    assert case_outcome(item, _ans([ART + "9:paragraph-1"])) is True
    assert case_outcome(item, _ans([ART + "9:paragraph-1:point-a"])) is False
    assert case_outcome(item, _ans([ART + "9"])) is False


def test_a_retrieval_case_is_right_only_on_its_exact_key_node():
    item = _ret("gold:ret-1", ["eu-ai-act:annex-iii:point-5:a"])
    assert case_outcome(item, _ans(["eu-ai-act:annex-iii:point-5:a"])) is True
    assert case_outcome(item, _ans(["eu-ai-act:annex-iii:point-5"])) is False
    assert case_outcome(item, _ans(["eu-ai-act:annex-iii:point-5:a:i"])) is False


def test_a_key_of_several_nodes_is_met_when_one_of_them_is_cited():
    item = _qa("bench:qa:1", [ART + "10", ART + "13"])
    assert case_outcome(item, _ans([ART + "13:paragraph-2"])) is True
    assert case_outcome(item, _ans([ART + "14"])) is False


def test_a_case_without_a_key_or_a_label_refuses():
    with pytest.raises(AnalysisError, match="gold:qa-9"):
        case_outcome(_qa("gold:qa-9", []), _ans([ART + "9"]))
    with pytest.raises(AnalysisError, match="gold:cls-9"):
        case_outcome({"id": "gold:cls-9", "kind": "classification", "gold": {}, "gold_citations": []},
                     _ans(level="high_risk"))


def test_the_majority_of_an_odd_number_of_outcomes():
    assert majority([True]) is True
    assert majority([True, False, True]) is True
    assert majority([False, False, True]) is False
    with pytest.raises(AnalysisError, match="even"):
        majority([True, False])


def test_mcnemar_exact_two_sided_matches_the_hand_computed_values():
    # D-G84 (3): counts 8 and 2: 2 * (C(10,0) + C(10,1) + C(10,2)) / 2^10 = 2 * 56 / 1024
    assert mcnemar_exact_p(8, 2) == 0.109375
    assert mcnemar_exact_p(2, 8) == 0.109375
    assert mcnemar_exact_p(3, 0) == 0.25  # 2 * 1 / 8
    assert mcnemar_exact_p(10, 0) == 2 / 1024
    assert mcnemar_exact_p(5, 5) == 1.0  # a doubled tail above 1 is 1
    assert mcnemar_exact_p(0, 0) == 1.0  # no discordant case


def test_the_percentile_interval_reads_the_projects_positions():
    # 1000 values: positions floor(999 * 0.025) = 24 and ceil(999 * 0.975) = 975 of the
    # sorted values, the dashboard's percentileInterval (spec F, t2.interval)
    assert percentile_interval([float(v) for v in range(1000)][::-1], 0.95) == (24.0, 975.0)
    assert percentile_interval([0.5], 0.95) == (0.5, 0.5)


def _pairs(both, cond_only, against_only, neither):
    return ([(True, True)] * both + [(True, False)] * cond_only
            + [(False, True)] * against_only + [(False, False)] * neither)


def test_a_paired_contrast_reads_one_outcome_per_case():
    result = paired_contrast(_pairs(3, 8, 2, 7), level=0.95, draws=1000, seed=20261011, label="c",
                             threshold=0.05 / 3)
    assert result["cases"] == 20
    assert (result["condition_right"], result["against_right"]) == (11, 5)
    assert (result["condition_only_right"], result["against_only_right"]) == (8, 2)
    assert result["difference"] == pytest.approx(6 / 20)
    assert result["mcnemar_exact_p"] == 0.109375
    assert result["no_difference_rejected"] is False  # 0.109375 is not below 0.05 / 3
    low, high = result["interval"]
    assert -1 <= low <= 0.3 <= high <= 1
    assert (result["draws"], result["seed"], result["level"]) == (1000, 20261011, 0.95)


def test_the_bootstrap_is_fixed_by_its_seed_and_its_label():
    kw = {"level": 0.95, "draws": 1000, "threshold": 0.05 / 3}
    first = paired_contrast(_pairs(3, 8, 2, 7), seed=1, label="x", **kw)["interval"]
    assert first == paired_contrast(_pairs(3, 8, 2, 7), seed=1, label="x", **kw)["interval"]
    a, b = seeded_rng(1, "x"), seeded_rng(1, "y")
    assert [a.randrange(1000) for _ in range(10)] != [b.randrange(1000) for _ in range(10)]


def test_a_contrast_with_no_discordant_case_or_only_one_side():
    none = paired_contrast(_pairs(4, 0, 0, 6), level=0.95, draws=200, seed=7, label="z", threshold=0.05 / 3)
    assert none["difference"] == 0.0 and none["interval"] == [0.0, 0.0] and none["mcnemar_exact_p"] == 1.0
    one_side = paired_contrast(_pairs(0, 5, 0, 0), level=0.95, draws=200, seed=7, label="z", threshold=0.05 / 3)
    assert one_side["difference"] == 1.0 and one_side["interval"] == [1.0, 1.0]


def test_a_strong_contrast_is_rejected_at_the_corrected_threshold():
    result = paired_contrast(_pairs(0, 10, 0, 0), level=0.95, draws=100, seed=7, label="z", threshold=0.05 / 3)
    assert result["mcnemar_exact_p"] == 2 / 1024 and result["no_difference_rejected"] is True


def test_a_contrast_with_no_case_is_not_computed():
    assert paired_contrast([], level=0.95, draws=100, seed=7, label="z", threshold=0.05 / 3) == {
        "cases": 0, "not_computed": "no case of the contrast's kinds in the answer key"}


def test_outcome_table_gives_a_run_once_case_its_one_call():
    once = {"conditions": ["graph_no_judge"], "case_kind": "classification"}
    cls, qa = _cls("gold:cls-1", "high_risk"), _qa("gold:qa-1", [ART + "9"])
    runs = [
        {"graph_no_judge": {"gold:cls-1": _ans(level="high_risk"), "gold:qa-1": _ans([ART + "9"])}},
        {"graph_no_judge": {"gold:qa-1": _ans([])}},
        {"graph_no_judge": {"gold:qa-1": _ans([ART + "9:paragraph-2"])}},
    ]
    assert outcome_table([cls, qa], runs, "graph_no_judge", once) == {
        "gold:cls-1": [True], "gold:qa-1": [True, False, True]}


def test_outcome_table_refuses_a_missing_result():
    once = {"conditions": [], "case_kind": "classification"}
    runs = [{"plain_llm": {"gold:cls-1": _ans(level="high_risk")}}, {"plain_llm": {}}]
    with pytest.raises(AnalysisError, match="run 2 .*plain_llm.*gold:cls-1"):
        outcome_table([_cls("gold:cls-1", "high_risk")], runs, "plain_llm", once)

"""E6's declared analysis, its pure functions (spec G D-G84, B150).

Covers DEC-11. Every expected value is computed by hand in the comment
beside it; the bootstrap is checked by its properties and its seed.
"""

from __future__ import annotations

import math
import statistics

import pytest

from tere4ai.eval.ablation_analysis import (
    AnalysisError,
    case_outcome,
    gate_answers,
    gate_share_intervals,
    gate_shares,
    labelled_interval,
    majority,
    mcnemar_exact_p,
    outcome_table,
    paired_contrast,
    per_call_summary,
    percentile_interval,
    pilot_count,
    required_repetitions,
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


def test_an_interval_is_labelled_by_the_resamples_left_out():
    values = [i / 100 for i in range(100)]
    kw = dict(draws=1000, level=0.95, conditional_up_to=25, what="wrong answer")
    clean = labelled_interval(values, 0, **kw)
    assert clean["label"] is None and clean["interval"] == list(percentile_interval(values, 0.95))
    edge = labelled_interval(values, 25, **kw)
    assert edge["interval"] == clean["interval"] and edge["left_out"] == 25
    assert edge["label"] == ("conditional: 25 of 1000 resamples held no wrong answer and were left out "
                             "(B150 Q11)")
    over = labelled_interval(values, 26, **kw)
    assert over["interval"] is None
    assert over["label"] == "none given: 26 of 1000 resamples held no wrong answer, more than 25 (B150 Q11)"
    assert labelled_interval([], 1000, **kw)["interval"] is None


def test_the_left_out_rule_names_the_question_that_applies_it():
    # B161 Q1 applies the same rule to the hand-made test set's kappa
    out = labelled_interval([0.1, 0.2], 3, draws=1000, level=0.95, conditional_up_to=25, what="kappa",
                            question="B161 Q1")
    assert out["label"] == "conditional: 3 of 1000 resamples held no kappa and were left out (B161 Q1)"


def test_a_paired_contrast_reads_one_outcome_per_case():
    result = paired_contrast(_pairs(3, 8, 2, 7), level=0.95, draws=1000, seed=20261011, label="c",
                             threshold=0.05 / 3)
    assert result["cases"] == 20
    assert (result["condition_right"], result["against_right"]) == (11, 5)
    assert (result["condition_only_right"], result["against_only_right"]) == (8, 2)
    assert result["difference"] == pytest.approx(6 / 20)
    assert result["mcnemar_exact_p"] == 0.109375
    assert result["no_difference_rejected"] is False  # 0.109375 is not below 0.05 / 3
    # pinned to the seeded draw (checked by hand by the Task 5 review): 0.3 sits inside
    assert result["interval"] == [0.0, 0.55]
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


def test_per_call_accuracy_pools_every_call_and_reports_the_variation():
    table = {"a": [True, True, False], "b": [False, False, False], "c": [True, False, False]}
    s = per_call_summary(table, 3)
    # repetition 1: a and c right (2 of 3); 2: a (1 of 3); 3: none; 3 right of 9 calls
    assert (s["cases"], s["repetitions"], s["calls"], s["right"]) == (3, 3, 9, 3)
    assert s["share"] == pytest.approx(3 / 9)
    assert s["by_repetition"] == pytest.approx([2 / 3, 1 / 3, 0.0])
    # sample standard deviation (n - 1) of 2/3, 1/3, 0: sqrt(((1/3)^2 + 0 + (1/3)^2) / 2) = 1/3
    assert s["standard_deviation"] == pytest.approx(1 / 3)


def test_one_repetition_has_no_variation_and_no_case_has_no_share():
    assert per_call_summary({"a": [True]}, 1)["standard_deviation"] is None
    assert per_call_summary({}, 3)["share"] is None


def test_a_run_once_case_counts_its_one_call_only():
    # Codex finding 1: one right classification run once and a question wrong three
    # times is 1 right of 4 calls, never 3 of 6; each repetition's accuracy reads the
    # case run in every repetition only (provisional, B150 Q13)
    s = per_call_summary({"cls": [True], "qa": [False, False, False]}, 3)
    assert (s["calls"], s["right"], s["share"]) == (4, 1, 0.25)
    assert (s["by_repetition"], s["standard_deviation"], s["cases_in_every_repetition"]) == ([0.0, 0.0, 0.0], 0.0, 1)


def test_the_four_gate_shares_on_hand_counted_answers():
    # (right, delivered): a right answer delivered twice and blocked once,
    # a wrong answer caught twice and let through once
    rows = [[(True, True), (True, True), (True, False)], [(False, False), (False, False), (False, True)]]
    s = gate_shares(rows)
    assert s["wrong_answers_caught"] == {"numerator": 2, "denominator": 3, "rate": 2 / 3}
    assert s["right_answers_blocked"] == {"numerator": 1, "denominator": 3, "rate": 1 / 3}
    assert s["accuracy_among_delivered"] == {"numerator": 2, "denominator": 3, "rate": 2 / 3}
    assert s["share_delivered"] == {"numerator": 3, "denominator": 6, "rate": 0.5}


def test_a_share_with_nothing_to_count_is_none_never_zero():
    assert gate_shares([[(True, True)]])["wrong_answers_caught"] == {"numerator": 0, "denominator": 0, "rate": None}
    assert gate_shares([])["share_delivered"]["rate"] is None


def test_gate_answers_leave_a_failed_call_out_and_list_it():
    item = _qa("gold:qa-1", [ART + "9"])
    runs = [
        {"graph_full": {"gold:qa-1": {"error": "RuntimeError: x", "answer_text": "", "citations": []}}},
        {"graph_full": {"gold:qa-1": dict(_ans([ART + "9"]), judge_verdict="accepted")}},
        {"graph_full": {"gold:qa-1": dict(_ans([]), judge_verdict="needs_human_review")}},
    ]
    answers, failed = gate_answers([item], runs, "graph_full")
    assert answers == {"gold:qa-1": [(True, True), (False, False)]}
    assert failed == [{"repetition": 1, "case": "gold:qa-1", "error": "RuntimeError: x"}]


def test_a_gated_answer_without_a_verdict_refuses():
    runs = [{"graph_full": {"gold:qa-1": _ans([ART + "9"])}}]
    with pytest.raises(AnalysisError, match="no runtime judge verdict"):
        gate_answers([_qa("gold:qa-1", [ART + "9"])], runs, "graph_full")


def test_gate_share_intervals_draw_each_case_with_all_its_repetitions():
    answers = {"a": [(True, True)] * 3, "b": [(False, False)] * 3,
               "c": [(True, False), (True, True), (True, True)]}
    out = gate_share_intervals(answers, level=0.95, draws=500, seed=3, label="g")
    low, high = out["share_delivered"]
    assert 0 <= low <= high <= 1
    # b is the only case with a wrong answer: a resample without it has none to catch
    assert out["wrong_answers_caught"].startswith("not computed: awaiting Jose's decision")
    assert "B150 Q11" in out["wrong_answers_caught"]
    assert out == gate_share_intervals(answers, level=0.95, draws=500, seed=3, label="g")
    every = {"a": [(False, True), (True, True)], "b": [(False, False), (True, True)]}
    low, high = gate_share_intervals(every, level=0.95, draws=500, seed=3, label="g")["wrong_answers_caught"]
    assert 0 <= low <= high <= 1
    assert gate_share_intervals({"a": [(True, True)]}, level=0.95, draws=10, seed=3,
                                label="g")["wrong_answers_caught"] is None  # nothing to count at all: n/a


def test_required_repetitions_is_the_smallest_odd_count_reaching_two_points():
    z, h = 1.96, 0.02
    assert required_repetitions(0.0, z=z, half_width=h) == 1
    assert required_repetitions(0.01, z=z, half_width=h) == 1  # 0.0196 <= 0.02
    assert required_repetitions(0.02, z=z, half_width=h) == 5  # 3 gives 0.0226, 5 gives 0.0175
    assert required_repetitions(0.03, z=z, half_width=h) == 9  # 7 gives 0.0222, 9 gives 0.0196
    assert required_repetitions(0.06 / 1.96, z=z, half_width=h) == 9  # exactly 0.02 at 9
    assert required_repetitions(0.05, z=z, half_width=h) == 25  # (1.96 * 0.05 / 0.02)^2 = 24.01


def test_the_pilot_count_takes_the_most_demanding_figure_and_the_cap():
    out = pilot_count({"accuracy:plain_llm": [1.0, 1.0, 1.0, 1.0, 0.975], "accuracy:vector_rag": [1.0] * 5},
                      z=1.96, half_width=0.02, cap=11)
    # standard deviation of 1, 1, 1, 1, 0.975 (n - 1) = 0.01118; (1.96 * 0.01118 / 0.02)^2 = 1.2, so 3
    assert (out["count"], out["cap_binds"], out["precision_reached"]) == (3, False, None)
    assert out["figures"]["accuracy:vector_rag"]["required"] == 1
    values = [0.9, 1.0, 0.9, 1.0, 0.9]
    capped = pilot_count({"accuracy:plain_llm": values}, z=1.96, half_width=0.02, cap=11)
    # standard deviation 0.05477; (1.96 * 0.05477 / 0.02)^2 = 28.8, so 29, above the cap
    assert (capped["count"], capped["cap_binds"]) == (11, True)
    assert capped["precision_reached"] == pytest.approx(1.96 * statistics.stdev(values) / math.sqrt(11))


def test_a_figure_without_a_value_in_a_repetition_leaves_the_count_not_computed():
    out = pilot_count({"wrong_answers_caught:graph_full": [0.5, None, 0.5, 0.5, 0.5]},
                      z=1.96, half_width=0.02, cap=11)
    assert out["count"] is None and "B150 Q11" in out["not_computed"]
    assert "wrong_answers_caught:graph_full" in out["not_computed"]


def test_a_figure_with_fewer_than_two_values_says_why_without_naming_a_question():
    # final review, Task 6 minor: no case run in every repetition gives an empty figure, which has no
    # standard deviation; that is a failure mechanic, not B150 Q11 (a repetition without a value)
    out = pilot_count({"accuracy:graph_full": [], "accuracy:plain_llm": [1.0, 1.0, 1.0, 1.0, 1.0]},
                      z=1.96, half_width=0.02, cap=11)
    assert out["count"] is None and out["figures"]["accuracy:graph_full"]["standard_deviation"] is None
    assert out["not_computed"] == ("not computed: a standard deviation needs a value in at least two repetitions, "
                                   "and accuracy:graph_full holds fewer than two (one repetition only, or no case "
                                   "of it run in every repetition)")
    both = pilot_count({"a": [0.5], "b": [0.5, None]}, z=1.96, half_width=0.02, cap=11)
    first, second = both["not_computed"].split("; ")
    assert "a holds fewer than two" in first and "B150 Q11" not in first
    assert "B150 Q11" in second and "(b)" in second

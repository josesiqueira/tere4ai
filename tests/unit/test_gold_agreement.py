"""The hand-made test set's agreement, by kind, as its protocol names it (B149).

Covers DEC-11. Every expected value is hand-computed from the mock items
below; no model; the bootstrap's only randomness is its recorded seed.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from tere4ai.eval.ablation_declaration import load_declaration
from tere4ai.eval.gold_agreement import (
    BOOTSTRAP,
    FEWER_THAN_TWO,
    KAPPA_NA,
    KAPPA_NA_IDS,
    NO_ARTICLE_LEVEL,
    NOT_ONE_ID,
    LabelError,
    agreement_report,
    article_level_of,
    article_of,
    interval_of,
    render_text,
)

A, B = "ann_a", "ann_b"
ART = "eu-ai-act:article-"


def _label(who, gold, cites=()):
    return {"annotator": who, "gold": gold, "gold_citations": list(cites), "note": ""}


def _item(item_id, kind, labels, **extra):
    item = {"id": item_id, "kind": kind, "gold": None, "gold_citations": [], "labels": labels,
            "adjudication": None, **extra}
    if kind == "classification":
        item["system_features"] = {"description": "mock", "flags": {}}
    else:
        item["question"] = "mock question"
    return item


def _cls(item_id, level_a, level_b, **extra):
    return _item(item_id, "classification",
                 [_label(A, {"risk_category": level_a}), _label(B, {"risk_category": level_b})], **extra)


def _ret(item_id, node_a, node_b, **extra):
    return _item(item_id, "retrieval",
                 [_label(A, {"node_id": node_a}), _label(B, {"node_id": node_b})], **extra)


def _qa(item_id, cites_a, cites_b):
    return _item(item_id, "qa", [_label(A, {"answer_text": "x"}, cites_a),
                                 _label(B, {"answer_text": "y"}, cites_b)])


ITEMS = [
    # classification: A = [high, high, minimal, unacceptable], B = [high, limited,
    # minimal, unacceptable]. p_o = 3/4. Marginal products: high 2*1, limited
    # 0*1, minimal 1*1, unacceptable 1*1 = 4 of 16, p_e = 1/4.
    # kappa = (3/4 - 1/4) / (3/4) = 2/3.
    _cls("gold:cls-01", "high_risk", "high_risk"),
    _cls("gold:cls-02", "high_risk", "limited_risk"),
    _cls("gold:cls-03", "minimal_risk", "minimal_risk"),
    _cls("gold:cls-04", "unacceptable_risk", "unacceptable_risk"),
    _item("gold:cls-05", "classification", [_label(A, {"risk_category": "high_risk"})]),  # B lacks
    _item("gold:cls-06", "classification", []),  # both lack
    # retrieval: one id each on ret-01 to ret-03, 2 of 3 identical; within the
    # Articles on ret-02 and ret-03, 2 of 2 in the same Article
    _ret("gold:ret-01", "eu-ai-act:annex-iii:point-4", "eu-ai-act:annex-iii:point-4"),
    _ret("gold:ret-02", ART + "5:paragraph-1:point-a", ART + "5:paragraph-1:point-b", contested=True),
    _ret("gold:ret-03", ART + "6:paragraph-2", ART + "6:paragraph-2"),
    _ret("gold:ret-04", ["eu-ai-act:annex-iii:point-5:a", "eu-ai-act:annex-iii:point-5:b"],
         "eu-ai-act:annex-iii:point-5:a"),  # a list-valued label, two ids
    # qa: one id each on qa-01 and qa-02, 1 of 2; qa-03 cites nothing on one side
    _qa("gold:qa-01", [ART + "9"], [ART + "9"]),
    _qa("gold:qa-02", [ART + "9"], [ART + "10"]),
    _qa("gold:qa-03", [], [ART + "13"]),
]


def test_classification_kappa_and_raw_agreement_by_hand():
    cls = agreement_report(ITEMS)["by_kind"]["classification"]
    assert cls["paired"] == 4
    assert cls["raw_agreement"] == {"agreed": 3, "compared": 4, "rate": 0.75}
    assert cls["cohen_kappa"] == pytest.approx(2 / 3)
    assert cls["kappa_note"] is None
    assert cls["confusion"]["high_risk"] == {
        "high_risk": 1, "limited_risk": 1, "minimal_risk": 0, "unacceptable_risk": 0}
    assert set(cls["intervals"]) == {"raw_agreement", "cohen_kappa"}


def test_every_case_one_labeller_lacks_is_listed_never_dropped():
    report = agreement_report(ITEMS)
    assert report["annotators"] == [A, B]
    assert report["items_total"] == 13
    assert report["missing"] == [
        {"id": "gold:cls-05", "kind": "classification", "lacking": [B]},
        {"id": "gold:cls-06", "kind": "classification", "lacking": [A, B]},
    ]
    paired = sum(block["paired"] for block in report["by_kind"].values())
    assert paired + len(report["missing"]) == report["items_total"]


def test_retrieval_exact_and_article_level_with_the_unsettled_cases_listed():
    ret = agreement_report(ITEMS)["by_kind"]["retrieval"]
    assert ret["paired"] == 4
    assert ret["exact_node_id_agreement"] == {"agreed": 2, "compared": 3, "rate": 2 / 3}
    assert ret["not_one_id"] == {"items": ["gold:ret-04"], "note": NOT_ONE_ID}
    # ret-01 (Annex III point 4 both), ret-02 (Article 5 both), ret-03 (Article 6 both): 3 of 3
    assert ret["article_level_agreement"] == {"agreed": 3, "compared": 3, "rate": 1.0}
    assert ret["no_article_level"] == {"items": [], "note": NO_ARTICLE_LEVEL}
    assert ret["contested"]["items"] == ["gold:ret-02"]


def test_an_annex_item_reads_its_top_level_point_at_article_level():
    # B149 Q2: Annex III point 5(a) against point 5(b) disagree by node id and agree at article level
    report = agreement_report([_ret("gold:ret-01", "eu-ai-act:annex-iii:point-5:a", "eu-ai-act:annex-iii:point-5:b"),
                               _ret("gold:ret-02", "eu-ai-act:annex-iii", "eu-ai-act:annex-iii:point-5")])
    ret = report["by_kind"]["retrieval"]
    assert ret["exact_node_id_agreement"] == {"agreed": 0, "compared": 2, "rate": 0.0}
    assert ret["article_level_agreement"] == {"agreed": 1, "compared": 1, "rate": 1.0}
    assert ret["no_article_level"] == {"items": ["gold:ret-02"], "note": NO_ARTICLE_LEVEL}


def test_article_level_of_reads_articles_and_annex_points_only():
    assert article_level_of(ART + "5:paragraph-1:point-a") == ART + "5"
    assert article_level_of("eu-ai-act:annex-iii:point-5:a") == "eu-ai-act:annex-iii:point-5"
    assert article_level_of("eu-ai-act:annex-iii:point-10:a") == "eu-ai-act:annex-iii:point-10"
    assert article_level_of("eu-ai-act:annex-iii:point-1") == "eu-ai-act:annex-iii:point-1"
    assert article_level_of("eu-ai-act:annex-i:section-a:point-1") == "eu-ai-act:annex-i:section-a:point-1"
    assert article_level_of("eu-ai-act:annex-iv:point-2:2.1") == "eu-ai-act:annex-iv:point-2"
    assert article_level_of("eu-ai-act:annex-viii:item-3") == "eu-ai-act:annex-viii:item-3"
    assert article_level_of("eu-ai-act:annex-iii") is None
    assert article_level_of("eu-ai-act:annex-i:section-a") is None
    assert article_level_of("eu-ai-act:recital-12") is None


def test_the_answered_questions_print_no_awaiting_and_no_provisional_line():
    text = render_text(agreement_report(ITEMS))
    assert "Back to the labeller" in text  # ret-04 and qa-03 listed as not compared (B149 Q1)
    assert "B149 Q5" in text and "provisional" not in text  # ret-02 contested
    # every question of B149 and B161 Q1 is answered: nothing waits on Jose
    assert "awaiting Jose's decision" not in text and "not computed" not in text


def test_qa_citation_agreement_by_exact_node_id():
    qa = agreement_report(ITEMS)["by_kind"]["qa"]
    assert qa["paired"] == 3
    assert qa["citation_agreement"] == {"agreed": 1, "compared": 2, "rate": 0.5}
    assert qa["not_one_id"]["items"] == ["gold:qa-03"]
    assert "not scored" in qa["answers"]


def test_one_shared_category_prints_n_a_never_one():
    report = agreement_report([_cls(f"gold:cls-{n}", "high_risk", "high_risk") for n in range(3)])
    cls = report["by_kind"]["classification"]
    assert cls["raw_agreement"]["rate"] == 1.0
    assert cls["cohen_kappa"] is None and cls["kappa_note"] == KAPPA_NA
    assert "cohen kappa: n/a: both labellers used one category" in render_text(report)


def test_a_kind_with_no_compared_case_reads_n_a_not_zero():
    report = agreement_report([_cls("gold:cls-01", "high_risk", "limited_risk")])
    assert report["by_kind"]["retrieval"]["exact_node_id_agreement"] == {
        "agreed": 0, "compared": 0, "rate": None}
    assert report["by_kind"]["qa"]["citation_agreement"]["rate"] is None
    assert "exact node-id agreement: n/a (no case to compare)" in render_text(report)


def test_article_of_reads_the_article_and_nothing_outside():
    assert article_of(ART + "5:paragraph-1:point-a") == ART + "5"
    assert article_of(ART + "6") == ART + "6"
    assert article_of("eu-ai-act:annex-iii:point-4") is None


def test_the_text_report_prints_each_figure_with_its_interval():
    text = render_text(agreement_report(ITEMS))
    assert "cases one labeller lacks: 2" in text
    assert "classification: 4 paired" in text and "retrieval: 4 paired" in text
    assert "qa: 3 paired" in text
    assert "gold:cls-05 (classification): lacks ann_b" in text
    assert "raw agreement: 3 of 4 (0.750)" in text
    assert "exact node-id agreement: 2 of 3 (0.667)" in text
    assert "article-level agreement: 3 of 3 (1.000)" in text
    assert "citation agreement: 1 of 2 (0.500)" in text
    # classification 0.667, retrieval 4/7, qa 0
    assert "cohen kappa: 0.667" in text and "cohen kappa: 0.571" in text and "cohen kappa: 0.000" in text
    # classification 2, retrieval 3, qa 2: one interval line under every figure
    assert text.count("95% interval:") == 7
    assert "bootstrap: 1000 draws over the compared cases, seed 20261011, 95% percentile interval" in text
    # ITEMS' agreeing cases make some kappa resamples hold one shared label on both sides (about 3 in 256 for
    # classification, 2 in 27 for retrieval, 1 in 4 for qa): conditional for the first, none given for the others
    kappa_lines = [line for line in text.splitlines()
                   if "resamples held no kappa" in line and line.startswith("  95% interval:")]
    assert len(kappa_lines) == 3
    assert re.fullmatch(r"  95% interval: \[-?\d\.\d{3}, \d\.\d{3}\]; conditional: \d+ of 1000 resamples held no "
                        r"kappa and were left out \(B161 Q1\)", kappa_lines[0])
    for line in kappa_lines[1:]:
        assert re.fullmatch(r"  95% interval: none given: \d+ of 1000 resamples held no kappa, more than 25 "
                            r"\(B161 Q1\)", line)
    assert "B149 Q3" not in text and "B149 Q4" not in text


def test_retrieval_and_qa_kappa_over_node_ids_by_hand():
    report = agreement_report(ITEMS)
    # retrieval one-id pairs: (P4, P4), (5:1:a, 5:1:b), (6:2, 6:2); p_o = 2/3; marginal products
    # P4 1*1 + 6:2 1*1 = 2 of 9, p_e = 2/9; kappa = (2/3 - 2/9) / (7/9) = 4/7
    assert report["by_kind"]["retrieval"]["cohen_kappa"] == pytest.approx(4 / 7)
    assert report["by_kind"]["retrieval"]["kappa_note"] is None
    # qa one-id pairs: (9, 9), (9, 10); p_o = 1/2; A 9 twice, B 9 once: 2 of 4, p_e = 1/2; kappa = 0
    assert report["by_kind"]["qa"]["cohen_kappa"] == pytest.approx(0.0)
    assert report["bootstrap"] == {"method": "percentile_bootstrap_over_cases", "level": 0.95, "draws": 1000,
                                   "seed": 20261011, "conditional_up_to": 25}
    assert report["bootstrap"] == BOOTSTRAP


def test_the_kappa_rule_holds_the_e6_declarations_limit_and_draws():
    # Task 3 review, Minor 2: B161 Q1 applies E6's rule ("Same rule as E6 (Recommended)"), so the hand-made
    # test set's limit and draws are the declaration's; a change to one without the other fails here
    rule = load_declaration()["empty_resamples"]
    assert BOOTSTRAP["conditional_up_to"] == rule["conditional_up_to"] == 25
    assert BOOTSTRAP["draws"] == rule["of_draws"] == 1000


def test_one_shared_node_id_prints_n_a_and_no_interval():
    report = agreement_report([_ret(f"gold:ret-{n}", ART + "9", ART + "9") for n in range(3)])
    ret = report["by_kind"]["retrieval"]
    assert ret["cohen_kappa"] is None and ret["kappa_note"] == KAPPA_NA_IDS
    assert ret["intervals"]["cohen_kappa"] is None
    assert ret["intervals"]["exact_node_id_agreement"] == [1.0, 1.0]
    assert "cohen kappa: n/a: both labellers gave one and the same node id" in render_text(report)


def test_an_interval_needs_two_cases():
    report = agreement_report([_cls("gold:cls-01", "high_risk", "limited_risk")])
    assert report["by_kind"]["classification"]["intervals"]["raw_agreement"] == FEWER_THAN_TWO
    assert report["by_kind"]["classification"]["intervals"]["cohen_kappa"] == FEWER_THAN_TWO
    assert FEWER_THAN_TWO == "n/a: no interval over fewer than two cases (spec G D-G17)"
    # a kind with no compared case: no interval on the share, none on the kappa it lacks
    assert report["by_kind"]["qa"]["intervals"] == {"citation_agreement": FEWER_THAN_TWO, "cohen_kappa": None}


def test_a_kappa_interval_is_read_when_every_resample_has_a_kappa():
    # no pair agrees, so no resample has both labellers on one and the same category: kappa is always defined
    items = [_cls("gold:cls-01", "high_risk", "limited_risk"), _cls("gold:cls-02", "limited_risk", "high_risk"),
             _cls("gold:cls-03", "minimal_risk", "unacceptable_risk")]
    first = agreement_report(items)["by_kind"]["classification"]["intervals"]
    low, high = first["cohen_kappa"]
    assert -1.0 <= low <= high <= 1.0
    assert first["raw_agreement"] == [0.0, 0.0]
    assert first == agreement_report(items)["by_kind"]["classification"]["intervals"]  # the seed fixes it


def test_a_kappa_interval_with_a_few_resamples_without_a_kappa_is_labelled_conditional():
    # B161 Q1 (Jose, 2026-10-11, "Same rule as E6 (Recommended)"): ITEMS' four classification pairs give no
    # kappa only when a resample draws one agreeing case four times, 3 in 256, about 12 of 1000
    interval = agreement_report(ITEMS)["by_kind"]["classification"]["intervals"]["cohen_kappa"]
    assert 1 <= interval["left_out"] <= 25 and interval["draws"] == 1000
    low, high = interval["interval"]
    assert -1.0 <= low <= high <= 1.0
    assert interval["label"] == (f"conditional: {interval['left_out']} of 1000 resamples held no kappa and were "
                                 "left out (B161 Q1)")


def test_a_kappa_interval_with_more_than_25_resamples_without_a_kappa_is_not_given():
    # two agreeing cases on two categories: a resample drawing one case twice, about 500 of 1000, has no kappa
    items = [_cls("gold:cls-01", "high_risk", "high_risk"), _cls("gold:cls-02", "limited_risk", "limited_risk")]
    intervals = agreement_report(items)["by_kind"]["classification"]["intervals"]
    assert intervals["raw_agreement"] == [1.0, 1.0]
    kappa = intervals["cohen_kappa"]
    assert kappa["interval"] is None and kappa["left_out"] > 25
    assert kappa["label"] == f"none given: {kappa['left_out']} of 1000 resamples held no kappa, more than 25 (B161 Q1)"


def test_interval_of_reads_the_percentile_positions_over_its_own_draws():
    pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("b", "a")]
    share = lambda xs, ys: sum(1 for x, y in zip(xs, ys) if x == y) / len(xs)  # noqa: E731
    low, high = interval_of(pairs, share, "mock")
    assert 0.0 <= low <= 0.5 <= high <= 1.0
    assert interval_of(pairs, share, "mock") == [low, high]  # the seed and the label fix it


@pytest.mark.parametrize("items, message", [
    ([], "no case carries a label"),
    ([_cls("gold:cls-01", "high_risk", "high_risk"),
      _item("gold:cls-02", "classification", [_label("ann_c", {"risk_category": "high_risk"})])],
     "name 3"),
    ([_cls("gold:cls-01", "high_risk", "prohibited")], "not one of the five risk categories"),
    ([_item("gold:cls-01", "classification", [_label(A, {"risk_category": "high_risk"}),
                                              _label(A, {"risk_category": "high_risk"})]),
      _cls("gold:cls-02", "high_risk", "high_risk")], "labelled it twice"),
    ([_ret("gold:ret-01", 7, "eu-ai-act:annex-iii:point-4")], "not node ids"),
    # a label is checked as it is read, on a case the other labeller lacks too
    ([_cls("gold:cls-01", "high_risk", "high_risk"),
      _item("gold:cls-02", "classification", [_label(A, {"risk_category": "prohibited"})])],
     "gold:cls-02: ann_a's level 'prohibited' is not one of the five risk categories"),
    ([_cls("gold:cls-01", "high_risk", "high_risk"),
      _item("gold:ret-01", "retrieval", [_label(B, {"node_id": 7})])],
     "gold:ret-01: ann_b's retrieval label gives 7, not node ids"),
    # a retrieval label whose gold_citations name other ids than its node_id
    ([_item("gold:ret-01", "retrieval", [_label(A, {"node_id": ART + "5"}, [ART + "6"]),
                                         _label(B, {"node_id": ART + "5"}, [ART + "5"])])],
     "gold:ret-01: ann_a's retrieval label gives node_id"),
    ([_cls("gold:cls-01", "high_risk", "high_risk"),
      _item("gold:cls-02", "classification", ["x"])],
     "gold:cls-02: a label is not an object"),
])
def test_a_label_outside_the_protocol_is_refused(items, message):
    with pytest.raises(LabelError, match=message):
        agreement_report(items)


ROOT = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location(
        "draft_gold_candidates", ROOT / "scripts" / "draft_gold_candidates.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_agreement_command_reads_the_item_file_and_writes_the_report(tmp_path, capsys):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"items": ITEMS}), encoding="utf-8")
    out = tmp_path / "agreement.json"
    assert _script().main(["agreement", str(path), "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "cohen kappa: 0.667" in text
    assert "gold:cls-06 (classification): lacks ann_a, ann_b" in text
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["by_kind"]["retrieval"]["exact_node_id_agreement"]["agreed"] == 2


def test_the_agreement_command_refuses_a_file_outside_the_protocol(tmp_path, capsys):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"items": [_cls("gold:cls-01", "high_risk", "prohibited")]}),
                    encoding="utf-8")
    assert _script().main(["agreement", str(path)]) == 1
    assert "refusing: gold:cls-01" in capsys.readouterr().err


def test_the_agreement_command_names_the_case_of_a_label_that_is_not_an_object(tmp_path, capsys):
    path = tmp_path / "items.json"
    path.write_text(json.dumps({"items": [_cls("gold:cls-01", "high_risk", "high_risk"),
                                          _item("gold:cls-02", "classification", ["x"])]}),
                    encoding="utf-8")
    assert _script().main(["agreement", str(path)]) == 1
    assert "refusing: gold:cls-02: a label is not an object" in capsys.readouterr().err


def test_the_agreement_command_refuses_the_old_flat_label_map(tmp_path, capsys):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"i1": "high_risk"}), encoding="utf-8")
    assert _script().main(["agreement", str(path)]) == 1
    assert "refusing:" in capsys.readouterr().err

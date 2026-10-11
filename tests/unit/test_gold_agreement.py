"""The hand-made test set's agreement, by kind, as its protocol names it (B149).

Covers DEC-11. Every expected value is hand-computed from the mock items
below; no model, no randomness.
"""

from __future__ import annotations

import pytest

from tere4ai.eval.gold_agreement import (
    CHANCE_CORRECTED,
    INTERVAL,
    KAPPA_NA,
    NOT_ONE_ID,
    OUTSIDE_ARTICLES,
    LabelError,
    agreement_report,
    article_of,
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
    assert cls["compared"] == 4
    assert cls["raw_agreement"] == {"agreed": 3, "compared": 4, "rate": 0.75}
    assert cls["cohen_kappa"] == pytest.approx(2 / 3)
    assert cls["kappa_note"] is None
    assert cls["confusion"]["high_risk"] == {
        "high_risk": 1, "limited_risk": 1, "minimal_risk": 0, "unacceptable_risk": 0}
    assert cls["interval"] == INTERVAL


def test_every_case_one_labeller_lacks_is_listed_never_dropped():
    report = agreement_report(ITEMS)
    assert report["annotators"] == [A, B]
    assert report["items_total"] == 13
    assert report["missing"] == [
        {"id": "gold:cls-05", "kind": "classification", "lacking": [B]},
        {"id": "gold:cls-06", "kind": "classification", "lacking": [A, B]},
    ]
    compared = sum(block["compared"] for block in report["by_kind"].values())
    assert compared + len(report["missing"]) == report["items_total"]


def test_retrieval_exact_and_article_level_with_the_unsettled_cases_listed():
    ret = agreement_report(ITEMS)["by_kind"]["retrieval"]
    assert ret["compared"] == 4
    assert ret["exact_node_id_agreement"] == {"agreed": 2, "compared": 3, "rate": 2 / 3}
    assert ret["not_one_id"] == {"items": ["gold:ret-04"], "note": NOT_ONE_ID}
    assert ret["article_level_agreement"] == {"agreed": 2, "compared": 2, "rate": 1.0}
    assert ret["outside_the_articles"] == {"items": ["gold:ret-01"], "note": OUTSIDE_ARTICLES}
    assert ret["chance_corrected"] == CHANCE_CORRECTED
    assert ret["contested"]["items"] == ["gold:ret-02"]


def test_qa_citation_agreement_by_exact_node_id():
    qa = agreement_report(ITEMS)["by_kind"]["qa"]
    assert qa["compared"] == 3
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


def test_the_text_report_prints_shares_as_n_of_m_and_names_every_open_question():
    text = render_text(agreement_report(ITEMS))
    assert "cases one labeller lacks: 2" in text
    assert "gold:cls-05 (classification): lacks ann_b" in text
    assert "raw agreement: 3 of 4 (0.750)" in text
    assert "cohen kappa: 0.667" in text
    assert "exact node-id agreement: 2 of 3 (0.667)" in text
    assert "article-level agreement: 2 of 2 (1.000)" in text
    assert "citation agreement: 1 of 2 (0.500)" in text
    for question in ("Q1", "Q2", "Q3", "Q4", "Q5"):
        assert f"B149 {question}" in text


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
])
def test_a_label_outside_the_protocol_is_refused(items, message):
    with pytest.raises(LabelError, match=message):
        agreement_report(items)

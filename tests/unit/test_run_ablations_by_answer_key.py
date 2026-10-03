"""run_ablations reports every measure for each answer key apart (B126, ruling R3).

The hand-made legal test set (items "gold:") and the published benchmark
(items "bench:") each get a block under by_answer_key; the pooled keys the
July readers use stay as they were.
"""

from __future__ import annotations

import json

from tests.unit.test_run_ablations_record import _argv, _load, runner  # noqa: F401

NODES = ["eu-ai-act:article-6", "eu-ai-act:article-9", "eu-ai-act:article-9:paragraph-2",
         "eu-ai-act:article-10", "eu-ai-act:article-13:paragraph-1"]


def _cls(item_id, risk, cites=()):
    return {"id": item_id, "kind": "classification", "gold": {"risk_category": risk},
            "gold_citations": list(cites)}


def _qa(item_id, cites):
    return {"id": item_id, "kind": "qa", "question": "q", "gold": {"answer_text": "a"},
            "gold_citations": list(cites)}


ITEMS = [
    _cls("gold:cls-1", "high_risk", ["eu-ai-act:article-6"]),
    _cls("gold:cls-2", "minimal_risk"),
    _qa("gold:qa-1", ["eu-ai-act:article-13:paragraph-1"]),
    _cls("bench:scenario:1", "high_risk", ["eu-ai-act:article-9"]),
    _cls("bench:scenario:2", "limited_risk"),
    _cls("bench:scenario:3", "high_risk"),
    _qa("bench:qa:1", ["eu-ai-act:article-10"]),
]

# (risk_category, citations) per item; bench:scenario:3 has no answer at all
ANSWERS = {
    "gold:cls-1": ("high_risk", ["eu-ai-act:article-6"]),
    "gold:cls-2": ("minimal_risk", []),
    "gold:qa-1": (None, ["eu-ai-act:article-13:paragraph-1"]),
    "bench:scenario:1": ("high_risk", ["eu-ai-act:article-9:paragraph-2", "fabricated:node"]),
    "bench:scenario:2": ("undetermined", []),
    "bench:qa:1": (None, ["eu-ai-act:article-10"]),
}


def test_each_answer_key_gets_its_own_measures_and_the_pooled_keys_are_unchanged(
    runner, tmp_path  # noqa: F811
):
    (tmp_path / "layer1.json").write_text(json.dumps(
        {"build": {"build_id": "build-b"}, "nodes": [{"id": n} for n in NODES], "edges": []}))
    runner.load_items = lambda b, f: ITEMS

    def fake_build(name, **kw):
        def strategy(item):
            kw["generator"].complete()
            if item["id"] not in ANSWERS:
                raise RuntimeError("no answer")  # recorded as the item's error, no risk_category
            risk, cites = ANSWERS[item["id"]]
            return {"answer_text": "x", "citations": cites, "risk_category": risk}

        strategy.models = {"generator": "g"}
        return strategy

    runner.strategies.build_strategy = fake_build
    assert runner.main(_argv(tmp_path)) == 0
    s = json.loads((tmp_path / "results" / "ablation_summary.json").read_text())["strategies"]["plain_llm"]

    hand = s["by_answer_key"]["hand_made"]
    assert hand["classification"] == {"correct": 2, "total": 2, "accuracy": 1.0, "abstained": 0}
    assert hand["citation_completeness"]["micro"] == {"found": 2, "required": 2, "completeness": 1.0}
    assert hand["hallucinated_citation_rate"]["rate"] == 0.0
    assert hand["hallucinated_citation_rate"]["cited"] == 2
    assert hand["citations_emitted"] == 2 and "hallucination_note" not in hand
    assert "citation_completeness_article_level" not in hand

    bench = s["by_answer_key"]["benchmark"]
    # the unanswered case counts as wrong and as abstained, beside "undetermined"
    assert bench["classification"] == {"correct": 1, "total": 3, "accuracy": 1 / 3, "abstained": 2}
    assert bench["citation_completeness"]["micro"] == {"found": 1, "required": 2, "completeness": 0.5}
    assert bench["hallucinated_citation_rate"]["hallucinated_ids"] == ["fabricated:node"]
    assert bench["hallucinated_citation_rate"]["rate"] == 1 / 3
    assert bench["citations_emitted"] == 3
    assert bench["citation_completeness_article_level"]["found"] == 2
    assert bench["citation_completeness_article_level"]["required"] == 2
    assert bench["citation_completeness_article_level"]["completeness"] == 1.0
    assert set(s["by_answer_key"]) == {"hand_made", "benchmark"}

    # the pooled keys as before B126
    assert s["risk_accuracy_overall"]["correct"] == 3 and s["risk_accuracy_overall"]["total"] == 5
    assert s["gold_structured_classification"]["correct"] == 2
    assert s["gold_structured_classification"]["total"] == 2
    assert {k: s["benchmark_freetext_classification"][k] for k in ("correct", "total", "abstained")} == {
        "correct": 1, "total": 3, "abstained": 2}
    assert s["benchmark_citation_completeness_article_level"] == bench["citation_completeness_article_level"]
    assert s["citations_emitted_total"] == 5
    assert s["citation_completeness"]["micro"] == {"found": 3, "required": 4, "completeness": 0.75}
    assert s["hallucinated_citation_rate"]["rate"] == 1 / 5
    assert s["errors"] == 1


def test_an_empty_key_has_no_accuracy_and_zero_citations_carry_the_vacuous_note():
    mod = _load()
    blocks = mod.answer_key_blocks({"gold:cls-1": {"risk_category": "high_risk", "citations": []}},
                                   [_cls("gold:cls-1", "high_risk")], set())
    assert blocks["benchmark"]["classification"] == {"correct": 0, "total": 0, "accuracy": None,
                                                     "abstained": 0}
    assert blocks["benchmark"]["citation_completeness_article_level"]["completeness"] is None
    for key in ("hand_made", "benchmark"):
        assert blocks[key]["citations_emitted"] == 0
        assert "vacuous" in blocks[key]["hallucination_note"]

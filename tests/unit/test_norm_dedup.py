"""Norm near-duplicate detection tests (DEC-03 partial)."""

from __future__ import annotations

from tere4ai.extract_norms.dedup import find_near_duplicates, jaccard, summarize


def _norm(nid, action, obj, article="eu-ai-act:article-9", actor="provider",
          deontic="obligation", verdict="accepted"):
    return {
        "norm_id": nid,
        "action": action,
        "object": obj,
        "source_node_id": f"{article}:paragraph-1",
        "actor_explicit": actor,
        "deontic_type": deontic,
        "judge_verdict": verdict,
    }


class TestJaccard:
    def test_identical_sets(self):
        s = frozenset({"a", "b"})
        assert jaccard(s, s) == 1.0

    def test_disjoint_sets(self):
        assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_empty_vs_empty_is_identical(self):
        assert jaccard(frozenset(), frozenset()) == 1.0


class TestFindNearDuplicates:
    def test_identical_wording_flagged_near_duplicate(self):
        norms = [
            _norm("n1", "establish and maintain", "a risk management system"),
            _norm("n2", "establish and maintain", "a risk management system"),
        ]
        pairs = find_near_duplicates(norms)
        assert len(pairs) == 1
        assert pairs[0]["band"] == "near_duplicate"
        assert pairs[0]["verdicts"] == ["accepted"]

    def test_one_token_variation_lands_in_review_band(self):
        # 6 shared tokens of 8 total = 0.75: flagged, but for human review.
        norms = [
            _norm("n1", "establish and maintain", "a risk management system"),
            _norm("n2", "establish and maintain", "the risk management system"),
        ]
        pairs = find_near_duplicates(norms)
        assert len(pairs) == 1
        assert pairs[0]["band"] == "review"

    def test_different_actor_never_paired(self):
        norms = [
            _norm("n1", "establish", "a risk management system", actor="provider"),
            _norm("n2", "establish", "a risk management system", actor="deployer"),
        ]
        assert find_near_duplicates(norms) == []

    def test_different_deontic_never_paired(self):
        norms = [
            _norm("n1", "process", "biometric data", deontic="obligation"),
            _norm("n2", "process", "biometric data", deontic="prohibition"),
        ]
        assert find_near_duplicates(norms) == []

    def test_different_article_never_paired(self):
        norms = [
            _norm("n1", "keep", "logs of operation", article="eu-ai-act:article-12"),
            _norm("n2", "keep", "logs of operation", article="eu-ai-act:article-19"),
        ]
        assert find_near_duplicates(norms) == []

    def test_unrelated_norms_not_flagged(self):
        norms = [
            _norm("n1", "establish", "a risk management system"),
            _norm("n2", "draw up", "technical documentation before placing on market"),
        ]
        assert find_near_duplicates(norms) == []

    def test_deterministic_ordering(self):
        norms = [
            _norm("n1", "establish and maintain", "risk management system"),
            _norm("n2", "establish and maintain", "the risk management system"),
            _norm("n3", "establish and maintain", "a risk management system process"),
        ]
        a = find_near_duplicates(norms)
        b = find_near_duplicates(list(reversed(norms)))
        assert [(p["norm_a"], p["norm_b"]) for p in a] == [
            (p["norm_a"], p["norm_b"]) for p in b
        ]


class TestSummary:
    def test_counts(self):
        norms = [
            _norm("n1", "establish and maintain", "a risk management system"),
            _norm("n2", "establish and maintain", "a risk management system"),
        ]
        pairs = find_near_duplicates(norms)
        s = summarize(pairs, total_norms=2)
        assert s["total_norms"] == 2
        assert s["pairs_flagged"] == 1
        assert s["near_duplicate_pairs"] == 1
        assert s["pairs_both_accepted"] == 1

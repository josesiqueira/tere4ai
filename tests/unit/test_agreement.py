"""Unit tests for tere4ai.eval.agreement (pure functions, hand-computed).

Covers DEC-11 (evaluation support: inter-annotator agreement statistics).
Every expected value below is hand-computed from the synthetic labels in
the comments; no model, no I/O, no randomness.
"""

import pytest

from tere4ai.eval.agreement import cohen_kappa, confusion, raw_agreement

# Worked 2x2 example, verified by hand:
#   both "accept": 20 items; both "reject": 15 items;
#   A "accept" / B "reject": 5 items; A "reject" / B "accept": 10 items.
#   n = 50.
#   p_o = (20 + 15) / 50 = 0.70
#   marginals: A accept = 25/50 = 0.5, B accept = 30/50 = 0.6
#   p_e = 0.5 * 0.6 + 0.5 * 0.4 = 0.30 + 0.20 = 0.50
#   kappa = (0.70 - 0.50) / (1 - 0.50) = 0.20 / 0.50 = 0.40
TWO_BY_TWO_A = ["accept"] * 20 + ["reject"] * 15 + ["accept"] * 5 + ["reject"] * 10
TWO_BY_TWO_B = ["accept"] * 20 + ["reject"] * 15 + ["reject"] * 5 + ["accept"] * 10


def test_worked_2x2_example_kappa_and_raw():
    assert raw_agreement(TWO_BY_TWO_A, TWO_BY_TWO_B) == pytest.approx(0.70)
    assert cohen_kappa(TWO_BY_TWO_A, TWO_BY_TWO_B) == pytest.approx(0.40)


def test_worked_2x2_confusion_counts():
    table = confusion(TWO_BY_TWO_A, TWO_BY_TWO_B)
    assert table == {
        "accept": {"accept": 20, "reject": 5},
        "reject": {"accept": 10, "reject": 15},
    }


def test_perfect_agreement_is_kappa_one():
    labels = ["a", "b", "c", "a", "b", "c"]
    assert raw_agreement(labels, list(labels)) == 1.0
    assert cohen_kappa(labels, list(labels)) == 1.0


def test_chance_level_agreement_is_kappa_zero():
    # A: [y, y, n, n], B: [y, n, y, n].
    # p_o = 2/4 = 0.5; marginals are 0.5/0.5 for both annotators, so
    # p_e = 0.5*0.5 + 0.5*0.5 = 0.5 and kappa = (0.5 - 0.5) / 0.5 = 0.0.
    assert cohen_kappa(["y", "y", "n", "n"], ["y", "n", "y", "n"]) == pytest.approx(0.0)


def test_three_categories_hand_computed():
    # A: [x, x, y, y, z, z], B: [x, y, y, y, z, x]. Agreements at positions
    # 1, 3, 4, 5: p_o = 4/6 = 2/3. Marginals: A gives 2/6 to each of x, y,
    # z; B gives x=2/6, y=3/6, z=1/6. p_e = (2*2 + 2*3 + 2*1) / 36 = 12/36
    # = 1/3. kappa = (2/3 - 1/3) / (1 - 1/3) = (1/3) / (2/3) = 0.5.
    a = ["x", "x", "y", "y", "z", "z"]
    b = ["x", "y", "y", "y", "z", "x"]
    assert raw_agreement(a, b) == pytest.approx(2 / 3)
    assert cohen_kappa(a, b) == pytest.approx(0.5)
    table = confusion(a, b)
    assert table["x"] == {"x": 1, "y": 1, "z": 0}
    assert table["y"] == {"x": 0, "y": 2, "z": 0}
    assert table["z"] == {"x": 1, "y": 0, "z": 1}
    # The table is square over every observed category.
    assert set(table) == {"x", "y", "z"}
    assert all(set(row) == {"x", "y", "z"} for row in table.values())


def test_disagreement_below_chance_is_negative_kappa():
    # Total disagreement on a balanced 2x2: A: [y, y, n, n], B: [n, n, y, y].
    # p_o = 0, p_e = 0.5, kappa = -1.0.
    assert cohen_kappa(["y", "y", "n", "n"], ["n", "n", "y", "y"]) == pytest.approx(-1.0)


def test_single_identical_category_degenerate_case():
    # p_e = 1.0 forces p_o = 1.0; kappa is defined as 1.0, not a division
    # by zero.
    assert cohen_kappa(["a", "a", "a"], ["a", "a", "a"]) == 1.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError, match="pair the same items"):
        raw_agreement(["a"], ["a", "b"])
    with pytest.raises(ValueError, match="pair the same items"):
        cohen_kappa(["a"], ["a", "b"])
    with pytest.raises(ValueError, match="pair the same items"):
        confusion(["a"], ["a", "b"])


def test_empty_input_raises_not_zero():
    with pytest.raises(ValueError, match="zero items"):
        raw_agreement([], [])
    with pytest.raises(ValueError, match="zero items"):
        cohen_kappa([], [])
    with pytest.raises(ValueError, match="zero items"):
        confusion([], [])

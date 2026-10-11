"""Inter-annotator agreement statistics: pure, hand-checkable functions.

@implements: DEC-11
@grounded_by: REF-16

Implements the agreement reporting of the annotation protocol
(eval/gold/ANNOTATION_PROTOCOL.md) and architecture.md Section 12: Cohen's
kappa over the closed classification categories and raw (observed)
agreement, plus a per-category confusion table for the disagreement
discussion. Kappa is None where it cannot be computed (both annotators used
one category), never 1.0. Every function is pure and deterministic: no
I/O, no model, no randomness. Inputs are two equal-length sequences of
labels where position i is the same item labelled by annotator A and
annotator B; labels are any hashable category values (two or more
categories are supported).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import TypeVar

L = TypeVar("L")


def _validated_pairs(labels_a: Sequence[L], labels_b: Sequence[L]) -> list[tuple[L, L]]:
    if len(labels_a) != len(labels_b):
        raise ValueError(
            f"label sequences must pair the same items: got {len(labels_a)} "
            f"labels from annotator A and {len(labels_b)} from annotator B"
        )
    if not labels_a:
        raise ValueError("agreement over zero items is undefined, not 0.0 or 1.0")
    return list(zip(labels_a, labels_b))


def raw_agreement(labels_a: Sequence[L], labels_b: Sequence[L]) -> float:
    """Observed proportion of items on which both annotators agree exactly.

    This is the p_o term of Cohen's kappa, reported on its own because the
    protocol reports raw agreement next to the chance-corrected statistic.
    Raises ValueError on empty or length-mismatched input.
    """
    pairs = _validated_pairs(labels_a, labels_b)
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(labels_a: Sequence[L], labels_b: Sequence[L]) -> float | None:
    """Cohen's kappa: (p_o - p_e) / (1 - p_e) over two or more categories.

    p_o is the observed agreement; p_e is the expected chance agreement from
    the two annotators' marginal label distributions (Cohen 1960, ADD-88,
    printed pages 39 and 40). Where p_e is exactly 1 both annotators used one
    and the same category for every item and the formula is 0 / 0: the value
    is None, printed n/a, never 1.0 (spec F conventions: "A value that cannot
    be computed prints "n/a", never a zero or a one"; the dashboard's
    cohenKappa does the same). p_e is tested in integers, so the test is
    exact for every n. Raises ValueError on empty or length-mismatched input.
    """
    pairs = _validated_pairs(labels_a, labels_b)
    n = len(pairs)
    agreed = sum(1 for a, b in pairs if a == b)
    marginal_a = Counter(a for a, _ in pairs)
    marginal_b = Counter(b for _, b in pairs)
    chance = sum(marginal_a[c] * marginal_b[c] for c in set(marginal_a) | set(marginal_b))
    if chance == n * n:
        return None
    p_o = agreed / n
    p_e = chance / (n * n)
    return (p_o - p_e) / (1.0 - p_e)


def confusion(labels_a: Sequence[L], labels_b: Sequence[L]) -> dict[L, dict[L, int]]:
    """Per-category confusion counts: result[label_a][label_b] = n items.

    Rows are annotator A's labels, columns annotator B's. Every category
    observed by either annotator appears as both a row and a column, filled
    with zeros where no item lands, so the table is square and directly
    printable. Raises ValueError on empty or length-mismatched input.
    """
    pairs = _validated_pairs(labels_a, labels_b)
    categories = sorted({a for a, _ in pairs} | {b for _, b in pairs}, key=repr)
    table: dict[L, dict[L, int]] = {row: {col: 0 for col in categories} for row in categories}
    for a, b in pairs:
        table[a][b] += 1
    return table

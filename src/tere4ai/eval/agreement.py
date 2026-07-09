"""Inter-annotator agreement statistics: pure, hand-checkable functions.

@implements: DEC-11
@grounded_by: REF-16

Implements the agreement reporting of the annotation protocol
(eval/gold/ANNOTATION_PROTOCOL.md) and architecture.md Section 12: Cohen's
kappa over the closed classification categories and raw (observed)
agreement, plus a per-category confusion table for the disagreement
discussion. Every function is pure and deterministic: no I/O, no model, no
randomness. Inputs are two equal-length sequences of labels where position
i is the same item labelled by annotator A and annotator B; labels are any
hashable category values (two or more categories are supported).
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


def cohen_kappa(labels_a: Sequence[L], labels_b: Sequence[L]) -> float:
    """Cohen's kappa: (p_o - p_e) / (1 - p_e) over two or more categories.

    p_o is the observed agreement; p_e is the expected chance agreement from
    the two annotators' marginal label distributions. Degenerate case: when
    p_e == 1.0 both annotators used a single identical category for every
    item, which forces p_o == 1.0, so kappa is returned as 1.0 instead of
    dividing by zero (agreement is perfect, just unmeasurable against
    chance). Raises ValueError on empty or length-mismatched input.
    """
    pairs = _validated_pairs(labels_a, labels_b)
    n = len(pairs)
    p_o = sum(1 for a, b in pairs if a == b) / n
    marginal_a = Counter(a for a, _ in pairs)
    marginal_b = Counter(b for _, b in pairs)
    categories = set(marginal_a) | set(marginal_b)
    p_e = sum(marginal_a[c] * marginal_b[c] for c in categories) / (n * n)
    if p_e == 1.0:
        return 1.0
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

"""E6's declared analysis: pure functions over kept ablation runs (spec G D-G84, B150).

@implements: DEC-11, DEC-17
@grounded_by: ADD-73, ADD-74, ADD-72

What spec G D-G84 declares, computed and nothing else: one right-or-wrong
outcome per case, condition and repetition (D-G84 (1)); the majority over
an odd number of repetitions, a run-once outcome its single value (D-G84
(3)); for each declared contrast the paired difference over the same cases,
its percentile interval from a paired bootstrap over cases (ADD-73, p. 1388;
the percentile interval itself is Efron and Tibshirani 1993, staged, not
registered), McNemar's exact test (ADD-74, VoR p. 1904) and Bonferroni's
threshold (ADD-73, pp. 1389 to 1390); each condition's per-call accuracy and
run-to-run variation, descriptive; the runtime judge's four shares on the
answers it gates (D-G84 (4)); the pilot run's count (D-G84 (5)). What D-G84
leaves unstated is returned as "not computed: awaiting Jose's decision" with
its question (thesis/CLAUDE.md, the methods rule). No I/O and no model;
randomness only from a random.Random seeded with the recorded seed and a
label.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Sequence
from fractions import Fraction
from typing import Any

# an Article's node id: a question key that is one credits a node inside it (D-G84 (1))
ARTICLE_ID = re.compile(r"^eu-ai-act:article-\d+[a-z]?$")
SHARES = ("wrong_answers_caught", "right_answers_blocked", "accuracy_among_delivered", "share_delivered")
# float rounding at the boundary of the pilot run's rule (ruling R18)
TOLERANCE = 1e-12


class AnalysisError(ValueError):
    """The kept runs or the answer key cannot be read as D-G84 states; the message says why."""


def not_computed(what: str, question: str) -> str:
    """The line printed in place of a computation D-G84 leaves to Jose."""
    return f"not computed: awaiting Jose's decision on {what} ({question})"


def case_outcome(item: dict[str, Any], result: dict[str, Any] | None) -> bool:
    """One case's outcome in one condition and one repetition (spec G D-G84 (1)).

    A classification case is right when the level equals the label; no
    answer, an abstention on a case labelled with a level and a failed call
    are not right. A question case is right when the answer's citations
    include a key node or, for a key node that is an Article, a node inside
    it; a retrieval case only on a key node itself; a key of several nodes is
    met when one is cited. A gated condition's citations are the ones the
    gate returned, as the run stored them."""
    kind = item.get("kind")
    if kind == "classification":
        label = (item.get("gold") or {}).get("risk_category")
        if label is None:
            raise AnalysisError(f"{item.get('id')}: a classification case without a label")
    elif kind in ("retrieval", "qa"):
        keys = [str(k) for k in item.get("gold_citations") or []]
        if not keys:
            raise AnalysisError(f"{item.get('id')}: a {kind} case without a key node")
    else:
        raise AnalysisError(f"{item.get('id')}: unknown case kind {kind!r}")
    if not result or "error" in result:
        return False
    if kind == "classification":
        return result.get("risk_category") == label
    cited = {str(c) for c in result.get("citations") or []}
    if kind == "retrieval":
        return any(k in cited for k in keys)
    return any(k in cited or (ARTICLE_ID.match(k) is not None and any(c.startswith(k + ":") for c in cited))
               for k in keys)


def majority(outcomes: Sequence[bool]) -> bool:
    """The majority of an odd number of outcomes (spec G D-G84 (3))."""
    if len(outcomes) % 2 == 0:
        raise AnalysisError(f"an even number of outcomes ({len(outcomes)}) has no majority; the count must be odd")
    return sum(1 for o in outcomes if o) * 2 > len(outcomes)


def mcnemar_exact_p(condition_only: int, against_only: int) -> float:
    """McNemar's exact two-sided p from the two discordant counts: twice the
    binomial tail at one half up to the smaller count, at most 1, in
    fractions (ADD-74, VoR p. 1904; ruling R6)."""
    n = condition_only + against_only
    smaller = min(condition_only, against_only)
    tail = Fraction(sum(math.comb(n, k) for k in range(smaller + 1)), 2**n)
    return float(min(Fraction(1), 2 * tail))


def percentile_interval(values: Sequence[float], level: float) -> tuple[float, float]:
    """The percentile interval at positions floor((k - 1) * tail) and
    ceil((k - 1) * (1 - tail)) of the sorted values, tail = (1 - level) / 2,
    the positions of spec F's calibration intervals (t2.interval): provisional,
    awaiting Jose (B150 Q12)."""
    ordered = sorted(values)
    if not ordered:
        raise AnalysisError("no resampled value to read an interval from")
    k = len(ordered)
    tail = (1 - level) / 2
    return ordered[math.floor((k - 1) * tail)], ordered[math.ceil((k - 1) * (1 - tail))]


def seeded_rng(seed: int, label: str) -> random.Random:
    """One generator per contrast or condition, from the recorded seed and a label (ruling R3)."""
    return random.Random(f"{seed}:{label}")


def paired_contrast(pairs: list[tuple[bool, bool]], *, level: float, draws: int, seed: int, label: str,
                    threshold: float) -> dict[str, Any]:
    """One declared contrast over the cases' majority outcomes, (condition,
    against) per case (spec G D-G84 (1) to (3)): the paired difference, its
    percentile interval from a paired bootstrap over cases (each resample
    draws cases with replacement with both conditions' outcomes), McNemar's
    exact p and whether it is below Bonferroni's threshold."""
    n = len(pairs)
    if n == 0:
        return {"cases": 0, "not_computed": "no case of the contrast's kinds in the answer key"}
    condition_only = sum(1 for a, b in pairs if a and not b)
    against_only = sum(1 for a, b in pairs if b and not a)
    signed = [int(a) - int(b) for a, b in pairs]
    rng = seeded_rng(seed, label)
    resampled = [sum(signed[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws)]
    low, high = percentile_interval(resampled, level)
    p = mcnemar_exact_p(condition_only, against_only)
    return {
        "cases": n,
        "condition_right": sum(1 for a, _ in pairs if a),
        "against_right": sum(1 for _, b in pairs if b),
        "condition_only_right": condition_only,
        "against_only_right": against_only,
        "difference": (condition_only - against_only) / n,
        "interval": [low, high], "level": level, "draws": draws, "seed": seed,
        "mcnemar_exact_p": p, "threshold": threshold,
        # an exact p is a multiple of 1 / 2 ** (b + c), never equal to 0.05 / 3 (ruling R7)
        "no_difference_rejected": p < threshold,
    }


def outcome_table(cases: list[dict[str, Any]], runs: list[dict[str, dict[str, dict[str, Any]]]],
                  condition: str, run_once: dict[str, Any]) -> dict[str, list[bool]]:
    """Each case's outcomes over the calls the group made, in order (runs[0] is
    the group's first run). A case the declaration runs once in this
    condition (spec G D-G84 (5)) has one call, in the first run: its row holds
    that one outcome, its single value (D-G84 (3)), never copies (Codex finding
    1, ruling R10); any other case must hold a result in every run."""
    once = condition in run_once["conditions"]
    table: dict[str, list[bool]] = {}
    for item in cases:
        ran_once = once and item.get("kind") == run_once["case_kind"]
        row = []
        for index, run in enumerate(runs[:1] if ran_once else runs):
            results = run.get(condition)
            if results is None or item["id"] not in results:
                raise AnalysisError(f"run {index + 1} of the group holds no result for {condition} on {item['id']}")
            row.append(case_outcome(item, results[item["id"]]))
        table[item["id"]] = row
    return table

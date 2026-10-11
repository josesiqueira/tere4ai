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
import statistics
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


# what each share counts, for the sentence that names an empty one
_COUNTS = {"wrong_answers_caught": "wrong answer", "right_answers_blocked": "right answer",
           "accuracy_among_delivered": "delivered answer", "share_delivered": "answer"}


def accuracy_by_repetition(table: dict[str, list[bool]], repetitions: int) -> list[float]:
    """Each repetition's share right over the cases run in every repetition, a
    run-once case (a row of one call) left out: provisional, awaiting Jose
    (B150 Q13, ruling R45). Empty when no case ran in every repetition."""
    full = [row for row in table.values() if len(row) == repetitions]
    if not full:
        return []
    return [sum(1 for row in full if row[r]) / len(full) for r in range(repetitions)]


def per_call_summary(table: dict[str, list[bool]], repetitions: int) -> dict[str, Any]:
    """A condition's per-call accuracy, the share right over every call the
    group made, a run-once case's one call counted once (D-G84 (3); Codex
    finding 1, ruling R10), and its run-to-run variation, the standard
    deviation (n - 1) across repetitions of each repetition's accuracy
    (rulings R8, R9; the basis provisional, B150 Q13). Descriptive, never
    tested."""
    by_repetition = accuracy_by_repetition(table, repetitions)
    calls = sum(len(row) for row in table.values())
    right = sum(1 for row in table.values() for outcome in row if outcome)
    return {"cases": len(table), "repetitions": repetitions, "calls": calls, "right": right,
            "share": right / calls if calls else None, "by_repetition": by_repetition,
            "cases_in_every_repetition": sum(1 for row in table.values() if len(row) == repetitions),
            "standard_deviation": statistics.stdev(by_repetition) if len(by_repetition) >= 2 else None}


def gate_answers(cases: list[dict[str, Any]], runs: list[dict[str, dict[str, dict[str, Any]]]], condition: str,
                 first_repetition: int = 1) -> tuple[dict[str, list[tuple[bool, bool]]], list[dict[str, Any]]]:
    """The answers the runtime judge gated in one condition, per case over the
    repetitions, each (right, delivered), delivered when the verdict is
    accepted (spec G D-G84 (4)). A failed call has no answer to gate: it is
    left out and listed (ruling R15); a gated answer without a verdict
    refuses (ruling R16)."""
    answers: dict[str, list[tuple[bool, bool]]] = {}
    failed: list[dict[str, Any]] = []
    for item in cases:
        row = []
        for offset, run in enumerate(runs):
            repetition = first_repetition + offset
            results = run.get(condition)
            if results is None or item["id"] not in results:
                raise AnalysisError(f"repetition {repetition} holds no result for {condition} on {item['id']}")
            result = results[item["id"]]
            if "error" in result:
                failed.append({"repetition": repetition, "case": item["id"], "error": str(result["error"])})
                continue
            verdict = result.get("judge_verdict")
            if verdict is None:
                raise AnalysisError(f"{condition} on {item['id']} in repetition {repetition} carries no "
                                    "runtime judge verdict")
            row.append((case_outcome(item, result), verdict == "accepted"))
        answers[item["id"]] = row
    return answers, failed


def _share(numerator: int, denominator: int) -> dict[str, Any]:
    # an empty denominator is None, never 0 or 1 (spec G D-G33)
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def gate_shares(rows: Sequence[Sequence[tuple[bool, bool]]]) -> dict[str, dict[str, Any]]:
    """The four shares of spec G D-G84 (4), pooled over every answer given."""
    pooled = [answer for row in rows for answer in row]
    wrong = [delivered for right, delivered in pooled if not right]
    right = [delivered for is_right, delivered in pooled if is_right]
    delivered = [is_right for is_right, was_delivered in pooled if was_delivered]
    return {
        "wrong_answers_caught": _share(sum(1 for d in wrong if not d), len(wrong)),
        "right_answers_blocked": _share(sum(1 for d in right if not d), len(right)),
        "accuracy_among_delivered": _share(sum(1 for r in delivered if r), len(delivered)),
        "share_delivered": _share(len(delivered), len(pooled)),
    }


def gate_share_intervals(answers: dict[str, list[tuple[bool, bool]]], *, level: float, draws: int, seed: int,
                         label: str) -> dict[str, list[float] | str | None]:
    """Each share's percentile interval from a bootstrap over cases that draws
    each case with all its repetitions (spec G D-G84 (4)). None where the
    share itself has nothing to count; the not-computed line where some
    resample has nothing to count (B150 Q11)."""
    point = gate_shares(list(answers.values()))
    ids = sorted(answers)
    rng = seeded_rng(seed, label)
    drawn: dict[str, list[float]] = {share: [] for share in SHARES}
    empty = dict.fromkeys(SHARES, 0)
    for _ in range(draws if ids else 0):
        rows = [answers[ids[rng.randrange(len(ids))]] for _ in ids]
        for share, value in gate_shares(rows).items():
            if value["rate"] is None:
                empty[share] += 1
            else:
                drawn[share].append(value["rate"])
    out: dict[str, list[float] | str | None] = {}
    for share in SHARES:
        if point[share]["rate"] is None:
            out[share] = None
        elif empty[share]:
            out[share] = not_computed(f"an interval when {empty[share]} of {draws} resamples hold no "
                                      f"{_COUNTS[share]}", "B150 Q11")
        else:
            out[share] = list(percentile_interval(drawn[share], level))
    return out


def gate_shares_by_repetition(cases: list[dict[str, Any]], runs: list[dict[str, dict[str, dict[str, Any]]]],
                              condition: str) -> dict[str, list[float | None]]:
    """Each repetition's four shares, for the pilot run's figures (spec G D-G84 (5))."""
    out: dict[str, list[float | None]] = {share: [] for share in SHARES}
    for index, run in enumerate(runs):
        answers, _ = gate_answers(cases, [run], condition, first_repetition=index + 1)
        for share, value in gate_shares(list(answers.values())).items():
            out[share].append(value["rate"])
    return out


def required_repetitions(sd: float, *, z: float, half_width: float) -> int:
    """The smallest odd N with z * sd / sqrt(N) at most half_width (spec G D-G84 (5))."""
    n = 1
    while z * sd > half_width * math.sqrt(n) + TOLERANCE:
        n += 2
    return n


def pilot_count(figures: dict[str, list[float | None]], *, z: float, half_width: float,
                cap: int) -> dict[str, Any]:
    """The main run's count from the pilot run's figures (spec G D-G84 (5)): for
    each figure the standard deviation (n - 1) across the repetitions and the
    smallest odd N reaching the half-width; N is the largest of them, at most
    cap, with the precision reached when the cap binds. A figure without a
    value in some repetition leaves N not computed (B150 Q11); a figure with
    fewer than two values (one repetition only, or no case run in every
    repetition) has no standard deviation, and N is not computed either, said in its own sentence (a
    failure mechanic, not a question for Jose)."""
    if not figures:
        raise AnalysisError("the pilot run gave no figure")
    rows: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    short: list[str] = []
    for name, values in figures.items():
        if len(values) < 2 or any(v is None for v in values):
            (short if len(values) < 2 else missing).append(name)
            rows[name] = {"by_repetition": values, "standard_deviation": None, "required": None}
            continue
        sd = statistics.stdev(values)
        rows[name] = {"by_repetition": values, "standard_deviation": sd,
                      "required": required_repetitions(sd, z=z, half_width=half_width)}
    if missing or short:
        reasons = []
        if short:
            reasons.append("not computed: a standard deviation needs a value in at least two repetitions, and "
                           + ", ".join(short) + (" holds" if len(short) == 1 else " hold")
                           + " fewer than two (one repetition only, or no case of it run in every repetition)")
        if missing:
            reasons.append(not_computed("the count when a figure has no value in a repetition ("
                                        + ", ".join(missing) + ")", "B150 Q11"))
        return {"figures": rows, "count": None, "cap": cap, "cap_binds": None, "precision_reached": None,
                "not_computed": "; ".join(reasons)}
    needed = max(r["required"] for r in rows.values())
    count = min(needed, cap)
    for r in rows.values():
        r["half_width_at_count"] = z * r["standard_deviation"] / math.sqrt(count)
    binds = needed > cap
    return {"figures": rows, "count": count, "cap": cap, "cap_binds": binds,
            "precision_reached": max(r["half_width_at_count"] for r in rows.values()) if binds else None,
            "not_computed": None}

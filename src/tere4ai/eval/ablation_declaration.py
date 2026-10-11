"""E6's declaration: the analysis spec G D-G84 declares before the main run (B150).

@implements: DEC-11, DEC-17
@grounded_by: ADD-73, ADD-74

One file, eval/e6_declaration.json, holds what Jose decided on 2026-10-11
(spec G D-G84 (1) to (5)): the three primary contrasts on the hand-made
legal test set with their case kinds, the outcome rules, the majority over
an odd number of repetitions, McNemar's exact test, the percentile interval
of a paired bootstrap over cases, Bonferroni's correction, the runtime
judge's four shares, and the pilot run's rule for the number of
repetitions. Every run record of scripts/run_ablations.py carries the
file's digest (D-G84 (7)), so the analysis says whether the family was
declared before the run started. The loader holds every value D-G84 states
(the three contrasts, their case kinds and readings, the outcome rules,
McNemar's exact test, Bonferroni at 0.05, a 95% level, the runtime judge's
conditions, case kinds and shares, the pilot run's 5 repetitions, z 1.96,
half-width 0.02 and cap 11, the run-once rule of D-G84 (5)) and refuses any
other, never reading one as a default, so a change of method needs a spec
amendment and a code change; the benchmark's secondary contrasts take the
primary list's shape and stay empty until Jose names them (B150 Q8). The
1000 draws are provisional, awaiting Jose (B150 Q12).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tere4ai.eval.strategies import STRATEGY_NAMES, uses_runtime_judge
from tere4ai.graph_store.build_chain import sha256_of_file

DECLARATION_PATH = Path(__file__).resolve().parents[3] / "eval" / "e6_declaration.json"
DECLARATION_VERSION = "e6_declaration.v1"
CASE_KINDS = ("classification", "retrieval", "qa")
# spec G D-G84 (1) and (3), by name; the analysis implements exactly these
OUTCOME_RULES = {
    "classification": "level_equals_label",
    "qa": "key_node_or_node_inside_key_article",
    "retrieval": "key_node_exact",
    "key_with_several_nodes": "at_least_one_cited",
    "gated_conditions": "citations_the_gate_returns",
    "failed_call": "wrong",
    "per_case": "majority_over_odd_repetitions",
}
SHARE_NAMES = ("wrong_answers_caught", "right_answers_blocked", "accuracy_among_delivered", "share_delivered")
_TOP = {"declaration", "decided", "primary_family", "outcome", "runtime_judge", "repetitions", "secondary"}
_CONTRAST = {"id", "condition", "against", "case_kinds", "reading"}
_READINGS = ("two_packages", "conditional_effect")
# spec G D-G84 (1): the family is exactly these three contrasts, in this order
PRIMARY_CONTRASTS = [
    {"id": "graph_full_minus_plain_llm", "condition": "graph_full", "against": "plain_llm",
     "case_kinds": ["classification", "retrieval", "qa"], "reading": "two_packages"},
    {"id": "graph_full_minus_vector_rag", "condition": "graph_full", "against": "vector_rag",
     "case_kinds": ["classification", "retrieval", "qa"], "reading": "two_packages"},
    {"id": "graph_build_judge_minus_graph_no_judge", "condition": "graph_build_judge",
     "against": "graph_no_judge", "case_kinds": ["retrieval", "qa"], "reading": "conditional_effect"},
]
PRIMARY_ALPHA = 0.05
RUNTIME_JUDGE_CONDITIONS = ["graph_runtime_judge", "graph_full"]
RUNTIME_JUDGE_CASE_KINDS = ["retrieval", "qa"]
RUN_ONCE_CONDITIONS = ["graph_no_judge", "graph_build_judge", "graph_full", "graph_runtime_judge"]
# D-G84 (5): the pilot run's rule for the number of repetitions
PILOT_REPETITIONS, Z, HALF_WIDTH, CAP = 5, 1.96, 0.02, 11
# PROVISIONAL, awaiting Jose (B150 Q12): the number of bootstrap draws
BOOTSTRAP_DRAWS = 1000


class DeclarationError(ValueError):
    """The declaration file is missing, unreadable or outside D-G84's shape; the message says which."""


def declaration_sha256(path: Path = DECLARATION_PATH) -> str:
    return sha256_of_file(path)


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise DeclarationError(f"e6 declaration: {what}")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_interval(block: Any, where: str, method: str) -> None:
    _need(isinstance(block, dict) and set(block) == {"method", "level", "draws", "seed"},
          f"{where} needs exactly method, level, draws and seed")
    _need(block["method"] == method, f"{where}.method must be {method}")
    # spec G D-G84 (3), (4): a 95% interval; another level would print under a false heading
    _need(block["level"] == 0.95, f"{where}.level must be 0.95 (spec G D-G84: a 95% interval)")
    _need(_integer(block["draws"]) and block["draws"] >= 1, f"{where}.draws must be a whole number of at least 1")
    # PROVISIONAL, awaiting Jose (B150 Q12): built as proposed
    _need(block["draws"] == BOOTSTRAP_DRAWS, f"{where}.draws must be {BOOTSTRAP_DRAWS} (provisional, B150 Q12)")
    _need(_integer(block["seed"]), f"{where}.seed must be a whole number")


def _check_contrasts(contrasts: Any, where: str) -> None:
    _need(isinstance(contrasts, list), f"{where} must be a list")
    seen: set[str] = set()
    for c in contrasts:
        _need(isinstance(c, dict) and set(c) == _CONTRAST,
              f"{where}: each contrast needs exactly {', '.join(sorted(_CONTRAST))}")
        _need(isinstance(c["id"], str) and c["id"] != "" and c["id"] not in seen,
              f"{where}: contrast id {c['id']!r} must be a new name")
        seen.add(c["id"])
        for side in ("condition", "against"):
            _need(c[side] in STRATEGY_NAMES, f"{c['id']}: {side} {c[side]!r} is not a condition of STRATEGY_NAMES")
        _need(c["condition"] != c["against"], f"{c['id']}: a condition is never compared with itself")
        kinds = c["case_kinds"]
        _need(isinstance(kinds, list) and kinds and all(isinstance(k, str) for k in kinds)
              and len(set(kinds)) == len(kinds) and set(kinds) <= set(CASE_KINDS),
              f"{c['id']}: case_kinds must name some of {', '.join(CASE_KINDS)}, each once")
        _need(c["reading"] in _READINGS, f"{c['id']}: reading must be one of {', '.join(_READINGS)}")


def _check(data: Any) -> None:
    _need(isinstance(data, dict), "the file must hold one object")
    _need(set(data) == _TOP, f"top-level keys must be {', '.join(sorted(_TOP))}; got {', '.join(sorted(data))}")
    _need(data["declaration"] == DECLARATION_VERSION, f"declaration must be {DECLARATION_VERSION}")
    _need(isinstance(data["decided"], str) and data["decided"] != "", "decided must name the decision")
    family = data["primary_family"]
    _need(isinstance(family, dict)
          and set(family) == {"answer_key", "contested", "contrasts", "correction", "test", "interval"},
          "primary_family needs exactly answer_key, contested, contrasts, correction, test and interval")
    _need(family["answer_key"] == "hand_made", "primary_family.answer_key must be hand_made")
    _need(family["contested"] == "left_out", "primary_family.contested must be left_out (B149)")
    _check_contrasts(family["contrasts"], "primary_family.contrasts")
    _need(family["contrasts"] == PRIMARY_CONTRASTS,
          "primary_family.contrasts must be exactly the three contrasts of spec G D-G84 (1), in order")
    correction = family["correction"]
    _need(isinstance(correction, dict) and set(correction) == {"method", "alpha"}
          and correction["method"] == "bonferroni", "primary_family.correction.method must be bonferroni")
    _need(_number(correction["alpha"]) and 0 < correction["alpha"] < 1,
          "primary_family.correction.alpha must lie between 0 and 1")
    _need(correction["alpha"] == PRIMARY_ALPHA, f"primary_family.correction.alpha must be {PRIMARY_ALPHA} (D-G84 (3))")
    _need(family["test"] == "mcnemar_exact_two_sided", "primary_family.test must be mcnemar_exact_two_sided")
    _check_interval(family["interval"], "primary_family.interval", "paired_bootstrap_percentile_over_cases")
    _need(data["outcome"] == OUTCOME_RULES, "outcome must name exactly the rules of spec G D-G84 (1) and (3)")
    judge = data["runtime_judge"]
    _need(isinstance(judge, dict) and set(judge) == {"conditions", "answer_key", "case_kinds", "delivered",
                                                     "shares", "pooling", "interval"},
          "runtime_judge needs exactly conditions, answer_key, case_kinds, delivered, shares, pooling and interval")
    _need(judge["conditions"] == RUNTIME_JUDGE_CONDITIONS,
          "runtime_judge.conditions must be graph_runtime_judge and graph_full (D-G84 (4))")
    _need(isinstance(judge["conditions"], list) and judge["conditions"]
          and all(c in STRATEGY_NAMES and uses_runtime_judge(c) for c in judge["conditions"]),
          "runtime_judge.conditions must name conditions that call the runtime judge")
    _need(judge["answer_key"] == "hand_made", "runtime_judge.answer_key must be hand_made")
    _need(judge["case_kinds"] == RUNTIME_JUDGE_CASE_KINDS,
          "runtime_judge.case_kinds must be retrieval and qa, the question and retrieval cases of D-G84 (4)")
    _need(judge["delivered"] == "verdict_accepted", "runtime_judge.delivered must be verdict_accepted")
    _need(judge["shares"] == list(SHARE_NAMES), f"runtime_judge.shares must be {', '.join(SHARE_NAMES)}")
    _need(judge["pooling"] == "every_answer_of_every_repetition",
          "runtime_judge.pooling must be every_answer_of_every_repetition")
    _check_interval(judge["interval"], "runtime_judge.interval", "case_bootstrap_percentile_all_repetitions")
    reps = data["repetitions"]
    _need(isinstance(reps, dict) and set(reps) == {"pilot_repetitions", "development_set", "figures", "z",
                                                   "half_width", "cap", "count", "run_once"},
          "repetitions needs exactly pilot_repetitions, development_set, figures, z, half_width, cap, count and run_once")
    _need(_integer(reps["pilot_repetitions"]) and reps["pilot_repetitions"] >= 2,
          "repetitions.pilot_repetitions must be a whole number of at least 2")
    _need(reps["development_set"] == "ref15_items_outside_the_frozen_sample",
          "repetitions.development_set must be ref15_items_outside_the_frozen_sample")
    _need(reps["figures"] == ["accuracy_per_condition", "runtime_judge_shares"],
          "repetitions.figures must be accuracy_per_condition and runtime_judge_shares")
    _need(_number(reps["z"]) and reps["z"] > 0, "repetitions.z must be a positive number")
    _need(_number(reps["half_width"]) and reps["half_width"] > 0, "repetitions.half_width must be a positive number")
    _need(_integer(reps["cap"]) and reps["cap"] >= 1 and reps["cap"] % 2 == 1,
          "repetitions.cap must be an odd whole number")
    _need(reps["pilot_repetitions"] == PILOT_REPETITIONS,
          f"repetitions.pilot_repetitions must be {PILOT_REPETITIONS} (D-G84 (5))")
    _need(reps["z"] == Z and reps["half_width"] == HALF_WIDTH and reps["cap"] == CAP,
          f"repetitions z, half_width and cap must be {Z}, {HALF_WIDTH} and {CAP} (D-G84 (5))")
    _need(reps["count"] == "smallest_odd", "repetitions.count must be smallest_odd")
    once = reps["run_once"]
    _need(isinstance(once, dict) and set(once) == {"conditions", "case_kind"}
          and once["case_kind"] == "classification"
          and once["conditions"] == RUN_ONCE_CONDITIONS,
          "repetitions.run_once must name conditions 3 to 6 and the classification case kind "
          "(the run-once rule of spec G D-G84 (5))")
    secondary = data["secondary"]
    _need(isinstance(secondary, dict) and set(secondary) == {"answer_key", "contrasts", "status"}
          and secondary["answer_key"] == "benchmark",
          "secondary needs exactly answer_key benchmark, contrasts and status")
    # empty until Jose names the benchmark's contrasts (B150 Q8); a listed one takes the primary list's shape
    _check_contrasts(secondary["contrasts"], "secondary.contrasts")
    _need(isinstance(secondary["status"], str) and secondary["status"] != "", "secondary.status must say what is declared")


def load_declaration(path: Path = DECLARATION_PATH) -> dict[str, Any]:
    """The declaration, checked against D-G84's shape; DeclarationError otherwise."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeclarationError(f"{Path(path).name}: not readable JSON ({type(exc).__name__})") from exc
    _check(data)
    return data

"""E6's declaration file: what spec G D-G84 declares before the main run (B150).

Covers DEC-11. The repository's file is read as it is; every refusal is a
mutated copy of it in a temporary directory.
"""

from __future__ import annotations

import json

import pytest

from tere4ai.eval.ablation_declaration import (
    DECLARATION_PATH,
    DeclarationError,
    declaration_sha256,
    load_declaration,
    pilot_draw,
)
from tere4ai.graph_store.build_chain import sha256_of_file


def test_the_repository_declaration_holds_d_g84():
    d = load_declaration()
    family = d["primary_family"]
    assert [(c["condition"], c["against"], c["case_kinds"]) for c in family["contrasts"]] == [
        ("graph_full", "plain_llm", ["classification", "retrieval", "qa"]),
        ("graph_full", "vector_rag", ["classification", "retrieval", "qa"]),
        ("graph_build_judge", "graph_no_judge", ["retrieval", "qa"]),
    ]
    assert family["correction"] == {"method": "bonferroni", "alpha": 0.05}
    assert family["test"] == "mcnemar_exact_two_sided"
    assert (family["interval"]["level"], family["interval"]["draws"]) == (0.95, 1000)
    assert d["runtime_judge"]["conditions"] == ["graph_runtime_judge", "graph_full"]
    assert d["runtime_judge"]["case_kinds"] == ["retrieval", "qa"]
    reps = d["repetitions"]
    assert (reps["pilot_repetitions"], reps["z"], reps["half_width"], reps["cap"]) == (5, 1.96, 0.02, 11)
    assert reps["run_once"] == {"conditions": ["graph_no_judge", "graph_build_judge", "graph_full",
                                               "graph_runtime_judge"], "case_kind": "classification"}
    assert reps["pilot_sample"] == {"drawn_from": "development_set", "composition": "frozen_sample",
                                    "scenarios_per_risk_level": 8, "qa_pairs": 15, "seed": 20261011}
    assert d["empty_resamples"] == {"rule": "left_out_and_counted", "conditional_up_to": 25, "of_draws": 1000,
                                    "pilot": "figure_left_out_of_n_and_named"}
    assert d["declaration"] == "e6_declaration.v2"
    assert d["secondary"]["contrasts"] == family["contrasts"] and d["secondary"]["test"] == "none"
    assert "provisional" not in json.dumps(d)
    assert pilot_draw(d) == {"seed": 20261011, "scenarios_per_risk_level": 8, "qa_pairs": 15}


def test_the_digest_is_the_files_own():
    assert declaration_sha256() == sha256_of_file(DECLARATION_PATH)


def _mutated(tmp_path, change):
    data = json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "e6_declaration.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("change, words", [
    (lambda d: d["primary_family"]["correction"].update(method="holm"), "bonferroni"),
    (lambda d: d["primary_family"].update(test="mcnemar_asymptotic"), "mcnemar_exact_two_sided"),
    (lambda d: d["primary_family"]["contrasts"][0].update(against="graph_traversal"), "STRATEGY_NAMES"),
    (lambda d: d["primary_family"]["contrasts"][2].update(case_kinds=["essay"]), "case_kinds"),
    (lambda d: d["primary_family"]["contrasts"][1].update(id="graph_full_minus_plain_llm"), "new name"),
    (lambda d: d["repetitions"].update(cap=10), "odd"),
    (lambda d: d["repetitions"].update(pilot_repetitions=1), "pilot_repetitions"),
    (lambda d: d["outcome"].update(qa="key_node_exact"), "outcome"),
    (lambda d: d["runtime_judge"]["interval"].update(level=0.8), "0.95"),
    (lambda d: d["secondary"]["contrasts"].append({"id": "x"}), "secondary.contrasts"),
    (lambda d: d.update(extra=1), "top-level keys"),
    (lambda d: d["runtime_judge"].update(case_kinds=["classification"]), "runtime_judge.case_kinds"),
    (lambda d: d["primary_family"]["interval"].update(draws=0), "draws"),
    (lambda d: d["primary_family"]["interval"].update(draws=500), "1000"),
    (lambda d: d["primary_family"]["interval"].update(level=0.8), "0.95"),
    (lambda d: d["primary_family"]["contrasts"].append(
        dict(d["primary_family"]["contrasts"][0], id="fourth")), "exactly the three contrasts"),
    (lambda d: d["primary_family"]["contrasts"][2].update(case_kinds=["classification", "retrieval", "qa"]),
     "exactly the three contrasts"),
    (lambda d: d["primary_family"]["contrasts"].reverse(), "exactly the three contrasts"),
    (lambda d: d["primary_family"]["correction"].update(alpha=0.10), "0.05"),
    (lambda d: d["repetitions"].update(pilot_repetitions=7), "pilot_repetitions must be 5"),
    (lambda d: d["repetitions"].update(z=1.64), "1.96"),
    (lambda d: d["repetitions"].update(half_width=0.05), "0.02"),
    (lambda d: d["repetitions"].update(cap=13), "11"),
    (lambda d: d["repetitions"]["run_once"].update(conditions=["graph_full"]), "run_once"),
    (lambda d: d["runtime_judge"].update(conditions=["graph_runtime_judge"]), "runtime_judge.conditions"),
    (lambda d: d["runtime_judge"]["interval"].update(draws=10), "1000"),
    (lambda d: d["primary_family"]["contrasts"][0].update(case_kinds=[["qa"]]), "case_kinds"),
    # final review M4: D-G84 (4) states both question and retrieval cases, so one alone is refused
    (lambda d: d["runtime_judge"].update(case_kinds=["qa"]), "runtime_judge.case_kinds must be retrieval and qa"),
    (lambda d: d["runtime_judge"].update(case_kinds=["retrieval"]), "runtime_judge.case_kinds must be retrieval and qa"),
    # B161: the v2 values (B150 Q8, Q10, Q11), each pinned
    (lambda d: d["secondary"].update(contrasts=[]), "secondary.contrasts must be the primary family's three"),
    (lambda d: d["secondary"].update(test="mcnemar_exact_two_sided"), "secondary.test must be none"),
    (lambda d: d["repetitions"]["pilot_sample"].update(seed=7), "repetitions.pilot_sample must be"),
    (lambda d: d["repetitions"]["pilot_sample"].update(qa_pairs=122), "repetitions.pilot_sample must be"),
    (lambda d: d["empty_resamples"].update(conditional_up_to=30), "empty_resamples must be"),
    # Task 3 review, Minor 1: B150 Q8 is answered, so a secondary status still awaiting it is refused
    (lambda d: d["secondary"].update(status="not computed: awaiting Jose's decision on the benchmark's contrasts "
                                            "(B150 Q8)"),
     "secondary.status must not await a decision"),
    (lambda d: d["secondary"].update(status="Awaiting B150 Q8"), "secondary.status must not await a decision"),
])
def test_a_declaration_outside_d_g84s_shape_is_refused(tmp_path, change, words):
    with pytest.raises(DeclarationError, match=words):
        load_declaration(_mutated(tmp_path, change))


def test_an_unlisted_secondary_contrast_is_refused(tmp_path):
    # B150 Q8: the benchmark's contrasts are exactly the primary family's three; a fourth is refused
    path = _mutated(tmp_path, lambda d: d["secondary"]["contrasts"].append(
        {"id": "graph_full_minus_graph_no_judge", "condition": "graph_full", "against": "graph_no_judge",
         "case_kinds": ["retrieval", "qa"], "reading": "two_packages"}))
    with pytest.raises(DeclarationError, match="secondary.contrasts must be the primary family's three"):
        load_declaration(path)


def test_an_unreadable_file_is_refused_by_name(tmp_path):
    path = tmp_path / "e6_declaration.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(DeclarationError, match="e6_declaration.json"):
        load_declaration(path)


def test_the_run_once_refusal_cites_the_decided_rule_not_a_question(tmp_path):
    # final review M3: the run-once rule is decided (D-G84 (5)); B150 Q13 is each repetition's accuracy only
    with pytest.raises(DeclarationError) as raised:
        load_declaration(_mutated(tmp_path, lambda d: d["repetitions"]["run_once"].update(conditions=["graph_full"])))
    message = str(raised.value)
    assert "spec G D-G84 (5)" in message and "Q13" not in message and "provisional" not in message

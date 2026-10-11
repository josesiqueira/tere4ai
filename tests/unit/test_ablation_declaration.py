"""E6's declaration file: what spec G D-G84 declares before the main run (B150).

Covers DEC-11. The repository's file is read as it is; every refusal is a
mutated copy of it in a temporary directory.
"""

from __future__ import annotations

import copy
import json

import pytest

from tere4ai.eval.ablation_declaration import (
    DECLARATION_PATH,
    DeclarationError,
    declaration_sha256,
    load_declaration,
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
    assert d["secondary"]["contrasts"] == [] and "B150 Q8" in d["secondary"]["status"]


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
])
def test_a_declaration_outside_d_g84s_shape_is_refused(tmp_path, change, words):
    with pytest.raises(DeclarationError, match=words):
        load_declaration(_mutated(tmp_path, change))


def test_a_listed_benchmark_contrast_loads(tmp_path):
    # B150 Q8: the list is empty until Jose names the contrasts; a listed one takes the primary shape
    path = _mutated(tmp_path, lambda d: d["secondary"]["contrasts"].append(
        dict(copy.deepcopy(d["primary_family"]["contrasts"][0]), id="bench_graph_full_minus_plain_llm")))
    assert load_declaration(path)["secondary"]["contrasts"][0]["against"] == "plain_llm"


def test_an_unreadable_file_is_refused_by_name(tmp_path):
    path = tmp_path / "e6_declaration.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(DeclarationError, match="e6_declaration.json"):
        load_declaration(path)

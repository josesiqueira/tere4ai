"""run_ablations' repetition group and run-once rule (spec G D-G84 (5), (7); B150).

Mock data only: the model clients and the strategies are doubles.
"""

from __future__ import annotations

import json
from collections import Counter

from tests.unit.test_run_ablations_record import runner  # noqa: F401

from tere4ai.eval.ablation_declaration import DECLARATION_PATH, declaration_sha256
from tere4ai.eval.evaluation_record import EvaluationRecordStore
from tere4ai.eval.strategies import STRATEGY_NAMES as SIX
from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable

ITEMS = [
    {"id": "gold:cls-1", "kind": "classification", "gold": {"risk_category": "high_risk"}, "gold_citations": []},
    {"id": "gold:qa-1", "kind": "qa", "question": "q", "gold": {}, "gold_citations": ["eu-ai-act:article-9"]},
]
GRAPH = ("graph_no_judge", "graph_build_judge", "graph_full", "graph_runtime_judge")


def _install(runner, monkeypatch, items=ITEMS, stop_once=None):  # noqa: F811
    """stop_once: a (condition, case) whose first call stops the run as an overloaded backend does."""
    monkeypatch.setattr(runner.strategies, "STRATEGY_NAMES", SIX)
    runner.load_items = lambda b, f: [dict(i) for i in items]
    calls: Counter = Counter()
    stops = {stop_once} if stop_once else set()

    def fake_build(name, **kw):
        def strategy(item):
            if (name, item["id"]) in stops:
                stops.discard((name, item["id"]))
                raise InferenceBackendUnavailable(6, "HTTP 529")
            kw["generator"].complete()
            calls[(name, item["id"])] += 1
            if item["kind"] == "classification":
                return {"answer_text": "x", "citations": [], "risk_category": "high_risk"}
            return {"answer_text": "x", "citations": ["eu-ai-act:article-9"], "risk_category": None}
        strategy.models = {"generator": "g"}
        return strategy

    monkeypatch.setattr(runner.strategies, "build_strategy", fake_build)
    return calls


def _run(runner, tmp_path, tag, *extra):  # noqa: F811
    argv = ["--dump-dir", str(tmp_path), "--checkpoint", str(tmp_path / "results" / f"{tag}.jsonl"),
            "--summary", str(tmp_path / "results" / f"{tag}.json"), *extra]
    code = runner.main(argv)
    records = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records()
               if (r.get("config") or {}).get("checkpoint_file") == f"{tag}.jsonl"]
    # a resume begins a new record on the same checkpoint: the newest is the run
    return code, (max(records, key=lambda r: (r["started_at"], r["record_id"])) if records else None)


def test_every_run_record_carries_the_declarations_digest(runner, tmp_path, monkeypatch):  # noqa: F811
    _install(runner, monkeypatch)
    code, rec = _run(runner, tmp_path, "first")
    assert code == 0
    (decl,) = [i for i in rec["inputs"] if i["input_kind"] == "e6_declaration"]
    assert decl == {"input_kind": "e6_declaration", "file": "e6_declaration.json", "sha256": declaration_sha256()}
    assert rec["config"]["item_set"] == "main" and rec["config"]["repetition"] == "first"


def test_a_repetition_runs_the_classification_cases_of_conditions_3_to_6_once(runner, tmp_path, monkeypatch):  # noqa: F811
    calls = _install(runner, monkeypatch)
    _, first = _run(runner, tmp_path, "first")
    code, repeat = _run(runner, tmp_path, "second", "--repeat-of", first["record_id"])
    assert code == 0 and repeat["outcome"]["status"] == "completed"
    assert repeat["config"]["repetition"] == "repeat" and repeat["relations"]["repeat_of"] == first["record_id"]
    for name in GRAPH:
        assert calls[(name, "gold:cls-1")] == 1, name  # the first run only
        assert calls[(name, "gold:qa-1")] == 2, name
    for name in ("plain_llm", "vector_rag"):
        assert calls[(name, "gold:cls-1")] == 2 and calls[(name, "gold:qa-1")] == 2
    summary = json.loads((tmp_path / "results" / "second.json").read_text(encoding="utf-8"))
    for name in GRAPH:
        hand = summary["strategies"][name]["by_answer_key"]["hand_made"]
        assert hand["classification"]["total"] == 0, name  # not run here, never scored wrong
    assert summary["strategies"]["plain_llm"]["by_answer_key"]["hand_made"]["classification"]["total"] == 1
    assert summary["run_once"]["conditions"] == sorted(GRAPH) and summary["run_once"]["first_run"] == first["record_id"]
    assert any("runtime judge is not called" in n for n in summary["notes"])
    first_summary = json.loads((tmp_path / "results" / "first.json").read_text(encoding="utf-8"))
    assert "run_once" not in first_summary
    assert any("runtime judge is not called" in n for n in first_summary["notes"])


def test_a_repetition_of_a_repetition_is_refused_naming_the_first_run(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    _install(runner, monkeypatch)
    _, first = _run(runner, tmp_path, "first")
    _, second = _run(runner, tmp_path, "second", "--repeat-of", first["record_id"])
    capsys.readouterr()
    code, third = _run(runner, tmp_path, "third", "--repeat-of", second["record_id"])
    assert code == 2 and third is None
    assert f"name the group's first run {first['record_id']}" in capsys.readouterr().out


def test_a_repetition_under_another_declaration_or_other_items_is_refused_before_any_call(
        runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    calls = _install(runner, monkeypatch)
    _, first = _run(runner, tmp_path, "first")
    before = sum(calls.values())
    other = tmp_path / "e6_declaration.json"
    data = json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))
    data["primary_family"]["interval"]["seed"] = 7
    other.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    code, rec = _run(runner, tmp_path, "second", "--repeat-of", first["record_id"], "--declaration", str(other))
    assert code == 2 and rec is None and "in e6_declaration" in capsys.readouterr().out
    other_calls = _install(runner, monkeypatch, items=ITEMS[:1])
    code, rec = _run(runner, tmp_path, "third", "--repeat-of", first["record_id"])
    assert code == 2 and rec is None and "items" in capsys.readouterr().out
    assert sum(calls.values()) == before and sum(other_calls.values()) == 0, "a refused repetition makes no model call"


def test_a_resume_under_another_declaration_is_refused(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    # Codex finding 4: the units already checkpointed ran under the declaration they name
    _install(runner, monkeypatch, stop_once=("vector_rag", "gold:cls-1"))
    code, stopped = _run(runner, tmp_path, "first")
    assert code == 3 and stopped["outcome"]["status"] == "partial"
    line = json.loads((tmp_path / "results" / "first.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["e6_declaration_sha256"] == declaration_sha256()
    other = tmp_path / "e6_declaration.json"
    data = json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))
    data["primary_family"]["interval"]["seed"] = 7
    other.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    code, _ = _run(runner, tmp_path, "first", "--declaration", str(other))
    assert code == 2 and "another E6 declaration" in capsys.readouterr().out
    code, resumed = _run(runner, tmp_path, "first")
    assert code == 0 and resumed["relations"]["resumes_record_id"] == stopped["record_id"]


def test_a_declaration_outside_its_shape_refuses_the_run(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    _install(runner, monkeypatch)
    bad = tmp_path / "e6_declaration.json"
    bad.write_text("{}", encoding="utf-8")
    code, rec = _run(runner, tmp_path, "first", "--declaration", str(bad))
    assert code == 2 and rec is None and "e6 declaration" in capsys.readouterr().out

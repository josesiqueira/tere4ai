"""scripts/analyse_ablations.py on mock runs (spec G D-G84, B150).

The runs are made by scripts/run_ablations.py itself with the model clients
and the strategies replaced by doubles (no model, no network), so the
analysis reads what a run keeps: its evaluation record and its checkpoint and
summary copies. Every expected figure is counted by hand in the comments.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
from collections import Counter
from pathlib import Path

import pytest
from tests.unit.test_run_ablations_record import runner  # noqa: F401

from tere4ai.eval import harness
from tere4ai.eval.ablation_declaration import DECLARATION_PATH, load_declaration, pilot_draw
from tere4ai.eval.evaluation_record import EvaluationRecordStore
from tere4ai.eval.strategies import STRATEGY_NAMES as SIX
from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable

ROOT = Path(__file__).resolve().parents[2]
ART = "eu-ai-act:article-"
R9, R10, R14, R99 = ART + "9", ART + "10", ART + "14", ART + "99"
LEVEL = {"gold:cls-1": "high_risk", "gold:cls-2": "minimal_risk", "gold:cls-3": "limited_risk",
         "bench:scenario:0": "high_risk"}
KEY = {"gold:ret-1": "eu-ai-act:annex-iii:point-4", "gold:qa-1": R9, "gold:qa-2": R14,
       "gold:qa-3": ART + "13", "bench:qa:0": R10}


def _analyser(tmp_path):
    spec = importlib.util.spec_from_file_location("analyse_ablations", ROOT / "scripts" / "analyse_ablations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.RESULTS_DIR = tmp_path / "results"  # never the repository's eval/results
    return mod


def _right(item_id):
    if item_id in LEVEL:
        return {"answer_text": "x", "citations": [], "risk_category": LEVEL[item_id]}
    return {"answer_text": "x", "citations": [KEY.get(item_id, R10)], "risk_category": None}


def _wrong(item_id):
    if item_id in LEVEL:
        return {"answer_text": "x", "citations": [],
                "risk_category": "high_risk" if LEVEL[item_id] == "minimal_risk" else "minimal_risk"}
    return {"answer_text": "x", "citations": [R99], "risk_category": None}


def main_answer(name, item_id, rep):
    """The main group's answers, repetition rep = 0, 1, 2."""
    gated = item_id not in LEVEL  # the runtime judge gates question and retrieval answers only
    if name == "plain_llm":
        if item_id == "gold:cls-2" or item_id == "gold:ret-1":
            return _wrong(item_id)
        if item_id == "gold:cls-3" and rep == 2:
            return _wrong(item_id)
        if item_id == "gold:qa-1":
            return dict(_right(item_id), citations=[R9 + ":paragraph-1"]) if rep == 0 else _wrong(item_id)
        if item_id == "gold:qa-2" and rep == 0:
            raise RuntimeError("generator reply lost")
        return _right(item_id)
    if name == "vector_rag":
        return _wrong(item_id) if item_id == "gold:cls-1" else _right(item_id)
    if name == "graph_no_judge":
        return _wrong(item_id) if item_id in ("gold:qa-1", "gold:qa-2") else _right(item_id)
    if name == "graph_build_judge":
        return _right(item_id)
    if name == "graph_full":
        result = _right(item_id)
        if gated:
            result["judge_verdict"] = "rejected" if (item_id, rep) == ("gold:qa-2", 0) else "accepted"
        return result
    if item_id == "gold:qa-1":  # graph_runtime_judge
        return dict(_wrong(item_id), judge_verdict="rejected")
    result = _right(item_id)
    if gated:
        result["judge_verdict"] = "rejected" if (item_id, rep) == ("gold:qa-2", 1) else "accepted"
    return result


def pilot_answer(name, item_id, rep):
    """The pilot group's answers on 40 development question pairs, rep = 0 to 4."""
    index = int(item_id.rsplit(":", 1)[1])
    right = {"answer_text": "x", "citations": [R10 + ":paragraph-1"], "risk_category": None}
    if name in ("graph_full", "graph_runtime_judge"):
        result = dict(_wrong(item_id) if index in (100, 101) else right)
        result["judge_verdict"] = "rejected" if index in (100, 102) else "accepted"
        return result
    if name == "plain_llm" and index == 100 and rep == 4:
        return _wrong(item_id)
    return right


def _install(runner, monkeypatch, answer):  # noqa: F811
    """The strategy doubles; returns the set of (condition, case, repetition) whose
    call stops the run once, as an overloaded backend does (a resume follows)."""
    monkeypatch.setattr(runner.strategies, "STRATEGY_NAMES", SIX)
    seen: Counter = Counter()
    stops: set = set()

    def fake_build(name, **kw):
        def strategy(item):
            rep = seen[(name, item["id"])]
            if (name, item["id"], rep) in stops:
                stops.discard((name, item["id"], rep))
                raise InferenceBackendUnavailable(6, "HTTP 529")
            kw["generator"].complete()
            seen[(name, item["id"])] += 1
            return answer(name, item["id"], rep)
        judged = name in ("graph_full", "graph_runtime_judge")
        strategy.models = {"generator": "g", **({"judge": "j", "judge_prompt_version": "v1"} if judged else {})}
        return strategy

    monkeypatch.setattr(runner.strategies, "build_strategy", fake_build)
    return stops


def _files(tmp_path):
    features = {"description": "mock", "flags": {}}
    items = [{"id": i, "kind": "classification", "system_features": features,
              "gold": {"risk_category": LEVEL[i]}, "gold_citations": []} for i in ("gold:cls-1", "gold:cls-2", "gold:cls-3")]
    items += [{"id": "gold:ret-1", "kind": "retrieval", "question": "q", "gold": {}, "gold_citations": [KEY["gold:ret-1"]]}]
    items += [{"id": i, "kind": "qa", "question": "q", "gold": {}, "gold_citations": [KEY[i]]}
              for i in ("gold:qa-1", "gold:qa-2")]
    items += [{"id": "gold:qa-3", "kind": "qa", "question": "q", "gold": {}, "gold_citations": [KEY["gold:qa-3"]],
               "contested": True}]
    gold = tmp_path / "gold_mock.json"
    gold.write_text(json.dumps({"items": items}), encoding="utf-8")
    bench = tmp_path / "bench_mock.json"
    bench.write_text(json.dumps({
        "scenarios": [{"role": "Provider", "intended_use": "u", "system_type": "t", "input_data": "d", "domain": "x",
                       "risk_level": "high-risk", "related_articles": [6], "obligations": [], "benchmark_index": 0}],
        "qa_pairs": [{"question": "q", "answer": "a", "relevant_article": 10, "benchmark_index": 0}]}), encoding="utf-8")
    sha = hashlib.sha256(harness.BENCHMARK_SAMPLE_PATH.read_bytes()).hexdigest()
    dev = tmp_path / "development_mock.json"
    dev.write_text(json.dumps({
        "development_set": {"rule": "mock", "sample_file": "benchmark_sample.json", "sample_sha256": sha,
                            "draw": pilot_draw(load_declaration()), "scenarios": 0, "qa_pairs": 40,
                            "benchmark_indexes": {"scenarios": [], "qa_pairs": list(range(100, 140))}},
        "scenarios": [],
        "qa_pairs": [{"question": "q", "answer": "a", "relevant_article": 10, "benchmark_index": i}
                     for i in range(100, 140)]}), encoding="utf-8")
    # the elicitor's prompt record of each facts file (scripts/elicit_benchmark_features.py): one version and
    # template, its rendered hash and graph_version differing between the item sets
    feats = tmp_path / "development_features_mock.json"
    feats.write_text(json.dumps({"features_by_item": {}, "prompt": {
        "version": "v7", "template_sha256": "t" * 64, "rendered_sha256": "d" * 64, "graph_version": "dev"}}),
        encoding="utf-8")
    main_feats = tmp_path / "benchmark_features_mock.json"
    main_feats.write_text(json.dumps({"features_by_item": {}, "prompt": {
        "version": "v7", "template_sha256": "t" * 64, "rendered_sha256": "m" * 64, "graph_version": "main"}}),
        encoding="utf-8")
    return gold, bench, dev, feats, main_feats


def _group(runner, tmp_path, tag, count, extra):  # noqa: F811
    ids = []
    for n in range(count):
        argv = ["--dump-dir", str(tmp_path), "--checkpoint", str(tmp_path / "results" / f"{tag}{n}.jsonl"),
                "--summary", str(tmp_path / "results" / f"{tag}{n}.json"), *extra]
        if ids:
            argv += ["--repeat-of", ids[0]]
        code = runner.main(argv)
        if code == 3:  # stopped as an overloaded backend stops it: resumed with the same command
            code = runner.main(argv)
        assert code == 0
        records = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records()
                   if (r.get("config") or {}).get("checkpoint_file") == f"{tag}{n}.jsonl"]
        resumed = {r["relations"]["resumes_record_id"] for r in records}
        # the last attempt: not resumed by another, and the newest (an attempt stopped before its
        # first unit is rerun as a new record that names none)
        rec = max((r for r in records if r["record_id"] not in resumed), key=lambda r: (r["started_at"], r["record_id"]))
        ids.append(rec["record_id"])
    return ids


def _newest_analysis(tmp_path):
    rows = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if r.get("kind") == "analysis"]
    return max(rows, key=lambda r: (r["started_at"], r["record_id"]))


def _text(tmp_path, record):
    copy = next(o for o in record["outputs"] if o["output_kind"] == "analysis_text")["copy"]
    return (tmp_path / "evaluation_records" / copy).read_text(encoding="utf-8")


def _report(tmp_path, record):
    copy = next(o for o in record["outputs"] if o["output_kind"] == "analysis")["copy"]
    return json.loads((tmp_path / "evaluation_records" / copy).read_text(encoding="utf-8"))


@pytest.fixture
def made(runner, tmp_path, monkeypatch):  # noqa: F811
    gold, bench, dev, feats, main_feats = _files(tmp_path)
    monkeypatch.setattr(harness, "GOLD_SEED_PATH", gold)
    _install(runner, monkeypatch, pilot_answer)
    pilot_runs = _group(runner, tmp_path, "pilot", 5, ["--development-set", "--benchmark", str(dev),
                                                       "--features", str(feats)])
    an = _analyser(tmp_path)
    assert an.main(["--dump-dir", str(tmp_path), "--group", pilot_runs[0], "--pilot", "--benchmark", str(dev)]) == 0
    pilot = _newest_analysis(tmp_path)
    stops = _install(runner, monkeypatch, main_answer)
    # Codex finding 3 and second-seat I1: the first repetition stops on its very first call, before
    # any unit is checkpointed, and is rerun as a new record ([h, r1e, r1, r2]); the second stops
    # on vector_rag's first case and is resumed; each is one repetition
    stops.add(("plain_llm", "gold:cls-1", 1))
    stops.add(("vector_rag", "gold:cls-1", 2))
    runner.load_items = lambda b, f: harness.load_gold_items(gold) + harness.load_benchmark_items(bench)
    main_runs = _group(runner, tmp_path, "main", 3, ["--benchmark", str(bench), "--features", str(main_feats)])
    base = ["--dump-dir", str(tmp_path), "--gold", str(gold), "--benchmark", str(bench)]
    return {"an": an, "pilot": pilot, "pilot_runs": pilot_runs, "main_runs": main_runs, "base": base,
            "dev": str(dev), "group": base + ["--group", main_runs[0], "--pilot-analysis", pilot["record_id"]]}


def test_the_pilot_run_fixes_the_count(made, tmp_path):
    pilot = made["pilot"]
    assert pilot["config"]["mode"] == "pilot" and pilot["config"]["pilot_count"] == 3
    assert pilot["relations"]["compares"] == made["pilot_runs"]
    report = _report(tmp_path, pilot)
    figures = report["pilot"]["figures"]
    assert figures["accuracy:plain_llm"]["by_repetition"] == pytest.approx([1, 1, 1, 1, 0.975])
    assert figures["accuracy:plain_llm"]["required"] == 3
    # conditions 5 and 6: 38 of 40 right in every repetition; the shares constant
    assert figures["accuracy:graph_full"]["standard_deviation"] == 0.0
    assert figures["wrong_answers_caught:graph_full"]["by_repetition"] == [0.5] * 5
    assert (report["pilot"]["count"], report["pilot"]["cap_binds"]) == (3, False)


def test_the_three_declared_contrasts_on_hand_counted_outcomes(made, tmp_path):
    assert made["an"].main(made["group"]) == 0
    report = _report(tmp_path, _newest_analysis(tmp_path))
    family = report["primary_family"]
    assert family["contested_left_out"] == ["gold:qa-3"]
    assert family["threshold"] == pytest.approx(0.05 / 3)
    c1, c2, c3 = family["contrasts"]
    # graph_full right on all six; plain_llm's majorities: cls-1 R, cls-2 W, cls-3 R (R, R, W),
    # ret-1 W, qa-1 W (R, W, W), qa-2 R (failed call, R, R): 3 right only in graph_full, 0 the other way
    assert (c1["cases"], c1["condition_only_right"], c1["against_only_right"]) == (6, 3, 0)
    assert c1["difference"] == pytest.approx(0.5) and c1["mcnemar_exact_p"] == 0.25
    assert c1["no_difference_rejected"] is False and 0 <= c1["interval"][0] <= 0.5 <= c1["interval"][1] <= 1
    # vector_rag wrong only on cls-1: one case
    assert (c2["condition_only_right"], c2["against_only_right"], c2["mcnemar_exact_p"]) == (1, 0, 1.0)
    assert c2["difference"] == pytest.approx(1 / 6)
    # graph_build_judge against graph_no_judge on ret-1, qa-1, qa-2: no_judge wrong on the two questions
    assert (c3["cases"], c3["condition_only_right"], c3["against_only_right"]) == (3, 2, 0)
    assert c3["difference"] == pytest.approx(2 / 3) and c3["mcnemar_exact_p"] == 0.5
    assert report["declaration"]["declared_before_runs"] is True


def test_a_labelled_interval_is_shown_with_its_label(tmp_path):
    # Task 5 review, Important: the Markdown keeps the conditional label beside the interval and shows the
    # none-given label alone (B150 Q11)
    show = _analyser(tmp_path)._interval
    conditional = {"interval": [0.1, 0.2], "left_out": 3, "draws": 1000,
                   "label": "conditional: 3 of 1000 resamples held no wrong answer and were left out (B150 Q11)"}
    assert show(conditional) == ("[0.100, 0.200]; conditional: 3 of 1000 resamples held no wrong answer and were "
                                 "left out (B150 Q11)")
    none_given = {"interval": None, "left_out": 26, "draws": 1000,
                  "label": "none given: 26 of 1000 resamples held no wrong answer, more than 25 (B150 Q11)"}
    assert show(none_given) == "none given: 26 of 1000 resamples held no wrong answer, more than 25 (B150 Q11)"
    assert show({"interval": [0.1, 0.2], "left_out": 0, "draws": 1000, "label": None}) == "[0.100, 0.200]"
    assert show(None) == "n/a"


def test_the_runtime_judge_is_read_on_the_answers_it_gates(made, tmp_path):
    assert made["an"].main(made["group"]) == 0
    judge = _report(tmp_path, _newest_analysis(tmp_path))["runtime_judge"]
    full = judge["graph_full"]["shares"]
    # 9 answers (ret-1, qa-1, qa-2 three times), all right; qa-2 blocked in repetition 1
    assert full["wrong_answers_caught"] == {"numerator": 0, "denominator": 0, "rate": None}
    assert full["right_answers_blocked"]["numerator"] == 1 and full["right_answers_blocked"]["denominator"] == 9
    assert (full["accuracy_among_delivered"]["numerator"], full["accuracy_among_delivered"]["denominator"]) == (8, 8)
    assert (full["share_delivered"]["numerator"], full["share_delivered"]["denominator"]) == (8, 9)
    assert judge["graph_full"]["intervals"]["wrong_answers_caught"] is None
    six = judge["graph_runtime_judge"]["shares"]
    # qa-1 wrong and caught three times; qa-2 right, blocked once; 5 delivered, all right
    assert (six["wrong_answers_caught"]["numerator"], six["wrong_answers_caught"]["denominator"]) == (3, 3)
    assert (six["right_answers_blocked"]["numerator"], six["right_answers_blocked"]["denominator"]) == (1, 6)
    assert (six["accuracy_among_delivered"]["numerator"], six["accuracy_among_delivered"]["denominator"]) == (5, 5)
    assert (six["share_delivered"]["numerator"], six["share_delivered"]["denominator"]) == (5, 9)
    # a resample without qa-1, about (2/3) cubed of the 1000, holds no wrong answer: far more than the
    # declaration's 25 are left out, so no interval is given (B150 Q11)
    caught = judge["graph_runtime_judge"]["intervals"]["wrong_answers_caught"]
    assert caught["interval"] is None and caught["left_out"] > 25 and caught["draws"] == 1000
    assert caught["label"] == (f"none given: {caught['left_out']} of 1000 resamples held no wrong answer, "
                               "more than 25 (B150 Q11)")
    # every resample holds an answer: the interval with no label
    delivered = judge["graph_runtime_judge"]["intervals"]["share_delivered"]
    assert delivered["left_out"] == 0 and delivered["label"] is None
    assert 0 <= delivered["interval"][0] <= 5 / 9 <= delivered["interval"][1] <= 1
    text = _text(tmp_path, _newest_analysis(tmp_path))
    section = text.split("### graph_runtime_judge")[1].split("### graph_full")[0]
    rows = {line.split(" | ")[0]: line for line in section.splitlines() if line.startswith("| ")}
    assert rows["| wrong_answers_caught"].endswith(f"| {caught['label']} |")
    assert rows["| share_delivered"].endswith(
        f"| [{delivered['interval'][0]:.3f}, {delivered['interval'][1]:.3f}] |")
    assert "conditional:" not in text


def test_per_call_accuracy_failed_calls_and_what_is_not_computed(made, tmp_path):
    assert made["an"].main(made["group"]) == 0
    report = _report(tmp_path, _newest_analysis(tmp_path))
    plain = report["per_call_accuracy"]["hand_made"]["plain_llm"]
    # repetitions: 3 of 6, 3 of 6, 2 of 6; 8 right of 18 calls
    assert (plain["calls"], plain["right"]) == (18, 8)
    assert plain["by_repetition"] == pytest.approx([0.5, 0.5, 1 / 3])
    no_judge = report["per_call_accuracy"]["hand_made"]["graph_no_judge"]
    # Codex finding 1: its three classification cases ran once, one call each; the question and
    # retrieval cases three times: 3 + 9 = 12 calls, 3 + 3 = 6 right; each repetition's accuracy over
    # the three cases run in every repetition is 1 of 3 (B150 Q13, "Cases run every time (Recommended)")
    assert (no_judge["calls"], no_judge["right"], no_judge["standard_deviation"]) == (12, 6, 0.0)
    assert no_judge["by_repetition"] == pytest.approx([1 / 3] * 3)
    assert report["per_call_accuracy"]["benchmark"]["plain_llm"]["share"] == 1.0
    assert report["failed_calls"] == [{"run": made["main_runs"][0], "condition": "plain_llm",
                                       "case": "gold:qa-2", "error": "RuntimeError: generator reply lost"}]
    # B161: Q12 and Q13 are decided, so no note is provisional, and Q8 is answered, so no line waits on it
    assert not any("provisional" in note for note in report["notes"])
    record = _newest_analysis(tmp_path)
    assert not any("provisional" in note for note in record["notes"])
    text_copy = next(o for o in record["outputs"] if o["output_kind"] == "analysis_text")["copy"]
    text = (tmp_path / "evaluation_records" / text_copy).read_text(encoding="utf-8")
    assert not any("B150 Q8" in line and "not computed" in line for line in text.splitlines())
    assert "provisional" not in text
    assert "B150 Q9" in report["four_measures"]["over_repetitions"]
    assert sorted(report["four_measures"]["by_run"]) == sorted(made["main_runs"])


def test_the_record_names_the_runs_it_read_and_the_text_report(made, tmp_path):
    assert made["an"].main(made["group"]) == 0
    rec = _newest_analysis(tmp_path)
    assert (rec["kind"], rec["step"], rec["command"]) == ("analysis", "E6", "analyse_ablations")
    assert rec["relations"]["compares"] == made["main_runs"]
    assert rec["config"]["mode"] == "main" and rec["config"]["pilot_record_id"] == made["pilot"]["record_id"]
    assert sorted(i["input_kind"] for i in rec["inputs"]) == sorted(
        ["e6_declaration", "gold_seed", "benchmark", "run_checkpoint", "run_checkpoint", "run_checkpoint"])
    assert {o["output_kind"] for o in rec["outputs"]} == {"analysis", "analysis_text"}
    stopped = [r["record_id"] for r in EvaluationRecordStore(tmp_path, create=False).list_records()
               if (r.get("config") or {}).get("checkpoint_file") in ("main1.jsonl", "main2.jsonl")
               and r["record_id"] not in made["main_runs"]]
    # r1e (no unit, left out) and r2's stopped attempt (read through its resume), each named once
    assert len(stopped) == 2 and all(any(rid in note for note in rec["notes"]) for rid in stopped)
    text_copy = next(o for o in rec["outputs"] if o["output_kind"] == "analysis_text")["copy"]
    text = (tmp_path / "evaluation_records" / text_copy).read_text(encoding="utf-8")
    for words in ("graph_full_minus_plain_llm", "0.250000", "not computed: awaiting Jose's decision", "gold:qa-3"):
        assert words in text


def test_a_main_analysis_without_the_pilot_is_refused(made, capsys):
    assert made["an"].main(made["base"] + ["--group", made["main_runs"][0]]) == 2
    assert "--pilot-analysis" in capsys.readouterr().out


def test_a_pilot_analysis_made_after_the_main_run_started_is_refused(made, tmp_path, capsys):
    # Codex finding 5: the count must be fixed before the main run, not after it
    an = made["an"]
    assert an.main(["--dump-dir", str(tmp_path), "--group", made["pilot_runs"][0], "--pilot",
                    "--benchmark", made["dev"]]) == 0
    late = _newest_analysis(tmp_path)["record_id"]
    capsys.readouterr()
    assert an.main(made["base"] + ["--group", made["main_runs"][0], "--pilot-analysis", late]) == 2
    assert "did not fix the count before the main run started" in capsys.readouterr().out


def test_a_listed_benchmark_contrast_gets_its_difference_and_interval_and_no_test(made, tmp_path):
    # B150 Q8, "The same three, no test (Recommended)": the repository's declaration lists the primary
    # family's three on the benchmark. graph_full, plain_llm and vector_rag are right on the benchmark's
    # scenario and question pair in every repetition (2 cases each), graph_build_judge and graph_no_judge
    # on its question pair (1 case, retrieval and question kinds only): no case is discordant
    assert made["an"].main(made["group"]) == 0
    secondary = _report(tmp_path, _newest_analysis(tmp_path))["secondary"]
    assert [c["id"] for c in secondary["contrasts"]] == [
        "graph_full_minus_plain_llm", "graph_full_minus_vector_rag", "graph_build_judge_minus_graph_no_judge"]
    assert [(c["cases"], c["difference"], c["interval"]) for c in secondary["contrasts"]] == [
        (2, 0.0, [0.0, 0.0]), (2, 0.0, [0.0, 0.0]), (1, 0.0, [0.0, 0.0])]
    for c in secondary["contrasts"]:
        assert c["test"] == made["an"].SECONDARY_TEST and "mcnemar_exact_p" not in c
    assert "B150 Q8" in secondary["status"] and "awaiting" not in secondary["status"]


def test_a_group_whose_size_the_pilot_did_not_fix_is_refused(made, runner, tmp_path, capsys):  # noqa: F811
    (lone,) = _group(runner, tmp_path, "lone", 1, ["--benchmark", made["base"][-1]])
    capsys.readouterr()
    assert made["an"].main(made["base"] + ["--group", lone, "--pilot-analysis", made["pilot"]["record_id"]]) == 2
    assert "the pilot run fixed 3" in capsys.readouterr().out


def test_a_repetition_under_another_declaration_is_refused(made, tmp_path, capsys):
    path = tmp_path / "evaluation_records" / f"{made['main_runs'][1]}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    for ref in record["inputs"]:
        if ref["input_kind"] == "e6_declaration":
            ref["sha256"] = "0" * 64
    path.write_text(json.dumps(record), encoding="utf-8")
    assert made["an"].main(made["group"]) == 2
    assert "e6_declaration" in capsys.readouterr().out


def test_a_drifted_checkpoint_copy_is_refused(made, tmp_path, capsys):
    copy = tmp_path / "evaluation_records" / made["main_runs"][2] / "checkpoint.jsonl"
    copy.write_text(copy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert made["an"].main(made["group"]) == 2
    assert "differs from the digest" in capsys.readouterr().out


def test_a_pilot_group_on_a_payload_drawn_otherwise_is_refused(made, tmp_path, capsys):
    # B161 (B150 Q10): the pilot run's payload is the declaration's draw; one drawn with another seed is
    # refused by the analysis as by the runner. The runs' records are made to name the rewritten file's
    # digest, so that the draw, not the digest, is what the analysis meets.
    dev = Path(made["dev"])
    payload = json.loads(dev.read_text(encoding="utf-8"))
    payload["development_set"]["draw"]["seed"] = 1
    dev.write_text(json.dumps(payload), encoding="utf-8")
    sha = hashlib.sha256(dev.read_bytes()).hexdigest()

    def same_digest(record):
        for ref in record["inputs"]:
            if ref["input_kind"] == "benchmark":
                ref["sha256"] = sha
    for record_id in made["pilot_runs"]:
        _edit(tmp_path, record_id, same_digest)
    capsys.readouterr()
    assert made["an"].main(["--dump-dir", str(tmp_path), "--group", made["pilot_runs"][0], "--pilot",
                            "--benchmark", str(dev)]) == 2
    assert "not the declaration's pilot sample" in capsys.readouterr().out


def test_a_declaration_other_than_the_runs_is_shown_as_such(made, tmp_path):
    other = tmp_path / "e6_declaration.json"
    data = json.loads(DECLARATION_PATH.read_text(encoding="utf-8"))
    data["primary_family"]["interval"]["seed"] = 7
    other.write_text(json.dumps(data), encoding="utf-8")
    assert made["an"].main(made["group"] + ["--declaration", str(other)]) == 0
    report = _report(tmp_path, _newest_analysis(tmp_path))
    assert report["declaration"]["declared_before_runs"] is False
    assert any("post hoc" in note for note in report["notes"])


def test_a_failed_pilot_call_is_listed_and_left_out_of_the_runtime_judge_shares(runner, tmp_path, monkeypatch):  # noqa: F811
    # carried from the Task 6 review: gate_shares_by_repetition leaves out the failed calls gate_answers
    # returns, so the pilot report lists them; graph_runtime_judge's call on case 139 fails in repetition 4
    gold, _, dev, feats, _ = _files(tmp_path)
    monkeypatch.setattr(harness, "GOLD_SEED_PATH", gold)

    def answer(name, item_id, rep):
        if (name, item_id, rep) == ("graph_runtime_judge", "bench:qa:139", 3):
            raise RuntimeError("judge reply lost")
        return pilot_answer(name, item_id, rep)

    _install(runner, monkeypatch, answer)
    runs = _group(runner, tmp_path, "pilot", 5, ["--development-set", "--benchmark", str(dev), "--features", str(feats)])
    assert _analyser(tmp_path).main(["--dump-dir", str(tmp_path), "--group", runs[0], "--pilot",
                                     "--benchmark", str(dev)]) == 0
    report = _report(tmp_path, _newest_analysis(tmp_path))
    assert report["failed_calls"] == [{"run": runs[3], "condition": "graph_runtime_judge", "case": "bench:qa:139",
                                       "error": "RuntimeError: judge reply lost"}]
    figures = report["pilot"]["figures"]
    # 38 right answers in a repetition, one blocked (case 102); in repetition 4 the failed call leaves 37
    assert figures["right_answers_blocked:graph_runtime_judge"]["by_repetition"] == pytest.approx(
        [1 / 38] * 3 + [1 / 37, 1 / 38])
    # 40 answers, 2 rejected (cases 100 and 102); in repetition 4, 39 answers and 37 delivered
    assert figures["share_delivered:graph_runtime_judge"]["by_repetition"] == pytest.approx(
        [38 / 40] * 3 + [37 / 39, 38 / 40])
    # in the accuracy the failed call counts wrong: 37 of 40 in repetition 4
    assert figures["accuracy:graph_runtime_judge"]["by_repetition"] == pytest.approx([0.95] * 3 + [0.925, 0.95])
    assert report["pilot"]["count"] == 3


def test_a_pilot_figure_without_a_value_in_a_repetition_is_left_out_of_n_and_named(runner, tmp_path,  # noqa: F811
                                                                                     monkeypatch):
    # B150 Q11: in repetition 2 graph_runtime_judge answers cases 100 and 101 right, so it gives no wrong
    # answer to catch; that figure is left out of N and named, and N is read on the others: its accuracy
    # 0.95, 1, 0.95, 0.95, 0.95 has standard deviation 0.02236, (1.96 * 0.02236 / 0.02) squared = 4.8, so 5
    gold, _, dev, feats, _ = _files(tmp_path)
    monkeypatch.setattr(harness, "GOLD_SEED_PATH", gold)

    def answer(name, item_id, rep):
        result = pilot_answer(name, item_id, rep)
        if name == "graph_runtime_judge" and rep == 1 and item_id.endswith((":100", ":101")):
            result = {"answer_text": "x", "citations": [R10 + ":paragraph-1"], "risk_category": None,
                      "judge_verdict": result["judge_verdict"]}
        return result

    _install(runner, monkeypatch, answer)
    runs = _group(runner, tmp_path, "pilot", 5, ["--development-set", "--benchmark", str(dev), "--features", str(feats)])
    assert _analyser(tmp_path).main(["--dump-dir", str(tmp_path), "--group", runs[0], "--pilot",
                                     "--benchmark", str(dev)]) == 0
    record = _newest_analysis(tmp_path)
    pilot = _report(tmp_path, record)["pilot"]
    name = "wrong_answers_caught:graph_runtime_judge"
    assert pilot["figures"][name]["by_repetition"] == [0.5, None, 0.5, 0.5, 0.5]
    assert pilot["figures"][name]["left_out"] == "no value in repetition(s) 2"
    assert pilot["left_out_of_n"] == [name] and pilot["count"] == 5 and pilot["not_computed"] is None
    assert record["config"]["pilot_count"] == 5
    text = _text(tmp_path, record)
    assert f"| {name} | 0.500, n/a, 0.500, 0.500, 0.500 | n/a | no value in repetition(s) 2 |" in text
    assert f"Left out of N (B150 Q11): {name} (no value in repetition(s) 2)" in text


def test_a_first_run_stopped_and_never_resumed_is_refused(made, runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    # carried from the Task 3 review: the head is the first run's last attempt. The made group's head
    # ended partial with every unit run (one failed call, listed by the analysis above), so it is read;
    # a head that stopped and was never resumed kept no checkpoint and is refused, never analysed
    # without its run-once cases
    store = EvaluationRecordStore(tmp_path, create=False)
    assert store.read(made["main_runs"][0])["outcome"]["status"] == "partial"
    stops = _install(runner, monkeypatch, main_answer)
    stops.add(("vector_rag", "gold:cls-1", 0))
    paths = [["--checkpoint", str(tmp_path / "results" / f"cut{n}.jsonl"),
              "--summary", str(tmp_path / "results" / f"cut{n}.json")] for n in range(3)]
    base = ["--dump-dir", str(tmp_path), "--benchmark", made["base"][-1]]
    assert runner.main(base + paths[0]) == 3
    (cut,) = [r for r in store.list_records() if (r.get("config") or {}).get("checkpoint_file") == "cut0.jsonl"]
    assert cut["outcome"]["status"] == "partial"
    for n in (1, 2):
        assert runner.main(base + paths[n] + ["--repeat-of", cut["record_id"]]) == 0
    capsys.readouterr()
    assert made["an"].main(made["base"] + ["--group", cut["record_id"],
                                           "--pilot-analysis", made["pilot"]["record_id"]]) == 2
    out = capsys.readouterr().out
    assert f"the group's first run {cut['record_id']} ended partial and kept no checkpoint" in out


def test_the_main_record_names_the_count_it_read_and_the_interpreter(made, tmp_path):
    # final review: the main record's config shows the N it read (Task 7 minor) and the interpreter whose
    # random module drew the bootstrap (second seat P3, ruling R3)
    assert made["an"].main(made["group"]) == 0
    config = _newest_analysis(tmp_path)["config"]
    assert (config["pilot_count"], config["pilot_count_reason"]) == (3, None)
    assert config["python_version"] == platform.python_version()
    assert made["pilot"]["config"]["python_version"] == platform.python_version()


def test_a_failure_after_the_record_opened_ends_it_failed(made, tmp_path, capsys):
    # second seat P2: --out-dir naming an existing file fails after store.begin; the record never stays running
    blocker = tmp_path / "a_file_not_a_directory"
    blocker.write_text("x", encoding="utf-8")
    assert made["an"].main(made["group"] + ["--out-dir", str(blocker)]) == 2
    rec = _newest_analysis(tmp_path)
    assert rec["outcome"]["status"] == "failed" and rec["ended_at"] is not None
    assert rec["outcome"]["error"].startswith("FileExistsError")
    assert f"evaluation record {rec['record_id']} ended failed" in capsys.readouterr().out


def _edit(tmp_path, record_id, change):
    path = tmp_path / "evaluation_records" / f"{record_id}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    change(record)
    path.write_text(json.dumps(record), encoding="utf-8")


@pytest.mark.parametrize("change, words", [
    (lambda r: r["models"].update(generator_model="another"), "the pilot run ran other models than the main run"),
    (lambda r: r["prompt_versions"]["graph_full"].update(judge_prompt_version="v2"),
     "the pilot run ran other prompt versions than the main run"),
])
def test_a_pilot_run_on_other_instruments_is_refused(made, tmp_path, capsys, change, words):
    # the Task 7 ruling: the count holds for the instruments it was fixed on (a failure mechanic)
    _edit(tmp_path, made["pilot_runs"][2], change)
    assert made["an"].main(made["group"]) == 2
    assert words in capsys.readouterr().out


def test_the_elicitors_version_and_template_are_compared_not_its_rendered_hash(made, tmp_path, capsys):
    # coordinator's re-review: conditions 1 and 2 read the elicited facts on every classification case in
    # every repetition, so the pilot's N depends on the elicitor's prompt; the made runs share its version
    # and template and differ in rendered_sha256 and graph_version (each item set elicited apart): accepted
    store = EvaluationRecordStore(tmp_path, create=False)
    pilot_entry = store.read(made["pilot_runs"][0])["prompt_versions"]["elicit_features"]
    main_entry = store.read(made["main_runs"][0])["prompt_versions"]["elicit_features"]
    assert (pilot_entry["version"], pilot_entry["template_sha256"]) == (main_entry["version"], main_entry["template_sha256"])
    assert pilot_entry["rendered_sha256"] != main_entry["rendered_sha256"]
    assert pilot_entry["graph_version"] != main_entry["graph_version"]
    assert made["an"].main(made["group"]) == 0
    for key, value in (("version", "v6"), ("template_sha256", "0" * 64)):
        _edit(tmp_path, made["pilot_runs"][1], lambda r, k=key, v=value: r["prompt_versions"]["elicit_features"].update({k: v}))
        capsys.readouterr()
        assert made["an"].main(made["group"]) == 2
        assert "another elicitor prompt" in capsys.readouterr().out
        _edit(tmp_path, made["pilot_runs"][1], lambda r, k=key, e=pilot_entry: r["prompt_versions"]["elicit_features"].update({k: e[k]}))

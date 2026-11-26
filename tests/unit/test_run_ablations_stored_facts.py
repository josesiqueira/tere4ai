"""run_ablations refuses stored facts the features schema does not accept, before any model could be called (B184, R16).

A benchmark scenario classified from facts elicited with an earlier prompt can
name a fact the schema refuses since B184 (DEC-32); classify_ai_system then
answers rejected_as_unsupported with no risk_category, and the summary would
count a refused input as a wrong answer. The runner checks every item it will
classify from stored facts against the schema first and stops with exit code
2, naming the count, the first items, the facts outside the schema and what to
do; a failure of another kind is named by its first schema error, without the
advice to elicit again. The check runs on the main run and the pilot run
(--development-set). Mock items only: no model, no eval/results file.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json

from tests.unit.test_development_set import _argv as _dev_argv
from tests.unit.test_development_set import _dev_file, _feats, mock_pilot_indexes  # noqa: F401
from tests.unit.test_run_ablations_record import _argv, runner  # noqa: F401

from tere4ai.mcp_server.classify import FEATURES_SCHEMA_PATH

SCHEMA = json.loads(FEATURES_SCHEMA_PATH.read_text(encoding="utf-8"))

VALID = {"id": "gold:cls-x", "kind": "classification",
         "system_features": {"description": "A movie recommender.", "flags": {"social_scoring": False}}}
REMOVED = {"id": "bench:scenario:76", "kind": "classification",
           "system_features": {"description": "Police risk tool.", "flags": {"law_enforcement_use": True}}}
FREE_TEXT = {"id": "bench:scenario:9", "kind": "classification", "system_features": None, "system_text": "t"}
QUESTION = {"id": "gold:qa-01", "kind": "qa", "question": "q"}
NOT_BOOLEAN = {"id": "bench:scenario:12", "kind": "classification",
               "system_features": {"description": "A movie recommender.", "flags": {"social_scoring": "yes"}}}
ADVICE = ("these features were elicited with an earlier prompt; elicit them again with the prompt of record, "
          "or run the harness at tag v2.0.0-beta.1")


def test_items_whose_stored_facts_fit_the_schema_pass(runner):  # noqa: F811
    assert runner.stored_facts_refusal([VALID, FREE_TEXT, QUESTION], SCHEMA) is None


def test_an_item_with_a_fact_outside_the_schema_is_refused_with_what_to_do(runner):  # noqa: F811
    message = runner.stored_facts_refusal([VALID, REMOVED, FREE_TEXT], SCHEMA)
    assert message is not None
    assert "1 item(s)" in message
    assert "bench:scenario:76" in message and "gold:cls-x" not in message
    assert "law_enforcement_use" in message
    assert ADVICE in message


def test_the_message_names_the_first_items_and_every_fact_outside_the_schema(runner):  # noqa: F811
    items = [{"id": f"bench:scenario:{n}", "kind": "classification",
              "system_features": {"description": "d", "flags": {
                  "employment_decisions" if n % 2 else "essential_services_access": False}}}
             for n in range(8)]
    message = runner.stored_facts_refusal(items, SCHEMA)
    assert "8 item(s)" in message
    assert "bench:scenario:0" in message and "bench:scenario:4" in message
    assert "bench:scenario:7" not in message  # only the first five are named
    assert "employment_decisions" in message and "essential_services_access" in message


def test_another_schema_failure_says_what_failed_without_the_advice(runner):  # noqa: F811
    # only facts outside the schema come from an earlier prompt; a value of the wrong type does not
    message = runner.stored_facts_refusal([VALID, NOT_BOOLEAN], SCHEMA)
    assert message is not None
    assert "1 item(s)" in message and "bench:scenario:12" in message
    assert "flags.social_scoring: 'yes' is not of type 'boolean'" in message
    assert ADVICE not in message
    assert "facts not in the schema" not in message


def test_both_kinds_of_failure_give_the_advice_and_the_other_error(runner):  # noqa: F811
    message = runner.stored_facts_refusal([REMOVED, NOT_BOOLEAN], SCHEMA)
    assert "2 item(s)" in message
    assert "facts not in the schema: law_enforcement_use" in message and ADVICE in message
    assert "bench:scenario:12" in message and "'yes' is not of type 'boolean'" in message


def test_the_gold_seed_passes_the_check(runner):  # noqa: F811
    assert runner.stored_facts_refusal(runner.harness.load_gold_items(), SCHEMA) is None


def test_main_stops_with_exit_2_before_the_live_gate_and_any_client(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    reached: list[str] = []

    def live_gate():
        reached.append("live gate")

    monkeypatch.setattr(runner, "load_items", lambda b, f: [VALID, REMOVED])
    monkeypatch.setattr(runner.harness, "_require_live_gate", live_gate)
    monkeypatch.setattr(runner, "OpenAIGenerator", lambda *a, **k: reached.append("generator"), raising=False)
    monkeypatch.setattr(runner, "AnthropicJudge", lambda *a, **k: reached.append("judge"), raising=False)
    assert runner.main(_argv(tmp_path)) == 2
    out = capsys.readouterr().out
    assert "bench:scenario:76" in out and "law_enforcement_use" in out
    assert reached == []
    assert not (tmp_path / "evaluation_records").exists()  # no record begun


def test_a_development_run_stops_on_stored_facts_outside_the_schema(runner, tmp_path, capsys,  # noqa: F811
                                                                    mock_pilot_indexes):  # noqa: F811
    # the check runs on the pilot run's path too (--development-set), before any record is begun
    dev = _dev_file(tmp_path)
    feats = _feats(tmp_path, {"bench:scenario:200": {"description": "A police risk tool.",
                                                     "flags": {"law_enforcement_use": True}}})
    code = runner.main(_dev_argv(tmp_path, "pilot", "--development-set", "--benchmark", str(dev),
                                 "--features", str(feats)))
    assert code == 2
    out = capsys.readouterr().out
    assert "bench:scenario:200" in out and "law_enforcement_use" in out and ADVICE in out
    assert not (tmp_path / "evaluation_records").exists()

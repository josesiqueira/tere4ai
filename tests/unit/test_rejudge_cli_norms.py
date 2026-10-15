"""B173 task 2: `python -m tere4ai.rejudge norms` on a published source build of
mock data. Scripted judges only; any generator client built fails the test.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime

import pytest
from tests.unit.rejudge_mock_build import (
    FILE_ORDER,
    GROUPS,
    NEW_NAME,
    NORM_A,
    NORM_B,
    NORM_C,
    NORM_D,
    NORMS_FILE,
    SOURCE_BUILD_ID,
    SOURCE_NAME,
    UNIT_OF,
    USD_PER_JUDGE_CALL,
    ScriptedJudge,
    fake_cfg,
    folder_state,
    make_source_build,
    patch_command,
    prices,
    source_judge_messages,
    unit_key,
)
from tests.unit.test_rejudge_cli_alignments import _copy_with_alignments

import tere4ai.rejudge.__main__ as cli
import tere4ai.rejudge.norms as rejudge_norms
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    USAGE_KEYS,
    InferenceBackendRefused,
    InferenceBackendUnavailable,
)
from tere4ai.extract_norms.pipeline import load_prompt
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import present_record
from tere4ai.rejudge.norms import JUDGE_FIELDS, norms_refusal
from tere4ai.rejudge.source import SourceError, expected_name, name_refusal, read_source

DESCRIPTION = "generator output of 2026-10-14-gpt-fake-high, judged by claude-fake"
ZERO_USAGE = dict.fromkeys(USAGE_KEYS, 0)


@pytest.fixture
def source(tmp_path):
    src = make_source_build(tmp_path)
    before = folder_state(src)
    yield src
    # every test that reads the source folder: its file list and every sha256 unchanged
    assert folder_state(src) == before


def _argv(src, new_dir, name=NEW_NAME, cost_stop="1000", *extra):
    return ["norms", "--source", str(src), "--out-dir", str(new_dir), "--name", name, "--cost-stop", cost_stop, *extra]


def _new(tmp_path, name=NEW_NAME, under="new"):
    return tmp_path / under / name


def _record(new_dir, name=NEW_NAME):
    store = BuildRecordStore(new_dir)
    return store, store.read(store.resolve(name))


def _payload(new_dir, name=NEW_NAME):
    return json.loads((new_dir / f"norms_{name}.json").read_text(encoding="utf-8"))


def _source_norms(src):
    return json.loads((src / NORMS_FILE).read_text(encoding="utf-8"))


def _no_record(new_dir):
    return not (new_dir / "build_records").is_dir() or BuildRecordStore(new_dir).list_records() == []


def test_norms_writes_a_new_build_with_zero_generator_calls(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    policies = patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(source, new_dir)) == 0
    assert policies == [TERMINAL_POLICY]
    assert sha256_of_file(new_dir / "layer1.json") == sha256_of_file(source / "layer1.json")
    assert not (new_dir / f"norms_{NEW_NAME}.checkpoint.jsonl").exists()
    _store, record = _record(new_dir)
    assert record["aliases"] == [NEW_NAME] and record["base_build_id"] == SOURCE_BUILD_ID
    (ex,) = record["executions"]
    assert ex["command"] == "rejudge_norms" and ex["status"] == "done" and ex["error"] is None
    assert ex["covers_steps"] == ["LAYER2_STEP1", "LAYER2_STEP2"] and ex["work_unit"] == "groups"
    assert ex["expected_total"] == 3 and ex["completed_keys"] == GROUPS
    assert ex["usage"]["generator"] == ZERO_USAGE
    assert ex["usage"]["judge"]["calls"] == 4 and ex["usage"]["judge"]["input_tokens"] == 4000
    assert ex["config"]["description"] == DESCRIPTION
    assert ex["config"] == {"prompt_version": "v6", "max_in_flight": 1, "cost_stop_usd": 1000.0,
                            "source_build": SOURCE_NAME, "source_record_id": record_source_id(source),
                            "source_chain_id": "a1b2c3d4e5f6", "judged_by": "claude-fake",
                            "description": DESCRIPTION}
    assert ex["models"] == fake_cfg().as_public_dict()
    assert ex["prompt_sha256"] == {"judge": rejudge_norms.prompt_sha256(load_prompt("judge_norms", "v6"))}
    assert ex["sampling"]["judge"] == "0" and ex["sampling"]["generator"] is None
    kinds = {i["input_kind"]: i for i in ex["inputs"]}
    assert kinds["layer1_dump"] == {"input_kind": "layer1_dump", "file": "layer1.json",
                                    "sha256": sha256_of_file(source / "layer1.json")}
    assert kinds["source_norms"]["file"] == f"../../{SOURCE_NAME}/{NORMS_FILE}"
    assert kinds["source_norms"]["sha256"] == sha256_of_file(source / NORMS_FILE)
    assert ex["outputs"] == [{"output_kind": "norms", "file": f"norms_{NEW_NAME}.json",
                              "sha256": sha256_of_file(new_dir / f"norms_{NEW_NAME}.json")}]
    assert ex["counts"]["source_verdicts"] == {"accepted": 3, "rejected": 1, "needs_human_review": 0}
    assert ex["counts"]["changed_verdicts"] == {"count": 1, "norm_ids": [NORM_C]}
    assert {"section_2_actor_audit", "addressee_values"} <= set(ex["counts"])
    payload = _payload(new_dir)
    assert payload["build"]["extraction_usage"] == {"generator": ZERO_USAGE, "judge": ex["usage"]["judge"]}
    assert payload["rejudge"]["description"] == DESCRIPTION
    # the event log is in the new build, one judge event per norm, never a generator event
    events = [json.loads(line) for line in
              (new_dir / "logs" / "rejudge_extraction_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["direction"] for e in events] == ["judge"] * 4 and all(e["input_sha256"] for e in events)
    assert all(e["model"] == "claude-fake" for e in events)
    # the library imports no generator client
    assert not hasattr(rejudge_norms, "OpenAIGenerator")
    out = capsys.readouterr().out
    assert "changed against the source: 1" in out and f"{4 * USD_PER_JUDGE_CALL:.4f} USD" in out


def record_source_id(src):
    return json.loads((src / "publications" / "a1b2c3d4e5f6.json").read_text(encoding="utf-8"))["record_id"]


def test_only_the_judge_fields_change_and_ids_are_kept(tmp_path, source, monkeypatch):
    # the new judge rejects A and accepts C, the reverse of the source's judge
    judge = ScriptedJudge({unit_key(UNIT_OF[NORM_A]): "rejected"})
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(source, new_dir)) == 0
    before, after = _source_norms(source), _payload(new_dir)
    assert list(after) == [*before, "rejudge"]
    assert [n["norm_id"] for n in after["norms"]] == FILE_ORDER
    for old, new in zip(before["norms"], after["norms"], strict=True):
        assert list(new) == list(old), "the key order is kept"
        assert {k for k in old if old[k] != new[k]} <= set(JUDGE_FIELDS)
        assert new["judge_run_id"] == old["judge_run_id"] and new["confidence"] == 0.7
    verdicts = {n["norm_id"]: n["judge_verdict"] for n in after["norms"]}
    assert verdicts == {NORM_A: "rejected", NORM_B: "accepted", NORM_C: "accepted", NORM_D: "accepted"}
    assert {n["norm_id"]: n["review_status"] for n in after["norms"]}[NORM_A] == "needs_review"
    runs = after["judge_runs"]
    assert [r["id"] for r in runs] == [n["judge_run_id"] for n in before["norms"]]
    assert {r["build_id"] for r in runs} == {SOURCE_BUILD_ID} and {r["judge_model"] for r in runs} == {"claude-fake"}
    assert after["stats"] == {**before["stats"], "candidates": 4,
                              "verdicts": {"accepted": 3, "rejected": 1, "needs_human_review": 0}}
    build, old_build = after["build"], before["build"]
    models = build["extraction_models"]
    assert {k: models[k] for k in ("generator_model", "generator_effort", "generator_temperature",
                                   "generator_json_mode")} == {k: old_build["extraction_models"][k] for k in (
        "generator_model", "generator_effort", "generator_temperature", "generator_json_mode")}
    assert (models["judge_model"], models["judge_temperature"]) == ("claude-fake", "0")
    assert models["model_parameters_sha256"] == "environment-parameters-sha256"
    assert build["extraction_temperature"] == {"generator": "N/A", "judge": "0"}
    assert build["extraction_sampling"] == {"generator": "N/A", "judge": "0"}
    assert build["extracted_at"] == old_build["extracted_at"] and build["prompt_version"] == "v6"
    rejudge = after["rejudge"]
    assert rejudge["source_build"] == SOURCE_NAME and rejudge["source_judge_model"] == "gpt-fake-sol"
    assert rejudge["source_norms_sha256"] == sha256_of_file(source / NORMS_FILE)
    assert rejudge["carried_generator_usage"] == old_build["extraction_usage"]["generator"]
    assert rejudge["source_judge_usage"] == old_build["extraction_usage"]["judge"]
    _store, record = _record(new_dir)
    assert record["executions"][0]["counts"]["changed_verdicts"] == {"count": 2, "norm_ids": [NORM_C, NORM_A]}


def test_every_stored_norm_is_judged_once_with_its_generation_time_message(tmp_path, source, monkeypatch):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    assert cli.main(_argv(source, _new(tmp_path))) == 0
    captured = source_judge_messages(tmp_path)["norms"]
    assert len(judge.calls) == 4
    assert {system for system, _user in judge.calls} == {load_prompt("judge_norms", "v6")}
    assert [user for _system, user in judge.calls] == [captured[norm_id] for norm_id in FILE_ORDER]


def test_the_source_folder_is_left_unchanged(tmp_path, source, monkeypatch):
    before = folder_state(source)
    patch_command(monkeypatch, cli, ScriptedJudge())
    assert cli.main(_argv(source, _new(tmp_path))) == 0
    assert cli.main(_argv(source, _new(tmp_path, under="other"), "2026-10-16-gpt-fake-high")) == 2
    assert folder_state(source) == before
    assert not list(source.rglob("*.checkpoint.jsonl")) and not (source / "logs").exists()


@pytest.mark.parametrize("name", [
    "2026-10-16-gpt-fake-high",  # no judge model
    "2026-10-16-gpt-fake-high-claude-fake",  # "claude-" kept
    "2026-13-01-gpt-fake-high-fake",  # not a date
    "2026-10-14-gpt-fake-high-fake-x",  # a trailing part that is not a number
])
def test_a_name_off_the_rule_is_refused(tmp_path, source, monkeypatch, capsys, name):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path, name)
    assert cli.main(_argv(source, new_dir, name)) == 2
    assert "does not follow the rule" in capsys.readouterr().err
    assert judge.calls == [] and not new_dir.exists()


def test_an_out_dir_not_named_by_the_name_is_refused(tmp_path, source, monkeypatch, capsys):
    patch_command(monkeypatch, cli, ScriptedJudge())
    new_dir = tmp_path / "new" / "elsewhere"
    assert cli.main(_argv(source, new_dir)) == 2
    assert f"must be named {NEW_NAME}" in capsys.readouterr().err and not new_dir.exists()


def test_another_date_and_a_trailing_number_are_accepted(tmp_path, source, monkeypatch):
    assert expected_name("2026-10-14-gpt-6-astra-high", "claude-opus-5-5", date(2026, 10, 16)) == \
        "2026-10-16-gpt-6-astra-high-opus-5-5"
    assert name_refusal("2026-10-17-gpt-6-astra-high-opus-5-5-2", "2026-10-14-gpt-6-astra-high",
                        "claude-opus-5-5") is None
    assert "2026-" in name_refusal("2026-10-16-gpt-6-astra-high", "2026-10-14-gpt-6-astra-high", "claude-opus-5-5")
    patch_command(monkeypatch, cli, ScriptedJudge())
    name = "2026-10-17-gpt-fake-high-fake-2"
    new_dir = _new(tmp_path, name)
    assert cli.main(_argv(source, new_dir, name)) == 0
    assert (new_dir / f"norms_{name}.json").is_file()
    assert _record(new_dir, name)[1]["executions"][0]["status"] == "done"


def _copy_with_norms(source, tmp_path, mutate):
    """A copy of the source whose norms file is changed by mutate, its
    publication manifest naming the new digest (the source is not touched)."""
    copy = tmp_path / "copies" / SOURCE_NAME
    shutil.copytree(source, copy)
    payload = json.loads((copy / NORMS_FILE).read_text(encoding="utf-8"))
    mutate(payload)
    (copy / NORMS_FILE).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    manifest_path = next((copy / "publications").glob("*.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["inputs"]:
        if entry["input_kind"] == "norms":
            entry["sha256"] = sha256_of_file(copy / NORMS_FILE)
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return copy


def test_another_generator_a_changed_prompt_and_v1_v2_are_refused(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    new_dir = _new(tmp_path)
    for cfg, said in ((fake_cfg(generator_model="gpt-other"), "generator_model"),
                      (fake_cfg(generator_effort="xhigh"), "generator_effort"),
                      (fake_cfg(generator_temperature="0"), "generator_temperature"),
                      (fake_cfg(generator_json_mode="N/A"), "generator_json_mode")):
        patch_command(monkeypatch, cli, judge, cfg=cfg)
        assert cli.main(_argv(source, new_dir)) == 2
        assert said in capsys.readouterr().err
    patch_command(monkeypatch, cli, judge)
    with monkeypatch.context() as m:
        m.setattr(rejudge_norms, "load_prompt", lambda kind, version: "judge_norms v6, edited since the source")
        assert cli.main(_argv(source, new_dir)) == 2
        assert "the source's judge runs recorded" in capsys.readouterr().err
    for version in ("v1", "v2"):
        copy = _copy_with_norms(source, tmp_path / version,
                                lambda payload, v=version: payload["build"].__setitem__("prompt_version", v))
        assert cli.main(_argv(copy, new_dir)) == 2
        assert "DEC-21" in capsys.readouterr().err
        assert "DEC-21" in norms_refusal({"build": {"prompt_version": version}}, fake_cfg().as_public_dict())
    assert judge.calls == [] and not new_dir.exists()


def _single_run_payload(tmp_path, source, monkeypatch):
    patch_command(monkeypatch, cli, ScriptedJudge())
    name = "2026-10-17-gpt-fake-high-fake"
    assert cli.main(_argv(source, _new(tmp_path, name, under="single"), name)) == 0
    return _payload(_new(tmp_path, name, under="single"), name)


def _without_run_details(payload):
    """A payload less what differs between two runs over the same verdicts:
    the clock and this run's usage."""
    payload = json.loads(json.dumps(payload))
    for run in payload["judge_runs"]:
        run.pop("started_at"), run.pop("completed_at")
    payload["rejudge"].pop("rejudged_at")
    payload["build"]["extraction_usage"].pop("judge")
    return payload


def test_the_cost_stop_ends_failed_keeps_the_checkpoint_and_a_resume_finishes(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    checkpoint = new_dir / f"norms_{NEW_NAME}.checkpoint.jsonl"
    first = ScriptedJudge()
    patch_command(monkeypatch, cli, first)
    assert cli.main(_argv(source, new_dir, NEW_NAME, "0.001")) == 5
    err = capsys.readouterr().err
    # the first group (Article 16: C and D) ran, then the spend reached the stop
    assert "cost stop: spent 0.0120 USD of 0.0010 USD" in err
    assert "--resume" in err and "raise --cost-stop" in err
    assert len(first.calls) == 2
    store, record = _record(new_dir)
    (ex,) = record["executions"]
    assert ex["status"] == "failed" and ex["error"] == "cost stop: spent 0.0120 USD of 0.0010 USD"
    assert ex["completed_keys"] == [GROUPS[0]] and ex["usage"]["judge"]["calls"] == 2
    assert [json.loads(line)["group"] for line in checkpoint.read_text(encoding="utf-8").splitlines()] == [GROUPS[0]]

    # a resume under a stop the record's spend already reached stops before any call
    blocked = ScriptedJudge()
    patch_command(monkeypatch, cli, blocked)
    assert cli.main(_argv(source, new_dir, NEW_NAME, "0.01", "--resume")) == 5
    assert "cost stop: spent 0.0120 USD of 0.0100 USD" in capsys.readouterr().err and blocked.calls == []

    second = ScriptedJudge()
    patch_command(monkeypatch, cli, second)
    assert cli.main(_argv(source, new_dir, NEW_NAME, "1000", "--resume")) == 0
    assert [user.split("\n", 1)[0] for _s, user in second.calls] == [
        f"Source unit node id: {UNIT_OF[n]}" for n in (NORM_B, NORM_A)]
    assert not checkpoint.exists()
    record = store.read(record["record_id"])
    last = record["executions"][-1]
    assert last["status"] == "done" and last["inherited_keys"] == [GROUPS[0]]
    assert last["resumes_run_id"] == ex["run_id"] and last["config"]["cost_stop_usd"] == 1000.0
    resumed = _payload(new_dir)
    assert resumed["build"]["extraction_usage"]["judge"]["calls"] == 2
    assert _without_run_details(resumed) == _without_run_details(_single_run_payload(tmp_path, source, monkeypatch))


def test_backend_unavailable_exits_3_and_prints_the_resume_command(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge(errors={unit_key(UNIT_OF[NORM_B]): InferenceBackendUnavailable(5, "HTTP 529 overloaded")})
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    argv = _argv(source, new_dir)
    assert cli.main(argv) == 3
    err = capsys.readouterr().err
    assert f"  .venv/bin/python -m tere4ai.rejudge norms --source {source}" in err
    assert err.rstrip().endswith("--resume") and "1 of 3 groups done" in err
    _store, record = _record(new_dir)
    (ex,) = record["executions"]
    assert ex["status"] == "failed" and "529" in ex["error"] and ex["completed_keys"] == [GROUPS[0]]
    assert (new_dir / f"norms_{NEW_NAME}.checkpoint.jsonl").is_file()


def test_the_presenter_reads_rejudge_progress(tmp_path, source, monkeypatch):
    new_dir = _new(tmp_path)
    seen: list[dict] = []

    def present_while_running(user):
        # the second group's first call: one group is in the checkpoint
        if unit_key(UNIT_OF[NORM_B]) in user:
            store, record = _record(new_dir)
            seen.append(present_record(record, new_dir, datetime.now(UTC), None, store))

    patch_command(monkeypatch, cli, ScriptedJudge(on_call=present_while_running))
    assert cli.main(_argv(source, new_dir, NEW_NAME, "0.013")) == 5
    (running,) = seen
    ex = running["executions"][0]
    assert ex["status"] == "running" and ex["liveness"] == "live"
    assert ex["progress"] == {"completed": 1, "expected_total": 3, "work_unit": "groups", "inherited": 0,
                              "source": "checkpoint"}
    store, record = _record(new_dir)
    ended = present_record(record, new_dir, datetime.now(UTC), None, store)["executions"][0]
    assert ended["status"] == "failed"
    assert ended["progress"] == {"completed": 2, "expected_total": 3, "work_unit": "groups", "inherited": 0,
                                 "source": "record"}
    # a model command: its models and usage are recorded, never "the command calls no model"
    assert ended["provenance"]["models"] == "recorded" and ended["provenance"]["usage"] == "recorded"
    assert "the command calls no model" not in ended["reasons"].values()



def test_a_source_norm_without_a_judge_field_is_refused(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)

    def drop_type_view(payload):
        del next(n for n in payload["norms"] if n["norm_id"] == NORM_D)["judge_type_agrees"]

    copy = _copy_with_norms(source, tmp_path, drop_type_view)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(copy, new_dir)) == 2
    assert f"the source norm {NORM_D} lacks judge_type_agrees" in capsys.readouterr().err
    assert judge.calls == [] and not new_dir.exists()
    assert norms_refusal({"build": {"prompt_version": "v6"}, "judge_runs": []}, fake_cfg().as_public_dict()) == \
        "the source build holds no judge runs, nothing to re-judge"


def test_a_published_file_outside_the_source_folder_is_refused(tmp_path, source):
    copy = tmp_path / "copies" / SOURCE_NAME
    shutil.copytree(source, copy)
    shutil.copyfile(copy / NORMS_FILE, tmp_path / "copies" / "outside.json")
    manifest_path = next((copy / "publications").glob("*.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(i for i in manifest["inputs"] if i["input_kind"] == "norms")["file"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    with pytest.raises(SourceError, match="lies outside the source folder"):
        read_source(copy)


def test_an_output_that_names_a_published_artefact_exits_1(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    (new_dir / "publications").mkdir(parents=True)
    out_path = new_dir / f"norms_{NEW_NAME}.json"
    out_path.write_text('{"published": true}', encoding="utf-8")
    (new_dir / "publications" / "0123456789ab.json").write_text(json.dumps(
        {"chain_id": "0123456789ab", "inputs": [{"input_kind": "norms", "file": out_path.name,
                                                 "sha256": sha256_of_file(out_path)}]}), encoding="utf-8")
    assert cli.main(_argv(source, new_dir)) == 1
    assert "it is an input of publication 0123456789ab" in capsys.readouterr().err
    assert out_path.read_text(encoding="utf-8") == '{"published": true}'
    assert judge.calls == [] and _no_record(new_dir)


def test_a_stale_checkpoint_without_resume_exits_2(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    new_dir.mkdir(parents=True)
    checkpoint = new_dir / f"norms_{NEW_NAME}.checkpoint.jsonl"
    checkpoint.write_text(json.dumps({"run_id": "0" * 12, "group": GROUPS[0],
                                      "result": {"norms": [], "judge_runs": [], "stats": {}}}) + "\n")
    assert cli.main(_argv(source, new_dir)) == 2
    assert "pass --resume" in capsys.readouterr().err
    assert judge.calls == [] and _no_record(new_dir)


def test_a_layer1_with_another_digest_exits_2(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    new_dir.mkdir(parents=True)
    (new_dir / "layer1.json").write_text("{}", encoding="utf-8")
    assert cli.main(_argv(source, new_dir)) == 2
    assert "is not the source's layer1.json" in capsys.readouterr().err
    assert (new_dir / "layer1.json").read_text(encoding="utf-8") == "{}"
    assert judge.calls == [] and _no_record(new_dir)


def test_a_missing_judge_price_row_exits_4(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    rows = {model: row for model, row in prices().items() if model != "claude-fake"}
    patch_command(monkeypatch, cli, judge, price_rows=rows)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(source, new_dir)) == 4
    assert "no price row for the judge 'claude-fake'" in capsys.readouterr().err
    assert judge.calls == [] and not new_dir.exists()


# ---- final review fixes (B173): the guards the two final reviewers found


def _copy_named(source, folder):
    """A copy of the source build in folder (any name: the source is found by its
    activation pointer, never by its folder's name)."""
    shutil.copytree(source, folder)
    return folder


@pytest.mark.parametrize("command", ["norms", "alignments", "report"])
def test_an_out_dir_inside_the_source_folder_is_refused(tmp_path, source, monkeypatch, capsys, command):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = source / NEW_NAME
    argv = ["--source", str(source), "--out-dir", str(new_dir), "--name", NEW_NAME]
    argv = [command, *argv] if command == "report" else [command, *argv, "--cost-stop", "1000"]
    assert cli.main(argv) == 2
    assert f"the out-dir {new_dir} lies inside the source folder {source}" in capsys.readouterr().err
    # nothing written into the source (the fixture checks every sha256 too), no record, no call
    assert not new_dir.exists() and judge.calls == []


def test_an_out_dir_equal_to_holding_or_linked_into_the_source_is_refused(tmp_path, source, monkeypatch, capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    # equal: a source copy in a folder named by the new name
    equal = _copy_named(source, tmp_path / "equal" / NEW_NAME)
    before = folder_state(equal)
    assert cli.main(_argv(equal, equal)) == 2
    assert f"the out-dir {equal} is the source folder {equal}" in capsys.readouterr().err
    assert folder_state(equal) == before
    # holding: a source copy inside a folder named by the new name
    holder = tmp_path / "holding" / NEW_NAME
    inner = _copy_named(source, holder / SOURCE_NAME)
    assert cli.main(_argv(inner, holder)) == 2
    assert f"the out-dir {holder} holds the source folder {inner}" in capsys.readouterr().err
    assert sorted(p.name for p in holder.iterdir()) == [SOURCE_NAME]
    # a symbolic link to the source: resolved, so the out-dir under it lies inside the source
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    assert cli.main(_argv(source, link / NEW_NAME)) == 2
    assert "lies inside the source folder" in capsys.readouterr().err
    assert judge.calls == []


def _reference(kind):
    return {"kind": kind, "layer": 2 if kind == "norms" else 3, "freeze_id": "freeze-x"}


_HUMAN_REVIEW = {"decision": "keep", "decided_by": "HUMAN1"}
# (the file changed, the change): its own reference block, or an item with a human_review entry
MATERIALISED = {
    "norms reference": ("norms", lambda p: p["build"].__setitem__("reference", _reference("norms"))),
    "norms human review": ("norms", lambda p: p["norms"][0].__setitem__("human_review", _HUMAN_REVIEW)),
    "alignments reference": ("alignments", lambda p: p["build"].__setitem__("reference", _reference("alignments"))),
    "alignments human review": ("alignments", lambda p: p["assertions"][0].__setitem__("human_review",
                                                                                         _HUMAN_REVIEW)),
}


@pytest.mark.parametrize("case", list(MATERIALISED))
@pytest.mark.parametrize("command", ["norms", "alignments"])
def test_a_materialised_source_is_refused(tmp_path, source, monkeypatch, capsys, case, command):
    which, mutate = MATERIALISED[case]
    if which == "norms":
        copy = _copy_with_norms(source, tmp_path, mutate)
    else:
        copy = _copy_with_alignments(source, tmp_path, mutate)
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    argv = [command, "--source", str(copy), "--out-dir", str(new_dir), "--name", NEW_NAME, "--cost-stop", "1000"]
    assert cli.main(argv) == 2
    assert ("the source is a materialised reference file (human decisions applied); only a generator build can be "
            "re-judged") in capsys.readouterr().err
    assert judge.calls == [] and not new_dir.exists()


def test_a_norm_with_an_inference_source_and_no_inferred_addressee_is_refused(tmp_path, source, monkeypatch,
                                                                              capsys):
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)

    def source_without_addressee(payload):
        norm = next(n for n in payload["norms"] if n["norm_id"] == NORM_C)
        assert norm["addressee_inferred"] is None
        norm["addressee_inference_source_node_id"] = "eu-ai-act:article-16:paragraph-1:point-a"

    copy = _copy_with_norms(source, tmp_path, source_without_addressee)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(copy, new_dir)) == 2
    err = capsys.readouterr().err
    assert (f"the source norm {NORM_C} keeps the inference source node eu-ai-act:article-16:paragraph-1:point-a "
            "beside no inferred addressee") in err
    assert "cannot give back" in err
    assert judge.calls == [] and not new_dir.exists()


def test_a_fresh_norms_run_over_a_consumed_norms_file_is_refused(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    patch_command(monkeypatch, cli, ScriptedJudge())
    assert cli.main(_argv(source, new_dir)) == 0
    capsys.readouterr()
    out_path = new_dir / f"norms_{NEW_NAME}.json"
    before = folder_state(new_dir)
    _store, record = _record(new_dir)
    (done,) = record["executions"]
    again = ScriptedJudge()
    patch_command(monkeypatch, cli, again)
    assert cli.main(_argv(source, new_dir)) == 2
    assert (f"{out_path.name} is the output of the done execution {done['run_id']}; choose another --name (a re-run "
            "would pay the judges again and leave the alignments stale)") in capsys.readouterr().err
    assert again.calls == [] and folder_state(new_dir) == before
    assert len(_record(new_dir)[1]["executions"]) == 1
    # a --resume once the run finished (no checkpoint left) is the same re-run
    assert cli.main([*_argv(source, new_dir), "--resume"]) == 2
    assert "is the output of the done execution" in capsys.readouterr().err
    assert again.calls == [] and folder_state(new_dir) == before


@pytest.mark.parametrize("raised", [InferenceBackendRefused("HTTP 400 invalid request"), KeyboardInterrupt()],
                         ids=["refused", "interrupt"])
def test_a_refused_request_or_an_interrupt_ends_failed_and_prints_the_resume_command(tmp_path, source, monkeypatch,
                                                                                    capsys, raised):
    judge = ScriptedJudge(errors={unit_key(UNIT_OF[NORM_B]): raised})
    patch_command(monkeypatch, cli, judge)
    new_dir = _new(tmp_path)
    with pytest.raises(type(raised)):
        cli.main(_argv(source, new_dir))
    err = capsys.readouterr().err
    assert f"  .venv/bin/python -m tere4ai.rejudge norms --source {source}" in err
    assert err.rstrip().endswith("--resume") and "1 of 3 groups done" in err
    _store, record = _record(new_dir)
    (ex,) = record["executions"]
    assert ex["status"] == "failed" and ex["error"].startswith(type(raised).__name__)
    assert ex["completed_keys"] == [GROUPS[0]] and ex["usage"]["judge"]["calls"] == 2
    assert (new_dir / f"norms_{NEW_NAME}.checkpoint.jsonl").is_file()


def test_the_judge_is_named_before_the_first_call(tmp_path, source, monkeypatch, capsys):
    seen: list[str] = []
    judge = ScriptedJudge(on_call=lambda _user: seen.append(capsys.readouterr().out))
    patch_command(monkeypatch, cli, judge)
    assert cli.main(_argv(source, _new(tmp_path))) == 0
    assert "judging with claude-fake, effort high, temperature 0\n" in seen[0]


def test_a_name_that_spells_another_declared_model_is_refused(tmp_path, source, monkeypatch, capsys):
    declared = ["claude-opus-5", "claude-opus-5-5", "gpt-6-astra"]
    src_name = "2026-10-14-gpt-6-astra-high"
    # judged by claude-opus-5, ...-opus-5-5 reads as opus-5 plus -5 and as opus-5-5
    refusal = name_refusal("2026-10-16-gpt-6-astra-high-opus-5-5", src_name, "claude-opus-5", declared)
    assert "also reads as 2026-10-14-gpt-6-astra-high judged by claude-opus-5-5" in refusal
    # the rule's own names read one way only
    assert name_refusal("2026-10-16-gpt-6-astra-high-opus-5-5", src_name, "claude-opus-5-5", declared) is None
    assert name_refusal("2026-10-16-gpt-6-astra-high-opus-5-2", src_name, "claude-opus-5", declared) is None
    assert name_refusal("2026-10-16-gpt-6-astra-high-opus-5-5", src_name, "claude-opus-5") is None
    # the command reads the declared models from config/model_parameters.json
    judge = ScriptedJudge()
    patch_command(monkeypatch, cli, judge)
    monkeypatch.setattr(cli, "load_model_parameters", lambda: {"claude-fake": {}, "claude-fake-2": {}})
    name = "2026-10-16-gpt-fake-high-fake-2"
    new_dir = _new(tmp_path, name)
    assert cli.main(_argv(source, new_dir, name)) == 2
    assert "also reads as 2026-10-14-gpt-fake-high judged by claude-fake-2" in capsys.readouterr().err
    assert judge.calls == [] and not new_dir.exists()

"""B173 task 3: `python -m tere4ai.rejudge alignments` on a published source build
of mock data, after `norms` re-judged its norms with a judge that accepts C
(rejected by the source's judge) and rejects D (accepted by it). Scripted
clients only; the Layer 3 generator is ScriptedGenerator, which fails the test
for any norm but C.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20
"""

from __future__ import annotations

import json
import shutil

import pytest
from tests.unit.rejudge_mock_build import (
    ALIGNMENTS_FILE,
    GENERATOR_MODEL,
    NEW_NAME,
    NORM_A,
    NORM_B,
    NORM_C,
    NORM_D,
    NORMS_FILE,
    SOURCE_BUILD_ID,
    SOURCE_NAME,
    UNIT_OF,
    USD_PER_GENERATOR_CALL,
    USD_PER_JUDGE_CALL,
    ScriptedGenerator,
    ScriptedJudge,
    fake_cfg,
    folder_state,
    make_source_build,
    patch_command,
    prices,
    source_judge_messages,
    unit_key,
)

import tere4ai.rejudge.__main__ as cli
import tere4ai.rejudge.alignments as rejudge_alignments
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.align_hleg.pipeline import MECHANICAL_JUDGE_MODEL
from tere4ai.extract_norms.model_clients import TERMINAL_POLICY
from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE

DESCRIPTION = "generator output of 2026-10-14-gpt-fake-high, judged by claude-fake"
NORMS_SPEND = 4 * USD_PER_JUDGE_CALL  # the norms run: one judge call per norm


@pytest.fixture
def source(tmp_path):
    src = make_source_build(tmp_path)
    before = folder_state(src)
    yield src
    # every test that reads the source folder: its file list and every sha256 unchanged
    assert folder_state(src) == before


def _argv(command, src, new_dir, name=NEW_NAME, cost_stop="1000", *extra):
    return [command, "--source", str(src), "--out-dir", str(new_dir), "--name", name, "--cost-stop", cost_stop,
            *extra]


def _new(tmp_path, name=NEW_NAME, under="new"):
    return tmp_path / under / name


def _rejudge_norms(monkeypatch, src, new_dir, name=NEW_NAME):
    """`norms` first: the new judge accepts C and rejects D; A and B stay accepted."""
    patch_command(monkeypatch, cli, ScriptedJudge({unit_key(UNIT_OF[NORM_D]): "rejected"}))
    assert cli.main(_argv("norms", src, new_dir, name)) == 0


def _both(tmp_path, src, monkeypatch, judge=None, generator=None, name=NEW_NAME, under="new", extra=()):
    """`norms`, then `alignments` on scripted clients; returns the folder and the clients."""
    new_dir = _new(tmp_path, name, under)
    _rejudge_norms(monkeypatch, src, new_dir, name)
    judge = judge or ScriptedJudge()
    generator = generator or ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", src, new_dir, name, "1000", *extra)) == 0
    return new_dir, judge, generator


def _alignments(new_dir, name=NEW_NAME):
    return json.loads((new_dir / f"alignments_{name}.json").read_text(encoding="utf-8"))


def _source_alignments(src):
    return json.loads((src / ALIGNMENTS_FILE).read_text(encoding="utf-8"))


def _source_ids(src, norm_id):
    return [a["id"] for a in _source_alignments(src)["assertions"] if a["source_norm_id"] == norm_id]


def _record(new_dir, name=NEW_NAME):
    store = BuildRecordStore(new_dir)
    return store, store.read(store.resolve(name))


def _alignments_execution(new_dir, name=NEW_NAME):
    return [ex for ex in _record(new_dir, name)[1]["executions"] if ex["command"] == "rejudge_alignments"]


def _norm_lines(calls):
    return [line for _system, user in calls for line in user.splitlines() if line.startswith("Norm id:")]


def _copy_with_alignments(source, tmp_path, mutate):
    """A copy of the source whose alignments file is changed by mutate, its
    publication manifest naming the new digest (the source is not touched)."""
    copy = tmp_path / "copies" / SOURCE_NAME
    shutil.copytree(source, copy)
    payload = json.loads((copy / ALIGNMENTS_FILE).read_text(encoding="utf-8"))
    mutate(payload)
    (copy / ALIGNMENTS_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest_path = next((copy / "publications").glob("*.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["inputs"]:
        if entry["input_kind"] == "alignments":
            entry["sha256"] = sha256_of_file(copy / ALIGNMENTS_FILE)
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return copy


def test_layer3_generator_calls_are_exactly_the_newly_accepted_norms(tmp_path, source, monkeypatch):
    new_dir, _judge, generator = _both(tmp_path, source, monkeypatch)
    assert _norm_lines(generator.calls) == [f"Norm id: {NORM_C}"]
    assert {system for system, _user in generator.calls} == {load_prompt("align_hleg", "v3")}
    payload = _alignments(new_dir)
    assert payload["stats"]["newly_aligned_norms"] == [NORM_C]
    source_runs = _source_alignments(source)["mapping_runs"]
    (new_run,) = [run for run in payload["mapping_runs"] if run["id"] not in {r["id"] for r in source_runs}]
    assert payload["mapping_runs"] == [*source_runs, new_run]
    assert new_run["generator_model"] == GENERATOR_MODEL and new_run["build_id"] == SOURCE_BUILD_ID
    (c_assertion,) = [a for a in payload["assertions"] if a["source_norm_id"] == NORM_C]
    c_suffix = NORM_C.removeprefix("norm:")
    assert c_assertion["id"] == f"align:{c_suffix}:transparency:1"
    assert c_assertion["judge_run_id"] == f"judgerun:mapping:{c_suffix}:transparency:c1"
    assert c_assertion["mapping_run_id"] == new_run["id"] and c_assertion["proposed_relation_type"] == "supports"
    (ex,) = _alignments_execution(new_dir)
    assert ex["usage"]["generator"]["calls"] == 1
    assert ex["counts"]["newly_aligned_norms"] == {"count": 1, "norm_ids": [NORM_C]}


def test_carried_candidates_are_judged_with_the_generation_time_message(tmp_path, source, monkeypatch):
    _new_dir, judge, _generator = _both(tmp_path, source, monkeypatch)
    captured = source_judge_messages(tmp_path)["alignments"]
    assert {system for system, _user in judge.calls} == {load_prompt("judge_alignment", "v3")}
    # C's new candidate, then A's two stored ones; nothing for B or D
    assert _norm_lines(judge.calls) == [f"Norm id: {n}" for n in (NORM_C, NORM_A, NORM_A)]
    a_messages = [user for _system, user in judge.calls if f"Norm id: {NORM_A}\n" in user]
    assert a_messages == [captured[assertion_id] for assertion_id in _source_ids(source, NORM_A)]


def test_a_source_made_under_v2_is_rejudged_under_v3(tmp_path, source, monkeypatch):
    """B174 R4: the alignment judge, and the generator of the newly accepted
    norms, run at the code's default version, v3; the mock source was made
    under v2. The stored candidates reach the judge as at generation time,
    under v3's system prompt."""
    assert rejudge_alignments.DEFAULT_PROMPT_VERSION == "v3"
    new_dir, judge, generator = _both(tmp_path, source, monkeypatch)
    v3 = load_prompt("judge_alignment", "v3")
    assert "the law in force" in v3 and "the law in force" not in load_prompt("judge_alignment", "v2")
    assert {system for system, _user in judge.calls} == {v3}
    assert {system for system, _user in generator.calls} == {load_prompt("align_hleg", "v3")}
    captured = source_judge_messages(tmp_path)["alignments"]
    a_messages = [user for _system, user in judge.calls if f"Norm id: {NORM_A}\n" in user]
    assert a_messages == [captured[assertion_id] for assertion_id in _source_ids(source, NORM_A)]
    payload, source_payload = _alignments(new_dir), _source_alignments(source)
    source_run_ids = {r["id"] for r in source_payload["mapping_runs"]}
    judged = [r for r in payload["judge_runs"] if r["judge_model"] != MECHANICAL_JUDGE_MODEL]
    assert {(r["prompt_version"], r["prompt_sha256"]) for r in judged} == {("v3", prompt_sha256(v3))}
    assert {r["prompt_version"] for r in source_payload["judge_runs"]} == {"v2"}
    new_runs = [r for r in payload["mapping_runs"] if r["id"] not in source_run_ids]
    assert {(r["prompt_version"], r["prompt_sha256"]) for r in new_runs} == {
        ("v3", prompt_sha256(load_prompt("align_hleg", "v3")))}
    # the source's runs the kept assertions name are carried with their v2 records
    assert {r["prompt_version"] for r in payload["mapping_runs"] if r["id"] in source_run_ids} == {"v2"}
    build = payload["build"]
    assert build["alignment_prompt_version"] == "v3" and source_payload["build"]["alignment_prompt_version"] == "v2"
    assert (build["alignment_rejudge"]["source_prompt_version"],
            build["alignment_rejudge"]["judge_prompt_version"]) == ("v2", "v3")


def test_a_source_whose_relation_type_handling_differs_from_the_judge_version_is_refused(tmp_path, source,
                                                                                       monkeypatch, capsys):
    monkeypatch.setattr(rejudge_alignments, "_PROMPTS_TAKING_ANY_CORRECTION", frozenset({"v1", "v3"}))
    for command in ("norms", "alignments"):
        judge, generator = ScriptedJudge(), ScriptedGenerator()
        patch_command(monkeypatch, cli, judge, generator=generator)
        new_dir = _new(tmp_path, under=command)
        assert cli.main(_argv(command, source, new_dir)) == 2
        assert ("the source alignments were made under prompt version v2, whose candidate or handling of the "
                "judge's relation type differs from v3's") in capsys.readouterr().err
        assert judge.calls == [] and generator.calls == [] and not new_dir.exists()


def test_a_source_whose_alignment_runs_carry_another_sha_is_still_refused(tmp_path, source, monkeypatch, capsys):
    """The source's judge and alignment runs must carry the sha256 of the
    source version's files (v2) as they are today; v3's digests do not stand
    in for them."""
    for kind, key, whose in (("judge_alignment", "judge_runs", "judge runs"),
                             ("align_hleg", "mapping_runs", "alignment runs")):
        v3_sha = prompt_sha256(load_prompt(kind, "v3"))

        def mutate(payload, key=key, v3_sha=v3_sha):
            for run in payload[key]:
                if run.get("judge_model") != MECHANICAL_JUDGE_MODEL:
                    run["prompt_sha256"] = v3_sha

        copy = _copy_with_alignments(source, tmp_path / kind, mutate)
        judge, generator = ScriptedJudge(), ScriptedGenerator()
        patch_command(monkeypatch, cli, judge, generator=generator)
        new_dir = _new(tmp_path, under=kind)
        assert cli.main(_argv("alignments", copy, new_dir)) == 2
        assert (f"the {kind} v2 prompt has sha256 {prompt_sha256(load_prompt(kind, 'v2'))} today; the source's "
                f"{whose} recorded {v3_sha}") in capsys.readouterr().err
        assert judge.calls == [] and generator.calls == [] and not new_dir.exists()


def test_alignments_of_norms_now_rejected_are_dropped_and_counted(tmp_path, source, monkeypatch):
    new_dir, judge, generator = _both(tmp_path, source, monkeypatch)
    payload = _alignments(new_dir)
    (d_id,) = _source_ids(source, NORM_D)
    (d_source,) = [a for a in _source_alignments(source)["assertions"] if a["id"] == d_id]
    assert payload["stats"]["dropped_assertions"] == [d_id]
    assert payload["stats"]["norms_skipped_not_accepted"] == 1 and payload["stats"]["norms_total"] == 4
    assert d_id not in {a["id"] for a in payload["assertions"]}
    assert d_source["judge_run_id"] not in {r["id"] for r in payload["judge_runs"]}
    assert all(NORM_D not in json.dumps(entry) for key in ("mechanical_rejects", "invalid_candidates",
                                                            "invalid_assertions", "norms_failed")
               for entry in payload["stats"][key])
    assert f"Norm id: {NORM_D}" not in _norm_lines(judge.calls) + _norm_lines(generator.calls)
    (ex,) = _alignments_execution(new_dir)
    assert ex["counts"]["dropped_assertions"] == {"count": 1, "assertion_ids": [d_id]}
    assert ex["counts"]["norms_skipped_not_accepted"] == 1


def test_a_zero_alignment_norm_stays_zero_without_a_call(tmp_path, source, monkeypatch):
    new_dir, judge, generator = _both(tmp_path, source, monkeypatch)
    payload = _alignments(new_dir)
    assert payload["stats"]["zero_alignment_norms"] == 1
    assert f"Norm id: {NORM_B}" not in _norm_lines(judge.calls) + _norm_lines(generator.calls)
    assert NORM_B not in {a["source_norm_id"] for a in payload["assertions"]}
    assert payload["stats"]["norms_failed"] == [] and payload["stats"]["invalid_candidates"] == []
    (ex,) = _alignments_execution(new_dir)
    assert ex["counts"]["zero_alignment_norms"] == 1


def test_a_carried_candidate_failing_the_quote_check_is_rejected_mechanically(tmp_path, source, monkeypatch):
    a1, a2 = _source_ids(source, NORM_A)

    def unquotable(payload):
        next(a for a in payload["assertions"] if a["id"] == a1)["source_quote"] = "a quote the norm does not hold"

    copy = _copy_with_alignments(source, tmp_path, unquotable)
    new_dir, judge, _generator = _both(tmp_path, copy, monkeypatch)
    payload = _alignments(new_dir)
    source_a1 = next(a for a in _source_alignments(copy)["assertions"] if a["id"] == a1)
    run = next(r for r in payload["judge_runs"] if r["id"] == source_a1["judge_run_id"])
    assert run["judge_model"] == MECHANICAL_JUDGE_MODEL and run["verdict"] == "rejected"
    assert run["build_id"] == SOURCE_BUILD_ID and run["rationale"] == "quote not found in source"
    assert payload["stats"]["mechanical_rejects"] == [{"norm_id": NORM_A, "target_id": source_a1["target_id"],
                                                       "source_quote_found": False, "target_quote_found": True}]
    assert [a["id"] for a in payload["assertions"] if a["source_norm_id"] == NORM_A] == [a2]
    assert not any("a quote the norm does not hold" in user for _system, user in judge.calls)
    assert payload["stats"]["candidates"] == 3 and payload["stats"]["carried_candidates"] == 2
    events = [json.loads(line) for line in
              (new_dir / "logs" / "rejudge_alignment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["direction"] for e in events].count("mechanical") == 1
    (ex,) = _alignments_execution(new_dir)
    assert ex["counts"]["mechanical_rejects_count"] == 1


def test_ids_are_kept_and_the_relation_type_follows_the_new_judge(tmp_path, source, monkeypatch):
    a1, a2 = _source_ids(source, NORM_A)
    judge = ScriptedJudge({'"source_quote": "kept and maintained"': "rejected"},
                          corrections={'"source_quote": "A risk log shall be kept"': "supports"})
    new_dir, _judge, _generator = _both(tmp_path, source, monkeypatch, judge=judge)
    before, after = _source_alignments(source), _alignments(new_dir)
    old = {a["id"]: a for a in before["assertions"]}
    new = {a["id"]: a for a in after["assertions"]}
    for assertion_id in (a1, a2):
        assert list(new[assertion_id]) == list(old[assertion_id]), "the key order is kept"
        for key in ("judge_run_id", "mapping_run_id", "source_norm_id", "target_id", "source_quote", "target_quote",
                    "proposed_relation_type", "generator_rationale", "source_evidence_span_ids",
                    "target_evidence_span_ids"):
            assert new[assertion_id][key] == old[assertion_id][key], key
    assert old[a1]["proposed_relation_type"] == "partially_operationalizes"
    assert (new[a1]["relation_type"], new[a1]["judge_verdict"]) == ("supports", "accepted")
    assert (new[a2]["relation_type"], new[a2]["judge_verdict"]) == ("related_to", "rejected")
    assert new[a2]["review_status"] == "needs_review" and new[a2]["rationale"] == "scripted by claude-fake"
    runs = {r["id"]: r for r in after["judge_runs"]}
    assert runs[old[a1]["judge_run_id"]]["corrected_relation_type"] == "supports"
    assert {r["build_id"] for r in after["judge_runs"]} == {SOURCE_BUILD_ID}
    assert {r["judge_model"] for r in after["judge_runs"]} == {"claude-fake"}
    assert after["mapping_runs"][:len(before["mapping_runs"])] == before["mapping_runs"]
    assert after["stats"]["verdicts"] == {"accepted": 2, "rejected": 1, "needs_human_review": 0}
    assert after["stats"]["accepted_by_requirement"]["hleg:transparency"] == 1
    assert after["stats"]["assertions_by_requirement"]["hleg:transparency"] == 2


def test_the_alignments_file_names_its_norms_digest_and_both_usage_blocks(tmp_path, source, monkeypatch, capsys):
    new_dir, judge, generator = _both(tmp_path, source, monkeypatch)
    payload = _alignments(new_dir)
    source_build = _source_alignments(source)["build"]
    norms_path = new_dir / f"norms_{NEW_NAME}.json"
    norms_build = json.loads(norms_path.read_text(encoding="utf-8"))["build"]
    build = payload["build"]
    assert list(payload) == ["build", "assertions", "mapping_runs", "judge_runs", "stats"]
    assert build["alignment_input_sha256"] == sha256_of_file(norms_path)
    pair = load_pair()
    assert (build["hleg_text_sha256"], build["hleg_derivation_record_sha256"]) == (
        pair.text_sha256, pair.record_sha256) == (source_build["hleg_text_sha256"],
                                                  source_build["hleg_derivation_record_sha256"])
    # the norms block as align_hleg carries it: the re-judged norms' build block
    assert {k: build[k] for k in norms_build} == norms_build and build["norms_reference"] is None
    (ex,) = _alignments_execution(new_dir)
    assert build["alignment_usage"] == ex["usage"] == {"generator": generator.usage, "judge": judge.usage}
    assert ex["usage"]["generator"]["calls"] == 1 and ex["usage"]["judge"]["calls"] == 3
    models = build["alignment_models"]
    for key in ("generator_model", "generator_effort", "generator_temperature", "generator_json_mode"):
        assert models[key] == source_build["alignment_models"][key]
    assert (models["judge_model"], models["judge_temperature"]) == ("claude-fake", "0")
    assert models["model_parameters_sha256"] == "environment-parameters-sha256"
    assert build["alignment_sampling"] == {"generator": "N/A", "judge": "0"}
    assert build["alignment_effort"] == {"generator": "high", "judge": "high"}
    assert build["alignment_prompt_version"] == "v3"
    assert build["alignment_rejudge"] == {
        "description": DESCRIPTION, "source_build": SOURCE_NAME,
        "source_alignments_sha256": sha256_of_file(source / ALIGNMENTS_FILE),
        "source_aligned_at": source_build["aligned_at"],
        "carried_generator_usage": source_build["alignment_usage"]["generator"],
        "source_judge_usage": source_build["alignment_usage"]["judge"],
        "source_prompt_version": "v2", "judge_prompt_version": "v3",
    }
    assert list(build)[-1] == "alignment_rejudge"
    # the record
    assert ex["status"] == "done" and ex["covers_steps"] == ["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"]
    assert ex["work_unit"] == "batches" and ex["expected_total"] == 1
    source_record_id = json.loads((source / "publications" / "a1b2c3d4e5f6.json").read_text(
        encoding="utf-8"))["record_id"]
    assert ex["config"] == {"prompt_version": "v3", "source_prompt_version": "v2", "batch_size": 20,
                            "max_in_flight": 1, "cost_stop_usd": 1000.0,
                            "source_build": SOURCE_NAME, "source_record_id": source_record_id,
                            "source_chain_id": "a1b2c3d4e5f6", "judged_by": "claude-fake",
                            "description": DESCRIPTION}
    assert ex["inputs"] == [
        {"input_kind": "norms", "file": f"norms_{NEW_NAME}.json", "sha256": sha256_of_file(norms_path)},
        {"input_kind": "source_alignments", "file": f"../../{SOURCE_NAME}/{ALIGNMENTS_FILE}",
         "sha256": sha256_of_file(source / ALIGNMENTS_FILE)},
        {"input_kind": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(source / "layer1.json")},
        {"input_kind": "hleg_text", "file": TEXT_FILE, "sha256": pair.text_sha256},
        {"input_kind": "hleg_derivation_record", "file": RECORD_FILE, "sha256": pair.record_sha256},
    ]
    assert ex["models"] == fake_cfg().as_public_dict()
    assert ex["prompt_sha256"] == {"generator": prompt_sha256(load_prompt("align_hleg", "v3")),
                                   "judge": prompt_sha256(load_prompt("judge_alignment", "v3"))}
    assert ex["outputs"] == [{"output_kind": "alignments", "file": f"alignments_{NEW_NAME}.json",
                              "sha256": sha256_of_file(new_dir / f"alignments_{NEW_NAME}.json")}]
    assert ex["counts"]["source_verdicts"] == {"accepted": 3, "rejected": 0, "needs_human_review": 0}
    assert ex["counts"]["verdicts"] == {"accepted": 3, "rejected": 0, "needs_human_review": 0}
    assert ex["counts"]["carried_candidates"] == 2 and ex["counts"]["candidates"] == 3
    assert ex["counts"]["norms_total"] == 4 and ex["counts"]["mechanical_rejects_count"] == 0
    events = [json.loads(line) for line in
              (new_dir / "logs" / "rejudge_alignment_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["direction"] for e in events] == ["generator", "judge", "judge", "judge"]
    assert not (new_dir / f"alignments_{NEW_NAME}.checkpoint.jsonl").exists()
    out = capsys.readouterr().out
    this_run = USD_PER_GENERATOR_CALL + 3 * USD_PER_JUDGE_CALL
    assert f"spend: {this_run:.4f} USD at list price in this run, {NORMS_SPEND + this_run:.4f} USD" in out


def test_a_norms_file_not_made_by_the_records_rejudge_is_refused(tmp_path, source, monkeypatch, capsys):
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    new_dir = _new(tmp_path)
    # no norms run: nothing to align
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    assert "run `norms` with the same --out-dir and --name first" in capsys.readouterr().err
    assert not new_dir.exists()
    # a norms file the record's rejudge_norms execution did not write
    _rejudge_norms(monkeypatch, source, new_dir)
    norms_path = new_dir / f"norms_{NEW_NAME}.json"
    norms_path.write_text(norms_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    assert "is not the output of a done rejudge_norms execution of the record" in capsys.readouterr().err
    # the source's own norms file copied in is not the record's either
    shutil.copyfile(source / NORMS_FILE, norms_path)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    assert "is not the output of a done rejudge_norms execution" in capsys.readouterr().err
    assert judge.calls == [] and generator.calls == []
    assert _alignments_execution(new_dir) == [] and not (new_dir / f"alignments_{NEW_NAME}.json").exists()


def test_a_norms_file_rejudged_from_another_source_is_refused(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    _rejudge_norms(monkeypatch, source, new_dir)
    store, record = _record(new_dir)
    record_path = new_dir / "build_records" / f"{record['record_id']}.json"
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    (norms_ex,) = [ex for ex in stored["executions"] if ex["command"] == "rejudge_norms"]
    source_record_id = norms_ex["config"]["source_record_id"]
    norms_ex["config"]["source_record_id"] = "another-source-record"
    record_path.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    assert (f"was re-judged from the source record another-source-record, not from {source_record_id}, the "
            "record of --source") in capsys.readouterr().err
    assert judge.calls == [] and generator.calls == [] and _alignments_execution(new_dir) == []


def _without_run_details(payload, source_run_ids):
    """A payload less what differs between two runs over the same verdicts: the
    clock, this run's usage, the new alignment run's random id and the digest of
    a norms file whose judge runs carry their own clock."""
    payload = json.loads(json.dumps(payload))
    for run in payload["judge_runs"]:
        run.pop("started_at"), run.pop("completed_at")
    renamed = {}
    for run in payload["mapping_runs"]:
        if run["id"] not in source_run_ids:
            renamed[run["id"]] = run["id"] = f"new-{len(renamed)}"
            run.pop("started_at"), run.pop("completed_at")
    for assertion in payload["assertions"]:
        assertion["mapping_run_id"] = renamed.get(assertion["mapping_run_id"], assertion["mapping_run_id"])
    for key in ("aligned_at", "alignment_usage", "alignment_input_sha256"):
        payload["build"].pop(key)
    return payload


def test_the_cost_stop_and_resume_work_for_batches(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    checkpoint = new_dir / f"alignments_{NEW_NAME}.checkpoint.jsonl"
    _rejudge_norms(monkeypatch, source, new_dir)
    # two batches in the norms file's order: (C, D), then (B, A)
    first_judge, first_generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, first_judge, generator=first_generator)
    assert cli.main(_argv("alignments", source, new_dir, NEW_NAME, "0.03", "--batch-size", "2")) == 5
    err = capsys.readouterr().err
    # before the first batch the record had spent the norms run's 0.024 USD; the
    # first batch's generator and judge call brought it to 0.045
    spent = NORMS_SPEND + USD_PER_GENERATOR_CALL + USD_PER_JUDGE_CALL
    assert f"cost stop: spent {spent:.4f} USD of 0.0300 USD" in err
    assert "--resume" in err and "raise --cost-stop" in err and "1 of 2 batches done" in err
    assert _norm_lines(first_generator.calls) == [f"Norm id: {NORM_C}"]
    assert _norm_lines(first_judge.calls) == [f"Norm id: {NORM_C}"]
    store, record = _record(new_dir)
    (ex,) = _alignments_execution(new_dir)
    first_batch = f"batch:0:{NORM_C}"
    assert ex["status"] == "failed" and ex["error"] == f"cost stop: spent {spent:.4f} USD of 0.0300 USD"
    assert ex["completed_keys"] == [first_batch] and ex["usage"]["generator"]["calls"] == 1
    assert [json.loads(line)["batch"] for line in checkpoint.read_text(encoding="utf-8").splitlines()] == [
        first_batch]

    # a resume under a stop the record's spend already reached stops before any call
    blocked_judge, blocked_generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, blocked_judge, generator=blocked_generator)
    assert cli.main(_argv("alignments", source, new_dir, NEW_NAME, "0.04", "--batch-size", "2", "--resume")) == 5
    assert f"cost stop: spent {spent:.4f} USD of 0.0400 USD" in capsys.readouterr().err
    assert blocked_judge.calls == [] and blocked_generator.calls == []

    judge, generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir, NEW_NAME, "1000", "--batch-size", "2", "--resume")) == 0
    assert generator.calls == [] and _norm_lines(judge.calls) == [f"Norm id: {NORM_A}"] * 2
    assert not checkpoint.exists()
    last = store.read(record["record_id"])["executions"][-1]
    assert last["command"] == "rejudge_alignments" and last["status"] == "done"
    assert last["inherited_keys"] == [first_batch] and last["resumes_run_id"] == ex["run_id"]
    assert last["config"]["cost_stop_usd"] == 1000.0
    resumed = _alignments(new_dir)
    # this run's usage only: the resume called the judge twice and no generator
    assert resumed["build"]["alignment_usage"]["judge"]["calls"] == 2
    assert resumed["build"]["alignment_usage"]["generator"]["calls"] == 0
    single_name = "2026-10-17-gpt-fake-high-fake"
    single_dir, _j, _g = _both(tmp_path, source, monkeypatch, name=single_name, under="single",
                               extra=("--batch-size", "2"))
    source_run_ids = {run["id"] for run in _source_alignments(source)["mapping_runs"]}
    assert _without_run_details(resumed, source_run_ids) == _without_run_details(
        _alignments(single_dir, single_name), source_run_ids)


def test_the_source_folder_is_left_unchanged(tmp_path, source, monkeypatch):
    before = folder_state(source)
    new_dir, _judge, _generator = _both(tmp_path, source, monkeypatch)
    assert (new_dir / f"alignments_{NEW_NAME}.json").is_file()
    # a refused run reads the source too
    patch_command(monkeypatch, cli, ScriptedJudge(), generator=ScriptedGenerator())
    assert cli.main(_argv("alignments", source, _new(tmp_path, under="other"))) == 2
    assert folder_state(source) == before
    assert not list(source.rglob("*.checkpoint.jsonl")) and not (source / "logs").exists()


def test_source_mechanical_rejects_invalid_candidates_and_failures_are_carried(tmp_path, source, monkeypatch):
    a_suffix = NORM_A.removeprefix("norm:")
    mechanical_run = {
        "id": f"judgerun:mapping:{a_suffix}:accountability:c3", "type": "JudgeRun", "layer": 3,
        "judge_kind": "mapping", "judge_model": MECHANICAL_JUDGE_MODEL, "verdict": "rejected",
        "rationale": "quote not found in source", "corrected_relation_type": None, "build_id": SOURCE_BUILD_ID,
    }
    reject = {"norm_id": NORM_A, "target_id": "hleg:accountability", "source_quote_found": False,
              "target_quote_found": True}
    invalid = {"norm_id": NORM_A, "reason": "unknown target_id: 'hleg:invented'"}
    failed = {"norm_id": NORM_B, "reason": "generator JSON lacks an 'alignments' list"}

    def with_carried_entries(payload):
        payload["judge_runs"].append(mechanical_run)
        payload["stats"]["mechanical_rejects"].append(reject)
        payload["stats"]["invalid_candidates"].append(invalid)
        payload["stats"]["norms_failed"].append(failed)

    copy = _copy_with_alignments(source, tmp_path, with_carried_entries)
    new_dir, _judge, generator = _both(tmp_path, copy, monkeypatch)
    payload = _alignments(new_dir)
    stats = payload["stats"]
    assert stats["mechanical_rejects"] == [reject] and stats["invalid_candidates"] == [invalid]
    assert stats["norms_failed"] == [failed] and stats["zero_alignment_norms"] == 0
    # B failed at the source and is carried as failed, never aligned again
    assert _norm_lines(generator.calls) == [f"Norm id: {NORM_C}"]
    a1, a2 = (next(a for a in _source_alignments(copy)["assertions"] if a["id"] == i)
              for i in _source_ids(copy, NORM_A))
    c_suffix = NORM_C.removeprefix("norm:")
    assert [r["id"] for r in payload["judge_runs"]] == [
        f"judgerun:mapping:{c_suffix}:transparency:c1", a1["judge_run_id"], a2["judge_run_id"], mechanical_run["id"]]
    assert payload["judge_runs"][-1] == mechanical_run
    assert stats["candidates"] == 4 and stats["carried_candidates"] == 2
    (ex,) = _alignments_execution(new_dir)
    assert ex["work_failures"]["norms_failed"] == 1 and ex["counts"]["mechanical_rejects_count"] == 1


def _refusal_case(name):
    """(the change to the source alignments, the cfg, the words the refusal says)."""
    return {
        "v1": (lambda p: p["build"].__setitem__("alignment_prompt_version", "v1"), None, "DEC-28"),
        "no claimed type": (lambda p: p["assertions"][0].pop("proposed_relation_type"), None,
                            "has no proposed_relation_type"),
        "other norms": (lambda p: p["build"].__setitem__("alignment_input_sha256", "0" * 64), None,
                        "made over a norms file with sha256 " + "0" * 64),
        "other generator": (None, fake_cfg(generator_effort="xhigh"), "alignment generator in generator_effort"),
        "unpaired mechanical run": (lambda p: p["judge_runs"].append(
            {"id": "judgerun:mapping:x:n1:accountability:c1", "judge_model": MECHANICAL_JUDGE_MODEL}), None,
            "has no mechanical reject of its norm"),
        # a judged candidate whose assertion failed the schema: nothing stored to judge again or carry
        "invalid assertion": (lambda p: p["stats"]["invalid_assertions"].append(
            {"norm_id": NORM_A, "target_id": "hleg:accountability", "assertion_id": "align:x:accountability:3",
             "errors": ["'source_evidence_span_ids' is a required property"]}), None,
            "the source holds 1 invalid assertion(s), which this command cannot carry or re-judge"),
        "unknown target": (lambda p: p["assertions"][0].__setitem__("target_id", "hleg:invented"), None,
                           "names 'hleg:invented', which is not one of the seven HLEG requirements"),
        # the generation-time judge read the generator's rationale, which a null cannot give back
        "no generator rationale": (lambda p: p["assertions"][0].__setitem__("generator_rationale", None), None,
                                   "keeps no generator_rationale as text (None)"),
    }[name]


@pytest.mark.parametrize("case", ["v1", "no claimed type", "other norms", "other generator",
                                  "unpaired mechanical run", "invalid assertion", "unknown target",
                                  "no generator rationale"])
@pytest.mark.parametrize("command", ["alignments", "norms"])
def test_a_source_the_alignments_cannot_rejudge_is_refused_before_any_record(tmp_path, source, monkeypatch, capsys,
                                                                             case, command):
    """`norms` runs the same Layer 3 checks before it writes anything (final
    review), so Layer 2 is never paid for a source whose Layer 3 is refused."""
    mutate, cfg, said = _refusal_case(case)
    if command == "norms" and case == "other generator":
        said = "differs from the source's in generator_effort"  # norms_refusal says it first
    src = _copy_with_alignments(source, tmp_path, mutate) if mutate else source
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, cfg=cfg, generator=generator)
    new_dir = _new(tmp_path)
    assert cli.main(_argv(command, src, new_dir)) == 2
    assert said in capsys.readouterr().err
    assert judge.calls == [] and generator.calls == [] and not new_dir.exists()


def test_changed_prompts_another_hleg_text_and_a_missing_generator_price_are_refused(tmp_path, source, monkeypatch,
                                                                                     capsys):
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    new_dir = _new(tmp_path)
    for kind, whose in (("judge_alignment", "judge runs"), ("align_hleg", "alignment runs")):
        patch_command(monkeypatch, cli, judge, generator=generator)
        real = rejudge_alignments.load_prompt
        with monkeypatch.context() as m:
            m.setattr(rejudge_alignments, "load_prompt",
                      lambda k, v, kind=kind, real=real: f"{kind} {v}, edited since the source" if k == kind
                      else real(k, v))
            assert cli.main(_argv("alignments", source, new_dir)) == 2
        assert f"the source's {whose} recorded" in capsys.readouterr().err
    rows = {model: row for model, row in prices().items() if model != GENERATOR_MODEL}
    patch_command(monkeypatch, cli, judge, generator=generator, price_rows=rows)
    assert cli.main(_argv("alignments", source, new_dir)) == 4
    assert f"no price row for the generator '{GENERATOR_MODEL}'" in capsys.readouterr().err
    assert not new_dir.exists()

    # the HLEG pair is checked before anything is written, by `norms` too
    # (final review: Layer 2 is never paid for a source whose Layer 3 is refused)
    copy = _copy_with_alignments(source, tmp_path, lambda p: p["build"].__setitem__("hleg_text_sha256", "1" * 64))
    for command in ("norms", "alignments"):
        patch_command(monkeypatch, cli, judge, generator=generator)
        assert cli.main(_argv(command, copy, new_dir)) == 2
        assert "the source alignments were made on " + "1" * 64 in capsys.readouterr().err
    assert judge.calls == [] and generator.calls == [] and not new_dir.exists()


def test_the_terminal_policy_builds_both_clients(tmp_path, source, monkeypatch):
    built: list = []
    generator = ScriptedGenerator()
    new_dir = _new(tmp_path)
    _rejudge_norms(monkeypatch, source, new_dir)
    policies = patch_command(monkeypatch, cli, ScriptedJudge())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda _cfg, **kw: built.append(kw.get("retry_policy")) or generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 0
    assert policies == [TERMINAL_POLICY] and built == [TERMINAL_POLICY]


# ---- final review fixes (B173)


def test_a_live_rejudge_execution_of_the_other_subcommand_refuses_alignments(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    _rejudge_norms(monkeypatch, source, new_dir)
    store, record = _record(new_dir)
    # a `norms` run still running on the record: a fresh heartbeat
    live = store.start_execution(record["record_id"], command="rejudge_norms",
                                 covers_steps=["LAYER2_STEP1", "LAYER2_STEP2"], argv=[], inputs=[], config={},
                                 expected_total=3, work_unit="groups", checkpoint_file=None, models={},
                                 prompt_sha256={}, sampling={})
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    err = capsys.readouterr().err
    assert f"has a live running execution: {live} (rejudge_norms, heartbeat " in err
    assert judge.calls == [] and generator.calls == [] and _alignments_execution(new_dir) == []
    assert not (new_dir / f"alignments_{NEW_NAME}.json").exists()


def test_layer3_is_refused_under_another_judge_than_the_norms_run(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    _rejudge_norms(monkeypatch, source, new_dir)
    judge, generator = ScriptedJudge(), ScriptedGenerator()
    # the environment names another effort than the norms run's judge
    patch_command(monkeypatch, cli, judge, cfg=fake_cfg(judge_effort="xhigh"), generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    assert "in judge_effort ('xhigh', the norms run 'high'); Layer 3 is judged by the judge of Layer 2" in \
        capsys.readouterr().err
    # the record's execution names another effort than the environment
    _store, record = _record(new_dir)
    record_path = new_dir / "build_records" / f"{record['record_id']}.json"
    stored = json.loads(record_path.read_text(encoding="utf-8"))
    (norms_ex,) = [ex for ex in stored["executions"] if ex["command"] == "rejudge_norms"]
    norms_ex["models"]["judge_effort"] = "low"
    record_path.write_text(json.dumps(stored, indent=1), encoding="utf-8")
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 2
    err = capsys.readouterr().err
    assert f"re-judged norms_{NEW_NAME}.json (execution {norms_ex['run_id']}) in judge_effort ('high', the norms run " \
           "'low')" in err
    assert judge.calls == [] and generator.calls == [] and _alignments_execution(new_dir) == []


def test_alignments_names_its_judge_before_the_first_batch(tmp_path, source, monkeypatch, capsys):
    new_dir = _new(tmp_path)
    _rejudge_norms(monkeypatch, source, new_dir)
    capsys.readouterr()
    seen: list[str] = []
    judge = ScriptedJudge(on_call=lambda _user: seen.append(capsys.readouterr().out))
    generator = ScriptedGenerator()
    patch_command(monkeypatch, cli, judge, generator=generator)
    assert cli.main(_argv("alignments", source, new_dir)) == 0
    assert "judging with claude-fake, effort high, temperature 0, under judge_alignment v3; the source under v2\n" \
        in seen[0]

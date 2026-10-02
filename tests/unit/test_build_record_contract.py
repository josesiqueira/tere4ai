"""The build record contract with the dashboard (plan 2b): schema and fixtures (D-G26)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from tests.fixtures.build_records.regenerate import NOW
from tests.fixtures.build_records.regenerate import _intermediate_scenario as intermediate_scenario
from tests.fixtures.build_records.regenerate import main as regenerate
from tests.unit.test_align_cli import _fakes as align_fakes
from tests.unit.test_align_cli import _norms_file as norms_file
from tests.unit.test_extract_norms_cli import _dump as extract_dump
from tests.unit.test_extract_norms_cli import _fakes as extract_fakes

from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.present import present_record

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "build_record.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "build_records"
EXPECTED = {"parse.json", "resumed_align.json", "legacy_core.json", "legacy_core_b74.json", "intermediate_build.json",
            "list.json"}


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validator_for(definition: str) -> Draft202012Validator:
    schema = _schema()
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


def test_schema_is_valid_and_names_the_definitions():
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert {"execution", "publication", "presented_record", "builds_list", "freeze_manifest_layer2",
            "freeze_manifest_hleg", "reference_block", "publication_manifest", "neo4j_target"} <= set(schema["$defs"])


def test_exactly_the_expected_fixtures_exist():
    assert {p.name for p in FIXTURES.glob("*.json")} == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED - {"list.json"}))
def test_each_record_fixture_validates(name):
    errors = sorted(validator_for("presented_record").iter_errors(json.loads((FIXTURES / name).read_text())),
                    key=lambda e: list(e.path))
    assert not errors, f"{name}: {errors[0].message} at {list(errors[0].path)}"


def test_list_fixture_validates():
    errors = list(validator_for("builds_list").iter_errors(json.loads((FIXTURES / "list.json").read_text())))
    assert not errors, errors[0].message


def test_fixtures_state_the_honesty_rules():
    b74 = json.loads((FIXTURES / "legacy_core_b74.json").read_text())
    align = next(e for e in b74["executions"] if e["command"] == "align_hleg")
    assert align["status"] == "running" and align["liveness"] == "unknown"
    assert align["progress"]["expected_total"] is None and align["progress"]["completed"] == 15
    assert align["provenance"]["run_id"] == "unavailable" and align["provenance"]["inherited_keys"] == "derived"
    assert b74["publication"] is None and b74["steps"]["P.1"] == "not_recorded"
    core = json.loads((FIXTURES / "legacy_core.json").read_text())
    assert core["provenance"]["publication"] == "derived" and core["publication"]["published_at"] is None
    assert core["steps"]["P.1"] == core["steps"]["P.2"] == "not_recorded", "a legacy chain record proves no load"
    assert "predates the load" in core["reasons"]["P.2"] and "G1 to G6" in core["reasons"]["P.1"]
    mid = json.loads((FIXTURES / "intermediate_build.json").read_text())
    parent = mid["parent_record_id"]
    assert all(mid["steps"][s] == "inherited" and mid["reasons"][s] == f"done in record {parent}"
               for s in ("L0.1", "L1.1", "L2.1", "L2.2"))
    assert all(mid["steps"][s] == "done" for s in ("L2.4", "L3.1", "L3.2", "L3.3"))
    assert mid["steps"]["P.1"] == mid["steps"]["P.2"] == "not_started" and mid["publication"] is None
    assert mid["depends_on_state"]["P.1"] == "done" and mid["depends_on_state"]["P.2"] == "not_started"
    resumed = json.loads((FIXTURES / "resumed_align.json").read_text())
    ex = resumed["executions"][-1]
    assert ex["resumes_run_id"] == "run2prev0000" and ex["inherited_from"] == "run2prev0000"
    assert ex["progress"] == {"completed": 5, "expected_total": 5, "work_unit": "batches", "inherited": 3, "source": "record"}


def test_fixtures_are_byte_stable_against_the_presenter():
    produced = regenerate()
    for name, text in produced.items():
        assert (FIXTURES / name).read_text(encoding="utf-8") == text, f"{name} drifted: run python -m tests.fixtures.build_records.regenerate and commit"


def test_the_usage_of_a_role_documents_the_two_completeness_counts():
    """B91 (spec F D-F26 (g)): requests sent and replies with usage, optional so older records validate."""
    schema = _schema()
    role = schema["$defs"]["role_usage"]
    # final review A3 adds a sixth optional count, requests_refused, and spec F
    # D-F32 a seventh, requests_rejected_before_processing
    assert set(role["properties"]) == {"calls", "input_tokens", "output_tokens", "requests_sent",
                                       "replies_with_usage", "requests_refused",
                                       "requests_rejected_before_processing"}
    assert list(validator_for("usage_by_role").iter_errors({"generator": {"requests_refused": -1}}))
    assert list(validator_for("usage_by_role").iter_errors(
        {"generator": {"requests_rejected_before_processing": -1}}))
    # the description names the seven statuses and the subset relation for a reader
    assert "HTTP 400, 401, 403, 404, 413, 422 or 429" in role["description"]
    assert "subset of requests_refused" in role["description"]
    assert role.get("required", []) == []
    for definition in ("execution", "presented_execution"):
        assert schema["$defs"][definition]["properties"]["usage"] == {"$ref": "#/$defs/usage_by_role"}
    by_role = validator_for("usage_by_role")
    assert not list(by_role.iter_errors(None))
    assert not list(by_role.iter_errors({"generator": {"calls": 1}, "judge": {}}))
    assert list(by_role.iter_errors({"generator": {"requests_sent": -1}}))
    assert list(by_role.iter_errors({"generator": 3}))


def test_the_resumed_align_mock_data_carries_an_incomplete_failed_attempt():
    resumed = json.loads((FIXTURES / "resumed_align.json").read_text())
    failed, done = (e for e in resumed["executions"] if e["command"] == "align_hleg")
    assert failed["usage"]["generator"]["requests_sent"] == 4
    assert failed["usage"]["generator"]["replies_with_usage"] == 3
    assert done["usage"]["judge"]["requests_sent"] == done["usage"]["judge"]["replies_with_usage"] == 2


def test_the_resumed_align_mock_data_carries_a_request_rejected_before_processing():
    """Spec F D-F32: the resumed attempt's generator met one 429 and retried it,
    so the dashboard's copy can test a line with the seventh count above 0;
    the failed attempt's timeout is refused nowhere."""
    resumed = json.loads((FIXTURES / "resumed_align.json").read_text())
    failed, done = (e for e in resumed["executions"] if e["command"] == "align_hleg")
    generator = done["usage"]["generator"]
    assert (generator["requests_sent"], generator["replies_with_usage"], generator["requests_refused"],
            generator["requests_rejected_before_processing"]) == (3, 2, 1, 1)
    for execution in (failed, done):
        for role in execution["usage"].values():
            assert role["requests_rejected_before_processing"] <= role["requests_refused"] <= role["requests_sent"]
    assert failed["usage"]["generator"]["requests_rejected_before_processing"] == 0


def test_the_contract_carries_a_record_with_declared_parameters_and_older_ones_stay_valid():
    """B99 (spec F D-F29): the declared keys are documented, and the mock data
    hold one execution of the new shape beside the older ones."""
    schema = _schema()
    defs = schema["$defs"]
    assert set(defs["execution_sampling"]["properties"]) == {
        "generator", "judge", "generator_temperature", "judge_temperature", "generator_effort", "judge_effort",
        "generator_json_mode"}
    # B99 final review: the models line holds the eight keys of ModelConfig.as_public_dict()
    models_keys = {"generator_model", "judge_model", "generator_effort", "judge_effort", "generator_temperature",
                   "judge_temperature", "generator_json_mode", "model_parameters_sha256"}
    assert set(defs["execution_models"]["properties"]) == models_keys
    record = json.loads((FIXTURES / "intermediate_build.json").read_text(encoding="utf-8"))
    last = [e for e in record["executions"] if e["run_id"] == "run4align000"][0]
    # review X-C1: the dashboard reads the declared temperature under <role>_temperature
    assert last["sampling"] == {"generator": "N/A", "judge": "N/A", "generator_temperature": "N/A",
                                "judge_temperature": "N/A", "generator_effort": "xhigh",
                                "judge_effort": "xhigh", "generator_json_mode": "sent"}
    assert last["models"]["model_parameters_sha256"] == "6" * 64 and set(last["models"]) == models_keys
    bad = {**last, "sampling": {**last["sampling"], "generator_effort": 5}}
    validator = Draft202012Validator({**schema, "$ref": "#/$defs/presented_execution"})
    assert list(validator.iter_errors(last)) == [] and list(validator.iter_errors(bad)) != []
    # review T-M3: present.py _sampling_with_effort gives null for a role a dump's effort dict lacks
    missing_role = {**last, "sampling": {"generator": "0", "judge": "0", "generator_effort": "xhigh",
                                         "judge_effort": None}}
    assert list(validator.iter_errors(missing_role)) == []


# ---- B102 task 3 (B79 item 16, ruling R3)

# Each pair holds a base definition and the derived one that copies its
# property list. The derived executions list holds presented executions,
# so that one reference differs by design.
SHARED_PAIRS = [("execution", "presented_execution"), ("stored_record", "presented_record"),
                ("publication", "publication_manifest")]
DERIVED_REFS = {"#/$defs/execution": "#/$defs/presented_execution"}


def _as_derived(definition):
    if isinstance(definition, dict):
        return {k: DERIVED_REFS.get(v, v) if k == "$ref" else _as_derived(v) for k, v in definition.items()}
    if isinstance(definition, list):
        return [_as_derived(v) for v in definition]
    return definition


@pytest.mark.parametrize(("base", "derived"), SHARED_PAIRS)
def test_every_shared_key_of_a_copied_property_list_has_the_same_definition(base, derived):
    defs = _schema()["$defs"]
    base_props, derived_props = defs[base]["properties"], defs[derived]["properties"]
    assert set(base_props) <= set(derived_props), f"{derived} lacks {set(base_props) - set(derived_props)}"
    for key, definition in base_props.items():
        assert derived_props[key] == _as_derived(definition), f"{base}.{key} and {derived}.{key} differ"
    assert set(defs[base]["required"]) <= set(defs[derived]["required"])


def test_progress_source_is_record_or_checkpoint():
    progress = {"completed": 1, "expected_total": 2, "work_unit": "batches", "inherited": 0}
    for source in ("record", "checkpoint"):
        assert not list(validator_for("progress").iter_errors({**progress, "source": source}))
    assert list(validator_for("progress").iter_errors({**progress, "source": "other"}))


# ---- B102 task 3 (B79 item 6)


def _command_execution(dump_dir, alias, command):
    store = BuildRecordStore(dump_dir)
    presented = present_record(store.read(store.resolve(alias)), dump_dir, NOW, None, store)
    errors = list(validator_for("presented_record").iter_errors(presented))
    assert not errors, f"{command}: {errors[0].message} at {list(errors[0].path)}"
    return next(e for e in presented["executions"] if e["command"] == command)


def test_records_the_commands_write_match_the_contract(tmp_path, monkeypatch):
    """The extract and align commands, run with the fakes of their CLI tests,
    write records that present and validate, with the execution keys and the
    count keys the mock data carry, so the counts regenerate.py writes by
    hand cannot part from what the commands write."""
    import tere4ai.align_hleg.__main__ as align_cli
    import tere4ai.extract_norms.__main__ as extract_cli

    extract_dir, align_dir, regenerated_dir = (tmp_path / d for d in ("extract", "align", "regenerated"))
    for d in (extract_dir, align_dir, regenerated_dir):
        d.mkdir()
    extract_fakes(monkeypatch, extract_cli, [])
    dump = extract_dump(extract_dir)
    assert extract_cli.main(["--nodes", "eu-ai-act:article-9,eu-ai-act:article-10", "--dump", str(dump),
                             "--out", str(extract_dir / "norms_test.json")]) == 0
    align_fakes(monkeypatch, align_cli, [])
    norms_path, layer1, _ = norms_file(align_dir, 3)
    assert align_cli.main(["--norms", str(norms_path), "--dump", str(layer1),
                           "--out", str(align_dir / "alignments_test.json"), "--batch-size", "2"]) == 0
    extract = _command_execution(extract_dir, "test", "extract_norms")
    align = _command_execution(align_dir, "test", "align_hleg")

    committed_align = [e for name in ("intermediate_build.json", "resumed_align.json")
                       for e in json.loads((FIXTURES / name).read_text(encoding="utf-8"))["executions"]
                       if e["command"] == "align_hleg" and e["status"] == "done"]
    assert committed_align
    for execution in committed_align:
        assert set(align) == set(execution)
        assert set(align["counts"]) == set(execution["counts"])
    # No committed file holds a recorded extract execution (intermediate_build.json
    # is the descendant record); the one regenerate.py writes is the published
    # parent of scenario (e), presented for list.json.
    _, parent, _ = intermediate_scenario(regenerated_dir, "0" * 12)
    regenerated = next(e for e in parent["executions"] if e["command"] == "extract_norms")
    assert set(extract) == set(regenerated)
    assert set(extract["counts"]) == set(regenerated["counts"])

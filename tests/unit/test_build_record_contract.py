"""The build record contract with the dashboard (plan 2b): schema and fixtures (D-G26)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from tests.fixtures.build_records.regenerate import main as regenerate

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

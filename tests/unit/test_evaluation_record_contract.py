"""The evaluation record contract with the dashboard (plan 3b): schema and fixtures (D-G33)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "evaluation_record.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "evaluation_records"
EXPECTED = {
    "list.json", "e1_sample.json", "e1_labelling.json", "e1_analysis.json", "e6_run.json",
    "e6_run_repeat.json", "e6_run_other_build.json", "e6_comparison.json", "e6_legacy_summary.json",
    "e1_legacy_sheet.json", "e6_offline.json", "e6_partial.json", "e6_failed.json", "e6_resumed.json",
    "e6_copy_missing.json",
}


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validator_for(definition: str) -> Draft202012Validator:
    schema = _schema()
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_is_valid_and_names_the_definitions():
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert {"stored_record", "presented_record", "summary", "evaluations_list", "outcome", "build_identity",
            "relations", "output_ref", "presented_output"} <= set(schema["$defs"])


def test_exactly_the_expected_fixtures_exist():
    assert {p.name for p in FIXTURES.glob("*.json")} == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED - {"list.json"}))
def test_each_record_fixture_validates(name):
    errors = sorted(validator_for("presented_record").iter_errors(_fixture(name)), key=lambda e: list(e.path))
    assert not errors, f"{name}: {errors[0].message} at {list(errors[0].path)}"


def test_list_fixture_validates_and_states_its_order():
    listed = _fixture("list.json")
    assert not list(validator_for("evaluations_list").iter_errors(listed))
    assert "records without a date last" in listed["order"]
    keys = [g["build_key"] for g in listed["groups"]]
    assert keys[-1] == "unknown", "the group with no build identity is last"


def test_fixtures_state_the_honesty_rules():
    legacy = _fixture("e6_legacy_summary.json")
    assert legacy["origin"] == "legacy" and legacy["synthesised"] is True
    assert legacy["outcome"] is None and legacy["provenance"]["outcome"] == "unavailable"
    assert legacy["build"]["base_build_id"] is None and legacy["reasons"]["build"].startswith("not recorded")
    assert legacy["provenance"]["build"] == "unavailable"
    assert legacy["started_at"] is None and legacy["provenance"]["started_at"] == "unavailable"
    assert all(o["copy_state"] == "not_kept" for o in legacy["outputs"])
    sheet = _fixture("e1_legacy_sheet.json")
    assert sheet["kind"] == "sample" and sheet["build"]["base_build_id"] == "build-3b753e5e9297"
    assert sheet["counts"] == {"items": 50, "labelled": 0} and sheet["provenance"]["counts"] == "derived"
    partial = _fixture("e6_partial.json")
    assert partial["outcome"]["status"] == "partial"
    assert set(partial["outcome"]["completed_items"]) < set(partial["outcome"]["intended_items"])
    failed = _fixture("e6_failed.json")
    assert failed["outcome"]["status"] == "failed" and failed["outcome"]["error"]
    assert failed["ended_at"] is not None
    resumed = _fixture("e6_resumed.json")
    assert resumed["relations"]["resumes_record_id"] == "e6a000000001"
    missing = _fixture("e6_copy_missing.json")
    states = {o["role"]: o["copy_state"] for o in missing["outputs"]}
    assert states == {"summary": "missing", "checkpoint": "drifted"}
    assert missing["outcome"]["status"] == "completed", "a lost copy never rewrites the outcome"
    analysis = _fixture("e1_analysis.json")
    assert analysis["relations"]["sample_id"] == "sample-a1b2c3d4e5f6"
    assert analysis["relations"]["labelling_record_ids"] == ["e1b000000001"]
    assert "sample estimate" in " ".join(analysis["notes"])
    repeat = _fixture("e6_run_repeat.json")
    assert repeat["relations"]["repeat_of"] == "e6a000000001"
    comparison = _fixture("e6_comparison.json")
    assert comparison["relations"]["compares"] == ["e6a000000001", None] and "run_b is named by no record" in comparison["notes"]
    other = _fixture("e6_run_other_build.json")
    assert other["build"]["publication"] is None and other["build"]["base_build_id"] == "build-c"
    offline = _fixture("e6_offline.json")
    assert offline["config"]["mode"] == "offline" and offline["models"] is None


def test_fixtures_are_byte_stable(tmp_path):
    from tests.fixtures.evaluation_records.regenerate import main as regenerate

    for path in regenerate(tmp_path):
        assert path.read_bytes() == (FIXTURES / path.name).read_bytes(), f"{path.name} drifted: rerun regenerate"

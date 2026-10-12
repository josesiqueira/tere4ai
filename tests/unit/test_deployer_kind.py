"""B160: the deployer's legal form is the fact deployer_kind; "actor" keeps no
technical meaning (spec G D-G80 (21)). Kept records keep the old word
(B158 ruling R9): the prompts v1 to v7, the benchmark gold features
elicited by prompts v1 and v2, and the recorded demo sessions."""

import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from tests.unit.test_fria import _credit_scorer_features, dump  # noqa: F401

from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION, features_of_record
from tere4ai.mcp_server.classify import classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "system_features.schema.json").read_text(encoding="utf-8"))
PROMPTS = ROOT / "prompts" / "elicit_features"
OLD = "deployer_actor"
KEPT_AS_RECORDED = (
    "demo/mcp_demo/sessions/",
    "tests/fixtures/demo_sessions/",
    "eval/gold/benchmark_features.json",
    "eval/gold/benchmark_features_full.json",
    "CHANGELOG.md",
) + tuple(f"prompts/elicit_features/v{n}.md" for n in range(1, 8))
# Ruling R6: the one live reader of facts stored before B160 names the old key.
READS_KEPT_RECORDS = ("src/tere4ai/elicit_features/elicitor.py",)


def test_the_schema_names_deployer_kind_only():
    props = SCHEMA["properties"]
    assert "deployer_kind" in props and OLD not in props
    assert props["deployer_kind"]["type"] == ["string", "null"]


def test_the_old_key_is_refused_by_the_schema():
    validator = Draft202012Validator(SCHEMA)
    described = {"description": "A spam filter for a small company's inboxes."}
    assert validator.is_valid({**described, "deployer_kind": "private_company"})
    assert not validator.is_valid({**described, OLD: "private_company"})


def test_v8_is_v7_with_the_fact_renamed_and_the_default():
    v7 = (PROMPTS / "v7.md").read_text(encoding="utf-8")
    v8 = (PROMPTS / "v8.md").read_text(encoding="utf-8")
    assert v7.count(OLD) == 2
    assert v8 == v7.replace(OLD, "deployer_kind")
    assert DEFAULT_PROMPT_VERSION == "v8"


def test_no_live_file_names_the_old_key():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "grep", "-lz", OLD], capture_output=True, text=True, check=False)
    except OSError:
        pytest.skip("git is not available")
    if out.returncode not in (0, 1):
        pytest.skip("not a git checkout")
    naming = [p for p in out.stdout.split("\0")
              if p and not p.startswith(KEPT_AS_RECORDED) and p not in READS_KEPT_RECORDS
              and p != "tests/unit/test_deployer_kind.py"]
    assert naming == []


def test_the_classifier_reads_neither_key(dump):  # noqa: F811
    """The deployer's legal form is context only: the risk category and the
    FRIA block are the same whatever deployer_kind says, and without it. The
    old key is no longer a fact the schema knows, so the classifier refuses
    it at the boundary as any unknown key, before any rule runs."""
    answers = [
        classify_ai_system(_credit_scorer_features(**extra), dump)["answer"]
        for extra in ({"deployer_kind": "public_authority"}, {"deployer_kind": "private_company"}, {})
    ]
    assert answers[0]["risk_category"] == "high_risk"
    for answer in answers[1:]:
        assert answer["risk_category"] == answers[0]["risk_category"]
        assert answer["fria"] == answers[0]["fria"]
    refused = classify_ai_system(_credit_scorer_features(**{OLD: "public_authority"}), dump)
    assert refused["status"] == "rejected_as_unsupported"
    assert any(OLD in fact for fact in refused["missing_facts"])


def test_features_of_record_reads_the_old_key_as_deployer_kind():
    """Ruling R6: facts stored before B160 are read through one function."""
    stored = {"description": "A credit scorer for a bank.", OLD: "private_company"}
    assert features_of_record(stored) == {"description": "A credit scorer for a bank.",
                                          "deployer_kind": "private_company"}
    assert stored == {"description": "A credit scorer for a bank.", OLD: "private_company"}
    current = {"description": "A credit scorer for a bank.", "deployer_kind": "individual"}
    assert features_of_record(current) == current
    both = {"description": "x" * 10, OLD: "public_authority", "deployer_kind": "individual"}
    assert features_of_record(both) == {"description": "x" * 10, "deployer_kind": "individual"}
    assert OLD in both

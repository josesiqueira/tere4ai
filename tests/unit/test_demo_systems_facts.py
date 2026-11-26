"""The demo systems' facts are the schema's facts (B184 Task 8).

scripts/record_mcp_demo.py, scripts/make_compliance.py and
scripts/make_prohibition.py hold the facts of the demo systems, translated by
the plan's table "One translation per system". These tests read the scripts'
data only and classify it in process from data/graph_dumps: no server, no
model, no network.
"""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tere4ai.elicit_features.elicitor import schema_flag_names
from tere4ai.mcp_server.classify import classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"


def _load(name: str) -> Any:
    # make_compliance and make_prohibition read an output path from argv at
    # import; pytest's own argv must not reach them.
    saved = sys.argv
    sys.argv = [name]
    try:
        spec = importlib.util.spec_from_file_location(f"_demo_{name}", SCRIPTS / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    return module


@pytest.fixture(scope="module")
def recorder() -> Any:
    return _load("record_mcp_demo")


@pytest.fixture(scope="module")
def compliance() -> Any:
    return _load("make_compliance")


@pytest.fixture(scope="module")
def prohibition() -> Any:
    return _load("make_prohibition")


def _system(recorder: Any, key: str) -> dict[str, Any]:
    return next(s for s in recorder.SYSTEMS if s["key"] == key)


def _every_features(recorder: Any, compliance: Any, prohibition: Any) -> list[tuple[str, dict]]:
    out = [
        (f"record_mcp_demo {s['key']} round {i + 1}", f)
        for s in recorder.SYSTEMS
        for i, f in enumerate(s["features_rounds"])
    ]
    out.append(("make_compliance", compliance.FEATURES))
    out.append(("make_prohibition round 1", prohibition.ROUND_1))
    out.append(("make_prohibition round 2", prohibition.ROUND_2))
    return out


def test_demo_scripts_name_only_schema_facts(recorder, compliance, prohibition):
    known = set(schema_flag_names())
    unknown = [
        (where, fact)
        for where, features in _every_features(recorder, compliance, prohibition)
        for fact in features["flags"]
        if fact not in known
    ]
    unknown += [("EVERY_FACT", f) for f in recorder.EVERY_FACT if f not in known]
    for module in (compliance, prohibition):
        unknown += [
            (module.__name__, field)
            for field, _value, _why in module.ASSUMPTIONS
            if field.startswith("flags.") and field.removeprefix("flags.") not in known
        ]
    assert unknown == []


def test_every_fact_names_the_new_facts_and_leaves_the_purpose_absent(recorder):
    new = {f for f in schema_flag_names() if f.startswith("annex_iii_")}
    new |= {"narrow_procedural_task", "preparatory_task"}
    assert new <= set(recorder.EVERY_FACT)
    # The plan's table: law_enforcement_purpose stays absent unless a system
    # sets real_time_remote_biometric_public true, and none does.
    assert "law_enforcement_purpose" not in recorder.EVERY_FACT


def test_the_abstention_system_leaves_work_relationships_absent(recorder):
    abstention = _system(recorder, "abstention")
    flags = abstention["features_rounds"][-1]["flags"]
    assert "annex_iii_4b_work_relationships" not in flags
    assert flags["annex_iii_4a_recruitment"] is False
    for point in ("3", "5", "6", "7", "8"):
        uses = [f for f in schema_flag_names() if f.startswith(f"annex_iii_{point}")]
        assert all(flags[f] is False for f in uses), point
    assert flags["creditworthiness_evaluation"] is False
    assert flags["life_health_insurance_risk_pricing"] is False
    assert flags["narrow_procedural_task"] is False
    assert flags["preparatory_task"] is False


def test_moodwatch_monitors_workers_and_spamguard_is_a_narrow_procedural_task(
    recorder, prohibition
):
    for flags in (
        _system(recorder, "unacceptablerisk")["features_rounds"][-1]["flags"],
        prohibition.ROUND_2["flags"],
    ):
        assert flags["annex_iii_4b_work_relationships"] is True
        assert flags["annex_iii_4a_recruitment"] is False
    spamguard = _system(recorder, "minimalrisk")["features_rounds"][-1]["flags"]
    assert spamguard["narrow_procedural_task"] is True
    assert spamguard["preparatory_task"] is False


@pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")
def test_each_demo_system_answers_its_level_without_a_fact_conflict(
    recorder, compliance, prohibition
):
    dump = json.loads(DUMP_PATH.read_text(encoding="utf-8"))
    expected = {
        "minimalrisk": ("minimal_risk", "not_applicable"),
        "limitedrisk": ("limited_risk", "potentially_applicable"),
        "highrisk": ("high_risk", "potentially_applicable"),
        "unacceptablerisk": ("unacceptable_risk", "potentially_applicable"),
        "abstention": ("high_risk", "requires_human_review"),
    }
    got = {}
    conflicts = {}
    for system in recorder.SYSTEMS:
        envelope = classify_ai_system(system["features_rounds"][-1], dump)
        got[system["key"]] = (envelope["answer"]["risk_category"], envelope["status"])
        conflicts[system["key"]] = envelope["answer"]["fact_conflicts"]
    for name, features in (
        ("make_compliance", compliance.FEATURES),
        ("make_prohibition", prohibition.ROUND_2),
    ):
        envelope = classify_ai_system(features, dump)
        got[name] = (envelope["answer"]["risk_category"], envelope["status"])
        conflicts[name] = envelope["answer"]["fact_conflicts"]
    expected["make_compliance"] = expected["highrisk"]
    expected["make_prohibition"] = expected["unacceptablerisk"]
    assert got == expected
    assert all(c == [] for c in conflicts.values()), conflicts

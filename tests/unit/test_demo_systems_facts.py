"""The demo systems' facts are the schema's facts (B184 Task 8).

scripts/record_mcp_demo.py, scripts/make_compliance.py and
scripts/make_prohibition.py hold the facts of the demo systems, translated by
the plan's table "One translation per system". These tests read the scripts'
data only and classify it in process from data/graph_dumps: no server, no
model, no network.
"""

import importlib.util
import json
import re
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


# --- The copies of each demo system agree (B184 Task 8, fix round 1, M2) ----
#
# For each demo system, the 25 listed-use facts of Annex III and the two
# Article 6(3) facts must have one value in every copy: the last round of
# scripts/record_mcp_demo.py, the make_* script that holds the system, and the
# web preset ("unknown" in a preset counts as absent).

PRESETS_PATH = ROOT / "web" / "src" / "app" / "(demo)" / "assess" / "presets.ts"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"


def _listed_use_facts() -> list[str]:
    flags = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["flags"]
    return [n for n, d in flags["properties"].items() if "x-annex-iii-area" in d]


ARTICLE_6_3_FACTS = ("narrow_procedural_task", "preparatory_task")


def compared_facts() -> list[str]:
    return [*_listed_use_facts(), *ARTICLE_6_3_FACTS]


def preset_flags(text: str) -> dict[str, dict[str, bool]]:
    """Each preset's facts as the page would send them: allFalse sets every
    key false, law_enforcement_purpose unknown, then the overrides; an
    "unknown" value is left out (absent)."""
    body = text[text.index("export const SCENARIO_PRESETS"):]
    found: dict[str, dict[str, bool]] = {}
    for match in re.finditer(r'id: "([^"]+)".*?flags: allFalse\(\{(.*?)\}\),', body, re.S):
        preset_id, overrides = match.groups()
        values = {name: "false" for name in schema_flag_names()}
        values["law_enforcement_purpose"] = "unknown"
        overrides = re.sub(r"/\*.*?\*/", "", overrides, flags=re.S)
        for name, value in re.findall(r'(\w+): "(true|false|unknown)"', overrides):
            values[name] = value
        found[preset_id] = {k: v == "true" for k, v in values.items() if v != "unknown"}
    return found


def copies_of_each_system(recorder: Any, compliance: Any, prohibition: Any, presets: dict) -> dict:
    def last(key: str) -> dict:
        return _system(recorder, key)["features_rounds"][-1]["flags"]

    return {
        "SpamGuard": {"record minimalrisk": last("minimalrisk"), "preset spamguard": presets["spamguard"]},
        "ShopBot": {"record limitedrisk": last("limitedrisk"), "preset shopbot": presets["shopbot"]},
        "CredScore": {
            "record highrisk": last("highrisk"),
            "make_compliance": compliance.FEATURES["flags"],
            "preset credscore": presets["credscore"],
        },
        "MoodWatch": {
            "record unacceptablerisk": last("unacceptablerisk"),
            "make_prohibition ROUND_2": prohibition.ROUND_2["flags"],
            "preset moodwatch": presets["moodwatch"],
        },
        "MoodWatch driver fatigue variant": {
            "record abstention": last("abstention"),
            "preset moodwatch-safety": presets["moodwatch-safety"],
        },
    }


# Differences that predate B184 on facts the card did not translate (the plan's
# table leaves them as recorded); they go to the owner's list, not fixed here.
DIFFERENCES_BEFORE_B184 = {
    ("MoodWatch", "biometric_categorisation_sensitive_or_protected_attributes"),
    ("MoodWatch driver fatigue variant", "biometric_categorisation_sensitive_or_protected_attributes"),
    ("MoodWatch driver fatigue variant", "critical_infrastructure_safety"),
}


def differences_between_copies(copies: dict) -> list[tuple[str, str, dict]]:
    out = []
    for system, by_copy in copies.items():
        for fact in compared_facts():
            values = {where: flags.get(fact, "absent") for where, flags in by_copy.items()}
            if len(set(map(str, values.values()))) > 1 and (system, fact) not in DIFFERENCES_BEFORE_B184:
                out.append((system, fact, values))
    return out


def test_each_demo_system_has_one_value_per_listed_use_in_every_copy(recorder, compliance, prohibition):
    presets = preset_flags(PRESETS_PATH.read_text(encoding="utf-8"))
    copies = copies_of_each_system(recorder, compliance, prohibition, presets)
    assert differences_between_copies(copies) == []


def test_the_differences_before_b184_are_still_differences(recorder, compliance, prohibition):
    # An entry of the allowance that no longer differs must leave it.
    presets = preset_flags(PRESETS_PATH.read_text(encoding="utf-8"))
    copies = copies_of_each_system(recorder, compliance, prohibition, presets)
    for system, fact in DIFFERENCES_BEFORE_B184:
        values = {flags.get(fact, "absent") for flags in copies[system].values()}
        assert len(set(map(str, values))) > 1, (system, fact)


# --- The demo copy says what the recording shows (fix round 1, I1) ---------

SESSIONS_DIR = ROOT / "demo" / "mcp_demo" / "sessions"


def _session(key: str) -> list[dict]:
    path = SESSIONS_DIR / f"{key}.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _last_answer(session: list[dict], tool: str) -> dict | None:
    found = [r for r in session if r["tool"] == tool]
    return found[-1]["envelope"] if found else None


def claims_the_recording_contradicts(text: str, session: list[dict]) -> list[str]:
    """Checks a passage of demo copy against the session's own fields."""
    out: list[str] = []
    classify = _last_answer(session, "classify_ai_system") or {}
    requirements = (_last_answer(session, "get_applicable_requirements") or {}).get("answer") or {}
    summary = requirements.get("summary") or {}
    trace = (_last_answer(session, "trace_implementation") or {}).get("answer") or {}
    lowered = " ".join(text.lower().split())
    if re.search(r"\brefus\w*", lowered) and "tag" in lowered and not trace.get("invalid_tags"):
        out.append("claims a refused tag; the session has none")
    if re.search(r"(still|remains) in (the )?human review|human review queue", lowered) and not (
        summary.get("needs_human_review_total")
    ):
        out.append("claims a norm in human review; the session counts none")
    if "single fact" in lowered and len(classify.get("missing_facts") or []) != 1:
        out.append("claims a single missing fact; the session names another number")
    for number in re.findall(r"(\d+) judge-accepted requirements", lowered):
        if int(number) != summary.get("returned"):
            out.append(f"claims {number} judge-accepted requirements; the session returned {summary.get('returned')}")
    for number in re.findall(r"across (\d+) articles", lowered):
        if int(number) != len(summary.get("per_article") or {}):
            out.append(f"claims {number} articles; the session has {len(summary.get('per_article') or {})}")
    for number in re.findall(r"(\d+) applicable norms", lowered):
        if int(number) != (trace.get("summary") or {}).get("applicable_norms"):
            out.append(f"claims {number} applicable norms; the trace has another number")
    return out


def _what_should_happen(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.index("## What should happen"):]


def test_the_demo_blurbs_say_what_each_recording_shows():
    index = _load("build_mcp_demo_index")
    found = {
        system["key"]: claims_the_recording_contradicts(system["blurb"], _session(system["key"]))
        for system in index.SYSTEMS
    }
    assert {k: v for k, v in found.items() if v} == {}


def test_the_project_prompts_say_what_each_recording_shows():
    projects = ROOT / "demo" / "mcp_demo" / "projects"
    found = {
        name: claims_the_recording_contradicts(_what_should_happen(projects / name / "PROMPT.md"), _session(key))
        for name, key in (("shopbot", "limitedrisk"), ("credscore", "highrisk"))
    }
    assert {k: v for k, v in found.items() if v} == {}


def test_a_blurb_claiming_a_refused_tag_fails_on_a_session_without_one():
    claim = "one tag the server refuses because the norm behind it is still in human review"
    assert claims_the_recording_contradicts(claim, _session("limitedrisk"))
    session = [
        {"tool": "trace_implementation", "envelope": {"answer": {"invalid_tags": [{"norm_id": "x"}]}}},
        {"tool": "get_applicable_requirements", "envelope": {"answer": {"summary": {"needs_human_review_total": 1}}}},
    ]
    assert claims_the_recording_contradicts(claim, session) == []

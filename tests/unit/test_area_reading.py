"""One Annex III reading (B185, spec G D-G92 (2), (3), (5), (ii), (vi), (vii), DEC-33).

A listed use that is true decides the Annex III point, and the domain's point
is read only when no listed use of any point is true. A level that rests on
the area alone says so, is marked for human review and carries the point in
annex_iii_area_unconfirmed; the routes, the Section B check, the section
fact, the citations and the dates read only confirmed listed uses. The cases
are the table of area cases (tests/unit/area_cases.py). Offline: the
published Layer 1 dump and the norms on disk, skipped when absent.

@implements: DEC-33
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.area_cases import (
    AREA_ALONE_POINT_1,
    AREA_ALONE_POINT_3,
    AREA_CASES,
    AREA_RULED_OUT_POINT_3,
    POINT_3,
    POINT_4,
    SCOPE_UNCONFIRMED_POINT_3,
    _features,
)
from tests.unit.b184_cases import all_false

from tere4ai.mcp_server.application_dates import ROUTE_ANNEX_I, ROUTE_ANNEX_III
from tere4ai.mcp_server.classify import (
    ANNEX_I_SECTION_UNKNOWN_FACT,
    classify_ai_system,
    read_annex_iii,
    route_of,
)
from tere4ai.mcp_server.requirements import (
    SECTION_B_ANNEX_III_UNKNOWN_MESSAGE,
    get_applicable_requirements,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

ANSWER_KEYS = ("risk_category", "annex_iii_category", "annex_iii_area_unconfirmed", "high_risk_routes",
               "annex_i_section", "transparency_duties", "area_conflicts", "article_6_3_exception_candidate")

# The definite levels in order; undetermined is not a level (facts missing)
# and is compared with nothing.
LEVEL_RANK = {"minimal_risk": 0, "limited_risk": 1, "high_risk": 2, "unacceptable_risk": 3}


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    if not NORMS_PATH.is_file():
        pytest.skip("norms_core.json not built")
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("cid", list(AREA_CASES))
def test_area_case(dump, cid):
    env = classify_ai_system(AREA_CASES[cid]["features"], dump)
    a = env["answer"]
    for task, exp in AREA_CASES[cid]["expected"].items():
        for key in ANSWER_KEYS:
            if key in exp:
                assert a[key] == exp[key], (task, key)
        if "status" in exp:
            assert (env["status"], env["confidence"]) == exp["status"], task
        for node in exp.get("cites", ()):
            assert node in env["source_nodes"], (task, node)
        for node in exp.get("not_cited", ()):
            assert node not in env["source_nodes"], (task, node)
        for line in exp.get("notes", ()):
            assert line in env["legal_status_notes"], (task, line)
        for line in exp.get("missing", ()):
            assert line in env["missing_facts"], (task, line)


def test_finding_1_area_alone_is_marked_and_says_so(dump):
    env = classify_ai_system(AREA_CASES["C1"]["features"], dump)
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert ("eu-ai-act:annex-iii:point-3: the level rests on the area alone: domain 'education' places the system in "
            "Annex III point 3 (Education and vocational training), and no listed use of the point is confirmed; "
            "the listed uses still unknown: annex_iii_3a_admission") in env["legal_status_notes"]
    assert env["answer"]["annex_iii_listed_uses"] == []
    assert ("rule high_risk_area_alone: domain 'education' names Annex III point 3 (eu-ai-act:annex-iii:point-3) "
            "and no listed use of any point is true; high_risk on the area alone, for human review"
            ) in env["answer"]["rationale"]
    # No listed use is cited for the area: only Article 6(2) and the point.
    assert not any(node.startswith("eu-ai-act:annex-iii:point-3:") for node in env["source_nodes"])


def test_finding_2_a_true_listed_use_decides_the_point(dump):
    a = classify_ai_system(AREA_CASES["C3"]["features"], dump)["answer"]
    assert a["annex_iii_category"] == POINT_4
    assert a["annex_iii_listed_uses"] == ["eu-ai-act:annex-iii:point-4:a"]


def test_domain_is_not_read_beside_a_true_listed_use(dump):
    env = classify_ai_system(AREA_CASES["C3"]["features"], dump)
    assert env["answer"]["annex_iii_area_unconfirmed"] is None
    assert POINT_3 not in env["source_nodes"]
    lines = [*env["legal_status_notes"], *env["answer"]["rationale"]]
    assert not any("domain 'education'" in line for line in lines)


def test_finding_4_section_b_product_with_an_area_is_served_as_section_b(dump, norms):
    env = classify_ai_system(AREA_CASES["C11"]["features"], dump)
    a = env["answer"]
    assert a["high_risk_routes"] == ["article_6_1"]
    assert a["annex_iii_category"] is None and a["annex_iii_area_unconfirmed"] == POINT_3
    assert SCOPE_UNCONFIRMED_POINT_3 in env["legal_status_notes"]
    assert not any("Annex III category also matches" in line for line in a["rationale"])
    served = get_applicable_requirements(env, norms, dump)
    assert served["answer"]["annex_i_section"] == "B"
    assert served["answer"]["requirements_by_article"] == {}
    assert served["answer"]["message"] == SECTION_B_ANNEX_III_UNKNOWN_MESSAGE


def test_unknown_section_is_named_by_the_classifier_and_the_requirements(dump, norms):
    env = classify_ai_system(AREA_CASES["C12"]["features"], dump)
    assert env["answer"]["high_risk_routes"] == ["article_6_1"]
    assert ANNEX_I_SECTION_UNKNOWN_FACT in env["missing_facts"]
    served = get_applicable_requirements(env, norms, dump)
    assert ANNEX_I_SECTION_UNKNOWN_FACT in served["missing_facts"]


def test_point_1_gains_the_area_alone_answer(dump):
    env = classify_ai_system(AREA_CASES["C14"]["features"], dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk"
    assert a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-1"
    assert (env["status"], env["confidence"]) == ("requires_human_review", 0.5)
    assert AREA_ALONE_POINT_1 in env["legal_status_notes"]


def test_area_ruled_out_line(dump):
    env = classify_ai_system(AREA_CASES["C2"]["features"], dump)
    assert AREA_RULED_OUT_POINT_3 in env["answer"]["rationale"]
    assert env["answer"]["annex_iii_area_unconfirmed"] is None


@pytest.mark.parametrize("cid", ["C15", "C16"])
def test_both_routes_cite_article_6_2(dump, cid):
    env = classify_ai_system(AREA_CASES[cid]["features"], dump)
    assert env["answer"]["high_risk_routes"] == ["article_6_1", "article_6_2"]
    assert "eu-ai-act:article-6:paragraph-1" in env["source_nodes"]
    assert "eu-ai-act:article-6:paragraph-2" in env["source_nodes"]


def test_area_alone_is_dated_as_annex_iii(dump):
    a = classify_ai_system(AREA_CASES["C1"]["features"], dump)["answer"]
    assert route_of(a) == ROUTE_ANNEX_III
    # Point (c)(i) of Article 113 as amended: 2 December 2027 for Annex III.
    assert {e["date"] for e in a["application_dates"]} == {"2027-12-02"}
    # The bare answer, without high_risk_routes, reads the same way.
    assert route_of({"risk_category": "high_risk", "annex_iii_area_unconfirmed": POINT_3}) == ROUTE_ANNEX_III
    assert route_of({"risk_category": "minimal_risk", "annex_iii_area_unconfirmed": POINT_3}) is None


def test_area_beside_article_6_1_is_dated_on_that_route_alone(dump):
    a = classify_ai_system(AREA_CASES["C10"]["features"], dump)["answer"]
    assert route_of(a) == ROUTE_ANNEX_I
    # Point (c)(ii): 2 August 2028 for Annex I, and no Annex III date.
    assert {e["date"] for e in a["application_dates"]} == {"2028-08-02"}


def test_area_alone_also_on_an_open_article_6_1_route(dump):
    env = classify_ai_system(AREA_CASES["C9"]["features"], dump)
    assert AREA_ALONE_POINT_3 in env["legal_status_notes"]
    assert any(line.startswith("flags.annex_i_covered_product is unknown") for line in env["missing_facts"])


def test_the_reading_keeps_confirmed_points_apart_from_the_area():
    flags = all_false(annex_iii_4a_recruitment=True)
    del flags["annex_iii_3a_admission"]
    reading = read_annex_iii(flags, "education")
    assert reading.confirmed == (POINT_4,)
    assert reading.trigger_fact == "annex_iii_4a_recruitment"
    assert reading.area_point is None and reading.area_unknown_uses == () and reading.area_ruled_out is False

    reading = read_annex_iii({k: v for k, v in all_false().items() if k != "annex_iii_3c_education_level"},
                             "education")
    assert reading.confirmed == () and reading.first_rule is None
    assert reading.area_point == POINT_3 and reading.area_unknown_uses == ("annex_iii_3c_education_level",)

    assert read_annex_iii(all_false(), "education").area_ruled_out is True
    assert read_annex_iii(all_false(), "education").area_point is None
    for domain in ("none_of_these_areas", None):
        reading = read_annex_iii({}, domain)
        assert reading.area_point is None and reading.area_ruled_out is False and reading.confirmed == ()


def test_the_field_is_null_off_the_high_risk_level(dump):
    for cid in ("C2", "C6", "C7", "C8", "C23"):
        assert classify_ai_system(AREA_CASES[cid]["features"], dump)["answer"]["annex_iii_area_unconfirmed"] is None


def _level(features: dict, dump: dict) -> str:
    return classify_ai_system(features, dump)["answer"]["risk_category"]


@pytest.mark.parametrize("cid", list(AREA_CASES))
def test_an_unknown_fact_made_false_never_raises_and_made_true_never_lowers_the_level(dump, cid):
    """Level safety: for each fact absent from a case, answering it false never
    gives a higher definite level, and answering it true never a lower one.
    An Article 5 exception fact answered false while its practice is true
    proves the ban (DEC-18), the one designed exception to the first half; no
    case of the table has such a pending exception."""
    features = AREA_CASES[cid]["features"]
    level = _level(features, dump)
    absent = [f for f in all_false() if f not in features["flags"]]
    for fact in absent:
        for value, never in ((False, "higher"), (True, "lower")):
            changed = {**features, "flags": {**features["flags"], fact: value}}
            after = _level(changed, dump)
            if level not in LEVEL_RANK or after not in LEVEL_RANK:
                continue
            if never == "higher":
                assert LEVEL_RANK[after] <= LEVEL_RANK[level], (cid, fact, value, level, after)
            else:
                assert LEVEL_RANK[after] >= LEVEL_RANK[level], (cid, fact, value, level, after)


def test_a_domain_never_lowers_the_level_beside_a_true_listed_use(dump):
    """A true listed use gives high_risk whatever the domain."""
    for domain in (None, "biometrics", "critical_infrastructure", "education", "employment",
                   "essential_services", "law_enforcement", "migration", "justice", "none_of_these_areas"):
        features = _features(true=("annex_iii_8a_judicial",), domain=domain)
        a = classify_ai_system(features, dump)["answer"]
        assert a["risk_category"] == "high_risk", domain
        assert a["annex_iii_category"] == "eu-ai-act:annex-iii:point-8", domain
        assert a["annex_iii_area_unconfirmed"] is None, domain


def test_area_alone_line_names_every_unknown_listed_use_in_point_order(dump):
    features = _features(absent=("annex_iii_3d_test_monitoring", "annex_iii_3a_admission"))
    env = classify_ai_system(features, dump)
    assert AREA_ALONE_POINT_3.replace(
        "annex_iii_3a_admission", "annex_iii_3a_admission, annex_iii_3d_test_monitoring"
    ) in env["legal_status_notes"]

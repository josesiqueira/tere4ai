"""The applicable requirements and trace_implementation read the classification
from the answer itself (B185 Task 7, spec G D-G92 (3), (5), (8), (i), (vii),
rulings P11, P12, P25, R5, DEC-33).

get_applicable_requirements decides whether the classification is settled,
and which causes of review hold, through the one module review_causes.py,
from the answer's own fields, so an envelope and its bare answer give the
same status, confidence, provisional flag, note, requirements served and
dates. The provisional note names every cause that holds, in the order of
D-G92 (8), and never names a change to Unacceptable risk while
unacceptable_risk is false. trace_implementation reads the requirements'
answer and needs no change of its own (its test is in test_trace_code.py).
The cases are the table of area cases
(tests/unit/area_cases.py, the t7 column) and inputs built for the five
classes of answer whose note named Unacceptable risk at 5d5bc14 while the
field was false. Offline: the published Layer 1 and norms dumps on disk,
skipped when absent.

@implements: DEC-33
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.unit.area_cases import AREA_CASES, DEPLOYER, P61, _features
from tests.unit.b184_cases import all_false, case

from tere4ai.mcp_server.application_dates import ROUTE_ANNEX_I, ROUTE_ANNEX_III, provision_dates
from tere4ai.mcp_server.classify import (
    ARTICLE_2_2_CONDITIONAL_PROVISIONS,
    ARTICLE_2_2_PROVISIONS,
    classify_ai_system,
)
from tere4ai.mcp_server.requirements import (
    PROVISIONAL_NOTE_PLAIN,
    PROVISIONAL_NOTE_TEMPLATE,
    SECTION_B_ANNEX_III_UNKNOWN_MESSAGE,
    SECTION_B_DEROGATION_NOTE,
    SECTION_B_LISTED_USE_UNKNOWN_FACT,
    UNSETTLED_FALLBACK_FACT,
    get_applicable_requirements,
)
from tere4ai.mcp_server.review_causes import (
    ANNEX_III_UNKNOWN_TAG,
    REVIEW_CAUSE_REASONS,
    review_causes_of_answer,
    review_reason,
    review_status_line,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

pytestmark = pytest.mark.skipif(
    not (DUMP_PATH.is_file() and NORMS_PATH.is_file()),
    reason="graph dumps not built",
)

# What an envelope and its bare answer must give alike (the coordinator's
# check (d) of Task 7); the missing facts are compared apart, since the bare
# answer does not carry the classification's missing facts.
SAME_KEYS = ("status", "confidence", "provisional", "provisional_note", "message", "groups", "application_dates")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def _view(env: dict[str, Any]) -> dict[str, Any]:
    a = env["answer"] or {}
    return {
        "status": env["status"],
        "confidence": env["confidence"],
        "provisional": a.get("provisional"),
        "provisional_note": a.get("provisional_note"),
        "message": a.get("message"),
        "groups": {g: [n["norm_id"] for n in v] for g, v in (a.get("requirements_by_article") or {}).items()},
        "application_dates": a.get("application_dates"),
    }


def _both(features: dict[str, Any], dump: dict, norms: dict) -> tuple[dict, dict, dict]:
    """The classification, and the requirements from its envelope and from its bare answer."""
    cls = classify_ai_system(features, dump)
    return (cls, get_applicable_requirements(cls, norms, dump),
            get_applicable_requirements(cls["answer"], norms, dump))


def _note(*causes: str) -> str:
    return PROVISIONAL_NOTE_TEMPLATE.format(reasons=review_reason(list(causes)))


# The fixed sentences (the brief of Task 7, word for word) -------------------

def test_the_provisional_notes_word_for_word():
    assert PROVISIONAL_NOTE_TEMPLATE == (
        "These requirements are provisional pending the human-review determination of the classification: "
        "{reasons}.")
    assert PROVISIONAL_NOTE_PLAIN == (
        "These requirements are provisional pending the human-review determination of the classification.")


# The table of area cases, the t7 column -------------------------------------

@pytest.mark.parametrize("cid", [cid for cid, c in AREA_CASES.items() if "t7" in c["expected"]])
def test_t7_column_in_both_forms(dump, norms, cid):
    exp = AREA_CASES[cid]["expected"]["t7"]
    _cls, env, bare = _both(AREA_CASES[cid]["features"], dump, norms)
    for given in (env, bare):
        assert (given["status"], given["confidence"]) == exp["requirements_status"]
        assert given["answer"].get("provisional_note") == exp["requirements_note"]
        assert given["answer"].get("provisional", False) is (exp["requirements_note"] is not None)
        if "requirements_message" in exp:
            assert given["answer"]["message"] == exp["requirements_message"]
    assert _view(env) == _view(bare)


@pytest.mark.parametrize("cid", list(AREA_CASES))
def test_every_table_case_reads_the_same_from_envelope_and_bare_answer(dump, norms, cid):
    _cls, env, bare = _both(AREA_CASES[cid]["features"], dump, norms)
    assert _view(env) == _view(bare)


def test_bare_area_alone_answer_is_provisional_with_its_cause(dump, norms):  # C1, Review Focus 3
    answer = classify_ai_system(AREA_CASES["C1"]["features"], dump)["answer"]
    env = get_applicable_requirements(answer, norms, dump)   # the bare answer, no envelope
    assert env["status"] == "requires_human_review" and env["answer"]["provisional"] is True
    assert env["confidence"] == 0.5
    assert env["answer"]["provisional_note"] == PROVISIONAL_NOTE_TEMPLATE.format(
        reasons=REVIEW_CAUSE_REASONS["area_alone"])
    assert env["answer"]["requirements_by_article"]                   # Chapter III served as provisional
    assert env["answer"]["application_dates"] == {
        g: provision_dates(f"eu-ai-act:{g}", dump, ROUTE_ANNEX_III) for g in env["answer"]["requirements_by_article"]}


def test_section_b_with_an_area_is_served_as_section_b_and_unsettled(dump, norms):  # C11, P25
    cls, env, bare = _both(AREA_CASES["C11"]["features"], dump, norms)
    assert cls["answer"]["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    provisions = [*ARTICLE_2_2_PROVISIONS, *ARTICLE_2_2_CONDITIONAL_PROVISIONS]
    for given in (env, bare):
        a = given["answer"]
        assert (given["status"], given["confidence"]) == ("requires_human_review", 0.5)
        assert a["requirements_by_article"] == {} and "article_2_2" in a
        assert a["message"] == SECTION_B_ANNEX_III_UNKNOWN_MESSAGE
        assert given["legal_status_notes"] == [SECTION_B_ANNEX_III_UNKNOWN_MESSAGE]
        assert a["application_dates"] == {n: provision_dates(n, dump, ROUTE_ANNEX_I) for n in provisions}
        assert "provisional_note" not in a
    assert any("Annex III high-risk relevant" in m for m in env["missing_facts"])
    # The bare answer brings no missing facts; the point that rests on the area
    # is named from its own field, so the message's "see the missing facts"
    # points at a line (Task 7 follow-up, item 3). The envelope already names
    # the unknown listed uses and gains no such line.
    assert bare["missing_facts"] == [
        "annex_iii_area_unconfirmed is eu-ai-act:annex-iii:point-3: the domain places the system in that Annex III "
        "point, and the listed uses of the point are not confirmed"]
    assert not any(m.startswith("annex_iii_area_unconfirmed is ") for m in env["missing_facts"])


def test_section_b_candidate_note_names_the_candidacy_and_what_it_changes(dump, norms):  # C21 (I1)
    env = classify_ai_system(AREA_CASES["C21"]["features"], dump)
    note = get_applicable_requirements(env, norms, dump)["answer"]["provisional_note"]
    assert note == PROVISIONAL_NOTE_TEMPLATE.format(
        reasons=REVIEW_CAUSE_REASONS["article_6_3_candidate"]) + SECTION_B_DEROGATION_NOTE


def test_note_names_every_cause_in_order(dump, norms):  # C18
    cls, env, bare = _both(AREA_CASES["C18"]["features"], dump, norms)
    assert cls["answer"]["unacceptable_risk"] is None
    for given in (env, bare):
        assert given["answer"]["provisional_note"] == PROVISIONAL_NOTE_TEMPLATE.format(
            reasons=REVIEW_CAUSE_REASONS["article_5_unknown"] + "; " + REVIEW_CAUSE_REASONS["area_alone"])


def test_finding_16_the_note_names_the_candidacy_not_unacceptable_risk(dump, norms):  # C22, M4
    env = classify_ai_system(AREA_CASES["C22"]["features"], dump)
    assert env["answer"]["unacceptable_risk"] is False
    note = get_applicable_requirements(env, norms, dump)["answer"]["provisional_note"]
    assert note == PROVISIONAL_NOTE_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["article_6_3_candidate"])


def test_bare_area_conflict_answer_is_provisional(dump, norms):  # C5
    cls, env, bare = _both(AREA_CASES["C5"]["features"], dump, norms)
    assert cls["answer"]["area_conflicts"]
    for given in (env, bare):
        assert given["status"] == "requires_human_review" and given["answer"]["provisional"] is True
        assert given["answer"]["provisional_note"] == _note("area_conflict")
        assert cls["answer"]["area_conflicts"][0]["note"] in given["missing_facts"]


def test_a_bare_answer_marked_for_review_with_no_cause_found_gets_the_plain_note(dump, norms):
    # A hand-written answer with no field that marks it, passed in an envelope
    # whose status is requires_human_review: the classification's own status
    # is kept (DEC-08), and the note names no cause it cannot find.
    cls = classify_ai_system(AREA_CASES["C4"]["features"], dump)
    marked = {**cls, "status": "requires_human_review", "confidence": 0.5}
    req = get_applicable_requirements(marked, norms, dump)
    assert req["status"] == "requires_human_review" and req["answer"]["provisional"] is True
    assert req["answer"]["provisional_note"] == PROVISIONAL_NOTE_PLAIN


# The five classes whose note named Unacceptable risk at 5d5bc14 while
# unacceptable_risk was false (measured by Task 6's reviewer on 3,000
# generated inputs: 250, 54, 41, 19 and 38) ----------------------------------

FIVE_CLASSES = {
    # An Article 6(3) candidate where Annex III decides what is served (C22).
    "candidate": (AREA_CASES["C22"]["features"], ("article_6_3_candidate",)),
    # The area alone (C1).
    "area_alone": (AREA_CASES["C1"]["features"], ("area_alone",)),
    # An area conflict (C5).
    "area_conflict": (AREA_CASES["C5"]["features"], ("area_conflict",)),
    # limited_risk answers: an open Article 6(1) route, and an unknown listed use.
    "limited_article_6_1_open": (
        case({k: v for k, v in all_false(interacts_with_natural_persons=True,
                                         third_party_conformity_assessment_required=True).items()
              if k != "annex_i_covered_product"}, deployer=dict(DEPLOYER)),
        ("article_6_1_open",)),
    "limited_listed_use_unknown": (
        case({k: v for k, v in all_false(interacts_with_natural_persons=True).items()
              if k != "annex_iii_4a_recruitment"}, deployer=dict(DEPLOYER)),
        ("listed_use_unknown",)),
    # Combinations: the candidate on a Section B product (C21), the candidate
    # beside an area conflict, the candidate beside the area alone.
    "candidate_section_b": (AREA_CASES["C21"]["features"], ("article_6_3_candidate",)),
    "conflict_and_candidate": (
        _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"), domain="none_of_these_areas"),
        ("area_conflict", "article_6_3_candidate")),
    "area_alone_and_candidate": (
        _features(true=("narrow_procedural_task",), absent=("annex_iii_3a_admission",)),
        ("area_alone", "article_6_3_candidate")),
}


@pytest.mark.parametrize("name", list(FIVE_CLASSES))
def test_no_note_names_unacceptable_risk_while_the_field_is_false(dump, norms, name):
    features, causes = FIVE_CLASSES[name]
    cls, env, bare = _both(features, dump, norms)
    assert cls["answer"]["unacceptable_risk"] is False
    assert cls["status"] == "requires_human_review"
    expected = _note(*causes) + (SECTION_B_DEROGATION_NOTE if name == "candidate_section_b" else "")
    for given in (env, bare):
        a = given["answer"]
        texts = [a.get("provisional_note") or "", a.get("message") or "", *given["missing_facts"],
                 *given["legal_status_notes"]]
        assert not any("Unacceptable risk" in text for text in texts), name
        assert given["status"] == "requires_human_review" and a["provisional"] is True
        assert a["provisional_note"] == expected
    assert _view(env) == _view(bare)


def test_a_section_b_product_with_a_listed_use_unknown_reads_the_same_bare(dump, norms):
    # No domain, so no point rests on the area: the unknown listed use is
    # named only among the envelope's missing facts, and the bare answer
    # carries it in its status line, which the requirements read.
    features = _features(absent=("annex_iii_4a_recruitment",), domain=None, **P61,
                         annex_i_section_b_legislation=True)
    cls, env, bare = _both(features, dump, norms)
    assert cls["answer"]["annex_iii_area_unconfirmed"] is None and cls["status"] == "requires_human_review"
    for given in (env, bare):
        assert given["status"] == "requires_human_review"
        assert given["answer"]["message"] == SECTION_B_ANNEX_III_UNKNOWN_MESSAGE
    assert _view(env) == _view(bare)


def test_a_bare_section_b_answer_with_a_listed_use_unknown_names_it_among_its_missing_facts(dump, norms):
    # B185 Task 8, item (b) of the coordinator (from Task 7's re-review): the
    # bare answer carries no missing facts, and with no area set its only
    # missing fact was the fallback line. It now says, from what the bare
    # answer carries (its status line), that a fact of the Annex III route is
    # unknown and that the classification's missing facts name which; the
    # envelope, which names the facts, does not gain the line.
    features = _features(absent=("annex_iii_4a_recruitment",), domain=None, **P61,
                         annex_i_section_b_legislation=True)
    cls, env, bare = _both(features, dump, norms)
    assert SECTION_B_LISTED_USE_UNKNOWN_FACT not in env["missing_facts"]
    assert any(ANNEX_III_UNKNOWN_TAG in m for m in env["missing_facts"])
    assert bare["missing_facts"] == [SECTION_B_LISTED_USE_UNKNOWN_FACT]
    assert UNSETTLED_FALLBACK_FACT not in bare["missing_facts"]
    assert _view(env) == _view(bare)
    # With an area set, the line of the area is given instead, as before.
    cls, env, bare = _both({**features, "domain": "employment"}, dump, norms)
    assert cls["answer"]["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-4"
    assert SECTION_B_LISTED_USE_UNKNOWN_FACT not in bare["missing_facts"]
    assert SECTION_B_LISTED_USE_UNKNOWN_FACT not in env["missing_facts"]


def test_the_listed_use_line_is_worded_once():
    assert SECTION_B_LISTED_USE_UNKNOWN_FACT == (
        "an Annex III fact is unknown: a listed use, or real_time_remote_biometric_public, which also gives "
        "point 1; the answer's status line says so, and the classification's missing facts name which")


def test_the_causes_of_a_bare_answer_read_the_two_that_need_missing_facts_from_its_status_lines():
    # review_causes_of_answer (B185 Task 7): with the envelope's missing facts
    # it is review_causes; on a bare answer the open Article 6(1) route and
    # the unknown listed use are read from the answer's own status lines, on
    # the answers where their rules can hold.
    limited = {"risk_category": "limited_risk", "unacceptable_risk": False, "fact_conflicts": [],
               "area_conflicts": [], "high_risk_routes": [], "article_6_3_exception_candidate": False,
               "annex_i_section": None}
    line_6_1 = review_status_line("article_6_1_open", limited)
    line_use = review_status_line("listed_use_unknown", limited)
    assert review_causes_of_answer({**limited, "rationale": [line_use, line_6_1]}) == [
        "article_6_1_open", "listed_use_unknown"]
    # With the missing facts given they decide, the lines are not read.
    assert review_causes_of_answer({**limited, "rationale": [line_6_1]}, []) == []
    # No line, no cause; and not on a level where the rule cannot hold.
    assert review_causes_of_answer(limited) == []
    assert review_causes_of_answer({**limited, "risk_category": "minimal_risk", "rationale": [line_6_1]}) == []
    section_b = {**limited, "risk_category": "high_risk", "annex_i_section": "B", "high_risk_routes": ["article_6_1"]}
    line_b = review_status_line("listed_use_unknown", section_b)
    assert review_causes_of_answer({**section_b, "rationale": [line_b]}) == ["listed_use_unknown"]
    assert review_causes_of_answer({**section_b, "high_risk_routes": ["article_6_1", "article_6_2"],
                                    "rationale": [line_b]}) == []
    assert review_causes_of_answer({**section_b, "rationale": [line_6_1]}) == []


# Task 7 follow-up, item 1: real_time_remote_biometric_public unknown with
# Article 5(1)(h) open is named under both tags, as a prohibition fact and as
# a fact of the Annex III route (D-G92 (2): it gives point 1), so the cause
# "an unknown listed use" holds.

PROHIBITION_LINE = (
    "flags.real_time_remote_biometric_public is unknown (prohibition-relevant, Article 5); absence is not treated "
    "as false")
ANNEX_III_LINE = (
    "flags.real_time_remote_biometric_public is unknown (Annex III high-risk relevant, Article 6(2)); absence is not "
    "treated as false")
ARTICLE_5_STATUS_LINE = (
    "status lowered to requires_human_review: unknown prohibition-relevant flags could change the outcome to "
    "Unacceptable risk")
LISTED_USE_STATUS_LINE = (
    "status lowered to requires_human_review: unknown Annex III high-risk flags could add high-risk obligations on "
    "top of the Article 50 transparency duty")


def _real_time_unknown(purpose_false: bool = False, **values: Any) -> dict[str, Any]:
    gone = ("real_time_remote_biometric_public", "law_enforcement_purpose")
    flags = {k: v for k, v in all_false(**values).items() if k not in gone}
    if purpose_false:
        flags["law_enforcement_purpose"] = False
    return case(flags, deployer=dict(DEPLOYER))


def test_case_a_real_time_fact_with_point_h_open_is_named_under_both_tags(dump, norms):
    cls, env, bare = _both(_real_time_unknown(interacts_with_natural_persons=True), dump, norms)
    a = cls["answer"]
    assert a["risk_category"] == "limited_risk" and a["unacceptable_risk"] is None
    assert PROHIBITION_LINE in cls["missing_facts"] and ANNEX_III_LINE in cls["missing_facts"]
    assert cls["missing_facts"].index(PROHIBITION_LINE) < cls["missing_facts"].index(ANNEX_III_LINE)
    assert [line for line in a["rationale"] if line.startswith("status lowered")] == [
        ARTICLE_5_STATUS_LINE, LISTED_USE_STATUS_LINE]
    for given in (env, bare):
        assert given["answer"]["provisional_note"] == _note("article_5_unknown", "listed_use_unknown")
    assert _view(env) == _view(bare)


def test_case_b_section_b_product_with_the_real_time_fact_unknown_gets_the_unknown_message(dump, norms):
    features = _real_time_unknown(**P61, annex_i_section_b_legislation=True)
    cls, env, bare = _both(features, dump, norms)
    assert cls["answer"]["high_risk_routes"] == ["article_6_1"] and cls["answer"]["annex_i_section"] == "B"
    for given in (env, bare):
        assert given["answer"]["message"] == SECTION_B_ANNEX_III_UNKNOWN_MESSAGE
        assert given["status"] == "requires_human_review"
    assert _view(env) == _view(bare)


def test_the_real_time_fact_with_point_h_ruled_out_reads_as_before(dump, norms):
    # law_enforcement_purpose false rules point (h) out: the fact is named only
    # for the Annex III route, as at 74d6713.
    cls, env, bare = _both(_real_time_unknown(purpose_false=True, interacts_with_natural_persons=True), dump, norms)
    a = cls["answer"]
    assert a["risk_category"] == "limited_risk" and a["unacceptable_risk"] is False
    assert PROHIBITION_LINE not in cls["missing_facts"] and ANNEX_III_LINE in cls["missing_facts"]
    assert [line for line in a["rationale"] if line.startswith("status lowered")] == [LISTED_USE_STATUS_LINE]
    for given in (env, bare):
        assert given["answer"]["provisional_note"] == _note("listed_use_unknown")

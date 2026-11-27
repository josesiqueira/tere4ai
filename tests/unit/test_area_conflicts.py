"""area_conflicts: a listed use that is true while domain is none_of_these_areas
(B185, spec G D-G92 (4) and (iii), DEC-33, ruling P26).

none_of_these_areas is a person's statement that the system is in none of the
eight areas of Annex III. It is never a reason to read a listed use as no: an
unknown listed use stays unknown and is named. A listed use that is true
beside it (as answered, or as it follows from a definition of the Act) keeps
its effect, and the pair is named in area_conflicts, one entry per listed use,
with its note among the missing facts; the answer is marked for human review
on every exit, unacceptable_risk included, as an entry of fact_conflicts
marks it, and the level never changes. Offline: the published Layer 1 dump
and the norms on disk, skipped when absent.

@implements: DEC-33
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from tests.unit.area_cases import AREA_CASES, AREA_RULED_OUT_POINT_3, P61, _features

from tere4ai.mcp_server.classify import (
    AREA_CONFLICT_NOTE,
    PROHIBITED_PRACTICE_NOTE_MARK,
    PROHIBITION_AREA_CONFLICT_CLAUSE,
    PROHIBITION_FACT_CONFLICT_CLAUSE,
    _classify_core,
    area_conflicts,
    classify_ai_system,
)
from tere4ai.mcp_server.fria import (
    AREA_CONFLICT_REASON,
    FACT_CONFLICT_REASON,
    assess_fria_applicability,
)
from tere4ai.mcp_server.requirements import PROHIBITED_MESSAGE, get_applicable_requirements
from tere4ai.mcp_server.review_causes import (
    review_causes,
    review_status_line,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"


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


def test_the_fixed_words():
    # The spec's note (D-G92 (iii)), the clause of P26 and the reason of Task 6's
    # REVIEW_CAUSE_REASONS["area_conflict"], word for word.
    assert AREA_CONFLICT_NOTE == "domain is none_of_these_areas while flags.{fact} is true; the fact keeps its effect"
    assert PROHIBITION_AREA_CONFLICT_CLAUSE == (
        "This rests on the facts as read: a listed use is true while domain is none_of_these_areas "
        "(area_conflicts), so it stands for human review."
    )
    assert AREA_CONFLICT_REASON == (
        "a listed use of Annex III is true while the domain says none of these areas (area_conflicts), so one "
        "of the two answers is wrong"
    )


def test_none_of_these_areas_beside_a_true_listed_use_is_an_area_conflict(dump):  # C5
    env = classify_ai_system(AREA_CASES["C5"]["features"], dump)
    a = env["answer"]
    assert a["area_conflicts"] == [{"domain": "none_of_these_areas", "fact": "annex_iii_4a_recruitment",
        "note": "domain is none_of_these_areas while flags.annex_iii_4a_recruitment is true; the fact keeps its effect"}]
    assert a["fact_conflicts"] == [] and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-4"
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert a["area_conflicts"][0]["note"] in env["missing_facts"]
    # The status line of the cause area_conflict (review_causes.py, worded in
    # test_review_causes.py; the constant classify.py kept of it had no reader
    # and left with the final fix wave, item 7).
    assert review_status_line("area_conflict", a) in a["rationale"]
    # The mark reaches the Article 27 block, computed after it.
    assert a["fria"]["applicability"] == "unknown"


def test_entailed_listed_use_beside_none_of_these_areas_is_an_area_conflict(dump):  # C20
    a = classify_ai_system(AREA_CASES["C20"]["features"], dump)["answer"]
    assert [e["fact"] for e in a["area_conflicts"]] == ["biometric_identification"] and a["fact_conflicts"] == []


def test_none_of_these_areas_never_reads_a_listed_use_as_no(dump):  # C7
    env = classify_ai_system(AREA_CASES["C7"]["features"], dump)
    assert env["answer"]["risk_category"] == "undetermined"
    assert any(line.startswith("flags.annex_iii_3a_admission is unknown") for line in env["missing_facts"])
    assert env["answer"]["area_conflicts"] == []


def test_area_conflict_marks_a_prohibited_answer_for_review(dump, norms):  # C23
    env = classify_ai_system(AREA_CASES["C23"]["features"], dump)
    assert env["answer"]["risk_category"] == "unacceptable_risk"
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    prohibited = [n for n in env["legal_status_notes"] if PROHIBITED_PRACTICE_NOTE_MARK in n]
    assert prohibited and all(n.endswith(f". {PROHIBITION_AREA_CONFLICT_CLAUSE}") for n in prohibited)
    assert all(PROHIBITION_FACT_CONFLICT_CLAUSE not in n for n in prohibited)
    assert env["answer"]["fria"]["applicability"] == "unknown"
    assert any(AREA_CONFLICT_REASON in line for line in env["answer"]["fria"]["rationale"])
    req = get_applicable_requirements(env["answer"], norms, dump)  # the bare answer
    assert req["status"] == "requires_human_review" and req["answer"]["requirements_by_article"] == {}
    assert req["answer"]["message"] == f"{PROHIBITED_MESSAGE} {PROHIBITION_AREA_CONFLICT_CLAUSE}"
    assert env["answer"]["area_conflicts"][0]["note"] in req["missing_facts"]
    served = get_applicable_requirements(env, norms, dump)  # the envelope
    assert served["status"] == "requires_human_review" and served["missing_facts"] == env["missing_facts"]


def test_both_marks_on_a_prohibited_answer_name_the_fact_conflict_first(dump):
    features = copy.deepcopy(AREA_CASES["C23"]["features"])
    features["flags"]["emotion_recognition"] = False  # contradicts Article 3(39)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["risk_category"] == "unacceptable_risk" and a["fact_conflicts"] and a["area_conflicts"]
    prohibited = [n for n in env["legal_status_notes"] if PROHIBITED_PRACTICE_NOTE_MARK in n]
    assert prohibited and all(
        n.endswith(f". {PROHIBITION_FACT_CONFLICT_CLAUSE} {PROHIBITION_AREA_CONFLICT_CLAUSE}") for n in prohibited
    )
    sentence = a["fria"]["rationale"][0]
    assert a["fria"]["applicability"] == "unknown"
    assert sentence.index(FACT_CONFLICT_REASON) < sentence.index(AREA_CONFLICT_REASON)


def test_the_block_names_each_mark_that_holds_on_unacceptable_risk():
    def sentence(**marks):
        # B185 Task 6, fix round 1: the causes come from the one decider,
        # review_causes.py, built here from the marks of a prohibited answer.
        answer = {"risk_category": "unacceptable_risk", "unacceptable_risk": True, **marks}
        block = assess_fria_applicability("unacceptable_risk", None, {}, {}, review_causes=review_causes(answer))
        assert block["applicability"] == "unknown"
        return block["rationale"][0]

    fact_only = sentence(fact_conflicts=[{"note": "x"}])
    assert FACT_CONFLICT_REASON in fact_only and AREA_CONFLICT_REASON not in fact_only
    area_only = sentence(area_conflicts=[{"note": "y"}])
    assert AREA_CONFLICT_REASON in area_only and FACT_CONFLICT_REASON not in area_only
    assert area_only == (
        "the system falls under an Article 5 prohibited practice on the facts as read, but "
        + AREA_CONFLICT_REASON + "; FRIA applicability stays unknown until the classification is confirmed"
    )
    both = sentence(fact_conflicts=[{"note": "x"}], area_conflicts=[{"note": "y"}])
    assert both.index(FACT_CONFLICT_REASON) < both.index(AREA_CONFLICT_REASON)
    assert assess_fria_applicability("unacceptable_risk", None, {}, {})["applicability"] == "does_not_apply"


def test_rejected_input_has_no_area_conflicts(dump):
    for features in ({"description": "short"},
                     {"description": "a domain outside the list", "flags": {"annex_iii_4a_recruitment": True},
                      "domain": "banking"}):
        env = classify_ai_system(features, dump)
        assert env["status"] == "rejected_as_unsupported" and env["answer"]["area_conflicts"] == []


def test_area_conflicts_reads_only_true_listed_uses_beside_none_of_these_areas():
    flags = {"creditworthiness_evaluation": True, "annex_iii_8a_judicial": False, "annex_iii_4a_recruitment": True}
    entries = area_conflicts(flags, "none_of_these_areas")
    # Point order, not input order, one entry per listed use that is true; a
    # false or absent one (biometric_identification here) gives none.
    assert [e["fact"] for e in entries] == ["annex_iii_4a_recruitment", "creditworthiness_evaluation"]
    for domain in (None, "employment", "education"):
        assert area_conflicts(flags, domain) == []
    assert area_conflicts({"annex_iii_8a_judicial": False}, "none_of_these_areas") == []
    assert area_conflicts("not a dict", "none_of_these_areas") == []  # type: ignore[arg-type]


@pytest.mark.parametrize("domain", [None, "biometrics", "critical_infrastructure", "education", "employment",
                                    "essential_services", "law_enforcement", "migration", "justice",
                                    "none_of_these_areas"])
def test_an_area_conflict_changes_status_and_confidence_only(dump, domain):
    """The level, the point and the routes are the same with or without the
    conflict; only none_of_these_areas beside a true listed use marks it."""
    features = _features(true=("annex_iii_8a_judicial",), domain=domain)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-8"
    assert a["high_risk_routes"] == ["article_6_2"]
    marked = domain == "none_of_these_areas"
    assert bool(a["area_conflicts"]) is marked
    assert (env["status"], env["confidence"]) == (
        ("requires_human_review", 0.5) if marked else ("potentially_applicable", 1.0)
    )


@pytest.mark.parametrize("section_b", [False, True])
def test_article_6_1_exit_says_the_area_stopped_counting(dump, section_b):
    """Spec G D-G92 (3): with every listed use of the domain's area known false
    the area stops counting and the answer says so in one line, on the Article
    6(1) exit as on the Annex III one (review of Task 2, item (a))."""
    features = _features(**P61, annex_i_section_b_legislation=section_b)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["high_risk_routes"] == ["article_6_1"] and a["annex_i_section"] == ("B" if section_b else "A")
    assert a["annex_iii_area_unconfirmed"] is None
    assert a["rationale"].count(AREA_RULED_OUT_POINT_3) == 1
    assert AREA_RULED_OUT_POINT_3 in _classify_core(copy.deepcopy(features), dump)["answer"]["rationale"]

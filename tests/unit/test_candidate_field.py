"""The Article 6(3) candidate field for the Annex III part of an answer (B185, spec G D-G92 (6), (iv), passage (k), DEC-33).

article_6_3_exception_candidate is true when a condition (points (a) to (d))
is true and profiling is not true, false when profiling is true or every
condition is false, and null otherwise, with each unknown condition and an
unknown profiling fact named among the missing facts. It describes an answer
that has an Annex III point (a listed use that is true, or a point that rests
on the area); on every other answer it is false and no condition fact is
named. An unknown candidate changes neither the status nor the Article 27(1)
block. A true candidate cites Article 6(3), its points and Article 6(4); it
marks the answer for review where Annex III decides what is served (the
Annex III exit, a Section B product included), while a system on both routes
whose product legislation is not in Section B keeps the status of the
Article 6(1) route (ruling P29). The Article 27 block reads the field. The
cases are the table of area cases (tests/unit/area_cases.py). Offline: the
published Layer 1 dump on disk, skipped when it is absent.

@implements: DEC-33
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.area_cases import AREA_CASES, P61, _features

from tere4ai.mcp_server.classify import (
    ARTICLE_6_3_BOTH_ROUTES_LINE,
    ARTICLE_6_3_BOTH_ROUTES_NOTE,
    ARTICLE_6_3_CONDITIONS,
    ARTICLE_6_3_UNKNOWN_CONDITION_LINE,
    ARTICLE_6_3_UNKNOWN_PROFILING_LINE,
    ARTICLE_6_4_LINE,
    ARTICLE_6_PARAGRAPH_4,
    article_6_3_candidate,
    classify_ai_system,
)
from tere4ai.mcp_server.fria import (
    FRIA_AREA_ALONE_REASON,
    FRIA_AREA_BESIDE_ARTICLE_6_1_REASON,
    FRIA_OTHER_CAUSES_TEMPLATE,
)
from tere4ai.mcp_server.review_causes import REVIEW_CAUSE_REASONS

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")

ARTICLE_6_3 = "eu-ai-act:article-6:paragraph-3"
POINT_A = "eu-ai-act:article-6:paragraph-3:point-a"
CONDITION_FACTS = tuple(flag for flag, _points, _label in ARTICLE_6_3_CONDITIONS)
FLAGGED_NOTE = (
    "eu-ai-act:article-6:paragraph-3: Article 6(3) derogation candidacy is flagged for human review; the "
    "classification stays high_risk until a human legal reviewer decides"
)
PROFILING_UNKNOWN_WITH_CONDITION = (
    "flags.profiling_of_natural_persons is unknown while an Article 6(3) derogation condition matched; "
    "profiling cancels the derogation (Article 6(3) third subparagraph)"
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _unknown_condition_lines(env: dict) -> list[str]:
    return [line for line in env["missing_facts"] if line.endswith("so the derogation candidacy is unknown, not no")]


def test_the_fixed_words():
    assert ARTICLE_6_PARAGRAPH_4 == "eu-ai-act:article-6:paragraph-4"
    assert ARTICLE_6_3_UNKNOWN_CONDITION_LINE == (
        "flags.{flag} is unknown (Article 6(3) {label}); no condition is true, so the derogation candidacy "
        "is unknown, not no"
    )
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE == (
        "flags.profiling_of_natural_persons is unknown while the Article 6(3) derogation candidacy is unknown; "
        "profiling cancels the derogation (Article 6(3) third subparagraph)"
    )
    assert ARTICLE_6_4_LINE == (
        "eu-ai-act:article-6:paragraph-4: a provider who considers that the system is not high-risk documents "
        "the assessment before placing it on the market or putting it into service, registers under Article "
        "49(2), and provides the documentation of the assessment to the national competent authorities on "
        "request"
    )
    assert ARTICLE_6_3_BOTH_ROUTES_LINE == (
        "Article 6(3) condition for the Annex III part: '{label}' met by {flag}; the level stays high_risk "
        "under Article 6(1), which the derogation does not reach"
    )
    assert ARTICLE_6_3_BOTH_ROUTES_NOTE == (
        "eu-ai-act:article-6:paragraph-3: an Article 6(3) condition is true for the Annex III part of the "
        "answer; the level stays high_risk under Article 6(1), which the derogation does not reach"
    )


def test_the_candidate_of_the_facts():
    """(6): true, false or null, from the four conditions and profiling."""
    every_false = dict.fromkeys(CONDITION_FACTS, False)
    assert article_6_3_candidate({**every_false, "narrow_procedural_task": True}) is True
    assert article_6_3_candidate({"narrow_procedural_task": True}) is True  # profiling unknown
    assert article_6_3_candidate(
        {**every_false, "narrow_procedural_task": True, "profiling_of_natural_persons": True}
    ) is False
    assert article_6_3_candidate({"profiling_of_natural_persons": True}) is False  # every condition unknown
    assert article_6_3_candidate(every_false) is False  # profiling unknown
    assert article_6_3_candidate({**every_false, "profiling_of_natural_persons": False}) is False
    assert article_6_3_candidate({}) is None
    assert article_6_3_candidate({"profiling_of_natural_persons": False}) is None
    del every_false["preparatory_task"]
    assert article_6_3_candidate(every_false) is None


def test_finding_14_an_unknown_condition_is_named_and_the_candidate_is_unknown(dump):  # C19
    env = classify_ai_system(AREA_CASES["C19"]["features"], dump)
    assert env["answer"]["article_6_3_exception_candidate"] is None
    assert ("flags.narrow_procedural_task is unknown (Article 6(3) narrow procedural task (point a)); no condition "
            "is true, so the derogation candidacy is unknown, not no") in env["missing_facts"]
    assert len(_unknown_condition_lines(env)) == 1
    assert env["status"] == "potentially_applicable" and env["confidence"] == 1.0
    # Profiling is known false, so it is not named; nothing is cited for 6(3).
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]
    assert ARTICLE_6_3 not in env["source_nodes"] and ARTICLE_6_PARAGRAPH_4 not in env["source_nodes"]
    # An unknown candidate does not hold the Article 27(1) block (iv).
    assert env["answer"]["fria"]["applicability"] == "does_not_apply"


def test_every_unknown_condition_and_an_unknown_profiling_are_named(dump):
    features = _features(true=("annex_iii_4a_recruitment",), absent=(*CONDITION_FACTS, "profiling_of_natural_persons"),
                         domain=None)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is None
    assert _unknown_condition_lines(env) == [
        ARTICLE_6_3_UNKNOWN_CONDITION_LINE.format(flag=flag, label=label)
        for flag, _points, label in ARTICLE_6_3_CONDITIONS
    ]
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE in env["missing_facts"]
    assert env["status"] == "potentially_applicable"


def test_profiling_true_settles_the_candidate_false_whatever_is_unknown(dump):
    features = _features(true=("annex_iii_4a_recruitment", "profiling_of_natural_persons"),
                         absent=CONDITION_FACTS, domain=None)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is False
    assert _unknown_condition_lines(env) == []
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]
    assert env["status"] == "potentially_applicable"


def test_profiling_true_cancels_a_true_condition(dump):
    features = _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task", "profiling_of_natural_persons"),
                         domain=None)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is False
    assert "eu-ai-act:article-6:paragraph-3:subparagraph-3" in env["source_nodes"]
    assert ARTICLE_6_PARAGRAPH_4 not in env["source_nodes"] and ARTICLE_6_4_LINE not in env["legal_status_notes"]
    assert env["status"] == "potentially_applicable"


def test_every_condition_false_settles_the_candidate_false(dump):
    features = _features(true=("annex_iii_4a_recruitment",), absent=("profiling_of_natural_persons",), domain=None)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is False
    assert _unknown_condition_lines(env) == []
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]


@pytest.mark.parametrize("cid", ["C2", "C8"])
def test_an_answer_without_an_annex_iii_point_has_candidate_false_and_names_no_condition(dump, cid):
    features = AREA_CASES[cid]["features"]
    features = {**features, "flags": {k: v for k, v in features["flags"].items() if k not in CONDITION_FACTS}}
    env = classify_ai_system(features, dump)
    assert env["answer"]["annex_iii_category"] is None and env["answer"]["annex_iii_area_unconfirmed"] is None
    assert env["answer"]["article_6_3_exception_candidate"] is False
    assert _unknown_condition_lines(env) == []
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]


def test_area_alone_answer_carries_the_candidate(dump):  # C1 with narrow_procedural_task true
    features = _features(true=("narrow_procedural_task",), absent=("annex_iii_3a_admission",))
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3" and a["high_risk_routes"] == []
    assert a["article_6_3_exception_candidate"] is True
    assert {ARTICLE_6_3, POINT_A, ARTICLE_6_PARAGRAPH_4} <= set(env["source_nodes"])
    assert ARTICLE_6_4_LINE in env["legal_status_notes"] and FLAGGED_NOTE in env["legal_status_notes"]
    assert ("rule article_6_3: derogation condition 'narrow procedural task (point a)' met by narrow_procedural_task; "
            "the Article 6(3) derogation may apply but requires human legal judgment, no automatic downgrade"
            ) in a["rationale"]
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    # B185 Task 6 (spec G D-G92 (v), (8), ruling P13): the level rests on the
    # area, so the block gives the area's sentence first, then names the
    # candidate among the other causes; the field is the value it reads.
    assert a["fria"]["applicability"] == "unknown"
    assert a["fria"]["rationale"] == [
        FRIA_AREA_ALONE_REASON.format(domain="education", number=3),
        FRIA_OTHER_CAUSES_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["article_6_3_candidate"]),
    ]


def test_area_alone_answer_with_profiling_true_has_candidate_false(dump):
    features = _features(true=("narrow_procedural_task", "profiling_of_natural_persons"),
                         absent=("annex_iii_3a_admission",))
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    assert a["article_6_3_exception_candidate"] is False
    assert ARTICLE_6_PARAGRAPH_4 not in env["source_nodes"]
    assert ARTICLE_6_3 not in a["fria"]["basis_nodes"]


def test_area_alone_answer_with_a_condition_unknown_has_candidate_null(dump):
    features = _features(absent=("annex_iii_3a_admission", "preparatory_task"))
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    assert a["article_6_3_exception_candidate"] is None
    assert _unknown_condition_lines(env) == [
        ARTICLE_6_3_UNKNOWN_CONDITION_LINE.format(
            flag="preparatory_task",
            label="preparatory task to an assessment relevant for the purposes of the use cases listed in "
                  "Annex III (point d)",
        )
    ]
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]
    assert ARTICLE_6_3 not in a["fria"]["basis_nodes"]


def test_article_6_1_exit_with_an_unconfirmed_area_carries_the_candidate(dump):
    """The field and the Article 27 block agree on the Article 6(1) exit with a
    point that rests on the area; the status stays the route's (iv)."""
    features = _features(true=("narrow_procedural_task",), absent=("annex_iii_3a_admission",), **P61,
                         annex_i_section_b_legislation=False)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["high_risk_routes"] == ["article_6_1"] and a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    assert a["article_6_3_exception_candidate"] is True
    assert env["status"] == "potentially_applicable" and env["confidence"] == 1.0
    assert ARTICLE_6_3_BOTH_ROUTES_NOTE in env["legal_status_notes"] and ARTICLE_6_4_LINE in env["legal_status_notes"]
    # B185 Task 6 (spec G D-G92 (v), passage (k)): beside the Article 6(1)
    # route the block gives the area's sentence; on a Section A product the
    # candidate is no cause of review, so no sentence says the classification
    # is not settled, and none says the system remains under Article 6(2).
    assert a["fria"]["applicability"] == "unknown"
    assert a["fria"]["rationale"] == [FRIA_AREA_BESIDE_ARTICLE_6_1_REASON.format(domain="education", number=3)]


def test_both_routes_candidate_follows_the_annex_iii_part_and_keeps_the_route_status(dump):  # C16
    env = classify_ai_system(AREA_CASES["C16"]["features"], dump)
    a = env["answer"]
    assert a["article_6_3_exception_candidate"] is True and env["status"] == "potentially_applicable"
    assert {ARTICLE_6_3, POINT_A, ARTICLE_6_PARAGRAPH_4} <= set(env["source_nodes"])
    assert ARTICLE_6_4_LINE in env["legal_status_notes"] and ARTICLE_6_3_BOTH_ROUTES_NOTE in env["legal_status_notes"]
    assert ARTICLE_6_3_BOTH_ROUTES_LINE.format(
        label="narrow procedural task (point a)", flag="narrow_procedural_task"
    ) in a["rationale"]
    texts = [*a["rationale"], *env["legal_status_notes"]]
    assert not any("flagged for human review" in t or "until a human legal reviewer decides" in t for t in texts)
    assert not any(t.startswith("rule article_6_3:") for t in a["rationale"])
    # The Article 27 block keeps today's candidacy sentence (P29).
    assert a["fria"]["applicability"] == "unknown" and ARTICLE_6_3 in a["fria"]["basis_nodes"]


def test_both_routes_with_a_condition_unknown_names_it_and_keeps_the_status(dump):
    features = _features(true=("annex_iii_4a_recruitment",), absent=("narrow_procedural_task",), domain=None,
                         **P61, annex_i_section_b_legislation=False)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is None
    assert len(_unknown_condition_lines(env)) == 1
    assert env["status"] == "potentially_applicable" and env["confidence"] == 1.0


def test_section_b_candidate_keeps_the_review_status(dump):  # C21 (I1)
    env = classify_ai_system(AREA_CASES["C21"]["features"], dump)
    assert env["answer"]["article_6_3_exception_candidate"] is True and env["answer"]["annex_i_section"] == "B"
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert FLAGGED_NOTE in env["legal_status_notes"]


@pytest.mark.parametrize("cid", ["C16", "C21", "C22"])
def test_article_6_4_line_with_every_candidate(dump, cid):
    env = classify_ai_system(AREA_CASES[cid]["features"], dump)
    assert env["answer"]["article_6_3_exception_candidate"] is True
    assert ARTICLE_6_PARAGRAPH_4 in env["source_nodes"]
    assert env["legal_status_notes"].count(ARTICLE_6_4_LINE) == 1
    # Article 49 is named in the line, not cited (ruling P9).
    assert not any(node.startswith("eu-ai-act:article-49") for node in env["source_nodes"])


def test_a_candidate_with_profiling_unknown_names_profiling(dump):
    features = _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"),
                         absent=("profiling_of_natural_persons",), domain=None)
    env = classify_ai_system(features, dump)
    assert env["answer"]["article_6_3_exception_candidate"] is True
    assert PROFILING_UNKNOWN_WITH_CONDITION in env["missing_facts"]
    assert ARTICLE_6_3_UNKNOWN_PROFILING_LINE not in env["missing_facts"]


@pytest.mark.parametrize("cid", list(AREA_CASES))
def test_the_field_and_the_article_27_block_read_one_value(dump, cid):
    """On every case the Article 27 block holds at unknown for the candidacy
    exactly when the field is true (iv)."""
    env = classify_ai_system(AREA_CASES[cid]["features"], dump)
    a = env["answer"]
    candidacy_sentence = any("Article 6(3) derogation candidacy" in line for line in a["fria"]["rationale"])
    assert candidacy_sentence == (a["article_6_3_exception_candidate"] is True), cid


def test_the_rejected_input_keeps_candidate_false(dump):
    env = classify_ai_system({"flags": {"no_such_fact": True}}, dump)
    assert env["status"] == "rejected_as_unsupported"
    assert env["answer"]["article_6_3_exception_candidate"] is False


def test_section_b_product_with_an_unconfirmed_area_and_a_candidate_stays_marked(dump):
    """Passage (k): a Section B product is marked with a candidate; on the
    Article 6(1) exit its point rests on the area, whose unknown listed uses
    already mark it (R39), so the status is review and the field is true."""
    features = _features(true=("narrow_procedural_task",), absent=("annex_iii_3a_admission",), **P61,
                         annex_i_section_b_legislation=True)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["high_risk_routes"] == ["article_6_1"] and a["annex_i_section"] == "B"
    assert a["article_6_3_exception_candidate"] is True
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert ARTICLE_6_3_BOTH_ROUTES_NOTE in env["legal_status_notes"]

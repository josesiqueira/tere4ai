"""Article 5(1)(h) reads law_enforcement_purpose (Article 3(46)) and the point (h) sentence (B184, D-G91, DEC-32).

Point (h) is proven with real_time_remote_biometric_public and
law_enforcement_purpose both true (and the carve-out known false), ruled out
when either is known false, and marked for human review with the purpose
named while the purpose is unknown (DEC-18 as amended by DEC-32). When point
(h) is the only prohibition that fired, the classification's note and the
applicable requirements' message say that the Act prohibits the use for the
purposes of law enforcement and not the placing on the market, and that the
system is listed in Annex III point 1(a); with another point beside it the
general sentence stays (rulings R2, R12, P8). On the unacceptable_risk exit
only Article 5 is cited (ruling R14). Offline: the published Layer 1 dump on
disk, skipped when it is absent.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.b184_cases import all_false
from tests.unit.b184_cases import case as _case

from tere4ai.mcp_server.classify import (
    ARTICLE_5_POINT_H,
    ARTICLE_5_POINT_H_FRAGMENT,
    POINT_H_PRACTICE_NOTE_END,
    PROHIBITED_PRACTICE_NOTE_END,
    classify_ai_system,
)
from tere4ai.mcp_server.requirements import (
    PROHIBITED_MESSAGE,
    PROHIBITED_MESSAGE_POINT_H,
    get_applicable_requirements,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
POINT_1A = "eu-ai-act:annex-iii:point-1:a"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")

POLICE_LFR = dict(biometric_identification=True, real_time_remote_biometric_public=True,
                  law_enforcement_purpose=True, rtrb_strictly_necessary_authorised=False)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def test_finding_7_police_live_facial_recognition_is_prohibited_by_the_purpose_fact(dump):
    """Ruling R14: the prohibited answer cites only Article 5; the field still
    names the listed use that is true (biometric_identification, point 1(a))."""
    env = classify_ai_system(_case(all_false(**POLICE_LFR), domain="law_enforcement"), dump)
    a = env["answer"]
    assert a["risk_category"] == "unacceptable_risk" and a["unacceptable_risk"] is True
    assert env["source_nodes"] == [ARTICLE_5_POINT_H]
    assert a["annex_iii_listed_uses"] == [POINT_1A]
    assert ("rule unacceptable_risk: flag real_time_remote_biometric_public + law_enforcement_purpose matches "
            f"{ARTICLE_5_POINT_H} ({ARTICLE_5_POINT_H_FRAGMENT})") in a["rationale"]


def test_point_h_names_the_purpose_fact_when_unknown(dump):
    flags = {k: v for k, v in all_false(**POLICE_LFR).items() if k != "law_enforcement_purpose"}
    env = classify_ai_system(_case(flags), dump)
    assert env["answer"]["unacceptable_risk"] is None and env["status"] == "requires_human_review"
    assert ("flags.law_enforcement_purpose is unknown while flags.real_time_remote_biometric_public is true; "
            "Article 5(1) point (h) applies only to use for the purposes of law enforcement (Article 3(46))") in env["missing_facts"]


def test_point_h_is_ruled_out_when_the_purpose_is_false(dump):
    """Not prohibited, so the point 1(a) unit is cited as Task 2 built it."""
    env = classify_ai_system(_case(all_false(**{**POLICE_LFR, "law_enforcement_purpose": False})), dump)
    assert env["answer"]["unacceptable_risk"] is False and env["answer"]["risk_category"] == "high_risk"
    assert env["answer"]["annex_iii_listed_uses"] == [POINT_1A]
    assert POINT_1A in env["source_nodes"] and ARTICLE_5_POINT_H not in env["source_nodes"]


def test_point_h_is_ruled_out_by_the_carve_out_with_the_purpose_true(dump):
    env = classify_ai_system(_case(all_false(**{**POLICE_LFR, "rtrb_strictly_necessary_authorised": True})), dump)
    assert env["answer"]["unacceptable_risk"] is False and env["answer"]["risk_category"] == "high_risk"
    assert POINT_1A in env["source_nodes"] and ARTICLE_5_POINT_H not in env["source_nodes"]


def test_point_h_is_ruled_out_by_the_purpose_false_while_rtrb_is_absent(dump):  # DEC-18 as amended
    flags = {k: v for k, v in all_false(law_enforcement_purpose=False).items() if k != "real_time_remote_biometric_public"}
    env = classify_ai_system(_case(flags), dump)
    assert not any(m.startswith("flags.real_time_remote_biometric_public is unknown (prohibition-relevant")
                   for m in env["missing_facts"])
    assert env["answer"]["unacceptable_risk"] is False


def test_point_h_stays_open_while_rtrb_and_the_purpose_are_absent(dump):
    flags = {k: v for k, v in all_false().items()
             if k not in ("real_time_remote_biometric_public", "law_enforcement_purpose")}
    env = classify_ai_system(_case(flags), dump)
    assert ("flags.real_time_remote_biometric_public is unknown (prohibition-relevant, Article 5); "
            "absence is not treated as false") in env["missing_facts"]
    assert env["answer"]["unacceptable_risk"] is None


def test_finding_10_point_h_alone_says_the_use_is_prohibited_not_the_placing_on_the_market(dump):
    env = classify_ai_system(_case(all_false(**POLICE_LFR)), dump)
    assert env["legal_status_notes"] == [f"{ARTICLE_5_POINT_H}: this practice is a prohibited AI practice under Article 5(1) "
                                         f"({ARTICLE_5_POINT_H_FRAGMENT}); {POINT_H_PRACTICE_NOTE_END}"]


def test_point_h_beside_another_point_keeps_the_general_sentence(dump):
    env = classify_ai_system(_case(all_false(**POLICE_LFR, subliminal_or_manipulative=True, causes_significant_harm=True)), dump)
    article_5_notes = [n for n in env["legal_status_notes"] if ":article-5:" in n]
    assert len(article_5_notes) == 2
    assert all(n.endswith(PROHIBITED_PRACTICE_NOTE_END) for n in article_5_notes)
    assert not any(POINT_H_PRACTICE_NOTE_END in n for n in env["legal_status_notes"])


def test_finding_10_requirements_for_point_h_alone_give_the_point_h_message(dump, norms):
    cls = classify_ai_system(_case(all_false(**POLICE_LFR)), dump)
    req = get_applicable_requirements(cls, norms, dump)
    assert req["answer"]["message"] == PROHIBITED_MESSAGE_POINT_H
    assert req["source_nodes"] == [ARTICLE_5_POINT_H]  # requirements.py keeps only the ":article-5" nodes
    assert req["answer"]["requirements_by_article"] == {}


def test_requirements_point_h_beside_point_a_keeps_the_general_message(dump, norms):
    cls = classify_ai_system(_case(all_false(**POLICE_LFR, subliminal_or_manipulative=True, causes_significant_harm=True)), dump)
    assert get_applicable_requirements(cls, norms, dump)["answer"]["message"] == PROHIBITED_MESSAGE


def test_requirements_for_another_point_alone_keep_the_general_message(dump, norms):
    cls = classify_ai_system(_case(all_false(subliminal_or_manipulative=True, causes_significant_harm=True)), dump)
    assert get_applicable_requirements(cls, norms, dump)["answer"]["message"] == PROHIBITED_MESSAGE


def test_point_h_beside_point_ba_gives_the_general_sentence_and_the_general_message(dump, norms):  # Task 3 review (c)
    cls = classify_ai_system(_case(all_false(**POLICE_LFR, generates_nonconsensual_intimate_material=True)), dump)
    article_5_notes = [n for n in cls["legal_status_notes"] if "prohibited AI practice under Article 5(1)" in n]
    assert len(article_5_notes) == 2
    assert all(n.endswith(PROHIBITED_PRACTICE_NOTE_END) for n in article_5_notes)
    assert not any(POINT_H_PRACTICE_NOTE_END in n for n in cls["legal_status_notes"])
    assert all(":article-5:" in node for node in cls["source_nodes"])  # ruling R14
    assert get_applicable_requirements(cls, norms, dump)["answer"]["message"] == PROHIBITED_MESSAGE

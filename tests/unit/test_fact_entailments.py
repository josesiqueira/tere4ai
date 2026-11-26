"""The facts corrected by the Act's definitions, and fact_conflicts (B184, D-G91 (6) and (10), DEC-32).

Four pairs of facts follow from the Act's definitions (ruling P9): a narrower
fact true makes the wider one true. When the wider fact was answered false it
is read as true, the pair is named in fact_conflicts and among the missing
facts, and the status is requires_human_review with confidence 0.5 on every
exit, the level unchanged (ruling R7). When the wider fact is unknown it is
read as true with a line in the rationale and no entry (ruling R6). The facts
are corrected once, where classify_ai_system receives them, so the level, the
Article 27 block and the high-risk routes read the same facts (ruling R4,
P11). On the unacceptable_risk exit only Article 5 is cited (ruling R14).
Offline: the published Layer 1 dump on disk, skipped when it is absent.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tests.unit.b184_cases import all_false
from tests.unit.b184_cases import case as _case

from tere4ai.mcp_server.classify import (
    ARTICLE_5_POINT_H,
    FACT_ENTAILMENTS,
    POINT_H_PRACTICE_NOTE_END,
    PROHIBITION_FACT_CONFLICT_CLAUSE,
    apply_entailments,
    classify_ai_system,
    fact_conflict_line,
)
from tere4ai.mcp_server.requirements import PROHIBITED_MESSAGE, get_applicable_requirements

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
SERVER_PATH = ROOT / "src" / "tere4ai" / "mcp_server" / "server.py"
CLASSIFY_PATH = ROOT / "src" / "tere4ai" / "mcp_server" / "classify.py"
# The sentences kept for every cause of review other than a fact conflict alone.
# B185 Task 6 (spec G D-G92 (8), ruling P13): the block names every cause of
# review in order; an unknown Article 5 fact is the first.
FRIA_UNSETTLED_ARTICLE_5 = ("the risk classification is high-risk but not settled: an unknown Article 5 fact could "
                            "change the level to Unacceptable risk; FRIA applicability stays unknown until the "
                            "classification is confirmed")
FRIA_UNSETTLED_ARTICLE_5_AND_CONFLICT = (
    "the risk classification is high-risk but not settled: an unknown Article 5 fact could change the level to "
    "Unacceptable risk; answers contradict a definition of the Act (fact_conflicts) and one answer of each pair is "
    "wrong, so the classification could change once they are corrected; FRIA applicability stays unknown until "
    "the classification is confirmed")
PROVISIONAL_NOTE_OLD = ("These requirements are provisional pending the human-review determination of the "
                        "classification. The risk category is tentative and could change, for example to "
                        "Unacceptable risk, which yields zero requirements.")
CONFLICT_REASON = ("answers contradict a definition of the Act (fact_conflicts) and one answer of each pair is "
                   "wrong, so the classification could change once they are corrected")
POINT_1A = "eu-ai-act:annex-iii:point-1:a"
POINT_1B = "eu-ai-act:annex-iii:point-1:b"
POINT_G = "eu-ai-act:article-5:paragraph-1:point-g"
STATUS_LINE = "status lowered to requires_human_review: answers contradict a definition of the Act: see fact_conflicts"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")

POLICE_LFR = dict(real_time_remote_biometric_public=True, law_enforcement_purpose=True,
                  rtrb_strictly_necessary_authorised=False)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def test_the_entailments_are_the_four_pairs_of_the_acts_definitions():
    assert FACT_ENTAILMENTS == (
        ("biometric_categorisation", "biometric_categorisation_system", "eu-ai-act:article-3:paragraph-1:point-40"),
        ("biometric_categorisation", "biometric_categorisation_sensitive_or_protected_attributes", "eu-ai-act:annex-iii:point-1:b"),
        ("real_time_remote_biometric_public", "biometric_identification", "eu-ai-act:article-3:paragraph-1:point-42"),
        ("emotion_recognition_workplace_or_education", "emotion_recognition", "eu-ai-act:article-3:paragraph-1:point-39"),
    )


def test_each_provision_of_the_entailments_is_a_unit_of_the_build(dump):
    ids = {n["id"] for n in dump["nodes"] if isinstance(n, dict) and "id" in n}
    assert {provision for _n, _w, provision in FACT_ENTAILMENTS} <= ids


def test_the_conflict_line_is_the_specs_sentence():
    assert fact_conflict_line("real_time_remote_biometric_public", "biometric_identification",
                              "eu-ai-act:article-3:paragraph-1:point-42") == (
        "flags.biometric_identification was answered false while flags.real_time_remote_biometric_public is true; "
        "eu-ai-act:article-3:paragraph-1:point-42 makes the first follow from the second, so it is read as true; "
        "one of the two answers is wrong")


def test_apply_entailments_reads_only_true_and_false_and_never_changes_the_input():
    flags = {"biometric_categorisation": True, "biometric_categorisation_system": False,
             "real_time_remote_biometric_public": True, "biometric_identification": "yes",
             "emotion_recognition_workplace_or_education": None}
    before = dict(flags)
    corrected, conflicts, lines = apply_entailments(flags)
    assert flags == before
    assert corrected["biometric_categorisation_system"] is True
    assert corrected["biometric_categorisation_sensitive_or_protected_attributes"] is True
    assert corrected["biometric_identification"] == "yes"  # not a boolean: left for the schema to refuse
    assert "emotion_recognition" not in corrected  # the narrower fact is not true
    assert corrected["biometric_categorisation"] is True and corrected["real_time_remote_biometric_public"] is True
    assert [c["wider"] for c in conflicts] == ["biometric_categorisation_system"]
    assert lines == ["flags.biometric_categorisation_sensitive_or_protected_attributes is unknown while "
                     "flags.biometric_categorisation is true; eu-ai-act:annex-iii:point-1:b makes the first "
                     "follow from the second, so it is read as true"]


def test_finding_9_emotion_at_work_with_exception_and_wider_fact_false_is_high_risk_for_review(dump):
    env = classify_ai_system(_case(all_false(emotion_recognition_workplace_or_education=True,
                                             emotion_recognition_medical_or_safety=True)), dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["annex_iii_category"] == "eu-ai-act:annex-iii:point-1"
    point_39 = "eu-ai-act:article-3:paragraph-1:point-39"
    assert a["fact_conflicts"] == [{"narrower": "emotion_recognition_workplace_or_education", "wider": "emotion_recognition",
                                    "provision": point_39,
                                    "note": fact_conflict_line("emotion_recognition_workplace_or_education", "emotion_recognition", point_39)}]
    assert a["fact_conflicts"][0]["note"] in env["missing_facts"]
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert "eu-ai-act:article-50:paragraph-3" in a["transparency_duties"]
    assert STATUS_LINE in a["rationale"]
    assert a["rationale"].index(STATUS_LINE) > 0  # ruling P10: after the core's lines
    assert a["annex_iii_listed_uses"] == ["eu-ai-act:annex-iii:point-1:c"]


def test_a_conflict_marks_the_unacceptable_exit_without_changing_the_level(dump):
    env = classify_ai_system(_case(all_false(biometric_categorisation=True, biometric_categorisation_lawful_or_law_enforcement=False)), dump)
    assert env["answer"]["risk_category"] == "unacceptable_risk" and env["answer"]["unacceptable_risk"] is True
    assert {c["wider"] for c in env["answer"]["fact_conflicts"]} == {"biometric_categorisation_system",
                                                                      "biometric_categorisation_sensitive_or_protected_attributes"}
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert env["source_nodes"] == [POINT_G]  # ruling R14
    assert env["answer"]["annex_iii_listed_uses"] == [POINT_1B]
    assert env["answer"]["transparency_duties"] == []


def test_entailment_from_unknown_wider_fact_leaves_the_status(dump):
    flags = {k: v for k, v in all_false(biometric_categorisation=True, biometric_categorisation_lawful_or_law_enforcement=False).items()
             if k not in ("biometric_categorisation_system", "biometric_categorisation_sensitive_or_protected_attributes")}
    env = classify_ai_system(_case(flags), dump)
    assert env["answer"]["fact_conflicts"] == []
    assert env["status"] == "potentially_applicable" and env["confidence"] == 1.0
    assert any(line.startswith("flags.biometric_categorisation_system is unknown while flags.biometric_categorisation is true;")
               for line in env["answer"]["rationale"])
    assert not any("biometric_categorisation_system is unknown" in m for m in env["missing_facts"])
    assert not any("biometric_categorisation_sensitive_or_protected_attributes is unknown" in m for m in env["missing_facts"])
    assert env["source_nodes"] == [POINT_G]  # ruling R14


def test_point_h_sentence_with_biometric_identification_unknown_shows_point_1a(dump):  # Task 3 review (a)
    flags = {k: v for k, v in all_false(**POLICE_LFR).items() if k != "biometric_identification"}
    env = classify_ai_system(_case(flags), dump)
    a = env["answer"]
    assert a["risk_category"] == "unacceptable_risk" and env["status"] == "potentially_applicable"
    assert env["legal_status_notes"][-1].endswith(POINT_H_PRACTICE_NOTE_END)
    assert a["annex_iii_listed_uses"] == [POINT_1A] and a["fact_conflicts"] == []
    assert env["source_nodes"] == [ARTICLE_5_POINT_H]  # ruling R14
    assert any(line.startswith("flags.biometric_identification is unknown while flags.real_time_remote_biometric_public is true;")
               for line in a["rationale"])


def test_point_h_sentence_with_biometric_identification_false_is_a_conflict(dump):  # Task 3 review (a)
    env = classify_ai_system(_case(all_false(**POLICE_LFR)), dump)
    a = env["answer"]
    assert a["risk_category"] == "unacceptable_risk" and a["unacceptable_risk"] is True
    # Final fix wave (M3): the marked answer's note adds the clause after the point (h) sentence.
    assert env["legal_status_notes"][-1].endswith(f"{POINT_H_PRACTICE_NOTE_END}. {PROHIBITION_FACT_CONFLICT_CLAUSE}")
    assert a["annex_iii_listed_uses"] == [POINT_1A]
    assert [(c["narrower"], c["wider"]) for c in a["fact_conflicts"]] == [
        ("real_time_remote_biometric_public", "biometric_identification")]
    assert env["status"] == "requires_human_review" and env["confidence"] == 0.5
    assert env["source_nodes"] == [ARTICLE_5_POINT_H]  # ruling R14


def test_the_routes_and_the_article_27_block_read_the_corrected_facts(dump):  # review I6
    flags = {k: v for k, v in all_false(emotion_recognition_workplace_or_education=True,
                                        emotion_recognition_medical_or_safety=True).items() if k != "emotion_recognition"}
    env = classify_ai_system(_case(flags, deployer={"body_governed_by_public_law": True,
                                                    "private_entity_providing_public_services": False}), dump)
    a = env["answer"]
    assert a["fact_conflicts"] == [] and env["status"] == "potentially_applicable"
    assert a["high_risk_routes"] == ["article_6_2"]
    assert a["fria"]["applicability"] == "applies"
    # fria.py's deployer branch: Article 27(1), then each Annex III point other than point 2.
    assert a["fria"]["basis_nodes"] == ["eu-ai-act:article-27:paragraph-1", "eu-ai-act:annex-iii:point-1"]
    assert a["fria"]["missing_facts"] == []


def test_a_listed_use_true_by_a_definition_is_not_said_to_be_answered_yes(dump):  # Task 4 review, Task 5
    """biometric_identification was answered no and is read as true by Article
    3(42); on the Article 6(1) exit no "rule high_risk" line names it, so its
    unit gets the listed-use line, which must not say it was answered yes."""
    flags = all_false(annex_i_covered_product=True, third_party_conformity_assessment_required=True,
                      real_time_remote_biometric_public=True)
    env = classify_ai_system(_case(flags), dump)
    a = env["answer"]
    assert a["fact_conflicts"][0]["wider"] == "biometric_identification"
    assert a["annex_iii_listed_uses"] == [POINT_1A] and POINT_1A in env["source_nodes"]
    assert ("Annex III listed use true: flag biometric_identification is true for eu-ai-act:annex-iii:point-1:a; "
            "cited with the answer") in a["rationale"]
    assert not any("answered yes" in line for line in a["rationale"])


def test_answering_no_never_settles_more_than_unknown(dump):
    base = all_false(real_time_remote_biometric_public=True, law_enforcement_purpose=False)
    unknown = {k: v for k, v in base.items() if k != "biometric_identification"}
    answered_no = classify_ai_system(_case(base), dump)
    left_unknown = classify_ai_system(_case(unknown), dump)
    assert answered_no["answer"]["risk_category"] == "high_risk"
    assert left_unknown["answer"]["risk_category"] == "high_risk"
    assert answered_no["status"] == "requires_human_review" and left_unknown["status"] == "potentially_applicable"


def test_exception_without_its_practice_is_not_a_conflict(dump):
    env = classify_ai_system(_case(all_false(emotion_recognition_medical_or_safety=True)), dump)
    assert env["answer"]["fact_conflicts"] == [] and env["answer"]["risk_category"] == "minimal_risk"


@pytest.mark.parametrize("flags,level", [
    (dict(annex_i_covered_product=True, third_party_conformity_assessment_required=True, annex_i_section_b_legislation=False), "high_risk"),
    (dict(interacts_with_natural_persons=True), "limited_risk"),
])
def test_no_conflict_entry_on_the_other_exits(dump, flags, level):
    env = classify_ai_system(_case(all_false(**flags)), dump)
    assert env["answer"]["risk_category"] == level and env["answer"]["fact_conflicts"] == []


def test_no_conflict_entry_on_the_undetermined_exit(dump):
    # The third-party assessment answered false rules the Article 6(1) route out (B123, R4), so both are left unknown.
    flags = {k: v for k, v in all_false().items()
             if k not in ("annex_i_covered_product", "third_party_conformity_assessment_required")}
    env = classify_ai_system(_case(flags), dump)
    assert env["answer"]["risk_category"] == "undetermined" and env["answer"]["fact_conflicts"] == []


def test_the_input_is_not_changed_and_the_rejected_answer_has_no_conflicts(dump):
    features = _case(all_false(emotion_recognition_workplace_or_education=True, emotion_recognition_medical_or_safety=True))
    before = json.dumps(features, sort_keys=True)
    classify_ai_system(features, dump)
    assert json.dumps(features, sort_keys=True) == before
    assert classify_ai_system({"description": "short"}, dump)["answer"]["fact_conflicts"] == []


def test_a_rejected_input_with_a_contradiction_keeps_its_rejection(dump):
    flags = all_false(emotion_recognition_workplace_or_education=True, emotion_recognition_medical_or_safety=True,
                      law_enforcement_use=True)  # a removed fact: refused by name
    env = classify_ai_system(_case(flags), dump)
    assert env["status"] == "rejected_as_unsupported" and env["answer"]["fact_conflicts"] == []
    assert not any("contradict a definition" in line for line in env["answer"]["rationale"])


def test_a_marked_answer_holds_the_article_27_block_open(dump):  # P11
    env = classify_ai_system(_case(all_false(emotion_recognition_workplace_or_education=True, emotion_recognition_medical_or_safety=True)), dump)
    assert env["answer"]["fria"]["applicability"] == "unknown"


# Fix round 1 of the Task 4 review: the mark reaches the applicable
# requirements and the Article 27 block, and each states its true reason.

PROHIBITED_MARKED = dict(biometric_categorisation=True, biometric_categorisation_lawful_or_law_enforcement=False)
HIGH_RISK_MARKED = dict(emotion_recognition_workplace_or_education=True, emotion_recognition_medical_or_safety=True)


def test_requirements_of_a_marked_prohibited_answer_keep_the_mark(dump, norms):  # review I1 (a)
    cls = classify_ai_system(_case(all_false(**PROHIBITED_MARKED)), dump)
    notes = [c["note"] for c in cls["answer"]["fact_conflicts"]]
    assert len(notes) == 2
    for given in (cls, cls["answer"]):  # the envelope and the bare answer
        req = get_applicable_requirements(given, norms, dump)
        assert req["status"] == "requires_human_review" and req["confidence"] == 0.5
        assert all(note in req["missing_facts"] for note in notes)
        assert req["answer"]["requirements_by_article"] == {} and req["answer"]["summary"] == {"returned": 0}
        # Final fix wave (M3): the message of a marked prohibited answer adds the clause.
        assert req["answer"]["message"] == f"{PROHIBITED_MESSAGE} {PROHIBITION_FACT_CONFLICT_CLAUSE}"
    # Fix round 2: the envelope's requirements carry every missing fact of the classification.
    assert get_applicable_requirements(cls, norms, dump)["missing_facts"] == cls["missing_facts"]
    assert get_applicable_requirements(cls, norms, dump)["source_nodes"] == [POINT_G]  # ruling R14


SMALLEST_MARKED_PROHIBITED = {"biometric_categorisation": True, "biometric_categorisation_system": False,
                              "biometric_categorisation_lawful_or_law_enforcement": False}


def test_requirements_of_a_marked_prohibited_answer_carry_every_missing_fact(dump, norms):  # fix round 2
    cls = classify_ai_system(_case(dict(SMALLEST_MARKED_PROHIBITED)), dump)
    assert cls["answer"]["risk_category"] == "unacceptable_risk" and cls["status"] == "requires_human_review"
    notes = [c["note"] for c in cls["answer"]["fact_conflicts"]]
    assert len(cls["missing_facts"]) > len(notes)  # unknown facts beside the conflict line
    envelope_form = get_applicable_requirements(cls, norms, dump)
    assert envelope_form["missing_facts"] == cls["missing_facts"]  # every one, in the classification's order
    assert len(envelope_form["missing_facts"]) == len(set(envelope_form["missing_facts"]))
    assert envelope_form["status"] == "requires_human_review" and envelope_form["confidence"] == 0.5
    assert envelope_form["answer"]["requirements_by_article"] == {}
    assert envelope_form["answer"]["message"] == f"{PROHIBITED_MESSAGE} {PROHIBITION_FACT_CONFLICT_CLAUSE}"  # M3
    assert envelope_form["source_nodes"] == [POINT_G]  # ruling R14
    # The bare answer holds no missing facts, only fact_conflicts: its requirements carry the conflict lines,
    # each a line of the classification.
    bare_form = get_applicable_requirements(cls["answer"], norms, dump)
    assert bare_form["missing_facts"] == notes
    assert all(line in cls["missing_facts"] for line in bare_form["missing_facts"])
    assert bare_form["status"] == "requires_human_review" and bare_form["answer"]["requirements_by_article"] == {}


def test_requirements_of_an_unmarked_prohibited_answer_stay_settled(dump, norms):
    cls = classify_ai_system(_case(all_false(**PROHIBITED_MARKED, biometric_categorisation_system=True,
                                             biometric_categorisation_sensitive_or_protected_attributes=True)), dump)
    req = get_applicable_requirements(cls, norms, dump)
    assert req["status"] == "not_applicable" and req["confidence"] == 1.0 and req["missing_facts"] == []


def test_the_article_27_block_of_a_marked_prohibited_answer_is_unknown(dump):  # review I1 (b)
    fria = classify_ai_system(_case(all_false(**PROHIBITED_MARKED)), dump)["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert any(CONFLICT_REASON in line for line in fria["rationale"])
    unmarked = classify_ai_system(_case(all_false(**PROHIBITED_MARKED, biometric_categorisation_system=True,
                                                  biometric_categorisation_sensitive_or_protected_attributes=True)), dump)
    assert unmarked["answer"]["fria"]["applicability"] == "does_not_apply"


def test_a_conflict_alone_gives_its_own_reason_in_both_sentences(dump, norms):  # review I2
    cls = classify_ai_system(_case(all_false(**HIGH_RISK_MARKED),
                                   deployer={"body_governed_by_public_law": True,
                                             "private_entity_providing_public_services": False}), dump)
    assert cls["answer"]["unacceptable_risk"] is False and cls["answer"]["fact_conflicts"]
    fria = cls["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert any(CONFLICT_REASON in line for line in fria["rationale"])
    assert not any("Unacceptable risk" in line for line in fria["rationale"])
    req = get_applicable_requirements(cls, norms, dump)
    assert req["answer"]["provisional"] is True and req["status"] == "requires_human_review"
    assert CONFLICT_REASON in req["answer"]["provisional_note"]
    assert "Unacceptable risk" not in req["answer"]["provisional_note"]


@pytest.mark.parametrize("conflict", [True, False])
def test_an_unknown_article_5_fact_is_named_first_and_the_note_keeps_its_sentence(dump, norms, conflict):  # review I2
    flags = {k: v for k, v in all_false(**HIGH_RISK_MARKED).items() if k != "facial_image_scraping"}
    if not conflict:
        flags["emotion_recognition"] = True
    cls = classify_ai_system(_case(flags, deployer={"body_governed_by_public_law": True,
                                                    "private_entity_providing_public_services": False}), dump)
    assert cls["answer"]["unacceptable_risk"] is None and bool(cls["answer"]["fact_conflicts"]) is conflict
    # B185 Task 6: the block names the causes that hold, in order (D-G92 (8));
    # the requirements' note is Task 7's.
    expected = FRIA_UNSETTLED_ARTICLE_5_AND_CONFLICT if conflict else FRIA_UNSETTLED_ARTICLE_5
    assert cls["answer"]["fria"]["rationale"] == [expected]
    assert get_applicable_requirements(cls, norms, dump)["answer"]["provisional_note"] == PROVISIONAL_NOTE_OLD


def _docstring(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return " ".join((ast.get_docstring(node) or "").split())


def test_the_served_description_says_a_fact_is_true_as_answered_or_by_a_definition():  # review I3, M1
    served = _docstring(SERVER_PATH, "classify_ai_system")
    assert "listed use answered yes" not in served
    assert "triggered by a known fact" not in served
    assert ("annex_iii_listed_uses names the legal unit of every Annex III listed use that is true, as answered "
            "or as it follows from another fact by a definition of the Act") in served
    assert "triggered by a fact that is true, as answered or as it follows from a definition of the Act" in served
    assert "The list is empty when there is no such pair, and on a rejected input" in served
    core = _docstring(CLASSIFY_PATH, "_classify_core")
    assert "triggered by a known fact" not in core
    assert "triggered by a fact that is true, as answered or as it follows from a definition of the Act" in core

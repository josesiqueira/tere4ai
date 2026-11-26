"""The fixes of the two whole-change reviews of B184 (DEC-32, spec G D-G91).

The point (h) message from the bare answer form, the point (h) sentences
pinned word for word (ruling P8), the clause a prohibited answer marked by a
fact conflict carries, the line naming what replaces a fact that left the
schema, the domain rule the high-risk routes read, and the served description
of classify_ai_system. Offline: the published Layer 1 dump and norms file on
disk, skipped when absent.

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
    ANNEX_III_RULES,
    ARTICLE_5_POINT_H,
    POINT_H_PRACTICE_NOTE_END,
    PROHIBITED_PRACTICE_NOTE_END,
    REMOVED_FACT_REPLACEMENTS,
    classify_ai_system,
)
from tere4ai.mcp_server.requirements import (
    PROHIBITED_MESSAGE,
    PROHIBITED_MESSAGE_POINT_H,
    PROHIBITED_MESSAGE_POINT_NOT_NAMED,
    get_applicable_requirements,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
SERVER_PATH = ROOT / "src" / "tere4ai" / "mcp_server" / "server.py"
ARCHITECTURE_PATH = ROOT / "docs" / "architecture.md"
POINT_G = "eu-ai-act:article-5:paragraph-1:point-g"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")

POINT_H_ALONE = dict(real_time_remote_biometric_public=True, law_enforcement_purpose=True,
                     rtrb_strictly_necessary_authorised=False)
MARKED_PROHIBITED = {"biometric_categorisation": True, "biometric_categorisation_system": False,
                     "biometric_categorisation_lawful_or_law_enforcement": False}
CONFLICT_CLAUSE = ("This rests on the facts as read: answers contradict a definition of the Act (fact_conflicts), "
                   "so it stands for human review.")

# Ruling P8 of the plan (thesis sdd/2026-11-26-B184-fact-definitions/plan.md, Task 3, "Exact copy (P8)").
P8_NOTE_END = ("point (h) prohibits the use for the purposes of law enforcement in publicly accessible spaces and "
               "does not prohibit placing on the market; the system is listed in Annex III point 1(a), and no "
               "tailored requirement can make the prohibited use permissible")
P8_MESSAGE = ("This system falls under Article 5(1) point (h). The Act prohibits the use of real-time remote "
              "biometric identification systems in publicly accessible spaces for the purposes of law "
              "enforcement; point (h) does not prohibit placing such a system on the market, and the system is "
              "listed in Annex III point 1(a). Prohibited uses receive no applicable requirements, so no "
              "tailored requirement can make that use permissible. Seek legal review.")
# The sentences of an unmarked prohibited answer, word for word.
GENERAL_MESSAGE = ("This system falls under an Article 5 prohibited AI practice. Prohibited systems receive no "
                   "applicable requirements: placing on the market, putting into service, and use are banned, so "
                   "no tailored requirement can make the system permissible. Seek legal review.")
POINT_G_NOTE = (f"{POINT_G}: this practice is a prohibited AI practice under Article 5(1) (biometric "
                "categorisation deducing or inferring race, political opinions, trade union membership, "
                "religious or philosophical beliefs, sex life or sexual orientation); placing on the market, "
                "putting into service, and use are banned, so no tailored requirement can make the system "
                "permissible")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def _docstring(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return " ".join((ast.get_docstring(node) or "").split())


# I1: the bare answer form names the point it fired on.

@pytest.mark.parametrize("biometric_identification", [True, False])
def test_point_h_alone_gives_the_point_h_message_in_both_forms(dump, norms, biometric_identification):
    # The review's input sets every other fact false, biometric_identification included, which Article 3(42)
    # makes follow from real_time_remote_biometric_public: that answer is marked by a fact conflict (M3).
    cls = classify_ai_system(_case(all_false(**POINT_H_ALONE, biometric_identification=biometric_identification)),
                             dump)
    expected = PROHIBITED_MESSAGE_POINT_H + ("" if biometric_identification else f" {CONFLICT_CLAUSE}")
    assert bool(cls["answer"]["fact_conflicts"]) is not biometric_identification
    for given in (cls, cls["answer"]):
        req = get_applicable_requirements(given, norms, dump)
        assert req["answer"]["message"] == expected
        assert req["source_nodes"] == [ARTICLE_5_POINT_H]  # ruling R14
        assert req["answer"]["requirements_by_article"] == {}


def test_another_point_alone_gives_the_general_message_in_both_forms(dump, norms):
    cls = classify_ai_system(_case(all_false(subliminal_or_manipulative=True, causes_significant_harm=True)), dump)
    for given in (cls, cls["answer"]):
        assert get_applicable_requirements(given, norms, dump)["answer"]["message"] == PROHIBITED_MESSAGE


def test_a_bare_answer_that_names_no_point_makes_no_claim_about_placing_on_the_market(dump, norms):
    req = get_applicable_requirements({"risk_category": "unacceptable_risk"}, norms, dump)
    assert req["answer"]["message"] == PROHIBITED_MESSAGE_POINT_NOT_NAMED
    assert "placing" not in PROHIBITED_MESSAGE_POINT_NOT_NAMED
    assert "the classification's own note says which acts the point prohibits" in PROHIBITED_MESSAGE_POINT_NOT_NAMED
    assert req["source_nodes"] == ["eu-ai-act:article-5"]


# I2: the point (h) sentences, word for word as ruling P8 gives them.

def test_the_point_h_sentences_are_the_words_of_ruling_p8():
    assert POINT_H_PRACTICE_NOTE_END == P8_NOTE_END
    assert PROHIBITED_MESSAGE_POINT_H == P8_MESSAGE


@pytest.mark.parametrize("sentence", [P8_NOTE_END, P8_MESSAGE])
def test_each_point_h_sentence_says_the_three_things_of_d_g91_4(sentence):
    assert "use" in sentence and "for the purposes of law enforcement" in sentence
    assert "publicly accessible spaces" in sentence
    assert "does not prohibit placing" in sentence and "on the market" in sentence
    assert "listed in Annex III point 1(a)" in sentence


# M3: a prohibited answer marked by a fact conflict says it stands for review.

def test_a_marked_prohibited_answer_adds_the_clause_to_its_note_and_message(dump, norms):
    cls = classify_ai_system(_case(dict(MARKED_PROHIBITED)), dump)
    assert cls["status"] == "requires_human_review"
    assert cls["legal_status_notes"] == [f"{POINT_G_NOTE}. {CONFLICT_CLAUSE}"]
    for given in (cls, cls["answer"]):
        assert get_applicable_requirements(given, norms, dump)["answer"]["message"] == (
            f"{GENERAL_MESSAGE} {CONFLICT_CLAUSE}")


def test_an_unmarked_prohibited_answer_keeps_its_sentences_word_for_word(dump, norms):
    cls = classify_ai_system(_case(all_false(**{**MARKED_PROHIBITED, "biometric_categorisation_system": True,
                                                "biometric_categorisation_sensitive_or_protected_attributes": True})),
                             dump)
    assert cls["status"] == "potentially_applicable"
    assert cls["legal_status_notes"] == [POINT_G_NOTE]
    assert PROHIBITED_PRACTICE_NOTE_END in POINT_G_NOTE
    assert get_applicable_requirements(cls, norms, dump)["answer"]["message"] == GENERAL_MESSAGE
    assert PROHIBITED_MESSAGE == GENERAL_MESSAGE


# M2: a rejected input names what replaces a fact that left the schema.

def test_the_table_holds_the_seven_removed_facts_and_names_only_schema_facts():
    schema_flags = set(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["flags"]["properties"])
    assert set(REMOVED_FACT_REPLACEMENTS) == {
        "education_scoring_or_access", "employment_decisions", "essential_services_access", "law_enforcement_use",
        "migration_asylum_border_use", "justice_democratic_use", "preparatory_or_narrow_procedural_task"}
    assert not set(REMOVED_FACT_REPLACEMENTS) & schema_flags
    for line in REMOVED_FACT_REPLACEMENTS.values():
        named = {word.strip(",;()") for word in line.split()} & schema_flags
        assert named, line


def test_a_rejected_input_with_a_removed_fact_names_its_replacements(dump):
    features = _case(all_false(law_enforcement_use=True, employment_decisions=False))
    env = classify_ai_system(features, dump)
    assert env["status"] == "rejected_as_unsupported" and env["confidence"] == 0.0
    assert env["missing_facts"][0].startswith("schema validation: flags: Additional properties are not allowed")
    assert env["missing_facts"][1:] == [
        "flags.employment_decisions left the schema (DEC-32); answer annex_iii_4a_recruitment and "
        "annex_iii_4b_work_relationships (Annex III points 4(a) and 4(b))",
        "flags.law_enforcement_use left the schema (DEC-32); answer law_enforcement_purpose for Article 5(1) "
        "point (h), and annex_iii_6a_victim_risk, annex_iii_6b_polygraphs, annex_iii_6c_evidence_reliability, "
        "annex_iii_6d_offending_risk and annex_iii_6e_profiling for Annex III points 6(a) to 6(e)",
    ]
    assert env["answer"]["fact_conflicts"] == [] and env["answer"]["annex_iii_listed_uses"] == []
    assert env["answer"]["risk_category"] is None


def test_a_rejected_input_without_a_removed_fact_gets_no_extra_line(dump):
    env = classify_ai_system(_case(all_false(social_scoring="yes")), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert all(line.startswith("schema validation:") for line in env["missing_facts"])


# M6: the domain rule the high-risk routes read.

def test_the_routes_read_the_domain_rule(dump):
    point_5 = next(rule for rule in ANNEX_III_RULES if rule["node"] == "eu-ai-act:annex-iii:point-5")
    flags = all_false(annex_i_covered_product=True, third_party_conformity_assessment_required=True,
                      annex_i_section_b_legislation=False)
    assert all(flags[fact] is False for fact, _unit in point_5["uses"])
    env = classify_ai_system(_case(flags, domain="banking"), dump)
    assert env["answer"]["high_risk_routes"] == ["article_6_1"]
    flags.pop("annex_iii_5a_public_benefits")
    env = classify_ai_system(_case(flags, domain="banking"), dump)
    assert env["answer"]["high_risk_routes"] == ["article_6_1", "article_6_2"]


# M1, M8 and the rejected input: the served description.

def test_the_served_description_states_annex_iii_category_the_entry_and_the_rejection():
    served = _docstring(SERVER_PATH, "classify_ai_system")
    assert ("annex_iii_category is the first matching point when Annex III decided the level, and is null when "
            "the Article 6(1) route or a prohibition decided it, even if annex_iii_listed_uses names a listed use"
            ) in served
    assert "on the Article 6(1) route the listed uses are cited without their point" in served
    assert "an entry holds narrower, wider, provision (the legal unit of the definition) and note" in served
    assert ("An input the schema refuses returns status rejected_as_unsupported with the schema's errors in "
            "missing_facts, and a line for each fact that left the schema naming the facts that replace it"
            ) in served


def test_dec_32_records_annex_iii_category_and_the_section_b_domain_case():
    text = " ".join(ARCHITECTURE_PATH.read_text(encoding="utf-8").split())
    assert ("annex_iii_category is the first matching point when Annex III decided the level and null when the "
            "Article 6(1) route or a prohibition decided it, even when annex_iii_listed_uses names a listed use"
            ) in text
    assert "card B185 owns it" in text

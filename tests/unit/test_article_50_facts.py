"""Article 50 on every exit where it can apply, and the two duties of Article 50(4)
(B185 Task 5, spec G D-G92 (7) and (x), DEC-33, ruling P10).

An unknown trigger fact is named on every exit on which Article 50 can apply,
never on a refused input, an unacceptable_risk answer or a Section B product
served under Article 2(2). Article 50(4) gains two facts, one per duty of the
paragraph, each quoting its sentence: generates_deep_fake (a deep fake as
Article 3(60) defines it) and generates_public_interest_text (text published
to inform the public on matters of public interest). A fact that is true is a
trigger of limited_risk like the other Article 50 facts; an unknown one is
named and never changes the level (DEC-18). A deep fake fact does not make
generates_synthetic_content follow. The answer's note says "a fact that is
true" and no longer says that paragraph 4 is not decided by the rules.
Offline: the published Layer 1 dump, skipped when absent.

@implements: DEC-33
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from tests.unit.area_cases import AREA_CASES
from tests.unit.b184_cases import all_false, case
from tests.unit.flags_of_record import ARTICLE_50_RULES_OF_V9, FLAGS_OF_V9
from tests.unit.test_features_schema_descriptions import _normalised

from tere4ai.mcp_server.application_dates import dates_for
from tere4ai.mcp_server.classify import (
    ARTICLE_50_RULES,
    ARTICLE_50_SECTION_B_NOTE,
    ARTICLE_50_TRIGGER_FLAGS,
    ARTICLE_50_TRIGGERED_NOTE,
    FACT_ENTAILMENTS,
    classify_ai_system,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"

DEEP_FAKE = "generates_deep_fake"
PUBLIC_INTEREST_TEXT = "generates_public_interest_text"
PARAGRAPH_4 = "eu-ai-act:article-50:paragraph-4"
SUBPARAGRAPH_2 = "eu-ai-act:article-50:paragraph-4:subparagraph-2"
DEFINITION_60 = "eu-ai-act:article-3:paragraph-1:point-60"

# The two descriptions, word for word (the brief of Task 5; the quotations are
# the node texts of layer1.json, read 2026-11-26).
DEEP_FAKE_DESCRIPTION = (
    "Article 50(4), the Act's words: 'Deployers of an AI system that generates or manipulates image, audio or "
    "video content constituting a deep fake, shall disclose that the content has been artificially generated or "
    "manipulated'. Article 3(60) defines the term, the Act's words: 'deep fake means AI-generated or manipulated "
    "image, audio or video content that resembles existing persons, objects, places, entities or events and "
    "would falsely appear to a person to be authentic or truthful'. A use authorised by law to detect, prevent, "
    "investigate or prosecute criminal offences is false, the Act's words: 'This obligation shall not apply where "
    "the use is authorised by law to detect, prevent, investigate or prosecute criminal offence'. Content that "
    "forms part of an evidently artistic, creative, satirical, fictional or analogous work or programme is true: "
    "the duty stays and only its manner changes. True triggers the Article 50(4) disclosure duty of deployers; it "
    "says nothing about generates_synthetic_content. Absence is unknown."
)
PUBLIC_INTEREST_TEXT_DESCRIPTION = (
    "Article 50(4) second subparagraph, the Act's words: 'Deployers of an AI system that generates or manipulates "
    "text which is published with the purpose of informing the public on matters of public interest shall "
    "disclose that the text has been artificially generated or manipulated'. False where the Act's exception "
    "applies, the Act's words: 'This obligation shall not apply where the use is authorised by law to detect, "
    "prevent, investigate or prosecute criminal offences or where the AI-generated content has undergone a "
    "process of human review or editorial control and where a natural or legal person holds editorial "
    "responsibility for the publication of the content'. True triggers the Article 50(4) disclosure duty of "
    "deployers. Absence is unknown."
)
# The answer's note, word for word.
NOTE = (
    "eu-ai-act:article-50: the paragraphs in transparency_duties are triggered by a fact that is true, not proven "
    "to apply: their own exceptions (an interaction obvious to the person, assistive editing, uses authorised by "
    "law to detect, prevent, investigate or prosecute criminal offences in 50(1) and 50(2), uses permitted by law "
    "to detect, prevent or investigate criminal offences in 50(3)) and paragraph 5 are not decided by the rules; "
    "the two facts of 50(4) are false where its exceptions apply, and for a deep fake that forms part of an "
    "evidently artistic, creative, satirical, fictional or analogous work or programme the 50(4) duty stays and "
    "only its manner changes"
)
DEEP_FAKE_ROW = (DEEP_FAKE, PARAGRAPH_4, "a deep fake must be disclosed as artificially generated or manipulated")
PUBLIC_INTEREST_TEXT_ROW = (
    PUBLIC_INTEREST_TEXT, SUBPARAGRAPH_2,
    "text published to inform the public on matters of public interest must be disclosed as artificially "
    "generated or manipulated",
)
# The Annex I facts of the Article 6(1) route, both true.
P61 = {"annex_i_covered_product": True, "third_party_conformity_assessment_required": True}
DEPLOYER = {"body_governed_by_public_law": False, "private_entity_providing_public_services": False}


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dump_texts(dump) -> dict[str, str]:
    return {n["id"]: _normalised(n.get("text") or "") for n in dump["nodes"]
            if n.get("type") != "UnitVersion" and n.get("text")}


def _flags_schema() -> dict[str, dict]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["flags"]["properties"]


def _line(flag: str, node_id: str, listed: list[str]) -> str:
    """The missing-facts line of an absent Article 50 fact, as the classifier writes it."""
    consequence = (f"{node_id} is already listed through another trigger" if node_id in listed
                   else "that duty may be missing from transparency_duties")
    return (f"flags.{flag} is unknown (Article 50 transparency trigger, {node_id}); absence is not treated "
            f"as false, so {consequence}")


def _article_50_lines(env: dict) -> list[str]:
    return [line for line in env["missing_facts"] if "(Article 50 transparency trigger" in line]


def _without_article_50(flags: dict, keep: tuple[str, ...] = ()) -> dict:
    """The flags with every Article 50 trigger fact removed but those named in keep."""
    return {k: v for k, v in flags.items() if k not in ARTICLE_50_TRIGGER_FLAGS or k in keep}


def _expected_lines(env: dict, absent: list[str]) -> list[str]:
    listed = env["answer"]["transparency_duties"]
    return [_line(flag, node_id, listed) for flag, node_id, _note in ARTICLE_50_RULES if flag in absent]


# The rows and the facts ------------------------------------------------------

def test_the_two_article_50_4_rows_follow_the_other_rows():
    assert ARTICLE_50_RULES[-2:] == (DEEP_FAKE_ROW, PUBLIC_INTEREST_TEXT_ROW)
    assert ARTICLE_50_RULES[:4] == ARTICLE_50_RULES_OF_V9
    assert ARTICLE_50_TRIGGER_FLAGS[-2:] == (DEEP_FAKE, PUBLIC_INTEREST_TEXT)


def test_the_two_facts_stand_after_generates_synthetic_content_with_their_descriptions():
    flags = _flags_schema()
    names = list(flags)
    at = names.index("generates_synthetic_content")
    assert names[at + 1: at + 3] == [DEEP_FAKE, PUBLIC_INTEREST_TEXT]
    assert flags[DEEP_FAKE] == {"type": "boolean", "description": DEEP_FAKE_DESCRIPTION}
    assert flags[PUBLIC_INTEREST_TEXT] == {"type": "boolean", "description": PUBLIC_INTEREST_TEXT_DESCRIPTION}


def test_no_entailment_reads_or_writes_an_article_50_4_fact():
    for narrower, wider, _provision in FACT_ENTAILMENTS:
        assert {narrower, wider}.isdisjoint({DEEP_FAKE, PUBLIC_INTEREST_TEXT}), (narrower, wider)


def test_article_50_4_descriptions_quote_their_sentences(dump_texts):
    """Each duty's sentence and its exception's sentence of Article 50(4) are
    quoted whole (as the descriptions of listed uses quote their unit), and the
    deep fake's description quotes Article 3(60) whole."""
    flags = _flags_schema()
    paragraph = dump_texts[PARAGRAPH_4]
    sentences = [s.rstrip(".") for s in re.split(r"(?<=\.) ", re.sub(r"^4\. ", "", paragraph))]
    deep_fake = _normalised(flags[DEEP_FAKE]["description"])
    public_interest = _normalised(flags[PUBLIC_INTEREST_TEXT]["description"])
    assert sentences[0] in deep_fake and sentences[1] in deep_fake
    assert dump_texts[DEFINITION_60].rstrip(";") in deep_fake
    for sentence in (s.rstrip(".") for s in re.split(r"(?<=\.) ", dump_texts[SUBPARAGRAPH_2])):
        assert sentence in public_interest, sentence
        assert sentence in paragraph, sentence


def test_article_50_4_nodes_are_dated(dump):
    for node_id in (PARAGRAPH_4, SUBPARAGRAPH_2):
        assert dates_for([node_id], dump), node_id


def test_the_note_says_a_fact_that_is_true_and_no_longer_paragraph_4():
    assert ARTICLE_50_TRIGGERED_NOTE == NOTE
    assert "a known fact" not in ARTICLE_50_TRIGGERED_NOTE and "paragraphs 4 and 5" not in ARTICLE_50_TRIGGERED_NOTE
    assert "satirical" in ARTICLE_50_TRIGGERED_NOTE and "only its manner changes" in ARTICLE_50_TRIGGERED_NOTE


def test_v9_reads_the_facts_it_was_written_for():
    assert len(FLAGS_OF_V9) == 54 and DEEP_FAKE not in FLAGS_OF_V9 and PUBLIC_INTEREST_TEXT not in FLAGS_OF_V9
    assert [name for name in _flags_schema() if name not in (DEEP_FAKE, PUBLIC_INTEREST_TEXT)] == list(FLAGS_OF_V9)
    assert len(ARTICLE_50_RULES_OF_V9) == 4


# A fact that is true ----------------------------------------------------------

@pytest.mark.parametrize("fact,node", [(DEEP_FAKE, PARAGRAPH_4), (PUBLIC_INTEREST_TEXT, SUBPARAGRAPH_2)])
def test_finding_17_each_article_50_4_fact_triggers_limited_risk(dump, fact, node):
    env = classify_ai_system(case(all_false(**{fact: True})), dump)
    assert env["answer"]["risk_category"] == "limited_risk" and env["answer"]["transparency_duties"] == [node]
    assert ARTICLE_50_TRIGGERED_NOTE in env["legal_status_notes"]
    assert node in env["source_nodes"]
    assert (env["status"], env["confidence"]) == ("potentially_applicable", 1.0)


@pytest.mark.parametrize("fact,node", [(DEEP_FAKE, PARAGRAPH_4), (PUBLIC_INTEREST_TEXT, SUBPARAGRAPH_2)])
def test_a_true_article_50_4_fact_is_listed_beside_a_high_risk_answer(dump, fact, node):
    """Article 50(6): the duty stays beside the high-risk classification."""
    env = classify_ai_system(case(all_false(annex_iii_4a_recruitment=True, **{fact: True})), dump)
    assert env["answer"]["risk_category"] == "high_risk"
    assert env["answer"]["transparency_duties"] == [node]
    assert ARTICLE_50_TRIGGERED_NOTE in env["legal_status_notes"]


def test_a_deep_fake_does_not_make_synthetic_content_follow(dump):
    flags = {k: v for k, v in all_false(generates_deep_fake=True).items() if k != "generates_synthetic_content"}
    env = classify_ai_system(case(flags), dump)
    a = env["answer"]
    assert a["risk_category"] == "limited_risk"
    assert a["transparency_duties"] == [PARAGRAPH_4]
    assert a["fact_conflicts"] == []
    assert "eu-ai-act:article-50:paragraph-2" not in env["source_nodes"]
    assert _article_50_lines(env) == [_line("generates_synthetic_content", "eu-ai-act:article-50:paragraph-2",
                                            [PARAGRAPH_4])]
    assert not any("generates_synthetic_content" in line and "follows" in line for line in a["rationale"])


# An unknown fact, named on every exit where Article 50 can apply -----------------

def test_finding_15_limited_risk_names_absent_article_50_facts(dump):
    flags = _without_article_50(all_false(interacts_with_natural_persons=True),
                                keep=("interacts_with_natural_persons",))
    env = classify_ai_system(case(flags, deployer=dict(DEPLOYER)), dump)
    assert env["answer"]["risk_category"] == "limited_risk"
    absent = [f for f in ARTICLE_50_TRIGGER_FLAGS if f != "interacts_with_natural_persons"]
    assert len(absent) == 5
    assert _article_50_lines(env) == _expected_lines(env, absent)


def test_an_absent_article_50_4_fact_beside_a_true_one_on_limited_risk_leaves_the_status(dump):
    """Naming is information only: the status and the level stay."""
    known = classify_ai_system(case(all_false(generates_deep_fake=True)), dump)
    flags = {k: v for k, v in all_false(generates_deep_fake=True).items() if k != PUBLIC_INTEREST_TEXT}
    env = classify_ai_system(case(flags), dump)
    assert env["answer"]["risk_category"] == known["answer"]["risk_category"] == "limited_risk"
    assert (env["status"], env["confidence"]) == (known["status"], known["confidence"])
    assert _article_50_lines(env) == [_line(PUBLIC_INTEREST_TEXT, SUBPARAGRAPH_2, [PARAGRAPH_4])]


def test_undetermined_exits_name_absent_article_50_facts(dump):
    # C8: no rule fired and a listed use is unknown.
    c8 = AREA_CASES["C8"]["features"]
    env = classify_ai_system({**c8, "flags": _without_article_50(c8["flags"])}, dump)
    assert env["answer"]["risk_category"] == "undetermined"
    assert _article_50_lines(env) == _expected_lines(env, list(ARTICLE_50_TRIGGER_FLAGS))
    # The undetermined exit of an open Article 6(1) route.
    flags = {k: v for k, v in all_false(annex_i_covered_product=True).items()
             if k != "third_party_conformity_assessment_required"}
    env = classify_ai_system(case(_without_article_50(flags)), dump)
    assert env["answer"]["risk_category"] == "undetermined"
    assert "rule undetermined: the Article 6(1) plus Annex I embedded-product" in env["answer"]["rationale"][-1]
    assert _article_50_lines(env) == _expected_lines(env, list(ARTICLE_50_TRIGGER_FLAGS))


def test_area_alone_names_absent_article_50_facts(dump):
    c1 = AREA_CASES["C1"]["features"]
    env = classify_ai_system({**c1, "flags": _without_article_50(c1["flags"])}, dump)
    assert env["answer"]["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    assert _article_50_lines(env) == _expected_lines(env, list(ARTICLE_50_TRIGGER_FLAGS))


def test_the_article_6_1_and_annex_iii_exits_name_the_two_new_facts(dump):
    for flags in (all_false(annex_iii_4a_recruitment=True),
                  all_false(**P61, annex_i_section_b_legislation=False)):
        env = classify_ai_system(case({k: v for k, v in flags.items()
                                       if k not in (DEEP_FAKE, PUBLIC_INTEREST_TEXT)}), dump)
        assert env["answer"]["risk_category"] == "high_risk"
        assert _article_50_lines(env) == _expected_lines(env, [DEEP_FAKE, PUBLIC_INTEREST_TEXT])


def test_an_unknown_article_50_4_fact_leaves_a_minimal_answer_minimal(dump):
    """DEC-18 (Jose, 2026-10-01: "Keep minimal, name the fact")."""
    for fact in (DEEP_FAKE, PUBLIC_INTEREST_TEXT):
        flags = {k: v for k, v in all_false().items() if k != fact}
        env = classify_ai_system(case(flags), dump)
        assert env["answer"]["risk_category"] == "minimal_risk"
        assert (env["status"], env["confidence"]) == ("not_applicable", 1.0)
        assert env["missing_facts"] == _expected_lines(env, [fact])


def test_no_article_50_line_on_refused_prohibited_or_section_b_only(dump):
    # C11: a Section B product served under Article 2(2).
    c11 = AREA_CASES["C11"]["features"]
    env = classify_ai_system({**c11, "flags": _without_article_50(c11["flags"])}, dump)
    assert env["answer"]["annex_i_section"] == "B" and env["answer"]["transparency_duties"] == []
    assert ARTICLE_50_SECTION_B_NOTE in env["legal_status_notes"]
    assert _article_50_lines(env) == []
    # C23: unacceptable_risk (its true Article 50 fact kept).
    c23 = AREA_CASES["C23"]["features"]
    keep = tuple(k for k, v in c23["flags"].items() if v is True)
    env = classify_ai_system({**c23, "flags": _without_article_50(c23["flags"], keep=keep)}, dump)
    assert env["answer"]["risk_category"] == "unacceptable_risk"
    assert _article_50_lines(env) == []
    # A refused input.
    flags = _without_article_50(all_false())
    env = classify_ai_system(case(flags, domain="banking"), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert _article_50_lines(env) == []


@pytest.mark.parametrize("cid", [cid for cid in AREA_CASES if "t5" in AREA_CASES[cid]["expected"]])
def test_area_case_names_absent_article_50_facts(dump, cid):
    """The t5 column of the table of area cases: the case as given names no
    Article 50 fact (every one is known), and with every Article 50 trigger
    fact it does not set true removed, each is named or none is."""
    features = AREA_CASES[cid]["features"]
    expected = AREA_CASES[cid]["expected"]["t5"]
    assert _article_50_lines(classify_ai_system(features, dump)) == []
    keep = tuple(k for k, v in features["flags"].items() if v is True)
    env = classify_ai_system({**features, "flags": _without_article_50(features["flags"], keep=keep)}, dump)
    absent = [f for f in ARTICLE_50_TRIGGER_FLAGS if f not in keep]
    if expected["article_50_absent_named"]:
        assert _article_50_lines(env) == _expected_lines(env, absent)
    else:
        assert _article_50_lines(env) == []

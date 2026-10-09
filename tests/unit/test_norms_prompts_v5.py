"""B145 (spec G D-G80 (8), (9), (21); brief A7): extract_norms v5 and
judge_norms v5 are v4 with the changes D-G80 names and nothing else. The
expected texts are built here from v4, the scope's second version, the
Act's parties and the set-up table, and the prompt files must equal them
byte for byte; the version 4 files are never edited."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from tere4ai import act_parties
from tere4ai.extract_norms import set_up_rule
from tere4ai.extract_norms.requirement_type import DEFINITIONS_TEXT, SCOPE_TEXT, SCOPE_TEXT_V2

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
# extract_norms v5 prints the set-up rows of the core of B74, the units B74
# extracts (this plan's R73); the table in set_up_rule.py holds the rest.
CORE_NODES = [c.strip() for c in (ROOT / "data" / "graph_dumps" / "core_nodes.txt").read_text(encoding="utf-8").split(",") if c.strip()]
V4_SHA256 = {
    "extract_norms": "ef8667be79225f6b03d98869bb20e5cfd24ed8eb7cbeb296a0faa3247d35f1c2",
    "judge_norms": "5418525dfd0be52c93332f02d1bb136451b3cb1cebdf8adc812a990302d1644b",
}


def _read(kind: str, version: str) -> str:
    return (PROMPTS / kind / f"{version}.md").read_text(encoding="utf-8")


def _rename(text: str) -> str:
    """The settled words (spec G D-G80 (21)): the fields first, then the slot's word."""
    for old, new in (("actor_inference_source_node_id", "addressee_inference_source_node_id"),
                     ("actor_explicit", "addressee_explicit"), ("actor_inferred", "addressee_inferred"),
                     ("actor-inference", "addressee-inference"), ("Actor-inference", "Addressee-inference")):
        text = text.replace(old, new)
    text = re.sub(r"\bActor\b", "Addressee", text)
    text = re.sub(r"\bactors\b", "addressees", text)
    return re.sub(r"\bactor\b", "addressee", text)


V4_RULE_2 = """2. An article holds many norms. One sentence can hold several norms (for
   example one per listed duty or per addressed actor). Split them; do not
   merge distinct duties into one norm. If the unit contains no norm (for
   example a pure definition fragment or a list header), return
   {"norms": []}.
"""
V5_RULE_2 = """2. An article holds many norms. One sentence can hold several norms (for
   example one per listed duty or per addressee). Split them; do not
   merge distinct duties into one norm. When the text names several
   parties for one duty, write one norm per party, its addressee_explicit
   holding that party's words only. If the unit contains no norm (for
   example a pure definition fragment or a list header), return
   {"norms": []}.
"""
V4_OTHER_UNIT = """   - Any other unit. If the text literally names the actor, put the
     named phrase in actor_explicit (verbatim, lowercased is fine) and
     set actor_inferred null. If the text names no actor:
     - set actor_explicit to null, and
     - if a valid, recorded inference applies, set actor_inferred to the
       canonical role and actor_inference_source_node_id to the node
       that licenses the inference.
     - if no valid inference applies, set actor_inferred to
       "unspecified_needs_review" and actor_inference_source_node_id to
       the id of the source unit itself.
"""
V5_OTHER_UNIT = """   - Any other unit. If the text literally names the person or body that
     must act, put the named phrase in addressee_explicit (verbatim,
     lowercased is fine) and set addressee_inferred null. When that
     subject is a pronoun ("it", "they"), write the phrase it stands for,
     word for word from this same unit; if that phrase is not in this
     unit, the text names no addressee.
   - A thing is never the addressee, outside Articles 8 to 15 (inside
     them the Article 16(a) rule above decides). When the subject is a thing (a
     system, a document, a report, information, a mandate, a template,
     rules, guidance, an obligation) that a sentence of the same Article
     makes one named party set up, draw up, produce or carry, or a part
     of it, a copy of it, its implementation or the time set for it,
     the norm is that party's (the set-up rule): set addressee_explicit
     to null, addressee_inferred to the party's value and
     addressee_inference_source_node_id to the node that holds that
     sentence: the source unit's own id when the sentence is in it,
     else the node the recorded set-up inferences below name for this
     unit. Use only a sentence of this unit or a row of that table,
     never a sentence of another Article. When sentences of the Article
     make two parties each set the thing up, write one norm per party,
     each with its own node. When the sentence that sets the thing up
     names no party, the set-up rule does not apply. A point given
     alone that yields a norm under the set-up rule takes as its source
     the paragraph that holds the setting-up sentence, never the point
     (Article 17(1)'s points take eu-ai-act:article-17:paragraph-1).
   - If the text names no addressee and the set-up rule does not apply:
     - set addressee_explicit to null, and
     - if a valid, recorded inference applies, set addressee_inferred to
       the party's value and addressee_inference_source_node_id to the
       node that licenses the inference.
     - if no valid inference applies, set addressee_inferred to
       "unspecified_needs_review" and addressee_inference_source_node_id
       to the id of the source unit itself.
"""
V4_VOCABULARY = """- actor_inferred: one of "provider", "deployer", "importer", "distributor",
  "authorised_representative", "product_manufacturer", "notified_body",
  "notifying_authority", "market_surveillance_authority", "commission",
  "ai_office", "member_state", "affected_person", "operator_general",
  "unspecified_needs_review", or null.
"""
REQUIREMENT_TYPE_HEADING = "## Requirement type (ISO/IEC/IEEE 29148:2018 clause 5.2.8.3, DEC-19)\n"
SET_UP_BLOCK = """## Worked examples of the addressee slots outside Articles 8 to 15

- Article 17(1), its second sentence, "That system shall be documented in
  a systematic and orderly manner ...": an obligation with
  addressee_explicit null, addressee_inferred "provider" and
  addressee_inference_source_node_id "eu-ai-act:article-17:paragraph-1",
  the unit itself, whose first sentence reads "Providers of high-risk AI
  systems shall put a quality management system in place".
- Article 72(2), "The post-market monitoring system shall actively and
  systematically collect, document and analyse relevant data ...": you
  are given paragraph 2 alone; the table below names the sentence of
  paragraph 1 that sets the system up, so addressee_explicit null,
  addressee_inferred "provider" and addressee_inference_source_node_id
  "eu-ai-act:article-72:paragraph-1".
- Article 73(3), "... the report referred to in paragraph 1 of this
  Article shall be provided immediately, and not later than two days
  ...": addressee_inferred "provider" and
  addressee_inference_source_node_id "eu-ai-act:article-73:paragraph-1".
- Article 50(5), "The information referred to in paragraphs 1 to 4 shall
  be provided to the natural persons concerned ...": two norms, one with
  addressee_inferred "provider" and addressee_inference_source_node_id
  "eu-ai-act:article-50:paragraph-1", one with "deployer" and
  "eu-ai-act:article-50:paragraph-3".
- Article 22(3), its second sentence, "It shall provide a copy of the
  mandate to the market surveillance authorities upon request ...": "It"
  stands for "The authorised representative" of the first sentence, so
  addressee_explicit "the authorised representative" and
  addressee_inferred null.

Inside Articles 8 to 15 a party the text names stays written:
Article 11(1)'s "SMEs, including start-ups, and SMCs, may provide the
elements of the technical documentation specified in Annex IV in a
simplified manner" is a permission with addressee_explicit "SMEs,
including start-ups, and SMCs" and both inference slots null; the
pipeline places those words on the Act's parties, never you.

## The recorded set-up inferences (outside Articles 8 to 15)

Each line names a paragraph of the units you may be given, the thing as
the Act writes it there, the party whose duty it is, and the node that
holds the setting-up sentence with its words. A point of a listed
paragraph whose subject is the row's thing takes the same node. The set-up
rule does not cover Article 22(3)'s points (a) to (e): their party is the
authorised representative, whom the paragraph's first sentence names ("The
authorised representative shall perform the tasks specified in the
mandate"), with eu-ai-act:article-22:paragraph-3 as the node.

"""


def expected_extract_v5() -> str:
    text = _read("extract_norms", "v4")
    for old, new in (
        ("# extract_norms system prompt, version v4\n", "# extract_norms system prompt, version v5\n"),
        (V4_RULE_2, V5_RULE_2),
        (V4_OTHER_UNIT, V5_OTHER_UNIT),
        (V4_VOCABULARY, act_parties.render_vocabulary() + "\n"),
        (SCOPE_TEXT, SCOPE_TEXT_V2),
        (REQUIREMENT_TYPE_HEADING, SET_UP_BLOCK + set_up_rule.render_rows(set_up_rule.rows_in(CORE_NODES)) + "\n\n" + REQUIREMENT_TYPE_HEADING),
    ):
        assert text.count(old) == 1, old[:60]
        text = text.replace(old, new)
    return _rename(text)


V4_CHECK_3_TAIL = """another thing, in actor_explicit on a unit of Articles 8 to 15. Every other inference
   resting on Article 16 (point (c) for Article 17, for instance) is
   judged as above, against the source text you receive.
"""
V4_CHECK_3_SENTENCE = """Check an inference against the actor-inference source text
   you receive: that provision must assign the duty to the inferred actor.
"""
V5_CHECK_3_SENTENCE = """Check an inference against the actor-inference source text
   you receive: that provision must assign the duty to the inferred actor
   or, under the set-up rule below (outside Articles 8 to 15), make that
   party set up, draw up, produce or carry the thing the candidate's
   subject refers to.
"""
V5_CHECK_3_TAIL = """another thing, in addressee_explicit on a unit of Articles 8 to 15.
   Every other recorded inference is judged as above, against the source
   text you receive.
   Outside Articles 8 to 15, the set-up rule: addressee_inferred with an
   addressee_inference_source_node_id that holds a sentence of the same
   Article making that party set up, draw up, produce or carry the thing
   the candidate's subject refers to (by its name, by another name the
   Article gives it, by "that", "this", "such" or "those", or by
   "referred to in paragraph N"; or a part of it, a copy of it, its
   implementation or the time set for it) is a valid inference. When the
   unit has recorded set-up rows you receive them under "Set-up rows for
   this unit", each with its setting-up text. Grounds for rejection under
   this check, beside those above: that inference where the setting-up
   text names another party, or where the source is in another Article;
   on a unit with set-up rows, the row's thing, or a pronoun that stands
   for it, in addressee_explicit; a pronoun in addressee_explicit.
"""


def expected_judge_v5() -> str:
    text = _read("judge_norms", "v4")
    for old, new in (
        ("# judge_norms system prompt, version v4\n", "# judge_norms system prompt, version v5\n"),
        (V4_CHECK_3_SENTENCE, V5_CHECK_3_SENTENCE),
        (V4_CHECK_3_TAIL, V5_CHECK_3_TAIL),
        (SCOPE_TEXT, SCOPE_TEXT_V2),
    ):
        assert text.count(old) == 1, old[:60]
        text = text.replace(old, new)
    return _rename(text)


def test_the_v4_prompts_are_never_edited():
    for kind, sha in V4_SHA256.items():
        assert hashlib.sha256((PROMPTS / kind / "v4.md").read_bytes()).hexdigest() == sha


def test_extract_norms_v5_is_v4_with_d_g80s_changes_only():
    assert _read("extract_norms", "v5") == expected_extract_v5()


def test_judge_norms_v5_is_v4_with_check_3_extended_and_the_settled_words():
    assert _read("judge_norms", "v5") == expected_judge_v5()


def test_the_v5_prompts_carry_the_definitions_the_second_scope_and_no_actor_word():
    for kind in ("extract_norms", "judge_norms"):
        text = _read(kind, "v5")
        assert DEFINITIONS_TEXT in text and SCOPE_TEXT_V2 in text and SCOPE_TEXT not in text
        assert not re.search(r"\bactors?\b", text, re.IGNORECASE), kind
        assert "\u2014" not in text and "\u2013" not in text


def test_the_extractor_v5_names_the_37_values_and_the_cores_set_up_rows():
    text = _read("extract_norms", "v5")
    for value in act_parties.values():
        assert f'"{value}"' in text, value
    core_rows = set_up_rule.rows_in(CORE_NODES)
    assert len({row.unit for row in core_rows}) == 26
    assert set_up_rule.render_rows(core_rows) in text
    assert "eu-ai-act:article-47:paragraph-2" not in text
    for unit in ("eu-ai-act:article-17:paragraph-1", "eu-ai-act:article-72:paragraph-1",
                 "eu-ai-act:article-73:paragraph-1", "eu-ai-act:article-50:paragraph-3"):
        assert unit in text

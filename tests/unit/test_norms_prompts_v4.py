"""B144 (DEC-26, spec G D-G76 (5)): the v4 prompts are v3 with the rule for
the requirements of Articles 8 to 15 and nothing else changed. Offline, no
model."""

from __future__ import annotations

from tere4ai.extract_norms.pipeline import load_prompt
from tere4ai.extract_norms.requirement_type import DEFINITIONS_TEXT, SCOPE_TEXT

POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"

V3_RULE_3 = """3. Never invent an actor. If the text literally names the actor, put the
   named phrase in actor_explicit (verbatim, lowercased is fine) and set
   actor_inferred null. If the text names no actor:
   - set actor_explicit to null, and
   - if a valid, recorded inference applies, set actor_inferred to the
     canonical role and actor_inference_source_node_id to the node that
     licenses the inference. The canonical example: duties stated in the
     passive voice for high-risk AI systems in Chapter III Section 2 fall on
     the provider via Article 16(a); record actor_inferred "provider" with
     actor_inference_source_node_id "eu-ai-act:article-16".
   - if no valid inference applies, set actor_inferred to
     "unspecified_needs_review" and actor_inference_source_node_id to the id
     of the source unit itself.
"""

V4_RULE_3 = """3. Never invent an actor. Read the Article from the source unit node id;
   the rule depends on it.
   - Articles 8 to 15 (Chapter III, Section 2 of the Regulation, the
     requirements for high-risk AI systems):
     - If the text literally names the person or body that must act, as
       the subject or as the agent of the passive verb that carries the
       duty (a sentence of the form "X shall be done by the deployer"),
       put that phrase in actor_explicit (verbatim, lowercased is fine)
       and set actor_inferred null. A person named only inside what a
       requirement must ensure is not its actor: in Article 14(5) the
       measures "shall be such as to ensure that ... no action or
       decision is taken by the deployer", so the requirement is the
       measures', and the provider's.
     - Otherwise, a norm that states one of the Section's requirements
       for the high-risk AI system, or qualifies one (how it may be met,
       or when it does not apply), is the provider's, whatever its
       grammatical subject (the system, a part of it, its data, its
       documentation, its instructions for use, its risk management
       system, its oversight measures) and whether its verb is active or
       passive. Article 8(1) requires high-risk AI systems to comply with
       the requirements laid down in that Section, and Article 16(a)
       requires providers to "ensure that their high-risk AI systems are
       compliant with the requirements set out in Section 2". Set
       actor_explicit to null, actor_inferred to "provider" and
       actor_inference_source_node_id to
       "eu-ai-act:article-16:paragraph-1:point-a".
     - The system is never the actor, and neither is a person the text
       names only as the one a requirement serves or enables (the
       deployer the system is provided to, the natural persons it must
       enable).
     - A right, and a permission, an ability or a duty of a person the
       system must enable or inform, is not such a requirement: set its
       actor by the rule for any other unit below.
   - Any other unit. If the text literally names the actor, put the
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

WORKED_EXAMPLES = """## Worked examples of rule 3 (Articles 8 to 15)

- Article 12(1), "High-risk AI systems shall technically allow for the
  automatic recording of events (logs) over the lifetime of the system":
  one obligation, modal "shall", actor_explicit null, actor_inferred
  "provider", actor_inference_source_node_id
  "eu-ai-act:article-16:paragraph-1:point-a", action "technically allow
  for", object "the automatic recording of events (logs)", conditions
  ["over the lifetime of the system"]. "High-risk AI systems" is the
  subject the requirement constrains, not its actor; its words stay in
  the source text the norm cites.
- Article 14(4), the paragraph, "For the purpose of implementing
  paragraphs 1, 2 and 3, the high-risk AI system shall be provided to
  the deployer in such a way that natural persons to whom human
  oversight is assigned are enabled, as appropriate and proportionate:
  (a) ... (e)": each of its norms is an obligation with actor_explicit
  null, actor_inferred "provider" and actor_inference_source_node_id
  "eu-ai-act:article-16:paragraph-1:point-a". The deployer and the
  natural persons are those the requirement serves, not its actor.
- Article 14(4), point (d), given alone, "to decide, in any particular
  situation, not to use the high-risk AI system or to otherwise
  disregard, override or reverse the output of the high-risk AI
  system;": its text holds no modal and names no one who must act,
  because "shall be provided ... are enabled" is in its paragraph, which
  you are not given. Extract only what the point's own text supports
  (rule 1), which may be no norm. If you read in it a permission of
  the person who oversees the system to override the output, that
  permission is not a requirement for the system: never give it to the
  provider through Article 16(a); set its actor by the rule for any
  other unit.
- Article 15(4), "The robustness of high-risk AI systems may be achieved
  through technical redundancy solutions, which may include backup or
  fail-safe plans": a permission that qualifies a requirement for the
  system (how it may be met), with actor_explicit null, actor_inferred
  "provider" and actor_inference_source_node_id
  "eu-ai-act:article-16:paragraph-1:point-a".

"""

TYPE_ANCHOR = "## Requirement type (ISO/IEC/IEEE 29148:2018 clause 5.2.8.3, DEC-19)\n"

# R26: the output example's actor lines (v3 lines 21 to 23), corrected in v4:
# its duty is Article 9(1)'s passive "A risk management system shall be
# established ...", whose actor under v3's rule and v4's is the provider
# inferred, never a written "provider" the text does not hold.
V3_EXAMPLE_ACTOR = '''      "actor_explicit": "provider",
      "actor_inferred": null,
      "actor_inference_source_node_id": null,
'''
V4_EXAMPLE_ACTOR = '''      "actor_explicit": null,
      "actor_inferred": "provider",
      "actor_inference_source_node_id": "eu-ai-act:article-16:paragraph-1:point-a",
'''
# Review M4: the example names its unit, so a model does not copy the point
# (a) source onto a passive duty outside Articles 8 to 15.
EXAMPLE_ANCHOR = "Respond with a single JSON object and nothing else:\n\n"
EXAMPLE_UNIT = """The example below is one norm of Article 9(1), "A risk management system shall be
established, implemented, documented and maintained in relation to
high-risk AI systems": a passive duty of Articles 8 to 15, so its actor is
the provider through Article 16(a) (rule 3). A passive duty outside
Articles 8 to 15 never takes that source.

"""

# v3's rule 3 sentences that v4 keeps for any other unit (R11: only the
# canonical example, which was about Chapter III Section 2, is dropped).
V3_SENTENCES_KEPT = (
    "Never invent an actor.",
    "If the text literally names the actor, put the named phrase in actor_explicit (verbatim, lowercased is fine)"
    " and set actor_inferred null.",
    "If the text names no actor:",
    "- set actor_explicit to null, and",
    "- if a valid, recorded inference applies, set actor_inferred to the canonical role and"
    " actor_inference_source_node_id to the node that licenses the inference.",
    '- if no valid inference applies, set actor_inferred to "unspecified_needs_review" and'
    " actor_inference_source_node_id to the id of the source unit itself.",
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def rebuild_v4_extractor() -> str:
    """v3 with the five changes D-G76 (5) allows (R26, review M4), and nothing else."""
    v3 = load_prompt("extract_norms", "v3")
    for part in (V3_RULE_3, TYPE_ANCHOR, V3_EXAMPLE_ACTOR, EXAMPLE_ANCHOR):
        assert v3.count(part) == 1, part
    return (
        v3.replace("# extract_norms system prompt, version v3", "# extract_norms system prompt, version v4", 1)
        .replace(EXAMPLE_ANCHOR, EXAMPLE_UNIT + EXAMPLE_ANCHOR, 1)
        .replace(V3_EXAMPLE_ACTOR, V4_EXAMPLE_ACTOR, 1)
        .replace(V3_RULE_3, V4_RULE_3, 1)
        .replace(TYPE_ANCHOR, WORKED_EXAMPLES + TYPE_ANCHOR, 1)
    )


def test_the_v4_extractor_is_v3_with_rule_3_rewritten_and_the_worked_examples():
    assert load_prompt("extract_norms", "v4") == rebuild_v4_extractor()


def test_the_v4_rule_names_the_range_the_point_a_node_and_article_12_1():
    extract = load_prompt("extract_norms", "v4")
    rule = _flat(V4_RULE_3)
    assert "Articles 8 to 15 (Chapter III, Section 2 of the Regulation" in rule
    assert f'"{POINT_A}"' in rule
    assert "Article 12(1)" in _flat(WORKED_EXAMPLES) and WORKED_EXAMPLES in extract
    for sentence in V3_SENTENCES_KEPT:
        assert sentence in _flat(V4_RULE_3), sentence
    # the canonical example of v3 is gone, and with it the whole-Article source
    assert "The canonical example" not in extract
    assert '"eu-ai-act:article-16"' not in extract


def test_the_v4_extractor_carries_the_requirement_type_texts_and_the_output_example_but_its_actor_lines():
    v3, v4 = load_prompt("extract_norms", "v3"), load_prompt("extract_norms", "v4")
    assert DEFINITIONS_TEXT in v4 and SCOPE_TEXT in v4
    example = v3[v3.index("```json"):v3.index("## Extraction rules")]
    assert example.replace(V3_EXAMPLE_ACTOR, V4_EXAMPLE_ACTOR, 1) in v4
    # the example's actor now follows the rule it illustrates (R26), and the
    # paragraph naming its unit opens the output format section, before the
    # instruction that introduces the JSON (review M4, re-review N3)
    assert V3_EXAMPLE_ACTOR not in v4 and v4.count(V4_EXAMPLE_ACTOR) == 1
    assert "## Output format\n\n" + EXAMPLE_UNIT + EXAMPLE_ANCHOR + "```json" in v4
    assert "Article 9(1)" in _flat(EXAMPLE_UNIT) and "outside Articles 8 to 15 never takes that source" in _flat(EXAMPLE_UNIT)


V3_CHECK_3 = """3. Actor: the actor is either explicitly named in the text (actor_explicit
   matches the text) or a valid recorded inference (actor_inferred with an
   actor_inference_source_node_id, for example provider duties inferred via
   Article 16). Check an inference against the actor-inference source text
   you receive: that provision must assign the duty to the inferred actor.
   An invented actor, or an inference its source text does not support, is
   grounds for rejection. An actor of "unspecified_needs_review" is
   acceptable only when the text truly names no actor and no valid
   inference applies.
"""

V4_CHECK_3 = """3. Actor: the actor is either explicitly named in the text (actor_explicit
   matches the text) or a valid recorded inference (actor_inferred with an
   actor_inference_source_node_id, for example provider duties inferred via
   Article 16). Check an inference against the actor-inference source text
   you receive: that provision must assign the duty to the inferred actor.
   When the source is a point, you also receive the text of the paragraph
   that holds it, which names who the point's duty falls on.
   An invented actor, or an inference its source text does not support, is
   grounds for rejection. An actor of "unspecified_needs_review" is
   acceptable only when the text truly names no actor and no valid
   inference applies.
   Articles 8 to 15 (Chapter III, Section 2; read the Article from the
   source unit node id): actor_inferred "provider" with
   actor_inference_source_node_id
   "eu-ai-act:article-16:paragraph-1:point-a" is a valid inference when
   the norm states one of the Section's requirements for the high-risk AI
   system, or qualifies one (how it may be met, or when it does not
   apply), and the text names no person or body that must act, whatever
   the grammatical subject (the system, a part of it, its data, its
   documentation, its instructions for use, its risk management system,
   its oversight measures) and whether the verb is active or passive.
   Article 16(a) requires providers to "ensure that their high-risk AI
   systems are compliant with the requirements set out in Section 2".
   Grounds for rejection under this check, beside those above: that
   inference on a unit outside Articles 8 to 15; that inference where the
   text names the person or body that must act, as the subject or as the
   agent of the passive verb that carries the duty (a person named only
   inside what a requirement must ensure, as the deployer in Article
   14(5), is not the one who must act); that inference for a permission
   or an ability of a person the system must enable; the system, or
   another thing, in actor_explicit on a unit of Articles 8 to 15. Every other inference
   resting on Article 16 (point (c) for Article 17, for instance) is
   judged as above, against the source text you receive.
"""

FOUR_GROUNDS = (
    "that inference on a unit outside Articles 8 to 15",
    "that inference where the text names the person or body that must act",
    "that inference for a permission or an ability of a person the system must enable",
    "the system, or another thing, in actor_explicit on a unit of Articles 8 to 15",
)


def rebuild_v4_judge() -> str:
    """v3 with its version line and check 3 changed, and nothing else."""
    v3 = load_prompt("judge_norms", "v3")
    assert v3.count(V3_CHECK_3) == 1
    return (
        v3.replace("# judge_norms system prompt, version v3", "# judge_norms system prompt, version v4", 1)
        .replace(V3_CHECK_3, V4_CHECK_3, 1)
    )


def test_the_v4_judge_is_v3_with_check_3_rewritten():
    assert load_prompt("judge_norms", "v4") == rebuild_v4_judge()


def test_the_v4_check_3_names_the_range_the_point_a_node_and_the_four_grounds():
    check = _flat(V4_CHECK_3)
    assert "Articles 8 to 15 (Chapter III, Section 2;" in check
    assert f'"{POINT_A}"' in check
    for ground in FOUR_GROUNDS:
        assert ground in check, ground
    # every v3 sentence of check 3 stays
    for sentence in _flat(V3_CHECK_3).split(". "):
        assert sentence.rstrip(".") in check


def test_the_v4_judge_carries_the_requirement_type_texts_byte_for_byte():
    judge = load_prompt("judge_norms", "v4")
    assert DEFINITIONS_TEXT in judge and SCOPE_TEXT in judge

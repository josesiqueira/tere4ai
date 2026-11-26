"""Prompt v10 of elicit_features, the prompt of record (B185 Task 8, DEC-33),
and the tool description of classify_ai_system that names the answer's new
fields.

v10 is v9 with four changes, each tested here: the `domain` bullet offers the
eight Annex III areas with their point numbers, says that the model proposes
an area only from the description's own words that place the system in it,
that it never proposes none_of_these_areas (the elicitor's code drops it from
every proposal, ruling P3) and that it omits the field when the description
does not settle the area (spec G D-G92 (10), (xi)); the flag list holds the 56
facts of the live schema in the schema file's order; a section
"### Article 50(4)" prints paragraph 4, its second subparagraph and Article
3(60) with the two facts of the paragraph and their answer rules (D-G92 (7),
(x)); the worked example leaves out `domain` (ruling P24). v9 stays as the
prompt of B184's record (ruling P27). Offline only: the repository's dump,
FakeClient replies, no model and no network.

@implements: DEC-33
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from tests.unit.test_elicit_prompt_v9 import (
    LISTED_USE_UNIT,
    SCHEMA_QUOTE_EXCEPTIONS,
    _schema_quote_gaps,
)

from tere4ai.elicit_features import elicit
from tere4ai.elicit_features.elicitor import (
    DEFAULT_PROMPT_VERSION,
    DOMAIN_DROP_NONE_REASON,
    SNAPSHOTS_DIR,
    render_prompt,
)
from tere4ai.elicit_features.provisions import PLACEHOLDER_RE, fact_provisions, render_template
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.mcp_server.classify import (
    ANNEX_III_RULES,
    ARTICLE_5_EXCULPATING_FACT,
    ARTICLE_5_POINT_BY_FLAG,
    ARTICLE_5_POINT_H,
    ARTICLE_5_POINT_H_EXCULPATING,
    ARTICLE_5_SCOPING_PARAGRAPHS,
    ARTICLE_6_3_CONDITIONS,
    ARTICLE_6_3_PROFILING_OVERRIDE,
    ARTICLE_50_RULES,
    FACT_ENTAILMENTS,
    classify_ai_system,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts" / "elicit_features"
V10_PATH = PROMPTS / "v10.md"
V10 = V10_PATH.read_text(encoding="utf-8") if V10_PATH.is_file() else ""
V9 = (PROMPTS / "v9.md").read_text(encoding="utf-8")
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "system_features.schema.json").read_text(encoding="utf-8"))
# M10: the schema file's order, never schema_flag_names(), which is sorted.
SCHEMA_FLAGS = list(SCHEMA["properties"]["flags"]["properties"])
DOMAIN = SCHEMA["properties"]["domain"]
AREA_VALUES: dict[str, int] = DOMAIN["x-annex-iii-area-values"]
NONE_OF_THESE_AREAS = "none_of_these_areas"
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SERVER_PATH = ROOT / "src" / "tere4ai" / "mcp_server" / "server.py"
DESCRIPTION = (
    "An internal tool that scores each office worker's productivity from the "
    "tickets they close and suggests who should get a bonus."
)
LAWFUL_USE_SENTENCE = (
    "Answer for the use the system is intended for; whether that use is permitted "
    "under Union or national law is not part of this fact."
)
POINT_5_USES = tuple(fact for fact, _unit in ANNEX_III_RULES[4]["uses"])
ARTICLE_50_4 = "eu-ai-act:article-50:paragraph-4"
ARTICLE_50_4_SECOND = "eu-ai-act:article-50:paragraph-4:subparagraph-2"
DEEP_FAKE_DEFINITION = "eu-ai-act:definition:deep-fake"
# The sentences of Task 8's brief for the tool description, word for word.
DESCRIPTION_SENTENCES = (
    "annex_iii_category is also null when the point rests on the area: annex_iii_area_unconfirmed then names it. "
    "domain is one of biometrics, critical_infrastructure, education, employment, essential_services, "
    "law_enforcement, migration, justice, none_of_these_areas, or unknown; any other value is refused with a "
    "message, and no value of domain reads a listed use as false. area_conflicts names each listed use that is "
    "true while domain is none_of_these_areas; the answer then requires human review. "
    "article_6_3_exception_candidate describes the Annex III part of the answer: true, false, or null when an "
    "Article 6(3) condition is unknown and none is true. A refused input carries no fria block (null)."
)
ANNEX_III_CATEGORY_SENTENCE = (
    "annex_iii_category is the first matching point when Annex III decided the level, and is null when the "
    "Article 6(1) route or a prohibition decided it, even if annex_iii_listed_uses names a listed use."
)


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _flat(text: str) -> str:
    return " ".join(text.split())


def _sections(text: str) -> dict[str, str]:
    """Each '### ' heading of the template and the text under it."""
    found: dict[str, str] = {}
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        found[heading.strip()] = body.split("\n## ")[0]
    return found


def _point_section(point: int) -> str:
    matches = [body for heading, body in _sections(V10).items()
               if re.match(rf"Annex III point {point}\b", heading)]
    assert len(matches) == 1, point
    return matches[0]


def _top_list() -> list[str]:
    start = V10.index('- "flags": an object of booleans, ONLY from this list:')
    block = V10[start:V10.index("Rules, all binding:")]
    return re.findall(r"[a-z0-9_]+", block.split("this list:", 1)[1])


def _domain_bullet() -> str:
    return _flat(V10[V10.index('- "domain":'):V10.index('- "purposes":')])


def _example() -> tuple[str, dict]:
    output = V10[V10.index("## Output"):]
    description = re.search(r"```text\n(.*?)\n```", output, re.S)
    reply = re.search(r"```json\n(.*?)\n```", output, re.S)
    assert description and reply
    return description.group(1), json.loads(reply.group(1))


def _docstring(name: str) -> str:
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    return _flat(ast.get_docstring(node) or "")


# The prompt of record --------------------------------------------------------

def test_v10_is_the_prompt_of_record():
    assert V10, "prompts/elicit_features/v10.md is missing"
    assert DEFAULT_PROMPT_VERSION == "v10"


def test_v10_renders_over_the_build_with_every_provision_resolved(dump):
    system, record = render_prompt(dump, SNAPSHOTS_DIR, "v10")
    assert record["version"] == "v10" and "{{provision:" not in system
    # The default renders v10.
    assert render_prompt(dump, SNAPSHOTS_DIR)[1]["version"] == "v10"


def test_v10_renders_no_deleted_provision_and_only_the_tables_nodes(dump):
    rendered, provisions = render_template(V10, dump, SNAPSHOTS_DIR)
    assert "Deleted by" not in rendered
    table_ids = {n for nodes in fact_provisions(V10).values() for n in nodes}
    assert {p["node_id"] for p in provisions} == table_ids == set(PLACEHOLDER_RE.findall(V10))


def test_v10_has_no_em_or_en_dash():
    assert chr(0x2014) not in V10
    assert chr(0x2013) not in V10


def test_v10_keeps_v9s_rules():
    rules = V9[V9.index("Rules, all binding:"): V9.index("## Facts and their provisions")]
    assert rules in V10


# The facts of the live schema --------------------------------------------------

def test_v10_flag_list_is_the_schema_flags_in_the_schema_files_order():
    assert len(SCHEMA_FLAGS) == 56
    assert _top_list() == SCHEMA_FLAGS


def test_v10_names_every_schema_flag_and_only_those():
    assert set(re.findall(r"flags\.([a-z0-9_]+)", V10)) == set(SCHEMA_FLAGS)


def test_v10_every_schema_flag_has_a_provision():
    table = fact_provisions(V10)
    assert [name for name in SCHEMA_FLAGS if not table.get(f"flags.{name}")] == []


def test_v10_article_5_and_article_50_facts_quote_the_classifiers_nodes():
    table = fact_provisions(V10)
    for flag, (node_id, _fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        assert node_id in table.get(f"flags.{flag}", []), flag
    for flag, (fact, _value, _element) in ARTICLE_5_EXCULPATING_FACT.items():
        assert ARTICLE_5_POINT_BY_FLAG[flag][0] in table.get(f"flags.{fact}", []), fact
    assert ARTICLE_5_POINT_H in table[f"flags.{ARTICLE_5_POINT_H_EXCULPATING[0]}"]
    for flag, paragraphs in ARTICLE_5_SCOPING_PARAGRAPHS.items():
        for paragraph in paragraphs:
            assert paragraph in table[f"flags.{flag}"], (flag, paragraph)
    assert ARTICLE_6_3_PROFILING_OVERRIDE in table["flags.profiling_of_natural_persons"]
    # The live table, the two Article 50(4) facts included.
    assert {flag for flag, _node, _note in ARTICLE_50_RULES} >= {"generates_deep_fake",
                                                                  "generates_public_interest_text"}
    for flag, node_id, _note in ARTICLE_50_RULES:
        assert node_id in table.get(f"flags.{flag}", []), flag


def test_v10_attaches_to_each_fact_every_unit_its_schema_description_quotes(dump):
    """Every unit a fact's schema description quotes is a provision v10
    attaches to the fact, over all 56 facts of the live schema, with v9's
    exceptions (the opening words of points 1, 6 and 7), each still used."""
    gaps, used = _schema_quote_gaps(V10, dump, facts=SCHEMA_FLAGS)
    assert gaps == []
    assert used == set(SCHEMA_QUOTE_EXCEPTIONS), "an exception no longer applies"


@pytest.mark.parametrize("fact,placeholder", [
    *((fact, "{{provision:" + unit + "}}") for fact, unit in sorted(LISTED_USE_UNIT.items())),
    ("generates_deep_fake", "{{provision:" + ARTICLE_50_4 + "}}"),
    ("generates_public_interest_text", "{{provision:" + ARTICLE_50_4_SECOND + "}}"),
])
def test_the_schema_check_fails_when_a_fact_loses_its_unit(fact, placeholder, dump):
    """Mutation: v10 without the placeholder of the fact's own unit, in memory,
    gives a gap for that fact."""
    assert placeholder in V10, fact
    mutated = "\n".join(line for line in V10.splitlines() if line.strip() != placeholder)
    gaps, _used = _schema_quote_gaps(mutated, dump, facts=SCHEMA_FLAGS)
    assert fact in {gap[0] for gap in gaps}, fact


def test_every_quotation_of_the_act_in_v10_is_exact(dump):
    """Every passage in double quotes in the section of facts and provisions is
    the text of a node of layer1.json (whitespace collapsed), and the section
    quotes the Act at least once (the Article 50(4) answer rules)."""
    from tests.unit.test_features_schema_descriptions import _normalised

    section = V10[V10.index("## Facts and their provisions"):V10.index("## Output")]
    # "- Facts:" is the prompt's own syntax, named in the section's first
    # paragraph, not a quotation of the Act.
    passages = [p for p in re.findall(r'"([^"]+)"', section) if p != "- Facts:"]
    assert passages, "the section quotes no passage of the Act"
    texts = [_normalised(n.get("text") or "") for n in dump["nodes"]
             if n.get("type") != "UnitVersion" and n.get("text")]
    missing = [p for p in passages if not any(_normalised(p) in t for t in texts)]
    assert missing == []


# The Annex III headings, the listed uses and the other facts, as in v9 -------------

def test_v10_each_listed_use_stands_under_its_own_point_heading_with_its_unit():
    for number, rule in enumerate(ANNEX_III_RULES, start=1):
        section = _point_section(number)
        table = fact_provisions("## Facts and their provisions\n" + section)
        for fact, unit in rule["uses"]:
            assert unit in table.get(f"flags.{fact}", []), (number, fact)


def test_v10_area_headings_are_the_schemas_area_names():
    areas = SCHEMA["properties"]["flags"]["x-annex-iii-areas"]
    headings = [h for h in _sections(V10) if h.startswith("Annex III point ")]
    assert headings == [f"Annex III point {key}: {areas[key]}" for key in sorted(areas, key=int)]


def test_v10_points_1_6_and_7_say_lawful_use_is_not_part_of_the_fact():
    for point in (1, 6, 7):
        section = _flat(_point_section(point))
        assert LAWFUL_USE_SENTENCE in section, point
        assert "are not a fact" in section, point
    for point in (2, 3, 4, 5, 8):
        assert LAWFUL_USE_SENTENCE not in _flat(_point_section(point)), point


def test_v10_purpose_fact_quotes_article_3_46_and_point_h():
    table = fact_provisions(V10)
    assert "eu-ai-act:definition:law-enforcement" in table["flags.law_enforcement_purpose"]
    assert ARTICLE_5_POINT_H in table["flags.law_enforcement_purpose"]


def test_v10_recital_18_is_context_and_there_is_no_drowsiness_example():
    assert "drowsiness" not in V10.lower()
    table = fact_provisions(V10)
    for fact in ("emotion_recognition", "emotion_recognition_workplace_or_education",
                 "emotion_recognition_medical_or_safety"):
        assert "eu-ai-act:recital-18" in table[f"flags.{fact}"], fact
    line = next(i for i, text in enumerate(V10.splitlines()) if "{{provision:eu-ai-act:recital-18}}" in text)
    assert "context, not binding: what the notion of emotion leaves out" in V10.splitlines()[line - 1]


def test_v10_article_6_3_facts_quote_their_points():
    table = fact_provisions(V10)
    for flag, nodes, _label in ARTICLE_6_3_CONDITIONS:
        assert set(nodes) <= set(table[f"flags.{flag}"])


def test_v10_biometric_identification_is_defined_by_its_own_unit():
    nodes = fact_provisions(V10)["flags.biometric_identification"]
    assert "eu-ai-act:definition:biometric-identification" not in nodes
    assert "eu-ai-act:annex-iii:point-1:a" in nodes


def test_v10_consistency_paragraph_names_every_entailment():
    paragraph = _flat(V10[V10.index("Consistency:"):].split("\n\n")[0])
    sentences = [s for s in re.split(r"(?<=\.) ", paragraph) if s]
    for narrower, wider, _provision in FACT_ENTAILMENTS:
        assert any(s.startswith(f"When {narrower} is true") and wider in s for s in sentences), (narrower, wider)


# Article 50(4): the two facts and their answer rules (D-G92 (7), (x)) -------------

def _article_50_4_section() -> str:
    sections = _sections(V10)
    assert "Article 50(4)" in sections
    return sections["Article 50(4)"]


def test_the_article_50_4_section_prints_its_three_provisions_with_the_two_facts():
    section = _article_50_4_section()
    for node in (ARTICLE_50_4, ARTICLE_50_4_SECOND, DEEP_FAKE_DEFINITION):
        assert "{{provision:" + node + "}}" in section, node
    table = fact_provisions("## Facts and their provisions\n" + section)
    assert {ARTICLE_50_4, DEEP_FAKE_DEFINITION} <= set(table["flags.generates_deep_fake"])
    assert ARTICLE_50_4_SECOND in table["flags.generates_public_interest_text"]
    assert set(table) == {"flags.generates_deep_fake", "flags.generates_public_interest_text"}


def test_the_article_50_4_answer_rules_follow_the_schema():
    section = _flat(_article_50_4_section())
    deep_fake = section[section.index("generates_deep_fake: "):section.index("{{provision:" + DEEP_FAKE_DEFINITION)]
    text = section[section.index("generates_public_interest_text: "):]
    # A use authorised by law for criminal offences answers no, for both facts.
    for rule in (deep_fake, text):
        assert "authorised by law to detect, prevent, investigate or prosecute criminal offences" in rule
        assert "is false" in rule
    # For the text, also editorial control under a person's editorial responsibility.
    assert "human review or editorial control" in text and "editorial responsibility" in text
    # Artistic or satirical content answers yes: the duty stays, its manner changes.
    assert "evidently artistic, creative, satirical, fictional or analogous work or programme" in deep_fake
    assert "is true: the duty stays and only its manner changes" in deep_fake
    # A deep fake does not make generates_synthetic_content follow.
    assert ("generates_deep_fake true does not make generates_synthetic_content true, nor the other way round"
            in section)


# The domain bullet (D-G92 (10), (xi); item (c) of the coordinator) ------------------

def test_the_domain_bullet_offers_the_eight_areas_with_their_points():
    bullet = _domain_bullet()
    assert set(AREA_VALUES) | {NONE_OF_THESE_AREAS} == {v for v in DOMAIN["enum"] if v is not None}
    for value, point in AREA_VALUES.items():
        assert re.search(rf"\b{value} \((Annex III )?point {point}\)", bullet), value
    assert NONE_OF_THESE_AREAS in bullet
    assert "only from the description's own words" in bullet
    assert "never propose none_of_these_areas" in bullet
    assert "omit the field when the description does not settle the area" in bullet


def test_v10_never_offers_none_of_these_areas_as_a_value_to_propose():
    bullet = _domain_bullet()
    offered = bullet[bullet.index("one of"):bullet.index(".", bullet.index("justice"))]
    assert NONE_OF_THESE_AREAS not in offered
    assert all(value in offered for value in AREA_VALUES)
    # Every mention of the value in the whole prompt is the sentence that
    # forbids proposing it.
    assert V10.count(NONE_OF_THESE_AREAS) == _flat(V10).count("never propose none_of_these_areas") == 1


def test_the_old_domain_words_are_gone_from_the_bullet():
    bullet = _domain_bullet()
    for word in ("healthcare", "banking", "insurance", "consumer", "short lowercase noun"):
        assert word not in bullet, word


# The worked example (ruling P24) ---------------------------------------------------

def test_v10_example_validates_and_carries_no_domain():
    description, example = _example()
    assert set(example) == {"features", "quotes"}
    features = example["features"]
    assert "domain" not in features and "domain" not in example["quotes"]
    assert list(Draft202012Validator(SCHEMA).iter_errors({"description": description, **features})) == []
    for path, quote in example["quotes"].items():
        assert len(quote.split()) >= 3, path
        assert quote in description, path
        if path.startswith("flags."):
            assert path[len("flags."):] in features["flags"], path
        else:
            assert path in features, path
    for name in features["flags"]:
        assert f"flags.{name}" in example["quotes"], name


def test_v10_example_says_why_it_has_no_domain():
    before = _flat(V10[V10.index("## Output"):V10.index("```text")])
    assert "places the chatbot in no area" in before


def test_v10_example_answers_every_point_5_listed_use_false_and_classifies_without_contradiction(dump):
    description, example = _example()
    flags = example["features"]["flags"]
    assert {fact: flags.get(fact) for fact in POINT_5_USES} == dict.fromkeys(POINT_5_USES, False)
    env = classify_ai_system({"description": description, **example["features"]}, dump)
    answer = env["answer"]
    assert answer["fact_conflicts"] == [] and answer["area_conflicts"] == []
    assert answer["annex_iii_category"] is None and answer["annex_iii_area_unconfirmed"] is None
    assert answer["risk_category"] == "limited_risk"


# The elicitor under the default version (mock model answers only) ------------------

def test_v10_elicitation_with_a_fake_client_keeps_a_listed_use_fact(dump):
    reply = {"features": {"flags": {"annex_iii_4b_work_relationships": True}},
             "quotes": {"flags.annex_iii_4b_work_relationships": "scores each office worker's productivity"}}
    result = elicit(DESCRIPTION, FakeClient({DESCRIPTION[:30]: json.dumps(reply)}), dump=dump,
                    snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.prompt["version"] == "v10"


def test_a_proposed_none_of_these_areas_is_dropped_under_v10(dump):
    reply = {"features": {"domain": NONE_OF_THESE_AREAS, "flags": {"annex_iii_4b_work_relationships": True}},
             "quotes": {"domain": "An internal tool that scores",
                        "flags.annex_iii_4b_work_relationships": "scores each office worker's productivity"}}
    result = elicit(DESCRIPTION, FakeClient({DESCRIPTION[:30]: json.dumps(reply)}), dump=dump,
                    snapshots_dir=SNAPSHOTS_DIR)
    assert result.prompt["version"] == "v10"
    assert "domain" not in result.features and "domain" not in result.quotes
    assert {"path": "domain", "reason": DOMAIN_DROP_NONE_REASON} in result.dropped
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}


# The tool description (Task 8 and item (a) of the coordinator) ---------------------

def test_the_tool_description_names_the_new_fields_word_for_word():
    served = _docstring("classify_ai_system")
    assert ANNEX_III_CATEGORY_SENTENCE + " " + DESCRIPTION_SENTENCES in served


def test_the_tool_description_says_an_article_50_duty_can_be_a_subparagraph():
    served = _docstring("classify_ai_system")
    assert "transparency_duties lists the Article 50 paragraphs or subparagraphs triggered" in served
    assert "a listed paragraph or subparagraph is triggered, not proven" in served
    assert "transparency_duties lists the Article 50 paragraphs triggered" not in served

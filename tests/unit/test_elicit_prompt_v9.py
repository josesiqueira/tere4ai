"""Prompt v9 of elicit_features, B184's prompt of record (B184 Task 7, DEC-32).

v9 asks the 54 facts of the schema: the 25 Annex III listed uses under eight
headings, one per point, each with its own legal unit; law_enforcement_purpose
under Article 5(1)(h); narrow_procedural_task and preparatory_task under
Article 6(3) points (a) and (d). v8 stays as the prompt of tag v2.0.0-beta.1
(ruling P15). Offline only: the repository's dump, FakeClient replies, no
model and no network.

B185 (ruling P27): v9 is the prompt of B184's record; from B185 Task 5 on the
schema has two more facts (the duties of Article 50(4)), so the tests that
compare v9 with the facts read FLAGS_OF_V9 and ARTICLE_50_RULES_OF_V9 of
tests/unit/flags_of_record.py, frozen at 09472d6, never the live schema or
ARTICLE_50_RULES. Task 8 made v10 the prompt of record.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from tests.unit.flags_of_record import ARTICLE_50_RULES_OF_V9, FLAGS_OF_V9

from tere4ai.elicit_features import elicit
from tere4ai.elicit_features.elicitor import (
    DEFAULT_PROMPT_VERSION,
    SNAPSHOTS_DIR,
    render_prompt,
    schema_flag_names,
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
    FACT_ENTAILMENTS,
    classify_ai_system,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts" / "elicit_features"
V9 = (PROMPTS / "v9.md").read_text(encoding="utf-8") if (PROMPTS / "v9.md").is_file() else ""
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "system_features.schema.json").read_text(encoding="utf-8"))
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
DESCRIPTION = (
    "An internal tool that scores each office worker's productivity from the "
    "tickets they close and suggests who should get a bonus."
)
# R15: the schema's sentence for the listed uses of points 1, 6 and 7.
LAWFUL_USE_SENTENCE = (
    "Answer for the use the system is intended for; whether that use is permitted "
    "under Union or national law is not part of this fact."
)
# Fix round 1, M7: the note for a key the schema does not define.
OUTSIDE_NOTE = "{path} was proposed but is not a fact of the schema; it was not kept"
POINT_5_USES = tuple(fact for fact, _unit in ANNEX_III_RULES[4]["uses"])


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _sections(text: str) -> dict[str, str]:
    """Each '### ' heading of the template and the text under it."""
    found: dict[str, str] = {}
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        found[heading.strip()] = body.split("\n## ")[0]
    return found


def _point_section(point: int) -> str:
    matches = [body for heading, body in _sections(V9).items()
               if re.match(rf"Annex III point {point}\b", heading)]
    assert len(matches) == 1, point
    return matches[0]


def _top_list() -> list[str]:
    start = V9.index('- "flags": an object of booleans, ONLY from this list:')
    block = V9[start:V9.index("Rules, all binding:")]
    return re.findall(r"[a-z0-9_]+", block.split("this list:", 1)[1])


def _example() -> tuple[str, dict]:
    output = V9[V9.index("## Output"):]
    description = re.search(r"```text\n(.*?)\n```", output, re.S)
    reply = re.search(r"```json\n(.*?)\n```", output, re.S)
    assert description and reply
    return description.group(1), json.loads(reply.group(1))


# B185 Task 8: v10 is the prompt of record; v9 is kept byte for byte as the
# prompt of B184's record (the sha256 of the file at 0e45ac1).
V9_SHA256 = "7d902c912b29b1e3af3f948b8f185bc834a854db03d5501bf93737758c170d02"


def test_v9_is_kept_and_v10_is_the_prompt_of_record():
    assert hashlib.sha256((PROMPTS / "v9.md").read_bytes()).hexdigest() == V9_SHA256
    assert DEFAULT_PROMPT_VERSION == "v10"
    assert (PROMPTS / "v8.md").is_file()


# v9 is the prompt of B184's record; Task 8 made v10 the prompt of record
# (B185, ruling P27): the tests below read the facts v9 was written for.
def test_v9_names_every_schema_flag_and_only_those():
    listed = set(re.findall(r"flags\.([a-z0-9_]+)", V9))
    assert listed == set(FLAGS_OF_V9)


def test_v9_flag_list_is_the_schema_flags_in_the_schema_files_order():
    assert _top_list() == list(FLAGS_OF_V9)


def test_v9_each_listed_use_fact_quotes_its_own_unit():
    table = fact_provisions(V9)
    for rule in ANNEX_III_RULES:
        for fact, unit in rule["uses"]:
            assert unit in table[f"flags.{fact}"], fact


def test_v9_each_listed_use_stands_under_its_own_point_heading():
    for number, rule in enumerate(ANNEX_III_RULES, start=1):
        section = _point_section(number)
        table = fact_provisions("## Facts and their provisions\n" + section)
        for fact, unit in rule["uses"]:
            assert unit in table.get(f"flags.{fact}", []), (number, fact)
    headings = [h for h in _sections(V9) if h.startswith("Annex III point ")]
    assert len(headings) == 8


def test_v9_points_1_6_and_7_say_lawful_use_is_not_part_of_the_fact():
    for point in (1, 6, 7):
        section = " ".join(_point_section(point).split())
        assert LAWFUL_USE_SENTENCE in section, point
        assert "are not a fact" in section, point
    for point in (2, 3, 4, 5, 8):
        assert LAWFUL_USE_SENTENCE not in " ".join(_point_section(point).split()), point


def test_v9_purpose_fact_quotes_article_3_46_and_point_h():
    table = fact_provisions(V9)
    assert "eu-ai-act:definition:law-enforcement" in table["flags.law_enforcement_purpose"]
    assert ARTICLE_5_POINT_H in table["flags.law_enforcement_purpose"]


def test_finding_11_prompt_v9_has_no_drowsiness_example():
    assert "drowsiness" not in V9.lower()
    assert "eu-ai-act:recital-18" in fact_provisions(V9)["flags.emotion_recognition_medical_or_safety"]


def test_v9_recital_18_is_marked_as_context_under_the_emotion_facts():
    table = fact_provisions(V9)
    for fact in ("emotion_recognition", "emotion_recognition_workplace_or_education"):
        assert "eu-ai-act:recital-18" in table[f"flags.{fact}"], fact
    line = next(i for i, text in enumerate(V9.splitlines()) if "{{provision:eu-ai-act:recital-18}}" in text)
    assert "context, not binding: what the notion of emotion leaves out" in V9.splitlines()[line - 1]


def test_v9_article_6_3_facts_quote_their_points():
    table = fact_provisions(V9)
    for flag, nodes, _label in ARTICLE_6_3_CONDITIONS:
        assert set(nodes) <= set(table[f"flags.{flag}"])


def test_v9_biometric_identification_is_defined_by_its_own_unit_not_article_3_35():
    """Codex review: the fact is the remote biometric identification system of
    Annex III point 1(a) and Article 3(41); the wider Article 3(35) notion is
    not printed as its meaning."""
    nodes = fact_provisions(V9)["flags.biometric_identification"]
    assert "eu-ai-act:definition:biometric-identification" not in nodes
    assert nodes[0] in {"eu-ai-act:definition:remote-biometric-identification-system",
                        "eu-ai-act:annex-iii:point-1:a"}
    assert "eu-ai-act:annex-iii:point-1:a" in nodes


def test_v9_consistency_paragraph_names_every_entailment():
    paragraph = " ".join(V9[V9.index("Consistency:"):].split("\n\n")[0].split())
    sentences = [s for s in re.split(r"(?<=\.) ", paragraph) if s]
    for narrower, wider, _provision in FACT_ENTAILMENTS:
        assert any(s.startswith(f"When {narrower} is true") and wider in s for s in sentences), (narrower, wider)


def test_v9_article_5_and_article_50_facts_quote_the_classifiers_nodes():
    table = fact_provisions(V9)
    for flag, (node_id, _fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        assert node_id in table.get(f"flags.{flag}", []), flag
    for flag, (fact, _value, _element) in ARTICLE_5_EXCULPATING_FACT.items():
        assert ARTICLE_5_POINT_BY_FLAG[flag][0] in table.get(f"flags.{fact}", []), fact
    assert ARTICLE_5_POINT_H in table[f"flags.{ARTICLE_5_POINT_H_EXCULPATING[0]}"]
    for flag, paragraphs in ARTICLE_5_SCOPING_PARAGRAPHS.items():
        for paragraph in paragraphs:
            assert paragraph in table[f"flags.{flag}"], (flag, paragraph)
    assert ARTICLE_6_3_PROFILING_OVERRIDE in table["flags.profiling_of_natural_persons"]
    for flag, node_id, _note in ARTICLE_50_RULES_OF_V9:
        assert node_id in table.get(f"flags.{flag}", []), flag


def test_v9_every_schema_flag_has_a_provision():
    table = fact_provisions(V9)
    assert [name for name in FLAGS_OF_V9 if not table.get(f"flags.{name}")] == []


def test_v9_renders_over_the_build_with_every_provision_resolved(dump):
    system, record = render_prompt(dump, SNAPSHOTS_DIR, "v9")
    assert record["version"] == "v9" and "{{provision:" not in system


def test_v9_renders_no_deleted_provision_and_only_the_tables_nodes(dump):
    rendered, provisions = render_template(V9, dump, SNAPSHOTS_DIR)
    assert "Deleted by" not in rendered
    table_ids = {n for nodes in fact_provisions(V9).values() for n in nodes}
    assert {p["node_id"] for p in provisions} == table_ids == set(PLACEHOLDER_RE.findall(V9))


def test_v9_keeps_v8s_opening_rules_and_output_text():
    v8 = (PROMPTS / "v8.md").read_text(encoding="utf-8")
    assert V9.startswith(v8[: v8.index('- "flags": an object of booleans')])
    rules = v8[v8.index("Rules, all binding:"): v8.index("## Facts and their provisions")]
    assert rules in V9
    output = v8[v8.index("## Output"): v8.index("```text")]
    assert output in V9


def test_v9_example_quotes_are_in_its_description_and_name_schema_facts():
    description, example = _example()
    assert set(example) == {"features", "quotes"}
    flags = example["features"]["flags"]
    assert set(flags) <= set(schema_flag_names())
    for path, quote in example["quotes"].items():
        assert len(quote.split()) >= 3, path
        assert quote in description, path
        if path.startswith("flags."):
            assert path[len("flags."):] in flags, path
        else:
            assert path in example["features"], path
    for name in flags:
        assert f"flags.{name}" in example["quotes"], name


def test_v9_example_answers_every_point_5_listed_use_false_and_classifies_without_contradiction(dump):
    """The bank chatbot with the domain banking: with every point 5 listed use
    answered false the domain word stops counting (D-G91 (3)), so the
    classifier gives no Annex III point and marks no fact conflict.

    B185 (DEC-33): v9 is a record from B185 Task 1 on, and its example's
    domain banking is not a value of the schema, so the example is classified
    with its domain removed; prompt v10 (B185 Task 8) gives the example of
    record."""
    description, example = _example()
    flags = example["features"]["flags"]
    assert {fact: flags.get(fact) for fact in POINT_5_USES} == dict.fromkeys(POINT_5_USES, False)
    assert example["features"].get("domain") == "banking"
    features = {k: v for k, v in example["features"].items() if k != "domain"}
    env = classify_ai_system({"description": description, **features}, dump)
    assert env["answer"]["fact_conflicts"] == []
    assert env["answer"]["annex_iii_category"] is None
    assert env["answer"]["risk_category"] == "limited_risk"


def test_v9_has_no_em_or_en_dash():
    assert chr(0x2014) not in V9
    assert chr(0x2013) not in V9


def test_v9_elicitation_with_a_fake_client_keeps_a_listed_use_fact(dump):
    reply = {"features": {"flags": {"annex_iii_4b_work_relationships": True}},
             "quotes": {"flags.annex_iii_4b_work_relationships": "scores each office worker's productivity"}}
    fake = FakeClient({DESCRIPTION[:30]: json.dumps(reply)})
    # B185 Task 8: v9 is no longer the default, so it is named.
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR, prompt_version="v9")
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.prompt["version"] == "v9"


def test_a_proposed_fact_outside_the_schema_is_named_in_the_notes_and_not_kept(dump):
    """A flag the schema does not define (here employment_decisions, removed by
    B184) is removed by the cleaning step and is not in dropped; the notes name
    it once, in a fixed form, whether or not the reply quoted it (fix round 1,
    M7). A top-level field outside the schema is named the same way."""
    quote = "scores each office worker's productivity"
    reply = {"features": {"risk_category": "high_risk",
                          "flags": {"annex_iii_4b_work_relationships": True, "employment_decisions": True}},
             "quotes": {"flags.annex_iii_4b_work_relationships": quote, "flags.employment_decisions": quote}}
    fake = FakeClient({DESCRIPTION[:30]: json.dumps(reply)})
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert "risk_category" not in result.features
    assert result.dropped == []
    named = [note for note in result.notes if "employment_decisions" in note or "risk_category" in note]
    assert named == [OUTSIDE_NOTE.format(path="risk_category"),
                     OUTSIDE_NOTE.format(path="flags.employment_decisions")]

    del reply["quotes"]["flags.employment_decisions"]
    fake = FakeClient({DESCRIPTION[:30]: json.dumps(reply)})
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.dropped == []
    assert [note for note in result.notes if "employment_decisions" in note] == [
        OUTSIDE_NOTE.format(path="flags.employment_decisions")]


def test_v9_real_time_identification_quotes_article_3_44():
    assert "eu-ai-act:definition:publicly-accessible-space" in fact_provisions(V9)["flags.real_time_remote_biometric_public"]


def test_v9_point_2_fact_quotes_article_6_1a_and_6_1b():
    nodes = fact_provisions(V9)["flags.critical_infrastructure_safety"]
    assert {"eu-ai-act:article-6:paragraph-1a", "eu-ai-act:article-6:paragraph-1b"} <= set(nodes)


# Facts whose schema description quotes words that v9 does not attach to them,
# each with its reason (fix rounds 1 and 2, I3): (fact, the opening words of
# the quoted passage). Only the opening words of points 1, 6 and 7 are
# excepted; the quotation of each listed use is never excepted.
OPENING_WORDS = {
    0: "Biometrics, in so far as",
    5: "Law enforcement, in so far as",
    6: "Migration, asylum and border control management, in so far as",
}
SCHEMA_QUOTE_EXCEPTIONS: dict[tuple[str, str], str] = {
    (fact, words): f"P16: the opening words of point {index + 1} are stated in the prompt's words under its "
                   "heading; the whole point node is not printed"
    for index, words in OPENING_WORDS.items()
    for fact, _unit in ANNEX_III_RULES[index]["uses"]
}
# The listed-use fact to its own legal unit, the node its x-annex-iii-use names.
LISTED_USE_UNIT = {fact: unit for rule in ANNEX_III_RULES for fact, unit in rule["uses"]}


def _schema_quote_gaps(
    text: str, dump: dict, facts: tuple[str, ...] | list[str] = FLAGS_OF_V9
) -> tuple[list[tuple[str, str, str]], set[tuple[str, str]]]:
    """The gaps between a prompt template and the schema descriptions, and the
    exceptions used.

    Each passage a fact's description quotes (the QUOTED pattern of
    test_features_schema_descriptions.py) is resolved, as that file's
    test_every_quoted_passage_is_the_text_of_a_node resolves it, to the nodes
    whose normalised text holds it; one of them must be a provision the
    template attaches to the fact (a parent node counts, since its printed text
    holds the passage). For a listed-use fact, the quotation of the use itself
    (the passage after "the Act's words:") must be held by the use's own legal
    unit and that unit must be attached to the fact; a parent point never
    counts for it. A passage opening with the words of an exception is excused
    for that fact only. A gap is (fact, the reason, the passage's first words).
    facts names the facts checked: FLAGS_OF_V9 for v9, the live schema's for
    v10.
    """
    from tests.unit.test_features_schema_descriptions import QUOTE, QUOTED, _normalised

    texts = {n["id"]: _normalised(n.get("text") or "") for n in dump["nodes"]
             if n.get("type") != "UnitVersion" and n.get("text")}
    table = fact_provisions(text)
    gaps: list[tuple[str, str, str]] = []
    used: set[tuple[str, str]] = set()
    for fact, spec in SCHEMA["properties"]["flags"]["properties"].items():
        if fact not in facts:
            # B185 (ruling P27): a fact the schema gained after v9 was written
            # (the two Article 50(4) facts) is not one v9 asks; the tests of
            # v10 (B185 Task 8) pass the live schema's facts.
            continue
        attached = set(table.get(f"flags.{fact}", []))
        use_quote = None
        if fact in LISTED_USE_UNIT:
            unit = LISTED_USE_UNIT[fact]
            use_quote = _normalised(QUOTE.search(spec["description"]).group(1))
            if use_quote not in texts.get(unit, ""):
                gaps.append((fact, f"the use's quotation is not the text of {unit}", use_quote[:60]))
            elif unit not in attached:
                gaps.append((fact, f"{unit} is not attached", use_quote[:60]))
        for quoted in QUOTED.findall(spec["description"]):
            passage = _normalised(quoted)
            if passage == use_quote:
                continue
            holders = {node for node, node_text in texts.items() if passage in node_text}
            if not holders:
                gaps.append((fact, "no node holds the passage", passage[:60]))
            elif not holders & attached:
                excepted = [key for key in SCHEMA_QUOTE_EXCEPTIONS
                            if key[0] == fact and passage.startswith(key[1])]
                if excepted:
                    used.update(excepted)
                else:
                    gaps.append((fact, f"none of {sorted(holders)} is attached", passage[:60]))
    return gaps, used


def test_v9_attaches_to_each_fact_every_unit_its_schema_description_quotes(dump):
    """Every unit a fact's schema description quotes is a provision v9
    attaches to the fact, the exceptions above excepted, and each exception
    still applies."""
    gaps, used = _schema_quote_gaps(V9, dump)
    assert gaps == []
    assert used == set(SCHEMA_QUOTE_EXCEPTIONS), "an exception no longer applies"


@pytest.mark.parametrize("fact", sorted(LISTED_USE_UNIT))
def test_the_schema_check_fails_when_a_listed_use_loses_its_unit(fact, dump):
    """Mutation: v9 without the placeholder of the fact's own unit, in memory,
    gives a gap for that fact (fix round 2)."""
    placeholder = "{{provision:" + LISTED_USE_UNIT[fact] + "}}"
    assert placeholder in V9, fact
    mutated = "\n".join(line for line in V9.splitlines() if line.strip() != placeholder)
    gaps, _used = _schema_quote_gaps(mutated, dump)
    assert fact in {gap[0] for gap in gaps}, fact


def test_v9_area_headings_are_the_schemas_area_names():
    areas = SCHEMA["properties"]["flags"]["x-annex-iii-areas"]
    headings = [h for h in _sections(V9) if h.startswith("Annex III point ")]
    assert headings == [f"Annex III point {key}: {areas[key]}" for key in sorted(areas, key=int)]


def test_v9_names_the_facts_under_points_1_and_2_that_are_not_listed_uses():
    point_1 = " ".join(_point_section(1).split())
    point_2 = " ".join(_point_section(2).split())
    assert "Each listed-use fact under this heading" in point_1
    assert "Each fact under this heading" not in V9
    assert re.search(r"real_time_remote_biometric_public [^.]*not a listed use of point 1", point_1)
    assert re.search(r"medical_or_safety_component and annex_i_covered_product [^.]*not listed uses of point 2",
                     point_2)


def test_v9_consistency_paragraph_gives_the_emotion_pair_as_the_projects_reading():
    paragraph = " ".join(V9[V9.index("Consistency:"):].split("\n\n")[0].split())
    sentence = next(s for s in re.split(r"(?<=\.) ", paragraph)
                    if s.startswith("When emotion_recognition_workplace_or_education is true"))
    assert "the project's reading of point (f)" in sentence

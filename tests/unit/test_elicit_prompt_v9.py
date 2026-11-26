"""Prompt v9 of elicit_features, the prompt of record (B184 Task 7, DEC-32).

v9 asks the 54 facts of the schema: the 25 Annex III listed uses under eight
headings, one per point, each with its own legal unit; law_enforcement_purpose
under Article 5(1)(h); narrow_procedural_task and preparatory_task under
Article 6(3) points (a) and (d). v8 stays as the prompt of tag v2.0.0-beta.1
(ruling P15). Offline only: the repository's dump, FakeClient replies, no
model and no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

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
    ARTICLE_50_RULES,
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


def test_v9_is_the_prompt_of_record():
    assert DEFAULT_PROMPT_VERSION == "v9"
    assert (PROMPTS / "v8.md").is_file()


def test_v9_names_every_schema_flag_and_only_those():
    listed = set(re.findall(r"flags\.([a-z0-9_]+)", V9))
    assert listed == set(schema_flag_names())


def test_v9_flag_list_is_the_schema_flags_in_the_schema_files_order():
    assert _top_list() == list(SCHEMA["properties"]["flags"]["properties"])


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
    for flag, node_id, _note in ARTICLE_50_RULES:
        assert node_id in table.get(f"flags.{flag}", []), flag


def test_v9_every_schema_flag_has_a_provision():
    table = fact_provisions(V9)
    assert [name for name in schema_flag_names() if not table.get(f"flags.{name}")] == []


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
    classifier gives no Annex III point and marks no fact conflict."""
    description, example = _example()
    flags = example["features"]["flags"]
    assert {fact: flags.get(fact) for fact in POINT_5_USES} == dict.fromkeys(POINT_5_USES, False)
    env = classify_ai_system({"description": description, **example["features"]}, dump)
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
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.prompt["version"] == "v9"


def test_a_proposed_fact_outside_the_schema_is_removed_before_the_quote_check(dump):
    """A flag the schema does not define (here employment_decisions, removed by
    B184) is removed by the cleaning step: it is neither kept nor named in
    dropped; its quote, when the reply gives one, is named in the notes as
    ignored. The same reply without that quote leaves no trace."""
    quote = "scores each office worker's productivity"
    reply = {"features": {"flags": {"annex_iii_4b_work_relationships": True, "employment_decisions": True}},
             "quotes": {"flags.annex_iii_4b_work_relationships": quote, "flags.employment_decisions": quote}}
    fake = FakeClient({DESCRIPTION[:30]: json.dumps(reply)})
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.dropped == []
    assert "quote for flags.employment_decisions ignored: the features carry no such fact" in result.notes

    del reply["quotes"]["flags.employment_decisions"]
    fake = FakeClient({DESCRIPTION[:30]: json.dumps(reply)})
    result = elicit(DESCRIPTION, fake, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"annex_iii_4b_work_relationships": True}
    assert result.dropped == []
    assert not any("employment_decisions" in note for note in result.notes)

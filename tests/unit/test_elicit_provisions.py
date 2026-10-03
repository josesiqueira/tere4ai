"""Unit tests for the elicitor's provisions rendered from the graph (B10).

Offline only: runs against the repository's published dump
(data/graph_dumps/layer1.json) and the frozen snapshots (data/snapshots).
No model, no network.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from tere4ai.elicit_features.provisions import (
    ProvisionUnresolved,
    fact_provisions,
    provision_text,
    render_template,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

DEFINITION_ID = "eu-ai-act:definition:ai-system"
POINT_ID = "eu-ai-act:annex-iii:point-5:b"
ARTICLE_ID = "eu-ai-act:article-16"


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _node(dump: dict, node_id: str) -> dict:
    return next(n for n in dump["nodes"] if n["id"] == node_id)


def test_definition_renders_as_id_and_exactly_the_node_text(dump: dict) -> None:
    node = _node(dump, DEFINITION_ID)
    got = provision_text(DEFINITION_ID, dump, SNAPSHOTS_DIR)
    assert got == {
        "node_id": DEFINITION_ID,
        "span_id": node["source_span"]["span_id"],
        "text": node["text"],
    }
    rendered, provisions = render_template(
        "Definition:\n{{provision:" + DEFINITION_ID + "}}\n", dump, SNAPSHOTS_DIR
    )
    assert rendered == f"Definition:\n[{DEFINITION_ID}] {node['text']}\n"
    assert "<" not in rendered
    assert provisions == [
        {"node_id": DEFINITION_ID, "span_id": node["source_span"]["span_id"]}
    ]


def test_render_lists_each_provision_once_in_order(dump: dict) -> None:
    template = (
        "{{provision:" + POINT_ID + "}}\n"
        "{{provision:" + DEFINITION_ID + "}}\n"
        "{{provision:" + POINT_ID + "}}\n"
    )
    rendered, provisions = render_template(template, dump, SNAPSHOTS_DIR)
    assert [p["node_id"] for p in provisions] == [POINT_ID, DEFINITION_ID]
    point_text = _node(dump, POINT_ID)["text"]
    assert rendered.count(f"[{POINT_ID}] {point_text}") == 2
    assert "{{provision:" not in rendered
    assert "<" not in rendered


def test_unknown_node_raises_naming_node_and_build(dump: dict) -> None:
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text("eu-ai-act:no-such-node", dump, SNAPSHOTS_DIR)
    message = str(exc.value)
    assert "eu-ai-act:no-such-node" in message
    assert dump["build"]["build_id"] in message
    assert "unknown node" in message


def test_node_without_text_raises(dump: dict) -> None:
    assert not _node(dump, ARTICLE_ID).get("text")
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(ARTICLE_ID, dump, SNAPSHOTS_DIR)
    assert ARTICLE_ID in str(exc.value)
    assert "no text" in str(exc.value)


def test_node_without_span_raises(dump: dict) -> None:
    altered = copy.deepcopy(dump)
    del _node(altered, DEFINITION_ID)["source_span"]
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(DEFINITION_ID, altered, SNAPSHOTS_DIR)
    assert "no source span" in str(exc.value)


def test_altered_snapshot_checksum_raises(dump: dict) -> None:
    altered = copy.deepcopy(dump)
    _node(altered, DEFINITION_ID)["source_span"]["snapshot_sha256"] = "0" * 64
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(DEFINITION_ID, altered, SNAPSHOTS_DIR)
    message = str(exc.value)
    assert "span verification failed" in message
    assert "checksum mismatch" in message


def test_render_raises_before_returning_on_any_unresolved(dump: dict) -> None:
    template = "{{provision:" + DEFINITION_ID + "}} {{provision:" + ARTICLE_ID + "}}"
    with pytest.raises(ProvisionUnresolved):
        render_template(template, dump, SNAPSHOTS_DIR)


def test_template_without_placeholders_is_identity(dump: dict) -> None:
    text = "No provisions here.\n## Output\n{\"features\": {}}\n"
    assert render_template(text, dump, SNAPSHOTS_DIR) == (text, [])


def test_fact_provisions_reads_the_section() -> None:
    template = (
        "# Role\n"
        "{{provision:eu-ai-act:definition:ai-system}}\n"
        "## Facts and their provisions\n"
        "- Facts: flags.social_scoring\n"
        "{{provision:eu-ai-act:article-5:paragraph-1:c}}\n"
        "- Facts: flags.creditworthiness_evaluation, flags.life_health_insurance_risk_pricing\n"
        "{{provision:eu-ai-act:annex-iii:point-5:b}}\n"
        "{{provision:eu-ai-act:annex-iii:point-5:c}}\n"
        "## Output\n"
        "{{provision:eu-ai-act:article-50:paragraph-1}}\n"
    )
    assert fact_provisions(template) == {
        "flags.social_scoring": ["eu-ai-act:article-5:paragraph-1:c"],
        "flags.creditworthiness_evaluation": [
            "eu-ai-act:annex-iii:point-5:b",
            "eu-ai-act:annex-iii:point-5:c",
        ],
        "flags.life_health_insurance_risk_pricing": [
            "eu-ai-act:annex-iii:point-5:b",
            "eu-ai-act:annex-iii:point-5:c",
        ],
    }


def test_fact_provisions_without_the_section_is_empty() -> None:
    assert fact_provisions("# Role\n{{provision:eu-ai-act:definition:ai-system}}\n") == {}


def test_fact_provisions_rejects_a_placeholder_before_any_facts_line() -> None:
    template = (
        "## Facts and their provisions\n"
        "{{provision:eu-ai-act:definition:ai-system}}\n"
    )
    with pytest.raises(ValueError):
        fact_provisions(template)


# Prompt v6 (B10 task 2): the fact-to-provision table lives in the template.

V6_PATH = ROOT / "prompts" / "elicit_features" / "v6.md"
OMNIBUS_FLAGS = ("generates_nonconsensual_intimate_material", "generates_csam")


def _v6_text() -> str:
    return V6_PATH.read_text(encoding="utf-8")


def _v6_table() -> dict[str, list[str]]:
    return fact_provisions(_v6_text())


def test_v6_every_schema_flag_but_the_two_omnibus_facts_has_a_provision() -> None:
    """Each flag's list is not empty; the Omnibus points have no node in the
    pinned base graph, so they carry none."""
    from tere4ai.elicit_features.elicitor import schema_flag_names

    table = _v6_table()
    without = [
        name
        for name in schema_flag_names()
        if name not in OMNIBUS_FLAGS and not table.get(f"flags.{name}")
    ]
    assert without == []
    for name in OMNIBUS_FLAGS:
        assert table.get(f"flags.{name}", []) == []


def test_v6_article_5_flags_quote_the_point_the_classifier_cites() -> None:
    from tere4ai.mcp_server.classify import (
        ARTICLE_5_EXCULPATING_FACT,
        ARTICLE_5_POINT_BY_FLAG,
        ARTICLE_5_POINT_H,
        ARTICLE_5_POINT_H_EXCULPATING,
    )

    table = _v6_table()
    for flag, (node_id, _fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        assert node_id in table.get(f"flags.{flag}", []), flag
    assert ARTICLE_5_POINT_H in table["flags.real_time_remote_biometric_public"]
    # Each exculpating fact quotes the point whose exception or element it is.
    for flag, (fact, _value, _element) in ARTICLE_5_EXCULPATING_FACT.items():
        point = ARTICLE_5_POINT_BY_FLAG[flag][0]
        assert point in table.get(f"flags.{fact}", []), fact
    assert ARTICLE_5_POINT_H in table[f"flags.{ARTICLE_5_POINT_H_EXCULPATING[0]}"]


def test_v6_annex_iii_flags_quote_the_classifiers_node_or_one_of_its_points() -> None:
    from tere4ai.mcp_server.classify import ANNEX_III_RULES

    table = _v6_table()
    for rule in ANNEX_III_RULES:
        node = rule["node"]
        for flag in (*rule["flags"], *rule.get("subflags", ())):
            nodes = table.get(f"flags.{flag}", [])
            assert any(n == node or n.startswith(node + ":") for n in nodes), flag
    assert "eu-ai-act:annex-iii:point-5:b" in table["flags.creditworthiness_evaluation"]
    assert "eu-ai-act:annex-iii:point-5:c" in table["flags.life_health_insurance_risk_pricing"]
    assert "eu-ai-act:annex-iii:point-1:b" in table[
        "flags.biometric_categorisation_sensitive_or_protected_attributes"
    ]


def test_v6_article_6_and_article_50_flags_quote_the_classifiers_nodes() -> None:
    from tere4ai.mcp_server.classify import (
        ARTICLE_6_3_CONDITIONS,
        ARTICLE_6_3_PROFILING_OVERRIDE,
        ARTICLE_50_RULES,
    )

    table = _v6_table()
    for flag, node_ids, _note in ARTICLE_6_3_CONDITIONS:
        for node_id in node_ids:
            assert node_id in table.get(f"flags.{flag}", []), flag
    assert ARTICLE_6_3_PROFILING_OVERRIDE in table["flags.profiling_of_natural_persons"]
    assert "eu-ai-act:article-6:paragraph-1:point-a" in table["flags.annex_i_covered_product"]
    assert "eu-ai-act:article-6:paragraph-1:point-b" in table[
        "flags.third_party_conformity_assessment_required"
    ]
    for flag, node_id, _note in ARTICLE_50_RULES:
        assert node_id in table.get(f"flags.{flag}", []), flag


def test_v6_keeps_the_article_3_definitions_v5_used() -> None:
    v5 = (ROOT / "prompts" / "elicit_features" / "v5.md").read_text(encoding="utf-8")
    v5_definitions = set(re.findall(r"\[(eu-ai-act:definition:[a-z0-9-]+)\]", v5))
    assert v5_definitions, "v5 names its definitions"
    quoted = {n for nodes in _v6_table().values() for n in nodes}
    assert v5_definitions <= quoted


def test_v6_renders_against_the_repository_dump(dump: dict) -> None:
    """Every provision resolves on the repository's build; the rendered
    prompt carries node text only, never raw Formex or HTML."""
    text = _v6_text()
    rendered, provisions = render_template(text, dump, SNAPSHOTS_DIR)
    assert "{{provision:" not in rendered
    assert "<" not in rendered
    rendered_ids = [p["node_id"] for p in provisions]
    table_ids = {n for nodes in fact_provisions(text).values() for n in nodes}
    # No placeholder outside the table, none in the table left unrendered.
    assert set(rendered_ids) == table_ids
    for node_id in rendered_ids:
        node = _node(dump, node_id)
        assert node.get("type") not in {"Article", "Annex"}, node_id
        if node.get("amendment") == "deleted":
            # B132: v6 still names Annex I Section A point 1, which the
            # Omnibus deleted; the rendered prompt says so.
            assert f"[{node_id}] Deleted by {node['deleted_by']}, from 27 July 2026." in rendered
            continue
        assert f"[{node_id}] {node['text']}" in rendered


def test_v6_output_example_quotes_are_in_its_description() -> None:
    """The worked example shows the reply shape: features and quotes, each
    quote at least three words copied from the example description."""
    text = _v6_text()
    description = re.search(r"```text\n(.*?)\n```", text, re.S)
    reply = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert description and reply
    example = json.loads(reply.group(1))
    assert set(example) == {"features", "quotes"}
    quotes = example["quotes"]
    flags = example["features"].get("flags", {})
    assert any(value is False for value in flags.values()), "a false flag is quoted too"
    for path, quote in quotes.items():
        assert len(quote.split()) >= 3, path
        assert quote in description.group(1), path
        if path.startswith("flags."):
            assert path[len("flags."):] in flags, path
        else:
            assert path in example["features"], path
    for name in flags:
        assert f"flags.{name}" in quotes, name


def test_v6_has_no_em_or_en_dash() -> None:
    text = _v6_text()
    assert chr(0x2014) not in text
    assert chr(0x2013) not in text

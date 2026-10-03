"""The norms' target_system_category: four values, set by rule (DEC-21, B124).

Spec G D-G62: the field names the part of the Act's rules the norm belongs
to, by the category of AI systems those rules govern, and a rule table over
the source Article or Annex sets it; no model decides it. Pure functions
plus the Layer 1 dump; no model, no network.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tere4ai.extract_norms.pipeline import expand_source_units
from tere4ai.extract_norms.target_system_category import (
    ANY_AI_SYSTEM,
    ARTICLE_50_AI_SYSTEM,
    HIGH_RISK_AI_SYSTEM,
    PROHIBITED_AI_PRACTICE,
    RULE_TABLE,
    TARGET_SYSTEM_CATEGORIES,
    category_for,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "norms.schema.json").read_text(encoding="utf-8"))
DUMPS = ROOT / "data" / "graph_dumps"
LAYER1_PATH = DUMPS / "layer1.json"
CORE_NODES_PATH = DUMPS / "core_nodes.txt"
needs_layer1 = pytest.mark.skipif(
    not (LAYER1_PATH.is_file() and CORE_NODES_PATH.is_file()),
    reason="layer1.json or core_nodes.txt not built",
)


def _core_ids() -> list[str]:
    return [i.strip() for i in CORE_NODES_PATH.read_text(encoding="utf-8").split(",") if i.strip()]


@pytest.fixture(scope="module")
def layer1():
    return json.loads(LAYER1_PATH.read_text(encoding="utf-8"))


def test_the_four_values_are_the_schemas_closed_set():
    assert TARGET_SYSTEM_CATEGORIES == (
        "any_ai_system", "prohibited_ai_practice", "high_risk_ai_system", "article_50_ai_system",
    )
    assert SCHEMA["$defs"]["targetSystemCategory"]["enum"] == list(TARGET_SYSTEM_CATEGORIES)
    field = SCHEMA["properties"]["target_system_category"]
    assert field["anyOf"] == [{"$ref": "#/$defs/targetSystemCategory"}, {"type": "null"}]
    assert "the part of the Act's rules the norm belongs to" in field["description"]
    assert "target_system_category" not in SCHEMA["required"]


def test_category_for_reads_the_article_or_annex_of_the_unit():
    # D-G62's example: Article 6(4) is a high-risk classification rule,
    # whatever system its sentence talks about.
    assert category_for("eu-ai-act:article-6:paragraph-4") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:article-5:paragraph-2") == PROHIBITED_AI_PRACTICE
    assert category_for("eu-ai-act:article-50:paragraph-3") == ARTICLE_50_AI_SYSTEM
    assert category_for("eu-ai-act:article-3:paragraph-1:point-63") == ANY_AI_SYSTEM
    assert category_for("eu-ai-act:annex-iii:point-1:a") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:annex-iv:point-1") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:article-73:paragraph-11") == HIGH_RISK_AI_SYSTEM
    # Outside the table: null, never a guess, even inside Chapter III.
    for outside in ("eu-ai-act:article-4:paragraph-1", "eu-ai-act:article-30:paragraph-1",
                    "eu-ai-act:article-53:paragraph-1", "eu-ai-act:annex-i:section-a:point-1"):
        assert category_for(outside) is None


def test_category_for_matches_the_whole_article_segment():
    """Review focus 2: article-5 is not article-50, article-7 is not 72 or 73."""
    assert category_for("eu-ai-act:article-5:paragraph-1:point-a") == PROHIBITED_AI_PRACTICE
    assert category_for("eu-ai-act:article-50:paragraph-1") == ARTICLE_50_AI_SYSTEM
    assert category_for("eu-ai-act:article-7:paragraph-1") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:article-72:paragraph-1") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:article-16:paragraph-1") == HIGH_RISK_AI_SYSTEM
    assert category_for("eu-ai-act:article-1") is None
    assert category_for("eu-ai-act:article-500:paragraph-1") is None


def test_category_for_never_raises_on_a_malformed_id():
    """Review focus 5: a hand-written decisions file may carry anything."""
    for malformed in (None, 7, "", "x", "eu-ai-act", "article-9:paragraph-1"):
        assert category_for(malformed) is None


@needs_layer1
def test_the_table_has_one_row_per_core_id():
    assert sorted(RULE_TABLE) == sorted(_core_ids())
    assert len(RULE_TABLE) == 29


@needs_layer1
def test_every_core_unit_of_the_layer1_dump_resolves_to_a_value(layer1):
    """Acceptance 2: every source unit B74 extracts gets a value by the rule:
    414 on the Act as amended (B132; 405 on the 2024 text), before plan B
    adds Article 4a."""
    units = expand_source_units(layer1, _core_ids())
    assert len(units) == 414
    values = Counter(category_for(unit["node_id"]) for unit in units)
    assert values == {
        HIGH_RISK_AI_SYSTEM: 294, ANY_AI_SYSTEM: 82, PROHIBITED_AI_PRACTICE: 31, ARTICLE_50_AI_SYSTEM: 7,
    }


@needs_layer1
def test_each_rows_deciding_wording_is_verbatim_in_the_layer1_dump(layer1):
    nodes = {node["id"]: node for node in layer1["nodes"]}
    for container, row in RULE_TABLE.items():
        assert row.value in TARGET_SYSTEM_CATEGORIES, container
        assert row.wording, container
        for node_id, words in row.wording:
            node = nodes[node_id]
            haystack = " ".join(f"{node.get('title') or ''} {node.get('text') or ''}".split())
            assert words in haystack, (container, node_id, words)


@needs_layer1
def test_a_row_decided_by_a_chapter_title_names_the_chapter_that_holds_its_article(layer1):
    nodes = {node["id"]: node for node in layer1["nodes"]}
    parent = {e["to"]: e["from"] for e in layer1["edges"] if e["edge_type"] in ("HAS_ARTICLE", "HAS_SECTION")}

    def chapter_of(node_id: str) -> str | None:
        up = parent.get(node_id)
        while up is not None and nodes[up]["type"] != "Chapter":
            up = parent.get(up)
        return up

    checked = 0
    for container, row in RULE_TABLE.items():
        for node_id, _words in row.wording:
            if nodes[node_id]["type"] == "Chapter":
                assert chapter_of(container) == node_id, container
                checked += 1
    assert checked == 25  # Articles 3, 5, 6 to 27 and 50

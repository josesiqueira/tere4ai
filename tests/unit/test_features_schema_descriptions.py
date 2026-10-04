"""Every fact of the features schema says what it means in the Act's words (B122, DEC-18).

The classifier page, the project door and a person confirming the
elicitor's proposal read each flag's meaning from its description, so a
flag without one has no meaning anywhere. Each description names its
provision and quotes the Act; every quoted passage is checked word for
word against the text of a node of the published Layer 1 dump.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

PROVISION = re.compile(r"\b(Article \d+\(\d+[a-z]?\)|Annex [IVX]+ point \d)")
QUOTE = re.compile(r"the Act's words: '([^']+)'")
# Every passage in single quotes, opened after a space or a bracket (so the
# apostrophe of "Act's" never opens one); the Act's own apostrophes are
# typographic and never close one.
QUOTED = re.compile(r"(?:^|[\s(])'([^']+)'(?=[\s.,;)]|$)")


def _flags() -> dict[str, dict]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return schema["properties"]["flags"]["properties"]


def _normalised(text: str) -> str:
    """Whitespace collapsed and the single quotation marks around a quoted term
    dropped: the Formex text keeps them ('real-time' remote biometric
    identification, B132), the descriptions' quotes leave them out. An
    apostrophe (a lone right mark) stays."""
    text = re.sub(
        "\N{LEFT SINGLE QUOTATION MARK}([^\N{LEFT SINGLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK}]*)"
        "\N{RIGHT SINGLE QUOTATION MARK}", r"\1", text)
    return " ".join(text.split())


def test_every_flag_has_a_description_naming_its_provision():
    for name, spec in _flags().items():
        description = spec.get("description", "")
        assert description.strip(), f"{name} has no description"
        assert PROVISION.search(description), f"{name}: the description names no Article or Annex point"


def test_every_flag_quotes_the_act():
    """B132: the two prohibitions the Digital Omnibus inserted are Article 5
    points of the graph now, so they quote it like every other flag."""
    for name, spec in _flags().items():
        assert QUOTE.search(spec["description"]), f"{name}: no passage quoted in the Act's words"


@pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")
def test_every_quoted_passage_is_the_text_of_a_node():
    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    # In-force text only: an earlier version (UnitVersion) is not the Act in force.
    texts = [_normalised(node.get("text") or "") for node in dump["nodes"] if node.get("type") != "UnitVersion"]
    for name, spec in _flags().items():
        for quoted in QUOTED.findall(spec["description"]):
            passage = _normalised(quoted)
            assert any(passage in text for text in texts), f"{name}: '{passage}' is in no node's text"


def test_the_amended_article_6_and_article_3_14_are_in_the_facts_they_bear_on():
    """D7.2: Article 6(1a) to (1c) and the replaced Article 3(14) in the Act's
    words; the Annex I section fact quotes Article 2(2)."""
    flags = _flags()
    assert "Article 3(14) as replaced by Regulation (EU) 2026/1744" in flags["medical_or_safety_component"]["description"]
    for name in ("medical_or_safety_component", "annex_i_covered_product"):
        assert "Article 6(1a)" in flags[name]["description"] and "Article 6(1b)" in flags[name]["description"], name
    assert "Article 6(1c)" in flags["third_party_conformity_assessment_required"]["description"]
    assert "Article 2(2)" in flags["annex_i_section_b_legislation"]["description"]
    assert flags["annex_i_section_b_legislation"]["type"] == "boolean"

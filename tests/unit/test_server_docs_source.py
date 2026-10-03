"""The one source explaining the MCP server, docs/server/index.md (DEC-22, B90).

The source holds its sections in a fixed order, an opening with the
definition, the screenshot and the notice region, six generated regions
written as pairs of markers, the README part and the reading part, and one
example request that the generator sends to the server, so it must be a
valid system_features object.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "server" / "index.md"
FEATURES_SCHEMA = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
SCREENSHOT = (
    "https://raw.githubusercontent.com/josesiqueira/tere4ai/main/"
    "docs/screenshots/readme-mcp-demo.png"
)

SECTIONS = [
    "Who it is for",
    "Wire it into your agent",
    "What a call looks like",
    "The tools",
    "What it is not",
    "How to read every answer",
    "Paid calls and the replay window",
    "MCP revisions and clients",
    "Span offsets",
    "Duplicate keys",
    "The instructions the server sends",
    "The tool reference",
]
REGIONS = ["notice", "example", "tools", "fields", "statuses", "instructions"]


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_sections_are_second_level_headings_in_order():
    headings = re.findall(r"^## (.+?)\s*$", _source(), re.MULTILINE)
    assert headings == SECTIONS


def test_the_opening_holds_the_definition_the_screenshot_and_the_notice():
    opening = _source().split("\n## ", 1)[0]
    assert "MCP server" in opening and "coding agent" in opening
    assert "rule ladder alone decides the level" in opening
    assert f"]({SCREENSHOT})" in opening
    assert "<!-- generated: notice -->" in opening
    assert "<!-- end generated: notice -->" in opening


def test_each_region_has_one_opening_and_one_closing_marker():
    text = _source()
    for name in REGIONS:
        assert text.count(f"<!-- generated: {name} -->") == 1, name
        assert text.count(f"<!-- end generated: {name} -->") == 1, name
        assert text.index(f"<!-- generated: {name} -->") < text.index(
            f"<!-- end generated: {name} -->"
        ), name


def test_the_readme_part_and_the_reading_part_appear_once():
    text = _source()
    for part in ("readme", "reading"):
        assert text.count(f"<!-- {part}: start -->") == 1, part
        assert text.count(f"<!-- {part}: end -->") == 1, part
        assert text.index(f"<!-- {part}: start -->") < text.index(f"<!-- {part}: end -->")
    readme = text.split("<!-- readme: start -->", 1)[1].split("<!-- readme: end -->", 1)[0]
    assert "## What it is not" in readme
    assert "## How to read every answer" not in readme
    reading = text.split("<!-- reading: start -->", 1)[1].split("<!-- reading: end -->", 1)[0]
    for name in ("fields", "statuses"):
        assert f"<!-- generated: {name} -->" in reading


def test_the_example_request_is_one_valid_json_block():
    text = _source()
    assert text.count("<!-- example request: start -->") == 1
    block = text.split("<!-- example request: start -->", 1)[1].split(
        "<!-- example request: end -->", 1
    )[0]
    fences = re.findall(r"```json\n(.*?)\n```", block, re.DOTALL)
    assert len(fences) == 1
    request = json.loads(fences[0])
    assert list(request) == ["features"]
    schema = json.loads(FEATURES_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(request["features"], schema)

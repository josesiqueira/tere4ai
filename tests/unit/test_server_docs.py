"""The server docs generator and the checks on the public texts (DEC-22, B90).

Tests 2 to 6 read the served surface once from the real server (started
over stdio with the official MCP Python SDK client, no model keys, only
the two free tools called). Tests 7 to 13 use mock surfaces and temporary
copies of the files, no server. Test 1 runs the generator's --check.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tere4ai.mcp_server.keys import TOOL_SCOPES
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    SECTION_8_ENVELOPE_FIELDS,
    STATUS_VOCABULARY,
)
from tere4ai.server_docs import prose, render, session
from tere4ai.server_docs.session import ServedTool, Surface

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "server" / "index.md"
FEATURES_SCHEMA = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
GENERATOR = ROOT / "scripts" / "gen_server_docs.py"
PROSE_FILES = ("docs/server/index.md", "README.md", "SKILL.md", "USER.md", "PRODUCT.md")


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def served() -> Surface:
    """The surface the real server serves, read once for this module."""
    return session.read_surface(render.example_request(SOURCE.read_text(encoding="utf-8")))


# 1. The generated files are current.


def test_generated_files_are_current():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# 2 to 6: the real served surface.


def test_generator_calls_only_free_tools(served):
    assert served.called == ["coverage_report", "classify_ai_system"]
    assert list(session.CALLED_TOOLS) == served.called
    by_name = {tool.name: tool for tool in served.tools}
    for name in served.called:
        assert by_name[name].annotations.get("openWorldHint") is False, name


def test_paid_markers_agree(served):
    assert {tool.name for tool in served.tools} == set(TOOL_SCOPES)
    for tool in served.tools:
        open_world = tool.annotations.get("openWorldHint") is True
        says_paid = "PAID" in tool.description
        paid_scope = TOOL_SCOPES[tool.name].endswith("_paid")
        assert open_world == says_paid == paid_scope, tool.name
    assert render.paid_disagreements(served.tools) == []


def test_skill_names_every_tool(served):
    skill = _text("SKILL.md")
    for tool in served.tools:
        assert re.search(rf"\b{re.escape(tool.name)}\b", skill), tool.name


def _keys(value: object) -> set[str]:
    """Every dict key at any depth, lists included."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found |= _keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= _keys(item)
    return found


def _schema_properties(schema: object) -> set[str]:
    """Every property name of a JSON schema, at any depth."""
    found: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            found |= set(properties)
        for item in schema.values():
            found |= _schema_properties(item)
    elif isinstance(schema, list):
        for item in schema:
            found |= _schema_properties(item)
    return found


def test_backticked_names_are_known(served):
    known: set[str] = set()
    for tool in served.tools:
        known.add(tool.name)
        known |= set(tool.input_schema.get("properties", {}))
    known |= set(TOOL_SCOPES.values())
    known |= set(SECTION_8_ENVELOPE_FIELDS)
    known |= set(STATUS_VOCABULARY)
    known |= _schema_properties(json.loads(FEATURES_SCHEMA.read_text(encoding="utf-8")))
    known |= _keys(served.coverage) | _keys(served.classification)
    for relative in ("docs/server/index.md", "SKILL.md"):
        unknown = prose.code_names(_text(relative)) - known
        assert unknown == set(), f"{relative}: {sorted(unknown)}"


def test_no_counts_in_prose(served):
    hits: list[str] = []
    for relative in PROSE_FILES:
        sentences = prose.sentences(prose.prose_of_markdown(_text(relative)))
        hits += [f"{relative}: {s}" for s in prose.count_hits(sentences)]
    for path in sorted((ROOT / "web" / "src").rglob("*.tsx")):
        for run in prose.prose_of_tsx(path.read_text(encoding="utf-8")):
            hits += [
                f"{path.relative_to(ROOT)}: {s}" for s in prose.count_hits(prose.sentences(run))
            ]
    assert hits == []


# 7 to 13: mock surfaces and temporary copies, no server.


def _normalised(text: str) -> str:
    return " ".join(text.split())


def test_notice_is_word_for_word():
    for relative in ("README.md", "docs/server/index.md", "SKILL.md"):
        assert _normalised(NON_LEGAL_ADVICE_NOTICE) in _normalised(_text(relative)), relative


def test_links_follow_the_rule():
    for path in sorted((ROOT / "docs" / "server").glob("*.md")):
        assert prose.link_problems(path.read_text(encoding="utf-8")) == [], path.name
    bad = (
        "<!-- readme: start -->\n# T\n\nSee [the tools](tools.md).\n<!-- readme: end -->\n"
        "\n## After\n\n[tools](tools.md), [x](../thesis/x.md), ![i](i.png), D-G65, B90, sdd/x\n"
    )
    problems = prose.link_problems(bad)
    assert any("README part" in p and "tools.md" in p for p in problems)
    assert any("../thesis/x.md" in p for p in problems)
    assert any("i.png" in p for p in problems)
    for marker in ("D-G65", "B90", "sdd/"):
        assert any(marker in p for p in problems), marker
    good = "<!-- readme: start -->\n# T\n<!-- readme: end -->\n\n[s](sessions/highrisk.html)\n"
    assert prose.link_problems(good) == []


def _tool(name: str, description: str, paid: bool, properties: dict | None = None) -> ServedTool:
    return ServedTool(
        name=name,
        description=description,
        annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": paid},
        input_schema={
            "type": "object",
            "properties": properties or {},
            "required": sorted(properties or {}),
        },
    )


def _mock_surface(build: str = "build-aaaaaaaaaaaa", features: dict | None = None) -> Surface:
    features = features or render.example_request(SOURCE.read_text(encoding="utf-8"))
    envelope_base = {
        "answer": None,
        "status": "not_applicable",
        "confidence": 1.0,
        "source_nodes": [],
        "source_spans": [],
        "graph_evidence_subgraph": {},
        "legal_status_notes": [f"served by {build}"],
        "missing_facts": [],
        "judge_verdict": "not_applicable_deterministic",
        "generated_at": f"2026-10-0{len(build) % 9 + 1}T00:00:00+00:00",
        "graph_version": build,
        "non_legal_advice_notice": NON_LEGAL_ADVICE_NOTICE,
    }
    coverage = dict(envelope_base, answer={"layer2_nodes": {"count": len(build)}})
    classification = dict(
        envelope_base,
        answer={
            "risk_category": "high_risk",
            "unacceptable_risk": None,
            "annex_iii_category": "eu-ai-act:annex-iii:point-5",
            "rationale": [f"rule high_risk: Annex III point 5 (read from {build})"],
            "fria": {"applicability": "unknown", "basis_nodes": ["eu-ai-act:article-27:paragraph-1"]},
        },
        status="requires_human_review",
        confidence=0.5,
        missing_facts=["fact one", "fact two", "fact three"],
        source_nodes=["eu-ai-act:annex-iii:point-5"],
    )
    tools = [
        _tool(name, f"{name.replace('_', ' ').capitalize()} does its work. More text.",
              TOOL_SCOPES[name].endswith("_paid"), {"x": {"type": "string"}})
        for name in sorted(TOOL_SCOPES)
    ]
    tools = [
        ServedTool(t.name, ("PAID: " if t.annotations["openWorldHint"] else "") + t.description,
                   t.annotations, t.input_schema)
        for t in tools
    ]
    return Surface(
        instructions="Mock instructions. " + NON_LEGAL_ADVICE_NOTICE,
        tools=tools,
        coverage=coverage,
        classification=classification,
        request=copy.deepcopy(features),
        called=list(session.CALLED_TOOLS),
    )


def _texts() -> dict[str, str]:
    return {name: _text(name) for name in render.SOURCE_FILES}


def test_renders_nothing_build_specific():
    first = render.render_files(_texts(), _mock_surface("build-aaaaaaaaaaaa+chain-111111111111"))
    second = render.render_files(_texts(), _mock_surface("build-bbbbbbbbbbbbbbbbbb"))
    assert first == second
    for name, text in first.items():
        assert "build-" not in text, name
    example = render.regions(_mock_surface())["example"]
    shown = json.loads(re.search(r"```json\n(.*?)\n```", example, re.DOTALL).group(1))
    assert "graph_version" not in shown
    assert shown["missing_facts"] == ["fact one", "fact two", "..."]


def _copy_tree(tmp_path: Path) -> Path:
    for name in ("README.md", "SKILL.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / "docs" / "server", tmp_path / "docs" / "server")
    return tmp_path


def _write_current(root: Path, surface: Surface) -> None:
    texts = {name: (root / name).read_text(encoding="utf-8") for name in render.SOURCE_FILES}
    for name, text in render.render_files(texts, surface).items():
        (root / name).write_text(text, encoding="utf-8")
    assert render.check(root, surface) == []


def test_check_fails_on_an_edited_region(tmp_path):
    root = _copy_tree(tmp_path)
    surface = _mock_surface()
    _write_current(root, surface)
    source = root / "docs" / "server" / "index.md"
    text = source.read_text(encoding="utf-8")
    region = text.split("<!-- generated: tools -->", 1)[1].split("<!-- end generated: tools -->")[0]
    edited = region.replace("does its work.", "does other work.", 1)
    assert edited != region
    source.write_text(text.replace(region, edited), encoding="utf-8")
    assert render.check(root, surface) == ["docs/server/index.md"]


def test_check_fails_on_a_changed_surface(tmp_path):
    root = _copy_tree(tmp_path)
    surface = _mock_surface()
    _write_current(root, surface)
    changed = copy.deepcopy(surface)
    first = changed.tools[0]
    changed.tools[0] = ServedTool(
        first.name, "A changed first sentence. " + first.description, first.annotations,
        first.input_schema,
    )
    named = render.check(root, changed)
    assert {"docs/server/tools.md", "docs/server/index.md"} <= set(named)


def test_request_comes_from_the_source(tmp_path):
    root = _copy_tree(tmp_path)
    surface = _mock_surface()
    _write_current(root, surface)
    source = root / "docs" / "server" / "index.md"
    old = surface.request["description"]
    new = "A changed description of the example system, long enough to be valid."
    source.write_text(source.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    features = render.example_request(source.read_text(encoding="utf-8"))
    assert features["description"] == new
    assert "docs/server/index.md" in render.check(root, surface)


def test_sessions_page_from_the_real_shape():
    index = {
        "graph_versions": ["build-111111111111"],
        "non_legal_advice_notice": NON_LEGAL_ADVICE_NOTICE,
        "systems": [
            {"key": "minimalrisk", "label": "Minimal risk", "product": "SpamGuard",
             "blurb": "A spam filter.", "classification": {}, "report": "/mcp-demo/minimalrisk.html",
             "session_file": "minimalrisk.jsonl"},
            {"key": "highrisk", "label": "High risk", "product": "CredScore",
             "blurb": "A credit scorer.", "classification": {}, "report": "/mcp-demo/highrisk.html",
             "session_file": "highrisk.jsonl"},
        ],
    }
    sessions = {
        "minimalrisk.jsonl": [
            {"seq": 1, "ts": "2026-10-02T17:48:39+00:00", "tool": "classify_ai_system",
             "envelope": {"graph_version": "build-111111111111"}},
            {"seq": 2, "ts": "2026-10-03T09:00:00+00:00", "tool": "coverage_report",
             "envelope": {"graph_version": "build-222222222222"}},
        ],
        "highrisk.jsonl": [
            {"seq": 1, "ts": "2026-09-30T08:00:00+00:00", "tool": "classify_ai_system",
             "envelope": {"graph_version": "build-333333333333"}},
        ],
    }
    page = render.sessions_page(index, sessions)
    assert "[Minimal risk](sessions/minimalrisk.html)" in page
    assert "[High risk](sessions/highrisk.html)" in page
    assert "build-111111111111" in page and "2026-10-02" in page
    assert "build-333333333333" in page and "2026-09-30" in page
    assert "build-222222222222" not in page and "2026-10-03" not in page
    assert "current" not in page.lower()
    assert prose.link_problems(page) == []

"""Render the generated parts of the public texts from a served surface (DEC-22).

Pure functions from a Surface (session.py) and the files' text to the
generated text: the six regions of docs/server/index.md, the tool reference
docs/server/tools.md, the README part copied into README.md, the reading
part copied into SKILL.md, and the recorded sessions page. Nothing that
depends on which build is served is written: no graph_version, no count
from coverage_report, no time, and a build id inside a served sentence is
replaced by "<build id>". read_sessions and check are the only functions
that read files; nothing here writes one.

@implements: DEC-22
@grounded_by: REF-31
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tere4ai.mcp_server.keys import TOOL_SCOPES
from tere4ai.mcp_server.tools import SECTION_8_ENVELOPE_FIELDS, STATUS_VOCABULARY
from tere4ai.server_docs.session import ServedTool, Surface

SOURCE = "docs/server/index.md"
TOOLS_PAGE = "docs/server/tools.md"
SESSIONS_PAGE = "docs/server/sessions.md"
README = "README.md"
SKILL = "SKILL.md"
SOURCE_FILES = (SOURCE, README, SKILL)
SESSIONS_INDEX = "web/public/mcp-demo/index.json"
SESSIONS_DIR = "demo/mcp_demo/sessions"

REGION_NAMES = ("notice", "example", "tools", "fields", "statuses", "instructions")
EDIT_NOTE = "<!-- edit docs/server/index.md, then run scripts/gen_server_docs.py -->"
COPY_START = "<!-- generated from docs/server/index.md: start -->"
COPY_END = "<!-- generated from docs/server/index.md: end -->"
FEATURES_SCHEMA_URL = (
    "https://github.com/josesiqueira/tere4ai/blob/main/"
    "schema/json_schemas/system_features.schema.json"
)

_REQUEST_BLOCK = re.compile(
    r"<!-- example request: start -->\s*```json\n(.*?)\n```\s*<!-- example request: end -->",
    re.DOTALL,
)
_BUILD_ID = re.compile(r"\bbuild-[0-9a-f]+(?:\+chain-[0-9a-f]+)?")
_SENTENCE_END = re.compile(r"\.(?:\s|$)")


def _part(source: str, name: str) -> str:
    """The text between the marker lines <!-- name: start --> and
    <!-- name: end -->, byte for byte."""
    start, end = f"<!-- {name}: start -->\n", f"<!-- {name}: end -->"
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"the source must hold one {name} part")
    return source.split(start, 1)[1].split(end, 1)[0]


def readme_part(source: str) -> str:
    """The README part of the source."""
    return _part(source, "readme")


def reading_part(source: str) -> str:
    """The part on reading every answer, copied into SKILL.md."""
    return _part(source, "reading")


def example_request(source: str) -> dict[str, Any]:
    """The features of the source's example request block: what the
    generator sends to classify_ai_system, so the page shows the call made."""
    match = _REQUEST_BLOCK.search(source)
    if match is None:
        raise ValueError("the source holds no example request block")
    request = json.loads(match.group(1))
    return request["features"]


def _scrub(text: str) -> str:
    return _BUILD_ID.sub("<build id>", text)


def first_sentence(description: str) -> str:
    """The first paragraph with whitespace collapsed, up to the first period
    followed by a space, or the whole paragraph."""
    paragraph = " ".join(description.strip().split("\n\n", 1)[0].split())
    match = _SENTENCE_END.search(paragraph)
    return paragraph[: match.start() + 1] if match else paragraph


def is_paid(tool: ServedTool) -> bool:
    """Free or paid is the served openWorldHint."""
    return tool.annotations.get("openWorldHint") is True


def paid_disagreements(tools: Iterable[ServedTool]) -> list[str]:
    """The tools whose openWorldHint, the word PAID in their description and
    a _paid scope in TOOL_SCOPES do not agree."""
    found = []
    for tool in tools:
        scope = TOOL_SCOPES.get(tool.name, "")
        marks = (is_paid(tool), "PAID" in tool.description, scope.endswith("_paid"))
        if len(set(marks)) != 1:
            found.append(
                f"{tool.name}: openWorldHint {marks[0]}, PAID in description {marks[1]}, "
                f"scope {scope or 'none'}"
            )
    return found


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _example_region(envelope: dict[str, Any]) -> str:
    answer = envelope.get("answer") or {}
    fria = answer.get("fria") or {}
    missing = list(envelope.get("missing_facts") or [])
    shown = {
        "answer": {
            "risk_category": answer.get("risk_category"),
            "unacceptable_risk": answer.get("unacceptable_risk"),
            "annex_iii_category": answer.get("annex_iii_category"),
            "rationale": answer.get("rationale", []),
            "fria": {
                "applicability": fria.get("applicability"),
                "basis_nodes": fria.get("basis_nodes", []),
            },
        },
        "status": envelope.get("status"),
        "confidence": envelope.get("confidence"),
        "judge_verdict": envelope.get("judge_verdict"),
        "missing_facts": missing[:2] + (["..."] if len(missing) > 2 else []),
        "source_nodes": envelope.get("source_nodes", []),
    }
    return "```json\n" + _scrub(json.dumps(shown, indent=2, ensure_ascii=False)) + "\n```"


def _tools_region(tools: list[ServedTool]) -> str:
    rows = ["| Tool | What it does | Cost |", "|---|---|---|"]
    for tool in tools:
        cost = "paid" if is_paid(tool) else "free"
        rows.append(f"| `{tool.name}` | {_cell(_scrub(first_sentence(tool.description)))} | {cost} |")
    paid = sum(1 for tool in tools if is_paid(tool))
    total = len(tools)
    rows.append("")
    rows.append(f"{total} tools: {total - paid} free and {paid} paid.")
    return "\n".join(rows)


def _fields_region(envelope: dict[str, Any]) -> str:
    fields = set(envelope)
    if fields != SECTION_8_ENVELOPE_FIELDS:
        raise ValueError(
            "the coverage_report answer's fields differ from SECTION_8_ENVELOPE_FIELDS: "
            f"{sorted(fields ^ SECTION_8_ENVELOPE_FIELDS)}"
        )
    return ", ".join(f"`{name}`" for name in sorted(fields)) + "."


def _statuses_region() -> str:
    return ", ".join(f"`{status}`" for status in STATUS_VOCABULARY) + "."


def regions(surface: Surface) -> dict[str, str]:
    """The content of each generated region of the source."""
    return {
        "notice": _scrub(str(surface.coverage["non_legal_advice_notice"])),
        "example": _example_region(surface.classification),
        "tools": _tools_region(surface.tools),
        "fields": _fields_region(surface.coverage),
        "statuses": _statuses_region(),
        "instructions": "```text\n" + _scrub(surface.instructions) + "\n```",
    }


def fill_regions(source: str, surface: Surface) -> str:
    """The source with every generated region rewritten from the surface."""
    for name, content in regions(surface).items():
        pattern = re.compile(
            rf"(<!-- generated: {name} -->\n).*?(<!-- end generated: {name} -->)", re.DOTALL
        )
        if len(pattern.findall(source)) != 1:
            raise ValueError(f"the source must hold one region {name}")
        source = pattern.sub(lambda m, c=content: m.group(1) + c + "\n" + m.group(2), source)
    return source


def _type(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        return " or ".join(_type(option) for option in schema["anyOf"])
    kind = schema.get("type", "any")
    if isinstance(kind, list):
        return " or ".join(kind)
    items = schema.get("items")
    if kind == "array" and isinstance(items, dict):
        return f"array of {_type(items)}"
    return str(kind)


def _inputs(tool: ServedTool) -> list[str]:
    properties = tool.input_schema.get("properties") or {}
    if not properties:
        return ["No input."]
    required = set(tool.input_schema.get("required") or [])
    rows = ["| Input | Type | Required |", "|---|---|---|"]
    for name in sorted(properties):
        label = f"`{name}`"
        if tool.name == "classify_ai_system" and name == "features":
            label = f"[`{name}`]({FEATURES_SCHEMA_URL})"
        rows.append(f"| {label} | {_type(properties[name])} | {'yes' if name in required else 'no'} |")
    return rows


def tools_page(tools: list[ServedTool]) -> str:
    """docs/server/tools.md: per tool, free or paid, its annotations, its
    whole served description and its input fields."""
    lines = [
        "# Tool reference",
        "",
        "Every tool the MCP server serves, in the order its tool list gives",
        "them: free or paid, its annotations, its whole description as a client",
        "receives it, and its input fields. This page is generated from the",
        "running server by scripts/gen_server_docs.py; the descriptions are",
        "written in src/tere4ai/mcp_server/server.py.",
    ]
    for tool in tools:
        annotations = ", ".join(
            f"{key} {json.dumps(value)}" for key, value in sorted(tool.annotations.items())
        )
        lines += [
            "",
            f"## `{tool.name}`",
            "",
            f"{'Paid' if is_paid(tool) else 'Free'}. Annotations: {annotations or 'none'}.",
            "",
            "```text",
            _scrub(tool.description.strip()),
            "```",
            "",
            *_inputs(tool),
        ]
    return "\n".join(lines) + "\n"


def sessions_page(index: dict[str, Any], sessions: dict[str, list[dict[str, Any]]]) -> str:
    """docs/server/sessions.md: each recorded session with its label, the
    build it was recorded on and the day it was recorded, both read from
    the first line of its session file."""
    lines = [
        "# Recorded sessions",
        "",
        "Each page is one session recorded with the MCP server, the answers",
        "exactly as the server returned them on the day of the recording. A",
        "session shows the build it was recorded on, which may differ from the",
        "build a server serves today.",
        "",
        "| Session | System | Build | Recorded |",
        "|---|---|---|---|",
    ]
    for system in index.get("systems", []):
        first = (sessions.get(system["session_file"]) or [{}])[0]
        build = (first.get("envelope") or {}).get("graph_version", "unknown")
        day = str(first.get("ts", "unknown"))[:10]
        lines.append(
            f"| [{_cell(system['label'])}](sessions/{system['key']}.html) | "
            f"{_cell(system.get('product') or '')} | `{build}` | {day} |"
        )
    return "\n".join(lines) + "\n"


def splice(target: str, part: str, name: str) -> str:
    """target with the text between its copy markers replaced by part."""
    if target.count(COPY_START) != 1 or target.count(COPY_END) != 1:
        raise ValueError(f"{name} must hold the markers {COPY_START} and {COPY_END} once")
    head, rest = target.split(COPY_START, 1)
    tail = rest.split(COPY_END, 1)[1]
    return head + COPY_START + "\n" + part + COPY_END + tail


def render_files(
    texts: dict[str, str],
    surface: Surface,
    sessions: tuple[dict[str, Any], dict[str, list[dict[str, Any]]]] | None = None,
) -> dict[str, str]:
    """The generated text of every file, from the current text of the source,
    README.md and SKILL.md and the served surface; sessions.md too when the
    sessions' index and files are given. Refuses a surface whose paid
    markers disagree."""
    problems = paid_disagreements(surface.tools)
    if problems:
        raise ValueError("free or paid disagrees: " + "; ".join(problems))
    source = fill_regions(texts[SOURCE], surface)
    out = {
        SOURCE: source,
        TOOLS_PAGE: tools_page(surface.tools),
        README: splice(texts[README], readme_part(source), README),
        SKILL: splice(texts[SKILL], reading_part(source), SKILL),
    }
    if sessions is not None:
        out[SESSIONS_PAGE] = sessions_page(*sessions)
    return out


def read_sessions(root: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """The recorded sessions' index and the lines of each session file."""
    index = json.loads((root / SESSIONS_INDEX).read_text(encoding="utf-8"))
    sessions = {}
    for system in index.get("systems", []):
        path = root / SESSIONS_DIR / system["session_file"]
        sessions[system["session_file"]] = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        ]
    return index, sessions


def check(root: Path, surface: Surface) -> list[str]:
    """The files under root that the generator would change: the source
    (also when its example request is not the one the surface answered),
    tools.md, README.md, SKILL.md, and sessions.md whenever it exists."""
    texts = {name: (root / name).read_text(encoding="utf-8") for name in SOURCE_FILES}
    sessions = read_sessions(root) if (root / SESSIONS_PAGE).is_file() else None
    changed = []
    for name, text in render_files(texts, surface, sessions).items():
        path = root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            changed.append(name)
    if example_request(texts[SOURCE]) != surface.request and SOURCE not in changed:
        changed.append(SOURCE)
    return sorted(changed)

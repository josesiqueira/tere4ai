"""The stored inputs carry a `domain` of the schema or none (B185, DEC-33).

Spec G D-G92 (11): the stored inputs of the demo sessions, the presets and
the answer key are converted to the nine values (ruling P19 of the plan: a
word that named Annex III point 5 becomes essential_services only where the
description states a listed use of point 5, any other word becomes the value
of the area whose listed use the description states, and the field is left
out otherwise; no conversion writes none_of_these_areas). This test reads
every `domain` given in a request of the sessions under
tests/fixtures/demo_sessions and demo/mcp_demo/sessions, in the answer key
eval/gold/gold_seed.json, and in the systems of the recording scripts under
scripts/ (read from their source, so no script runs and no server starts),
and fails on a value outside the schema's enum. Records are not read:
tests/fixtures/legacy holds sessions of their day, and
eval/gold/benchmark_features.json and benchmark_features_full.json stay
records of tag v2.0.0-beta.1 (ruling P21, B184 ruling R16). The demo site's
presets are checked by tests/unit/test_web_copy_honesty.py (Task 10).

@implements: DEC-33
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
SESSION_DIRS = (ROOT / "tests" / "fixtures" / "demo_sessions", ROOT / "demo" / "mcp_demo" / "sessions")
GOLD_SEED = ROOT / "eval" / "gold" / "gold_seed.json"
SCRIPTS = ROOT / "scripts"
# The recording scripts whose systems carry a domain (B185 Task 1 converted
# them); the scan below also reads every other script.
RECORDING_SCRIPTS = ("record_mcp_demo.py", "make_compliance.py", "make_prohibition.py")


def _domains_in(value: Any, where: str) -> list[tuple[str, Any]]:
    """Every value of a key "domain" inside a JSON value, with where it is."""
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == "domain":
                found.append((where, inner))
            found.extend(_domains_in(inner, f"{where}/{key}"))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found.extend(_domains_in(inner, f"{where}[{index}]"))
    return found


def _session_domains() -> dict[str, list[tuple[str, Any]]]:
    """The domains given in the requests of each session file (never the
    envelopes, whose area_conflicts entries also carry a key "domain")."""
    found: dict[str, list[tuple[str, Any]]] = {}
    for directory in SESSION_DIRS:
        for session in sorted(directory.glob("*.jsonl")):
            name = str(session.relative_to(ROOT))
            found[name] = []
            for number, raw in enumerate(session.read_text(encoding="utf-8").splitlines(), start=1):
                if raw.strip():
                    line = json.loads(raw)
                    found[name].extend(_domains_in(line.get("request"), f"line {number} request"))
    return found


def _script_domains() -> dict[str, list[tuple[str, Any]]]:
    """The domains written as a dict entry "domain": <value> in each script,
    read from the source; a value that is not a literal is reported as such,
    so the scan cannot be passed by building the word at run time."""
    found: dict[str, list[tuple[str, Any]]] = {}
    for script in sorted(SCRIPTS.glob("*.py")):
        name = str(script.relative_to(ROOT))
        found[name] = []
        for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "domain":
                    literal = value.value if isinstance(value, ast.Constant) else f"<not a literal: {ast.unparse(value)}>"
                    found[name].append((f"line {value.lineno}", literal))
    return found


def test_presets_and_session_requests_use_values_of_the_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    values = set(schema["properties"]["domain"]["enum"])
    gold = json.loads(GOLD_SEED.read_text(encoding="utf-8"))
    sources = {
        **_session_domains(),
        str(GOLD_SEED.relative_to(ROOT)): _domains_in(gold, ""),
        **_script_domains(),
    }
    # The scan reads what it should: each session directory has sessions and
    # each recording script and the answer key carry at least one domain.
    for directory in SESSION_DIRS:
        assert any(name.startswith(str(directory.relative_to(ROOT))) for name in sources), directory
    for script in RECORDING_SCRIPTS:
        assert sources[f"scripts/{script}"], script
    assert sources[str(GOLD_SEED.relative_to(ROOT))]
    outside = [(name, where, value) for name, found in sources.items() for where, value in found
               if not (isinstance(value, str) or value is None) or value not in values]
    assert outside == []

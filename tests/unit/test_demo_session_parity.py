"""Replay honesty: a recorded session replays to the same envelopes.

Spec deviation, recorded deliberately: the spec says byte-equal, but
every envelope carries a fresh generated_at timestamp, so equality is
asserted on the full envelope with generated_at masked on both sides.
Everything else must match exactly, or replay would be showing the
audience something the live system did not say.

Note: classify_ai_system here takes (features, dump), not (features)
alone, matching the module-level signature in tere4ai.mcp_server.classify
(the MCP tool wrapper in tere4ai.mcp_server.server loads the dump
internally); this test loads the same on-disk dump the live server uses.
"""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.requirements import get_applicable_requirements

SESSIONS_DIR = Path(__file__).parent.parent / "fixtures" / "demo_sessions"
FIXTURE = SESSIONS_DIR / "spamguard-classify.jsonl"
ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

pytestmark = pytest.mark.skipif(
    not DUMP_PATH.is_file(), reason="layer1.json dump not built"
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


def _mask(envelope):
    masked = dict(envelope)
    masked["generated_at"] = "MASKED"
    return masked


def test_recorded_spamguard_session_replays_identically(dump):
    lines = [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]
    assert lines, "fixture must not be empty"
    for line in lines:
        assert set(line.keys()) == {"seq", "ts", "tool", "request", "envelope", "repo_ref"}
        if line["tool"] != "classify_ai_system":
            continue
        live = classify_ai_system(line["request"]["features"], dump)
        assert _mask(live) == _mask(line["envelope"])


@pytest.mark.skipif(not NORMS_PATH.is_file(), reason="norms_core.json dump not built")
@pytest.mark.parametrize(
    "session_path",
    sorted(SESSIONS_DIR.glob("*.jsonl")),
    ids=lambda p: p.name,
)
def test_every_recorded_session_replays_identically(session_path, dump, norms):
    """Replay honesty for every session the /agent page can serve, not just
    the first one recorded. The page claims the envelopes it shows are what
    the live system produced; a fixture that has drifted from current
    behaviour would put words in the system's mouth in front of an audience.

    Both free tools are replayed. Anything else recorded in future would be
    skipped here, so the tool coverage below is asserted rather than assumed.
    """
    lines = [
        json.loads(line)
        for line in session_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, f"{session_path.name} must not be empty"

    replayed = 0
    for line in lines:
        assert set(line.keys()) == {"seq", "ts", "tool", "request", "envelope", "repo_ref"}
        tool = line["tool"]
        if tool == "classify_ai_system":
            live = classify_ai_system(line["request"]["features"], dump)
        elif tool == "get_applicable_requirements":
            classification = line["request"]["classification"]
            live = get_applicable_requirements(classification, norms, dump)
        else:
            pytest.fail(
                f"{session_path.name} records tool {tool!r}, which this replay "
                "guard does not cover; extend the guard rather than shipping an "
                "unverified recording to the demo page"
            )
        assert _mask(live) == _mask(line["envelope"]), (
            f"{session_path.name} seq {line['seq']} ({tool}) no longer replays to "
            "the recorded envelope; re-record it or fix the drift"
        )
        replayed += 1

    assert replayed == len(lines)

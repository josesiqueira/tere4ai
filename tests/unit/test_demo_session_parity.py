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

FIXTURE = Path(__file__).parent.parent / "fixtures" / "demo_sessions" / "spamguard-classify.jsonl"
ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(
    not DUMP_PATH.is_file(), reason="layer1.json dump not built"
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _mask(envelope):
    masked = dict(envelope)
    masked["generated_at"] = "MASKED"
    return masked


def test_recorded_spamguard_session_replays_identically(dump):
    lines = [json.loads(l) for l in FIXTURE.read_text().splitlines() if l.strip()]
    assert lines, "fixture must not be empty"
    for line in lines:
        assert set(line.keys()) == {"seq", "ts", "tool", "request", "envelope", "repo_ref"}
        if line["tool"] != "classify_ai_system":
            continue
        live = classify_ai_system(line["request"]["features"], dump)
        assert _mask(live) == _mask(line["envelope"])

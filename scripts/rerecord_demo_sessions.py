"""Re-record the demo sessions on the published dumps (B132).

tests/unit/test_demo_session_parity.py replays every session under
tests/fixtures/demo_sessions and compares each recorded envelope with the
tool's answer today, generated_at masked. When a change alters what
classify_ai_system or get_applicable_requirements returns, this script
writes each session's envelopes again from data/graph_dumps (layer1.json
and norms_core.json), keeping each request, except that a requirements
request takes the classification just recorded before it in the session
(B184 ruling P20). Deterministic and free: the two
tools call no model. Run from the repository root:

    .venv/bin/python scripts/rerecord_demo_sessions.py

B184 (DEC-32): the requests of the sessions under tests/fixtures/demo_sessions
were first translated into the facts of DEC-32 by the plan's rule for recorded
systems (a one-off step, not this script), then their envelopes were recorded
again with this script.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.elicit_features.elicitor import features_of_record
from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.requirements import get_applicable_requirements

ROOT = Path(__file__).resolve().parents[1]


def envelope_of(line: dict, dump: dict, norms: dict) -> dict:
    """The envelope the tool answers today for one recorded line. A recorded
    request keeps its facts as recorded; classify reads them through
    features_of_record, since a session recorded before B160 names the
    deployer's legal form by its old key (B160 ruling R6)."""
    if line["tool"] == "classify_ai_system":
        return classify_ai_system(features_of_record(line["request"]["features"]), dump)
    return get_applicable_requirements(line["request"]["classification"], norms, dump)


def rerecord_session(lines: list[dict], dump: dict, norms: dict) -> list[dict]:
    """Record each line of one session again, in order (B184 ruling P20).

    The envelope just recorded for a classify_ai_system line is written into
    the classification of every later get_applicable_requirements line of
    the same session before that line is recorded, since a requirements
    request holds the classification it was made from. Each request is kept
    otherwise. The lines are changed in place and returned."""
    classification = None
    for line in lines:
        if line["tool"] == "get_applicable_requirements" and classification is not None:
            line["request"]["classification"] = classification
        line["envelope"] = envelope_of(line, dump, norms)
        if line["tool"] == "classify_ai_system":
            classification = line["envelope"]
    return lines


def main() -> int:
    dumps = ROOT / "data" / "graph_dumps"
    dump = json.loads((dumps / "layer1.json").read_text(encoding="utf-8"))
    norms = json.loads((dumps / "norms_core.json").read_text(encoding="utf-8"))
    for session in sorted((ROOT / "tests" / "fixtures" / "demo_sessions").glob("*.jsonl")):
        recorded = [
            json.loads(raw) for raw in session.read_text(encoding="utf-8").splitlines() if raw.strip()
        ]
        lines = [
            json.dumps(line, ensure_ascii=False, sort_keys=True)
            for line in rerecord_session(recorded, dump, norms)
        ]
        session.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"re-recorded {session.name}: {len(lines)} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

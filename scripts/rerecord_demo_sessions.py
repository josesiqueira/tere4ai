"""Re-record the demo sessions on the published dumps (B132).

tests/unit/test_demo_session_parity.py replays every session under
tests/fixtures/demo_sessions and compares each recorded envelope with the
tool's answer today, generated_at masked. When a change alters what
classify_ai_system or get_applicable_requirements returns, this script
writes each session's envelopes again from data/graph_dumps (layer1.json
and norms_core.json), keeping each request. Deterministic and free: the two
tools call no model. Run from the repository root:

    .venv/bin/python scripts/rerecord_demo_sessions.py
"""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.requirements import get_applicable_requirements

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dumps = ROOT / "data" / "graph_dumps"
    dump = json.loads((dumps / "layer1.json").read_text(encoding="utf-8"))
    norms = json.loads((dumps / "norms_core.json").read_text(encoding="utf-8"))
    for session in sorted((ROOT / "tests" / "fixtures" / "demo_sessions").glob("*.jsonl")):
        lines = []
        for raw in session.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            line = json.loads(raw)
            if line["tool"] == "classify_ai_system":
                line["envelope"] = classify_ai_system(line["request"]["features"], dump)
            else:
                line["envelope"] = get_applicable_requirements(line["request"]["classification"], norms, dump)
            lines.append(json.dumps(line, ensure_ascii=False, sort_keys=True))
        session.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"re-recorded {session.name}: {len(lines)} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

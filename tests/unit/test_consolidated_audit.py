"""B138 fix wave W6 (final review F6, spec G D-G74 (9)): the consolidated
audit leaves the demo judge's lines (judge_setting "demo", DEC-24) out of
its verdict and model counts and counts them apart, labelled. Mock data, no
log file read."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("consolidated_audit", ROOT / "scripts" / "consolidated_audit.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

EVENTS = [
    {"timestamp": "2026-10-07T10:00:00Z", "log_kind": "runtime_grounding", "direction": "judge", "verdict": "accepted",
     "model": "claude-opus-5-5", "prompt_version": "v2"},
    {"timestamp": "2026-10-07T10:01:00Z", "log_kind": "runtime_grounding", "direction": "judge", "verdict": "accepted",
     "model": "gpt-6-sol", "prompt_version": "v2", "judge_setting": "demo"},
]


def test_demo_judge_lines_are_left_out_of_the_counts_and_counted_apart(monkeypatch, capsys):
    monkeypatch.setattr(audit, "consolidate", lambda: list(EVENTS))
    assert audit.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "  runtime_grounding verdict=accepted: 1" in out
    assert "  model=gpt-6-sol prompt=v2: 1" not in out and "  model=claude-opus-5-5 prompt=v2: 1" in out
    assert "events: 1" in out
    assert "demo judge lines (judge_setting demo, DEC-24), left out of the counts above: 1" in out
    assert "  demo runtime_grounding verdict=accepted: 1" in out

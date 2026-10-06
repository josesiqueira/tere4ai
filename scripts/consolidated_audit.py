"""Consolidated judge-decision audit view over the three logs (#39).

@implements: DEC-24
@grounded_by: REF-24

Merges extraction, alignment, and runtime grounding logs (timestamp order,
tagged with log_kind) and prints per-kind verdict/model/prompt-version
counts; --jsonl streams the merged events for downstream analysis. Section
13: the logs are body-free of secrets by construction (audit_log.scrub).
The demo judge's lines (judge_setting "demo", DEC-24, spec G D-G74 (9)) are
left out of the counts and counted apart, labelled (B138 fix wave W6).

Usage:
  .venv/bin/python scripts/consolidated_audit.py [--jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.judge.audit_log import DEFAULT_LOGS, consolidate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jsonl", action="store_true", help="stream merged events")
    args = parser.parse_args(argv)

    events = consolidate()
    if args.jsonl:
        for event in events:
            print(json.dumps(event, ensure_ascii=False))
        return 0

    demo = [e for e in events if e.get("judge_setting") == DEMO_SETTING]
    events = [e for e in events if e.get("judge_setting") != DEMO_SETTING]
    print(f"logs: {', '.join(str(p) for p in DEFAULT_LOGS.values())}")
    print(f"events: {len(events)}")
    by_kind = Counter(e.get("log_kind") for e in events)
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")
    for (kind, verdict), count in _verdicts(events):
        print(f"  {kind} verdict={verdict}: {count}")
    models = Counter(
        (e.get("model"), e.get("prompt_version")) for e in events if e.get("model")
    )
    for (model, version), count in sorted(models.items()):
        print(f"  model={model} prompt={version}: {count}")
    print(f"demo judge lines (judge_setting demo, DEC-24), left out of the counts above: {len(demo)}")
    for (kind, verdict), count in _verdicts(demo):
        print(f"  demo {kind} verdict={verdict}: {count}")
    return 0


DEMO_SETTING = "demo"


def _verdicts(events: list[dict]) -> list[tuple[tuple[str | None, str | None], int]]:
    counts = Counter(
        (e.get("log_kind"), e.get("verdict"))
        for e in events
        if e.get("direction") == "judge" or e.get("verdict")
    )
    return sorted(counts.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))


if __name__ == "__main__":
    sys.exit(main())

"""Consolidated judge-decision audit view over the three logs (#39).

@grounded_by: REF-24

Merges extraction, alignment, and runtime grounding logs (timestamp order,
tagged with log_kind) and prints per-kind verdict/model/prompt-version
counts; --jsonl streams the merged events for downstream analysis. Section
13: the logs are body-free of secrets by construction (audit_log.scrub).

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

    print(f"logs: {', '.join(str(p) for p in DEFAULT_LOGS.values())}")
    print(f"events: {len(events)}")
    by_kind = Counter(e.get("log_kind") for e in events)
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")
    verdicts = Counter(
        (e.get("log_kind"), e.get("verdict"))
        for e in events
        if e.get("direction") == "judge" or e.get("verdict")
    )
    for (kind, verdict), count in sorted(verdicts.items()):
        print(f"  {kind} verdict={verdict}: {count}")
    models = Counter(
        (e.get("model"), e.get("prompt_version")) for e in events if e.get("model")
    )
    for (model, version), count in sorted(models.items()):
        print(f"  model={model} prompt={version}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

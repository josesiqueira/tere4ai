"""Adjudicate the human review queue (norms, alignments, cross-references).

@implements: DEC-06 (partial: human review loop)
@grounded_by: REF-24, REF-32

Pure-argv CLI, no interactive prompts (agent friendly). Decisions never touch
the pipeline dumps: they accumulate in data/review_queue/decisions.json and
are applied at publish time by scripts/publish_layer23.py.

Usage:
  .venv/bin/python scripts/review_cli.py list [--kind norm|alignment|crossref]
  .venv/bin/python scripts/review_cli.py show <queue_id>
  .venv/bin/python scripts/review_cli.py decide <queue_id> accept|reject \
      --rationale "why" --reviewer name
  .venv/bin/python scripts/review_cli.py stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.review_queue import (  # noqa: E402
    list_pending,
    load_decisions,
    record_decision,
    save_decisions,
)

NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = ROOT / "data" / "graph_dumps" / "alignments_core.json"
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
DECISIONS_PATH = ROOT / "data" / "review_queue" / "decisions.json"


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_queue(decisions: dict | None = None) -> list[dict]:
    return list_pending(
        norms_payload=_load_json(NORMS_PATH),
        alignments_payload=_load_json(ALIGNMENTS_PATH),
        layer1_dump=_load_json(LAYER1_PATH),
        decisions=decisions,
    )


def cmd_list(args: argparse.Namespace) -> int:
    decisions = load_decisions(args.decisions)
    pending = _load_queue(decisions)
    if args.kind:
        pending = [it for it in pending if it["kind"] == args.kind]
    for it in pending:
        print(f"{it['queue_id']}  [{it['kind']}]  {it['digest']}")
    by_kind: dict[str, int] = {}
    for it in pending:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    kinds = ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())) or "none"
    print(f"pending: {len(pending)} ({kinds}); decided so far: {len(decisions)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    decisions = load_decisions(args.decisions)
    all_items = _load_queue()
    match = next((it for it in all_items if it["queue_id"] == args.queue_id), None)
    if match is None:
        print(f"queue_id not found in the pending pools: {args.queue_id}", file=sys.stderr)
        return 1
    print(f"queue_id: {match['queue_id']}")
    print(f"kind:     {match['kind']}")
    print(f"digest:   {match['digest']}")
    print(f"source text: {match['source_excerpt'] or '(no source text found in the dump)'}")
    print(f"judge rationale: {match['judge_rationale'] or '(none recorded)'}")
    print("candidate record:")
    print(json.dumps(match["item"], indent=2, ensure_ascii=False))
    prior = decisions.get(args.queue_id)
    if prior:
        print(f"already decided: {json.dumps(prior, ensure_ascii=False)}")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    all_items = _load_queue()
    known_ids = {it["queue_id"] for it in all_items}
    if args.queue_id not in known_ids:
        print(f"queue_id not found in the pending pools: {args.queue_id}", file=sys.stderr)
        return 1
    decisions = load_decisions(args.decisions)
    try:
        entry = record_decision(
            decisions,
            queue_id=args.queue_id,
            decision=args.decision,
            rationale=args.rationale,
            reviewer=args.reviewer,
        )
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    save_decisions(decisions, args.decisions)
    print(
        f"recorded {entry['decision']} for {args.queue_id} "
        f"by {entry['reviewer']} at {entry['decided_at']}"
    )
    print(f"decisions file: {args.decisions} ({len(decisions)} total)")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    decisions = load_decisions(args.decisions)
    full = _load_queue()
    pending = _load_queue(decisions)
    total_by_kind: dict[str, int] = {}
    pending_by_kind: dict[str, int] = {}
    for it in full:
        total_by_kind[it["kind"]] = total_by_kind.get(it["kind"], 0) + 1
    for it in pending:
        pending_by_kind[it["kind"]] = pending_by_kind.get(it["kind"], 0) + 1
    accepted = sum(1 for d in decisions.values() if d.get("decision") == "accept")
    rejected = sum(1 for d in decisions.values() if d.get("decision") == "reject")
    print("review queue stats")
    for kind in sorted(total_by_kind):
        total = total_by_kind[kind]
        left = pending_by_kind.get(kind, 0)
        print(f"  {kind}: {total} queued, {total - left} decided, {left} pending")
    print(f"  decisions: {len(decisions)} total ({accepted} accept, {rejected} reject)")
    print(f"  decisions file: {args.decisions}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--decisions", type=Path, default=DECISIONS_PATH, help="decisions file path"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="pending queue items with digests")
    p_list.add_argument("--kind", choices=["norm", "alignment", "crossref"], default=None)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="full item: source text, candidate, judge rationale")
    p_show.add_argument("queue_id")
    p_show.set_defaults(func=cmd_show)

    p_decide = sub.add_parser("decide", help="record an accept or reject decision")
    p_decide.add_argument("queue_id")
    p_decide.add_argument("decision", choices=["accept", "reject"])
    p_decide.add_argument("--rationale", required=True, help="why (required, non-empty)")
    p_decide.add_argument("--reviewer", required=True, help="who decided")
    p_decide.set_defaults(func=cmd_decide)

    p_stats = sub.add_parser("stats", help="queue and decision counts")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

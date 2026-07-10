"""Shared audit log for every judge decision (Section 13 observability).

@implements: DEC-06 (partial: consolidated judge-decision audit trail)
@grounded_by: REF-16, REF-24

One module owns the append path for the three judge logs (extraction,
alignment, runtime grounding) so the envelope and the redaction rule cannot
drift between pipelines. Events are JSON lines; the writer scrubs anything
that looks like key material (OpenAI/Anthropic-style sk- tokens, TERE4AI
t4a_ keys, bearer headers) before the line is written, because rationale
and input text are model-visible strings that could echo a secret.

read_events / consolidate provide the merged audit view over the three
default logs for scripts/consolidated_audit.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = REPO_ROOT / "data" / "review_queue"
DEFAULT_LOGS: dict[str, Path] = {
    "extraction": LOG_DIR / "extraction_log.jsonl",
    "alignment": LOG_DIR / "alignment_log.jsonl",
    "runtime_grounding": LOG_DIR / "runtime_log.jsonl",
}

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}"
    r"|t4a_[0-9a-f]{6,}_[A-Za-z0-9_-]{8,}"
    r"|Bearer\s+[A-Za-z0-9._~+/-]{16,})"
)
REDACTED = "[REDACTED]"


def scrub(value: Any) -> Any:
    """Replace key-material-shaped substrings anywhere in the event."""
    if isinstance(value, str):
        return _SECRET_RE.sub(REDACTED, value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def append_event(log_path: Path, event: dict[str, Any]) -> None:
    """Append one scrubbed JSON line. Never raises key material into a log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(scrub(event), ensure_ascii=False) + "\n")


def read_events(log_path: Path, kind: str | None = None) -> Iterator[dict[str, Any]]:
    if not log_path.is_file():
        return
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if kind is not None:
                event.setdefault("log_kind", kind)
            yield event


def consolidate(logs: dict[str, Path] | None = None) -> list[dict[str, Any]]:
    """All events from every log, tagged with log_kind, timestamp-sorted."""
    logs = logs or DEFAULT_LOGS
    events: list[dict[str, Any]] = []
    for kind, path in logs.items():
        events.extend(read_events(path, kind=kind))
    return sorted(events, key=lambda e: str(e.get("timestamp", "")))

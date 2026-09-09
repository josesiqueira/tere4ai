"""Record keeping.

Events are appended to a durable, timestamped log that survives restart, and
each entry carries the period of use, the input data the score was computed
from, and the natural person who verified the result.

@implements: norm:eu-ai-act:article-12:paragraph-1:n1
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class AuditLog:
    path: Path = field(default_factory=lambda: Path("var/credscore-events.jsonl"))
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event_type: str, payload: dict[str, Any]) -> None:
        """Append one event, in memory and on disk.

        The on-disk copy is what makes the record survive the process. The
        entry carries the start of the period of use and the input data of the
        scored application alongside the event itself.

        @implements: norm:eu-ai-act:article-12:paragraph-3:n1
        @implements: norm:eu-ai-act:article-12:paragraph-3:n3
        """
        entry = {
            "type": event_type,
            "recorded_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        self.events.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def record_verifier(self, applicant_id: str, officer_id: str) -> None:
        """Log which natural person checked the result of the scoring run.

        @implements: norm:eu-ai-act:article-12:paragraph-3:n4
        """
        self.record(
            "human_verification",
            {"applicant_id": applicant_id, "verified_by": officer_id},
        )

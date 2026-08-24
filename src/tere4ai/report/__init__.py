"""Client-side report renderer: recorded MCP envelopes to one HTML file.

@implements: DEC-08, DEC-15
@grounded_by: ADD-14, ADD-15

Renders an audit-grade EU AI Act engineering requirements report from a
recorded MCP session (JSONL of request/envelope exchanges) plus optional
loose Section 8 envelopes. Runs CLIENT-SIDE, like tere4ai.trace_scan: it is
stdlib-only, calls no model, opens no network connection, and touches no
database. Determinism is a hard requirement: the output is a pure function
of the input bytes; every timestamp shown comes from the envelopes' own
generated_at or line ts fields, never from a clock.

Honesty rules, deliberate and load-bearing:
- Statuses describe evidence state; they are never grades and are never
  summed into a percentage or score.
- Envelope-carried text is emitted through one function (emit_field) so the
  rendered document can be audited for untouched pass-through.
- The non-legal-advice notice renders twice and is never hidden.

Usage:
    python -m tere4ai.report <session.jsonl> [more...] \\
        [--envelope FILE ...] -o report.html
"""

from __future__ import annotations

from tere4ai.report.ingest import (
    Exchange,
    IngestResult,
    ProblemCard,
    fingerprint_tool,
    ingest_inputs,
)
from tere4ai.report.render import emit_field, render_report, render_report_from_paths

__all__ = [
    "Exchange",
    "IngestResult",
    "ProblemCard",
    "emit_field",
    "fingerprint_tool",
    "ingest_inputs",
    "render_report",
    "render_report_from_paths",
]

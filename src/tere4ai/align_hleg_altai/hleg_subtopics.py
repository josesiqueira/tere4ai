"""Deterministic HLEGRequirementSubtopic nodes (Layer 3 subtopic targets).

@implements: DEC-05 (partial: subtopic targets under the seven HLEG requirements)
@grounded_by: REF-33, REF-10

Slices the frozen HLEG Ethics Guidelines working text (the same file
hleg_nodes.py verifies and slices) one level deeper: within each requirement
section 1.1 to 1.7, the subtopic headings appear as short bold-style lines
that open a paragraph and end with a period before the paragraph's first
sentence ("Fundamental rights.", "Human agency.", "Resilience to attack and
security.", ...). The parent set is the closed canonical seven
(hleg_nodes.CANONICAL); this module never invents a parent.

Detection is deterministic and conservative (never guess): a line is a
CANDIDATE when it starts at column 0 with an uppercase letter and contains
". " with a non-empty tail on the same line. A candidate is ACCEPTED as a
heading only when the prefix before the first ". " looks like a heading: 1
to 7 words, at most 60 characters, no comma, semicolon, colon, digit, or
parenthesis, and the tail starts with an uppercase letter. Candidates that
fail the strict test are NOT emitted; they are recorded in the module-level
SKIPPED_REPORT (populated on every build call) so ambiguity is visible, per
the no-silent-degradation rule (architecture.md Section 13).

Node ids: hleg:<req-slug>:subtopic:<slug-of-heading>, layer 3, with a source
span into the frozen text (heading start to the next accepted heading or the
section end). Each parent HLEGRequirement gets a HAS_SUBTOPIC edge to its
subtopics, provenance EXTRACTED_SOURCE, method hleg_subtopic_slice_v1.

No LLM or model client is used anywhere in this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tere4ai.align_hleg_altai.hleg_nodes import (
    _HEADING,
    CANONICAL,
    DEFAULT_MANIFEST,
    DEFAULT_TEXT,
)

SUBTOPIC_METHOD = "hleg_subtopic_slice_v1"

# Section 1.7 runs to the next chapter-level heading of the working text.
_NEXT_CHAPTER = re.compile(r"^2\.\s", re.M)
# A candidate heading line (see module docstring). The tail must sit on the
# SAME line as the heading (a paragraph opener), so only [ \t] after the
# period: a period at end of line is a sentence end, not a heading.
_CANDIDATE = re.compile(r"^([A-Z][^\n]*?)\.[ \t]+(\S)", re.M)
_HEADING_FORBIDDEN = re.compile(r"[,;:()\d]")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# First sentence end: a period followed by whitespace and an uppercase start.
_SENTENCE_END = re.compile(r"\.(?=\s+[A-Z0-9(])")

_MAX_HEADING_WORDS = 7
_MAX_HEADING_CHARS = 60
_MAX_DESCRIPTION_CHARS = 600

# Rejected candidates of the most recent build call: list of dicts with keys
# section_id, heading_candidate, offset, reason. Tests assert on this.
SKIPPED_REPORT: list[dict[str, Any]] = []


def _slug(label: str) -> str:
    slug = _SLUG_STRIP.sub("-", label.lower()).strip("-")
    if not slug:
        raise ValueError(f"heading {label!r} yields an empty slug")
    return slug


def _heading_reject_reason(heading: str, tail_first: str) -> str | None:
    words = heading.split()
    if not 1 <= len(words) <= _MAX_HEADING_WORDS:
        return f"prefix has {len(words)} words (max {_MAX_HEADING_WORDS})"
    if len(heading) > _MAX_HEADING_CHARS:
        return f"prefix is {len(heading)} chars (max {_MAX_HEADING_CHARS})"
    if _HEADING_FORBIDDEN.search(heading):
        return "prefix contains punctuation or digits"
    if not tail_first.isupper():
        return "text after the period does not start a sentence"
    return None


def _first_sentence(text: str, start: int, end: int) -> str:
    """Whitespace-collapsed first sentence of text[start:end]."""
    raw = " ".join(text[start:end].split())
    match = _SENTENCE_END.search(raw)
    sentence = raw[: match.end()] if match else raw
    return sentence[:_MAX_DESCRIPTION_CHARS]


def build_hleg_subtopics(
    text_path: Path | str = DEFAULT_TEXT,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    build_id: str | None = None,
) -> dict[str, Any]:
    """Return {"nodes": [...], "edges": [...], "skipped": [...]}.

    Verifies the text file checksum against the snapshot manifest first
    (frozen-source rule). Deterministic: same input, same output; the
    skipped list is also copied to the module-level SKIPPED_REPORT.
    """
    text_path = Path(text_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entry = next(
        (s for s in manifest["snapshots"] if s["file"] == text_path.name), None
    )
    if entry is None:
        raise ValueError(f"{text_path.name} is not in the snapshot manifest")
    sha256 = hashlib.sha256(text_path.read_bytes()).hexdigest()
    if sha256 != entry["sha256"]:
        raise ValueError(
            f"checksum mismatch for {text_path.name}: manifest {entry['sha256']}, file {sha256}"
        )
    if build_id is None:
        build_id = f"build-{sha256[:12]}"

    text = text_path.read_text(encoding="utf-8")
    headings = list(_HEADING.finditer(text))
    if len(headings) != 7:
        raise ValueError(f"expected exactly 7 requirement headings, found {len(headings)}")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for i, section in enumerate(headings):
        order = int(section.group(1))
        req_id, _ = CANONICAL[order - 1]
        body_start = section.end()
        if i + 1 < len(headings):
            body_end = headings[i + 1].start()
        else:
            nxt = _NEXT_CHAPTER.search(text, body_start)
            body_end = nxt.start() if nxt else min(body_start + 6000, len(text))

        accepted: list[tuple[int, str, int]] = []  # (abs offset, label, tail offset)
        for match in _CANDIDATE.finditer(text, body_start, body_end):
            heading = match.group(1)
            reason = _heading_reject_reason(heading, match.group(2))
            if reason is not None:
                skipped.append(
                    {
                        "section_id": req_id,
                        "heading_candidate": heading[:80],
                        "offset": match.start(),
                        "reason": reason,
                    }
                )
                continue
            accepted.append((match.start(), heading, match.start(2)))

        for j, (start, label, tail_start) in enumerate(accepted):
            end = accepted[j + 1][0] if j + 1 < len(accepted) else body_end
            subtopic_id = f"{req_id}:subtopic:{_slug(label)}"
            span_id = f"span:{subtopic_id}"
            nodes.append(
                {
                    "id": subtopic_id,
                    "type": "HLEGRequirementSubtopic",
                    "layer": 3,
                    "hleg_requirement_id": req_id,
                    "order": j + 1,
                    "label": label,
                    "description": _first_sentence(text, tail_start, end),
                    "source_span": {
                        "span_id": span_id,
                        "snapshot_file": text_path.name,
                        "snapshot_sha256": entry["sha256"],
                        "start": start,
                        "end": end,
                        "anchor": f"{label}.",
                    },
                }
            )
            edges.append(
                {
                    "edge_id": f"edge:has_subtopic:{subtopic_id}",
                    "edge_type": "HAS_SUBTOPIC",
                    "from": req_id,
                    "to": subtopic_id,
                    "provenance_class": "EXTRACTED_SOURCE",
                    "source_span_id": span_id,
                    "method": SUBTOPIC_METHOD,
                    "confidence": 1.0,
                    "review_status": "auto_accepted",
                    "build_id": build_id,
                }
            )

    seen = set()
    for node in nodes:
        if node["id"] in seen:
            raise ValueError(f"duplicate subtopic id: {node['id']}")
        seen.add(node["id"])

    SKIPPED_REPORT[:] = skipped
    return {"nodes": nodes, "edges": edges, "skipped": skipped}

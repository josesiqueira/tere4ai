"""Deterministic builder for the seven HLEGRequirement nodes (Layer 3).

@implements: DEC-05 (partial: target-side HLEG nodes; assertions arrive with the mapping pipeline)
@grounded_by: REF-33, REF-10

Slices the frozen HLEG Ethics Guidelines working text (sections 1.1 to 1.7 of
chapter II) into the seven canonical requirements. The set is closed
(alignments.schema.json enforces the ids); this module never invents an
eighth. Source spans point into the frozen, checksum-verified text file so
every future AlignmentAssertion can cite ethics-side evidence spans.

The ALTAI question lists (assessment section of the same document) are NOT
emitted here; ALTAI redistribution has a pending license check (OPEN-LICENSE).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEXT = ROOT / "data" / "snapshots" / "hleg_ethics_guidelines_2019_en_v1text.txt"
DEFAULT_MANIFEST = ROOT / "data" / "snapshots" / "MANIFEST.json"

# Canonical order and ids (closed set; mirrors alignments.schema.json).
CANONICAL = [
    ("hleg:human-agency-and-oversight", "Human agency and oversight"),
    ("hleg:technical-robustness-and-safety", "Technical robustness and safety"),
    ("hleg:privacy-and-data-governance", "Privacy and data governance"),
    ("hleg:transparency", "Transparency"),
    (
        "hleg:diversity-non-discrimination-and-fairness",
        "Diversity, non-discrimination and fairness",
    ),
    ("hleg:societal-and-environmental-well-being", "Societal and environmental well-being"),
    ("hleg:accountability", "Accountability"),
]

_HEADING = re.compile(r"^1\.([1-7]) (.+)$", re.M)


def build_hleg_nodes(
    text_path: Path | str = DEFAULT_TEXT,
    manifest_path: Path | str = DEFAULT_MANIFEST,
) -> list[dict[str, Any]]:
    """Return the seven HLEGRequirement nodes with source spans.

    Verifies the text file checksum against the snapshot manifest first
    (frozen-source rule, architecture.md Section 6). Raises on any drift or
    if the seven sections are not found exactly once each, in order.
    """
    text_path = Path(text_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entry = next(
        (s for s in manifest["snapshots"] if s["file"] == text_path.name), None
    )
    if entry is None:
        raise ValueError(f"{text_path.name} is not in the snapshot manifest")
    actual = hashlib.sha256(text_path.read_bytes()).hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(
            f"checksum mismatch for {text_path.name}: manifest {entry['sha256']}, file {actual}"
        )

    text = text_path.read_text(encoding="utf-8")
    headings = list(_HEADING.finditer(text))
    if len(headings) != 7:
        raise ValueError(f"expected exactly 7 requirement headings, found {len(headings)}")

    nodes: list[dict[str, Any]] = []
    for i, match in enumerate(headings):
        order = int(match.group(1))
        req_id, canonical_name = CANONICAL[order - 1]
        # section body runs to the next heading (or a hard cap for 1.7)
        start = match.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else start + 6000
        section = text[start:end]
        # description: first non-heading paragraph of the section
        body_lines = section.splitlines()[1:]
        description_lines: list[str] = []
        for line in body_lines:
            if not line.strip():
                if description_lines:
                    break
                continue
            description_lines.append(line.strip())
        nodes.append(
            {
                "id": req_id,
                "type": "HLEGRequirement",
                "layer": 3,
                "order": order,
                "name": canonical_name,
                "description": " ".join(description_lines),
                "source_span": {
                    "span_id": f"span:hleg:req{order}",
                    "snapshot_file": text_path.name,
                    "snapshot_sha256": entry["sha256"],
                    "start": start,
                    "end": min(end, len(text)),
                    "anchor": match.group(0).strip(),
                },
            }
        )
    return nodes

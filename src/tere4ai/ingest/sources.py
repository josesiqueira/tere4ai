"""Layer 0 source registry: the version pin for M1.

@implements: DEC-12
@grounded_by: REF-01, REF-02, REF-04

Emits the SourceDocument nodes and versioning edges required by
docs/architecture.md Section 11:
  - base Act (Regulation (EU) 2024/1689), legal_status in_force
  - Digital Omnibus on AI (Regulation (EU) 2026/1744), legal_status
    in_force, linked to the base Act by AMENDS and HAS_VERSION edges,
    carrying the deferred high-risk deadlines and an explicit
    merged_into_base=False marker
  - the frozen SourceFile snapshot(s) from data/snapshots/MANIFEST.json

Omnibus edits are never merged into the base text (Section 11 version pin);
now that the Omnibus is in force, merged_into_base states that explicitly.
Published identity verified on EUR-Lex 2026-09-02: Regulation (EU) 2026/1744,
OJ L, 2026/1744, 24.7.2026, in force since 27.7.2026 (REF-02).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_ACT_ID = "src:eu-ai-act:oj-2024-07-12"
OMNIBUS_ID = "src:omnibus-com-2025-836"

# Deferred application dates introduced by the Omnibus (architecture.md S11).
OMNIBUS_DEFERRED_DEADLINES = {
    "annex_iii_standalone_high_risk": "2027-12-02",
    "annex_i_embedded_high_risk": "2028-08-02",
}


def _edge(
    edge_id: str,
    edge_type: str,
    from_id: str,
    to_id: str,
    build_id: str,
    derivation_id: str,
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "from": from_id,
        "to": to_id,
        "provenance_class": "EXTRACTED_SOURCE",
        "derivation_id": derivation_id,
        "method": "source_registry_v1",
        "confidence": 1.0,
        "review_status": "auto_accepted",
        "build_id": build_id,
    }


def layer0(build_id: str, manifest_path: str | Path) -> tuple[list[dict], list[dict]]:
    """Return (nodes, edges) for Layer 0: source documents, files, versioning.

    manifest_path points at data/snapshots/MANIFEST.json; every listed
    snapshot becomes a SourceFile node linked to the base Act.
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    nodes: list[dict] = [
        {
            "id": BASE_ACT_ID,
            "layer": 0,
            "type": "SourceDocument",
            "title": "Regulation (EU) 2024/1689 (Artificial Intelligence Act)",
            "celex": "32024R1689",
            "eli": "http://data.europa.eu/eli/reg/2024/1689/oj",
            "legal_status": "in_force",
            "notes": "Base act, version pin for M1 (architecture.md Section 11).",
        },
        {
            "id": OMNIBUS_ID,
            "layer": 0,
            "type": "SourceDocument",
            "title": "Digital Omnibus on AI, Regulation (EU) 2026/1744",
            "celex": "32026R1744",
            "eli": "http://data.europa.eu/eli/reg/2026/1744/oj",
            "legal_status": "in_force",
            "merged_into_base": False,
            "notes": (
                "Amending instrument, OJ L, 2026/1744, 24.7.2026, in force since "
                "27.7.2026; adopted from COM(2025) 836 final, procedure "
                "2025/0359(COD), which the stable node id still names. Defers "
                "standalone Annex III high-risk to "
                f"{OMNIBUS_DEFERRED_DEADLINES['annex_iii_standalone_high_risk']} and embedded "
                f"Annex I to {OMNIBUS_DEFERRED_DEADLINES['annex_i_embedded_high_risk']}, "
                "both confirmed against the OJ text (REF-02). Never merged into "
                "base text: merged_into_base stays False."
            ),
        },
    ]

    edges: list[dict] = [
        _edge(
            "edge:omnibus-amends-base",
            "AMENDS",
            OMNIBUS_ID,
            BASE_ACT_ID,
            build_id,
            "derivation:source_registry:omnibus",
        ),
        _edge(
            "edge:base-has-version-omnibus",
            "HAS_VERSION",
            BASE_ACT_ID,
            OMNIBUS_ID,
            build_id,
            "derivation:source_registry:omnibus",
        ),
    ]

    for snap in manifest["snapshots"]:
        file_id = f"srcfile:{snap['file']}"
        nodes.append(
            {
                "id": file_id,
                "layer": 0,
                "type": "SourceFile",
                "file": snap["file"],
                "sha256": snap["sha256"],
                "manifestation": snap.get("manifestation", ""),
                "language": snap.get("language", ""),
                "retrieved_at": snap.get("retrieved_at", ""),
            }
        )
        edges.append(
            _edge(
                f"edge:{file_id}-derived-from-{BASE_ACT_ID}",
                "DERIVED_FROM_SOURCE",
                file_id,
                BASE_ACT_ID,
                build_id,
                f"derivation:source_registry:{snap['file']}",
            )
        )

    return nodes, edges

"""Layer 0 source registry: the version pin for M1.

@implements: DEC-12, DEC-23
@grounded_by: REF-01, REF-02, REF-04

Emits the SourceDocument nodes and versioning edges required by
docs/architecture.md Section 11:
  - base Act (Regulation (EU) 2024/1689), legal_status in_force
  - Digital Omnibus on AI (Regulation (EU) 2026/1744), legal_status
    in_force, linked to the base Act by AMENDS and HAS_VERSION edges,
    carrying the deferred high-risk deadlines; since B132 merged into the
    base text (merged_into_base True, the date and the reviewed marker
    list's sha256) when layer0 is given the marker list
  - EUR-Lex's consolidated text of 27 July 2026 (B132), legal_status
    non_binding: it has no legal effect, and Layer 1 checks every unit
    of it against the Official Journal wording (architecture.md Section 11)
  - the frozen SourceFile snapshot(s) from data/snapshots/MANIFEST.json

Since B132 (spec G D-G68) Layer 1 is the Act as amended: the Omnibus's
changes are read from the consolidated text's markers and checked against
the Official Journal wording, so the Omnibus is merged into the base text,
and gate G6 lets that through only with the record of the checks. Without
a marker list (the Act as enacted) merged_into_base stays False.
Published identity verified on EUR-Lex 2026-09-02: Regulation (EU) 2026/1744,
OJ L, 2026/1744, 24.7.2026, in force since 27.7.2026 (REF-02).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BASE_ACT_ID = "src:eu-ai-act:oj-2024-07-12"
OMNIBUS_ID = "src:omnibus-com-2025-836"
CONSOLIDATED_ID = "src:eu-ai-act:consolidated-2026-07-27"
CONSOLIDATED_NOTE = (
    "EUR-Lex consolidated text, CELEX 02024R1689-20260727, START.DATE 20260727. EUR-Lex: \"This text is meant "
    "purely as a documentation tool and has no legal effect.\" Layer 1 is parsed from it and every unit is "
    "checked against the Official Journal wording of the act that enacted it (architecture.md Section 11)."
)

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


def layer0(
    build_id: str, manifest_path: str | Path, marker_list_path: str | Path | None = None
) -> tuple[list[dict], list[dict]]:
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
        {
            "id": CONSOLIDATED_ID,
            "layer": 0,
            "type": "SourceDocument",
            "title": "Regulation (EU) 2024/1689, consolidated text of 27 July 2026 (EUR-Lex)",
            "celex": "02024R1689-20260727",
            "eli": "http://data.europa.eu/eli/reg/2024/1689/2026-07-27",
            "legal_status": "non_binding",
            "notes": CONSOLIDATED_NOTE,
        },
    ]
    if marker_list_path is not None:
        # B132: the Omnibus is merged into the base text; the reviewed marker
        # list's digest ties the merge to the checks gate G6 verifies.
        omnibus = next(n for n in nodes if n["id"] == OMNIBUS_ID)
        omnibus.update({
            "merged_into_base": True,
            "merged_on": "2026-07-27",
            "marker_list_sha256": hashlib.sha256(Path(marker_list_path).read_bytes()).hexdigest(),
            "notes": (
                "Amending instrument, OJ L, 2026/1744, 24.7.2026, in force since 27.7.2026; adopted from "
                "COM(2025) 836 final, procedure 2025/0359(COD), which the stable node id still names. Merged "
                "into the base text since B132: Layer 1 is the Act as amended, each change read from the "
                "consolidated text's markers and checked against this instrument (marker list "
                "data/amendments/omnibus_markers.json, its sha256 in marker_list_sha256)."
            ),
        })

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

    # Which SourceDocument a snapshot manifests. Everything not named here
    # keeps the historical base-act linkage (including the HLEG snapshots,
    # whose own SourceDocument only exists at Layer 3 publication).
    source_ids = {"omnibus": OMNIBUS_ID, "eu-ai-act-consolidated": CONSOLIDATED_ID}
    for snap in manifest["snapshots"]:
        file_id = f"srcfile:{snap['file']}"
        source_id = source_ids.get(snap.get("source_document", ""), BASE_ACT_ID)
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
                f"edge:{file_id}-derived-from-{source_id}",
                "DERIVED_FROM_SOURCE",
                file_id,
                source_id,
                build_id,
                f"derivation:source_registry:{snap['file']}",
            )
        )

    return nodes, edges

"""The architecture diagram is a derived artifact and stays current.

The previous SVG was an unregenerable blob that drifted from decided facts
(eIds that do not exist, a judge-family decision left open, a superseded
v1-migration plan). These tests pin the figure to its generator and the
generator to the decided facts, so the diagram can never silently drift
again: the committed SVG must be byte-identical to the generator output,
must be well-formed XML, and must not contain the stale claims.
"""

from __future__ import annotations

import sys

# Parsing our own generator's output string, never external XML, so the
# stdlib parser is safe here (no external entities can occur in build()).
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from make_architecture_diagram import OUT_PATH, build  # noqa: E402

STALE_CLAIMS = (
    # No eId attributes exist in the served manifestations (architecture.md S6).
    "eIds",
    # DEC-07 closed the judge-family decision on 2026-07-08.
    "judge family: OPEN",
    # M2 replaced v1-slice migration with regeneration; the poster query is a fixture.
    "migration seed",
)

DECIDED_FACTS = (
    "no LLM",
    "Anthropic Claude",
    "regression fixture",
    "runtime needs NO live database",
    "never 'compliant'",
)


def test_committed_svg_matches_the_generator_output():
    assert OUT_PATH.read_text(encoding="utf-8") == build(), (
        "tere4ai_v2_architecture.svg differs from its generator; run "
        ".venv/bin/python scripts/make_architecture_diagram.py and re-render "
        "the PNG"
    )


def test_svg_is_well_formed_xml():
    ET.fromstring(build())


def test_no_stale_claims_and_all_decided_facts_present():
    svg = build()
    for stale in STALE_CLAIMS:
        assert stale not in svg, f"stale claim back in the diagram: {stale!r}"
    for fact in DECIDED_FACTS:
        assert fact in svg, f"decided fact missing from the diagram: {fact!r}"


def test_mermaid_companion_carries_the_same_decided_facts():
    """docs/diagrams/architecture.mmd is the editable mermaid companion of
    the generated SVG; it must state the same decided facts and never the
    stale claims."""
    mmd = (ROOT / "docs" / "diagrams" / "architecture.mmd").read_text(
        encoding="utf-8"
    )
    for stale in STALE_CLAIMS:
        assert stale not in mmd, f"stale claim in the mermaid companion: {stale!r}"
    for fact in DECIDED_FACTS:
        assert fact in mmd, f"decided fact missing from the mermaid companion: {fact!r}"

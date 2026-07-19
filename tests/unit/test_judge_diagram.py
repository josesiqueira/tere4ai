"""The judge-pipeline diagram is a derived artifact and stays truthful.

Same discipline as test_architecture_diagram.py: the committed SVG must be
byte-identical to its generator, and the generator must state the verified
judge facts (three judges, mechanical gates, verdict-not-threshold
gating, safe fallback, honest FA/FR limitation) and never the tempting
overclaims (no numeric acceptance thresholds exist, and the judge system
must not be described as measured while task 25 is open).
"""

from __future__ import annotations

import sys

# Parsing our own generator's output string, never external XML, so the
# stdlib parser is safe here (no external entities can occur in build()).
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from make_judge_diagram import OUT_PATH, build  # noqa: E402

REQUIRED_FACTS = (
    "Extraction judge",
    "Mapping judge",
    "Runtime grounding judge",
    "Mechanical quote gate",
    "never accept anything",
    "requires_human_review",
    "instrumented but unmeasured",
    "mechanical:quote_check",
)


def test_committed_svg_matches_the_generator_output():
    assert OUT_PATH.read_text(encoding="utf-8") == build(), (
        "judge_diagram.svg differs from its generator; run "
        ".venv/bin/python scripts/make_judge_diagram.py and re-render the PNG"
    )


def test_svg_is_well_formed_xml():
    ET.fromstring(build())


def test_verified_judge_facts_present():
    svg = build()
    for fact in REQUIRED_FACTS:
        assert fact in svg, f"verified judge fact missing from the diagram: {fact!r}"

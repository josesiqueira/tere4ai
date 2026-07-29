"""The web copies of the guard-tested diagrams must stay byte-identical.

The root SVGs are deterministically regenerated and guard-tested; the web
page serves copies from web/public. This test makes silent drift
impossible: regenerate a diagram, re-copy it, or the suite fails.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

PAIRS = [
    ("tere4ai_v2_architecture.svg", "web/public/tere4ai_v2_architecture.svg"),
    ("judge_diagram.svg", "web/public/judge_diagram.svg"),
]


def test_web_diagram_copies_are_byte_identical():
    for source, copy in PAIRS:
        src = ROOT / source
        dst = ROOT / copy
        assert dst.is_file(), f"missing web copy: {copy}"
        assert src.read_bytes() == dst.read_bytes(), f"drifted: {copy}"

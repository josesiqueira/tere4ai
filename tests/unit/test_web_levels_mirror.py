"""The web copy of the level names equals the Python source (DEC-20)."""

from __future__ import annotations

import re
from pathlib import Path

from tere4ai.mcp_server.levels import LEVEL_NAMES

LEVELS_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "levels.ts"


def test_web_level_names_equal_the_python_level_names():
    text = LEVELS_TS.read_text(encoding="utf-8")
    block = text.split("export const LEVEL_NAMES", 1)[1].split("};", 1)[0]
    pairs = dict(re.findall(r'(\w+):\s*"([^"]+)"', block))
    assert len(pairs) == 5
    assert pairs == LEVEL_NAMES

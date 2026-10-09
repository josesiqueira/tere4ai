"""B145 (spec G D-G80 (3); brief A2): one list per meaning. The names of the
lists B145 replaced appear in no source file of tere4ai2 but the one frozen
function of the first reading (brief R27); the recorded instruments (the
prompts v1 to v4, norms schema version 1) and the tests are not scanned."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_NAMES = ("CANONICAL_ACTORS", "OPERATOR_ROLES", "NON_OPERATOR_ROLES", "_OPERATOR_CANONICAL", "_OPERATOR_WORDS",
             "_NON_OPERATOR_WORDS", "_SYNONYMS", "_canonical_actor_roles", "actorRole", "LEGAL_ACTORS",
             "ACTOR_ROLES", "legalActor")
EXCEPTED = {ROOT / "src" / "tere4ai" / "extract_norms" / "scope_first_reading.py"}
PATTERN = re.compile(r"\b(" + "|".join(re.escape(n) for n in OLD_NAMES) + r")\b")


def _sources():
    return sorted(p for top in ("src", "scripts") for p in (ROOT / top).rglob("*.py") if "__pycache__" not in p.parts)


def test_the_scan_reads_the_source_tree():
    assert len(_sources()) > 100  # 134 files at B145


def test_no_source_file_names_a_replaced_list():
    hits = [f"{p.relative_to(ROOT)}:{i}: {m.group(1)}"
            for p in _sources() if p not in EXCEPTED
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            for m in PATTERN.finditer(line)]
    assert hits == []


def test_the_exception_is_the_frozen_first_reading():
    (frozen,) = EXCEPTED
    text = frozen.read_text(encoding="utf-8")
    assert "OPERATOR_ROLES" in text and "_CANONICAL_ACTORS" in text and "8440c99" in text

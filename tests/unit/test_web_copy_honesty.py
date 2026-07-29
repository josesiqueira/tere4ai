"""Structural honesty guards for the demo web UI.

The server side has a scoped banned-term contract (DEC-08) and a dash
gate; until this file existed, nothing scanned the UI's own copy. These
guards walk web/src so a hand-typed em dash or claim term can never ship.
Word-boundary matching keeps the mandated caveat legal ("certify",
"compliance" are not the banned claim terms).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
WEB_SRC = ROOT / "web" / "src"
BANNED = re.compile(r"\b(compliant|certified|legally approved)\b", re.IGNORECASE)
DASHES = re.compile("[—–]")


def _web_files():
    files = [
        p for p in WEB_SRC.rglob("*")
        if p.suffix in {".tsx", ".ts", ".css"} and p.is_file()
    ]
    assert files, "web/src scan found no files; layout changed?"
    return files


def test_web_copy_has_no_em_or_en_dashes():
    offenders = [
        str(p.relative_to(ROOT))
        for p in _web_files()
        if DASHES.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_web_copy_has_no_banned_claim_terms():
    offenders = []
    for p in _web_files():
        for m in BANNED.finditer(p.read_text(encoding="utf-8")):
            offenders.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert offenders == []


def test_ui_data_serves_the_recorded_chain_id_and_schema_flags():
    ui = json.loads((ROOT / "web" / "public" / "ui_data.json").read_text())
    current = (
        (ROOT / "data" / "graph_dumps" / "BUILD_CHAIN_CURRENT.txt")
        .read_text()
        .strip()
    )
    assert ui["build"]["chain_id"] == current
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    assert ui["schema_flags"] == schema_flag_names()


def test_presets_cover_every_schema_flag():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    presets_text = (WEB_SRC / "app" / "assess" / "presets.ts").read_text()
    missing = [f for f in schema_flag_names() if f'"{f}"' not in presets_text]
    assert missing == [], f"presets.ts missing schema flags: {missing}"


def test_flag_panel_covers_every_schema_flag():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    page_text = (WEB_SRC / "app" / "assess" / "page.tsx").read_text()
    missing = [f for f in schema_flag_names() if f'"{f}"' not in page_text]
    assert missing == [], f"page.tsx flag panel missing schema flags: {missing}"

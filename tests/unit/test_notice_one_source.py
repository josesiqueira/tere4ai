"""The notice has one source (B34 item b, DEC-22)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from tere4ai.http_facade import app as facade
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE

ROOT = Path(__file__).resolve().parents[2]
NOTICE_TS = ROOT / "web" / "src" / "lib" / "notice.ts"


def test_web_notice_equals_the_python_notice():
    text = NOTICE_TS.read_text(encoding="utf-8")
    match = re.search(r'export const NOTICE =\s*"([^"]+)";', text)
    assert match, "web/src/lib/notice.ts must export NOTICE as one string literal"
    assert match.group(1) == NON_LEGAL_ADVICE_NOTICE


def test_no_other_web_file_words_a_notice():
    words = ("documentation support", "legal advice", "certif")
    found = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "web" / "src").rglob("*.tsx")
        if any(w in p.read_text(encoding="utf-8").lower() for w in words)
    ]
    assert found == []


def test_llms_txt_and_well_known_serve_the_constant():
    # The app's state is set by its lifespan, which runs inside the with.
    with TestClient(facade.create_app()) as client:
        llms = client.get("/llms.txt").text
        well_known = client.get("/.well-known/tere4ai.json").json()
    assert NON_LEGAL_ADVICE_NOTICE in llms
    assert "never claims compliance" not in llms
    assert well_known["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE

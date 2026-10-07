"""The hand-made v1 copy of the HLEG Guidelines is gone (B143, acceptance 6).

No tracked file names it outside the disposable pre-B74 data (data/graph_dumps,
data/review_queue) and the recorded MAISA demo sessions, whose tool answers
are kept as recorded (ruling R21). Git history keeps the file.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
V1 = "hleg_ethics_guidelines_2019_en_v1text.txt"
KEPT_AS_RECORDED = ("data/graph_dumps/", "data/review_queue/", "demo/mcp_demo/sessions/")


def test_the_v1_copy_is_gone():
    assert not (ROOT / "data" / "snapshots" / V1).exists()
    assert V1 not in (ROOT / "data" / "snapshots" / "MANIFEST.json").read_text(encoding="utf-8")


def test_no_tracked_code_test_or_document_names_it():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", V1], capture_output=True, text=True, check=False)
    except OSError:
        pytest.skip("git is not available")
    if out.returncode not in (0, 1):
        pytest.skip("not a git checkout")
    naming = [p for p in out.stdout.split() if not p.startswith(KEPT_AS_RECORDED) and p != "tests/unit/test_v1_text_gone.py"]
    assert naming == []

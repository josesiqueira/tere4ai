import re
from pathlib import Path


def test_release_checks_are_named_in_full_words():
    text = (Path(__file__).resolve().parents[2] / "scripts/check_release_hygiene.py").read_text(encoding="utf-8")
    assert "RELEASE_CHECK1" in text and "RELEASE_CHECK2" in text and "RELEASE_CHECK3" in text
    assert not re.search(r"\bH[1-3]\b", text)

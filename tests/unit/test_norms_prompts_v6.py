"""B170 part 1 (2026-10-13): extract_norms v6 is v5 without the
lifecycle_phase_ids slot, a slot no source grounds (Jose: "if it is not
grounded in anything we will drop from everywhere"), and judge_norms v6 is
judge_norms v5 under the new version line (the two share one version)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(kind: str, version: str) -> str:
    return (ROOT / "prompts" / kind / f"{version}.md").read_text(encoding="utf-8")


def expected_extract_v6() -> str:
    text = _read("extract_norms", "v5")
    for old, new in (
        ("# extract_norms system prompt, version v5\n", "# extract_norms system prompt, version v6\n"),
        ('      "lifecycle_phase_ids": ["design_development", "cross_phase"],\n', ""),
        ('- lifecycle_phase_ids: zero or more of "design_development",\n'
         '  "data_and_training", "verification_validation", "placing_on_market",\n'
         '  "putting_into_service", "operation_monitoring", "substantial_modification",\n'
         '  "post_market", "decommissioning", "cross_phase".\n', ""),
    ):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def test_extract_norms_v6_is_v5_without_the_lifecycle_slot():
    text = _read("extract_norms", "v6")
    assert text == expected_extract_v6()
    assert "lifecycle" not in text.lower()


def test_judge_norms_v6_is_v5_under_the_new_version_line():
    v5 = _read("judge_norms", "v5")
    assert _read("judge_norms", "v6") == v5.replace(
        "# judge_norms system prompt, version v5\n", "# judge_norms system prompt, version v6\n", 1)
    assert "lifecycle" not in v5.lower()

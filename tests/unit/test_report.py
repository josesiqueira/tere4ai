"""Report renderer tests: determinism, ingestion, tiers, CLI exit codes.

The renderer is a pure function of its input bytes: no clock, no model, no
network, no dumps. All tests run against the committed demo session fixtures
plus small doctored files written to tmp_path.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tere4ai.report import ingest_inputs, render_report_from_paths

SESSIONS_DIR = Path(__file__).parent.parent / "fixtures" / "demo_sessions"
SHOPBOT = SESSIONS_DIR / "shopbot-transparency.jsonl"
MOODWATCH = SESSIONS_DIR / "moodwatch-prohibited.jsonl"
CREDSCORE = SESSIONS_DIR / "credscore-highrisk.jsonl"

# Loose Section 8 envelope artifact recorded from the live server. It lives
# in the sibling demo-systems checkout, not in this repository.
BACKLOG_ENVELOPE = (
    Path(__file__).resolve().parents[2].parent
    / "demo-systems"
    / "_fallbacks"
    / "highrisk-backlog-article9.json"
)


def _section_body(html: str, section: str) -> str:
    marker = f'data-section="{section}"'
    assert marker in html
    return html.split(marker, 1)[1].split("</section>", 1)[0]


def test_determinism_byte_identical() -> None:
    first = render_report_from_paths([SHOPBOT])
    second = render_report_from_paths([SHOPBOT])
    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_shopbot_renders_rows_and_placeholders() -> None:
    html = render_report_from_paths([SHOPBOT])
    # 13 accepted article-50 norms in the recorded requirements envelope.
    assert html.count('class="norm-row"') == 13
    # Unrecorded tools still get their fixed sections, as placeholders.
    for tool in (
        "trace_implementation",
        "generate_control_backlog",
        "evaluate_project_evidence",
    ):
        assert f"{tool}: not recorded in this session" in html
    # Fixed section order is always present.
    for section in (
        "classification",
        "requirements",
        "trace_matrix",
        "backlog",
        "alignment",
        "evidence",
        "provenance",
    ):
        assert f'data-section="{section}"' in html
    # The notice renders twice and never inside <details>.
    assert html.count('data-envelope-field="non_legal_advice_notice"') == 2
    # The fixed trace honesty sentence is inside the trace matrix section.
    assert "A trace is a developer claim, not evidence." in _section_body(
        html, "trace_matrix"
    )


def test_malformed_line_becomes_problem_card_and_rest_renders(
    tmp_path: Path,
) -> None:
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    doctored = tmp_path / "doctored.jsonl"
    doctored.write_text(
        lines[0] + "\n{this is not json\n" + lines[1] + "\n", encoding="utf-8"
    )
    result = ingest_inputs([doctored])
    assert len(result.exchanges) == 2
    assert len(result.problems) == 1
    assert "invalid JSON" in result.problems[0].errors[0]
    html = render_report_from_paths([doctored])
    assert "Recording problems" in html
    assert html.count('class="norm-row"') == 13


def test_missing_keys_line_is_problem_card(tmp_path: Path) -> None:
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    del record["envelope"]
    doctored = tmp_path / "missing.jsonl"
    doctored.write_text(
        json.dumps(record) + "\n" + lines[1] + "\n", encoding="utf-8"
    )
    result = ingest_inputs([doctored])
    assert len(result.exchanges) == 1
    assert len(result.problems) == 1
    assert result.problems[0].claimed_tool == "classify_ai_system"
    assert any("envelope" in e for e in result.problems[0].errors)


@pytest.mark.skipif(
    not BACKLOG_ENVELOPE.is_file(),
    reason="demo-systems backlog artifact not checked out alongside this repo",
)
def test_loose_backlog_envelope_fingerprints_and_renders() -> None:
    result = ingest_inputs([CREDSCORE], [BACKLOG_ENVELOPE])
    backlog = [e for e in result.exchanges if e.tool == "generate_control_backlog"]
    assert len(backlog) == 1
    assert backlog[0].origin == "loose"
    assert backlog[0].seq == 3  # appended after the session max seq
    assert backlog[0].request is None
    html = render_report_from_paths([CREDSCORE], [BACKLOG_ENVELOPE])
    backlog_body = _section_body(html, "backlog")
    assert backlog_body.count("<li>") == 6
    assert "judge-record" in backlog_body
    # Integrity counters are printed even at zero, from the envelope values.
    assert 'data-envelope-field="dropped_items"' in backlog_body
    assert 'data-envelope-field="merged_items"' in backlog_body
    assert "items dropped" in backlog_body and "merged" in backlog_body
    assert "not truncated" in backlog_body


def test_mixed_graph_versions_banner(tmp_path: Path) -> None:
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["envelope"]["graph_version"] = "build-doctored"
    doctored = tmp_path / "mixed.jsonl"
    doctored.write_text(
        lines[0] + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )
    html = render_report_from_paths([doctored])
    assert "MIXED GRAPH VERSIONS" in html
    assert "build-doctored" in html
    # Every card is stamped with its own version when versions are mixed.
    assert html.count('data-envelope-field="graph_version"') > 2


def test_single_version_no_banner() -> None:
    html = render_report_from_paths([SHOPBOT])
    assert "MIXED GRAPH VERSIONS" not in html


def test_prohibited_full_stop_banner() -> None:
    html = render_report_from_paths([MOODWATCH])
    assert "prohibition-banner" in html
    # The requirements message renders verbatim.
    message = json.loads(MOODWATCH.read_text(encoding="utf-8").splitlines()[1])[
        "envelope"
    ]["answer"]["message"]
    assert message in html
    # Article 5 source node chips.
    assert "eu-ai-act:article-5:paragraph-1:point-f" in html
    # No matrix body: no table and no trace rows inside the matrix section.
    matrix_body = _section_body(html, "trace_matrix")
    assert "<table" not in matrix_body
    assert "data-trace-row" not in matrix_body
    # Scoreboard suppressed.
    assert "summary figures are not rendered" in html
    # The nonexistent "violated principles" field is never invented.
    assert "violated" not in html.lower()


def test_duplicate_classify_last_wins_with_call_history(tmp_path: Path) -> None:
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    second = json.loads(lines[0])
    second["seq"] = 3
    second["request"] = json.loads(json.dumps(second["request"]))
    second["request"]["features"]["description"] = (
        "ShopBot rev2 now also recommends products to returning customers."
    )
    doctored = tmp_path / "dup.jsonl"
    doctored.write_text(
        json.dumps(first) + "\n" + lines[1] + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )
    html = render_report_from_paths([doctored])
    classification = _section_body(html, "classification")
    assert "call-history" in classification
    assert "seq 1" in classification
    assert "re-classified: inputs changed" in classification
    # Last call wins the H1 identity too.
    assert "ShopBot rev2" in html


def test_nonmonotonic_seq_flagged_never_fatal(tmp_path: Path) -> None:
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["seq"] = 1  # duplicate of the classify seq
    doctored = tmp_path / "dupseq.jsonl"
    doctored.write_text(
        lines[0] + "\n" + json.dumps(second) + "\n", encoding="utf-8"
    )
    result = ingest_inputs([doctored])
    assert len(result.exchanges) == 2
    assert any("seq" in f for f in result.header_flags)
    html = render_report_from_paths([doctored])
    assert html.count('class="norm-row"') == 13


def test_statuses_and_legend_present() -> None:
    html = render_report_from_paths([SHOPBOT])
    assert (
        "Statuses describe evidence state. They are not grades and do not sum"
        in html
    )
    for status in (
        "not_applicable",
        "requires_human_review",
        "satisfied_with_evidence",
    ):
        assert f'data-status="{status}"' in html


def test_cli_exit_codes(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    ok = subprocess.run(
        [
            sys.executable,
            "-m",
            "tere4ai.report",
            str(SHOPBOT),
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")

    missing = subprocess.run(
        [
            sys.executable,
            "-m",
            "tere4ai.report",
            str(tmp_path / "does-not-exist.jsonl"),
            "-o",
            str(tmp_path / "x.html"),
        ],
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 2

    no_output = subprocess.run(
        [sys.executable, "-m", "tere4ai.report", str(SHOPBOT)],
        capture_output=True,
        text=True,
    )
    assert no_output.returncode == 2

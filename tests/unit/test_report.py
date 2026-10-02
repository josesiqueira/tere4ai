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
    assert "truncated" not in backlog_body


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


def _render_with_prohibited(tmp_path: Path, value: object) -> str:
    """Render the shopbot session with the classify answer's unacceptable_risk
    field set to value (the recorded value is replaced, not relied on)."""
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["tool"] == "classify_ai_system"
    first["envelope"]["answer"]["unacceptable_risk"] = value
    doctored = tmp_path / f"unacceptable-{value}.jsonl"
    doctored.write_text(
        "\n".join([json.dumps(first), *lines[1:]]) + "\n", encoding="utf-8"
    )
    return render_report_from_paths([doctored])


def test_false_prohibited_renders_verbatim(tmp_path: Path) -> None:
    """DEC-18: false is shown as false, not as unknown."""
    html = _render_with_prohibited(tmp_path, False)
    assert 'data-envelope-field="unacceptable_risk">no<' in html
    assert 'data-envelope-field="unacceptable_risk">unknown<' not in html


def test_null_prohibited_renders_as_unknown(tmp_path: Path) -> None:
    """DEC-18: a null unacceptable_risk is printed as unknown, never as null."""
    # Start from a known non-null value so the test reads as a change.
    before = _render_with_prohibited(tmp_path, True)
    assert 'data-envelope-field="unacceptable_risk">yes<' in before
    html = _render_with_prohibited(tmp_path, None)
    assert 'data-envelope-field="unacceptable_risk">unknown<' in html
    assert 'data-envelope-field="unacceptable_risk">null<' not in html


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


def _doctored_shopbot(tmp_path: Path, extra=None, edit=None) -> Path:
    lines = [json.loads(x) for x in SHOPBOT.read_text(encoding="utf-8").splitlines() if x.strip()]
    if edit is not None:
        edit(lines)
    path = tmp_path / "doctored-shopbot.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in [*lines, *(extra or [])]), encoding="utf-8")
    return path


def test_requirement_rows_show_the_requirement_type_and_read_null_by_the_scope(tmp_path: Path) -> None:
    """DEC-19 (rulings 53 and 58): the label is "requirement type"; a null on
    an in-scope obligation reads "no type", a null outside the scope "not an
    operator requirement"; a row recorded before DEC-19 shows nothing."""
    before = render_report_from_paths([SHOPBOT])
    assert 'data-envelope-field="requirement_type"' not in before
    assert "requirement type" not in before

    def edit(lines):
        requirements = next(x for x in lines if x["tool"] == "get_applicable_requirements")
        rows = requirements["envelope"]["answer"]["requirements_by_article"]["article-50"]
        rows[0]["requirement_type"] = "process"
        rows[1]["requirement_type"] = None
        rows[2]["requirement_type"] = None
        rows[2]["deontic_type"] = "permission"

    html = _section_body(render_report_from_paths([_doctored_shopbot(tmp_path, edit=edit)]), "requirements")
    assert html.count('requirement type <span class="field" data-envelope-field="requirement_type">process<') == 1
    assert html.count('requirement type <span class="muted">no type</span>') == 1
    assert html.count('requirement type <span class="muted">not an operator requirement</span>') == 1


def test_the_explain_record_shows_the_requirement_type(tmp_path: Path) -> None:
    lines = [json.loads(x) for x in SHOPBOT.read_text(encoding="utf-8").splitlines() if x.strip()]
    requirements = next(x for x in lines if x["tool"] == "get_applicable_requirements")
    entry = requirements["envelope"]["answer"]["requirements_by_article"]["article-50"][0]
    explain = {
        "seq": 3, "ts": requirements["ts"], "tool": "explain_requirement", "repo_ref": requirements["repo_ref"],
        "request": {"norm_id": entry["norm_id"]},
        "envelope": {
            **{k: v for k, v in requirements["envelope"].items() if k != "answer"},
            "answer": {
                "norm_id": entry["norm_id"], "found": True, "review_note": "This norm is judge-accepted.",
                "deontic": {"deontic_type": "obligation", "modal": "shall", "action": "inform",
                            "object": "natural persons", "requirement_type": "functional",
                            "actor": {"explicit": "providers", "inferred": None, "inference_source_node_id": None}},
                "source": {"node_id": entry["source_node_id"]},
            },
        },
    }
    html = _section_body(render_report_from_paths([_doctored_shopbot(tmp_path, extra=[explain])]), "requirements")
    record = html.split("explain_requirement record for", 1)[1]
    assert 'requirement type <span class="field" data-envelope-field="requirement_type">functional<' in record


def test_backlog_items_show_their_type_and_the_judges_view(tmp_path: Path) -> None:
    """DEC-19: a control's type ("no type" for null, ruling 21) and the
    runtime judge's recorded view of it, when the answer records them."""
    lines = [json.loads(x) for x in SHOPBOT.read_text(encoding="utf-8").splitlines() if x.strip()]
    classify = next(x for x in lines if x["tool"] == "classify_ai_system")
    backlog = {
        "seq": 3, "ts": classify["ts"], "tool": "generate_control_backlog", "repo_ref": classify["repo_ref"],
        "request": {"norm_ids": ["norm:a:n1"], "system_context": "A shop assistant."},
        "envelope": {
            **{k: v for k, v in classify["envelope"].items() if k != "answer"},
            "judge_verdict": "accepted",
            "status": "applicable_missing_evidence",
            "answer": {
                "tool": "generate_control_backlog",
                "items": [
                    {"title": "Disclose the chatbot", "description": "Show a notice.", "norm_ids": ["norm:a:n1"],
                     "suggested_evidence": [], "priority": "must", "requirement_type": "functional"},
                    {"title": "Keep a record", "description": "Log the notices.", "norm_ids": ["norm:a:n1"],
                     "suggested_evidence": [], "priority": "must", "requirement_type": None},
                ],
                "judge_type_views": [
                    {"judge_type_agrees": False, "judge_requirement_type": "process"},
                    {"judge_type_agrees": None, "judge_requirement_type": None},
                ],
                "dropped_items": 0, "merged_items": 0, "notes": [],
                "judge_model": "m", "judge_effort": "xhigh",
            },
        },
    }
    path = tmp_path / "with_backlog.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in [*lines, backlog]), encoding="utf-8")
    html = _section_body(render_report_from_paths([path]), "backlog")
    assert html.count('requirement type</span> <span class="token"><span class="field" data-envelope-field="requirement_type">functional<') == 1
    assert html.count("no type") == 1
    assert 'judge gives the requirement type</span> <span class="field" data-envelope-field="judge_requirement_type">process<' in html
    # B84 item 1: the judge record names the judge's effort beside its model
    assert ' · effort <span class="field" data-envelope-field="judge_effort">xhigh<' in html


def test_the_alignment_judge_run_line_shows_the_judge_effort(tmp_path: Path) -> None:
    """B84 item 1: the trace_alignment judge run line prints the judge's
    effort; a judge run recorded before B84 has no effort key and shows no
    effort part."""
    lines = [json.loads(x) for x in SHOPBOT.read_text(encoding="utf-8").splitlines() if x.strip()]
    classify = next(x for x in lines if x["tool"] == "classify_ai_system")

    def alignment(seq: int, norm_id: str, judge_run: dict) -> dict:
        assertion = {"source_norm_id": norm_id, "relation_type": "supports", "target_id": "hleg:req:1",
                     "judge_verdict": "accepted", "judge_run": judge_run}
        return {
            "seq": seq, "ts": classify["ts"], "tool": "trace_alignment", "repo_ref": classify["repo_ref"],
            "request": {"id": norm_id},
            "envelope": {
                **{k: v for k, v in classify["envelope"].items() if k != "answer"},
                "answer": {"tool": "trace_alignment", "id": norm_id, "assertions": [assertion]},
            },
        }

    run = {"id": "jr-1", "judge_model": "m", "prompt_version": "v1", "verdict": "accepted"}
    exchanges = [alignment(3, "norm:a:n1", {**run, "judge_effort": "xhigh"}), alignment(4, "norm:b:n1", run)]
    path = tmp_path / "with_alignment.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in [*lines, *exchanges]), encoding="utf-8")
    html = _section_body(render_report_from_paths([path]), "alignment")
    with_effort, without_effort = html.split('data-section="alignment_trace"')[1:]
    assert (
        'data-envelope-field="judge_model">m</span> · effort '
        '<span class="field" data-envelope-field="judge_effort">xhigh<'
    ) in with_effort
    assert 'data-envelope-field="judge_model">m</span> · prompt ' in without_effort
    assert "judge_effort" not in without_effort


def test_old_session_renders_as_not_classified() -> None:
    """B118 (ruling R9): a session recorded before the rename, whose
    classify answer carries an old level, renders as not classified,
    never as a full requirements report."""
    path = (
        Path(__file__).parent.parent
        / "fixtures"
        / "legacy"
        / "moodwatch-prohibited-pre-b118.jsonl"
    )
    html = render_report_from_paths([path])
    assert "is not a level this report knows" in html
    assert "'prohibited'" in html
    assert "applicable requirements returned" not in html
    assert "class=\"prohibition-banner" not in html
    assert "returned" not in html
    # (the fixed status legend names not_applicable; the recorded sections do not)
    for section in ("requirements", "trace_matrix"):
        body = _section_body(html, section)
        assert "not_applicable" not in body
        assert "returned" not in body
    assert "prohibited AI practice" not in html
    assert "not rendered: the recorded classification uses a level" in html


@pytest.mark.parametrize(
    ("value", "tier"),
    [
        ("unacceptable_risk", "prohibited"),
        ("minimal_risk", "minimal"),
        ("high_risk", "full"),
        ("limited_risk", "full"),
        ("undetermined", "uncertain"),
    ],
)
def test_tier_maps_each_current_level(value: str, tier: str) -> None:
    """B118: _tier reads the stored values (the tier names stay private)."""
    from tere4ai.report.ingest import Exchange
    from tere4ai.report.render import _tier

    ex = Exchange(
        seq=0,
        ts="",
        tool="classify_ai_system",
        request={},
        envelope={"status": "ok", "answer": {"risk_category": value}},
        source="t.jsonl",
    )
    assert _tier(ex) == tier


def test_non_string_level_renders_as_not_classified(tmp_path: Path) -> None:
    """B118: a risk_category that is not a string takes the unknown path."""
    lines = SHOPBOT.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["envelope"]["answer"]["risk_category"] = ["high_risk"]
    doctored = tmp_path / "list-level.jsonl"
    doctored.write_text(
        "\n".join([json.dumps(first), *lines[1:]]) + "\n", encoding="utf-8"
    )
    html = render_report_from_paths([doctored])
    assert "is not a level this report knows" in html
    assert "[&#x27;high_risk&#x27;]" in html or "['high_risk']" in html

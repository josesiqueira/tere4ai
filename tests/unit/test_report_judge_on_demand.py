"""DEC-24 (spec G D-G74 (8), rulings S79, S81): the report takes a demo
judge's part as a session line of its own (tool judge_on_demand), attaches
it to the generation its generation id names and shows it beside the
unchanged generator backlog with its label (B138 builds phase 5; evidence
answers keyed by generation id are B140's). Offline, mock data."""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.report import ingest_inputs, render_report_from_paths

SHOPBOT = Path(__file__).parent.parent / "fixtures" / "demo_sessions" / "shopbot-transparency.jsonl"
LABEL = "judged by gpt-6-sol, the generator&#x27;s own family (demo setting)"


def _base() -> tuple[list[dict], dict]:
    lines = [json.loads(x) for x in SHOPBOT.read_text(encoding="utf-8").splitlines() if x.strip()]
    classify = next(x for x in lines if x["tool"] == "classify_ai_system")
    return lines, classify


def _envelope(classify: dict, **over) -> dict:
    return {**{k: v for k, v in classify["envelope"].items() if k != "answer"}, **over}


def _record(gid: str) -> dict:
    return {"generation_id": gid, "format": "tere4ai.signed_answer.v1"}


def _backlog_line(classify: dict, seq: int, gid: str) -> dict:
    return {"seq": seq, "ts": classify["ts"], "tool": "generate_control_backlog", "repo_ref": None,
            "request": {"norm_ids": ["norm:a:n1"], "system_context": "A door."},
            "envelope": _envelope(classify, judge_verdict="not_checked", status="requires_human_review", answer={
                "tool": "generate_control_backlog", "dropped_items": 0, "merged_items": 0, "notes": [],
                "items": [{"title": "Keep a log", "description": "Record events.", "norm_ids": ["norm:a:n1"], "suggested_evidence": [],
                           "priority": "must", "requirement_type": "functional"}],
                "signed_record": _record(gid), "signature": "f" * 64})}


def _judge_line(classify: dict, seq: int, gid: str, tool: str, verdict: str = "accepted", status: str = "applicable_missing_evidence") -> dict:
    return {"seq": seq, "ts": classify["ts"], "tool": "judge_on_demand", "repo_ref": None, "request": {"generation_id": gid},
            "envelope": _envelope(classify, judge_verdict=verdict, status=status, answer={
                "tool": tool, "generation_id": gid, "judge_model": "gpt-6-sol", "judge_effort": "xhigh", "judge_run_id": "judgerun:runtime_grounding:abc",
                "judge_rationale": "Within the cited norms.", "judge_setting": "demo",
                "judge_type_views": [{"judge_type_agrees": False, "judge_requirement_type": "process"}]})}


def _write(tmp_path: Path, *extra: dict) -> Path:
    lines, _ = _base()
    path = tmp_path / "session.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in [*lines, *extra]), encoding="utf-8")
    return path


def _section(html: str, name: str) -> str:
    return html.split(f'data-section="{name}"', 1)[1].split("</section>", 1)[0]


def test_a_backlog_not_judged_reads_not_checked_by_the_judge(tmp_path):
    _, classify = _base()
    html = _section(render_report_from_paths([_write(tmp_path, _backlog_line(classify, 50, "g-1"))]), "backlog")
    assert "not checked by the judge" in html and "judge setting" not in html


def test_the_latest_judge_part_of_a_generation_is_shown_beside_it_with_its_label_and_item_views(tmp_path):
    _, classify = _base()
    path = _write(tmp_path, _backlog_line(classify, 50, "g-1"),
                  _judge_line(classify, 51, "g-1", "generate_control_backlog", "rejected", "requires_human_review"),
                  _judge_line(classify, 52, "g-1", "generate_control_backlog"))
    html = _section(render_report_from_paths([path]), "backlog")
    assert LABEL in html and 'judge setting <span class="field" data-envelope-field="judge_setting">demo<' in html
    assert html.count("judge record") == 1 and ">accepted<" in html and ">rejected<" not in html
    assert 'judge gives the requirement type</span> <span class="field" data-envelope-field="judge_requirement_type">process<' in html
    assert "not checked by the judge" not in html


def test_a_judge_part_without_its_generation_is_shown_apart_and_named(tmp_path):
    _, classify = _base()
    path = _write(tmp_path, _judge_line(classify, 70, "g-missing", "generate_control_backlog"))
    result = ingest_inputs([path])
    assert [ex.seq for ex in result.unattached_judge_parts] == [70]
    html = _section(render_report_from_paths([path]), "judge-parts-apart")
    assert "g-missing" in html and LABEL in html


def _judge_error_line(classify: dict, seq: int, gid: str, tool: str) -> dict:
    line = _judge_line(classify, seq, gid, tool, "judge_error", "requires_human_review")
    answer = line["envelope"]["answer"]
    answer.pop("judge_rationale")
    answer["error"] = "the judge's reply was cut"
    return line


def test_a_judge_error_part_is_captioned_as_an_error_never_as_judged(tmp_path):
    """Ruling R77: a judge request that failed after it was sent is shown
    as an error; the generator's backlog is not shown as judged."""
    _, classify = _base()
    path = _write(tmp_path, _backlog_line(classify, 50, "g-1"),
                  _judge_error_line(classify, 51, "g-1", "generate_control_backlog"))
    html = _section(render_report_from_paths([path]), "backlog")
    assert "the judge failed after its request was sent: the judge&#x27;s reply was cut; not judged (demo setting, gpt-6-sol)" in html
    assert LABEL not in html and "status after the judge" not in html


def test_a_later_judged_part_stands_over_an_earlier_judge_error(tmp_path):
    _, classify = _base()
    path = _write(tmp_path, _backlog_line(classify, 50, "g-1"),
                  _judge_error_line(classify, 51, "g-1", "generate_control_backlog"),
                  _judge_line(classify, 52, "g-1", "generate_control_backlog"))
    html = _section(render_report_from_paths([path]), "backlog")
    assert LABEL in html and ">accepted<" in html and "the judge failed" not in html


def test_a_judge_error_part_apart_is_named_as_an_error(tmp_path):
    _, classify = _base()
    path = _write(tmp_path, _judge_error_line(classify, 70, "g-missing", "generate_control_backlog"))
    html = _section(render_report_from_paths([path]), "judge-parts-apart")
    assert "the judge failed after its request was sent" in html and LABEL not in html

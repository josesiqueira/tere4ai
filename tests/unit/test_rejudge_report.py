"""B173 task 4: `python -m tere4ai.rejudge report` on the Task 3 mock run: the
source build of mock data re-judged by `norms` (C newly accepted, D newly
rejected) and `alignments` (C aligned by the generator, D's assertion
dropped, the first of A's two assertions now rejected). Scripted clients
only, never a paid model call.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20
"""

from __future__ import annotations

import csv

import pytest
from tests.unit.rejudge_mock_build import (
    GENERATOR_MODEL,
    JUDGE_MODEL,
    NEW_NAME,
    NORM_A,
    NORM_C,
    NORM_D,
    SOURCE_JUDGE_MODEL,
    UNIT_OF,
    ScriptedJudge,
    folder_state,
    make_source_build,
    prices,
)
from tests.unit.test_rejudge_cli_alignments import _alignments, _both, _source_alignments

import tere4ai.rejudge.__main__ as cli
import tere4ai.rejudge.report as report

# The quote of A's first source assertion; the new alignment judge rejects it.
A_FIRST_QUOTE = "A risk log shall be kept"


@pytest.fixture
def source(tmp_path):
    src = make_source_build(tmp_path)
    before = folder_state(src)
    yield src
    assert folder_state(src) == before


@pytest.fixture
def rejudged(tmp_path, source, monkeypatch):
    """The mock run, both subcommands; the report reads the test price rows."""
    judge = ScriptedJudge({f'"source_quote": "{A_FIRST_QUOTE}"': "rejected"})
    new_dir, _judge, _generator = _both(tmp_path, source, monkeypatch, judge=judge)
    monkeypatch.setattr(report, "load_model_prices", prices)
    return source, new_dir


def _report(source, new_dir, *extra):
    return cli.main(["report", "--source", str(source), "--out-dir", str(new_dir), "--name", NEW_NAME, *extra])


def _readme(new_dir):
    return (new_dir / "README.md").read_text(encoding="utf-8")


def _csv(new_dir):
    with (new_dir / "changed_verdicts.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def test_the_report_lists_exactly_the_changed_verdicts(rejudged):
    source, new_dir = rejudged
    assert _report(source, new_dir) == 0
    source_assertions = _source_alignments(source)["assertions"]
    a_first = next(a["id"] for a in source_assertions if a["source_quote"] == A_FIRST_QUOTE)
    d_assertion = next(a["id"] for a in source_assertions if a["source_norm_id"] == NORM_D)
    source_ids = {a["id"] for a in source_assertions}
    c_new = [a["id"] for a in _alignments(new_dir)["assertions"] if a["id"] not in source_ids]
    assert len(c_new) == 1
    assert _csv(new_dir) == [
        ["layer", "id", "source_unit_or_norm", "source_verdict", "new_verdict"],
        ["layer2", NORM_C, UNIT_OF[NORM_C], "rejected", "accepted"],
        ["layer2", NORM_D, UNIT_OF[NORM_D], "accepted", "rejected"],
        ["layer3", a_first, NORM_A, "accepted", "rejected"],
        ["layer3", d_assertion, NORM_D, "accepted", "dropped, norm not accepted"],
        ["layer3", c_new[0], NORM_C, "new, norm newly accepted", "accepted"],
    ]
    text = _readme(new_dir)
    assert text.startswith(f"# Build {NEW_NAME}\n\nGenerator output of 2026-10-14-gpt-fake-high, judged by "
                           f"{JUDGE_MODEL} (effort high, temperature 0), made by `python -m tere4ai.rejudge` "
                           "(card B173) on ")
    section = text.split(f"## Verdicts that changed against {SOURCE_JUDGE_MODEL}\n", 1)[1]
    assert (f"| Norm | Source unit | {SOURCE_JUDGE_MODEL} | {JUDGE_MODEL} |\n|---|---|---|---|\n"
            f"| `{NORM_C}` | `{UNIT_OF[NORM_C]}` | rejected | accepted |\n"
            f"| `{NORM_D}` | `{UNIT_OF[NORM_D]}` | accepted | rejected |\n") in section
    assert (f"| Assertion | {SOURCE_JUDGE_MODEL} | {JUDGE_MODEL} |\n|---|---|---|\n"
            f"| `{a_first}` | accepted | rejected |\n") in section
    assert f"| `{d_assertion}` | `{NORM_D}` | accepted | rejected |\n" in section
    assert f"| Norm | New assertions | accepted |\n|---|---|---|\n| `{NORM_C}` | 1 | 1 |\n" in section
    assert "## What it is" in text and "| Build id | not published yet |" in text
    assert "## Counts" in text and "## Files" in text
    # the sections in the order of the brief
    order = ["## What it is", "## Counts", "## Cost, as the inference backends report it",
             f"## Verdicts that changed against {SOURCE_JUDGE_MODEL}", "## Files"]
    assert [text.index(heading) for heading in order] == sorted(text.index(heading) for heading in order)


def test_the_cost_table_uses_the_price_rows(rejudged):
    source, new_dir = rejudged
    assert _report(source, new_dir) == 0
    text = _readme(new_dir)
    # claude-fake 4.00 and 20.00, gpt-fake 10.00 and 50.00 USD per million tokens;
    # every scripted call 1000 input and 100 output tokens.
    # Layer 2 judge: 4 calls, (4000 * 4 + 400 * 20) / 1e6 = 0.024
    # Layer 3 generator: 1 call (C), (1000 * 10 + 100 * 50) / 1e6 = 0.015
    # Layer 3 judge: 3 calls (C's new one, A's two), (3000 * 4 + 300 * 20) / 1e6 = 0.018
    # Total: 8 calls, 0.057
    assert ("| Step | Calls | Input tokens | Output tokens | USD at list price |\n|---|---|---|---|---|\n"
            f"| Layer 2 judge ({JUDGE_MODEL}) | 4 | 4,000 | 400 | 0.0240 |\n"
            f"| Layer 3 generator for newly accepted norms only ({GENERATOR_MODEL}) | 1 | 1,000 | 100 | 0.0150 |\n"
            f"| Layer 3 judge ({JUDGE_MODEL}) | 3 | 3,000 | 300 | 0.0180 |\n"
            "| Total | 8 | 8,000 | 800 | 0.0570 |\n") in text
    assert (f"- {JUDGE_MODEL}: 4.00 USD per million input tokens and 20.00 per million output tokens "
            "(config/model_prices.json, read on 2026-10-15 from https://example.org/pricing)") in text
    assert f"- {GENERATOR_MODEL}: 10.00 USD per million input tokens and 50.00" in text
    # the source's carried generator usage: Layer 2 (9000 * 10 + 1200 * 50) / 1e6 = 0.15,
    # Layer 3 (5000 * 10 + 700 * 50) / 1e6 = 0.085
    assert (f"- Layer 2 generator ({GENERATOR_MODEL}): 4 calls, 9,000 input tokens, 1,200 output tokens, "
            "0.1500 USD at list price") in text
    assert (f"- Layer 3 generator ({GENERATOR_MODEL}): 3 calls, 5,000 input tokens, 700 output tokens, "
            "0.0850 USD at list price") in text
    assert "Cost stop (--cost-stop): 1000.0000 USD." in text
    assert "a run can pass it by at most the group or batch in flight" in text


def test_an_existing_readme_is_not_overwritten_without_the_flag(rejudged, capsys):
    source, new_dir = rejudged
    (new_dir / "README.md").write_text("kept by hand\n", encoding="utf-8")
    assert _report(source, new_dir) == 1
    assert "refusing to overwrite README.md" in capsys.readouterr().err
    assert _readme(new_dir) == "kept by hand\n"
    assert not (new_dir / "changed_verdicts.csv").exists()
    assert _report(source, new_dir, "--overwrite") == 0
    assert _readme(new_dir).startswith(f"# Build {NEW_NAME}\n")
    assert _report(source, new_dir) == 1, "the report just written is not replaced either"


def test_the_report_has_no_em_or_en_dash(rejudged):
    source, new_dir = rejudged
    assert _report(source, new_dir) == 0
    for name in ("README.md", "changed_verdicts.csv"):
        text = (new_dir / name).read_text(encoding="utf-8")
        assert "\u2014" not in text and "\u2013" not in text, name

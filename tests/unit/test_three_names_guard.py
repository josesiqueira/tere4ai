"""B181 (DEC-30): the tool, the keys, the routes and the signed format carry the
three names (applicable requirement, tailored requirement, generation) and no
other. Kept records keep the old words; the files that name an old word on
purpose are listed with their reason."""

import re
import subprocess
from pathlib import Path

import pytest

from tere4ai.mcp_server.classify import PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181
from tere4ai.mcp_server.requirements import (
    PROHIBITED_MESSAGE_BEFORE_B181,
    PROHIBITED_NOTE_BEFORE_B181,
)

ROOT = Path(__file__).resolve().parents[2]
OLD_NAMES = (
    "generate_control_backlog",
    "backlog_paid",
    "api/backlog",
    "dropped_items",
    "merged_items",
    "signed_answer.v1",
    "BACKLOG_CORE_FIELDS",
)
KEPT_AS_RECORDED = (
    "CHANGELOG.md",
    "docs/architecture.md",
    "docs/references.md",
    "data/",
    "eval/results/",
    "eval/gold/",
    "demo/mcp_demo/sessions/",
    "demo/mcp_demo/projects/",
    "tests/fixtures/demo_sessions/",
    "tests/fixtures/legacy/",
) + tuple(f"prompts/{d}/v{n}.md" for d in ("generate_backlog", "runtime_grounding") for n in (1, 2, 3))
# Each names an old word on purpose: the v1 to v3 judge input, the scope
# mapping, the reader of stored records, the rewrite and the tests that pin them.
NAMES_BY_DESIGN = (
    "src/tere4ai/mcp_server/backlog.py",
    "src/tere4ai/mcp_server/keys.py",
    "src/tere4ai/report/ingest.py",
    "scripts/rename_tailored_requirement_keys.py",
    "tests/unit/test_backlog.py",
    "tests/unit/test_mcp_keys.py",
    "tests/unit/test_report.py",
    "tests/unit/test_report_judge_on_demand.py",
    "tests/unit/test_rename_tailored_requirement_keys.py",
    "tests/unit/test_signed_answer.py",
    "tests/unit/test_http_facade_judge_routes.py",
    "tests/unit/test_http_facade.py",
    "tests/unit/test_prompts_v4_three_names.py",
    "tests/unit/test_three_names_guard.py",
)


def test_no_live_file_names_an_old_name():
    for old in OLD_NAMES:
        try:
            out = subprocess.run(["git", "-C", str(ROOT), "grep", "-lzF", old],
                                 capture_output=True, text=True, check=False)
        except OSError:
            pytest.skip("git is not available")
        if out.returncode not in (0, 1):
            pytest.skip("not a git checkout")
        naming = [p for p in out.stdout.split("\0")
                  if p and not p.startswith(KEPT_AS_RECORDED) and p not in NAMES_BY_DESIGN]
        assert naming == [], old


# The old phrases, searched as whole words in the text a person or a model
# reads, string literals split over lines joined first (a check over one line
# at a time missed two live sentences, B181 final review).
OLD_PHRASES = re.compile(
    r"\b(engineering requirements?|control backlogs?|backlog items?|backlog generation)\b",
    re.IGNORECASE,
)
# Two adjacent literals ("a " "b", 'a ' + 'b', "a " f"b") read as one.
_ADJACENT_LITERALS = re.compile(r"""(["'])\s*\+?\s*[rRbBfFuU]{0,2}\1""")
# The sentences recorded sessions keep (DEC-30): each of-record constant's
# definition, and only its definition, is taken out of the text before the
# search, so the same words in a live sentence are still found.
SENTENCES_OF_RECORD = {
    "PROHIBITED_MESSAGE_BEFORE_B181": PROHIBITED_MESSAGE_BEFORE_B181,
    "PROHIBITED_NOTE_BEFORE_B181": PROHIBITED_NOTE_BEFORE_B181,
    "PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181": PROHIBITED_PRACTICE_NOTE_END_BEFORE_B181,
}
# Each names an old phrase on purpose: "backlog item" for a card of the
# project task board, another sense (the plan's Appendix A); the v3-to-v4
# prompt test that lists the old words; this guard.
PHRASES_BY_DESIGN = (
    "docs/DEMO.md",
    "tests/unit/test_prompts_v4_three_names.py",
    "tests/unit/test_three_names_guard.py",
)


def _read_as_one_line(text: str) -> str:
    return re.sub(r"\s+", " ", _ADJACENT_LITERALS.sub("", text))


def test_the_split_string_reader_joins_literals_across_lines():
    source = 'note = (\n    "no engineering "\n    "requirements are generated"\n)\n'
    assert OLD_PHRASES.search(_read_as_one_line(source))
    assert OLD_PHRASES.search(_read_as_one_line("so no engineering\n  requirement can"))
    assert OLD_PHRASES.search(_read_as_one_line("label = 'Control ' +\n  'backlog';"))


def test_only_the_definition_of_a_sentence_of_record_is_left_out():
    name, sentence = "PROHIBITED_NOTE_BEFORE_B181", PROHIBITED_NOTE_BEFORE_B181
    definition = _read_as_one_line(f'{name} = (\n    "{sentence}"\n)\n')
    assert not OLD_PHRASES.search(definition.replace(f'{name} = ( "{sentence}" )', ""))
    live = _read_as_one_line(f'notes = [f"{{n}}: {sentence}"]\n')
    assert OLD_PHRASES.search(live.replace(f'{name} = ( "{sentence}" )', ""))


def test_no_live_file_names_an_old_phrase_even_split_over_lines():
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*.py", "*.ts", "*.tsx", "*.md"],
            capture_output=True, text=True, check=False)
    except OSError:
        pytest.skip("git is not available")
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    of_record = [f'{name} = ( "{sentence}" )' for name, sentence in SENTENCES_OF_RECORD.items()]
    naming = {}
    for rel in out.stdout.split("\0"):
        if not rel or rel.startswith(KEPT_AS_RECORDED) or rel in PHRASES_BY_DESIGN:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = _read_as_one_line(path.read_text(encoding="utf-8", errors="replace"))
        for definition in of_record:
            text = text.replace(definition, "")
        hits = sorted({m.group(0).lower() for m in OLD_PHRASES.finditer(text)})
        if hits:
            naming[rel] = hits
    assert naming == {}

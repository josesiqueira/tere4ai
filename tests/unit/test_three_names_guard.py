"""B181 (DEC-30): the tool, the keys, the routes and the signed format carry the
three names (applicable requirement, tailored requirement, generation) and no
other. Kept records keep the old words; the files that name an old word on
purpose are listed with their reason."""

import subprocess
from pathlib import Path

import pytest

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

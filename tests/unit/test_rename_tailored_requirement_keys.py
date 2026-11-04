"""The one-off rewrite of a kept file to the tailored requirement keys (B181, DEC-30, R11, R16).

Mock data in tmp_path only; the script is run as the command line runs it.
"""

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rename_tailored_requirement_keys.py"

OLD_TOOL = "generate_control_backlog"
NEW_TOOL = "generate_tailored_requirements"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def _entries() -> list[dict]:
    return [
        {"title": f"Tailored requirement {n}", "description": f"Do the thing {n}, the provider’s duty.",
         "norm_ids": [f"norm:a:n{n}"], "suggested_evidence": ["a document"], "priority": "must"}
        for n in range(1, 7)
    ]


def _kept_envelope() -> dict:
    """The shape of the kept file recorded on 2026-08-24: the old tool name,
    the three old keys and truncated beside them."""
    return {
        "answer": {
            "tool": OLD_TOOL,
            "items": _entries(),
            "dropped_items": 0,
            "merged_items": 0,
            "truncated": False,
            "notes": [],
            "judge_rationale": "Within the cited norms.",
        },
        "status": "applicable_missing_evidence",
        "judge_verdict": "accepted",
    }


def test_the_script_renames_the_keys_and_the_tool_and_proves_it(tmp_path):
    path = tmp_path / "highrisk-backlog-article9.json"
    # The kept file's form: indent 2, non-ASCII written as \u escapes.
    path.write_text(json.dumps(_kept_envelope(), indent=2) + "\n", encoding="utf-8")
    before = path.read_bytes()

    done = _run(path)

    assert done.returncode == 0, done.stderr
    after = json.loads(path.read_text(encoding="utf-8"))
    answer = after["answer"]
    assert answer["tool"] == NEW_TOOL
    assert answer["tailored_requirements"] == _entries()
    assert answer["dropped_tailored_requirements"] == 0 and answer["merged_tailored_requirements"] == 0
    assert answer["truncated"] is False
    assert not {"items", "dropped_items", "merged_items"} & answer.keys()
    differences = [line for line in done.stdout.splitlines() if line.startswith("difference: ")]
    assert differences == [
        "difference: answer.tool from 'generate_control_backlog' to 'generate_tailored_requirements'",
        "difference: answer.items renamed answer.tailored_requirements, the value unchanged",
        "difference: answer.dropped_items renamed answer.dropped_tailored_requirements, the value unchanged",
        "difference: answer.merged_items renamed answer.merged_tailored_requirements, the value unchanged",
    ]
    assert f"sha256 before: {hashlib.sha256(before).hexdigest()}" in done.stdout
    assert f"sha256 after: {hashlib.sha256(path.read_bytes()).hexdigest()}" in done.stdout
    copy = tmp_path / "highrisk-backlog-article9.pre-B181.json"
    assert copy.read_bytes() == before
    # Every other byte is as it was: the keys keep their places, the indent
    # and the escapes their form.
    expected = (
        before.replace(b'"tool": "generate_control_backlog"', b'"tool": "generate_tailored_requirements"')
        .replace(b'"items":', b'"tailored_requirements":')
        .replace(b'"dropped_items":', b'"dropped_tailored_requirements":')
        .replace(b'"merged_items":', b'"merged_tailored_requirements":')
    )
    assert path.read_bytes() == expected


def test_a_file_without_the_old_keys_is_refused_and_untouched(tmp_path):
    path = tmp_path / "new.json"
    envelope = _kept_envelope()
    answer = envelope["answer"]
    answer["tool"] = NEW_TOOL
    answer["tailored_requirements"] = answer.pop("items")
    del answer["dropped_items"], answer["merged_items"]
    path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    before = path.read_bytes()

    done = _run(path)

    assert done.returncode == 2
    assert "nothing to rename" in done.stderr
    assert path.read_bytes() == before
    assert not (tmp_path / "new.pre-B181.json").exists()

    # A rename that would drop a value (an old key beside its new one) is a
    # difference the script does not allow: refused, the file untouched.
    both = tmp_path / "both.json"
    answer["items"] = [{"title": "an older entry"}]
    both.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    before = both.read_bytes()

    done = _run(both)

    assert done.returncode == 2
    assert "not a rename" in done.stderr
    assert both.read_bytes() == before
    assert not (tmp_path / "both.pre-B181.json").exists()


def test_a_second_run_is_refused(tmp_path):
    path = tmp_path / "kept.json"
    path.write_text(json.dumps(_kept_envelope(), indent=2) + "\n", encoding="utf-8")
    assert _run(path).returncode == 0
    rewritten = path.read_bytes()

    done = _run(path)

    assert done.returncode == 2
    assert "nothing to rename" in done.stderr
    assert path.read_bytes() == rewritten


def test_an_existing_copy_of_the_original_refuses_the_run_and_nothing_is_written(tmp_path):
    path = tmp_path / "kept.json"
    path.write_text(json.dumps(_kept_envelope(), indent=2) + "\n", encoding="utf-8")
    copy = tmp_path / "kept.pre-B181.json"
    copy.write_bytes(b"an earlier copy")
    before = path.read_bytes()

    done = _run(path)

    assert done.returncode == 2
    assert "kept.pre-B181.json already exists" in done.stderr
    assert path.read_bytes() == before
    assert copy.read_bytes() == b"an earlier copy"


def test_the_rewritten_file_and_its_copy_keep_the_input_files_mode(tmp_path):
    path = tmp_path / "kept.json"
    path.write_text(json.dumps(_kept_envelope(), indent=2) + "\n", encoding="utf-8")
    path.chmod(0o664)

    assert _run(path).returncode == 0

    assert stat.S_IMODE(path.stat().st_mode) == 0o664
    assert stat.S_IMODE((tmp_path / "kept.pre-B181.json").stat().st_mode) == 0o664

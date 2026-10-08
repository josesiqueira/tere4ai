import json
import subprocess
import sys
from pathlib import Path

import pytest

from tere4ai.graph_store.build_record import STEP_IDS, BuildRecordStore, RecordError

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rename_build_record_steps.py"
OLD = {"LAYER0_STEP1": "L0.1", "LAYER1_STEP1": "L1.1", "LAYER2_STEP1": "L2.1", "LAYER2_STEP2": "L2.2", "LAYER2_STEP3": "L2.3",
       "LAYER2_STEP4": "L2.4", "LAYER3_STEP1": "L3.1", "LAYER3_STEP2": "L3.2", "LAYER3_STEP3": "L3.3", "LAYER3_STEP4": "L3.4",
       "LAYER3_STEP5": "L3.5", "PUBLICATION_STEP1": "P.1", "PUBLICATION_STEP2": "P.2"}


def _old_shape(tmp_path):
    store = BuildRecordStore(tmp_path)
    rid = store.create_record("old.alias", None, "abc")
    # The step ids live in each execution's covers_steps; one execution covers all thirteen.
    store.start_execution(rid, command="parse_legal_structure", covers_steps=list(STEP_IDS), argv=[], inputs=[],
                          config={}, expected_total=None, work_unit=None, checkpoint_file=None)
    path = tmp_path / "build_records" / f"{rid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = "build_record.v1"
    for ex in data["executions"]:
        ex["covers_steps"] = [OLD[k] for k in ex["covers_steps"]]
        # A file name that happens to carry an old step token is not a step id.
        ex["outputs"] = [{"role": "norms", "file": "norms-L2.1.json", "sha256": "0" * 64}]
    path.write_text(json.dumps(data), encoding="utf-8")
    return store, rid, path


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_the_old_shape_is_refused_before_the_rewrite(tmp_path):
    store, rid, _ = _old_shape(tmp_path)
    with pytest.raises(RecordError):
        store.read(rid)


def test_rewrites_keys_and_version_once_and_the_record_reads_again(tmp_path):
    store, rid, path = _old_shape(tmp_path)
    out = _run(tmp_path / "build_records")
    assert out.returncode == 0 and f"{rid}.json" in out.stdout
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.read_text(encoding="utf-8") == json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    covered = data["executions"][0]["covers_steps"]
    assert data["schema_version"] == "build_record.v2" and covered == list(STEP_IDS) and "L0.1" not in covered
    assert data["executions"][0]["outputs"][0]["file"] == "norms-L2.1.json"
    assert store.read(rid)["record_id"] == rid
    again = _run(tmp_path / "build_records")
    assert again.returncode == 0 and f"{rid}.json" not in again.stdout


def test_a_file_that_is_not_json_is_reported_and_skipped_and_the_run_exits_1(tmp_path):
    store, rid, path = _old_shape(tmp_path)
    bad = tmp_path / "build_records" / "tmp123.json"
    bad.write_text("{", encoding="utf-8")
    out = _run(tmp_path / "build_records")
    assert out.returncode == 1 and f"{rid}.json" in out.stdout
    assert "skipped tmp123.json:" in out.stderr and "Traceback" not in out.stderr
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "build_record.v2"
    assert store.read(rid)["record_id"] == rid and bad.read_text(encoding="utf-8") == "{"


def test_a_file_of_bytes_that_are_not_utf8_is_reported_and_skipped(tmp_path):
    store, rid, path = _old_shape(tmp_path)
    bad = tmp_path / "build_records" / "broken.json"
    bad.write_bytes(b"\xff\xfe\x00not utf-8")
    out = _run(tmp_path / "build_records")
    assert out.returncode == 1 and f"{rid}.json" in out.stdout
    assert "skipped broken.json:" in out.stderr and "Traceback" not in out.stderr
    assert store.read(rid)["record_id"] == rid and bad.read_bytes() == b"\xff\xfe\x00not utf-8"


def test_only_step_keys_and_covers_steps_are_renamed(tmp_path):
    d = tmp_path / "records"
    d.mkdir()
    presented = d / "presented.json"
    presented.write_text(json.dumps({
        "alias": "core.L2.1", "steps": {"L2.1": {"state": "done"}, "P.1": {"state": "not_started"}},
        "executions": [{"covers_steps": ["L3.5"], "note": "L3.5 ran", "checkpoint_file": "align-L3.1.jsonl"}],
    }), encoding="utf-8")
    aliases = d / "aliases.json"
    aliases.write_text(json.dumps({"core.L2.1": "abc", "core.L2.2": "def"}), encoding="utf-8")
    out = _run(d)
    assert out.returncode == 0
    data = json.loads(presented.read_text(encoding="utf-8"))
    assert data["steps"] == {"LAYER2_STEP1": {"state": "done"}, "PUBLICATION_STEP1": {"state": "not_started"}}
    assert data["executions"][0] == {"covers_steps": ["LAYER3_STEP5"], "note": "L3.5 ran",
                                     "checkpoint_file": "align-L3.1.jsonl"}
    assert data["alias"] == "core.L2.1"
    assert json.loads(aliases.read_text(encoding="utf-8")) == {"core.L2.1": "abc", "core.L2.2": "def"}
    assert "aliases.json" not in out.stdout


@pytest.mark.parametrize("args", [[], ["one", "two"]])
def test_anything_but_one_argument_prints_the_usage_and_exits_2(args):
    out = _run(*args)
    assert out.returncode == 2 and out.stderr.startswith("usage:") and "Traceback" not in out.stderr


def test_a_directory_that_does_not_exist_prints_the_usage_and_exits_2(tmp_path):
    out = _run(tmp_path / "no_such_dir")
    assert out.returncode == 2 and out.stderr.startswith("usage:") and out.stdout == ""


def test_the_script_finds_the_package_without_an_installed_copy(tmp_path):
    """python3 -I scripts/... from an interpreter where tere4ai is not installed:
    the src entry the editable install adds is removed before the script runs."""
    _, rid, _ = _old_shape(tmp_path)
    code = (
        "import runpy, sys; "
        f"src = {str(ROOT / 'src')!r}; "
        "sys.path[:] = [p for p in sys.path if p.rstrip('/') != src]; "
        f"sys.argv = [{str(SCRIPT)!r}, {str(tmp_path / 'build_records')!r}]; "
        f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert out.returncode == 0 and f"{rid}.json" in out.stdout, out.stderr

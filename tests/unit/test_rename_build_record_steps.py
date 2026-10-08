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
    path.write_text(json.dumps(data), encoding="utf-8")
    return store, rid, path


def _run(d):
    return subprocess.run([sys.executable, str(SCRIPT), str(d)], capture_output=True, text=True)


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

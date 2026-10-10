"""The one-off rewrite of stored records to the input and output kind keys (B158, spec G D-G81 (6))."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rename_record_kinds.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def test_inputs_and_outputs_take_their_kind_keys_and_the_versions_move(tmp_path):
    chain = {"build_id": "b+chain-x", "chain_id": "x", "inputs": [{"role": "layer1_dump", "file": "layer1.json", "sha256": "a" * 64}]}
    (tmp_path / "build_chain_x.json").write_text(json.dumps(chain, indent=2), encoding="utf-8")
    rec = {"schema_version": "build_record.v2", "record_id": "r", "executions": [{
        "inputs": [{"role": "norms", "file": "n.json", "sha256": "b" * 64}],
        "outputs": [{"role": "build_chain", "file": "build_chain_x.json", "sha256": "0" * 64}]}]}
    (tmp_path / "build_records").mkdir()
    (tmp_path / "build_records" / "r.json").write_text(json.dumps(rec), encoding="utf-8")
    ev = {"schema_version": "evaluation_record.v1", "record_id": "e", "kind": "sample",
          "inputs": [{"role": "benchmark", "file": "b.json", "sha256": "c" * 64}],
          "outputs": [{"role": "summary", "file": "s.json", "sha256": "d" * 64, "copy": None}]}
    (tmp_path / "e.json").write_text(json.dumps(ev), encoding="utf-8")
    result = _run(tmp_path / "build_chain_x.json", tmp_path / "build_records" / "r.json", tmp_path / "e.json", "--dump-dir", tmp_path)
    assert result.returncode == 0, result.stderr
    out_chain = json.loads((tmp_path / "build_chain_x.json").read_text(encoding="utf-8"))
    assert out_chain["inputs"] == [{"input_kind": "layer1_dump", "file": "layer1.json", "sha256": "a" * 64}]
    out = json.loads((tmp_path / "build_records" / "r.json").read_text(encoding="utf-8"))
    assert out["schema_version"] == "build_record.v3"
    ex = out["executions"][0]
    assert ex["inputs"] == [{"input_kind": "norms", "file": "n.json", "sha256": "b" * 64}]
    digest = hashlib.sha256((tmp_path / "build_chain_x.json").read_bytes()).hexdigest()
    assert ex["outputs"] == [{"output_kind": "build_chain", "file": "build_chain_x.json", "sha256": digest}]
    out_ev = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert out_ev["schema_version"] == "evaluation_record.v2"
    assert out_ev["kind"] == "sample"
    assert out_ev["inputs"][0] == {"input_kind": "benchmark", "file": "b.json", "sha256": "c" * 64}
    assert out_ev["outputs"][0] == {"output_kind": "summary", "file": "s.json", "sha256": "d" * 64, "copy": None}


def test_a_second_run_changes_nothing(tmp_path):
    chain = {"chain_id": "x", "inputs": [{"input_kind": "norms", "file": "n.json", "sha256": "a" * 64}]}
    path = tmp_path / "build_chain_x.json"
    path.write_text(json.dumps(chain, indent=2), encoding="utf-8")
    before = path.read_bytes()
    assert _run(path, "--dump-dir", tmp_path).returncode == 0
    assert path.read_bytes() == before

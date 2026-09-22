"""Materialise a freeze's decisions exactly once into a reference file (D-G27)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.review_queue.materialize import (
    MaterializeError,
    already_materialised,
    materialize,
    verify_freeze_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
NORM = {
    "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1", "layer": 2, "type": "NormativeStatement",
    "source_node_id": "eu-ai-act:article-9:paragraph-1", "source_span_id": "span:x", "deontic_type": "obligation",
    "modal": "shall", "actor_explicit": "providers", "actor_inferred": None, "actor_inference_source_node_id": None,
    "action": "establish", "object": "a risk management system", "conditions": [], "exceptions": [],
    "condition_ids": [], "exception_ids": [], "lifecycle_phase_ids": [], "extraction_method": "llm_extract_v1",
    "extractor_model": "g", "extractor_prompt_version": "v1", "confidence": 0.9, "judge_verdict": "accepted",
    "judge_run_id": "judgerun:x", "review_status": "accepted",
}


def _decisions(tmp_path, entries=None):
    p = tmp_path / "decisions.json"
    p.write_text(json.dumps(entries if entries is not None else {
        NORM["norm_id"]: {"decision": "reject", "rationale": "not a norm", "reviewer": "adj",
                          "decided_at": "2026-09-19T00:00:00+00:00"}}))
    return p


def _manifest(decisions_path, **over):
    m = {"schema_version": "freeze_manifest.v1", "campaign_type": "layer2_annotation", "campaign_id": "c1",
         "freeze_id": "f1", "stage": "production", "round": None, "pinned_build_id": "build-b+chain-000000000000",
         "guideline_version": "v1", "scope_core_nodes": ["eu-ai-act:article-9"], "units_in_scope": 1,
         "units_adjudicated": 1, "units_undecided": 0, "rows_included": ["row1"],
         "decisions_sha256": sha256_of_file(decisions_path), "frozen_at": "2026-09-19T00:00:00+00:00"}
    m.update(over)
    return m


def _cli():
    spec = importlib.util.spec_from_file_location("materialize_reference", ROOT / "scripts" / "materialize_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_manifest_types_digest_and_pinned_build(tmp_path):
    d = _decisions(tmp_path)
    verify_freeze_manifest(_manifest(d), d, expected_pinned_build_id="build-b+chain-000000000000")
    with pytest.raises(MaterializeError, match="decisions_sha256"):
        verify_freeze_manifest(_manifest(d, decisions_sha256="0" * 64), d, expected_pinned_build_id=None)
    with pytest.raises(MaterializeError, match="taken on build"):
        verify_freeze_manifest(_manifest(d), d, expected_pinned_build_id="build-b+chain-111111111111")
    with pytest.raises(MaterializeError, match="campaign_type"):
        verify_freeze_manifest(_manifest(d, campaign_type="other"), d, expected_pinned_build_id=None)
    with pytest.raises(MaterializeError, match="rows_included"):
        m = _manifest(d)
        del m["rows_included"]
        verify_freeze_manifest(m, d, expected_pinned_build_id=None)
    hleg = {"schema_version": "freeze_manifest.v1", "campaign_type": "hleg_alignment", "campaign_id": "c", "freeze_id": "f",
            "pinned_build_id": "b", "rows_included": [], "verdicts_sha256": "v" * 64, "decisions_sha256": None,
            "frozen_at": "t"}
    verify_freeze_manifest(hleg, None, expected_pinned_build_id=None)
    with pytest.raises(MaterializeError, match="sub-project 4"):
        verify_freeze_manifest(hleg, d, expected_pinned_build_id=None)


def test_materialize_applies_once_and_stamps_the_reference_block(tmp_path):
    d = _decisions(tmp_path)
    pristine = {"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}
    out = materialize("norms", pristine, json.loads(d.read_text()), _manifest(d), source_sha256="s" * 64,
                      source_build_id="build-b+chain-000000000000", decisions_sha256=sha256_of_file(d))
    assert out["norms"][0]["judge_verdict"] == "rejected" and pristine["norms"][0]["judge_verdict"] == "accepted"
    ref = out["build"]["reference"]
    assert ref["kind"] == "norms" and ref["layer"] == 2 and ref["decisions_applied"] == 1 and ref["freeze_id"] == "f1"
    assert ref["source_build_id"] == "build-b+chain-000000000000" and ref["scope_core_nodes"] == ["eu-ai-act:article-9"]
    assert already_materialised(out) and not already_materialised(pristine)
    with pytest.raises(MaterializeError, match="already"):
        materialize("norms", out, json.loads(d.read_text()), _manifest(d), source_sha256="s" * 64,
                    source_build_id="x", decisions_sha256=sha256_of_file(d))
    with pytest.raises(MaterializeError, match="no decisions"):
        materialize("norms", pristine, {}, _manifest(d), source_sha256="s" * 64, source_build_id="x", decisions_sha256="e" * 64)


def test_cli_refuses_aliasing_and_existing_output(tmp_path, capsys):
    cli = _cli()
    d = _decisions(tmp_path)
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    m = tmp_path / "freeze.json"
    m.write_text(json.dumps(_manifest(d)))
    common = ["--pristine", str(pristine), "--decisions", str(d), "--manifest", str(m), "--source-build-id", "build-b+chain-000000000000"]
    assert cli.main(common + ["--out", str(pristine)]) == 1 and "same file" in capsys.readouterr().err
    existing = tmp_path / "norms_core.reference.json"
    existing.write_text("{}")
    assert cli.main(common) == 1 and "exists" in capsys.readouterr().err
    assert existing.read_text() == "{}", "nothing overwritten"


def test_cli_writes_reference_as_descendant_of_the_published_record(tmp_path):
    cli = _cli()
    d = _decisions(tmp_path)
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    store = BuildRecordStore(tmp_path)
    src = store.create_record("core", "build-b", None)
    run = store.start_execution(src, command="extract_norms", covers_steps=["L2.1", "L2.2"], argv=[], inputs=[], config={},
                                expected_total=1, work_unit="groups", checkpoint_file=None)
    store.finish_execution(src, run, status="done", outputs=[{"role": "norms", "file": "norms_core.json", "sha256": sha256_of_file(pristine)}])
    store.set_publication(src, {"chain_id": "0" * 12, "build_id": "build-b+chain-000000000000", "published_at": "t",
                               "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [],
                               "postload_gates": [], "manifests": []})
    m = tmp_path / "freeze.json"
    m.write_text(json.dumps(_manifest(d)))
    rc = cli.main(["--pristine", str(pristine), "--decisions", str(d), "--manifest", str(m)])
    assert rc == 0
    out = tmp_path / "norms_core.reference.json"
    written = json.loads(out.read_text())
    assert written["build"]["reference"]["source_sha256"] == sha256_of_file(pristine)
    child = store.resolve("core.reference")
    assert store.read(child)["parent_record_id"] == src
    ex = store.read(child)["executions"][0]
    assert ex["command"] == "materialize_reference" and ex["covers_steps"] == ["L2.4"] and ex["status"] == "done"
    assert {i["role"] for i in ex["inputs"]} == {"norms", "decisions", "freeze_manifest"}
    assert ex["outputs"][0] == {"role": "norms_reference", "file": out.name, "sha256": sha256_of_file(out)}
    assert store.find_by_output_digest(sha256_of_file(out)) == child


def test_cli_refuses_a_freeze_pinned_to_another_build(tmp_path, capsys):
    cli = _cli()
    d = _decisions(tmp_path)
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    m = tmp_path / "freeze.json"
    m.write_text(json.dumps(_manifest(d, pinned_build_id="build-b+chain-999999999999")))
    rc = cli.main(["--pristine", str(pristine), "--decisions", str(d), "--manifest", str(m), "--source-build-id", "build-b+chain-000000000000"])
    assert rc == 1 and "taken on build" in capsys.readouterr().err


def test_cli_records_failed_on_any_exception_and_reraises(tmp_path, monkeypatch):
    cli = _cli()
    d = _decisions(tmp_path)
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    m = tmp_path / "freeze.json"
    m.write_text(json.dumps(_manifest(d)))

    def _boom(*args, **kwargs):
        raise KeyError("boom")

    monkeypatch.setattr(cli, "materialize", _boom)
    with pytest.raises(KeyError):
        cli.main(["--pristine", str(pristine), "--decisions", str(d), "--manifest", str(m),
                  "--source-build-id", "build-b+chain-000000000000"])
    out = tmp_path / "norms_core.reference.json"
    assert not out.exists()
    store = BuildRecordStore(tmp_path)
    record_id = store.resolve("core.reference")
    ex = store.read(record_id)["executions"][-1]
    assert ex["status"] == "failed" and "boom" in ex["error"]


def test_cli_refuses_a_missing_decisions_file(tmp_path, capsys):
    cli = _cli()
    pristine = tmp_path / "norms_core.json"
    pristine.write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [dict(NORM)], "judge_runs": []}))
    missing_decisions = tmp_path / "missing_decisions.json"
    m = tmp_path / "freeze.json"
    m.write_text(json.dumps({
        "schema_version": "freeze_manifest.v1", "campaign_type": "layer2_annotation", "campaign_id": "c1",
        "freeze_id": "f1", "stage": "production", "round": None, "pinned_build_id": "build-b+chain-000000000000",
        "guideline_version": "v1", "scope_core_nodes": ["eu-ai-act:article-9"], "units_in_scope": 1,
        "units_adjudicated": 1, "units_undecided": 0, "rows_included": ["row1"], "decisions_sha256": "0" * 64,
        "frozen_at": "2026-09-19T00:00:00+00:00",
    }))
    rc = cli.main(["--pristine", str(pristine), "--decisions", str(missing_decisions), "--manifest", str(m),
                  "--source-build-id", "build-b+chain-000000000000"])
    assert rc == 1 and "file not found" in capsys.readouterr().err
    assert not (tmp_path / "norms_core.reference.json").exists()


def test_materialize_refuses_a_freeze_of_the_other_kind(tmp_path):
    d = _decisions(tmp_path)
    pristine = {"build": {"build_id": "build-b"}, "assertions": [], "mapping_runs": [], "judge_runs": []}
    with pytest.raises(MaterializeError, match="f1.*alignments.*hleg_alignment.*layer2_annotation"):
        materialize("alignments", pristine, json.loads(d.read_text()), _manifest(d), source_sha256="s" * 64,
                    source_build_id="build-b+chain-000000000000", decisions_sha256=sha256_of_file(d))

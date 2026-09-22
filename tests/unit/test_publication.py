"""Publication evidence: gating per layer, manifest binding, the whole-build label, the target state (D-G21, D-G27)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tere4ai.graph_store.build_chain import build_chain, served_build_id
from tere4ai.graph_store.publication import (
    ACTIVE_POINTER,
    ActivationError,
    PublicationError,
    activate,
    active_manifest,
    bind_manifests,
    gating_of,
    load_active,
    read_target_state,
    set_target_state,
    whole_build_label,
    write_publication_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def _ref(freeze="f1", kind="norms", digest="d" * 64, ctype="layer2_annotation", source="build-b+chain-000000000000"):
    return {"kind": kind, "layer": 2 if kind == "norms" else 3, "campaign_id": "c", "freeze_id": freeze,
            "campaign_type": ctype, "decisions_sha256": digest, "source_build_id": source}


def _manifest(freeze="f1", stage="production", undecided=0, adjudicated=1, in_scope=1, digest="d" * 64,
              ctype="layer2_annotation", scope=("eu-ai-act:article-9",), pinned="build-b+chain-000000000000"):
    return {"campaign_id": "c", "freeze_id": freeze, "campaign_type": ctype, "stage": stage, "units_undecided": undecided,
            "units_adjudicated": adjudicated, "units_in_scope": in_scope, "decisions_sha256": digest,
            "scope_core_nodes": list(scope), "pinned_build_id": pinned}


def test_gating_reads_the_reference_blocks():
    assert gating_of({"build": {}}, None) == {"layer2": "llm", "layer3": "absent"}
    assert gating_of({"build": {"reference": _ref()}}, {"build": {}}) == {"layer2": "human", "layer3": "llm"}
    assert gating_of({"build": {"reference": _ref()}}, {"build": {"reference": _ref(kind="alignments", ctype="hleg_alignment")}}) == {"layer2": "human", "layer3": "human"}


def test_bind_manifests_requires_exactly_one_match_per_reference():
    bound = bind_manifests([_ref()], [_manifest()])
    keys = ("campaign_id", "freeze_id", "campaign_type", "stage", "decisions_sha256", "layer")
    assert {k: bound[0][k] for k in keys} == {"campaign_id": "c", "freeze_id": "f1", "campaign_type": "layer2_annotation",
                                            "stage": "production", "decisions_sha256": "d" * 64, "layer": 2}
    assert bound[0]["units_in_scope"] == 1
    with pytest.raises(PublicationError, match="pinned"):
        bind_manifests([_ref()], [_manifest(pinned="other-build")])
    with pytest.raises(PublicationError, match="f1"):
        bind_manifests([_ref()], [])
    with pytest.raises(PublicationError, match="f2"):
        bind_manifests([_ref()], [_manifest(), _manifest(freeze="f2")])
    with pytest.raises(PublicationError, match="digest"):
        bind_manifests([_ref()], [_manifest(digest="e" * 64)])
    with pytest.raises(PublicationError, match="twice"):
        bind_manifests([_ref()], [_manifest(), _manifest()])


def test_whole_build_label_needs_both_layers_production_complete_and_in_scope():
    core = ["eu-ai-act:article-9"]
    l2 = {**_manifest(), "layer": 2}
    # The Layer 3 manifest is synthetic: a schema-valid HLEG freeze carries no stage or units until sub-project 4.
    l3 = {**_manifest(freeze="f3", ctype="hleg_alignment"), "layer": 3}
    assert whole_build_label({"layer2": "llm", "layer3": "llm"}, [], core) == "llm-gated"
    assert whole_build_label({"layer2": "llm", "layer3": "absent"}, [], core) is None
    assert whole_build_label({"layer2": "human", "layer3": "llm"}, [l2], core) is None, "intermediate build"
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [l2, l3], core) == "human-adjudicated"
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [{**l2, "stage": "pilot"}, l3], core) is None
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [{**l2, "units_undecided": 1}, l3], core) is None
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [{**l2, "units_adjudicated": 0}, l3], core) is None
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [{**l2, "scope_core_nodes": ["x"]}, l3], core) is None
    assert whole_build_label({"layer2": "human", "layer3": "human"}, [l2], core) is None, "one manifest cannot cover two layers"


def test_target_state_round_trip(tmp_path):
    assert read_target_state(tmp_path) is None
    set_target_state(tmp_path, state="loading", build_id="b", uri="bolt://x", reason=None)
    assert read_target_state(tmp_path)["state"] == "loading"
    set_target_state(tmp_path, state="unavailable", build_id="b", uri="bolt://x", reason="P1 failed")
    state = read_target_state(tmp_path)
    assert state["state"] == "unavailable" and state["reason"] == "P1 failed" and state["since"]


def test_target_state_records_no_credentials(tmp_path):
    set_target_state(tmp_path, state="loading", build_id="b", uri="neo4j+s://neo4j:hunter2@db.example:7687/x?y=1", reason=None)
    assert read_target_state(tmp_path)["uri"] == "neo4j+s://db.example:7687"
    assert "hunter2" not in (tmp_path / "NEO4J_TARGET.json").read_text()


def test_one_manifest_binds_one_reference_of_its_own_kind():
    norms_ref = _ref()
    align_ref = {**_ref(kind="alignments"), "campaign_type": "layer2_annotation"}
    with pytest.raises(PublicationError, match="f1 is bound to two reference blocks"):
        bind_manifests([norms_ref, align_ref], [_manifest()])
    with pytest.raises(PublicationError, match="f1.*alignments.*hleg_alignment.*layer2_annotation"):
        bind_manifests([align_ref], [_manifest()])


def _dumps(tmp_path):
    files = {}
    for role, name, payload in (("layer1_dump", "layer1.json", {"build": {"build_id": "build-b"}, "nodes": [], "edges": []}),
                                ("norms", "norms_core.json", {"build": {"build_id": "build-b"}, "norms": []}),
                                ("alignments", "alignments_core.json", {"build": {"build_id": "build-b"}, "assertions": []})):
        p = tmp_path / name
        p.write_text(json.dumps(payload))
        files[role] = p
    return files


def _publish_fixture(tmp_path, files):
    chain = build_chain(files["layer1_dump"], files["norms"], alignments_path=files["alignments"])
    publication = {"chain_id": chain["chain_id"], "build_id": "build-b+chain-" + chain["chain_id"], "published_at": "t",
                   "gating": {"layer2": "llm", "layer3": "llm"}, "label": "llm-gated", "gates": [], "postload_gates": [],
                   "manifests": []}
    write_publication_manifest(tmp_path, publication, record_id="r", inputs=chain["inputs"],
                               files={"layer1_dump": "layer1.json", "norms": "norms_core.json", "alignments": "alignments_core.json"})
    return chain["chain_id"]


def test_activate_verifies_and_writes_the_pointer(tmp_path):
    files = _dumps(tmp_path)
    chain_id = _publish_fixture(tmp_path, files)
    with pytest.raises(ActivationError, match="no publication"):
        activate(tmp_path, "000000000000")
    assert activate(tmp_path, chain_id)["chain_id"] == chain_id
    assert active_manifest(tmp_path)["chain_id"] == chain_id
    files["norms"].write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [1]}))
    with pytest.raises(ActivationError, match="norms"):
        activate(tmp_path, chain_id)


def test_load_active_prefers_the_pointer_and_falls_back_to_legacy(tmp_path):
    files = _dumps(tmp_path)
    legacy = load_active(tmp_path)
    assert legacy.source == "legacy" and legacy.error is None and legacy.build_id == served_build_id(tmp_path, "build-b")
    chain_id = _publish_fixture(tmp_path, files)
    activate(tmp_path, chain_id)
    loaded = load_active(tmp_path)
    assert loaded.source == "manifest" and loaded.build_id == "build-b+chain-" + chain_id
    assert loaded.norms["build"]["build_id"] == loaded.build_id and loaded.alignments is not None
    assert served_build_id(tmp_path, "build-b") == loaded.build_id
    files["alignments"].write_text("{}")
    drifted = load_active(tmp_path)
    assert drifted.source == "manifest" and drifted.norms is None and "alignments" in drifted.error


def test_facade_and_mcp_serve_the_activated_build_and_refuse_a_drifted_one(tmp_path, monkeypatch):
    import tere4ai.http_facade.app as facade
    import tere4ai.mcp_server.server as server

    files = _dumps(tmp_path)
    chain_id = _publish_fixture(tmp_path, files)
    activate(tmp_path, chain_id)
    with TestClient(facade.create_app(tmp_path)) as client:
        assert client.get("/api/health").json()["norms_build"] == "build-b+chain-" + chain_id
    monkeypatch.setattr(server, "DUMP_PATH", tmp_path / "layer1.json")
    assert server._read_dump()["build"]["build_id"] == "build-b+chain-" + chain_id
    report = server.coverage_report()
    assert report["graph_version"] == "build-b+chain-" + chain_id
    files["norms"].write_text("{}")
    with TestClient(facade.create_app(tmp_path)) as client:
        health = client.get("/api/health")
        assert health.status_code == 503 and "norms" in health.json()["error"]
    assert server._read_dump() is None
    refused = server.coverage_report()["missing_facts"][0]
    assert "differs" in refused and "norms_core.json" in refused and "build it with" not in refused


def test_loaded_build_is_taken_once_per_mcp_call(tmp_path, monkeypatch):
    import tere4ai.mcp_server.server as server

    calls = []
    original = server._active

    def counting():
        calls.append(1)
        return original()

    files = _dumps(tmp_path)
    chain_id = _publish_fixture(tmp_path, files)
    activate(tmp_path, chain_id)
    monkeypatch.setattr(server, "DUMP_PATH", tmp_path / "layer1.json")
    monkeypatch.setattr(server, "_active", counting)
    server.explain_requirement("norm:none")
    assert len(calls) == 1, "one LoadedBuild per tool call, never one per payload"


def _activate_cli():
    spec = importlib.util.spec_from_file_location("activate_build_cli", ROOT / "scripts" / "activate_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_activate_build_cli_refuses_an_unknown_or_drifted_chain_and_activates_a_valid_one(tmp_path, capsys):
    cli = _activate_cli()
    files = _dumps(tmp_path)
    chain_id = _publish_fixture(tmp_path, files)
    assert cli.main(["000000000000", "--dump-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "not activated" in err and "no publication" in err
    assert not (tmp_path / ACTIVE_POINTER).exists()
    assert cli.main([chain_id, "--dump-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "build-b+chain-" + chain_id in out and "restart the facade to serve it" in out
    assert json.loads((tmp_path / ACTIVE_POINTER).read_text())["chain_id"] == chain_id
    (tmp_path / ACTIVE_POINTER).unlink()
    files["norms"].write_text(json.dumps({"build": {"build_id": "build-b"}, "norms": [1]}))
    assert cli.main([chain_id, "--dump-dir", str(tmp_path)]) == 1
    assert "norms" in capsys.readouterr().err
    assert not (tmp_path / ACTIVE_POINTER).exists()

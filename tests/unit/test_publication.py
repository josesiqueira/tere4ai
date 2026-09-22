"""Publication evidence: gating per layer, manifest binding, the whole-build label, the target state (D-G21, D-G27)."""

from __future__ import annotations

import pytest

from tere4ai.graph_store.publication import (
    PublicationError,
    bind_manifests,
    gating_of,
    read_target_state,
    set_target_state,
    whole_build_label,
)


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

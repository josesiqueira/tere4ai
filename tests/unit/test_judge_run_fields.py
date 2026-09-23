"""The judge run's completed time and prompt hash on units and traced assertions (spec G D-G39, DEC-17)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
from tere4ai.mcp_server import trace as trace_tool

_VOLATILE_KEYS = {"generated_at", "graph_version", "alignments_build_id"}


def _strip_volatile(payload):
    if isinstance(payload, dict):
        return {k: _strip_volatile(v) for k, v in payload.items() if k not in _VOLATILE_KEYS}
    if isinstance(payload, list):
        return [_strip_volatile(v) for v in payload]
    return payload


def _dumps(tmp_path, with_hash):
    run = {"id": "jr-1", "type": "JudgeRun", "layer": 2, "judge_kind": "extraction", "judge_model": "j",
           "prompt_version": "v1", "verdict": "accepted", "scores": {}, "rationale": "ok",
           "started_at": "2026-09-01T00:00:00+00:00", "completed_at": "2026-09-01T00:00:01+00:00", "build_id": "build-b"}
    if with_hash:
        run["prompt_sha256"] = "5" * 64
    norm = {"norm_id": "n1", "source_node_id": "eu-ai-act:article-9:paragraph-1", "deontic_type": "obligation",
            "modal": "shall", "actor_explicit": "provider", "actor_inferred": None, "actor_inference_source_node_id": None,
            "action": "do", "object": "x", "conditions": [], "exceptions": [], "lifecycle_phase_ids": [],
            "extractor_model": "g", "extractor_prompt_version": "v1", "judge_verdict": "accepted",
            "review_status": "accepted", "judge_run_id": "jr-1"}
    mapping_run = {"id": "mr-1", "type": "MappingRun", "layer": 3, "generator_model": "g", "prompt_version": "v1",
                   "started_at": "2026-09-01T00:00:00+00:00", "completed_at": "2026-09-01T00:00:02+00:00", "build_id": "build-b"}
    judge_run_3 = {**run, "id": "jr-3", "judge_kind": "mapping", "layer": 3, "corrected_relation_type": None,
                   "review_status": "accepted"}
    assertion = {"id": "a1", "source_norm_id": "n1", "target_id": "hleg:req-1", "relation_type": "ALIGNS_WITH",
                 "scores": {}, "final_score": 1.0, "judge_verdict": "accepted", "rationale": "r", "review_status": "accepted",
                 "source_evidence_span_ids": [], "target_evidence_span_ids": [], "source_quote": "q", "target_quote": "t",
                 "mapping_run_id": "mr-1", "judge_run_id": "jr-3"}
    dump = {"build": {"build_id": "build-b"},
            "nodes": [{"id": "eu-ai-act:article-9", "type": "Article", "title": "Article 9"},
                      {"id": "eu-ai-act:article-9:paragraph-1", "type": "Paragraph", "text": "Providers shall do x.",
                       "parent_id": "eu-ai-act:article-9"}],
            "edges": []}
    norms = {"build": {"build_id": "build-b"}, "norms": [norm], "judge_runs": [run], "stats": {}}
    alignments = {"build": {"build_id": "build-b"}, "assertions": [assertion], "mapping_runs": [mapping_run],
                  "judge_runs": [judge_run_3], "stats": {}}
    (tmp_path / "layer1.json").write_text(json.dumps(dump))
    (tmp_path / "norms_core.json").write_text(json.dumps(norms))
    (tmp_path / "alignments_core.json").write_text(json.dumps(alignments))
    (tmp_path / "core_nodes.txt").write_text("eu-ai-act:article-9\n")
    return dump, alignments


def test_units_and_trace_carry_completed_at_and_a_null_prompt_hash_when_absent(tmp_path):
    dump, alignments = _dumps(tmp_path, with_hash=False)
    rendered = trace_tool.trace_alignment("n1", alignments, dump)
    (chain,) = rendered["answer"]["assertions"]  # the envelope's answer holds the rendered chain (trace.py line 152)
    assert chain["judge_run"]["completed_at"] == "2026-09-01T00:00:01+00:00" and chain["judge_run"]["prompt_sha256"] is None
    assert chain["mapping_run"]["completed_at"] == "2026-09-01T00:00:02+00:00"
    with TestClient(facade.create_app(tmp_path)) as client:
        units = client.get("/api/units").json()["units"]
        candidate = [u for u in units if u["candidates"]][0]["candidates"][0]
        assert candidate["judge"]["completed_at"] == "2026-09-01T00:00:01+00:00"
        assert candidate["judge"]["prompt_sha256"] is None
        batch = client.post("/api/trace/batch", json={"ids": ["n1"]}).json()["envelopes"]["n1"]
        # generated_at is a timestamp and graph_version (top level and nested
        # under answer.alignments_build_id) is stamped with a chain suffix by
        # the facade's loader (build_chain.py) even for a dump directory with
        # no build_chain_*.json manifest, so a chain built straight from
        # these fixtures (unstamped) never matches the served one; both are
        # pre-existing, unrelated to D-G39.
        assert batch == rendered or _strip_volatile(batch) == _strip_volatile(rendered)


def test_units_and_trace_carry_the_prompt_hash_when_the_dump_records_it(tmp_path):
    dump, alignments = _dumps(tmp_path, with_hash=True)
    rendered = trace_tool.trace_alignment("n1", alignments, dump)
    chain = rendered["answer"]["assertions"][0]
    assert chain["judge_run"]["prompt_sha256"] == "5" * 64
    with TestClient(facade.create_app(tmp_path)) as client:
        candidate = [u for u in client.get("/api/units").json()["units"] if u["candidates"]][0]["candidates"][0]
        assert candidate["judge"]["prompt_sha256"] == "5" * 64

"""Tests for the Layer 2/3 graph adapter (persistence of norms and alignments)."""

from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes
from tere4ai.graph_store.layer23 import alignments_to_graph, norms_to_graph
from tere4ai.graph_store.store import EDGE_TYPES, NODE_LABELS, GraphStore


def _norms_result():
    return {
        "norms": [
            {
                "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
                "source_node_id": "eu-ai-act:article-9:paragraph-1",
                "source_span_id": "span:009.001",
                "deontic_type": "obligation",
                "modal": "shall",
                "action": "be established",
                "object": "a risk management system",
                "extraction_method": "llm_extract_v1",
                "extractor_model": "gpt-test",
                "confidence": 0.9,
                "judge_verdict": "accepted",
                "judge_run_id": "judgerun:x:1",
                "review_status": "accepted",
                "conditions": ["in relation to high-risk AI systems"],
            },
            {
                "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n2",
                "source_node_id": "eu-ai-act:article-9:paragraph-1",
                "source_span_id": "span:009.001",
                "deontic_type": "obligation",
                "modal": "shall",
                "action": "be documented",
                "object": "the system",
                "extraction_method": "llm_extract_v1",
                "extractor_model": "gpt-test",
                "confidence": 0.4,
                "judge_verdict": "rejected",
                "judge_run_id": "judgerun:x:2",
                "review_status": "needs_review",
            },
        ],
        "judge_runs": [
            {
                "id": "judgerun:x:1",
                "judge_kind": "extraction",
                "judge_model": "claude-test",
                "prompt_version": "v1",
                "verdict": "accepted",
                "rationale": "grounded",
                "started_at": "t",
                "build_id": "b",
                "scores": {"evidence_strength": 0.9},
            }
        ],
    }


def test_norms_to_graph_provenance_split():
    g = norms_to_graph(_norms_result(), build_id="b")
    derived = {e["from"]: e for e in g["edges"] if e["edge_type"] == "DERIVED_FROM"}
    assert (
        derived["norm:eu-ai-act:article-9:paragraph-1:n1"]["provenance_class"]
        == "LLM_JUDGED_ACCEPTED"
    )
    assert (
        derived["norm:eu-ai-act:article-9:paragraph-1:n2"]["provenance_class"]
        == "LLM_CANDIDATE"
    )
    assert all(e.get("derivation_id") for e in g["edges"])


def test_all_labels_and_edge_types_are_allowlisted():
    g = norms_to_graph(_norms_result())
    align = {
        "assertions": [
            {
                "id": "align:x:1",
                "relation_type": "supports",
                "final_score": 0.7,
                "judge_verdict": "accepted",
                "review_status": "accepted",
                "source_norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1",
                "target_id": "hleg:accountability",
                "mapping_run_id": "mappingrun:x:1",
                "judge_run_id": "judgerun:x:3",
                "source_evidence_span_ids": ["span:009.001"],
                "target_evidence_span_ids": ["span:hleg:req7"],
                "scores": {"judge_confidence": 0.8},
            }
        ],
        "mapping_runs": [
            {"id": "mappingrun:x:1", "generator_model": "gpt-test", "prompt_version": "v1",
             "started_at": "t", "build_id": "b"}
        ],
        "judge_runs": [
            {"id": "judgerun:x:3", "judge_kind": "mapping", "judge_model": "claude-test",
             "prompt_version": "v1", "verdict": "accepted", "rationale": "ok",
             "started_at": "t", "build_id": "b"}
        ],
    }
    g2 = alignments_to_graph(align, build_hleg_nodes())
    for graph in (g, g2):
        for n in graph["nodes"]:
            assert n["type"] in NODE_LABELS, n["type"]
        for e in graph["edges"]:
            assert e["edge_type"] in EDGE_TYPES, e["edge_type"]

    # reified structure: assertion links to norm, target, run, judge
    types = {e["edge_type"] for e in g2["edges"] if e["from"] == "align:x:1"}
    assert types == {
        "ASSERTS_ALIGNMENT_OF",
        "ASSERTS_ALIGNMENT_TO",
        "PRODUCED_BY_MAPPING_RUN",
        "JUDGED_BY",
    }


def test_loadable_through_graph_store_fake_driver():
    class FakeSession:
        def __init__(self, log):
            self.log = log

        def run(self, query, params=None, **kw):
            self.log.append(query)
            return []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeDriver:
        def __init__(self):
            self.log = []

        def session(self, **kw):
            return FakeSession(self.log)

    g = norms_to_graph(_norms_result(), build_id="b")
    dump = {"build": {"build_id": "b", "built_at": "t", "tere4ai_version": "x", "snapshots": []},
            "nodes": g["nodes"], "edges": g["edges"]}
    driver = FakeDriver()
    counts = GraphStore().load_dump(dump, driver)
    assert sum(v for k, v in counts.items() if k.startswith("node:")) == 3
    assert any("NormativeStatement" in q for q in driver.log)

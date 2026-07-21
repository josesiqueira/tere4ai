"""Null-input degradation at the MCP tool boundary (Section 13, Section 8).

Live audit 2026-07-21: hostile null-family arguments made MCP tool wrappers
raise unhandled exceptions (surfacing as raw ToolError) instead of degrading:
get_applicable_requirements crashed on a non-dict classification
(AttributeError in requirements._unwrap_classification) and
evaluate_project_evidence_batch crashed on a non-string article_node_id
(TypeError in evidence.accepted_norms_for_article); generate_control_backlog
crashed on a non-iterable norm_ids. These tests pin the boundary contract:
unusable input comes back as a full Section 8 envelope with a degraded
status, the invalid argument named in missing_facts, confidence 0.0, and the
non-legal-advice notice, never an exception. Paid tools must degrade before
any model client is constructed (same wrapper-level guard as audit D9).
"""

import pytest

from tere4ai.mcp_server import server
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE

ENVELOPE_FIELDS = (
    "answer",
    "status",
    "confidence",
    "source_nodes",
    "source_spans",
    "graph_evidence_subgraph",
    "legal_status_notes",
    "missing_facts",
    "judge_verdict",
    "generated_at",
    "graph_version",
    "non_legal_advice_notice",
)

DUMP = {"build": {"build_id": "build-fixture"}, "nodes": [], "edges": []}
NORMS_PAYLOAD = {
    "norms": [
        {
            "norm_id": "norm:a9-1",
            "source_node_id": "eu-ai-act:article-9:paragraph-1",
            "judge_verdict": "accepted",
            "deontic_type": "obligation",
            "modal": "shall",
            "action": "establish a risk management system",
            "object": "risk management system",
        }
    ]
}


@pytest.fixture()
def offline_server(monkeypatch):
    """Server wrappers over synthetic dumps; paid clients must never be built."""
    monkeypatch.setattr(server, "_read_dump", lambda *a, **k: DUMP)

    def _read_json(path):
        if path == server.NORMS_PATH:
            return NORMS_PAYLOAD
        if path == server.ALIGNMENTS_PATH:
            return {"assertions": []}
        return None

    monkeypatch.setattr(server, "_read_json", _read_json)

    def _no_paid_clients():
        raise AssertionError(
            "paid model client construction was reached from a null-input test"
        )

    monkeypatch.setattr(server, "_paid_clients_or_envelope", _no_paid_clients)
    return server


def _assert_degraded_envelope(envelope, invalid_field):
    for field in ENVELOPE_FIELDS:
        assert field in envelope, f"envelope missing {field}"
    assert envelope["status"] == "requires_human_review"
    assert envelope["confidence"] == 0.0
    assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    facts = " ".join(envelope["missing_facts"])
    assert invalid_field in facts, f"missing_facts does not name {invalid_field!r}: {facts!r}"


def test_get_applicable_requirements_non_dict_classification_degrades(offline_server):
    """Audit crasher 1: classification=None raised AttributeError in
    requirements._unwrap_classification. Every non-dict must degrade."""
    for bad in (None, 123, "high_risk", [], [{"risk_category": "high_risk"}]):
        envelope = offline_server.get_applicable_requirements(classification=bad)
        _assert_degraded_envelope(envelope, "classification")


def test_evaluate_evidence_batch_non_string_article_id_degrades(offline_server):
    """Audit crasher 2: article_node_id=None raised TypeError in
    evidence.accepted_norms_for_article. Every non-string must degrade."""
    for bad in (None, 123, [], {}):
        envelope = offline_server.evaluate_project_evidence_batch(
            article_node_id=bad, artifact_type="policy_doc", content="real content"
        )
        _assert_degraded_envelope(envelope, "article_node_id")


def test_evaluate_evidence_batch_blank_article_id_degrades(offline_server):
    """A blank article_node_id prefix-matches EVERY accepted norm via
    startswith(''), which would trigger a paid model call per norm. It must
    degrade at the boundary before any client is constructed."""
    for bad in ("", "   "):
        envelope = offline_server.evaluate_project_evidence_batch(
            article_node_id=bad, artifact_type="policy_doc", content="real content"
        )
        _assert_degraded_envelope(envelope, "article_node_id")


def test_generate_control_backlog_non_list_norm_ids_degrades(offline_server):
    """Audit crasher 3: norm_ids=123 raised TypeError (not iterable);
    norm_ids='abc' was silently iterated as characters. Non-list must degrade."""
    for bad in (123, "abc", {"norm:a9-1": True}):
        envelope = offline_server.generate_control_backlog(
            norm_ids=bad, system_context="a credit scoring service"
        )
        _assert_degraded_envelope(envelope, "norm_ids")


def test_generate_control_backlog_empty_norm_ids_still_clean(offline_server):
    """Regression pin: falsy norm_ids (None, []) keep the pre-existing clean
    not_applicable degrade and never raise."""
    for empty in (None, []):
        envelope = offline_server.generate_control_backlog(
            norm_ids=empty, system_context="a credit scoring service"
        )
        assert envelope["status"] == "not_applicable"
        assert "norm_ids" in " ".join(envelope["missing_facts"])


def test_generate_control_backlog_null_system_context_degrades(offline_server):
    """system_context None/blank/non-string with valid norm_ids previously
    flowed toward the paid path (backlog raises ValueError pre-model). It must
    degrade at the boundary, before any client is constructed."""
    for bad in (None, "", "   ", 123):
        envelope = offline_server.generate_control_backlog(
            norm_ids=["norm:a9-1"], system_context=bad
        )
        _assert_degraded_envelope(envelope, "system_context")


def test_evaluate_project_evidence_null_artifact_type_degrades(offline_server):
    """Audit D9's uncovered half: artifact_type None/blank/non-string with a
    valid norm and content reached evidence._validate_evidence, whose
    ValueError surfaced as a raw ToolError. It must degrade at the wrapper."""
    for bad in (None, "", "   ", 123):
        envelope = offline_server.evaluate_project_evidence(
            norm_id="norm:a9-1", artifact_type=bad, content="real content"
        )
        _assert_degraded_envelope(envelope, "artifact_type")


def test_evaluate_evidence_batch_null_artifact_type_degrades(offline_server):
    """Same D9 wrapper guard on the batch tool."""
    for bad in (None, "", "   ", 123):
        envelope = offline_server.evaluate_project_evidence_batch(
            article_node_id="eu-ai-act:article-9",
            artifact_type=bad,
            content="real content",
        )
        _assert_degraded_envelope(envelope, "artifact_type")


def test_free_tools_tolerate_null_ids(offline_server):
    """Regression pin: the free lookup tools already degrade cleanly on
    null-family ids and must keep doing so."""
    for bad in (None, "", 123, [], {}):
        for envelope in (
            offline_server.source_trace(node_id=bad),
            offline_server.explain_requirement(norm_id=bad),
            offline_server.trace_alignment(id=bad),
            offline_server.resolve_span(span_id=bad),
            offline_server.classify_ai_system(features=bad),
        ):
            assert envelope["status"] in ("not_applicable", "requires_human_review")
            assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE

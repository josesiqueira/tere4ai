"""Unit tests for explain_requirement, trace_alignment, and the span helper.

Offline only: runs against the real published build artifacts on disk
(layer1.json, norms_core.json, alignments_core.json, and the frozen
snapshots), skipping when any has not been built. No model, no network, no
database. Deterministic assembly is asserted via the envelope invariants of
DEC-08: the calibrated status vocabulary, the non-legal-advice notice, the
not_applicable_deterministic judge verdict, and no compliance-like claim in
the tool's own text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT, explain_requirement
from tere4ai.mcp_server.spans import (
    SpanIntegrityError,
    SpanNotFoundError,
    resolve_span,
    resolve_span_envelope,
)
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
    strip_verbatim_quote_fields,
)
from tere4ai.mcp_server.trace import trace_alignment

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = ROOT / "data" / "graph_dumps" / "alignments_core.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
MANIFEST_PATH = SNAPSHOTS_DIR / "MANIFEST.json"

ACCEPTED_NORM_ID = "norm:eu-ai-act:article-9:paragraph-1:n1"
HLEG_ID = "hleg:technical-robustness-and-safety"
KNOWN_SPAN_ID = "span:009.001"

pytestmark = pytest.mark.skipif(
    not (
        DUMP_PATH.is_file()
        and NORMS_PATH.is_file()
        and ALIGNMENTS_PATH.is_file()
        and MANIFEST_PATH.is_file()
    ),
    reason="layer1.json, norms_core.json, alignments_core.json, or snapshots not built",
)

# Fields whose content is cited legal source text or verbatim build-time
# judge/generator text, not a claim made by the tool itself, are removed
# before the DEC-08 no-compliance-claim check. The shared exemption list is
# tools.VERBATIM_QUOTE_FIELDS; the full scoped contract is encoded in
# tests/unit/test_banned_term_scope.py.


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms_payload() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alignments_payload() -> dict:
    return json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_ids(dump) -> set:
    return {n["id"] for n in dump["nodes"]}


@pytest.fixture(scope="module")
def span_ids_in_dump(dump) -> set:
    return {
        n["source_span"]["span_id"]
        for n in dump["nodes"]
        if isinstance(n.get("source_span"), dict) and n["source_span"].get("span_id")
    }


def assert_envelope_invariants(envelope: dict, node_ids: set) -> None:
    assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    assert envelope["status"] in STATUS_VOCABULARY
    assert envelope["judge_verdict"] == "not_applicable_deterministic"
    serialized = json.dumps(strip_verbatim_quote_fields(envelope)).lower()
    assert "compliant" not in serialized
    assert "certified" not in serialized
    for node_id in envelope["source_nodes"]:
        assert node_id in node_ids, f"cited node {node_id} not in dump"


# explain_requirement --------------------------------------------------------


def test_explain_accepted_norm_full_chain(
    dump, norms_payload, alignments_payload, node_ids, span_ids_in_dump
):
    envelope = explain_requirement(
        ACCEPTED_NORM_ID, dump, norms_payload, alignments_payload
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["found"] is True
    assert answer["review_status"] == "accepted"
    assert answer["build_judge_verdict"] == "accepted"
    # Deontic decomposition.
    deontic = answer["deontic"]
    assert deontic["deontic_type"] == "obligation"
    assert deontic["modal"] == "shall"
    assert deontic["actor"]["inferred"] == "provider"
    assert deontic["actor"]["inference_source_node_id"] == "eu-ai-act:article-16"
    assert deontic["object"] == "a risk management system"
    assert deontic["conditions"] == ["in relation to high-risk AI systems"]
    # Source unit full text, resolved via source_node_id from the dump.
    assert answer["source"]["node_id"] == "eu-ai-act:article-9:paragraph-1"
    assert "risk management system" in answer["source"]["text"]
    # Article 3 definitions literally occurring in action/object: 'risk'
    # (Article 3 point 2) occurs in 'a risk management system'.
    matched_ids = {d["definition_node_id"] for d in answer["article_3_definitions"]}
    assert "eu-ai-act:article-3:paragraph-1:point-2" in matched_ids
    for d in answer["article_3_definitions"]:
        assert d["definition_node_id"].startswith("eu-ai-act:article-3:")
        assert d["term"]
    # At least one accepted HLEG target with a relation type and final score.
    accepted = answer["hleg_alignments"]["accepted"]
    assert accepted, "expected at least one accepted HLEG alignment"
    for target in accepted:
        assert target["target_id"].startswith("hleg:")
        assert target["relation_type"]
        assert isinstance(target["final_score"], (int, float))
    assert answer["hleg_alignments"]["caveat"] == HLEG_MAPPING_CAVEAT
    # Span trace: valid span ids; the norm's own span resolves in the dump.
    trace_ids = [s["span_id"] for s in answer["span_trace"]]
    assert KNOWN_SPAN_ID in trace_ids
    hleg_text = SNAPSHOTS_DIR / "hleg_ethics_guidelines_2019_en_v1text.txt"
    for entry in answer["span_trace"]:
        assert entry["span_id"].startswith("span:")
        if entry["span_id"] in span_ids_in_dump:
            assert entry["snapshot_file"]
        if entry["span_id"].startswith("span:hleg:") and hleg_text.is_file():
            assert entry["snapshot_file"] == hleg_text.name
    assert envelope["source_spans"][0]["span_id"] == KNOWN_SPAN_ID


def test_explain_non_accepted_norm_states_review_status(
    dump, norms_payload, alignments_payload, node_ids
):
    non_accepted = next(
        n for n in norms_payload["norms"] if n["judge_verdict"] != "accepted"
    )
    envelope = explain_requirement(
        non_accepted["norm_id"], dump, norms_payload, alignments_payload
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "requires_human_review"
    answer = envelope["answer"]
    assert answer["found"] is True
    assert answer["review_status"] == non_accepted["review_status"]
    assert answer["build_judge_verdict"] == non_accepted["judge_verdict"]
    assert "NOT judge-accepted" in answer["review_note"]
    assert any("NOT judge-accepted" in note for note in envelope["legal_status_notes"])


def test_explain_unknown_norm_id_is_clean(
    dump, norms_payload, alignments_payload, node_ids
):
    envelope = explain_requirement(
        "norm:eu-ai-act:article-999:n1", dump, norms_payload, alignments_payload
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["found"] is False
    assert any("article-999" in fact for fact in envelope["missing_facts"])


# trace_alignment ------------------------------------------------------------


def test_trace_hleg_target_renders_full_reified_chains(
    dump, alignments_payload, node_ids
):
    envelope = trace_alignment(HLEG_ID, alignments_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["mode"] == "hleg_target"
    assert answer["assertion_count"] >= 1
    assert answer["accepted_count"] >= 1
    assert answer["caveat"] == HLEG_MAPPING_CAVEAT
    assert HLEG_MAPPING_CAVEAT in envelope["legal_status_notes"]
    for assertion in answer["assertions"]:
        # Full reified chain, never a bare edge.
        assert assertion["target_id"] == HLEG_ID
        assert assertion["relation_type"]
        assert assertion["scores"]
        assert isinstance(assertion["final_score"], (int, float))
        assert assertion["judge_verdict"] in ("accepted", "rejected", "needs_human_review")
        assert assertion["rationale"]
        # Evidence spans on BOTH sides.
        assert assertion["evidence"]["source_evidence_span_ids"]
        assert assertion["evidence"]["target_evidence_span_ids"]
        # MappingRun: generator model plus prompt version.
        assert assertion["mapping_run"]["generator_model"]
        assert assertion["mapping_run"]["prompt_version"]
        # JudgeRun: judge model plus rationale.
        assert assertion["judge_run"]["judge_model"]
        assert assertion["judge_run"]["rationale"]


def test_trace_norm_id_selects_assertions_from_that_norm(
    dump, alignments_payload, node_ids
):
    envelope = trace_alignment(ACCEPTED_NORM_ID, alignments_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["mode"] == "norm"
    assert answer["assertion_count"] >= 1
    assert all(
        a["source_norm_id"] == ACCEPTED_NORM_ID for a in answer["assertions"]
    )
    span_stub_ids = {s["span_id"] for s in envelope["source_spans"]}
    assert KNOWN_SPAN_ID in span_stub_ids


def test_trace_unknown_id_is_clean(dump, alignments_payload, node_ids):
    envelope = trace_alignment("hleg:no-such-requirement", alignments_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["found"] is False
    assert any("no-such-requirement" in fact for fact in envelope["missing_facts"])


# resolve_span ---------------------------------------------------------------


def test_resolve_span_returns_checksum_verified_slice(dump):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    html_entry = next(
        s
        for s in manifest["snapshots"]
        if s["file"].startswith("eu_ai_act_") and s["file"].endswith(".html")
    )
    resolved = resolve_span(KNOWN_SPAN_ID, dump, SNAPSHOTS_DIR)
    assert resolved["span_id"] == KNOWN_SPAN_ID
    assert resolved["snapshot_file"] == html_entry["file"]
    assert resolved["sha256"] == html_entry["sha256"]
    assert "risk management system" in resolved["text"]
    assert resolved["end"] - resolved["start"] == len(resolved["text"])


def test_resolve_span_handles_formex_subpath_spans(dump):
    fmx_span_id = next(
        n["source_span"]["span_id"]
        for n in dump["nodes"]
        if isinstance(n.get("source_span"), dict)
        and str(n["source_span"].get("snapshot_file", "")).startswith("formex/")
    )
    resolved = resolve_span(fmx_span_id, dump, SNAPSHOTS_DIR)
    assert resolved["snapshot_file"].startswith("formex/")
    assert resolved["text"]


def test_resolve_span_unknown_id_raises_not_found(dump):
    with pytest.raises(SpanNotFoundError):
        resolve_span("span:no-such-span", dump, SNAPSHOTS_DIR)


def test_resolve_span_checksum_drift_raises_integrity_error(dump, tmp_path):
    node = next(
        n
        for n in dump["nodes"]
        if isinstance(n.get("source_span"), dict)
        and n["source_span"].get("span_id") == KNOWN_SPAN_ID
    )
    drifted = tmp_path / node["source_span"]["snapshot_file"]
    drifted.write_text("not the frozen snapshot", encoding="utf-8")
    with pytest.raises(SpanIntegrityError, match="checksum mismatch"):
        resolve_span(KNOWN_SPAN_ID, dump, tmp_path)


def test_resolve_span_envelope_known_and_unknown(dump, node_ids):
    ok = resolve_span_envelope(KNOWN_SPAN_ID, dump, SNAPSHOTS_DIR)
    assert_envelope_invariants(ok, node_ids)
    assert ok["status"] == "satisfied_with_evidence"
    assert "risk management system" in ok["answer"]["text"]
    assert ok["source_spans"][0]["span_id"] == KNOWN_SPAN_ID

    missing = resolve_span_envelope("span:no-such-span", dump, SNAPSHOTS_DIR)
    assert_envelope_invariants(missing, node_ids)
    assert missing["status"] == "not_applicable"
    assert missing["answer"]["found"] is False
    assert missing["missing_facts"]


def test_resolve_span_extra_nodes_cover_hleg_spans(dump):
    from tere4ai.align_hleg_altai.hleg_nodes import build_hleg_nodes

    hleg_nodes = build_hleg_nodes()
    resolved = resolve_span(
        "span:hleg:req2", dump, SNAPSHOTS_DIR, extra_nodes=hleg_nodes
    )
    assert "robustness" in resolved["text"].lower()


# server registration --------------------------------------------------------


def test_server_registers_explain_trace_and_span_tools():
    from tere4ai.mcp_server import server

    for name in ("explain_requirement", "trace_alignment", "resolve_span"):
        assert hasattr(server, name), f"server.py does not register {name}"

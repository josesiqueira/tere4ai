"""Unit tests for the M1 MCP tools (DEC-08, DEC-10) over synthetic dumps."""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.spans import SpanResolutionError, resolve_span
from tere4ai.mcp_server.tools import (
    EXPECTED_CHAPTERS,
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
    coverage_report,
    source_trace,
)

SHA = "a" * 64
SNAPSHOT_FILE = "eu_ai_act_32024R1689_eurlex_html_2026-07-08.html"

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


def _span(anchor: str, start: int) -> dict:
    return {
        "span_id": f"span:{anchor}",
        "snapshot_file": SNAPSHOT_FILE,
        "snapshot_sha256": SHA,
        "start": start,
        "end": start + 40,
        "anchor": anchor,
    }


def _edge(edge_id: str, edge_type: str, from_id: str, to_id: str) -> dict:
    return {
        "edge_id": edge_id,
        "edge_type": edge_type,
        "from": from_id,
        "to": to_id,
        "provenance_class": "EXTRACTED_SOURCE",
        "source_span_id": f"span:{edge_id}",
        "method": "html_anchor_hierarchy",
        "confidence": 1.0,
        "review_status": "auto_accepted",
        "build_id": "build-fixture",
    }


def make_complete_dump() -> dict:
    """Synthetic dump satisfying every structural expectation of M1."""
    nodes = [
        {
            "id": "eu-ai-act",
            "layer": 0,
            "type": "SourceDocument",
            "title": "Regulation (EU) 2024/1689",
            "legal_status": "in_force",
        },
        {"id": "eu-ai-act:regulation", "layer": 1, "type": "Regulation"},
    ]
    edges = []
    for i, roman in enumerate(EXPECTED_CHAPTERS, start=1):
        cid = f"eu-ai-act:chapter-{roman.lower()}"
        nodes.append({"id": cid, "layer": 1, "type": "Chapter", "number": roman})
        edges.append(_edge(f"e:ch{i}", "HAS_CHAPTER", "eu-ai-act:regulation", cid))
    for n in range(1, 114):
        aid = f"eu-ai-act:article-{n}"
        roman = EXPECTED_CHAPTERS[(n - 1) % len(EXPECTED_CHAPTERS)]
        nodes.append(
            {
                "id": aid,
                "layer": 1,
                "type": "Article",
                "number": n,
                "title": f"Article {n}",
                "source_span": _span(f"art_{n}", n * 100),
            }
        )
        edges.append(
            _edge(f"e:art{n}", "HAS_ARTICLE", f"eu-ai-act:chapter-{roman.lower()}", aid)
        )
    for n in range(1, 181):
        nodes.append(
            {
                "id": f"eu-ai-act:recital-{n}",
                "layer": 1,
                "type": "Recital",
                "number": n,
                "text": f"Recital {n} text",
                "source_span": _span(f"rct_{n}", 20000 + n * 100),
            }
        )
    romans13 = EXPECTED_CHAPTERS
    for n, roman in enumerate(romans13, start=1):
        nodes.append(
            {
                "id": f"eu-ai-act:annex-{roman.lower()}",
                "layer": 1,
                "type": "Annex",
                "number": roman,
                "source_span": _span(f"anx_{roman}", 40000 + n * 100),
            }
        )
    nodes.append(
        {
            "id": "eu-ai-act:article-9:paragraph-1",
            "layer": 1,
            "type": "Paragraph",
            "index": 1,
            "text": "A risk management system shall be established.",
            "source_span": _span("009.001", 50000),
        }
    )
    edges.append(
        _edge("e:par9.1", "HAS_PARAGRAPH", "eu-ai-act:article-9", "eu-ai-act:article-9:paragraph-1")
    )
    return {
        "build": {
            "build_id": "build-fixture",
            "built_at": "2026-07-08T00:00:00Z",
            "tere4ai_version": "2.0.0a0",
            "snapshots": [{"file": SNAPSHOT_FILE, "sha256": SHA}],
        },
        "nodes": nodes,
        "edges": edges,
    }


def make_incomplete_dump() -> dict:
    """Complete dump minus Article 9, 50 recitals, and Chapter XIII."""
    dump = make_complete_dump()
    dump["nodes"] = [
        n
        for n in dump["nodes"]
        if n["id"] != "eu-ai-act:article-9"
        and not (n["type"] == "Recital" and n["number"] > 130)
        and not (n["type"] == "Chapter" and n["number"] == "XIII")
    ]
    return dump


def test_no_compliance_claim():
    """DEC-08: the vocabulary never contains compliance-like terms, and the
    envelope always carries the non-legal-advice notice."""
    for status in STATUS_VOCABULARY:
        for forbidden in ("compliant", "certified", "approved"):
            assert forbidden not in status
    assert set(STATUS_VOCABULARY) == {
        "not_applicable",
        "potentially_applicable",
        "applicable_missing_evidence",
        "partially_satisfied",
        "satisfied_with_evidence",
        "rejected_as_unsupported",
        "requires_human_review",
    }
    dump = make_complete_dump()
    for envelope in (
        coverage_report(dump),
        source_trace(dump, "eu-ai-act:article-9"),
        source_trace(dump, "no:such:node"),
    ):
        assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
        assert "does not certify EU AI Act compliance" in envelope["non_legal_advice_notice"]
        assert envelope["status"] in STATUS_VOCABULARY


def test_envelope_shape_and_deterministic_verdict():
    envelope = coverage_report(make_complete_dump())
    for field in ENVELOPE_FIELDS:
        assert field in envelope, f"envelope missing {field}"
    assert envelope["judge_verdict"] == "not_applicable_deterministic"
    assert envelope["confidence"] == 1.0
    assert envelope["graph_version"] == "build-fixture"


def test_coverage_report_complete_fixture():
    envelope = coverage_report(make_complete_dump())
    assert envelope["status"] == "satisfied_with_evidence"
    assert envelope["missing_facts"] == []
    answer = envelope["answer"]
    assert answer["actual"]["articles"] == 113
    assert answer["actual"]["recitals"] == 180
    assert answer["actual"]["annexes"] == 13
    assert answer["actual"]["paragraphs"] == 1
    assert answer["high_risk_core"]["missing"] == []
    assert answer["layer2_nodes"] == {"count": 0, "status": "not_started"}
    assert answer["layer3_nodes"] == {"count": 0, "status": "not_started"}
    # per-chapter article listing is present and covers all 113 articles
    listed = [a for arts in answer["per_chapter_articles"].values() for a in arts]
    assert sorted(listed) == list(range(1, 114))


def test_coverage_report_incomplete_fixture():
    envelope = coverage_report(make_incomplete_dump())
    assert envelope["status"] == "requires_human_review"
    facts = " ".join(envelope["missing_facts"])
    assert "expected 113 Article nodes, found 112" in facts
    assert "expected 180 Recital nodes, found 130" in facts
    assert "XIII" in facts
    assert 9 in envelope["answer"]["high_risk_core"]["missing"]


def test_source_trace_known_node():
    dump = make_complete_dump()
    envelope = source_trace(dump, "eu-ai-act:article-9:paragraph-1")
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["snapshot_file"] == SNAPSHOT_FILE
    assert answer["snapshot_sha256"] == SHA
    assert answer["span_start"] == 50000
    assert answer["span_end"] == 50040
    assert answer["anchor"] == "009.001"
    assert "risk management system" in answer["excerpt"]
    assert envelope["source_nodes"] == ["eu-ai-act:article-9:paragraph-1"]
    assert envelope["source_spans"][0]["anchor"] == "009.001"


def test_source_trace_slices_over_untranslated_bytes(tmp_path):
    """Audit 2026-07-21: span offsets are computed over the raw (byte-decoded)
    snapshot, which preserves CRLF line endings. source_trace must resolve
    through resolve_span (read_bytes then decode), not read_text, whose
    universal-newline translation collapses every \\r\\n and shifts all later
    offsets, returning the wrong legal text (the observed bug on the real
    CRLF-terminated EUR-Lex HTML)."""
    import hashlib

    target = "SNAPSHOT SLICE FOR PARAGRAPH NINE ONE ok"
    prefix = "line\r\n" * 8000  # CRLF pairs before the span
    content = prefix + target + "\r\ntail"
    raw = content.encode("utf-8")
    char_start = len(prefix)  # offset over the untranslated decoded text
    (tmp_path / SNAPSHOT_FILE).write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    node = {
        "id": "eu-ai-act:article-9:paragraph-1",
        "type": "Paragraph",
        "layer": 1,
        "text": "fallback should not be used",
        "source_span": {
            "span_id": "span:009.001",
            "snapshot_file": SNAPSHOT_FILE,
            "snapshot_sha256": sha,
            "start": char_start,
            "end": char_start + len(target),
            "anchor": "009.001",
        },
    }
    dump = {"nodes": [node], "build": {"build_id": "b"}}
    envelope = source_trace(dump, "eu-ai-act:article-9:paragraph-1", snapshots_dir=tmp_path)
    assert envelope["answer"]["excerpt"] == target
    # The old read_text path (universal newlines) would have sliced wrongly.
    translated = (tmp_path / SNAPSHOT_FILE).read_text(encoding="utf-8")
    assert translated[char_start : char_start + len(target)] != target


def test_source_trace_forged_snapshot_path_does_not_leak(tmp_path):
    """Audit 2026-07-21: a span whose snapshot_file escapes the snapshots dir
    must not leak arbitrary files; resolve_span's containment + checksum guard
    makes source_trace fall back to the node text."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET should never be returned", encoding="utf-8")
    node = {
        "id": "x",
        "type": "Paragraph",
        "layer": 1,
        "text": "safe fallback",
        "source_span": {
            "span_id": "span:evil",
            "snapshot_file": "../secret.txt",
            "snapshot_sha256": "0" * 64,
            "start": 0,
            "end": 20,
            "anchor": "evil",
        },
    }
    dump = {"nodes": [node], "build": {"build_id": "b"}}
    envelope = source_trace(dump, "x", snapshots_dir=tmp_path / "snapshots")
    assert "SECRET" not in (envelope["answer"]["excerpt"] or "")
    assert envelope["answer"]["excerpt"] == "safe fallback"


def test_source_trace_unknown_node_is_graceful():
    envelope = source_trace(make_complete_dump(), "eu-ai-act:article-999")
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["found"] is False
    assert envelope["missing_facts"]
    assert "eu-ai-act:article-999" in envelope["missing_facts"][0]


def test_source_trace_recital_flags_non_binding():
    envelope = source_trace(make_complete_dump(), "eu-ai-act:recital-12")
    assert any("never binding" in note for note in envelope["legal_status_notes"])


# --- Redteam fix: truncation must be explicit, never silent ---------------
#
# The two tests below run against the real published dump (a build
# artifact, gitignored like data/graph_dumps/*.json elsewhere in this
# suite), because "find a genuinely short real node" is the point: a
# synthetic fixture could accidentally encode the assumption being tested.
# They skip cleanly on a fresh clone that has not built the dump yet.

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_DUMP_PATH = _REPO_ROOT / "data" / "graph_dumps" / "layer1.json"
_REAL_SNAPSHOTS_DIR = _REPO_ROOT / "data" / "snapshots"
_REAL_DUMP_MISSING = not (_REAL_DUMP_PATH.is_file() and _REAL_SNAPSHOTS_DIR.is_dir())


def _resolve_full_text(node: dict, dump: dict) -> str:
    """Independent ground truth for a node's full resolved source text,
    mirroring the documented resolve_span-then-node-text-fallback order
    (tools._excerpt's docstring), using only public API."""
    span = node["source_span"]
    try:
        return resolve_span(str(span["span_id"]), dump, _REAL_SNAPSHOTS_DIR)["text"]
    except (SpanResolutionError, OSError, KeyError):
        fallback = node.get("text") or node.get("title")
        assert isinstance(fallback, str)
        return fallback


@pytest.mark.skipif(
    _REAL_DUMP_MISSING,
    reason="published graph dump/snapshots not present (build artifact, gitignored)",
)
def test_source_trace_long_real_span_flags_truncation_explicitly():
    """Article 5(1) (prohibited practices) is long: its excerpt must come
    back capped at 500 characters AND explicitly flagged as truncated, with
    span_chars reporting the true full length and the returned characters
    byte-exact against the first excerpt_chars of the real source text."""
    dump = json.loads(_REAL_DUMP_PATH.read_text(encoding="utf-8"))
    node_id = "eu-ai-act:article-5:paragraph-1"
    node = next(n for n in dump["nodes"] if n["id"] == node_id)
    full_text = _resolve_full_text(node, dump)
    assert len(full_text) > 500, "fixture assumption: this node must be genuinely long"

    envelope = source_trace(dump, node_id, snapshots_dir=_REAL_SNAPSHOTS_DIR)
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["excerpt_truncated"] is True
    assert answer["excerpt_chars"] == 500
    assert answer["span_chars"] == len(full_text)
    assert answer["span_chars"] > answer["excerpt_chars"]
    assert answer["excerpt"] == full_text[:500]


@pytest.mark.skipif(
    _REAL_DUMP_MISSING,
    reason="published graph dump/snapshots not present (build artifact, gitignored)",
)
def test_source_trace_short_real_span_is_not_flagged_truncated():
    """eu-ai-act:annex-ii:item-12 is a genuinely short AnnexItem (well under
    the 500-char cap): its excerpt must equal the full source text exactly,
    with excerpt_truncated false and excerpt_chars == span_chars."""
    dump = json.loads(_REAL_DUMP_PATH.read_text(encoding="utf-8"))
    node_id = "eu-ai-act:annex-ii:item-12"
    node = next(n for n in dump["nodes"] if n["id"] == node_id)
    full_text = _resolve_full_text(node, dump)
    assert len(full_text) < 500, "fixture assumption: this node must be genuinely short"

    envelope = source_trace(dump, node_id, snapshots_dir=_REAL_SNAPSHOTS_DIR)
    assert envelope["status"] == "satisfied_with_evidence"
    answer = envelope["answer"]
    assert answer["excerpt_truncated"] is False
    assert answer["excerpt_chars"] == answer["span_chars"] == len(full_text)
    assert answer["excerpt"] == full_text


def test_server_module_wraps_tools():
    """Smoke test: the FastMCP server registers both read-only tools."""
    from tere4ai.mcp_server import server

    assert server.mcp.name == "tere4ai"
    degraded = server.tools.dump_unavailable_envelope("no dump")
    assert degraded["status"] == "requires_human_review"
    assert degraded["confidence"] == 0.0
    assert degraded["graph_version"] == "unavailable"

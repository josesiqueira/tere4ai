"""M1 MCP tools: coverage_report and source_trace as pure functions.

Both tools operate on the offline Layer 0+1 dump dict
(schema/json_schemas/layer1_dump.schema.json) and require no database.
They are deterministic and structural, so judge_verdict is
"not_applicable_deterministic" and confidence is 1.0. Every response uses
the full envelope of docs/architecture.md Section 8 and the calibrated
status vocabulary; the vocabulary never contains compliance claims.

@implements: DEC-08, DEC-10
@grounded_by: REF-16, REF-17, REF-15
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# DEC-08: calibrated vocabulary. Never compliant, certified, or legally approved.
STATUS_VOCABULARY = (
    "not_applicable",
    "potentially_applicable",
    "applicable_missing_evidence",
    "partially_satisfied",
    "satisfied_with_evidence",
    "rejected_as_unsupported",
    "requires_human_review",
)

# DEC-08 banned claim terms (architecture.md Sections 8 and 16): these words
# may never appear in any SYSTEM-GENERATED text field of an envelope.
BANNED_CLAIM_TERMS = ("compliant", "certified", "legally approved")

# DEC-08 scope (decided 2026-07-21 after a live audit): the ban covers every
# field TERE4AI composes itself (status, answer text, notes, summaries,
# messages, backlog titles and descriptions). Fields that carry VERBATIM
# quoted text are exempt, because the EU AI Act's own sentences say things
# like "compliant with the requirements" (Article 8(2), Article 16 point
# (a)) and Article 82 is titled "Compliant AI systems which present a risk".
# Those are the regulator's words, not TERE4AI's claim; they are
# structurally marked by the field names below, are never presented as a
# system verdict, and must never be altered: sanitizing a quote would break
# the byte-exact traceability of quoted source text, a harder invariant
# than the wording ban. Replayed generator and judge free text (rationales,
# evidence quotes) is exempt from this mechanical string scan because it may
# legitimately quote the statute; actual compliance assertions in that text
# are rejected semantically by the runtime grounding judge (Section 7,
# prompt check "no compliance assertion").
VERBATIM_QUOTE_FIELDS = frozenset(
    {
        # Verbatim frozen-source text (the regulator's words).
        "text",
        "title",
        "excerpt",
        "source_text",
        # Norm deontic content quoted from the Act.
        "action",
        "object",
        "conditions",
        "exceptions",
        # Alignment evidence quotes on both sides.
        "source_quote",
        "target_quote",
        # Verbatim quotes lifted from untrusted project evidence.
        "quotes",
        # Replayed model free text, judge-gated semantically, kept byte-exact.
        "rationale",
        "judge_rationale",
    }
)


def strip_verbatim_quote_fields(value: Any) -> Any:
    """Recursively drop the DEC-08-exempt verbatim-quote fields.

    Used by the banned-term enforcement tests: what remains after this scrub
    is system-generated text, in which BANNED_CLAIM_TERMS may never occur.
    """
    if isinstance(value, dict):
        return {
            k: strip_verbatim_quote_fields(v)
            for k, v in value.items()
            if k not in VERBATIM_QUOTE_FIELDS
        }
    if isinstance(value, list):
        return [strip_verbatim_quote_fields(v) for v in value]
    return value

# The mandatory response envelope of architecture.md Section 8: every
# user-facing tool response MUST carry exactly these keys. make_envelope is
# the single constructor and its output is asserted against this set in the
# envelope-contract test, so the two can never drift.
SECTION_8_ENVELOPE_FIELDS = frozenset(
    {
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
    }
)

# Legal caveat, docs/architecture.md Section 0. Included in every response.
NON_LEGAL_ADVICE_NOTICE = (
    "TERE4AI provides engineering and documentation support. It does not "
    "certify EU AI Act compliance and does not replace legal review, "
    "conformity assessment, or competent-authority interpretation."
)

DETERMINISTIC_JUDGE_VERDICT = "not_applicable_deterministic"

# Structural expectations for the M1 acceptance (docs/architecture.md Section 10).
EXPECTED_ARTICLES = 113
EXPECTED_RECITALS = 180
EXPECTED_ANNEXES = 13
EXPECTED_CHAPTERS = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
)

# Section 10 high-risk core set: articles that must be structurally present.
HIGH_RISK_CORE_ARTICLES = tuple(
    sorted({3, 5, 6, 7} | set(range(8, 16)) | set(range(16, 28)) | {50, 72, 73})
)

# Payload cap for source_trace's excerpt field. Kept for payload discipline
# (a 13k-character Article 5(1) span should not ride on every trace call),
# never changed silently: this is the single point of truth for the cap
# value, and source_trace's docstring below states it explicitly. The cap
# never hides truncation: source_trace reports excerpt_truncated,
# excerpt_chars, and span_chars alongside the excerpt (redteam fix, see
# source_trace docstring), so a consumer can always tell a partial quote
# from a complete one without re-deriving it from span_start/span_end.
_EXCERPT_MAX_CHARS = 500


def make_envelope(
    answer: Any,
    status: str,
    *,
    graph_version: str,
    confidence: float = 1.0,
    source_nodes: list[str] | None = None,
    source_spans: list[dict[str, Any]] | None = None,
    graph_evidence_subgraph: dict[str, Any] | None = None,
    legal_status_notes: list[str] | None = None,
    missing_facts: list[str] | None = None,
    judge_verdict: str = DETERMINISTIC_JUDGE_VERDICT,
) -> dict[str, Any]:
    """Build the mandatory response envelope of architecture.md Section 8."""
    if status not in STATUS_VOCABULARY:
        raise ValueError(f"status {status!r} is not in the calibrated vocabulary")
    return {
        "answer": answer,
        "status": status,
        "confidence": confidence,
        "source_nodes": source_nodes or [],
        "source_spans": source_spans or [],
        "graph_evidence_subgraph": graph_evidence_subgraph or {},
        "legal_status_notes": legal_status_notes or [],
        "missing_facts": missing_facts or [],
        "judge_verdict": judge_verdict,
        "generated_at": datetime.now(UTC).isoformat(),
        "graph_version": graph_version,
        "non_legal_advice_notice": NON_LEGAL_ADVICE_NOTICE,
    }


def dump_unavailable_envelope(reason: str) -> dict[str, Any]:
    """Degraded response when no graph dump is available (Section 13)."""
    return make_envelope(
        answer=None,
        status="requires_human_review",
        graph_version="unavailable",
        confidence=0.0,
        missing_facts=[reason],
    )


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _legal_status_notes(nodes: list[dict[str, Any]]) -> list[str]:
    return [
        f"{n['id']}: legal_status {n.get('legal_status', 'unknown_needs_review')}"
        for n in nodes
        if n.get("type") == "SourceDocument"
    ]


def _verdict_breakdown(items: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        verdict = item.get("judge_verdict", "unknown")
        out[verdict] = out.get(verdict, 0) + 1
    return out


def _layer2_block(dump_count: int, norms_payload: dict[str, Any] | None) -> dict[str, Any]:
    if norms_payload is None:
        return {
            "count": dump_count,
            "status": "not_started" if dump_count == 0 else "in_progress",
        }
    norms = norms_payload.get("norms", [])
    return {
        "count": len(norms),
        "status": "populated_high_risk_core",
        "verdicts": _verdict_breakdown(norms),
    }


def _layer3_block(
    dump_count: int, alignments_payload: dict[str, Any] | None
) -> dict[str, Any]:
    if alignments_payload is None:
        return {
            "count": dump_count,
            "status": "not_started" if dump_count == 0 else "in_progress",
        }
    assertions = alignments_payload.get("assertions", [])
    return {
        "count": len(assertions),
        "status": "populated_high_risk_core",
        "verdicts": _verdict_breakdown(assertions),
        "hleg_requirements": 7,
    }


def coverage_report(
    dump: dict[str, Any],
    norms_payload: dict[str, Any] | None = None,
    alignments_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structural coverage of the Layer 0+1 dump against the M1 acceptance.

    Checks the expected counts (113 articles, 180 recitals, 13 annexes,
    chapters I to XIII, a nonzero paragraph count), lists articles per
    chapter, reports layer 2 and layer 3 node counts, and verifies structural
    presence of the Section 10 high-risk core article set.

    When the judged M2 build artifacts are passed (norms_payload from
    extract_norms, alignments_payload from align_hleg_altai), the layer 2 and
    3 blocks report the real judged counts with verdict breakdowns instead of
    the dump-derived zeros.
    """
    nodes = dump.get("nodes", [])
    edges = dump.get("edges", [])
    graph_version = _graph_version(dump)

    nodes_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        nodes_by_type[node.get("type", "unknown")].append(node)

    article_numbers = {
        n.get("number") for n in nodes_by_type["Article"] if isinstance(n.get("number"), int)
    }
    chapter_numbers = {n.get("number") for n in nodes_by_type["Chapter"]}
    recital_count = len(nodes_by_type["Recital"])
    annex_count = len(nodes_by_type["Annex"])
    paragraph_count = len(nodes_by_type["Paragraph"])
    layer2_count = sum(1 for n in nodes if n.get("layer") == 2)
    layer3_count = sum(1 for n in nodes if n.get("layer") == 3)

    missing_facts: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            missing_facts.append(detail)

    check(
        "article_count",
        len(nodes_by_type["Article"]) == EXPECTED_ARTICLES,
        f"expected {EXPECTED_ARTICLES} Article nodes, found {len(nodes_by_type['Article'])}",
    )
    check(
        "recital_count",
        recital_count == EXPECTED_RECITALS,
        f"expected {EXPECTED_RECITALS} Recital nodes, found {recital_count}",
    )
    check(
        "annex_count",
        annex_count == EXPECTED_ANNEXES,
        f"expected {EXPECTED_ANNEXES} Annex nodes, found {annex_count}",
    )
    missing_chapters = [c for c in EXPECTED_CHAPTERS if c not in chapter_numbers]
    check(
        "chapters_i_to_xiii",
        not missing_chapters,
        f"missing Chapter nodes: {missing_chapters}",
    )
    check(
        "paragraph_count",
        paragraph_count > 0,
        f"expected a nonzero Paragraph count, found {paragraph_count}",
    )
    missing_core = [a for a in HIGH_RISK_CORE_ARTICLES if a not in article_numbers]
    check(
        "high_risk_core_present",
        not missing_core,
        f"high-risk core articles structurally missing: {missing_core}",
    )

    # Per-chapter article listing via HAS_ARTICLE edges (directly from a
    # chapter, or via a section reached by HAS_SECTION).
    node_by_id = {n["id"]: n for n in nodes}
    section_to_chapter: dict[str, str] = {}
    for edge in edges:
        if edge.get("edge_type") == "HAS_SECTION":
            section_to_chapter[edge["to"]] = edge["from"]
    per_chapter: dict[str, list[int]] = defaultdict(list)
    for edge in edges:
        if edge.get("edge_type") != "HAS_ARTICLE":
            continue
        parent = node_by_id.get(edge["from"], {})
        chapter_id = (
            edge["from"] if parent.get("type") == "Chapter" else section_to_chapter.get(edge["from"])
        )
        chapter = node_by_id.get(chapter_id or "", {})
        article = node_by_id.get(edge["to"], {})
        if chapter.get("type") == "Chapter" and isinstance(article.get("number"), int):
            per_chapter[str(chapter.get("number"))].append(article["number"])
    per_chapter_articles = {k: sorted(v) for k, v in sorted(per_chapter.items())}

    edge_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        edge_counts[edge.get("edge_type", "unknown")] += 1

    answer = {
        "expected": {
            "articles": EXPECTED_ARTICLES,
            "recitals": EXPECTED_RECITALS,
            "annexes": EXPECTED_ANNEXES,
            "chapters": list(EXPECTED_CHAPTERS),
        },
        "actual": {
            "articles": len(nodes_by_type["Article"]),
            "recitals": recital_count,
            "annexes": annex_count,
            "chapters": sorted(chapter_numbers, key=str),
            "paragraphs": paragraph_count,
        },
        "per_chapter_articles": per_chapter_articles,
        "high_risk_core": {
            "expected_articles": list(HIGH_RISK_CORE_ARTICLES),
            "present": [a for a in HIGH_RISK_CORE_ARTICLES if a in article_numbers],
            "missing": missing_core,
        },
        "layer2_nodes": _layer2_block(layer2_count, norms_payload),
        "layer3_nodes": _layer3_block(layer3_count, alignments_payload),
        "checks": checks,
    }

    return make_envelope(
        answer=answer,
        status="satisfied_with_evidence" if not missing_facts else "requires_human_review",
        graph_version=graph_version,
        source_nodes=[n["id"] for n in nodes_by_type["Regulation"]],
        graph_evidence_subgraph={
            "node_counts_by_type": {t: len(ns) for t, ns in sorted(nodes_by_type.items())},
            "edge_counts_by_type": dict(sorted(edge_counts.items())),
        },
        legal_status_notes=_legal_status_notes(nodes),
        missing_facts=missing_facts,
    )


def source_trace(
    dump: dict[str, Any], node_id: str, snapshots_dir: Path | str | None = None
) -> dict[str, Any]:
    """Trace a node back to its frozen source snapshot.

    Returns the snapshot file, its sha256, the span start and end offsets,
    the HTML anchor, and a text excerpt. An unknown node_id returns status
    not_applicable with missing_facts populated, never an exception.

    The excerpt is capped at _EXCERPT_MAX_CHARS (500) characters for payload
    discipline: a long provision (Article 5(1) is over 13,000 characters)
    should not ride on every trace call. That cap must never produce a
    silent partial quote, so the answer always also carries:
      - excerpt_truncated: True when the excerpt is shorter than the full
        resolved source text (i.e. the cap actually cut something).
      - excerpt_chars: the character length of the returned excerpt.
      - span_chars: the character length of the FULL resolved source text,
        so a consumer can see what fraction of the provision it received
        (excerpt_chars / span_chars) without re-deriving it from
        span_start/span_end, which describe the full span regardless of the
        excerpt cap and must not be mistaken for proof of completeness.
      The excerpt string itself is never altered to signal truncation (it
      stays byte-exact against the source, per VERBATIM_QUOTE_FIELDS above,
      which excerpt is a member of): truncation is signalled only through
      these three flags, never by appending marker text into the quote.
    The full verbatim text of the span, untruncated, is always available
    byte-exact via the resolve_span MCP tool (spans.py) keyed by the same
    span_id, or the HTTP facade's /api/span/{span_id} endpoint, both of
    which return the whole resolved slice with no cap.
    """
    nodes = dump.get("nodes", [])
    graph_version = _graph_version(dump)
    node = next((n for n in nodes if n.get("id") == node_id), None)

    if node is None:
        return make_envelope(
            answer={"node_id": node_id, "found": False},
            status="not_applicable",
            graph_version=graph_version,
            missing_facts=[
                f"node_id '{node_id}' is not present in graph dump build {graph_version}"
            ],
        )

    span = node.get("source_span")
    if not span:
        return make_envelope(
            answer={"node_id": node_id, "found": True, "type": node.get("type")},
            status="requires_human_review",
            graph_version=graph_version,
            source_nodes=[node_id],
            missing_facts=[
                f"node '{node_id}' carries no source_span; its source trace cannot be verified"
            ],
        )

    excerpt, span_chars = _excerpt(node, span, dump, snapshots_dir)
    excerpt_chars = len(excerpt) if excerpt is not None else 0
    excerpt_truncated = excerpt is not None and excerpt_chars < span_chars
    legal_status_notes = _legal_status_notes(nodes)
    if node.get("type") == "Recital":
        legal_status_notes = legal_status_notes + [
            "Recitals are context only and never binding (architecture.md Section 1)"
        ]

    answer = {
        "node_id": node_id,
        "found": True,
        "type": node.get("type"),
        "layer": node.get("layer"),
        "snapshot_file": span.get("snapshot_file"),
        "snapshot_sha256": span.get("snapshot_sha256"),
        "span_start": span.get("start"),
        "span_end": span.get("end"),
        "anchor": span.get("anchor"),
        "excerpt": excerpt,
        "excerpt_truncated": excerpt_truncated,
        "excerpt_chars": excerpt_chars,
        "span_chars": span_chars,
    }
    return make_envelope(
        answer=answer,
        status="satisfied_with_evidence",
        graph_version=graph_version,
        source_nodes=[node_id],
        source_spans=[span],
        graph_evidence_subgraph={"nodes": [node_id], "edges": []},
        legal_status_notes=legal_status_notes,
    )


def _excerpt(
    node: dict[str, Any],
    span: dict[str, Any],
    dump: dict[str, Any],
    snapshots_dir: Path | str | None,
) -> tuple[str | None, int]:
    """Capped text excerpt for a traced node, plus the full resolved length.

    Resolves the literal snapshot slice through resolve_span, which reads the
    snapshot as BYTES then decodes. The span offsets are computed over that
    raw byte-decoded text, which preserves CRLF line endings; the previous
    Path.read_text applied universal-newline translation, collapsing every
    \\r\\n to \\n and shifting all later offsets, so it returned the wrong
    provision (audit 2026-07-21, measured on the CRLF-terminated EUR-Lex
    HTML). resolve_span also verifies the snapshot sha256 and guards against
    path escape. Falls back to the node's own text or title when the span
    cannot be resolved.

    Returns (excerpt, span_chars): excerpt is the first _EXCERPT_MAX_CHARS
    characters of whichever full text was actually resolved (byte-exact,
    never altered), or None when no text could be resolved at all;
    span_chars is the character length of that full resolved text (0 when
    nothing was resolved), so the caller can flag truncation as
    excerpt_chars < span_chars without a second read of the snapshot.
    """
    span_id = span.get("span_id")
    full_text: str | None = None
    if snapshots_dir is not None and span_id:
        # Lazy import: spans imports make_envelope from this module.
        from tere4ai.mcp_server.spans import SpanResolutionError, resolve_span

        try:
            resolved = resolve_span(str(span_id), dump, snapshots_dir)
            full_text = resolved["text"]
        except (SpanResolutionError, OSError, KeyError):
            full_text = None
    if full_text is None:
        fallback = node.get("text") or node.get("title")
        full_text = fallback if isinstance(fallback, str) else None
    if full_text is None:
        return None, 0
    return full_text[:_EXCERPT_MAX_CHARS], len(full_text)

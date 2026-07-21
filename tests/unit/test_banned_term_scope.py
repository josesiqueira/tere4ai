"""DEC-08 banned-term scope: system-generated fields versus verbatim quotes.

@implements: DEC-08
@grounded_by: REF-16

DEC-08 bans the terms compliant, certified, and legally approved from every
SYSTEM-GENERATED text field of every envelope (status, composed answer text,
legal_status_notes, missing_facts, summaries, messages, backlog titles and
descriptions). Fields that carry VERBATIM quoted text are exempt: frozen EU
AI Act source text, norm deontic content quoted from the Act, alignment
evidence quotes, verbatim project-evidence quotes, and replayed generator or
judge rationales. The law's own sentences literally say things such as
"compliant with the requirements" (Article 8(2), Article 16 point (a)), so
those words are the regulator's, not a TERE4AI claim; they are structurally
marked by their field names, and altering them would break the byte-exact
traceability of quoted source text, a harder invariant than the wording ban.
A live audit on 2026-07-21 found the word inside quoted Act text returned by
get_applicable_requirements; the decided fix scopes the ban rather than
sanitizing the quote.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server.requirements import get_applicable_requirements
from tere4ai.mcp_server.tools import (
    BANNED_CLAIM_TERMS,
    STATUS_VOCABULARY,
    VERBATIM_QUOTE_FIELDS,
    strip_verbatim_quote_fields,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = ROOT / "data" / "graph_dumps" / "alignments_core.json"

# Fields the system composes itself; they carry TERE4AI's own words and must
# therefore always be inside the banned-term scan, never exempt.
SYSTEM_GENERATED_FIELDS = (
    "status",
    "answer",
    "legal_status_notes",
    "missing_facts",
    "non_legal_advice_notice",
    "message",
    "summary",
    "notes",
    "review_note",
    "needs_human_review_note",
    "gaps",
    "description",
)


def assert_no_banned_terms(envelope: dict) -> None:
    """The scoped DEC-08 scan: scrub verbatim-quote fields, then ban terms."""
    serialized = json.dumps(strip_verbatim_quote_fields(envelope)).lower()
    for term in BANNED_CLAIM_TERMS:
        assert term not in serialized, f"banned term {term!r} in a system-generated field"
        underscored = term.replace(" ", "_")
        assert underscored not in serialized, (
            f"banned term {underscored!r} in a system-generated field"
        )


# The scope definition itself -------------------------------------------------


def test_banned_terms_are_the_dec08_closed_set():
    assert BANNED_CLAIM_TERMS == ("compliant", "certified", "legally approved")


def test_verbatim_exemption_never_covers_system_generated_fields():
    """The exemption is structural: only quote-carrying fields, never any
    field in which TERE4AI speaks for itself."""
    for field in SYSTEM_GENERATED_FIELDS:
        assert field not in VERBATIM_QUOTE_FIELDS, (
            f"system-generated field {field!r} must not be exempt from DEC-08"
        )


def test_status_vocabulary_never_contains_banned_terms():
    for status in STATUS_VOCABULARY:
        lowered = status.lower()
        for term in BANNED_CLAIM_TERMS:
            assert term not in lowered
            assert term.replace(" ", "_") not in lowered


# Verbatim quotes are preserved byte-exact and exempt (fixture) ---------------

# Mimics the served norm for Article 8(2), whose object quotes the Act's own
# wording; the real published norm carries the same phrase.
ARTICLE_8_2_OBJECT = (
    "compliant with the requirements established in this Section, taking "
    "into account the intended purpose of the high-risk AI system"
)

_FIXTURE_NORM = {
    "norm_id": "norm:eu-ai-act:article-8:paragraph-2:n1",
    "source_node_id": "eu-ai-act:article-8:paragraph-2",
    "source_span_id": "span:008.002",
    "deontic_type": "obligation",
    "modal": "shall",
    "actor_explicit": "providers of high-risk AI systems",
    "actor_inferred": "provider",
    "action": "ensure that the high-risk AI system is",
    "object": ARTICLE_8_2_OBJECT,
    "judge_verdict": "accepted",
}

_FIXTURE_NORMS_PAYLOAD = {
    "build": {"build_id": "build-banned-term-scope-fixture"},
    "norms": [_FIXTURE_NORM],
}

_FIXTURE_DUMP = {
    "build": {"build_id": "build-banned-term-scope-fixture"},
    "nodes": [
        {"id": "eu-ai-act:article-8", "type": "Article", "number": 8, "layer": 1},
        {
            "id": "eu-ai-act:article-8:paragraph-2",
            "type": "Paragraph",
            "layer": 1,
        },
    ],
    "edges": [],
}


def test_verbatim_quote_field_may_say_compliant_and_is_preserved_byte_exact():
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, _FIXTURE_NORMS_PAYLOAD, _FIXTURE_DUMP
    )
    entries = envelope["answer"]["requirements_by_article"]["article-8"]
    entry = next(e for e in entries if e["norm_id"] == _FIXTURE_NORM["norm_id"])
    # Byte-exact: the quoted deontic wording is never sanitized or altered.
    assert entry["object"] == ARTICLE_8_2_OBJECT
    assert "compliant" in entry["object"]
    # The word therefore appears in the raw serialization (the exemption is
    # real, not vacuous)...
    assert "compliant" in json.dumps(envelope).lower()
    # ...but every system-generated field stays clean under the scoped scan.
    assert_no_banned_terms(envelope)


# The scoped scan over the published build artifacts --------------------------

pytestmark_dumps = pytest.mark.skipif(
    not (DUMP_PATH.is_file() and NORMS_PATH.is_file() and ALIGNMENTS_PATH.is_file()),
    reason="published graph dumps not built",
)


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms_payload() -> dict:
    if not NORMS_PATH.is_file():
        pytest.skip("norms_core.json not built")
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def alignments_payload() -> dict:
    if not ALIGNMENTS_PATH.is_file():
        pytest.skip("alignments_core.json not built")
    return json.loads(ALIGNMENTS_PATH.read_text(encoding="utf-8"))


@pytestmark_dumps
def test_published_requirement_quote_with_compliant_is_served_byte_exact(
    dump, norms_payload
):
    """The real published norms that quote 'compliant with the requirements'
    must reach the consumer unaltered."""
    quoting = [
        n
        for n in norms_payload["norms"]
        if n.get("judge_verdict") == "accepted"
        and "compliant" in str(n.get("object", "")).lower()
    ]
    if not quoting:
        pytest.skip("no accepted norm in the published dump quotes 'compliant'")
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump
    )
    served = {
        e["norm_id"]: e
        for group in envelope["answer"]["requirements_by_article"].values()
        for e in group
    }
    for norm in quoting:
        entry = served.get(norm["norm_id"])
        if entry is None:
            # Accepted but outside the requirement scope (for example an
            # annex or classification group); scope filtering is not this
            # test's subject.
            continue
        assert entry["object"] == norm["object"], (
            f"verbatim quote altered for {norm['norm_id']}"
        )
    assert_no_banned_terms(envelope)


@pytestmark_dumps
def test_offline_endpoints_have_no_banned_terms_in_system_fields(
    dump, norms_payload, alignments_payload
):
    """Cross-endpoint scoped scan over the real build artifacts: coverage,
    trace, classify, requirements, explain, alignment trace."""
    from tere4ai.mcp_server.classify import classify_ai_system
    from tere4ai.mcp_server.explain import explain_requirement
    from tere4ai.mcp_server.tools import coverage_report, source_trace
    from tere4ai.mcp_server.trace import trace_alignment

    classification = classify_ai_system(
        {
            "description": "AI system that screens and ranks job applicants.",
            "domain": "employment",
            "flags": {"social_scoring": False},
        },
        dump,
    )
    accepted_norm_id = next(
        n["norm_id"]
        for n in norms_payload["norms"]
        if n.get("judge_verdict") == "accepted"
    )
    envelopes = [
        coverage_report(dump, norms_payload, alignments_payload),
        # Article 82 is titled "Compliant AI systems which present a risk" in
        # the Act itself; its trace must still pass the scoped scan.
        source_trace(dump, "eu-ai-act:article-82"),
        classification,
        get_applicable_requirements(classification, norms_payload, dump),
        explain_requirement(accepted_norm_id, dump, norms_payload, alignments_payload),
        trace_alignment(accepted_norm_id, alignments_payload, dump),
    ]
    for envelope in envelopes:
        assert_no_banned_terms(envelope)

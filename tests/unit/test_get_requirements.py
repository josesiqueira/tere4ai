"""Unit tests for get_applicable_requirements (M3 deterministic runtime tool).

Offline only: runs against the real published Layer 0+1 dump and the judged
norms build artifact on disk, skipping when either has not been built. No
model, no network, no database.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from tere4ai.mcp_server import requirements as requirements_module
from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.requirements import get_applicable_requirements
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE, STATUS_VOCABULARY

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

pytestmark = pytest.mark.skipif(
    not (DUMP_PATH.is_file() and NORMS_PATH.is_file()),
    reason="layer1.json or norms_core.json dump not built",
)


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms_payload() -> dict:
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_ids(dump) -> set:
    return {n["id"] for n in dump["nodes"]}


def _group(source_node_id: str) -> str:
    return source_node_id.split(":")[1]


def assert_envelope_invariants(envelope: dict, node_ids: set) -> None:
    assert envelope["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    assert envelope["status"] in STATUS_VOCABULARY
    assert envelope["judge_verdict"] == "not_applicable_deterministic"
    # DEC-08: the tool's own text never says compliant or certified. Norm
    # entries quote the Act's deontic content verbatim (Article 8(2) and
    # Article 16 point (a) literally say "compliant with the requirements"),
    # so the quoted action/object/conditions fields are excluded from this
    # check: they are cited legal source text, not a claim by the tool.
    scrubbed = json.loads(json.dumps(envelope))
    for group in scrubbed.get("answer", {}).get("requirements_by_article", {}).values():
        for entry in group:
            for quoted_field in ("action", "object", "conditions"):
                entry.pop(quoted_field, None)
    serialized = json.dumps(scrubbed).lower()
    assert "compliant" not in serialized
    assert "certified" not in serialized
    for node_id in envelope["source_nodes"]:
        assert node_id in node_ids, f"cited node {node_id} not in dump"


# Prohibited: zero requirements ------------------------------------------------


def test_prohibited_returns_zero_requirements(dump, norms_payload, node_ids):
    classification = classify_ai_system(
        {
            "description": "Deepfake intimate content generator used for coercion.",
            "flags": {
                "social_scoring": False,
                "subliminal_or_manipulative": True,
                "causes_significant_harm": True,
            },
        },
        dump,
    )
    assert classification["answer"]["risk_category"] == "prohibited"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["requirements_by_article"] == {}
    assert answer["summary"]["returned"] == 0
    assert "no engineering requirements" in answer["message"]
    # Cites the prohibition node carried over from the classification.
    assert "eu-ai-act:article-5:paragraph-1:point-a" in envelope["source_nodes"]
    assert any("Article 5" in note for note in envelope["legal_status_notes"])


def test_prohibited_bare_answer_falls_back_to_article_5(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "prohibited"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["answer"]["requirements_by_article"] == {}
    assert envelope["source_nodes"] == ["eu-ai-act:article-5"]


# High risk: all judge-accepted norms, grouped ----------------------------------


def test_high_risk_returns_only_accepted_norms_grouped(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "applicable_missing_evidence"
    answer = envelope["answer"]

    from tere4ai.mcp_server.requirements import _is_requirement_group

    def _in_req_scope(n):
        return _is_requirement_group(_group(n["source_node_id"]))

    verdict_by_norm = {n["norm_id"]: n["judge_verdict"] for n in norms_payload["norms"]}
    # Audit W3: a high-risk system's requirements are the obligation regime,
    # never the classification/prohibition groups (Article 5/6/7, Annex).
    accepted = [
        n
        for n in norms_payload["norms"]
        if n["judge_verdict"] == "accepted" and _in_req_scope(n)
    ]
    needs_review = [
        n
        for n in norms_payload["norms"]
        if n["judge_verdict"] == "needs_human_review" and _in_req_scope(n)
    ]

    entries = [e for group in answer["requirements_by_article"].values() for e in group]
    # Only accepted requirement-group norms, and all of them.
    assert all(verdict_by_norm[e["norm_id"]] == "accepted" for e in entries)
    assert len(entries) == len(accepted)
    assert answer["summary"]["total_accepted_in_scope"] == len(accepted)
    assert answer["summary"]["returned"] == len(accepted)
    # No classification or prohibition group is ever served as a requirement.
    served_groups = set(answer["requirements_by_article"])
    assert "article-5" not in served_groups
    assert not any(g.startswith("annex-") for g in served_groups)

    # Grouping matches each norm's source article or annex.
    for group, group_entries in answer["requirements_by_article"].items():
        for entry in group_entries:
            assert _group(entry["source_node_id"]) == group

    # Per-article counts match the dump.
    accepted_counts = Counter(_group(n["source_node_id"]) for n in accepted)
    review_counts = Counter(_group(n["source_node_id"]) for n in needs_review)
    for group, counts in answer["summary"]["per_article"].items():
        assert counts["accepted"] == accepted_counts.get(group, 0)
        assert counts["needs_human_review"] == review_counts.get(group, 0)
    assert sum(c["accepted"] for c in answer["summary"]["per_article"].values()) == len(accepted)

    # needs_human_review norms are reported but never returned.
    assert answer["summary"]["needs_human_review_total"] == len(needs_review)
    returned_ids = {e["norm_id"] for e in entries}
    assert not returned_ids & {n["norm_id"] for n in needs_review}

    # Entry shape: the fields the spec requires.
    for entry in entries[:20]:
        for field in (
            "norm_id",
            "deontic_type",
            "modal",
            "actor",
            "action",
            "object",
            "source_node_id",
            "source_span_id",
        ):
            assert field in entry, field

    # Cited group nodes exist in the dump; spans carry the norms' span ids.
    assert envelope["source_nodes"]
    assert len(envelope["source_spans"]) == len(accepted)
    span_ids = {s["span_id"] for s in envelope["source_spans"]}
    assert span_ids == {n["source_span_id"] for n in accepted}


def test_high_risk_entries_carry_conditions_when_present(dump, norms_payload):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump
    )
    entries = [
        e
        for group in envelope["answer"]["requirements_by_article"].values()
        for e in group
    ]
    from tere4ai.mcp_server.requirements import _is_requirement_group

    with_conditions = [e for e in entries if "conditions" in e]
    conditioned_accepted = [
        n
        for n in norms_payload["norms"]
        if n["judge_verdict"] == "accepted"
        and n.get("conditions")
        and _is_requirement_group(_group(n["source_node_id"]))
    ]
    assert len(with_conditions) == len(conditioned_accepted)


def test_actor_filter_provider(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump, actor="provider"
    )
    assert_envelope_invariants(envelope, node_ids)
    entries = [
        e
        for group in envelope["answer"]["requirements_by_article"].values()
        for e in group
    ]
    assert entries, "provider filter should match norms in the high-risk core"
    norms_by_id = {n["norm_id"]: n for n in norms_payload["norms"]}
    for entry in entries:
        norm = norms_by_id[entry["norm_id"]]
        assert norm.get("actor_inferred") == "provider" or "provider" in (
            norm.get("actor_explicit") or ""
        ).lower(), entry["norm_id"]
    assert envelope["answer"]["summary"]["actor_filter"] == "provider"
    assert envelope["answer"]["summary"]["returned"] == len(entries)
    accepted = [n for n in norms_payload["norms"] if n["judge_verdict"] == "accepted"]
    assert len(entries) < len(accepted)


def test_actor_filter_rejects_non_canonical_actor(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump, actor="vendor"
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert any("canonical actor vocabulary" in f for f in envelope["missing_facts"])


# Transparency only: Article 50 norms only --------------------------------------


def test_transparency_only_returns_article_50_norms_only(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "transparency_only"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "applicable_missing_evidence"
    answer = envelope["answer"]
    assert set(answer["requirements_by_article"]) == {"article-50"}
    accepted_50 = [
        n
        for n in norms_payload["norms"]
        if n["judge_verdict"] == "accepted" and _group(n["source_node_id"]) == "article-50"
    ]
    assert len(answer["requirements_by_article"]["article-50"]) == len(accepted_50)
    assert envelope["source_nodes"] == ["eu-ai-act:article-50"]
    for entry in answer["requirements_by_article"]["article-50"]:
        assert entry["source_node_id"].startswith("eu-ai-act:article-50")


# Minimal and uncertain ----------------------------------------------------------


def test_minimal_returns_empty_not_applicable(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "minimal_or_none"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert envelope["answer"]["message"]


def test_uncertain_requires_human_review(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "uncertain"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "requires_human_review"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert envelope["missing_facts"]


def test_unrecognised_risk_category_is_graceful(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "sky_high"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert any("not a recognised" in f for f in envelope["missing_facts"])


def test_empty_norms_payload_degrades_never_fabricates(dump, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, {"norms": []}, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "requires_human_review"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert any("no norms" in f for f in envelope["missing_facts"])


# End-to-end over the classify envelope ------------------------------------------


def test_classify_envelope_feeds_requirements(dump, norms_payload, node_ids):
    classification = classify_ai_system(
        {
            "description": "Hospital emergency department triage support system.",
            "domain": "healthcare",
            "flags": {"essential_services_access": True},
        },
        dump,
    )
    assert classification["answer"]["risk_category"] == "high_risk"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "applicable_missing_evidence"
    assert envelope["answer"]["requirements_by_article"]


# Determinism and purity ----------------------------------------------------------


def test_requirements_are_deterministic(dump, norms_payload):
    first = get_applicable_requirements({"risk_category": "high_risk"}, norms_payload, dump)
    second = get_applicable_requirements({"risk_category": "high_risk"}, norms_payload, dump)
    for key in ("answer", "status", "source_nodes", "source_spans", "missing_facts"):
        assert first[key] == second[key]


def test_no_model_client_imports_in_module_source():
    source = Path(requirements_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "model_clients", "ModelClient", "fastmcp"):
        assert forbidden not in source, f"requirements.py must not reference {forbidden}"
    for dash in (chr(0x2014), chr(0x2013)):
        assert dash not in source, "no em or en dashes"


# Exceptions (carve-outs) must never be silently dropped ---------------------------


def test_requirement_entry_carries_exceptions_when_the_norm_has_them():
    """A carve-out ("shall not apply where...") limits the obligation; a
    consumer building to the requirement without it over-implements or
    mis-implements. Mirror of the conditions behavior."""
    norm = {
        "norm_id": "norm:test:n1",
        "deontic_type": "obligation",
        "modal": "shall",
        "actor_explicit": "provider",
        "action": "notify",
        "object": "the authority",
        "source_node_id": "eu-ai-act:article-99",
        "source_span_id": "span:099.001",
        "conditions": ["where the system is deployed"],
        "exceptions": ["unless already notified under other Union law"],
    }
    entry = requirements_module._requirement_entry(norm)
    assert entry["conditions"] == ["where the system is deployed"]
    assert entry["exceptions"] == ["unless already notified under other Union law"]


def test_no_served_requirement_drops_its_norms_exceptions(dump, norms_payload):
    """Census over the real dump: every served entry whose source norm
    carries exceptions must surface them verbatim."""
    by_id = {n["norm_id"]: n for n in norms_payload["norms"]}
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump
    )
    checked = 0
    for entries in envelope["answer"]["requirements_by_article"].values():
        for entry in entries:
            norm = by_id[entry["norm_id"]]
            if norm.get("exceptions"):
                checked += 1
                assert entry.get("exceptions") == norm["exceptions"], (
                    f"{entry['norm_id']} served without its exceptions"
                )
    assert checked > 0, (
        "census vacuous: no served high-risk requirement has exceptions; "
        "expected some (37 accepted norms carry them)"
    )

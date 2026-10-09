"""Unit tests for get_applicable_requirements (MILESTONE3 deterministic runtime tool).

Offline only: runs against the real published Layer 0+1 dump and the judged
norms build artifact on disk, skipping when either has not been built. No
model, no network, no database.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from tere4ai import act_parties as ap
from tere4ai.mcp_server import classify as classify_module
from tere4ai.mcp_server import requirements as requirements_module
from tere4ai.mcp_server.classify import classify_ai_system
from tere4ai.mcp_server.requirements import (
    UNCERTAIN_HIGH_RISK_MESSAGE,
    UNCERTAIN_MESSAGE,
    get_applicable_requirements,
)
from tere4ai.mcp_server.tools import (
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
    strip_verbatim_quote_fields,
)
from tere4ai.parse_legal_structure import amendments as amend

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
    # DEC-08 banned-term scope: the tool's own text never says compliant or
    # certified. Norm entries quote the Act's deontic content verbatim
    # (Article 8(2) and Article 16 point (a) literally say "compliant with
    # the requirements"), so the verbatim-quote fields are scrubbed before
    # the check: they are cited legal source text, not a claim by the tool.
    # The shared exemption list lives in tools.VERBATIM_QUOTE_FIELDS; see
    # tests/unit/test_banned_term_scope.py for the full scoped contract.
    serialized = json.dumps(strip_verbatim_quote_fields(envelope)).lower()
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
    assert classification["answer"]["risk_category"] == "unacceptable_risk"
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
        {"risk_category": "unacceptable_risk"}, norms_payload, dump
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

    deleted_units = {x["id"] for x in dump["nodes"] if amend.is_deleted(x)}

    def _in_req_scope(n):
        # F7: a norm on a unit the Omnibus deleted is no requirement of the Act in force
        return _is_requirement_group(_group(n["source_node_id"])) and n["source_node_id"] not in deleted_units

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
            "addressee",
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
        and n["source_node_id"] not in {x["id"] for x in dump["nodes"] if amend.is_deleted(x)}
    ]
    assert len(with_conditions) == len(conditioned_accepted)


def test_addressee_filter_provider(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump, "provider"
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
        assert entry["addressee"] in ("provider", "operator_general"), entry["norm_id"]
        assert ap.addressee_of(norm).value in ("provider", "operator_general"), entry["norm_id"]
    assert envelope["answer"]["summary"]["addressee_filter"] == "provider"
    assert envelope["answer"]["summary"]["returned"] == len(entries)
    accepted = [n for n in norms_payload["norms"] if n["judge_verdict"] == "accepted"]
    assert len(entries) < len(accepted)


def test_addressee_filter_refuses_a_value_outside_the_list(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "high_risk"}, norms_payload, dump, "vendor"
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert any("is not a party a request can name" in f for f in envelope["missing_facts"])


# Transparency only: Article 50 norms only --------------------------------------


def test_transparency_only_returns_article_50_norms_only(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "limited_risk"}, norms_payload, dump
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
        {"risk_category": "minimal_risk"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["requirements_by_article"] == {}
    assert envelope["answer"]["message"]


def test_uncertain_requires_human_review(dump, norms_payload, node_ids):
    envelope = get_applicable_requirements(
        {"risk_category": "undetermined"}, norms_payload, dump
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


def test_old_level_value_is_refused_not_mapped(dump, norms_payload, node_ids):
    """DEC-20: an answer from before B118 sent back is refused with not_applicable
    and confidence 0, its old value named; it is not mapped (CHANGELOG)."""
    envelope = get_applicable_requirements(
        {"risk_category": "transparency_only"}, norms_payload, dump
    )
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "not_applicable"
    assert envelope["confidence"] == 0.0
    from tere4ai.mcp_server.classify import RISK_CATEGORIES

    refusal = [f for f in envelope["missing_facts"] if "'transparency_only'" in f]
    assert refusal
    assert all(category in refusal[0] for category in RISK_CATEGORIES)


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
    # This classify envelope is itself unsettled: it is flagged
    # requires_human_review at confidence 0.5 with prohibition-relevant facts
    # still unknown. The provisional requirements flow through so the answer
    # stays useful, but the abstention must be preserved (DEC-08, C1 fix): the
    # requirements envelope must never claim more certainty than the
    # classification it rests on.
    assert classification["status"] == "requires_human_review"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "requires_human_review"
    assert envelope["confidence"] == classification["confidence"]
    assert envelope["missing_facts"]
    assert envelope["answer"].get("provisional") is True
    assert envelope["answer"]["requirements_by_article"]


# Unsettled classification must never be laundered into certainty (DEC-08) ---------


def test_unsettled_classification_is_not_laundered_into_certainty(
    dump, norms_payload, node_ids
):
    """Regression for C1: a moodwatch-safety-shaped classify envelope that is
    flagged requires_human_review at confidence 0.5 with a real missing fact
    (its risk_category is a tentative high_risk that could still settle to
    prohibited) must not become a confident applicable_missing_evidence answer
    with empty missing_facts when chained into get_applicable_requirements."""
    missing = (
        "the point (f) medical or safety exception decides whether the system "
        "is prohibited (Article 5); absence does not settle the ban, so the "
        "classification stays for human review"
    )
    upstream = {
        "answer": {"risk_category": "high_risk"},
        "status": "requires_human_review",
        "confidence": 0.5,
        "missing_facts": [missing],
        "source_nodes": [],
    }
    envelope = get_applicable_requirements(upstream, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    # The abstention is preserved, never upgraded.
    assert envelope["status"] == "requires_human_review"
    assert envelope["status"] != "applicable_missing_evidence"
    assert envelope["confidence"] == 0.5
    assert envelope["confidence"] != 1.0
    assert missing in envelope["missing_facts"]
    assert envelope["missing_facts"] != []
    # The provisional requirements may still be listed, but marked provisional.
    assert envelope["answer"].get("provisional") is True


def test_settled_high_risk_still_confident_no_regression(dump, norms_payload, node_ids):
    """A genuinely settled high_risk classification (confidence 1.0, no missing
    facts) must still return applicable_missing_evidence at confidence 1.0 and
    must not be marked provisional."""
    settled = {
        "answer": {"risk_category": "high_risk"},
        "status": "applicable_missing_evidence",
        "confidence": 1.0,
        "missing_facts": [],
        "source_nodes": [],
    }
    envelope = get_applicable_requirements(settled, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    assert envelope["status"] == "applicable_missing_evidence"
    assert envelope["confidence"] == 1.0
    assert "provisional" not in envelope["answer"]


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


def test_uncertain_message_follows_the_classification_state(dump, norms_payload):
    """Research case 3 followed by its requirements call: Article 5 is ruled
    out and only an Annex III fact is missing, so the message must not say
    prohibition-relevant facts are unknown (Codex brief finding 8)."""
    all_false = {
        **dict.fromkeys(classify_module.PROHIBITION_RELEVANT_FLAGS, False),
        **dict.fromkeys(classify_module.ANNEX_III_RELEVANT_FLAGS, False),
        "interacts_with_natural_persons": False,
        "generates_synthetic_content": False,
        "medical_or_safety_component": False,
        "annex_i_covered_product": False,
    }
    del all_false["employment_decisions"]
    classification = classify_ai_system({"description": "A hiring helper.", "flags": all_false}, dump)
    assert classification["answer"]["risk_category"] == "undetermined"
    assert classification["answer"]["unacceptable_risk"] is False
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert envelope["answer"]["message"] == UNCERTAIN_HIGH_RISK_MESSAGE


def test_uncertain_message_names_article_5_when_prohibited_is_unknown(dump, norms_payload):
    classification = classify_ai_system({"description": "Nothing settled."}, dump)
    assert classification["answer"]["unacceptable_risk"] is None
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert envelope["answer"]["message"] == UNCERTAIN_MESSAGE


def test_bare_uncertain_answer_keeps_the_conservative_message(dump, norms_payload):
    envelope = get_applicable_requirements({"risk_category": "undetermined"}, norms_payload, dump)
    assert envelope["answer"]["message"] == UNCERTAIN_MESSAGE


def test_high_risk_keeps_the_whole_article_50_group_without_a_trigger(dump, norms_payload):
    """DEC-18: get_applicable_requirements is not gated on the answer's
    transparency_duties: the triggers do not cover 50(4) or 50(5), so a
    high-risk system is served the whole Article 50 group (the conservative
    side) even when no trigger is known true."""
    flags = {
        **dict.fromkeys(classify_module.PROHIBITION_RELEVANT_FLAGS, False),
        **dict.fromkeys(classify_module.ANNEX_III_RELEVANT_FLAGS, False),
        **dict.fromkeys(classify_module.ARTICLE_50_TRIGGER_FLAGS, False),
        "employment_decisions": True,
    }
    classification = classify_ai_system({"description": "CV screening for hiring.", "flags": flags}, dump)
    assert classification["answer"]["risk_category"] == "high_risk"
    assert classification["answer"]["transparency_duties"] == []
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert "article-50" in envelope["answer"]["requirements_by_article"]


# DEC-19: the requirement type on every served requirement whose norm
# carries it; a norm from a build before DEC-19 gets no key.


def test_requirement_entry_carries_the_type_when_the_norm_has_it():
    base = {"norm_id": "norm:test:n1", "deontic_type": "obligation", "modal": "shall",
            "actor_explicit": "provider", "action": "keep", "object": "the logs",
            "source_node_id": "eu-ai-act:article-19:paragraph-1", "source_span_id": "span:019.001"}
    assert requirements_module._requirement_entry({**base, "requirement_type": "process"})["requirement_type"] == "process"
    assert requirements_module._requirement_entry({**base, "requirement_type": None})["requirement_type"] is None
    assert "requirement_type" not in requirements_module._requirement_entry(base)


def test_the_pre_dec_19_norms_build_serves_no_type(dump, norms_payload):
    """norms_core.json predates DEC-19 (disposable, replaced at B74): no
    served entry gains a type it never had."""
    envelope = get_applicable_requirements({"risk_category": "high_risk"}, norms_payload, dump)
    entries = [e for rows in envelope["answer"]["requirements_by_article"].values() for e in rows]
    assert entries
    assert all("requirement_type" not in e for e in entries)


def test_a_norm_on_a_unit_the_omnibus_deleted_is_not_a_requirement(dump, norms_payload):
    """Final review F7 (brief D3: requirement selection skips deleted units). The dev
    norms were extracted from the 2024 text and D9 dropped those on changed units,
    so one accepted norm is moved onto the deleted paragraph."""
    norm = next(n for n in norms_payload["norms"] if n.get("judge_verdict") == "accepted"
                and n["source_node_id"].startswith("eu-ai-act:article-9:"))
    deleted = [{**norm, "norm_id": "norm:eu-ai-act:article-10:paragraph-5:n1",
                "source_node_id": "eu-ai-act:article-10:paragraph-5", "source_span_id": "span:010.005"}]
    payload = {**norms_payload, "norms": [*norms_payload["norms"], *deleted]}
    answer = get_applicable_requirements({"risk_category": "high_risk"}, payload, dump)["answer"]
    entries = [e for group in answer["requirements_by_article"].values() for e in group]
    assert entries
    assert not [e for e in entries if e["source_node_id"].startswith("eu-ai-act:article-10:paragraph-5")]
    assert answer["summary"]["deleted_source_skipped"] >= len(deleted)


def test_groups_follow_the_acts_order_with_letter_suffixed_articles():
    """Final review F10: article-4a sorts between article-4 and article-5."""
    from tere4ai.mcp_server.requirements import _group_sort_key

    groups = ["article-50", "annex-iii", "article-5", "article-4a", "article-3", "article-4"]
    assert sorted(groups, key=_group_sort_key) == [
        "article-3", "article-4", "article-4a", "article-5", "article-50", "annex-iii"]


# B132 (spec G D-G68 (6), rulings R6, R7, R14, R26, R36, R37, R39): the Annex I section, the
# application dates of the served groups, and the text every answer follows.

AMENDED = "Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744"


def _annex_i(section: bool | None, **facts: bool) -> dict:
    flags = {name: False for name in classify_module.PROHIBITION_RELEVANT_FLAGS}
    flags.update({name: False for name in classify_module.ANNEX_III_RELEVANT_FLAGS})
    flags.update(annex_i_covered_product=True, third_party_conformity_assessment_required=True, **facts)
    if section is not None:
        flags[classify_module.ANNEX_I_SECTION_FACT] = section
    return {"description": "AI safety component of a machine.", "flags": flags}


def test_a_section_b_system_is_served_article_2_2_not_chapter_iii(dump, norms_payload, node_ids):
    """R6: no Chapter III obligation and no norm; Article 2(2)'s provisions
    cited, its condition on Articles 57 to 59 stated and not decided."""
    classification = classify_ai_system(_annex_i(True), dump)
    assert classification["answer"]["annex_i_section"] == "B"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["risk_category"] == "high_risk"
    assert answer["requirements_by_article"] == {}
    assert answer["summary"]["returned"] == 0
    assert answer["article_2_2"]["condition_decided"] is False
    assert "Articles 57, 58 and 59 shall apply only in so far as" in answer["article_2_2"]["condition"]
    for node in ("eu-ai-act:article-2:paragraph-2", "eu-ai-act:article-6:paragraph-1", "eu-ai-act:article-60a",
                 "eu-ai-act:article-102", "eu-ai-act:article-112", "eu-ai-act:article-57"):
        assert node in envelope["source_nodes"], node
    assert envelope["status"] == "potentially_applicable"
    dates = {p: [e["date"] for e in entries] for p, entries in answer["application_dates"].items()}
    assert dates["eu-ai-act:article-6:paragraph-1"] == ["2028-08-02"]
    assert dates["eu-ai-act:article-102"] == ["2026-07-27"]
    assert dates["eu-ai-act:article-111"] == ["2026-08-02"]
    assert answer["legal_text"] == AMENDED


def test_an_unknown_section_serves_chapter_iii_and_names_the_fact(dump, norms_payload, node_ids):
    """R14: while the section is unknown the Chapter III requirements are
    served as for Section A, the fact is named and Article 2(2) is said."""
    section_a = get_applicable_requirements(classify_ai_system(_annex_i(False), dump), norms_payload, dump)
    unknown = get_applicable_requirements(classify_ai_system(_annex_i(None), dump), norms_payload, dump)
    assert_envelope_invariants(unknown, node_ids)
    assert unknown["answer"]["requirements_by_article"] == section_a["answer"]["requirements_by_article"]
    assert unknown["status"] == section_a["status"]
    assert unknown["answer"]["annex_i_section"] == "unknown"
    assert classify_module.ANNEX_I_SECTION_UNKNOWN_FACT in unknown["missing_facts"]
    assert any("Article 2(2)" in n for n in unknown["legal_status_notes"])
    assert section_a["answer"]["annex_i_section"] == "A"
    assert classify_module.ANNEX_I_SECTION_UNKNOWN_FACT not in section_a["missing_facts"]


def test_each_served_group_carries_its_dates_by_route(dump, norms_payload):
    """R7: Chapter III by the classification's route; Article 50 from the
    general date with Article 111(4) as a note."""
    annex_iii = classify_ai_system(
        {"description": "CV screening tool.",
         "flags": {**{f: False for f in classify_module.PROHIBITION_RELEVANT_FLAGS}, "employment_decisions": True}},
        dump,
    )
    dates = get_applicable_requirements(annex_iii, norms_payload, dump)["answer"]["application_dates"]
    assert [e["date"] for e in dates["article-9"]] == ["2027-12-02"]
    annex_i = get_applicable_requirements(classify_ai_system(_annex_i(False), dump), norms_payload, dump)
    assert [e["date"] for e in annex_i["answer"]["application_dates"]["article-9"]] == ["2028-08-02"]
    limited = get_applicable_requirements({"risk_category": "limited_risk"}, norms_payload, dump)["answer"]
    [article_50] = limited["application_dates"]["article-50"]
    assert article_50["date"] == "2026-08-02"
    assert any("Article 111(4)" in n for n in article_50["notes"])
    assert set(limited["application_dates"]) == set(limited["requirements_by_article"])


def test_every_requirements_answer_names_the_text_it_follows(dump, norms_payload):
    for category in ("unacceptable_risk", "minimal_risk", "undetermined", "high_risk", "limited_risk"):
        answer = get_applicable_requirements({"risk_category": category}, norms_payload, dump)["answer"]
        assert answer["legal_text"] == AMENDED, category


def test_a_section_b_system_with_an_article_50_trigger_is_served_no_article_50_norm(dump, norms_payload):
    """R36: Article 2(2) applies none of Article 50 to a Section B system
    high-risk only under Article 6(1); the answer says so."""
    classification = classify_ai_system(_annex_i(True, interacts_with_natural_persons=True), dump)
    assert classification["answer"]["transparency_duties"] == []
    answer = get_applicable_requirements(classification, norms_payload, dump)["answer"]
    assert answer["requirements_by_article"] == {}
    assert "Article 50 transparency obligations do not apply" in answer["message"]


def test_a_section_b_system_matching_annex_iii_gets_one_consistent_answer(dump, norms_payload, node_ids):
    """R26 reversed (Codex plan review P1 3): with Section B legislation, an
    Annex III match and a public-law deployer, the classification, its FRIA
    block and the requirements all follow the Annex III route."""
    features = {**_annex_i(True, employment_decisions=True), "deployer": {"body_governed_by_public_law": True}}
    classification = classify_ai_system(features, dump)
    assert classification["answer"]["annex_iii_category"] == "eu-ai-act:annex-iii:point-4"
    assert classification["answer"]["annex_i_section"] == "B"
    assert classification["answer"]["fria"]["applicability"] == "applies"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert "article_2_2" not in answer
    assert answer["annex_i_section"] == "B"
    assert "article-9" in answer["requirements_by_article"] and "article-27" in answer["requirements_by_article"]
    # R43: Article 2(2) excludes point (c)(ii)'s Article 6(1) systems for a
    # Section B product, so Chapter III is dated by the Annex III route only.
    for group in answer["requirements_by_article"]:
        dates = answer["application_dates"][group]
        if group in ("article-9", "article-27"):
            assert [e["date"] for e in dates] == ["2027-12-02"], group
    assert [e["date"] for e in answer["application_dates"]["article-9"]] == ["2027-12-02"]
    assert answer["fria"]["applicability"] == "applies"
    assert envelope["status"] == "applicable_missing_evidence"


def test_a_system_on_both_routes_dates_its_requirements_by_both_and_agrees_with_its_fria(dump, norms_payload):
    """R37, the opus re-check's reproduced case: Section A, an Annex III point
    and a public deployer. The FRIA applies from 2027-12-02, so article-27
    and article-9 carry that date as well as 2 August 2028."""
    features = {**_annex_i(False, employment_decisions=True), "deployer": {"body_governed_by_public_law": True}}
    classification = classify_ai_system(features, dump)
    assert classification["answer"]["high_risk_routes"] == ["article_6_1", "article_6_2"]
    fria_date = classification["answer"]["fria"]["applies_from"]["date"]
    answer = get_applicable_requirements(classification, norms_payload, dump)["answer"]
    for group in ("article-27", "article-9"):
        dates = [e["date"] for e in answer["application_dates"][group]]
        assert dates == ["2027-12-02", "2028-08-02"], group
        assert fria_date in dates, group
    assert answer["fria"]["applicability"] == "applies"


def test_a_section_b_system_with_unknown_annex_iii_facts_is_not_settled(dump, norms_payload, node_ids):
    """R39: the requirements answer names the unknown Annex III facts, says
    the Chapter III requirements do not apply unless an Annex III point
    applies, and requires human review, as the classification does."""
    flags = {k: v for k, v in _annex_i(True)["flags"].items() if k not in classify_module.ANNEX_III_RELEVANT_FLAGS}
    classification = classify_ai_system({"description": "AI safety component of a machine.", "flags": flags}, dump)
    assert classification["status"] == "requires_human_review"
    envelope = get_applicable_requirements(classification, norms_payload, dump)
    assert_envelope_invariants(envelope, node_ids)
    answer = envelope["answer"]
    assert answer["requirements_by_article"] == {} and "article_2_2" in answer
    assert "do not apply unless an Annex III point applies" in answer["message"]
    assert envelope["status"] == "requires_human_review"
    assert any(m.startswith("flags.employment_decisions is unknown (Annex III high-risk relevant")
               for m in envelope["missing_facts"])


def test_a_section_b_derogation_candidate_on_the_annex_iii_route_says_what_can_change(dump, norms_payload):
    """The re-check's note on the provisional note: an Article 6(3) derogation
    candidate on the R26 path could take the answer back to Article 2(2)."""
    features = _annex_i(True, employment_decisions=True, improves_previous_human_activity=True)
    classification = classify_ai_system(features, dump)
    assert classification["answer"]["article_6_3_exception_candidate"] is True
    answer = get_applicable_requirements(classification, norms_payload, dump)["answer"]
    assert answer["provisional"] is True
    assert "the answer would become the Article 2(2) one" in answer["provisional_note"]
    annex_iii_only = {**_annex_i(None, employment_decisions=True, improves_previous_human_activity=True)}
    annex_iii_only["flags"]["annex_i_covered_product"] = False
    plain = get_applicable_requirements(classify_ai_system(annex_iii_only, dump), norms_payload, dump)
    assert plain["answer"]["provisional"] is True
    assert "Article 2(2)" not in plain["answer"]["provisional_note"]


def test_an_unknown_section_with_an_annex_iii_match_names_no_section_fact(dump, norms_payload):
    """R44: with an Annex III match Chapter III is served whatever the section,
    so neither the Article 2(2) note nor the section fact is given; on the
    Article 6(1) route alone both stay."""
    matched = classify_ai_system(_annex_i(None, employment_decisions=True), dump)
    assert matched["answer"]["high_risk_routes"] == ["article_6_1", "article_6_2"]
    envelope = get_applicable_requirements(matched, norms_payload, dump)
    assert not any("Article 2(2)" in n for n in envelope["legal_status_notes"])
    assert not any(m.startswith(f"flags.{classify_module.ANNEX_I_SECTION_FACT} is unknown") for m in envelope["missing_facts"])
    alone = get_applicable_requirements(classify_ai_system(_annex_i(None), dump), norms_payload, dump)
    assert any("Article 2(2)" in n for n in alone["legal_status_notes"])
    assert classify_module.ANNEX_I_SECTION_UNKNOWN_FACT in alone["missing_facts"]

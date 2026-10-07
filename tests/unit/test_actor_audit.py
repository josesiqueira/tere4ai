"""B144 (DEC-26, spec G D-G76 (7)): the extraction build record's two checks
over the norms of Articles 8 to 15. Mock norms only, plus Layer 1's Section
2 read from the tracked dump."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tere4ai.extract_norms.actor_audit import (
    POINT_A_NODE,
    SECTION_2_ARTICLES,
    SECTION_2_NODE,
    actor_audit,
    in_section_2,
    not_served_to_provider,
    point_a_outside_section_2,
    report_lines,
    section_2_checks,
)

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
S12 = "eu-ai-act:article-12:paragraph-1"
S14D = "eu-ai-act:article-14:paragraph-4:point-d"
S17 = "eu-ai-act:article-17:paragraph-1"


def _n(norm_id, source, explicit=None, inferred=None, src=None, verdict="accepted", deontic="obligation"):
    return {"norm_id": norm_id, "source_node_id": source, "actor_explicit": explicit, "actor_inferred": inferred,
            "actor_inference_source_node_id": src, "judge_verdict": verdict, "deontic_type": deontic}


DUMP = {"nodes": [
    {"id": "eu-ai-act:article-10:paragraph-5", "type": "Paragraph", "amendment": "deleted"},
    {"id": S12, "type": "Paragraph", "amendment": "unchanged"},
]}


def test_the_range_is_articles_8_to_15_read_from_the_article_segment():
    assert SECTION_2_ARTICLES == tuple(f"article-{n}" for n in range(8, 16))
    for inside in ("eu-ai-act:article-8", "eu-ai-act:article-8:paragraph-1", "eu-ai-act:article-15:paragraph-4", S14D):
        assert in_section_2(inside), inside
    for outside in ("eu-ai-act:article-80:paragraph-1", "eu-ai-act:article-150", "eu-ai-act:article-1:paragraph-1",
                    POINT_A_NODE, "eu-ai-act:article-7", "eu-ai-act:annex-iv:point-1", "article-12:paragraph-1",
                    "", None):
        assert not in_section_2(outside), outside


def test_the_served_count_lists_the_accepted_norms_the_provider_is_not_served():
    norms = [
        _n("a", S12, explicit="high-risk AI systems"),                                   # listed
        _n("b", S12, inferred="provider", src=POINT_A_NODE),                             # served
        _n("c", "eu-ai-act:article-8:paragraph-2", explicit="providers"),                # served by the word
        _n("d", S12, explicit="the Commission", verdict="rejected"),                     # not accepted
        _n("e", S12, explicit="the Commission", verdict="needs_human_review"),           # not accepted
        _n("f", "eu-ai-act:article-10:paragraph-5", explicit="the Commission"),          # a deleted unit
        _n("g", "eu-ai-act:article-80:paragraph-1", explicit="the Commission"),          # outside the range
        _n("h", "eu-ai-act:article-14:paragraph-5", explicit="the deployer"),            # listed
    ]
    assert not_served_to_provider(norms, DUMP) == ["a", "h"]


def test_the_four_groups_take_every_norm_once_in_the_stated_order():
    norms = [
        _n("rule", S12, inferred="provider", src=POINT_A_NODE),
        _n("both-set", S12, explicit="the deployer", inferred="provider", src=POINT_A_NODE),
        _n("both-empty", S12),
        _n("blank-written", S12, explicit="   "),
        _n("no-source", S12, inferred="provider"),
        _n("art16", S12, inferred="provider", src="eu-ai-act:article-16"),
        _n("party", S12, explicit="SMEs, including start-ups, and SMCs"),
        _n("enabled", S14D, inferred="unspecified_needs_review", src=S14D, deontic="permission"),
        _n("deployer-inferred", S14D, inferred="deployer", src="eu-ai-act:article-26"),
        _n("outside", S17, inferred="provider", src=POINT_A_NODE),
    ]
    audit = actor_audit(norms)
    assert audit["against_the_representation"] == {"count": 5, "norms": [
        {"norm_id": "both-set", "reason": "both actor slots set"},
        {"norm_id": "both-empty", "reason": "both actor slots empty"},
        {"norm_id": "blank-written", "reason": "both actor slots empty"},
        {"norm_id": "no-source", "reason": "provider inferred with no source"},
        {"norm_id": "art16", "reason": "provider inferred with another source: eu-ai-act:article-16"},
    ]}
    assert audit["rule_applied"] == {"count": 1, "norm_ids": ["rule"]}
    assert audit["written_party"] == {"count": 1, "norms": [
        {"norm_id": "party", "label": "unresolved", "phrase": "SMEs, including start-ups, and SMCs"}]}
    assert audit["outside_the_rule"] == {"count": 2, "norms": [
        {"norm_id": "enabled", "actor_inferred": "unspecified_needs_review", "deontic_type": "permission"},
        {"norm_id": "deployer-inferred", "actor_inferred": "deployer", "deontic_type": "obligation"}]}
    assert audit["sum"] == audit["norms_of_section_2"] == 9


def test_a_blank_inferred_actor_counts_as_empty():
    norms = [_n("blank-inferred", S12, inferred="  ", src=POINT_A_NODE), _n("blank-both", S12, explicit=" ", inferred="\t")]
    audit = actor_audit(norms)
    assert audit["against_the_representation"]["norms"] == [
        {"norm_id": "blank-inferred", "reason": "both actor slots empty"},
        {"norm_id": "blank-both", "reason": "both actor slots empty"}]


def test_a_written_party_is_labelled_with_the_canonical_actor_of_the_canonicalization():
    norms = [_n("1", S12, explicit="the Commission"), _n("2", S12, explicit="notified bodies"),
             _n("3", S12, explicit="providers of high-risk AI systems"), _n("4", S12, explicit="high-risk AI systems")]
    assert actor_audit(norms)["written_party"]["norms"] == [
        {"norm_id": "1", "label": "commission"}, {"norm_id": "2", "label": "notified_body"},
        {"norm_id": "3", "label": "provider"}, {"norm_id": "4", "label": "unresolved", "phrase": "high-risk AI systems"}]


def test_the_norms_outside_the_range_citing_point_a_are_listed_whatever_their_verdict():
    norms = [_n("17a", S17, inferred="provider", src=POINT_A_NODE, verdict="rejected"),
             _n("17c", S17, inferred="provider", src="eu-ai-act:article-16:paragraph-1:point-c"),
             _n("80a", "eu-ai-act:article-80:paragraph-1", inferred="provider", src=POINT_A_NODE),
             _n("12a", S12, inferred="provider", src=POINT_A_NODE)]
    assert point_a_outside_section_2(norms) == ["17a", "80a"]


def test_a_norm_without_a_source_node_id_is_outside_every_check():
    """The shape of the command's mock groups (test_extract_norms_cli.py _fakes)."""
    empty = {"count": 0, "norm_ids": []}
    assert section_2_checks([{"norm_id": "norm:eu-ai-act:article-9:n1"}], {"nodes": []}) == {
        "section_2_not_served_to_provider": empty,
        "section_2_actor_audit": {
            "rule_applied": empty, "written_party": {"count": 0, "norms": []},
            "outside_the_rule": {"count": 0, "norms": []}, "against_the_representation": {"count": 0, "norms": []},
            "sum": 0, "norms_of_section_2": 0,
        },
        "point_a_source_outside_section_2": empty,
    }


def test_the_report_lines_name_the_counts_and_the_ids_to_read():
    norms = [_n("a", S12, explicit="high-risk AI systems"), _n("b", S12),
             _n("c", S12, inferred="provider", src=POINT_A_NODE), _n("d", S17, inferred="provider", src=POINT_A_NODE)]
    assert report_lines(section_2_checks(norms, DUMP)) == [
        "Articles 8 to 15, accepted norms the provider is not served: 2",
        "  a",
        "  b",
        "Articles 8 to 15, actor audit of 3 norms: rule applied 1, written party 1, outside the rule 0, "
        "against the representation 1 (sum 3)",
        "  against the representation: b (both actor slots empty)",
        "Norms outside Articles 8 to 15 whose actor source is eu-ai-act:article-16:paragraph-1:point-a: 1",
        "  d",
    ]


@pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")
def test_layer1_section_2_holds_articles_8_to_15_and_nothing_else():
    """A4: the range the prompt names is the one Layer 1 parsed (R8)."""
    dump = json.loads(LAYER1.read_text(encoding="utf-8"))
    targets = sorted(e["to"] for e in dump["edges"]
                     if e.get("edge_type") == "HAS_ARTICLE" and e.get("from") == SECTION_2_NODE)
    assert targets == sorted(f"eu-ai-act:{article}" for article in SECTION_2_ARTICLES)
    nodes = {n["id"]: n for n in dump["nodes"]}
    assert nodes[POINT_A_NODE]["text"] == (
        "ensure that their high-risk AI systems are compliant with the requirements set out in Section 2;")

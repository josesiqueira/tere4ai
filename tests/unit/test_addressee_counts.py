"""B145 (spec G D-G80 (11); brief D11, A4's lists): the four counts of the
addressee in the extraction's build record, over scripted norms (mock data)
in either schema version, and the lines the command prints."""

from __future__ import annotations

from tere4ai import act_parties as ap
from tere4ai.extract_norms.actor_audit import (
    ADDRESSEE_COUNT_KEYS,
    actor_audit,
    addressee_counts,
    addressee_report_lines,
)

U17, U72_1, U72_2, U11, U12, U50_5 = (
    "eu-ai-act:article-17:paragraph-1", "eu-ai-act:article-72:paragraph-1", "eu-ai-act:article-72:paragraph-2",
    "eu-ai-act:article-11:paragraph-1", "eu-ai-act:article-12:paragraph-1", "eu-ai-act:article-50:paragraph-5")
POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"


def _n(norm_id, unit, explicit=None, inferred=None, source=None):
    return ap.in_v2_names({"norm_id": norm_id, "source_node_id": unit, "actor_explicit": explicit,
                           "actor_inferred": inferred, "actor_inference_source_node_id": source,
                           "deontic_type": "obligation", "judge_verdict": "accepted"})


NORMS = [
    _n("17-1", U17, inferred="provider", source=U17),                     # the rule, its own unit
    _n("72-2", U72_2, inferred="provider", source=U72_1),                 # the rule, a row's source
    _n("72-2-thing", U72_2, explicit="the post-market monitoring system"),  # the thing written
    _n("11-1", U11, explicit="SMEs, including start-ups, and SMCs"),       # placed on provider
    _n("12-1", U12, inferred="provider", source=POINT_A),                 # B144's rule, not the set-up rule
    _n("50-5-d", U50_5, inferred="deployer", source="eu-ai-act:article-50:paragraph-3"),
    _n("50-5-x", U50_5, inferred="deployer", source="eu-ai-act:article-50:paragraph-1"),  # wrong party for that row
    _n("unset", U72_2, inferred="unspecified_needs_review", source=U72_2),  # a sentinel is never the rule
    _n("they", U17, explicit="they"),
]


def test_the_four_counts_over_the_run():
    counts = addressee_counts(NORMS)
    assert tuple(counts) == ADDRESSEE_COUNT_KEYS
    assert counts["addressee_values"] == {"provider": 4, "deployer": 2, "unspecified_needs_review": 3}
    assert sum(counts["addressee_values"].values()) == len(NORMS)
    assert counts["unplaced_written_addressees"] == [
        {"phrase": "the post-market monitoring system", "norm_ids": ["72-2-thing"]},
        {"phrase": "they", "norm_ids": ["they"]}]
    assert counts["set_up_rule_applied"] == {"count": 3, "norm_ids": ["17-1", "72-2", "50-5-d"]}
    assert counts["set_up_thing_as_written_addressee"] == {"count": 1, "norm_ids": ["72-2-thing"]}


def test_the_counts_are_the_same_for_version_1_norms():
    assert addressee_counts([ap.in_v1_names(n) for n in NORMS]) == addressee_counts(NORMS)


def test_zero_counts_are_printed():
    counts = addressee_counts([])
    assert counts == {"addressee_values": {}, "unplaced_written_addressees": [],
                      "set_up_rule_applied": {"count": 0, "norm_ids": []},
                      "set_up_thing_as_written_addressee": {"count": 0, "norm_ids": []}}
    assert addressee_report_lines(counts) == [
        "Addressees by value of the Act's parties: none",
        "Written addressees the Act's parties could not place: 0",
        "Norms whose addressee rests on the set-up rule: 0",
        "Norms on a set-up unit whose written addressee is the row's thing: 0",
    ]


def test_the_printed_lines_name_the_ids():
    lines = addressee_report_lines(addressee_counts(NORMS))
    assert lines[0] == "Addressees by value of the Act's parties: provider 4, deployer 2, unspecified_needs_review 3"
    assert '  "the post-market monitoring system": 72-2-thing' in lines
    assert "Norms whose addressee rests on the set-up rule: 3" in lines and "  50-5-d" in lines


def test_the_actor_audit_reads_version_2_norms_and_labels_a_written_party_by_its_value():
    section_2 = [_n("11-sme", U11, explicit="SMEs, including start-ups, and SMCs"),
                 _n("12-rule", U12, inferred="provider", source=POINT_A),
                 _n("12-thing", U12, explicit="high-risk AI systems")]
    audit = actor_audit(section_2)
    assert audit["rule_applied"] == {"count": 1, "norm_ids": ["12-rule"]}
    assert audit["written_party"]["norms"] == [
        {"norm_id": "11-sme", "label": "provider"},
        {"norm_id": "12-thing", "label": "unresolved", "phrase": "high-risk AI systems"}]

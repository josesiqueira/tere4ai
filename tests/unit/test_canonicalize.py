"""Canonicalize step tests (#33, DEC-04): actor table + clause materialisation."""

from __future__ import annotations

import pytest

from tere4ai.canonicalize.canonicalizer import canonicalize_actor, canonicalize_norms


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("provider", "provider"),
        ("the provider", "provider"),
        ("providers", "provider"),
        ("providers of high-risk ai systems", "provider"),
        ("Providers of high-risk AI systems", "provider"),
        ("the deployer", "deployer"),
        ("deployers", "deployer"),
        ("importers", "importer"),
        ("distributors", "distributor"),
        ("the commission", "commission"),
        ("European Commission", "commission"),
        ("authorised representatives", "authorised_representative"),
        ("notified bodies", "notified_body"),
        ("market surveillance authorities", "market_surveillance_authority"),
        ("member states", "member_state"),
    ],
)
def test_actor_table_resolves_observed_wordings(raw, expected):
    canonical, method = canonicalize_actor(raw)
    assert canonical == expected
    assert method == "canonicalize_rule_v1"


@pytest.mark.parametrize(
    "raw", ["that system", "they", "unspecified_needs_review", "", None, "office"]
)
def test_unmappable_actors_stay_unresolved_never_guessed(raw):
    canonical, _reason = canonicalize_actor(raw)
    assert canonical is None


def make_payload():
    return {
        "build": {"build_id": "build-test"},
        "norms": [
            {
                "norm_id": "norm:a",
                "actor_explicit": "the provider",
                "conditions": ["in relation to high-risk AI systems"],
                "exceptions": [],
            },
            {
                "norm_id": "norm:b",
                "actor_explicit": None,
                "actor_inferred": "providers",
                "conditions": ["In relation to HIGH-RISK ai systems"],
                "exceptions": ["unless the system is in testing"],
            },
            {
                "norm_id": "norm:c",
                "actor_explicit": "that system",
                "conditions": [],
                "exceptions": [],
            },
        ],
    }


def test_shared_condition_wording_resolves_to_one_node():
    result = canonicalize_norms(make_payload())
    norms = {n["norm_id"]: n for n in result["norms"]}
    # Same normalised wording (case/whitespace-insensitive) = same node id.
    assert norms["norm:a"]["condition_ids"] == norms["norm:b"]["condition_ids"]
    assert len(result["conditions"]) == 1
    assert result["conditions"][0]["type"] == "Condition"
    assert result["conditions"][0]["id"].startswith("cond:")
    assert len(result["exceptions"]) == 1
    assert norms["norm:b"]["exception_ids"] == [result["exceptions"][0]["id"]]
    assert norms["norm:c"]["condition_ids"] == []


def test_actor_fields_populated_and_unresolved_reported():
    result = canonicalize_norms(make_payload())
    norms = {n["norm_id"]: n for n in result["norms"]}
    assert norms["norm:a"]["actor_canonical"] == "provider"
    assert norms["norm:b"]["actor_canonical"] == "provider"
    assert "actor_canonical" not in norms["norm:c"]
    stats = result["canonicalization"]
    assert stats["actors_resolved"] == 2
    assert stats["actors_unresolved"] == {"that system": 1}


def test_canonicalize_is_idempotent_and_deterministic():
    once = canonicalize_norms(make_payload())
    twice = canonicalize_norms(once)
    assert once == twice


def test_clause_nodes_flow_into_the_graph_form():
    from tere4ai.graph_store.layer23 import norms_to_graph

    payload = canonicalize_norms(make_payload())
    for norm in payload["norms"]:
        norm.setdefault("source_node_id", "eu-ai-act:article-9:paragraph-1")
        norm.setdefault("judge_verdict", "accepted")
    graph = norms_to_graph(payload, build_id="build-test")
    clause_nodes = [n for n in graph["nodes"] if n["type"] in ("Condition", "Exception")]
    assert len(clause_nodes) == 2
    clause_edges = [
        e for e in graph["edges"] if e["edge_type"] in ("HAS_CONDITION", "HAS_EXCEPTION")
    ]
    assert len(clause_edges) == 3  # norm:a cond + norm:b cond + norm:b exc
    for edge in clause_edges:
        assert edge["provenance_class"] == "RESOLVED_DETERMINISTIC"
        assert edge["method"] == "canonicalize_rule_v1"

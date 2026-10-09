"""B145 (spec G D-G80 (2), (4), (10); DEC-27): the Act's parties, held by
hand in schema/act_parties.json and checked against the tracked
layer1.json; the normaliser that places a written addressee; the one reader
of a norm's addressee in either norms schema version; and which request a
norm is served to. Brief acceptance A1 and A3."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tere4ai import act_parties as ap

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
needs_layer1 = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")

# search.md row 123: the 17 Definition nodes of the parties Article 3 defines.
PARTY_DEFINITIONS = tuple(f"eu-ai-act:definition:{slug}" for slug in (
    "provider", "deployer", "authorised-representative", "importer", "distributor", "operator",
    "notified-body", "notifying-authority", "market-surveillance-authority", "national-competent-authority",
    "ai-office", "conformity-assessment-body", "law-enforcement-authority", "downstream-provider", "subject",
    "micro-small-and-medium-sized-enterprise", "small-mid-cap-enterprise"))
# The three that are phrases of provider, each with the Article 3 point that defines it (D-G80 (2)).
PHRASE_DEFINITIONS = {
    "eu-ai-act:definition:downstream-provider": "eu-ai-act:article-3:paragraph-1:point-68",
    "eu-ai-act:definition:micro-small-and-medium-sized-enterprise": "eu-ai-act:article-3:paragraph-1:point-14a",
    "eu-ai-act:definition:small-mid-cap-enterprise": "eu-ai-act:article-3:paragraph-1:point-14b",
}


def _nodes():
    return {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"]}


def _holds(text: str, term: str) -> bool:
    """term's folded words occur, contiguous, in text's folded words (singular or plural)."""
    words, wanted = ap._words(text), ap._words(term)
    return any(words[i:i + len(wanted)] == wanted for i in range(len(words) - len(wanted) + 1))


def test_the_list_holds_37_values_by_kind_each_once():
    values = ap.values()
    assert len(values) == 37 and len(set(values)) == 37
    assert Counter(p.kind for p in ap.parties()) == {
        "role": 6, "authority": 9, "body": 2, "institution": 9, "person": 9, "sentinel": 2}
    assert ap.ai_act_roles() == ("provider", "product_manufacturer", "deployer",
                                 "authorised_representative", "importer", "distributor")
    assert ap.SENTINELS == ("operator_general", "unspecified_needs_review")
    assert ap.addressee_condition() == ap.ai_act_roles() + ap.SENTINELS
    assert set(ap.requestable()) == set(values) - set(ap.SENTINELS)


def test_also_served_to_is_exactly_article_3_47_and_3_48_one_way():
    served = {p.value: p.also_served_to for p in ap.parties() if p.also_served_to}
    assert served == {"ai_office": ("commission",),
                      "national_competent_authority": ("notifying_authority", "market_surveillance_authority")}


@needs_layer1
def test_every_ground_exists_is_not_deleted_and_holds_the_act_term():
    from tere4ai.parse_legal_structure.amendments import is_deleted

    nodes = _nodes()
    for p in ap.parties():
        if p.ground is None:
            assert p.value == "unspecified_needs_review"
            continue
        node = nodes.get(p.ground)
        assert node is not None and not is_deleted(node), p.value
        assert _holds(node["text"], p.act_term), p.value


@needs_layer1
def test_every_phrase_ground_exists_and_holds_the_phrase():
    nodes = _nodes()
    for p in ap.parties():
        for text, ground in p.phrases:
            assert ground in nodes, (p.value, text)
            assert _holds(nodes[ground]["text"], text), (p.value, text)


@needs_layer1
def test_every_definition_node_defines_its_term():
    nodes = _nodes()
    for p in ap.parties():
        if p.definition_node_id is None:
            continue
        node = nodes[p.definition_node_id]
        assert node["type"] == "Definition", p.value
        assert node["text"].startswith(f"‘{p.act_term}’"), p.value


@needs_layer1
def test_each_of_the_17_party_definitions_is_a_value_or_a_phrase_ground():
    nodes = _nodes()
    by_definition = {p.definition_node_id for p in ap.parties()}
    phrase_grounds = {ground for p in ap.parties() for _t, ground in p.phrases}
    for definition in PARTY_DEFINITIONS:
        assert definition in nodes, definition
        assert definition in by_definition or PHRASE_DEFINITIONS.get(definition) in phrase_grounds, definition


@needs_layer1
def test_the_six_roles_are_article_3_8s_terms_in_its_order():
    text = _nodes()["eu-ai-act:article-3:paragraph-1:point-8"]["text"]
    assert text == "‘operator’ means a provider, product manufacturer, deployer, authorised representative, importer or distributor;"
    terms = text.split(" means a ")[1].rstrip(";").replace(" or ", ", ").split(", ")
    assert [p.act_term for p in ap.parties() if p.kind == "role"] == terms


@needs_layer1
def test_the_bodies_are_those_article_3_defines_as_a_body():
    nodes = _nodes()
    for p in ap.parties():
        if p.kind == "body":
            definition = nodes[p.definition_node_id]["text"]
            assert definition.split(" means ")[1].startswith(("a body", "a conformity assessment body")), p.value


@needs_layer1
def test_the_one_way_constructions_are_grounded_in_article_3_47_and_3_48():
    nodes = _nodes()
    assert "references in this Regulation to the AI Office shall be construed as references to the Commission" in (
        nodes["eu-ai-act:article-3:paragraph-1:point-47"]["text"])
    assert "‘national competent authority’ means a notifying authority or a market surveillance authority" in (
        nodes["eu-ai-act:article-3:paragraph-1:point-48"]["text"])


# A3: the normaliser, run in the order of D-G80 (4). Expected values come from
# the brief's table of cases, never from the code under test.
PLACED = {
    "providers of high-risk AI systems": "provider",
    "the provider": "provider",
    "that initial provider": "provider",
    "downstream providers": "provider",
    "providers or prospective providers": "provider",
    "deployers who are employers": "deployer",
    "deployers of high-risk AI systems that are public authorities, or Union institutions, bodies, offices or agencies": "deployer",
    "notified bodies": "notified_body",
    "market surveillance authorities": "market_surveillance_authority",
    "the national data protection authorities of Member States": "national_data_protection_authority",
    "the Court of Justice of the European Union": "court_of_justice",
    "the EU AI Office": "ai_office",
    "the Board": "board",
    "the staff of notified bodies": "notified_body_staff",
    "the experts on the scientific panel": "scientific_panel_expert",
    "the third party that supplies an AI system, AI model, tools, services, components, or processes ...": "third_party_supplier",
    "SMEs, including start-ups, and SMCs": "provider",
    "an SME, including a start-up": "provider",
    "the relevant operator": "operator_general",
    "conformity assessment bodies": "conformity_assessment_body",
    "subjects of testing": "subject_of_testing",
    # R91: a closed list of words may stand before the head
    "national market surveillance authorities": "market_surveillance_authority",
    # R98: a descriptor with no coordinated party still places
    "providers of general-purpose AI models with systemic risk": "provider",
}
UNPLACED = (
    "that system", "the post-market monitoring system", "it", "they", "the provider or the deployer",
    "any distributor, importer, deployer or other third-party",
    "National market surveillance authorities and the national data protection authorities of Member States",
    "the data subject", "", "   ",
    # R91 (review Important 2): a thing whose words name the party that acts
    # on it is never placed on that party
    "the report submitted by the provider",
    "the technical documentation drawn up by the provider",
    "any information obtained by a competent authority pursuant to this article",
    # R98: a party coordinated after a descriptor is still several parties
    "providers of AI systems and deployers of AI systems",
    "deployers of high-risk AI systems and importers",
    # R58: only the guard on the one word "subject" decides these
    "subject", "the subject",
)


@pytest.mark.parametrize("phrase,value", sorted(PLACED.items()))
def test_a_written_party_is_placed_on_one_value(phrase, value):
    assert ap.place(phrase) == value


@pytest.mark.parametrize("phrase", UNPLACED)
def test_a_thing_a_pronoun_or_several_parties_is_never_placed(phrase):
    assert ap.place(phrase) is None
    assert ap.compute(phrase, None) == ("unspecified_needs_review", "unplaced")


def test_never_a_substring_anywhere_in_the_phrase():
    # "provider" inside a longer word, and a party named only after " of "
    assert ap.place("the providership arrangements") is None
    assert ap.place("the representatives of the Member States' authorities") is None


# The one reader (D-G80 (21), R48): the same norm in either version.
V1 = {"norm_id": "n", "actor_explicit": "SMEs, including start-ups, and SMCs", "actor_inferred": None,
      "actor_inference_source_node_id": None}
V2 = {"norm_id": "n", "addressee_explicit": "SMEs, including start-ups, and SMCs", "addressee_inferred": None,
      "addressee_inference_source_node_id": None, "addressee": "provider", "addressee_method": "act_parties_v1",
      "addressee_placement": "placed"}


def test_the_one_reader_gives_the_same_addressee_in_either_version():
    assert ap.addressee_of(V1) == ap.addressee_of(V2) == ap.Addressee(
        "SMEs, including start-ups, and SMCs", None, None, "provider", "placed")
    inferred = {"actor_explicit": None, "actor_inferred": "provider",
                "actor_inference_source_node_id": "eu-ai-act:article-72:paragraph-1"}
    assert ap.addressee_of(inferred) == ap.Addressee(None, "provider", "eu-ai-act:article-72:paragraph-1",
                                                     "provider", "inferred")


def test_a_version_2_norm_is_read_as_stored_and_an_old_stamp_is_computed_again():
    stored = {**V2, "addressee": "deployer"}  # as stored, whatever the words say
    assert ap.addressee_of(stored).value == "deployer"
    old = {**V2, "addressee": "deployer", "addressee_method": "canonicalize_rule_v1"}
    assert ap.addressee_of(old).value == "provider"


def test_in_v2_names_drops_the_version_1_keys_and_keeps_every_other():
    out = ap.in_v2_names({**V1, "action": "provide", "actor_canonical": "x",
                          "actor_canonicalization_method": "canonicalize_rule_v1"})
    assert not [k for k in out if k.startswith("actor_")]
    assert out["action"] == "provide" and out["addressee"] == "provider"
    assert out["addressee_method"] == "act_parties_v1" and out["addressee_placement"] == "placed"


def test_which_request_a_norm_is_served_to():
    assert ap.serves("provider", "provider")
    assert not ap.serves("provider", "deployer")
    for role in ap.ai_act_roles():
        assert ap.serves("operator_general", role)  # R7
    assert not ap.serves("operator_general", "commission")
    assert ap.serves("ai_office", "commission") and not ap.serves("commission", "ai_office")  # R26
    assert ap.serves("national_competent_authority", "notifying_authority")
    assert ap.serves("national_competent_authority", "market_surveillance_authority")
    assert not ap.serves("notifying_authority", "national_competent_authority")
    assert not any(ap.serves("unspecified_needs_review", v) for v in ap.requestable())  # R38

"""Tests for the feature elicitor (LLM extracts facts, rules decide)."""

import json
import re
from pathlib import Path

import pytest

from tere4ai.elicit_features import elicit
from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION
from tere4ai.extract_norms.model_clients import FakeClient

DESC = "A chatbot that answers shopper questions and tracks their mood at work."


def test_valid_elicitation_passes_schema_and_keeps_description():
    payload = {
        "domain": "consumer",
        "autonomy": "advisory",
        "flags": {"interacts_with_natural_persons": True, "social_scoring": False},
        "description": "model tried to overwrite this",
    }
    fake = FakeClient({DESC[:30]: json.dumps(payload)})
    # B10: the default is v6, whose reply nests the facts under "features"
    # beside "quotes"; this test keeps v5's reply shape, so it names v5.
    # B10: elicit_features (the wrapper) is gone; elicit() with v5 renders no
    # provision, so the dump it is given is not read.
    features = elicit(DESC, fake, dump={}, snapshots_dir=SNAPSHOTS_DIR, prompt_version="v5").features
    assert features is not None
    assert features["description"] == DESC, "original description always wins"
    assert features["flags"]["interacts_with_natural_persons"] is True


def test_unknown_fields_and_non_boolean_flags_stripped():
    payload = {
        "domain": "consumer",
        "risk_category": "high_risk",
        "flags": {"interacts_with_natural_persons": "yes", "social_scoring": False,
                  "invented_flag": True},
    }
    fake = FakeClient({DESC[:30]: json.dumps(payload)})
    # B10: v5's reply shape, so v5 is named (the default is v6).
    # B10: elicit() replaces the deleted elicit_features wrapper.
    features = elicit(DESC, fake, dump={}, snapshots_dir=SNAPSHOTS_DIR, prompt_version="v5").features
    assert features is not None
    assert "risk_category" not in features, "elicitor never outputs a classification"
    assert "invented_flag" not in features["flags"]
    assert "interacts_with_natural_persons" not in features["flags"], "non-boolean dropped"
    assert features["flags"]["social_scoring"] is False


def test_invalid_json_retries_then_none(dump):
    calls = []

    class Bad:
        model = "fake"

        def complete(self, system, user):
            calls.append(1)
            return "not json at all"

    # B10: elicit() over the repository's build replaces the deleted wrapper.
    result = elicit(DESC, Bad(), dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    features, notes = result.features, result.notes
    assert features is None
    assert len(calls) == 2, "exactly one retry"
    assert any("failed" in n for n in notes)


def test_default_prompt_carries_the_dump_verbatim_article_3_definitions():
    """Missing-context audit F3: the elicitor sets flags whose terms have
    binding Article 3 definitions; the default prompt embeds those definitions
    from the graph dump. The comparison ignores only the quotation marks
    around the defined term, which the Formex text keeps and the prompt leaves
    out. This guard fails if the prompt's definition text ever drifts from
    the dump's."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    dump_path = root / "data" / "graph_dumps" / "layer1.json"
    if not dump_path.is_file():
        pytest.skip("layer1.json dump not built")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    by_id = {n["id"]: n for n in dump["nodes"]}
    # v5 (B36.2) quotes the definitions as enacted, without the quotation
    # marks around the defined term that the Formex text keeps (B132); the
    # one the Omnibus replaced, Article 3(14), is compared with its earlier
    # version, the 2024 wording.
    prompt = (root / "prompts" / "elicit_features" / "v5.md").read_text(
        encoding="utf-8"
    )
    for node_id in (
        "eu-ai-act:definition:biometric-identification",
        "eu-ai-act:definition:real-time-remote-biometric-identification-system",
        "eu-ai-act:definition:biometric-categorisation-system",
        "eu-ai-act:definition:emotion-recognition-system",
        "eu-ai-act:definition:profiling",
    ):
        assert _without_term_quotes(by_id[node_id]["text"]).strip() in prompt, (
            f"v5 prompt lost or drifted the verbatim definition {node_id}"
        )
    enacted = by_id["version:2024-07-12:eu-ai-act:article-3:paragraph-1:point-14"]["text"]
    assert _without_term_quotes(enacted).strip() in prompt, "v5 prompt lost the 2024 safety component definition"


def _without_term_quotes(text: str) -> str:
    """The text without the single quotation marks around a quoted term
    ('biometric identification' means ...), which the Formex text keeps (B132)
    and the hand-quoted prompts and schema descriptions leave out."""
    return re.sub(
        "\N{LEFT SINGLE QUOTATION MARK}([^\N{RIGHT SINGLE QUOTATION MARK}]*)\N{RIGHT SINGLE QUOTATION MARK}",
        r"\1", text)


def test_v4_prompt_carries_the_article_5_exculpating_facts():
    """Audit B25: v4 teaches the elicitor the Article 5 exculpating facts and
    the FRIA facts, so a genuinely harmful system resolves to prohibited
    instead of abstaining. Every new schema flag must be named in the prompt."""
    from pathlib import Path

    prompt = (
        Path(__file__).resolve().parents[2] / "prompts" / "elicit_features" / "v4.md"
    ).read_text(encoding="utf-8")
    for flag in (
        "causes_significant_harm",
        "social_score_detrimental_treatment",
        "supports_human_assessment_on_verifiable_facts",
        "emotion_recognition_medical_or_safety",
        "biometric_categorisation_lawful_or_law_enforcement",
        "rtrb_strictly_necessary_authorised",
        "creditworthiness_evaluation",
        "life_health_insurance_risk_pricing",
        "body_governed_by_public_law",
        "private_entity_providing_public_services",
    ):
        assert flag in prompt, f"v4 prompt omits the fact {flag}"


def test_default_prompt_version_is_v7():
    """DEC-18: the elicitor and the facade share one default."""
    import inspect

    from tere4ai.elicit_features.elicitor import elicit, render_prompt
    from tere4ai.mcp_server.elicit import elicit_envelope

    # B10: the default moved from v5 to v6, which quotes every flag's
    # provisions from the graph and asks for a quote per fact; B132: to v7,
    # which follows the Act as amended.
    assert DEFAULT_PROMPT_VERSION == "v7"
    # B10: the elicit_features wrapper is deleted (Task 5); render_prompt,
    # which the benchmark script calls, shares the default.
    for function in (elicit, render_prompt, elicit_envelope):
        signature = inspect.signature(function)
        assert signature.parameters["prompt_version"].default == "v7"


# DEC-18, B36.2: the three biometric facts and the point (d) and (g)
# exceptions are defined by the Act's words. Each passage is checked against
# the dump first, so a match in the schema or the prompt proves the copy is
# verbatim (build build-3b753e5e9297).

ROOT = Path(__file__).resolve().parents[2]
ACT_PASSAGES = {
    "eu-ai-act:definition:biometric-categorisation-system": (
        "biometric categorisation system means an AI system for the purpose of "
        "assigning natural persons to specific categories on the basis of their "
        "biometric data, unless it is ancillary to another commercial service and "
        "strictly necessary for objective technical reasons"
    ),
    "eu-ai-act:annex-iii:point-1:b": (
        "AI systems intended to be used for biometric categorisation, according to "
        "sensitive or protected attributes or characteristics based on the inference "
        "of those attributes or characteristics"
    ),
    "eu-ai-act:article-5:paragraph-1:point-g": (
        "biometric categorisation systems that categorise individually natural persons "
        "based on their biometric data to deduce or infer their race, political "
        "opinions, trade union membership, religious or philosophical beliefs, sex "
        "life or sexual orientation"
    ),
    "eu-ai-act:article-5:paragraph-1:point-d": (
        "this prohibition shall not apply to AI systems used to support the human "
        "assessment of the involvement of a person in a criminal activity, which is "
        "already based on objective and verifiable facts directly linked to a "
        "criminal activity"
    ),
}
# Point (g)'s exception, checked against the same node as its trait list.
POINT_G_EXCEPTION = (
    "this prohibition does not cover any labelling or filtering of lawfully acquired "
    "biometric datasets, such as images, based on biometric data or categorizing of "
    "biometric data in the area of law enforcement"
)
SCHEMA_PASSAGES = {
    "biometric_categorisation_system": ACT_PASSAGES["eu-ai-act:definition:biometric-categorisation-system"],
    "biometric_categorisation_sensitive_or_protected_attributes": ACT_PASSAGES["eu-ai-act:annex-iii:point-1:b"],
    "biometric_categorisation": ACT_PASSAGES["eu-ai-act:article-5:paragraph-1:point-g"],
    "supports_human_assessment_on_verifiable_facts": ACT_PASSAGES["eu-ai-act:article-5:paragraph-1:point-d"],
    "biometric_categorisation_lawful_or_law_enforcement": POINT_G_EXCEPTION,
}


def _act_nodes() -> dict:
    dump_path = ROOT / "data" / "graph_dumps" / "layer1.json"
    if not dump_path.is_file():
        pytest.skip("layer1.json dump not built")
    nodes = {n["id"]: n for n in json.loads(dump_path.read_text(encoding="utf-8"))["nodes"]}
    for node_id, passage in ACT_PASSAGES.items():
        assert passage in _without_term_quotes(nodes[node_id]["text"]), node_id
    assert POINT_G_EXCEPTION in nodes["eu-ai-act:article-5:paragraph-1:point-g"]["text"]
    return nodes


def test_schema_defines_the_biometric_facts_and_the_exceptions_by_the_acts_words():
    """Jose, 2026-10-01: three biometric facts defined by the Act's words,
    and the point (d) and (g) exceptions corrected to the Act's words."""
    _act_nodes()
    schema = json.loads(
        (ROOT / "schema" / "json_schemas" / "system_features.schema.json").read_text(encoding="utf-8")
    )
    flags = schema["properties"]["flags"]["properties"]
    for flag, passage in SCHEMA_PASSAGES.items():
        assert passage in flags[flag]["description"], flag


def _collapse(text: str) -> str:
    return " ".join(text.split())


def test_v5_prompt_carries_the_acts_words_for_biometrics_and_exceptions():
    """DEC-18 (B36.2): v5 teaches the elicitor the three biometric facts and
    the corrected point (d) and (g) exceptions, verbatim."""
    _act_nodes()
    prompt = _collapse((ROOT / "prompts" / "elicit_features" / "v5.md").read_text(encoding="utf-8"))
    for passage in (*ACT_PASSAGES.values(), POINT_G_EXCEPTION):
        assert passage in prompt, passage[:60]


# B132: the Annex I section fact joined the schema after v6; v5 and v6 are
# kept unchanged for the records that name them, and v7 asks it.
FLAGS_AFTER_V6 = ("annex_i_section_b_legislation",)


def test_v5_prompt_names_every_schema_flag():
    """Every fact the schema defines is in the v5 list, the two Omnibus
    prohibition facts included (Jose, 2026-10-01: "Add them to v5")."""
    from tere4ai.elicit_features.elicitor import schema_flag_names

    prompt = (ROOT / "prompts" / "elicit_features" / "v5.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"[a-z0-9_]+", prompt))
    missing = [name for name in schema_flag_names() if name not in listed and name not in FLAGS_AFTER_V6]
    assert missing == []


# v5 and v6 quoted the Omnibus points from the amending act, in the words of
# the verified inventory docs/omnibus_amendments.md, since the base-text dump
# then had no node for them (REF-02, DEC-12); they are graph nodes now (B132).
OMNIBUS_PASSAGES = (
    "(ba) the placing on the market, the putting into service or the use of an AI "
    "system that generates or manipulates realistic images, videos, audio or similar "
    "material of an identifiable natural person\u2019s intimate parts, or of an "
    "identifiable natural person engaged in sexually explicit activities, without that "
    "person\u2019s freely-given, specific, informed, unambiguous and explicit consent "
    "for that generation or manipulation;",
    "(bb) the placing on the market, the putting into service or the use of an AI "
    "system that generates or manipulates material or performance within the meaning "
    "of Article 2, points (c) and (e), of Directive 2011/93/EU, except where a "
    "\u201cwithout right\u201d defence applies under national law;",
    "(b) the use of an AI system that generates or manipulates the material or "
    "performance referred to in paragraph 1, first subparagraph, points (ba) and (bb) "
    "is only prohibited where the deployer uses the system for the purpose of "
    "generating or manipulating such material or performance.",
    "1b. For the purposes of paragraph 1, first subparagraph, point (ba), an AI system "
    "that manipulates material in a way that does not increase the exposure of any "
    "depicted intimate parts or alter the nature of any depicted sexually explicit "
    "activities shall not constitute manipulation.",
    "1a. For the purposes of paragraph 1, first subparagraph, points (ba) and (bb):",
    "(a) the placing on the market or putting into service of an AI system that generates or manipulates the material or performance referred to in paragraph 1, first subparagraph, point (ba) or (bb) is only prohibited where:",
    "(i) that generation or manipulation is the intended purpose of the AI system; or",
    "(ii) the system\u2019s design, training, architecture, capabilities or user-facing functionalities make that generation or manipulation a reasonably foreseeable and reproducible outcome, without requiring significant technical modification, and the system does not have reasonable and adequate technical safety measures and other safeguards to reliably prevent that generation or manipulation, taking into account reasonably foreseeable misuse, and to correct observed or reported misuse;",
)


def test_v5_prompt_carries_the_omnibus_points_verbatim():
    """Jose, 2026-10-01: "Add them to v5": points (ba) and (bb) and the
    Article 5(1a), 5(1b) scoping, in the amending act's words."""
    inventory = (ROOT / "docs" / "omnibus_amendments.md").read_text(encoding="utf-8")
    prompt = _collapse((ROOT / "prompts" / "elicit_features" / "v5.md").read_text(encoding="utf-8"))
    for passage in OMNIBUS_PASSAGES:
        assert passage in inventory, passage[:60]
        assert passage in prompt, passage[:60]


def test_v6_prompt_carries_the_omnibus_points_verbatim_and_says_why():
    """B10: the base graph is pinned before the amendment and has no node
    for points (ba) and (bb), so v6 keeps the amending act's words from the
    verified inventory, under a heading that says so."""
    raw = (ROOT / "prompts" / "elicit_features" / "v6.md").read_text(encoding="utf-8")
    prompt = _collapse(raw)
    for passage in OMNIBUS_PASSAGES:
        assert passage in prompt, passage[:60]
    heading = next(
        line for line in raw.splitlines() if line.startswith("## ") and "Omnibus" in line
    )
    assert "verbatim from the amending act" in heading
    assert "docs/omnibus_amendments.md" in prompt
    assert "no node for these points" in prompt


def test_v6_prompt_names_every_schema_flag():
    """Every fact the schema defines is in the v6 field list."""
    from tere4ai.elicit_features.elicitor import schema_flag_names

    prompt = (ROOT / "prompts" / "elicit_features" / "v6.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"[a-z0-9_]+", prompt))
    missing = [name for name in schema_flag_names() if name not in listed and name not in FLAGS_AFTER_V6]
    assert missing == []


def test_v6_prompt_keeps_the_v5_binding_rules():
    """v6 keeps v5's role and binding rules 1 to 5 word for word."""
    v5 = _collapse((ROOT / "prompts" / "elicit_features" / "v5.md").read_text(encoding="utf-8"))
    v6 = _collapse((ROOT / "prompts" / "elicit_features" / "v6.md").read_text(encoding="utf-8"))
    role = v5[: v5.index("Output exactly one JSON object")]
    assert v6.startswith(role)
    rules = v5[v5.index("Rules, all binding:") : v5.index("5. Output the JSON object only")]
    assert rules in v6


def test_v4_prompt_is_kept_unchanged_for_the_records_that_name_it():
    """A recorded elicitation names its prompt version, so v4 stays as it was."""
    prompt = (ROOT / "prompts" / "elicit_features" / "v4.md").read_text(encoding="utf-8")
    assert "biometric_categorisation_system" not in prompt


# B10 Task 3: elicit() keeps a fact only with a quote from the description
# (at least three words, found by character identity after collapsing
# whitespace runs) and names every fact it drops. The prompt is rendered
# from the graph first; a provision that does not resolve stops the call
# before the generator is asked anything.

import copy  # noqa: E402
import hashlib  # noqa: E402

from tere4ai.elicit_features import Elicitation  # noqa: E402
from tere4ai.elicit_features.provisions import PLACEHOLDER_RE, ProvisionUnresolved  # noqa: E402

DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
V7_PATH = ROOT / "prompts" / "elicit_features" / "v7.md"
BANK = (
    "A chatbot on our bank's website answers customers' questions about opening "
    "hours and card fees. It does not make or support any decision about credit."
)


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


class Scripted:
    """Fake generator: replies in order and records every system prompt."""

    model = "fake"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.systems: list[str] = []

    def complete(self, system, user):
        self.systems.append(system)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply if isinstance(reply, str) else json.dumps(reply)


def _run(reply, dump, description=BANK, **kwargs):
    gen = reply if isinstance(reply, Scripted) else Scripted(reply)
    result = elicit(description, gen, dump=dump, snapshots_dir=SNAPSHOTS_DIR, **kwargs)
    return result, gen


def test_quoted_true_flag_is_kept_with_its_offsets(dump):
    quote = "A chatbot on our bank's website answers customers' questions"
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": quote}},
        dump,
    )
    assert isinstance(result, Elicitation)
    assert result.features["flags"] == {"interacts_with_natural_persons": True}
    assert result.features["description"] == BANK
    got = result.quotes["flags.interacts_with_natural_persons"]
    assert got == {"text": quote, "start": 0, "end": len(quote)}
    assert result.dropped == []


def test_false_flag_with_its_quote_is_kept(dump):
    quote = "It does not make or support any decision about credit."
    result, _ = _run(
        {"features": {"flags": {"creditworthiness_evaluation": False}},
         "quotes": {"flags.creditworthiness_evaluation": quote}},
        dump,
    )
    assert result.features["flags"] == {"creditworthiness_evaluation": False}
    start = BANK.index(quote)
    assert result.quotes["flags.creditworthiness_evaluation"] == {
        "text": quote, "start": start, "end": start + len(quote),
    }


def test_unquoted_flag_is_dropped_and_its_empty_flags_object_removed(dump):
    result, _ = _run(
        {"features": {"domain": "banking", "flags": {"social_scoring": False}},
         "quotes": {"domain": "on our bank's website"}},
        dump,
    )
    assert "flags" not in result.features
    assert result.features["domain"] == "banking"
    assert result.dropped == [{"path": "flags.social_scoring", "reason": "no quote"}]


def test_quote_not_in_the_description_is_dropped(dump):
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True,
                                "social_scoring": False}},
         "quotes": {"flags.interacts_with_natural_persons": "a bot that talks to people",
                    "flags.social_scoring": "It does not make or support any decision"}},
        dump,
    )
    assert result.features["flags"] == {"social_scoring": False}
    assert result.dropped == [{"path": "flags.interacts_with_natural_persons",
                               "reason": "quote not in the description"}]
    assert "flags.interacts_with_natural_persons" not in result.quotes


def test_two_word_quote_is_dropped(dump):
    result, _ = _run(
        {"features": {"domain": "banking", "flags": {"interacts_with_natural_persons": True}},
         "quotes": {"domain": "bank's website",
                    "flags.interacts_with_natural_persons": "A chatbot on our bank's website"}},
        dump,
    )
    assert "domain" not in result.features
    assert result.dropped == [{"path": "domain", "reason": "quote shorter than three words"}]


def test_whitespace_differences_are_tolerated_and_offsets_name_the_original(dump):
    description = "A chatbot  on our\nbank's   website answers customers."
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": " chatbot on   our bank's\twebsite "}},
        dump,
        description=description,
    )
    got = result.quotes["flags.interacts_with_natural_persons"]
    assert (got["start"], got["end"]) == (2, description.index(" answers"))
    assert got["text"] == description[got["start"]:got["end"]]
    assert got["text"] == "chatbot  on our\nbank's   website"


def test_case_differences_are_not_tolerated(dump):
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": "a chatbot on our bank's website"}},
        dump,
    )
    assert "flags" not in result.features
    assert result.dropped == [{"path": "flags.interacts_with_natural_persons",
                               "reason": "quote not in the description"}]


def test_offsets_are_code_points_at_the_first_occurrence(dump):
    description = "Café \U0001F600 bot: it answers questions. Later: it answers questions."
    quote = "it answers questions."
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": quote}},
        dump,
        description=description,
    )
    got = result.quotes["flags.interacts_with_natural_persons"]
    assert got["start"] == description.index(quote) == 12
    assert got["end"] == 12 + len(quote)


def test_deployer_key_without_quote_is_dropped_and_array_field_kept(dump):
    result, _ = _run(
        {"features": {"purposes": ["answer questions about card fees"],
                      "deployer": {"body_governed_by_public_law": False}},
         "quotes": {"purposes": "answers customers' questions about opening hours and card fees"}},
        dump,
    )
    assert result.features["purposes"] == ["answer questions about card fees"]
    assert "deployer" not in result.features
    assert result.dropped == [{"path": "deployer.body_governed_by_public_law",
                               "reason": "no quote"}]


def test_quote_for_a_path_the_features_do_not_carry_is_ignored_and_noted(dump):
    result, _ = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": "A chatbot on our bank's website",
                    "flags.social_scoring": "It does not make or support any decision"}},
        dump,
    )
    assert "flags.social_scoring" not in result.quotes
    assert result.dropped == []
    assert any("flags.social_scoring" in n and "ignored" in n for n in result.notes)


def test_reply_without_features_is_retried(dump):
    gen = Scripted(
        {"quotes": {}},
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": "A chatbot on our bank's website"}},
    )
    result, gen = _run(gen, dump)
    assert len(gen.systems) == 2, "exactly one retry"
    assert result.features["flags"] == {"interacts_with_natural_persons": True}
    assert any("attempt 1" in n and "features" in n for n in result.notes)


@pytest.mark.parametrize("reply", [
    ["not an object"],
    {"features": {"flags": {}}},
    {"features": "x", "quotes": {}},
    {"features": {}, "quotes": ["a"]},
])
def test_reply_of_the_wrong_shape_is_a_schema_violation_twice_then_none(dump, reply):
    result, gen = _run(reply, dump)
    assert len(gen.systems) == 2
    assert result.features is None
    assert result.quotes == {} and result.dropped == []
    assert any("failed" in n for n in result.notes)


def test_prompt_record_names_the_template_the_render_and_the_build(dump):
    result, gen = _run(
        {"features": {}, "quotes": {}}, dump,
    )
    template = V7_PATH.read_bytes()
    ids = list(dict.fromkeys(PLACEHOLDER_RE.findall(template.decode("utf-8"))))
    assert result.prompt == {
        "prompt": "elicit_features",
        "version": "v7",
        "template_sha256": hashlib.sha256(template).hexdigest(),
        "rendered_sha256": hashlib.sha256(gen.systems[0].encode("utf-8")).hexdigest(),
        "provisions": ids,
        "graph_version": dump["build"]["build_id"],
    }
    assert "{{provision:" not in gen.systems[0]


def test_provision_failure_makes_no_generator_call(dump):
    broken = copy.deepcopy(dump)
    first = PLACEHOLDER_RE.findall(V7_PATH.read_text(encoding="utf-8"))[0]
    broken["nodes"] = [n for n in broken["nodes"] if n.get("id") != first]
    gen = Scripted({"features": {}, "quotes": {}})
    result, gen = _run(gen, broken)
    assert gen.systems == [], "no model call"
    assert result.features is None
    assert result.quotes == {} and result.dropped == []
    assert result.notes == [
        f"definition {first} does not resolve in {dump['build']['build_id']}: "
        "unknown node; no model call made"
    ]
    assert result.prompt["rendered_sha256"] is None
    assert result.prompt["provisions"] == []


def test_v5_still_works_and_returns_no_quotes(dump):
    result, gen = _run(
        {"domain": "banking", "flags": {"interacts_with_natural_persons": True}},
        dump,
        prompt_version="v5",
    )
    v5 = (ROOT / "prompts" / "elicit_features" / "v5.md").read_bytes()
    assert gen.systems == [v5.decode("utf-8")]
    assert result.features["flags"] == {"interacts_with_natural_persons": True}
    assert result.quotes == {} and result.dropped == []
    assert result.prompt["version"] == "v5"
    assert result.prompt["provisions"] == []
    assert result.prompt["template_sha256"] == hashlib.sha256(v5).hexdigest()


def test_the_served_build_renders_v6_and_names_dropped_facts():
    """B10: was the elicit_features wrapper's test; the wrapper is deleted
    (Task 5) and its callers serve the build load_active reads from
    data/graph_dumps, so elicit() is run over that build here."""
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    from tere4ai.graph_store.publication import load_active

    gen = Scripted(
        {"features": {"flags": {"interacts_with_natural_persons": True,
                                "social_scoring": False}},
         "quotes": {"flags.interacts_with_natural_persons": "A chatbot on our bank's website"}},
    )
    # B10: the dropped fact is in result.dropped, no longer folded into the notes
    result = elicit(BANK, gen, dump=load_active(ROOT / "data" / "graph_dumps").dump,
                    snapshots_dir=SNAPSHOTS_DIR)
    assert result.features["flags"] == {"interacts_with_natural_persons": True}
    assert {"path": "flags.social_scoring", "reason": "no quote"} in result.dropped
    assert "{{provision:" not in gen.systems[0]


def test_render_prompt_is_the_system_prompt_elicit_sends_and_its_record(dump):
    """B10: the benchmark script records the prompt once per run with
    render_prompt; it is the prompt and record elicit() uses."""
    from tere4ai.elicit_features.elicitor import render_prompt

    system, prompt = render_prompt(dump, SNAPSHOTS_DIR)
    result, gen = _run(
        {"features": {"flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": "A chatbot on our bank's website"}},
        dump,
    )
    assert gen.systems == [system]
    assert prompt == result.prompt
    assert prompt["version"] == "v7" and prompt["graph_version"] == dump["build"]["build_id"]


def test_render_prompt_raises_when_a_provision_does_not_resolve(dump):
    from tere4ai.elicit_features.elicitor import render_prompt

    broken = {**dump, "nodes": [n for n in dump["nodes"] if n["id"] != "eu-ai-act:definition:profiling"]}
    with pytest.raises(ProvisionUnresolved, match="eu-ai-act:definition:profiling"):
        render_prompt(broken, SNAPSHOTS_DIR)


def test_null_and_empty_list_fields_are_unknown_not_dropped_facts(dump):
    """B10 final review: a field the model sets to null or to an empty list
    states no fact, so it needs no quote, is removed as unknown and is not
    named in dropped."""
    quote = "A chatbot on our bank's website"
    result, _ = _run(
        {"features": {"domain": None, "purposes": [], "affected_persons": [],
                      "autonomy": None,
                      "flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": quote}},
        dump,
    )
    assert result.dropped == []
    for key in ("domain", "purposes", "affected_persons", "autonomy"):
        assert key not in result.features
    assert result.features["flags"] == {"interacts_with_natural_persons": True}


def test_null_deployer_key_is_unknown_not_a_schema_violation(dump):
    quote = "A chatbot on our bank's website"
    result, gen = _run(
        {"features": {"deployer": {"body_governed_by_public_law": None},
                      "flags": {"interacts_with_natural_persons": True}},
         "quotes": {"flags.interacts_with_natural_persons": quote}},
        dump,
    )
    assert len(gen.systems) == 1, "no retry"
    assert result.dropped == []
    assert "deployer" not in result.features


LOAN = "The bank scores loan applicants, then a clerk decides."


def test_quote_that_cuts_a_word_is_not_in_the_description(dump):
    """B10 final review: a match must start and end at word boundaries."""
    result, _ = _run(
        {"features": {"flags": {"creditworthiness_evaluation": True}},
         "quotes": {"flags.creditworthiness_evaluation": "ank scores loan"}},
        dump,
        description=LOAN,
    )
    assert "flags" not in result.features
    assert result.dropped == [{"path": "flags.creditworthiness_evaluation",
                               "reason": "quote not in the description"}]


def test_quote_ending_before_punctuation_is_kept(dump):
    result, _ = _run(
        {"features": {"flags": {"creditworthiness_evaluation": True}},
         "quotes": {"flags.creditworthiness_evaluation": "scores loan applicants"}},
        dump,
        description=LOAN,
    )
    assert result.features["flags"] == {"creditworthiness_evaluation": True}
    start = LOAN.index("scores")
    assert result.quotes["flags.creditworthiness_evaluation"] == {
        "text": "scores loan applicants", "start": start, "end": start + len("scores loan applicants"),
    }


def test_a_later_occurrence_on_word_boundaries_is_found(dump):
    description = "Our sandbank scores loan games; the bank scores loan risk daily."
    result, _ = _run(
        {"features": {"flags": {"creditworthiness_evaluation": True}},
         "quotes": {"flags.creditworthiness_evaluation": "bank scores loan"}},
        dump,
        description=description,
    )
    got = result.quotes["flags.creditworthiness_evaluation"]
    assert got["start"] == description.index("the bank") + len("the ")

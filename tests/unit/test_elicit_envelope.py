"""Elicitation envelope: proposals only, never a classification.

The elicited facts are proposals until a human confirms them, so the
envelope status is requires_human_review by construction (DEC-13 keeps
the deterministic ladder the only decision path). B10: the envelope and
the MCP tool elicit over the served build's dump, and the answer carries
the quotes, the dropped facts and the prompt record beside the features.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from tere4ai.elicit_features.elicitor import schema_flag_names
from tere4ai.elicit_features.provisions import PLACEHOLDER_RE
from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.mcp_server import replay, server
from tere4ai.mcp_server.elicit import MIN_DESCRIPTION_CHARS, elicit_envelope
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE, SECTION_8_ENVELOPE_FIELDS

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
V6_PATH = ROOT / "prompts" / "elicit_features" / "v6.md"

SPAM = "A spam filter for a small company's inboxes. It quarantines mail retrievably."
QUOTE = "A spam filter for a small company's inboxes."
ANSWER_FIELDS = {"features", "quotes", "dropped", "notes", "prompt"}
QUOTE_LINE = (
    "each proposed fact carries words of the description; code checked that "
    "the words are there, a person judges whether they support the fact"
)


class FakeGenerator:
    model = "fake"

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        return self._payload


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _reply_with_a_dropped_flag() -> str:
    """Two quoted facts kept, one flag whose quote is not in the description."""
    return json.dumps({
        "features": {
            "domain": "email security",
            "flags": {
                "social_scoring": False,
                "interacts_with_natural_persons": False,
                "biometric_categorisation": False,
            },
        },
        "quotes": {
            "domain": QUOTE,
            "flags.social_scoring": QUOTE,
            "flags.interacts_with_natural_persons": QUOTE,
            "flags.biometric_categorisation": "it never sorts people by their faces",
        },
    })


def _assert_quoted_answer(env: dict, build_id: str) -> None:
    """The answer fields B10 adds, and the dropped flag named once."""
    assert set(env["answer"]) == ANSWER_FIELDS
    answer = env["answer"]
    assert answer["quotes"]["flags.social_scoring"]["text"] == QUOTE
    assert answer["quotes"]["flags.social_scoring"]["start"] == 0
    assert answer["dropped"] == [
        {"path": "flags.biometric_categorisation", "reason": "quote not in the description"}
    ]
    assert "biometric_categorisation" not in answer["features"]["flags"]
    assert answer["prompt"]["version"] == "v6"
    assert re.fullmatch(r"[0-9a-f]{64}", answer["prompt"]["template_sha256"])
    assert answer["prompt"]["graph_version"] == build_id
    # Other flag names start with this one, so match the whole name.
    named = [
        m for m in env["missing_facts"]
        if re.search(r"\bbiometric_categorisation\b", m)
    ]
    assert named == ["flags.biometric_categorisation dropped: quote not in the description"]
    assert env["graph_version"] == build_id


def test_schema_flag_names_lists_all_38_flags():
    names = schema_flag_names()
    assert len(names) == 38
    assert names == sorted(names)
    assert "social_scoring" in names
    assert "creditworthiness_evaluation" in names


def test_elicit_envelope_is_a_section8_proposal(dump):
    # B10: the envelope elicits over the served build's dump and snapshots
    # (no graph_version argument: the envelope names the dump's build), and
    # the answer carries quotes, dropped and the prompt record.
    gen = FakeGenerator(_reply_with_a_dropped_flag())
    env = elicit_envelope(SPAM, gen, dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert set(env.keys()) == set(SECTION_8_ENVELOPE_FIELDS)
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.5
    assert env["answer"]["features"]["flags"]["social_scoring"] is False
    assert "risk_category" not in json.dumps(env["answer"])
    _assert_quoted_answer(env, dump["build"]["build_id"])
    unspecified = env["missing_facts"]
    assert "flag not elicited: subliminal_or_manipulative" in unspecified
    assert not any("social_scoring" in m for m in unspecified)
    assert QUOTE_LINE in env["legal_status_notes"]


def test_elicit_envelope_names_a_dropped_field_outside_the_flags(dump):
    reply = json.dumps({
        "features": {"domain": "email security", "autonomy": "full"},
        "quotes": {"domain": QUOTE, "autonomy": "full"},
    })
    env = elicit_envelope(SPAM, FakeGenerator(reply), dump=dump, snapshots_dir=SNAPSHOTS_DIR)
    assert "autonomy" not in env["answer"]["features"]
    assert "autonomy dropped: quote shorter than three words" in env["missing_facts"]


def test_elicit_envelope_degrades_when_elicitation_fails(dump):
    env = elicit_envelope(
        "Too vague.", FakeGenerator("not json"), dump=dump, snapshots_dir=SNAPSHOTS_DIR
    )
    assert env["status"] == "requires_human_review"
    assert env["confidence"] == 0.0
    assert env["answer"] is None
    assert env["missing_facts"] == ["elicitation failed; fill the facts manually"]


def test_elicit_envelope_names_an_unresolved_definition(dump):
    broken = copy.deepcopy(dump)
    first = PLACEHOLDER_RE.findall(V6_PATH.read_text(encoding="utf-8"))[0]
    broken["nodes"] = [n for n in broken["nodes"] if n.get("id") != first]
    gen = FakeGenerator(_reply_with_a_dropped_flag())
    env = elicit_envelope(SPAM, gen, dump=broken, snapshots_dir=SNAPSHOTS_DIR)
    assert gen.calls == 0, "no model call"
    assert env["answer"] is None
    assert env["missing_facts"][0] == (
        f"definition {first} does not resolve in {dump['build']['build_id']}: "
        "unknown node; no model call made"
    )
    assert env["graph_version"] == dump["build"]["build_id"]


# The MCP tool: the active build per call, the paid clients through
# _paid_clients_or_envelope, the facade's minimum description length.


@pytest.fixture()
def mcp_server(monkeypatch, dump):
    built = []

    def install(generator):
        monkeypatch.setattr(
            server,
            "_active",
            lambda: LoadedBuild(dump, {"norms": []}, {"assertions": []},
                                dump["build"]["build_id"], "legacy", None),
        )

        def clients():
            built.append(generator)
            # C3: the paid clients carry the model parameters hash, which
            # keys the replay window; a fresh window keeps tests apart.
            return server.PaidClients(generator, None, "mock-parameters")

        monkeypatch.setattr(server, "_paid_clients_or_envelope", clients)
        monkeypatch.setattr(server, "_REPLAY", replay.ReplayStore(window_seconds=600))
        return built

    return install


def test_mcp_elicit_features_answers_with_quotes_dropped_and_prompt(mcp_server, dump):
    gen = FakeGenerator(_reply_with_a_dropped_flag())
    mcp_server(gen)
    env = server.elicit_features(SPAM)
    assert env["status"] == "requires_human_review"
    assert gen.calls == 1
    _assert_quoted_answer(env, dump["build"]["build_id"])


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_mcp_elicit_features_refuses_an_empty_description(mcp_server, bad):
    built = mcp_server(FakeGenerator("{}"))
    env = server.elicit_features(bad)
    assert built == [], "no paid client is built"
    assert env["answer"] is None
    assert env["confidence"] == 0.0
    assert "'description'" in env["missing_facts"][0]
    assert env["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE


def test_mcp_elicit_features_keeps_the_facades_minimum_length(mcp_server):
    from tere4ai.http_facade.app import ElicitRequest

    floor = ElicitRequest.model_fields["description"].metadata[0].min_length
    assert MIN_DESCRIPTION_CHARS == floor == 30
    built = mcp_server(FakeGenerator("{}"))
    env = server.elicit_features("x" * (MIN_DESCRIPTION_CHARS - 1))
    assert built == []
    assert env["answer"] is None
    assert f"at least {MIN_DESCRIPTION_CHARS} characters" in env["missing_facts"][0]


def test_mcp_elicit_features_without_a_dump_degrades(monkeypatch):
    monkeypatch.setattr(
        server, "_active",
        lambda: LoadedBuild(None, None, None, None, "manifest", "publication drifted"),
    )
    monkeypatch.setattr(
        server, "_paid_clients_or_envelope",
        lambda: pytest.fail("paid clients built without a dump"),
    )
    env = server.elicit_features(SPAM)
    assert env["answer"] is None
    assert env["graph_version"] == "unavailable"
    assert "publication drifted" in " ".join(env["missing_facts"])


def test_mcp_elicit_features_passes_a_config_error_through(monkeypatch, dump):
    monkeypatch.setattr(
        server, "_active",
        lambda: LoadedBuild(dump, None, None, dump["build"]["build_id"], "legacy", None),
    )
    degraded = {"answer": None, "missing_facts": ["missing model configuration"]}
    monkeypatch.setattr(server, "_paid_clients_or_envelope", lambda: degraded)
    assert server.elicit_features(SPAM) is degraded

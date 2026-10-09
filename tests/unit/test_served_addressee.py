"""B145 (spec G D-G80 (10), (21); brief A5, A19): the role filter serves by
the stored value of the Act's parties, the served entry names the value and
the written words, the argument is addressee and the old one is refused, and
the one loader serves a version 1 file in version 2's names without
rewriting it. Scripted norms (mock data) unless a test names the tracked
dumps."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tere4ai import act_parties as ap
from tere4ai.mcp_server.requirements import ACTOR_RETIRED, get_applicable_requirements
from tere4ai.mcp_server.trace_code import trace_implementation

ROOT = Path(__file__).resolve().parents[2]
DUMPS = ROOT / "data" / "graph_dumps"
LAYER1 = DUMPS / "layer1.json"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")
HIGH_RISK = {"risk_category": "high_risk"}


@pytest.fixture(scope="module")
def dump():
    return json.loads(LAYER1.read_text(encoding="utf-8"))


def _norm(n, unit, explicit=None, inferred=None, source=None):
    return {"norm_id": f"norm:{unit}:n{n}", "source_node_id": unit, "source_span_id": "s", "deontic_type": "obligation",
            "modal": "shall", "actor_explicit": explicit, "actor_inferred": inferred,
            "actor_inference_source_node_id": source, "action": "a", "object": "o", "judge_verdict": "accepted",
            "review_status": "accepted", "extractor_prompt_version": "v4"}


U17, U26, U72, U16 = ("eu-ai-act:article-17:paragraph-1", "eu-ai-act:article-26:paragraph-1",
                      "eu-ai-act:article-72:paragraph-1", "eu-ai-act:article-16:paragraph-1")
PAYLOAD = {"norms": [
    _norm(1, U17, explicit="providers of high-risk AI systems"),
    _norm(2, U17, explicit="downstream providers"),
    _norm(3, U26, explicit="deployers who are employers"),
    _norm(4, U26, explicit="notified bodies"),
    _norm(5, U26, explicit="the Board"),
    _norm(6, U72, inferred="operator_general", source=U72),
    _norm(7, U72, inferred="ai_office", source=U72),
    _norm(8, U72, inferred="national_competent_authority", source=U72),
    _norm(9, U72, inferred="unspecified_needs_review", source=U72),
    _norm(10, U16, explicit="that system"),
]}


def _served(addressee, payload=PAYLOAD, dump_=None):
    answer = get_applicable_requirements(HIGH_RISK, payload, dump_, addressee)["answer"]
    return {e["norm_id"].rsplit(":n", 1)[1]: e for group in answer["requirements_by_article"].values() for e in group}


def test_the_filter_serves_by_the_stored_value(dump):
    def ids(addressee):
        return sorted(int(k) for k in _served(addressee, dump_=dump))
    assert ids("provider") == [1, 2, 6]          # R7: operators in general to every role
    assert ids("deployer") == [3, 6]
    assert ids("importer") == [6]
    assert ids("notified_body") == [4]           # "notified bodies" was missed by the substring
    assert ids("board") == [5]
    assert ids("commission") == [7]              # R26: Article 3(47), one way
    assert ids("ai_office") == [7]
    assert ids("notifying_authority") == [8]     # R26: Article 3(48), one way
    assert ids("market_surveillance_authority") == [8]
    assert ids("national_competent_authority") == [8]
    for value in ap.requestable():
        assert 9 not in ids(value) and 10 not in ids(value)  # unplaced and unsettled: served to no request


def test_the_entry_names_the_value_the_written_words_and_the_source(dump):
    served = _served(None, dump_=dump)
    assert {k: served["1"][k] for k in ("addressee", "addressee_explicit", "addressee_source",
                                         "addressee_inference_source_node_id")} == {
        "addressee": "provider", "addressee_explicit": "providers of high-risk AI systems",
        "addressee_source": "explicit", "addressee_inference_source_node_id": None}
    assert {k: served["7"][k] for k in ("addressee", "addressee_explicit", "addressee_source",
                                         "addressee_inference_source_node_id")} == {
        "addressee": "ai_office", "addressee_explicit": None, "addressee_source": "inferred",
        "addressee_inference_source_node_id": U72}
    assert served["10"]["addressee"] == "unspecified_needs_review"
    assert not [k for e in served.values() for k in e if k.startswith("actor")]


def test_the_same_answer_for_a_version_2_payload(dump):
    v2 = {"norms_schema_version": 2, "norms": [ap.in_v2_names(n) for n in PAYLOAD["norms"]]}
    assert _served("provider", dump_=dump) == _served("provider", payload=v2, dump_=dump)


@pytest.mark.parametrize("bad", ["unspecified_needs_review", "operator_general", "vendor", "Provider"])
def test_a_sentinel_or_a_value_outside_the_list_is_refused_with_the_accepted_values(dump, bad):
    envelope = get_applicable_requirements(HIGH_RISK, PAYLOAD, dump, bad)
    assert envelope["status"] == "not_applicable"
    assert envelope["answer"]["requirements_by_article"] == {}
    (fact,) = envelope["missing_facts"]
    assert f"'{bad}'" in fact and "provider, product_manufacturer, deployer" in fact
    assert "unspecified_needs_review" not in fact.split(":", 1)[1]


def test_the_retired_actor_argument_is_refused_naming_addressee(dump):
    """Review Focus 3: never served every party's norms because the old argument was dropped."""
    envelope = get_applicable_requirements(HIGH_RISK, PAYLOAD, dump, actor="provider")
    assert envelope["status"] == "not_applicable"
    assert envelope["missing_facts"] == [ACTOR_RETIRED]
    assert "addressee" in ACTOR_RETIRED
    traced = trace_implementation(HIGH_RISK, [], PAYLOAD, {"assertions": []}, dump, actor="provider")
    assert ACTOR_RETIRED in traced["missing_facts"]
    assert get_applicable_requirements(HIGH_RISK, PAYLOAD, dump, "provider")["answer"]["summary"][
        "addressee_filter"] == "provider"


def _app(tmp_path):
    from tere4ai.http_facade.app import create_app

    for name in ("layer1.json", "norms_core.json", "alignments_core.json", "core_nodes.txt"):
        shutil.copyfile(DUMPS / name, tmp_path / name)
    return create_app(dump_dir=tmp_path)


def test_the_facade_serves_a_version_1_file_in_version_2_names_and_leaves_it_unchanged(tmp_path):
    """Review Focus 1, A19: norms_core.json (version 1, disposable, pre-B74) read through the list."""
    app = _app(tmp_path)
    before = hashlib.sha256((tmp_path / "norms_core.json").read_bytes()).hexdigest()
    with TestClient(app) as client:
        env = client.post("/api/requirements", json={"classification": HIGH_RISK, "addressee": "provider"}).json()
        entries = [e for g in env["answer"]["requirements_by_article"].values() for e in g]
        assert entries and all(e["addressee"] in ("provider", "operator_general") for e in entries)
        assert any(e["addressee_explicit"] and e["addressee_explicit"].lower() != "provider" for e in entries)
        refused = client.post("/api/requirements", json={"classification": HIGH_RISK, "actor": "provider"}).json()
        assert refused["missing_facts"] == [ACTOR_RETIRED]
        units = client.get("/api/units").json()
        candidate = next(c for u in units["units"] for c in u["candidates"])
        assert {"addressee_explicit", "addressee_inferred", "addressee_inference_source_node_id", "addressee"} <= set(candidate)
        assert not [k for k in candidate if k.startswith("actor")]
        norm_id = entries[0]["norm_id"]
        explained = client.post("/api/explain", json={"norm_id": norm_id}).json()
        assert set(explained["answer"]["deontic"]["addressee"]) == {"value", "explicit", "inferred", "inference_source_node_id"}
        assert "actor" not in explained["answer"]["deontic"]
    assert hashlib.sha256((tmp_path / "norms_core.json").read_bytes()).hexdigest() == before
    raw = json.loads((tmp_path / "norms_core.json").read_text(encoding="utf-8"))
    assert "norms_schema_version" not in raw and "actor_explicit" in raw["norms"][0]

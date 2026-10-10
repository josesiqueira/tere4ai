"""B145 (spec G D-G80; brief acceptance A4, A5, A19): the v5 pipeline through
its command line with scripted models (no network, no keys) over ten units
of the Act as amended, read from a copy of the tracked layer1.json; then the
requirements tool and the facade over its output. The scripted replies
stand for a model that follows v5 on most norms and writes the thing on
one; what a real model does under v5 is measured by B74, the build record's
counts, E1 and LAYER2_STEP3, not here."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from tere4ai import act_parties as ap
from tere4ai.graph_store.build_record import BuildRecordStore

ROOT = Path(__file__).resolve().parents[2]
DUMPS = ROOT / "data" / "graph_dumps"
LAYER1 = DUMPS / "layer1.json"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")


def _a(n, p):
    return f"eu-ai-act:article-{n}:paragraph-{p}"


U17, U72_1, U72_2, U73_1, U73_3, U11, U22_3, U26_7, U50_5, U12 = (
    _a(17, 1), _a(72, 1), _a(72, 2), _a(73, 1), _a(73, 3), _a(11, 1), _a(22, 3), _a(26, 7), _a(50, 5), _a(12, 1))
UNITS = [U17, U72_1, U72_2, U73_1, U73_3, U11, U22_3, U26_7, U50_5, U12]
POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"


def _c(action, obj, explicit=None, inferred=None, source=None, deontic="obligation", modal="shall"):
    return {"deontic_type": deontic, "modal": modal, "addressee_explicit": explicit, "addressee_inferred": inferred,
            "addressee_inference_source_node_id": source, "action": action, "object": obj, "conditions": [],
            "exceptions": [], "lifecycle_phase_ids": [], "requirement_type": "process"}


SCRIPT = {
    U17: [_c("put in place", "a quality management system", explicit="providers of high-risk AI systems"),
          _c("document", "the quality management system", inferred="provider", source=U17)],
    U72_1: [_c("establish and document", "a post-market monitoring system", explicit="providers")],
    U72_2: [_c("collect, document and analyse", "relevant data", inferred="provider", source=U72_1),
            _c("include", "an analysis of the interaction with other AI systems",
               explicit="the post-market monitoring system")],
    U73_1: [_c("report", "any serious incident",
               explicit="providers of high-risk AI systems placed on the Union market")],
    U73_3: [_c("provide", "the report referred to in paragraph 1", inferred="provider", source=U73_1)],
    U11: [_c("provide", "the elements of the technical documentation specified in Annex IV",
             explicit="SMEs, including start-ups, and SMCs", deontic="permission", modal="may")],
    U22_3: [_c("provide", "a copy of the mandate", explicit="the authorised representative")],
    U26_7: [_c("inform", "workers’ representatives and the affected workers", explicit="deployers who are employers")],
    U50_5: [_c("provide", "the information referred to in paragraphs 1 to 4", inferred="provider", source=_a(50, 1)),
            _c("provide", "the information referred to in paragraphs 1 to 4", inferred="deployer", source=_a(50, 3))],
    U12: [_c("technically allow for", "the automatic recording of events (logs)", inferred="provider", source=POINT_A)],
}
ACCEPT = json.dumps({"verdict": "accepted", "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9,
                     "operational_utility": 0.8, "evidence_strength": 0.85, "judge_confidence": 0.9},
                     "rationale": "scripted", "requirement_type_agrees": None})


def _id(unit, n):
    return f"norm:{unit}:n{n}"


def _run(tmp_path, monkeypatch):
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.extract_norms import pipeline
    from tere4ai.extract_norms.model_clients import FakeClient

    class ScriptedModel(FakeClient):
        sampling = temperature = "API default (rejected by the model)"
        effort = "xhigh"
        json_mode = "sent"

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.usage = {}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"}

    dump_path = tmp_path / "layer1.json"
    shutil.copyfile(LAYER1, dump_path)
    generator = ScriptedModel({f"Source unit node id: {u}\n": json.dumps({"norms": SCRIPT[u]}) for u in UNITS}, model="g")
    judge = ScriptedModel({"Candidate norm (JSON)": ACCEPT}, model="j")
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: generator)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: judge)
    monkeypatch.setattr(pipeline, "DEFAULT_LOG_PATH", tmp_path / "extraction_log.jsonl")
    out = tmp_path / "norms_core.json"
    # no --prompt-version: the run takes the default, v5, as B74 does
    assert cli.main(["--nodes", ",".join(UNITS), "--dump", str(dump_path), "--out", str(out)]) == 0
    store = BuildRecordStore(tmp_path)
    (execution,) = store.read(store.resolve("core"))["executions"]
    return json.loads(out.read_text(encoding="utf-8")), execution, judge, out


@pytest.fixture
def run(tmp_path, monkeypatch):
    return _run(tmp_path, monkeypatch)


def _judge_input(judge, unit, action):
    (user,) = [u for _s, u in judge.calls if f"Source unit node id: {unit}\n" in u and f'"action": "{action}"' in u]
    return user


def test_the_v5_run_writes_version_2_with_both_v5_hashes_and_the_list_as_an_input(run):
    payload, execution, _judge, _out = run
    assert payload["norms_schema_version"] == 2
    assert {n["extractor_prompt_version"] for n in payload["norms"]} == {"v5"}
    validator = Draft202012Validator(json.loads(ap.NORMS_SCHEMA_PATHS[2].read_text(encoding="utf-8")))
    for norm in payload["norms"]:
        assert list(validator.iter_errors(norm)) == [], norm["norm_id"]
        assert norm["addressee"] in ap.values() and norm["addressee_method"] == "act_parties_v1"
    sha = {kind: hashlib.sha256((ROOT / "prompts" / kind / "v5.md").read_bytes()).hexdigest()
           for kind in ("extract_norms", "judge_norms")}
    assert execution["config"]["prompt_version"] == "v5"
    assert execution["prompt_sha256"] == {"generator": sha["extract_norms"], "judge": sha["judge_norms"]}
    (listed,) = [i for i in execution["inputs"] if i["input_kind"] == "act_parties"]
    assert listed["sha256"] == hashlib.sha256(ap.ACT_PARTIES_PATH.read_bytes()).hexdigest()
    assert len(payload["norms"]) == 13


def test_the_set_up_rule_norms_carry_their_party_and_source(run):
    payload, _e, judge, _out = run
    by_id = {n["norm_id"]: n for n in payload["norms"]}
    slots = lambda nid: tuple(by_id[nid][k] for k in ("addressee_explicit", "addressee_inferred",  # noqa: E731
                                                      "addressee_inference_source_node_id"))
    assert slots(_id(U17, 2)) == (None, "provider", U17)
    assert slots(_id(U72_2, 1)) == (None, "provider", U72_1)
    assert slots(_id(U73_3, 1)) == (None, "provider", U73_1)
    assert slots(_id(U50_5, 1)) == (None, "provider", _a(50, 1))
    assert slots(_id(U50_5, 2)) == (None, "deployer", _a(50, 3))
    assert slots(_id(U22_3, 1)) == ("the authorised representative", None, None)
    assert slots(_id(U12, 1)) == (None, "provider", POINT_A)
    nodes = {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"]}
    user = _judge_input(judge, U72_2, "collect, document and analyse")
    assert f"Addressee-inference source: {U72_1} (Paragraph)\nVerbatim text of the addressee-inference source:\n[{U72_1}] {nodes[U72_1]['text']}" in user
    assert "Set-up rows for this unit:" in user
    assert "Set-up rows for this unit:" in _judge_input(judge, U72_2, "include")


def test_the_sme_permission_keeps_its_words_and_is_placed_on_provider(run):
    payload, _e, _j, _out = run
    (norm,) = [n for n in payload["norms"] if n["source_node_id"] == U11]
    assert (norm["addressee_explicit"], norm["addressee_inferred"], norm["addressee_inference_source_node_id"]) == (
        "SMEs, including start-ups, and SMCs", None, None)
    assert (norm["addressee"], norm["addressee_placement"]) == ("provider", "placed")


def test_the_build_records_lists(run):
    payload, execution, _j, _out = run
    counts = execution["counts"]
    assert counts["set_up_rule_applied"]["norm_ids"] == [
        _id(U17, 2), _id(U72_2, 1), _id(U73_3, 1), _id(U50_5, 1), _id(U50_5, 2)]
    assert counts["set_up_thing_as_written_addressee"]["norm_ids"] == [_id(U72_2, 2)]
    assert counts["unplaced_written_addressees"] == [
        {"phrase": "the post-market monitoring system", "norm_ids": [_id(U72_2, 2)]}]
    assert sum(counts["addressee_values"].values()) == len(payload["norms"])
    assert counts["section_2_not_served_to_provider"] == {"count": 0, "norm_ids": []}


def test_what_each_party_is_served_through_the_tool(run):
    """A5 over the run's output, a high-risk classification."""
    from tere4ai.mcp_server.requirements import get_applicable_requirements

    payload, _e, _j, _out = run
    dump = json.loads(LAYER1.read_text(encoding="utf-8"))

    def served(addressee):
        answer = get_applicable_requirements({"risk_category": "high_risk"}, payload, dump, addressee)["answer"]
        return {e["norm_id"] for g in answer["requirements_by_article"].values() for e in g}

    provider, deployer = served("provider"), served("deployer")
    assert {_id(U17, 1), _id(U17, 2), _id(U72_2, 1), _id(U73_3, 1), _id(U50_5, 1), _id(U11, 1), _id(U12, 1)} <= provider
    assert deployer == {_id(U26_7, 1), _id(U50_5, 2)}
    assert _id(U72_2, 2) not in provider | deployer
    assert served("authorised_representative") == {_id(U22_3, 1)}


def test_the_facade_reads_the_version_2_file_as_stored(run, tmp_path):
    """A19: a version 2 file is read as stored; the file is not rewritten."""
    from tere4ai.http_facade.app import create_app

    _payload, _e, _j, out = run
    served_dir = tmp_path / "served"
    served_dir.mkdir()
    for name in ("layer1.json", "alignments_core.json", "core_nodes.txt"):
        shutil.copyfile(DUMPS / name, served_dir / name)
    shutil.copyfile(out, served_dir / "norms_core.json")
    before = (served_dir / "norms_core.json").read_bytes()
    with TestClient(create_app(dump_dir=served_dir)) as client:
        env = client.post("/api/requirements", json={"classification": {"risk_category": "high_risk"},
                                                     "addressee": "deployer"}).json()
        entries = {e["norm_id"]: e for g in env["answer"]["requirements_by_article"].values() for e in g}
        assert set(entries) == {_id(U26_7, 1), _id(U50_5, 2)}
        assert entries[_id(U50_5, 2)]["addressee_inference_source_node_id"] == _a(50, 3)
        assert entries[_id(U26_7, 1)]["addressee_explicit"] == "deployers who are employers"
    assert (served_dir / "norms_core.json").read_bytes() == before

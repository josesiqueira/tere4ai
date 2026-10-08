"""B144 (DEC-26, spec G D-G76): the v4 pipeline through its command line
with scripted models (no network, no keys) over five units of the Act as
amended, read from a copy of the tracked layer1.json, then the requirements
tool and the facade over its output. The brief's acceptance A2 and A3. The
scripted replies stand for a model that follows v4 on some norms and fails
it on others; what a real model does under v4 is measured by B74, the
build record's checks, E1 and LAYER2_STEP3, not here."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tere4ai.graph_store.build_record import BuildRecordStore

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")

U11 = "eu-ai-act:article-11:paragraph-1"
U12 = "eu-ai-act:article-12:paragraph-1"
U14 = "eu-ai-act:article-14:paragraph-4"
U14D = "eu-ai-act:article-14:paragraph-4:point-d"
U17 = "eu-ai-act:article-17:paragraph-1"
UNITS = (U11, U12, U14, U14D, U17)
ART16 = "eu-ai-act:article-16"
ART16_P1 = "eu-ai-act:article-16:paragraph-1"
POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"
POINT_C = "eu-ai-act:article-16:paragraph-1:point-c"


def _norm(deontic, modal, explicit, inferred, source, action, obj, conditions=(), phases=(), rtype=None):
    return {"deontic_type": deontic, "modal": modal, "actor_explicit": explicit, "actor_inferred": inferred,
            "actor_inference_source_node_id": source, "action": action, "object": obj,
            "conditions": list(conditions), "exceptions": [], "lifecycle_phase_ids": list(phases),
            "requirement_type": rtype}


SCRIPT = {
    U11: [
        _norm("obligation", "shall", "the Commission", None, None, "establish",
              "a simplified technical documentation form"),
        _norm("obligation", "shall", "notified bodies", None, None, "accept", "the form",
              ["for the purposes of the conformity assessment"]),
    ],
    U12: [
        _norm("obligation", "shall", None, "provider", POINT_A, "technically allow for",
              "the automatic recording of events (logs)", ["over the lifetime of the system"], ["cross_phase"],
              "functional"),
        # a model that still writes the system as the actor (v3's reading)
        _norm("obligation", "shall", "high-risk AI systems", None, None, "technically allow",
              "the automatic recording of events", rtype="functional"),
    ],
    U14: [
        _norm("obligation", "shall", None, "provider", POINT_A, "be provided", "the high-risk AI system",
              ["for the purpose of implementing paragraphs 1, 2 and 3"], rtype="functional"),
        _norm("obligation", "shall", None, "provider", ART16, "provide", "the high-risk AI system to the deployer",
              rtype="functional"),
        _norm("obligation", "shall", "the deployer", "provider", POINT_A, "be provided to", "the deployer",
              rtype="functional"),
    ],
    U14D: [
        _norm("permission", "other_explicit", None, "unspecified_needs_review", U14D, "decide",
              "not to use the high-risk AI system", ["in any particular situation"], ["operation_monitoring"]),
        _norm("permission", "other_explicit", None, None, None, "disregard, override or reverse",
              "the output of the high-risk AI system"),
    ],
    U17: [
        _norm("obligation", "shall", None, "provider", POINT_A, "put in place", "a quality management system",
              rtype="process"),
        _norm("obligation", "shall", None, "provider", POINT_C, "document", "that system",
              ["in a systematic and orderly manner"], rtype="process"),
        _norm("obligation", "shall", None, "provider", ART16_P1, "include", "at least the following aspects",
              rtype="process"),
    ],
}


def _verdict(verdict):
    return json.dumps({"verdict": verdict, "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9,
                       "operational_utility": 0.8, "evidence_strength": 0.85, "judge_confidence": 0.9},
                       "rationale": "scripted", "requirement_type_agrees": None})


# FakeClient answers the first key found in its input, in this order
JUDGE_SCRIPT = {
    '"action": "accept"': _verdict("rejected"),
    '"action": "disregard, override or reverse"': _verdict("needs_human_review"),
    "Candidate norm (JSON)": _verdict("accepted"),
}


def _nodes():
    return {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"]}


def _prepare(tmp_path, monkeypatch):
    """The scripted models on the command, the dump copied beside the output."""
    import tere4ai.extract_norms.__main__ as cli
    from tere4ai.extract_norms import pipeline
    from tere4ai.extract_norms.model_clients import FakeClient

    class ScriptedModel(FakeClient):
        sampling = temperature = "provider default (rejected by the model)"
        effort = "xhigh"
        json_mode = "sent"
        usage: dict = {}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "xhigh", "judge_effort": "xhigh"}

    dump_path = tmp_path / "layer1.json"
    shutil.copyfile(LAYER1, dump_path)
    generator = ScriptedModel(
        {f"Source unit node id: {unit}\n": json.dumps({"norms": SCRIPT[unit]}) for unit in UNITS}, model="g")
    judge = ScriptedModel(JUDGE_SCRIPT, model="j")
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: generator)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: judge)
    monkeypatch.setattr(pipeline, "DEFAULT_LOG_PATH", tmp_path / "extraction_log.jsonl")
    out = tmp_path / "norms_core.json"
    # no --prompt-version: the run takes the default, as B74 does
    argv = ["--nodes", ",".join(UNITS), "--dump", str(dump_path), "--out", str(out)]
    return cli, argv, out, generator, judge


def _run(tmp_path, monkeypatch):
    cli, argv, out, generator, judge = _prepare(tmp_path, monkeypatch)
    assert cli.main(argv) == 0
    store = BuildRecordStore(tmp_path)
    (execution,) = store.read(store.resolve("core"))["executions"]
    return json.loads(out.read_text(encoding="utf-8")), execution, generator, judge


def _judge_input(judge, unit, action):
    (user,) = [u for _s, u in judge.calls if f"Source unit node id: {unit}\n" in u and f'"action": "{action}"' in u]
    return user


def _id(unit, n):
    return f"norm:{unit}:n{n}"


def test_the_v4_run_records_v4_on_every_norm_and_both_v4_hashes(tmp_path, monkeypatch):
    payload, execution, generator, judge = _run(tmp_path, monkeypatch)
    sha = {kind: hashlib.sha256((ROOT / "prompts" / kind / "v4.md").read_bytes()).hexdigest()
           for kind in ("extract_norms", "judge_norms")}
    assert payload["build"]["prompt_version"] == "v4"
    assert execution["config"]["prompt_version"] == "v4"
    assert execution["prompt_sha256"] == {"generator": sha["extract_norms"], "judge": sha["judge_norms"]}
    assert len(payload["norms"]) == 12
    assert {n["extractor_prompt_version"] for n in payload["norms"]} == {"v4"}
    assert {r["prompt_version"] for r in payload["judge_runs"]} == {"v4"}
    assert all(s.startswith("# extract_norms system prompt, version v4") for s, _u in generator.calls)
    assert all(s.startswith("# judge_norms system prompt, version v4") for s, _u in judge.calls)
    assert payload["stats"]["verdicts"] == {"accepted": 10, "rejected": 1, "needs_human_review": 1}


def test_the_article_12_1_and_14_4_paragraph_norms_carry_the_provider_through_point_a(tmp_path, monkeypatch):
    payload, _execution, _g, _j = _run(tmp_path, monkeypatch)
    by_id = {n["norm_id"]: n for n in payload["norms"]}
    for norm_id in (_id(U12, 1), _id(U14, 1)):
        norm = by_id[norm_id]
        assert (norm["actor_explicit"], norm["actor_inferred"], norm["actor_inference_source_node_id"]) == (
            None, "provider", POINT_A), norm_id
        assert norm["judge_verdict"] == "accepted"
    assert by_id[_id(U12, 1)]["action"] == "technically allow for"


def test_the_judge_reads_point_a_with_article_16_1_and_its_chapeau(tmp_path, monkeypatch):
    _payload, _execution, _g, judge = _run(tmp_path, monkeypatch)
    nodes = _nodes()
    assert nodes[ART16_P1]["text"].startswith("Providers of high-risk AI systems shall:")
    expected = (
        f"Actor-inference source: {POINT_A} (Point)\n"
        f"Verbatim text of the actor-inference source:\n[{POINT_A}] {nodes[POINT_A]['text']}\n"
        f"Verbatim text of the paragraph that holds it:\n[{ART16_P1}] {nodes[ART16_P1]['text']}\n\n"
        "Candidate norm (JSON):"
    )
    for unit, action in ((U12, "technically allow for"), (U14, "be provided")):
        user = _judge_input(judge, unit, action)
        assert expected in user, unit
        assert "target_system_category" not in user


def test_a_container_a_paragraph_and_the_unit_itself_reach_the_judge_as_under_v3(tmp_path, monkeypatch):
    _payload, _execution, _g, judge = _run(tmp_path, monkeypatch)
    nodes = _nodes()
    # Article 16 has one top-level unit with text, its paragraph 1 (the data)
    assert [i for i in nodes if i.startswith(ART16 + ":paragraph-") and i.count(":") == 2] == [ART16_P1]
    body = f"[{ART16_P1}] {nodes[ART16_P1]['text']}"
    container = _judge_input(judge, U14, "provide")
    assert (f"Actor-inference source: {ART16} (Article)\nVerbatim text of the actor-inference source:\n"
            f"{body}\n\nCandidate norm (JSON):") in container
    paragraph = _judge_input(judge, U17, "include")
    assert (f"Actor-inference source: {ART16_P1} (Paragraph)\nVerbatim text of the actor-inference source:\n"
            f"{body}\n\nCandidate norm (JSON):") in paragraph
    itself = _judge_input(judge, U14D, "decide")
    assert f"Actor-inference source: {U14D}, the source unit above.\n\nCandidate norm (JSON):" in itself
    for user in (container, paragraph, itself):
        assert "paragraph that holds it" not in user


def test_the_build_record_lists_the_unserved_norms_and_places_every_norm_in_one_group(tmp_path, monkeypatch):
    _payload, execution, _g, _j = _run(tmp_path, monkeypatch)
    counts = execution["counts"]
    # accepted, Articles 8 to 15, not served to the provider: the Commission, the
    # system as written actor, and the oversight person's permission
    assert counts["section_2_not_served_to_provider"] == {
        "count": 3, "norm_ids": [_id(U11, 1), _id(U12, 2), _id(U14D, 1)]}
    audit = counts["section_2_actor_audit"]
    assert audit["rule_applied"] == {"count": 2, "norm_ids": [_id(U12, 1), _id(U14, 1)]}
    assert audit["written_party"] == {"count": 3, "norms": [
        {"norm_id": _id(U11, 1), "label": "commission"},
        {"norm_id": _id(U11, 2), "label": "notified_body"},
        {"norm_id": _id(U12, 2), "label": "unresolved", "phrase": "high-risk AI systems"}]}
    assert audit["outside_the_rule"] == {"count": 1, "norms": [
        {"norm_id": _id(U14D, 1), "actor_inferred": "unspecified_needs_review", "deontic_type": "permission"}]}
    assert audit["against_the_representation"] == {"count": 3, "norms": [
        {"norm_id": _id(U14, 2), "reason": "provider inferred with another source: eu-ai-act:article-16"},
        {"norm_id": _id(U14, 3), "reason": "both actor slots set"},
        {"norm_id": _id(U14D, 2), "reason": "both actor slots empty"}]}
    # the scripted norms of Articles 8 to 15: two of 11(1), two of 12(1), three of
    # 14(4), two of 14(4)(d)
    assert audit["sum"] == audit["norms_of_section_2"] == 9


def test_the_build_record_lists_the_point_a_norm_outside_the_range_and_not_the_point_c_one(tmp_path, monkeypatch):
    _payload, execution, _g, _j = _run(tmp_path, monkeypatch)
    assert execution["counts"]["point_a_source_outside_section_2"] == {"count": 1, "norm_ids": [_id(U17, 1)]}


def test_the_command_prints_the_two_checks(tmp_path, monkeypatch, capsys):
    _run(tmp_path, monkeypatch)
    printed = capsys.readouterr().out
    assert ("Articles 8 to 15, actor audit of 9 norms: rule applied 2, written party 3, outside the rule 1, "
            "against the representation 3 (sum 9)\n") in printed
    assert f"  against the representation: {_id(U14D, 2)} (both actor slots empty)\n" in printed
    assert f"Articles 8 to 15, accepted norms the provider is not served: 3\n  {_id(U11, 1)}\n" in printed


def test_a_resumed_run_audits_the_inherited_groups_too(tmp_path, monkeypatch):
    """Review Focus 1: B74 stopped by an overload and continued with --resume."""
    from tere4ai.extract_norms.model_clients import ProviderUnavailable

    cli, argv, _out, _g, _j = _prepare(tmp_path, monkeypatch)
    inner = cli.extract_norms

    def stop_on_article_17(dump, node_ids, generator, judge, prompt_version="v4"):
        if node_ids[0] == U17:
            raise ProviderUnavailable(6, "HTTP 529")
        return inner(dump, node_ids, generator, judge, prompt_version=prompt_version)

    monkeypatch.setattr(cli, "extract_norms", stop_on_article_17)
    assert cli.main(argv) == 3
    monkeypatch.setattr(cli, "extract_norms", inner)
    assert cli.main([*argv, "--resume"]) == 0
    store = BuildRecordStore(tmp_path)
    _first, resumed = store.read(store.resolve("core"))["executions"]
    assert resumed["inherited_keys"] == [U11, U12, U14, U14D]
    assert resumed["counts"]["section_2_not_served_to_provider"]["count"] == 3
    assert resumed["counts"]["section_2_actor_audit"]["norms_of_section_2"] == 9
    assert resumed["counts"]["point_a_source_outside_section_2"]["norm_ids"] == [_id(U17, 1)]


def test_the_provider_is_served_article_12_1_by_get_applicable_requirements(tmp_path, monkeypatch):
    """A3, the tool."""
    from tere4ai.mcp_server.requirements import get_applicable_requirements

    payload, _execution, _g, _j = _run(tmp_path, monkeypatch)
    dump = json.loads((tmp_path / "layer1.json").read_text(encoding="utf-8"))

    def article_12(actor):
        answer = get_applicable_requirements({"risk_category": "high_risk"}, payload, dump, actor=actor)["answer"]
        return {e["norm_id"]: e for e in answer["requirements_by_article"].get("article-12", [])}

    provider = article_12("provider")
    assert list(provider) == [_id(U12, 1)]
    assert (provider[_id(U12, 1)]["actor"], provider[_id(U12, 1)]["actor_source"]) == ("provider", "inferred")
    everyone = article_12(None)
    assert set(everyone) == {_id(U12, 1), _id(U12, 2)}
    assert (everyone[_id(U12, 1)]["actor"], everyone[_id(U12, 1)]["actor_source"]) == ("provider", "inferred")
    assert _id(U12, 1) not in article_12("deployer")


def test_the_facade_serves_article_12_1_to_the_provider_and_not_to_the_deployer(tmp_path, monkeypatch):
    """A3 through the facade the dashboard reads (B142 ruling R1; this plan R19)."""
    import tere4ai.http_facade.app as facade

    _run(tmp_path, monkeypatch)
    with TestClient(facade.create_app(tmp_path)) as client:
        def served(actor):
            body = {"classification": {"risk_category": "high_risk"}, **({"actor": actor} if actor else {})}
            response = client.post("/api/requirements", json=body)
            assert response.status_code == 200, response.text
            return {e["norm_id"]: e for e in response.json()["answer"]["requirements_by_article"].get("article-12", [])}

        provider = served("provider")
        assert list(provider) == [_id(U12, 1)]
        assert provider[_id(U12, 1)]["actor_source"] == "inferred"
        assert set(served(None)) == {_id(U12, 1), _id(U12, 2)}
        assert _id(U12, 1) not in served("deployer")


def test_the_reporting_effects_of_d_g76_8_hold_on_the_mock_run(tmp_path, monkeypatch):
    """The canonicalization resolves a covered norm to provider; the system
    as written actor stays unresolved under its phrase."""
    from tere4ai.canonicalize.canonicalizer import canonicalize_norms

    payload, _execution, _g, _j = _run(tmp_path, monkeypatch)
    canonical = canonicalize_norms(payload)
    by_id = {n["norm_id"]: n for n in canonical["norms"]}
    assert by_id[_id(U12, 1)]["actor_canonical"] == "provider"
    assert "actor_canonical" not in by_id[_id(U12, 2)]
    assert canonical["canonicalization"]["actors_unresolved"]["high-risk AI systems"] == 1

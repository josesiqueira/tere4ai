"""B163 (DEC-28, spec G D-G86; the brief's Section 5 and acceptance A9): the
alignment command at its default, align_hleg v2 and judge_alignment v2, with
scripted models (no network, no keys) over five accepted norms of Articles
9(1), 12(1), 50(1) and 50(2) and one rejected norm, their source texts read
from a copy of the tracked layer1.json, then the E1 sheet drawn from its
output. The scripted replies stand for a model; what a real model does
under v2 is measured by B74, not here."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")

A9, A12, A50_1, A50_2 = (f"eu-ai-act:article-{a}:paragraph-{p}" for a, p in ((9, 1), (12, 1), (50, 1), (50, 2)))
POINT_A = "eu-ai-act:article-16:paragraph-1:point-a"
AGENCY = "hleg:human-agency-and-oversight"
ROBUSTNESS = "hleg:technical-robustness-and-safety"
TRANSPARENCY = "hleg:transparency"
PRIVACY = "hleg:privacy-and-data-governance"
DIVERSITY = "hleg:diversity-non-discrimination-and-fairness"
SOCIETAL = "hleg:societal-and-environmental-well-being"
ACCOUNTABILITY = "hleg:accountability"
N9, N12, N50, N50B, N50C, N50D = (f"norm:{A9}:n1", f"norm:{A12}:n1", f"norm:{A50_1}:n1", f"norm:{A50_1}:n2",
                                  f"norm:{A50_2}:n1", f"norm:{A50_2}:n2")
SCORES = {"semantic_similarity": 0.8, "normative_relevance": 0.9, "operational_utility": 0.7,
          "evidence_strength": 0.85, "judge_confidence": 0.9}
ZERO = dict.fromkeys(SCORES, 0.0)
# the mechanical gate's hash at tere4ai2 ad86369: the gate is not changed (CHANGE8)
GATE_SHA256 = "0cd96693108bc197ce2670f10ab146256bf783751aa0522789941944854555ff"


def _norm(norm_id, unit, span, action, obj, explicit=None, inferred=None, source=None, verdict="accepted",
          conditions=()):
    """A norm in norms schema version 2's names (B145)."""
    return {"norm_id": norm_id, "layer": 2, "type": "NormativeStatement", "source_node_id": unit,
            "source_span_id": span, "deontic_type": "obligation", "modal": "shall",
            "addressee_explicit": explicit, "addressee_inferred": inferred,
            "addressee_inference_source_node_id": source, "action": action, "object": obj,
            "conditions": list(conditions), "exceptions": [], "lifecycle_phase_ids": [],
            "judge_verdict": verdict, "review_status": "accepted" if verdict == "accepted" else "needs_review"}


NORMS = [
    _norm(N9, A9, "span:009.001", "establish, implement, document and maintain", "a risk management system",
          inferred="provider", source=POINT_A, conditions=["in relation to high-risk AI systems"]),
    _norm(N12, A12, "span:012.001", "technically allow for", "the automatic recording of events (logs)",
          inferred="provider", source=POINT_A, conditions=["over the lifetime of the system"]),
    _norm(N50, A50_1, "span:050.001", "ensure", "that the natural persons concerned are informed",
          explicit="providers"),
    _norm(N50B, A50_1, "span:050.001", "ensure", "that the obligation does not apply to authorised systems",
          explicit="providers"),
    _norm(N50C, A50_2, "span:050.002", "ensure", "that the outputs of the AI system are marked",
          explicit="providers"),
    _norm(N50D, A50_2, "span:050.002", "ensure", "that their technical solutions are effective",
          explicit="providers", verdict="rejected"),
]


def _c(target, relation, source_quote, target_quote, rationale):
    return {"target_id": target, "relation_type": relation, "source_quote": source_quote,
            "target_quote": target_quote, "rationale": rationale}


# Every quote below is in layer1.json's unit text or in the description
# build_hleg_nodes gives (checked by the plan writer at ad86369), except
# CBAD's source quote, which the mechanical gate must reject.
C9 = _c(ROBUSTNESS, "partially_operationalizes", "A risk management system shall be established",
        "developed with a preventative approach to risks", "A risk management system is a preventative approach.")
C12A = _c(TRANSPARENCY, "related_to", "automatic recording of events (logs)", "to allow for traceability",
          "Recorded events allow traceability.")
C12B = _c(TRANSPARENCY, "supports", "over the lifetime of the system",
          "Traceability facilitates auditability as well as explainability", "Lifetime records help traceability.")
C50A = _c(TRANSPARENCY, "directly_operationalizes", "are informed that they are interacting with an AI system",
          "AI systems should not represent themselves as humans to users", "Informed persons know it is no human.")
C50B = _c(AGENCY, "supports", "the natural persons concerned are informed", "allow for human oversight",
          "Informed persons can oversee.")
C50C = _c(ACCOUNTABILITY, "supports", "unless this is obvious from the point of view of a natural person",
          "Auditability entails the enablement of the assessment of algorithms, data and design processes",
          "An exemption bears on assessment.")
C50D = _c(SOCIETAL, "related_to", "the circumstances and the context of use",
          "Sustainability and ecological responsibility of AI systems should be encouraged", "Context relates.")
CBAD = _c(ROBUSTNESS, "supports", "this fragment is not in Article 50", "developed with a preventative approach to risks",
          "A quote the norm does not hold.")

GENERATOR_SCRIPT = {
    f"Norm id: {N9}\n": {"alignments": [C9]},  # a good candidate
    f"Norm id: {N12}\n": {"alignments": [C12A, C12B]},  # two against one requirement
    f"Norm id: {N50}\n": {"alignments": [C50A, C50B, C50C, C50D]},  # four, cut to three
    f"Norm id: {N50B}\n": {"alignments": [CBAD]},  # a quote the check rejects
    f"Norm id: {N50C}\n": {"alignments": []},  # zero alignments
}


def _key(candidate):
    return f'"source_quote": "{candidate["source_quote"]}"'


def _reply(verdict, corrected=None, rationale="scripted"):
    return json.dumps({"verdict": verdict, "corrected_relation_type": corrected, "scores": SCORES,
                       "rationale": rationale})


JUDGE_SCRIPT = {
    _key(C9): _reply("accepted"),
    _key(C12A): _reply("accepted", "supports", "Recording supports traceability."),  # a correction
    _key(C12B): _reply("accepted"),
    _key(C50A): _reply("accepted", "no_clear_relation", "Unclear."),  # CHANGE3's guard
    _key(C50B): _reply("needs_human_review", "no_clear_relation", "Ambiguous."),  # CHANGE3's guard
    _key(C50C): _reply("rejected", "no_clear_relation", "No relation."),  # kept as given
}


def _guard(verdict, rationale):
    return ("judge response unusable, defaulting to human review: verdict "
            f"{verdict!r} with corrected_relation_type no_clear_relation, which only a rejection may "
            f"carry (judge_alignment checks 3 and 4); the judge's rationale: {rationale}")


# the seven requirements in the order the spread is stored and printed, written
# out here so the test does not take its expectation from the code it checks
HLEG_ORDER = [AGENCY, ROBUSTNESS, PRIVACY, TRANSPARENCY, DIVERSITY, SOCIETAL, ACCOUNTABILITY]


def test_the_hleg_nodes_come_in_the_order_the_spread_is_stored():
    assert [n["id"] for n in build_hleg_nodes(load_pair())] == HLEG_ORDER


def _counts(**values):
    return {i: values.get(i, 0) for i in HLEG_ORDER}


EXPECTED_STATS = {
    "norms_total": 6,
    "norms_skipped_not_accepted": 1,
    "norms_failed": [],
    "zero_alignment_norms": 1,
    "candidates": 7,
    "mechanical_rejects": [{"norm_id": N50B, "target_id": ROBUSTNESS, "source_quote_found": False,
                            "target_quote_found": True}],
    "invalid_candidates": [{"norm_id": N50, "reason": "generator proposed 4 candidates; kept the first 3"}],
    "invalid_assertions": [],
    "verdicts": {"accepted": 3, "rejected": 1, "needs_human_review": 2},
    "assertions_by_requirement": _counts(**{AGENCY: 1, ROBUSTNESS: 1, TRANSPARENCY: 3, ACCOUNTABILITY: 1}),
    "accepted_by_requirement": _counts(**{ROBUSTNESS: 1, TRANSPARENCY: 2}),
    "pairs_by_requirement": _counts(**{AGENCY: 1, ROBUSTNESS: 1, TRANSPARENCY: 2, ACCOUNTABILITY: 1}),
    "accepted_pairs_by_requirement": _counts(**{ROBUSTNESS: 1, TRANSPARENCY: 1}),
}


def _text(kind, version="v2"):
    return (ROOT / "prompts" / kind / f"{version}.md").read_text(encoding="utf-8")


def _sha(kind, version="v2"):
    return hashlib.sha256((ROOT / "prompts" / kind / f"{version}.md").read_bytes()).hexdigest()


def _nodes():
    return {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"] if isinstance(n, dict)}


def _prepare(tmp_path, monkeypatch):
    """The scripted models on the command; the dump copied, with the two HLEG
    source files listed (R22: the tracked layer1.json predates B143, and the
    command refuses a dump that does not list the HLEG text, D-G75 (8))."""
    import tere4ai.align_hleg.__main__ as cli
    from tere4ai.align_hleg import pipeline
    from tere4ai.extract_norms.model_clients import FakeClient

    class ScriptedModel(FakeClient):
        sampling = temperature = "provider default (rejected by the model)"
        effort = "high"
        json_mode = "sent"
        usage: dict = {}

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "high", "judge_effort": "high"}

    pair = load_pair()
    dump = json.loads(LAYER1.read_text(encoding="utf-8"))
    dump["nodes"] += [
        {"id": f"srcfile:{TEXT_FILE}", "layer": 0, "type": "SourceFile", "file": TEXT_FILE, "sha256": pair.text_sha256},
        {"id": f"srcfile:{RECORD_FILE}", "layer": 0, "type": "SourceFile", "file": RECORD_FILE,
         "sha256": pair.record_sha256},
    ]
    dump_path = tmp_path / "layer1.json"
    dump_path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    norms_path = tmp_path / "norms_core.json"
    norms_path.write_text(json.dumps({"build": {"build_id": "build-b163-mock"}, "norms_schema_version": 2,
                                      "norms": NORMS, "judge_runs": []}), encoding="utf-8")
    generator = ScriptedModel({k: json.dumps(v) for k, v in GENERATOR_SCRIPT.items()}, model="g")
    judge = ScriptedModel(JUDGE_SCRIPT, model="j")
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: generator)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: judge)
    monkeypatch.setattr(pipeline, "DEFAULT_LOG_PATH", tmp_path / "alignment_log.jsonl")
    out = tmp_path / "alignments_core.json"
    # no --prompt-version: the run takes the default, as B74 does
    argv = ["--norms", str(norms_path), "--dump", str(dump_path), "--out", str(out)]
    return cli, argv, out, generator, judge


def _run(tmp_path, monkeypatch, *extra):
    cli, argv, out, generator, judge = _prepare(tmp_path, monkeypatch)
    assert cli.main([*argv, *extra]) == 0
    store = BuildRecordStore(tmp_path)
    executions = store.read(store.resolve("core"))["executions"]
    return json.loads(out.read_text(encoding="utf-8")), executions[-1], generator, judge


def _by_id(payload):
    return {a["id"]: a for a in payload["assertions"]}


def _aid(norm_id, target, index):
    return f"align:{norm_id.removeprefix('norm:')}:{target.removeprefix('hleg:')}:{index}"


def test_the_run_records_v2_and_both_v2_hashes_everywhere(tmp_path, monkeypatch):
    payload, execution, generator, judge = _run(tmp_path, monkeypatch)
    assert execution["config"]["prompt_version"] == "v2"
    assert execution["prompt_sha256"] == {"generator": _sha("align_hleg"), "judge": _sha("judge_alignment")}
    assert payload["build"]["alignment_prompt_version"] == "v2"
    assert payload["build"]["hleg_text_sha256"] == load_pair().text_sha256
    (mapping_run,) = payload["mapping_runs"]
    assert (mapping_run["prompt_version"], mapping_run["prompt_sha256"]) == ("v2", _sha("align_hleg"))
    model_runs = [r for r in payload["judge_runs"] if r["judge_model"] == "j"]
    (gate_run,) = [r for r in payload["judge_runs"] if r["judge_model"] == "mechanical:quote_check"]
    assert len(model_runs) == 6
    assert {(r["prompt_version"], r["prompt_sha256"]) for r in model_runs} == {("v2", _sha("judge_alignment"))}
    assert (gate_run["prompt_version"], gate_run["prompt_sha256"]) == ("v2", GATE_SHA256)
    log = [json.loads(line) for line in (tmp_path / "alignment_log.jsonl").read_text().splitlines()]
    assert sorted(line["direction"] for line in log) == ["generator"] * 5 + ["judge"] * 6 + ["mechanical"]
    assert {line["prompt_version"] for line in log} == {"v2"}
    assert {line["prompt_sha256"] for line in log if line["direction"] == "generator"} == {_sha("align_hleg")}
    assert {line["prompt_sha256"] for line in log if line["direction"] == "judge"} == {_sha("judge_alignment")}
    assert [s for s, _u in generator.calls] == [_text("align_hleg")] * 5
    assert [s for s, _u in judge.calls] == [_text("judge_alignment")] * 6
    definitions = (ROOT / "prompts" / "relation_type" / "definitions.md").read_text(encoding="utf-8")
    assert all(definitions in s for s, _u in judge.calls)


def test_the_generator_reads_addressee_and_the_judge_reads_what_it_read_before(tmp_path, monkeypatch):
    """A6 end to end; the judge's user message is unchanged in form."""
    _payload, _ex, generator, judge = _run(tmp_path, monkeypatch)
    nodes, hleg = _nodes(), build_hleg_nodes(load_pair())
    expected = "\n".join([
        f"Norm id: {N9}", "Deontic type: obligation", "Addressee: provider",
        "Action: establish, implement, document and maintain", "Object: a risk management system",
        'Conditions: ["in relation to high-risk AI systems"]', "Exceptions: []",
        "Verbatim legal source text of the norm:", nodes[A9]["text"], "",
        "The seven HLEG requirements (closed set, quote target_quote from the description):",
        *[line for h in hleg for line in (f"--- {h['id']} ({h['name']}) ---", h["description"])],
    ])
    (n9,) = [u for _s, u in generator.calls if u.startswith(f"Norm id: {N9}\n")]
    assert n9 == expected
    (n50,) = [u for _s, u in generator.calls if u.startswith(f"Norm id: {N50}\n")]
    assert "\nAddressee: providers\n" in n50 and "\nActor:" not in n50
    robustness = {h["id"]: h for h in hleg}[ROBUSTNESS]
    (c9,) = [u for _s, u in judge.calls if _key(C9) in u]
    assert c9 == (f"Norm id: {N9}\nVerbatim legal source text of the norm:\n{nodes[A9]['text']}\n\n"
                  f"Target HLEG requirement: {ROBUSTNESS} (Technical robustness and safety)\n"
                  f"HLEG requirement description:\n{robustness['description']}\n\n"
                  f"Candidate alignment (JSON):\n{json.dumps(C9, ensure_ascii=False, indent=1)}")


def test_the_stats_count_the_spread_and_the_repeated_pair_once(tmp_path, monkeypatch):
    """A7, A13: the stats as found."""
    payload, execution, _g, _j = _run(tmp_path, monkeypatch)
    assert payload["stats"] == EXPECTED_STATS
    assert execution["counts"]["verdicts"] == EXPECTED_STATS["verdicts"]
    assert not any(key in execution["counts"] for key in EXPECTED_STATS if key.endswith("_by_requirement"))


def test_the_assertions_keep_the_claim_and_take_the_guard(tmp_path, monkeypatch):
    """A8, A12 end to end."""
    from jsonschema import Draft202012Validator

    payload, _ex, _g, _j = _run(tmp_path, monkeypatch)
    validator = Draft202012Validator(json.loads(
        (ROOT / "schema" / "json_schemas" / "alignments.schema.json").read_text(encoding="utf-8")))
    by_id = _by_id(payload)
    assert len(by_id) == 6
    for assertion in by_id.values():
        validator.validate(assertion)
    expected = {
        _aid(N9, ROBUSTNESS, 1): ("partially_operationalizes", "partially_operationalizes", "accepted", "scripted"),
        _aid(N12, TRANSPARENCY, 1): ("supports", "related_to", "accepted", "Recording supports traceability."),
        _aid(N12, TRANSPARENCY, 2): ("supports", "supports", "accepted", "scripted"),
        _aid(N50, TRANSPARENCY, 1): ("directly_operationalizes", "directly_operationalizes", "needs_human_review",
                                     _guard("accepted", "Unclear.")),
        _aid(N50, AGENCY, 2): ("supports", "supports", "needs_human_review", _guard("needs_human_review", "Ambiguous.")),
        _aid(N50, ACCOUNTABILITY, 3): ("no_clear_relation", "supports", "rejected", "No relation."),
    }
    for assertion_id, (relation, proposed, verdict, rationale) in expected.items():
        a = by_id[assertion_id]
        assert (a["relation_type"], a["proposed_relation_type"], a["judge_verdict"], a["rationale"]) == (
            relation, proposed, verdict, rationale), assertion_id
    assert by_id[_aid(N12, TRANSPARENCY, 1)]["generator_rationale"] == C12A["rationale"]
    assert by_id[_aid(N50, TRANSPARENCY, 1)]["scores"] == ZERO


def test_the_command_prints_the_summary_and_the_spread(tmp_path, monkeypatch, capsys):
    _run(tmp_path, monkeypatch)
    printed = capsys.readouterr().out
    assert "norms: 6 total, 1 skipped (not accepted), 1 with zero alignments\n" in printed
    assert "candidates: 7, verdicts: {'accepted': 3, 'rejected': 1, 'needs_human_review': 2}\n" in printed
    assert "mechanical quote-check rejects: 1\n" in printed
    assert "invalid candidates: 1, invalid assertions dropped: 0\n" in printed
    spread = [EXPECTED_STATS[key] for key in ("assertions_by_requirement", "accepted_by_requirement",
                                              "pairs_by_requirement", "accepted_pairs_by_requirement")]
    lines = ["per requirement: assertions, accepted, norm and requirement pairs, accepted pairs"] + [
        f"  {i}: " + ", ".join(str(counts[i]) for counts in spread) for i in spread[0]]
    assert "\n".join(lines) + "\n" in printed
    assert "  hleg:transparency: 3, 2, 2, 1\n" in printed


def test_a_run_stopped_after_its_first_batch_resumes_with_v2_and_counts_the_same(tmp_path, monkeypatch):
    """Review Focus 1: the inherited batch's counts are summed with the rest."""
    from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable

    cli, argv, out, _g, _j = _prepare(tmp_path, monkeypatch)
    inner = cli.align_norms

    def stop_on_the_second_batch(chunk, hleg, generator, judge, prompt_version="unset", build_id="adhoc", max_in_flight=1):
        if chunk[0]["norm_id"] == N50:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id, max_in_flight=max_in_flight)

    monkeypatch.setattr(cli, "align_norms", stop_on_the_second_batch)
    assert cli.main([*argv, "--batch-size", "2"]) == 3
    monkeypatch.setattr(cli, "align_norms", inner)
    assert cli.main([*argv, "--batch-size", "2", "--resume"]) == 0
    store = BuildRecordStore(tmp_path)
    _first, resumed = store.read(store.resolve("core"))["executions"]
    assert resumed["inherited_keys"] == [f"batch:0:{N9}"] and resumed["config"]["prompt_version"] == "v2"
    assert json.loads(out.read_text(encoding="utf-8"))["stats"] == EXPECTED_STATS


def test_a_resume_over_a_checkpoint_without_the_spread_counts_it_from_the_assertions(tmp_path, monkeypatch):
    """B163 final review F6: batches written before B163 lack the four spread dicts; the stats still equal
    the counts recomputed from the merged assertions (and so an uninterrupted run's)."""
    from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable

    cli, argv, out, _g, _j = _prepare(tmp_path, monkeypatch)
    inner = cli.align_norms

    def stop_on_the_second_batch(chunk, hleg, generator, judge, prompt_version="unset", build_id="adhoc", max_in_flight=1):
        if chunk[0]["norm_id"] == N50:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        return inner(chunk, hleg, generator, judge, prompt_version=prompt_version, build_id=build_id, max_in_flight=max_in_flight)

    monkeypatch.setattr(cli, "align_norms", stop_on_the_second_batch)
    assert cli.main([*argv, "--batch-size", "2"]) == 3
    checkpoint = out.with_suffix(".checkpoint.jsonl")
    lines = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "the first batch is in the checkpoint"
    spread_keys = ("assertions_by_requirement", "accepted_by_requirement", "pairs_by_requirement",
                   "accepted_pairs_by_requirement")
    for line in lines:
        for key in spread_keys:
            line["result"]["stats"].pop(key)
    checkpoint.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    monkeypatch.setattr(cli, "align_norms", inner)
    assert cli.main([*argv, "--batch-size", "2", "--resume"]) == 0
    stats = json.loads(out.read_text(encoding="utf-8"))["stats"]
    assert stats == EXPECTED_STATS
    assert any(stats["assertions_by_requirement"].values())


def test_a_v1_checkpoint_is_refused_by_a_v2_run(tmp_path, monkeypatch, capsys):
    """Review Focus 2: the command's stale-checkpoint refusal, exit 2."""
    from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable

    cli, argv, _out, generator, _j = _prepare(tmp_path, monkeypatch)
    inner = cli.align_norms

    def stop_on_the_second_batch(chunk, hleg, generator_, judge, prompt_version="unset", build_id="adhoc", max_in_flight=1):
        if chunk[0]["norm_id"] == N50:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        return inner(chunk, hleg, generator_, judge, prompt_version=prompt_version, build_id=build_id, max_in_flight=max_in_flight)

    monkeypatch.setattr(cli, "align_norms", stop_on_the_second_batch)
    assert cli.main([*argv, "--batch-size", "2", "--prompt-version", "v1"]) == 3
    calls = len(generator.calls)
    monkeypatch.setattr(cli, "align_norms", inner)
    assert cli.main([*argv, "--batch-size", "2", "--resume"]) == 2
    assert "used a different config: prompt_version" in capsys.readouterr().err
    assert len(generator.calls) == calls, "refused before any model call"


def _sampling(monkeypatch):
    spec = importlib.util.spec_from_file_location("sample_judge_decisions", ROOT / "scripts" / "sample_judge_decisions.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "sample_judge_decisions", module)
    spec.loader.exec_module(module)
    return module


def test_the_e1_sheet_of_the_v2_run_is_blind_and_shows_what_the_judge_read(tmp_path, monkeypatch):
    """A11 end to end: no correction under Judged content; the claimed type;
    the definitions once; the two texts equal to the judge's message; one
    order by the decision ids' sha256 (R21)."""
    sampling = _sampling(monkeypatch)
    payload, _ex, _g, judge = _run(tmp_path, monkeypatch)
    norms = json.loads((tmp_path / "norms_core.json").read_text(encoding="utf-8"))
    layer1 = json.loads((tmp_path / "layer1.json").read_text(encoding="utf-8"))
    hleg, note = sampling.hleg_nodes_for(payload)
    assert note is None
    sheet = sampling.build_sheet(norms, payload, layer1, total=6, minimum=1, hleg_nodes=hleg)
    ids = [item["decision_id"] for item in sheet["items"]]
    assert len(ids) == 6 and ids == sorted(ids, key=lambda i: hashlib.sha256(i.encode("utf-8")).hexdigest())
    definitions = (ROOT / "prompts" / "relation_type" / "definitions.md").read_text(encoding="utf-8")
    for item in sheet["items"]:
        content = item["judged_content"]
        assert "relation_type" not in content and content["proposed_relation_type"]
        assert item["relation_type_definitions"] == definitions and "texts_notes" not in item
        (user,) = [u for _s, u in judge.calls if f'"source_quote": "{content["source_quote"]}"' in u]
        assert f"Verbatim legal source text of the norm:\n{item['norm_source_text']}\n\n" in user
        assert f"Target HLEG requirement: {item['hleg_requirement']}\nHLEG requirement description:\n" \
               f"{item['hleg_description']}\n\n" in user
    md = sampling.render_sheet_md(sheet)
    assert md.count(definitions.splitlines()[0]) == 1
    corrected = sheet["items"][ids.index(f"judgerun:mapping:{A12}:n1:transparency:c1")]
    assert corrected["judged_content"]["proposed_relation_type"] == "related_to"
    assert corrected["judge_run"]["corrected_relation_type"] == "supports"
    section = md.split(f"{corrected['item_id']}\n", 1)[1].split("## Item ", 1)[0]
    assert corrected["decision_id"] not in md and A12 not in section  # R44
    judged, folded = section.split("<details>", 1)
    assert "- proposed_relation_type: related_to" in judged and "- relation_type:" not in judged
    assert "- corrected_relation_type: supports" in folded

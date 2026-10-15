"""B174 (2026-10-15): every judge prompt states that the legal text it
receives is the AI Act as amended by the Digital Omnibus, in force.

judge_norms v7, judge_alignment v3 and runtime_grounding v3 are their
predecessors plus one paragraph, inserted after the first paragraph; the
generator prompts loaded under the same version (extract_norms v7, align_hleg
v3, generate_backlog v3) are byte-identical to their predecessors apart from
the heading's version line. The new versions are the defaults and the
versions of record; the evidence tool's judge moves to runtime_grounding v3:
on an evidence answer it reads v1's message, its verdict is handled as under
v1, and the answer records no type view.
Scripted models (FakeClient) only: no network, no keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.test_rejudge_messages import A16_PA, A17_P1, A99_P1, _dump

from tere4ai.align_hleg import pipeline as align_pipeline
from tere4ai.align_hleg.relation_types import judge_read_definitions
from tere4ai.extract_norms import pipeline as extract_pipeline
from tere4ai.extract_norms.model_clients import FakeClient
from tere4ai.extract_norms.requirement_type import is_operator_actor, types_for
from tere4ai.extract_norms.scope_first_reading import FIRST_READING_VERSIONS
from tere4ai.judge.runtime_grounding import ground_check
from tere4ai.mcp_server import backlog, evidence
from tere4ai.mcp_server.evidence import evaluate_project_evidence
from tere4ai.rejudge import alignments as rejudge_alignments
from tere4ai.rejudge import norms as rejudge_norms

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"

PARAGRAPH = (
    "The legal text you receive is Regulation (EU) 2024/1689 as amended by\n"
    "Regulation (EU) 2026/1744 (the Digital Omnibus on AI), in force since\n"
    "27 July 2026. Units the amendment inserted or replaced (Article 4a,\n"
    "Article 5(1) points (ba) and (bb), Article 6(1a), Annex XIV and the\n"
    "others) are binding law, not a proposal. Judge the text in front of you\n"
    "as the law in force; never reject or doubt a unit because your own\n"
    "knowledge of the Regulation predates the amendment.\n"
)

JUDGE_PROMPTS = (("judge_norms", "v6", "v7"), ("judge_alignment", "v2", "v3"), ("runtime_grounding", "v2", "v3"))
GENERATOR_PROMPTS = (("extract_norms", "v6", "v7"), ("align_hleg", "v2", "v3"), ("generate_backlog", "v2", "v3"))

SCORES = {"semantic_similarity": 0.9, "normative_relevance": 0.85, "operational_utility": 0.8,
          "evidence_strength": 0.75, "judge_confidence": 0.9}
ACCEPT = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norm."})


def _read(kind: str, version: str) -> str:
    return (ROOT / "prompts" / kind / f"{version}.md").read_text(encoding="utf-8")


def _heading(kind: str, version: str) -> str:
    return f"# {kind} system prompt, version {version}\n"


def _with_new_heading(kind: str, old: str, new: str) -> str:
    text = _read(kind, old)
    assert text.startswith(_heading(kind, old))
    return _heading(kind, new) + text[len(_heading(kind, old)):]


@pytest.mark.parametrize(("kind", "old", "new"), JUDGE_PROMPTS)
def test_each_judge_prompt_is_its_predecessor_plus_the_paragraph(kind, old, new):
    before = _with_new_heading(kind, old, new)
    heading = _heading(kind, new)
    first_paragraph_end = before.index("\n\n", len(heading) + 1) + 2
    assert before[len(heading) + 1:].startswith("You are the ")
    expected = before[:first_paragraph_end] + PARAGRAPH + "\n" + before[first_paragraph_end:]
    text = _read(kind, new)
    assert text == expected
    assert text.count(PARAGRAPH) == 1
    assert PARAGRAPH not in _read(kind, old)


@pytest.mark.parametrize(("kind", "old", "new"), GENERATOR_PROMPTS)
def test_each_paired_generator_prompt_is_byte_identical_to_its_predecessor(kind, old, new):
    assert _read(kind, new) == _with_new_heading(kind, old, new)
    assert PARAGRAPH not in _read(kind, new)


def test_the_paragraph_is_one_text():
    held = []
    for kind, _, new in JUDGE_PROMPTS:
        text = _read(kind, new)
        start = text.index("The legal text you receive is")
        end = text.index("predates the amendment.\n", start) + len("predates the amendment.\n")
        held.append(text[start:end])
    assert held == [PARAGRAPH] * 3
    assert "\u2014" not in PARAGRAPH and "\u2013" not in PARAGRAPH


def test_the_defaults_are_the_new_versions():
    assert extract_pipeline.DEFAULT_PROMPT_VERSION == "v7"
    assert align_pipeline.DEFAULT_PROMPT_VERSION == "v3"
    assert backlog.DEFAULT_PROMPT_VERSION == "v3"
    assert evidence.JUDGE_PROMPT_VERSION == "v3"
    assert evidence.GENERATOR_PROMPT_VERSION == "v1"
    record = (ROOT / "eval" / "config_evaluated.yaml").read_text(encoding="utf-8")
    for line in ("extract_norms: v7", "judge_norms: v7", "align_hleg: v3", "judge_alignment: v3",
                 "evaluate_evidence: v1", "generate_backlog: v3", "runtime_grounding: v3"):
        assert f"  {line}\n" in record, line
    # v7 is read as v6 by every version table, v3 as v2 (each gate below).
    assert extract_pipeline.writes_addressee("v7")
    assert extract_pipeline.candidate_fields("v7") == extract_pipeline.candidate_fields("v6")


def _inference_block(version):
    """The paragraph-of-point gate: a candidate inferred through point (a) of
    Article 16(1), judged on Article 99(1)."""
    dump = _dump()
    nodes = extract_pipeline._index_nodes(dump)
    unit = extract_pipeline.unit_of_norm(dump, {"source_node_id": A99_P1})
    slots = [n for n in extract_pipeline.candidate_fields(version)
             if n.endswith(("_explicit", "_inferred", "_inference_source_node_id"))]
    candidate = {slots[0]: None, slots[1]: "provider", slots[2]: A16_PA}
    return extract_pipeline.judge_inference_block(dump, nodes, unit, candidate, version)


def _set_up_block(version):
    """The set-up gate: Article 17(1), a unit the set-up table covers."""
    nodes = extract_pipeline._index_nodes(_dump())
    return extract_pipeline.judge_set_up_block(nodes, {"node_id": A17_P1}, version)


# Every version gate of the extraction and alignment instruments, each read
# under the new version and under the one it continues (Task 1 review minor 3).
EXTRACTION_GATES = {
    "writes_addressee": extract_pipeline.writes_addressee,
    "candidate_fields": extract_pipeline.candidate_fields,
    "judged_candidate_fields": extract_pipeline.judged_candidate_fields,
    "types_for": types_for,
    "inference text": lambda v: v in extract_pipeline._PROMPTS_WITHOUT_INFERENCE_TEXT,
    "model category": lambda v: v in extract_pipeline._PROMPTS_WITH_MODEL_CATEGORY,
    "paragraph of point": lambda v: v not in extract_pipeline._PROMPTS_WITHOUT_PARAGRAPH_OF_POINT,
    "paragraph of point, the judge's text": _inference_block,
    "lifecycle": lambda v: v in extract_pipeline._PROMPTS_WITH_LIFECYCLE,
    "set-up rows": _set_up_block,
    "scope_first_reading": lambda v: v in FIRST_READING_VERSIONS,
    "requirement_type scope": lambda v: (is_operator_actor("the notified body", None, v),
                                         is_operator_actor(None, "provider", v)),
    "rejudge norms rebuildable": lambda v: v in rejudge_norms.UNREBUILDABLE_PROMPT_VERSIONS,
}
ALIGNMENT_GATES = {
    "actor label": lambda v: v in align_pipeline._PROMPTS_WITH_ACTOR_LABEL,
    "any correction": lambda v: v in align_pipeline._PROMPTS_TAKING_ANY_CORRECTION,
    "judge_read_definitions": judge_read_definitions,
    "rejudge alignments rebuildable": lambda v: v in rejudge_alignments.UNREBUILDABLE_PROMPT_VERSIONS,
}


@pytest.mark.parametrize(("gate", "new", "old"),
                         [(g, "v7", "v6") for g in EXTRACTION_GATES] + [(g, "v3", "v2") for g in ALIGNMENT_GATES])
def test_every_version_gate_reads_the_new_version_as_its_predecessor(gate, new, old):
    function = (EXTRACTION_GATES | ALIGNMENT_GATES)[gate]
    assert function(new) == function(old)
    assert _set_up_block("v6") is not None and _inference_block("v6") is not None


EVIDENCE_NORM = {
    "norm_id": "norm:eu-ai-act:article-9:paragraph-1:n1", "layer": 2, "type": "NormativeStatement",
    "source_node_id": "eu-ai-act:article-9:paragraph-1", "source_span_id": "span:009.001",
    "deontic_type": "obligation", "modal": "shall", "actor_explicit": None, "actor_inferred": "provider",
    "actor_inference_source_node_id": "eu-ai-act:article-16",
    "action": "establish, implement, document and maintain", "object": "a risk management system",
    "target_system_category": "high_risk", "conditions": [], "exceptions": [],
    "extraction_method": "llm_extract_v1", "extractor_model": "fake-generator", "confidence": 0.9,
    "judge_verdict": "accepted", "review_status": "accepted",
}
EVIDENCE = {"artifact_type": "risk_management_plan", "artifact_id": "rmp-001",
            "content": "We maintain a documented risk management system for our high-risk AI service."}
GENERATOR_REPLY = json.dumps({"assessment": "satisfied",
                              "quotes": ["We maintain a documented risk management system"],
                              "gaps": [], "rationale": "The plan names the system."})


# The replies a v3 judge sends: v2's instructions ask for "type_views": [] on
# any answer that is not a backlog; a judge may still send views.
ACCEPT_NO_VIEWS = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norm.",
                              "type_views": []})
ACCEPT_WITH_VIEWS = json.dumps({"verdict": "accepted", "scores": SCORES, "rationale": "Grounded in the cited norm.",
                                "type_views": [{"item": 1, "requirement_type_agrees": False,
                                                "requirement_type": "process"}]})


def _evidence_run(tmp_path, reply=ACCEPT, **kwargs):
    generator = FakeClient({EVIDENCE_NORM["norm_id"]: GENERATOR_REPLY}, model="fake-generator")
    judge = FakeClient({EVIDENCE_NORM["norm_id"]: reply}, model="fake-judge")
    envelope = evaluate_project_evidence(EVIDENCE_NORM, EVIDENCE, generator, judge, graph_version="build-test",
                                         log_path=tmp_path / "runtime_log.jsonl", **kwargs)
    return envelope, judge


def _comparable(envelope):
    answer = {k: v for k, v in envelope["answer"].items() if k != "judge_run_id"}
    return {**{k: v for k, v in envelope.items() if k not in ("answer", "generated_at")}, "answer": answer}


@pytest.mark.parametrize("reply", [ACCEPT_NO_VIEWS, ACCEPT_WITH_VIEWS], ids=["empty views", "views sent"])
def test_the_evidence_judge_under_v3_records_no_type_view(tmp_path, reply):
    v3, v3_judge = _evidence_run(tmp_path, reply)  # the default is v3
    v1, v1_judge = _evidence_run(tmp_path, reply, judge_prompt_version="v1")
    assert PARAGRAPH in v3_judge.calls[0][0] and PARAGRAPH not in v1_judge.calls[0][0]
    assert v3_judge.calls[0][1] == v1_judge.calls[0][1]  # the judge reads the same message
    assert v3["judge_verdict"] == "accepted" and v3["status"] == "satisfied_with_evidence"
    assert _comparable(v3) == _comparable(v1)
    assert "judge_type_views" not in v3["answer"]
    log = [json.loads(line) for line in (tmp_path / "runtime_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["prompt_version"] for e in log if e.get("direction") == "judge"] == ["v3", "v1"]
    # ground_check hands the raw views back; the evidence answer never records them
    judge = FakeClient({EVIDENCE_NORM["norm_id"]: reply}, model="fake-judge")
    check = ground_check(GENERATOR_REPLY, [EVIDENCE_NORM], EVIDENCE["content"], judge, prompt_version="v3",
                         log_path=tmp_path / "ground.jsonl")
    assert check["verdict"] == "accepted" and check["type_views"] == json.loads(reply)["type_views"]
    assert not any("type_view" in key for key in v3["answer"])


@pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")
def test_a_build_judge_at_v7_sends_the_paragraph(tmp_path):
    dump = json.loads(LAYER1.read_text(encoding="utf-8"))
    unit = "eu-ai-act:article-12:paragraph-1"
    names = extract_pipeline.candidate_fields("v7")
    slots = [n for n in names if n.endswith(("_explicit", "_inferred", "_inference_source_node_id"))]
    candidate = {"deontic_type": "obligation", "modal": "shall", slots[0]: None, slots[1]: "provider",
                 slots[2]: "eu-ai-act:article-16:paragraph-1:point-a", "action": "allow",
                 "object": "the automatic recording of events", "conditions": [], "exceptions": [],
                 "requirement_type": "functional"}
    generator = FakeClient({f"Source unit node id: {unit}\n": json.dumps({"norms": [candidate]})}, model="g")
    judge = FakeClient({"Candidate norm (JSON)": ACCEPT}, model="j")
    result = extract_pipeline.extract_norms(dump, [unit], generator, judge, log_path=tmp_path / "log.jsonl")
    assert judge.calls and generator.calls
    assert all(PARAGRAPH in system for system, _ in judge.calls)
    assert all(PARAGRAPH not in system for system, _ in generator.calls)
    assert judge.calls[0][0] == extract_pipeline.load_prompt("judge_norms", "v7")
    assert {run["prompt_version"] for run in result["judge_runs"]} == {"v7"}

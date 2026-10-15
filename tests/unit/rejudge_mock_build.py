"""B173: a published source build of mock data for the rejudge tests, and the
scripted clients and configuration the tests run the command with. No tests
here; FakeClient and scripted clients only, never a paid model call.

The source folder holds what a published build holds: the Task 1 Layer 1
dump as layer1.json, norms and alignments made by the extract_norms and
align_hleg pipelines with FakeClients, a build record (alias
2026-10-14-gpt-fake-high) with its extract_norms and align_hleg executions
and its publication, publications/<chain>.json and ACTIVE_MANIFEST.json.
Four norms, one per source unit, written in the dump's unit order (C, D, B,
A; three groups, Article 16, 17 and 99):

- A (Article 99(1)): accepted, two alignments;
- B (Article 17(1), the unit the set-up table covers): accepted, none;
- C (Article 16(1)): rejected, so never aligned;
- D (Article 16(1)(a)): accepted, one alignment.

The judge messages the source's judges received are kept beside the folder
(source_judge_messages.json in tmp_path, outside the source folder) by norm
id and by assertion id. ScriptedGenerator answers the Layer 3 generator for a
norm the rejudge newly accepts (C, NEW_NORM_CANDIDATES).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tests.unit.test_rejudge_messages import A16, A16_P1, A16_PA, A17_P1, A99_P1, _dump

from tere4ai.align_hleg.__main__ import _attach_source_text
from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.align_hleg.pipeline import align_norms, spread_of
from tere4ai.extract_norms import model_clients
from tere4ai.extract_norms.model_clients import USAGE_KEYS, FakeClient
from tere4ai.extract_norms.pipeline import extract_norms, load_prompt, prompt_sha256
from tere4ai.graph_store.build_chain import sha256_of_file
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.graph_store.publication import write_publication_manifest

SOURCE_NAME = "2026-10-14-gpt-fake-high"
CHAIN_ID = "a1b2c3d4e5f6"
SOURCE_BUILD_ID = "build-test"
GENERATOR_MODEL = "gpt-fake"
SOURCE_JUDGE_MODEL = "gpt-fake-sol"
JUDGE_MODEL = "claude-fake"
NEW_NAME = "2026-10-16-gpt-fake-high-fake"
MESSAGES_FILE = "source_judge_messages.json"
NORMS_FILE = f"norms_{SOURCE_NAME}.json"
ALIGNMENTS_FILE = f"alignments_{SOURCE_NAME}.json"

NORM_A, NORM_B, NORM_C, NORM_D = (f"norm:{unit}:n1" for unit in (A99_P1, A17_P1, A16_P1, A16_PA))
UNIT_OF = {NORM_A: A99_P1, NORM_B: A17_P1, NORM_C: A16_P1, NORM_D: A16_PA}
SOURCE_VERDICTS = {A99_P1: "accepted", A17_P1: "accepted", A16_P1: "rejected", A16_PA: "accepted"}
FILE_ORDER = [NORM_C, NORM_D, NORM_B, NORM_A]
GROUPS = ["eu-ai-act:article-16", "eu-ai-act:article-17", "eu-ai-act:article-99"]

# What the source's generator and judge ran under, as cfg.as_public_dict() writes it.
SOURCE_MODELS = {
    "generator_model": GENERATOR_MODEL, "judge_model": SOURCE_JUDGE_MODEL,
    "generator_effort": "high", "judge_effort": "high",
    "generator_temperature": "N/A", "judge_temperature": "N/A",
    "generator_json_mode": "sent", "model_parameters_sha256": "source-parameters-sha256",
}
# A scripted judge call's usage, and the list prices the tests price it at:
# (1000 * 4.00 + 100 * 20.00) / 1e6 = 0.006 USD per call; a generator call
# at the gpt-fake row (1000 * 10.00 + 100 * 50.00) / 1e6 = 0.015 USD.
INPUT_TOKENS_PER_CALL = 1000
OUTPUT_TOKENS_PER_CALL = 100
USD_PER_JUDGE_CALL = 0.006
USD_PER_GENERATOR_CALL = 0.015


def unit_key(unit: str) -> str:
    """The line that names a source unit in an extraction judge's message."""
    return f"Source unit node id: {unit}\n"


def _usage(calls: int, input_tokens: int, output_tokens: int) -> dict[str, int]:
    usage = dict.fromkeys(USAGE_KEYS, 0)
    usage.update(calls=calls, input_tokens=input_tokens, output_tokens=output_tokens, requests_sent=calls,
                 replies_with_usage=calls)
    return usage


def _v6(**fields: Any) -> dict[str, Any]:
    candidate = {
        "deontic_type": "obligation", "modal": "shall",
        "addressee_explicit": None, "addressee_inferred": None, "addressee_inference_source_node_id": None,
        "action": "keep", "object": "a risk log", "conditions": [], "exceptions": [],
        "requirement_type": "process",
    }
    candidate.update(fields)
    return candidate


GENERATOR_REPLIES = {
    A99_P1: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A16_PA,
                 action="keep and maintain", conditions=["for high-risk AI systems"], exceptions=["unless exempted"])],
    A17_P1: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A17_P1,
                 action="document", object="that system")],
    A16_P1: [_v6(addressee_explicit="providers", action="comply", object="with the requirements")],
    A16_PA: [_v6(addressee_inferred="provider", addressee_inference_source_node_id=A16_PA,
                 action="ensure", object="that their high-risk AI systems are compliant",
                 requirement_type="functional")],
}


def judge_reply(verdict: str, evidence_strength: float = 0.8, rationale: str = "scripted",
                corrected: str | None = None) -> str:
    """A judge reply both judges parse: the extraction judge reads the verdict,
    the scores and the type view, the alignment judge also the correction."""
    return json.dumps({
        "verdict": verdict, "corrected_relation_type": corrected,
        "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9, "operational_utility": 0.8,
                   "evidence_strength": evidence_strength, "judge_confidence": 0.9},
        "rationale": rationale, "requirement_type_agrees": True,
    })


ALIGNMENT_CANDIDATES = {
    NORM_A: [
        {"target_quote": "developed with a preventative approach to risks", "relation_type": "partially_operationalizes",
         "source_quote": "A risk log shall be kept", "rationale": "A kept log serves a preventative approach.",
         "requirement": "Technical robustness and safety"},
        {"target_quote": "to allow for traceability", "relation_type": "related_to",
         "source_quote": "kept and maintained", "rationale": "A log allows traceability.",
         "requirement": "Transparency"},
    ],
    NORM_B: [],
    NORM_D: [
        {"target_quote": "to allow for traceability", "relation_type": "supports",
         "source_quote": "ensure that their high-risk AI systems are compliant",
         "rationale": "Compliance supports traceability.", "requirement": "Transparency"},
    ],
}


# What the Layer 3 generator proposes for C, rejected by the source's judge and
# accepted by the rejudge (Article 16(1): "1. Providers of high-risk AI systems shall:").
NEW_NORM_CANDIDATES = {
    NORM_C: [
        {"target_quote": "to allow for traceability", "relation_type": "supports",
         "source_quote": "Providers of high-risk AI systems", "rationale": "Providers keep systems traceable.",
         "requirement": "Transparency"},
    ],
}


def _alignment_reply(norm_id: str, hleg: list[dict[str, Any]], candidates: dict | None = None) -> str:
    by_name = {h["name"]: h["id"] for h in hleg}
    return json.dumps({"alignments": [
        {"target_id": by_name[c["requirement"]], "relation_type": c["relation_type"],
         "source_quote": c["source_quote"], "target_quote": c["target_quote"], "rationale": c["rationale"]}
        for c in (candidates or ALIGNMENT_CANDIDATES)[norm_id]]})


def make_source_build(tmp_path: Path) -> Path:
    """Write the published source build into tmp_path/SOURCE_NAME and return
    the folder; the source judges' messages go to tmp_path/MESSAGES_FILE."""
    src = tmp_path / SOURCE_NAME
    src.mkdir()
    logs = tmp_path / "source_logs"
    dump = _dump()
    layer1 = src / "layer1.json"
    layer1.write_text(json.dumps(dump, indent=1), encoding="utf-8")

    generator = FakeClient({unit_key(unit): json.dumps({"norms": cands}) for unit, cands in GENERATOR_REPLIES.items()},
                           model=GENERATOR_MODEL)
    judge = FakeClient({unit_key(unit): judge_reply(verdict, 0.85) for unit, verdict in SOURCE_VERDICTS.items()},
                       model=SOURCE_JUDGE_MODEL)
    result = extract_norms(dump, [A99_P1, A17_P1, A16], generator, judge, prompt_version="v6",
                           log_path=logs / "extraction_log.jsonl")
    assert result["stats"]["invalid_norms"] == [] and result["stats"]["nodes_failed"] == []
    assert [n["norm_id"] for n in result["norms"]] == FILE_ORDER
    norm_messages = {norm["norm_id"]: user for norm, (_s, user) in zip(result["norms"], judge.calls, strict=True)}
    norms_payload = {
        "norms_schema_version": 2,
        "build": {
            **dump["build"],
            "extraction_models": dict(SOURCE_MODELS),
            "extraction_sampling": {"generator": "N/A", "judge": "N/A"},
            "extraction_effort": {"generator": "high", "judge": "high"},
            "extraction_temperature": {"generator": "N/A", "judge": "N/A"},
            "extraction_usage": {"generator": _usage(4, 9000, 1200), "judge": _usage(4, 7000, 900)},
            "extracted_at": "2026-10-14T00:21:28+00:00",
            "prompt_version": "v6",
        },
        **result,
    }
    norms_path = src / NORMS_FILE
    norms_path.write_text(json.dumps(norms_payload, ensure_ascii=False, indent=1), encoding="utf-8")

    pair = load_pair()
    hleg = build_hleg_nodes(pair)
    to_align = json.loads(json.dumps(result["norms"]))
    _attach_source_text(to_align, dump)
    align_generator = FakeClient({f"Norm id: {norm_id}\n": _alignment_reply(norm_id, hleg)
                                  for norm_id in ALIGNMENT_CANDIDATES}, model=GENERATOR_MODEL)
    align_judge = FakeClient({f'"source_quote": "{c["source_quote"]}"': judge_reply("accepted")
                              for cands in ALIGNMENT_CANDIDATES.values() for c in cands}, model=SOURCE_JUDGE_MODEL)
    aligned = align_norms(to_align, hleg, align_generator, align_judge, prompt_version="v2",
                          log_path=logs / "alignment_log.jsonl", build_id=SOURCE_BUILD_ID)
    assert len(aligned["assertions"]) == 3 and len(align_judge.calls) == 3
    aligned["stats"].update(spread_of(aligned["assertions"], [node["id"] for node in hleg]))
    assertion_messages = {a["id"]: user for a, (_s, user) in zip(aligned["assertions"], align_judge.calls, strict=True)}
    alignments_payload = {
        "build": {
            **norms_payload["build"], "norms_reference": None,
            "alignment_models": dict(SOURCE_MODELS),
            "alignment_sampling": {"generator": "N/A", "judge": "N/A"},
            "alignment_effort": {"generator": "high", "judge": "high"},
            "alignment_usage": {"generator": _usage(3, 5000, 700), "judge": _usage(3, 4000, 500)},
            "alignment_input_sha256": sha256_of_file(norms_path),
            "hleg_text_sha256": pair.text_sha256, "hleg_derivation_record_sha256": pair.record_sha256,
            "aligned_at": "2026-10-14T00:40:00+00:00", "alignment_prompt_version": "v2",
        },
        **aligned,
    }
    alignments_path = src / ALIGNMENTS_FILE
    alignments_path.write_text(json.dumps(alignments_payload, ensure_ascii=False, indent=1), encoding="utf-8")

    inputs = [{"input_kind": "layer1_dump", "file": "layer1.json", "sha256": sha256_of_file(layer1)},
              {"input_kind": "norms", "file": NORMS_FILE, "sha256": sha256_of_file(norms_path)},
              {"input_kind": "alignments", "file": ALIGNMENTS_FILE, "sha256": sha256_of_file(alignments_path)}]
    store = BuildRecordStore(src)
    record_id = store.create_record(SOURCE_NAME, SOURCE_BUILD_ID, inputs[0]["sha256"])
    sampling = {"generator": "N/A", "judge": "N/A", "generator_temperature": "N/A", "judge_temperature": "N/A",
                "generator_effort": "high", "judge_effort": "high", "generator_json_mode": "sent"}
    for command, steps, step_inputs, output, prompts, usage in (
            ("extract_norms", ["LAYER2_STEP1", "LAYER2_STEP2"], inputs[:1], inputs[1],
             {"generator": prompt_sha256(load_prompt("extract_norms", "v6")),
              "judge": prompt_sha256(load_prompt("judge_norms", "v6"))},
             norms_payload["build"]["extraction_usage"]),
            ("align_hleg", ["LAYER3_STEP1", "LAYER3_STEP2", "LAYER3_STEP3"], inputs[:2], inputs[2],
             {"generator": prompt_sha256(load_prompt("align_hleg", "v2")),
              "judge": prompt_sha256(load_prompt("judge_alignment", "v2"))},
             alignments_payload["build"]["alignment_usage"])):
        run_id = store.start_execution(record_id, command=command, covers_steps=steps, argv=[], inputs=step_inputs,
                                       config={"prompt_version": "v6" if command == "extract_norms" else "v2"},
                                       expected_total=None, work_unit=None, checkpoint_file=None,
                                       models=dict(SOURCE_MODELS), prompt_sha256=prompts, sampling=sampling)
        store.finish_execution(record_id, run_id, status="done", usage=usage,
                               outputs=[{"output_kind": output["input_kind"], "file": output["file"],
                                         "sha256": output["sha256"]}])
    publication = {"chain_id": CHAIN_ID, "build_id": f"{SOURCE_BUILD_ID}+chain-{CHAIN_ID}",
                   "published_at": "2026-10-14T00:50:19+00:00", "gating": {"layer2": "llm", "layer3": "llm"},
                   "label": "llm-gated", "gates": [], "postload_gates": [], "manifests": [], "build_number": 1}
    store.set_publication(record_id, publication)
    write_publication_manifest(src, publication, record_id=record_id, inputs=inputs,
                               files={"layer1_dump": "layer1.json", "norms": NORMS_FILE, "alignments": ALIGNMENTS_FILE})
    (src / "ACTIVE_MANIFEST.json").write_text(
        json.dumps({"chain_id": CHAIN_ID, "activated_at": "2026-10-14T00:50:39+00:00"}, indent=1), encoding="utf-8")
    (tmp_path / MESSAGES_FILE).write_text(
        json.dumps({"norms": norm_messages, "alignments": assertion_messages}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return src


def source_judge_messages(tmp_path: Path) -> dict[str, dict[str, str]]:
    """The user messages the source's judges received: {"norms": {norm id:
    message}, "alignments": {assertion id: message}}."""
    return json.loads((tmp_path / MESSAGES_FILE).read_text(encoding="utf-8"))


def folder_state(folder: Path) -> dict[str, str]:
    """Every file under folder, by relative path, with its sha256."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


class _Cfg:
    """The model configuration the environment names, as the command reads it."""

    def __init__(self, public: dict[str, str]):
        self._public = public
        self.generator_model = public["generator_model"]
        self.judge_model = public["judge_model"]

    def as_public_dict(self) -> dict[str, str]:
        return dict(self._public)


def fake_cfg(**overrides: str) -> _Cfg:
    """The source's generator as declared, judged by claude-fake (effort high,
    temperature 0); overrides change any key of the public dict."""
    public = {**SOURCE_MODELS, "judge_model": JUDGE_MODEL, "judge_effort": "high", "judge_temperature": "0",
              "model_parameters_sha256": "environment-parameters-sha256"}
    public.update(overrides)
    return _Cfg(public)


def prices() -> dict[str, dict[str, Any]]:
    """Price rows as load_model_prices returns them (floats, USD per million tokens)."""
    def row(backend: str, inp: float, out: float) -> dict[str, Any]:
        return {"inference_backend": backend, "currency": "USD", "input": inp, "output": out,
                "batch_input": inp / 2, "batch_output": out / 2,
                "pricing": {"url": "https://example.org/pricing", "read_on": "2026-10-15"}}
    return {JUDGE_MODEL: row("anthropic", 4.0, 20.0), GENERATOR_MODEL: row("openai", 10.0, 50.0)}


class ScriptedJudge:
    """A judge client with the attributes the commands read and a usage record:
    each call adds INPUT_TOKENS_PER_CALL and OUTPUT_TOKENS_PER_CALL. verdicts
    maps a substring of the message to a verdict (the first match wins; else
    accepted); errors maps a substring to an exception raised before any usage
    is counted; on_call(user) runs at the start of every call; corrections maps
    a substring to the corrected_relation_type the reply carries."""

    def __init__(self, verdicts: dict[str, str] | None = None, *, errors: dict[str, BaseException] | None = None,
                 model: str = JUDGE_MODEL, on_call=None, corrections: dict[str, str] | None = None):
        self.model = model
        self.effort = "high"
        self.temperature = "0"
        self.sampling = "0"
        self.json_mode = "N/A"
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self.verdicts = dict(verdicts or {})
        self.errors = dict(errors or {})
        self.on_call = on_call
        self.corrections = dict(corrections or {})
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        if self.on_call is not None:
            self.on_call(user)
        for key, exc in self.errors.items():
            if key in user:
                self.usage["requests_sent"] += 1
                raise exc
        self.calls.append((system, user))
        for key, value in ((("calls", 1), ("input_tokens", INPUT_TOKENS_PER_CALL),
                            ("output_tokens", OUTPUT_TOKENS_PER_CALL), ("requests_sent", 1),
                            ("replies_with_usage", 1))):
            self.usage[key] += value
        verdict = next((v for k, v in self.verdicts.items() if k in user), "accepted")
        corrected = next((v for k, v in self.corrections.items() if k in user), None)
        return judge_reply(verdict, 0.7, rationale=f"scripted by {self.model}", corrected=corrected)


class ScriptedGenerator:
    """A Layer 3 generator client with the attributes the commands read and a
    usage record (INPUT_TOKENS_PER_CALL and OUTPUT_TOKENS_PER_CALL a call, so
    (1000 * 10.00 + 100 * 50.00) / 1e6 = 0.015 USD at the gpt-fake row): it
    answers "Norm id: <id>" with NEW_NORM_CANDIDATES[id] and fails the test on
    any other norm."""

    def __init__(self, candidates: dict | None = None, model: str = GENERATOR_MODEL):
        self.model = model
        self.effort = "high"
        self.temperature = "N/A"
        self.sampling = "N/A"
        self.json_mode = "sent"
        self.usage = dict.fromkeys(USAGE_KEYS, 0)
        self.candidates = dict(candidates if candidates is not None else NEW_NORM_CANDIDATES)
        self.hleg = build_hleg_nodes(load_pair())
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for key, value in ((("calls", 1), ("input_tokens", INPUT_TOKENS_PER_CALL),
                            ("output_tokens", OUTPUT_TOKENS_PER_CALL), ("requests_sent", 1),
                            ("replies_with_usage", 1))):
            self.usage[key] += value
        norm_id = next((n for n in self.candidates if f"Norm id: {n}\n" in user), None)
        if norm_id is None:
            raise AssertionError(f"the generator was called for a norm it has no script for: {user.splitlines()[0]}")
        return _alignment_reply(norm_id, self.hleg, self.candidates)


def no_generator(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("a generator client was built where the command must build none")


def patch_command(monkeypatch, cli, judge: Any, *, cfg: Any = None, price_rows: dict | None = None,
                  generator: Any = None) -> list:
    """Run cli (tere4ai.rejudge.__main__) on scripted clients: the model
    configuration, the price table, the judge; OpenAIGenerator fails the test
    when called unless a generator is given. Returns the retry policies the
    judge was built with."""
    policies: list = []
    monkeypatch.setattr(cli, "load_model_config", lambda: cfg or fake_cfg())
    monkeypatch.setattr(cli, "load_model_prices", lambda: price_rows if price_rows is not None else prices())
    monkeypatch.setattr(cli, "AnthropicJudge", lambda _cfg, **kw: policies.append(kw.get("retry_policy")) or judge)
    monkeypatch.setattr(model_clients, "OpenAIGenerator", no_generator)
    if hasattr(cli, "OpenAIGenerator"):
        monkeypatch.setattr(cli, "OpenAIGenerator",
                            (lambda _cfg, **_kw: generator) if generator is not None else no_generator)
    return policies

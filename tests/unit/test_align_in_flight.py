"""B164 (spec F D-F30 as amended 2026-10-12): the alignment with 8 calls in
flight writes what one call at a time writes from the same replies. Mock data
written here: 12 norms of Article 14 (one not accepted, one without its source
text) and two HLEG requirements; scripted models answer later norms first. The
counts below were read from today's align_norms over this mock data."""

from __future__ import annotations

import json
import threading
import time

from tere4ai.align_hleg import pipeline
from tere4ai.align_hleg.hleg_source import load_pair
from tere4ai.align_hleg.pipeline import align_norms
from tere4ai.extract_norms.model_clients import FakeClient, InferenceBackendUnavailable
from tere4ai.graph_store.build_record import BuildRecordStore
from tere4ai.ingest.hleg_text import RECORD_FILE, TEXT_FILE

HLEG = [{"id": "hleg:human_agency_and_oversight", "name": "Human agency and oversight",
         "description": "AI systems should support human autonomy and decision-making, with human oversight.",
         "source_span": {"span_id": "span:hleg:1"}},
        {"id": "hleg:transparency", "name": "Transparency",
         "description": "The data, system and AI business models should be transparent and traceable.",
         "source_span": {"span_id": "span:hleg:4"}}]
HA, TR = HLEG[0]["id"], HLEG[1]["id"]
TIMES = ("timestamp", "started_at", "completed_at", "aligned_at")


def _norm(i, verdict="accepted", text=True):
    norm = {"norm_id": f"norm:eu-ai-act:article-14:paragraph-{i}:n1", "source_node_id": f"eu-ai-act:article-14:paragraph-{i}",
            "source_span_id": f"span:a14:{i}", "deontic_type": "obligation", "modal": "shall",
            "addressee_explicit": "the provider", "addressee_inferred": None, "addressee_inference_source_node_id": None,
            "action": f"design system {i}", "object": "human oversight measures", "conditions": [], "exceptions": [],
            "judge_verdict": verdict}
    if text:
        norm["source_text"] = f"Mock paragraph {i}: high-risk AI systems shall be designed so that natural persons can oversee them."
    return norm


NORMS = [_norm(i) for i in range(1, 11)] + [_norm(11, verdict="rejected"), _norm(12, text=False)]
ORDER = {norm["norm_id"]: position for position, norm in enumerate(NORMS)}


def _cand(target, rel="supports", sq="natural persons can oversee them"):
    tq = "with human oversight" if target == HA else "transparent and traceable"
    return {"target_id": target, "relation_type": rel, "source_quote": sq, "target_quote": tq, "rationale": "scripted claim"}


def _generator_script():
    special = {2: {"alignments": []},
               3: {"alignments": [_cand(HA), _cand("hleg:invented"), "not an object"]},
               4: {"alignments": [_cand(HA, sq="a sentence the norm never says")]},
               5: {"alignments": [_cand(HA), _cand(TR), _cand(HA, rel="related_to"), _cand(TR)]},
               7: {"alignments": [_cand(TR, rel="no_clear_relation")]}}
    script = {}
    for i in range(1, 11):
        key = f"Norm id: {NORMS[i - 1]['norm_id']}\n"
        if i == 6:
            script[key] = ["not json", "still not json"]
        elif i in special:
            script[key] = json.dumps(special[i])
        else:
            script[key] = json.dumps({"alignments": [_cand(HA, rel="directly_operationalizes"), _cand(TR)]
                                      if i % 2 else [_cand(HA)]})
    return script


def _judged(verdict, corrected=None):
    return json.dumps({"verdict": verdict, "scores": {"semantic_similarity": 0.8, "normative_relevance": 0.8,
                       "operational_utility": 0.7, "evidence_strength": 0.75, "judge_confidence": 0.8},
                       "rationale": f"scripted {verdict}", "corrected_relation_type": corrected})


def _judge_script():
    script = {}
    for i in range(1, 11):
        reply = (_judged("accepted") if i in (1, 3, 5, 9) else _judged("rejected", "no_clear_relation") if i == 8
                 else _judged("needs_human_review") if i == 10 else _judged("accepted", "partially_operationalizes"))
        script[f"Norm id: {NORMS[i - 1]['norm_id']}\n"] = reply
    return script


class _Timed(FakeClient):
    """Replies take longer for earlier norms; counts the calls running at once."""

    sampling = temperature = "N/A"
    effort = "high"
    json_mode = "sent"

    def __init__(self, scripted, model, stop_on=None, delay=0.002):
        super().__init__(scripted, model=model)
        self.stop_on = stop_on
        self.delay = delay
        self._gauge = threading.Lock()
        self.running = self.most = 0

    def complete(self, system, user):
        norm_id = next(n for n in ORDER if f"Norm id: {n}\n" in user)
        with self._gauge:
            self.running += 1
            self.most = max(self.most, self.running)
        if self.delay:
            time.sleep(self.delay * (len(NORMS) - ORDER[norm_id]))
        with self._gauge:
            self.running -= 1
        if norm_id == self.stop_on:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        return super().complete(system, user)

    @property
    def usage(self):
        return {}


def _untimed(value):
    """Every time replaced, and the alignment run's random id (uuid4 in any run)."""
    if isinstance(value, dict):
        return {k: ("T" if k in TIMES else _untimed(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_untimed(v) for v in value]
    if isinstance(value, str) and value.startswith("mappingrun:"):
        return "mappingrun:X"
    return value


def _direct(max_in_flight, tmp_path, delay=0.002):
    generator, judge = _Timed(_generator_script(), "g", delay=delay), _Timed(_judge_script(), "j", delay=delay)
    log = tmp_path / f"alignment_log_{max_in_flight}.jsonl"
    result = align_norms(NORMS, HLEG, generator, judge, prompt_version="v2", log_path=log,
                         build_id="build-mock-b164", max_in_flight=max_in_flight)
    return result, generator, judge, log


def test_eight_calls_in_flight_give_the_result_of_one_at_a_time_byte_for_byte(tmp_path):
    one, g1, j1, log1 = _direct(1, tmp_path)
    eight, g8, j8, log8 = _direct(8, tmp_path)
    assert json.dumps(_untimed(eight), ensure_ascii=False) == json.dumps(_untimed(one), ensure_ascii=False)
    stats = one["stats"]
    assert (stats["norms_total"], stats["norms_skipped_not_accepted"], stats["zero_alignment_norms"],
            stats["candidates"], stats["verdicts"]) == (12, 1, 1, 11, {"accepted": 8, "rejected": 1,
                                                                      "needs_human_review": 1})
    assert [f["norm_id"] for f in stats["norms_failed"]] == [NORMS[5]["norm_id"], NORMS[11]["norm_id"]]
    assert len(stats["mechanical_rejects"]) == 1 and len(stats["invalid_candidates"]) == 4
    assert stats["pairs_by_requirement"] == {HA: 6, TR: 3}
    assert (len(one["assertions"]), len(one["judge_runs"])) == (10, 11)
    assert (len(g1.calls), len(j1.calls)) == (11, 10)
    assert sorted(g8.calls) == sorted(g1.calls) and sorted(j8.calls) == sorted(j1.calls)
    assert g1.most == j1.most == 1 and 1 < g8.most <= 8 and j8.most <= 8
    lines1 = [json.dumps(_untimed(json.loads(line))) for line in log1.read_text().splitlines()]
    lines8 = [json.dumps(_untimed(json.loads(line))) for line in log8.read_text().splitlines()]
    assert len(lines1) == 21 and sorted(lines8) == sorted(lines1)


def test_instant_replies_at_eight_give_the_result_of_one_at_a_time(tmp_path):
    """Mock replies that return at once, so the threads rarely overlap."""
    one, _, _, log1 = _direct(1, tmp_path, delay=0)
    eight, g8, _, log8 = _direct(8, tmp_path, delay=0)
    assert json.dumps(_untimed(eight), ensure_ascii=False) == json.dumps(_untimed(one), ensure_ascii=False)
    assert g8.most <= 8
    lines1 = [json.dumps(_untimed(json.loads(line))) for line in log1.read_text().splitlines()]
    lines8 = [json.dumps(_untimed(json.loads(line))) for line in log8.read_text().splitlines()]
    assert sorted(lines8) == sorted(lines1)


def _command(tmp_path, monkeypatch, max_in_flight, stop_on=None):
    import tere4ai.align_hleg.__main__ as cli

    pair = load_pair()

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "high", "judge_effort": "high"}

    norms_path, layer1 = tmp_path / "norms_mock.json", tmp_path / "layer1.json"
    if not norms_path.exists():
        norms_path.write_text(json.dumps({"build": {"build_id": "build-mock-b164"}, "norms": NORMS}), encoding="utf-8")
        layer1.write_text(json.dumps({"build": {}, "edges": [], "nodes": [
            {"id": f"srcfile:{TEXT_FILE}", "layer": 0, "type": "SourceFile", "file": TEXT_FILE, "sha256": pair.text_sha256},
            {"id": f"srcfile:{RECORD_FILE}", "layer": 0, "type": "SourceFile", "file": RECORD_FILE,
             "sha256": pair.record_sha256}]}), encoding="utf-8")
    generator, judge = _Timed(_generator_script(), "g"), _Timed(_judge_script(), "j", stop_on=stop_on)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: generator)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: judge)
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda pair=None: HLEG)
    monkeypatch.setattr(pipeline, "DEFAULT_LOG_PATH", tmp_path / "alignment_log.jsonl")
    out = tmp_path / "alignments_mock.json"
    argv = ["--norms", str(norms_path), "--dump", str(layer1), "--out", str(out), "--record", "mock",
            "--batch-size", "4", "--max-in-flight", str(max_in_flight)]
    return cli, argv, out, generator


def _executions(tmp_path):
    store = BuildRecordStore(tmp_path)
    return store.read(store.resolve("mock"))["executions"]


def test_the_command_at_eight_writes_the_alignments_file_and_record_of_one_at_a_time(tmp_path, monkeypatch, capsys):
    files, most = {}, {}
    for setting in (1, 8):
        run_dir = tmp_path / f"at-{setting}"
        run_dir.mkdir()
        cli, argv, out, generator = _command(run_dir, monkeypatch, setting)
        assert cli.main(argv) == 0
        printed = capsys.readouterr().out
        assert f"calls in flight: at most {setting} (--max-in-flight)\n" in printed
        assert "per requirement: assertions, accepted, norm and requirement pairs, accepted pairs\n" in printed
        files[setting] = (json.loads(out.read_text(encoding="utf-8")), _executions(run_dir)[0])
        most[setting] = generator.most
    # the setting is applied, not only recorded
    assert most[1] == 1 and 1 < most[8] <= 8
    (payload1, ex1), (payload8, ex8) = files[1], files[8]
    assert json.dumps(_untimed(payload8), ensure_ascii=False) == json.dumps(_untimed(payload1), ensure_ascii=False)
    assert len(payload8["mapping_runs"]) == 3  # batches of 4 over 12 norms
    assert (ex1["config"], ex8["config"]) == ({"prompt_version": "v2", "batch_size": 4, "max_in_flight": 1},
                                              {"prompt_version": "v2", "batch_size": 4, "max_in_flight": 8})
    for key in ("completed_keys", "counts", "work_failures", "status"):
        assert ex8[key] == ex1[key], key


def test_a_run_stopped_at_eight_resumes_at_two(tmp_path, monkeypatch):
    """Review Focus 2: norm 5's judge call stops the second batch (norms 5 to 8), which
    is not checkpointed; a resume at another setting finishes the run."""
    reference = tmp_path / "reference"
    reference.mkdir()
    cli, argv, out, _ = _command(reference, monkeypatch, 1)
    assert cli.main(argv) == 0
    expected = json.dumps(_untimed(json.loads(out.read_text(encoding="utf-8"))), ensure_ascii=False)

    stopped = tmp_path / "stopped"
    stopped.mkdir()
    cli, argv, out, _ = _command(stopped, monkeypatch, 8, stop_on=NORMS[4]["norm_id"])
    assert cli.main(argv) == 3
    ckpt = out.with_suffix(".checkpoint.jsonl")
    assert [json.loads(line)["batch"] for line in ckpt.read_text().splitlines()] == [f"batch:0:{NORMS[0]['norm_id']}"]
    cli, argv, out, _ = _command(stopped, monkeypatch, 2)
    assert cli.main([*argv, "--resume"]) == 0
    assert json.dumps(_untimed(json.loads(out.read_text(encoding="utf-8"))), ensure_ascii=False) == expected
    first, resumed = _executions(stopped)
    assert (first["config"]["max_in_flight"], resumed["config"]["max_in_flight"]) == (8, 2)
    assert resumed["inherited_keys"] == [f"batch:0:{NORMS[0]['norm_id']}"]

"""B164 (spec F D-F30 as amended 2026-10-12): the extraction with 8 calls in
flight writes what one call at a time writes from the same replies. Scripted
models (FakeClient) answer later units first, so the calls finish out of order;
the mock data is written here (13 source units of Articles 9 and 14), never
read from the tracked dumps. The counts below were read from today's
extract_norms (one call at a time) over this mock data before B164."""

from __future__ import annotations

import json
import os
import threading
import time

from tere4ai.act_parties import ACT_PARTIES_PATH
from tere4ai.extract_norms import pipeline
from tere4ai.extract_norms.model_clients import FakeClient, InferenceBackendUnavailable, _new_usage
from tere4ai.extract_norms.pipeline import extract_norms
from tere4ai.graph_store.build_record import BuildRecordStore

ART9, ART14 = "eu-ai-act:article-9", "eu-ai-act:article-14"
UNITS = [f"{ART9}:paragraph-{n}" for n in range(1, 9)] + [f"{ART14}:paragraph-{n}" for n in range(1, 6)]
ORDER = {unit: position for position, unit in enumerate(UNITS)}
TIMES = ("timestamp", "started_at", "completed_at", "extracted_at")


def _dump():
    nodes = [{"id": ART9, "type": "Article", "number": "9", "title": "Risk management system"},
             {"id": ART14, "type": "Article", "number": "14", "title": "Human oversight"}]
    nodes += [{"id": unit, "type": "Paragraph", "text": f"Mock text of {unit}: the provider shall keep a record.",
               "source_span": {"span_id": f"span:{unit}"}} for unit in UNITS]
    return {"build": {"build_id": "build-mock-b164"}, "nodes": nodes, "edges": []}


def _candidate(action, deontic="obligation"):
    return {"deontic_type": deontic, "modal": "shall", "addressee_explicit": "the provider", "addressee_inferred": None,
            "addressee_inference_source_node_id": None, "action": action, "object": "a record",
            "conditions": [], "exceptions": [], "lifecycle_phase_ids": [], "requirement_type": "process"}


def _generator_script():
    """Per unit: one or two candidates; paragraph 9(3) adds one that is not an object, 9(5)
    answers no JSON twice, 14(2) gives a deontic type outside the schema."""
    counts = {f"{ART9}:paragraph-1": 2, f"{ART9}:paragraph-6": 2, f"{ART14}:paragraph-3": 2}
    script = {}
    for unit in UNITS:
        key = f"Source unit node id: {unit}\n"
        if unit == f"{ART9}:paragraph-5":
            script[key] = ["not json", "still not json"]
        elif unit == f"{ART9}:paragraph-3":
            script[key] = json.dumps({"norms": [_candidate(f"keep record {unit} 1"), "not an object"]})
        elif unit == f"{ART14}:paragraph-2":
            script[key] = json.dumps({"norms": [_candidate(f"keep record {unit} 1", deontic="maybe")]})
        else:
            script[key] = json.dumps({"norms": [_candidate(f"keep record {unit} {i}")
                                                for i in range(1, counts.get(unit, 1) + 1)]})
    return script


def _verdict(verdict):
    return json.dumps({"verdict": verdict, "scores": {"semantic_similarity": 0.9, "normative_relevance": 0.9,
                       "operational_utility": 0.8, "evidence_strength": 0.85, "judge_confidence": 0.9},
                       "rationale": f"scripted {verdict}"})


JUDGE_SCRIPT = {f"Source unit node id: {unit}\n": _verdict("accepted" if unit.startswith(ART9 + ":") else "rejected")
                for unit in UNITS}


class _Timed(FakeClient):
    """Replies take longer for earlier units, so calls in flight finish out of order;
    counts the calls running at once; stop_on names a unit whose call raises. Metered
    (final review F5): each reply counts one call, its prompt's characters as input
    tokens and its reply's as output tokens, under the stub's lock, so a usage figure
    that depends on the order or the overlap of the calls would show; a stopped call
    counts nothing."""

    sampling = temperature = "N/A"
    effort = "high"
    json_mode = "sent"

    def __init__(self, scripted, model, stop_on=None):
        super().__init__(scripted, model=model)
        self.stop_on = stop_on
        self._gauge = threading.Lock()
        self.running = self.most = 0
        self._usage = _new_usage()

    def complete(self, system, user):
        unit = next(u for u in UNITS if f"Source unit node id: {u}\n" in user)
        with self._gauge:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.002 * (len(UNITS) - ORDER[unit]))
        with self._gauge:
            self.running -= 1
        if unit == self.stop_on:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        reply = super().complete(system, user)
        with self._gauge:
            for key, count in (("calls", 1), ("requests_sent", 1), ("replies_with_usage", 1),
                               ("input_tokens", len(system) + len(user)), ("output_tokens", len(reply))):
                self._usage[key] += count
        return reply

    @property
    def usage(self):
        with self._gauge:
            return dict(self._usage)


def _untimed(value):
    """The run with every time replaced: two runs differ in their clocks only."""
    if isinstance(value, dict):
        return {k: ("T" if k in TIMES else _untimed(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_untimed(v) for v in value]
    return value


def _direct(max_in_flight, tmp_path):
    generator, judge = _Timed(_generator_script(), "g"), _Timed(JUDGE_SCRIPT, "j")
    log = tmp_path / f"extraction_log_{max_in_flight}.jsonl"
    result = extract_norms(_dump(), [ART9, ART14], generator, judge, prompt_version="v5", log_path=log,
                           max_in_flight=max_in_flight)
    return result, generator, judge, log


def test_eight_calls_in_flight_give_the_result_of_one_at_a_time_byte_for_byte(tmp_path):
    one, g1, j1, log1 = _direct(1, tmp_path)
    eight, g8, j8, log8 = _direct(8, tmp_path)
    assert json.dumps(_untimed(eight), ensure_ascii=False) == json.dumps(_untimed(one), ensure_ascii=False)
    # the mock data's counts, as today's extract_norms gives them
    stats = one["stats"]
    assert (stats["source_units"], stats["candidates"], stats["verdicts"]) == (
        13, 15, {"accepted": 9, "rejected": 5, "needs_human_review": 0})
    assert [f["node_id"] for f in stats["nodes_failed"]] == [f"{ART9}:paragraph-5"]
    assert [(i["node_id"], i.get("norm_id")) for i in stats["invalid_norms"]] == [
        (f"{ART9}:paragraph-3", None), (f"{ART14}:paragraph-2", f"norm:{ART14}:paragraph-2:n1")]
    assert (len(one["norms"]), len(one["judge_runs"])) == (14, 15)
    assert [n["source_node_id"] for n in one["norms"]] == sorted(
        (n["source_node_id"] for n in one["norms"]), key=ORDER.__getitem__)
    # the calls: the same prompts, out of order, never more than eight at once
    assert (len(g1.calls), len(j1.calls)) == (14, 15)
    assert sorted(g8.calls) == sorted(g1.calls) and sorted(j8.calls) == sorted(j1.calls)
    assert g1.most == j1.most == 1 and 1 < g8.most <= 8 and j8.most <= 8
    # the clients' usage: the same counts, whatever the order the calls finished in
    assert (g1.usage["calls"], j1.usage["calls"]) == (14, 15)
    assert (g8.usage, j8.usage) == (g1.usage, j1.usage)
    # the log: the same 28 lines, in the order the calls finished
    lines1 = [json.dumps(_untimed(json.loads(line))) for line in log1.read_text().splitlines()]
    lines8 = [json.dumps(_untimed(json.loads(line))) for line in log8.read_text().splitlines()]
    assert len(lines1) == 28 and sorted(lines8) == sorted(lines1)


def _command(tmp_path, monkeypatch, max_in_flight, stop_on=None, name="norms_mock.json", nodes=(ART9, ART14)):
    """The command over the mock dump, its scripted models answering out of order."""
    import tere4ai.extract_norms.__main__ as cli

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j", "generator_effort": "high", "judge_effort": "high"}

    dump_path = tmp_path / "layer1.json"
    if not dump_path.exists():
        dump_path.write_text(json.dumps(_dump()), encoding="utf-8")
    generator, judge = _Timed(_generator_script(), "g"), _Timed(JUDGE_SCRIPT, "j", stop_on=stop_on)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg, **kw: generator)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg, **kw: judge)
    monkeypatch.setattr(pipeline, "DEFAULT_LOG_PATH", tmp_path / "extraction_log.jsonl")
    out = tmp_path / name
    argv = ["--nodes", ",".join(nodes), "--dump", str(dump_path), "--out", str(out), "--record", "mock",
            "--max-in-flight", str(max_in_flight)]
    return cli, argv, out, generator, judge


def _executions(tmp_path):
    store = BuildRecordStore(tmp_path)
    return store.read(store.resolve("mock"))["executions"]


def test_the_command_at_eight_writes_the_norms_file_and_record_of_one_at_a_time(tmp_path, monkeypatch, capsys):
    files = {}
    for setting in (1, 8):
        run_dir = tmp_path / f"at-{setting}"
        run_dir.mkdir()
        cli, argv, out, generator, judge = _command(run_dir, monkeypatch, setting)
        assert cli.main(argv) == 0
        # the setting reaches the calls: one at a time at 1, overlapping (never above 8) at 8
        assert (generator.most == 1) if setting == 1 else (1 < generator.most <= 8 and judge.most <= 8)
        assert f"calls in flight: at most {setting} (--max-in-flight)\n" in capsys.readouterr().out
        files[setting] = (json.loads(out.read_text(encoding="utf-8")), _executions(run_dir)[0])
    (payload1, ex1), (payload8, ex8) = files[1], files[8]
    assert json.dumps(_untimed(payload8), ensure_ascii=False) == json.dumps(_untimed(payload1), ensure_ascii=False)
    # the usage written in the norms file and in the record: equal, and not empty (F5)
    assert payload1["build"]["extraction_usage"]["generator"]["calls"] == 14
    assert payload1["build"]["extraction_usage"]["judge"]["calls"] == 15
    assert payload8["build"]["extraction_usage"] == payload1["build"]["extraction_usage"] == ex1["usage"] == ex8["usage"]
    assert (ex1["config"]["max_in_flight"], ex8["config"]["max_in_flight"]) == (1, 8)
    assert {k: v for k, v in ex8["config"].items() if k != "max_in_flight"} == {
        "prompt_version": "v7", "nodes": [ART9, ART14]}
    for key in ("completed_keys", "counts", "work_failures", "status", "inherited_keys"):
        assert ex8[key] == ex1[key], key
    assert ex8["completed_keys"] == [ART9, ART14]


def test_a_run_stopped_with_calls_in_flight_resumes_to_the_uninterrupted_result(tmp_path, monkeypatch, capsys):
    """Review Focus 1: the judge's call on 14(3) stops the run; Article 9's group is
    checkpointed, Article 14's is not; the resume at 8 finishes it. The norms file equals
    the uninterrupted run's but for its usage: the resumed invocation records the usage of
    the calls it made, which leaves out the inherited group, so it equals a run over
    Article 14 alone (final review F5)."""
    reference = tmp_path / "reference"
    reference.mkdir()
    cli, argv, out, _g, _j = _command(reference, monkeypatch, 1)
    assert cli.main(argv) == 0
    expected = _untimed(json.loads(out.read_text(encoding="utf-8")))
    total_usage = expected["build"].pop("extraction_usage")
    only_14 = tmp_path / "only-14"
    only_14.mkdir()
    cli, argv, out, _g, _j = _command(only_14, monkeypatch, 1, nodes=(ART14,))
    assert cli.main(argv) == 0
    usage_14 = json.loads(out.read_text(encoding="utf-8"))["build"]["extraction_usage"]
    assert 0 < usage_14["generator"]["calls"] < total_usage["generator"]["calls"]

    stopped = tmp_path / "stopped"
    stopped.mkdir()
    cli, argv, out, generator, judge = _command(stopped, monkeypatch, 8, stop_on=f"{ART14}:paragraph-3")
    assert cli.main(argv) == 3
    assert 1 < generator.most <= 8 and judge.most <= 8  # stopped with calls in flight
    assert "stopped: inference backend unavailable after 6 attempts: HTTP 529" in capsys.readouterr().err
    ckpt = out.with_suffix(".checkpoint.jsonl")
    assert [json.loads(line)["group"] for line in ckpt.read_text().splitlines()] == [ART9]
    cli, argv, out, generator, judge = _command(stopped, monkeypatch, 8)
    assert cli.main([*argv, "--resume"]) == 0
    assert generator.most <= 8 and judge.most <= 8
    resumed_payload = _untimed(json.loads(out.read_text(encoding="utf-8")))
    assert resumed_payload["build"].pop("extraction_usage") == usage_14
    assert json.dumps(resumed_payload, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
    first, resumed = _executions(stopped)
    assert first["status"] == "failed" and first["error"] == "inference backend unavailable after 6 attempts: HTTP 529"
    assert first["completed_keys"] == [ART9]
    assert resumed["inherited_keys"] == [ART9] and resumed["completed_keys"] == [ART14]
    assert resumed["config"]["max_in_flight"] == 8
    assert resumed["usage"] == usage_14


def test_act_parties_input_is_recorded_as_before(tmp_path, monkeypatch):
    """The setting adds one config key and changes no input."""
    cli, argv, _out, _g, _j = _command(tmp_path, monkeypatch, 8)
    assert cli.main(argv) == 0
    (ex,) = _executions(tmp_path)
    assert [i["input_kind"] for i in ex["inputs"]] == ["layer1_dump", "act_parties"]
    assert ex["inputs"][1]["file"] == os.path.relpath(ACT_PARTIES_PATH.resolve(), tmp_path.resolve())

"""B164: the elicitation with scenarios in flight writes the checkpoint lines and the
features file in the benchmark's order. Offline: the config, the client, the build and
the elicitor are replaced, as in test_elicit_benchmark_features.py."""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

from tests.fixtures.model_parameters import declared

from tere4ai.elicit_features import Elicitation
from tere4ai.extract_norms.model_clients import InferenceBackendUnavailable
from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.judge.config import ModelConfig

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [{"id": f"bench:{n}", "kind": "classification", "system_text": f"a scoring system number {n}"}
         for n in range(1, 7)]
ITEMS.insert(4, {"id": "bench:short", "kind": "classification", "system_text": "short"})
DUMP = {"build": {"build_id": "build-x"}, "nodes": []}
PROMPT = {"prompt": "elicit_features", "version": "v8", "template_sha256": "a" * 64, "rendered_sha256": "b" * 64,
          "provisions": [], "graph_version": "build-x"}


def _cfg():
    return ModelConfig(generator_model="g", judge_model="claude-j", generator_api_key="k1", judge_api_key="k2",
                       generator_parameters=declared("g", "openai"), judge_parameters=declared("claude-j", "anthropic"))


class Gauge:
    """The most elicitations running at once (the same interface as the E6 test's Gauge:
    used as `with gauge:` around one call, read as `gauge.most`)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = self.most = 0

    def __enter__(self):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)

    def __exit__(self, *exc):
        with self.lock:
            self.running -= 1


def _script(monkeypatch, fail_on=None, gauge=None, pause=0.003):
    spec = importlib.util.spec_from_file_location("elicit_benchmark_features",
                                                  ROOT / "scripts" / "elicit_benchmark_features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.harness, "load_benchmark_items", lambda path: [dict(i) for i in ITEMS])
    monkeypatch.setattr(mod, "load_model_config", _cfg)
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: object())
    monkeypatch.setattr(mod, "load_active", lambda d: LoadedBuild(DUMP, None, None, "build-x", "legacy", None))
    monkeypatch.setattr(mod, "render_prompt", lambda dump, snapshots_dir, version: ("system", dict(PROMPT, version=version)))

    def elicit(description, generator, *, dump, snapshots_dir, prompt_version):
        number = int(description.rsplit(" ", 1)[1])
        with gauge or Gauge():
            time.sleep(pause * (8 - number))  # later scenarios answer first
        if description == fail_on:
            raise InferenceBackendUnavailable(6, "HTTP 529")
        return Elicitation(features={"flag": number % 2 == 0}, quotes={}, dropped=[],
                           notes=["elicited on attempt 1"], prompt=dict(PROMPT, version=prompt_version))

    monkeypatch.setattr(mod, "elicit", elicit)
    return mod


def _payload(out):
    payload = json.loads(out.read_text(encoding="utf-8"))
    return payload.pop("max_in_flight"), json.dumps(payload, ensure_ascii=False)


def _printed_items(printed):
    """The item lines in the order printed; each is printed right after its checkpoint line."""
    return [line[2:].rsplit(": ", 1)[0] for line in printed.splitlines() if line.startswith("  bench:")]


def test_four_in_flight_write_the_checkpoint_and_the_file_of_one_at_a_time(tmp_path, monkeypatch, capsys):
    outs, most = {}, {}
    for setting in (1, 4):
        out = tmp_path / f"features_{setting}.json"
        gauge = Gauge()
        assert _script(monkeypatch, gauge=gauge).main(["--out", str(out), "--max-in-flight", str(setting)]) == 0
        most[setting] = gauge.most
        printed = capsys.readouterr().out
        assert f"calls in flight: at most {setting} (--max-in-flight)\n" in printed
        assert "  bench:short: SKIPPED (no text)\n" in printed
        outs[setting] = (_payload(out), _printed_items(printed))
    ((setting1, file1), items1), ((setting4, file4), items4) = outs[1], outs[4]
    assert (setting1, setting4) == (1, 4) and file4 == file1
    assert most[1] == 1 and 1 < most[4] <= 4  # the setting reaches the calls
    assert items1 == items4 == [i["id"] for i in ITEMS]
    assert list(json.loads(file1)["features_by_item"]) == [i["id"] for i in ITEMS]


def test_a_stop_with_a_gap_reruns_to_the_uninterrupted_file(tmp_path, monkeypatch, capsys):
    """Review Focus 3: scenario 3 stops the run with 4 in flight; the finished ones are
    kept in order without it, and the rerun writes the file in the benchmark's order."""
    reference = tmp_path / "reference.json"
    assert _script(monkeypatch).main(["--out", str(reference), "--max-in-flight", "1"]) == 0
    out = tmp_path / "features.json"
    mod = _script(monkeypatch, fail_on="a scoring system number 3")
    assert mod.main(["--out", str(out), "--max-in-flight", "4"]) == 3
    assert "stopped: inference backend unavailable after 6 attempts: HTTP 529" in capsys.readouterr().err
    kept = [json.loads(line)["item_id"] for line in out.with_suffix(".checkpoint.jsonl").read_text().splitlines()]
    assert "bench:3" not in kept and kept[:2] == ["bench:1", "bench:2"] and "bench:4" in kept
    assert kept == [i["id"] for i in ITEMS if i["id"] in kept]
    assert _script(monkeypatch).main(["--out", str(out), "--max-in-flight", "4"]) == 0
    assert _payload(out)[1] == _payload(reference)[1]


def test_instant_work_writes_the_same_file_at_four_as_at_one(tmp_path, monkeypatch):
    payloads = {}
    for setting in (1, 4):
        out = tmp_path / f"instant_{setting}.json"
        assert _script(monkeypatch, pause=0).main(["--out", str(out), "--max-in-flight", str(setting)]) == 0
        payloads[setting] = _payload(out)
    assert payloads[4][1] == payloads[1][1]

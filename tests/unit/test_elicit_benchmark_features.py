"""scripts/elicit_benchmark_features.py is a terminal run (spec F D-F30, B101
ruling S4): it builds its generator with the terminal policy, and an inference
backend stop or refusal keeps the checkpoint and prints the command that resumes it.
Offline: the model config, the client and the elicitor are replaced.

B10: the run elicits with elicit() over the build load_active serves, and
every checkpoint entry and the output carry the quotes, the dropped facts and
the prompt record; a resume under another prompt is refused like one under
other models."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
from pathlib import Path

import pytest
from tests.fixtures.model_parameters import declared

from tere4ai.elicit_features import Elicitation
from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION
from tere4ai.elicit_features.provisions import ProvisionUnresolved
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    InferenceBackendRefused,
    InferenceBackendUnavailable,
)
from tere4ai.graph_store.publication import LoadedBuild
from tere4ai.judge.config import DeclaredParameterRefused, ModelConfig

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [{"id": "bench:1", "kind": "classification", "system_text": "a scoring system for loans"},
         {"id": "bench:2", "kind": "classification", "system_text": "a triage system for claims"}]


DUMP = {"build": {"build_id": "build-x"}, "nodes": []}
PROMPT = {"prompt": "elicit_features", "version": "v7", "template_sha256": "a" * 64,
          "rendered_sha256": "b" * 64, "provisions": ["eu-ai-act:definition:profiling"],
          "graph_version": "build-x"}
QUOTES = {"flags.flag": {"text": "a scoring system", "start": 0, "end": 16}}
DROPPED = [{"path": "domain", "reason": "no quote"}]


def _cfg(effort="xhigh"):
    return ModelConfig(generator_model="g", judge_model="claude-j", generator_api_key="k1", judge_api_key="k2",
                       generator_parameters=declared("g", "openai", effort=effort),
                       judge_parameters=declared("claude-j", "anthropic"))


def _script(monkeypatch, fail_on=None, failure=None, cfg=None, prompt=None, loaded=None, unresolved=None):
    spec = importlib.util.spec_from_file_location("elicit_benchmark_features",
                                                  ROOT / "scripts" / "elicit_benchmark_features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    policies: list = []
    monkeypatch.setattr(mod.harness, "load_benchmark_items", lambda path: [dict(i) for i in ITEMS])
    # B99 (spec F D-F29) final review M1: a real configuration, whose declaration the script records
    loads = []
    monkeypatch.setattr(mod, "load_model_config", lambda: loads.append(1) or (cfg or _cfg()))
    mod._TEST_LOADS = loads
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or object())
    # B10: the build and the rendered prompt are mock data unless a test asks for the repository's
    monkeypatch.setattr(mod, "load_active", lambda d: loaded or LoadedBuild(DUMP, None, None, "build-x", "legacy", None))
    run_prompt = dict(prompt or PROMPT)

    def render(dump, snapshots_dir, prompt_version):
        if unresolved is not None:
            raise unresolved
        return "system", dict(run_prompt, version=prompt_version)
    monkeypatch.setattr(mod, "render_prompt", render)

    def elicit(description, generator, *, dump, snapshots_dir, prompt_version):
        assert dump is (loaded.dump if loaded else DUMP)
        if fail_on is not None and description == fail_on:
            raise failure
        return Elicitation(features={"flag": True}, quotes=QUOTES, dropped=DROPPED,
                           notes=["elicited on attempt 1"], prompt=dict(run_prompt, version=prompt_version))
    monkeypatch.setattr(mod, "elicit", elicit)
    return mod, policies


def test_a_backend_stop_keeps_the_checkpoint_prints_the_resume_and_a_rerun_finishes(tmp_path, monkeypatch, capsys):
    out = tmp_path / "features.json"
    argv = ["--out", str(out)]
    mod, policies = _script(monkeypatch, fail_on=ITEMS[1]["system_text"],
                            failure=InferenceBackendUnavailable(6, "HTTP 529"))
    assert mod.main(argv) == 3
    assert policies == [TERMINAL_POLICY]
    ckpt = out.with_suffix(".checkpoint.jsonl")
    assert [json.loads(line)["item_id"] for line in ckpt.read_text().splitlines()] == ["bench:1"]
    assert not out.exists()
    err = capsys.readouterr().err
    assert "stopped: inference backend unavailable after 6 attempts: HTTP 529" in err
    assert f"the checkpoint {ckpt.name} is kept (1 of 2 items done); continue with:" in err
    assert "  " + shlex.join([".venv/bin/python", "scripts/elicit_benchmark_features.py", *argv]) in err
    mod, _ = _script(monkeypatch)
    assert mod.main(argv) == 0
    assert set(json.loads(out.read_text())["features_by_item"]) == {"bench:1", "bench:2"}


def test_a_backend_refusal_names_the_item_and_exits_5(tmp_path, monkeypatch, capsys):
    """B101 ruling S5: the item refused is fixed before the rerun, never skipped."""
    mod, _ = _script(monkeypatch, fail_on=ITEMS[0]["system_text"], failure=InferenceBackendRefused("HTTP 413"))
    assert mod.main(["--out", str(tmp_path / "features.json")]) == 5
    assert "stopped: inference backend refused the request: HTTP 413 (item bench:1)" in capsys.readouterr().err


def test_the_entries_and_the_output_name_the_declaration_and_the_config_is_loaded_once(tmp_path, monkeypatch):
    """B99 (spec F D-F29) final review M1."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=InferenceBackendUnavailable(6, "HTTP 529"))
    assert mod.main(["--out", str(out)]) == 3
    (entry,) = [json.loads(line) for line in out.with_suffix(".checkpoint.jsonl").read_text().splitlines()]
    assert entry["models"] == _cfg().as_public_dict() and entry["elicitor_model"] == "g"
    mod, _ = _script(monkeypatch)
    assert mod.main(["--out", str(out)]) == 0
    assert mod._TEST_LOADS == [1]
    payload = json.loads(out.read_text())
    assert payload["models"] == _cfg().as_public_dict() and payload["elicitor_model"] == "g"


def test_a_rerun_under_another_declaration_is_refused_by_name(tmp_path, monkeypatch, capsys):
    """B99 (spec F D-F29) final review M1: the cache never mixes items
    elicited under two declarations."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=InferenceBackendUnavailable(6, "HTTP 529"))
    assert mod.main(["--out", str(out)]) == 3
    ckpt = out.with_suffix(".checkpoint.jsonl")
    before = ckpt.read_bytes()
    mod, _ = _script(monkeypatch, cfg=_cfg(effort="high"))
    assert mod.main(["--out", str(out)]) == 2
    assert (f"refusing to resume {ckpt.name}: an elicited item was run under different models: "
            "model_parameters_sha256; restore the row in config/model_parameters.json to resume it, or move "
            "the checkpoint away to start again") in capsys.readouterr().out
    assert ckpt.read_bytes() == before and not out.exists()


def test_a_refused_declared_parameter_exits_4_and_keeps_the_checkpoint(tmp_path, monkeypatch, capsys):
    out = tmp_path / "features.json"
    refused = DeclaredParameterRefused("openai", "g", "effort", "xhigh", "HTTP 400: effort unsupported")
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=refused)
    assert mod.main(["--out", str(out)]) == 4
    assert ("stopped: configuration error: openai:g refused the declared effort xhigh (HTTP 400: effort "
            "unsupported); correct its row in config/model_parameters.json") in capsys.readouterr().err
    assert out.with_suffix(".checkpoint.jsonl").exists() and not out.exists()


def test_the_default_prompt_version_is_the_elicitors(tmp_path, monkeypatch):
    """Jose, 2026-10-01: "Re-extract at B74 with v5": without --prompt-version
    the run elicits with the elicitor's own default, one default, not two."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch)
    seen: list[str] = []

    # B10: the run calls elicit(), keyword arguments over the served build
    def elicit(description, generator, *, dump, snapshots_dir, prompt_version):
        seen.append(prompt_version)
        return Elicitation(features={"flag": True}, notes=["elicited on attempt 1"],
                           prompt=dict(PROMPT, version=prompt_version))

    monkeypatch.setattr(mod, "elicit", elicit)
    assert mod.main(["--out", str(out)]) == 0
    assert seen == [DEFAULT_PROMPT_VERSION, DEFAULT_PROMPT_VERSION]
    # B10: the elicitor's default moved from v5 to v6 (quotes per fact);
    # B132: to v7 (the Act as amended).
    assert DEFAULT_PROMPT_VERSION == "v7"
    assert json.loads(out.read_text())["prompt_version"] == "v7"


def test_the_entries_and_the_output_carry_quotes_dropped_facts_and_the_prompt(tmp_path, monkeypatch):
    """B10: each entry carries the quotes, the dropped facts and the prompt
    record; the output names the prompt once (the run is on one build) beside
    quotes_by_item, dropped_by_item and the unchanged features_by_item."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=InferenceBackendUnavailable(6, "HTTP 529"))
    assert mod.main(["--out", str(out)]) == 3
    (entry,) = [json.loads(line) for line in out.with_suffix(".checkpoint.jsonl").read_text().splitlines()]
    assert entry["quotes"] == QUOTES and entry["dropped"] == DROPPED and entry["prompt"] == PROMPT
    mod, _ = _script(monkeypatch)
    assert mod.main(["--out", str(out)]) == 0
    payload = json.loads(out.read_text())
    assert payload["prompt"] == PROMPT
    assert payload["features_by_item"] == {"bench:1": {"flag": True}, "bench:2": {"flag": True}}
    assert payload["quotes_by_item"] == {"bench:1": QUOTES, "bench:2": QUOTES}
    assert payload["dropped_by_item"] == {"bench:1": DROPPED, "bench:2": DROPPED}


def test_an_item_without_text_carries_the_runs_prompt_and_no_quotes(tmp_path, monkeypatch):
    """B10: a skipped item makes no call, but its entry names the run's prompt
    so a resume over it is checked like any other."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch)
    monkeypatch.setattr(mod.harness, "load_benchmark_items",
                        lambda path: [{"id": "bench:0", "kind": "classification", "system_text": "short"}])
    assert mod.main(["--out", str(out)]) == 0
    payload = json.loads(out.read_text())
    assert payload["features_by_item"] == {"bench:0": None}
    assert payload["quotes_by_item"] == {"bench:0": {}} and payload["dropped_by_item"] == {"bench:0": []}
    assert payload["prompt"] == PROMPT


@pytest.mark.parametrize("key", ["version", "template_sha256", "rendered_sha256", "graph_version"])
def test_a_rerun_under_another_prompt_is_refused_by_name(tmp_path, monkeypatch, capsys, key):
    """B10: the cache never mixes items elicited under two prompts (another
    version or template), nor over two builds, which would make the output's
    one prompt record untrue; mirrors the models check."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=InferenceBackendUnavailable(6, "HTTP 529"))
    assert mod.main(["--out", str(out)]) == 3
    ckpt = out.with_suffix(".checkpoint.jsonl")
    before = ckpt.read_bytes()
    other = dict(PROMPT, **{key: "v5" if key == "version" else "c" * 64})
    mod, policies = _script(monkeypatch, prompt=other)
    argv = ["--out", str(out)] + (["--prompt-version", "v5"] if key == "version" else [])
    assert mod.main(argv) == 2
    assert (f"refusing to resume {ckpt.name}: an elicited item was run under a different prompt: {key}; "
            "rerun with the prompt version and the build the checkpoint names to resume it, or move the "
            "checkpoint away to start again") in capsys.readouterr().out
    assert ckpt.read_bytes() == before and not out.exists() and policies == []


def test_a_checkpoint_entry_without_a_prompt_record_is_refused(tmp_path, monkeypatch, capsys):
    """B10: an entry written before the prompt record existed differs too."""
    out = tmp_path / "features.json"
    ckpt = out.with_suffix(".checkpoint.jsonl")
    ckpt.write_text(json.dumps({"item_id": "bench:1", "features": None, "notes": [],
                                "models": _cfg().as_public_dict()}) + "\n")
    mod, _ = _script(monkeypatch)
    assert mod.main(["--out", str(out)]) == 2
    assert "an elicited item was run under a different prompt: graph_version, rendered_sha256, " \
           "template_sha256, version;" in capsys.readouterr().out


def test_a_build_that_does_not_load_is_refused_before_any_client(tmp_path, monkeypatch, capsys):
    out = tmp_path / "features.json"
    failed = LoadedBuild(None, None, None, None, "manifest", "the activation pointer is unreadable")
    mod, policies = _script(monkeypatch, loaded=failed)
    assert mod.main(["--out", str(out)]) == 2
    assert "refusing to elicit: no build is served: the activation pointer is unreadable" in capsys.readouterr().out
    assert policies == [] and not out.exists()


def test_a_provision_that_does_not_resolve_is_refused_before_any_client(tmp_path, monkeypatch, capsys):
    out = tmp_path / "features.json"
    exc = ProvisionUnresolved("eu-ai-act:definition:nowhere", "build-x", "unknown node")
    mod, policies = _script(monkeypatch, unresolved=exc)
    assert mod.main(["--out", str(out)]) == 2
    assert ("refusing to elicit: definition eu-ai-act:definition:nowhere does not resolve in build-x: "
            "unknown node; no model call made") in capsys.readouterr().out
    assert policies == [] and not out.exists()


def test_the_prompt_record_is_the_rendered_v6_over_the_repositorys_build(tmp_path, monkeypatch):
    """B10: unpatched, the run renders v6 over the build load_active serves
    from data/graph_dumps (no model call: the elicitor is replaced)."""
    if not (ROOT / "data" / "graph_dumps" / "layer1.json").is_file():
        pytest.skip("layer1.json dump not built")
    spec = importlib.util.spec_from_file_location("elicit_benchmark_features",
                                                  ROOT / "scripts" / "elicit_benchmark_features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.harness, "load_benchmark_items", lambda path: [dict(ITEMS[0])])
    monkeypatch.setattr(mod, "load_model_config", lambda: _cfg())
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: object())
    monkeypatch.setattr(mod, "elicit", lambda description, generator, *, dump, snapshots_dir, prompt_version:
                        Elicitation(features=None, notes=["mock"], prompt=mod.render_prompt(
                            dump, snapshots_dir, prompt_version)[1]))
    out = tmp_path / "features.json"
    assert mod.main(["--out", str(out)]) == 0
    prompt = json.loads(out.read_text())["prompt"]
    v7 = (ROOT / "prompts" / "elicit_features" / "v7.md").read_bytes()
    assert prompt["version"] == "v7" and prompt["template_sha256"] == hashlib.sha256(v7).hexdigest()
    assert prompt["graph_version"] == mod.load_active(mod.DUMP_DIR).build_id
    assert len(prompt["rendered_sha256"]) == 64 and prompt["provisions"]

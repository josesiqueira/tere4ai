"""scripts/elicit_benchmark_features.py is a terminal run (spec F D-F30, B101
ruling S4): it builds its generator with the terminal policy, and a provider
stop or refusal keeps the checkpoint and prints the command that resumes it.
Offline: the model config, the client and the elicitor are replaced."""

from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path

from tests.fixtures.model_parameters import declared

from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION
from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    ProviderRefused,
    ProviderUnavailable,
)
from tere4ai.judge.config import DeclaredParameterRefused, ModelConfig

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [{"id": "bench:1", "kind": "classification", "system_text": "a scoring system for loans"},
         {"id": "bench:2", "kind": "classification", "system_text": "a triage system for claims"}]


def _cfg(effort="xhigh"):
    return ModelConfig(generator_model="g", judge_model="claude-j", generator_api_key="k1", judge_api_key="k2",
                       generator_parameters=declared("g", "openai", effort=effort),
                       judge_parameters=declared("claude-j", "anthropic"))


def _script(monkeypatch, fail_on=None, failure=None, cfg=None):
    spec = importlib.util.spec_from_file_location("elicit_benchmark_features",
                                                  ROOT / "scripts" / "elicit_benchmark_features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    policies: list = []
    monkeypatch.setattr(mod.harness, "load_benchmark_items", lambda path: [dict(i) for i in ITEMS])
    # B99 (spec F D-F29) final review M1: a real configuration, whose declaration the script records
    loaded = []
    monkeypatch.setattr(mod, "load_model_config", lambda: loaded.append(1) or (cfg or _cfg()))
    mod._TEST_LOADS = loaded
    monkeypatch.setattr(mod, "OpenAIGenerator", lambda cfg, **kw: policies.append(kw.get("retry_policy")) or object())

    def elicit(description, generator, prompt_version="v2"):
        if fail_on is not None and description == fail_on:
            raise failure
        return {"flag": True}, ["elicited on attempt 1"]
    monkeypatch.setattr(mod, "elicit_features", elicit)
    return mod, policies


def test_a_provider_stop_keeps_the_checkpoint_prints_the_resume_and_a_rerun_finishes(tmp_path, monkeypatch, capsys):
    out = tmp_path / "features.json"
    argv = ["--out", str(out)]
    mod, policies = _script(monkeypatch, fail_on=ITEMS[1]["system_text"],
                            failure=ProviderUnavailable(6, "HTTP 529"))
    assert mod.main(argv) == 3
    assert policies == [TERMINAL_POLICY]
    ckpt = out.with_suffix(".checkpoint.jsonl")
    assert [json.loads(line)["item_id"] for line in ckpt.read_text().splitlines()] == ["bench:1"]
    assert not out.exists()
    err = capsys.readouterr().err
    assert "stopped: provider unavailable after 6 attempts: HTTP 529" in err
    assert f"the checkpoint {ckpt.name} is kept (1 of 2 items done); continue with:" in err
    assert "  " + shlex.join([".venv/bin/python", "scripts/elicit_benchmark_features.py", *argv]) in err
    mod, _ = _script(monkeypatch)
    assert mod.main(argv) == 0
    assert set(json.loads(out.read_text())["features_by_item"]) == {"bench:1", "bench:2"}


def test_a_provider_refusal_names_the_item_and_exits_5(tmp_path, monkeypatch, capsys):
    """B101 ruling S5: the item refused is fixed before the rerun, never skipped."""
    mod, _ = _script(monkeypatch, fail_on=ITEMS[0]["system_text"], failure=ProviderRefused("HTTP 413"))
    assert mod.main(["--out", str(tmp_path / "features.json")]) == 5
    assert "stopped: provider refused the request: HTTP 413 (item bench:1)" in capsys.readouterr().err


def test_the_entries_and_the_output_name_the_declaration_and_the_config_is_loaded_once(tmp_path, monkeypatch):
    """B99 (spec F D-F29) final review M1."""
    out = tmp_path / "features.json"
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=ProviderUnavailable(6, "HTTP 529"))
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
    mod, _ = _script(monkeypatch, fail_on=ITEMS[1]["system_text"], failure=ProviderUnavailable(6, "HTTP 529"))
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

    def elicit(description, generator, prompt_version):
        seen.append(prompt_version)
        return {"flag": True}, ["elicited on attempt 1"]

    monkeypatch.setattr(mod, "elicit_features", elicit)
    assert mod.main(["--out", str(out)]) == 0
    assert seen == [DEFAULT_PROMPT_VERSION, DEFAULT_PROMPT_VERSION]
    # B10: the elicitor's default moved from v5 to v6 (quotes per fact).
    assert DEFAULT_PROMPT_VERSION == "v6"
    assert json.loads(out.read_text())["prompt_version"] == "v6"

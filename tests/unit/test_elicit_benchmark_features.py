"""scripts/elicit_benchmark_features.py is a terminal run (spec F D-F30, B101
ruling S4): it builds its generator with the terminal policy, and a provider
stop or refusal keeps the checkpoint and prints the command that resumes it.
Offline: the model config, the client and the elicitor are replaced."""

from __future__ import annotations

import importlib.util
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

from tere4ai.extract_norms.model_clients import (
    TERMINAL_POLICY,
    ProviderRefused,
    ProviderUnavailable,
)

ROOT = Path(__file__).resolve().parents[2]
ITEMS = [{"id": "bench:1", "kind": "classification", "system_text": "a scoring system for loans"},
         {"id": "bench:2", "kind": "classification", "system_text": "a triage system for claims"}]


def _script(monkeypatch, fail_on=None, failure=None):
    spec = importlib.util.spec_from_file_location("elicit_benchmark_features",
                                                  ROOT / "scripts" / "elicit_benchmark_features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    policies: list = []
    monkeypatch.setattr(mod.harness, "load_benchmark_items", lambda path: [dict(i) for i in ITEMS])
    monkeypatch.setattr(mod, "load_model_config", lambda: SimpleNamespace(generator_model="g"))
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

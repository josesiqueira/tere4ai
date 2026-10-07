"""B149: eval/config_evaluated.yaml names the declared models, settings and
prompt versions, and these tests fail when it drifts from .env, from
config/model_parameters.json (spec F D-F22, D-F29) or from the code defaults.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from dotenv import dotenv_values

from tere4ai.align_hleg import pipeline as align_pipeline
from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION as ELICITOR_DEFAULT
from tere4ai.eval import strategies
from tere4ai.extract_norms.pipeline import DEFAULT_PROMPT_VERSION as EXTRACT_DEFAULT
from tere4ai.mcp_server import backlog, evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "eval" / "config_evaluated.yaml"
PARAMETERS = REPO_ROOT / "config" / "model_parameters.json"
ENV_FILE = REPO_ROOT / ".env"


def _sections() -> dict[str, dict[str, str]]:
    """The two-level 'section: / key: value' layout of the file."""
    sections: dict[str, dict[str, str]] = {}
    current = None
    for raw in CONFIG.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            current = line.split(":", 1)[0].strip()
            sections[current] = {}
            continue
        key, _, value = line.strip().partition(":")
        sections[current][key.strip()] = value.strip()
    return sections


def _default_of(fn, parameter: str) -> str:
    return inspect.signature(fn).parameters[parameter].default


def _declared_row(model_id: str) -> dict:
    return json.loads(PARAMETERS.read_text(encoding="utf-8"))["models"][model_id]


def test_model_ids_equal_the_ones_env_names():
    if not ENV_FILE.is_file():
        pytest.skip("no .env in this checkout")
    env = dotenv_values(ENV_FILE)
    sections = _sections()
    assert sections["generator"]["model"] == env["TERE4AI_GENERATOR_MODEL"]
    assert sections["judges"]["model"] == env["TERE4AI_JUDGE_MODEL"]


def test_settings_equal_the_declared_rows_of_the_parameters_table():
    sections = _sections()
    for role in ("generator", "judges"):
        row = _declared_row(sections[role]["model"])
        assert sections[role]["family"] == row["provider"]
        assert sections[role]["temperature"] == row["temperature"]
        assert sections[role]["effort"] == row["effort"]


def test_prompt_versions_equal_the_code_defaults():
    versions = _sections()["prompt_versions"]
    assert versions["extract_norms"] == EXTRACT_DEFAULT
    assert versions["judge_norms"] == EXTRACT_DEFAULT
    assert versions["evaluate_evidence"] == evidence.GENERATOR_PROMPT_VERSION
    assert versions["align_hleg"] == _default_of(align_pipeline.align_norms, "prompt_version")
    assert versions["judge_alignment"] == versions["align_hleg"]
    # the runtime judge (runtime_grounding) runs at a version per path (B149 NEEDS_CONTEXT)
    assert versions["runtime_grounding_evidence"] == evidence.JUDGE_PROMPT_VERSION
    assert versions["generate_backlog"] == backlog.DEFAULT_PROMPT_VERSION
    assert versions["runtime_grounding_backlog"] == backlog.DEFAULT_PROMPT_VERSION
    assert versions["runtime_grounding_ablation"] == _default_of(
        strategies.GraphStrategy.__init__, "judge_prompt_version")
    assert versions["elicit_features"] == ELICITOR_DEFAULT


def test_the_builds_block_names_no_disposable_build():
    builds = _sections()["builds"]
    assert set(builds.values()) == {"to be filled by B74"}

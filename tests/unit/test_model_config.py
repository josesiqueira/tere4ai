"""Tests for DEC-07 model configuration (no real keys needed)."""

import pytest

from tere4ai.judge.config import ModelConfig, ModelConfigError, load_model_config

FULL_ENV = {
    "TERE4AI_GENERATOR_MODEL": "gpt-test-pinned",
    "TERE4AI_JUDGE_MODEL": "claude-test-pinned",
    "OPENAI_API_KEY": "sk-fake",
    "ANTHROPIC_API_KEY": "sk-ant-fake",
}


def test_valid_config_loads():
    cfg = load_model_config(dict(FULL_ENV))
    assert isinstance(cfg, ModelConfig)
    assert cfg.generator_model == "gpt-test-pinned"
    assert cfg.judge_model == "claude-test-pinned"


def test_missing_vars_fail_fast_and_list_all():
    env = dict(FULL_ENV)
    env.pop("ANTHROPIC_API_KEY")
    env["TERE4AI_JUDGE_MODEL"] = ""
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env)
    msg = str(exc.value)
    assert "ANTHROPIC_API_KEY" in msg and "TERE4AI_JUDGE_MODEL" in msg


def test_same_family_judge_rejected():
    env = dict(FULL_ENV)
    env["TERE4AI_JUDGE_MODEL"] = "gpt-5.2"
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env)
    assert "independent" in str(exc.value)


def test_public_dict_never_leaks_keys():
    cfg = load_model_config(dict(FULL_ENV))
    public = cfg.as_public_dict()
    assert "sk-fake" not in str(public) and "sk-ant-fake" not in str(public)
    assert set(public) == {"generator_model", "judge_model"}

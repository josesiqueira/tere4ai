"""Tests for DEC-07 model configuration (no real keys needed)."""

import pytest

from tere4ai.judge.config import (
    ModelConfig,
    ModelConfigError,
    assert_independent_judge,
    load_model_config,
    require_independent_clients,
)

FULL_ENV = {
    "TERE4AI_GENERATOR_MODEL": "gpt-test-pinned",
    "TERE4AI_JUDGE_MODEL": "claude-test-pinned",
    "OPENAI_API_KEY": "sk-fake",
    "ANTHROPIC_API_KEY": "sk-ant-fake",
    "TERE4AI_GENERATOR_EFFORT": "xhigh",
    "TERE4AI_JUDGE_EFFORT": "xhigh",
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


def test_same_model_id_for_generator_and_judge_rejected():
    """The generator judging its own output collapses the control (DEC-07)."""
    env = dict(FULL_ENV)
    env["TERE4AI_GENERATOR_MODEL"] = "claude-test-pinned"
    env["TERE4AI_JUDGE_MODEL"] = "claude-test-pinned"
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env)
    assert "same" in str(exc.value).lower() or "judging its own" in str(exc.value)


def test_assert_independent_judge_accepts_a_distinct_non_openai_judge():
    # Does not raise.
    assert_independent_judge("gpt-5.2", "claude-opus-4-8")


@pytest.mark.parametrize("openai_name", ["gpt-5.2", "o3-mini", "o4-preview", "OpenAI-x"])
def test_assert_independent_judge_rejects_openai_family_names(openai_name):
    with pytest.raises(ModelConfigError):
        assert_independent_judge("gpt-5.2", openai_name)


def test_require_independent_clients_rejects_the_same_object_twice():
    """A programmatic caller passing one client as both must be caught."""

    class _Stub:
        model = "same-model"

    only_one = _Stub()
    with pytest.raises(ModelConfigError) as exc:
        require_independent_clients(only_one, only_one)
    assert "self-assessment" in str(exc.value)


def test_require_independent_clients_allows_two_distinct_stubs():
    """Distinct offline stubs sharing a default model id are fine (config
    already vets production ids); only object identity is the use-time bug."""

    class _Stub:
        def __init__(self, model):
            self.model = model

    # Even sharing a model string, two distinct objects pass the use-time guard.
    require_independent_clients(_Stub("fake-model"), _Stub("fake-model"))


def test_public_dict_never_leaks_keys():
    cfg = load_model_config(dict(FULL_ENV))
    public = cfg.as_public_dict()
    assert "sk-fake" not in str(public) and "sk-ant-fake" not in str(public)
    # Efforts are public config (spec F D-F22), not keys, so they belong here too.
    assert set(public) == {"generator_model", "judge_model", "generator_effort", "judge_effort"}


def test_effort_levels_are_the_closed_vocabulary():
    from tere4ai.judge.config import EFFORT_LEVELS
    assert EFFORT_LEVELS == ("low", "medium", "high", "xhigh", "max")


def test_efforts_load_and_are_public():
    cfg = load_model_config(dict(FULL_ENV))
    assert cfg.generator_effort == "xhigh" and cfg.judge_effort == "xhigh"
    assert cfg.as_public_dict() == {
        "generator_model": "gpt-test-pinned", "judge_model": "claude-test-pinned",
        "generator_effort": "xhigh", "judge_effort": "xhigh",
    }


def test_missing_effort_is_listed_with_the_other_missing_variables():
    env = dict(FULL_ENV)
    env.pop("TERE4AI_JUDGE_EFFORT")
    env["TERE4AI_GENERATOR_EFFORT"] = ""
    env.pop("OPENAI_API_KEY")
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env)
    msg = str(exc.value)
    assert "TERE4AI_JUDGE_EFFORT" in msg and "TERE4AI_GENERATOR_EFFORT" in msg and "OPENAI_API_KEY" in msg


def test_effort_outside_the_vocabulary_is_refused_by_name():
    env = dict(FULL_ENV)
    env["TERE4AI_JUDGE_EFFORT"] = "extra-high"
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env)
    msg = str(exc.value)
    assert "TERE4AI_JUDGE_EFFORT" in msg and "extra-high" in msg and "low, medium, high, xhigh, max" in msg

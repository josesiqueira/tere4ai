"""Tests for DEC-07 model configuration and the declared model parameters
(spec F D-F29); no real keys, no network."""

import json
from pathlib import Path

import pytest
from tests.fixtures.model_parameters import declared, table, write_table

from tere4ai.judge import config as config_module
from tere4ai.judge.config import (
    ConfigurationError,
    ModelConfig,
    ModelConfigError,
    assert_independent_judge,
    declaration_for,
    load_model_config,
    load_model_parameters,
    require_independent_clients,
    runtime_judge_declaration,
)

ROOT = Path(__file__).resolve().parents[2]

# B99 (spec F D-F29): the efforts left the environment for the declared table.
FULL_ENV = {
    "TERE4AI_GENERATOR_MODEL": "gpt-test-pinned",
    "TERE4AI_JUDGE_MODEL": "claude-test-pinned",
    "OPENAI_API_KEY": "sk-fake",
    "ANTHROPIC_API_KEY": "sk-ant-fake",
}


@pytest.fixture
def table_path(tmp_path):
    return write_table(tmp_path / "model_parameters.json",
                       declared("gpt-test-pinned", "openai", temperature="N/A"),
                       declared("claude-test-pinned", "anthropic"))


def _refusal(env, path) -> str:
    with pytest.raises(ConfigurationError) as exc:
        load_model_config(env, parameters_path=path)
    message = str(exc.value)
    assert message.startswith("configuration error: ")
    return message


def test_valid_config_loads(table_path):
    cfg = load_model_config(dict(FULL_ENV), parameters_path=table_path)
    assert isinstance(cfg, ModelConfig)
    assert cfg.generator_model == "gpt-test-pinned"
    assert cfg.judge_model == "claude-test-pinned"


def test_missing_vars_fail_fast_and_list_all(table_path):
    env = dict(FULL_ENV)
    env.pop("ANTHROPIC_API_KEY")
    env["TERE4AI_JUDGE_MODEL"] = ""
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env, parameters_path=table_path)
    msg = str(exc.value)
    assert "ANTHROPIC_API_KEY" in msg and "TERE4AI_JUDGE_MODEL" in msg


def test_same_family_judge_rejected(table_path):
    env = dict(FULL_ENV)
    env["TERE4AI_JUDGE_MODEL"] = "gpt-5.2"
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env, parameters_path=table_path)
    assert "independent" in str(exc.value)


def test_same_model_id_for_generator_and_judge_rejected(table_path):
    """The generator judging its own output collapses the control (DEC-07)."""
    env = dict(FULL_ENV)
    env["TERE4AI_GENERATOR_MODEL"] = "claude-test-pinned"
    env["TERE4AI_JUDGE_MODEL"] = "claude-test-pinned"
    with pytest.raises(ModelConfigError) as exc:
        load_model_config(env, parameters_path=table_path)
    assert "same" in str(exc.value).lower() or "judging its own" in str(exc.value)


def test_assert_independent_judge_accepts_a_distinct_non_openai_judge():
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

    require_independent_clients(_Stub("fake-model"), _Stub("fake-model"))


def test_effort_levels_are_the_closed_vocabulary():
    from tere4ai.judge.config import EFFORT_LEVELS
    assert EFFORT_LEVELS == ("low", "medium", "high", "xhigh", "max")


# B99 (spec F D-F29): the declared table, keyed by model id, selects nothing.


def test_the_public_dict_carries_the_declared_values_and_their_digest_never_a_key(table_path):
    public = load_model_config(dict(FULL_ENV), parameters_path=table_path).as_public_dict()
    assert "sk-fake" not in str(public) and "sk-ant-fake" not in str(public)
    assert {k: v for k, v in public.items() if k != "model_parameters_sha256"} == {
        "generator_model": "gpt-test-pinned", "judge_model": "claude-test-pinned",
        "generator_effort": "xhigh", "judge_effort": "xhigh",
        "generator_temperature": "N/A", "judge_temperature": "0", "generator_json_mode": "sent",
    }
    assert len(public["model_parameters_sha256"]) == 64


def test_a_configured_model_without_a_row_is_refused_naming_both_components(tmp_path):
    message = _refusal(dict(FULL_ENV), write_table(tmp_path / "empty.json"))
    assert "declares no row for model 'gpt-test-pinned'" in message
    assert "declares no row for model 'claude-test-pinned'" in message


def test_a_row_without_its_documentation_page_or_day_is_refused(tmp_path):
    rows = table(declared("gpt-test-pinned", "openai"), declared("claude-test-pinned", "anthropic"))
    rows["models"]["claude-test-pinned"]["documentation"] = {"url": None, "read_on": None}
    rows["models"]["gpt-test-pinned"]["documentation"] = {"url": "http://docs.example.invalid", "read_on": "27.9.2026"}
    path = tmp_path / "nodoc.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    message = _refusal(dict(FULL_ENV), path)
    assert "the row for 'claude-test-pinned' in nodoc.json names no documentation page (https)" in message
    assert "the row for 'gpt-test-pinned'" in message


@pytest.mark.parametrize(("url", "read_on"), [
    ("https://docs.example.invalid/models", "2026-W39-1"),  # a week date Python reads as 2026-09-21
    ("https://docs.example.invalid/models", "20260927"),
    ("https://", "2026-09-27"),  # no host
    ("https:///models", "2026-09-27"),
    ("https://[docs.example", "2026-09-27"),  # urlsplit raises ValueError: refused by name, never a bare error
])
def test_a_week_date_or_a_page_without_a_host_is_refused(tmp_path, url, read_on):
    """B99 final review (ruling P2): the row names a page with a host and the
    day it was read as YYYY-MM-DD, nothing else."""
    rows = table(declared("gpt-test-pinned", "openai"), declared("claude-test-pinned", "anthropic"))
    rows["models"]["claude-test-pinned"]["documentation"] = {"url": url, "read_on": read_on}
    path = tmp_path / "baddoc.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    message = _refusal(dict(FULL_ENV), path)
    assert "the row for 'claude-test-pinned' in baddoc.json names no documentation page (https)" in message
    assert "'gpt-test-pinned'" not in message


def test_a_model_config_whose_rows_name_other_models_or_backends_is_refused():
    """B99 final review: a client never sends one model's id with another
    model's declaration, nor a row of the other inference backend."""
    def build(generator_row, judge_row):
        return ModelConfig(generator_model="gpt-a", judge_model="claude-a", generator_api_key="k1",
                           judge_api_key="k2", generator_parameters=generator_row, judge_parameters=judge_row)

    assert build(declared("gpt-a", "openai"), declared("claude-a", "anthropic")).generator_model == "gpt-a"
    with pytest.raises(ConfigurationError, match=r"^configuration error: the generator model 'gpt-a' is given "
                       r"the declared row of 'gpt-b'"):
        build(declared("gpt-b", "openai"), declared("claude-a", "anthropic"))
    with pytest.raises(ConfigurationError, match=r"the judge model 'claude-a' is given the declared row of "
                       r"'claude-b'"):
        build(declared("gpt-a", "openai"), declared("claude-b", "anthropic"))
    with pytest.raises(ConfigurationError, match=r"the judge row for 'claude-a' names inference backend openai, but the "
                       r"judge client is anthropic"):
        build(declared("gpt-a", "openai"), declared("claude-a", "openai"))


def test_every_malformed_row_is_named_at_once(tmp_path):
    rows = table(declared("gpt-test-pinned", "openai"), declared("claude-test-pinned", "anthropic"))
    rows["models"]["x"] = {"inference_backend": "mistral", "temperature": 0, "effort": "extra-high", "json_mode": "sent",
                           "documentation": {}, "colour": 1}
    rows["models"]["y"] = {**declared("y", "anthropic").as_row(), "json_mode": "sent"}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    message = _refusal(dict(FULL_ENV), path)
    for piece in ("x: unknown colour", "x: inference_backend must be one of openai, anthropic",
                  'x: temperature must be "0" or "N/A"', "x: effort must be one of low, medium, high, xhigh, max",
                  "x: documentation must be", 'y: json_mode must be "N/A" on an anthropic row'):
        assert piece in message


def test_a_row_of_the_other_backend_is_refused(tmp_path):
    path = write_table(tmp_path / "swap.json", declared("gpt-test-pinned", "anthropic"),
                       declared("claude-test-pinned", "anthropic"))
    assert ("swap.json declares 'gpt-test-pinned' with inference backend anthropic, but the openai client is "
            "configured to use it" in _refusal(dict(FULL_ENV), path))


def test_a_missing_or_unreadable_table_is_refused(tmp_path):
    assert "nope.json is missing" in _refusal(dict(FULL_ENV), tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert "broken.json cannot be read (JSONDecodeError)" in _refusal(dict(FULL_ENV), broken)


def test_the_retired_effort_variables_are_refused_by_name(table_path):
    message = _refusal({**FULL_ENV, "TERE4AI_JUDGE_EFFORT": "xhigh"}, table_path)
    assert message == ("configuration error: TERE4AI_JUDGE_EFFORT is no longer read: each model's effort is declared "
                       "in config/model_parameters.json (spec F D-F29); remove the line from .env and from the environment")


def test_the_runtime_judge_declaration_reports_a_retired_effort_variable(table_path):
    """Review B101 3A-M11: a retired effort line refuses every paid path, so the
    health answer says so instead of a clean declaration."""
    answer = runtime_judge_declaration("claude-test-pinned", table_path, env={"TERE4AI_GENERATOR_EFFORT": "xhigh"})
    assert answer == {"model": "claude-test-pinned", "effort": None, "temperature": None, "declaration_error": (
        "configuration error: TERE4AI_GENERATOR_EFFORT is no longer read: each model's effort is declared in "
        "config/model_parameters.json (spec F D-F29); remove the line from .env and from the environment")}
    assert runtime_judge_declaration("claude-test-pinned", table_path, env={}) == {
        "model": "claude-test-pinned", "effort": "xhigh", "temperature": "0", "declaration_error": None}


def test_the_digest_follows_the_rows_in_use_and_no_other(tmp_path, table_path):
    base = load_model_config(dict(FULL_ENV), parameters_path=table_path).model_parameters_sha256
    more = write_table(tmp_path / "more.json", declared("gpt-test-pinned", "openai", temperature="N/A"),
                       declared("claude-test-pinned", "anthropic"), declared("claude-other", "anthropic", effort="low"))
    changed = write_table(tmp_path / "changed.json", declared("gpt-test-pinned", "openai", temperature="N/A"),
                          declared("claude-test-pinned", "anthropic", effort="high"))
    assert load_model_config(dict(FULL_ENV), parameters_path=more).model_parameters_sha256 == base
    assert load_model_config(dict(FULL_ENV), parameters_path=changed).model_parameters_sha256 != base


def test_the_committed_table_is_well_formed_and_declares_the_models_of_env_example():
    """The repository's own table loads, and holds a row, with the right
    inference backend, for each model .env.example names. Both rows name the
    model developer's page they were read from and the day (plan ruling P3): declaration_for,
    the check every paid path makes, accepts them (review B101 3A-M5)."""
    models = load_model_parameters()
    root = config_module.MODEL_PARAMETERS_PATH.parents[1]
    named = dict(line.split("=", 1) for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
                 if line.startswith("TERE4AI_") and "=" in line)
    assert models[named["TERE4AI_GENERATOR_MODEL"]]["inference_backend"] == "openai"
    assert models[named["TERE4AI_JUDGE_MODEL"]]["inference_backend"] == "anthropic"
    for variable, inference_backend in (("TERE4AI_GENERATOR_MODEL", "openai"), ("TERE4AI_JUDGE_MODEL", "anthropic")):
        row = declaration_for(models, named[variable], inference_backend)
        assert row.documentation_url.startswith("https://") and len(row.documentation_read_on) == 10


def test_a_row_names_its_inference_backend_and_its_model_developer_follows():
    from tere4ai.judge.config import model_developer_of
    rows = json.loads((ROOT / "config" / "model_parameters.json").read_text(encoding="utf-8"))["models"]
    assert all("inference_backend" in r and "provider" not in r for r in rows.values())
    assert {model_developer_of(r["inference_backend"]) for r in rows.values()} <= {"anthropic", "openai"}
    with pytest.raises(ValueError, match="no model developer known for the inference backend 'bedrock'"):
        model_developer_of("bedrock")

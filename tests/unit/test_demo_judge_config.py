"""DEC-24 (spec G D-G74 (2), (3), (5)): each facade route loads only what it
calls: the generator-only mode, the demo judge and the signing key, each
without DEC-07's Anthropic judge. No real key, no network."""

import json

import pytest
from tests.fixtures.model_parameters import declared, write_table

from tere4ai.extract_norms.model_clients import OpenAIDemoJudge, OpenAIGenerator
from tere4ai.judge.config import (
    ConfigurationError,
    DemoJudgeConfig,
    GeneratorConfig,
    ModelConfigError,
    load_demo_judge_config,
    load_generator_config,
    load_model_parameters,
    load_model_prices,
    load_signing_key,
    route_readiness,
)

KEY = "a" * 64
ENV = {"TERE4AI_GENERATOR_MODEL": "gpt-gen", "TERE4AI_DEMO_JUDGE_MODEL": "gpt-judge", "OPENAI_API_KEY": "sk-fake",
       "TERE4AI_ANSWER_SIGNING_KEY": KEY}


def _price_row(inference_backend: str = "openai") -> dict:
    return {"inference_backend": inference_backend, "currency": "USD", "input": "2.00", "output": "10.00", "batch_input": "1.00",
            "batch_output": "5.00", "pricing": {"url": "https://example.invalid/p", "read_on": "2026-10-06"}}


@pytest.fixture
def paths(tmp_path):
    parameters = write_table(tmp_path / "model_parameters.json", declared("gpt-gen", "openai", temperature="N/A"),
                             declared("gpt-judge", "openai", temperature="N/A"))
    prices = tmp_path / "model_prices.json"
    prices.write_text(json.dumps({"schema_version": 1, "models": {"gpt-judge": _price_row()}}), encoding="utf-8")
    return parameters, prices


def test_the_generator_alone_loads_without_any_anthropic_setting(paths):
    cfg = load_generator_config(dict(ENV), paths[0])
    assert isinstance(cfg, GeneratorConfig)
    assert (cfg.generator_model, cfg.generator_parameters.inference_backend) == ("gpt-gen", "openai")


def test_the_generator_alone_names_what_is_missing():
    with pytest.raises(ModelConfigError, match="OPENAI_API_KEY"):
        load_generator_config({"TERE4AI_GENERATOR_MODEL": "gpt-gen"})


def test_the_demo_judge_loads_with_its_declared_row_and_its_price(paths):
    cfg = load_demo_judge_config(dict(ENV), *paths)
    assert isinstance(cfg, DemoJudgeConfig)
    assert (cfg.model, cfg.parameters.inference_backend, cfg.price["input"]) == ("gpt-judge", "openai", 2.0)


def test_the_demo_judge_is_never_the_generator(paths):
    with pytest.raises(ModelConfigError, match="the generator's model"):
        load_demo_judge_config({**ENV, "TERE4AI_DEMO_JUDGE_MODEL": "GPT-GEN"}, *paths)


def test_the_demo_judge_needs_an_openai_row_and_a_price_row(tmp_path, paths):
    anthropic_row = write_table(tmp_path / "other.json", declared("gpt-judge", "anthropic"))
    with pytest.raises(ConfigurationError, match="inference backend anthropic"):
        load_demo_judge_config(dict(ENV), anthropic_row, paths[1])
    no_price = tmp_path / "prices.json"
    no_price.write_text(json.dumps({"schema_version": 1, "models": {}}), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="no price row for the demo judge 'gpt-judge'"):
        load_demo_judge_config(dict(ENV), paths[0], no_price)


@pytest.mark.parametrize("value", ["", "a" * 63, "g" * 64, "a" * 65])
def test_the_signing_key_is_64_hexadecimal_characters(value):
    with pytest.raises(ModelConfigError, match="TERE4AI_ANSWER_SIGNING_KEY"):
        load_signing_key({"TERE4AI_ANSWER_SIGNING_KEY": value})
    assert load_signing_key({"TERE4AI_ANSWER_SIGNING_KEY": KEY}) == bytes.fromhex(KEY)


def test_readiness_names_each_route_apart_and_never_the_key(paths):
    ready = route_readiness(dict(ENV), *paths)
    assert ready["generator_only"]["ready"] and ready["demo_judge"]["ready"]
    assert ready["signing_key"] == {"present": True, "error": None}
    assert KEY not in json.dumps(ready)
    broken = route_readiness({**ENV, "TERE4AI_ANSWER_SIGNING_KEY": "short", "TERE4AI_DEMO_JUDGE_MODEL": "gpt-gen"}, *paths)
    assert broken["generator_only"]["ready"] is True
    assert broken["demo_judge"]["ready"] is False and "generator's model" in broken["demo_judge"]["declaration_error"]
    assert broken["signing_key"]["present"] is True and "64 hexadecimal" in broken["signing_key"]["error"]
    assert "short" not in json.dumps(broken)


def test_the_demo_judge_client_is_an_openai_client_built_from_its_own_configuration(paths, monkeypatch):
    import sys
    import types

    built = {}
    fake = types.ModuleType("openai")
    fake.OpenAI = lambda **kwargs: built.update(kwargs) or object()
    monkeypatch.setitem(sys.modules, "openai", fake)
    client = OpenAIDemoJudge(load_demo_judge_config(dict(ENV), *paths))
    assert isinstance(client, OpenAIGenerator)
    assert (client.model, client.inference_backend, client.effort) == ("gpt-judge", "openai", "xhigh")
    assert built == {"api_key": "sk-fake", "max_retries": 0}


def test_the_committed_tables_declare_gpt_6_sol_as_the_spec_quotes_it():
    row = load_model_parameters()["gpt-6-sol"]
    assert (row["inference_backend"], row["temperature"], row["effort"], row["json_mode"]) == ("openai", "N/A", "xhigh", "sent")
    # Ruling R80: the day the page was read, 2026-10-06 or later, never a fixed date.
    assert row["documentation"]["url"] == "https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-sol"
    assert row["documentation"]["read_on"] >= "2026-10-06"
    price = load_model_prices()["gpt-6-sol"]
    assert (price["input"], price["output"], price["batch_input"], price["batch_output"]) == (2.0, 10.0, 1.0, 5.0)

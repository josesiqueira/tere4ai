"""Provider-reported usage accounting on the model clients (Section 13).

Offline: instances are built without SDK construction and given stub
transport clients, so no network and no keys are involved.
"""

from __future__ import annotations

from types import SimpleNamespace

from tere4ai.extract_norms.model_clients import (
    AnthropicJudge,
    OpenAIGenerator,
    _new_usage,
)


def _openai_response(content: str, prompt_tokens=None, completion_tokens=None):
    usage = None
    if prompt_tokens is not None:
        usage = SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def _generator_with(responses: list) -> OpenAIGenerator:
    gen = OpenAIGenerator.__new__(OpenAIGenerator)
    gen.model = "stub-generator"
    gen.usage = _new_usage()
    queue = list(responses)
    gen._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: queue.pop(0))
        )
    )
    return gen


def test_generator_accumulates_provider_counts():
    gen = _generator_with(
        [_openai_response("a", 100, 20), _openai_response("b", 50, 5)]
    )
    assert gen.complete("s", "u") == "a"
    assert gen.complete("s", "u") == "b"
    assert gen.usage == {"calls": 2, "input_tokens": 150, "output_tokens": 25}


def test_generator_without_usage_block_counts_only_the_call():
    gen = _generator_with([_openai_response("a")])
    gen.complete("s", "u")
    assert gen.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0}


def _anthropic_response(text: str, input_tokens=None, output_tokens=None):
    usage = None
    if input_tokens is not None:
        usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], usage=usage
    )


def _judge_with(responses: list) -> AnthropicJudge:
    judge = AnthropicJudge.__new__(AnthropicJudge)
    judge.model = "stub-judge"
    judge.usage = _new_usage()
    judge._max_tokens = 16
    queue = list(responses)
    judge._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: queue.pop(0))
    )
    return judge


def test_judge_accumulates_provider_counts():
    judge = _judge_with(
        [_anthropic_response("v", 200, 40), _anthropic_response("w", 10, 1)]
    )
    assert judge.complete("s", "u") == "v"
    assert judge.complete("s", "u") == "w"
    assert judge.usage == {"calls": 2, "input_tokens": 210, "output_tokens": 41}


def test_judge_without_usage_block_counts_only_the_call():
    judge = _judge_with([_anthropic_response("v")])
    judge.complete("s", "u")
    assert judge.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0}

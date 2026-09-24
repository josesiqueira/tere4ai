"""Provider-reported usage accounting on the model clients (Section 13).

Offline: instances are built without SDK construction and given stub
transport clients, so no network and no keys are involved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tere4ai.extract_norms.model_clients import (
    EFFORT_MIXED,
    EFFORT_NONE,
    EFFORT_NOT_APPLICABLE,
    EFFORT_NOT_CONFIGURED,
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


# B74: current-generation models reject sampling parameters. A rejection is
# learned once per client (never one wasted request per call), JSON mode
# survives a temperature rejection, and the client reports what it actually
# sent in the same vocabulary the dashboard's judge records.


class _Rejecting:
    """Stub transport: raises the given message when a listed kwarg is sent."""

    def __init__(self, reject: dict[str, str], response):
        self.reject = reject
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        for key, message in self.reject.items():
            if key in kwargs:
                raise RuntimeError(message)
        return self.response


def _generator_over(transport: _Rejecting) -> OpenAIGenerator:
    gen = OpenAIGenerator.__new__(OpenAIGenerator)
    gen.model = "stub-generator"
    gen.usage = _new_usage()
    gen._init_sampling()
    gen._client = SimpleNamespace(chat=SimpleNamespace(completions=transport))
    return gen


def _judge_over(transport: _Rejecting) -> AnthropicJudge:
    judge = AnthropicJudge.__new__(AnthropicJudge)
    judge.model = "stub-judge"
    judge.usage = _new_usage()
    judge._max_tokens = 16
    judge._init_sampling()
    judge._client = SimpleNamespace(messages=transport)
    return judge


def test_generator_sends_temperature_zero_and_json_mode_by_default():
    transport = _Rejecting({}, _openai_response('{"ok": true}', 1, 1))
    gen = _generator_over(transport)
    gen.complete("s", "u")
    assert transport.calls[0]["temperature"] == 0
    assert transport.calls[0]["response_format"] == {"type": "json_object"}
    assert gen.sampling == "0"


def test_generator_keeps_json_mode_when_only_temperature_is_rejected():
    transport = _Rejecting(
        {"temperature": "Unsupported value: 'temperature' does not support 0 with this model."},
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    assert gen.complete("s", "u") == '{"ok": true}'
    assert "temperature" not in transport.calls[-1]
    assert transport.calls[-1]["response_format"] == {"type": "json_object"}
    assert gen.sampling == "provider default (rejected by the model)"


def test_generator_learns_the_rejection_once():
    transport = _Rejecting(
        {"temperature": "temperature is not supported"}, _openai_response("x", 1, 1)
    )
    gen = _generator_over(transport)
    gen.complete("s", "u")
    gen.complete("s", "u")
    gen.complete("s", "u")
    # one rejected attempt, then one clean call per complete(): 4, not 6
    assert len(transport.calls) == 4
    assert all("temperature" not in call for call in transport.calls[1:])
    assert gen.usage["calls"] == 3


def test_generator_drops_json_mode_only_when_the_model_rejects_it():
    transport = _Rejecting(
        {"response_format": "response_format is not supported"}, _openai_response("x", 1, 1)
    )
    gen = _generator_over(transport)
    gen.complete("s", "u")
    assert "response_format" not in transport.calls[-1]
    assert transport.calls[-1]["temperature"] == 0


def test_generator_reraises_any_other_error():
    transport = _Rejecting({"model": "invalid api key"}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    try:
        gen.complete("s", "u")
    except RuntimeError as exc:
        assert "invalid api key" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unrelated provider error must propagate")
    assert len(transport.calls) == 1


def test_generator_sampling_is_mixed_when_a_rejection_arrives_mid_run():
    transport = _Rejecting({}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    gen.complete("s", "u")
    transport.reject = {"temperature": "temperature unsupported"}
    gen.complete("s", "u")
    assert gen.sampling == "mixed"


def test_sampling_before_any_reply_is_no_replies():
    gen = _generator_over(_Rejecting({}, _openai_response("x")))
    assert gen.sampling == "no replies"


def test_judge_default_output_cap_leaves_room_for_thinking():
    import inspect

    default = inspect.signature(AnthropicJudge.__init__).parameters["max_tokens"].default
    assert default >= 16000


def test_judge_learns_a_temperature_rejection_once_and_reports_it():
    transport = _Rejecting(
        {"temperature": "Messages.create() got an unexpected keyword argument 'temperature'"},
        _anthropic_response("v", 2, 1),
    )
    judge = _judge_over(transport)
    assert judge.complete("s", "u") == "v"
    assert judge.complete("s", "u") == "v"
    assert len(transport.calls) == 3
    assert "temperature" not in transport.calls[-1]
    assert transport.calls[-1]["max_tokens"] == 16
    assert judge.sampling == "provider default (rejected by the model)"
    assert judge.usage["calls"] == 2


def test_judge_reports_temperature_zero_when_accepted():
    transport = _Rejecting({}, _anthropic_response("v", 2, 1))
    judge = _judge_over(transport)
    judge.complete("s", "u")
    assert transport.calls[0]["temperature"] == 0
    assert judge.sampling == "0"


def test_judge_reads_only_text_blocks_past_a_thinking_block():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text='{"verdict": "accepted"}'),
        ],
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )
    judge = _judge_over(_Rejecting({}, response))
    assert judge.complete("s", "u") == '{"verdict": "accepted"}'


# B84 (spec F D-F22): every client sends the configured effort and learns a
# rejection once, like temperature; the outcome is reported in the same
# vocabulary so a manifest states the effort regime, never assumes it.


def test_generator_sends_the_configured_effort_and_reports_it():
    transport = _Rejecting({}, _openai_response('{"ok": true}', 1, 1))
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    assert gen.effort == EFFORT_NONE
    gen.complete("s", "u")
    assert transport.calls[0]["reasoning_effort"] == "xhigh"
    assert gen.effort == "xhigh" and gen.effort_requested == "xhigh"


def test_generator_learns_a_rejected_effort_once_and_keeps_temperature():
    transport = _Rejecting(
        {"reasoning_effort": "Unsupported parameter: 'reasoning_effort' is not supported with this model."},
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    gen.complete("s", "u")
    gen.complete("s", "u")
    assert len(transport.calls) == 3
    assert "reasoning_effort" in transport.calls[0]
    assert "reasoning_effort" not in transport.calls[1] and "reasoning_effort" not in transport.calls[2]
    assert transport.calls[2]["temperature"] == 0
    assert gen.effort == EFFORT_NOT_APPLICABLE


def test_generator_rejecting_both_temperature_and_effort_learns_both_in_three_requests():
    transport = _Rejecting(
        {"temperature": "temperature does not support 0 with this model",
         "reasoning_effort": "Unsupported parameter: 'reasoning_effort'"},
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    assert gen.complete("s", "u") == '{"ok": true}'
    assert len(transport.calls) == 3
    assert "temperature" not in transport.calls[2] and "reasoning_effort" not in transport.calls[2]
    assert gen.sampling.startswith("provider default") and gen.effort == EFFORT_NOT_APPLICABLE


def test_generator_does_not_learn_a_parameter_it_did_not_send():
    # The message names temperature, but only the effort was in the request
    # (temperature already learned): nothing to learn, the error propagates.
    transport = _Rejecting({"reasoning_effort": "temperature is invalid"}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    gen._temperature_rejected = True
    with pytest.raises(RuntimeError):
        gen.complete("s", "u")
    assert len(transport.calls) == 1


def test_generator_without_effort_config_sends_none_and_says_so():
    transport = _Rejecting({}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    gen.complete("s", "u")
    assert "reasoning_effort" not in transport.calls[0]
    assert gen.effort == EFFORT_NOT_CONFIGURED


def test_judge_sends_the_effort_in_output_config_and_reports_it():
    transport = _Rejecting({}, _anthropic_response("v", 1, 1))
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    judge.complete("s", "u")
    assert transport.calls[0]["output_config"] == {"effort": "xhigh"}
    assert transport.calls[0]["temperature"] == 0
    assert judge.effort == "xhigh"


def test_judge_learns_a_rejected_effort_once():
    transport = _Rejecting({"output_config": "output_config.effort: this model does not support effort"},
                           _anthropic_response("v", 1, 1))
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    judge.complete("s", "u")
    judge.complete("s", "u")
    assert len(transport.calls) == 3
    assert "output_config" not in transport.calls[1] and "output_config" not in transport.calls[2]
    assert judge.effort == EFFORT_NOT_APPLICABLE


def test_judge_rejecting_both_learns_both_in_three_requests():
    transport = _Rejecting(
        {"temperature": "temperature: extra inputs are not permitted",
         "output_config": "effort is not supported"},
        _anthropic_response("v", 1, 1),
    )
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    assert judge.complete("s", "u") == "v"
    assert len(transport.calls) == 3
    assert "temperature" not in transport.calls[2] and "output_config" not in transport.calls[2]
    assert judge.sampling.startswith("provider default") and judge.effort == EFFORT_NOT_APPLICABLE


def test_effort_mixed_when_replies_differ():
    transport = _Rejecting({}, _anthropic_response("v", 1, 1))
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    judge.complete("s", "u")
    judge._effort_rejected = True  # a provider that changes mid-lifetime, recorded, never assumed away
    judge.complete("s", "u")
    assert judge.effort == EFFORT_MIXED


def test_generator_rejecting_all_three_parameters_learns_all_three_in_four_requests():
    transport = _Rejecting(
        {"temperature": "temperature does not support 0 with this model",
         "response_format": "response_format is not supported",
         "reasoning_effort": "Unsupported parameter: 'reasoning_effort'"},
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    assert gen.complete("s", "u") == '{"ok": true}'
    assert len(transport.calls) == 4
    assert not ({"temperature", "response_format", "reasoning_effort"} & set(transport.calls[3]))

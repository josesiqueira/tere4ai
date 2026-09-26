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
    # B91: the usage record also counts requests sent and replies with usage
    assert gen.usage == {"calls": 2, "input_tokens": 150, "output_tokens": 25,
                         "requests_sent": 2, "replies_with_usage": 2}


def test_generator_without_usage_block_counts_only_the_call():
    gen = _generator_with([_openai_response("a")])
    gen.complete("s", "u")
    # B91: the usage record also counts requests sent and replies with usage
    # (no usage block: sent and answered, but not reported)
    assert gen.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                         "requests_sent": 1, "replies_with_usage": 0}


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
    # B91: the usage record also counts requests sent and replies with usage
    assert judge.usage == {"calls": 2, "input_tokens": 210, "output_tokens": 41,
                           "requests_sent": 2, "replies_with_usage": 2}


def test_judge_without_usage_block_counts_only_the_call():
    judge = _judge_with([_anthropic_response("v")])
    judge.complete("s", "u")
    # B91: the usage record also counts requests sent and replies with usage
    # (no usage block: sent and answered, but not reported)
    assert judge.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                           "requests_sent": 1, "replies_with_usage": 0}


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


# B84 fix wave G5: pin Review Focus 1 and 2 (a rejection that names no
# carried parameter propagates; "model" is always in kwargs and is never
# learnable) on the judge's loop too, and the generator's fourth attempt.


def test_judge_propagates_when_the_rejection_names_no_carried_parameter():
    """Review Focus 1, judge side: effort is already learned rejected, so
    output_config is not sent; the rejection message names 'effort', not
    the temperature that was actually carried, so nothing is learnable and
    the error propagates on the first call."""
    transport = _Rejecting(
        {"temperature": "effort is not supported"}, _anthropic_response("v", 1, 1)
    )
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    judge._effort_rejected = True
    with pytest.raises(RuntimeError):
        judge.complete("s", "u")
    assert len(transport.calls) == 1


def test_judge_propagates_on_the_third_call_when_a_third_parameter_is_rejected():
    """Review Focus 2, judge side: 'model' is always present in kwargs (it
    names the request, never a learnable sampling or effort parameter), so
    once temperature and effort are both learned rejected, a rejection
    naming 'model' on the loop's last attempt propagates rather than
    retrying forever."""
    transport = _Rejecting(
        {"temperature": "temperature: extra inputs are not permitted",
         "output_config": "effort is not supported",
         "model": "rate limited"},
        _anthropic_response("v", 1, 1),
    )
    judge = _judge_over(transport)
    judge._init_effort("xhigh")
    with pytest.raises(RuntimeError) as exc_info:
        judge.complete("s", "u")
    assert "rate limited" in str(exc_info.value)
    assert len(transport.calls) == 3


def test_generator_learns_the_sdks_real_value_level_effort_rejection():
    """B84 fix wave G6: pin the SDK's real rejection shape (verified against
    the OpenAI SDK reference 2026-09-24), a value-level 400 naming the param
    inside a nested error object, not a bare 'not supported' sentence. The
    'reasoning_effort' param name substring must still be found and learned."""
    transport = _Rejecting(
        {
            "reasoning_effort": (
                "Error code: 400 - {'error': {'message': \"Invalid value: "
                "'xhigh'. Supported values are: 'low', 'medium', and "
                "'high'.\", 'type': 'invalid_request_error', 'param': "
                "'reasoning_effort', 'code': 'invalid_value'}}"
            )
        },
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    gen.complete("s", "u")
    assert len(transport.calls) == 2
    assert "reasoning_effort" not in transport.calls[-1]
    assert gen.effort == EFFORT_NOT_APPLICABLE


def test_generator_propagates_on_the_fourth_call_when_a_fourth_parameter_is_rejected():
    """Review Focus 2, generator side: the same 'model is always present'
    shape, one attempt longer because the generator has three learnable
    parameters (temperature, response_format, reasoning_effort)."""
    transport = _Rejecting(
        {"temperature": "temperature does not support 0 with this model",
         "response_format": "response_format is not supported",
         "reasoning_effort": "Unsupported parameter: 'reasoning_effort'",
         "model": "rate limited"},
        _openai_response('{"ok": true}', 1, 1),
    )
    gen = _generator_over(transport)
    gen._init_effort("xhigh")
    with pytest.raises(RuntimeError) as exc_info:
        gen.complete("s", "u")
    assert "rate limited" in str(exc_info.value)
    assert len(transport.calls) == 4


# B91 (spec F D-F26 (g)): a total must tell complete from incomplete, so the
# clients count the requests they sent and the replies that reported usage.


def test_generator_counts_a_request_that_raises_after_send():
    transport = _Rejecting({"model": "503 upstream overloaded"}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    with pytest.raises(RuntimeError, match="overloaded"):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1 and gen.usage["replies_with_usage"] == 0
    assert gen.usage["calls"] == 0


def test_judge_counts_a_request_that_raises_after_send():
    transport = _Rejecting({"model": "529 overloaded"}, _anthropic_response("v", 2, 1))
    judge = _judge_over(transport)
    with pytest.raises(RuntimeError, match="overloaded"):
        judge.complete("s", "u")
    assert judge.usage["requests_sent"] == 1 and judge.usage["replies_with_usage"] == 0


def test_a_learned_rejection_is_not_a_request_sent():
    # the SDK or the model refused a parameter before any generation: nothing billed
    transport = _Rejecting({"temperature": "temperature is not supported"}, _openai_response("x", 1, 1))
    gen = _generator_over(transport)
    gen.complete("s", "u")
    assert len(transport.calls) == 2
    assert gen.usage["requests_sent"] == 1 and gen.usage["replies_with_usage"] == 1


def test_generator_counts_an_interrupted_request_as_sent():
    class _Interrupting:
        def create(self, **kwargs):
            raise KeyboardInterrupt
    gen = _generator_over(_Interrupting())
    with pytest.raises(KeyboardInterrupt):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1 and gen.usage["calls"] == 0


def test_a_usage_block_without_both_token_figures_is_not_a_reported_reply():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="a"))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=None),
    )
    gen = _generator_with([response])
    gen.complete("s", "u")
    assert gen.usage["replies_with_usage"] == 0 and gen.usage["input_tokens"] == 12
    assert gen.usage["requests_sent"] == 1


def test_usage_since_is_the_difference_and_none_without_a_record():
    from tere4ai.extract_norms.model_clients import usage_since, usage_snapshot

    gen = _generator_with([_openai_response("a", 100, 20), _openai_response("b", 50, 5)])
    gen.complete("s", "u")
    before = usage_snapshot(gen)
    gen.complete("s", "u")
    assert usage_since(gen, before) == {"calls": 1, "input_tokens": 50, "output_tokens": 5,
                                        "requests_sent": 1, "replies_with_usage": 1}
    assert usage_snapshot(object()) is None and usage_since(object(), None) is None


# Task 1a (B91, spec F D-F26 (e) and (g), ruling R3): the SDKs' hidden
# retries are off (max_retries=0 on both constructors), so the clients
# retry a transient failure themselves, counting every physical attempt as
# a request sent. Retryable (review fix F1): a numeric status_code of 408,
# 409, 429 or 5xx, or the SDK's connection/timeout error matched by class
# name (APIConnectionError, whose APITimeoutError subclass matches the same
# way), so the mixin never imports an SDK. The learned-rejection check
# above runs first and is never counted or retried; anything else not
# retryable raises after one attempt.


class _ProviderError(Exception):
    """Test double for the SDKs' APIStatusError: carries status_code and a
    response with headers, without importing either SDK."""

    def __init__(self, message: str, status_code: int | None = None,
                 headers: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {})


class APIConnectionError(Exception):
    """Test double named like the SDKs' connection error; the retry check
    matches by class name only (review fix F1), never by importing an SDK."""


class _Flaky:
    """Stub transport: replays a scripted sequence of exceptions and
    responses, one per physical attempt (a retry included)."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_generator_retries_a_429_then_succeeds():
    waits = []
    transport = _Flaky([_ProviderError("rate limited", status_code=429),
                        _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = waits.append
    assert gen.complete("s", "u") == "a"
    assert gen.usage["requests_sent"] == 2 and gen.usage["calls"] == 1
    assert waits == [1]


def test_generator_raises_after_three_consecutive_503s():
    waits = []
    transport = _Flaky([_ProviderError("upstream overloaded", status_code=503)] * 3)
    gen = _generator_over(transport)
    gen._wait = waits.append
    with pytest.raises(_ProviderError):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 3 and gen.usage["calls"] == 0
    assert waits == [1, 4]


def test_generator_does_not_retry_a_401():
    def refuse_to_wait(seconds):
        raise AssertionError("a 401 must not be retried")
    transport = _Flaky([_ProviderError("unauthorized", status_code=401)])
    gen = _generator_over(transport)
    gen._wait = refuse_to_wait
    with pytest.raises(_ProviderError):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1


def test_generator_waits_the_retry_after_header():
    waits = []
    transport = _Flaky([
        _ProviderError("rate limited", status_code=429, headers={"retry-after": "2"}),
        _openai_response("a", 1, 1),
    ])
    gen = _generator_over(transport)
    gen._wait = waits.append
    gen.complete("s", "u")
    assert waits == [2]


def test_generator_caps_the_retry_after_wait_at_sixty_seconds():
    waits = []
    transport = _Flaky([
        _ProviderError("rate limited", status_code=429, headers={"retry-after": "600"}),
        _openai_response("a", 1, 1),
    ])
    gen = _generator_over(transport)
    gen._wait = waits.append
    gen.complete("s", "u")
    assert waits == [60]


def test_generator_retries_a_connection_error_then_succeeds():
    transport = _Flaky([APIConnectionError("connection reset"),
                        _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = lambda seconds: None
    assert gen.complete("s", "u") == "a"
    assert gen.usage["requests_sent"] == 2 and gen.usage["calls"] == 1


def test_both_constructors_pass_max_retries_zero(monkeypatch):
    import anthropic
    import openai

    from tere4ai.judge.config import ModelConfig

    captured_openai: dict = {}
    captured_anthropic: dict = {}

    class _StubOpenAI:
        def __init__(self, **kwargs):
            captured_openai.update(kwargs)

    class _StubAnthropic:
        def __init__(self, **kwargs):
            captured_anthropic.update(kwargs)

    monkeypatch.setattr(openai, "OpenAI", _StubOpenAI)
    monkeypatch.setattr(anthropic, "Anthropic", _StubAnthropic)
    cfg = ModelConfig(
        generator_model="gpt-x", judge_model="claude-x",
        generator_api_key="k1", judge_api_key="k2",
        generator_effort="high", judge_effort="high",
    )
    OpenAIGenerator(cfg)
    AnthropicJudge(cfg)
    assert captured_openai["max_retries"] == 0
    assert captured_anthropic["max_retries"] == 0


# Same shapes for the judge; the transport is messages.create and usage
# reports input_tokens/output_tokens, but the retry classification and
# counting are the same mixin logic.


def test_judge_retries_a_429_then_succeeds():
    waits = []
    transport = _Flaky([_ProviderError("rate limited", status_code=429),
                        _anthropic_response("v", 2, 1)])
    judge = _judge_over(transport)
    judge._wait = waits.append
    assert judge.complete("s", "u") == "v"
    assert judge.usage["requests_sent"] == 2 and judge.usage["calls"] == 1
    assert waits == [1]


def test_judge_raises_after_three_consecutive_529s():
    waits = []
    transport = _Flaky([_ProviderError("overloaded", status_code=529)] * 3)
    judge = _judge_over(transport)
    judge._wait = waits.append
    with pytest.raises(_ProviderError):
        judge.complete("s", "u")
    assert judge.usage["requests_sent"] == 3 and judge.usage["calls"] == 0
    assert waits == [1, 4]


def test_judge_does_not_retry_a_401():
    def refuse_to_wait(seconds):
        raise AssertionError("a 401 must not be retried")
    transport = _Flaky([_ProviderError("unauthorized", status_code=401)])
    judge = _judge_over(transport)
    judge._wait = refuse_to_wait
    with pytest.raises(_ProviderError):
        judge.complete("s", "u")
    assert judge.usage["requests_sent"] == 1


def test_judge_waits_the_retry_after_header():
    waits = []
    transport = _Flaky([
        _ProviderError("rate limited", status_code=429, headers={"retry-after": "2"}),
        _anthropic_response("v", 2, 1),
    ])
    judge = _judge_over(transport)
    judge._wait = waits.append
    judge.complete("s", "u")
    assert waits == [2]


def test_judge_retries_a_connection_error_then_succeeds():
    transport = _Flaky([APIConnectionError("connection reset"),
                        _anthropic_response("v", 2, 1)])
    judge = _judge_over(transport)
    judge._wait = lambda seconds: None
    assert judge.complete("s", "u") == "v"
    assert judge.usage["requests_sent"] == 2 and judge.usage["calls"] == 1

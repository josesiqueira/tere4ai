"""Provider-reported usage accounting on the model clients (Section 13).

Offline: instances are built without SDK construction and given stub
transport clients, so no network and no keys are involved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from tests.fixtures.model_parameters import declared

from tere4ai.extract_norms.model_clients import (
    SERVICE_POLICY,
    TERMINAL_POLICY,
    AnthropicJudge,
    OpenAIGenerator,
    ProviderRefused,
    ProviderUnavailable,
    _new_usage,
    declared_sampling,
    retry_after_seconds,
)
from tere4ai.judge.config import ConfigurationError, DeclaredParameterRefused


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
    # final review A3 adds the sixth count, requests_refused (none here)
    assert gen.usage == {"calls": 2, "input_tokens": 150, "output_tokens": 25,
                         "requests_sent": 2, "replies_with_usage": 2, "requests_refused": 0}


def test_generator_without_usage_block_counts_only_the_call():
    gen = _generator_with([_openai_response("a")])
    gen.complete("s", "u")
    # B91: the usage record also counts requests sent and replies with usage
    # (no usage block: sent and answered, but not reported)
    # final review A3 adds the sixth count, requests_refused (none here)
    assert gen.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                         "requests_sent": 1, "replies_with_usage": 0, "requests_refused": 0}


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
    # final review A3 adds the sixth count, requests_refused (none here)
    assert judge.usage == {"calls": 2, "input_tokens": 210, "output_tokens": 41,
                           "requests_sent": 2, "replies_with_usage": 2, "requests_refused": 0}


def test_judge_without_usage_block_counts_only_the_call():
    judge = _judge_with([_anthropic_response("v")])
    judge.complete("s", "u")
    # B91: the usage record also counts requests sent and replies with usage
    # (no usage block: sent and answered, but not reported)
    # final review A3 adds the sixth count, requests_refused (none here)
    assert judge.usage == {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                           "requests_sent": 1, "replies_with_usage": 0, "requests_refused": 0}


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


# B99 (spec F D-F29): a stub client carries a declaration, temperature 0, effort xhigh, JSON mode sent on the generator, unless a test declares otherwise
def _generator_over(transport, **values) -> OpenAIGenerator:
    gen = OpenAIGenerator.__new__(OpenAIGenerator)
    gen.model = "stub-generator"
    gen.usage = _new_usage()
    gen._declared = declared("stub-generator", "openai", **values)
    gen._client = SimpleNamespace(chat=SimpleNamespace(completions=transport))
    return gen


def _judge_over(transport, **values) -> AnthropicJudge:
    judge = AnthropicJudge.__new__(AnthropicJudge)
    judge.model = "stub-judge"
    judge.usage = _new_usage()
    judge._max_tokens = 16
    judge._declared = declared("stub-judge", "anthropic", **values)
    judge._client = SimpleNamespace(messages=transport)
    return judge


# B99 (spec F D-F29): each model's temperature, effort and JSON mode are
# declared and sent as declared; a declared parameter the provider or its SDK
# refuses is a configuration error that stops the run, never learned.


def _never_wait(seconds):
    raise AssertionError("this failure must not be waited out")


def test_the_generator_sends_every_declared_parameter():
    transport = _Rejecting({}, _openai_response('{"ok": true}', 1, 1))
    gen = _generator_over(transport)
    gen.complete("s", "u")
    call = transport.calls[0]
    assert call["temperature"] == 0 and call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "xhigh"
    assert (gen.temperature, gen.sampling, gen.effort, gen.json_mode) == ("0", "0", "xhigh", "sent")


def test_a_parameter_declared_n_a_is_never_sent():
    transport = _Rejecting({}, _openai_response("x", 1, 1))
    gen = _generator_over(transport, temperature="N/A", effort="N/A", json_mode="N/A")
    gen.complete("s", "u")
    gen.complete("s", "u")
    assert all(set(call) == {"model", "messages"} for call in transport.calls)
    assert (gen.temperature, gen.effort, gen.json_mode) == ("N/A", "N/A", "N/A")


def test_the_judge_sends_its_declared_temperature_and_effort_and_has_no_json_mode():
    transport = _Rejecting({}, _anthropic_response("v", 1, 1))
    judge = _judge_over(transport)
    judge.complete("s", "u")
    assert transport.calls[0]["temperature"] == 0 and transport.calls[0]["output_config"] == {"effort": "xhigh"}
    assert judge.json_mode == "N/A"
    plain = _Rejecting({}, _anthropic_response("v", 1, 1))
    _judge_over(plain, temperature="N/A", effort="N/A").complete("s", "u")
    assert "temperature" not in plain.calls[0] and "output_config" not in plain.calls[0]


@pytest.mark.parametrize("message, parameter, value", [
    ("Unsupported value: 'temperature' does not support 0 with this model.", "temperature", "0"),
    ("response_format json_object is not supported with this model", "json_mode", "sent"),
    ("Error code: 400 - {'error': {'message': \"Invalid value: 'xhigh'. Supported values are: 'low', "
     "'medium', and 'high'.\", 'type': 'invalid_request_error', 'param': 'reasoning_effort', "
     "'code': 'invalid_value'}}", "effort", "xhigh"),
])
def test_a_400_naming_a_declared_parameter_stops_as_a_configuration_error(message, parameter, value):
    transport = _Flaky([_ProviderError(message, status_code=400)])
    gen = _generator_over(transport)
    gen._wait = _never_wait
    with pytest.raises(DeclaredParameterRefused) as refused:
        gen.complete("s", "u")
    assert refused.value.parameter == parameter and refused.value.value == value
    assert refused.value.provider == "openai"
    assert str(refused.value).startswith(
        f"configuration error: openai:stub-generator refused the declared {parameter} {value} (HTTP 400: ")
    assert str(refused.value).endswith("); correct its row in config/model_parameters.json")
    assert isinstance(refused.value, ConfigurationError) and len(transport.calls) == 1
    # a provider's 400 is a request sent, and a refused one (spec F D-F29, final review A3)
    assert gen.usage["requests_sent"] == 1 and gen.usage["requests_refused"] == 1


def test_the_judge_names_a_refused_effort():
    transport = _Flaky([_ProviderError("output_config.effort: this model does not support effort", status_code=400)])
    judge = _judge_over(transport)
    with pytest.raises(DeclaredParameterRefused) as refused:
        judge.complete("s", "u")
    assert (refused.value.provider, refused.value.model, refused.value.parameter, refused.value.value) == (
        "anthropic", "stub-judge", "effort", "xhigh")


def test_an_sdk_refusal_before_sending_stops_and_is_not_a_request_sent():
    transport = _Rejecting({"temperature": "Messages.create() got an unexpected keyword argument 'temperature'"},
                           _anthropic_response("v", 1, 1))
    judge = _judge_over(transport)
    with pytest.raises(DeclaredParameterRefused) as refused:
        judge.complete("s", "u")
    assert str(refused.value) == (
        "configuration error: anthropic:stub-judge refused the declared temperature 0 (RuntimeError: "
        "Messages.create() got an unexpected keyword argument 'temperature'); correct its row in "
        "config/model_parameters.json")
    assert len(transport.calls) == 1
    assert judge.usage["requests_sent"] == 0 and judge.usage["requests_refused"] == 0


def test_a_400_naming_a_parameter_that_was_not_sent_is_an_ordinary_error():
    transport = _Flaky([_ProviderError("temperature is required for this model", status_code=400)])
    gen = _generator_over(transport, temperature="N/A")
    with pytest.raises(_ProviderError):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1 and gen.usage["requests_refused"] == 1


def test_a_client_without_a_declaration_sends_none_of_the_three_and_says_so():
    transport = _Rejecting({}, _openai_response("a", 1, 1))
    gen = OpenAIGenerator.__new__(OpenAIGenerator)
    gen.model, gen.usage = "stub-generator", _new_usage()
    gen._client = SimpleNamespace(chat=SimpleNamespace(completions=transport))
    gen.complete("s", "u")
    assert set(transport.calls[0]) == {"model", "messages"}
    assert (gen.temperature, gen.effort, gen.json_mode) == ("not declared",) * 3


def test_declared_sampling_names_every_declared_value_and_unknown_for_a_stub():
    gen = _generator_over(_Rejecting({}, None), temperature="N/A")
    judge = _judge_over(_Rejecting({}, None))
    assert declared_sampling(gen, judge) == {"generator": "N/A", "judge": "0", "generator_temperature": "N/A",
                                             "judge_temperature": "0", "generator_effort": "xhigh",
                                             "judge_effort": "xhigh", "generator_json_mode": "sent"}
    assert declared_sampling(object(), object())["generator_effort"] == "unknown"
    # B99 (spec F D-F29), Task 5 review: no judge client built leaves the
    # judge-role keys null, as the records stored before B99
    no_judge = declared_sampling(gen, None)
    assert no_judge["generator_effort"] == "xhigh"
    assert (no_judge["judge"], no_judge["judge_temperature"], no_judge["judge_effort"]) == (None, None, None)


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


def test_judge_default_output_cap_leaves_room_for_thinking():
    import inspect

    default = inspect.signature(AnthropicJudge.__init__).parameters["max_tokens"].default
    assert default >= 16000


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


# B84 fix wave G5: pin Review Focus 1 on the judge (a rejection that names
# no carried parameter propagates). B99 (spec F D-F29): the Review Focus 2
# tests pinned the learning loop's last attempt; there is no loop any more.


def test_judge_propagates_when_the_rejection_names_no_carried_parameter():
    """Review Focus 1, judge side: effort is declared N/A, so output_config
    is not sent; the rejection message names 'effort', not the temperature
    that was actually carried, so it names no carried parameter and the
    error propagates on the first call."""
    transport = _Rejecting(
        {"temperature": "effort is not supported"}, _anthropic_response("v", 1, 1)
    )
    # B99 (spec F D-F29): declared, never learned
    judge = _judge_over(transport, effort="N/A")
    with pytest.raises(RuntimeError):
        judge.complete("s", "u")
    assert len(transport.calls) == 1


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
    # final review A3 adds the sixth count, requests_refused (none here)
    assert usage_since(gen, before) == {"calls": 1, "input_tokens": 50, "output_tokens": 5,
                                        "requests_sent": 1, "replies_with_usage": 1, "requests_refused": 0}
    assert usage_snapshot(object()) is None and usage_since(object(), None) is None


# Task 1a (B91, spec F D-F26 (e) and (g), ruling R3): the SDKs' hidden
# retries are off (max_retries=0 on both constructors), so the clients
# retry a transient failure themselves, counting every physical attempt as
# a request sent. Retryable (review fix F1): a numeric status_code of 408,
# 409, 429 or 5xx, or the SDK's connection/timeout error matched by class
# name (APIConnectionError, whose APITimeoutError subclass matches the same
# way), so the mixin never imports an SDK. B99 (spec F D-F29): a refused
# declared parameter is checked first and is never retried (see the
# configuration error tests above); anything else not retryable raises
# after one attempt.


class _ProviderError(Exception):
    """Test double for the SDKs' APIStatusError: carries status_code and a
    response with headers, without importing either SDK."""

    def __init__(self, message: str, status_code: int | None = None,
                 headers: dict | None = None, code: str | None = None, body: object = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {})
        # B99 (spec F D-F30): an error code and body, as the SDKs carry them
        self.code = code
        self.body = body


class APIConnectionError(Exception):
    """Test double named like the SDKs' connection error; the retry check
    matches by class name only (review fix F1), never by importing an SDK."""


class APITimeoutError(APIConnectionError):
    """Test double named like the SDKs' timeout error, a subclass of the connection error there too."""


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
    # B99 (spec F D-F29): the declaration replaces the effort fields
    cfg = ModelConfig(generator_model="gpt-x", judge_model="claude-x", generator_api_key="k1", judge_api_key="k2",
                      generator_parameters=declared("gpt-x", "openai", effort="high"),
                      judge_parameters=declared("claude-x", "anthropic", effort="high"))
    OpenAIGenerator(cfg)
    AnthropicJudge(cfg)
    assert captured_openai["max_retries"] == 0
    assert captured_anthropic["max_retries"] == 0
    # B99 (spec F D-F30): the policy is the caller's, the service policy by default
    assert OpenAIGenerator(cfg)._retry_policy is SERVICE_POLICY
    assert AnthropicJudge(cfg)._retry_policy is SERVICE_POLICY
    assert OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)._retry_policy is TERMINAL_POLICY
    assert AnthropicJudge(cfg, retry_policy=TERMINAL_POLICY)._retry_policy is TERMINAL_POLICY


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


# Final review A5: a refused declared parameter is a 400 (or an error with
# no status, as the SDK raises for a keyword it no longer accepts; B99, spec
# F D-F29, makes it a configuration error); a retryable error whose message
# happens to name a parameter is retried, and the parameter stays.


def test_generator_retries_a_429_naming_temperature_and_keeps_the_parameter():
    waits = []
    transport = _Flaky([_ProviderError("rate limit on requests with temperature", status_code=429),
                        _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = waits.append
    assert gen.complete("s", "u") == "a"
    assert waits == [1] and all("temperature" in call for call in transport.calls)
    assert gen.usage["requests_sent"] == 2 and gen.sampling == "0"


def test_judge_retries_a_529_naming_effort_and_keeps_the_parameter():
    waits = []
    transport = _Flaky([_ProviderError("overloaded: effort queue full", status_code=529),
                        _anthropic_response("v", 1, 1)])
    # B99 (spec F D-F29): declared, never learned
    judge = _judge_over(transport)
    judge._wait = waits.append
    assert judge.complete("s", "u") == "v"
    assert waits == [1] and all("output_config" in call for call in transport.calls)
    assert judge.effort == "xhigh"


# Final review A3: a sixth count separates a request the provider answered
# with an HTTP error status (refused, not billed as a generation) from one
# that failed without a reply (connection error, timeout, interrupt: it may
# have been billed). requests_sent keeps counting every attempt.


def test_a_retried_429_counts_one_refused_request():
    transport = _Flaky([_ProviderError("rate limited", status_code=429), _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = lambda seconds: None
    gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 2 and gen.usage["requests_refused"] == 1
    assert gen.usage["replies_with_usage"] == 1


def test_a_non_retryable_status_is_refused_too():
    transport = _Flaky([_ProviderError("unauthorized", status_code=401)])
    judge = _judge_over(transport)
    with pytest.raises(_ProviderError):
        judge.complete("s", "u")
    assert judge.usage["requests_sent"] == 1 and judge.usage["requests_refused"] == 1


def test_a_connection_error_or_an_interrupt_is_not_refused():
    transport = _Flaky([APIConnectionError("connection reset"), _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = lambda seconds: None
    gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 2 and gen.usage["requests_refused"] == 0

    class _Interrupting:
        def create(self, **kwargs):
            raise KeyboardInterrupt
    gen = _generator_over(_Interrupting())
    with pytest.raises(KeyboardInterrupt):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1 and gen.usage["requests_refused"] == 0



# B99 (spec F D-F30): the terminal policy of the runs a person resumes from a
# terminal. Five pauses (10, 30, 90, 270, 600 s), an alert line before each, a
# Retry-After that only lengthens a pause, capped at 600 s, then a stop. No
# test sleeps: the wait and the alert clock are replaced on the instance.
NOON = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)


def _terminal(client, waits=None):
    client._retry_policy = TERMINAL_POLICY
    client._now = lambda: NOON
    client._wait = waits.append if waits is not None else _never_wait
    return client


def test_the_terminal_policy_waits_five_growing_pauses_with_an_alert_then_stops(capsys):
    waits = []
    transport = _Flaky([_ProviderError("overloaded", status_code=529)] * 6)
    judge = _terminal(_judge_over(transport), waits)
    with pytest.raises(ProviderUnavailable) as stop:
        judge.complete("s", "u")
    assert str(stop.value) == "provider unavailable after 6 attempts: HTTP 529: overloaded"
    assert waits == [10, 30, 90, 270, 600] and len(transport.calls) == 6
    assert judge.usage["requests_sent"] == 6 and judge.usage["requests_refused"] == 6 and judge.usage["calls"] == 0
    assert capsys.readouterr().err.splitlines() == [
        f"ALERT 2026-09-27T12:00:00.000Z anthropic:stub-judge: HTTP 529: overloaded; attempt {n} of 6 failed; "
        f"next attempt in {pause} s"
        for n, pause in zip(range(1, 6), (10, 30, 90, 270, 600))
    ]
    assert not isinstance(stop.value, (RuntimeError, ValueError)), "no parse or per-item handler may absorb it"


def test_the_terminal_policy_carries_a_timeout_a_lost_connection_and_a_500(capsys):
    waits = []
    transport = _Flaky([APIConnectionError("Connection error."), APITimeoutError("Request timed out."),
                        _ProviderError("boom", status_code=500), _openai_response("a", 1, 1)])
    gen = _terminal(_generator_over(transport), waits)
    assert gen.complete("s", "u") == "a"
    assert waits == [10, 30, 90]
    assert gen.usage["requests_sent"] == 4 and gen.usage["requests_refused"] == 1 and gen.usage["calls"] == 1
    err = capsys.readouterr().err
    assert "openai:stub-generator: APIConnectionError: Connection error.; attempt 1 of 6 failed" in err
    assert "APITimeoutError: Request timed out.; attempt 2 of 6 failed; next attempt in 30 s" in err


def test_a_stop_after_a_lost_connection_names_the_error():
    transport = _Flaky([APIConnectionError("Connection error.")] * 6)
    gen = _terminal(_generator_over(transport), [])
    with pytest.raises(ProviderUnavailable, match=r"^provider unavailable after 6 attempts: "
                                                  r"APIConnectionError: Connection error\.$"):
        gen.complete("s", "u")
    assert gen.usage["requests_refused"] == 0


def test_a_retry_after_only_lengthens_a_terminal_pause_and_never_past_600_s(capsys):
    waits = []
    transport = _Flaky([
        _ProviderError("x", status_code=429, headers={"retry-after": "45"}),
        _ProviderError("x", status_code=429, headers={"retry-after": "5"}),
        _ProviderError("x", status_code=503, headers={"retry-after-ms": "120500"}),
        _ProviderError("x", status_code=503, headers={"retry-after": "9999"}),
        _openai_response("a", 1, 1),
    ])
    gen = _terminal(_generator_over(transport), waits)
    gen.complete("s", "u")
    assert waits == [45, 30, 120.5, 600]
    # B101 ruling S1: the alert prints the pause in whole seconds rounded up, as the dashboard does
    assert "attempt 3 of 6 failed; next attempt in 121 s" in capsys.readouterr().err


def test_retry_after_reads_seconds_a_date_and_milliseconds():
    def headers(**h):
        return _ProviderError("x", status_code=503, headers={k.replace("_", "-"): v for k, v in h.items()})
    assert retry_after_seconds(headers(retry_after="Sun, 27 Sep 2026 12:02:00 GMT"), NOON) == 120.0
    assert retry_after_seconds(headers(retry_after="Sun, 27 Sep 2026 11:00:00 GMT"), NOON) == 0.0
    assert retry_after_seconds(headers(retry_after="7"), NOON) == 7.0
    assert retry_after_seconds(headers(retry_after_ms="1500", retry_after="7"), NOON) == 1.5
    assert retry_after_seconds(headers(retry_after_ms="nan", retry_after="3"), NOON) == 3.0
    assert retry_after_seconds(headers(retry_after="soon"), NOON) is None
    assert retry_after_seconds(headers(retry_after="-4"), NOON) is None
    assert retry_after_seconds(_ProviderError("x", status_code=503), NOON) is None
    # a date in the past reads 0, so the planned pause stands
    assert TERMINAL_POLICY.pause(0, 0.0) == 10


@pytest.mark.parametrize("refusal", [
    _ProviderError("You exceeded your current quota", status_code=429, code="insufficient_quota"),
    _ProviderError("quota", status_code=429, body={"error": {"code": "insufficient_quota"}}),
    _ProviderError("quota", status_code=429, body={"code": "insufficient_quota"}),
])
def test_a_quota_refusal_stops_the_terminal_policy_at_once(refusal):
    gen = _terminal(_generator_over(_Flaky([refusal])))
    with pytest.raises(ProviderRefused, match=r"^provider refused the request: HTTP 429: \S") as refused:
        gen.complete("s", "u")
    assert refused.value.__cause__ is refusal
    assert gen.usage["requests_sent"] == 1 and gen.usage["requests_refused"] == 1


def test_the_service_policy_still_retries_a_quota_429():
    waits = []
    transport = _Flaky([_ProviderError("quota", status_code=429, code="insufficient_quota"),
                        _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = waits.append
    assert gen.complete("s", "u") == "a" and waits == [1]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_every_other_4xx_stops_the_terminal_policy_at_once(status):
    gen = _terminal(_generator_over(_Flaky([_ProviderError("no", status_code=status)])))
    # the cause is the status and the provider's first line (B101 ruling S1)
    with pytest.raises(ProviderRefused, match=rf"^provider refused the request: HTTP {status}: no$"):
        gen.complete("s", "u")
    assert gen.usage["requests_sent"] == 1


def test_an_sdk_error_before_sending_stops_the_terminal_policy_uncounted_by_status():
    """Ruling P21: an SDK error raised before sending that names nothing
    declared is a refusal too. It counts in requests_sent as at HEAD
    (model_clients.py:234; the pre-B74 R1 rule exempts only a refused declared
    parameter) and carries no status, so it is not in requests_refused."""
    gen = _terminal(_generator_over(_Flaky([TypeError("unexpected keyword argument 'foo'")])))
    with pytest.raises(ProviderRefused, match=r"^provider refused the request: TypeError: unexpected keyword argument 'foo'$"):
        gen.complete("s", "u")
    assert gen.usage["requests_refused"] == 0


def test_the_service_policy_raises_a_refusal_as_the_sdks_own_error():
    gen = _generator_over(_Flaky([_ProviderError("unauthorized", status_code=401)]))
    with pytest.raises(_ProviderError):
        gen.complete("s", "u")


def test_the_service_policy_ignores_a_date_and_a_millisecond_header():
    """Coordinator ruling on review T-M2: the service policy reads Retry-After
    in seconds only, as before B99; a past date or a millisecond header leaves
    the 1 s pause."""
    waits = []
    transport = _Flaky([_ProviderError("x", status_code=503, headers={
        "retry-after": "Sun, 27 Sep 2026 11:00:00 GMT", "retry-after-ms": "5"}), _openai_response("a", 1, 1)])
    gen = _generator_over(transport)
    gen._wait = waits.append
    gen.complete("s", "u")
    assert waits == [1]


@pytest.mark.parametrize("status", [408, 409, 501, 520, 529])
def test_408_409_and_any_5xx_are_retried_by_the_terminal_policy(status):
    waits = []
    gen = _terminal(_generator_over(_Flaky([_ProviderError("x", status_code=status), _openai_response("a", 1, 1)])),
                    waits)
    gen.complete("s", "u")
    assert waits == [10]


def test_a_429_naming_temperature_is_waited_out_never_a_configuration_error():
    waits = []
    transport = _Flaky([_ProviderError("rate limit on requests with temperature", status_code=429),
                        _openai_response("a", 1, 1)])
    gen = _terminal(_generator_over(transport), waits)
    assert gen.complete("s", "u") == "a" and waits == [10]
    assert all(call["temperature"] == 0 for call in transport.calls)


def test_an_interrupt_during_a_pause_ends_at_once():
    def interrupt(seconds):
        raise KeyboardInterrupt
    transport = _Flaky([_ProviderError("overloaded", status_code=529), _anthropic_response("v", 1, 1)])
    judge = _terminal(_judge_over(transport))
    judge._wait = interrupt
    with pytest.raises(KeyboardInterrupt):
        judge.complete("s", "u")
    assert len(transport.calls) == 1 and judge.usage["requests_sent"] == 1


def test_the_service_policy_is_unchanged():
    assert SERVICE_POLICY.pauses == (1.0, 4.0) and SERVICE_POLICY.retry_after_cap == 60.0
    assert not SERVICE_POLICY.alert and not SERVICE_POLICY.stop_when_exhausted
    assert not SERVICE_POLICY.retry_after_reads_dates_and_ms and not SERVICE_POLICY.stop_on_refusal
    assert TERMINAL_POLICY.retry_after_reads_dates_and_ms and TERMINAL_POLICY.stop_on_refusal
    assert TERMINAL_POLICY.pauses == (10.0, 30.0, 90.0, 270.0, 600.0) and TERMINAL_POLICY.attempts == 6


def test_only_the_four_terminal_commands_choose_the_terminal_policy():
    """B99 (spec F D-F30): the facade, the MCP server and the harness keep the
    service policy by not naming one; only the runs with a checkpoint and a
    resume name the terminal policy (scripts/elicit_benchmark_features.py
    since B101 ruling S4), and only the two scripts name the provider
    refusal, to name the item it stopped on (ruling P21, B101 ruling S5)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]

    def users(name):
        return sorted(str(p.relative_to(root)) for base in ("src", "scripts") for p in (root / base).rglob("*.py")
                      if name in p.read_text(encoding="utf-8"))

    assert users("TERMINAL_POLICY") == ["scripts/elicit_benchmark_features.py", "scripts/run_ablations.py",
                                        "src/tere4ai/align_hleg/__main__.py",
                                        "src/tere4ai/extract_norms/__main__.py",
                                        "src/tere4ai/extract_norms/model_clients.py"]
    assert users("ProviderRefused") == ["scripts/elicit_benchmark_features.py", "scripts/run_ablations.py",
                                        "src/tere4ai/extract_norms/model_clients.py"]

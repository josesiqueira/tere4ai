"""Model clients for the M2 norm-extraction pipeline.

@implements: DEC-07
@grounded_by: REF-24

The generator (norm extraction) runs on the OpenAI family and the extraction
judge runs on an independent non-OpenAI family (Anthropic Claude), because
same-family judges have correlated failure modes (architecture.md Section 7,
decided 2026-07-08). All model ids come from tere4ai.judge.config.ModelConfig,
never hardcoded here. API keys are used to construct SDK clients and are
never logged or echoed.
"""

from __future__ import annotations

import time
from typing import Protocol

from tere4ai.judge.config import (
    NOT_APPLICABLE,
    DeclaredParameterRefused,
    ModelConfig,
    ModelParameters,
)


class ModelClient(Protocol):
    """Minimal contract the pipeline needs from any model backend."""

    model: str

    def complete(self, system: str, user: str) -> str:
        """Return the raw text completion for one system + user exchange."""
        ...


# B91 (spec F D-F26 (g)): beside the provider-reported token sums, every
# client counts the requests it sent and the replies that reported usage,
# so a total can say whether it is complete: sent > with usage means some
# request may have been billed without a figure. Final review A3: a sixth
# count, requests_refused, counts the failed attempts the provider answered
# with an HTTP error status (a 429 or a 5xx included), so a paid run can tell
# a refused request from one that failed without a reply (connection error,
# timeout, interrupt) and may have been billed. requests_sent counts every
# attempt the SDK sent, a 400 refusing a declared parameter included; a
# refusal the SDK raises before sending is not a request sent (spec F D-F29).
USAGE_KEYS = ("calls", "input_tokens", "output_tokens", "requests_sent", "replies_with_usage",
              "requests_refused")


def _new_usage() -> dict[str, int]:
    return {key: 0 for key in USAGE_KEYS}


def usage_snapshot(client: object) -> dict[str, int] | None:
    """A copy of the client's usage record, or None for a client without one (a stub)."""
    usage = getattr(client, "usage", None)
    return dict(usage) if isinstance(usage, dict) else None


def usage_since(client: object, before: dict[str, int] | None) -> dict[str, int] | None:
    """The client's usage since the snapshot `before`; None when either side is missing."""
    now = usage_snapshot(client)
    if now is None or before is None:
        return None
    return {key: now.get(key, 0) - before.get(key, 0) for key in now}


# Spec F D-F29 (2026-09-27): each model's temperature, effort and JSON mode
# are declared in config/model_parameters.json and sent as declared on every
# request; a parameter declared N/A is never sent. Nothing is learned: a
# declared parameter the provider or its SDK refuses is a configuration error
# (DeclaredParameterRefused) that stops the run. A client built without a
# declaration (the offline tests build clients with __new__) sends none of
# the three and reports "not declared".
NOT_DECLARED = "not declared"


def declared_sampling(generator: object, judge: object) -> dict[str, str]:
    """The execution record's sampling (spec F D-F29): each role's declared
    temperature under the keys the records have always used and again under
    <role>_temperature (review X-C1), the declared efforts and the generator's
    JSON mode; "unknown" for a stub without them."""
    def field(client: object, name: str) -> str:
        return str(getattr(client, name, "unknown"))
    return {"generator": field(generator, "sampling"), "judge": field(judge, "sampling"),
            "generator_temperature": field(generator, "temperature"),
            "judge_temperature": field(judge, "temperature"),
            "generator_effort": field(generator, "effort"), "judge_effort": field(judge, "effort"),
            "generator_json_mode": field(generator, "json_mode")}


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return text[0][:200] if text else ""


class _SamplingRecord:
    """Mixin: the declared parameters, the usage counts and the retries."""

    # Class-level default so an instance built without __init__ (the offline
    # tests construct clients with __new__ and a stub transport) starts with
    # no declaration.
    _declared: ModelParameters | None = None

    # Task 1a (B91, spec F D-F26 (e), ruling R3): the wait between retries,
    # a class attribute so a client built with __new__ (the offline tests)
    # still has one, and a test can replace it to never actually sleep.
    _wait = staticmethod(time.sleep)

    @property
    def temperature(self) -> str:
        return self._declared.temperature if self._declared is not None else NOT_DECLARED

    @property
    def sampling(self) -> str:
        """The declared temperature, under the name the records have always used."""
        return self.temperature

    @property
    def effort(self) -> str:
        return self._declared.effort if self._declared is not None else NOT_DECLARED

    @property
    def json_mode(self) -> str:
        return self._declared.json_mode if self._declared is not None else NOT_DECLARED

    def _declared_value(self, parameter: str) -> str:
        return {"temperature": self.temperature, "effort": self.effort, "json_mode": self.json_mode}[parameter]

    def _count_sent(self) -> None:
        self.usage["requests_sent"] = self.usage.get("requests_sent", 0) + 1

    def _count_refused(self, exc: BaseException) -> None:
        """A failed attempt the provider answered with an HTTP error status
        (any numeric status_code) is refused (final review A3); a connection
        error, a timeout or an interrupt carries no status and is not."""
        if isinstance(getattr(exc, "status_code", None), int):
            self.usage["requests_refused"] = self.usage.get("requests_refused", 0) + 1

    def _count_reply(self, reported: object, input_field: str, output_field: str) -> None:
        """One reply received: add the provider's token figures; count the reply as
        reporting usage only when both figures are integers (a partial block is
        not a complete report)."""
        self.usage["calls"] += 1
        if reported is None:
            return
        input_tokens = getattr(reported, input_field, None)
        output_tokens = getattr(reported, output_field, None)
        if isinstance(input_tokens, int):
            self.usage["input_tokens"] += input_tokens
        if isinstance(output_tokens, int):
            self.usage["output_tokens"] += output_tokens
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            self.usage["replies_with_usage"] = self.usage.get("replies_with_usage", 0) + 1

    # Task 1a (B91, spec F D-F26 (e) and (g), ruling R3): the SDKs' own
    # hidden retries are off (max_retries=0 on both constructors), so a
    # transient failure is retried here instead, with every physical
    # attempt counted. Review fix F1 classification: retryable when the
    # exception carries a numeric status_code of 408, 409, 429 or a 5xx
    # (529 included), or when it is a connection or timeout error, matched
    # by class name (APIConnectionError; both SDKs' APITimeoutError
    # subclasses it) so this mixin imports no SDK.
    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and (status in (408, 409, 429) or status >= 500):
            return True
        return any(cls.__name__ == "APIConnectionError" for cls in type(exc).__mro__)

    def _retry_delay(self, exc: BaseException, retries_used: int) -> float:
        """The provider's retry-after header when present, capped at 60 s;
        otherwise 1 s after the first failure, 4 s after the second."""
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) if response is not None else None
        getter = getattr(headers, "get", None) if headers is not None else None
        retry_after = getter("retry-after") if callable(getter) else None
        if retry_after is not None:
            try:
                return min(float(retry_after), 60.0)
            except (TypeError, ValueError):
                pass
        return 1.0 if retries_used == 0 else 4.0

    def _send(self, do_request, parameter_named):
        """Send one request through do_request(), retrying a transient failure
        (see _is_retryable) at most twice, waiting _retry_delay between
        attempts. Every attempt the SDK sent counts one requests_sent. A 400
        naming a declared parameter (counted), or a refusal raised before
        sending that names one (not counted), is DeclaredParameterRefused at
        once (spec F D-F29). A KeyboardInterrupt is counted once, then raised."""
        retries_used = 0
        while True:
            try:
                response = do_request()
            except Exception as exc:  # noqa: BLE001
                status = getattr(exc, "status_code", None)
                parameter = parameter_named(exc)
                if parameter is not None and (status == 400 or (status is None and not self._is_retryable(exc))):
                    if status is not None:
                        self._count_sent()  # the provider answered: a request sent (spec F D-F29)
                        self._count_refused(exc)
                    detail = f"HTTP {status}: {_first_line(exc)}" if status is not None else (
                        f"{type(exc).__name__}: {_first_line(exc)}")
                    raise DeclaredParameterRefused(self.provider, self.model, parameter,
                                                   self._declared_value(parameter), detail) from exc
                self._count_sent()  # it may have been billed; count every physical attempt
                self._count_refused(exc)
                if self._is_retryable(exc) and retries_used < 2:
                    self._wait(self._retry_delay(exc, retries_used))
                    retries_used += 1
                    continue
                raise
            except BaseException:
                self._count_sent()  # an interrupt mid-request: the request may have been billed
                raise
            self._count_sent()
            return response


class OpenAIGenerator(_SamplingRecord):
    """Generator client (OpenAI family, cfg.generator_model).

    Sends the model's declared temperature (0), JSON mode and reasoning
    effort, each only where the table declares it (spec F D-F29); a refusal
    of one is DeclaredParameterRefused, never learned. .usage accumulates
    provider-reported token counts plus requests_sent, replies_with_usage
    and requests_refused (spec F D-F26 (g)). The SDK's own retries are off
    (max_retries=0); complete() retries a transient failure itself,
    counting every attempt.
    """

    provider = "openai"

    def __init__(self, cfg: ModelConfig):
        from openai import OpenAI  # imported lazily so offline tests need no SDK

        self.model = cfg.generator_model
        self.usage = _new_usage()
        self._declared = cfg.generator_parameters
        self._client = OpenAI(api_key=cfg.generator_api_key, max_retries=0)

    def _request_kwargs(self, messages: list[dict[str, str]]) -> dict:
        kwargs: dict = {"model": self.model, "messages": messages}
        declared = self._declared
        if declared is not None:
            if declared.temperature != NOT_APPLICABLE:
                kwargs["temperature"] = 0
            if declared.json_mode != NOT_APPLICABLE:
                kwargs["response_format"] = {"type": "json_object"}
            if declared.effort != NOT_APPLICABLE:
                kwargs["reasoning_effort"] = declared.effort
        return kwargs

    @staticmethod
    def _parameter_named(exc: BaseException, kwargs: dict) -> str | None:
        message = str(exc)
        for keyword, parameter in (("temperature", "temperature"), ("response_format", "json_mode"),
                                   ("reasoning_effort", "effort")):
            if keyword in kwargs and keyword in message:
                return parameter
        return None

    def complete(self, system: str, user: str) -> str:
        kwargs = self._request_kwargs([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        response = self._send(lambda: self._client.chat.completions.create(**kwargs),
                              lambda exc: self._parameter_named(exc, kwargs))
        self._count_reply(getattr(response, "usage", None), "prompt_tokens", "completion_tokens")
        return response.choices[0].message.content or ""


class AnthropicJudge(_SamplingRecord):
    """Judge client (independent Claude family, cfg.judge_model).

    Sends the model's declared temperature (0) and effort (output_config),
    each only where the table declares it (spec F D-F29); a refusal of one
    is DeclaredParameterRefused, never learned. The output cap defaults to
    16000 tokens because current Claude models think before answering and
    the thinking counts against max_tokens: the former 2048 would have
    truncated the judge's JSON mid-rationale. Only text blocks are returned; thinking
    blocks (empty by default) are skipped. .usage accumulates
    provider-reported token counts plus requests_sent and
    replies_with_usage (spec F D-F26 (g)); a response without a complete
    usage block adds to calls and requests_sent only (thinking tokens are
    inside output_tokens). The SDK's own retries are off (max_retries=0);
    complete() retries a transient failure itself, counting every attempt
    (Task 1a, ruling R3).
    """

    provider = "anthropic"

    def __init__(self, cfg: ModelConfig, max_tokens: int = 16000):
        import anthropic  # imported lazily so offline tests need no SDK

        self.model = cfg.judge_model
        self.usage = _new_usage()
        self._declared = cfg.judge_parameters
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=cfg.judge_api_key, max_retries=0)

    @property
    def json_mode(self) -> str:
        """The judge client has no JSON mode parameter; every anthropic row declares N/A."""
        return NOT_APPLICABLE

    def _request_kwargs(self, system: str, user: str) -> dict:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        declared = self._declared
        if declared is not None:
            if declared.temperature != NOT_APPLICABLE:
                kwargs["temperature"] = 0
            if declared.effort != NOT_APPLICABLE:
                kwargs["output_config"] = {"effort": declared.effort}
        return kwargs

    @staticmethod
    def _parameter_named(exc: BaseException, kwargs: dict) -> str | None:
        message = str(exc)
        if "temperature" in kwargs and "temperature" in message:
            return "temperature"
        if "output_config" in kwargs and ("effort" in message or "output_config" in message):
            return "effort"
        return None

    def complete(self, system: str, user: str) -> str:
        kwargs = self._request_kwargs(system, user)
        response = self._send(lambda: self._client.messages.create(**kwargs),
                              lambda exc: self._parameter_named(exc, kwargs))
        self._count_reply(getattr(response, "usage", None), "input_tokens", "output_tokens")
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )


class FakeClient:
    """Scripted offline client for unit tests. Never calls a network.

    scripted maps a substring key (typically a source node id) to either a
    single response string or a list of response strings consumed in order,
    which lets tests script a parse failure followed by a retry. Every call
    is recorded in .calls as (system, user) so tests can assert on inputs.
    """

    def __init__(self, scripted: dict, model: str = "fake-model"):
        self.model = model
        self._scripted = {key: list(value) if isinstance(value, list) else [value]
                          for key, value in scripted.items()}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for key, responses in self._scripted.items():
            if key in user:
                if len(responses) > 1:
                    return responses.pop(0)
                return responses[0]
        raise KeyError(f"FakeClient has no scripted response matching this input; keys: {sorted(self._scripted)}")

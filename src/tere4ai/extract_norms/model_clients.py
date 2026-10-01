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

import math
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
# Spec F D-F32: a seventh count, requests_rejected_before_processing, counts
# the attempts the provider answered with one of the seven statuses below,
# known by the status alone (the D-F26 (e) class, which the providers do not
# bill). It is a subset of requests_refused, and each such attempt stays in
# requests_sent. The name spells the class out so it is never read as
# requests_refused; the dashboard pins its own copy of the seven (spend.ts).
USAGE_KEYS = ("calls", "input_tokens", "output_tokens", "requests_sent", "replies_with_usage",
              "requests_refused", "requests_rejected_before_processing")
REJECTED_BEFORE_PROCESSING_STATUSES = (400, 401, 403, 404, 413, 422, 429)


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


def declared_sampling(generator: object, judge: object | None) -> dict[str, str | None]:
    """The execution record's sampling (spec F D-F29): each role's declared
    temperature under the keys the records have always used and again under
    <role>_temperature (review X-C1), the declared efforts and the generator's
    JSON mode; "unknown" for a stub without them. A run that built no judge
    (the harness without graph_full, a judge constructor that raised) gets
    null judge-role keys, as its records stored before B99."""
    def field(client: object, name: str) -> str | None:
        return None if client is None else str(getattr(client, name, "unknown"))
    return {"generator": field(generator, "sampling"), "judge": field(judge, "sampling"),
            "generator_temperature": field(generator, "temperature"),
            "judge_temperature": field(judge, "temperature"),
            "generator_effort": field(generator, "effort"), "judge_effort": field(judge, "effort"),
            "generator_json_mode": field(generator, "json_mode")}


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return text[0][:200] if text else ""


@dataclass(frozen=True)
class RetryPolicy:
    """How a client meets a failure that may pass (spec F D-F30), chosen by the
    caller at construction. pauses[n] is the wait before attempt n + 2, so a
    policy makes len(pauses) + 1 attempts. retry_after_lengthens_only: a
    provider's Retry-After only lengthens a pause (terminal) instead of
    replacing it (service); either way it is capped at retry_after_cap.
    retry_after_reads_dates_and_ms: the header is read in milliseconds, in
    seconds or as a date (terminal), or in seconds only, as before B99
    (service). stop_on_refusal: a failure no retry fixes is raised as
    ProviderRefused (terminal) or as the SDK's own error (service)."""

    name: str
    pauses: tuple[float, ...]
    retry_after_cap: float
    retry_after_lengthens_only: bool
    retry_after_reads_dates_and_ms: bool
    quota_429_retryable: bool
    alert: bool
    stop_when_exhausted: bool
    stop_on_refusal: bool

    @property
    def attempts(self) -> int:
        return len(self.pauses) + 1

    def pause(self, retries_used: int, retry_after: float | None) -> float:
        planned = self.pauses[retries_used]
        if retry_after is None:
            return planned
        if self.retry_after_lengthens_only:
            return min(max(planned, retry_after), self.retry_after_cap)
        return min(retry_after, self.retry_after_cap)


# The facade, the MCP server and the evaluation harness outside
# run_ablations: today's two retries at 1 and 4 s, Retry-After in place of
# the pause, read in seconds only, capped at 60 s (pre-B74 plan ruling R3,
# unchanged by B99: review T-M2); a failure after them
# raises and the caller answers degraded with its spend (f220480).
SERVICE_POLICY = RetryPolicy(name="service", pauses=(1.0, 4.0), retry_after_cap=60.0,
                             retry_after_lengthens_only=False, retry_after_reads_dates_and_ms=False,
                             quota_429_retryable=True, alert=False, stop_when_exhausted=False,
                             stop_on_refusal=False)
# The terminal runs with a checkpoint and a resume (extract_norms, align_hleg,
# scripts/run_ablations.py, scripts/elicit_benchmark_features.py): five growing pauses, an alert line on standard
# error before each, a quota refusal never waited out, a refusal no retry
# fixes raised as ProviderRefused, and a stop the command records and
# resumes (spec F D-F30).
TERMINAL_POLICY = RetryPolicy(name="terminal", pauses=(10.0, 30.0, 90.0, 270.0, 600.0), retry_after_cap=600.0,
                              retry_after_lengthens_only=True, retry_after_reads_dates_and_ms=True,
                              quota_429_retryable=False, alert=True, stop_when_exhausted=True,
                              stop_on_refusal=True)


class ProviderUnavailable(Exception):
    """The terminal policy's stop (spec F D-F30): the last attempt failed for a
    reason that may pass. Not a RuntimeError or ValueError, so no per-item or
    parse handler absorbs it; the terminal commands record it and print the
    resume command."""

    def __init__(self, attempts: int, cause: str):
        super().__init__(f"provider unavailable after {attempts} attempts: {cause}")
        self.attempts, self.cause = attempts, cause


class ProviderRefused(Exception):
    """The terminal policy's refusal (spec F D-F30, review T-I1): the provider
    answered with a status no retry fixes (a 4xx other than 408, 409 and a
    passable 429; a quota 429), or the SDK refused the request before
    sending. The run stops at once; never an item's error."""

    def __init__(self, cause: str):
        super().__init__(f"provider refused the request: {cause}")
        self.cause = cause


def _is_connection_error(exc: BaseException) -> bool:
    """A lost connection or a timeout, matched by class name (APIConnectionError;
    both SDKs' APITimeoutError subclasses it) so this module imports no SDK."""
    return any(cls.__name__ == "APIConnectionError" for cls in type(exc).__mro__)


def _is_quota_refusal(exc: BaseException) -> bool:
    """OpenAI answers an exhausted quota with 429 and the error code
    insufficient_quota, on the exception's code or in its body."""
    codes = [getattr(exc, "code", None)]
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        codes.append(body.get("code"))
        nested = body.get("error")
        if isinstance(nested, dict):
            codes.append(nested.get("code"))
    return "insufficient_quota" in codes


def _is_retryable(exc: BaseException, policy: RetryPolicy) -> bool:
    """408, 409, 429 (a quota refusal only where the policy allows it), any 5xx
    (529 included), a timeout or a lost connection; every other failure is not
    retried."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status == 429:
            return policy.quota_429_retryable or not _is_quota_refusal(exc)
        return status in (408, 409) or status >= 500
    return _is_connection_error(exc)


def _status_or_error(exc: BaseException) -> str:
    """The cause in a stop reason, an alert line and a configuration error:
    "HTTP 529: <first line of the provider's message, cut to 200 characters>"
    (or "HTTP 529" when the message is empty), or the error's class and first
    line for a failure without a status; the dashboard's failureText prints
    the same (coordinator ruling S1 of B101)."""
    status = getattr(exc, "status_code", None)
    line = _first_line(exc)
    if isinstance(status, int):
        return f"HTTP {status}: {line}" if line else f"HTTP {status}"
    return f"{type(exc).__name__}: {line}" if line else type(exc).__name__


def _retry_after_header_seconds(exc: BaseException) -> float | None:
    """The service policy's reading, exactly as before B99 (model_clients.py
    at 9673819, lines 205 to 213): Retry-After as a number of seconds, any
    other form ignored."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    getter = getattr(headers, "get", None) if headers is not None else None
    raw = getter("retry-after") if callable(getter) else None
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def retry_after_seconds(exc: BaseException, now: datetime) -> float | None:
    """The provider's requested wait: retry-after-ms when present, else
    Retry-After in seconds or as an HTTP date; None when absent or unreadable."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    getter = getattr(headers, "get", None) if headers is not None else None
    if not callable(getter):
        return None
    millis = getter("retry-after-ms")
    if millis is not None:
        try:
            value = float(millis) / 1000.0
        except (TypeError, ValueError):
            value = math.nan
        if math.isfinite(value) and value >= 0:
            return value
    raw = getter("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = math.nan
    if math.isfinite(value):
        return value if value >= 0 else None
    try:
        when = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _SamplingRecord:
    """Mixin: the declared parameters, the usage counts and the retries."""

    # Class-level default so an instance built without __init__ (the offline
    # tests construct clients with __new__ and a stub transport) starts with
    # no declaration.
    _declared: ModelParameters | None = None

    # The wait between attempts and the clock of the alert line, class
    # attributes so a test replaces them and never sleeps (spec F D-F30).
    _wait = staticmethod(time.sleep)
    _now = staticmethod(_utc_now)
    _retry_policy: RetryPolicy = SERVICE_POLICY

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
        error, a timeout or an interrupt carries no status and is not. One of
        the seven statuses is also rejected before processing (spec F D-F32)."""
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            self.usage["requests_refused"] = self.usage.get("requests_refused", 0) + 1
            if status in REJECTED_BEFORE_PROCESSING_STATUSES:
                key = "requests_rejected_before_processing"
                self.usage[key] = self.usage.get(key, 0) + 1

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

    def _alert(self, exc: BaseException, failed_attempt: int, attempts: int, pause: float) -> None:
        """Spec F D-F30: one line on standard error before each pause, in the
        one shape both repositories print (review X-M1); the pause in whole
        seconds rounded up, as the dashboard prints it (B101 ruling S1)."""
        when = self._now().astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        print(f"ALERT {when} {self.provider}:{self.model}: {_status_or_error(exc)}; attempt {failed_attempt} "
              f"of {attempts} failed; next attempt in {math.ceil(pause)} s", file=sys.stderr, flush=True)

    def _send(self, do_request, parameter_named):
        """Send one request through do_request() under the client's retry
        policy. Every attempt the SDK sent counts one requests_sent. A 400
        naming a declared parameter (counted), or a refusal raised before
        sending that names one (not counted), is DeclaredParameterRefused at
        once. A failure that may pass is sent again after the policy's pause;
        when the attempts run out, the terminal policy raises
        ProviderUnavailable and the service policy raises the last error. A
        failure no retry fixes is ProviderRefused under the terminal policy
        and the SDK's own error under the service policy. An interrupt, in a
        request or in a pause, is raised at once."""
        policy = self._retry_policy
        retries_used = 0
        while True:
            try:
                response = do_request()
            except Exception as exc:  # noqa: BLE001
                status = getattr(exc, "status_code", None)
                parameter = parameter_named(exc)
                if parameter is not None and (status == 400 or (status is None and not _is_connection_error(exc))):
                    if status is not None:
                        self._count_sent()  # the provider answered: a request sent (spec F D-F29)
                        self._count_refused(exc)
                    raise DeclaredParameterRefused(
                        self.provider, self.model, parameter, self._declared_value(parameter),
                        _status_or_error(exc),
                    ) from exc
                self._count_sent()  # it may have been billed; count every physical attempt
                self._count_refused(exc)
                if not _is_retryable(exc, policy):
                    # a lost connection is always retryable, so every failure here is a
                    # provider answer or an SDK error raised before sending (ruling P21)
                    if policy.stop_on_refusal:
                        raise ProviderRefused(_status_or_error(exc)) from exc
                    raise
                if retries_used == len(policy.pauses):
                    if policy.stop_when_exhausted:
                        raise ProviderUnavailable(policy.attempts, _status_or_error(exc)) from exc
                    raise
                retry_after = (retry_after_seconds(exc, self._now()) if policy.retry_after_reads_dates_and_ms
                               else _retry_after_header_seconds(exc))
                pause = policy.pause(retries_used, retry_after)
                if policy.alert:
                    self._alert(exc, retries_used + 1, policy.attempts, pause)
                self._wait(pause)
                retries_used += 1
                continue
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
    provider-reported token counts plus requests_sent, replies_with_usage,
    requests_refused (spec F D-F26 (g)) and requests_rejected_before_processing
    (spec F D-F32). The SDK's own retries are off
    (max_retries=0); the retry policy is the caller's (spec F D-F30).
    """

    provider = "openai"

    def __init__(self, cfg: ModelConfig, retry_policy: RetryPolicy = SERVICE_POLICY):
        from openai import OpenAI  # imported lazily so offline tests need no SDK

        self.model = cfg.generator_model
        self.usage = _new_usage()
        self._declared = cfg.generator_parameters
        self._retry_policy = retry_policy
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
    provider-reported token counts plus requests_sent, replies_with_usage,
    requests_refused (spec F D-F26 (g)) and requests_rejected_before_processing
    (spec F D-F32); a response without a complete
    usage block adds to calls and requests_sent only (thinking tokens are
    inside output_tokens). The SDK's own retries are off (max_retries=0);
    the retry policy is the caller's (spec F D-F30).
    """

    provider = "anthropic"

    def __init__(self, cfg: ModelConfig, max_tokens: int = 16000, retry_policy: RetryPolicy = SERVICE_POLICY):
        import anthropic  # imported lazily so offline tests need no SDK

        self.model = cfg.judge_model
        self.usage = _new_usage()
        self._declared = cfg.judge_parameters
        self._retry_policy = retry_policy
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

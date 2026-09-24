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

from typing import Protocol

from tere4ai.judge.config import ModelConfig


class ModelClient(Protocol):
    """Minimal contract the pipeline needs from any model backend."""

    model: str

    def complete(self, system: str, user: str) -> str:
        """Return the raw text completion for one system + user exchange."""
        ...


def _new_usage() -> dict[str, int]:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0}


# B74 (2026-09-16): current-generation models on both providers reject
# sampling parameters (gpt-6-astra answers 400 "temperature does not support
# 0 with this model"; the anthropic SDK 1.x no longer accepts the keyword
# at all). Every client still asks for temperature 0 first, learns a
# rejection ONCE for its lifetime instead of paying one refused request per
# call, and reports what was actually sent in the vocabulary the dashboard
# judge records ("0", "provider default (rejected by the model)", "mixed",
# "no replies"), so a build's provenance states the sampling regime rather
# than assuming it. B84 (spec F D-F22) extends the same learn-once rule to
# the requested effort level, reported below in the matching vocabulary.
SAMPLING_ZERO = "0"
SAMPLING_DEFAULT = "provider default (rejected by the model)"
SAMPLING_MIXED = "mixed"
SAMPLING_NONE = "no replies"

# B84 (spec F D-F22): the effort is part of the instrument. Every client
# sends the configured level and learns a rejection ONCE, like temperature;
# the outcome uses the same four shapes so a manifest reads one vocabulary.
EFFORT_NOT_APPLICABLE = "not applicable (rejected by the model)"
EFFORT_MIXED = "mixed"
EFFORT_NONE = "no replies"
EFFORT_NOT_CONFIGURED = "not configured"


class _SamplingRecord:
    """Mixin: which sampling parameter and which effort each reply was produced under."""

    # Class-level defaults so an instance built without __init__ (the offline
    # tests construct clients with __new__ and a stub transport) starts in
    # the same state as a real one; increments create instance attributes.
    _temperature_rejected: bool = False
    _json_mode_rejected: bool = False
    _replies_at_zero: int = 0
    _replies_at_default: int = 0
    _effort_requested: str | None = None
    _effort_rejected: bool = False
    _replies_with_effort: int = 0
    _replies_without_effort: int = 0

    def _init_sampling(self) -> None:
        self._temperature_rejected = False
        self._json_mode_rejected = False
        self._replies_at_zero = 0
        self._replies_at_default = 0

    def _record_reply(self, with_temperature: bool) -> None:
        if with_temperature:
            self._replies_at_zero += 1
        else:
            self._replies_at_default += 1

    @property
    def sampling(self) -> str:
        if self._replies_at_zero and self._replies_at_default:
            return SAMPLING_MIXED
        if self._replies_at_zero:
            return SAMPLING_ZERO
        if self._replies_at_default:
            return SAMPLING_DEFAULT
        return SAMPLING_NONE

    def _init_effort(self, requested: str | None) -> None:
        self._effort_requested = requested
        self._effort_rejected = False
        self._replies_with_effort = 0
        self._replies_without_effort = 0

    def _record_effort(self, with_effort: bool) -> None:
        if with_effort:
            self._replies_with_effort += 1
        else:
            self._replies_without_effort += 1

    @property
    def effort_requested(self) -> str | None:
        return self._effort_requested

    @property
    def effort(self) -> str:
        if self._effort_requested is None:
            return EFFORT_NOT_CONFIGURED
        if self._replies_with_effort and self._replies_without_effort:
            return EFFORT_MIXED
        if self._replies_with_effort:
            return self._effort_requested
        if self._replies_without_effort:
            return EFFORT_NOT_APPLICABLE
        return EFFORT_NONE


class OpenAIGenerator(_SamplingRecord):
    """Generator client (OpenAI family, cfg.generator_model).

    Asks for temperature 0 and JSON mode; each is dropped only after the
    model itself rejects it, and stays dropped for the client's lifetime.
    .usage accumulates provider-reported token counts across the client's
    lifetime (Section 13 observability); callers snapshot it to attribute
    spend to a unit of work. Counts are the provider's own numbers, never
    estimated here; a response without a usage block adds only to calls.
    """

    def __init__(self, cfg: ModelConfig):
        from openai import OpenAI  # imported lazily so offline tests need no SDK

        self.model = cfg.generator_model
        self.usage = _new_usage()
        self._init_sampling()
        self._init_effort(cfg.generator_effort)
        self._client = OpenAI(api_key=cfg.generator_api_key)

    def _request_kwargs(self, messages: list[dict[str, str]]) -> dict:
        kwargs: dict = {"model": self.model, "messages": messages}
        if not self._temperature_rejected:
            kwargs["temperature"] = 0
        if not self._json_mode_rejected:
            kwargs["response_format"] = {"type": "json_object"}
        if self._effort_requested is not None and not self._effort_rejected:
            kwargs["reasoning_effort"] = self._effort_requested
        return kwargs

    def complete(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = None
        for _attempt in range(4):
            kwargs = self._request_kwargs(messages)
            try:
                response = self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                learned = False
                if "temperature" in kwargs and "temperature" in message:
                    self._temperature_rejected = True
                    learned = True
                if "response_format" in kwargs and "response_format" in message:
                    self._json_mode_rejected = True
                    learned = True
                if "reasoning_effort" in kwargs and "reasoning_effort" in message:
                    self._effort_rejected = True
                    learned = True
                if not learned:
                    raise
        if response is None:  # pragma: no cover - three rejections at most
            raise RuntimeError("model request could not be formed")
        self._record_reply(with_temperature="temperature" in kwargs)
        self._record_effort(with_effort="reasoning_effort" in kwargs)
        self.usage["calls"] += 1
        reported = getattr(response, "usage", None)
        if reported is not None:
            self.usage["input_tokens"] += getattr(reported, "prompt_tokens", 0) or 0
            self.usage["output_tokens"] += getattr(reported, "completion_tokens", 0) or 0
        return response.choices[0].message.content or ""


class AnthropicJudge(_SamplingRecord):
    """Judge client (independent Claude family, cfg.judge_model).

    Asks for temperature 0, dropped for the client's lifetime once the
    SDK or the model rejects it. The output cap defaults to 16000 tokens
    because current Claude models think before answering and the thinking
    counts against max_tokens: the former 2048 would have truncated the
    judge's JSON mid-rationale. Only text blocks are returned; thinking
    blocks (empty by default) are skipped. .usage: same provider-reported
    accounting as OpenAIGenerator (thinking tokens are inside output_tokens).
    """

    def __init__(self, cfg: ModelConfig, max_tokens: int = 16000):
        import anthropic  # imported lazily so offline tests need no SDK

        self.model = cfg.judge_model
        self.usage = _new_usage()
        self._init_sampling()
        self._init_effort(cfg.judge_effort)
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=cfg.judge_api_key)

    def _request_kwargs(self, system: str, user: str) -> dict:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if not self._temperature_rejected:
            kwargs["temperature"] = 0
        if self._effort_requested is not None and not self._effort_rejected:
            kwargs["output_config"] = {"effort": self._effort_requested}
        return kwargs

    def complete(self, system: str, user: str) -> str:
        response = None
        for _attempt in range(3):
            kwargs = self._request_kwargs(system, user)
            try:
                response = self._client.messages.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                learned = False
                if "temperature" in kwargs and "temperature" in message:
                    self._temperature_rejected = True
                    learned = True
                if "output_config" in kwargs and "effort" in message:
                    self._effort_rejected = True
                    learned = True
                if not learned:
                    raise
        if response is None:  # pragma: no cover - two rejections at most
            raise RuntimeError("model request could not be formed")
        self._record_reply(with_temperature="temperature" in kwargs)
        self._record_effort(with_effort="output_config" in kwargs)
        self.usage["calls"] += 1
        reported = getattr(response, "usage", None)
        if reported is not None:
            self.usage["input_tokens"] += getattr(reported, "input_tokens", 0) or 0
            self.usage["output_tokens"] += getattr(reported, "output_tokens", 0) or 0
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

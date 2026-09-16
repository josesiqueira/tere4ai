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
# than assuming it.
SAMPLING_ZERO = "0"
SAMPLING_DEFAULT = "provider default (rejected by the model)"
SAMPLING_MIXED = "mixed"
SAMPLING_NONE = "no replies"


class _SamplingRecord:
    """Mixin: which sampling parameter each reply was produced under."""

    # Class-level defaults so an instance built without __init__ (the offline
    # tests construct clients with __new__ and a stub transport) starts in
    # the same state as a real one; increments create instance attributes.
    _temperature_rejected: bool = False
    _json_mode_rejected: bool = False
    _replies_at_zero: int = 0
    _replies_at_default: int = 0

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
        self._client = OpenAI(api_key=cfg.generator_api_key)

    def _request_kwargs(self, messages: list[dict[str, str]]) -> dict:
        kwargs: dict = {"model": self.model, "messages": messages}
        if not self._temperature_rejected:
            kwargs["temperature"] = 0
        if not self._json_mode_rejected:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def complete(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = None
        for _attempt in range(3):
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
                if not learned:
                    raise
        if response is None:  # pragma: no cover - two rejections at most
            raise RuntimeError("model request could not be formed")
        self._record_reply(with_temperature="temperature" in kwargs)
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
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=cfg.judge_api_key)

    def complete(self, system: str, user: str) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        with_temperature = not self._temperature_rejected
        if with_temperature:
            try:
                response = self._client.messages.create(temperature=0, **kwargs)
            except Exception as exc:  # noqa: BLE001
                if "temperature" not in str(exc):
                    raise
                self._temperature_rejected = True
                with_temperature = False
                response = self._client.messages.create(**kwargs)
        else:
            response = self._client.messages.create(**kwargs)
        self._record_reply(with_temperature=with_temperature)
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

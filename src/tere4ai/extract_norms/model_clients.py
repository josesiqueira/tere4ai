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


class OpenAIGenerator:
    """Generator client (OpenAI family, cfg.generator_model, temperature 0)."""

    def __init__(self, cfg: ModelConfig):
        from openai import OpenAI  # imported lazily so offline tests need no SDK

        self.model = cfg.generator_model
        self._client = OpenAI(api_key=cfg.generator_api_key)

    def complete(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            # Some models reject response_format or temperature overrides;
            # retry once without the JSON response hint before giving up.
            if "response_format" not in str(exc) and "temperature" not in str(exc):
                raise
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
        return response.choices[0].message.content or ""


class AnthropicJudge:
    """Judge client (independent Claude family, cfg.judge_model, temperature 0)."""

    def __init__(self, cfg: ModelConfig, max_tokens: int = 2048):
        import anthropic  # imported lazily so offline tests need no SDK

        self.model = cfg.judge_model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=cfg.judge_api_key)

    def complete(self, system: str, user: str) -> str:
        kwargs = dict(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        try:
            response = self._client.messages.create(temperature=0, **kwargs)
        except Exception as exc:  # noqa: BLE001
            # Some newer Claude models deprecate the temperature parameter;
            # retry once without it before giving up.
            if "temperature" not in str(exc):
                raise
            response = self._client.messages.create(**kwargs)
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

"""Runtime model configuration: generator and judge families.

@implements: DEC-07
@grounded_by: REF-24, ADD-16

Architecture.md Section 7 (decided 2026-07-08): the generator (extraction,
alignment, runtime generation) runs on OpenAI; the three judges (extraction,
mapping, runtime grounding) run on an independent non-OpenAI family
(Anthropic Claude), because same-family judges have correlated failure modes.

All model ids and keys are config values, never hardcoded. Missing
configuration fails fast with a clear message; the pipeline must never fall
back silently to a default model (no silent degradation, Section 13).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ModelConfigError(RuntimeError):
    """Raised when required model configuration is absent."""


# OpenAI-family name markers. The judge must not be any of these (DEC-07:
# same-family generator and judge have correlated failure modes). This is a
# deny-list, so it cannot prove family disjointness for an unknown vendor
# name; the generator-is-not-judge checks below close the most dangerous
# gap (the generator grading its own output) regardless of naming.
_OPENAI_FAMILY_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt", "openai", "davinci")


def assert_independent_judge(generator_model: str, judge_model: str) -> None:
    """Reject a judge that is not independent of the generator (DEC-07).

    Two failure modes: the judge is an OpenAI-family model (same family as
    the generator), or the judge is literally the same model id as the
    generator (the generator judging itself). Either collapses the control.
    """
    if judge_model.strip().lower().startswith(_OPENAI_FAMILY_PREFIXES):
        raise ModelConfigError(
            f"judge model {judge_model!r} looks like an OpenAI-family model; "
            "DEC-07 requires an independent non-OpenAI judge family."
        )
    if generator_model.strip().lower() == judge_model.strip().lower():
        raise ModelConfigError(
            f"generator and judge share the model id {generator_model!r}; "
            "DEC-07 requires an independent judge, not the generator judging "
            "its own output."
        )


def require_independent_clients(generator: object, judge: object) -> None:
    """Use-time guard against self-assessment (DEC-07).

    load_model_config enforces distinct model ids for production, but a
    programmatic caller can still pass one client object as both generator
    and judge, bypassing config. This catches that: the same object judging
    its own output is not a control. Distinct client objects that happen to
    share a model id (offline test stubs) are allowed here; production ids
    are already vetted at config load.
    """
    if generator is judge:
        raise ModelConfigError(
            "the same model client was passed as both generator and judge; "
            "DEC-07 requires an independent judge (self-assessment is not a "
            "control)."
        )


def _load_dotenv_once() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")


@dataclass(frozen=True)
class ModelConfig:
    """Pinned model configuration for one build or run."""

    generator_model: str
    judge_model: str
    generator_api_key: str
    judge_api_key: str

    def as_public_dict(self) -> dict[str, str]:
        """Loggable form: model ids only, never keys."""
        return {
            "generator_model": self.generator_model,
            "judge_model": self.judge_model,
        }


def load_model_config(env: dict[str, str] | None = None) -> ModelConfig:
    """Load and validate the model configuration.

    env defaults to os.environ (after loading .env). Raises ModelConfigError
    listing every missing variable at once, so a misconfigured run stops
    before any model call.
    """
    if env is None:
        _load_dotenv_once()
        env = dict(os.environ)

    required = {
        "TERE4AI_GENERATOR_MODEL": "generator model id (OpenAI family)",
        "TERE4AI_JUDGE_MODEL": "judge model id (independent non-OpenAI family, DEC-07)",
        "OPENAI_API_KEY": "generator API key",
        "ANTHROPIC_API_KEY": "judge API key",
    }
    missing = [name for name in required if not env.get(name)]
    if missing:
        details = "; ".join(f"{name} ({required[name]})" for name in missing)
        raise ModelConfigError(
            f"missing model configuration: {details}. Set these in .env "
            "(see .env.example); the pipeline never falls back to defaults."
        )

    judge_model = env["TERE4AI_JUDGE_MODEL"]
    generator_model = env["TERE4AI_GENERATOR_MODEL"]
    assert_independent_judge(generator_model, judge_model)

    return ModelConfig(
        generator_model=generator_model,
        judge_model=judge_model,
        generator_api_key=env["OPENAI_API_KEY"],
        judge_api_key=env["ANTHROPIC_API_KEY"],
    )

"""The extraction generator's settings as a norms dump records them.

Spec F D-F22 and D-F29: the effort and the declared temperature are shown
wherever the model id is. A norms dump records them once, in its build
block (extraction_effort, extraction_temperature), not on each norm, so the
readers that name a norm's extractor model read them here.
"""

from __future__ import annotations

from typing import Any


def extraction_generator_settings(norms_payload: dict[str, Any], norm: dict[str, Any]) -> tuple[str | None, str | None]:
    """(effort, temperature) of the generator that extracted the norm.

    None for a value the dump does not record (a dump made before it was
    recorded), never invented; (None, None) for a norm a person wrote,
    whose extractor_model is human:<name>, since no model made it.
    """
    if str(norm.get("extractor_model") or "").startswith("human:"):
        return None, None
    build = norms_payload.get("build") if isinstance(norms_payload.get("build"), dict) else {}

    def generator(key: str) -> str | None:
        block = build.get(key)
        value = block.get("generator") if isinstance(block, dict) else None
        return None if value is None else str(value)

    return generator("extraction_effort"), generator("extraction_temperature")

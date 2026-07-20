"""Feature elicitation: free-text system description to system_features.

@implements: DEC-13
@grounded_by: REF-17, REF-16

The trust split of USER.md holds: the LLM extracts FACTS from the given
text, the rule ladder decides. The elicitor never outputs a risk category.
Flags are emitted true or false ONLY when the text supports them; anything
the text does not settle is omitted, which the classifier then surfaces in
missing_facts. Output is validated against
schema/json_schemas/system_features.schema.json; invalid output gets one
retry and then returns None (the caller keeps the honest-abstention path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
PROMPT_PATH = ROOT / "prompts" / "elicit_features" / "v1.md"

_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_validator = Draft202012Validator(_schema)


def _clean(candidate: dict[str, Any], description: str) -> dict[str, Any]:
    """Keep only schema-known fields; force the original description."""
    allowed = set(_schema["properties"])
    cleaned = {k: v for k, v in candidate.items() if k in allowed}
    cleaned["description"] = description
    flags = cleaned.get("flags")
    if isinstance(flags, dict):
        allowed_flags = set(_schema["properties"]["flags"]["properties"])
        cleaned["flags"] = {
            k: v for k, v in flags.items() if k in allowed_flags and isinstance(v, bool)
        }
    return cleaned


def elicit_features(
    description: str,
    generator: Any,
    prompt_version: str = "v3",
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (schema-valid system_features, notes) or (None, notes).

    Never guesses: the prompt requires textual support for every flag, and
    schema validation plus field allow-listing runs mechanically here.
    """
    prompt_path = PROMPT_PATH.with_name(f"{prompt_version}.md")
    system = prompt_path.read_text(encoding="utf-8")
    notes: list[str] = []

    for attempt in (1, 2):
        raw = generator.complete(system, description)
        try:
            candidate = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            notes.append(f"attempt {attempt}: generator output was not valid JSON")
            continue
        if not isinstance(candidate, dict):
            notes.append(f"attempt {attempt}: generator output was not an object")
            continue
        cleaned = _clean(candidate, description)
        errors = list(_validator.iter_errors(cleaned))
        if errors:
            notes.append(
                f"attempt {attempt}: schema violations: "
                + "; ".join(e.message for e in errors[:3])
            )
            continue
        notes.append(f"elicited on attempt {attempt}")
        return cleaned, notes

    notes.append("elicitation failed; caller must keep the abstention path")
    return None, notes

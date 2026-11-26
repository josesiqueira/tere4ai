"""Cases of the B184 tests (DEC-32): every schema fact known false, then the overrides.

The flag names are read from the schema file, so a case keeps up with the
schema without a list of its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"


def _flag_names() -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(schema["properties"]["flags"]["properties"])


def all_false(**overrides: Any) -> dict[str, Any]:
    """Every flag the schema file defines set false, then the overrides."""
    flags: dict[str, Any] = dict.fromkeys(_flag_names(), False)
    flags.update(overrides)
    return flags


def case(
    flags: dict[str, Any],
    domain: str | None = None,
    autonomy: str | None = None,
    deployer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A features input for classify_ai_system; the description is context only."""
    features: dict[str, Any] = {"description": "B184 test system; the description is context only.", "flags": flags}
    if domain is not None:
        features["domain"] = domain
    if autonomy is not None:
        features["autonomy"] = autonomy
    if deployer is not None:
        features["deployer"] = deployer
    return features

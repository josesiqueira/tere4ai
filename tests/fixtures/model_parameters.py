"""Mock data for the declared model parameters (spec F D-F29).

Rows and tables for the tests only. The documentation address uses the
reserved .invalid domain (RFC 2606), so no test names a real provider page.
"""

from __future__ import annotations

import json
from pathlib import Path

from tere4ai.judge.config import ModelParameters

DOC_URL = "https://docs.example.invalid/models"
READ_ON = "2026-09-27"


def declared(model_id: str, provider: str, *, temperature: str = "0", effort: str = "xhigh",
             json_mode: str | None = None) -> ModelParameters:
    if json_mode is None:
        json_mode = "sent" if provider == "openai" else "N/A"
    return ModelParameters(model_id=model_id, provider=provider, temperature=temperature, effort=effort,
                           json_mode=json_mode, documentation_url=DOC_URL, documentation_read_on=READ_ON)


def table(*rows: ModelParameters) -> dict:
    return {"schema_version": 1, "about": "mock data",
            "models": {row.model_id: row.as_row() for row in rows}}


def write_table(path: Path, *rows: ModelParameters) -> Path:
    path.write_text(json.dumps(table(*rows)), encoding="utf-8")
    return path

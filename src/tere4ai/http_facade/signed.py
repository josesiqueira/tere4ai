"""The signed record of a generator-only answer (DEC-24).

@implements: DEC-24

DEC-24 is an engineering decision for the dashboard's demonstration; it needs
no literature grounding (AGENTS.md's grounding bar), so no @grounded_by.

The facade keeps no state and builds its clients per request, so a judge
route knows that it judges exactly what the generator wrote, for the caller
and the generation it was written for, only through a signature the facade
made when it answered (spec G D-G74 (3), rulings S52, S70, S71). The record
holds the format version, the route, a generation id drawn at random (UUID
version 4), the caller reference, the sorted norm ids, the graph version and
norms build, the generator's model and prompt, the judge prompt the judge
route will use, the SHA-256 of the untrusted text the generator read, and the
answer's core as returned. Its bytes are the record as JSON with keys sorted
at every level, the separators "," and ":" without spaces, non-ASCII written
as UTF-8, every field present (null where empty) and no floating-point
number, so a copy stored as Postgres jsonb (which reorders keys) gives the
same bytes again. The signature is HMAC-SHA256 over those bytes, written as
64 hexadecimal characters and compared with hmac.compare_digest.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from typing import Any

FORMAT = "tere4ai.signed_answer.v1"
RECORD_FIELDS: tuple[str, ...] = (
    "format", "route", "generation_id", "caller", "norm_ids", "graph_version", "norms_build",
    "generator_model", "generator_prompt", "judge_prompt", "untrusted_sha256", "core",
)
CALLER_FIELDS: tuple[str, ...] = ("project", "repository_run", "document")
PROMPT_FIELDS: tuple[str, ...] = ("name", "version")
EVIDENCE_CORE_FIELDS: tuple[str, ...] = (
    "tool", "norm_id", "artifact_type", "artifact_id", "assessment", "quotes", "gaps", "rationale",
)
BACKLOG_CORE_FIELDS: tuple[str, ...] = ("items",)
ROUTES: dict[str, tuple[str, ...]] = {"/api/evidence": EVIDENCE_CORE_FIELDS, "/api/backlog": BACKLOG_CORE_FIELDS}
_SIGNATURE = re.compile(r"[0-9a-f]{64}", re.ASCII)


class RecordError(ValueError):
    """A record that is not a record of this format: a field missing or
    unknown, a floating-point number, a value of the wrong kind."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _no_floats(value: Any, where: str) -> None:
    if isinstance(value, float):
        raise RecordError(f"{where} is a floating-point number; a signed record holds none")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecordError(f"{where} has a key that is not a string")
            _no_floats(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _no_floats(item, f"{where}[{index}]")


def _exact_keys(value: Any, fields: tuple[str, ...], where: str) -> None:
    if not isinstance(value, dict) or set(value) != set(fields):
        raise RecordError(f"{where} must hold exactly the fields {', '.join(fields)}")


_TEXT_FIELDS: tuple[str, ...] = (
    "format", "route", "generation_id", "graph_version", "norms_build", "generator_model", "untrusted_sha256",
)


def _text(value: Any, where: str, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise RecordError(f"{where} must be text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise RecordError(f"{where} holds a character UTF-8 cannot write (a lone surrogate)") from None


def _encodable(value: Any, where: str) -> None:
    """Every string of the record, keys included, writable as UTF-8."""
    if isinstance(value, str):
        _text(value, where)
    elif isinstance(value, dict):
        for key, item in value.items():
            _text(key, f"{where} key")
            _encodable(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _encodable(item, f"{where}[{index}]")


def check_record(record: Any) -> dict[str, Any]:
    """The record if it has this format's shape; RecordError naming the
    first field that does not. Every value is of its kind and writable as
    UTF-8, so nothing after this check raises on a record a client sent
    (ruling R68)."""
    _exact_keys(record, RECORD_FIELDS, "the record")
    for name in _TEXT_FIELDS:
        _text(record[name], f"the record's {name}")
    if record["format"] != FORMAT:
        raise RecordError(f"the record's format is {record['format']!r}, not {FORMAT!r}")
    if record["route"] not in ROUTES:
        raise RecordError(f"the record's route {record['route']!r} is not a route that signs")
    _exact_keys(record["caller"], CALLER_FIELDS, "the record's caller")
    for field in CALLER_FIELDS:
        _text(record["caller"][field], f"the record's caller.{field}", nullable=True)
    for name in ("generator_prompt", "judge_prompt"):
        _exact_keys(record[name], PROMPT_FIELDS, f"the record's {name}")
        for field in PROMPT_FIELDS:
            _text(record[name][field], f"the record's {name}.{field}")
    _exact_keys(record["core"], ROUTES[record["route"]], "the record's core")
    norm_ids = record["norm_ids"]
    if not isinstance(norm_ids, list) or not all(isinstance(n, str) for n in norm_ids) or norm_ids != sorted(norm_ids):
        raise RecordError("the record's norm_ids must be a sorted list of text")
    _no_floats(record, "the record")
    _encodable(record, "the record")
    return record


def canonical_bytes(record: dict[str, Any]) -> bytes:
    """The record's bytes: keys sorted at every level, no spaces, UTF-8."""
    check_record(record)
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sign(record: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical_bytes(record), hashlib.sha256).hexdigest()


def verify(record: Any, signature: Any, key: bytes) -> bool:
    """True only for a record of this format whose signature is the facade's;
    never raises on a malformed record or signature."""
    if not isinstance(signature, str) or not _SIGNATURE.fullmatch(signature):
        return False
    try:
        expected = sign(record, key)
    except (RecordError, TypeError, ValueError, RecursionError):
        return False
    return hmac.compare_digest(expected, signature)


def build_record(*, route: str, caller: dict[str, Any], norm_ids: list[str], graph_version: str, norms_build: str,
                 generator_model: str, generator_prompt: dict[str, str], judge_prompt: dict[str, str],
                 untrusted_text: str, core: dict[str, Any], generation_id: str | None = None) -> dict[str, Any]:
    """A record of this format, every field present, the norm ids sorted."""
    record = {
        "format": FORMAT,
        "route": route,
        "generation_id": generation_id or str(uuid.uuid4()),
        "caller": {field: caller.get(field) for field in CALLER_FIELDS},
        "norm_ids": sorted(norm_ids),
        "graph_version": graph_version,
        "norms_build": norms_build,
        "generator_model": generator_model,
        "generator_prompt": {field: generator_prompt.get(field) for field in PROMPT_FIELDS},
        "judge_prompt": {field: judge_prompt.get(field) for field in PROMPT_FIELDS},
        "untrusted_sha256": sha256_text(untrusted_text),
        "core": {field: core.get(field) for field in ROUTES[route]},
    }
    return check_record(record)

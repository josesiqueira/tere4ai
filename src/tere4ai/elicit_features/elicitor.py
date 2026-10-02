"""Feature elicitation: free-text system description to system_features.

@implements: DEC-13, DEC-18
@grounded_by: REF-17, REF-16

The trust split of USER.md holds: the LLM extracts FACTS from the given
text, the rule ladder decides. The elicitor never outputs a risk category.
Flags are emitted true or false ONLY when the text supports them; anything
the text does not settle is omitted, which the classifier then surfaces in
missing_facts. Output is validated against
schema/json_schemas/system_features.schema.json; invalid output gets one
retry and then returns None (the caller keeps the honest-abstention path).

B10: a template with provision placeholders (v6 on) is rendered from the
graph dump of the build the call is served on before any model call; a
provision that does not resolve stops the call. Its reply carries
"features" and "quotes", and a fact is kept only with a quote of at least
three words found in the description (character identity after collapsing
whitespace runs, no case folding); every other fact is dropped and named.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.elicit_features.provisions import (
    PLACEHOLDER_RE,
    ProvisionUnresolved,
    render_template,
)
from tere4ai.extract_norms.pipeline import prompt_sha256

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
PROMPT_PATH = ROOT / "prompts" / "elicit_features" / "v1.md"
DUMP_DIR = ROOT / "data" / "graph_dumps"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
PROMPT_NAME = "elicit_features"
# DEC-18: the one default prompt version; the facade's elicit_envelope and
# scripts/elicit_benchmark_features.py import it rather than repeat it.
DEFAULT_PROMPT_VERSION = "v6"
MIN_QUOTE_WORDS = 3
# Fact paths with a level below the top: "flags.<name>", "deployer.<key>".
NESTED_FACT_FIELDS = ("flags", "deployer")

_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_validator = Draft202012Validator(_schema)


@dataclass(frozen=True)
class Elicitation:
    """One elicitation: the proposed facts and what supports them.

    features: schema-valid system_features, or None when elicitation
    failed. quotes: {fact path: {"text", "start", "end"}}, the words of the
    description each kept fact rests on (start and end are code point
    offsets into the original description, text its slice there). dropped:
    [{"path", "reason"}] for each fact removed for want of a quote. prompt:
    the instrument, {"prompt", "version", "template_sha256",
    "rendered_sha256", "provisions", "graph_version"}.
    """

    features: dict[str, Any] | None
    quotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    dropped: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    prompt: dict[str, Any] = field(default_factory=dict)


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


def _schema_errors(features: dict[str, Any]) -> list[str]:
    return [e.message for e in _validator.iter_errors(features)]


def _collapsed_with_offsets(text: str) -> tuple[str, list[int]]:
    """text with each whitespace run made one space, and for each character
    of the result the index of the original character it stands for."""
    chars: list[str] = []
    offsets: list[int] = []
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                chars.append(" ")
                offsets.append(index)
            in_space = True
        else:
            chars.append(char)
            offsets.append(index)
            in_space = False
    return "".join(chars), offsets


def _locate(quote: Any, description: str) -> tuple[dict[str, Any] | None, str | None]:
    """({"text", "start", "end"}, None) when the quote is in the description,
    else (None, the reason the fact is dropped)."""
    if not isinstance(quote, str) or not quote.strip():
        return None, "no quote"
    words = quote.split()
    if len(words) < MIN_QUOTE_WORDS:
        return None, "quote shorter than three words"
    needle = " ".join(words)
    haystack, offsets = _collapsed_with_offsets(description)
    at = haystack.find(needle)
    if at < 0:
        return None, "quote not in the description"
    start = offsets[at]
    end = offsets[at + len(needle) - 1] + 1
    return {"text": description[start:end], "start": start, "end": end}, None


def _fact_paths(features: dict[str, Any]) -> list[str]:
    """Every fact the features state, as the paths the quotes are keyed by."""
    paths: list[str] = []
    for key, value in features.items():
        if key == "description":
            continue
        if key in NESTED_FACT_FIELDS and isinstance(value, dict):
            paths.extend(f"{key}.{name}" for name in value)
        else:
            paths.append(key)
    return paths


def _remove(features: dict[str, Any], path: str) -> None:
    head, _, name = path.partition(".")
    if name:
        features[head].pop(name, None)
    else:
        features.pop(head, None)


def _keep_quoted(
    features: dict[str, Any], quotes: dict[str, Any], description: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, str]], list[str]]:
    """Remove every fact without a quote found in the description."""
    kept_features = copy.deepcopy(features)
    kept: dict[str, dict[str, Any]] = {}
    dropped: list[dict[str, str]] = []
    paths = _fact_paths(features)
    for path in paths:
        located, reason = _locate(quotes.get(path), description)
        if located is None:
            _remove(kept_features, path)
            dropped.append({"path": path, "reason": reason or "no quote"})
        else:
            kept[path] = located
    for name in NESTED_FACT_FIELDS:
        if kept_features.get(name) == {}:
            del kept_features[name]
    notes = [
        f"quote for {path} ignored: the features carry no such fact"
        for path in quotes
        if path not in paths
    ]
    return kept_features, kept, dropped, notes


def _parse_quoted(
    candidate: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Split a v6 reply into (features, quotes) or name its schema violation."""
    if not isinstance(candidate, dict):
        return None, None, "generator output was not an object"
    for name in ("features", "quotes"):
        if name not in candidate:
            return None, None, f'schema violations: "{name}" is missing'
        if not isinstance(candidate[name], dict):
            return None, None, f'schema violations: "{name}" is not an object'
    return candidate["features"], candidate["quotes"], None


def _template(prompt_version: str, dump: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The template text and its record before rendering (rendered_sha256
    None, provisions empty). The hash is of the file's bytes, the text those
    bytes decoded, so the two are the same bytes."""
    template_bytes = PROMPT_PATH.with_name(f"{prompt_version}.md").read_bytes()
    build = dump.get("build") if isinstance(dump, dict) else None
    graph_version = (
        str(build["build_id"]) if isinstance(build, dict) and build.get("build_id") else None
    )
    return template_bytes.decode("utf-8"), {
        "prompt": PROMPT_NAME,
        "version": prompt_version,
        "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
        "rendered_sha256": None,
        "provisions": [],
        "graph_version": graph_version,
    }


def render_prompt(
    dump: dict[str, Any],
    snapshots_dir: Path | str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, dict[str, Any]]:
    """The system prompt a call over this build sends, and its record
    {"prompt", "version", "template_sha256", "rendered_sha256",
    "provisions", "graph_version"}. Makes no model call; raises
    ProvisionUnresolved when a provision does not resolve. elicit() uses it,
    and scripts/elicit_benchmark_features.py records a run's prompt with it
    once before the first item."""
    template, prompt = _template(prompt_version, dump)
    system, provisions = render_template(template, dump, snapshots_dir)
    prompt["rendered_sha256"] = prompt_sha256(system)
    prompt["provisions"] = [p["node_id"] for p in provisions]
    return system, prompt


def elicit(
    description: str,
    generator: Any,
    *,
    dump: dict[str, Any],
    snapshots_dir: Path | str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> Elicitation:
    """Render the prompt over the served build, then elicit with quotes.

    A template without provision placeholders (v1 to v5) parses as before:
    the whole reply object is the features, and quotes and dropped stay
    empty. A template with placeholders is rendered from the dump first;
    ProvisionUnresolved returns features None with no generator call.
    """
    template, unrendered = _template(prompt_version, dump)
    quoted = PLACEHOLDER_RE.search(template) is not None
    try:
        system, prompt = render_prompt(dump, snapshots_dir, prompt_version)
    except ProvisionUnresolved as exc:
        return Elicitation(
            features=None,
            notes=[
                f"definition {exc.node_id} does not resolve in {exc.build}: "
                f"{exc.reason}; no model call made"
            ],
            prompt=unrendered,
        )
    notes: list[str] = []

    for attempt in (1, 2):
        raw = generator.complete(system, description)
        try:
            candidate = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            notes.append(f"attempt {attempt}: generator output was not valid JSON")
            continue
        quotes: dict[str, Any] = {}
        if quoted:
            features, quotes, violation = _parse_quoted(candidate)
            if violation is not None:
                notes.append(f"attempt {attempt}: {violation}")
                continue
            candidate = features
        if not isinstance(candidate, dict):
            notes.append(f"attempt {attempt}: generator output was not an object")
            continue
        cleaned = _clean(candidate, description)
        errors = _schema_errors(cleaned)
        if errors:
            notes.append(f"attempt {attempt}: schema violations: " + "; ".join(errors[:3]))
            continue
        if not quoted:
            notes.append(f"elicited on attempt {attempt}")
            return Elicitation(features=cleaned, notes=notes, prompt=prompt)
        kept, kept_quotes, dropped, quote_notes = _keep_quoted(cleaned, quotes, description)
        errors = _schema_errors(kept)
        if errors:
            notes.append(
                f"attempt {attempt}: schema violations after dropping unquoted facts: "
                + "; ".join(errors[:3])
            )
            continue
        notes.extend(quote_notes)
        notes.append(f"elicited on attempt {attempt}")
        return Elicitation(
            features=kept, quotes=kept_quotes, dropped=dropped, notes=notes, prompt=prompt
        )

    notes.append("elicitation failed; caller must keep the abstention path")
    return Elicitation(features=None, notes=notes, prompt=prompt)


def schema_flag_names() -> list[str]:
    """Sorted names of every flag in system_features.schema.json."""
    return sorted(_schema["properties"]["flags"]["properties"].keys())

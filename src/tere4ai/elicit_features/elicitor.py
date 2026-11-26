"""Feature elicitation: free-text system description to system_features.

@implements: DEC-13, DEC-18
@implements: DEC-23
@implements: DEC-32
@implements: DEC-33
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
whitespace runs, no case folding, starting and ending on word boundaries);
every other fact is dropped and named. A field set to null or to an empty
list states no fact: it is removed as unknown, needs no quote and is not
named as dropped.

B184 (fix round 1): a field or flag the reply proposes that the schema does
not define is not kept, and the notes name it once,
OUTSIDE_SCHEMA_NOTE, whether or not the reply quoted it; the note that its
quote was ignored is then not added for the same path.

B185 (DEC-33, ruling P3): a proposed `domain` that is none_of_these_areas,
or that is not a value of the schema, is dropped before the schema check
(_drop_domain) and named in dropped with its reason, so one wrong word never
fails the whole elicitation; none_of_these_areas is a person's statement and
is never taken from a proposal, whatever the prompt says.
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
from tere4ai.mcp_server.removed_facts import (
    DOMAIN_NONE_OF_THESE_AREAS,
    domain_is_a_value,
    domain_refusal,
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
PROMPT_PATH = ROOT / "prompts" / "elicit_features" / "v1.md"
DUMP_DIR = ROOT / "data" / "graph_dumps"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
PROMPT_NAME = "elicit_features"
# DEC-18: the one default prompt version; the facade's elicit_envelope and
# scripts/elicit_benchmark_features.py import it rather than repeat it.
# B132 (spec G D-G68 (6)): v7 follows the Act as amended (the amended Annex I
# points, points (ba) and (bb) as Article 5 nodes, the Annex I section fact).
# B160: v8 is v7 with the fact deployer_actor renamed deployer_kind, the
# version of record for B74.
# B184 (spec G D-G91, DEC-32): v9 asks the 54 facts of the schema, the 25
# Annex III listed uses under one heading per point, law_enforcement_purpose
# under Article 5(1)(h), and the Article 6(3) points (a) and (d) as two
# facts; v8 stays as the prompt of tag v2.0.0-beta.1.
DEFAULT_PROMPT_VERSION = "v9"
MIN_QUOTE_WORDS = 3
# B184 fix round 1: the note for a field or flag outside the schema.
OUTSIDE_SCHEMA_NOTE = "{path} was proposed but is not a fact of the schema; it was not kept"
# B185 (DEC-33, rulings P3 and P30): the reasons a proposed domain is dropped.
DOMAIN_DROP_NONE_REASON = (
    "none_of_these_areas is never taken from a proposal (DEC-33); the domain is left unknown"
)
DOMAIN_DROP_OUTSIDE_REASON = "{refusal}; the domain is left unknown"
# Fact paths with a level below the top: "flags.<name>", "deployer.<key>".
NESTED_FACT_FIELDS = ("flags", "deployer")

_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_validator = Draft202012Validator(_schema)

# B160 ruling R6: the fact's name before B160. Live input carrying it is
# refused by the schema; only features_of_record reads it, in facts stored
# before B160. Deleted with the pre-B74 records after B74.
FACT_NAME_BEFORE_B160 = "deployer_actor"


def features_of_record(features: dict) -> dict:
    """Facts stored before B160 (the benchmark gold features of prompts v1
    and v2, the recorded demo sessions) as the schema reads them today: a
    copy with deployer_actor renamed deployer_kind, its value kept. When both
    keys are present, deployer_kind is kept and the old key dropped. The
    input is never changed (B160 ruling R6)."""
    if FACT_NAME_BEFORE_B160 not in features:
        return dict(features)
    renamed = {k: v for k, v in features.items() if k != FACT_NAME_BEFORE_B160}
    renamed.setdefault("deployer_kind", features[FACT_NAME_BEFORE_B160])
    return renamed


@dataclass(frozen=True)
class Elicitation:
    """One elicitation: the proposed facts and what supports them.

    features: schema-valid system_features, or None when elicitation
    failed. quotes: {fact path: {"text", "start", "end"}}, the words of the
    description each kept fact rests on (start and end are code point
    offsets into the original description, text its slice there). dropped:
    [{"path", "reason"}] for each fact removed for want of a quote, and for a
    proposed domain the elicitor cannot take (B185, _drop_domain). prompt:
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


def _outside_schema(candidate: dict[str, Any]) -> list[str]:
    """The paths of the fields and flags the candidate proposes that the
    schema does not define, in the candidate's order: the ones _clean drops
    by name ("description" is the schema's own field and never counted)."""
    allowed = set(_schema["properties"])
    paths = [k for k in candidate if k not in allowed]
    flags = candidate.get("flags")
    if isinstance(flags, dict):
        allowed_flags = set(_schema["properties"]["flags"]["properties"])
        paths.extend(f"flags.{k}" for k in flags if k not in allowed_flags)
    return paths


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


def _on_word_boundaries(text: str, start: int, end: int) -> bool:
    """True when text[start:end] neither begins nor ends inside a word: the
    character before it and the character after it, where there is one, is
    not a letter or digit."""
    before_ok = start == 0 or not text[start - 1].isalnum()
    after_ok = end == len(text) or not text[end].isalnum()
    return before_ok and after_ok


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
    while at >= 0 and not _on_word_boundaries(haystack, at, at + len(needle)):
        at = haystack.find(needle, at + 1)
    if at < 0:
        return None, "quote not in the description"
    start = offsets[at]
    end = offsets[at + len(needle) - 1] + 1
    return {"text": description[start:end], "start": start, "end": end}, None


def _is_unknown(value: Any) -> bool:
    """A value that states no fact: None or an empty list."""
    return value is None or value == []


def _without_unknowns(features: dict[str, Any]) -> dict[str, Any]:
    """features without the fields that state no fact (None or an empty
    list, and a deployer key set to None): such a field is unknown, so it
    needs no quote and is not a dropped fact (B10 final review)."""
    kept = {k: v for k, v in features.items() if not _is_unknown(v)}
    deployer = kept.get("deployer")
    if isinstance(deployer, dict):
        kept["deployer"] = {k: v for k, v in deployer.items() if v is not None}
    return kept


def _drop_domain(features: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """features without a proposed domain the elicitor cannot take, and the
    dropped entry naming it (B185, ruling P3).

    none_of_these_areas is never taken from a proposal (DEC-33, spec G D-G92
    (iii)); a value that is not a value of the schema is dropped with the
    schema's refusal (domain_refusal, ruling P30). A null or absent domain,
    or a value of the list that names an area, is kept as it is. The input
    is never changed.

    @implements: DEC-33
    """
    if "domain" not in features or features["domain"] is None:
        return features, []
    proposed = features["domain"]
    if proposed == DOMAIN_NONE_OF_THESE_AREAS:
        reason = DOMAIN_DROP_NONE_REASON
    elif not domain_is_a_value(proposed):
        reason = DOMAIN_DROP_OUTSIDE_REASON.format(refusal=domain_refusal(proposed))
    else:
        return features, []
    kept = {k: v for k, v in features.items() if k != "domain"}
    return kept, [{"path": "domain", "reason": reason}]


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
    the whole reply object is the features, quotes stay empty and dropped
    names only a domain _drop_domain removed (B185). A template with placeholders is rendered from the dump first;
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
            candidate = _without_unknowns(features)
        if not isinstance(candidate, dict):
            notes.append(f"attempt {attempt}: generator output was not an object")
            continue
        # B185 (ruling P3): after _without_unknowns, before _outside_schema.
        candidate, domain_dropped = _drop_domain(candidate)
        outside = _outside_schema(candidate)
        cleaned = _clean(candidate, description)
        errors = _schema_errors(cleaned)
        if errors:
            notes.append(f"attempt {attempt}: schema violations: " + "; ".join(errors[:3]))
            continue
        outside_notes = [OUTSIDE_SCHEMA_NOTE.format(path=path) for path in outside]
        if not quoted:
            notes.extend(outside_notes)
            notes.append(f"elicited on attempt {attempt}")
            return Elicitation(features=cleaned, dropped=domain_dropped, notes=notes, prompt=prompt)
        kept, kept_quotes, dropped, quote_notes = _keep_quoted(cleaned, quotes, description)
        dropped = [*domain_dropped, *dropped]
        errors = _schema_errors(kept)
        if errors:
            notes.append(
                f"attempt {attempt}: schema violations after dropping unquoted facts: "
                + "; ".join(errors[:3])
            )
            continue
        notes.extend(outside_notes)
        # A dropped domain is named in dropped, so its quote is not also
        # reported as ignored (B185).
        named = [*outside, *(entry["path"] for entry in domain_dropped)]
        notes.extend(
            note for note in quote_notes
            if not any(note.startswith(f"quote for {path} ignored") for path in named)
        )
        notes.append(f"elicited on attempt {attempt}")
        return Elicitation(
            features=kept, quotes=kept_quotes, dropped=dropped, notes=notes, prompt=prompt
        )

    notes.append("elicitation failed; caller must keep the abstention path")
    return Elicitation(features=None, notes=notes, prompt=prompt)


def schema_flag_names() -> list[str]:
    """Sorted names of every flag in system_features.schema.json."""
    return sorted(_schema["properties"]["flags"]["properties"].keys())

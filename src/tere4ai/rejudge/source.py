"""The source build a rejudge run reads, and the rule its new build is named by.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

A published build folder (the publication of scripts/publish_layer23.py,
activated by scripts/activate_build.py) is found through its activation
pointer: ACTIVE_MANIFEST.json names the chain, publications/<chain>.json
names the record and the three published files with their sha256, and
build_records/<record>.json holds the record. Everything is read as plain
JSON and every file's digest is checked; the folder is never opened as a
build record store, since a store writes lock files (B173 global
constraints), and nothing in it is written.

The new build's name (B173 R11): <date>-<source name without its leading
date>-<judge model without a leading "claude-">, any valid date, with an
optional trailing -N; 2026-10-14-gpt-6-astra-high judged by claude-opus-5-5
on 2026-10-16 gives 2026-10-16-gpt-6-astra-high-opus-5-5.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from tere4ai.graph_store.build_chain import sha256_of_file

ACTIVE_POINTER = "ACTIVE_MANIFEST.json"
PUBLISHED_KINDS = ("layer1_dump", "norms", "alignments")
_LEADING_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


class SourceError(RuntimeError):
    """The source folder is not a published build this command can read."""


@dataclass(frozen=True)
class SourceBuild:
    """A published build, as its publication manifest names it."""

    dir: Path
    name: str
    record_id: str
    chain_id: str
    layer1_path: Path
    norms_path: Path
    alignments_path: Path
    layer1_sha256: str
    norms_sha256: str
    alignments_sha256: str
    record: dict[str, Any]


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SourceError(f"{what} {path.name} is missing in {path.parent}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"{what} {path.name} cannot be read ({type(exc).__name__})") from None


def read_source(source_dir: Path | str) -> SourceBuild:
    """The published build in source_dir: the activated chain, its record and
    its three files, each file verified against the digest its publication
    manifest records. Raises SourceError naming what is missing or differs."""
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise SourceError(f"the source {source_dir} is not a folder")
    pointer = _read_json(source_dir / ACTIVE_POINTER, "the activation pointer")
    chain_id = pointer.get("chain_id") if isinstance(pointer, dict) else None
    if not isinstance(chain_id, str) or not chain_id:
        raise SourceError(f"{ACTIVE_POINTER} names no chain")
    manifest = _read_json(source_dir / "publications" / f"{chain_id}.json", "the publication manifest")
    if not isinstance(manifest, dict):
        raise SourceError(f"the publication manifest of chain {chain_id} is not an object")
    record_id = manifest.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise SourceError(f"the publication manifest of chain {chain_id} names no record")
    by_kind = {i.get("input_kind"): i for i in manifest.get("inputs") or [] if isinstance(i, dict)}
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    for kind in PUBLISHED_KINDS:
        entry = by_kind.get(kind)
        if entry is None or not entry.get("file") or not entry.get("sha256"):
            raise SourceError(f"the publication manifest of chain {chain_id} names no {kind} input with its sha256")
        path = source_dir / entry["file"]
        if not path.is_file():
            raise SourceError(f"the published {kind} file {entry['file']} is missing")
        actual = sha256_of_file(path)
        if actual != entry["sha256"]:
            raise SourceError(f"the published {kind} file {entry['file']} has sha256 {actual}, "
                              f"the publication recorded {entry['sha256']}")
        paths[kind], digests[kind] = path, actual
    record = _read_json(source_dir / "build_records" / f"{record_id}.json", "the build record")
    aliases = record.get("aliases") if isinstance(record, dict) else None
    if not isinstance(aliases, list) or not aliases or not isinstance(aliases[0], str):
        raise SourceError(f"the build record {record_id} has no alias to name the source by")
    return SourceBuild(
        dir=source_dir, name=aliases[0], record_id=record_id, chain_id=chain_id,
        layer1_path=paths["layer1_dump"], norms_path=paths["norms"], alignments_path=paths["alignments"],
        layer1_sha256=digests["layer1_dump"], norms_sha256=digests["norms"],
        alignments_sha256=digests["alignments"], record=record,
    )


def _name_stem(source_name: str, judge_model: str) -> str:
    return f"{_LEADING_DATE.sub('', source_name)}-{judge_model.removeprefix('claude-')}"


def expected_name(source_name: str, judge_model: str, day: date) -> str:
    """The new build's name on day (R11)."""
    return f"{day.isoformat()}-{_name_stem(source_name, judge_model)}"


def name_refusal(name: str, source_name: str, judge_model: str) -> str | None:
    """Why name breaks the rule (R11), or None: any valid date, then the
    source name without its date, then the judge model without "claude-",
    then an optional -N."""
    pattern = re.compile(r"(\d{4}-\d{2}-\d{2})-" + re.escape(_name_stem(source_name, judge_model)) + r"(-\d+)?")
    match = pattern.fullmatch(name)
    valid_day = False
    if match:
        try:
            date.fromisoformat(match.group(1))
            valid_day = True
        except ValueError:
            valid_day = False
    if valid_day:
        return None
    return (f"the name {name!r} does not follow the rule <date>-<source name without its date>-<judge model "
            f"without 'claude-'>[-N]; for {source_name} judged by {judge_model} it reads "
            f"{expected_name(source_name, judge_model, date.today())}")

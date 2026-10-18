"""Which build tere4ai2 serves: the one resolver the facade and the MCP server call.

@implements: DEC-29
@grounded_by: REF-27, ADD-20

The served directory is chosen in this order: the explicit directory a
caller passes (the facade's create_app argument, the tests); else
TERE4AI_DUMP_DIR, a pinned directory; else TERE4AI_BUILDS_DIR, the newest
published build in that builds directory; else data/graph_dumps. Both
variables are read after load_dotenv_once, so the repository's .env may set
them and an exported value wins. The builds directory is a setting only:
no path to it is written in this repository.

A published build is an immediate subfolder of the builds directory whose
ACTIVE_MANIFEST.json names a chain with a readable publications/<chain>.json;
the newest is the one whose published_at is latest, ties going to the
greater folder name. A build whose norms or alignments file records a
judge that fails DEC-07 (an OpenAI-family judge, or the generator judging
its own output; judge/config.py assert_independent_judge) is a comparison
build and never a candidate (Jose, 2026-10-18: "THE LATEST BUILD IS THE
GPT 6 ASTRA WITH THE OPUS 5-5 AS A JUDGE"); a build that records no judge
stays a candidate. A subfolder that cannot be read is not a candidate;
a builds directory that cannot be read is an error naming its folder, as
one with no published build is. Nothing is cached: every call reads the
folders afresh, so the next call after a newer build is published serves
it. Choosing a build does not verify it; load_active does, and a drifted
newest build is refused, never replaced by an older one (architecture.md
Section 13).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from tere4ai.graph_store.present import exception_reason
from tere4ai.graph_store.publication import active_manifest
from tere4ai.judge.config import ModelConfigError, assert_independent_judge, load_dotenv_once

DUMP_DIR_ENV = "TERE4AI_DUMP_DIR"
BUILDS_DIR_ENV = "TERE4AI_BUILDS_DIR"
DEFAULT_DUMP_DIR = Path(__file__).resolve().parents[3] / "data" / "graph_dumps"

Source = Literal["explicit", "pinned", "newest", "default"]


@dataclass(frozen=True)
class PublishedBuild:
    """One published build of a builds directory; folder is the folder's
    name, published_at the string as its publication manifest records it."""

    folder: str
    dump_dir: Path
    chain_id: str
    build_id: str
    published_at: str


@dataclass(frozen=True)
class Resolution:
    """The directory to serve and why. newest is the newest published build
    of TERE4AI_BUILDS_DIR whenever that variable is set, whatever the source,
    so a pinned directory can be compared with it (None when that builds
    directory cannot be read); error is set when the builds directory, as
    the source, holds no published build or cannot be read, and unreadable
    tells the second from the first (the facade's recheck keeps the build
    it serves when the builds directory cannot be read, and logs why)."""

    dump_dir: Path
    source: Source
    newest: PublishedBuild | None
    error: str | None
    unreadable: bool = False


def _published_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A time without an offset is read as UTC, so it compares with the rest.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


_BUILD_BLOCKS: dict[tuple[str, int, int], dict] = {}


def _build_block(path: Path) -> dict:
    """The build block of a dump file, kept per path, size and modification
    time so a recheck does not parse the same large file again."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _BUILD_BLOCKS:
        try:
            block = json.loads(path.read_text(encoding="utf-8")).get("build")
        except (ValueError, AttributeError):
            block = None
        _BUILD_BLOCKS[key] = block if isinstance(block, dict) else {}
    return _BUILD_BLOCKS[key]


def _judged_independently(folder: Path, manifest: dict) -> bool:
    """False when the build's norms or alignments file records a judge that
    fails DEC-07; True otherwise, a build recording no judge included."""
    files = manifest.get("files")
    if not isinstance(files, dict):
        return True
    for name in ("norms", "alignments"):
        relative = files.get(name)
        if not isinstance(relative, str) or not (folder / relative).is_file():
            continue
        block = _build_block(folder / relative)
        for key in ("extraction_models", "alignment_models"):
            models = block.get(key)
            if not isinstance(models, dict) or not isinstance(models.get("judge_model"), str):
                continue
            try:
                assert_independent_judge(str(models.get("generator_model") or ""), models["judge_model"])
            except ModelConfigError:
                return False
    return True


def _candidate(folder: Path) -> tuple[datetime, PublishedBuild] | None:
    # active_manifest reads the pointer and publications/<chain>.json, and
    # answers None for a missing or unreadable one of either.
    manifest = active_manifest(folder)
    if manifest is None:
        return None
    moment = _published_time(manifest.get("published_at"))
    chain_id, build_id = manifest.get("chain_id"), manifest.get("build_id")
    if moment is None or not isinstance(chain_id, str) or not isinstance(build_id, str):
        return None
    if not _judged_independently(folder, manifest):
        return None
    return moment, PublishedBuild(folder=folder.name, dump_dir=folder, chain_id=chain_id, build_id=build_id,
                                  published_at=str(manifest["published_at"]))


def _readable_candidate(entry: Path) -> tuple[datetime, PublishedBuild] | None:
    # A subfolder that cannot be read is not a candidate; it never stops the
    # scan of the others.
    try:
        return _candidate(entry) if entry.is_dir() else None
    except OSError:
        return None


def scan_builds(builds_dir: Path | str) -> tuple[PublishedBuild | None, str | None]:
    """The newest published build among the immediate subfolders of
    builds_dir, with the reason the builds directory itself cannot be read
    (None when it can). A builds_dir that is no directory holds no build. A
    subfolder without a pointer, or whose pointer or manifest is unreadable,
    whose chain_id or build_id is no string, or whose published_at is no ISO
    8601 time, is not a candidate. The reason names the folder by its name
    only (audit W4)."""
    builds_dir = Path(builds_dir)
    try:
        entries = list(builds_dir.iterdir()) if builds_dir.is_dir() else []
    except OSError as exc:
        return None, f"the builds directory {builds_dir.name} cannot be read: {exception_reason(exc)}"
    candidates = [c for c in map(_readable_candidate, entries) if c is not None]
    if not candidates:
        return None, None
    return max(candidates, key=lambda c: (c[0], c[1].folder))[1], None


def newest_published(builds_dir: Path | str) -> PublishedBuild | None:
    """The newest published build of builds_dir (see scan_builds), or None
    when there is none or the builds directory cannot be read."""
    return scan_builds(builds_dir)[0]


def resolve_served(explicit: Path | str | None = None) -> Resolution:
    """The directory to serve on this call (see the module docstring)."""
    load_dotenv_once()
    builds_value = os.environ.get(BUILDS_DIR_ENV, "")
    builds_dir = Path(builds_value) if builds_value else None
    newest, unreadable = scan_builds(builds_dir) if builds_dir is not None else (None, None)
    if explicit is not None:
        return Resolution(Path(explicit), "explicit", newest, None)
    pinned = os.environ.get(DUMP_DIR_ENV, "")
    if pinned:
        return Resolution(Path(pinned), "pinned", newest, None)
    if builds_dir is not None:
        if unreadable is not None:
            return Resolution(builds_dir, "newest", None, unreadable, unreadable=True)
        if newest is None:
            return Resolution(builds_dir, "newest", None,
                              f"no published build in the builds directory {builds_dir.name}")
        return Resolution(newest.dump_dir, "newest", newest, None)
    return Resolution(DEFAULT_DUMP_DIR, "default", None, None)

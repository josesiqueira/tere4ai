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
greater folder name. Nothing is cached: every call reads the folders afresh,
so the next call after a newer build is published serves it. Choosing a
build does not verify it; load_active does, and a drifted newest build is
refused, never replaced by an older one (architecture.md Section 13).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from tere4ai.graph_store.publication import active_manifest
from tere4ai.judge.config import load_dotenv_once

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
    so a pinned directory can be compared with it; error is set when the
    builds directory holds no published build."""

    dump_dir: Path
    source: Source
    newest: PublishedBuild | None
    error: str | None


def _published_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    # A time without an offset is read as UTC, so it compares with the rest.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _candidate(folder: Path) -> tuple[datetime, PublishedBuild] | None:
    # active_manifest reads the pointer and publications/<chain>.json, and
    # answers None for a missing or unreadable one of either.
    manifest = active_manifest(folder)
    if manifest is None:
        return None
    moment = _published_time(manifest.get("published_at"))
    if moment is None:
        return None
    return moment, PublishedBuild(folder=folder.name, dump_dir=folder, chain_id=str(manifest.get("chain_id")),
                                  build_id=str(manifest.get("build_id")),
                                  published_at=str(manifest["published_at"]))


def newest_published(builds_dir: Path | str) -> PublishedBuild | None:
    """The newest published build among the immediate subfolders of
    builds_dir, or None when there is none (or builds_dir is no directory).
    A subfolder without a pointer, or whose pointer or manifest is
    unreadable, or whose published_at is no ISO 8601 time, is not a
    candidate."""
    builds_dir = Path(builds_dir)
    if not builds_dir.is_dir():
        return None
    candidates = [c for c in (_candidate(f) for f in builds_dir.iterdir() if f.is_dir()) if c is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1].folder))[1]


def resolve_served(explicit: Path | str | None = None) -> Resolution:
    """The directory to serve on this call (see the module docstring)."""
    load_dotenv_once()
    builds_value = os.environ.get(BUILDS_DIR_ENV, "")
    builds_dir = Path(builds_value) if builds_value else None
    newest = newest_published(builds_dir) if builds_dir is not None else None
    if explicit is not None:
        return Resolution(Path(explicit), "explicit", newest, None)
    pinned = os.environ.get(DUMP_DIR_ENV, "")
    if pinned:
        return Resolution(Path(pinned), "pinned", newest, None)
    if builds_dir is not None:
        if newest is None:
            return Resolution(builds_dir, "newest", None,
                              f"no published build in the builds directory {builds_dir.name}")
        return Resolution(newest.dump_dir, "newest", newest, None)
    return Resolution(DEFAULT_DUMP_DIR, "default", None, None)

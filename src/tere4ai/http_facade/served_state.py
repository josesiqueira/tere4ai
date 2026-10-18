"""The build the HTTP facade serves: one frozen state per request, replaced
in one assignment when a newer build is published.

@implements: DEC-29
@grounded_by: REF-27, ADD-20

ServedState holds what the facade's start-up loaded (the three payloads,
the core node list, the served HLEG spans, the load error) with the
resolution that chose the directory and the publication that directory
serves. app.state.served holds one; a middleware copies the reference into
request.state.served before the handler runs, and every handler reads the
build from there, so a request sees one build from start to end.

When the resolution's source is "newest", BuildFollower rechecks the builds
directory at most every TERE4AI_BUILD_RECHECK_SECONDS (default 30; 0
rechecks on every request). When the newest published chain differs from
the served one, or the served state has an error, it loads the newest build
in a worker thread and replaces app.state.served in one assignment (for the
same chain only when the result differs). A lock taken without waiting keeps a
second request from starting a second load: that request, and every other
one until the load is done, is served by the state that is ready. A newer
build that fails verification becomes the served state with its error, as
the start-up load would make it: the facade never falls back to an older
build (architecture.md Section 13). A pinned, explicit or default
directory is never rechecked.
"""

from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tere4ai.align_hleg.hleg_source import ServedHleg, served_hleg
from tere4ai.graph_store.present import exception_reason
from tere4ai.graph_store.publication import active_manifest, load_active
from tere4ai.graph_store.served_build import (
    BUILDS_DIR_ENV,
    PublishedBuild,
    Resolution,
    newest_published,
    resolve_served,
)

RECHECK_ENV = "TERE4AI_BUILD_RECHECK_SECONDS"
DEFAULT_RECHECK_SECONDS = 30.0


@dataclass(frozen=True)
class ServedState:
    """What one request is served from. published describes the
    publication the served directory's activation pointer names (None for
    the legacy files, or when the resolution found no build); it is read
    when the state is built, beside the payloads it describes."""

    dump: dict[str, Any] | None
    norms: dict[str, Any] | None
    alignments: dict[str, Any] | None
    served_source: str
    dump_dir: Path
    core_nodes: list[str] | None
    served_hleg: ServedHleg
    load_error: str | None
    resolution: Resolution
    published: PublishedBuild | None


def _published(dump_dir: Path) -> PublishedBuild | None:
    manifest = active_manifest(dump_dir)
    if manifest is None:
        return None
    return PublishedBuild(folder=dump_dir.name, dump_dir=dump_dir, chain_id=str(manifest.get("chain_id", "")),
                          build_id=str(manifest.get("build_id", "")),
                          published_at=str(manifest.get("published_at", "")))


def _error_state(resolution: Resolution, error: str, published: PublishedBuild | None) -> ServedState:
    """A state that serves nothing but its error, every endpoint answering
    503 with it (no silent degradation, Section 13)."""
    return ServedState(dump=None, norms=None, alignments=None, served_source="manifest",
                       dump_dir=resolution.dump_dir, core_nodes=None, served_hleg=served_hleg(None),
                       load_error=error, resolution=resolution, published=published)


def load_served_state(resolution: Resolution) -> ServedState:
    """Load the directory the resolution names through the one loader
    (load_active, D-G21): the activated publication when ACTIVE_MANIFEST.json
    exists (verified, a drifted file refusing service), else the legacy
    files. A resolution error (a builds directory with no published build)
    is served as a missing build naming that reason, as the MCP server
    answers it; the builds directory itself is not loaded."""
    if resolution.error is not None:
        # served_source "manifest": a builds directory serves published
        # builds only, never legacy files.
        return _error_state(resolution, resolution.error, None)
    base = resolution.dump_dir
    loaded = load_active(base)
    core_path = base / "core_nodes.txt"
    core_nodes = (
        [n.strip() for n in core_path.read_text(encoding="utf-8").split(",") if n.strip()]
        if core_path.is_file()
        else None
    )
    missing = [name for name, payload in (("layer1.json", loaded.dump), ("norms_core.json", loaded.norms))
               if payload is None]
    # Name the files, not the absolute server directory (audit W4).
    load_error = loaded.error or (
        f"graph dumps unavailable: missing or unreadable {', '.join(missing)}; "
        "build them with python -m tere4ai.parse_legal_structure "
        "and python -m tere4ai.extract_norms"
        if missing
        else None
    )
    return ServedState(dump=loaded.dump, norms=loaded.norms, alignments=loaded.alignments,
                       served_source=loaded.source, dump_dir=base, core_nodes=core_nodes,
                       served_hleg=served_hleg(loaded.dump), load_error=load_error, resolution=resolution,
                       published=_published(base))


def build_recheck_seconds() -> float:
    """TERE4AI_BUILD_RECHECK_SECONDS: unset or empty is 30; any other value
    must be a finite number of seconds, 0 or more, or the facade does not
    start (a setting it cannot read is never replaced by a default)."""
    value = os.environ.get(RECHECK_ENV, "").strip()
    if not value:
        return DEFAULT_RECHECK_SECONDS
    try:
        seconds = float(value)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{RECHECK_ENV} must be a number of seconds, 0 or more, not {value!r}")
    return seconds


def _chain(build: PublishedBuild | None) -> str | None:
    return build.chain_id if build is not None else None


def _load_newest(resolution: Resolution) -> ServedState:
    """load_served_state for a newest build found by a recheck; a load that
    raises (a manifest missing a key load_active reads, say) becomes the
    served error state, as a verification failure does, never a fall back
    to the build served before. Runs in a worker thread."""
    try:
        return load_served_state(resolution)
    except Exception as exc:  # noqa: BLE001 - served as the build's error, never a 500
        try:
            published = _published(resolution.dump_dir)
        except Exception:  # noqa: BLE001 - the error state names the folder through the resolution
            published = None
        folder = resolution.newest.folder if resolution.newest else resolution.dump_dir.name
        return _error_state(resolution, f"the newest build {folder} could not be loaded: {exception_reason(exc)}",
                            published)


class BuildFollower:
    """The recheck of the builds directory for one facade app."""

    def __init__(self, recheck_seconds: float) -> None:
        self.recheck_seconds = recheck_seconds
        self._last_check = time.monotonic()
        self._lock = threading.Lock()

    async def follow(self, app: Any, log: Callable[[dict[str, Any]], None]) -> None:
        """Replace app.state.served with the newest published build when it
        is due and differs; never waits for a load another request runs.

        A newest chain other than the served one is loaded and served. The
        same chain is loaded again only while the served state has an error
        (a build copied into the builds folder by hand can be read before
        its files are complete), and replaces it only when the result
        differs, the error gone or changed, so the log does not repeat."""
        current: ServedState = app.state.served
        if current.resolution.source != "newest":
            return
        if time.monotonic() - self._last_check < self.recheck_seconds:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._last_check = time.monotonic()
            current = app.state.served
            try:
                resolution = await asyncio.to_thread(resolve_served)
            except Exception as exc:  # noqa: BLE001 - the served build stays; the reason is logged
                log({"event": "served_build_recheck_failed", "reason": exception_reason(exc)})
                return
            if resolution.source != "newest":
                return
            same_chain = _chain(resolution.newest) == _chain(current.resolution.newest)
            if same_chain and current.load_error is None:
                return
            newer = await asyncio.to_thread(_load_newest, resolution)
            if same_chain and newer.load_error == current.load_error:
                return
            app.state.served = newer
            old, new = current.resolution.newest, newer.resolution.newest
            log({"event": "served_build_switch",
                 "old_chain_id": _chain(old), "old_published_at": old.published_at if old else None,
                 "new_chain_id": _chain(new), "new_published_at": new.published_at if new else None})
        finally:
            self._lock.release()


def _described(build: PublishedBuild | None) -> dict[str, Any] | None:
    if build is None:
        return None
    return {"folder": build.folder, "chain_id": build.chain_id, "build_id": build.build_id,
            "published_at": build.published_at}


def health_fields(state: ServedState) -> dict[str, Any]:
    """The health answer's served, newest_published and served_is_newest.
    The newest published build is read on every call from
    TERE4AI_BUILDS_DIR (null when it is not set or holds no published
    build), so a pinned directory is compared with what is published now;
    served_is_newest is null when there is no newest build to compare
    with. Folders are named by their name only (audit W4)."""
    published = state.published
    served = {"source": state.resolution.source, "folder": state.dump_dir.name,
              "chain_id": published.chain_id if published else None,
              "build_id": published.build_id if published else None,
              "published_at": published.published_at if published else None}
    builds_value = os.environ.get(BUILDS_DIR_ENV, "")
    newest = newest_published(Path(builds_value)) if builds_value else None
    served_is_newest = None if newest is None else (published is not None and published.chain_id == newest.chain_id)
    return {"served": served, "newest_published": _described(newest), "served_is_newest": served_is_newest}

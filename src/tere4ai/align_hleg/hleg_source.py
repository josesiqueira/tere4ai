"""The HLEG text Layer 3 reads and its derivation record, read through their checksums.

@implements: DEC-25 (partial: the pair the alignment, publication and serving use)
@grounded_by: ADD-01

The derived text and the record (tere4ai.ingest.hleg_text) are a pair: the
requirement descriptions and spans are slices of the text at the record's
ranges, so a run, a publication or a served build is bound to both sha256
(spec G D-G75 (7) and (8)). load_pair reads them through the current
manifest; listed_pair reads which pair a Layer 0+1 dump lists among its
SourceFile nodes. Deterministic, no model; imports no PDF library.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tere4ai.ingest.hleg_text import DEFAULT_MANIFEST, RECORD_FILE, SNAPSHOTS_DIR, TEXT_FILE

HLEG_SPAN_PREFIX = "span:hleg:"


class HlegSourceError(ValueError):
    """A file of the pair is missing, unlisted or differs from its recorded sha256."""


@dataclass(frozen=True)
class HlegPair:
    text: str
    record: dict[str, Any]
    text_sha256: str
    record_sha256: str


def read_pair(snapshots_dir: Path | str, expected: dict[str, str]) -> HlegPair:
    """Both files from snapshots_dir, each checked against expected[file]."""
    folder = Path(snapshots_dir)
    raw: dict[str, tuple[bytes, str]] = {}
    for name in (TEXT_FILE, RECORD_FILE):
        if name not in expected:
            raise HlegSourceError(f"{name} has no recorded sha256")
        path = folder / name
        if not path.is_file():
            raise HlegSourceError(f"{name} is not present under {folder}")
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected[name]:
            raise HlegSourceError(f"checksum mismatch for {name}: recorded {expected[name]}, file {actual}")
        raw[name] = (data, actual)
    try:
        record = json.loads(raw[RECORD_FILE][0].decode("utf-8"))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError (final review F2, M1)
        raise HlegSourceError(f"{RECORD_FILE} is not a JSON object: {type(exc).__name__}: {exc}") from exc
    if not isinstance(record, dict):
        raise HlegSourceError(f"{RECORD_FILE} is not a JSON object: it holds a JSON {type(record).__name__}")
    if record.get("derived_file") != TEXT_FILE:
        raise HlegSourceError(f"{RECORD_FILE} is the record of {record.get('derived_file')!r}, not of {TEXT_FILE}")
    return HlegPair(raw[TEXT_FILE][0].decode("utf-8"), record, raw[TEXT_FILE][1], raw[RECORD_FILE][1])


def load_pair(manifest_path: Path | str = DEFAULT_MANIFEST) -> HlegPair:
    manifest_path = Path(manifest_path)
    entries = {e["file"]: e["sha256"] for e in json.loads(manifest_path.read_text(encoding="utf-8"))["snapshots"]}
    missing = [name for name in (TEXT_FILE, RECORD_FILE) if name not in entries]
    if missing:
        raise HlegSourceError(f"{' and '.join(missing)} not in {manifest_path.name}")
    return read_pair(manifest_path.parent, entries)


def listed_pair(layer1: dict[str, Any] | None) -> dict[str, str]:
    """{file: sha256} of the derived text and the record among the dump's SourceFile nodes.

    Raises HlegSourceError when a node of the dump is not a JSON object (final review F2, M1).
    """
    listed: dict[str, str] = {}
    for n in (layer1 or {}).get("nodes", []):
        if not isinstance(n, dict):
            raise HlegSourceError(f"a node of the Layer 1 dump is not a JSON object: {type(n).__name__}")
        if n.get("type") == "SourceFile" and n.get("file") in (TEXT_FILE, RECORD_FILE):
            listed[n["file"]] = n["sha256"]
    return listed


def pair_refusal(layer1: dict[str, Any] | None, pair: HlegPair) -> str | None:
    """None when the dump lists both files with the pair's sha256, else why not."""
    listed = listed_pair(layer1)
    if listed.get(TEXT_FILE) == pair.text_sha256 and listed.get(RECORD_FILE) == pair.record_sha256:
        return None
    return (f"the Layer 1 dump lists {TEXT_FILE} {listed.get(TEXT_FILE, 'not at all')} and {RECORD_FILE} "
            f"{listed.get(RECORD_FILE, 'not at all')}; the HLEG text read is {pair.text_sha256} and its record "
            f"{pair.record_sha256}")


REFUSAL_PREFIX = "HLEG span resolution refused (D-G75 (8)):"


@dataclass(frozen=True)
class ServedHleg:
    """The HLEG requirement nodes a served build resolves spans into, or why none."""

    nodes: list[dict[str, Any]]
    refusal: str | None


def served_hleg(dump: dict[str, Any] | None, snapshots_dir: Path | str | None = None) -> ServedHleg:
    """The one loader of HLEG spans for a served build (the facade, the MCP server,
    explain): the nodes are built from the files on disk only when the served
    layer1.json lists the derived text and its record with exactly their sha256;
    otherwise the refusal names both files. Never raises."""
    from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes

    listed: dict[str, str] = {}
    disk: dict[str, str] = {}
    try:
        folder = Path(snapshots_dir) if snapshots_dir is not None else SNAPSHOTS_DIR
        listed = listed_pair(dump)
        disk = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() if (folder / name).is_file()
                else "missing" for name in (TEXT_FILE, RECORD_FILE)}
        if all(listed.get(name) == disk[name] for name in (TEXT_FILE, RECORD_FILE)):
            return ServedHleg(build_hleg_nodes(read_pair(folder, listed)), None)
    except (OSError, HlegSourceError, ValueError, KeyError, TypeError) as exc:  # review M3: never raises
        return ServedHleg([], f"{REFUSAL_PREFIX} {TEXT_FILE} and {RECORD_FILE} cannot be used: "
                              f"{type(exc).__name__}: {exc}")
    return ServedHleg([], (
        f"{REFUSAL_PREFIX} the served build's layer1.json lists {TEXT_FILE} as {listed.get(TEXT_FILE, 'not listed')} "
        f"and {RECORD_FILE} as {listed.get(RECORD_FILE, 'not listed')}; the files on disk are {disk[TEXT_FILE]} and "
        f"{disk[RECORD_FILE]}. A span of this build resolves only into the text it was made on."))

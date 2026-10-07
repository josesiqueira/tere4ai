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

from tere4ai.ingest.hleg_text import DEFAULT_MANIFEST, RECORD_FILE, TEXT_FILE

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
    record = json.loads(raw[RECORD_FILE][0].decode("utf-8"))
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
    """{file: sha256} of the derived text and the record among the dump's SourceFile nodes."""
    return {n["file"]: n["sha256"] for n in (layer1 or {}).get("nodes", [])
            if n.get("type") == "SourceFile" and n.get("file") in (TEXT_FILE, RECORD_FILE)}


def pair_refusal(layer1: dict[str, Any] | None, pair: HlegPair) -> str | None:
    """None when the dump lists both files with the pair's sha256, else why not."""
    listed = listed_pair(layer1)
    if listed.get(TEXT_FILE) == pair.text_sha256 and listed.get(RECORD_FILE) == pair.record_sha256:
        return None
    return (f"the Layer 1 dump lists {TEXT_FILE} {listed.get(TEXT_FILE, 'not at all')} and {RECORD_FILE} "
            f"{listed.get(RECORD_FILE, 'not at all')}; the HLEG text read is {pair.text_sha256} and its record "
            f"{pair.record_sha256}")

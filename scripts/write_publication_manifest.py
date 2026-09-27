"""Write the missing publication manifest, and the pointer when asked, of a published chain.

@implements: DEC-16 (partial: repair of a publication whose manifest or pointer write failed after the record was frozen)
@grounded_by: REF-27, ADD-20

Usage: .venv/bin/python scripts/write_publication_manifest.py <chain_id> [--dump-dir data/graph_dumps] [--pointer]

publish_layer23 freezes the build record with its build number before it
writes publications/<chain>.json and BUILD_CHAIN_CURRENT.txt; when one of
those writes fails, this command writes them from what is already recorded
(spec G D-G50, B94a final review B-P2-2): the publication block of the frozen
record that published the chain, and the inputs of build_chain_<chain>.json.
It refuses when no frozen record published the chain, when the chain record
is missing or names another record or another number, and when a present
manifest disagrees with them. It never assigns or changes a build number,
never rewrites a chain record, a record or a present manifest, and never
touches Neo4j. --pointer also writes BUILD_CHAIN_CURRENT.txt, which records
the latest publication: refused when a later build number is published.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.graph_store.build_record import BuildRecordStore, numbered_files  # noqa: E402
from tere4ai.graph_store.publication import (  # noqa: E402
    CURRENT_POINTER_FILENAME,
    PUBLICATIONS_DIRNAME,
    PublicationError,
    manifest_path,
    write_current_pointer,
    write_publication_manifest,
)

CHAIN_ID = re.compile(r"^[0-9a-f]{12}$")
FILE_ROLES = ("layer1_dump", "norms", "alignments")


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _files_by_role(inputs: list) -> dict[str, str | None] | None:
    """The manifest's files block from the chain record's inputs, as publish
    builds it; None when the layer1 dump or the norms file is not named once."""
    named = {role: [i.get("file") for i in inputs if isinstance(i, dict) and i.get("role") == role]
             for role in FILE_ROLES}
    if len(named["layer1_dump"]) != 1 or len(named["norms"]) != 1 or len(named["alignments"]) > 1:
        return None
    return {"layer1_dump": named["layer1_dump"][0], "norms": named["norms"][0],
            "alignments": named["alignments"][0] if named["alignments"] else None}


def _highest_number(store: BuildRecordStore, dump_dir: Path) -> int:
    numbers, _ = numbered_files(dump_dir)
    held = list(numbers.values())
    held += [n for r in store.list_records() if not r.get("unreadable")
             and isinstance(n := (r.get("publication") or {}).get("build_number"), int)]
    return max(held, default=0)


def _refuse(message: str) -> int:
    print(f"not written: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("chain_id")
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    parser.add_argument("--pointer", action="store_true", help=f"also write {CURRENT_POINTER_FILENAME}")
    args = parser.parse_args(argv)
    chain_id, dump_dir = args.chain_id, args.dump_dir
    if not CHAIN_ID.match(chain_id):
        return _refuse(f"{chain_id!r} is not a chain id (twelve hexadecimal characters)")
    store = BuildRecordStore(dump_dir)
    # Every writer of a chain record, a manifest or a number holds the
    # numbering lock (spec G D-G50), so nothing changes under these checks.
    with store.numbering_lock():
        record = store.publisher_of(chain_id)
        if record is None:
            return _refuse(f"no build record published chain {chain_id}; a manifest is written only for a "
                           "chain a frozen record published")
        publication = record["publication"]
        number = publication.get("build_number")
        chain_name = f"build_chain_{chain_id}.json"
        chain = _read(dump_dir / chain_name)
        if chain is None:
            return _refuse(f"{chain_name} is missing or unreadable; the manifest takes its inputs from it")
        if chain.get("record_id") != record["record_id"] or chain.get("build_number") != number:
            return _refuse(f"{chain_name} names record {chain.get('record_id')} and carries Build "
                           f"{chain.get('build_number')}, the frozen record {record['record_id']} carries Build "
                           f"{number}; a number is never changed, so compare the two by hand")
        files = _files_by_role(chain.get("inputs") or [])
        if files is None:
            return _refuse(f"{chain_name} does not name exactly one layer1 dump and one norms file")
        named = f"Build {number}" if number is not None else "a build published before build numbers"
        mpath = manifest_path(dump_dir, chain_id)
        rel = f"{PUBLICATIONS_DIRNAME}/{mpath.name}"
        if mpath.exists():
            present = _read(mpath)
            if (present is None or present.get("record_id") != record["record_id"]
                    or present.get("build_number") != number):
                return _refuse(f"{rel} is present and does not match record {record['record_id']} and {named}; "
                               "a present manifest is never rewritten")
            print(f"{rel} is present, left as it is")
        else:
            try:
                write_publication_manifest(dump_dir, publication, record_id=record["record_id"],
                                           inputs=chain["inputs"], files=files)
            except PublicationError as exc:
                return _refuse(f"the manifest does not validate: {exc}")
            print(f"wrote {rel} for {named} ({publication['build_id']}), record {record['record_id']}")
        if args.pointer:
            highest = _highest_number(store, dump_dir)
            if highest > (number or 0):
                return _refuse(f"{CURRENT_POINTER_FILENAME} records the latest publication and Build {highest} "
                               f"is published after it; the pointer is left as it is")
            write_current_pointer(dump_dir, chain_id)
            print(f"wrote {CURRENT_POINTER_FILENAME}: {chain_id}")
    print(f"activate with: scripts/activate_build.py {chain_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

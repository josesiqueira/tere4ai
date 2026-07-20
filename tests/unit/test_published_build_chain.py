"""The published dumps must match exactly one recorded build chain.

Section 13 makes reproducibility a MUST and task 48 built the chain:
every publication writes a build_chain_<id>.json recording the sha256 of
each input dump. Until now nothing verified the dumps ON DISK against
those records (the 2026-07-17 audit did it by hand), so a hand-edited or
half-updated dump directory would keep serving under a stale identity.

This file makes the manual check a standing gate: recompute the sha256 of
every published dump with the production hashing code and assert that
exactly one chain record matches, that its chain id recomputes from the
role map, and that its chained build id derives from the layer1 dump's own
build id. Stale chain records beside the current one are expected history
and must NOT match the current bytes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tere4ai.graph_store.build_chain import (
    chained_build_id,
    compose_chain_id,
    sha256_of_file,
)

ROOT = Path(__file__).resolve().parents[2]
_DUMP_DIR = Path(os.environ.get("TERE4AI_DUMP_DIR") or ROOT / "data" / "graph_dumps")
_DUMP_FILES = ("layer1.json", "norms_core.json", "alignments_core.json")

pytestmark = pytest.mark.skipif(
    not (
        all((_DUMP_DIR / name).is_file() for name in _DUMP_FILES)
        and list(_DUMP_DIR.glob("build_chain_*.json"))
    ),
    reason="published dumps or build_chain records not present (see README quick start)",
)


def _recomputed_checksums() -> dict[str, str]:
    return {name: sha256_of_file(_DUMP_DIR / name) for name in _DUMP_FILES}


def _matching_records() -> list[dict]:
    """Chain records whose every recorded input matches the bytes on disk."""
    on_disk = _recomputed_checksums()
    matches = []
    for path in sorted(_DUMP_DIR.glob("build_chain_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        recorded = {i["file"]: i["sha256"] for i in record["inputs"]}
        if all(on_disk.get(f) == sha for f, sha in recorded.items()):
            matches.append(record)
    return matches


def test_exactly_one_chain_record_matches_the_dumps_on_disk():
    matches = _matching_records()
    assert len(matches) == 1, (
        f"expected exactly one build_chain record matching the dump bytes on "
        f"disk, found {len(matches)}: either a dump was modified after "
        f"publication (0 matches) or duplicate records exist (>1)"
    )


def test_matching_chain_id_recomputes_from_the_role_map():
    (record,) = _matching_records()
    role_map = {i["role"]: i["sha256"] for i in record["inputs"]}
    assert record["chain_id"] == compose_chain_id(role_map)


def test_matching_build_id_derives_from_the_layer1_build():
    (record,) = _matching_records()
    layer1 = json.loads((_DUMP_DIR / "layer1.json").read_text(encoding="utf-8"))
    base_build_id = layer1["build"]["build_id"]
    assert record["build_id"] == chained_build_id(base_build_id, record)


def test_runtime_verify_accepts_the_real_dumps():
    """The runtime D3 gate (verify_dumps_against_chain) accepts the published
    dumps and reports the current chain id."""
    from tere4ai.graph_store.build_chain import verify_dumps_against_chain

    dump_dir = ROOT / "data" / "graph_dumps"
    if not (dump_dir / "layer1.json").is_file():
        import pytest

        pytest.skip("dumps not built")
    ok, detail = verify_dumps_against_chain(dump_dir)
    assert ok, detail
    assert "verified against build chain" in detail


def test_runtime_verify_rejects_a_tampered_dump(tmp_path):
    """A single tampered byte in a copied dump makes the runtime gate refuse:
    the recomputed chain matches no recorded record."""
    import json as _json
    import shutil

    from tere4ai.graph_store.build_chain import verify_dumps_against_chain

    dump_dir = ROOT / "data" / "graph_dumps"
    if not (dump_dir / "layer1.json").is_file():
        import pytest

        pytest.skip("dumps not built")
    for name in ("layer1.json", "norms_core.json", "alignments_core.json"):
        src = dump_dir / name
        if src.is_file():
            shutil.copy2(src, tmp_path / name)
    for rec in dump_dir.glob("build_chain_*.json"):
        shutil.copy2(rec, tmp_path / rec.name)
    # Tamper: flip one accepted norm's verdict on the copy.
    norms = _json.loads((tmp_path / "norms_core.json").read_text())
    norms["norms"][0]["judge_verdict"] = "accepted"
    norms["norms"][0]["review_status"] = "accepted"
    norms["norms"][0]["object"] = "INJECTED by a tamper test"
    (tmp_path / "norms_core.json").write_text(_json.dumps(norms))
    ok, detail = verify_dumps_against_chain(tmp_path)
    assert not ok
    assert "no recorded build chain" in detail

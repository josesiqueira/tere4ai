"""scripts/write_publication_manifest.py (spec G D-G50, B94a final review
B-P2-2 and A-M9): a missing publication manifest and pointer are written
from the chain record and the frozen record, never with a new number."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from tests.unit.test_publish_layer23 import _fakes, _files, _publish

from tere4ai.graph_store.build_record import BuildRecordStore

ROOT = Path(__file__).resolve().parents[2]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_b94a_fix", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _published_without_manifest(tmp_path, monkeypatch):
    """A publication whose manifest write failed after the record was frozen."""
    cli = _publish()
    layer1, norms, alignments, store, rid = _files(tmp_path)
    _fakes(monkeypatch, cli)
    real = cli.atomic_write_json

    def failing(path, payload):
        if Path(path).parent.name == "publications":
            raise OSError("disk full")
        real(path, payload)

    monkeypatch.setattr(cli, "atomic_write_json", failing)
    with pytest.raises(OSError):
        cli.main(["--dump", str(layer1), "--norms", str(norms), "--alignments", str(alignments),
                  "--dump-dir", str(tmp_path)])
    chain_id = json.loads(next(tmp_path.glob("build_chain_*.json")).read_text())["chain_id"]
    return store, rid, chain_id


def test_the_missing_manifest_and_pointer_are_written_from_the_chain_record(tmp_path, monkeypatch, capsys):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("build_chain_*.json")}
    record_before = (store.dir / f"{rid}.json").read_bytes()
    counter_before = (store.dir / "numbering.json").read_bytes()
    monkeypatch.setitem(sys.modules, "neo4j", None)  # never touches Neo4j: an import would fail
    capsys.readouterr()
    assert _script("write_publication_manifest").main([chain_id, "--dump-dir", str(tmp_path), "--pointer"]) == 0
    out = capsys.readouterr().out
    assert f"wrote publications/{chain_id}.json for Build 1" in out and "BUILD_CHAIN_CURRENT.txt" in out
    manifest = json.loads((tmp_path / "publications" / f"{chain_id}.json").read_text())
    chain = json.loads((tmp_path / f"build_chain_{chain_id}.json").read_text())
    publication = store.read(rid)["publication"]
    assert manifest["build_number"] == chain["build_number"] == publication["build_number"] == 1
    assert manifest["record_id"] == rid and manifest["inputs"] == chain["inputs"]
    assert manifest["files"] == {"layer1_dump": "layer1.json", "norms": "norms_core.json",
                                 "alignments": "alignments_core.json"}
    assert {k: manifest[k] for k in publication} == publication
    assert (tmp_path / "BUILD_CHAIN_CURRENT.txt").read_text().strip() == chain_id
    # nothing else changed: no number assigned, no chain record or record rewritten
    assert {p.name: p.read_bytes() for p in tmp_path.glob("build_chain_*.json")} == before
    assert (store.dir / f"{rid}.json").read_bytes() == record_before
    assert (store.dir / "numbering.json").read_bytes() == counter_before
    # the operator's next line works
    monkeypatch.delitem(sys.modules, "neo4j")
    assert _script("activate_build").main([chain_id, "--dump-dir", str(tmp_path)]) == 0


def test_without_the_pointer_flag_only_the_manifest_is_written(tmp_path, monkeypatch):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    assert _script("write_publication_manifest").main([chain_id, "--dump-dir", str(tmp_path)]) == 0
    assert (tmp_path / "publications" / f"{chain_id}.json").is_file()
    assert not (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists()


def test_a_present_manifest_is_left_as_it_is_and_the_pointer_still_written(tmp_path, monkeypatch, capsys):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    script = _script("write_publication_manifest")
    assert script.main([chain_id, "--dump-dir", str(tmp_path)]) == 0
    manifest = tmp_path / "publications" / f"{chain_id}.json"
    written = manifest.read_bytes()
    capsys.readouterr()
    assert script.main([chain_id, "--dump-dir", str(tmp_path), "--pointer"]) == 0
    assert "is present, left as it is" in capsys.readouterr().out
    assert manifest.read_bytes() == written
    assert (tmp_path / "BUILD_CHAIN_CURRENT.txt").read_text().strip() == chain_id


def test_a_chain_no_frozen_record_published_is_refused(tmp_path, capsys):
    BuildRecordStore(tmp_path)
    (tmp_path / "build_chain_aaaaaaaaaaaa.json").write_text(json.dumps({"chain_id": "a" * 12, "inputs": []}))
    assert _script("write_publication_manifest").main(["a" * 12, "--dump-dir", str(tmp_path), "--pointer"]) == 1
    assert "no build record published chain aaaaaaaaaaaa" in capsys.readouterr().err
    assert not (tmp_path / "publications").exists() and not (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists()


def test_a_chain_record_whose_number_differs_from_the_record_is_refused(tmp_path, monkeypatch, capsys):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    path = tmp_path / f"build_chain_{chain_id}.json"
    chain = json.loads(path.read_text())
    path.write_text(json.dumps({**chain, "build_number": 2}))
    capsys.readouterr()
    assert _script("write_publication_manifest").main([chain_id, "--dump-dir", str(tmp_path)]) == 1
    assert "carries Build 2" in capsys.readouterr().err
    assert not list((tmp_path / "publications").glob("*.json"))


def test_a_missing_chain_record_is_refused(tmp_path, monkeypatch, capsys):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    (tmp_path / f"build_chain_{chain_id}.json").unlink()
    capsys.readouterr()
    assert _script("write_publication_manifest").main([chain_id, "--dump-dir", str(tmp_path)]) == 1
    assert f"build_chain_{chain_id}.json is missing or unreadable" in capsys.readouterr().err
    assert not list((tmp_path / "publications").glob("*.json"))


def test_the_pointer_is_refused_when_a_later_build_is_published(tmp_path, monkeypatch, capsys):
    store, rid, chain_id = _published_without_manifest(tmp_path, monkeypatch)
    (tmp_path / "build_chain_bbbbbbbbbbbb.json").write_text(json.dumps({"chain_id": "b" * 12, "build_number": 2}))
    capsys.readouterr()
    assert _script("write_publication_manifest").main([chain_id, "--dump-dir", str(tmp_path), "--pointer"]) == 1
    err = capsys.readouterr().err
    assert "Build 2 is published after it" in err
    assert (tmp_path / "publications" / f"{chain_id}.json").is_file(), "the manifest is still written"
    assert not (tmp_path / "BUILD_CHAIN_CURRENT.txt").exists()

"""The served build id carries the publication chain (B74, Section 13).

publish_layer23 stamps <base>+chain-<12hex> on every published node and
edge, where the chain digests the exact dump files. Until B74 the facade
and the MCP server reported only the base id (the legal snapshot hash),
which does not change when the norms are re-extracted with other models,
so a rebuild was indistinguishable from the build it replaced. Now every
dump read from a directory is served under that directory's chained id.
Offline: synthetic dumps in tmp_path, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade
import tere4ai.mcp_server.server as server
from tere4ai.graph_store.build_chain import (
    build_chain,
    chained_build_id,
    served_build_id,
    stamp_served_build,
)

BASE = "build-fixture"


def _dump(base: str = BASE) -> dict:
    return {"build": {"build_id": base, "built_at": "2026-07-08T00:00:00Z"}, "nodes": [], "edges": []}


def _write(directory: Path, name: str, payload: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _expected(directory: Path, base: str = BASE) -> str:
    alignments = directory / "alignments_core.json"
    chain = build_chain(
        directory / "layer1.json",
        directory / "norms_core.json",
        alignments if alignments.is_file() else None,
    )
    return chained_build_id(base, chain)


class TestServedBuildId:
    def test_is_the_chained_id_publish_would_stamp(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        _write(tmp_path, "alignments_core.json", {"build": {"build_id": BASE}, "assertions": []})
        assert served_build_id(tmp_path, BASE) == _expected(tmp_path)
        assert "+chain-" in served_build_id(tmp_path, BASE)

    def test_without_alignments_the_chain_names_only_what_exists(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        assert served_build_id(tmp_path, BASE) == _expected(tmp_path)

    def test_falls_back_to_the_base_id_when_no_norms_are_published(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        assert served_build_id(tmp_path, BASE) == BASE

    def test_changed_norms_change_the_served_id(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": ["a"]})
        first = served_build_id(tmp_path, BASE)
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": ["b"]})
        second = served_build_id(tmp_path, BASE)
        assert first != second
        assert first.split("+chain-")[0] == second.split("+chain-")[0] == BASE

    def test_never_stacks_a_chain_suffix(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        once = served_build_id(tmp_path, BASE)
        assert served_build_id(tmp_path, once) == once

    def test_stamp_rewrites_the_payload_build_id_in_place(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        payload = _dump()
        assert stamp_served_build(payload, tmp_path) is payload
        assert payload["build"]["build_id"] == _expected(tmp_path)

    def test_stamp_leaves_a_payload_without_a_build_record_alone(self, tmp_path):
        payload = {"nodes": []}
        assert stamp_served_build(payload, tmp_path) == {"nodes": []}


class TestMcpServerReadsStampedDumps:
    def test_read_json_serves_the_chained_id(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", _dump())
        norms = _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        assert server._read_json(layer1)["build"]["build_id"] == _expected(tmp_path)
        assert server._read_json(norms)["build"]["build_id"] == _expected(tmp_path)

    def test_read_json_keeps_the_base_id_for_an_unpublished_directory(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", _dump())
        assert server._read_json(layer1)["build"]["build_id"] == BASE


class TestFacadeHealthServesTheChainedId:
    def test_health_reports_one_chained_id_for_graph_and_norms(self, tmp_path):
        _write(tmp_path, "layer1.json", _dump())
        _write(tmp_path, "norms_core.json", {"build": {"build_id": BASE}, "norms": []})
        _write(tmp_path, "alignments_core.json", {"build": {"build_id": BASE}, "assertions": []})
        with TestClient(facade.create_app(dump_dir=tmp_path)) as client:
            body = client.get("/api/health").json()
        assert body["ok"] is True
        assert body["graph_version"] == _expected(tmp_path)
        assert body["norms_build"] == _expected(tmp_path)

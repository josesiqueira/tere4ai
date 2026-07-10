"""Build reproducibility chain tests (DEC-10 partial, Section 13).

The chain id must be a pure function of the input file bytes: identical
inputs give identical ids, any single-byte change gives a different id, and
the composed build_id never stacks chain suffixes on re-publication.
"""

from __future__ import annotations

import json

from tere4ai.graph_store.build_chain import (
    build_chain,
    chained_build_id,
    compose_chain_id,
    sha256_of_file,
)


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class TestChainDeterminism:
    def test_same_files_same_chain_id(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        a = build_chain(layer1, norms)
        b = build_chain(layer1, norms)
        assert a["chain_id"] == b["chain_id"]
        assert a["inputs"] == b["inputs"]

    def test_any_input_change_changes_chain_id(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        before = build_chain(layer1, norms)["chain_id"]
        norms.write_text(json.dumps({"norms": [2, 3]}), encoding="utf-8")
        after = build_chain(layer1, norms)["chain_id"]
        assert before != after

    def test_optional_inputs_enter_the_chain(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        alignments = _write(tmp_path, "alignments.json", {"assertions": []})
        without = build_chain(layer1, norms)
        with_al = build_chain(layer1, norms, alignments_path=alignments)
        assert without["chain_id"] != with_al["chain_id"]
        assert [i["role"] for i in with_al["inputs"]] == [
            "layer1_dump",
            "norms",
            "alignments",
        ]

    def test_missing_decisions_file_is_omitted_not_hashed(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        chain = build_chain(
            layer1, norms, decisions_path=tmp_path / "absent.json"
        )
        assert all(i["role"] != "decisions" for i in chain["inputs"])

    def test_compose_ignores_dict_order(self):
        cks = {"norms": "aa", "layer1_dump": "bb"}
        assert compose_chain_id(cks) == compose_chain_id(dict(reversed(cks.items())))

    def test_sha256_matches_file_bytes(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"tere4ai")
        import hashlib

        assert sha256_of_file(p) == hashlib.sha256(b"tere4ai").hexdigest()


class TestChainedBuildId:
    def test_appends_chain_suffix(self):
        chain = {"chain_id": "abc123def456"}
        assert chained_build_id("build-2026", chain) == "build-2026+chain-abc123def456"

    def test_republication_replaces_never_stacks(self):
        first = chained_build_id("build-2026", {"chain_id": "aaaaaaaaaaaa"})
        second = chained_build_id(first, {"chain_id": "bbbbbbbbbbbb"})
        assert second == "build-2026+chain-bbbbbbbbbbbb"
        assert second.count("+chain-") == 1

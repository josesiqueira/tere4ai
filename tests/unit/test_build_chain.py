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
    verify_dumps_against_chain,
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


class TestManifestsInTheChain:
    def test_each_manifest_changes_the_id_and_order_does_not(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        m1 = _write(tmp_path, "m1.json", {"freeze_id": "f1"})
        m2 = _write(tmp_path, "m2.json", {"freeze_id": "f2"})
        both = build_chain(layer1, norms, manifest_paths=[m1, m2])
        swapped = build_chain(layer1, norms, manifest_paths=[m2, m1])
        assert both["chain_id"] == swapped["chain_id"]
        assert [i["role"] for i in both["inputs"]] == ["layer1_dump", "norms", "freeze_manifest", "freeze_manifest"]
        m1.write_text(json.dumps({"freeze_id": "f1b"}), encoding="utf-8")
        assert build_chain(layer1, norms, manifest_paths=[m1, m2])["chain_id"] != both["chain_id"]
        m1.write_text(json.dumps({"freeze_id": "f1"}), encoding="utf-8")
        m2.write_text(json.dumps({"freeze_id": "f2b"}), encoding="utf-8")
        assert build_chain(layer1, norms, manifest_paths=[m1, m2])["chain_id"] != both["chain_id"]

    def test_without_manifests_the_legacy_id_is_unchanged(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms.json", {"norms": [2]})
        assert build_chain(layer1, norms)["chain_id"] == build_chain(layer1, norms, manifest_paths=None)["chain_id"]
        assert build_chain(layer1, norms, manifest_paths=[])["chain_id"] == build_chain(layer1, norms)["chain_id"]


class TestVerifyAgainstPublication:
    def _publication(self, tmp_path, manifests):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms_core.reference.json", {"norms": [2]})
        chain = build_chain(layer1, norms, manifest_paths=manifests)
        pub_dir = tmp_path / "publications"
        pub_dir.mkdir()
        (pub_dir / f"{chain['chain_id']}.json").write_text(json.dumps({
            "schema_version": "publication.v1", "chain_id": chain["chain_id"], "build_id": "b+chain-" + chain["chain_id"],
            "inputs": chain["inputs"], "files": {"layer1_dump": "layer1.json", "norms": "norms_core.reference.json", "alignments": None},
        }), encoding="utf-8")
        return chain["chain_id"]

    def test_verifies_named_files_and_manifests(self, tmp_path):
        m = _write(tmp_path, "freeze-f1.json", {"freeze_id": "f1"})
        chain_id = self._publication(tmp_path, [m])
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id=chain_id)
        assert ok, detail
        m.write_text(json.dumps({"freeze_id": "tampered"}), encoding="utf-8")
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id=chain_id)
        assert not ok and "freeze-f1.json" in detail
        m.unlink()
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id=chain_id)
        assert not ok and "missing" in detail

    def test_unknown_chain_id_is_refused(self, tmp_path):
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id="000000000000")
        assert not ok and "no publication manifest" in detail

    def test_malformed_publication_manifest_fails_closed(self, tmp_path):
        layer1 = _write(tmp_path, "layer1.json", {"nodes": [1]})
        norms = _write(tmp_path, "norms_core.reference.json", {"norms": [2]})
        chain = build_chain(layer1, norms)
        pub_dir = tmp_path / "publications"
        pub_dir.mkdir()

        missing_files_key = "aaaaaaaaaaaa"
        (pub_dir / f"{missing_files_key}.json").write_text(json.dumps({
            "schema_version": "publication.v1", "chain_id": missing_files_key,
            "inputs": chain["inputs"], "files": {"norms": "norms_core.reference.json"},
        }), encoding="utf-8")
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id=missing_files_key)
        assert not ok and "malformed" in detail

        missing_sha_key = "bbbbbbbbbbbb"
        bad_inputs = [dict(i) for i in chain["inputs"]]
        del bad_inputs[0]["sha256"]
        (pub_dir / f"{missing_sha_key}.json").write_text(json.dumps({
            "schema_version": "publication.v1", "chain_id": missing_sha_key,
            "inputs": bad_inputs,
            "files": {"layer1_dump": "layer1.json", "norms": "norms_core.reference.json"},
        }), encoding="utf-8")
        ok, detail = verify_dumps_against_chain(tmp_path, chain_id=missing_sha_key)
        assert not ok and "malformed" in detail

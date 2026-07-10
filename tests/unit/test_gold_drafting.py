"""Gold-set drafting CLI tests (#26): deterministic, verified, protocol-true."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "draft_gold_candidates", ROOT / "scripts" / "draft_gold_candidates.py"
)
draft_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_mod)

pytestmark = pytest.mark.skipif(
    not draft_mod.DUMP_PATH.is_file(), reason="layer1.json dump not built"
)


@pytest.fixture(scope="module")
def payload(tmp_path_factory):
    out = tmp_path_factory.mktemp("gold") / "draft_candidates.json"
    rc = draft_mod.main(["draft", "--out", str(out)])
    assert rc == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_target_size_and_kind_mix(payload):
    items = payload["items"]
    assert 60 <= len(items) <= 80
    kinds = {i["kind"] for i in items}
    assert kinds == {"classification", "retrieval", "qa"}


def test_every_citation_resolves_in_the_dump(payload):
    dump = json.loads(draft_mod.DUMP_PATH.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in dump["nodes"]}
    for item in payload["items"]:
        for cited in item["gold_citations"]:
            assert cited in node_ids, f"{item['id']} cites unknown {cited}"


def test_drafts_are_marked_and_pass_harness_validation(payload):
    from tere4ai.eval.harness import _validated_item

    for item in payload["items"]:
        assert item["status"] == "draft"
        _validated_item(item, Path("draft_candidates.json"))


def test_second_annotator_share_is_stratified_20_to_30_percent(payload):
    items = payload["items"]
    for kind in ("classification", "retrieval", "qa"):
        kind_items = [i for i in items if i["kind"] == kind]
        share = sum(1 for i in kind_items if i["second_annotator"]) / len(kind_items)
        assert 0.15 <= share <= 0.35, f"{kind}: share {share}"


def test_drafting_is_deterministic(tmp_path):
    out_a, out_b = tmp_path / "a.json", tmp_path / "b.json"
    assert draft_mod.main(["draft", "--out", str(out_a)]) == 0
    assert draft_mod.main(["draft", "--out", str(out_b)]) == 0
    assert out_a.read_text() == out_b.read_text()


def test_retrieval_gold_is_leaf_precise(payload):
    ids = {i["gold"]["node_id"] for i in payload["items"] if i["kind"] == "retrieval"}
    for node_id in ids:
        assert not any(
            other != node_id and other.startswith(node_id + ":") for other in ids
        ), f"{node_id} has a more precise child in the gold set"


def test_agreement_subcommand_computes_kappa(tmp_path, capsys):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"i1": "high_risk", "i2": "prohibited", "i3": "minimal"}))
    b.write_text(json.dumps({"i1": "high_risk", "i2": "prohibited", "i3": "high_risk"}))
    rc = draft_mod.main(["agreement", str(a), str(b)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "items compared: 3" in out
    assert "cohen kappa" in out

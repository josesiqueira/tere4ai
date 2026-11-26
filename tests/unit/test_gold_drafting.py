"""Gold-set drafting CLI tests (#26, B128): deterministic, verified, protocol-true."""

from __future__ import annotations

import importlib.util
import json
import re
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
def payload():
    # B184: the draft mode refuses at this commit (last test); the drafting as the tag ran it stays testable
    return draft_mod.draft_payload()


def test_target_size_and_kind_mix(payload):
    items = payload["items"]
    assert 60 <= len(items) <= 80
    kinds = {i["kind"] for i in items}
    assert kinds == {"classification", "retrieval", "qa"}


def test_every_draft_source_resolves_in_the_dump(payload):
    dump = json.loads(draft_mod.DUMP_PATH.read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in dump["nodes"]}
    for item in payload["items"]:
        node_id = item["drafted_from"].get("node_id")
        if node_id is not None:
            assert node_id in node_ids, f"{item['id']} is drafted from unknown {node_id}"


def test_drafts_are_marked_and_pass_harness_validation(payload):
    from tere4ai.eval.harness import _validated_item

    for item in payload["items"]:
        assert item["status"] == "draft"
        _validated_item(item, Path("draft_candidates.json"))


def test_no_draft_carries_a_label(payload):
    # B128: two annotators label every case from the Act's text; a label
    # drafted from the classifier or the extracted norms would agree by
    # construction with the system the ablation scores.
    for item in payload["items"]:
        assert item["gold"] is None, item["id"]
        assert item["gold_citations"] == [], item["id"]
        assert item["labels"] == [], item["id"]
        assert item["adjudication"] is None, item["id"]


def test_ids_do_not_name_the_answer(payload):
    # An annotator reads the id; a slug such as "prohibited-social-scoring"
    # or an Annex point would show the case writer's intended answer.
    for item in payload["items"]:
        assert re.fullmatch(r"draft:(cls|ret|qa)-\d{2}", item["id"]), item["id"]


def test_drafting_never_calls_the_classifier():
    assert not hasattr(draft_mod, "classify_ai_system")


def test_drafting_is_deterministic():
    assert json.dumps(draft_mod.draft_payload()) == json.dumps(draft_mod.draft_payload())


def test_retrieval_drafts_come_from_leaf_items(payload):
    ids = {i["drafted_from"]["node_id"] for i in payload["items"] if i["kind"] == "retrieval"}
    for node_id in ids:
        assert not any(
            other != node_id and other.startswith(node_id + ":") for other in ids
        ), f"{node_id} has a more precise child among the drafts"


def test_draft_mode_refuses_at_this_commit_and_names_the_tag(tmp_path, capsys):
    # B184 (DEC-32): the drafts are written in facts of tag v2.0.0-beta.1, some
    # of which the features schema refuses since B184, so draft mode stops with
    # exit code 2 and writes nothing; it is run at that tag
    out = tmp_path / "draft_candidates.json"
    assert draft_mod.main(["draft", "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert "v2.0.0-beta.1" in err and "run it at that tag" in err
    assert not out.exists()

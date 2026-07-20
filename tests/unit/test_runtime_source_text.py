"""Audit D4/D9: the runtime evidence/backlog path resolves verbatim source
text before the model, and degrades (never raises) on empty content.

The F4 fix added source_text to the judge digest field list, but the served
norms payload does not carry it, so at real serving time it was always
"(not provided)". These tests pin the serve-time resolution and the
empty-content degrade path. No model is called.
"""

import json
from pathlib import Path

import pytest

from tere4ai.mcp_server import server
from tere4ai.mcp_server.tools import NON_LEGAL_ADVICE_NOTICE, STATUS_VOCABULARY

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="dump not built")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def test_attach_source_text_populates_from_the_dump(dump):
    node = next(
        n for n in dump["nodes"] if n.get("text") and n["id"].startswith("eu-ai-act:article-9")
    )
    norm = {"norm_id": "x", "source_node_id": node["id"]}
    server._attach_source_text([norm], dump)
    assert norm["source_text"] == node["text"]
    assert norm["source_text"] and norm["source_text"] != "(not provided)"


def test_attach_source_text_is_a_noop_when_already_present(dump):
    norm = {"norm_id": "x", "source_node_id": "eu-ai-act:article-9", "source_text": "kept"}
    server._attach_source_text([norm], dump)
    assert norm["source_text"] == "kept"


def test_empty_content_degrades_to_a_full_envelope(dump):
    env = server._empty_content_envelope("content", dump)
    assert env["status"] in STATUS_VOCABULARY
    assert env["status"] == "not_applicable"
    assert env["non_legal_advice_notice"] == NON_LEGAL_ADVICE_NOTICE
    assert any("no model call was made" in f for f in env["missing_facts"])
    serialized = json.dumps(env).lower()
    assert "compliant" not in serialized and "certified" not in serialized


def test_evaluate_project_evidence_empty_content_makes_no_model_call(dump):
    # A real accepted norm id, empty content: the tool must degrade BEFORE
    # any client construction, so it returns a Section 8 envelope with no
    # model configuration required.
    norms_payload = server._read_json(server.NORMS_PATH)
    if norms_payload is None:
        pytest.skip("norms payload not built")
    norm_id = next(
        n["norm_id"] for n in norms_payload["norms"] if n.get("judge_verdict") == "accepted"
    )
    env = server.evaluate_project_evidence(
        norm_id=norm_id, artifact_type="design_doc", content="   "
    )
    assert env["status"] == "not_applicable"
    assert any("non-empty" in f for f in env["missing_facts"])

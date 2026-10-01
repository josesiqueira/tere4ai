"""Unit tests for the elicitor's provisions rendered from the graph (B10).

Offline only: runs against the repository's published dump
(data/graph_dumps/layer1.json) and the frozen snapshots (data/snapshots).
No model, no network.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tere4ai.elicit_features.provisions import (
    ProvisionUnresolved,
    fact_provisions,
    provision_text,
    render_template,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"

DEFINITION_ID = "eu-ai-act:definition:ai-system"
POINT_ID = "eu-ai-act:annex-iii:point-5:b"
ARTICLE_ID = "eu-ai-act:article-16"


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _node(dump: dict, node_id: str) -> dict:
    return next(n for n in dump["nodes"] if n["id"] == node_id)


def test_definition_renders_as_id_and_exactly_the_node_text(dump: dict) -> None:
    node = _node(dump, DEFINITION_ID)
    got = provision_text(DEFINITION_ID, dump, SNAPSHOTS_DIR)
    assert got == {
        "node_id": DEFINITION_ID,
        "span_id": node["source_span"]["span_id"],
        "text": node["text"],
    }
    rendered, provisions = render_template(
        "Definition:\n{{provision:" + DEFINITION_ID + "}}\n", dump, SNAPSHOTS_DIR
    )
    assert rendered == f"Definition:\n[{DEFINITION_ID}] {node['text']}\n"
    assert "<" not in rendered
    assert provisions == [
        {"node_id": DEFINITION_ID, "span_id": node["source_span"]["span_id"]}
    ]


def test_render_lists_each_provision_once_in_order(dump: dict) -> None:
    template = (
        "{{provision:" + POINT_ID + "}}\n"
        "{{provision:" + DEFINITION_ID + "}}\n"
        "{{provision:" + POINT_ID + "}}\n"
    )
    rendered, provisions = render_template(template, dump, SNAPSHOTS_DIR)
    assert [p["node_id"] for p in provisions] == [POINT_ID, DEFINITION_ID]
    point_text = _node(dump, POINT_ID)["text"]
    assert rendered.count(f"[{POINT_ID}] {point_text}") == 2
    assert "{{provision:" not in rendered
    assert "<" not in rendered


def test_unknown_node_raises_naming_node_and_build(dump: dict) -> None:
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text("eu-ai-act:no-such-node", dump, SNAPSHOTS_DIR)
    message = str(exc.value)
    assert "eu-ai-act:no-such-node" in message
    assert dump["build"]["build_id"] in message
    assert "unknown node" in message


def test_node_without_text_raises(dump: dict) -> None:
    assert not _node(dump, ARTICLE_ID).get("text")
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(ARTICLE_ID, dump, SNAPSHOTS_DIR)
    assert ARTICLE_ID in str(exc.value)
    assert "no text" in str(exc.value)


def test_node_without_span_raises(dump: dict) -> None:
    altered = copy.deepcopy(dump)
    del _node(altered, DEFINITION_ID)["source_span"]
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(DEFINITION_ID, altered, SNAPSHOTS_DIR)
    assert "no source span" in str(exc.value)


def test_altered_snapshot_checksum_raises(dump: dict) -> None:
    altered = copy.deepcopy(dump)
    _node(altered, DEFINITION_ID)["source_span"]["snapshot_sha256"] = "0" * 64
    with pytest.raises(ProvisionUnresolved) as exc:
        provision_text(DEFINITION_ID, altered, SNAPSHOTS_DIR)
    message = str(exc.value)
    assert "span verification failed" in message
    assert "checksum mismatch" in message


def test_render_raises_before_returning_on_any_unresolved(dump: dict) -> None:
    template = "{{provision:" + DEFINITION_ID + "}} {{provision:" + ARTICLE_ID + "}}"
    with pytest.raises(ProvisionUnresolved):
        render_template(template, dump, SNAPSHOTS_DIR)


def test_template_without_placeholders_is_identity(dump: dict) -> None:
    text = "No provisions here.\n## Output\n{\"features\": {}}\n"
    assert render_template(text, dump, SNAPSHOTS_DIR) == (text, [])


def test_fact_provisions_reads_the_section() -> None:
    template = (
        "# Role\n"
        "{{provision:eu-ai-act:definition:ai-system}}\n"
        "## Facts and their provisions\n"
        "- Facts: flags.social_scoring\n"
        "{{provision:eu-ai-act:article-5:paragraph-1:c}}\n"
        "- Facts: flags.creditworthiness_evaluation, flags.life_health_insurance_risk_pricing\n"
        "{{provision:eu-ai-act:annex-iii:point-5:b}}\n"
        "{{provision:eu-ai-act:annex-iii:point-5:c}}\n"
        "## Output\n"
        "{{provision:eu-ai-act:article-50:paragraph-1}}\n"
    )
    assert fact_provisions(template) == {
        "flags.social_scoring": ["eu-ai-act:article-5:paragraph-1:c"],
        "flags.creditworthiness_evaluation": [
            "eu-ai-act:annex-iii:point-5:b",
            "eu-ai-act:annex-iii:point-5:c",
        ],
        "flags.life_health_insurance_risk_pricing": [
            "eu-ai-act:annex-iii:point-5:b",
            "eu-ai-act:annex-iii:point-5:c",
        ],
    }


def test_fact_provisions_without_the_section_is_empty() -> None:
    assert fact_provisions("# Role\n{{provision:eu-ai-act:definition:ai-system}}\n") == {}


def test_fact_provisions_rejects_a_placeholder_before_any_facts_line() -> None:
    template = (
        "## Facts and their provisions\n"
        "{{provision:eu-ai-act:definition:ai-system}}\n"
    )
    with pytest.raises(ValueError):
        fact_provisions(template)

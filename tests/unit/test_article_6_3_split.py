"""Article 6(3) points (a) and (d) as two facts, neither depending on autonomy (B184, D-G91 (7), DEC-32).

The combined fact preparatory_or_narrow_procedural_task leaves the schema
(an input that carries it is refused by name, test_listed_uses); the fact
narrow_procedural_task stands for point (a) and preparatory_task for point
(d), each cites only its own point and quotes its own words, and neither
needs the output to be advisory (ruling R5). The profiling override of the
third subparagraph still cancels the candidacy. Offline: the published
Layer 1 dump on disk, skipped when it is absent.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.b184_cases import all_false
from tests.unit.b184_cases import case as _case

from tere4ai.mcp_server.classify import ARTICLE_6_3_CONDITIONS, classify_ai_system

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
POINT_A = "eu-ai-act:article-6:paragraph-3:point-a"
POINT_D = "eu-ai-act:article-6:paragraph-3:point-d"

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _node_text(dump: dict, node_id: str) -> str:
    return next(n["text"] for n in dump["nodes"] if n.get("id") == node_id)


def test_finding_12_narrow_procedural_task_marks_a_candidate_with_full_autonomy(dump):
    env = classify_ai_system(
        _case(all_false(annex_iii_4a_recruitment=True, narrow_procedural_task=True), autonomy="full"), dump
    )
    assert env["answer"]["article_6_3_exception_candidate"] is True
    assert POINT_A in env["source_nodes"]
    assert POINT_D not in env["source_nodes"]
    assert env["answer"]["risk_category"] == "high_risk" and env["status"] == "requires_human_review"


def test_preparatory_task_cites_point_d_only(dump):
    env = classify_ai_system(
        _case(all_false(annex_iii_4a_recruitment=True, preparatory_task=True), autonomy="partial"), dump
    )
    assert env["answer"]["article_6_3_exception_candidate"] is True
    assert POINT_D in env["source_nodes"]
    assert POINT_A not in env["source_nodes"]


def test_profiling_still_cancels_the_split_conditions(dump):
    env = classify_ai_system(
        _case(all_false(annex_iii_4a_recruitment=True, preparatory_task=True, profiling_of_natural_persons=True)),
        dump,
    )
    assert env["answer"]["article_6_3_exception_candidate"] is False


def test_a_candidate_with_no_autonomy_given_is_marked(dump):
    """No autonomy at all (the field absent) is no longer a reason to drop the candidacy."""
    env = classify_ai_system(_case(all_false(annex_iii_4a_recruitment=True, narrow_procedural_task=True)), dump)
    assert env["answer"]["article_6_3_exception_candidate"] is True
    assert any("by narrow_procedural_task" in line for line in env["answer"]["rationale"])


def test_the_conditions_stand_in_point_order_one_point_each():
    assert [(flag, points) for flag, points, _label in ARTICLE_6_3_CONDITIONS] == [
        ("narrow_procedural_task", (POINT_A,)),
        ("improves_previous_human_activity", ("eu-ai-act:article-6:paragraph-3:point-b",)),
        ("detects_patterns_without_replacing_human_assessment", ("eu-ai-act:article-6:paragraph-3:point-c",)),
        ("preparatory_task", (POINT_D,)),
    ]


@pytest.mark.parametrize(("fact", "node_id"), [("narrow_procedural_task", POINT_A), ("preparatory_task", POINT_D)])
def test_each_description_quotes_its_point_whole_and_names_no_autonomy(dump, fact, node_id):
    flags = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["flags"]["properties"]
    assert "preparatory_or_narrow_procedural_task" not in flags
    description = flags[fact]["description"]
    quoted = description.split("the Act's words: '", 1)[1].split("'", 1)[0]
    assert quoted == _node_text(dump, node_id).rstrip(";.")
    assert "whatever its autonomy" in description
    assert "advisory" not in description


def test_a_candidate_with_full_autonomy_holds_the_article_27_block_open(dump):
    """Point 5(b) makes Article 27(1) apply for any deployer; a candidacy, now
    raised whatever the autonomy, keeps the block unknown, as it did before for
    an advisory system and for points (b) and (c)."""
    settled = classify_ai_system(_case(all_false(creditworthiness_evaluation=True), autonomy="full"), dump)
    assert settled["answer"]["fria"]["applicability"] == "applies"
    env = classify_ai_system(
        _case(all_false(creditworthiness_evaluation=True, narrow_procedural_task=True), autonomy="full"), dump
    )
    fria = env["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert any("Article 6(3) derogation candidacy is pending" in m for m in fria["missing_facts"])

"""B145 (spec G D-G80 (6), (7); brief acceptance A6): the set-up table
against the tracked layer1.json, and the brief's widest sweep rerun over the
core so a back reference the table does not hold fails here."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tere4ai import act_parties as ap
from tere4ai.extract_norms import set_up_rule as su
from tere4ai.parse_legal_structure.amendments import is_deleted

ROOT = Path(__file__).resolve().parents[2]
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"
CORE = ROOT / "data" / "graph_dumps" / "core_nodes.txt"
pytestmark = pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")

# The sweep (brief Section 2, "What the Act's text shows"): a sentence whose
# subject, at its start or after a leading clause, opens with a
# demonstrative or refers back to a paragraph, and is no party of the list.
SENTENCES = re.compile(r"(?<=[.;:])\s+(?=[A-Z])")
SUBJECT = re.compile(
    r"^(?:(?P<lead>.{0,160}?),\s+)?(?P<subject>(?:the|that|this|those|these|such)\b[^;:]{0,140}?)\s+(?:shall|may|must)\b",
    re.IGNORECASE,
)
BACK_REFERENCE = re.compile(r"^(?:that|this|those|these|such)\b|referred to in paragraph", re.IGNORECASE)


@pytest.fixture(scope="module")
def nodes():
    return {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"]}


def test_every_row_names_a_live_unit_and_source_holding_its_words_verbatim(nodes):
    for row in su.ROWS:
        for node_id in (row.unit, row.source):
            assert node_id in nodes and not is_deleted(nodes[node_id]), node_id
            assert nodes[node_id]["type"] == "Paragraph", node_id
        for thing in row.things:
            assert thing in nodes[row.unit]["text"], (row.unit, thing)
        assert row.setting_up in nodes[row.source]["text"], (row.unit, row.setting_up)
        assert row.unit.split(":")[1] == row.source.split(":")[1], f"{row.unit}: never another Article (R11)"
        assert row.party in ap.values() and row.party not in ap.SENTINELS, row.unit


def test_every_not_covered_entry_quotes_its_unit_verbatim(nodes):
    # final review, Task 5 minor: the words of each case left alone are the Act's
    for case in su.NOT_COVERED:
        assert case.unit in nodes and case.words in nodes[case.unit]["text"], (case.unit, case.words)


def test_the_setting_up_words_name_the_rows_party():
    by_value = {p.value: p for p in ap.parties()}
    for row in su.ROWS:
        assert ap.place(row.setting_up.split(" shall ")[0].split(" may ")[0]) == row.party or any(
            ap._words(term) and " ".join(ap._words(term)) in " ".join(ap._words(row.setting_up))
            for term in (by_value[row.party].act_term, *(t for t, _g in by_value[row.party].phrases))
        ), row.unit


def test_the_core_rows_are_the_26_paragraph_units_of_the_brief():
    core = [c.strip() for c in CORE.read_text(encoding="utf-8").split(",") if c.strip()]
    covered = sorted({row.unit for row in su.ROWS if any(row.unit.startswith(c + ":") for c in core)})
    assert len(covered) == 26


def test_the_widest_sweep_over_the_core_finds_nothing_the_table_does_not_name(nodes):
    core = [c.strip() for c in CORE.read_text(encoding="utf-8").split(",") if c.strip()]
    section_2 = {f"article-{n}" for n in range(8, 16)}
    unknown = []
    for node in nodes.values():
        unit = node["id"]
        if node["type"] != "Paragraph" or not node.get("text") or is_deleted(node):
            continue
        if not any(unit.startswith(c + ":") for c in core) or unit.split(":")[1] in section_2 | {"article-3"}:
            continue
        text = re.sub(r"^\d+[a-z]?\.\s+", "", node["text"])
        for sentence in SENTENCES.split(text):
            match = SUBJECT.match(sentence)
            if not match:
                continue
            subject = match.group("subject")
            if ap.place(subject) is not None or not BACK_REFERENCE.search(subject):
                continue
            if re.match(su.PROVISION_SUBJECT, subject, re.IGNORECASE):
                continue  # an application clause (R39)
            named = any(row.unit == unit and any(subject.lower().startswith(t.lower()) for t in row.things) for row in su.ROWS)
            listed = any(nc.unit == unit and subject.lower().startswith(nc.words.lower()) for nc in su.NOT_COVERED)
            if not (named or listed):
                unknown.append((unit, subject))
    assert unknown == []


def test_the_rows_of_a_unit_and_the_rendering():
    assert [r.party for r in su.rows_for("eu-ai-act:article-50:paragraph-5")] == ["provider", "deployer"]
    assert su.rows_for("eu-ai-act:article-12:paragraph-1") == ()
    rendered = su.render_rows(su.rows_for("eu-ai-act:article-72:paragraph-2"))
    assert rendered == (
        "- eu-ai-act:article-72:paragraph-2: “The post-market monitoring system”; “post-market monitoring”; "
        "“This obligation” is provider's; source eu-ai-act:article-72:paragraph-1: "
        "“Providers shall establish and document a post-market monitoring system”"
    )

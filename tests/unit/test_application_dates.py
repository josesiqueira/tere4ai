"""Application dates as data, from Article 113 as amended (B132, D-G68 (6), R7).

Every row quotes its point verbatim from the Layer 1 dump; each provision
the classifier and the requirements cite gets the date of its point; a
wording the Omnibus inserted or replaced applies no earlier than 27 July
2026; Article 111(4) is a note on Article 50(2). No model, no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tere4ai.mcp_server.application_dates import (
    ARTICLE_111_4_WORDING,
    ARTICLE_111_PARAGRAPH_4,
    LEGAL_TEXT_AMENDED,
    OMNIBUS_ENTRY_INTO_FORCE,
    ROUTE_ANNEX_I,
    ROUTE_ANNEX_III,
    ROWS,
    dates_for,
    fria_applies_from,
    legal_text,
    provision_dates,
)

ROOT = Path(__file__).resolve().parents[2]
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
OMNIBUS_FORMEX = ROOT / "data" / "snapshots" / "formex" / "L_202601744EN.000101.fmx.xml"


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(LAYER1_PATH.read_text(encoding="utf-8"))


def _date(node_id: str, dump: dict, route: str | None = None) -> list[str]:
    return [e["date"] for e in provision_dates(node_id, dump, route)]


def test_every_row_quotes_its_point_verbatim(dump):
    nodes = {n["id"]: n for n in dump["nodes"]}
    for key, row in ROWS.items():
        text = " ".join((nodes[row.basis_node].get("text") or "").split())
        assert row.wording in text, key
        assert row.applies_from in ("2025-02-02", "2025-08-02", "2026-07-27", "2026-08-02", "2026-12-02",
                                    "2027-12-02", "2028-08-02"), key


def test_the_omnibus_entry_into_force_and_article_111_4_are_quoted_verbatim(dump):
    raw = OMNIBUS_FORMEX.read_text(encoding="utf-8")
    text = " ".join(re.sub(r"<[^>]+>", " ", raw).split())
    assert OMNIBUS_ENTRY_INTO_FORCE in text
    article_111_4 = next(n for n in dump["nodes"] if n["id"] == ARTICLE_111_PARAGRAPH_4)
    assert ARTICLE_111_4_WORDING in " ".join(article_111_4["text"].split())


def test_chapters_i_and_ii_from_2_february_2025_except_the_omnibus_prohibitions(dump):
    assert _date("eu-ai-act:article-5:paragraph-1:point-a", dump) == ["2025-02-02"]
    assert _date("eu-ai-act:article-3", dump) == ["2025-02-02"]
    for unit in ("eu-ai-act:article-5:paragraph-1:point-ba", "eu-ai-act:article-5:paragraph-1:point-bb",
                 "eu-ai-act:article-5:paragraph-1a", "eu-ai-act:article-5:paragraph-1b"):
        assert _date(unit, dump) == ["2026-12-02"], unit


def test_chapter_iii_sections_1_to_3_follow_the_route_and_article_6_5_the_general_date(dump):
    for article in ("eu-ai-act:article-6:paragraph-1", "eu-ai-act:article-9", "eu-ai-act:article-27"):
        assert _date(article, dump, ROUTE_ANNEX_III) == ["2027-12-02"]
        assert _date(article, dump, ROUTE_ANNEX_I) == ["2028-08-02"]
        assert _date(article, dump) == ["2027-12-02", "2028-08-02"]
    assert _date("eu-ai-act:article-6:paragraph-5", dump, ROUTE_ANNEX_III) == ["2026-08-02"]


def test_the_2_august_2025_group_the_omnibus_articles_and_the_general_date(dump):
    for unit in ("eu-ai-act:article-30", "eu-ai-act:article-53", "eu-ai-act:article-65",
                 "eu-ai-act:article-99", "eu-ai-act:article-78"):
        assert _date(unit, dump) == ["2025-08-02"], unit
    assert _date("eu-ai-act:article-101", dump) == ["2026-08-02"]
    for unit in ("eu-ai-act:article-102", "eu-ai-act:article-110"):
        assert _date(unit, dump) == ["2026-07-27"], unit
    for unit in ("eu-ai-act:article-50:paragraph-1", "eu-ai-act:article-72", "eu-ai-act:article-73",
                 "eu-ai-act:article-111", "eu-ai-act:article-112", "eu-ai-act:article-60a",
                 "eu-ai-act:annex-ii:item-1", "eu-ai-act:annex-xiv"):
        assert _date(unit, dump) == ["2026-08-02"], unit


def test_an_annex_takes_the_date_of_the_article_that_brings_it_into_application(dump):
    """R24 (Codex plan review P1 1): Annex I through Article 6(1), point
    (c)(ii); Annex III through Article 6(2), point (c)(i); Annex IV through
    Article 11(1), on the answer's route; descendants included. The general
    date (2 August 2026) would fail every line here."""
    for unit in ("eu-ai-act:annex-i", "eu-ai-act:annex-i:section-b:point-21"):
        assert _date(unit, dump) == ["2028-08-02"], unit
        assert _date(unit, dump, ROUTE_ANNEX_III) == ["2028-08-02"], unit
    for unit in ("eu-ai-act:annex-iii", "eu-ai-act:annex-iii:point-4", "eu-ai-act:annex-iii:point-5:b"):
        assert _date(unit, dump) == ["2027-12-02"], unit
        assert _date(unit, dump, ROUTE_ANNEX_I) == ["2027-12-02"], unit
    assert _date("eu-ai-act:annex-iv:point-1:a", dump, ROUTE_ANNEX_III) == ["2027-12-02"]
    assert _date("eu-ai-act:annex-iv:point-1:a", dump, ROUTE_ANNEX_I) == ["2028-08-02"]
    assert _date("eu-ai-act:annex-iv", dump) == ["2027-12-02", "2028-08-02"]
    [entry] = provision_dates("eu-ai-act:annex-iii:point-4", dump)
    assert entry["provision"] == "eu-ai-act:annex-iii:point-4"
    assert entry["applies_through"] == "eu-ai-act:article-6:paragraph-2"
    assert any("Annex III applies through Article 6(2)" in n for n in entry["notes"])
    [article] = provision_dates("eu-ai-act:article-9", dump, ROUTE_ANNEX_III)
    assert article["applies_through"] is None


def test_inserted_or_replaced_wording_applies_no_earlier_than_27_july_2026(dump):
    """The spec review's finding: Article 4a, the replaced Article 2(2) and
    Article 3(14a) and (14b) carry the later of their date and 27 July 2026."""
    for unit in ("eu-ai-act:article-4a", "eu-ai-act:article-2:paragraph-2",
                 "eu-ai-act:definition:safety-component",
                 "eu-ai-act:definition:micro-small-and-medium-sized-enterprise",
                 "eu-ai-act:definition:small-mid-cap-enterprise"):
        [entry] = provision_dates(unit, dump)
        assert entry["date"] == "2026-07-27", unit
        assert any("no earlier than its entry into force on 27 July 2026" in n for n in entry["notes"]), unit
    # Chapter II's inserted points keep their own later date.
    assert _date("eu-ai-act:article-5:paragraph-1:point-ba", dump) == ["2026-12-02"]


def test_article_111_4_is_a_note_on_article_50_2_not_its_date(dump):
    [entry] = provision_dates("eu-ai-act:article-50:paragraph-2", dump)
    assert entry["date"] == "2026-08-02"
    assert any("Article 111(4)" in n and "by 2 December 2026" in n for n in entry["notes"])
    [other] = provision_dates("eu-ai-act:article-50:paragraph-1", dump)
    assert other["notes"] == []


def test_each_entry_names_its_point_and_the_text(dump):
    [entry] = provision_dates("eu-ai-act:article-9", dump, ROUTE_ANNEX_III)
    assert entry["source"].startswith("Article 113, third paragraph, point (c)(i), of " + LEGAL_TEXT_AMENDED)
    assert entry["basis_node"] == "eu-ai-act:article-113:paragraph-1:point-c:point-i"
    assert entry["legal_status"] == "in_force"
    assert [e["provision"] for e in dates_for(["eu-ai-act:article-9", "eu-ai-act:article-9"], dump,
                                                ROUTE_ANNEX_III)] == ["eu-ai-act:article-9"]


def test_the_fria_date_comes_from_the_same_table():
    assert fria_applies_from()["date"] == ROWS["c_i"].applies_from == "2027-12-02"


def test_legal_text_names_the_act_as_amended_only_when_the_omnibus_is_merged(dump):
    assert legal_text(dump) == "Regulation (EU) 2024/1689 as amended by Regulation (EU) 2026/1744"
    kept_apart = {"nodes": [{"id": "src:omnibus-com-2025-836", "merged_into_base": False}]}
    assert legal_text(kept_apart) == "Regulation (EU) 2024/1689"

"""The 25 listed uses of Annex III are facts of the features schema (B184, D-G91, DEC-32).

A fact of the classifier means the provision it is read for: each listed use
quotes the whole text of its legal unit, the introductory words of points 1, 6
and 7 are printed and are not a fact, and each fact carries its area and its
use as schema keys. The quotations are compared with the node texts of the
published Layer 1 dump; the test is skipped when the dump is absent, as
test_features_schema_descriptions.py is.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.test_features_schema_descriptions import QUOTE, _normalised

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"

pytestmark = pytest.mark.skipif(not LAYER1_PATH.is_file(), reason="layer1.json dump not built")

# (fact, the use as the Act numbers it, the legal unit), in point order.
LISTED_USES: tuple[tuple[str, str, str], ...] = (
    ("biometric_identification", "1(a)", "eu-ai-act:annex-iii:point-1:a"),
    ("biometric_categorisation_sensitive_or_protected_attributes", "1(b)", "eu-ai-act:annex-iii:point-1:b"),
    ("emotion_recognition", "1(c)", "eu-ai-act:annex-iii:point-1:c"),
    ("critical_infrastructure_safety", "2", "eu-ai-act:annex-iii:point-2"),
    ("annex_iii_3a_admission", "3(a)", "eu-ai-act:annex-iii:point-3:a"),
    ("annex_iii_3b_learning_outcomes", "3(b)", "eu-ai-act:annex-iii:point-3:b"),
    ("annex_iii_3c_education_level", "3(c)", "eu-ai-act:annex-iii:point-3:c"),
    ("annex_iii_3d_test_monitoring", "3(d)", "eu-ai-act:annex-iii:point-3:d"),
    ("annex_iii_4a_recruitment", "4(a)", "eu-ai-act:annex-iii:point-4:a"),
    ("annex_iii_4b_work_relationships", "4(b)", "eu-ai-act:annex-iii:point-4:b"),
    ("annex_iii_5a_public_benefits", "5(a)", "eu-ai-act:annex-iii:point-5:a"),
    ("creditworthiness_evaluation", "5(b)", "eu-ai-act:annex-iii:point-5:b"),
    ("life_health_insurance_risk_pricing", "5(c)", "eu-ai-act:annex-iii:point-5:c"),
    ("annex_iii_5d_emergency_calls", "5(d)", "eu-ai-act:annex-iii:point-5:d"),
    ("annex_iii_6a_victim_risk", "6(a)", "eu-ai-act:annex-iii:point-6:a"),
    ("annex_iii_6b_polygraphs", "6(b)", "eu-ai-act:annex-iii:point-6:b"),
    ("annex_iii_6c_evidence_reliability", "6(c)", "eu-ai-act:annex-iii:point-6:c"),
    ("annex_iii_6d_offending_risk", "6(d)", "eu-ai-act:annex-iii:point-6:d"),
    ("annex_iii_6e_profiling", "6(e)", "eu-ai-act:annex-iii:point-6:e"),
    ("annex_iii_7a_polygraphs", "7(a)", "eu-ai-act:annex-iii:point-7:a"),
    ("annex_iii_7b_entry_risk", "7(b)", "eu-ai-act:annex-iii:point-7:b"),
    ("annex_iii_7c_applications", "7(c)", "eu-ai-act:annex-iii:point-7:c"),
    ("annex_iii_7d_identification", "7(d)", "eu-ai-act:annex-iii:point-7:d"),
    ("annex_iii_8a_judicial", "8(a)", "eu-ai-act:annex-iii:point-8:a"),
    ("annex_iii_8b_elections", "8(b)", "eu-ai-act:annex-iii:point-8:b"),
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _flags() -> dict[str, dict]:
    return _schema()["properties"]["flags"]["properties"]


@pytest.fixture(scope="module")
def dump_texts() -> dict[str, str]:
    dump = json.loads(LAYER1_PATH.read_text(encoding="utf-8"))
    return {n["id"]: n.get("text") or "" for n in dump["nodes"] if n.get("type") != "UnitVersion"}


def test_the_25_listed_uses_are_facts_with_their_area_and_use():
    flags = _flags()
    for fact, use, _unit in LISTED_USES:
        assert flags[fact]["type"] == "boolean"
        assert flags[fact]["x-annex-iii-use"] == use
        assert flags[fact]["x-annex-iii-area"] == int(use[0])
    assert "x-annex-iii-area" not in flags["real_time_remote_biometric_public"]
    keyed = [n for n, s in flags.items() if "x-annex-iii-use" in s]
    assert keyed == [fact for fact, _u, _n in LISTED_USES]  # point order (P4)
    keyed_by_area = [n for n, s in flags.items() if "x-annex-iii-area" in s]
    assert keyed_by_area == [fact for fact, _u, _n in LISTED_USES]
    names = list(flags)
    first = names.index(keyed[0])
    assert names[first:first + 25] == keyed  # contiguous (P4)


@pytest.mark.parametrize("fact,use,unit", LISTED_USES)
def test_each_listed_use_quotes_its_unit_whole(fact, use, unit, dump_texts):
    quoted = _normalised(QUOTE.search(_flags()[fact]["description"]).group(1))
    text = _normalised(dump_texts[unit])
    if unit == "eu-ai-act:annex-iii:point-2":
        text = text.split(": ", 1)[1]
    assert quoted == text.rstrip(";.")


def test_finding_8_point_4b_fact_quotes_the_whole_listed_use():
    description = _flags()["annex_iii_4b_work_relationships"]["description"]
    assert "to allocate tasks based on individual behaviour or personal traits or characteristics" in description
    assert "to monitor and evaluate the performance and behaviour of persons in such relationships" in description


def test_finding_11_point_5_and_6_facts_quote_whole():
    flags = _flags()
    assert "as well as to grant, reduce, revoke, or reclaim such benefits and services" in flags["annex_iii_5a_public_benefits"]["description"]
    assert "to assess the risk of a natural person becoming the victim of criminal offences" in flags["annex_iii_6a_victim_risk"]["description"]


def test_points_1_6_and_7_print_their_opening_words():
    words = "in so far as their use is permitted under relevant Union or national law"
    for fact, use, _unit in LISTED_USES:
        assert (words in _flags()[fact]["description"]) == (use[0] in "167")


def test_area_headings_are_the_acts_headings(dump_texts):
    areas = _schema()["properties"]["flags"]["x-annex-iii-areas"]
    assert list(areas) == [str(n) for n in range(1, 9)]
    for n, heading in areas.items():
        assert heading == _normalised(dump_texts[f"eu-ai-act:annex-iii:point-{n}"]).split(": ", 1)[0]


PERMITTED_USE_SENTENCE = (
    "Answer for the use the system is intended for; whether that use is permitted under Union or "
    "national law is not part of this fact."
)


def test_points_1_6_and_7_say_how_to_answer_the_opening_words():
    """R15: the opening words on lawful use are not a fact, and the twelve facts
    of areas 1, 6 and 7 say so in one sentence; no other fact carries it."""
    carrying = [n for n, s in _flags().items() if PERMITTED_USE_SENTENCE in s["description"]]
    assert carrying == [fact for fact, use, _u in LISTED_USES if use[0] in "167"]
    assert len(carrying) == 12
    for fact in carrying:
        description = _flags()[fact]["description"]
        assert description.index("are not a fact.") < description.index(PERMITTED_USE_SENTENCE)

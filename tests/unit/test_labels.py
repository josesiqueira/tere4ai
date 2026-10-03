"""The Act's own Article and paragraph numbers, letter suffixes included (B132, DEC-23).

Spec G D-G68 (3): inserted units take the Act's numbers (Article 4a,
Article 6(1a)); the node schema reads an Article or paragraph number as the
Act's label with a sort key. Pure functions; no files.
"""

from __future__ import annotations

import pytest

from tere4ai.parse_legal_structure.labels import label_of, padded, parse_label, sort_key


def test_parse_label_splits_number_and_letter():
    assert parse_label("4a") == (4, "a")
    assert parse_label("75") == (75, "")
    assert parse_label("1a") == (1, "a")


def test_sort_key_orders_like_the_act():
    labels = ["5", "4a", "4", "75d", "75a", "75", "76", "6", "4b"]
    assert sorted(labels, key=sort_key) == ["4", "4a", "4b", "5", "6", "75", "75a", "75d", "76"]
    assert sort_key("4") == 400 and sort_key("4a") == 401 and sort_key("1a") == 101


def test_label_of_reads_formex_identifiers():
    assert label_of("004A") == "4a"
    assert label_of("001A") == "1a"
    assert label_of("113") == "113"
    assert label_of("001") == "1"


def test_padded_keeps_the_span_names_of_unchanged_units():
    assert padded("5") == "005"
    assert padded("4a") == "004a"
    assert padded("1a") == "001a"


@pytest.mark.parametrize("bad", ["", "0", "04", "4A", "4aa", "a4", "4 a", None, 4])
def test_anything_else_is_refused(bad):
    with pytest.raises(ValueError):
        parse_label(bad)

"""The Act's own numbers for Articles and paragraphs, letter suffixes included.

@implements: DEC-01 (partial: Article and paragraph labels)
@implements: DEC-23
@grounded_by: REF-01, REF-02, REF-04

The Digital Omnibus (Regulation (EU) 2026/1744) inserts units numbered the
way the Act numbers insertions: Article 4a, Article 6(1a), Articles 75a to
75d. EU acts do not renumber, so an inserted unit keeps the number of the
unit before it and adds a letter. A label is that number as the Act prints
it ("4", "4a", "1a"); the node id carries it unchanged
(eu-ai-act:article-4a:paragraph-1, eu-ai-act:article-6:paragraph-1a). The
sort key orders labels the way the Act does: number times 100 plus the
letter's place in the alphabet (4 -> 400, 4a -> 401, 5 -> 500).

Formex writes the numbers in IDENTIFIER attributes, zero-padded and with an
upper-case letter (ARTICLE "004A", PARAG "005.001A"); label_of reads them.
padded gives the zero-padded lower-case form the span names use
(span:004a.001, fmx:art_005.parag_001a), so a span name of a unit the
Omnibus did not touch is exactly the name it had before (span:005.001).

Deterministic, no model calls (DEC-01).
"""

from __future__ import annotations

import re

LABEL_PATTERN = r"[1-9][0-9]*[a-z]?"
_LABEL = re.compile(r"^([1-9][0-9]*)([a-z]?)$")
_FORMEX_NUMBER = re.compile(r"^0*([1-9][0-9]*)([A-Za-z]?)$")


def parse_label(label: str) -> tuple[int, str]:
    """Split a label into number and letter: "4a" -> (4, "a"), "75" -> (75, "")."""
    match = _LABEL.match(label) if isinstance(label, str) else None
    if match is None:
        raise ValueError(f"not an Article or paragraph label: {label!r}")
    return int(match.group(1)), match.group(2)


def sort_key(label: str) -> int:
    """The Act's order: 4 -> 400, 4a -> 401, 4b -> 402, 5 -> 500."""
    number, letter = parse_label(label)
    return number * 100 + (ord(letter) - ord("a") + 1 if letter else 0)


def label_of(formex_number: str) -> str:
    """A Formex IDENTIFIER part as the Act's label: "004A" -> "4a", "001" -> "1"."""
    match = _FORMEX_NUMBER.match(formex_number) if isinstance(formex_number, str) else None
    if match is None:
        raise ValueError(f"not a Formex number: {formex_number!r}")
    return f"{int(match.group(1))}{match.group(2).lower()}"


def padded(label: str) -> str:
    """The zero-padded form of span names: "5" -> "005", "4a" -> "004a"."""
    number, letter = parse_label(label)
    return f"{number:03d}{letter}"

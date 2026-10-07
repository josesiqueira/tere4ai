"""Cross-check of the subtopic headings (B143, spec G D-G75 (6)): the heading
heuristic that sliced the v1 copy until B143, run over the derived text, finds
the same 23 headings the publisher's typography gives (measured: 23 equal, the
6 rejected candidates are opening sentences of six sections). The heuristic is
test code now; the runtime takes the headings from the derivation record."""

import re

from tere4ai.align_hleg.hleg_source import load_pair

_CANDIDATE = re.compile(r"^([A-Z][^\n]*?)\.[ \t]+(\S)", re.M)
_HEADING_FORBIDDEN = re.compile(r"[,;:()\d]")


def _reject_reason(heading: str, tail_first: str) -> str | None:
    words = heading.split()
    if not 1 <= len(words) <= 7:
        return f"prefix has {len(words)} words (max 7)"
    if len(heading) > 60:
        return f"prefix is {len(heading)} chars (max 60)"
    if _HEADING_FORBIDDEN.search(heading):
        return "prefix contains punctuation or digits"
    if not tail_first.isupper():
        return "text after the period does not start a sentence"
    return None


def test_the_old_heuristic_finds_the_publishers_23_headings():
    pair = load_pair()
    heads = pair.record["requirement_headings"]
    accepted, rejected = [], []
    for i, head in enumerate(heads):
        end = heads[i + 1]["start"] if i + 1 < len(heads) else len(pair.text)
        for match in _CANDIDATE.finditer(pair.text, head["end"], end):
            (rejected if _reject_reason(match.group(1), match.group(2)) else accepted).append(match.group(1))
    assert accepted == [s["label"] for s in pair.record["subtopic_headings"]]
    assert len(rejected) == 6 and all(len(r.split()) > 7 for r in rejected)

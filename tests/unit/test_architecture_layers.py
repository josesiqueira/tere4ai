"""docs/architecture.md Section 1 names exactly the node labels the graph store
accepts (B143, DEC-25; owner, 2026-10-07: "we cant have a stale architecture.md
or untruthful"). The labels are written in backticks on the "- Layer" lines;
the "- Not built:" line names the planned types never built, without backticks
(ruling R22)."""

import re
from pathlib import Path

from tere4ai.graph_store.store import NODE_LABELS

ARCHITECTURE = Path(__file__).resolve().parents[2] / "docs" / "architecture.md"
_CAMEL = re.compile(r"\b[A-Z]{2,}[A-Z][a-z0-9]+\w*|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b")


def _section_1() -> list[str]:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    start = text.index("## 1. Layered graph model")
    return text[start:text.index("\n## 2. ", start)].splitlines()


def test_the_layer_lines_name_exactly_the_labels_the_store_accepts():
    lines = [line for line in _section_1() if line.startswith("- Layer ")]
    assert [line.split()[2] for line in lines] == ["0", "1", "2", "3", "4"]
    named = {label for line in lines for label in re.findall(r"`([A-Za-z]+)`", line)}
    assert named == set(NODE_LABELS)


def test_no_planned_type_is_named_as_if_it_existed():
    lines = _section_1()
    not_built = [line for line in lines if line.startswith("- Not built:")]
    assert len(not_built) == 1 and "`" not in not_built[0]
    planned = set(_CAMEL.findall(not_built[0])) | set(re.findall(r"\b(Obligation|Prohibition|Permission|Right|Project)\b",
                                                                  not_built[0]))
    assert planned and not planned & set(NODE_LABELS)
    for line in (line for line in lines if line.startswith("- Layer ")):
        stray = {w for w in _CAMEL.findall(line) if w not in NODE_LABELS}
        assert not stray, (line[:40], stray)
        assert not {w for w in planned if re.search(rf"\b{w}\b", line)}, line[:40]

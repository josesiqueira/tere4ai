"""The relation-type definitions both Layer 3 prompts carry (B163).

@implements: DEC-28 (partial: the relation-type definitions align_hleg and judge_alignment share)
@grounded_by: REF-24

From judge_alignment v2 on, the alignment judge receives the five
definitions the generator has always received (align_hleg v1 lines 32 to
42), from this one file, so the judge checks and corrects a relation type
against the definitions the generator chose it from (spec G D-G86 (2),
CHANGE4). The prompt files carry the text byte for byte and a test checks
both; the E1 label sheet prints the same constant for an alignment whose
judge read it.
"""

from __future__ import annotations

from pathlib import Path

RELATION_TYPE_DEFINITIONS_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "relation_type" / "definitions.md"
)
RELATION_TYPE_DEFINITIONS_TEXT = RELATION_TYPE_DEFINITIONS_PATH.read_text(encoding="utf-8")

# judge_alignment v1 never received the definitions; every later version does.
JUDGE_PROMPTS_WITHOUT_DEFINITIONS = frozenset({"v1"})


def judge_read_definitions(prompt_version: str | None) -> bool:
    """True when an alignment judge run under this prompt version received
    the definitions; a run that records no version is read as v1."""
    return (prompt_version or "v1") not in JUDGE_PROMPTS_WITHOUT_DEFINITIONS

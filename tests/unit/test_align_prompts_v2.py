"""B163 (DEC-28, spec G D-G86 (1), (2)): align_hleg v2 and judge_alignment v2
are their v1 files with D-G86's changes and nothing else. The expected texts
are built here from the v1 files, and the prompt files must equal them byte
for byte; the v1 files, the July build's instruments, are never edited.
Offline, no model."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tere4ai.align_hleg.relation_types import (
    JUDGE_PROMPTS_WITHOUT_DEFINITIONS,
    RELATION_TYPE_DEFINITIONS_PATH,
    RELATION_TYPE_DEFINITIONS_TEXT,
    judge_read_definitions,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"
LAYER1 = ROOT / "data" / "graph_dumps" / "layer1.json"

# the v1 files at tere4ai2 ad86369 (G2)
V1_SHA256 = {
    "align_hleg": "c4678afd98b8e797e1f5f7035dc33024069f8054b79698dc839d9778aba4d7a2",
    "judge_alignment": "41c783c201e303072391bb1edddf8ab526863b70e0b3ce28bf54616c09e0b860",
}
# align_hleg v1.md lines 32 to 42, the five definitions (614 bytes)
DEFINITIONS_SHA256 = "90110cb755a9ee708462323432e1991243081995a3262f2e36a1a33a6e1a633f"

# CHANGE1, CHANGE5, CHANGE8, CHANGE2 (align_hleg's one "mapping")
ALIGN_CHANGES = (
    ("# align_hleg system prompt, version v1\n", "# align_hleg system prompt, version v2\n"),
    ('      "relation_type": "supports",\n', '      "relation_type": "partially_operationalizes",\n'),
    ("   The quotes are checked mechanically by exact substring match; a\n",
     "   The quotes are checked mechanically by substring match, every run of\n"
     "   spaces and line breaks counting as one space; a\n"),
    ('this norm, return {"alignments": []}. Never force a mapping, never pick\n',
     'this norm, return {"alignments": []}. Never force an alignment, never pick\n'),
)


def _read(kind: str, version: str) -> str:
    return (PROMPTS / kind / f"{version}.md").read_text(encoding="utf-8")


def definitions_from_v1() -> str:
    """align_hleg v1.md lines 32 to 42, read from the v1 file itself."""
    return "".join(_read("align_hleg", "v1").splitlines(keepends=True)[31:42])


def judge_changes() -> tuple[tuple[str, str], ...]:
    """CHANGE1, CHANGE2 (six places), CHANGE3 (checks 3 and 4) and CHANGE4
    (the relation-type section before the checks, ending with CHANGE3's
    sentence on no_clear_relation)."""
    section = (
        "## Relation types\n"
        "\n"
        "The generator chose the candidate's relation_type from these definitions;\n"
        "judge it, and any correction you make, against the same definitions:\n"
        "\n"
        f"{definitions_from_v1()}"
        "\n"
        "no_clear_relation is never a type the generator proposes; you use it\n"
        "only as the corrected_relation_type of a rejected candidate (check 4).\n"
        "\n"
    )
    return (
        ("# judge_alignment system prompt, version v1\n", "# judge_alignment system prompt, version v2\n"),
        ("You are the build-time mapping judge for TERE4AI, an evidence-gated\n",
         "You are the build-time alignment judge for TERE4AI, an evidence-gated\n"),
        ("them. Your job is to gate the candidate: only mappings grounded in evidence\n",
         "them. Your job is to gate the candidate: only alignments grounded in evidence\n"),
        ("on both sides may enter the graph. A mapping is an auditable claim, not law.\n",
         "on both sides may enter the graph. An alignment is an auditable claim, not law.\n"),
        ("   in the quoted spans. Reject any mapping whose rationale relies on\n",
         "   in the quoted spans. Reject any alignment whose rationale relies on\n"),
        ("4. No forced mapping: if the spans show no clear relation between the norm\n",
         "4. No forced alignment: if the spans show no clear relation between the norm\n"),
        ("- operational_utility: how useful this mapping is to an engineering team\n",
         "- operational_utility: how useful this alignment is to an engineering team\n"),
        ("   supports, related_to, conflicts_with, no_clear_relation) and judge the\n",
         "   supports, related_to, conflicts_with) and judge the\n"),
        ("   vague relation.\n", "   vague relation, and set corrected_relation_type to no_clear_relation.\n"),
        ("## Checks (all must hold for acceptance)\n", section + "## Checks (all must hold for acceptance)\n"),
    )


def rebuild(kind: str) -> str:
    text = _read(kind, "v1")
    for old, new in ALIGN_CHANGES if kind == "align_hleg" else judge_changes():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def test_the_v1_prompts_are_never_edited():
    for kind, sha in V1_SHA256.items():
        assert hashlib.sha256((PROMPTS / kind / "v1.md").read_bytes()).hexdigest() == sha, kind


def test_the_definitions_file_is_align_hleg_v1_lines_32_to_42_byte_for_byte():
    expected = definitions_from_v1()
    assert expected.startswith('- "directly_operationalizes": the legal norm makes the HLEG requirement\n')
    assert expected.endswith("  requirement demands.\n")
    assert RELATION_TYPE_DEFINITIONS_PATH == PROMPTS / "relation_type" / "definitions.md"
    assert RELATION_TYPE_DEFINITIONS_PATH.read_bytes() == expected.encode("utf-8")
    assert len(expected.encode("utf-8")) == 614
    assert hashlib.sha256(expected.encode("utf-8")).hexdigest() == DEFINITIONS_SHA256
    assert RELATION_TYPE_DEFINITIONS_TEXT == expected


def test_align_hleg_v2_is_v1_with_d_g86s_changes_only():
    assert _read("align_hleg", "v2") == rebuild("align_hleg")


def test_judge_alignment_v2_is_v1_with_d_g86s_changes_only():
    assert _read("judge_alignment", "v2") == rebuild("judge_alignment")


def test_the_definitions_are_carried_by_both_v2_prompts_and_by_no_v1_judge():
    """A3 (G4): one source, carried byte for byte where a judge or the generator reads it."""
    assert _read("align_hleg", "v1").count(RELATION_TYPE_DEFINITIONS_TEXT) == 1
    assert _read("align_hleg", "v2").count(RELATION_TYPE_DEFINITIONS_TEXT) == 1
    assert _read("judge_alignment", "v2").count(RELATION_TYPE_DEFINITIONS_TEXT) == 1
    assert RELATION_TYPE_DEFINITIONS_TEXT not in _read("judge_alignment", "v1")


def test_which_judge_versions_read_the_definitions():
    """The E1 sheet shows the definitions only where the judge read them (R10)."""
    assert JUDGE_PROMPTS_WITHOUT_DEFINITIONS == frozenset({"v1"})
    assert not judge_read_definitions("v1") and not judge_read_definitions(None)
    for path in sorted((PROMPTS / "judge_alignment").glob("v*.md")):
        carries = RELATION_TYPE_DEFINITIONS_TEXT in path.read_text(encoding="utf-8")
        assert carries == judge_read_definitions(path.stem), path.name


def test_neither_v2_prompt_says_mapping_or_carries_a_dash():
    """A4 (R2, G14)."""
    for kind in ("align_hleg", "judge_alignment"):
        text = _read(kind, "v2")
        assert text.startswith(f"# {kind} system prompt, version v2\n"), kind
        assert not re.search(r"\bmappings?\b", text, re.IGNORECASE), kind
        assert "\u2014" not in text and "\u2013" not in text, kind


@pytest.mark.skipif(not LAYER1.is_file(), reason="the tracked layer1.json is absent")
def test_the_v2_output_example_obeys_the_rules():
    """A5 (G5, R5): both quotes pass the quote check against Article 9(1) and
    the technical robustness and safety description, the target id is one of
    the seven, and the type is the one the definitions give."""
    from tere4ai.align_hleg.hleg_nodes import build_hleg_nodes
    from tere4ai.align_hleg.pipeline import PROPOSABLE_RELATION_TYPES, _quote_found

    text = _read("align_hleg", "v2")
    example = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
    (candidate,) = example["alignments"]
    assert candidate["relation_type"] == "partially_operationalizes"
    assert candidate["relation_type"] in PROPOSABLE_RELATION_TYPES
    nodes = {n["id"]: n for n in json.loads(LAYER1.read_text(encoding="utf-8"))["nodes"] if isinstance(n, dict)}
    hleg = {n["id"]: n["description"] for n in build_hleg_nodes()}
    assert candidate["target_id"] == "hleg:technical-robustness-and-safety" and candidate["target_id"] in hleg
    assert _quote_found(candidate["source_quote"], nodes["eu-ai-act:article-9:paragraph-1"]["text"])
    assert [i for i, d in hleg.items() if _quote_found(candidate["target_quote"], d)] == [candidate["target_id"]]


def test_v3_is_the_default_and_the_version_of_record_for_b74():
    """A10 (R1): one constant; the record file names its value (a YAML file
    cannot read a Python constant, so the test checks the value). v2 until
    B174; v3 (v2 plus the judge's paragraph on the Act in force) since
    2026-10-15."""
    import inspect

    from tere4ai.align_hleg import pipeline

    assert pipeline.DEFAULT_PROMPT_VERSION == "v3"
    assert inspect.signature(pipeline.align_norms).parameters["prompt_version"].default == "v3"
    record = (ROOT / "eval" / "config_evaluated.yaml").read_text(encoding="utf-8")
    assert "  align_hleg: v3\n" in record and "  judge_alignment: v3\n" in record

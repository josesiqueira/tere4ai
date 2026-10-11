"""What makes two E6 runs repetitions of one another (spec G D-G84 (7); B150).

@implements: DEC-17
@grounded_by: ADD-20

A repetition names the group's first run (--repeat-of), and its run must
read the same files (by digest), the same items, the same models and the
same build, in the same item set; once both runs have ended, the same
prompt versions too. scripts/run_ablations.py checks the first five before
any model call; scripts/analyse_ablations.py checks all of them before it
reads a figure.
"""

from __future__ import annotations

from typing import Any

# the inputs, by kind, two runs of one group read alike; "checkpoint_resumed"
# is a run's own and is never compared
GROUP_INPUT_KINDS = ("layer1_dump", "norms", "benchmark", "gold_seed", "features", "e6_declaration")


def _inputs(record: dict[str, Any]) -> dict[str, str]:
    return {i["input_kind"]: i["sha256"] for i in record.get("inputs") or []}


def _build(record: dict[str, Any]) -> tuple[Any, Any]:
    build = record.get("build") or {}
    return build.get("base_build_id"), build.get("publication")


def identity_differences(first: dict[str, Any], other: dict[str, Any], *, prompt_versions: bool) -> list[str]:
    """The names of what differs between two run records (or a record and the
    record a run is about to begin); empty when they are one group's runs."""
    out = [kind for kind in GROUP_INPUT_KINDS if _inputs(first).get(kind) != _inputs(other).get(kind)]
    if first.get("item_selection_sha256") != other.get("item_selection_sha256"):
        out.append("items")
    if (first.get("models") or {}) != (other.get("models") or {}):
        out.append("models")
    if _build(first) != _build(other):
        out.append("build")
    if (first.get("config") or {}).get("item_set") != (other.get("config") or {}).get("item_set"):
        out.append("item_set")
    if prompt_versions and (first.get("prompt_versions") or {}) != (other.get("prompt_versions") or {}):
        out.append("prompt_versions")
    return out


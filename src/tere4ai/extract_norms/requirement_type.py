"""The requirement type of a norm or a control: one closed slot, three values.

@implements: DEC-19
@implements: DEC-27
@grounded_by: ADD-54, ADD-55, ADD-56, ADD-57

Every operator obligation or prohibition carries requirement_type,
functional, quality or process, three of the examples of the requirements
type attribute in ISO/IEC/IEEE 29148:2018 clause 5.2.8.3 (ADD-54); every
other norm carries null, shown "not an operator requirement". The scope is
a closed rule over fields the norm already has (deontic type, actor, source
group), so it is applied here in code and no model decides it (ruling 13 of
the B65 rulings file). The judges record their view of the type and never
gate on it; parse_judge_view turns a judge reply into that record, and a
reply that omits it or gives an invalid value records null.

The definitions, the reading rules and the scope have one source each,
prompts/requirement_type/definitions.md and scope.md, read here into
DEFINITIONS_TEXT and SCOPE_TEXT. The v2 and v3 prompts that name the type
carry those bytes (tests check it), so each prompt's hash covers what the model
read, and the extractor, the extraction judge, the backlog generator and the
runtime judge read the same words; the dashboard pins its copy for the
specialists, the judge template and the annotation guideline against the
same file.

B145 (DEC-27): the addressee condition reads schema/act_parties.json from extract_norms v5 on; v1 to v4 read the first reading, frozen in scope_first_reading.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tere4ai.act_parties import addressee_condition, compute, is_v2
from tere4ai.extract_norms.scope_first_reading import (
    FIRST_READING_VERSIONS,
    is_operator_actor_first_reading,
)
from tere4ai.mcp_server.requirements import _is_requirement_group, _source_group

REQUIREMENT_TYPES = ("functional", "quality", "process")

# How a null type reads (DEC-19; B65 ruling 53): outside the scope it is "not
# an operator requirement"; inside it, a missing type is "no type" (the
# extractor or the generator gave none), never the scope's reading.
NOT_AN_OPERATOR_REQUIREMENT = "not an operator requirement"
NO_TYPE = "no type"

# The judge's recorded view on a norm, a judge run or a backlog item. A
# record from a build before DEC-19 carries none of the type fields, and no
# reader invents null for it.
JUDGE_VIEW_FIELDS = ("judge_type_agrees", "judge_requirement_type")

# The one source of the definitions, the reading rules and the scope.
TEXT_DIR = Path(__file__).resolve().parents[3] / "prompts" / "requirement_type"
DEFINITIONS_PATH = TEXT_DIR / "definitions.md"
SCOPE_PATH = TEXT_DIR / "scope.md"
DEFINITIONS_TEXT = DEFINITIONS_PATH.read_text(encoding="utf-8")
SCOPE_TEXT = SCOPE_PATH.read_text(encoding="utf-8")
# B145 (spec G D-G80 (3)): the scope's second version, carried by
# extract_norms v5, judge_norms v5 and guideline v4; scope.md stays the
# first, carried by v2 to v4 (brief R20).
SCOPE_V2_PATH = TEXT_DIR / "scope_v2.md"
SCOPE_TEXT_V2 = SCOPE_V2_PATH.read_text(encoding="utf-8")

TYPED_DEONTIC_TYPES = ("obligation", "prohibition")

# B65 ruling 49: the prompt versions written before DEC-19 (extract_norms and
# judge_norms v1, generate_backlog and runtime_grounding v1). A run under one
# of them feeds its judge the input it always had and writes no type field.
UNTYPED_PROMPT_VERSIONS = frozenset({"v1"})


def types_for(prompt_version: str) -> bool:
    """True when a run under this prompt version carries the requirement type."""
    return prompt_version not in UNTYPED_PROMPT_VERSIONS


def clean_type(value: Any) -> str | None:
    """A type value as recorded: one of REQUIREMENT_TYPES, else None."""
    return value if isinstance(value, str) and value in REQUIREMENT_TYPES else None


def is_operator_actor(explicit: Any, inferred: Any, prompt_version: str | None = None) -> bool:
    """True when the norm's addressee meets DEC-19's addressee condition.

    Under prompt versions v1 to v4 the condition is read as it was at
    tere4ai2 8440c99 (scope_first_reading, brief R27); from v5, and for a
    norm that names no extraction version (a human norm), the addressee's
    value of schema/act_parties.json decides: one of the six AI Act roles or
    the two sentinels (spec G D-G80 (3)). No addressee at all is unsettled,
    a pending human decision, and counts (ruling 17).
    """
    if prompt_version in FIRST_READING_VERSIONS:
        return is_operator_actor_first_reading(explicit, inferred)
    value, _placement = compute(explicit, inferred)
    return value in addressee_condition()


def _slots(norm: dict[str, Any]) -> tuple[Any, Any]:
    if is_v2(norm):
        return norm.get("addressee_explicit"), norm.get("addressee_inferred")
    return norm.get("actor_explicit"), norm.get("actor_inferred")


def in_scope(norm: dict[str, Any], prompt_version: str | None = None) -> bool:
    """DEC-19's scope: an obligation or prohibition addressed to an operator in
    a requirement group. prompt_version, when not given, is the norm's
    extractor_prompt_version."""
    if norm.get("deontic_type") not in TYPED_DEONTIC_TYPES:
        return False
    if not _is_requirement_group(_source_group(str(norm.get("source_node_id") or ""))):
        return False
    version = prompt_version if prompt_version is not None else norm.get("extractor_prompt_version")
    return is_operator_actor(*_slots(norm), prompt_version=version)


def scoped_type(norm: dict[str, Any], prompt_version: str | None = None) -> str | None:
    """The type a norm keeps: null outside the scope whatever was proposed,
    and null for a missing or invalid proposal inside it."""
    if not in_scope(norm, prompt_version):
        return None
    return clean_type(norm.get("requirement_type"))


def parse_judge_view(reply: Any, recorded_type: str | None) -> tuple[bool | None, str | None]:
    """A judge's recorded view of one type: (agrees, the judge's type).

    reply is the judge's object for the item ({"requirement_type_agrees":
    bool, "requirement_type": the judge's own type when it disagrees}).
    Agreement records the agreed type; disagreement records the judge's own
    type, which must be a valid type other than the recorded one. Anything
    else (a missing or non-boolean agreement, an invalid or equal own type)
    records (None, None) and never touches a verdict. On an item whose type
    is null nothing is recorded (DEC-19).
    """
    if recorded_type is None or not isinstance(reply, dict):
        return None, None
    agrees = reply.get("requirement_type_agrees")
    if agrees is True:
        return True, recorded_type
    own = clean_type(reply.get("requirement_type"))
    if agrees is False and own is not None and own != recorded_type:
        return False, own
    return None, None


def type_label(norm: dict[str, Any]) -> str:
    """How a norm's type reads: the type, NO_TYPE for an untyped norm inside
    the scope, NOT_AN_OPERATOR_REQUIREMENT outside it (ruling 53)."""
    value = clean_type(norm.get("requirement_type"))
    if value is not None:
        return value
    return NO_TYPE if in_scope(norm) else NOT_AN_OPERATOR_REQUIREMENT


def carried(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """The type fields a record carries, for a reader that passes them on."""
    return {key: record[key] for key in keys if key in record}

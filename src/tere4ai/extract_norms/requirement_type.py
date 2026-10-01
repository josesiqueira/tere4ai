"""The requirement type of a norm or a control: one closed slot, three values.

@implements: DEC-19
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
DEFINITIONS_TEXT and SCOPE_TEXT. The v2 prompts that name the type carry
those bytes (tests check it), so each prompt's hash covers what the model
read, and the extractor, the extraction judge, the backlog generator and the
runtime judge read the same words; the dashboard pins its copy for the
specialists, the judge template and the annotation guideline against the
same file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tere4ai.canonicalize.canonicalizer import canonicalize_actor
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

TYPED_DEONTIC_TYPES = ("obligation", "prohibition")

# B65 ruling 49: the prompt versions written before DEC-19 (extract_norms and
# judge_norms v1, generate_backlog and runtime_grounding v1). A run under one
# of them feeds its judge the input it always had and writes no type field.
UNTYPED_PROMPT_VERSIONS = frozenset({"v1"})


def types_for(prompt_version: str) -> bool:
    """True when a run under this prompt version carries the requirement type."""
    return prompt_version not in UNTYPED_PROMPT_VERSIONS


# DEC-19 (ruling 17): the actorRole values that are operators. An
# unspecified actor is a pending human decision, so it is in scope.
OPERATOR_ROLES = (
    "provider",
    "deployer",
    "importer",
    "distributor",
    "authorised_representative",
    "product_manufacturer",
    "operator_general",
    "unspecified_needs_review",
)
NON_OPERATOR_ROLES = (
    "commission",
    "ai_office",
    "member_state",
    "notifying_authority",
    "market_surveillance_authority",
    "notified_body",
    "affected_person",
)
# canonicalize_actor's closed table names "operator" for the Act's
# operators; every other canonical value maps to itself.
_OPERATOR_CANONICAL = frozenset(
    {"provider", "deployer", "importer", "distributor", "authorised_representative",
     "product_manufacturer", "operator"}
)
# Words that decide an explicit actor canonicalize_actor cannot resolve
# ("that initial provider", "the competent judicial authority"): an operator
# word keeps the norm in scope, otherwise a non-operator word takes it out,
# otherwise the actor is unspecified and in scope.
_OPERATOR_WORDS = ("provider", "deployer", "importer", "distributor",
                   "authorised representative", "manufacturer", "operator")
_NON_OPERATOR_WORDS = ("commission", "ai office", "member state", "authorit",
                       "notified bod", "affected person")


def clean_type(value: Any) -> str | None:
    """A type value as recorded: one of REQUIREMENT_TYPES, else None."""
    return value if isinstance(value, str) and value in REQUIREMENT_TYPES else None


def is_operator_actor(actor_explicit: Any, actor_inferred: Any) -> bool:
    """True when the norm's actor, explicit or inferred, is an operator.

    An inferred actor is an actorRole value and decides alone. An explicit
    actor goes through the canonical actor table (DEC-04); one the table
    cannot resolve is read by its words. No actor at all is unspecified,
    a pending human decision, and counts as an operator (ruling 17).
    """
    if isinstance(actor_inferred, str) and actor_inferred:
        return actor_inferred in OPERATOR_ROLES
    if not isinstance(actor_explicit, str) or not actor_explicit.strip():
        return True
    canonical, _method = canonicalize_actor(actor_explicit)
    if canonical is not None:
        return canonical in _OPERATOR_CANONICAL
    text = " ".join(actor_explicit.lower().split())
    if any(word in text for word in _OPERATOR_WORDS):
        return True
    return not any(word in text for word in _NON_OPERATOR_WORDS)


def in_scope(norm: dict[str, Any]) -> bool:
    """DEC-19's scope: an operator obligation or prohibition in a requirement group."""
    if norm.get("deontic_type") not in TYPED_DEONTIC_TYPES:
        return False
    if not _is_requirement_group(_source_group(str(norm.get("source_node_id") or ""))):
        return False
    return is_operator_actor(norm.get("actor_explicit"), norm.get("actor_inferred"))


def scoped_type(norm: dict[str, Any]) -> str | None:
    """The type a norm keeps: null outside the scope whatever was proposed,
    and null for a missing or invalid proposal inside it."""
    if not in_scope(norm):
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

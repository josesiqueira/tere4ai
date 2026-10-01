"""The requirement type's scope, cleaning and judge view (DEC-19, B65).

Pure functions, no model, no network. The scope cases follow DEC-19's
list: an operator obligation or prohibition in a requirement group keeps
its type; a permission, a norm in Articles 5 to 7 or an annex, and a norm
addressed to the Commission or an authority carry null whatever the
extractor proposed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tere4ai.extract_norms.requirement_type import (
    DEFINITIONS_PATH,
    DEFINITIONS_TEXT,
    NO_TYPE,
    NON_OPERATOR_ROLES,
    NOT_AN_OPERATOR_REQUIREMENT,
    OPERATOR_ROLES,
    REQUIREMENT_TYPES,
    SCOPE_PATH,
    SCOPE_TEXT,
    clean_type,
    in_scope,
    is_operator_actor,
    parse_judge_view,
    scoped_type,
    type_label,
    types_for,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schema" / "json_schemas" / "norms.schema.json").read_text(encoding="utf-8"))


def _norm(**overrides):
    norm = {
        "source_node_id": "eu-ai-act:article-12:paragraph-1",
        "deontic_type": "obligation",
        "actor_explicit": None,
        "actor_inferred": "provider",
        "requirement_type": "functional",
    }
    norm.update(overrides)
    return norm


def test_the_three_types_and_the_roles_match_the_schema():
    assert SCHEMA["$defs"]["requirementType"]["enum"] == list(REQUIREMENT_TYPES)
    roles = SCHEMA["$defs"]["actorRole"]["enum"]
    assert sorted(OPERATOR_ROLES + NON_OPERATOR_ROLES) == sorted(roles)


def test_the_type_fields_are_optional_and_nullable_in_the_schema():
    for field in ("requirement_type", "judge_type_agrees", "judge_requirement_type"):
        assert field in SCHEMA["properties"]
        assert field not in SCHEMA["required"]


def test_an_operator_obligation_in_a_requirement_group_keeps_its_type():
    assert in_scope(_norm())
    assert scoped_type(_norm()) == "functional"
    assert scoped_type(_norm(deontic_type="prohibition", requirement_type="process")) == "process"


@pytest.mark.parametrize(
    "overrides",
    [
        {"deontic_type": "permission"},
        {"deontic_type": "right"},
        {"deontic_type": "exemption"},
        {"source_node_id": "eu-ai-act:article-5:paragraph-1:point-a"},
        {"source_node_id": "eu-ai-act:article-6:paragraph-2"},
        {"source_node_id": "eu-ai-act:annex-iv:point-2"},
        {"actor_inferred": "commission"},
        {"actor_inferred": "market_surveillance_authority"},
        {"actor_inferred": "affected_person"},
        {"actor_inferred": None, "actor_explicit": "the Commission"},
        {"actor_inferred": None, "actor_explicit": "Member States"},
        {"actor_inferred": None, "actor_explicit": "national competent authorities"},
        {"actor_inferred": None, "actor_explicit": "the competent judicial authority"},
    ],
)
def test_outside_the_scope_the_type_is_null_whatever_was_proposed(overrides):
    assert scoped_type(_norm(**overrides)) is None


@pytest.mark.parametrize(
    "explicit",
    ["providers of high-risk AI systems", "that initial provider", "deployers who are employers",
     "any distributor, importer, deployer or other third party", "operators", "that system", "data sets"],
)
def test_an_explicit_operator_or_unspecified_actor_is_in_scope(explicit):
    assert is_operator_actor(explicit, None)
    assert scoped_type(_norm(actor_inferred=None, actor_explicit=explicit)) == "functional"


def test_unspecified_and_operator_general_inferred_actors_are_in_scope():
    assert is_operator_actor(None, "unspecified_needs_review")
    assert is_operator_actor(None, "operator_general")
    assert is_operator_actor(None, None)


@pytest.mark.parametrize("bad", [None, "", "non-functional", "Functional", "constraint", 3, ["quality"]])
def test_a_missing_or_invalid_proposal_in_scope_is_null(bad):
    assert clean_type(bad) is None
    assert scoped_type(_norm(requirement_type=bad)) is None


def test_the_judge_view_records_agreement_or_its_own_type():
    assert parse_judge_view({"requirement_type_agrees": True}, "quality") == (True, "quality")
    assert parse_judge_view(
        {"requirement_type_agrees": False, "requirement_type": "process"}, "quality"
    ) == (False, "process")


@pytest.mark.parametrize(
    "reply",
    [
        {},
        {"requirement_type_agrees": "yes"},
        {"requirement_type_agrees": False},
        {"requirement_type_agrees": False, "requirement_type": "quality"},
        {"requirement_type_agrees": False, "requirement_type": "non-functional"},
        "not an object",
        None,
    ],
)
def test_an_unusable_judge_view_records_null(reply):
    assert parse_judge_view(reply, "quality") == (None, None)


def test_no_view_is_recorded_on_a_norm_whose_type_is_null():
    assert parse_judge_view({"requirement_type_agrees": True}, None) == (None, None)
    assert parse_judge_view({"requirement_type_agrees": False, "requirement_type": "process"}, None) == (None, None)


def _normalised(text: str) -> str:
    return " ".join(text.split())


# The registered quotes DEC-19 rests on (tere4ai2 docs/references.md, ADD-54
# to ADD-57; the notes in the private research repository hold the page of
# each), word for word.
REGISTERED_QUOTES = (
    # ADD-54 q2, 29148 5.2.8.3, functional
    "Functional/Performance. Functional requirements describe the system or system element "
    "functions or tasks to be performed by the system.",
    # ADD-55 q1, 24765 3.1704, both definitions
    "1. statement that identifies what results a product or process shall produce 2. requirement "
    "that specifies a function that a system or system component shall perform",
    # ADD-54 q5, 29148 5.2.8.3, Quality (Non-Functional) Requirements
    "Include a number of the 'ilities' in requirements to include, for example, transportability, "
    "survivability, flexibility, portability, reusability, reliability, maintainability and security.",
    # ADD-55 q2, 24765 3.3287 definition 1
    "requirement that a software attribute be present in software to satisfy a contract, standard, "
    "specification, or other formally imposed document",
    # ADD-54 q3, 29148 5.2.8.3, process
    "Process Requirements. These are stakeholder, usually acquirer or user, requirements imposed "
    "through the contract or statement of work.",
    # ADD-57 q1, SWEBOK V4.0a 1.3
    "constrain the project that constructs the software.",
    # ADD-56 q1, Glinz section 4.2
    "As project and process requirements are conceptually different from system requirements, they "
    "should be distinguished at the root level and not in a sub-category such as non-functional "
    "requirements.",
)


def test_the_definitions_carry_dec_19s_quotes_for_all_three_types():
    """Review I2: the one source text holds DEC-19's definitions of all three
    types, each quote word for word as registered and as DEC-19 prints it."""
    text = _normalised(DEFINITIONS_TEXT)
    architecture = _normalised((ROOT / "docs" / "architecture.md").read_text(encoding="utf-8"))
    for quote in REGISTERED_QUOTES:
        assert quote in text, quote
        assert quote in architecture, quote
    assert "Quality (Non-Functional) Requirements" in text
    assert "not a closed list" in text
    assert "this project's reading beyond the source" in text
    for quote in re.findall(r'"([^"]+)"', text):
        if len(quote) >= 20:
            assert quote in architecture, quote


def test_the_one_source_is_the_two_files():
    assert DEFINITIONS_TEXT == DEFINITIONS_PATH.read_text(encoding="utf-8")
    assert SCOPE_TEXT == SCOPE_PATH.read_text(encoding="utf-8")
    assert DEFINITIONS_PATH.parent == ROOT / "prompts" / "requirement_type"


def test_a_null_type_reads_no_type_inside_the_scope_and_not_an_operator_requirement_outside():
    """Review I5: a missing type on an in-scope norm is the extractor's gap,
    never the scope's reading."""
    assert type_label(_norm(requirement_type="process")) == "process"
    assert type_label(_norm(requirement_type=None)) == NO_TYPE == "no type"
    assert type_label(_norm(requirement_type=None, deontic_type="permission")) == NOT_AN_OPERATOR_REQUIREMENT
    assert type_label(_norm(requirement_type="non-functional")) == NO_TYPE


def test_only_the_pre_dec_19_prompt_versions_are_untyped():
    assert not types_for("v1")
    assert types_for("v2") and types_for("v3")


def test_the_scope_text_names_every_non_operator_role():
    text = _normalised(SCOPE_TEXT).lower()
    for words in ("commission", "ai office", "member state", "notifying authority",
                  "market surveillance authority", "notified body", "affected person"):
        assert words in text

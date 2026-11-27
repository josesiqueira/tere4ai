"""An absent fact is never a silent no (B185, the evidence task; DEC-18, DEC-33).

The owner's words on card B185: "An absent fact is never a silent no: this
should be addressed definetely, because it looks like a silent 'no' and the
human can miss this". DEC-18's rule: an unknown fact is named among the
missing facts, and where it could change the level the answer is marked for
human review. B185's evidence run (thesis
sdd/2026-11-26-B185-domain-and-certainty/enumeration-b185-summary.json, the
invariant K-unnamed) found four kinds of fact that changed the answer once
completed and were named nowhere when absent:

1. medical_or_safety_component on the limited_risk exit while
   annex_i_covered_product is unknown (true gives undetermined);
2. the other fact of an open Article 5 point: the harm or exception fact of
   points (a), (b), (c) and (f), and point (h)'s purpose of law enforcement
   and strict-necessity carve-out, while the point's own flag is unknown;
3. the deployer fact that settles the Article 27(1) block when the other
   deployer fact is known false and only listed uses whose trigger is the
   deployer keep the block unknown;
4. the third-party conformity assessment while annex_i_covered_product is
   unknown, on the undetermined exits.

The first three are named where they could change the answer and only
there. The fourth was left unnamed by ruling R1 of B123 until the final fix
wave of B185: ruling R9 replaces R1, and the assessment is now named while the
Annex I fact is unknown, wherever answering it false (which rules the route
out, B123 R4) changes the answer: on the undetermined exits, where it gives
minimal_risk or limited_risk, and on the limited_risk exit, where it settles
the status. The invariant itself is tested over the table of area cases and a
fixed set of generated mock inputs: every absent fact whose completion (true
or false) changes the level, the status, the confidence, the duties, the
candidate, the routes, the Annex III point (annex_iii_category or
annex_iii_area_unconfirmed) or the Article 27(1) block's applicability is
named, in the envelope's missing facts or in the block's, but for the classes
_allowed below decides. Offline: the published Layer 1 dump on disk, skipped
when absent.

@implements: DEC-18
@implements: DEC-33
"""

from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path
from typing import Any

import pytest
from tests.unit.area_cases import AREA_CASES
from tests.unit.b184_cases import ARTICLE_50_TRIGGER_FLAGS, _flag_names, all_false, case

from tere4ai.mcp_server import classify as classify_module
from tere4ai.mcp_server.classify import (
    ANNEX_III_LISTED_USE_FACTS,
    ARTICLE_5_EXCULPATING_FACT,
    ARTICLE_5_POINT_BY_FLAG,
    ARTICLE_5_POINT_H_EXCULPATING,
    ARTICLE_6_1_THIRD_PARTY_UNKNOWN_FACT,
    ARTICLE_6_3_CONDITIONS,
    FACT_ENTAILMENTS,
    classify_ai_system,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"
DEPLOYER_FACTS = tuple(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"]["deployer"]["properties"]
)

DESCRIPTION = "B185 test system; the description is context only."

# The exact lines, word for word.
MEDICAL_LINE = (
    "flags.medical_or_safety_component is unknown while flags.annex_i_covered_product is unknown (Article 6(1) "
    "high-risk relevant, Annex I); a safety component whose Annex I coverage is unknown holds the classification "
    "at undetermined, so absence is not treated as false"
)
RTRB_LINE_REAL_TIME_UNKNOWN = (
    "flags.rtrb_strictly_necessary_authorised is unknown (prohibition-relevant, Article 5); answered true, it "
    "rules out point (h) while flags.real_time_remote_biometric_public and flags.law_enforcement_purpose are "
    "unknown, so absence is not treated as false"
)
RTRB_LINE_PURPOSE_UNKNOWN = (
    "flags.rtrb_strictly_necessary_authorised is unknown (prohibition-relevant, Article 5); answered true, it "
    "rules out point (h) while flags.law_enforcement_purpose is unknown, so absence is not treated as false"
)
PURPOSE_LINE = (
    "flags.law_enforcement_purpose is unknown (prohibition-relevant, Article 5); answered false, it rules out "
    "point (h) while flags.real_time_remote_biometric_public is unknown, so absence is not treated as false"
)
HARM_LINE = (
    "flags.causes_significant_harm is unknown (prohibition-relevant, Article 5); answered false, it rules out "
    "points (a) and (b) while flags.subliminal_or_manipulative and flags.exploits_vulnerabilities are unknown, "
    "so absence is not treated as false"
)
DETRIMENTAL_LINE = (
    "flags.social_score_detrimental_treatment is unknown (prohibition-relevant, Article 5); answered false, it "
    "rules out point (c) while flags.social_scoring is unknown, so absence is not treated as false"
)
EMOTION_EXCEPTION_LINE = (
    "flags.emotion_recognition_medical_or_safety is unknown (prohibition-relevant, Article 5); answered true, it "
    "rules out point (f) while flags.emotion_recognition_workplace_or_education is unknown, so absence is not "
    "treated as false"
)
DEPLOYER_BODY_LINE = (
    "deployer.body_governed_by_public_law is unknown (Article 27(1) FRIA-relevant); "
    "deployer.private_entity_providing_public_services is false, so if this is false too no unknown Annex III "
    "fact named here can make Article 27(1) apply; absence is not treated as false"
)

pytestmark = pytest.mark.skipif(not DUMP_PATH.is_file(), reason="layer1.json dump not built")


@pytest.fixture(scope="module")
def dump() -> dict:
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


def _without(flags: dict[str, Any], *names: str) -> dict[str, Any]:
    return {k: v for k, v in flags.items() if k not in names}


def _lines(envelope: dict[str, Any]) -> list[str]:
    """The envelope's missing facts and the Article 27(1) block's."""
    block = (envelope.get("answer") or {}).get("fria") or {}
    return [line for line in (*(envelope.get("missing_facts") or []), *(block.get("missing_facts") or []))
            if isinstance(line, str)]


def _named_in(lines: list[str], qualified: str) -> bool:
    """Whether the fact (flags.<name> or deployer.<name>) is named in the lines, as a whole name."""
    pattern = re.compile(re.escape(qualified) + r"(?![A-Za-z0-9_])")
    return any(pattern.search(line) for line in lines)


def _named(envelope: dict[str, Any], qualified: str) -> bool:
    return _named_in(_lines(envelope), qualified)


# Group 1: medical_or_safety_component ---------------------------------------


def test_group_1_the_evidence_example_names_the_safety_component(dump):
    env = classify_ai_system({"description": DESCRIPTION, "flags": {"interacts_with_natural_persons": True}}, dump)
    assert env["answer"]["risk_category"] == "limited_risk"
    assert env["status"] == "requires_human_review"
    assert MEDICAL_LINE in env["missing_facts"]
    # Completing it true gives undetermined, the change the line announces.
    completed = classify_ai_system(
        {"description": DESCRIPTION, "flags": {"interacts_with_natural_persons": True,
                                               "medical_or_safety_component": True}}, dump)
    assert completed["answer"]["risk_category"] == "undetermined"


def test_group_1_settled_article_5_and_annex_iii_still_names_it(dump):
    flags = _without(all_false(interacts_with_natural_persons=True), "annex_i_covered_product",
                     "third_party_conformity_assessment_required", "medical_or_safety_component")
    env = classify_ai_system(case(flags), dump)
    assert env["answer"]["risk_category"] == "limited_risk"
    assert MEDICAL_LINE in env["missing_facts"]


@pytest.mark.parametrize(
    "flags,why",
    [
        # The Annex I fact known false rules the route out.
        (_without(all_false(interacts_with_natural_persons=True), "medical_or_safety_component"), "annex_i false"),
        # The third-party assessment known false rules the route out (B123, R4).
        (_without(all_false(interacts_with_natural_persons=True), "medical_or_safety_component",
                  "annex_i_covered_product"), "third party false"),
        # A high_risk answer on a listed use: the safety component cannot change it.
        (_without(all_false(annex_iii_4a_recruitment=True), "medical_or_safety_component",
                  "annex_i_covered_product", "third_party_conformity_assessment_required"), "high_risk"),
        # The undetermined exit of rule 5: the level stays undetermined either way.
        (_without(all_false(), "medical_or_safety_component", "annex_i_covered_product",
                  "third_party_conformity_assessment_required"), "undetermined"),
    ],
)
def test_group_1_not_named_where_it_cannot_change_the_answer(dump, flags, why):
    env = classify_ai_system(case(flags), dump)
    assert not _named(env, "flags.medical_or_safety_component"), why


# Group 2: the other fact of an open Article 5 point --------------------------


ARTICLE_5_FALSE = dict.fromkeys(
    [*ARTICLE_5_POINT_BY_FLAG, "real_time_remote_biometric_public"], False
)


def test_group_2_the_evidence_example_names_the_carve_out(dump):
    flags = {**ARTICLE_5_FALSE, "real_time_remote_biometric_public": True, "annex_i_covered_product": False}
    env = classify_ai_system(case(flags), dump)
    assert env["answer"]["risk_category"] == "high_risk"
    assert env["status"] == "requires_human_review"
    assert RTRB_LINE_PURPOSE_UNKNOWN in env["missing_facts"]
    # The purpose keeps its own line of B184 (DEC-32).
    assert any(line.startswith("flags.law_enforcement_purpose is unknown while") for line in env["missing_facts"])


def test_group_2_point_h_with_the_biometric_fact_unknown(dump):
    flags = _without(all_false(annex_iii_4a_recruitment=True), "real_time_remote_biometric_public",
                     "law_enforcement_purpose", "rtrb_strictly_necessary_authorised")
    env = classify_ai_system(case(flags), dump)
    assert env["answer"]["risk_category"] == "high_risk"
    assert PURPOSE_LINE in env["missing_facts"]
    assert RTRB_LINE_REAL_TIME_UNKNOWN in env["missing_facts"]


def test_group_2_points_a_b_c_f_with_their_flags_unknown(dump):
    flags = _without(
        all_false(annex_iii_4a_recruitment=True),
        "subliminal_or_manipulative", "exploits_vulnerabilities", "causes_significant_harm",
        "social_scoring", "social_score_detrimental_treatment",
        "emotion_recognition_workplace_or_education", "emotion_recognition_medical_or_safety",
    )
    env = classify_ai_system(case(flags), dump)
    assert env["answer"]["risk_category"] == "high_risk"
    for line in (HARM_LINE, DETRIMENTAL_LINE, EMOTION_EXCEPTION_LINE):
        assert line in env["missing_facts"]


def test_group_2_the_pending_exception_keeps_its_own_line_once(dump):
    # exploits_vulnerabilities true with the harm unknown: the harm fact is
    # named by the Article 5 rule (audit D2), never a second time.
    flags = _without(all_false(exploits_vulnerabilities=True, annex_iii_4a_recruitment=True),
                     "subliminal_or_manipulative", "causes_significant_harm")
    env = classify_ai_system(case(flags), dump)
    harm = [line for line in env["missing_facts"] if line.startswith("flags.causes_significant_harm ")]
    assert len(harm) == 1
    assert "decides whether exploits_vulnerabilities is prohibited" in harm[0]


@pytest.mark.parametrize(
    "flags,fact,why",
    [
        # Both paths of the harm fact ruled out by their flags.
        (_without(all_false(), "causes_significant_harm"), "causes_significant_harm", "flags false"),
        # Point (h) ruled out by the biometric fact.
        (_without(all_false(annex_iii_4a_recruitment=True), "law_enforcement_purpose",
                  "rtrb_strictly_necessary_authorised"), "law_enforcement_purpose", "real time false"),
        (_without(all_false(annex_iii_4a_recruitment=True), "law_enforcement_purpose",
                  "rtrb_strictly_necessary_authorised"), "rtrb_strictly_necessary_authorised", "real time false"),
        # The point (d) and (g) exception facts never rule out an absent flag (DEC-18).
        (_without(all_false(annex_iii_4a_recruitment=True), "predictive_policing_profiling",
                  "supports_human_assessment_on_verifiable_facts"),
         "supports_human_assessment_on_verifiable_facts", "point (d)"),
        # The unacceptable_risk exit: nothing about another point can change it.
        (_without(all_false(facial_image_scraping=True), "subliminal_or_manipulative", "causes_significant_harm"),
         "causes_significant_harm", "unacceptable_risk"),
    ],
)
def test_group_2_not_named_where_it_cannot_change_the_answer(dump, flags, fact, why):
    env = classify_ai_system(case(flags), dump)
    assert not _named(env, f"flags.{fact}"), why


# Group 3: the deployer fact of the Article 27(1) block -----------------------


def _listed_use_unknown_limited(deployer: dict[str, Any]) -> dict[str, Any]:
    # limited_risk, every fact known but one listed use of an area whose
    # trigger is the deployer (point 8(a)).
    flags = _without(all_false(interacts_with_natural_persons=True), "annex_iii_8a_judicial")
    return case(flags, deployer=deployer)


def test_group_3_the_block_names_the_deployer_fact_that_settles_it(dump):
    env = classify_ai_system(_listed_use_unknown_limited({"private_entity_providing_public_services": False}), dump)
    block = env["answer"]["fria"]
    assert block["applicability"] == "unknown"
    assert DEPLOYER_BODY_LINE in block["missing_facts"]
    # Completing it false settles the block, the change the line announces.
    settled = classify_ai_system(_listed_use_unknown_limited(
        {"private_entity_providing_public_services": False, "body_governed_by_public_law": False}), dump)
    assert settled["answer"]["fria"]["applicability"] == "does_not_apply"
    # The block only: the envelope's missing facts do not change (DEC-14).
    assert not any(line.startswith("deployer.") for line in env["missing_facts"])


def test_group_3_on_a_point_2_system_with_5b_and_5c_known_false(dump):
    flags = _without(all_false(critical_infrastructure_safety=True), "annex_iii_8a_judicial")
    env = classify_ai_system(case(flags, deployer={"private_entity_providing_public_services": False}), dump)
    assert env["answer"]["risk_category"] == "high_risk"
    assert env["answer"]["fria"]["applicability"] == "unknown"
    assert DEPLOYER_BODY_LINE in env["answer"]["fria"]["missing_facts"]


@pytest.mark.parametrize(
    "deployer,flags_absent,why",
    [
        # Both deployer facts unknown: neither alone settles the block.
        ({}, ("annex_iii_8a_judicial",), "both unknown"),
        # The other deployer fact true: the deployer already triggers.
        ({"private_entity_providing_public_services": True}, ("annex_iii_8a_judicial",), "other true"),
        # A point 5(b) fact unknown triggers for any deployer.
        ({"private_entity_providing_public_services": False}, ("creditworthiness_evaluation",), "5(b) unknown"),
    ],
)
def test_group_3_not_named_where_it_cannot_settle_the_block(dump, deployer, flags_absent, why):
    flags = _without(all_false(interacts_with_natural_persons=True), *flags_absent)
    env = classify_ai_system(case(flags, deployer=deployer), dump)
    lines = env["answer"]["fria"]["missing_facts"]
    assert not any(line.startswith("deployer.body_governed_by_public_law") for line in lines), why


# Group 4: the third-party conformity assessment (ruling R9) ---------------


SIX_1_ABSENT = ("annex_i_covered_product", "third_party_conformity_assessment_required")


@pytest.mark.parametrize(
    "flags,completed_level,completed_status,why",
    [
        # The evidence run's rows: every Article 5 and Annex III fact known,
        # the two Article 6(1) facts absent (the lift case of B123).
        (_without(all_false(), *SIX_1_ABSENT), "minimal_risk", "not_applicable", "last undetermined exit"),
        # The exit a safety component gives.
        (_without(all_false(medical_or_safety_component=True), *SIX_1_ABSENT), "minimal_risk", "not_applicable",
         "safety component"),
        (_without(all_false(medical_or_safety_component=True, interacts_with_natural_persons=True),
                  *SIX_1_ABSENT), "limited_risk", "potentially_applicable", "safety component, Article 50"),
        # The limited_risk exit: the open route is the only cause of review.
        (_without(all_false(interacts_with_natural_persons=True), *SIX_1_ABSENT), "limited_risk",
         "potentially_applicable", "limited_risk"),
    ],
)
def test_group_4_ruling_r9_names_the_third_party_fact_while_annex_i_is_unknown(
    dump, flags, completed_level, completed_status, why
):
    env = classify_ai_system(case(flags), dump)
    assert env["missing_facts"].count(ARTICLE_6_1_THIRD_PARTY_UNKNOWN_FACT) == 1, why
    assert [m for m in env["missing_facts"] if "flags.third_party_conformity_assessment_required" in m] == [
        ARTICLE_6_1_THIRD_PARTY_UNKNOWN_FACT], why
    assert any(line.startswith("flags.annex_i_covered_product is unknown") for line in env["missing_facts"]), why
    assert env["status"] == "requires_human_review", why
    # Answered false it changes the answer, the change the line announces.
    done = classify_ai_system(case({**flags, "third_party_conformity_assessment_required": False}), dump)
    assert (done["answer"]["risk_category"], done["status"]) == (completed_level, completed_status), why


@pytest.mark.parametrize(
    "flags,why",
    [
        # Another unknown fact keeps the last undetermined exit undetermined.
        (_without(all_false(), *SIX_1_ABSENT, "annex_iii_4a_recruitment"), "an Annex III fact unknown too"),
        (_without(all_false(), *SIX_1_ABSENT, "facial_image_scraping"), "an Article 5 fact unknown too"),
        # On the limited_risk exit another cause keeps the status.
        (_without(all_false(interacts_with_natural_persons=True), *SIX_1_ABSENT, "annex_iii_4a_recruitment"),
         "limited_risk with an unknown listed use"),
        (_without(all_false(interacts_with_natural_persons=True), *SIX_1_ABSENT, "facial_image_scraping"),
         "limited_risk with an unknown Article 5 fact"),
        # A high_risk answer on a listed use, and the unacceptable_risk exit.
        (_without(all_false(annex_iii_4a_recruitment=True), *SIX_1_ABSENT), "high_risk"),
        (_without(all_false(facial_image_scraping=True), *SIX_1_ABSENT), "unacceptable_risk"),
    ],
)
def test_group_4_not_named_where_it_cannot_change_the_answer(dump, flags, why):
    env = classify_ai_system(case(flags), dump)
    assert not _named(env, "flags.third_party_conformity_assessment_required"), why


def test_group_4_the_area_alone_exit_does_not_name_it(dump):
    env = classify_ai_system(case(_without(all_false(), *SIX_1_ABSENT, "annex_iii_3a_admission"),
                                  domain="education"), dump)
    assert env["answer"]["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-3"
    assert not _named(env, "flags.third_party_conformity_assessment_required")


def test_group_4_never_twice_once_the_product_is_covered(dump):
    # With the Annex I fact true the B123 line names the assessment, alone.
    env = classify_ai_system(case(_without(all_false(annex_i_covered_product=True),
                                           "third_party_conformity_assessment_required")), dump)
    lines = [m for m in env["missing_facts"] if "flags.third_party_conformity_assessment_required" in m]
    assert len(lines) == 1 and lines[0] != ARTICLE_6_1_THIRD_PARTY_UNKNOWN_FACT


# The invariant over the table cases and a generated set ----------------------

GROUPS = {
    "article_5": (
        *ARTICLE_5_POINT_BY_FLAG, "real_time_remote_biometric_public", "law_enforcement_purpose",
        *dict.fromkeys(fact for fact, _value, _desc in ARTICLE_5_EXCULPATING_FACT.values()),
        ARTICLE_5_POINT_H_EXCULPATING[0],
    ),
    "annex_iii": ANNEX_III_LISTED_USE_FACTS,
    "article_6_1": ("annex_i_covered_product", "third_party_conformity_assessment_required",
                    "annex_i_section_b_legislation", "medical_or_safety_component"),
    "article_50": ARTICLE_50_TRIGGER_FLAGS,
    "article_6_3": (*(flag for flag, _p, _l in ARTICLE_6_3_CONDITIONS), "profiling_of_natural_persons"),
}
# The facts of one Article 5 point: its flag and its other fact, and point (h)'s three.
ARTICLE_5_POINTS = (
    *((flag, fact) for flag, (fact, _value, _desc) in ARTICLE_5_EXCULPATING_FACT.items()),
    ("real_time_remote_biometric_public", "law_enforcement_purpose", ARTICLE_5_POINT_H_EXCULPATING[0]),
    ("real_time_remote_biometric_public", ARTICLE_5_POINT_H_EXCULPATING[0]),
    ("law_enforcement_purpose", ARTICLE_5_POINT_H_EXCULPATING[0]),
)
DOMAINS = ("biometrics", "critical_infrastructure", "education", "employment", "essential_services",
           "law_enforcement", "migration", "justice", "none_of_these_areas", None)
GENERATED_COUNT = 1500


def generated_inputs(count: int = GENERATED_COUNT, seed: int = 15) -> list[dict[str, Any]]:
    """A fixed set of mock inputs: every flag false, then a few true, a few
    absent and, for some inputs, a whole group of facts absent (the facts of
    Article 5, of Annex III, of Article 6(1), of Article 50 or of Article
    6(3)), the facts of one Article 5 point absent, or a safety component
    with the two Article 6(1) facts absent, with the domain and the deployer
    drawn too, from a seeded generator, so the same inputs come back on every
    run."""
    rng = random.Random(seed)
    names = _flag_names()
    inputs = []
    for _ in range(count):
        flags = all_false()
        for fact in rng.sample(names, rng.randint(0, 3)):
            flags[fact] = True
        if rng.random() < 0.4:
            flags[rng.choice(ARTICLE_50_TRIGGER_FLAGS)] = True
        for group in rng.sample(sorted(GROUPS), rng.choice((0, 1, 1, 2, 2))):
            for fact in GROUPS[group]:
                if rng.random() < 0.8:
                    flags[fact] = None
        for fact in rng.sample(names, rng.randint(0, 5)):
            flags[fact] = None
        if rng.random() < 0.3:
            for fact in rng.choice(ARTICLE_5_POINTS):
                flags[fact] = None
        if rng.random() < 0.1:
            flags.update(medical_or_safety_component=True, annex_i_covered_product=None,
                         third_party_conformity_assessment_required=None)
        flags = {k: v for k, v in flags.items() if v is not None}
        deployer = {
            fact: value
            for fact in DEPLOYER_FACTS
            if (value := rng.choice((True, False, False, None))) is not None
        }
        inputs.append(case(flags, domain=rng.choice(DOMAINS), deployer=deployer))
    return inputs


def _view(env: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    a = env.get("answer") or {}
    flags = features.get("flags") or {}
    return {
        "lines": _lines(env),
        # The wider facts read true from unknown by a definition of the Act.
        "entailed": {wider for narrower, wider, _p in FACT_ENTAILMENTS
                     if flags.get(narrower) is True and wider not in flags},
        "level": a.get("risk_category"),
        "status": env.get("status"),
        "duties": tuple(a.get("transparency_duties") or ()),
        "candidate": a.get("article_6_3_exception_candidate"),
        "routes": (tuple(a.get("high_risk_routes") or ()), a.get("annex_i_section")),
        "category": a.get("annex_iii_category"),
        "area": a.get("annex_iii_area_unconfirmed"),
        "confidence": env.get("confidence"),
        "fria": ((a.get("fria") or {}).get("applicability")),
        "conflicts": len(a.get("fact_conflicts") or ()) + len(a.get("area_conflicts") or ()),
    }


def _completions(features: dict[str, Any]):
    flags = features.get("flags") or {}
    for name in _flag_names():
        if name not in flags:
            for value in (True, False):
                new = copy.deepcopy(features)
                new["flags"][name] = value
                yield f"flags.{name}", value, new
    deployer = features.get("deployer") or {}
    for name in DEPLOYER_FACTS:
        if name not in deployer:
            for value in (True, False):
                new = copy.deepcopy(features)
                new.setdefault("deployer", {})[name] = value
                yield f"deployer.{name}", value, new
    # The domain is not a yes-or-no fact: an absent domain is read as no area
    # given, and the area reading (DEC-33) has its own tests; the evidence
    # run's K-unnamed skips it the same way. autonomy decides nothing since
    # B184 (D-G91 (7), ruling R5), so it is not completed here.


def _allowed(name: str, base: dict[str, Any], done: dict[str, Any], features: dict[str, Any]) -> str | None:
    """The classes the spec decides, each with its reason; None when the row
    is not allowed."""
    fact = name.removeprefix("flags.")
    creates_conflict = name.startswith("flags.") and (
        fact in ENTAILMENT_FACTS
        or (fact in ANNEX_III_LISTED_USE_FACTS and features.get("domain") == "none_of_these_areas")
    )
    if done["conflicts"] > base["conflicts"] and creates_conflict:
        # The completion itself contradicts a definition of the Act or the
        # domain (fact_conflicts, area_conflicts; DEC-32, DEC-33 ruling P26):
        # a completed fact that is one side of a FACT_ENTAILMENTS pair, or a
        # listed use answered while the domain is none_of_these_areas. The
        # change comes from the conflict the completion creates, which the
        # completed answer names, not from a fact the base answer left unnamed.
        return "a conflict the completion itself creates"
    if name.startswith("flags.") and done["entailed"] - base["entailed"]:
        # The completion answers a wider fact by a definition of the Act
        # (FACT_ENTAILMENTS; DEC-32, ruling R6): emotion recognition at the
        # workplace is emotion recognition (Article 3(39)). The change is the
        # wider fact's, and the wider fact, absent, is named itself.
        wider = done["entailed"] - base["entailed"]
        if all(_named_in(base["lines"], f"flags.{w}") for w in wider):
            return "a wider fact the completion answers by a definition of the Act (R6)"
    if name == "flags.annex_i_section_b_legislation" and "article_6_2" in base["routes"][0]:
        # Ruling R44: with a listed use true Chapter III is served whatever the
        # section, so the section fact is not named beside it; completing it
        # true only moves the answer to the Annex III route of a Section B
        # product (R26), which serves the same requirements.
        return "the Annex I section beside a true listed use (R44)"
    return None


COMPARED = ("level", "status", "confidence", "duties", "candidate", "routes", "category", "area", "fria")
# The facts of the pairs of FACT_ENTAILMENTS, either side.
ENTAILMENT_FACTS = frozenset(fact for narrower, wider, _p in FACT_ENTAILMENTS for fact in (narrower, wider))


def _check(features: dict[str, Any], dump: dict[str, Any], unnamed: list[str]) -> None:
    env = classify_ai_system(copy.deepcopy(features), dump)
    if env["status"] == "rejected_as_unsupported":
        return
    base = _view(env, features)
    for name, value, new in _completions(features):
        done = _view(classify_ai_system(new, dump), new)
        changed = [k for k in COMPARED if done[k] != base[k]]
        if not changed or _named(env, name) or _allowed(name, base, done, features):
            continue
        unnamed.append(f"{name}={value} changes {'+'.join(changed)} on {base['level']}/{base['status']}: "
                       f"{json.dumps(features, sort_keys=True)}")


@pytest.fixture()
def fast_classify():
    """The node index built once and the dates left out, as the evidence
    harness does for its completion calls: both are data helpers whose
    output no rule reads (classify.py), so the fields compared are those of
    the unmodified function."""
    index: dict[int, Any] = {}
    real_index = classify_module._node_index

    def memo(dump_in):
        if id(dump_in) not in index:
            index[id(dump_in)] = real_index(dump_in)
        return index[id(dump_in)]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(classify_module, "_node_index", memo)
        patch.setattr(classify_module, "dates_for", lambda cited, dump_in, route: [])
        yield


def test_every_absent_fact_that_changes_the_answer_is_named_on_the_table_cases(dump, fast_classify):
    unnamed: list[str] = []
    for case_id, c in AREA_CASES.items():
        _check(c["features"], dump, unnamed)
    assert not unnamed, "\n".join(unnamed[:20])


def test_every_absent_fact_that_changes_the_answer_is_named_on_the_generated_set(dump, fast_classify):
    unnamed: list[str] = []
    for features in generated_inputs():
        _check(features, dump, unnamed)
    assert not unnamed, f"{len(unnamed)} rows; first:\n" + "\n".join(unnamed[:20])

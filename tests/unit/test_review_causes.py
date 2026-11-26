"""The causes of review in one place (B185 Task 6, spec G D-G92 (8), (9), (v), DEC-33).

Every fixed sentence that gives a reason for review names the causes that
hold, all of them, in the order of D-G92 (8); the status is
requires_human_review exactly when a cause holds or the level is
undetermined (rulings P11, P12, P32, R5); the Article 27(1) block never
counts a point that rests on the area as a confirmed area and names every
cause, the area first (D-G92 (5), (v), the rules added after the plan's
review, ruling P13); a refused input carries no block (D-G92 (9), P14). B185
Task 7: the applicable requirements read the causes from the answer itself,
so an envelope and its bare answer read alike, and their note names the
causes too (D-G92 (8), (i)); the causes are also recomputed in this file from
the answer's fields and the input facts by the spec's words, without
review_causes, and every place that prints them must agree. The cases are the
table of area cases (tests/unit/area_cases.py) and a fixed set of 6,000
generated mock inputs. Offline: the published Layer 1 and norms dumps on disk,
skipped when absent.

@implements: DEC-33
"""

from __future__ import annotations

import inspect
import json
import random
from pathlib import Path
from typing import Any

import pytest
from tests.unit.area_cases import (
    AREA_CASES,
    DEPLOYER,
    P61,
    _features,
)
from tests.unit.b184_cases import _flag_names, all_false, case

from tere4ai.mcp_server import fria
from tere4ai.mcp_server import requirements as requirements_module
from tere4ai.mcp_server.classify import (
    ANNEX_I_SECTION_UNKNOWN_FACT,
    ANNEX_III_LISTED_USE_FACTS,
    ARTICLE_5_POINT_H,
    ARTICLE_6_3_CONDITIONS,
    PROHIBITION_AREA_CONFLICT_CLAUSE,
    PROHIBITION_FACT_CONFLICT_CLAUSE,
    apply_entailments,
    article_6_3_candidate,
    classify_ai_system,
)
from tere4ai.mcp_server.fria import (
    FRIA_AREA_ALONE_REASON,
    FRIA_AREA_BESIDE_ARTICLE_6_1_REASON,
    FRIA_AREA_BESIDE_UNKNOWN_USE_LINE,
    FRIA_AREA_UNKNOWN_USE_LINE,
    FRIA_OTHER_CAUSES_TEMPLATE,
    FRIA_UNSETTLED_TEMPLATE,
)
from tere4ai.mcp_server.requirements import (
    MINIMAL_MESSAGE,
    PROHIBITED_MESSAGE,
    PROHIBITED_MESSAGE_POINT_H,
    PROVISIONAL_NOTE_TEMPLATE,
    SECTION_B_ANNEX_III_UNKNOWN_MESSAGE,
    SECTION_B_DEROGATION_NOTE,
    SECTION_B_LISTED_USE_UNKNOWN_FACT,
    SECTION_B_MESSAGE,
    UNSETTLED_FALLBACK_FACT,
    get_applicable_requirements,
)
from tere4ai.mcp_server.review_causes import (
    FACT_CONFLICT_REASON,
    REVIEW_CAUSE_REASONS,
    REVIEW_CAUSES,
    STATUS_LINE_PREFIX,
    review_causes,
    review_reason,
    review_status_line,
)

ROOT = Path(__file__).resolve().parents[2]
DUMP_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"

ARTICLE_6_4 = "eu-ai-act:article-6:paragraph-4"
CANDIDACY_SENTENCE = (
    "the classification flags Article 6(3) derogation candidacy; FRIA applicability stays unknown until a human "
    "reviewer settles whether the system remains high-risk under Article 6(2)"
)
# Words that say the classification itself is not settled, or that the level
# could change; none may stand on an answer whose status is not review.
UNSETTLED_WORDS = (
    "the classification is also not settled",
    "high-risk but not settled",
    "flagged for human review",
    "could change the outcome",
    "could change the level",
    "a change to Unacceptable risk",
)

DOMAINS = ("biometrics", "critical_infrastructure", "education", "employment", "essential_services",
           "law_enforcement", "migration", "justice", "none_of_these_areas", None)
ARTICLE_6_3_FACTS = ("narrow_procedural_task", "improves_previous_human_activity",
                     "detects_patterns_without_replacing_human_assessment", "preparatory_task",
                     "profiling_of_natural_persons")
GENERATED_COUNT = 6000


def generated_inputs(count: int = GENERATED_COUNT, seed: int = 185) -> list[dict[str, Any]]:
    """A fixed set of mock inputs: every flag false, then a few true and a few
    absent, the Article 6(1) facts, the Annex I section, the Article 6(3)
    facts, the domain and the deployer drawn from a seeded generator, so the
    same inputs come back on every run."""
    rng = random.Random(seed)
    names = _flag_names()
    inputs = []
    for _ in range(count):
        flags = all_false()
        for fact in rng.sample(names, rng.randint(0, 4)):
            flags[fact] = True
        if rng.random() < 0.3:
            flags["annex_i_covered_product"] = True
            flags["third_party_conformity_assessment_required"] = rng.choice((True, True, None))
            flags["annex_i_section_b_legislation"] = rng.choice((True, False, None))
        if rng.random() < 0.4:
            flags[rng.choice(ARTICLE_6_3_FACTS)] = rng.choice((True, None))
        for fact in rng.sample(names, rng.randint(0, 4)):
            flags[fact] = None
        flags = {k: v for k, v in flags.items() if v is not None}
        deployer = {
            fact: value
            for fact in ("body_governed_by_public_law", "private_entity_providing_public_services")
            if (value := rng.choice((True, False, False, None))) is not None
        }
        inputs.append(case(flags, domain=rng.choice(DOMAINS), deployer=deployer))
    return inputs


@pytest.fixture(scope="module")
def dump() -> dict:
    if not DUMP_PATH.is_file():
        pytest.skip("layer1.json dump not built")
    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def answered(dump) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """(name, features, envelope) for every table case and generated input."""
    named = [(cid, c["features"]) for cid, c in AREA_CASES.items()]
    named += [(f"G{i}", features) for i, features in enumerate(generated_inputs())]
    return [(name, features, classify_ai_system(features, dump)) for name, features in named]


@pytest.fixture(scope="module")
def norms() -> dict:
    if not NORMS_PATH.is_file():
        pytest.skip("norms_core.json not built")
    return json.loads(NORMS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def served(answered, dump, norms) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """name -> (the requirements from the envelope, the requirements from the
    bare answer), for every table case and generated input (B185 Task 7). The
    application dates of a provision depend only on the provision, the route
    and the dump, so they are computed once per pair here to keep the run
    short; the function that computes them is the one the tool calls."""
    computed: dict[tuple[str, str | None], Any] = {}
    original = requirements_module.provision_dates

    def dates_once(node_id: str, dump_in: dict, route: str | None) -> Any:
        if (node_id, route) not in computed:
            computed[(node_id, route)] = original(node_id, dump_in, route)
        return computed[(node_id, route)]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(requirements_module, "provision_dates", dates_once)
        return {
            name: (get_applicable_requirements(env, norms, dump),
                   get_applicable_requirements(env["answer"], norms, dump))
            for name, _features_in, env in answered
        }


def _status_lines(answer: dict[str, Any]) -> list[str]:
    return [line for line in answer["rationale"] if line.startswith(STATUS_LINE_PREFIX)]


# The fixed words of the module (the brief of Task 6, word for word) ---------

def test_the_causes_and_their_reasons_are_the_spec_order_word_for_word():
    assert REVIEW_CAUSES == ("article_5_unknown", "fact_conflict", "area_conflict", "area_alone",
                             "article_6_3_candidate", "article_6_1_open", "listed_use_unknown")
    assert list(REVIEW_CAUSE_REASONS) == list(REVIEW_CAUSES)
    assert REVIEW_CAUSE_REASONS == {
        "article_5_unknown": "an unknown Article 5 fact could change the level to Unacceptable risk",
        "fact_conflict": FACT_CONFLICT_REASON,
        "area_conflict": "a listed use of Annex III is true while the domain says none of these areas "
                         "(area_conflicts), so one of the two answers is wrong",
        "area_alone": "the level rests on the area alone: no listed use of the area is confirmed "
                      "(annex_iii_area_unconfirmed)",
        "article_6_3_candidate": "an Article 6(3) derogation candidacy is pending human legal review, and a "
                                 "confirmed derogation takes the system out of Article 6(2)",
        "article_6_1_open": "an unknown Article 6(1) fact could make the system high-risk",
        "listed_use_unknown": "an unknown Annex III listed use could put the system on the Annex III route",
    }
    assert FACT_CONFLICT_REASON == (
        "answers contradict a definition of the Act (fact_conflicts) and one answer of each pair is wrong, so "
        "the classification could change once they are corrected")
    assert review_reason(["listed_use_unknown", "article_5_unknown"]) == (
        REVIEW_CAUSE_REASONS["article_5_unknown"] + "; " + REVIEW_CAUSE_REASONS["listed_use_unknown"])


def test_the_status_lines_word_for_word():
    prefix = "status lowered to requires_human_review: "
    limited = {"risk_category": "limited_risk"}
    section_b = {"risk_category": "high_risk", "annex_i_section": "B"}
    assert review_status_line("article_5_unknown", limited) == (
        prefix + "unknown prohibition-relevant flags could change the outcome to Unacceptable risk")
    assert review_status_line("fact_conflict", limited) == (
        prefix + "answers contradict a definition of the Act: see fact_conflicts")
    assert review_status_line("area_conflict", limited) == (
        prefix + "a listed use is true while domain is none_of_these_areas: see area_conflicts")
    assert review_status_line("area_alone", section_b) == (
        prefix + "the level rests on the area alone; no listed use of the area is confirmed")
    assert review_status_line("article_6_3_candidate", section_b) == (
        prefix + "an Article 6(3) derogation candidacy is flagged for human legal review")
    assert review_status_line("article_6_1_open", limited) == (
        prefix + "unknown Article 6(1) facts could add high-risk obligations on top of the Article 50 "
        "transparency duty")
    assert review_status_line("listed_use_unknown", limited) == (
        prefix + "unknown Annex III high-risk flags could add high-risk obligations on top of the Article 50 "
        "transparency duty")
    assert review_status_line("listed_use_unknown", section_b) == (
        prefix + "unknown Annex III facts could put this Section B product on the Annex III route, which brings "
        "the Chapter III requirements and the Article 50 duties Article 2(2) does not")


def test_the_block_sentences_word_for_word():
    assert FRIA_AREA_ALONE_REASON == (
        "the level rests on the area alone: domain '{domain}' places the system in Annex III point {number}, and "
        "no listed use of the point is confirmed, so whether the system is a high-risk AI system referred to in "
        "Article 6(2) is not settled and FRIA applicability stays unknown")
    assert FRIA_AREA_BESIDE_ARTICLE_6_1_REASON == (
        "the system is high-risk via the Article 6(1) embedded-product route; domain '{domain}' places it in "
        "Annex III point {number}, but no listed use of the point is confirmed, so whether it is also a "
        "high-risk AI system referred to in Article 6(2) is not settled and FRIA applicability stays unknown")
    assert FRIA_AREA_UNKNOWN_USE_LINE == (
        "flags.{fact} is unknown (a listed use of Annex III point {number}); the level rests on the area alone "
        "until a listed use of the point is answered")
    assert FRIA_AREA_BESIDE_UNKNOWN_USE_LINE == (
        "flags.{fact} is unknown (a listed use of Annex III point {number}); whether the system is also one "
        "referred to in Article 6(2) is open until a listed use of the point is answered")
    assert FRIA_OTHER_CAUSES_TEMPLATE == "the classification is also not settled for these reasons: {reasons}"
    assert FRIA_UNSETTLED_TEMPLATE == (
        "the risk classification is high-risk but not settled: {reasons}; FRIA applicability stays unknown until "
        "the classification is confirmed")


def test_the_block_has_no_second_decider_of_the_causes():
    # Fix round 1: review_causes.py is the one decider; the block takes the
    # causes and reads no mark of its own (at daadd5c fria.py kept
    # _legacy_causes and the arguments it read).
    assert not hasattr(fria, "_legacy_causes")
    params = set(inspect.signature(fria.assess_fria_applicability).parameters)
    assert params.isdisjoint({"classification_unsettled", "fact_conflicts", "unacceptable_risk", "area_conflicts"})
    assert "review_causes" in params


def test_the_rules_of_each_cause_read_the_answer_fields():
    high = {"risk_category": "high_risk", "unacceptable_risk": False, "fact_conflicts": [], "area_conflicts": [],
            "annex_iii_area_unconfirmed": None, "high_risk_routes": ["article_6_2"],
            "article_6_3_exception_candidate": False, "annex_i_section": None}
    assert review_causes(high) == []
    assert review_causes({**high, "unacceptable_risk": None}) == ["article_5_unknown"]
    assert review_causes({**high, "risk_category": "minimal_risk", "unacceptable_risk": None}) == []
    assert review_causes({**high, "risk_category": "undetermined", "fact_conflicts": [{}]}) == []
    assert review_causes({**high, "risk_category": "unacceptable_risk", "unacceptable_risk": True,
                          "fact_conflicts": [{}], "area_conflicts": [{}]}) == ["fact_conflict", "area_conflict"]
    area = {**high, "annex_iii_area_unconfirmed": "eu-ai-act:annex-iii:point-3"}
    assert review_causes({**area, "high_risk_routes": []}) == ["area_alone"]
    assert review_causes({**area, "high_risk_routes": ["article_6_1"]}) == []
    annex_iii_line_b = "flags.annex_iii_3a_admission is unknown (Annex III high-risk relevant, Article 6(2)); x"
    candidate = {**high, "article_6_3_exception_candidate": True}
    assert review_causes(candidate) == ["article_6_3_candidate"]
    both = {**candidate, "high_risk_routes": ["article_6_1", "article_6_2"]}
    assert review_causes({**both, "annex_i_section": "A"}) == []
    assert review_causes({**both, "annex_i_section": "A"}, for_fria=True) == ["article_6_3_candidate"]
    assert review_causes({**both, "annex_i_section": "B"}) == ["article_6_3_candidate"]
    # Ruling R5: with a listed use that is true an unknown section could be B,
    # where the derogation changes what is served; with only a point that
    # rests on the area a Section B product is served as Section B whatever
    # the derogation, so the unknown section adds no cause there.
    assert review_causes({**both, "annex_i_section": "unknown"}) == ["article_6_3_candidate"]
    beside_area = {**candidate, "high_risk_routes": ["article_6_1"],
                   "annex_iii_area_unconfirmed": "eu-ai-act:annex-iii:point-3"}
    assert review_causes({**beside_area, "annex_i_section": "unknown"}) == []
    assert review_causes({**beside_area, "annex_i_section": "unknown"}, for_fria=True) == ["article_6_3_candidate"]
    # Fix round 1 (the coordinator's ruling): with only a point that rests on
    # the area, a known Section B adds no cause either; the unknown listed use
    # keeps such an answer under review.
    assert review_causes({**beside_area, "annex_i_section": "B"}) == []
    assert review_causes({**beside_area, "annex_i_section": "B"}, [annex_iii_line_b]) == ["listed_use_unknown"]
    assert review_causes({**beside_area, "annex_i_section": "A"}) == []
    assert review_causes({**high, "article_6_3_exception_candidate": None}) == []
    limited = {**high, "risk_category": "limited_risk", "high_risk_routes": []}
    article_6_1_line = "flags.annex_i_covered_product is unknown (Article 6(1) high-risk relevant, Annex I); x"
    annex_iii_line = "flags.annex_iii_3a_admission is unknown (Annex III high-risk relevant, Article 6(2)); x"
    assert review_causes(limited, [article_6_1_line, annex_iii_line]) == ["article_6_1_open", "listed_use_unknown"]
    assert review_causes(limited) == []
    section_b = {**high, "annex_i_section": "B", "high_risk_routes": ["article_6_1"]}
    assert review_causes(section_b, [annex_iii_line]) == ["listed_use_unknown"]
    assert review_causes({**section_b, "annex_i_section": "A"}, [annex_iii_line]) == []


# The table of cases and the findings ---------------------------------------

def test_causes_follow_the_order_of_d_g92(dump):  # C18
    env = classify_ai_system(AREA_CASES["C18"]["features"], dump)
    assert _status_lines(env["answer"]) == [review_status_line("article_5_unknown", env["answer"]),
                                            review_status_line("area_alone", env["answer"])]


def test_block_names_the_area_first_then_every_other_cause(dump):  # C18 (I5)
    fria = classify_ai_system(AREA_CASES["C18"]["features"], dump)["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert fria["rationale"] == [
        FRIA_AREA_ALONE_REASON.format(domain="education", number=3),
        FRIA_OTHER_CAUSES_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["article_5_unknown"])]
    assert FRIA_AREA_UNKNOWN_USE_LINE.format(fact="annex_iii_3a_admission", number=3) in fria["missing_facts"]


@pytest.mark.parametrize("cid", ["C5", "C20"])
def test_an_area_conflict_alone_is_named_and_never_unacceptable_risk(dump, cid):
    # Task 3's review: at 12eec31 the block printed the generic sentence that
    # names a change to Unacceptable risk although unacceptable_risk is false.
    env = classify_ai_system(AREA_CASES[cid]["features"], dump)
    a = env["answer"]
    assert a["unacceptable_risk"] is False
    texts = [*a["rationale"], *env["legal_status_notes"], *a["fria"]["rationale"], *a["fria"]["missing_facts"]]
    assert not any("Unacceptable risk" in text for text in texts)
    assert _status_lines(a) == [review_status_line("area_conflict", a)]
    assert a["fria"]["rationale"] == [
        FRIA_UNSETTLED_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["area_conflict"])]


def test_finding_16_both_routes_block_follows_the_candidate_field(dump):  # C16
    a = classify_ai_system(AREA_CASES["C16"]["features"], dump)["answer"]
    assert a["article_6_3_exception_candidate"] is True
    assert a["fria"]["rationale"][0].startswith("the classification flags Article 6(3) derogation candidacy")
    assert not any("not settled" in line for line in a["fria"]["rationale"])


def test_finding_3_the_block_never_counts_an_area_as_confirmed(dump):
    # domain education, annex_iii_3a_admission absent, deployer a body
    # governed by public law: at 12eec31 the block answered "applies".
    features = _features(absent=("annex_iii_3a_admission",))
    features["deployer"] = {"body_governed_by_public_law": True, "private_entity_providing_public_services": False}
    fria = classify_ai_system(features, dump)["answer"]["fria"]
    assert fria["applicability"] == "unknown"
    assert fria["rationale"] == [FRIA_AREA_ALONE_REASON.format(domain="education", number=3)]
    assert "eu-ai-act:annex-iii:point-3" not in fria["basis_nodes"]


def test_area_alone_on_point_2_is_unknown_with_a_true_sentence(dump):  # I4
    env = classify_ai_system(_features(absent=("critical_infrastructure_safety",),
                                       domain="critical_infrastructure"), dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["high_risk_routes"] == []
    assert a["annex_iii_area_unconfirmed"] == "eu-ai-act:annex-iii:point-2"
    assert a["fria"]["applicability"] == "unknown"
    assert a["fria"]["rationale"] == [FRIA_AREA_ALONE_REASON.format(domain="critical_infrastructure", number=2)]
    assert a["fria"]["missing_facts"] == [
        FRIA_AREA_UNKNOWN_USE_LINE.format(fact="critical_infrastructure_safety", number=2)]
    assert not any("which Article 27(1) covers" in line for line in a["fria"]["missing_facts"])


def test_area_beside_article_6_1_point_2_reads_as_that_route(dump):  # C13
    fria = classify_ai_system(AREA_CASES["C13"]["features"], dump)["answer"]["fria"]
    assert fria["applicability"] == "does_not_apply"
    assert fria["rationale"][0].startswith("the system is high-risk via the Article 6(1) embedded-product route only")


def test_area_beside_article_6_1_other_point_is_unknown(dump):  # C10, C11
    c10 = classify_ai_system(AREA_CASES["C10"]["features"], dump)
    beside = FRIA_AREA_BESIDE_ARTICLE_6_1_REASON.format(domain="education", number=3)
    assert c10["status"] == "potentially_applicable"
    assert c10["answer"]["fria"]["applicability"] == "unknown"
    assert c10["answer"]["fria"]["rationale"] == [beside]
    assert c10["answer"]["fria"]["missing_facts"] == [
        FRIA_AREA_BESIDE_UNKNOWN_USE_LINE.format(fact="annex_iii_3a_admission", number=3)]
    c11 = classify_ai_system(AREA_CASES["C11"]["features"], dump)["answer"]["fria"]
    assert c11["rationale"] == [
        beside, FRIA_OTHER_CAUSES_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["listed_use_unknown"])]


@pytest.mark.parametrize("section", [False, True])
def test_a_candidate_beside_article_6_1_with_only_an_area_gets_the_area_sentence(dump, section):
    # Task 4's review: at 12eec31 the block said "until a human reviewer
    # settles whether the system remains high-risk under Article 6(2)" although
    # the system is not on Article 6(2) there.
    features = _features(true=("narrow_procedural_task",), absent=("annex_iii_3a_admission",), **P61,
                         annex_i_section_b_legislation=section)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["article_6_3_exception_candidate"] is True and a["high_risk_routes"] == ["article_6_1"]
    beside = FRIA_AREA_BESIDE_ARTICLE_6_1_REASON.format(domain="education", number=3)
    assert not any("remains high-risk under Article 6(2)" in line for line in a["fria"]["rationale"])
    if section:
        # Section B with only a point that rests on the area: the product is
        # served as Section B whatever the derogation, so the candidate is no
        # cause (fix round 1); the unknown listed use keeps the answer under
        # review and is the cause named after the area.
        assert env["status"] == "requires_human_review"
        assert review_causes(a, env["missing_facts"]) == ["listed_use_unknown"]
        assert a["fria"]["rationale"] == [beside, FRIA_OTHER_CAUSES_TEMPLATE.format(
            reasons=REVIEW_CAUSE_REASONS["listed_use_unknown"])]
    else:
        # Section A: the candidate is no cause, and the answer is settled.
        assert env["status"] == "potentially_applicable"
        assert a["fria"]["rationale"] == [beside]


@pytest.mark.parametrize("cid", ["C10", "C11", "C12"])
def test_beside_article_6_1_the_unknown_use_line_never_says_the_level_rests_on_the_area(dump, cid):
    # Fix round 1: at daadd5c the block's missing line ended "the level rests
    # on the area alone until a listed use of the point is answered" although
    # the level rests on the Article 6(1) route there.
    fria = classify_ai_system(AREA_CASES[cid]["features"], dump)["answer"]["fria"]
    assert fria["missing_facts"] == [FRIA_AREA_BESIDE_UNKNOWN_USE_LINE.format(fact="annex_iii_3a_admission", number=3)]
    assert not any("rests on the area alone" in line for line in [*fria["rationale"], *fria["missing_facts"]])


def test_on_the_area_alone_the_unknown_use_line_says_so(dump):  # C1
    fria = classify_ai_system(AREA_CASES["C1"]["features"], dump)["answer"]["fria"]
    assert fria["missing_facts"] == [FRIA_AREA_UNKNOWN_USE_LINE.format(fact="annex_iii_3a_admission", number=3)]


def test_conflict_beside_candidate_names_both(dump):
    # 4(a) and the Article 6(3) point (a) true, and emotion_recognition answered
    # false while emotion_recognition_workplace_or_education is true (Article
    # 3(39)); the medical or safety exception rules out Article 5(1)(f).
    features = case(all_false(annex_iii_4a_recruitment=True, narrow_procedural_task=True,
                              emotion_recognition_workplace_or_education=True,
                              emotion_recognition_medical_or_safety=True),
                    deployer=dict(DEPLOYER))
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk" and a["fact_conflicts"] and a["article_6_3_exception_candidate"] is True
    assert _status_lines(a) == [review_status_line("fact_conflict", a),
                                review_status_line("article_6_3_candidate", a)]
    assert a["fria"]["rationale"] == [
        CANDIDACY_SENTENCE, FRIA_OTHER_CAUSES_TEMPLATE.format(reasons=REVIEW_CAUSE_REASONS["fact_conflict"])]


def test_refused_input_has_no_article_27_block(dump):
    env = classify_ai_system(case(all_false(), domain="banking"), dump)
    assert env["status"] == "rejected_as_unsupported"
    assert "fria" in env["answer"] and env["answer"]["fria"] is None


def test_ruling_r5_candidate_with_the_section_unknown_is_marked_and_names_the_section(dump):
    # A true listed use, a proven Article 6(1) route, a true candidate and the
    # Annex I section unknown: at 12eec31 potentially_applicable 1.0, the
    # section fact not named.
    features = _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"),
                         absent=("annex_i_section_b_legislation",), domain=None, **P61)
    env = classify_ai_system(features, dump)
    a = env["answer"]
    assert a["risk_category"] == "high_risk"
    assert a["high_risk_routes"] == ["article_6_1", "article_6_2"] and a["annex_i_section"] == "unknown"
    assert a["article_6_3_exception_candidate"] is True
    assert (env["status"], env["confidence"]) == ("requires_human_review", 0.5)
    assert review_causes(a, env["missing_facts"]) == ["article_6_3_candidate"]
    assert _status_lines(a) == [review_status_line("article_6_3_candidate", a)]
    assert ANNEX_I_SECTION_UNKNOWN_FACT in env["missing_facts"]
    # With the section known to be A the candidate is no cause and the
    # section fact is not named.
    known = _features(true=("annex_iii_4a_recruitment", "narrow_procedural_task"), domain=None, **P61,
                      annex_i_section_b_legislation=False)
    env_a = classify_ai_system(known, dump)
    assert env_a["status"] == "potentially_applicable" and ANNEX_I_SECTION_UNKNOWN_FACT not in env_a["missing_facts"]


# The invariant over the table and the generated set -------------------------

def test_the_generated_set_is_large_and_reaches_every_cause(answered):
    assert len(answered) >= 5000 + len(AREA_CASES)
    seen = {cause for _n, _f, env in answered for cause in review_causes(env["answer"], env["missing_facts"])}
    assert seen == set(REVIEW_CAUSES)


def test_status_is_review_exactly_when_a_cause_holds(answered):
    broken = []
    for name, _features_in, env in answered:
        a = env["answer"]
        if env["status"] == "rejected_as_unsupported":
            continue
        causes = review_causes(a, env["missing_facts"])
        if a["risk_category"] == "undetermined":
            ok = env["status"] == "requires_human_review" and not _status_lines(a)
        else:
            ok = (env["status"] == "requires_human_review") == bool(causes)
            ok = ok and env["confidence"] == (0.5 if causes else 1.0)
            ok = ok and _status_lines(a) == [review_status_line(cause, a) for cause in causes]
        if not ok:
            broken.append(name)
    assert broken == []


def test_the_block_names_every_cause_when_it_answers_unknown(answered):
    # On a high_risk or unacceptable_risk answer whose block answers unknown,
    # every cause of review that holds is named in the block's sentences, the
    # area first, then in the order of D-G92 (8) (the rule added after the
    # plan's review).
    broken = []
    for name, _features_in, env in answered:
        a = env["answer"]
        if a.get("risk_category") not in ("high_risk", "unacceptable_risk") or a["fria"]["applicability"] != "unknown":
            continue
        causes = review_causes(a, env["missing_facts"])
        text = " ".join(a["fria"]["rationale"])
        # The area alone is named by the block's own area sentence, first.
        words = {**REVIEW_CAUSE_REASONS, "area_alone": "the level rests on the area alone"}
        # In the block the area comes first, then the spec's order.
        in_block_order = sorted(causes, key=lambda cause: cause != "area_alone")
        positions = [text.find(words[cause]) for cause in in_block_order if cause != "article_6_3_candidate"]
        if "article_6_3_candidate" in causes and not (
            CANDIDACY_SENTENCE in text or REVIEW_CAUSE_REASONS["article_6_3_candidate"] in text
        ):
            broken.append(name)
        if -1 in positions or positions != sorted(positions):
            broken.append(name)
    assert broken == []


def test_no_sentence_names_unacceptable_risk_unless_it_is_unknown(answered, served):
    # B185 Task 7: the applicable requirements' note, message, notes and
    # missing facts are read too, from the envelope and from the bare answer
    # (at 5d5bc14 the note named a change to Unacceptable risk on every
    # unsettled answer, unacceptable_risk false included).
    broken = []
    for name, _features_in, env in answered:
        a = env["answer"]
        if a["unacceptable_risk"] is None or a["fria"] is None:
            continue
        texts = [*a["rationale"], *env["legal_status_notes"], *a["fria"]["rationale"], *a["fria"]["missing_facts"]]
        for req in served[name]:
            texts += [req["answer"].get("provisional_note") or "", req["answer"].get("message") or "",
                      *req["legal_status_notes"], *req["missing_facts"]]
        if any("Unacceptable risk" in text for text in texts):
            broken.append(name)
    assert broken == []


def test_no_sentence_says_not_settled_on_an_answer_that_is_not_review(answered):
    broken = []
    for name, _features_in, env in answered:
        a = env["answer"]
        if env["status"] in ("requires_human_review", "rejected_as_unsupported"):
            continue
        texts = [*a["rationale"], *env["legal_status_notes"], *a["fria"]["rationale"], *a["fria"]["missing_facts"]]
        if any(words in text for text in texts for words in UNSETTLED_WORDS):
            broken.append(name)
    assert broken == []


def test_the_candidate_lines_follow_the_returned_value(answered):
    # Task 5's review: the invariant the assert in _annex_iii_candidacy held,
    # now a test. A condition that is true and not cancelled by profiling is
    # exactly a true candidate; on an answer with an Annex III point the
    # Article 6(4) citation and the condition lines stand exactly then.
    broken = []
    for name, features_in, env in answered:
        flags = features_in["flags"]
        matched = [flag for flag, _points, _label in ARTICLE_6_3_CONDITIONS if flags.get(flag) is True]
        if flags.get("profiling_of_natural_persons") is True:
            matched = []
        if bool(matched) != (article_6_3_candidate(flags) is True):
            broken.append(name)
        a = env["answer"]
        has_point = a.get("annex_iii_category") or a.get("annex_iii_area_unconfirmed")
        if a.get("risk_category") == "high_risk" and has_point:
            cites_6_4 = ARTICLE_6_4 in env["source_nodes"]
            if cites_6_4 != (a["article_6_3_exception_candidate"] is True):
                broken.append(name)
    assert broken == []


# The causes recomputed by the spec's words (B185 Task 7, the coordinator's
# check (c)) and the envelope against the bare answer (check (d)) ----------

def _causes_by_the_spec(answer: dict[str, Any], features_in: dict[str, Any]) -> list[str]:
    """The causes of review that hold, recomputed here from the answer's
    fields and the input facts (corrected by the Act's definitions, as the
    classifier reads them), by the spec's words, in the order of D-G92 (8),
    without review_causes:
    - an unknown Article 5 fact: unacceptable_risk null on a high_risk or
      limited_risk answer (DEC-18);
    - facts that contradict a definition: fact_conflicts not empty (DEC-32);
    - a listed use true beside none_of_these_areas: area_conflicts not empty,
      on every exit (D-G92 (iii) and the rule added after the plan's review);
    - the area alone: a point in annex_iii_area_unconfirmed and no route
      (D-G92 (3), (i));
    - an Article 6(3) candidate where Annex III decides what is served: the
      field true, and Article 6(1) not a route, or Article 6(2) a route and
      the Annex I section B or unknown (passage (k), ruling R5 corrected);
    - an open Article 6(1) route on a limited_risk answer: neither fact known
      false and not both true (B123);
    - an unknown listed use, on a limited_risk answer or a Section B product
      on the Article 6(1) route alone: one of the 25 listed uses absent, or
      real_time_remote_biometric_public absent, which by D-G92 (2) also
      gives point 1 (R39)."""
    flags = apply_entailments(features_in["flags"])[0]
    level = answer["risk_category"]
    routes = answer["high_risk_routes"]
    section = answer["annex_i_section"]
    holds = []
    if level in ("high_risk", "limited_risk") and answer["unacceptable_risk"] is None:
        holds.append("article_5_unknown")
    if answer["fact_conflicts"]:
        holds.append("fact_conflict")
    if answer["area_conflicts"]:
        holds.append("area_conflict")
    if level == "high_risk" and answer["annex_iii_area_unconfirmed"] and routes == []:
        holds.append("area_alone")
    if answer["article_6_3_exception_candidate"] is True and (
        "article_6_1" not in routes or ("article_6_2" in routes and section in ("B", "unknown"))
    ):
        holds.append("article_6_3_candidate")
    covered, third_party = flags.get("annex_i_covered_product"), flags.get("third_party_conformity_assessment_required")
    if level == "limited_risk" and covered is not False and third_party is not False and not (
        covered is True and third_party is True
    ):
        holds.append("article_6_1_open")
    section_b_alone = level == "high_risk" and section == "B" and routes == ["article_6_1"]
    annex_iii_facts = (*ANNEX_III_LISTED_USE_FACTS, "real_time_remote_biometric_public")
    if (level == "limited_risk" or section_b_alone) and any(fact not in flags for fact in annex_iii_facts):
        holds.append("listed_use_unknown")
    return holds


def _expected_message(a: dict[str, Any], env: dict[str, Any], causes: list[str]) -> str | None:
    """The requirements' message where the spec fixes it: minimal_risk gets
    MINIMAL_MESSAGE; a Section B product on the Article 6(1) route alone gets
    the Article 2(2) message, its unknown form when an unknown listed use is
    a cause or a point rests on the area (R39, ruling P25); unacceptable_risk
    gets the point (h) message when point (h) is the only point of Article
    5(1) the classification cites, the general one otherwise (B184 rulings R2,
    R12), then the fact conflict clause and the area conflict clause, each
    when its cause holds (B184 M3, ruling P26). None elsewhere."""
    level = a["risk_category"]
    if level == "minimal_risk":
        return MINIMAL_MESSAGE
    if level == "high_risk" and a.get("annex_i_section") == "B" and a["high_risk_routes"] == ["article_6_1"]:
        unknown = "listed_use_unknown" in causes or a.get("annex_iii_area_unconfirmed")
        return SECTION_B_ANNEX_III_UNKNOWN_MESSAGE if unknown else SECTION_B_MESSAGE
    if level == "unacceptable_risk":
        points = sorted({n for n in env["source_nodes"] if n.startswith("eu-ai-act:article-5:paragraph-1:point-")})
        message = PROHIBITED_MESSAGE_POINT_H if points == [ARTICLE_5_POINT_H] else PROHIBITED_MESSAGE
        if "fact_conflict" in causes:
            message += " " + PROHIBITION_FACT_CONFLICT_CLAUSE
        if "area_conflict" in causes:
            message += " " + PROHIBITION_AREA_CONFLICT_CLAUSE
        return message
    return None


def test_every_place_agrees_with_the_causes_recomputed_by_the_spec(answered, served):
    words = {**REVIEW_CAUSE_REASONS, "area_alone": "the level rests on the area alone"}
    broken = []
    for name, features_in, env in answered:
        a = env["answer"]
        if env["status"] == "rejected_as_unsupported" or a["risk_category"] == "undetermined":
            continue
        causes = _causes_by_the_spec(a, features_in)
        # The classification's status, confidence and status lines.
        ok = (env["status"] == "requires_human_review") == bool(causes)
        ok = ok and env["confidence"] == (0.5 if causes else 1.0)
        ok = ok and _status_lines(a) == [review_status_line(cause, a) for cause in causes]
        # The Article 27(1) block, where it answers unknown on a high_risk or
        # unacceptable_risk answer: each cause named, no other one.
        if a["risk_category"] in ("high_risk", "unacceptable_risk") and a["fria"]["applicability"] == "unknown":
            text = " ".join(a["fria"]["rationale"])
            for cause in REVIEW_CAUSES:
                if cause == "article_6_3_candidate":
                    named = CANDIDACY_SENTENCE in text or words[cause] in text
                    ok = ok and (named or cause not in causes)
                else:
                    ok = ok and (words[cause] in text) == (cause in causes)
        # The applicable requirements, from the envelope and the bare answer.
        section_b_alone = a.get("annex_i_section") == "B" and a["high_risk_routes"] == ["article_6_1"]
        for req in served[name]:
            ra = req["answer"]
            if a["risk_category"] in ("unacceptable_risk", "minimal_risk") or section_b_alone:
                ok = ok and "provisional_note" not in ra
                ok = ok and ra.get("message") == _expected_message(a, env, causes)
                if a["risk_category"] != "minimal_risk":
                    ok = ok and (req["status"] == "requires_human_review") == bool(causes)
                continue
            if causes:
                note = PROVISIONAL_NOTE_TEMPLATE.format(reasons="; ".join(REVIEW_CAUSE_REASONS[c] for c in causes))
                if a.get("annex_i_section") == "B" and a.get("annex_iii_category"):
                    note += SECTION_B_DEROGATION_NOTE
                ok = ok and req["status"] == "requires_human_review" and ra.get("provisional_note") == note
            else:
                ok = ok and "provisional_note" not in ra
        if not ok:
            broken.append(name)
    assert broken == []


def _read_alike(req: dict[str, Any]) -> dict[str, Any]:
    ra = req["answer"] or {}
    return {
        "status": req["status"],
        "confidence": req["confidence"],
        "provisional": ra.get("provisional"),
        "provisional_note": ra.get("provisional_note"),
        "message": ra.get("message"),
        "groups": {g: [n["norm_id"] for n in v] for g, v in (ra.get("requirements_by_article") or {}).items()},
        "application_dates": ra.get("application_dates"),
        "annex_i_section": ra.get("annex_i_section"),
    }


# The lines the requirements give when the classification names no missing
# fact: an undetermined one, and an unsettled one.
AREA_UNCONFIRMED_FACT_START = "annex_iii_area_unconfirmed is "
UNDETERMINED_FALLBACK_FACT = (
    "the classification is Undetermined: facts missing; requirements cannot be determined until the "
    "classification is settled"
)


def test_an_envelope_and_its_bare_answer_read_alike(answered, served):
    # The status, confidence, provisional flag, note, message, requirements
    # served and dates are the same. The missing facts differ only by the
    # classification's own, which the bare answer does not carry: what the
    # requirements add is the same in both forms, the lines kept for a
    # classification that names no missing fact apart. (The cited Article 5
    # nodes of a prohibited answer also differ, as before B185: the bare
    # answer carries no cited provisions and its rationale names the point
    # only, B184 final review I1.)
    broken = []
    for name, _features_in, env in answered:
        from_envelope, from_bare = served[name]
        if _read_alike(from_envelope) != _read_alike(from_bare):
            broken.append(name)
            continue
        classification_missing = env["missing_facts"]
        # Set apart too: the line a bare Section B answer gives for a point
        # that rests on the area, in place of the classification's lines that
        # name its unknown listed uses (B185 Task 7 follow-up), and the line
        # it gives with no area set for an unknown listed use read from its
        # status line (B185 Task 8).
        def kept(m: str) -> bool:
            return (m not in classification_missing
                    and m not in (UNSETTLED_FALLBACK_FACT, UNDETERMINED_FALLBACK_FACT,
                                  SECTION_B_LISTED_USE_UNKNOWN_FACT)
                    and not m.startswith(AREA_UNCONFIRMED_FACT_START))

        added_envelope = [m for m in from_envelope["missing_facts"] if kept(m)]
        added_bare = [m for m in from_bare["missing_facts"] if kept(m)]
        if added_envelope != added_bare:
            broken.append(name)
    assert broken == []

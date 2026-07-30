"""M3 runtime tool: classify_ai_system as a pure, deterministic function.

Risk classification is decided by a fixed rule ladder over the structured
system features (schema/json_schemas/system_features.schema.json), never by
a model (@USER.md domain guardrail: the LLM never decides the risk
classification). The ladder is: Article 5 prohibitions, then the Article
6(1) embedded-product route (Annex I plus third-party conformity
assessment), then Article 6(2) plus Annex III high-risk categories, then
Article 6(3) derogation candidacy over the real second-subparagraph
conditions (with the third-subparagraph profiling override), then Article
50 transparency, else minimal. Every cited node id
is resolved against the offline Layer 0+1 dump; unknown facts are never
guessed, they surface in missing_facts and lower the status to
requires_human_review where they could change the outcome.

The rule logic follows the FLI compliance checker's decision structure as a
classification-logic source and baseline (REF-30, architecture.md Section
8); the text tested against is the frozen Regulation source (REF-01).

@implements: DEC-08, DEC-10 (partial: runtime classification)
@grounded_by: REF-30, REF-17, REF-01
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tere4ai.mcp_server.fria import assess_fria_applicability
from tere4ai.mcp_server.tools import make_envelope

_REPO_ROOT = Path(__file__).resolve().parents[3]
FEATURES_SCHEMA_PATH = _REPO_ROOT / "schema" / "json_schemas" / "system_features.schema.json"

# Article 5(1) prohibition rules: feature flag -> the real Point node in the
# Layer 1 dump. Each point marker was resolved by matching the dump text of
# eu-ai-act:article-5:paragraph-1:point-* (build build-3b753e5e9297); the
# quoted fragment below is from that node's text.
ARTICLE_5_POINT_BY_FLAG: dict[str, tuple[str, str]] = {
    # point (a): "deploys subliminal techniques beyond a person's
    # consciousness or purposefully manipulative or deceptive techniques"
    "subliminal_or_manipulative": (
        "eu-ai-act:article-5:paragraph-1:point-a",
        "subliminal, purposefully manipulative or deceptive techniques that "
        "materially distort behaviour",
    ),
    # point (b): "exploits any of the vulnerabilities of a natural person or a
    # specific group of persons due to their age, disability or a specific
    # social or economic situation"
    "exploits_vulnerabilities": (
        "eu-ai-act:article-5:paragraph-1:point-b",
        "exploitation of vulnerabilities due to age, disability or a specific "
        "social or economic situation",
    ),
    # point (c): "evaluation or classification of natural persons or groups of
    # persons over a certain period of time based on their social behaviour
    # ... with the social score leading to ..."
    "social_scoring": (
        "eu-ai-act:article-5:paragraph-1:point-c",
        "social scoring leading to detrimental or unfavourable treatment",
    ),
    # point (d): "making risk assessments of natural persons in order to
    # assess or predict the risk of a natural person committing a criminal
    # offence, based solely on the profiling of a natural person"
    "predictive_policing_profiling": (
        "eu-ai-act:article-5:paragraph-1:point-d",
        "predicting the risk of committing a criminal offence based solely on "
        "profiling or personality traits",
    ),
    # point (e): "create or expand facial recognition databases through the
    # untargeted scraping of facial images from the internet or CCTV footage"
    "facial_image_scraping": (
        "eu-ai-act:article-5:paragraph-1:point-e",
        "facial recognition databases built by untargeted scraping of facial "
        "images from the internet or CCTV footage",
    ),
    # point (f): "infer emotions of a natural person in the areas of workplace
    # and education institutions"
    "emotion_recognition_workplace_or_education": (
        "eu-ai-act:article-5:paragraph-1:point-f",
        "inferring emotions of a natural person in the areas of workplace and "
        "education institutions",
    ),
    # point (g): "biometric categorisation systems that categorise
    # individually natural persons based on their biometric data to deduce or
    # infer their race, political opinions, trade union membership, religious
    # or philosophical beliefs, sex life or sexual orientation"
    "biometric_categorisation": (
        "eu-ai-act:article-5:paragraph-1:point-g",
        "biometric categorisation deducing or inferring sensitive traits "
        "(race, political opinions, beliefs, sex life or sexual orientation)",
    ),
}

# point (h): "the use of real-time remote biometric identification systems in
# publicly accessible spaces for the purposes of law enforcement". This one
# needs BOTH flags: the biometric flag and the law-enforcement-use context.
ARTICLE_5_POINT_H = "eu-ai-act:article-5:paragraph-1:point-h"
ARTICLE_5_POINT_H_FRAGMENT = (
    "real-time remote biometric identification in publicly accessible spaces "
    "for the purposes of law enforcement"
)

# Article 5 statutory qualifiers and exceptions (audit 2026-07-20 D2). Each
# qualified point carries an EXCULPATING FACT: a boolean the caller can set
# that, when equal to `exculpating_value`, means the prohibition does NOT
# apply (the statute's exception is met, or its harm/outcome element is
# absent). When the fact is unknown the ban is not settled, so the system is
# routed to human review instead of being confidently prohibited; only an
# explicit non-exculpating value yields a confident prohibition. The point
# with no entry (facial image scraping, (e)) is a clean 1:1 with no statutory
# exception. Anchors are the frozen point texts.
# Tuple: (fact_name, exculpating_value, human-readable element description).
ARTICLE_5_EXCULPATING_FACT: dict[str, tuple[str, bool, str]] = {
    # (a)/(b) prohibit only "in a manner that causes or is reasonably likely
    # to cause ... significant harm"; without that element, not prohibited.
    "subliminal_or_manipulative": (
        "causes_significant_harm",
        False,
        "the point (a) 'significant harm' element",
    ),
    "exploits_vulnerabilities": (
        "causes_significant_harm",
        False,
        "the point (b) 'significant harm' element",
    ),
    # (c) prohibits social scoring "leading to detrimental or unfavourable
    # treatment" in unrelated contexts or unjustified/disproportionate.
    "social_scoring": (
        "social_score_detrimental_treatment",
        False,
        "the point (c) detrimental-treatment element",
    ),
    # (d) "shall not apply to AI systems used to support the human assessment
    # ... based on objective and verifiable facts".
    "predictive_policing_profiling": (
        "supports_human_assessment_on_verifiable_facts",
        True,
        "the point (d) human-assessment-on-verifiable-facts exception",
    ),
    # (f) "except where ... intended ... for medical or safety reasons".
    "emotion_recognition_workplace_or_education": (
        "emotion_recognition_medical_or_safety",
        True,
        "the point (f) medical or safety exception",
    ),
    # (g) "does not cover ... labelling or filtering of lawfully acquired
    # biometric datasets ... or ... in the area of law enforcement".
    "biometric_categorisation": (
        "biometric_categorisation_lawful_or_law_enforcement",
        True,
        "the point (g) lawful-dataset / law-enforcement carve-out",
    ),
}
# (h) real-time RBI for law enforcement is conditionally permitted where
# "strictly necessary" for objectives (i) to (iii) and duly authorised.
ARTICLE_5_POINT_H_EXCULPATING = (
    "rtrb_strictly_necessary_authorised",
    True,
    "the point (h) strict-necessity and authorisation carve-out (i) to (iii)",
)

# Flags whose unknown value can change the prohibition outcome. Absence is
# NOT treated as false (system_features.schema.json).
PROHIBITION_RELEVANT_FLAGS: tuple[str, ...] = (
    *ARTICLE_5_POINT_BY_FLAG.keys(),
    "real_time_remote_biometric_public",
)

# Article 6(2) + Annex III: the eight high-risk categories, each cited by its
# real AnnexItem node (eu-ai-act:annex-iii:point-1 .. point-8 in the dump).
# Checked in point order; the first match becomes annex_iii_category.
ANNEX_III_RULES: tuple[dict[str, Any], ...] = (
    {
        # point 1: "Biometrics ... remote biometric identification systems
        # ... emotion recognition"
        "node": "eu-ai-act:annex-iii:point-1",
        "label": "biometrics",
        "flags": (
            "biometric_identification",
            "emotion_recognition",
            "real_time_remote_biometric_public",
        ),
        "domains": (),
    },
    {
        # point 2: "Critical infrastructure: AI systems intended to be used
        # as safety components in the management and operation of critical
        # digital infrastructure, road traffic, or in the supply of water,
        # gas, heating or electricity."
        "node": "eu-ai-act:annex-iii:point-2",
        "label": "critical infrastructure",
        "flags": ("critical_infrastructure_safety",),
        "domains": ("critical_infrastructure",),
    },
    {
        # point 3: "Education and vocational training: ... determine access
        # or admission ... evaluate learning outcomes"
        "node": "eu-ai-act:annex-iii:point-3",
        "label": "education and vocational training",
        "flags": ("education_scoring_or_access",),
        "domains": ("education",),
    },
    {
        # point 4: "Employment, workers' management and access to
        # self-employment: ... recruitment or selection of natural persons"
        "node": "eu-ai-act:annex-iii:point-4",
        "label": "employment and workers management",
        "flags": ("employment_decisions",),
        "domains": ("employment",),
    },
    {
        # point 5: "Access to and enjoyment of essential private services and
        # essential public services and benefits: ... evaluate the
        # eligibility of natural persons for essential public assistance
        # benefits and services, including healthcare services"
        "node": "eu-ai-act:annex-iii:point-5",
        "label": "essential private and public services",
        "flags": ("essential_services_access",),
        # Sub-point facts (5(b) creditworthiness, 5(c) life/health insurance
        # pricing): a true value matches the category, but the domain-yield
        # rule below stays over the umbrella flag only, because an explicit
        # false on the umbrella already denies the whole point 5 area
        # (scenario 161 semantics preserved). These two also feed the FRIA
        # rule (fria.py, DEC-14).
        "subflags": (
            "creditworthiness_evaluation",
            "life_health_insurance_risk_pricing",
        ),
        "domains": ("healthcare", "banking", "insurance"),
    },
    {
        # point 6: "Law enforcement, in so far as their use is permitted
        # under relevant Union or national law"
        "node": "eu-ai-act:annex-iii:point-6",
        "label": "law enforcement",
        "flags": ("law_enforcement_use",),
        "domains": ("law_enforcement",),
    },
    {
        # point 7: "Migration, asylum and border control management"
        "node": "eu-ai-act:annex-iii:point-7",
        "label": "migration, asylum and border control",
        "flags": ("migration_asylum_border_use",),
        "domains": ("migration",),
    },
    {
        # point 8: "Administration of justice and democratic processes"
        "node": "eu-ai-act:annex-iii:point-8",
        "label": "administration of justice and democratic processes",
        "flags": ("justice_democratic_use",),
        "domains": ("justice",),
    },
)

# Flags whose unknown value can change an Annex III high-risk outcome. Like
# the prohibition flags, absence is NOT treated as false: an unknown Annex
# III fact is surfaced in missing_facts and blocks a confident
# minimal_or_none verdict (audit 2026-07-20 D1). Built from the rule table so
# it can never drift from the categories. Flags already covered by
# PROHIBITION_RELEVANT_FLAGS are excluded to avoid double-surfacing.
ANNEX_III_RELEVANT_FLAGS: tuple[str, ...] = tuple(
    f
    for f in dict.fromkeys(
        flag
        for rule in ANNEX_III_RULES
        for flag in (*rule["flags"], *rule.get("subflags", ()))
    )
    if f not in PROHIBITION_RELEVANT_FLAGS
)

ARTICLE_6_PARAGRAPH_1 = "eu-ai-act:article-6:paragraph-1"
ARTICLE_6_PARAGRAPH_2 = "eu-ai-act:article-6:paragraph-2"
ARTICLE_6_PARAGRAPH_3 = "eu-ai-act:article-6:paragraph-3"
ANNEX_I = "eu-ai-act:annex-i"
# Article 6(3) third subparagraph: "shall always be considered to be
# high-risk where the AI system performs profiling of natural persons".
ARTICLE_6_3_PROFILING_OVERRIDE = "eu-ai-act:article-6:paragraph-3:subparagraph-3"

# Article 6(3) second-subparagraph conditions: flag -> the real Point nodes.
# The legacy combined flag covers point (a) "narrow procedural task" and
# point (d) "preparatory task to an assessment"; the two newer flags map to
# points (b) and (c) one-to-one.
ARTICLE_6_3_CONDITIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "preparatory_or_narrow_procedural_task",
        (
            "eu-ai-act:article-6:paragraph-3:point-a",
            "eu-ai-act:article-6:paragraph-3:point-d",
        ),
        "narrow procedural task (point a) or preparatory task (point d)",
    ),
    (
        "improves_previous_human_activity",
        ("eu-ai-act:article-6:paragraph-3:point-b",),
        "improves the result of a previously completed human activity (point b)",
    ),
    (
        "detects_patterns_without_replacing_human_assessment",
        ("eu-ai-act:article-6:paragraph-3:point-c",),
        "detects decision-making patterns without replacing human assessment (point c)",
    ),
)

# Article 50 transparency rules: flag -> the real Paragraph node.
ARTICLE_50_RULES: tuple[tuple[str, str, str], ...] = (
    # 50(1): "Providers shall ensure that AI systems intended to interact
    # directly with natural persons are designed and developed ..."
    (
        "interacts_with_natural_persons",
        "eu-ai-act:article-50:paragraph-1",
        "interaction with natural persons must be disclosed",
    ),
    # 50(2): "Providers of AI systems ... generating synthetic audio, image,
    # video or text content ..."
    (
        "generates_synthetic_content",
        "eu-ai-act:article-50:paragraph-2",
        "synthetic content must be marked as artificially generated or manipulated",
    ),
    # 50(3): "Deployers of an emotion recognition system or a biometric
    # categorisation system shall inform the natural persons ..."
    (
        "emotion_recognition",
        "eu-ai-act:article-50:paragraph-3",
        "exposed persons must be informed of emotion recognition",
    ),
)

RISK_CATEGORIES = (
    "prohibited",
    "high_risk",
    "transparency_only",
    "minimal_or_none",
    "uncertain",
)


@lru_cache(maxsize=1)
def _features_validator() -> Draft202012Validator:
    schema = json.loads(FEATURES_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _graph_version(dump: dict[str, Any]) -> str:
    return str(dump.get("build", {}).get("build_id", "unknown"))


def _node_index(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in dump.get("nodes", []) if isinstance(n, dict) and "id" in n}


class _Citations:
    """Collects cited node ids and spans, resolved against the dump."""

    def __init__(self, node_index: dict[str, dict[str, Any]]):
        self._index = node_index
        self.node_ids: list[str] = []
        self.spans: list[dict[str, Any]] = []
        self.unresolved: list[str] = []

    def cite(self, node_id: str) -> None:
        if node_id in self.node_ids:
            return
        node = self._index.get(node_id)
        if node is None:
            # Never cite a node that does not exist in the dump; surface it.
            self.unresolved.append(
                f"cited node '{node_id}' is not present in the graph dump; "
                "citation withheld"
            )
            return
        self.node_ids.append(node_id)
        span = node.get("source_span")
        if isinstance(span, dict):
            self.spans.append(span)


def _normalize_domain(raw: Any) -> str | None:
    """Normalise a free-text domain token before matching.

    Drops Unicode format and control characters (zero-width space, soft
    hyphen, bidi marks) and applies NFKC, so an invisible or compatibility
    character cannot silently turn a known domain into a near-miss that then
    reads as out-of-scope (audit 2026-07-20 D8). Case-folded and trimmed.
    Returns None for a blank or non-string value. Note a genuine homoglyph
    (e.g. a Cyrillic letter) still will not match a Latin domain, which is
    correct: it is a different string, and the D1 unknown-flag guard then
    prevents a confident minimal verdict rather than this function guessing.
    """
    if not isinstance(raw, str):
        return None
    cleaned = "".join(ch for ch in raw if unicodedata.category(ch)[0] != "C")
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return cleaned.strip().casefold() or None


def _annex_iii_all_matches(flags: dict[str, Any], domain: str | None) -> list[str]:
    """Every Annex III point node the facts match, in point order.

    Unlike _annex_iii_scan (first match only), this returns the FULL set, so
    the FRIA rule can tell a multi-area system apart from a single-area one:
    the Article 27(1) point-2 exception is scoped to the point-2 AREA, not to
    a system that also falls under another point (audit 2026-07-20 D5). Same
    domain-yield semantics as the scan.
    """
    matches: list[str] = []
    for rule in ANNEX_III_RULES:
        all_flags = (*rule["flags"], *rule.get("subflags", ()))
        matched_flag = any(flags.get(f) is True for f in all_flags)
        matched_domain = domain in rule["domains"]
        if matched_domain and not matched_flag:
            if rule["flags"] and all(flags.get(f) is False for f in rule["flags"]):
                matched_domain = False
        if matched_flag or matched_domain:
            matches.append(rule["node"])
    return matches


def _article_6_3_candidate(flags: dict[str, Any], autonomy: Any) -> bool:
    """Whether an Article 6(3) derogation candidacy is flagged for this system.

    The boolean half of the ladder's 6(3) logic, extracted so the FRIA rule
    can apply it to the 6(2) side of a dual 6(1)+6(2) route system (audit
    2026-07-20 D7). A matched second-subparagraph condition (with the
    advisory-autonomy guard on the legacy combined flag) raises candidacy,
    which the third-subparagraph profiling override then cancels.
    """
    matched = False
    for flag, _points, _label in ARTICLE_6_3_CONDITIONS:
        if flags.get(flag) is not True:
            continue
        if flag == "preparatory_or_narrow_procedural_task" and autonomy != "advisory":
            continue
        matched = True
    if matched and flags.get("profiling_of_natural_persons") is True:
        return False
    return matched


def _annex_iii_scan(
    flags: dict[str, Any], domain: str | None
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Scan the Annex III rules in point order; first match wins.

    Returns (matched rule or None, trigger description or None, rationale
    notes collected on the way, e.g. the domain-yield note). Pure function
    of the structured facts, shared by the classification ladder and the
    FRIA rule so the two can never disagree on Annex III membership.
    """
    notes: list[str] = []
    for rule in ANNEX_III_RULES:
        all_flags = (*rule["flags"], *rule.get("subflags", ()))
        matched_flag = next((f for f in all_flags if flags.get(f) is True), None)
        matched_domain = domain if domain in rule["domains"] else None
        # Evidence-driven fix (eval/results/ELICITATION_ERRORS.md, scenario
        # 161): a bare domain match must YIELD when every specific flag of
        # the category is explicitly false. Annex III categories cover
        # specific uses within a domain, not the domain itself; with the
        # uses explicitly ruled out, domain alone is not a basis. Unknown
        # flags keep the match (unknown is never treated as false). The
        # yield check stays over the umbrella flags, not the subflags.
        if matched_domain and not matched_flag:
            all_explicitly_false = rule["flags"] and all(
                flags.get(f) is False for f in rule["flags"]
            )
            if all_explicitly_false:
                notes.append(
                    f"domain '{matched_domain}' matches Annex III category "
                    f"'{rule['label']}' but every specific flag of the "
                    "category is explicitly false; domain alone does not "
                    "gate high-risk (ELICITATION_ERRORS.md, scenario 161)"
                )
                matched_domain = None
        if matched_flag or matched_domain:
            trigger = (
                f"flag {matched_flag}" if matched_flag else f"domain '{matched_domain}'"
            )
            return rule, trigger, notes
    return None, None, notes


def _classify_core(features: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    """Deterministic EU AI Act risk classification of a described AI system.

    Consumes structured system features (system_features.schema.json) and the
    offline Layer 0+1 dump. Returns the mandatory response envelope with
    answer fields: risk_category, prohibited, annex_iii_category,
    article_6_3_exception_candidate, rationale. Schema-invalid input returns
    status rejected_as_unsupported (never an exception) with the validation
    errors in missing_facts: the input was refused, not assessed, so it must
    not borrow not_applicable, which is a substantive in-scope verdict ("this
    system is out of the high-risk or prohibited regime") that a consumer
    reading only status could mistake a rejected input for. A well-formed
    system that is simply out of scope still returns not_applicable. No model
    is involved anywhere in this function.
    """
    graph_version = _graph_version(dump)

    errors = sorted(_features_validator().iter_errors(features), key=lambda e: list(e.path))
    if errors:
        return make_envelope(
            answer={
                "risk_category": None,
                "prohibited": False,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": ["input rejected: features do not conform to system_features.schema.json"],
            },
            status="rejected_as_unsupported",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"schema validation: {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                for e in errors
            ],
        )

    flags = features.get("flags") or {}
    domain = _normalize_domain(features.get("domain"))
    autonomy = features.get("autonomy")

    citations = _Citations(_node_index(dump))
    rationale: list[str] = []
    legal_status_notes: list[str] = []
    missing_facts: list[str] = []

    # Unknown prohibition-relevant flags: absence is never treated as false.
    unknown_prohibition_flags = [f for f in PROHIBITION_RELEVANT_FLAGS if f not in flags]
    for flag in unknown_prohibition_flags:
        missing_facts.append(
            f"flags.{flag} is unknown (prohibition-relevant, Article 5); "
            "absence is not treated as false"
        )

    # Unknown Annex III high-risk flags: same discipline (audit 2026-07-20 D1).
    # An absent Annex III fact could be the one that makes the system
    # high-risk, so it must not be silently read as false and cleared as
    # minimal. Surfaced here; the minimal and transparency exits consult it.
    unknown_annex_flags = [f for f in ANNEX_III_RELEVANT_FLAGS if f not in flags]
    for flag in unknown_annex_flags:
        missing_facts.append(
            f"flags.{flag} is unknown (Annex III high-risk relevant, Article "
            "6(2)); absence is not treated as false"
        )

    # Rule 1: Article 5 prohibitions. A prohibition flag names a candidate
    # practice; where the statute qualifies the point (D2), the ban only
    # fires once the exculpating fact settles against the exception. Pending
    # exception facts go to prohibition_review, which (like an unknown
    # prohibition flag) blocks a confident non-prohibited verdict downstream.
    prohibition_hits: list[tuple[str, str, str]] = []
    prohibition_review: list[str] = []

    def _resolve_prohibition(
        flag: str,
        node_id: str,
        fragment: str,
        exculpating: tuple[str, bool, str] | None,
    ) -> None:
        if exculpating is None:
            prohibition_hits.append((flag, node_id, fragment))
            return
        fact_name, exculpating_value, desc = exculpating
        value = flags.get(fact_name)
        if value is exculpating_value:
            # The statutory exception is met / the harm element is absent.
            rationale.append(
                f"Article 5 exception: {flag} is true but {fact_name} is "
                f"{value}, so {desc} means the practice is not prohibited "
                "under that point; continuing the ladder"
            )
            return
        if fact_name not in flags:
            prohibition_review.append(fact_name)
            missing_facts.append(
                f"flags.{fact_name} is unknown; {desc} decides whether "
                f"{flag} is prohibited (Article 5); absence does not settle "
                "the ban, so the classification stays for human review"
            )
            return
        prohibition_hits.append((flag, node_id, fragment))

    for flag, (node_id, fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        if flags.get(flag) is True:
            _resolve_prohibition(
                flag, node_id, fragment, ARTICLE_5_EXCULPATING_FACT.get(flag)
            )
    if flags.get("real_time_remote_biometric_public") is True:
        if flags.get("law_enforcement_use") is True:
            _resolve_prohibition(
                "real_time_remote_biometric_public + law_enforcement_use",
                ARTICLE_5_POINT_H,
                ARTICLE_5_POINT_H_FRAGMENT,
                ARTICLE_5_POINT_H_EXCULPATING,
            )
        elif "law_enforcement_use" not in flags:
            # The unknown context could change the outcome to prohibited.
            unknown_prohibition_flags.append("law_enforcement_use")
            missing_facts.append(
                "flags.law_enforcement_use is unknown while "
                "flags.real_time_remote_biometric_public is true; Article 5(1) "
                "point (h) applies only to law-enforcement use"
            )

    if prohibition_hits:
        for flag, node_id, fragment in prohibition_hits:
            citations.cite(node_id)
            rationale.append(f"rule prohibited: flag {flag} matches {node_id} ({fragment})")
            legal_status_notes.append(
                f"{node_id}: this practice is a prohibited AI practice under "
                f"Article 5(1) ({fragment}); placing on the market, putting "
                "into service, and use are banned, so no engineering "
                "requirement can make the system permissible"
            )
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "prohibited",
                "prohibited": True,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": rationale,
            },
            status="potentially_applicable",
            graph_version=graph_version,
            confidence=1.0,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Pending Article 5 exception facts keep the ban unsettled: fold them into
    # the unknown-prohibition set so every downstream exit lowers to
    # requires_human_review and a bare no-match yields uncertain rather than a
    # confident non-prohibited verdict (audit D2).
    unknown_prohibition_flags.extend(prohibition_review)

    # Rule 2a: Article 6(1) embedded-product route. High-risk when the
    # system is a safety component of (or is itself) a product covered by
    # Annex I Union harmonisation legislation AND that product requires a
    # third-party conformity assessment. Both facts must be explicitly true;
    # this route is independent of Annex III and the Article 6(3) derogation
    # does not apply to it (6(3) derogates from paragraph 2 only).
    annex_i_covered = flags.get("annex_i_covered_product")
    third_party_required = flags.get("third_party_conformity_assessment_required")
    article_6_1_unresolved = False
    if annex_i_covered is True and third_party_required is True:
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        citations.cite(ANNEX_I)
        rationale.append(
            "rule article_6_1: annex_i_covered_product and "
            "third_party_conformity_assessment_required are both true; the "
            "system is high-risk under Article 6(1) via Annex I"
        )
        legal_status_notes.append(
            f"{ARTICLE_6_PARAGRAPH_3}: the Article 6(3) derogation applies "
            "only to Annex III systems under Article 6(2), not to the "
            "Article 6(1) embedded-product route"
        )
        missing_facts.extend(citations.unresolved)
        status = "potentially_applicable"
        confidence = 1.0
        if unknown_prohibition_flags:
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to prohibited"
            )
        return make_envelope(
            answer={
                "risk_category": "high_risk",
                "prohibited": False,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": rationale,
            },
            status=status,
            graph_version=graph_version,
            confidence=confidence,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )
    if annex_i_covered is True and third_party_required is None:
        article_6_1_unresolved = True
        missing_facts.append(
            "flags.third_party_conformity_assessment_required is unknown while "
            "flags.annex_i_covered_product is true; Article 6(1) point (b) "
            "requires a third-party conformity assessment for the route to fire"
        )
    if annex_i_covered is True and third_party_required is False:
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        rationale.append(
            "rule article_6_1: annex_i_covered_product is true but no "
            "third-party conformity assessment is required, so the Article "
            "6(1) route does not fire; continuing down the ladder"
        )

    # Rule 2b: Article 6(2) + Annex III high-risk categories.
    annex_match, annex_trigger, annex_notes = _annex_iii_scan(flags, domain)
    rationale.extend(annex_notes)
    if annex_match is not None:
        rationale.append(
            f"rule high_risk: {annex_trigger} matches Annex III category "
            f"'{annex_match['label']}' ({annex_match['node']}), high-risk "
            "under Article 6(2)"
        )

    exception_candidate = False
    if annex_match is not None:
        citations.cite(annex_match["node"])
        citations.cite(ARTICLE_6_PARAGRAPH_2)

        # Rule 3: Article 6(3) derogation candidacy over the real second-
        # subparagraph conditions. The derogation needs human legal judgment;
        # it is flagged, never auto-applied. The legacy combined flag keeps
        # its conservative advisory-autonomy guard; the point (b) and (c)
        # flags are specific enough to flag candidacy on their own.
        matched_conditions: list[tuple[str, tuple[str, ...], str]] = []
        for flag, point_nodes, label in ARTICLE_6_3_CONDITIONS:
            if flags.get(flag) is not True:
                continue
            if flag == "preparatory_or_narrow_procedural_task" and autonomy != "advisory":
                continue
            matched_conditions.append((flag, point_nodes, label))
        if matched_conditions and flags.get("profiling_of_natural_persons") is True:
            # Article 6(3) third subparagraph: profiling systems are always
            # high-risk, so candidacy is cancelled, not merely flagged.
            citations.cite(ARTICLE_6_3_PROFILING_OVERRIDE)
            rationale.append(
                "rule article_6_3_profiling: a derogation condition matched but "
                "profiling_of_natural_persons is true; Article 6(3) third "
                "subparagraph keeps profiling systems high-risk, so no "
                "derogation candidacy"
            )
            matched_conditions = []
        if matched_conditions:
            exception_candidate = True
            citations.cite(ARTICLE_6_PARAGRAPH_3)
            for flag, point_nodes, label in matched_conditions:
                for node_id in point_nodes:
                    citations.cite(node_id)
                # Wording note: this line must not read "rule X: flag Y
                # matches Z", which is the classification-trigger grammar
                # parsed by scripts/elicitation_error_report.py; derogation
                # candidacy is not a classification trigger.
                rationale.append(
                    f"rule article_6_3: derogation condition '{label}' met "
                    f"by {flag}; the Article 6(3) derogation may apply but "
                    "requires human legal judgment, no automatic downgrade"
                )
            legal_status_notes.append(
                f"{ARTICLE_6_PARAGRAPH_3}: Article 6(3) derogation candidacy is "
                "flagged for human review; the classification stays high_risk "
                "until a human legal reviewer decides"
            )
            if "profiling_of_natural_persons" not in flags:
                missing_facts.append(
                    "flags.profiling_of_natural_persons is unknown while an "
                    "Article 6(3) derogation condition matched; profiling "
                    "cancels the derogation (Article 6(3) third subparagraph)"
                )

        missing_facts.extend(citations.unresolved)
        status = "potentially_applicable"
        confidence = 1.0
        if exception_candidate:
            status = "requires_human_review"
            confidence = 0.5
        elif unknown_prohibition_flags:
            # An unknown prohibition flag could change high_risk to
            # prohibited, so the outcome is not settled.
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to prohibited"
            )
        return make_envelope(
            answer={
                "risk_category": "high_risk",
                "prohibited": False,
                "annex_iii_category": annex_match["node"],
                "article_6_3_exception_candidate": exception_candidate,
                "rationale": rationale,
            },
            status=status,
            graph_version=graph_version,
            confidence=confidence,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Safety valve, not an auto-classification: the Article 6(1) route was
    # not settled (its facts are unknown, or a safety component was declared
    # without the Annex I facts). Never silently call that minimal.
    if article_6_1_unresolved or (
        flags.get("medical_or_safety_component") is True and annex_i_covered is None
    ):
        citations.cite(ARTICLE_6_PARAGRAPH_1)
        rationale.append(
            "rule uncertain: the Article 6(1) plus Annex I embedded-product "
            "route cannot be settled from the provided facts and no Annex III "
            "category matched; human legal review is needed"
        )
        missing_facts.append(
            "whether the system is a safety component of a product covered by "
            "Annex I Union harmonisation legislation requiring third-party "
            "conformity assessment (Article 6(1)) cannot be decided "
            "deterministically from the provided facts"
        )
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "uncertain",
                "prohibited": False,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": rationale,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Rule 4: Article 50 transparency obligations.
    transparency_hits = [
        (flag, node_id, note)
        for flag, node_id, note in ARTICLE_50_RULES
        if flags.get(flag) is True
    ]
    if transparency_hits:
        for flag, node_id, note in transparency_hits:
            citations.cite(node_id)
            rationale.append(f"rule transparency: flag {flag} matches {node_id} ({note})")
        missing_facts.extend(citations.unresolved)
        status = "potentially_applicable"
        confidence = 1.0
        if unknown_prohibition_flags:
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown "
                "prohibition-relevant flags could change the outcome to prohibited"
            )
        elif unknown_annex_flags:
            # A transparency system could also be high-risk under Annex III;
            # with those facts unknown, do not present transparency-only as
            # settled (audit 2026-07-20 D1).
            status = "requires_human_review"
            confidence = 0.5
            rationale.append(
                "status lowered to requires_human_review: unknown Annex III "
                "high-risk flags could add high-risk obligations on top of the "
                "Article 50 transparency duty"
            )
        return make_envelope(
            answer={
                "risk_category": "transparency_only",
                "prohibited": False,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": rationale,
            },
            status=status,
            graph_version=graph_version,
            confidence=confidence,
            source_nodes=citations.node_ids,
            source_spans=citations.spans,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    # Rule 5: nothing fired. A confident minimal verdict requires that every
    # prohibition-relevant AND Annex III-relevant fact is known: an unknown
    # one could be the fact that makes the system high-risk or prohibited, so
    # absence must never be read as a clean "not regulated" (audit D1).
    if unknown_prohibition_flags or unknown_annex_flags:
        which = []
        if unknown_prohibition_flags:
            which.append("prohibition-relevant (Article 5)")
        if unknown_annex_flags:
            which.append("Annex III high-risk (Article 6(2))")
        rationale.append(
            "rule uncertain: no rule fired but "
            + " and ".join(which)
            + " flags are unknown, so the classification cannot be settled "
            "deterministically; the named facts must be provided before a "
            "minimal verdict is safe"
        )
        missing_facts.extend(citations.unresolved)
        return make_envelope(
            answer={
                "risk_category": "uncertain",
                "prohibited": False,
                "annex_iii_category": None,
                "article_6_3_exception_candidate": False,
                "rationale": rationale,
            },
            status="requires_human_review",
            graph_version=graph_version,
            confidence=0.5,
            legal_status_notes=legal_status_notes,
            missing_facts=missing_facts,
        )

    rationale.append(
        "rule minimal: all prohibition-relevant AND Annex III high-risk flags "
        "known false, no Annex III category matched, no Article 50 transparency "
        "flag set"
    )
    missing_facts.extend(citations.unresolved)
    return make_envelope(
        answer={
            "risk_category": "minimal_or_none",
            "prohibited": False,
            "annex_iii_category": None,
            "article_6_3_exception_candidate": False,
            "rationale": rationale,
        },
        status="not_applicable",
        graph_version=graph_version,
        confidence=1.0,
        legal_status_notes=legal_status_notes,
        missing_facts=missing_facts,
    )


def classify_ai_system(features: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    """Deterministic classification plus the Article 27(1) FRIA block.

    Runs the rule ladder (_classify_core), then adds answer["fria"], the
    deterministic FRIA applicability block (fria.py, DEC-14): applies,
    does_not_apply, or unknown with the missing facts named. The FRIA rule
    reuses the same Annex III scan as the ladder, so when the ladder took
    the Article 6(1) embedded-product route the system's separate Article
    6(2) membership is still checked (both routes can hold at once, and
    Article 27(1) covers the 6(2) side). The fria block is self-contained:
    it never changes risk_category, envelope status, or confidence.
    """
    envelope = _classify_core(features, dump)
    answer = envelope.get("answer")
    if not isinstance(answer, dict) or "risk_category" not in answer:
        return envelope
    flags = features.get("flags") if isinstance(features, dict) else None
    if not isinstance(flags, dict):
        flags = {}
    deployer = features.get("deployer") if isinstance(features, dict) else None
    if not isinstance(deployer, dict):
        deployer = {}
    # Invalid input still reaches this wrapper (the core reports the schema
    # errors in its envelope), so never assume field types here.
    domain = _normalize_domain(
        features.get("domain") if isinstance(features, dict) else None
    )
    annex_node = answer.get("annex_iii_category")
    # The full set of matched Annex III points, so the FRIA rule can scope
    # the point-2 exception to the area, not the whole system (audit D5).
    # This also recovers the 6(2) side of a system that took the 6(1) route.
    annex_points = _annex_iii_all_matches(flags, domain)
    if annex_node is None and annex_points:
        annex_node = annex_points[0]
    # Recompute Article 6(3) candidacy for the 6(2) side even when the ladder
    # returned via the 6(1) route (its answer flag is False there): a
    # dual-route system's 6(2) derogation candidacy still blocks FRIA (D7).
    autonomy = features.get("autonomy") if isinstance(features, dict) else None
    candidate = answer.get("article_6_3_exception_candidate") is True or (
        bool(annex_points) and _article_6_3_candidate(flags, autonomy)
    )
    answer["fria"] = assess_fria_applicability(
        answer.get("risk_category"),
        annex_node,
        flags,
        deployer,
        article_6_3_exception_candidate=candidate,
        annex_points=annex_points,
        # An unsettled high-risk classification (requires_human_review) must
        # not carry a settled FRIA verdict (audit D6).
        classification_unsettled=(envelope.get("status") == "requires_human_review"),
    )
    return envelope

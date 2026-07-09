"""M3 runtime tool: classify_ai_system as a pure, deterministic function.

Risk classification is decided by a fixed rule ladder over the structured
system features (schema/json_schemas/system_features.schema.json), never by
a model (@USER.md domain guardrail: the LLM never decides the risk
classification). The ladder is: Article 5 prohibitions, then Article 6(2)
plus Annex III high-risk categories, then the Article 6(3) exception
candidate, then Article 50 transparency, else minimal. Every cited node id
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
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

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

ARTICLE_6_PARAGRAPH_2 = "eu-ai-act:article-6:paragraph-2"
ARTICLE_6_PARAGRAPH_3 = "eu-ai-act:article-6:paragraph-3"

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


def classify_ai_system(features: dict[str, Any], dump: dict[str, Any]) -> dict[str, Any]:
    """Deterministic EU AI Act risk classification of a described AI system.

    Consumes structured system features (system_features.schema.json) and the
    offline Layer 0+1 dump. Returns the mandatory response envelope with
    answer fields: risk_category, prohibited, annex_iii_category,
    article_6_3_exception_candidate, rationale. Invalid input returns status
    not_applicable with the validation errors in missing_facts, never an
    exception. No model is involved anywhere in this function.
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
            status="not_applicable",
            graph_version=graph_version,
            confidence=0.0,
            missing_facts=[
                f"schema validation: {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                for e in errors
            ],
        )

    flags = features.get("flags") or {}
    domain = (features.get("domain") or "").strip().lower() or None
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

    # Rule 1: Article 5 prohibitions.
    prohibition_hits: list[tuple[str, str, str]] = []
    for flag, (node_id, fragment) in ARTICLE_5_POINT_BY_FLAG.items():
        if flags.get(flag) is True:
            prohibition_hits.append((flag, node_id, fragment))
    if flags.get("real_time_remote_biometric_public") is True:
        if flags.get("law_enforcement_use") is True:
            prohibition_hits.append(
                (
                    "real_time_remote_biometric_public + law_enforcement_use",
                    ARTICLE_5_POINT_H,
                    ARTICLE_5_POINT_H_FRAGMENT,
                )
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

    # Rule 2: Article 6(2) + Annex III high-risk categories.
    annex_match: dict[str, Any] | None = None
    for rule in ANNEX_III_RULES:
        matched_flag = next((f for f in rule["flags"] if flags.get(f) is True), None)
        matched_domain = domain if domain in rule["domains"] else None
        # Evidence-driven fix (eval/results/ELICITATION_ERRORS.md, scenario
        # 161): a bare domain match must YIELD when every specific flag of
        # the category is explicitly false. Annex III categories cover
        # specific uses within a domain, not the domain itself; with the
        # uses explicitly ruled out, domain alone is not a basis. Unknown
        # flags keep the match (unknown is never treated as false).
        if matched_domain and not matched_flag:
            all_explicitly_false = rule["flags"] and all(
                flags.get(f) is False for f in rule["flags"]
            )
            if all_explicitly_false:
                rationale.append(
                    f"domain '{matched_domain}' matches Annex III category "
                    f"'{rule['label']}' but every specific flag of the "
                    "category is explicitly false; domain alone does not "
                    "gate high-risk (ELICITATION_ERRORS.md, scenario 161)"
                )
                matched_domain = None
        if matched_flag or matched_domain:
            annex_match = rule
            trigger = (
                f"flag {matched_flag}" if matched_flag else f"domain '{matched_domain}'"
            )
            rationale.append(
                f"rule high_risk: {trigger} matches Annex III category "
                f"'{rule['label']}' ({rule['node']}), high-risk under Article 6(2)"
            )
            break

    exception_candidate = False
    if annex_match is not None:
        citations.cite(annex_match["node"])
        citations.cite(ARTICLE_6_PARAGRAPH_2)

        # Rule 3: Article 6(3) derogation candidate. The derogation needs
        # human legal judgment; it is flagged, never auto-applied.
        if flags.get("preparatory_or_narrow_procedural_task") is True and autonomy == "advisory":
            exception_candidate = True
            citations.cite(ARTICLE_6_PARAGRAPH_3)
            rationale.append(
                "rule article_6_3: preparatory_or_narrow_procedural_task is true "
                "and autonomy is advisory; the Article 6(3) derogation may apply "
                "but requires human legal judgment, no automatic downgrade"
            )
            legal_status_notes.append(
                f"{ARTICLE_6_PARAGRAPH_3}: Article 6(3) derogation candidacy is "
                "flagged for human review; the classification stays high_risk "
                "until a human legal reviewer decides"
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

    # Safety valve, not an auto-classification: a safety component of a
    # regulated product goes through Article 6(1) plus Annex I, a route this
    # deterministic ladder does not cover. Never silently call that minimal.
    if flags.get("medical_or_safety_component") is True:
        citations.cite("eu-ai-act:article-6:paragraph-1")
        rationale.append(
            "rule uncertain: medical_or_safety_component is true but no Annex "
            "III category matched; the Article 6(1) plus Annex I "
            "embedded-product route is outside this deterministic check and "
            "needs human legal review"
        )
        missing_facts.append(
            "whether the system is a safety component of a product covered by "
            "Annex I Union harmonisation legislation (Article 6(1)) cannot be "
            "decided deterministically from the provided facts"
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

    # Rule 5: nothing fired.
    if unknown_prohibition_flags:
        rationale.append(
            "rule uncertain: no rule fired but prohibition-relevant flags are "
            "unknown, so the classification cannot be settled deterministically"
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
        "rule minimal: all prohibition-relevant flags known false, no Annex III "
        "category matched, no Article 50 transparency flag set"
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

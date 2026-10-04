"""The part of the Act's rules a norm belongs to: one closed slot, four values.

@implements: DEC-21
@implements: DEC-23
@grounded_by: REF-01

Each norm's target_system_category names the part of the Act's rules the
norm belongs to, by the category of AI systems those rules govern (thesis
task B124, spec G D-G62 in the private research repository). It does not
say which system a single paragraph talks about: Article 6(4) ("A provider
who considers that an AI system referred to in Annex III is not high-risk
shall document its assessment") is one of the high-risk classification
rules, so its norms carry high_risk_ai_system. The addressee stays in the
actor fields.

The value is a closed rule over a field the norm already has, its
source_node_id, so it is applied here in code and no model decides it,
under any prompt version (requirement_type.py's scope is the precedent).
RULE_TABLE has one row per Article or Annex of the extraction scope
(data/graph_dumps/core_nodes.txt), each with the Layer 1 wording that
decides it; category_for reads the Article or Annex segment of
source_node_id, not the Layer 1 Chapter edges. A unit outside the table
gets None, which the extraction build record counts, so a scope that grows
beyond the table shows in the build instead of being filled by a guess.
Extending the scope means adding rows, each with its deciding wording.
"""

from __future__ import annotations

from dataclasses import dataclass

ANY_AI_SYSTEM = "any_ai_system"
PROHIBITED_AI_PRACTICE = "prohibited_ai_practice"
HIGH_RISK_AI_SYSTEM = "high_risk_ai_system"
ARTICLE_50_AI_SYSTEM = "article_50_ai_system"

# The closed set, in the order of the Act's Chapters (schema $defs.targetSystemCategory).
TARGET_SYSTEM_CATEGORIES = (
    ANY_AI_SYSTEM,
    PROHIBITED_AI_PRACTICE,
    HIGH_RISK_AI_SYSTEM,
    ARTICLE_50_AI_SYSTEM,
)


@dataclass(frozen=True)
class Row:
    """One row of the rule table: the value and the wording that decides it.

    wording holds (Layer 1 node id, words quoted verbatim from that node's
    title or text); Chapter titles are in capitals as the dump stores them.
    """

    value: str
    wording: tuple[tuple[str, str], ...]


_CHAPTER_III = (("eu-ai-act:chapter-iii", "HIGH-RISK AI SYSTEMS"),)

RULE_TABLE: dict[str, Row] = {
    # Chapter I, the general provisions, addresses "AI systems" (Article 4,
    # whose paragraph 1 as replaced by Regulation (EU) 2026/1744 keeps these
    # words); Article 3's definitions, general-purpose AI models included,
    # are general provisions.
    "eu-ai-act:article-3": Row(ANY_AI_SYSTEM, (
        ("eu-ai-act:chapter-i", "GENERAL PROVISIONS"),
        ("eu-ai-act:article-4:paragraph-1", "Providers and deployers of AI systems shall take measures"),
    )),
    # Article 4a, inserted by Regulation (EU) 2026/1744 in Chapter I, holds
    # the rule Article 10(5) held (B132, spec G D-G68 (7)); under D-G62's rule
    # the part of the Act decides, so it takes Chapter I's value, Article 3's.
    "eu-ai-act:article-4a": Row(ANY_AI_SYSTEM, (
        ("eu-ai-act:chapter-i", "GENERAL PROVISIONS"),
    )),
    # Chapter II; Article 5(2) to 5(7), the conditions on the permitted use
    # of real-time remote biometric identification, stay in its rules.
    "eu-ai-act:article-5": Row(PROHIBITED_AI_PRACTICE, (
        ("eu-ai-act:chapter-ii", "PROHIBITED AI PRACTICES"),
    )),
    # Chapter III (Articles 6 to 49); the extraction scope holds 6 to 27.
    **{f"eu-ai-act:article-{number}": Row(HIGH_RISK_AI_SYSTEM, _CHAPTER_III) for number in range(6, 28)},
    "eu-ai-act:article-50": Row(ARTICLE_50_AI_SYSTEM, (
        ("eu-ai-act:chapter-iv", "TRANSPARENCY OBLIGATIONS FOR PROVIDERS AND DEPLOYERS OF CERTAIN AI SYSTEMS"),
    )),
    "eu-ai-act:article-72": Row(HIGH_RISK_AI_SYSTEM, (
        ("eu-ai-act:article-72",
         "Post-market monitoring by providers and post-market monitoring plan for high-risk AI systems"),
    )),
    # Article 73's title, "Reporting of serious incidents", names no system;
    # its paragraphs 1, 9 and 10 name high-risk AI systems.
    "eu-ai-act:article-73": Row(HIGH_RISK_AI_SYSTEM, (
        ("eu-ai-act:article-73:paragraph-1", "Providers of high-risk AI systems placed on the Union market"),
        ("eu-ai-act:article-73:paragraph-9", "For high-risk AI systems referred to in Annex III"),
        ("eu-ai-act:article-73:paragraph-10", "For high-risk AI systems which are safety components of devices"),
    )),
    "eu-ai-act:annex-iii": Row(HIGH_RISK_AI_SYSTEM, (
        ("eu-ai-act:annex-iii", "High-risk AI systems referred to in Article 6(2)"),
    )),
    "eu-ai-act:annex-iv": Row(HIGH_RISK_AI_SYSTEM, (
        ("eu-ai-act:annex-iv", "Technical documentation referred to in Article 11(1)"),
        ("eu-ai-act:article-11:paragraph-1", "The technical documentation of a high-risk AI system"),
    )),
}


def category_for(source_node_id: object) -> str | None:
    """The rule's value for a norm on this source unit, or None outside the table.

    eu-ai-act:article-6:paragraph-4 -> high_risk_ai_system;
    eu-ai-act:annex-iii:point-1:a -> high_risk_ai_system;
    eu-ai-act:article-4:paragraph-1 -> None (not in the extraction scope).
    The whole Article or Annex segment is matched, so article-5 never reads
    as article-50. Anything that is not a string reads as outside the table.
    """
    if not isinstance(source_node_id, str):
        return None
    row = RULE_TABLE.get(":".join(source_node_id.split(":")[:2]))
    return row.value if row is not None else None

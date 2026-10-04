"""Application dates as data: Article 113 as amended, provision by provision.

@implements: DEC-23
@implements: DEC-14
@grounded_by: REF-01, REF-02

Article 113 of Regulation (EU) 2024/1689, as amended by Regulation (EU)
2026/1744 (the Digital Omnibus, Article 1, point (40)), dates provisions,
not routes: Chapters I and II from 2 February 2025, except Article 5(1),
points (ba) and (bb), and Article 5(1a) and (1b) from 2 December 2026;
Chapter III Section 4, Chapters V, VII and XII and Article 78 from 2 August
2025, except Article 101; Chapter III Sections 1 to 3, except Article 6(5),
from 2 December 2027 for systems high-risk under Article 6(2) and Annex III
and from 2 August 2028 under Article 6(1) and Annex I; Articles 102 to 110
from 27 July 2026; the rest from 2 August 2026 (thesis task B132, spec G
D-G68 (6), ruling R7, in the private research repository).

An Annex takes the date of the Article that brings it into application
(ruling R24): Annex I that of Article 6(1) and Annex III that of Article
6(2), each on the route point (c) names it with ((ii) and (i)), Annex IV
that of Article 11(1), on the answer's route (both points while the route
is unknown); descendants included. The provision stays the Annex, and the
entry names the Article it follows (applies_through). Another Annex takes
the general date.

ROWS is the reviewed table: each row quotes the words of the Layer 1 node
that holds its point, verbatim (tests/unit/test_application_dates.py
checks every quotation against layer1.json). A wording the Omnibus
inserted or replaced applies no earlier than the Omnibus's entry into
force, 27 July 2026 (its Article 4, quoted in OMNIBUS_ENTRY_INTO_FORCE),
so such a node carries the later of the two dates. Article 111(4) is a
transitional note on Article 50(2), never the date of Article 50. A date
is data, never control flow (DEC-14): no rule of the classifier or of the
requirements reads it. Chapter and Section membership is read from the
Layer 1 dump's HAS_SECTION and HAS_ARTICLE edges, never typed here.
Deterministic, no model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tere4ai.parse_legal_structure.amendments import OMNIBUS_ACT, OMNIBUS_IN_FORCE

BASE_ACT = "Regulation (EU) 2024/1689"
LEGAL_TEXT_AMENDED = f"{BASE_ACT} as amended by {OMNIBUS_ACT}"
OMNIBUS_SOURCE_DOCUMENT = "src:omnibus-com-2025-836"
OJ_CITATION = "OJ L, 2026/1744, 24.7.2026"

ARTICLE_113 = "eu-ai-act:article-113:paragraph-1"

# The two routes of Article 113, third paragraph, point (c).
ROUTE_ANNEX_III = "annex_iii"
ROUTE_ANNEX_I = "annex_i"


@dataclass(frozen=True)
class Row:
    """One point of Article 113: its date, how the Act cites it, the node
    that holds its words, those words verbatim, and what applies from it."""

    applies_from: str
    cited_as: str
    basis_node: str
    wording: str
    meaning: str


ROWS: dict[str, Row] = {
    "general": Row(
        "2026-08-02", "Article 113, second paragraph", ARTICLE_113,
        "It shall apply from 2 August 2026.",
        "the Regulation applies from this date, except where Article 113, third paragraph, provides otherwise",
    ),
    "a": Row(
        "2025-02-02", "Article 113, third paragraph, point (a)", f"{ARTICLE_113}:point-a",
        "Chapters I and II shall apply from 2 February 2025",
        "Chapters I and II apply from this date",
    ),
    "a_exception": Row(
        "2026-12-02", "Article 113, third paragraph, point (a)", f"{ARTICLE_113}:point-a",
        "with the exception of Article 5(1), first subparagraph, points (ba) and (bb), and Article 5(1a) "
        "and (1b) which shall apply from 2 December 2026",
        "Article 5(1), first subparagraph, points (ba) and (bb), and Article 5(1a) and (1b) apply from this date",
    ),
    "b": Row(
        "2025-08-02", "Article 113, third paragraph, point (b)", f"{ARTICLE_113}:point-b",
        "Chapter III Section 4, Chapter V, Chapter VII and Chapter XII and Article 78 shall apply from "
        "2 August 2025, with the exception of Article 101",
        "Chapter III Section 4, Chapters V, VII and XII and Article 78 apply from this date, except Article 101",
    ),
    "c_i": Row(
        "2027-12-02", "Article 113, third paragraph, point (c)(i)", f"{ARTICLE_113}:point-c:point-i",
        "2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III",
        "Chapter III, Sections 1, 2 and 3, except Article 6(5), apply from this date as regards AI systems "
        "classified as high-risk pursuant to Article 6(2) and Annex III",
    ),
    "c_ii": Row(
        "2028-08-02", "Article 113, third paragraph, point (c)(ii)", f"{ARTICLE_113}:point-c:point-ii",
        "2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I",
        "Chapter III, Sections 1, 2 and 3, except Article 6(5), apply from this date as regards AI systems "
        "classified as high-risk pursuant to Article 6(1) and Annex I",
    ),
    "d": Row(
        "2026-07-27", "Article 113, third paragraph, point (d)", f"{ARTICLE_113}:point-d",
        "Articles 102 to 110 shall apply from 27 July 2026",
        "Articles 102 to 110 apply from this date",
    ),
}

# The Omnibus's Article 4, verbatim from the frozen Formex of the Omnibus
# (L_202601744EN.000101.fmx.xml); published 24.7.2026, so in force from
# 27 July 2026 (OMNIBUS_IN_FORCE).
OMNIBUS_ENTRY_INTO_FORCE = (
    "This Regulation shall enter into force on the third day following that of its publication in the "
    "Official Journal of the European Union"
)
INSERTED_WORDING_NOTE = (
    f"wording inserted or replaced by {OMNIBUS_ACT} applies no earlier than its entry into force on "
    f"27 July 2026 ({OMNIBUS_ACT}, Article 4: \"{OMNIBUS_ENTRY_INTO_FORCE}\")"
)
COMPOSED_NOTE = (
    f"parts of this provision were inserted or replaced by {OMNIBUS_ACT} and apply no earlier than "
    "27 July 2026"
)

# Article 5 units the point (a) exception names.
ARTICLE_5_EXCEPTION_UNITS = (
    "eu-ai-act:article-5:paragraph-1:point-ba",
    "eu-ai-act:article-5:paragraph-1:point-bb",
    "eu-ai-act:article-5:paragraph-1a",
    "eu-ai-act:article-5:paragraph-1b",
)
ARTICLE_6_PARAGRAPH_5 = "eu-ai-act:article-6:paragraph-5"
ARTICLE_50 = "eu-ai-act:article-50"
ARTICLE_50_PARAGRAPH_2 = "eu-ai-act:article-50:paragraph-2"
ARTICLE_111_PARAGRAPH_4 = "eu-ai-act:article-111:paragraph-4"
ARTICLE_111_4_WORDING = (
    "Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, "
    "video or text content, that have been placed on the market before 2 August 2026 shall take the "
    "necessary steps in order to comply with Article 50(2) by 2 December 2026."
)
ARTICLE_111_4_NOTE = (
    f"transitional rule, Article 111(4): \"{ARTICLE_111_4_WORDING}\"; it is not the date of Article 50"
)

# R24: an Annex dated through the Article that brings it into application;
# the route is the one point (c) names the Annex with, or None to follow the
# answer's route.
ANNEX_APPLIES_THROUGH: dict[str, tuple[str, str | None, str]] = {
    "eu-ai-act:annex-i": (
        "eu-ai-act:article-6:paragraph-1", ROUTE_ANNEX_I,
        "Annex I applies through Article 6(1), and Article 113, third paragraph, point (c)(ii) names it",
    ),
    "eu-ai-act:annex-iii": (
        "eu-ai-act:article-6:paragraph-2", ROUTE_ANNEX_III,
        "Annex III applies through Article 6(2), and Article 113, third paragraph, point (c)(i) names it",
    ),
    "eu-ai-act:annex-iv": (
        "eu-ai-act:article-11:paragraph-1", None,
        "Annex IV applies through Article 11(1), the technical documentation of a high-risk AI system",
    ),
}

_B_CHAPTERS = frozenset({"eu-ai-act:chapter-v", "eu-ai-act:chapter-vii", "eu-ai-act:chapter-xii"})
_A_CHAPTERS = frozenset({"eu-ai-act:chapter-i", "eu-ai-act:chapter-ii"})
_C_SECTIONS = frozenset({f"eu-ai-act:chapter-iii:section-{n}" for n in (1, 2, 3)})
_B_SECTION = "eu-ai-act:chapter-iii:section-4"


def legal_text(dump: dict[str, Any]) -> str:
    """The text an answer on this dump follows: the Act as amended when the
    Omnibus SourceDocument is merged into the base (B132), else as enacted."""
    for node in dump.get("nodes", []):
        if node.get("id") == OMNIBUS_SOURCE_DOCUMENT:
            return LEGAL_TEXT_AMENDED if node.get("merged_into_base") is True else BASE_ACT
    return BASE_ACT


def _article_of(node_id: str) -> str | None:
    """The Article a provision belongs to; a definition is Article 3's."""
    if node_id.startswith("eu-ai-act:definition:"):
        return "eu-ai-act:article-3"
    parts = node_id.split(":")
    if len(parts) >= 2 and parts[0] == "eu-ai-act" and parts[1].startswith("article-"):
        return ":".join(parts[:2])
    return None


def _containers(article_id: str, dump: dict[str, Any]) -> set[str]:
    """The Section and Chapter nodes above an Article, from the dump's edges."""
    parent = {e["to"]: e["from"] for e in dump.get("edges", [])
              if e.get("edge_type") in ("HAS_ARTICLE", "HAS_SECTION")}
    found: set[str] = set()
    current = parent.get(article_id)
    while current is not None and current not in found:
        found.add(current)
        current = parent.get(current)
    return found


def _within(node_id: str, unit_id: str) -> bool:
    return node_id == unit_id or node_id.startswith(unit_id + ":")


def _annex_through(node_id: str) -> tuple[str, str | None, str] | None:
    """The Article an Annex unit applies through (R24), or None."""
    for annex, through in ANNEX_APPLIES_THROUGH.items():
        if _within(node_id, annex):
            return through
    return None


def _row_keys(node_id: str, dump: dict[str, Any], route: str | None) -> list[str]:
    article_id = _article_of(node_id)
    if article_id is None:
        return ["general"]  # another Annex, or the Regulation
    if any(_within(node_id, unit) for unit in ARTICLE_5_EXCEPTION_UNITS):
        return ["a_exception"]
    if _within(node_id, ARTICLE_6_PARAGRAPH_5):
        return ["general"]
    label = article_id.split("article-", 1)[1]
    if label == "101":
        return ["general"]
    if label.isdigit() and 102 <= int(label) <= 110:
        return ["d"]
    if label == "78":
        return ["b"]
    containers = _containers(article_id, dump)
    if _B_SECTION in containers or containers & _B_CHAPTERS:
        return ["b"]
    if containers & _C_SECTIONS:
        if route == ROUTE_ANNEX_III:
            return ["c_i"]
        if route == ROUTE_ANNEX_I:
            return ["c_ii"]
        return ["c_i", "c_ii"]
    if containers & _A_CHAPTERS:
        return ["a"]
    return ["general"]


def provision_dates(node_id: str, dump: dict[str, Any], route: str | None = None) -> list[dict[str, Any]]:
    """The dates a provision applies from, one entry per Article 113 point.

    route is ROUTE_ANNEX_III, ROUTE_ANNEX_I or None; it chooses between
    point (c)(i) and (c)(ii) for Chapter III Sections 1 to 3, and with None
    both are returned, each saying which systems it is for. An Annex is
    dated through its Article (ANNEX_APPLIES_THROUGH). Each entry:
    provision, applies_through (the Article an Annex follows, else None),
    date, meaning, legal_status, source (the point as the Act cites it, with
    the Official Journal reference), basis_node, wording (verbatim from
    basis_node), notes.
    """
    node = next((n for n in dump.get("nodes", []) if n.get("id") == node_id), None)
    amendment = (node or {}).get("amendment")
    through = _annex_through(node_id)
    dated_as, dated_route = node_id, route
    if through is not None:
        dated_as = through[0]
        dated_route = through[1] if through[1] is not None else route
    entries: list[dict[str, Any]] = []
    for key in _row_keys(dated_as, dump, dated_route):
        row = ROWS[key]
        date = row.applies_from
        notes: list[str] = [through[2]] if through is not None else []
        if date < OMNIBUS_IN_FORCE and amendment in ("inserted", "replaced"):
            date = OMNIBUS_IN_FORCE
            notes.append(INSERTED_WORDING_NOTE)
        elif date < OMNIBUS_IN_FORCE and amendment == "composed":
            notes.append(COMPOSED_NOTE)
        if node_id in (ARTICLE_50, ARTICLE_50_PARAGRAPH_2):
            notes.append(ARTICLE_111_4_NOTE)
        entries.append({
            "provision": node_id,
            "applies_through": through[0] if through is not None else None,
            "date": date,
            "meaning": row.meaning,
            "legal_status": "in_force",
            "source": f"{row.cited_as}, of {LEGAL_TEXT_AMENDED} ({OJ_CITATION})",
            "basis_node": row.basis_node,
            "wording": row.wording,
            "notes": notes,
        })
    return entries


def dates_for(node_ids: list[str], dump: dict[str, Any], route: str | None = None) -> list[dict[str, Any]]:
    """provision_dates for each node id, in order, each id once."""
    out: list[dict[str, Any]] = []
    for node_id in dict.fromkeys(node_ids):
        out.extend(provision_dates(node_id, dump, route))
    return out


def fria_applies_from() -> dict[str, str]:
    """Article 27's date for the FRIA block: point (c)(i), since Article
    27(1) concerns high-risk systems referred to in Article 6(2)."""
    row = ROWS["c_i"]
    return {
        "date": row.applies_from,
        "meaning": row.meaning + "; Article 27 is in Chapter III, Section 3",
        "legal_status": "in_force",
        "source": f"{row.cited_as}, of {LEGAL_TEXT_AMENDED} ({OJ_CITATION})",
    }

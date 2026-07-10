"""Rule-based cross-reference resolver for Layer 1 (build pipeline step 3).

@implements: DEC-02
@grounded_by: REF-26, REF-29

Deterministic rule pass over every Paragraph text in a Layer 1 dump
(schema/json_schemas/layer1_dump.schema.json). No LLM is involved here;
LLM repair of unresolved or ambiguous cases is a later milestone and its
inputs are exactly the review_queue items this module emits.

Rules (docs/architecture.md Sections 2, 6 step 3, 16 DEC-02):
- "Article N", "Articles N and M", "Articles N to M" resolve to REFERS_TO
  edges from the paragraph's parent Article node to eu-ai-act:article-N,
  expanding conjunctions and ranges.
- "Annex ROMAN" and "Annexes I and III" resolve to eu-ai-act:annex-<roman
  lowercase>; "Chapter ROMAN" resolves to eu-ai-act:chapter-<roman lowercase>.
- Self-references ("this Article", "this Regulation", bare "paragraph N"
  without an Article context) are internal and produce no edge.
- References to other instruments ("Article 4(2) of Regulation (EU)
  2016/679", "Article 6 of Directive (EU) 2020/1828") never resolve to
  eu-ai-act nodes; they go to the review_queue with reason
  "external_instrument".
- Mentions whose target node does not exist in the dump go to the
  review_queue with reason "unresolved_target".
- Edges are deduplicated on (from, to); the first citation_text wins.

Every emitted edge carries full provenance: provenance_class
RESOLVED_DETERMINISTIC, method crossref_rule_v1, confidence 1.0,
review_status auto_accepted, the referencing paragraph's source_span_id,
citation_text, and the build_id copied from the dump build block.

Reified cross-references (Section 1 lists CrossReference as a Layer 1 node
type): every resolved mention additionally becomes a CrossReference node
carrying citation_text and the referencing paragraph's span, connected by
HAS_CROSS_REFERENCE (paragraph -> node) and RESOLVES_TO (node -> target).
RESOLVES_TO targets are paragraph-level where determinable: an "Article
6(2)"-style token resolves to eu-ai-act:article-6:paragraph-2 when that
node exists, falling back to the article. The coarse article-to-article
REFERS_TO edges are kept unchanged for navigation and regression parity.
"""

from __future__ import annotations

import re
from typing import Any

NODE_ID_PREFIX = "eu-ai-act"
METHOD = "crossref_rule_v1"

# ---------------------------------------------------------------------------
# Roman numeral helpers (Annex and Chapter numbers are Roman in Layer 1 IDs).
# ---------------------------------------------------------------------------

_ROMAN_PAIRS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(roman: str) -> int:
    total = 0
    prev = 0
    for char in reversed(roman.upper()):
        value = _ROMAN_VALUES[char]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def _int_to_roman(number: int) -> str:
    out = []
    for value, symbol in _ROMAN_PAIRS:
        while number >= value:
            out.append(symbol)
            number -= value
    return "".join(out)


# ---------------------------------------------------------------------------
# Mention grammars.
# ---------------------------------------------------------------------------

# An article number, optionally with a paragraph designator: 6, 6(2).
_NUM = r"\d+(?:\(\d+\))?"
# Connectors inside a list of numbers: ", " / " and " / " or " / " to ".
_CONN = r"(?:\s*,\s*|\s+and\s+|\s+or\s+|\s+to\s+)"
# A valid Roman numeral, not running into a longer word ("Annex Implementation").
_ROMAN_TOKEN = (
    r"(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})(?![A-Za-z])"
)

_ARTICLE_MENTION = re.compile(rf"\bArticles?\s+{_NUM}(?:{_CONN}{_NUM})*")
_ANNEX_MENTION = re.compile(rf"\bAnnex(?:es)?\s+{_ROMAN_TOKEN}(?:{_CONN}{_ROMAN_TOKEN})*")
_CHAPTER_MENTION = re.compile(rf"\bChapters?\s+{_ROMAN_TOKEN}(?:{_CONN}{_ROMAN_TOKEN})*")

# Citation tail tokens that may sit between the mention and "of <Instrument>":
# ", point (c)", "(2)", "first subparagraph", and similar.
_TAIL = (
    r"(?:\s*(?:,|and|or|to|points?|paragraphs?|subparagraphs?"
    r"|first|second|third|fourth|fifth|\([A-Za-z0-9]+\)))*"
)
# Another instrument's identity: "Regulation (EU) 2016/679",
# "Directive (EU) 2020/1828", "Regulation (EC) No 300/2008", "Decision ...".
_INSTRUMENT = (
    r"(?:Regulation|Directive|Decision)"
    r"(?:\s*\((?:EU|EC|EEC|EU,\s*Euratom)\))?"
    r"(?:\s*No\.?)?"
    r"(?:\s*\d{1,4}/\d{1,4}(?:/(?:EU|EC|EEC))?)?"
)
# "... of Regulation (EU) 2016/679" right after the mention: external.
_EXT_AFTER = re.compile(rf"^{_TAIL}\s*of\s+(?:the\s+)?(?P<instrument>{_INSTRUMENT})")
# "... of this Regulation/Article/Chapter": explicitly internal, overrides.
_THIS_AFTER = re.compile(
    rf"^{_TAIL}\s*of\s+this\s+(?:Regulation|Article|Chapter|Section|Annex|paragraph)\b"
)
# Instrument citation with a number shortly before the mention, in the same
# clause (no sentence boundary between): external.
_EXT_BEFORE = re.compile(
    r"(?:Regulation|Directive|Decision)\s*(?:\((?:EU|EC|EEC|EU,\s*Euratom)\))?"
    r"\s*(?:No\.?\s*)?\d[\d/]*(?:/(?:EU|EC|EEC))?[^.;]*$"
)

_EXTERNAL_WINDOW = 60

_PARAGRAPH_ID = re.compile(r"^(?P<article>.*:article-\d+):paragraph-\d+$")
_TOKEN_TO = re.compile(rf"{_NUM}|\bto\b")
_TOKEN_ROMAN_TO = re.compile(rf"{_ROMAN_TOKEN}|\bto\b")


def _external_citation(text: str, start: int, end: int) -> str | None:
    """Return the full external citation text if this mention points at
    another instrument, else None. Checks up to 60 chars on each side."""
    window_after = text[end:end + _EXTERNAL_WINDOW]
    if _THIS_AFTER.match(window_after):
        return None
    match = _EXT_AFTER.match(window_after)
    if match:
        return text[start:end + match.end()]
    window_before = text[max(0, start - _EXTERNAL_WINDOW):start]
    match = _EXT_BEFORE.search(window_before)
    if match:
        return (window_before[match.start():] + text[start:end]).strip()
    return None


def _expand(tokens: list[str], to_int) -> list[int]:
    """Expand a token list like ['8', 'to', '15'] or ['I', 'III'] into
    the full list of integer numbers, honoring 'to' ranges."""
    numbers: list[int] = []
    prev: int | None = None
    pending_range = False
    for token in tokens:
        if token == "to":
            pending_range = prev is not None
            continue
        value = to_int(token)
        if pending_range and prev is not None and value > prev:
            numbers.extend(range(prev + 1, value + 1))
        else:
            numbers.append(value)
        prev = value
        pending_range = False
    return numbers


def _article_targets(citation: str) -> list[str]:
    tokens = _TOKEN_TO.findall(citation)
    numbers = _expand(tokens, lambda t: int(re.match(r"\d+", t).group(0)))
    return [f"{NODE_ID_PREFIX}:article-{n}" for n in numbers]


def _precise_article_targets(citation: str, node_ids: set[str]) -> list[str]:
    """Article targets refined to paragraph level where determinable.

    A token like "6(2)" resolves to eu-ai-act:article-6:paragraph-2 when
    that node exists in the dump; bare numbers and range expansions stay at
    article level. Order and dedup follow first occurrence.
    """
    tokens = _TOKEN_TO.findall(citation)
    coarse = _expand(tokens, lambda t: int(re.match(r"\d+", t).group(0)))
    precise_by_article: dict[int, str] = {}
    for token in tokens:
        match = re.match(r"(\d+)\((\d+)\)", token)
        if not match:
            continue
        article_no, paragraph_no = int(match.group(1)), int(match.group(2))
        candidate = f"{NODE_ID_PREFIX}:article-{article_no}:paragraph-{paragraph_no}"
        if candidate in node_ids:
            precise_by_article[article_no] = candidate
    targets: list[str] = []
    for number in coarse:
        target = precise_by_article.get(number, f"{NODE_ID_PREFIX}:article-{number}")
        if target not in targets:
            targets.append(target)
    return targets


def _annex_targets(citation: str) -> list[str]:
    tokens = _TOKEN_ROMAN_TO.findall(citation)
    numbers = _expand(tokens, _roman_to_int)
    return [f"{NODE_ID_PREFIX}:annex-{_int_to_roman(n).lower()}" for n in numbers]


def _chapter_targets(citation: str) -> list[str]:
    tokens = _TOKEN_ROMAN_TO.findall(citation)
    numbers = _expand(tokens, _roman_to_int)
    return [f"{NODE_ID_PREFIX}:chapter-{_int_to_roman(n).lower()}" for n in numbers]


_MENTION_RULES = (
    (_ARTICLE_MENTION, _article_targets),
    (_ANNEX_MENTION, _annex_targets),
    (_CHAPTER_MENTION, _chapter_targets),
)


def _parent_article(paragraph_id: str, has_paragraph_parents: dict[str, str]) -> str:
    """The node the REFERS_TO edge starts from: the paragraph's parent
    Article, derived from the deterministic ID convention (Section 2),
    with the HAS_PARAGRAPH edges as fallback."""
    match = _PARAGRAPH_ID.match(paragraph_id)
    if match:
        return match.group("article")
    return has_paragraph_parents.get(paragraph_id, paragraph_id)


def resolve(dump: dict) -> dict:
    """Apply the cross-reference rule pass to a Layer 1 dump.

    Returns a new dump dict (input is not mutated) with REFERS_TO edges
    appended to edges and unresolved or external mentions appended to
    review_queue.
    """
    build_id = dump.get("build", {}).get("build_id", "")
    nodes = dump.get("nodes", [])
    existing_edges = dump.get("edges", [])
    node_ids = {n["id"] for n in nodes if "id" in n}
    has_paragraph_parents = {
        e["to"]: e["from"] for e in existing_edges if e.get("edge_type") == "HAS_PARAGRAPH"
    }

    new_nodes: list[dict[str, Any]] = []
    new_edges: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_queue: set[tuple[str, str, str, str]] = set()
    seen_xrefs: set[tuple[str, str]] = set()
    edge_counter = 0
    queue_counter = 0
    xref_counter = 0

    def _edge_provenance(span_id: str, citation: str) -> dict[str, Any]:
        return {
            "provenance_class": "RESOLVED_DETERMINISTIC",
            "method": METHOD,
            "confidence": 1.0,
            "review_status": "auto_accepted",
            "source_span_id": span_id,
            "citation_text": citation,
            "build_id": build_id,
        }

    def _reify(
        paragraph: dict[str, Any],
        citation: str,
        span_id: str,
        resolved_targets: list[str],
    ) -> None:
        """CrossReference node + HAS_CROSS_REFERENCE + RESOLVES_TO edges.

        One node per (paragraph, citation_text); numbered in document
        order, which is deterministic for a fixed input dump.
        """
        nonlocal xref_counter, edge_counter
        if not resolved_targets:
            return
        key = (paragraph["id"], citation)
        if key in seen_xrefs:
            return
        seen_xrefs.add(key)
        xref_counter += 1
        xref_id = f"{NODE_ID_PREFIX}:xref-{xref_counter}"
        node: dict[str, Any] = {
            "id": xref_id,
            "type": "CrossReference",
            "layer": 1,
            "citation_text": citation,
            "from_node_id": paragraph["id"],
        }
        span = paragraph.get("source_span")
        if isinstance(span, dict):
            node["source_span"] = span
        new_nodes.append(node)
        edge_counter += 1
        new_edges.append(
            {
                "edge_id": f"xrefn:{paragraph['id']}->{xref_id}:{edge_counter}",
                "edge_type": "HAS_CROSS_REFERENCE",
                "from": paragraph["id"],
                "to": xref_id,
                **_edge_provenance(span_id, citation),
            }
        )
        for target in resolved_targets:
            edge_counter += 1
            new_edges.append(
                {
                    "edge_id": f"xrefn:{xref_id}->{target}:{edge_counter}",
                    "edge_type": "RESOLVES_TO",
                    "from": xref_id,
                    "to": target,
                    **_edge_provenance(span_id, citation),
                }
            )

    def _enqueue(from_id: str, citation_text: str, span_id: str, reason: str) -> None:
        nonlocal queue_counter
        key = (from_id, citation_text, span_id, reason)
        if key in seen_queue:
            return
        seen_queue.add(key)
        queue_counter += 1
        queue.append({
            "item_id": f"xrefq:{queue_counter}",
            "kind": "cross_reference",
            "citation_text": citation_text,
            "source_span_id": span_id,
            "from_node_id": from_id,
            "reason": reason,
        })

    for node in nodes:
        if node.get("type") != "Paragraph":
            continue
        text = node.get("text") or ""
        if not text:
            continue
        span_id = (node.get("source_span") or {}).get("span_id")
        if not span_id:
            continue
        from_id = _parent_article(node["id"], has_paragraph_parents)

        for mention_re, targets_of in _MENTION_RULES:
            for match in mention_re.finditer(text):
                citation = match.group(0)
                external = _external_citation(text, match.start(), match.end())
                if external is not None:
                    _enqueue(from_id, external, span_id, "external_instrument")
                    continue
                resolved: list[str] = []
                for target in targets_of(citation):
                    if target not in node_ids:
                        _enqueue(from_id, citation, span_id, "unresolved_target")
                        continue
                    resolved.append(target)
                    pair = (from_id, target)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    edge_counter += 1
                    new_edges.append({
                        "edge_id": f"xref:{from_id}->{target}:{edge_counter}",
                        "edge_type": "REFERS_TO",
                        "from": from_id,
                        "to": target,
                        **_edge_provenance(span_id, citation),
                    })
                # Reified node with paragraph-precise targets: article
                # mentions get "6(2)"-style refinement; annex and chapter
                # targets are already as precise as the citation grammar.
                if targets_of is _article_targets:
                    precise = [
                        t
                        for t in _precise_article_targets(citation, node_ids)
                        if t in node_ids
                    ]
                else:
                    precise = resolved
                _reify(node, citation, span_id, precise)

    result = dict(dump)
    result["nodes"] = list(nodes) + new_nodes
    result["edges"] = list(existing_edges) + new_edges
    result["review_queue"] = list(dump.get("review_queue", [])) + queue
    return result

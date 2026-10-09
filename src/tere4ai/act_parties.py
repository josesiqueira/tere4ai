"""The Act's parties: one list, one normaliser, one reader of a norm's addressee.

@implements: DEC-27
@grounded_by: REF-11

schema/act_parties.json holds the one list of the parties the EU AI Act
makes the subject of a duty, a power or a right (spec G D-G80 (2)). Every
reader that routes or groups norms by party reads it through this module:
the normaliser that places a written addressee on one value (D-G80 (4)),
the reader of a norm's addressee in either norms schema version (D-G80
(21)), and the rule of which request a norm is served to (D-G80 (10)).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ACT_PARTIES_PATH = REPO_ROOT / "schema" / "act_parties.json"

METHOD = "act_parties_v1"
UNSPECIFIED = "unspecified_needs_review"
OPERATOR_GENERAL = "operator_general"
SENTINELS = (OPERATOR_GENERAL, UNSPECIFIED)

# Leading words dropped before a phrase is read (D-G80 (4), first step).
_LEADING = ("the", "a", "an", "any", "each", "such", "that", "relevant")
# The words that end the governing part of a phrase (D-G80 (4), third step).
_RELATIVE_MARKERS = (" that ", " which ", " who ", " whose ", " established ",
                     " placed ", " participating ", " referred to ")
_DESCRIPTOR_TAIL = re.compile(
    r"\s+of\s+(?:such\s+)?(?:the\s+)?(?:high-risk\s+)?(?:general-purpose\s+)?ai\s+(?:systems?|models?).*$"
)
_COORDINATION = {"and", "or", "and/or", "other", "the", "a", "an", "any"}
# The words that may stand before the head without changing which party it
# names ("national market surveillance authorities", "the EU AI Office";
# plan R91). Any other first word is the head, and a head that is not a
# party leaves the phrase unplaced (plan R91, review Important 2).
# "european" before a party's name ("the European Commission"): plan R99
_HEAD_MODIFIERS = frozenset({"national", "eu", "union", "european"})
# A value whose act_term is one word the Act also uses for something else is
# matched by its phrases only: "subject" is the grammatical subject too.
_TERM_NOT_MATCHED = frozenset({"subject_of_testing"})


@dataclass(frozen=True)
class Party:
    value: str
    act_term: str | None
    kind: str
    ground: str | None
    definition_node_id: str | None
    phrases: tuple[tuple[str, str], ...]
    also_served_to: tuple[str, ...]


@lru_cache(maxsize=1)
def parties() -> tuple[Party, ...]:
    """The list, in the file's order."""
    data = json.loads(ACT_PARTIES_PATH.read_text(encoding="utf-8"))
    return tuple(
        Party(
            value=p["value"], act_term=p["act_term"], kind=p["kind"], ground=p["ground"],
            definition_node_id=p["definition_node_id"],
            phrases=tuple((ph["text"], ph["ground"]) for ph in p["phrases"]),
            also_served_to=tuple(p["also_served_to"]),
        )
        for p in data["parties"]
    )


def values() -> tuple[str, ...]:
    return tuple(p.value for p in parties())


def values_of_kind(kind: str) -> tuple[str, ...]:
    return tuple(p.value for p in parties() if p.kind == kind)


def ai_act_roles() -> tuple[str, ...]:
    """Article 3(8)'s six AI Act roles, in its order."""
    return values_of_kind("role")


def addressee_condition() -> tuple[str, ...]:
    """DEC-19's addressee condition from v5: the six AI Act roles and the two sentinels."""
    return ai_act_roles() + SENTINELS


def requestable() -> tuple[str, ...]:
    """The values a request may name (a sentinel names no party, D-G80 (10))."""
    return tuple(v for v in values() if v not in SENTINELS)


def _fold_word(word: str) -> str:
    word = word.strip("'")
    if word.endswith("'s"):
        word = word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("‘", "'")
    return [_fold_word(w) for w in re.findall(r"[a-z0-9][a-z0-9'/-]*", text)]


@lru_cache(maxsize=1)
def _terms() -> tuple[tuple[tuple[str, ...], str], ...]:
    """Every matchable wording as folded words, with its value, longest first."""
    out: list[tuple[tuple[str, ...], str]] = []
    for p in parties():
        texts = [t for t, _g in p.phrases]
        if p.act_term and p.value not in _TERM_NOT_MATCHED:
            texts.append(p.act_term)
        for t in texts:
            words = _words(t)
            if words and words[0] in _LEADING:
                words = words[1:]
            out.append((tuple(words), p.value))
    return tuple(sorted(out, key=lambda item: -len(item[0])))


def _strip_leading(text: str) -> str:
    changed = True
    while changed:
        changed = False
        for word in _LEADING:
            if text.startswith(word + " "):
                text = text[len(word) + 1:]
                changed = True
    return text


def _find(words: list[str]) -> list[tuple[int, int, str]]:
    """Non-overlapping term hits (start, end, value), longest first, in order."""
    taken = [False] * len(words)
    hits: list[tuple[int, int, str]] = []
    for term, value in _terms():
        n = len(term)
        for i in range(len(words) - n + 1):
            if tuple(words[i:i + n]) == term and not any(taken[i:i + n]):
                hits.append((i, i + n, value))
                for j in range(i, i + n):
                    taken[j] = True
    return sorted(hits)


def _after_of(words: list[str], start: int) -> bool:
    """The term at start follows " of " (an article between them allowed): a descriptor."""
    k = start - 1
    while k >= 0 and words[k] in ("the", "a", "an"):
        k -= 1
    return k >= 0 and words[k] == "of"


def _coordinated_after_descriptor(text: str) -> bool:
    """R98: after a descriptor ("of ... AI systems"), and before any relative
    marker, a party joined by "and" or "or" makes the phrase several parties."""
    match = re.search(r"\s+of\s+(?:such\s+)?(?:the\s+)?(?:high-risk\s+)?(?:general-purpose\s+)?ai\s+(?:systems?|models?)", text)
    if match is None:
        return False
    rest = text[match.end():]
    cut = min((rest.find(m) for m in _RELATIVE_MARKERS if m in rest), default=-1)
    if cut >= 0:
        rest = rest[:cut]
    words = _words(rest)
    for start, _end, _value in _find(words):
        k = start - 1
        while k >= 0 and words[k] in ("the", "a", "an", "any"):
            k -= 1
        if k >= 0 and words[k] in ("and", "or", "and/or"):
            return True
    return False


def place(phrase: Any) -> str | None:
    """The value a written addressee is placed on, or None when the list cannot place it.

    The five steps of spec G D-G80 (4), in order, so nothing is cut before
    the names in it are read; never a substring anywhere in the phrase.
    """
    if not isinstance(phrase, str) or not phrase.strip():
        return None
    text = " ".join(phrase.lower().replace("’", "'").split()).strip(" ,.;:")
    text = _strip_leading(text)
    if _coordinated_after_descriptor(text):
        return None  # R98: a party coordinated after a descriptor is still several parties
    # second step: the full name, with the descriptor tail removed or not
    for candidate in (text, _DESCRIPTOR_TAIL.sub("", text).strip(" ,.")):
        words = _words(candidate)
        for term, value in _terms():
            if tuple(words) == term:
                return value
    # third step: the parties in the governing part, a term after " of " left out
    governing = _DESCRIPTOR_TAIL.sub("", text)
    cut = min((governing.find(m) for m in _RELATIVE_MARKERS if m in governing), default=-1)
    if cut >= 0:
        governing = governing[:cut]
    words = _words(governing)
    hits = [h for h in _find(words) if not _after_of(words, h[0])]
    # a phrase is placed only when its head is a party (R91): a thing whose
    # words name a party that acts on it ("the report submitted by the
    # provider") is unplaced, and the build record lists it
    heads = (0, 1) if words and words[0] in _HEAD_MODIFIERS else (0,)
    if not hits or hits[0][0] not in heads:
        return None
    found = {value for _s, _e, value in hits}
    if len(found) == 1:
        return found.pop()
    between = [w for k in range(len(hits) - 1) for w in words[hits[k][1]:hits[k + 1][0]]]
    if all(w in _COORDINATION for w in between):
        return None  # several parties joined by a coordination: one norm per party
    # fourth step: the head, the term at the start of the governing part
    return hits[0][2]


# --- one reader of a norm's addressee, in either norms schema version (D-G80 (21))

V1_FIELDS = ("actor_explicit", "actor_inferred", "actor_inference_source_node_id",
             "actor_canonical", "actor_canonicalization_method")
V2_FIELDS = ("addressee_explicit", "addressee_inferred", "addressee_inference_source_node_id",
             "addressee", "addressee_method", "addressee_placement")


@dataclass(frozen=True)
class Addressee:
    explicit: str | None
    inferred: str | None
    source_node_id: str | None
    value: str
    placement: str  # "inferred", "placed" or "unplaced"


def _clean(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def is_v2(norm: dict[str, Any]) -> bool:
    """A norm written in norms schema version 2's names."""
    return any(key in norm for key in V2_FIELDS[:3])


def compute(explicit: Any, inferred: Any) -> tuple[str, str]:
    """(value, placement) from the two slots: the inferred value, else the
    written words placed by the normaliser, else unspecified_needs_review."""
    inferred = _clean(inferred)
    if inferred is not None:
        return inferred, "inferred"
    placed = place(_clean(explicit))
    if placed is None:
        return UNSPECIFIED, "unplaced"
    return placed, "placed"


def addressee_of(norm: dict[str, Any]) -> Addressee:
    """The norm's addressee, read from version 2's names or version 1's; the
    stored value is read as stored when its stamp is the current one, and
    computed otherwise (the disposable version 1 files)."""
    if is_v2(norm):
        explicit, inferred = norm.get("addressee_explicit"), norm.get("addressee_inferred")
        source = norm.get("addressee_inference_source_node_id")
        if norm.get("addressee_method") == METHOD and norm.get("addressee"):
            return Addressee(_clean(explicit), _clean(inferred), _clean(source),
                             str(norm["addressee"]), str(norm.get("addressee_placement") or ""))
    else:
        explicit, inferred = norm.get("actor_explicit"), norm.get("actor_inferred")
        source = norm.get("actor_inference_source_node_id")
    value, placement = compute(explicit, inferred)
    return Addressee(_clean(explicit), _clean(inferred), _clean(source), value, placement)


def addressee_fields(norm: dict[str, Any]) -> dict[str, Any]:
    """Version 2's six addressee fields for a norm of either version."""
    a = addressee_of(norm)
    return {
        "addressee_explicit": a.explicit,
        "addressee_inferred": a.inferred,
        "addressee_inference_source_node_id": a.source_node_id,
        "addressee": a.value,
        "addressee_method": METHOD,
        "addressee_placement": a.placement,
    }


def in_v2_names(norm: dict[str, Any]) -> dict[str, Any]:
    """A copy of the norm in version 2's names; version 1's actor keys dropped."""
    out = {k: v for k, v in norm.items() if k not in V1_FIELDS}
    out.update(addressee_fields(norm))
    return out


def payload_in_v2_names(payload: dict[str, Any]) -> dict[str, Any]:
    """A norms payload read into version 2's names in memory (the facade, the
    MCP server); the file on disk is never rewritten."""
    out = dict(payload)
    out["norms"] = [in_v2_names(n) for n in payload.get("norms", []) if isinstance(n, dict)]
    return out


def serves(value: str, requested: str) -> bool:
    """D-G80 (10): a norm whose addressee is value is served to a request for requested."""
    if value == requested:
        return True
    by_value = {p.value: p for p in parties()}
    party = by_value.get(value)
    if party is not None and requested in party.also_served_to:
        return True
    return value == OPERATOR_GENERAL and requested in ai_act_roles()

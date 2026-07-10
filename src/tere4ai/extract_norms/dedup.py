"""Norm near-duplicate detection: deterministic hygiene report for Layer 2.

@implements: DEC-03 (partial: norm de-duplication hygiene)
@grounded_by: REF-11, REF-12

An article often yields several NormativeStatements, and the generator can
emit two records for what a lawyer would call one norm (same actor, same
deontic force, near-identical action and object wording). This module finds
such pairs deterministically (token Jaccard over action plus object, within
blocks sharing source article, canonical actor, and deontic type), so a human
can merge or keep them deliberately. No model calls; the report is evidence
for the norm-quality discussion, never an automatic merge (the trust split:
rules surface candidates, humans decide).
"""

from __future__ import annotations

import re
from typing import Any

# Pairs at or above HIGH are near-duplicates; between REVIEW and HIGH they
# are flagged for human review only.
HIGH_SIMILARITY = 0.8
REVIEW_SIMILARITY = 0.6

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(norm: dict[str, Any]) -> frozenset[str]:
    text = f"{norm.get('action', '')} {norm.get('object', '')}".lower()
    return frozenset(_TOKEN_RE.findall(text))


def _article_of(source_node_id: str) -> str:
    """Blocking key: the article (or annex) part of an ELI-like node id."""
    parts = source_node_id.split(":")
    return ":".join(parts[:2]) if len(parts) >= 2 else source_node_id


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_near_duplicates(norms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """All pairs above REVIEW_SIMILARITY, most similar first.

    Blocking on (article, actor, deontic_type) keeps this O(block^2) instead
    of O(n^2) and encodes that two norms with different actors or deontic
    force are never duplicates of each other.
    """
    blocks: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for norm in norms:
        key = (
            _article_of(norm.get("source_node_id", "")),
            (norm.get("actor_explicit") or norm.get("actor_inferred") or "").lower(),
            (norm.get("deontic_type") or "").lower(),
        )
        blocks.setdefault(key, []).append(norm)

    pairs: list[dict[str, Any]] = []
    for (article, actor, deontic), members in blocks.items():
        if len(members) < 2:
            continue
        toks = [(n, _tokens(n)) for n in members]
        for i in range(len(toks)):
            for j in range(i + 1, len(toks)):
                score = jaccard(toks[i][1], toks[j][1])
                if score >= REVIEW_SIMILARITY:
                    a, b = toks[i][0], toks[j][0]
                    # Canonical within-pair order: the pair (x, y) is the same
                    # finding regardless of input order.
                    id_a, id_b = sorted((a["norm_id"], b["norm_id"]))
                    pairs.append(
                        {
                            "norm_a": id_a,
                            "norm_b": id_b,
                            "similarity": round(score, 3),
                            "band": "near_duplicate"
                            if score >= HIGH_SIMILARITY
                            else "review",
                            "article": article,
                            "actor": actor,
                            "deontic_type": deontic,
                            "verdicts": sorted(
                                {
                                    a.get("judge_verdict") or "none",
                                    b.get("judge_verdict") or "none",
                                }
                            ),
                        }
                    )
    pairs.sort(key=lambda p: (-p["similarity"], p["norm_a"], p["norm_b"]))
    return pairs


def summarize(pairs: list[dict[str, Any]], total_norms: int) -> dict[str, int]:
    return {
        "total_norms": total_norms,
        "pairs_flagged": len(pairs),
        "near_duplicate_pairs": sum(1 for p in pairs if p["band"] == "near_duplicate"),
        "review_pairs": sum(1 for p in pairs if p["band"] == "review"),
        "pairs_both_accepted": sum(
            1 for p in pairs if p["verdicts"] == ["accepted"]
        ),
    }

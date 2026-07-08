"""M4 evaluation metrics: pure functions over eval results and gold labels.

@implements: DEC-11
@grounded_by: REF-16, REF-15

Implements the Section 12 metric set that the M4 harness reports per
ablation condition: risk classification accuracy, runtime citation
completeness, hallucinated citation rate, judge false-accept and
false-reject rates, plus plain precision/recall/F1 helpers. Every function
here is pure and deterministic: no I/O, no model, no randomness. The
grounding target for the citation metrics is REF-16 (sibling systems ground
legal references correctly only around 50 to 68 percent of the time without
gating); the task split follows the REF-15 benchmark (classification,
retrieval, obligation generation, QA).

Conventions shared by the harness (harness.py):
- a "result" is one strategy answer for one item:
  {"answer_text": str, "citations": [node ids], "risk_category": str|None, ...}
- "results" maps item_id -> result for one strategy.
- "gold items" are the dicts of eval/gold/gold_seed.json (or the loaded
  benchmark items), each with "id", "kind", "gold", "gold_citations".
"""

from __future__ import annotations

from typing import Any

# Judge gold labels (annotation protocol, eval/gold/ANNOTATION_PROTOCOL.md).
JUDGE_GOLD_LABELS = ("accept", "reject")
# Judge verdicts as produced by the judges (tere4ai.judge.runtime_grounding).
JUDGE_VERDICTS = ("accepted", "rejected", "needs_human_review")


def precision(tp: int, fp: int) -> float:
    """tp / (tp + fp); 0.0 when the denominator is zero."""
    return tp / (tp + fp) if (tp + fp) else 0.0


def recall(tp: int, fn: int) -> float:
    """tp / (tp + fn); 0.0 when the denominator is zero."""
    return tp / (tp + fn) if (tp + fn) else 0.0


def f1(tp: int, fp: int, fn: int) -> float:
    """Harmonic mean of precision and recall; 0.0 when both are zero."""
    p = precision(tp, fp)
    r = recall(tp, fn)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def prf1(tp: int, fp: int, fn: int) -> dict[str, float]:
    """Precision, recall, and F1 in one dict, from raw counts."""
    return {"precision": precision(tp, fp), "recall": recall(tp, fn), "f1": f1(tp, fp, fn)}


def risk_classification_accuracy(
    results: dict[str, dict[str, Any]],
    gold_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Exact-match accuracy of risk_category on classification items.

    Only gold items of kind "classification" whose gold dict carries
    "risk_category" are scored. An item without a result, or a result whose
    risk_category is None, counts as wrong (the strategy failed to answer),
    never as skipped: silently dropping unanswered items would inflate the
    number.
    """
    correct = 0
    total = 0
    mismatches: list[dict[str, Any]] = []
    for item in gold_items:
        if item.get("kind") != "classification":
            continue
        gold_risk = (item.get("gold") or {}).get("risk_category")
        if gold_risk is None:
            continue
        total += 1
        predicted = (results.get(item["id"]) or {}).get("risk_category")
        if predicted == gold_risk:
            correct += 1
        else:
            mismatches.append({"id": item["id"], "gold": gold_risk, "predicted": predicted})
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "mismatches": mismatches,
    }


def citation_completeness(
    results: dict[str, dict[str, Any]],
    gold_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fraction of gold-required citations present in the predicted citations.

    Per item: |predicted intersect gold_citations| / |gold_citations|.
    Items with an empty gold_citations list are excluded (nothing is
    required, so completeness is undefined for them, not 1.0). Reports the
    macro average over scored items and the micro (pooled) counts.
    """
    per_item: dict[str, float] = {}
    found_total = 0
    required_total = 0
    for item in gold_items:
        gold_cites = item.get("gold_citations") or []
        if not gold_cites:
            continue
        predicted = set((results.get(item["id"]) or {}).get("citations") or [])
        found = sum(1 for c in gold_cites if c in predicted)
        per_item[item["id"]] = found / len(gold_cites)
        found_total += found
        required_total += len(gold_cites)
    macro = sum(per_item.values()) / len(per_item) if per_item else 0.0
    return {
        "macro_completeness": macro,
        "micro": {
            "found": found_total,
            "required": required_total,
            "completeness": found_total / required_total if required_total else 0.0,
        },
        "per_item": per_item,
    }


def hallucinated_citation_rate(
    results: dict[str, dict[str, Any]],
    graph_node_ids: set[str],
) -> dict[str, Any]:
    """Fraction of cited node ids that do not exist in the graph dump.

    A hallucinated citation is any predicted citation absent from the set of
    real node ids (data/graph_dumps/layer1.json). Pooled over all items of
    one strategy; duplicate citations within one item are counted once per
    item (a set), so a repeated fabrication is not double-counted there.
    """
    cited_total = 0
    hallucinated_ids: list[str] = []
    for item_id in sorted(results):
        citations = set((results.get(item_id) or {}).get("citations") or [])
        cited_total += len(citations)
        for cite in sorted(citations):
            if cite not in graph_node_ids:
                hallucinated_ids.append(cite)
    return {
        "hallucinated": len(hallucinated_ids),
        "cited": cited_total,
        "rate": len(hallucinated_ids) / cited_total if cited_total else 0.0,
        "hallucinated_ids": hallucinated_ids,
    }


def judge_error_rates(
    verdicts: dict[str, str],
    gold_labels: dict[str, str],
) -> dict[str, Any]:
    """Judge false-accept and false-reject rates against gold accept/reject labels.

    verdicts maps a judged item id (for example a norm_id) to the judge
    verdict ("accepted", "rejected", "needs_human_review"); gold_labels maps
    the same ids to "accept" or "reject" (assigned per the annotation
    protocol). Only ids present in BOTH maps are scored.

    - false accept: judge said accepted, gold says reject.
      Rate denominator: the number of gold-reject items judged.
    - false reject: judge said rejected, gold says accept.
      Rate denominator: the number of gold-accept items judged.
    - needs_human_review is an abstention: counted separately, never a
      false accept or false reject (the item goes to a human, which is the
      designed degradation path, architecture.md Section 13).
    """
    false_accepts: list[str] = []
    false_rejects: list[str] = []
    abstained: list[str] = []
    gold_accept_n = 0
    gold_reject_n = 0
    for item_id in sorted(set(verdicts) & set(gold_labels)):
        gold = gold_labels[item_id]
        if gold not in JUDGE_GOLD_LABELS:
            raise ValueError(f"gold label for {item_id!r} must be one of {JUDGE_GOLD_LABELS}")
        verdict = verdicts[item_id]
        if gold == "accept":
            gold_accept_n += 1
        else:
            gold_reject_n += 1
        if verdict == "needs_human_review":
            abstained.append(item_id)
        elif verdict == "accepted" and gold == "reject":
            false_accepts.append(item_id)
        elif verdict == "rejected" and gold == "accept":
            false_rejects.append(item_id)
    return {
        "false_accept_rate": len(false_accepts) / gold_reject_n if gold_reject_n else 0.0,
        "false_reject_rate": len(false_rejects) / gold_accept_n if gold_accept_n else 0.0,
        "counts": {
            "false_accepts": len(false_accepts),
            "false_rejects": len(false_rejects),
            "gold_accept": gold_accept_n,
            "gold_reject": gold_reject_n,
            "abstained": len(abstained),
            "scored": gold_accept_n + gold_reject_n,
        },
        "false_accept_ids": false_accepts,
        "false_reject_ids": false_rejects,
        "abstained_ids": abstained,
    }

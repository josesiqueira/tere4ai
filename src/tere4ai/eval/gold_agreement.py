"""Agreement of the hand-made test set's two independent labels, by kind.

@implements: DEC-11
@grounded_by: ADD-88, ADD-59, ADD-99

What eval/gold/ANNOTATION_PROTOCOL.md names (lines 65 to 73), computed on
the two independent labels of each case before any adjudication, for each
kind apart:

- classification: raw agreement and Cohen's kappa over the five risk
  categories, with the confusion table; kappa is None, printed n/a with its
  reason, where both labellers used one category for every case;
- retrieval: the exact node-id agreement rate, and the agreement at article
  level as a secondary number (the article level of an Annex item is the
  Annex's top-level point, B149 Q2);
- qa: the citation agreement by exact node id; free-text answers are not
  scored, their differences go to adjudication.

Every case one labeller lacks is listed, never dropped; every label is
checked as it is read, paired or not. What the protocol leaves unstated is
not computed: the report says so and names the open question (B149 Q3 and
Q4 until the next task builds them). Decided: a label giving more or fewer
than one node id goes back to its labeller (B149 Q1); contested cases stay in
the agreement (B149 Q5). Pure functions: no I/O, no model, no randomness.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from tere4ai.eval.agreement import cohen_kappa, confusion

RISK_CATEGORIES = ("unacceptable_risk", "high_risk", "limited_risk", "minimal_risk", "undetermined")
KINDS = ("classification", "retrieval", "qa")

_AWAITING = "not computed: awaiting Jose's decision on {} (B149 {})"
NOT_ONE_ID = ("not compared: the protocol asks for one node id per label, so a label giving more or fewer goes "
              "back to its labeller before the agreement is reported (B149 Q1, Jose 2026-10-11: "
              "\"Back to the labeller (Recommended)\")")
NO_ARTICLE_LEVEL = ("no article level: the id lies in no Article and in no point of an Annex (B149 Q2: the article "
                    "level of an Annex item is the Annex's top-level point)")
CHANCE_CORRECTED = _AWAITING.format("a chance-corrected statistic for this kind", "Q3")
INTERVAL = _AWAITING.format("an interval on the agreement", "Q4")
CONTESTED_KEPT = ("contested after adjudication and kept here: the agreement is computed before any adjudication "
                  "(B149 Q5, Claude's ruling on Jose's delegation, 2026-10-11)")
KAPPA_NA = "n/a: both labellers used one category for every case"
QA_ANSWERS = ("free-text answers are not scored by string match; their differences "
              "go to adjudication")

_ARTICLE = re.compile(r"eu-ai-act:article-\d+[a-z]?(?=:|$)")
_ANNEX_POINT = re.compile(r"eu-ai-act:annex-[ivxlc]+(?::section-[a-z0-9]+)?:(?:point|item)-\d+[a-z]?(?=:|$)")

Pair = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]


class LabelError(ValueError):
    """A label the protocol's shape does not allow: the report refuses it."""


def article_of(node_id: str) -> str | None:
    """The Article a node id lies in: a paragraph or point credits its Article,
    as run_ablations' article-level completeness reads it. None outside the
    Articles (an Annex item, a recital)."""
    match = _ARTICLE.match(node_id)
    return match.group(0) if match else None


def article_level_of(node_id: str) -> str | None:
    """The article level of a node id (B149 Q2, Claude's choice for this study on
    Jose's delegation, 2026-10-11, no source): an Article's node reads its
    Article (article_of); an Annex item reads the Annex's top-level point, the
    id cut after its first point or item segment, a section kept as the id
    holds it (Annex III points 5(a) and 5(b) read Annex III point 5). None for
    the Annex itself, an Annex section or anything outside both."""
    article = article_of(node_id)
    if article:
        return article
    match = _ANNEX_POINT.match(node_id)
    return match.group(0) if match else None


def _annotator(label: Any, item: dict[str, Any]) -> str:
    if not isinstance(label, dict):
        raise LabelError(f"{item['id']}: a label is not an object ({label!r})")
    name = label.get("annotator")
    if not isinstance(name, str) or not name:
        raise LabelError(f"{item['id']}: a label names no annotator")
    return name


def annotators_of(items: Iterable[dict[str, Any]]) -> tuple[str, str]:
    """The two labellers. Kappa pairs the same two readers on every case
    (Fleiss 1971, ADD-99 q2), so any other number of names is refused."""
    names = sorted({_annotator(label, item) for item in items for label in item.get("labels") or []})
    if not names:
        raise LabelError("no case carries a label yet")
    if len(names) != 2:
        raise LabelError(f"the agreement pairs the same two labellers on every case; "
                         f"the labels name {len(names)}: {', '.join(names)}")
    return names[0], names[1]


def pair_labels(
    items: Iterable[dict[str, Any]], annotators: tuple[str, str]
) -> tuple[dict[str, list[Pair]], list[dict[str, Any]]]:
    """Per kind, (item, first label, second label) for every case both
    labellers labelled; and every case one or both lack, with who lacks it."""
    first, second = annotators
    paired: dict[str, list[Pair]] = {kind: [] for kind in KINDS}
    missing: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") not in KINDS:
            raise LabelError(f"{item.get('id')}: unknown kind {item.get('kind')!r}")
        by_name: dict[str, dict[str, Any]] = {}
        for label in item.get("labels") or []:
            name = _annotator(label, item)
            if name in by_name:
                raise LabelError(f"{item['id']}: {name} labelled it twice")
            _check(item["kind"], label, item)
            by_name[name] = label
        lacking = [name for name in (first, second) if name not in by_name]
        if lacking:
            missing.append({"id": item["id"], "kind": item["kind"], "lacking": lacking})
        else:
            paired[item["kind"]].append((item, by_name[first], by_name[second]))
    return paired, missing


def _level(label: dict[str, Any], item: dict[str, Any]) -> str:
    level = (label.get("gold") or {}).get("risk_category")
    if level not in RISK_CATEGORIES:
        raise LabelError(f"{item['id']}: {label['annotator']}'s level {level!r} is not one "
                         f"of the five risk categories")
    return level


def _id_set(value: Any, kind: str, label: dict[str, Any], item: dict[str, Any]) -> frozenset[str]:
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise LabelError(f"{item['id']}: {label['annotator']}'s {kind} label gives "
                         f"{value!r}, not node ids")
    return frozenset(value)


def _ids(kind: str, label: dict[str, Any], item: dict[str, Any]) -> frozenset[str]:
    """The node ids a label gives: retrieval reads gold.node_id (protocol
    lines 49 to 50), qa reads gold_citations (lines 55 to 56). A string, a
    list of strings or null (no id) is accepted; anything else is refused.
    A retrieval label's non-empty gold_citations must name the same ids as
    its node_id (the protocol gives every label both fields, lines 27 to
    28), or the label is refused."""
    if kind == "qa":
        return _id_set(label.get("gold_citations"), kind, label, item)
    ids = _id_set((label.get("gold") or {}).get("node_id"), kind, label, item)
    cites = _id_set(label.get("gold_citations"), kind, label, item)
    if cites and cites != ids:
        raise LabelError(f"{item['id']}: {label['annotator']}'s retrieval label gives "
                         f"node_id {sorted(ids)} but gold_citations {sorted(cites)}")
    return ids


def _check(kind: str, label: dict[str, Any], item: dict[str, Any]) -> None:
    """A label is checked as it is read, whether or not the other labeller
    labelled the case."""
    if kind == "classification":
        _level(label, item)
    else:
        _ids(kind, label, item)


def _share(pairs: list[tuple[Any, Any, Any]]) -> dict[str, Any]:
    agreed = sum(1 for _, x, y in pairs if x == y)
    return {"agreed": agreed, "compared": len(pairs),
            "rate": agreed / len(pairs) if pairs else None}


def _contested(pairs: list[Pair]) -> dict[str, Any]:
    return {"items": [item["id"] for item, _, _ in pairs if item.get("contested") is True],
            "note": CONTESTED_KEPT}


def _one_id_each(kind: str, pairs: list[Pair]) -> tuple[list[tuple[str, str, str]], list[str]]:
    one: list[tuple[str, str, str]] = []
    other: list[str] = []
    for item, label_a, label_b in pairs:
        ids_a, ids_b = _ids(kind, label_a, item), _ids(kind, label_b, item)
        if len(ids_a) == 1 and len(ids_b) == 1:
            one.append((item["id"], next(iter(ids_a)), next(iter(ids_b))))
        else:
            other.append(item["id"])
    return one, other


def classification_block(pairs: list[Pair]) -> dict[str, Any]:
    levels = [(item["id"], _level(a, item), _level(b, item)) for item, a, b in pairs]
    block: dict[str, Any] = {
        "paired": len(pairs),
        "raw_agreement": _share(levels),
        "cohen_kappa": None,
        "kappa_note": None,
        "confusion": {},
        "contested": _contested(pairs),
        "interval": INTERVAL,
    }
    if levels:
        first = [x for _, x, _ in levels]
        second = [y for _, _, y in levels]
        block["cohen_kappa"] = cohen_kappa(first, second)
        block["confusion"] = confusion(first, second)
        if block["cohen_kappa"] is None:
            block["kappa_note"] = KAPPA_NA
    return block


def retrieval_block(pairs: list[Pair]) -> dict[str, Any]:
    one, other = _one_id_each("retrieval", pairs)
    in_articles = [(i, article_level_of(x), article_level_of(y)) for i, x, y in one
                   if article_level_of(x) and article_level_of(y)]
    outside = [i for i, x, y in one if not (article_level_of(x) and article_level_of(y))]
    return {
        "paired": len(pairs),
        "exact_node_id_agreement": _share(one),
        "not_one_id": {"items": other, "note": NOT_ONE_ID},
        "article_level_agreement": _share(in_articles),
        "no_article_level": {"items": outside, "note": NO_ARTICLE_LEVEL},
        "contested": _contested(pairs),
        "chance_corrected": CHANCE_CORRECTED,
        "interval": INTERVAL,
    }


def qa_block(pairs: list[Pair]) -> dict[str, Any]:
    one, other = _one_id_each("qa", pairs)
    return {
        "paired": len(pairs),
        "citation_agreement": _share(one),
        "not_one_id": {"items": other, "note": NOT_ONE_ID},
        "answers": QA_ANSWERS,
        "contested": _contested(pairs),
        "chance_corrected": CHANCE_CORRECTED,
        "interval": INTERVAL,
    }


def agreement_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    """The protocol's agreement for each kind apart; raises LabelError on a
    label the protocol's shape does not allow."""
    annotators = annotators_of(items)
    paired, missing = pair_labels(items, annotators)
    return {
        "protocol": "eval/gold/ANNOTATION_PROTOCOL.md",
        "annotators": list(annotators),
        "items_total": len(items),
        "missing": missing,
        "by_kind": {
            "classification": classification_block(paired["classification"]),
            "retrieval": retrieval_block(paired["retrieval"]),
            "qa": qa_block(paired["qa"]),
        },
    }


def _share_text(share: dict[str, Any]) -> str:
    if share["rate"] is None:
        return "n/a (no case to compare)"
    return f"{share['agreed']} of {share['compared']} ({share['rate']:.3f})"


def _listed(name: str, block: dict[str, Any]) -> list[str]:
    if not block["items"]:
        return []
    return [f"  {name}: {', '.join(block['items'])}; {block['note']}"]


def render_text(report: dict[str, Any]) -> str:
    """The report as text: shares as "n of m" with the rate to three
    decimals, kappa to three decimals or n/a with its reason (spec F
    conventions)."""
    first, second = report["annotators"]
    lines = [f"labellers: {first}, {second}; cases: {report['items_total']}; "
             f"cases one labeller lacks: {len(report['missing'])}"]
    lines += [f"  {m['id']} ({m['kind']}): lacks {', '.join(m['lacking'])}"
              for m in report["missing"]]
    cls = report["by_kind"]["classification"]
    kappa = cls["cohen_kappa"]
    if kappa is not None:
        kappa_text = f"{kappa:.3f}"
    else:
        kappa_text = cls["kappa_note"] or "n/a (no case to compare)"
    lines += [f"classification: {cls['paired']} paired",
              f"  raw agreement: {_share_text(cls['raw_agreement'])}",
              f"  cohen kappa: {kappa_text}",
              f"  interval: {cls['interval']}"]
    lines += _listed("contested", cls["contested"])
    ret = report["by_kind"]["retrieval"]
    lines += [f"retrieval: {ret['paired']} paired",
              f"  exact node-id agreement: {_share_text(ret['exact_node_id_agreement'])}"]
    lines += _listed("not compared", ret["not_one_id"])
    lines += [f"  article-level agreement: {_share_text(ret['article_level_agreement'])}"]
    lines += _listed("no article level", ret["no_article_level"])
    lines += [f"  chance-corrected statistic: {ret['chance_corrected']}",
              f"  interval: {ret['interval']}"]
    lines += _listed("contested", ret["contested"])
    qa = report["by_kind"]["qa"]
    lines += [f"qa: {qa['paired']} paired",
              f"  citation agreement: {_share_text(qa['citation_agreement'])}"]
    lines += _listed("not compared", qa["not_one_id"])
    lines += [f"  answers: {qa['answers']}",
              f"  chance-corrected statistic: {qa['chance_corrected']}",
              f"  interval: {qa['interval']}"]
    lines += _listed("contested", qa["contested"])
    return "\n".join(lines)

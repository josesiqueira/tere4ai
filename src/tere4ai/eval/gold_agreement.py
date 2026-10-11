"""Agreement of the hand-made test set's two independent labels, by kind.

@implements: DEC-11
@grounded_by: ADD-88, ADD-59, ADD-99, ADD-93

What eval/gold/ANNOTATION_PROTOCOL.md names, computed on the two
independent labels of each case before any adjudication, for each kind
apart:

- classification: raw agreement and Cohen's kappa over the five risk
  categories, with the confusion table; kappa is None, printed n/a with its
  reason, where both labellers used one category for every case;
- retrieval: the exact node-id agreement rate and Cohen's kappa over the
  node ids of the one-id pairs (B149 Q3), and the agreement at article
  level as a secondary number (the article level of an Annex item is the
  Annex's top-level point, B149 Q2);
- qa: the citation agreement by exact node id and Cohen's kappa over the
  node ids of the one-id pairs (B149 Q3); free-text answers are not scored,
  their differences go to adjudication.

Every agreement figure carries a 95% percentile bootstrap interval over the
cases it compares, 1000 draws from a recorded seed, none over fewer than
two cases (B149 Q4, spec G D-G17). A kappa resample with no kappa is left
out and counted, the interval labelled conditional at 1 to 25 of 1000 and
not given above 25 (B161 Q1, spec F D-F20's rule, as for E6 in B150 Q11).
Every case one labeller lacks is listed, never dropped; every label is
checked as it is read, paired or not. A label giving more or fewer than one
node id goes back to its labeller (B149 Q1); contested cases stay in the
agreement (B149 Q5). Pure functions: no I/O, no model; randomness only from
a random.Random seeded with the recorded seed and the figure's label.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from tere4ai.eval.ablation_analysis import labelled_interval, seeded_rng
from tere4ai.eval.agreement import cohen_kappa, confusion

RISK_CATEGORIES = ("unacceptable_risk", "high_risk", "limited_risk", "minimal_risk", "undetermined")
KINDS = ("classification", "retrieval", "qa")

# B149 Q4 (Jose, 2026-10-11, "Bootstrap over cases (Recommended)"): a 95% percentile bootstrap over the cases a
# figure compares, 1000 draws, the positions of ablation_analysis.percentile_interval (B150 Q12), from a recorded
# seed, one generator per figure label (B150 ruling R3); B161 Q1 (Jose, 2026-10-11, "Same rule as E6
# (Recommended)"): a kappa resample with no kappa is left out and counted, conditional up to 25 of 1000 left out,
# no interval above (spec F D-F20's rule)
BOOTSTRAP = {"method": "percentile_bootstrap_over_cases", "level": 0.95, "draws": 1000, "seed": 20261011,
             "conditional_up_to": 25}
FEWER_THAN_TWO = "n/a: no interval over fewer than two cases (spec G D-G17)"
NOT_ONE_ID = ("not compared: the protocol asks for one node id per label, so a label giving more or fewer goes "
              "back to its labeller before the agreement is reported (B149 Q1, Jose 2026-10-11: "
              "\"Back to the labeller (Recommended)\")")
NO_ARTICLE_LEVEL = ("no article level: the id lies in no Article and in no point of an Annex (B149 Q2: the article "
                    "level of an Annex item is the Annex's top-level point)")
CONTESTED_KEPT = ("contested after adjudication and kept here: the agreement is computed before any adjudication "
                  "(B149 Q5, Claude's ruling on Jose's delegation, 2026-10-11)")
KAPPA_NA = "n/a: both labellers used one category for every case"
KAPPA_NA_IDS = "n/a: both labellers gave one and the same node id on every case"
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


def _rate(first: list, second: list) -> float:
    return sum(1 for x, y in zip(first, second) if x == y) / len(first)


def interval_of(pairs: list[tuple[Any, Any]], statistic: Callable[[list, list], float | None],
                label: str) -> list[float] | dict[str, Any] | str:
    """The 95% percentile interval of a statistic over the cases a figure
    compares, each resample drawing its cases with replacement (B149 Q4):
    [low, high] when every resample gives a value; FEWER_THAN_TWO over fewer
    than two cases (spec G D-G17); when some resample gives no value (only
    kappa can), the resamples are left out and counted and the result is
    labelled_interval's dict, conditional or none given (B161 Q1)."""
    n = len(pairs)
    if n < 2:
        return FEWER_THAN_TWO
    rng = seeded_rng(BOOTSTRAP["seed"], label)
    values: list[float] = []
    undefined = 0
    for _ in range(BOOTSTRAP["draws"]):
        drawn = [pairs[rng.randrange(n)] for _ in range(n)]
        value = statistic([a for a, _ in drawn], [b for _, b in drawn])
        if value is None:
            undefined += 1
        else:
            values.append(value)
    out = labelled_interval(values, undefined, draws=BOOTSTRAP["draws"], level=BOOTSTRAP["level"],
                            conditional_up_to=BOOTSTRAP["conditional_up_to"], what="kappa", question="B161 Q1")
    return out["interval"] if out["label"] is None else out


def _kappa_interval(pairs: list[tuple[Any, Any]], kappa: float | None,
                    label: str) -> list[float] | dict[str, Any] | str | None:
    # no interval where the point kappa itself is n/a
    return None if kappa is None else interval_of(pairs, cohen_kappa, label)


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
    }
    if levels:
        first = [x for _, x, _ in levels]
        second = [y for _, _, y in levels]
        block["cohen_kappa"] = cohen_kappa(first, second)
        block["confusion"] = confusion(first, second)
        if block["cohen_kappa"] is None:
            block["kappa_note"] = KAPPA_NA
    compared = [(x, y) for _, x, y in levels]
    block["intervals"] = {
        "raw_agreement": interval_of(compared, _rate, "classification:raw_agreement"),
        "cohen_kappa": _kappa_interval(compared, block["cohen_kappa"], "classification:cohen_kappa"),
    }
    return block


def _id_kappa(ids: list[tuple[str, str]]) -> tuple[float | None, str | None]:
    """Cohen's kappa over the node ids of the one-id pairs (B149 Q3), each
    distinct id a category; n/a with its reason when both labellers gave one
    and the same id on every case."""
    if not ids:
        return None, None
    kappa = cohen_kappa([x for x, _ in ids], [y for _, y in ids])
    return kappa, (KAPPA_NA_IDS if kappa is None else None)


def retrieval_block(pairs: list[Pair]) -> dict[str, Any]:
    one, other = _one_id_each("retrieval", pairs)
    in_articles = [(i, article_level_of(x), article_level_of(y)) for i, x, y in one
                   if article_level_of(x) and article_level_of(y)]
    outside = [i for i, x, y in one if not (article_level_of(x) and article_level_of(y))]
    ids = [(x, y) for _, x, y in one]
    kappa, note = _id_kappa(ids)
    return {
        "paired": len(pairs),
        "exact_node_id_agreement": _share(one),
        "cohen_kappa": kappa,
        "kappa_note": note,
        "not_one_id": {"items": other, "note": NOT_ONE_ID},
        "article_level_agreement": _share(in_articles),
        "no_article_level": {"items": outside, "note": NO_ARTICLE_LEVEL},
        "contested": _contested(pairs),
        "intervals": {
            "exact_node_id_agreement": interval_of(ids, _rate, "retrieval:exact_node_id_agreement"),
            "cohen_kappa": _kappa_interval(ids, kappa, "retrieval:cohen_kappa"),
            "article_level_agreement": interval_of([(x, y) for _, x, y in in_articles], _rate,
                                                   "retrieval:article_level_agreement"),
        },
    }


def qa_block(pairs: list[Pair]) -> dict[str, Any]:
    one, other = _one_id_each("qa", pairs)
    ids = [(x, y) for _, x, y in one]
    kappa, note = _id_kappa(ids)
    return {
        "paired": len(pairs),
        "citation_agreement": _share(one),
        "cohen_kappa": kappa,
        "kappa_note": note,
        "not_one_id": {"items": other, "note": NOT_ONE_ID},
        "answers": QA_ANSWERS,
        "contested": _contested(pairs),
        "intervals": {
            "citation_agreement": interval_of(ids, _rate, "qa:citation_agreement"),
            "cohen_kappa": _kappa_interval(ids, kappa, "qa:cohen_kappa"),
        },
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
        "bootstrap": dict(BOOTSTRAP),
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


def _interval_text(value: list[float] | dict[str, Any] | str | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value["interval"] is None:
            return value["label"]
        low, high = value["interval"]
        return f"[{low:.3f}, {high:.3f}]; {value['label']}"
    low, high = value
    return f"[{low:.3f}, {high:.3f}]"


def _figure(name: str, text: str, interval: Any) -> list[str]:
    return [f"  {name}: {text}", f"  95% interval: {_interval_text(interval)}"]


def _kappa_text(block: dict[str, Any]) -> str:
    kappa = block["cohen_kappa"]
    if kappa is not None:
        return f"{kappa:.3f}"
    return block["kappa_note"] or "n/a (no case to compare)"


def render_text(report: dict[str, Any]) -> str:
    """The report as text: shares as "n of m" with the rate to three
    decimals, kappa to three decimals or n/a with its reason (spec F
    conventions), each figure followed by its 95% interval."""
    first, second = report["annotators"]
    boot = report["bootstrap"]
    lines = [f"labellers: {first}, {second}; cases: {report['items_total']}; "
             f"cases one labeller lacks: {len(report['missing'])}"]
    lines += [f"  {m['id']} ({m['kind']}): lacks {', '.join(m['lacking'])}"
              for m in report["missing"]]
    lines += [f"bootstrap: {boot['draws']} draws over the compared cases, seed {boot['seed']}, "
              f"{boot['level']:.0%} percentile interval; a kappa resample with no kappa is left out and counted, "
              f"the interval labelled conditional at 1 to {boot['conditional_up_to']} of {boot['draws']} and none "
              f"given above (B161 Q1)"]
    cls = report["by_kind"]["classification"]
    lines += [f"classification: {cls['paired']} paired"]
    lines += _figure("raw agreement", _share_text(cls["raw_agreement"]), cls["intervals"]["raw_agreement"])
    lines += _figure("cohen kappa", _kappa_text(cls), cls["intervals"]["cohen_kappa"])
    lines += _listed("contested", cls["contested"])
    ret = report["by_kind"]["retrieval"]
    lines += [f"retrieval: {ret['paired']} paired"]
    lines += _figure("exact node-id agreement", _share_text(ret["exact_node_id_agreement"]),
                     ret["intervals"]["exact_node_id_agreement"])
    lines += _figure("cohen kappa", _kappa_text(ret), ret["intervals"]["cohen_kappa"])
    lines += _listed("not compared", ret["not_one_id"])
    lines += _figure("article-level agreement", _share_text(ret["article_level_agreement"]),
                     ret["intervals"]["article_level_agreement"])
    lines += _listed("no article level", ret["no_article_level"])
    lines += _listed("contested", ret["contested"])
    qa = report["by_kind"]["qa"]
    lines += [f"qa: {qa['paired']} paired"]
    lines += _figure("citation agreement", _share_text(qa["citation_agreement"]), qa["intervals"]["citation_agreement"])
    lines += _figure("cohen kappa", _kappa_text(qa), qa["intervals"]["cohen_kappa"])
    lines += _listed("not compared", qa["not_one_id"])
    lines += [f"  answers: {qa['answers']}"]
    lines += _listed("contested", qa["contested"])
    return "\n".join(lines)

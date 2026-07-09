"""Stratified deterministic sample of judge decisions for FA/FR gold labels.

@implements: DEC-11
@grounded_by: REF-16

Implements the judge false-accept / false-reject labelling step of
eval/gold/ANNOTATION_PROTOCOL.md ("Judge false-accept / false-reject gold
labels") and architecture.md Section 12. Samples 50 judge decisions from the
published build artifacts, stratified over (extraction, mapping) x
(accepted, rejected, needs_human_review), proportional to stratum size with
a minimum of 3 items per non-empty stratum. Sampling is deterministic and
content-addressed: within a stratum the decision ids are ordered by the
sha256 hex digest of the id and the first k are taken. No random module, no
model call, anywhere.

Default mode writes:
- eval/gold/judge_label_sheet.json: the machine sheet, one item per sampled
  decision with the judged content, the layer1 source excerpt, the judge
  verdict and rationale, and empty human_label / human_rationale fields.
- eval/gold/judge_label_sheet.md: a human-friendly rendering for labelling.
  The judge verdict is folded away per the protocol (the annotator labels
  blind and opens the verdict only afterwards).

--compute reads the filled sheet and prints the FA/FR rates via
tere4ai.eval.metrics.judge_error_rates. Label semantics per the protocol:
human_label is "accept" when ALL extraction-judge (or mapping-judge)
criteria hold and "reject" on any single failure; the judge verdicts stay
"accepted" / "rejected" / "needs_human_review" and needs_human_review is an
abstention, never an FA or FR. --compute refuses while any human_label is
still null.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.metrics import JUDGE_GOLD_LABELS, judge_error_rates  # noqa: E402

NORMS_PATH = ROOT / "data" / "graph_dumps" / "norms_core.json"
ALIGNMENTS_PATH = ROOT / "data" / "graph_dumps" / "alignments_core.json"
LAYER1_PATH = ROOT / "data" / "graph_dumps" / "layer1.json"
SHEET_JSON = ROOT / "eval" / "gold" / "judge_label_sheet.json"
SHEET_MD = ROOT / "eval" / "gold" / "judge_label_sheet.md"

TOTAL_SAMPLE = 50
MIN_PER_STRATUM = 3
EXCERPT_CHARS = 600

JUDGE_KINDS = ("extraction", "mapping")
VERDICTS = ("accepted", "rejected", "needs_human_review")

# Norm fields shown to the annotator (the judged content of an extraction
# decision). Everything the extraction-judge criteria mention.
NORM_SHEET_FIELDS = (
    "norm_id",
    "source_node_id",
    "source_span_id",
    "deontic_type",
    "modal",
    "actor_explicit",
    "actor_inferred",
    "actor_inference_source_node_id",
    "action",
    "object",
    "target_system_category",
    "conditions",
    "exceptions",
)

# Assertion fields shown to the annotator (the judged content of a mapping
# decision), including both evidence quotes.
ASSERTION_SHEET_FIELDS = (
    "id",
    "source_norm_id",
    "target_id",
    "relation_type",
    "source_quote",
    "target_quote",
    "source_evidence_span_ids",
    "target_evidence_span_ids",
)


def _decision_sort_key(decision_id: str) -> str:
    """Content-hash ordering key: sha256 hex of the decision id."""
    return hashlib.sha256(decision_id.encode("utf-8")).hexdigest()


def allocate_stratified(
    stratum_sizes: dict[tuple[str, str], int],
    total: int = TOTAL_SAMPLE,
    minimum: int = MIN_PER_STRATUM,
) -> dict[tuple[str, str], int]:
    """Proportional allocation with a minimum per non-empty stratum.

    Deterministic: start from max(minimum, floor(proportional quota)) capped
    at the stratum size, then move single items toward the stratum whose
    allocation is furthest below (or above) its exact quota until the total
    is met; ties break on the sorted stratum key. Raises ValueError when the
    population is smaller than the requested total.
    """
    sizes = {k: v for k, v in stratum_sizes.items() if v > 0}
    if not sizes:
        raise ValueError("no non-empty strata to sample from")
    population = sum(sizes.values())
    if population < total:
        raise ValueError(f"population {population} is smaller than the sample size {total}")
    keys = sorted(sizes)
    quota = {k: total * sizes[k] / population for k in keys}
    alloc = {k: min(sizes[k], max(minimum, math.floor(quota[k]))) for k in keys}
    while sum(alloc.values()) < total:
        candidates = [k for k in keys if alloc[k] < sizes[k]]
        k = max(candidates, key=lambda k: (quota[k] - alloc[k], k))
        alloc[k] += 1
    while sum(alloc.values()) > total:
        candidates = [k for k in keys if alloc[k] > min(minimum, sizes[k])]
        k = max(candidates, key=lambda k: (alloc[k] - quota[k], k))
        alloc[k] -= 1
    return alloc


def load_decisions(
    norms_payload: dict[str, Any],
    alignments_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Join judge runs to their judged artifacts (norm or assertion).

    Returns (decisions, unjoinable_ids). A decision is a judge run whose
    judged artifact is present in the dump; judge runs whose artifact was
    dropped from the dump (schema-invalid norms, pruned rejected assertions)
    cannot be labelled against their content and are excluded, with their
    ids reported in the sheet metadata rather than silently dropped.
    """
    decisions: list[dict[str, Any]] = []
    unjoinable: list[str] = []

    norms_by_run = {n.get("judge_run_id"): n for n in norms_payload.get("norms", [])}
    for run in norms_payload.get("judge_runs", []):
        norm = norms_by_run.get(run["id"])
        if norm is None:
            unjoinable.append(run["id"])
            continue
        decisions.append({"judge_run": run, "judged_content": norm, "judge_kind": "extraction"})

    assertions_by_run = {a.get("judge_run_id"): a for a in alignments_payload.get("assertions", [])}
    for run in alignments_payload.get("judge_runs", []):
        assertion = assertions_by_run.get(run["id"])
        if assertion is None:
            unjoinable.append(run["id"])
            continue
        decisions.append({"judge_run": run, "judged_content": assertion, "judge_kind": "mapping"})

    return decisions, sorted(unjoinable)


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[:EXCERPT_CHARS] + " [... excerpt truncated]"


def _source_excerpt(
    decision: dict[str, Any],
    layer1_index: dict[str, dict[str, Any]],
    norms_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve the layer1 source text behind the judged artifact.

    Extraction: the norm's source_node_id. Mapping: the source norm's
    source_node_id (the target side is covered by the assertion's verbatim
    target_quote). Unresolvable nodes are reported, never invented.
    """
    if decision["judge_kind"] == "extraction":
        node_id = decision["judged_content"].get("source_node_id")
    else:
        source_norm = norms_by_id.get(decision["judged_content"].get("source_norm_id"))
        node_id = source_norm.get("source_node_id") if source_norm else None
    node = layer1_index.get(node_id) if node_id else None
    if node is None:
        return {
            "node_id": node_id,
            "text": None,
            "note": "source node not resolvable in layer1.json; label from the quotes only",
        }
    return {"node_id": node_id, "text": _excerpt(node.get("text"))}


def build_sheet(
    norms_payload: dict[str, Any],
    alignments_payload: dict[str, Any],
    layer1_payload: dict[str, Any],
    total: int = TOTAL_SAMPLE,
    minimum: int = MIN_PER_STRATUM,
) -> dict[str, Any]:
    """Build the label sheet dict: deterministic for fixed input payloads."""
    decisions, unjoinable = load_decisions(norms_payload, alignments_payload)
    by_stratum: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for decision in decisions:
        verdict = decision["judge_run"].get("verdict")
        if verdict not in VERDICTS:
            raise ValueError(
                f"judge run {decision['judge_run'].get('id')!r} has unknown verdict {verdict!r}"
            )
        by_stratum.setdefault((decision["judge_kind"], verdict), []).append(decision)

    sizes = {k: len(v) for k, v in by_stratum.items()}
    allocation = allocate_stratified(sizes, total=total, minimum=minimum)

    layer1_index = {
        n["id"]: n for n in layer1_payload.get("nodes", []) if isinstance(n, dict) and "id" in n
    }
    norms_by_id = {n.get("norm_id"): n for n in norms_payload.get("norms", [])}

    items: list[dict[str, Any]] = []
    for stratum in sorted(allocation):
        pool = {d["judge_run"]["id"]: d for d in by_stratum[stratum]}
        chosen_ids = sorted(pool, key=_decision_sort_key)[: allocation[stratum]]
        for decision_id in chosen_ids:
            decision = pool[decision_id]
            run = decision["judge_run"]
            content = decision["judged_content"]
            fields = (
                NORM_SHEET_FIELDS if decision["judge_kind"] == "extraction"
                else ASSERTION_SHEET_FIELDS
            )
            items.append(
                {
                    "decision_id": decision_id,
                    "stratum": {"judge_kind": decision["judge_kind"], "verdict": run["verdict"]},
                    "judge_run": {
                        "id": run["id"],
                        "judge_kind": run.get("judge_kind"),
                        "judge_model": run.get("judge_model"),
                        "prompt_version": run.get("prompt_version"),
                        "verdict": run.get("verdict"),
                        "rationale": run.get("rationale"),
                        "scores": run.get("scores"),
                        "build_id": run.get("build_id"),
                    },
                    "judged_content": {f: content.get(f) for f in fields},
                    "source_excerpt": _source_excerpt(decision, layer1_index, norms_by_id),
                    "human_label": None,
                    "human_rationale": None,
                }
            )

    return {
        "purpose": (
            "Gold accept/reject labels for judge FA/FR rates "
            "(eval/gold/ANNOTATION_PROTOCOL.md). Fill human_label with "
            "'accept' or 'reject' and human_rationale with one sentence; "
            "then run scripts/sample_judge_decisions.py --compute."
        ),
        "labelling_rule": (
            "accept only if ALL judge criteria hold against the source text "
            "(span exists, deontic type supported, actor explicit or a valid "
            "recorded inference, action and object grounded, conditions and "
            "exceptions not dropped; for mappings: both quotes verbatim and "
            "the relation supported by concepts present in both spans). Any "
            "single failure means reject. Do not read the judge verdict "
            "before labelling."
        ),
        "sampling": {
            "method": (
                "stratified over (judge_kind x verdict); proportional with a "
                f"minimum of {minimum} per non-empty stratum; within a "
                "stratum, ids sorted by sha256(decision_id) and the first k "
                "taken; no random module"
            ),
            "total": sum(allocation.values()),
            "population": sum(sizes.values()),
            "strata": [
                {
                    "judge_kind": kind,
                    "verdict": verdict,
                    "population": sizes[(kind, verdict)],
                    "sampled": allocation[(kind, verdict)],
                }
                for kind, verdict in sorted(allocation)
            ],
            "unjoinable_judge_runs_excluded": unjoinable,
        },
        "builds": {
            "norms_core": norms_payload.get("build", {}).get("build_id"),
            "alignments_core": alignments_payload.get("build", {}).get("build_id"),
            "layer1": layer1_payload.get("build", {}).get("build_id"),
        },
        "items": items,
    }


def render_sheet_md(sheet: dict[str, Any]) -> str:
    """Human-friendly rendering of the sheet for blind labelling.

    The judge verdict and rationale are placed inside a folded details block
    at the end of each item: the protocol requires that the annotator never
    sees the verdict while labelling.
    """
    lines: list[str] = [
        "# Judge decision label sheet",
        "",
        "> GENERATED by scripts/sample_judge_decisions.py from the published",
        "> build artifacts. Record your labels in judge_label_sheet.json",
        "> (fields human_label and human_rationale); this file is the reading",
        "> copy. Label BLIND: do not open the folded judge verdict blocks",
        "> until your label is written down.",
        "",
        f"Labelling rule: {sheet['labelling_rule']}",
        "",
        "## Sampling",
        "",
        "| judge_kind | verdict | population | sampled |",
        "| --- | --- | --- | --- |",
    ]
    for stratum in sheet["sampling"]["strata"]:
        lines.append(
            f"| {stratum['judge_kind']} | {stratum['verdict']} "
            f"| {stratum['population']} | {stratum['sampled']} |"
        )
    lines += [
        "",
        f"Total sampled: {sheet['sampling']['total']} of "
        f"{sheet['sampling']['population']} joinable judge decisions. "
        f"Excluded as unjoinable (judged artifact absent from the dump): "
        f"{len(sheet['sampling']['unjoinable_judge_runs_excluded'])}.",
        "",
    ]
    for i, item in enumerate(sheet["items"], start=1):
        stratum = item["stratum"]
        lines += [
            f"## Item {i:02d}: {item['decision_id']}",
            "",
            f"- stratum: {stratum['judge_kind']} / (verdict hidden below)",
            "",
            "### Judged content",
            "",
        ]
        for key, value in item["judged_content"].items():
            if value in (None, [], ""):
                continue
            if isinstance(value, list):
                value = "; ".join(str(v) for v in value)
            lines.append(f"- {key}: {value}")
        excerpt = item["source_excerpt"]
        lines += ["", "### Source text (layer1)", ""]
        if excerpt.get("text"):
            lines += [f"Node `{excerpt['node_id']}`:", "", f"> {excerpt['text']}"]
        else:
            lines.append(f"Not resolvable: {excerpt.get('note', 'no source text')}")
        lines += [
            "",
            "### Your label",
            "",
            "- human_label (accept | reject): fill in judge_label_sheet.json",
            "- human_rationale: fill in judge_label_sheet.json",
            "",
            "<details><summary>Judge verdict (open only AFTER labelling)</summary>",
            "",
            f"- verdict: {item['judge_run']['verdict']}",
            f"- rationale: {item['judge_run']['rationale']}",
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines)


def compute_error_rates(sheet: dict[str, Any]) -> dict[str, Any]:
    """FA/FR from a filled sheet via metrics.judge_error_rates.

    Raises ValueError when any human_label is still null (listing how many
    remain) or holds a value outside the protocol's accept/reject set.
    """
    items = sheet.get("items", [])
    unlabelled = [it["decision_id"] for it in items if it.get("human_label") is None]
    if unlabelled:
        raise ValueError(
            f"refusing to compute: {len(unlabelled)} of {len(items)} items "
            "still have human_label null; label them first. Remaining: "
            + ", ".join(unlabelled)
        )
    bad = [
        it["decision_id"] for it in items if it["human_label"] not in JUDGE_GOLD_LABELS
    ]
    if bad:
        raise ValueError(
            f"human_label must be one of {JUDGE_GOLD_LABELS}; invalid on: " + ", ".join(bad)
        )
    verdicts = {it["decision_id"]: it["judge_run"]["verdict"] for it in items}
    gold_labels = {it["decision_id"]: it["human_label"] for it in items}
    return judge_error_rates(verdicts, gold_labels)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--compute", action="store_true",
        help="read the filled sheet and print FA/FR instead of sampling",
    )
    parser.add_argument("--sheet", type=Path, default=SHEET_JSON)
    parser.add_argument("--sheet-md", type=Path, default=SHEET_MD)
    parser.add_argument("--norms", type=Path, default=NORMS_PATH)
    parser.add_argument("--alignments", type=Path, default=ALIGNMENTS_PATH)
    parser.add_argument("--layer1", type=Path, default=LAYER1_PATH)
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite an existing sheet even if it already carries human labels",
    )
    args = parser.parse_args(argv)

    if args.compute:
        try:
            rates = compute_error_rates(_load(args.sheet))
        except ValueError as exc:
            print(str(exc))
            return 2
        counts = rates["counts"]
        print(f"scored: {counts['scored']} (gold accept {counts['gold_accept']}, "
              f"gold reject {counts['gold_reject']}, abstained {counts['abstained']})")
        print(f"false_accept_rate: {rates['false_accept_rate']:.4f} "
              f"({counts['false_accepts']} of {counts['gold_reject']} gold-reject)")
        print(f"false_reject_rate: {rates['false_reject_rate']:.4f} "
              f"({counts['false_rejects']} of {counts['gold_accept']} gold-accept)")
        if rates["false_accept_ids"]:
            print("false accepts: " + ", ".join(rates["false_accept_ids"]))
        if rates["false_reject_ids"]:
            print("false rejects: " + ", ".join(rates["false_reject_ids"]))
        return 0

    if args.sheet.exists() and not args.force:
        existing = _load(args.sheet)
        labelled = sum(
            1 for it in existing.get("items", []) if it.get("human_label") is not None
        )
        if labelled:
            print(
                f"refusing to overwrite {args.sheet}: it already carries "
                f"{labelled} human labels; pass --force to discard them"
            )
            return 1

    sheet = build_sheet(_load(args.norms), _load(args.alignments), _load(args.layer1))
    args.sheet.parent.mkdir(parents=True, exist_ok=True)
    args.sheet.write_text(
        json.dumps(sheet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    args.sheet_md.write_text(render_sheet_md(sheet) + "\n", encoding="utf-8")
    strata = ", ".join(
        f"{s['judge_kind']}/{s['verdict']}={s['sampled']}" for s in sheet["sampling"]["strata"]
    )
    print(f"wrote {args.sheet} and {args.sheet_md}")
    print(f"sampled {sheet['sampling']['total']} of {sheet['sampling']['population']}: {strata}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Stratified deterministic sample of judge decisions for FA/FR gold labels.

@implements: DEC-11, DEC-17
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

The label act (--label <decision id> <accept|reject> [--rationale TEXT], or
--label-file <csv> with columns decision_id,human_label,human_rationale)
both require --by <name>: each labelled item records human_label,
human_rationale, labelled_by, and labelled_at (who and when, per item).
Relabelling an item that already carries a label is refused unless --force
is passed. A sheet without a sample block (the July sheet) is refused: draw
a recorded sample first. Every invocation writes one labelling evaluation
record.

--compute reads the filled sheet and prints the FA/FR rates via
tere4ai.eval.metrics.judge_error_rates_by_kind, pooled and per judge kind
(the sheet's "mapping" kind is reported as "alignment"). Label semantics per
the protocol: human_label is "accept" when ALL extraction-judge (or
mapping-judge) criteria hold and "reject" on any single failure; the judge
verdicts stay "accepted" / "rejected" / "needs_human_review" and
needs_human_review is an abstention, never an FA or FR. --compute refuses
while any human_label is still null or was recorded without an actor and a
time, and while the sheet's bytes are not the bytes the newest completed
label act on this store wrote (a hand edit after labelling); a rate with an empty denominator prints as null, never 0.0. This is a
sample estimate: population weighting is not designed. --compute writes one
analysis evaluation record.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval.evaluation_record import (  # noqa: E402
    EvaluationRecordError,
    EvaluationRecordStore,
    code_version,
    file_ref,
    observe_publication,
    served_input_paths,
)
from tere4ai.eval.metrics import (  # noqa: E402
    JUDGE_GOLD_LABELS,
    METRICS_VERSION,
    judge_error_rates_by_kind,
)
from tere4ai.graph_store.build_chain import sha256_of_file  # noqa: E402
from tere4ai.graph_store.present import exception_reason  # noqa: E402

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


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix="tmp", suffix=path.suffix, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build_sheet(
    norms_payload: dict[str, Any],
    alignments_payload: dict[str, Any],
    layer1_payload: dict[str, Any],
    total: int = TOTAL_SAMPLE,
    minimum: int = MIN_PER_STRATUM,
    sample: dict[str, Any] | None = None,
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
        **({"sample": sample} if sample is not None else {}),
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
        lines += ["", "### Your label", ""]
        if item.get("human_label"):
            lines.append(f"- human_label: {item['human_label']}")
            lines.append(f"- human_rationale: {item.get('human_rationale') or ''}")
            if item.get("labelled_by"):
                lines.append(f"- labelled_by: {item['labelled_by']}")
            if item.get("labelled_at"):
                lines.append(f"- labelled_at: {item['labelled_at']}")
        else:
            lines.append("- human_label (accept | reject): fill in judge_label_sheet.json")
            lines.append("- human_rationale: fill in judge_label_sheet.json")
        lines += [
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
    """FA/FR from a filled sheet, pooled and per judge kind (D-G33).

    Raises ValueError when any human_label is still null, holds a value
    outside the protocol's accept/reject set, or was typed without an actor
    and a time (the label act of this script records both).
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
    unattributed = [
        it["decision_id"] for it in items if not it.get("labelled_by") or not it.get("labelled_at")
    ]
    if unattributed:
        raise ValueError(
            f"refusing to compute: {len(unattributed)} items carry a label without an "
            "actor or a time; record them through --label. Unattributed: "
            + ", ".join(unattributed)
        )
    verdicts = {it["decision_id"]: it["judge_run"]["verdict"] for it in items}
    gold_labels = {it["decision_id"]: it["human_label"] for it in items}
    kinds: dict[str, str] = {}
    for it in items:
        kind = (it.get("stratum") or {}).get("judge_kind")
        if kind:
            kinds[it["decision_id"]] = "alignment" if kind == "mapping" else kind
    rates = judge_error_rates_by_kind(verdicts, gold_labels, kinds)
    return {
        **rates,
        "metrics_version": METRICS_VERSION,
        "note": "sample estimate: population weighting is not designed",
    }


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_build(sheet: dict[str, Any]) -> dict[str, Any]:
    """The build block the sheet's sample was drawn against, or a fallback
    for a sheet that predates sample ids.
    """
    return (sheet.get("sample") or {}).get("build") or {
        "base_build_id": sheet.get("builds", {}).get("norms_core"),
        "publication": None,
        "publication_reason": "the sheet predates sample ids",
    }


def _label_act(args: argparse.Namespace, argv: list[str] | None) -> int:
    """The E1 label act: record human_label, human_rationale, labelled_by
    and labelled_at per item, then write one labelling evaluation record.
    """
    if not args.by:
        print("--by <name> is required: the label act records who labelled")
        return 2
    sheet = _load(args.sheet)
    if not isinstance(sheet.get("sample"), dict):
        # the July sheet stays intact: a label act needs a drawn sample (F6)
        print(f"refusing to label {args.sheet}: it was not drawn through a recorded draw (no sample block); "
              "draw a recorded sample first")
        return 2
    by_id = {it["decision_id"]: it for it in sheet.get("items", [])}
    wanted: dict[str, tuple[str, str]] = {}
    if args.label:
        wanted[args.label[0]] = (args.label[1], args.rationale)
    if args.label_file:
        if not args.label_file.is_file():
            print(f"label file not found: {args.label_file}")
            return 2
        with args.label_file.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            if "decision_id" not in fieldnames or "human_label" not in fieldnames:
                print(f"label file must have the columns decision_id and human_label; found: {fieldnames}")
                return 2
            for row in reader:
                wanted[row["decision_id"]] = (row["human_label"], row.get("human_rationale") or "")
    unknown = [i for i in wanted if i not in by_id]
    bad = [i for i, (label, _) in wanted.items() if label not in JUDGE_GOLD_LABELS]
    if unknown or bad:
        print(f"unknown decision ids: {unknown}; labels outside {JUDGE_GOLD_LABELS}: {bad}")
        return 2
    already = [i for i in wanted if by_id[i].get("human_label") is not None]
    if already and not args.force:
        it = by_id[already[0]]
        print(f"refusing to relabel {already[0]}: labelled by {it.get('labelled_by')} at "
              f"{it.get('labelled_at')}; pass --force to replace")
        return 1
    store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
    sample_id = (sheet.get("sample") or {}).get("sample_id")
    notes = [] if sample_id else ["the sheet predates sample ids"]
    record_id = None
    if store is not None:
        record_id = store.begin(
            kind="labelling", step="E1", command="sample_judge_decisions",
            argv=list(argv) if argv is not None else sys.argv[1:],
            inputs=[file_ref("sheet_before", args.sheet)],
            build=_sample_build(sheet),
            config={"by": args.by, "labels": {i: label for i, (label, _) in wanted.items()}, "forced": already},
            relations={"sample_id": sample_id}, intended_items=list(wanted),
        )
    now = datetime.now(UTC).isoformat()
    for decision_id, (label, rationale) in wanted.items():
        by_id[decision_id].update({
            "human_label": label, "human_rationale": rationale or None,
            "labelled_by": args.by, "labelled_at": now,
        })
    labelled_total = sum(1 for it in sheet["items"] if it.get("human_label") is not None)
    try:
        _write_atomic(args.sheet, json.dumps(sheet, ensure_ascii=False, indent=1) + "\n")
        _write_atomic(args.sheet_md, render_sheet_md(sheet) + "\n")
        if store is not None and record_id is not None:
            store.finish(
                record_id, status="completed", completed_items=list(wanted),
                outputs=[store.keep_output(record_id, "sheet_after", args.sheet)],
                counts={"labelled_now": len(wanted), "labelled_total": labelled_total, "items": len(sheet["items"])},
                notes=notes,
            )
    except BaseException as exc:
        if store is not None and record_id is not None:
            try:
                store.finish(record_id, status="failed", error=exception_reason(exc), notes=notes)
            except EvaluationRecordError:
                pass
        raise
    print(f"labelled {len(wanted)} item(s) by {args.by}; {labelled_total} of {len(sheet['items'])} labelled")
    return 0


def _fmt_rate(rate: float | None, numerator: int, denominator: int, what: str) -> str:
    if rate is None:
        return f"null (no {what} item scored)"
    return f"{rate:.4f} ({numerator} of {denominator} {what})"


def _print_rates(label: str, r: dict[str, Any]) -> None:
    c = r["counts"]
    print(f"[{label}] scored: {c['scored']} (gold accept {c['gold_accept']}, gold reject {c['gold_reject']}, "
          f"abstained {c['abstained']})")
    print(f"[{label}] false_accept_rate: "
          f"{_fmt_rate(r['false_accept_rate'], c['false_accepts'], c['gold_reject'], 'gold-reject')}")
    print(f"[{label}] false_reject_rate: "
          f"{_fmt_rate(r['false_reject_rate'], c['false_rejects'], c['gold_accept'], 'gold-accept')}")
    if r["false_accept_ids"]:
        print(f"[{label}] false accepts: " + ", ".join(r["false_accept_ids"]))
    if r["false_reject_ids"]:
        print(f"[{label}] false rejects: " + ", ".join(r["false_reject_ids"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--compute", action="store_true",
        help="read the filled sheet and print FA/FR instead of sampling",
    )
    parser.add_argument("--sheet", type=Path, default=SHEET_JSON)
    parser.add_argument("--sheet-md", type=Path, default=SHEET_MD)
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    parser.add_argument("--norms", type=Path, default=None)
    parser.add_argument("--alignments", type=Path, default=None)
    parser.add_argument("--layer1", type=Path, default=None)
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite an existing sheet even if it already carries human labels",
    )
    parser.add_argument(
        "--no-record", action="store_true",
        help="draw without writing an evaluation record",
    )
    parser.add_argument(
        "--label", nargs=2, metavar=("DECISION_ID", "LABEL"), default=None,
        help="label one decision id accept or reject",
    )
    parser.add_argument(
        "--label-file", type=Path, default=None,
        help="a csv with columns decision_id,human_label,human_rationale",
    )
    parser.add_argument("--by", default=None, help="who is labelling (required by --label/--label-file)")
    parser.add_argument("--rationale", default="", help="rationale for --label")
    args = parser.parse_args(argv)

    if args.label or args.label_file:
        return _label_act(args, argv)

    if args.compute:
        sheet = _load(args.sheet)
        try:
            rates = compute_error_rates(sheet)
        except ValueError as exc:
            print(str(exc))
            return 2
        sample_id = (sheet.get("sample") or {}).get("sample_id")
        # completed label acts only, oldest first; the newest must have written these bytes (F7)
        labelling = sorted(
            (
                r for r in EvaluationRecordStore(args.dump_dir, create=False).list_records()
                if not r.get("unreadable") and r["kind"] == "labelling"
                and r["outcome"]["status"] == "completed" and sample_id
                and r["relations"]["sample_id"] == sample_id
            ),
            key=lambda r: (r["ended_at"], r["record_id"]),
        )
        labelling_ids = [r["record_id"] for r in labelling]
        compute_notes: list[str] = []
        if labelling:
            newest = labelling[-1]
            written = [o["sha256"] for o in newest["outputs"] if o["role"] == "sheet_after"]
            if sha256_of_file(args.sheet) not in written:
                print("refusing to compute: the sheet's bytes are not the bytes the last label act wrote "
                      f"({newest['record_id']}); label through --label or --label-file")
                return 2
        else:
            compute_notes.append("no labelling record on this store names the sheet's bytes")
        store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
        ids = [it["decision_id"] for it in sheet["items"]]
        pooled = rates["pooled"]
        record_id = None
        if store is not None:
            record_id = store.begin(
                kind="analysis", step="E1", command="sample_judge_decisions",
                argv=list(argv) if argv is not None else sys.argv[1:],
                inputs=[file_ref("sheet_labelled", args.sheet)],
                build=_sample_build(sheet),
                config={"metrics_version": METRICS_VERSION},
                relations={"sample_id": sample_id, "labelling_record_ids": labelling_ids},
                intended_items=ids,
            )
            rates_path = args.sheet.with_name("error_rates.json")
            notes = [rates["note"], *compute_notes]
            try:
                _write_atomic(rates_path, json.dumps(rates, ensure_ascii=False, indent=1) + "\n")
                store.finish(
                    record_id, status="completed", completed_items=ids,
                    outputs=[store.keep_output(record_id, "error_rates", rates_path)],
                    counts={
                        "scored": pooled["counts"]["scored"], "abstained": pooled["counts"]["abstained"],
                        "gold_accept": pooled["counts"]["gold_accept"], "gold_reject": pooled["counts"]["gold_reject"],
                    },
                    notes=notes,
                )
            except BaseException as exc:
                try:
                    store.finish(record_id, status="failed", error=exception_reason(exc), notes=notes)
                except EvaluationRecordError:
                    pass
                raise
        _print_rates("pooled", pooled)
        for kind, r in rates["by_kind"].items():
            _print_rates(kind, r)
        print(rates["note"])
        if record_id is not None:
            print(f"evaluation record {record_id} written under {store.dir}")
        return 0

    served = served_input_paths(args.dump_dir)
    resolved: dict[str, Path] = {}
    for role, explicit, flag in (
        ("norms", args.norms, "norms"),
        ("alignments", args.alignments, "alignments"),
        ("layer1_dump", args.layer1, "layer1"),
    ):
        if explicit is not None:
            resolved[role] = explicit
        elif role in served:
            resolved[role] = served[role]
        else:
            print(f"refusing to draw: the active publication names no {role} file; pass --{flag} explicitly")
            return 2
    norms_path, alignments_path, layer1_path = resolved["norms"], resolved["alignments"], resolved["layer1_dump"]

    if args.sheet.exists() and not args.force:
        existing = _load(args.sheet)
        items = existing.get("items", [])
        labelled = sum(1 for it in items if it.get("human_label") is not None)
        print(f"refusing to overwrite {args.sheet}: a sheet exists ({labelled} of {len(items)} items labelled); "
              "pass --force to draw a fresh sample")
        return 1

    norms_payload, alignments_payload, layer1_payload = _load(norms_path), _load(alignments_path), _load(layer1_path)
    store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
    if args.norms is None and args.alignments is None and args.layer1 is None:
        publication, publication_reason = observe_publication(args.dump_dir)
    else:  # a record binds to a publication only when it read the publication's files (F4)
        publication, publication_reason = None, "explicit input files given; the run did not read the served publication"
    base_build_id = (norms_payload.get("build") or {}).get("build_id")
    build = {"base_build_id": str(base_build_id) if base_build_id is not None else None,
             "publication": publication, "publication_reason": publication_reason}
    sample = {"sample_id": "sample-" + uuid.uuid4().hex[:12], "record_id": None,
              "drawn_at": datetime.now(UTC).isoformat(), "build": build}
    inputs = [file_ref("norms", norms_path), file_ref("alignments", alignments_path), file_ref("layer1_dump", layer1_path)]
    sheet = build_sheet(norms_payload, alignments_payload, layer1_payload, sample=sample)
    record_id = None
    if store is not None:
        record_id = store.begin(kind="sample", step="E1", command="sample_judge_decisions",
                                argv=list(argv) if argv is not None else sys.argv[1:], inputs=inputs, build=build,
                                config={"total": TOTAL_SAMPLE, "minimum": MIN_PER_STRATUM, "code_version": code_version(ROOT),
                                        "strata": sheet["sampling"]["strata"], "population": sheet["sampling"]["population"]},
                                relations={"sample_id": sample["sample_id"]},
                                intended_items=[it["decision_id"] for it in sheet["items"]])
        sample["record_id"] = record_id
        sheet["sample"] = sample  # the record id lands in the sheet before it is written
    try:
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(args.sheet, json.dumps(sheet, ensure_ascii=False, indent=1) + "\n")
        _write_atomic(args.sheet_md, render_sheet_md(sheet) + "\n")
        if store is not None and record_id is not None:
            ids = [it["decision_id"] for it in sheet["items"]]
            store.finish(record_id, status="completed", completed_items=ids,
                         outputs=[store.keep_output(record_id, "sheet_json", args.sheet),
                                  store.keep_output(record_id, "sheet_md", args.sheet_md)],
                         counts={"population": sheet["sampling"]["population"], "sampled": sheet["sampling"]["total"],
                                 "unjoinable": len(sheet["sampling"]["unjoinable_judge_runs_excluded"])})
    except BaseException as exc:
        if store is not None and record_id is not None:
            try:
                store.finish(record_id, status="failed", error=exception_reason(exc))
            except EvaluationRecordError:
                pass
        raise
    strata = ", ".join(
        f"{s['judge_kind']}/{s['verdict']}={s['sampled']}" for s in sheet["sampling"]["strata"]
    )
    print(f"wrote {args.sheet} and {args.sheet_md}")
    print(f"sampled {sheet['sampling']['total']} of {sheet['sampling']['population']}: {strata}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

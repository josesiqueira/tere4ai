"""E6's declared analysis over one group of kept ablation runs (spec G D-G84, B150).

@implements: DEC-11, DEC-17
@grounded_by: ADD-73, ADD-74

Reads kept outputs only: the evaluation records of one repetition group (the
group's first run and every run whose --repeat-of names it), each run's kept
checkpoint and summary copies, the answer keys the runs read (checked by
digest and by the item selection) and the declaration
(eval/e6_declaration.json). Writes ablation_analysis.json and
ablation_analysis.md under eval/results/analyses/<record id>/ and one
evaluation record of kind analysis whose relation compares lists the runs it
read (D-G33). Calls no model.

A group is refused when a run is not a completed or partial E6 run, when its
runs differ in an input, the items, the models, the build, the item set or the
prompt versions, when a kept copy is missing or differs from its digest, or
when a case lacks a result. A declaration that differs from the one the runs
carry is read and every figure labelled post hoc.

  --pilot                 the pilot run's group, five repetitions on the
                          development set: each figure's standard deviation
                          and the main run's count N (spec G D-G84 (5)).
  --pilot-analysis ID     a main run's group: the declared contrasts, the
                          runtime judge's shares and the per-call accuracy;
                          the group's size must be the count the pilot
                          analysis ID fixed, on the same build,
                          declaration, models and prompt versions (the
                          elicitor's included), the pilot run ended first.

Usage:
  .venv/bin/python scripts/analyse_ablations.py --group <first run id> --pilot
  .venv/bin/python scripts/analyse_ablations.py --group <first run id> --pilot-analysis <analysis record id>
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.eval import harness  # noqa: E402
from tere4ai.eval.ablation_analysis import (  # noqa: E402
    SHARES,
    AnalysisError,
    accuracy_by_repetition,
    gate_answers,
    gate_share_intervals,
    gate_shares,
    gate_shares_by_repetition,
    majority,
    not_computed,
    outcome_table,
    paired_contrast,
    per_call_summary,
    pilot_count,
)
from tere4ai.eval.ablation_declaration import (  # noqa: E402
    DECLARATION_PATH,
    DeclarationError,
    declaration_sha256,
    load_declaration,
)
from tere4ai.eval.ablation_group import identity_differences  # noqa: E402
from tere4ai.eval.evaluation_record import (  # noqa: E402
    EvaluationRecordError,
    EvaluationRecordStore,
    code_version,
    digest_of_ids,
    end_failed,
    input_ref,
)
from tere4ai.eval.strategies import STRATEGY_NAMES  # noqa: E402
from tere4ai.graph_store.build_chain import sha256_of_file  # noqa: E402
from tere4ai.graph_store.present import exception_reason  # noqa: E402

RESULTS_DIR = ROOT / "eval" / "results"
ANALYSES_DIRNAME = "analyses"
JSON_NAME = "ablation_analysis.json"
TEXT_NAME = "ablation_analysis.md"
ANALYSIS_VERSION = "e6_analysis.v1"
KEY_PREFIXES = {"hand_made": "gold:", "benchmark": "bench:"}
POST_HOC_NOTE = ("the declaration read here differs from the one the runs carry: every figure below is a post hoc "
                 "analysis (spec G D-G84, cost if wrong)")


class Refused(Exception):
    """The analysis cannot run on what was given; the message says why (exit 2)."""


def _input(record: dict[str, Any], kind: str) -> str | None:
    return next((i["sha256"] for i in record.get("inputs") or [] if i["input_kind"] == kind), None)


def _condition_prompts(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in (record.get("prompt_versions") or {}).items() if k != "elicit_features"}


def _elicitor_prompt(record: dict[str, Any]) -> tuple[Any, Any]:
    entry = (record.get("prompt_versions") or {}).get("elicit_features") or {}
    return entry.get("version"), entry.get("template_sha256")


def _build_key(record: dict[str, Any]) -> tuple[Any, Any]:
    build = record.get("build") or {}
    return build.get("base_build_id"), build.get("publication")


def provisional_note(declaration: dict) -> str:
    """The two settings built as proposed, awaiting Jose (plan Section 2, items 5 and 6),
    the draw count read from the declaration (second-seat M4)."""
    draws = declaration["primary_family"]["interval"]["draws"]
    return (f"provisional, awaiting Jose: the bootstrap's {draws} draws and the percentile positions (B150 Q12); "
            "each repetition's accuracy read over the cases run in every repetition (B150 Q13)")


def group_records(store: EvaluationRecordStore, first_id: str) -> tuple[list[dict], list[str], str]:
    """The group as logical runs (ruling R40, Codex finding 3). A run stopped and
    resumed is a chain of records linked by resumes_record_id, read through its
    last record, whose kept checkpoint holds every unit of the chain. The head
    is the last record of the first run's chain (first_id may name any record of
    it); the repetitions are the last records of the chains whose repeat_of
    names a record of that chain, by start time. Returns the group, the notes
    (superseded attempts, unreadable records) and the start of the first run's
    first attempt."""
    store.read(first_id)  # the store's own refusal when no such record exists
    readable, notes = [], []
    for record in store.list_records():
        if record.get("unreadable"):
            notes.append(f"evaluation record {record['record_id']} is unreadable and was not considered: "
                         f"{record['reason']}")
        else:
            readable.append(record)
    by_id = {r["record_id"]: r for r in readable}
    resumes = {r["record_id"]: (r.get("relations") or {}).get("resumes_record_id") for r in readable}
    resumed_by = {prior: rid for rid, prior in resumes.items() if prior}
    root = first_id
    while resumes.get(root) in by_id:
        root = resumes[root]
    chain = [root]
    while chain[-1] in resumed_by:
        chain.append(resumed_by[chain[-1]])
    members = [r for r in readable if (r.get("relations") or {}).get("repeat_of") in set(chain)]
    finals = [r for r in members if r["record_id"] not in resumed_by]
    # ruling R46 (second-seat I1): a member that kept no checkpoint holds no result: stopped before
    # its first unit and rerun as a new record, or stopped and never resumed; left out and named
    empty = sorted(r["record_id"] for r in finals if not any(
        o.get("output_kind") == "checkpoint" for o in r.get("outputs") or []))
    repeats = sorted((r for r in finals if r["record_id"] not in empty),
                     key=lambda r: (r.get("started_at") or "", r["record_id"]))
    superseded = chain[:-1] + sorted(r["record_id"] for r in members if r["record_id"] in resumed_by)
    if superseded:
        notes.append("attempts stopped and resumed by a later record, read through that record: "
                     + ", ".join(superseded))
    if empty:
        notes.append("repetitions that kept no checkpoint (stopped before any unit, or stopped and never "
                     "resumed), left out: " + ", ".join(empty))
    first_started = min(by_id[rid].get("started_at") or "" for rid in chain)
    return [by_id[chain[-1]], *repeats], notes, first_started


def group_refusal(group: list[dict], *, mode: str, declaration: dict, pilot_count_: int | None) -> str | None:
    first = group[0]
    for record in group:
        if record.get("kind") != "run" or record.get("step") != "E6":
            return f"evaluation record {record['record_id']} is not an E6 run"
        status = (record.get("outcome") or {}).get("status")
        if status not in ("completed", "partial"):
            return f"run {record['record_id']} ended {status}; only a completed or partial run is analysed"
    head = (first.get("relations") or {}).get("repeat_of")
    if head is not None:
        return f"{first['record_id']} is a repetition; name the group's first run {head}"
    # the head is the first run's last attempt (group_records); one that stopped and was never resumed kept
    # no checkpoint, and the run-once cases live in the first run only, so it is refused, never left out
    if not any(o.get("output_kind") == "checkpoint" for o in first.get("outputs") or []):
        return (f"the group's first run {first['record_id']} ended {(first.get('outcome') or {}).get('status')} "
                "and kept no checkpoint (stopped before its end and not resumed); resume it with the same "
                "command, then analyse the group")
    for record in group[1:]:
        differing = identity_differences(first, record, prompt_versions=True)
        if differing:
            return (f"run {record['record_id']} differs from the group's first run {first['record_id']} in "
                    f"{', '.join(differing)}")
    item_set = (first.get("config") or {}).get("item_set")
    size = len(group)
    if mode == "pilot":
        wanted = declaration["repetitions"]["pilot_repetitions"]
        if item_set != "development":
            return f"the pilot run's group runs the {item_set} item set, not the development set"
        if size != wanted:
            return f"the pilot run's group holds {size} run(s); spec G D-G84 (5) asks for {wanted}"
        return None
    if item_set != "main":
        return f"a main run's group runs the main item set, not {item_set}"
    if size % 2 == 0:
        return f"the group holds {size} runs, an even number, which leaves a majority undefined"
    if size != pilot_count_:
        return f"the group holds {size} run(s); the pilot run fixed {pilot_count_}"
    return None


def pilot_record(store: EvaluationRecordStore, pilot_id: str, first: dict, first_started: str) -> dict[str, Any]:
    """The pilot analysis that fixed the main run's count (spec G D-G84 (5); ruling R19):
    on the same build, under the declaration the main runs carry (read as declared
    before its own runs), its runs and the analysis itself ended before the main
    run's first attempt started (Codex finding 5)."""
    record = store.read(pilot_id)
    config = record.get("config") or {}
    if record.get("kind") != "analysis" or record.get("step") != "E6" or config.get("mode") != "pilot":
        raise Refused(f"evaluation record {pilot_id} is not the analysis of a pilot run")
    if (record.get("outcome") or {}).get("status") != "completed":
        raise Refused(f"the pilot analysis {pilot_id} did not complete")
    count = config.get("pilot_count")
    if not isinstance(count, int):
        raise Refused(f"the pilot analysis {pilot_id} gave no count: "
                      f"{config.get('pilot_count_reason') or 'none recorded'}")
    if _build_key(record) != _build_key(first):
        raise Refused(f"the pilot analysis {pilot_id} is on another build than the main run")
    runs = [store.read(rid) for rid in (record.get("relations") or {}).get("compares") or [] if rid]
    if not runs or any(_input(r, "e6_declaration") != _input(first, "e6_declaration") for r in runs):
        raise Refused("the pilot run carries another declaration than the main run")
    if _input(record, "e6_declaration") != _input(first, "e6_declaration") or config.get("declared_before_runs") is not True:
        raise Refused(f"the pilot analysis {pilot_id} read another declaration than the one its runs and the main "
                      "run carry")
    ended = [r.get("ended_at") or "" for r in runs]
    if any(not e for e in ended) or max(ended) >= first_started:
        raise Refused("the pilot run did not end before the main run started (spec G D-G84 (5): the pilot first)")
    if not record.get("ended_at") or record["ended_at"] >= first_started:
        raise Refused(f"the pilot analysis {pilot_id} did not fix the count before the main run started "
                      "(spec G D-G84 (5): the pilot first)")
    return {"record_id": pilot_id, "count": count}


def pilot_instrument_refusal(store: EvaluationRecordStore, pilot_id: str, first: dict) -> str | None:
    """The refusal sentence when the pilot run ran other instruments than the
    main run, read once the group itself is accepted (a failure mechanic, the
    coordinator's ruling on Task 7): the count holds for the models, the
    conditions' prompt versions and the elicitor's prompt it was fixed on.
    Conditions 1 and 2 read the elicited facts on every classification case
    in every repetition (strategies._item_question), so the elicitor's
    version and template hash are compared; its rendered hash and
    graph_version are not, as each item set's facts file is elicited apart
    and may differ there (coordinator's re-review of ruling (b))."""
    runs = [store.read(rid) for rid in (store.read(pilot_id).get("relations") or {}).get("compares") or [] if rid]
    if any((r.get("models") or {}) != (first.get("models") or {}) for r in runs):
        return ("the pilot run ran other models than the main run; fix the count again with a pilot run on the "
                "main run's models")
    if any(_condition_prompts(r) != _condition_prompts(first) for r in runs):
        return ("the pilot run ran other prompt versions than the main run; fix the count again with a pilot run "
                "on the main run's prompt versions")
    if any(_elicitor_prompt(r) != _elicitor_prompt(first) for r in runs):
        return ("the pilot run's facts were elicited with another elicitor prompt (version or template) than the "
                "main run's; elicit both with one prompt and fix the count again")
    return None


def kept_copy(store: EvaluationRecordStore, record: dict, output_kind: str) -> Path:
    rid = record["record_id"]
    for ref in record.get("outputs") or []:
        if ref["output_kind"] == output_kind and ref.get("copy"):
            path = store.dir / ref["copy"]
            if not path.is_file():
                raise Refused(f"run {rid}: its kept {output_kind} copy is missing")
            if sha256_of_file(path) != ref["sha256"]:
                raise Refused(f"run {rid}: its kept {output_kind} copy differs from the digest the record holds")
            return path
    raise Refused(f"run {rid} kept no {output_kind}")


def run_results(path: Path) -> dict[str, dict[str, dict]]:
    merged: dict[str, dict[str, dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            merged.setdefault(entry["strategy"], {}).update(entry["results"])
    return merged


def key_files(args: argparse.Namespace, mode: str) -> dict[str, Path]:
    if mode == "pilot":
        return {"benchmark": args.benchmark or harness.DEVELOPMENT_PAYLOAD_PATH}
    return {"gold_seed": args.gold, "benchmark": args.benchmark or harness.BENCHMARK_SAMPLE_PATH}


def group_items(first: dict, files: dict[str, Path], mode: str) -> list[dict]:
    """The items the runs read, from the same files (by digest) and in the same
    order (by the item selection's digest; ruling R39)."""
    for kind, path in files.items():
        if sha256_of_file(path) != _input(first, kind):
            raise Refused(f"{Path(path).name} is not the {kind} file the runs read (its digest differs)")
    if mode == "pilot":
        items = harness.load_development_items(files["benchmark"])
    else:
        items = harness.load_gold_items(files["gold_seed"]) + harness.load_benchmark_items(files["benchmark"])
    if digest_of_ids([i["id"] for i in items]) != first.get("item_selection_sha256"):
        raise Refused("the items loaded are not the runs' item selection")
    return items


def conditions_in(runs: list[dict]) -> list[str]:
    return [name for name in STRATEGY_NAMES if name in runs[0]]


def failed_calls(runs: list[dict], run_ids: list[str]) -> list[dict[str, Any]]:
    """Every failed call of the group, by run, condition and case (spec G D-G84 (5): listed)."""
    return [{"run": rid, "condition": name, "case": case, "error": str(result["error"])}
            for rid, run in zip(run_ids, runs) for name in conditions_in(runs)
            for case, result in sorted((run.get(name) or {}).items()) if "error" in result]


def analyse_main(items: list[dict], runs: list[dict], run_ids: list[str], summaries: list[dict],
                 declaration: dict) -> dict[str, Any]:
    run_once = declaration["repetitions"]["run_once"]
    family = declaration["primary_family"]
    interval = family["interval"]
    hand = [i for i in items if i["id"].startswith(KEY_PREFIXES["hand_made"])]
    scored = [i for i in hand if i.get("contested") is not True]
    threshold = family["correction"]["alpha"] / len(family["contrasts"])
    contrasts = []
    for c in family["contrasts"]:
        cases = [i for i in scored if i["kind"] in c["case_kinds"]]
        ours = outcome_table(cases, runs, c["condition"], run_once)
        theirs = outcome_table(cases, runs, c["against"], run_once)
        pairs = [(majority(ours[i["id"]]), majority(theirs[i["id"]])) for i in cases]
        contrasts.append({**c, **paired_contrast(pairs, level=interval["level"], draws=interval["draws"],
                                                 seed=interval["seed"], label=c["id"], threshold=threshold)})
    judge = declaration["runtime_judge"]
    judged_cases = [i for i in scored if i["kind"] in judge["case_kinds"]]
    runtime: dict[str, Any] = {}
    for condition in judge["conditions"]:
        answers, failed = gate_answers(judged_cases, runs, condition)
        runtime[condition] = {
            "cases": len(judged_cases), "answers": sum(len(row) for row in answers.values()),
            "failed_calls_left_out": failed, "shares": gate_shares(list(answers.values())),
            "intervals": gate_share_intervals(answers, level=judge["interval"]["level"],
                                              draws=judge["interval"]["draws"], seed=judge["interval"]["seed"],
                                              label=f"runtime_judge:{condition}"),
        }
    keys = {"hand_made": scored, "benchmark": [i for i in items if i["id"].startswith(KEY_PREFIXES["benchmark"])]}
    return {
        "primary_family": {"answer_key": family["answer_key"],
                           "contested_left_out": [i["id"] for i in hand if i.get("contested") is True],
                           "alpha": family["correction"]["alpha"], "threshold": threshold, "test": family["test"],
                           "contrasts": contrasts},
        "secondary": secondary_block(items, runs, declaration),
        "per_call_accuracy": {key: {name: per_call_summary(outcome_table(cases, runs, name, run_once), len(runs))
                                    for name in conditions_in(runs)} for key, cases in keys.items()},
        "runtime_judge": runtime,
        "four_measures": {
            "by_run": {rid: {name: block["by_answer_key"] for name, block in summary["strategies"].items()}
                       for rid, summary in zip(run_ids, summaries)},
            "over_repetitions": not_computed("one figure of the four measures over the repetitions", "B150 Q9")},
        "failed_calls": failed_calls(runs, run_ids),
    }


def secondary_block(items: list[dict], runs: list[dict], declaration: dict) -> dict[str, Any]:
    """The benchmark's contrasts, "secondary and outside the family ... reported as
    differences in agreement with its labels" (spec G D-G84 (1)): each listed one
    gets its paired difference with the 95% interval, as passage (d) reports
    every comparison of two conditions; whether a test goes with it is Jose's
    (B150 Q8), as is which ones are listed (none until he names them; ruling R44)."""
    run_once = declaration["repetitions"]["run_once"]
    interval = declaration["primary_family"]["interval"]
    bench = [i for i in items if i["id"].startswith(KEY_PREFIXES["benchmark"])]
    contrasts = []
    for c in declaration["secondary"]["contrasts"]:
        cases = [i for i in bench if i["kind"] in c["case_kinds"]]
        ours = outcome_table(cases, runs, c["condition"], run_once)
        theirs = outcome_table(cases, runs, c["against"], run_once)
        pairs = [(majority(ours[i["id"]]), majority(theirs[i["id"]])) for i in cases]
        result = paired_contrast(pairs, level=interval["level"], draws=interval["draws"], seed=interval["seed"],
                                 label=f"secondary:{c['id']}", threshold=0.0)
        for key in ("mcnemar_exact_p", "threshold", "no_difference_rejected"):
            result.pop(key, None)
        contrasts.append({**c, **result,
                          "test": not_computed("whether the benchmark's contrasts carry a test", "B150 Q8")})
    status = ("listed in the declaration" if contrasts else
              "none listed; " + not_computed("which of the benchmark's contrasts are reported", "B150 Q8"))
    return {"answer_key": "benchmark", "contrasts": contrasts, "status": status}


def analyse_pilot(items: list[dict], runs: list[dict], run_ids: list[str], declaration: dict) -> dict[str, Any]:
    reps = declaration["repetitions"]
    run_once = reps["run_once"]
    figures: dict[str, list] = {}
    for name in conditions_in(runs):
        figures[f"accuracy:{name}"] = accuracy_by_repetition(outcome_table(items, runs, name, run_once), len(runs))
    judge = declaration["runtime_judge"]
    judged_cases = [i for i in items if i["kind"] in judge["case_kinds"]]
    for condition in judge["conditions"]:
        for share, values in gate_shares_by_repetition(judged_cases, runs, condition).items():
            figures[f"{share}:{condition}"] = values
    return {
        "pilot": pilot_count(figures, z=reps["z"], half_width=reps["half_width"], cap=reps["cap"]),
        "per_call_accuracy": {"development": {name: per_call_summary(outcome_table(items, runs, name, run_once),
                                                                     len(runs))
                                              for name in conditions_in(runs)}},
        "failed_calls": failed_calls(runs, run_ids),
    }


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _share(share: dict[str, Any]) -> str:
    return f"{share['numerator']} of {share['denominator']} ({_rate(share['rate'])})"


def _interval(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    return f"[{value[0]:.3f}, {value[1]:.3f}]"


def render_markdown(report: dict[str, Any]) -> str:
    """The report as Markdown: shares as n of m, rates and intervals to three
    decimals, p values to six (ruling R24)."""
    group, decl = report["group"], report["declaration"]
    lines = [f"# E6 analysis, {report['mode']} run (spec G D-G84)", "",
             f"Group: first run {group['first_run']}, {group['repetitions']} run(s): {', '.join(group['runs'])}; "
             f"item set {group['item_set']}.",
             f"Declaration: {decl['file']} {decl['sha256'][:12]}; the runs carry {str(decl['runs_sha256'])[:12]}; "
             f"declared before the runs: {'yes' if decl['declared_before_runs'] else 'no'}.", ""]
    if report["mode"] == "pilot":
        pilot = report["pilot"]
        lines += ["## The pilot run's count", "", "| figure | by repetition | standard deviation | N it needs |",
                  "| --- | --- | --- | --- |"]
        for name, row in pilot["figures"].items():
            values = ", ".join(_rate(v) for v in row["by_repetition"])
            lines.append(f"| {name} | {values} | {_rate(row['standard_deviation'])} | {row['required'] or 'n/a'} |")
        lines.append("")
        if pilot["count"] is None:
            lines.append(f"N: {pilot['not_computed']}")
        else:
            lines.append(f"N = {pilot['count']} (cap {pilot['cap']}"
                         + (f", the cap binds: precision reached {pilot['precision_reached']:.4f})"
                            if pilot["cap_binds"] else ")"))
    else:
        family = report["primary_family"]
        lines += ["## The declared contrasts (hand-made legal test set)", "",
                  f"Contested cases left out: {', '.join(family['contested_left_out']) or 'none'}. "
                  f"Bonferroni: p below {family['alpha']} / {len(family['contrasts'])} = {family['threshold']:.4f}.", "",
                  "| contrast | reading | cases | condition right | against right | right only in the condition "
                  "| right only in the other | difference | 95% interval | McNemar exact p | no difference rejected |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for c in family["contrasts"]:
            if c["cases"] == 0:
                lines.append(f"| {c['id']} | {c['reading']} | 0 | {c['not_computed']} | | | | | | | |")
                continue
            lines.append(f"| {c['id']} | {c['reading']} | {c['cases']} | {c['condition_right']} | "
                         f"{c['against_right']} | {c['condition_only_right']} | {c['against_only_right']} | "
                         f"{c['difference']:.3f} | {_interval(c['interval'])} | {c['mcnemar_exact_p']:.6f} | "
                         f"{'yes' if c['no_difference_rejected'] else 'no'} |")
        secondary = report["secondary"]
        lines += ["", f"## The benchmark's contrasts (secondary, outside the family): {secondary['status']}", ""]
        for c in secondary["contrasts"]:
            lines.append(f"- {c['id']}: " + (c["not_computed"] if c["cases"] == 0 else
                         f"{c['cases']} cases, difference {c['difference']:.3f}, 95% interval "
                         f"{_interval(c['interval'])}; test: {c['test']}"))
        lines += ["", "## The runtime judge on the answers it gates", ""]
        for condition, block in report["runtime_judge"].items():
            lines += [f"### {condition} ({block['answers']} answers over {block['cases']} cases; "
                      f"{len(block['failed_calls_left_out'])} failed call(s) left out)", "",
                      "| share | value | 95% interval |", "| --- | --- | --- |"]
            lines += [f"| {share} | {_share(block['shares'][share])} | {_interval(block['intervals'][share])} |"
                      for share in SHARES]
            lines.append("")
        lines += [f"The four measures over the repetitions: {report['four_measures']['over_repetitions']}; "
                  "each run's figures are in the JSON file, under four_measures.by_run.", ""]
    lines += ["## Per-call accuracy and run-to-run variation (descriptive)", ""]
    for key, block in report["per_call_accuracy"].items():
        lines += [f"### {key}", "", "| condition | right of calls | share | by repetition | standard deviation |",
                  "| --- | --- | --- | --- | --- |"]
        for name, s in block.items():
            lines.append(f"| {name} | {s['right']} of {s['calls']} | {_rate(s['share'])} | "
                         f"{', '.join(_rate(v) for v in s['by_repetition'])} | {_rate(s['standard_deviation'])} |")
        lines.append("")
    lines += ["## Failed calls (each counted wrong)", ""]
    lines += [f"- {f['run']} {f['condition']} {f['case']}: {f['error']}" for f in report["failed_calls"]] or ["- none"]
    if report["notes"]:
        lines += ["", "## Notes", ""] + [f"- {note}" for note in report["notes"]]
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix="tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--group", required=True, help="record id of the group's first run")
    parser.add_argument("--pilot", action="store_true", help="the pilot run's group: report the count N")
    parser.add_argument("--pilot-analysis", default=None, help="record id of the pilot run's analysis (a main run)")
    parser.add_argument("--declaration", type=Path, default=DECLARATION_PATH)
    parser.add_argument("--gold", type=Path, default=harness.GOLD_SEED_PATH)
    parser.add_argument("--benchmark", type=Path, default=None,
                        help="the benchmark payload the runs read (default: the frozen sample; with --pilot "
                             "the development set payload)")
    parser.add_argument("--dump-dir", type=Path, default=ROOT / "data" / "graph_dumps")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="where the two files go (default: eval/results/analyses/<record id>)")
    parser.add_argument("--no-record", action="store_true", help="write no evaluation record (needs --out-dir)")
    args = parser.parse_args(argv)
    mode = "pilot" if args.pilot else "main"
    if args.pilot and args.pilot_analysis:
        print("refusing: --pilot reads no pilot analysis; drop --pilot-analysis")
        return 2
    if not args.pilot and args.pilot_analysis is None:
        print("refusing: a main run's analysis needs --pilot-analysis, the record of the pilot run that fixed "
              "its count (spec G D-G84 (5))")
        return 2
    if args.no_record and args.out_dir is None:
        print("refusing: --no-record has no record id to name its directory; pass --out-dir")
        return 2
    try:
        declaration = load_declaration(args.declaration)
        reader = EvaluationRecordStore(args.dump_dir, create=False)
        group, notes, first_started = group_records(reader, args.group)
        notes.append(provisional_note(declaration))
        pilot = pilot_record(reader, args.pilot_analysis, group[0], first_started) if mode == "main" else None
        refusal = group_refusal(group, mode=mode, declaration=declaration,
                                pilot_count_=pilot["count"] if pilot else None)
        if refusal is None and pilot is not None:
            refusal = pilot_instrument_refusal(reader, pilot["record_id"], group[0])
        if refusal is not None:
            raise Refused(refusal)
        files = key_files(args, mode)
        items = group_items(group[0], files, mode)
        checkpoints = [kept_copy(reader, record, "checkpoint") for record in group]
        runs = [run_results(path) for path in checkpoints]
        run_ids = [record["record_id"] for record in group]
        ours, theirs = declaration_sha256(args.declaration), _input(group[0], "e6_declaration")
        if ours != theirs:
            notes.append(POST_HOC_NOTE)
        if mode == "main":
            summaries = [json.loads(kept_copy(reader, record, "summary").read_text(encoding="utf-8"))
                         for record in group]
            body = {"pilot": pilot, **analyse_main(items, runs, run_ids, summaries, declaration)}
        else:
            body = analyse_pilot(items, runs, run_ids, declaration)
    except (Refused, AnalysisError, DeclarationError, EvaluationRecordError) as exc:
        print(f"refusing: {exc}")
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"refusing: {exception_reason(exc)}")
        return 2
    ids = [i["id"] for i in items]
    store = None if args.no_record else EvaluationRecordStore(args.dump_dir)
    record_id = None
    if store is not None:
        inputs = [input_ref("e6_declaration", args.declaration)]
        inputs += [input_ref(kind, path) for kind, path in files.items()]
        inputs += [input_ref("run_checkpoint", path) for path in checkpoints]
        # pilot_count: the count the analysis fixed (pilot) or read (main: the pilot analysis's, the group's size)
        record_id = store.begin(
            kind="analysis", step="E6", command="analyse_ablations",
            argv=list(argv) if argv is not None else sys.argv[1:], inputs=inputs, build=dict(group[0]["build"]),
            config={"code_version": code_version(ROOT), "mode": mode, "declared_before_runs": ours == theirs,
                    # the bootstrap draws come from Python's random module (ruling R3): the interpreter is named
                    "python_version": platform.python_version(),
                    "pilot_record_id": args.pilot_analysis, "pilot_count": body["pilot"]["count"],
                    "pilot_count_reason": body["pilot"].get("not_computed")},
            item_selection=ids, intended_items=ids, relations={"compares": run_ids})
    try:
        report = {"analysis": ANALYSIS_VERSION, "mode": mode, "record_id": record_id,
                  "group": {"first_run": run_ids[0], "runs": run_ids, "repetitions": len(run_ids),
                            "item_set": (group[0].get("config") or {}).get("item_set")},
                  "declaration": {"file": args.declaration.name, "sha256": ours, "runs_sha256": theirs,
                                  "declared_before_runs": ours == theirs},
                  **body, "notes": notes}
        out_dir = args.out_dir or RESULTS_DIR / ANALYSES_DIRNAME / str(record_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path, text_path = out_dir / JSON_NAME, out_dir / TEXT_NAME
        _write(json_path, json.dumps(report, ensure_ascii=False, indent=1))
        _write(text_path, render_markdown(report))
        if store is not None and record_id is not None:
            store.finish(record_id, status="completed", completed_items=ids, intended_items=ids,
                         outputs=[store.keep_output(record_id, "analysis", json_path),
                                  store.keep_output(record_id, "analysis_text", text_path)],
                         counts={"runs": len(run_ids), "failed_calls": len(report["failed_calls"])}, notes=notes)
    except BaseException as exc:
        # a record never stays running (B97 item 9): a failure after it was opened ends it failed with the reason
        reason = exception_reason(exc)
        if store is not None and record_id is not None:
            end_failed(store, record_id, reason, notes=notes)
        if not isinstance(exc, Exception):
            raise
        print(f"failed: {reason}" + (f"; evaluation record {record_id} ended failed" if record_id else ""))
        return 2
    if store is not None and record_id is not None:
        print(f"evaluation record {record_id} written under {store.dir}")
    print(f"wrote {json_path.name} and {text_path.name} in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

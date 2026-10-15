"""The README.md and changed_verdicts.csv of a re-judged build, from its files and its record.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

Card B173, the subcommand `report`. Everything printed is computed from the
source build's published files (read through source.py, never written),
the new build's norms and alignments files and its build record; a value
neither holds reads "not recorded". The verdicts that changed: at Layer 2,
every norm whose verdict differs from the source norm of the same norm_id;
at Layer 3, every kept assertion (the same id in both files) whose verdict
differs, every source assertion the new build dropped (its norm no longer
accepted) and every new assertion (an id the source file does not hold, its
norm newly accepted). The cost is the usage the inference backends reported,
summed over every rejudge execution of the record (a stopped one included),
at the list prices of config/model_prices.json (cost.py). An existing
README.md or changed_verdicts.csv is replaced only with --overwrite (R11).
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from tere4ai.graph_store.build_record import BuildRecordStore, RecordError
from tere4ai.judge.config import ConfigurationError, load_model_prices
from tere4ai.rejudge.cost import usage_cost, usd
from tere4ai.rejudge.norms import VERDICTS, verdict_counts
from tere4ai.rejudge.run import Refusal, refuse
from tere4ai.rejudge.source import SourceBuild, SourceError, read_source

README_FILE = "README.md"
CSV_FILE = "changed_verdicts.csv"
CSV_COLUMNS = ("layer", "id", "source_unit_or_norm", "source_verdict", "new_verdict")
DROPPED = "dropped, norm not accepted"
NEW = "new, norm newly accepted"
NOT_RECORDED = "not recorded"
NORMS_COMMAND = "rejudge_norms"
ALIGNMENTS_COMMAND = "rejudge_alignments"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise refuse(f"{what} {path} is missing; run `norms` and `alignments` with the same --out-dir and "
                     "--name first") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise refuse(f"{what} {path} cannot be read ({type(exc).__name__})") from None


def _or_not_recorded(value: Any) -> str:
    return NOT_RECORDED if value is None or value == "" else str(value)


def _count(value: Any) -> str:
    """A whole number with thousands separators, or "not recorded"."""
    return f"{value:,}" if isinstance(value, int) else NOT_RECORDED


def _utc(stamp: Any) -> str:
    """An ISO time as "YYYY-MM-DD HH:MM:SS UTC", or "not recorded"."""
    if not isinstance(stamp, str) or not stamp:
        return NOT_RECORDED
    try:
        return datetime.fromisoformat(stamp).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return stamp


def _verdicts(counts: Any) -> str:
    """Verdict counts in the fixed order, "accepted 3, rejected 1, needs_human_review 0"."""
    if not isinstance(counts, dict):
        return NOT_RECORDED
    keys = [*VERDICTS, *(k for k in counts if k not in VERDICTS)]
    return ", ".join(f"{key} {counts.get(key, 0)}" for key in keys)


def _code_version() -> str:
    """The checkout that writes the report: the short HEAD, with a note when a
    tracked file has uncommitted changes; "not recorded" without git."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return NOT_RECORDED
    return f"tere4ai2 {head}" + (" with uncommitted changes" if dirty else "")


def changed_verdict_rows(source_norms: list[dict[str, Any]], norms: list[dict[str, Any]],
                         source_assertions: list[dict[str, Any]], assertions: list[dict[str, Any]],
                         dropped_ids: list[str]) -> list[dict[str, str]]:
    """The rows of changed_verdicts.csv, in four runs: the changed norms, the
    changed kept assertions and the new assertions in the new files' order,
    the dropped assertions between the last two in the order the stats list
    them."""
    before_norm = {n["norm_id"]: n for n in source_norms}
    rows = [{"layer": "layer2", "id": n["norm_id"], "source_unit_or_norm": n.get("source_node_id", ""),
             "source_verdict": before_norm[n["norm_id"]].get("judge_verdict", ""),
             "new_verdict": n.get("judge_verdict", "")}
            for n in norms
            if n["norm_id"] in before_norm and before_norm[n["norm_id"]].get("judge_verdict") != n.get("judge_verdict")]
    before = {a["id"]: a for a in source_assertions}
    rows += [{"layer": "layer3", "id": a["id"], "source_unit_or_norm": a.get("source_norm_id", ""),
              "source_verdict": before[a["id"]].get("judge_verdict", ""), "new_verdict": a.get("judge_verdict", "")}
             for a in assertions
             if a["id"] in before and before[a["id"]].get("judge_verdict") != a.get("judge_verdict")]
    for assertion_id in dropped_ids:
        old = before.get(assertion_id) or {}
        rows.append({"layer": "layer3", "id": assertion_id, "source_unit_or_norm": old.get("source_norm_id", ""),
                     "source_verdict": old.get("judge_verdict", ""), "new_verdict": DROPPED})
    rows += [{"layer": "layer3", "id": a["id"], "source_unit_or_norm": a.get("source_norm_id", ""),
              "source_verdict": NEW, "new_verdict": a.get("judge_verdict", "")}
             for a in assertions if a["id"] not in before]
    return rows


def _executions(record: dict[str, Any], command: str) -> list[dict[str, Any]]:
    return [ex for ex in record.get("executions") or [] if ex.get("command") == command]


def _usage_row(executions: list[dict[str, Any]], component: str,
               prices: dict[str, dict[str, Any]]) -> tuple[dict[str, int] | None, float | None, list[str]]:
    """One component's usage summed over the executions, its USD at list price
    (None when an execution's model has no price row) and the models priced."""
    if not executions or not any((ex.get("usage") or {}).get(component) for ex in executions):
        return None, None, []
    total = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    cost: float | None = 0.0
    models: list[str] = []
    for ex in executions:
        usage = (ex.get("usage") or {}).get(component) or {}
        for key in total:
            total[key] += int(usage.get(key, 0) or 0)
        model = (ex.get("models") or {}).get(f"{component}_model")
        if not (usage.get("input_tokens") or usage.get("output_tokens")):
            continue
        if model not in models:
            models.append(model)
        if cost is not None and model in prices:
            cost += usage_cost(usage, prices[model])
        else:
            cost = None
    return total, cost, models


def _cost_cells(usage: dict[str, int] | None, cost: float | None, priced: bool) -> list[str]:
    if usage is None:
        return [NOT_RECORDED] * 4
    return [_count(usage["calls"]), _count(usage["input_tokens"]), _count(usage["output_tokens"]),
            usd(cost) if cost is not None else ("no price row" if priced else usd(0.0))]


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in rows]
    return lines


def _publication_cell(record: dict[str, Any], out_dir: Path) -> str:
    publication = record.get("publication")
    if not isinstance(publication, dict):
        return "not published yet"
    cell = (f"`{_or_not_recorded(publication.get('build_id'))}`, chain `{_or_not_recorded(publication.get('chain_id'))}`"
            f", Build {_or_not_recorded(publication.get('build_number'))} of this folder, published "
            f"{_utc(publication.get('published_at'))}")
    gates = publication.get("gates") or []
    postload = publication.get("postload_gates") or []
    if gates or postload:
        passed = sum(1 for g in [*gates, *postload] if g.get("ok"))
        cell += f", {passed} of {len(gates) + len(postload)} publication and post-load gates ok"
    try:
        pointer = json.loads((out_dir / "ACTIVE_MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pointer = None
    if isinstance(pointer, dict) and pointer.get("chain_id") == publication.get("chain_id"):
        cell += f"; activated {_utc(pointer.get('activated_at'))}"
    return cell


def _price_line(model: str, prices: dict[str, dict[str, Any]]) -> str:
    row = prices.get(model)
    if row is None:
        return f"- {model}: no price row in config/model_prices.json"
    pricing = row.get("pricing") or {}
    return (f"- {model}: {row['input']:.2f} USD per million input tokens and {row['output']:.2f} per million "
            f"output tokens (config/model_prices.json, read on {_or_not_recorded(pricing.get('read_on'))} from "
            f"{_or_not_recorded(pricing.get('url'))})")


def _carried_line(step: str, usage: Any, model: Any, prices: dict[str, dict[str, Any]]) -> str:
    if not isinstance(usage, dict):
        return f"- {step}: {NOT_RECORDED}"
    if model in prices:
        cost = usd(usage_cost(usage, prices[model])) + " USD at list price"
    elif model is None:
        cost = "no price, the model is not recorded"
    else:
        cost = f"no price row for {model}"
    return (f"- {step} ({_or_not_recorded(model)}): {_count(usage.get('calls'))} calls, "
            f"{_count(usage.get('input_tokens'))} input tokens, {_count(usage.get('output_tokens'))} output tokens, "
            f"{cost}")


def _files_section(out_dir: Path, name: str) -> list[str]:
    lines = [f"- `layer1.json`, `norms_{name}.json`, `alignments_{name}.json`: the build (layer1.json a byte copy "
             "of the source's)."]
    published = [f for f in ("BUILD_CHAIN_CURRENT.txt", "NEO4J_TARGET.json", "ACTIVE_MANIFEST.json")
                 if (out_dir / f).is_file()]
    chains = sorted(p.name for p in out_dir.glob("build_chain_*.json"))
    if (out_dir / "publications").is_dir():
        chains.append("publications/")
    if chains or published:
        lines.append(f"- {', '.join(f'`{f}`' for f in [*chains, *published])}: publication and activation.")
    lines.append("- `build_records/`: the execution records (inputs by digest, models, prompts, counts, usage, "
                 "gates).")
    logs = sorted(p.name for p in (out_dir / "logs").glob("*")) if (out_dir / "logs").is_dir() else []
    if logs:
        lines.append(f"- {', '.join(f'`logs/{f}`' for f in logs)}: the judges' and the generator's events, each "
                     "with the sha256 of its input.")
    lines.append(f"- `{README_FILE}` and `{CSV_FILE}`: this report (`python -m tere4ai.rejudge report`).")
    return lines


def _render(source: SourceBuild, out_dir: Path, name: str, record_id: str, record: dict[str, Any],
            norms_payload: dict[str, Any], alignments_payload: dict[str, Any], source_norms_payload: dict[str, Any],
            source_alignments_payload: dict[str, Any], rows: list[dict[str, str]],
            prices: dict[str, dict[str, Any]]) -> str:
    build = norms_payload.get("build") or {}
    rejudge = norms_payload.get("rejudge") or {}
    abuild = alignments_payload.get("build") or {}
    arejudge = abuild.get("alignment_rejudge") or {}
    emodels = build.get("extraction_models") or {}
    amodels = abuild.get("alignment_models") or {}
    judge = _or_not_recorded(emodels.get("judge_model") or rejudge.get("judge_model"))
    source_judge = _or_not_recorded(rejudge.get("source_judge_model"))
    source_alignment_judge = _or_not_recorded(
        ((source_alignments_payload.get("build") or {}).get("alignment_models") or {}).get("judge_model"))
    norms_runs, align_runs = _executions(record, NORMS_COMMAND), _executions(record, ALIGNMENTS_COMMAND)
    made_on = min((ex.get("started_at") for ex in [*norms_runs, *align_runs] if ex.get("started_at")), default=None)
    made_on_text = _utc(made_on)[:10] if made_on else NOT_RECORDED
    pv, apv = build.get("prompt_version"), abuild.get("alignment_prompt_version")
    out: list[str] = [
        f"# Build {name}", "",
        f"Generator output of {source.name}, judged by {judge} (effort {_or_not_recorded(emodels.get('judge_effort'))}, "
        f"temperature {_or_not_recorded(emodels.get('judge_temperature'))}), made by `python -m tere4ai.rejudge` "
        f"(card B173) on {made_on_text}.", "",
        "## What it is", "",
    ]
    in_flight = sorted({str((ex.get("config") or {}).get("max_in_flight")) for ex in [*norms_runs, *align_runs]
                        if (ex.get("config") or {}).get("max_in_flight") is not None})
    ran = [f"{ex.get('command')} {_utc(ex.get('started_at'))} to {_utc(ex.get('ended_at'))} ({ex.get('status')})"
           for ex in record.get("executions") or []]
    what = [
        ["Build id", _publication_cell(record, out_dir)],
        ["Alias", f"`{name}`"],
        ["Build record", f"`{record_id}`"],
        ["Source build", f"`{source.name}` (chain `{source.chain_id}`, build record `{source.record_id}`), read "
                         "only"],
        ["Generator (carried)", f"{_or_not_recorded(emodels.get('generator_model'))}, effort "
                                f"{_or_not_recorded(emodels.get('generator_effort'))}, temperature "
                                f"{_or_not_recorded(emodels.get('generator_temperature'))}, JSON mode "
                                f"{_or_not_recorded(emodels.get('generator_json_mode'))}; its stored output is the "
                                "source's, and at Layer 3 it aligned only the newly accepted norms"],
        ["Judges", f"{judge}, effort {_or_not_recorded(emodels.get('judge_effort'))}, temperature "
                   f"{_or_not_recorded(emodels.get('judge_temperature'))}, the extraction judge; "
                   f"{_or_not_recorded(amodels.get('judge_model'))}, effort "
                   f"{_or_not_recorded(amodels.get('judge_effort'))}, temperature "
                   f"{_or_not_recorded(amodels.get('judge_temperature'))}, the alignment judge"],
        ["Prompts", f"extract_norms {_or_not_recorded(pv)} (the source's generator), judge_norms "
                    f"{_or_not_recorded(pv)}, align_hleg {_or_not_recorded(apv)}, judge_alignment "
                    f"{_or_not_recorded(apv)}"],
        ["Code", f"{_code_version()} (the checkout that wrote this report; the records do not name the code)"],
        ["Calls in flight", ", ".join(in_flight) if in_flight else NOT_RECORDED],
        ["Ran", "; ".join(ran) if ran else NOT_RECORDED],
    ]
    out += _table(["", ""], what)

    norms, source_norms = norms_payload.get("norms") or [], source_norms_payload.get("norms") or []
    stats, astats = norms_payload.get("stats") or {}, alignments_payload.get("stats") or {}
    assertions = alignments_payload.get("assertions") or []
    source_assertions = source_alignments_payload.get("assertions") or []
    source_ids = {a["id"] for a in source_assertions}
    new_assertions = [a for a in assertions if a["id"] not in source_ids]
    newly = astats.get("newly_aligned_norms") or []
    dropped = astats.get("dropped_assertions") or []
    layer2_changed = sum(1 for r in rows if r["layer"] == "layer2")
    layer3_changed = sum(1 for r in rows if r["layer"] == "layer3" and r["source_verdict"] != NEW
                         and r["new_verdict"] != DROPPED)
    norms_total, skipped = astats.get("norms_total"), astats.get("norms_skipped_not_accepted")
    aligned = norms_total - skipped if isinstance(norms_total, int) and isinstance(skipped, int) else None
    mechanical = astats.get("mechanical_rejects")
    out += [
        "", "## Counts", "",
        "Layer 2 (no generator call):", "",
        f"- candidate norms judged again: {_count(len(norms))} (the source: {_count(len(source_norms))}), on "
        f"{_count(stats.get('source_units'))} source units",
        f"- verdicts: {_verdicts(verdict_counts(norms))} (the source's: {_verdicts(verdict_counts(source_norms))})",
        f"- norms whose verdict changed: {layer2_changed}",
        "", "Layer 3:", "",
        f"- norms: {_count(norms_total)}, of which {_count(aligned)} accepted and aligned, {_count(skipped)} not "
        f"accepted and skipped; {_count(astats.get('zero_alignment_norms'))} accepted norms with no alignment",
        f"- candidates: {_count(astats.get('candidates'))}; stored candidates carried and judged again: "
        f"{_count(astats.get('carried_candidates'))}; stopped by the quote check: "
        f"{_count(len(mechanical) if isinstance(mechanical, list) else None)}",
        f"- newly accepted norms aligned by the generator: {len(newly)}; their assertions: {len(new_assertions)}",
        f"- source assertions dropped (their norm no longer accepted): {len(dropped)}",
        f"- kept assertions whose verdict changed: {layer3_changed}",
        f"- verdicts of the assertions: {_verdicts(astats.get('verdicts'))} (the source's: "
        f"{_verdicts(verdict_counts(source_assertions))})",
    ]

    l2_usage, l2_cost, l2_models = _usage_row(norms_runs, "judge", prices)
    g3_usage, g3_cost, g3_models = _usage_row(align_runs, "generator", prices)
    j3_usage, j3_cost, j3_models = _usage_row(align_runs, "judge", prices)
    cost_rows = [
        [f"Layer 2 judge ({', '.join(l2_models) or judge})", *_cost_cells(l2_usage, l2_cost, bool(l2_models))],
        [f"Layer 3 generator for newly accepted norms only ({', '.join(g3_models) or 'no call'})",
         *_cost_cells(g3_usage, g3_cost, bool(g3_models))],
        [f"Layer 3 judge ({', '.join(j3_models) or _or_not_recorded(amodels.get('judge_model'))})",
         *_cost_cells(j3_usage, j3_cost, bool(j3_models))],
    ]
    known = [u for u in (l2_usage, g3_usage, j3_usage) if u is not None]
    if known:
        total = {key: sum(u[key] for u in known) for key in ("calls", "input_tokens", "output_tokens")}
        costs = [c for u, c, m in ((l2_usage, l2_cost, l2_models), (g3_usage, g3_cost, g3_models),
                                   (j3_usage, j3_cost, j3_models)) if u is not None]
        total_cost = None if any(c is None for c in costs) else sum(costs)
        cost_rows.append(["Total", *_cost_cells(total, total_cost, True)])
    else:
        cost_rows.append(["Total", *[NOT_RECORDED] * 4])
    priced_models = list(dict.fromkeys([*l2_models, *g3_models, *j3_models]))
    stops = sorted({usd(float((ex.get("config") or {})["cost_stop_usd"])) for ex in [*norms_runs, *align_runs]
                    if (ex.get("config") or {}).get("cost_stop_usd") is not None})
    out += [
        "", "## Cost, as the inference backends report it", "",
        f"Summed over the build record's {len(norms_runs)} {NORMS_COMMAND} and {len(align_runs)} "
        f"{ALIGNMENTS_COMMAND} executions (every attempt, a stopped one included); output tokens include "
        "reasoning, as billed; every input token at the full input price. build.extraction_usage and "
        "build.alignment_usage in the norms and alignments files hold only the last attempt's usage, while this "
        "table sums every attempt in the record.", "",
        *_table(["Step", "Calls", "Input tokens", "Output tokens", "USD at list price"], cost_rows),
        "", "Prices:",
        *(_price_line(model, prices) for model in priced_models),
        *([] if priced_models else [f"- {NOT_RECORDED}: no rejudge execution reported tokens"]),
        "",
        f"Cost stop (--cost-stop): {', '.join(stops) + ' USD' if stops else NOT_RECORDED}. The stop is checked "
        "before each group or batch, so a run can pass it by at most the group or batch in flight (one Article or "
        "Annex of judge calls at Layer 2, one batch of norms at Layer 3).", "",
        "The source's generator output is carried, not made again; what it cost when the source was built:",
        _carried_line("Layer 2 generator", rejudge.get("carried_generator_usage"),
                      emodels.get("generator_model"), prices),
        _carried_line("Layer 3 generator", arejudge.get("carried_generator_usage"),
                      amodels.get("generator_model"), prices),
    ]

    by_norm = {n["norm_id"]: n for n in norms}
    source_by_id = {a["id"]: a for a in source_assertions}
    l2_rows = [[f"`{r['id']}`", f"`{r['source_unit_or_norm']}`", r["source_verdict"], r["new_verdict"]]
               for r in rows if r["layer"] == "layer2"]
    l3_rows = [[f"`{r['id']}`", r["source_verdict"], r["new_verdict"]] for r in rows
               if r["layer"] == "layer3" and r["source_verdict"] != NEW and r["new_verdict"] != DROPPED]
    dropped_rows = [[f"`{aid}`", f"`{(source_by_id.get(aid) or {}).get('source_norm_id', NOT_RECORDED)}`",
                     (source_by_id.get(aid) or {}).get("judge_verdict", NOT_RECORDED),
                     _or_not_recorded((by_norm.get((source_by_id.get(aid) or {}).get("source_norm_id")) or {})
                                      .get("judge_verdict"))]
                    for aid in dropped]
    new_rows = [[f"`{norm_id}`", str(sum(1 for a in new_assertions if a.get("source_norm_id") == norm_id)),
                 str(sum(1 for a in new_assertions if a.get("source_norm_id") == norm_id
                         and a.get("judge_verdict") == "accepted"))]
                for norm_id in newly]
    out += [
        "", f"## Verdicts that changed against {source_judge}", "",
        f"Every row is in `{CSV_FILE}` too (layer, id, source unit or norm, source verdict, new verdict).", "",
        f"Layer 2, norms ({len(l2_rows)}):", "",
        *(_table(["Norm", "Source unit", source_judge, judge], l2_rows) if l2_rows else ["None."]),
        "", f"Layer 3, kept assertions whose verdict changed ({len(l3_rows)}):", "",
        *(_table(["Assertion", source_alignment_judge, _or_not_recorded(amodels.get("judge_model"))], l3_rows)
          if l3_rows else ["None."]),
        "", f"Layer 3, assertions dropped because their norm is no longer accepted ({len(dropped_rows)}):", "",
        *(_table(["Assertion", "Norm", source_alignment_judge, f"the norm under {judge}"], dropped_rows)
          if dropped_rows else ["None."]),
        "", f"Layer 3, newly accepted norms aligned by the generator ({len(new_rows)}):", "",
        *(_table(["Norm", "New assertions", "accepted"], new_rows) if new_rows else ["None."]),
        "", "## Files", "",
        *_files_section(out_dir, name),
    ]
    return "\n".join(out) + "\n"


def _csv_text(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_report(source: Path | str, out_dir: Path | str, name: str, *, overwrite: bool = False) -> tuple[Path, Path]:
    """Write NEW/README.md and NEW/changed_verdicts.csv for the re-judged build
    NAME made from the published build in source, and return their paths.
    Raises Refusal: a source that cannot be read, a missing norms or
    alignments file or record (exit 2), the price table unreadable (exit 4),
    or an existing report without overwrite (exit 1)."""
    out_dir = Path(out_dir)
    readme, csv_path = out_dir / README_FILE, out_dir / CSV_FILE
    existing = [p.name for p in (readme, csv_path) if p.exists()]
    if existing and not overwrite:
        raise Refusal(1, f"refusing to overwrite {' and '.join(existing)} in {out_dir}; pass --overwrite to "
                         "replace the report")
    try:
        src = read_source(source)
    except SourceError as exc:
        raise refuse(str(exc)) from None
    norms_payload = _read_json(out_dir / f"norms_{name}.json", "the norms file")
    alignments_payload = _read_json(out_dir / f"alignments_{name}.json", "the alignments file")
    source_norms_payload = _read_json(src.norms_path, "the source norms file")
    source_alignments_payload = _read_json(src.alignments_path, "the source alignments file")
    if (norms_payload.get("rejudge") or {}).get("source_record_id") != src.record_id:
        raise refuse(f"norms_{name}.json was not re-judged from the source record {src.record_id} that --source names")
    store = BuildRecordStore(out_dir, create=False)
    try:
        record_id = store.resolve(name)
        record = store.read(record_id) if record_id else None
    except RecordError as exc:
        raise refuse(f"the build record {name} cannot be read: {exc}") from None
    if record is None:
        raise refuse(f"there is no build record {name} in {out_dir}")
    try:
        prices = load_model_prices()
    except ConfigurationError as exc:
        raise Refusal(4, f"stopped: {exc}") from None
    rows = changed_verdict_rows(source_norms_payload.get("norms") or [], norms_payload.get("norms") or [],
                                source_alignments_payload.get("assertions") or [],
                                alignments_payload.get("assertions") or [],
                                (alignments_payload.get("stats") or {}).get("dropped_assertions") or [])
    text = _render(src, out_dir, name, record_id, record, norms_payload, alignments_payload, source_norms_payload,
                   source_alignments_payload, rows, prices)
    readme.write_text(text, encoding="utf-8")
    csv_path.write_text(_csv_text(rows), encoding="utf-8")
    return readme, csv_path

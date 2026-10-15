"""Layer 3 re-judged: the stored alignment candidates judged again, the generator
called only for the norms the new Layer 2 judge newly accepts.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

Each norm of the re-judged norms file is taken against its verdict in the
source norms file (B173 R9):

- not accepted now: skipped and counted in norms_skipped_not_accepted; its
  source assertions are listed in dropped_assertions and not written;
- accepted by both: each stored assertion is turned back into the candidate
  its judge read (alignment_candidate_of, R4), checked again by the quote
  check (a failure is the pipeline's mechanical rejection, no judge call) and
  judged with the message align_hleg builds today (judge_alignment), keeping
  the assertion id, its judge run id and its alignment run id (R6); the
  norm's source mechanical rejections, invalid candidates and failures are
  carried unchanged; a norm with none of these counts in zero_alignment_norms;
- accepted now and not before: aligned by align_norms (generator, quote
  check, judge), in one call per batch, and listed in newly_aligned_norms.

A norm accepted by both whose source alignment failed is carried as failed,
not aligned again, so the generator is called for exactly the newly accepted
norms. Everything is assembled in the norms' order, a new norm's results at
its place in the batch, and every assertion is validated as align_norms
validates it.

The judge (and the generator of the newly accepted norms) runs at the code's
default prompt version (B174 R4), which may be newer than the source's: a
source made under an older version is accepted when the candidate and the
handling of the judge's relation type are the same under both
(same_candidate_shape). The judge's message holds no version-dependent part.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tere4ai.align_hleg.pipeline import (
    _PROMPTS_TAKING_ANY_CORRECTION,
    DEFAULT_PROMPT_VERSION,
    MECHANICAL_JUDGE_MODEL,
    SPREAD_KEYS,
    _alignments_validator,
    _id_suffix,
    align_norms,
    alignment_candidate_of,
    assertion_of,
    judge_alignment,
    quote_check,
    spread_of,
)
from tere4ai.extract_norms.model_clients import ModelClient
from tere4ai.extract_norms.pipeline import load_prompt, prompt_sha256
from tere4ai.parallel_calls import run_in_flight
from tere4ai.rejudge.norms import GENERATOR_KEYS, VERDICTS, materialised_refusal

ALIGN_PROMPT_KIND = "align_hleg"
JUDGE_PROMPT_KIND = "judge_alignment"
# R5: a v1 assertion keeps no proposed_relation_type (DEC-28), so its
# candidate cannot be rebuilt.
UNREBUILDABLE_PROMPT_VERSIONS = ("v1",)
# The judge's fields of alignment_models, which the new judge sets again; the
# generator's are the source's (R5 checks the environment names the same).
JUDGE_MODEL_KEYS = ("judge_model", "judge_effort", "judge_temperature", "model_parameters_sha256")


@dataclass(frozen=True)
class SourceAlignments:
    """The source alignments file, indexed by norm (each list in the file's order)."""

    assertions_by_norm: dict[str, list[dict[str, Any]]]
    judge_runs_by_id: dict[str, dict[str, Any]]
    # (the mechanical judge run, its stats.mechanical_rejects entry)
    mechanical_by_norm: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]
    invalid_by_norm: dict[str, list[dict[str, Any]]]
    failed_by_norm: dict[str, list[dict[str, Any]]]
    mapping_runs_by_id: dict[str, dict[str, Any]]


_INDEXED_ASSERTION = re.compile(r"align:.+:\d+")
_INDEXED_JUDGE_RUN = re.compile(r"judgerun:mapping:.+:c\d+")


def judge_run_prefix(norm_id: str) -> str:
    """The prefix every judge run of a norm's candidates carries in align_norms."""
    return f"judgerun:mapping:{_id_suffix(norm_id)}:"


def _by_norm(entries: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        out.setdefault(entry.get(key), []).append(entry)
    return out


def source_index(payload: dict[str, Any], requirement_ids: Collection[str]) -> SourceAlignments:
    """Index the source alignments file. A mechanical judge run is matched to its
    norm by the id prefix judgerun:mapping:<norm id without 'norm:'>: and paired,
    in order, with that norm's stats.mechanical_rejects entries; a run or an
    entry left unpaired raises ValueError, as do an assertion or judge run id
    that does not end in its candidate's index (align_norms' ids), an
    assertion whose target is not among requirement_ids (the HLEG nodes), and
    any invalid assertion (stats.invalid_assertions: a judged candidate whose
    assertion failed the schema, which no stored assertion lets this command
    judge again or carry)."""
    stats = payload.get("stats") or {}
    invalid_assertions = stats.get("invalid_assertions") or []
    if invalid_assertions:
        raise ValueError(f"the source holds {len(invalid_assertions)} invalid assertion(s), which this command "
                         "cannot carry or re-judge")
    judge_runs = payload.get("judge_runs") or []
    mechanical_runs = [run for run in judge_runs if run.get("judge_model") == MECHANICAL_JUDGE_MODEL]
    mechanical_by_norm: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    paired: set[str] = set()
    for norm_id, rejects in _by_norm(stats.get("mechanical_rejects") or [], "norm_id").items():
        prefix = judge_run_prefix(str(norm_id))
        runs = [run for run in mechanical_runs if run["id"].startswith(prefix)]
        if len(runs) != len(rejects):
            raise ValueError(f"the source alignments hold {len(runs)} mechanical judge run(s) for {norm_id} and "
                             f"{len(rejects)} mechanical reject(s); they cannot be paired")
        paired.update(run["id"] for run in runs)
        mechanical_by_norm[norm_id] = list(zip(runs, rejects, strict=True))
    unpaired = [run["id"] for run in mechanical_runs if run["id"] not in paired]
    if unpaired:
        raise ValueError(f"the source mechanical judge run {unpaired[0]} has no mechanical reject of its norm")
    # the ids a re-judged candidate keeps and is ordered by, in align_norms' form
    for assertion in payload.get("assertions") or []:
        if not (_INDEXED_ASSERTION.fullmatch(str(assertion.get("id")))
                and _INDEXED_JUDGE_RUN.fullmatch(str(assertion.get("judge_run_id")))):
            raise ValueError(f"the source assertion {assertion.get('id')} or its judge run "
                             f"{assertion.get('judge_run_id')} does not end in the candidate's index")
        if assertion.get("target_id") not in requirement_ids:
            raise ValueError(f"the source assertion {assertion.get('id')} names {assertion.get('target_id')!r}, "
                             "which is not one of the seven HLEG requirements")
    for run in mechanical_runs:
        if not _INDEXED_JUDGE_RUN.fullmatch(run["id"]):
            raise ValueError(f"the source mechanical judge run {run['id']} does not end in the candidate's index")
    return SourceAlignments(
        assertions_by_norm=_by_norm(payload.get("assertions") or [], "source_norm_id"),
        judge_runs_by_id={run["id"]: run for run in judge_runs},
        mechanical_by_norm=mechanical_by_norm,
        invalid_by_norm=_by_norm(stats.get("invalid_candidates") or [], "norm_id"),
        failed_by_norm=_by_norm(stats.get("norms_failed") or [], "norm_id"),
        mapping_runs_by_id={run["id"]: run for run in payload.get("mapping_runs") or []},
    )


def same_candidate_shape(source_version: str, judge_version: str) -> bool:
    """True when a candidate stored under source_version can be judged under
    judge_version (B174 R4): both rebuild the five-key candidate (neither is
    v1, DEC-28) and both handle a no_clear_relation correction alike."""
    return (source_version not in UNREBUILDABLE_PROMPT_VERSIONS
            and judge_version not in UNREBUILDABLE_PROMPT_VERSIONS
            and (source_version in _PROMPTS_TAKING_ANY_CORRECTION)
            == (judge_version in _PROMPTS_TAKING_ANY_CORRECTION))


def alignments_refusal(source_payload: dict[str, Any], public_models: dict[str, Any],
                       source_norms_sha256: str, judge_version: str = DEFAULT_PROMPT_VERSION) -> str | None:
    """Why the source alignments cannot be re-judged in this environment under
    the prompt version judge_version (R5, B174 R4), or None: a materialised
    reference file, a prompt version v1, an assertion without
    proposed_relation_type or whose generator_rationale is not a string (its
    candidate cannot be rebuilt), a judge version missing from the checkout or
    whose candidate or relation-type handling differs from the source
    version's, a source version's judge_alignment or align_hleg prompt whose
    text today differs from what the source's judge or alignment runs
    recorded, alignments made over another norms file than the source's, or a
    generator that is not the source's."""
    materialised = materialised_refusal(source_payload)
    if materialised:
        return materialised
    build = source_payload.get("build") or {}
    version = build.get("alignment_prompt_version")
    if not isinstance(version, str) or not version:
        return "the source alignments file names no alignment_prompt_version"
    if version in UNREBUILDABLE_PROMPT_VERSIONS:
        return (f"the source alignments were made under prompt version {version}, whose assertions keep no "
                "proposed_relation_type (DEC-28); their candidates cannot be rebuilt")
    for assertion in source_payload.get("assertions") or []:
        if not assertion.get("proposed_relation_type"):
            return (f"the source assertion {assertion.get('id', '(no id)')} has no proposed_relation_type (kept "
                    "before DEC-28); its candidate cannot be rebuilt")
        if not isinstance(assertion.get("generator_rationale"), str):
            return (f"the source assertion {assertion.get('id', '(no id)')} keeps no generator_rationale as text "
                    f"({assertion.get('generator_rationale')!r}); the generation-time judge read the generator's "
                    "rationale, so its candidate cannot be rebuilt")
    for kind in (JUDGE_PROMPT_KIND, ALIGN_PROMPT_KIND):
        try:
            load_prompt(kind, judge_version)
        except FileNotFoundError:
            return f"there is no {kind} prompt {judge_version} in this checkout"
    if not same_candidate_shape(version, judge_version):
        return (f"the source alignments were made under prompt version {version}, whose candidate or handling of "
                f"the judge's relation type differs from {judge_version}'s; their candidates cannot be judged "
                f"under {judge_version}")
    for kind, runs in ((JUDGE_PROMPT_KIND, [run for run in source_payload.get("judge_runs") or []
                                            if run.get("judge_model") != MECHANICAL_JUDGE_MODEL]),
                       (ALIGN_PROMPT_KIND, source_payload.get("mapping_runs") or [])):
        try:
            today = prompt_sha256(load_prompt(kind, version))
        except FileNotFoundError:
            return f"there is no {kind} prompt {version} in this checkout"
        recorded = sorted({str(run.get("prompt_sha256")) for run in runs})
        if any(digest != today for digest in recorded):
            whose = "judge runs" if kind == JUDGE_PROMPT_KIND else "alignment runs"
            return (f"the {kind} {version} prompt has sha256 {today} today; the source's {whose} recorded "
                    f"{', '.join(recorded)}")
    if build.get("alignment_input_sha256") != source_norms_sha256:
        return (f"the source alignments were made over a norms file with sha256 {build.get('alignment_input_sha256')}, "
                f"the source's norms file has {source_norms_sha256}")
    source_models = build.get("alignment_models") or {}
    differing = [key for key in GENERATOR_KEYS if source_models.get(key) != public_models.get(key)]
    if differing:
        return ("the generator in the environment differs from the source's alignment generator in "
                + ", ".join(f"{key} ({public_models.get(key)!r}, the source {source_models.get(key)!r})"
                            for key in differing))
    return None


def _candidate_index(judge_run_id: str) -> int:
    """The candidate's place in its generator reply, from a judge run id ending
    in ":c<k>" (align_norms' form)."""
    return int(judge_run_id.rsplit(":c", 1)[1])


def _empty_stats(hleg_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "norms_total": 0,
        "norms_skipped_not_accepted": 0,
        "norms_failed": [],
        "zero_alignment_norms": 0,
        "candidates": 0,
        "mechanical_rejects": [],
        "invalid_candidates": [],
        "invalid_assertions": [],
        "verdicts": dict.fromkeys(VERDICTS, 0),
        **{key: {node["id"]: 0 for node in hleg_nodes} for key in SPREAD_KEYS},
        "newly_aligned_norms": [],
        "dropped_assertions": [],
        "carried_candidates": 0,
    }


def _of_norm(fresh: dict[str, Any], norm_id: str) -> dict[str, list[dict[str, Any]]]:
    """A newly aligned norm's share of align_norms' result."""
    stats = fresh["stats"]
    prefix = judge_run_prefix(norm_id)
    return {
        "assertions": [a for a in fresh["assertions"] if a["source_norm_id"] == norm_id],
        "judge_runs": [r for r in fresh["judge_runs"] if r["id"].startswith(prefix)],
        **{key: [e for e in stats[key] if e.get("norm_id") == norm_id]
           for key in ("mechanical_rejects", "invalid_candidates", "invalid_assertions", "norms_failed")},
    }


def rejudge_batch(
    norms: list[dict[str, Any]],
    source_verdicts: dict[str, str],
    source: SourceAlignments,
    hleg_nodes: list[dict[str, Any]],
    generator: ModelClient,
    judge: ModelClient,
    *,
    prompt_version: str,
    log_path: Path,
    build_id: str,
    max_in_flight: int = 1,
) -> dict[str, Any]:
    """One batch of the re-judged norms, by R9 (the module docstring). Returns
    {"assertions", "mapping_runs", "judge_runs", "stats"}, the shape of an
    align_norms result, its stats with newly_aligned_norms, dropped_assertions
    and carried_candidates (the stored candidates checked again) added;
    mapping_runs holds the source runs the kept assertions name, in the source
    file's order, then the run of align_norms when the batch has newly accepted
    norms. prompt_version is the judge's (B174 R4): the judge's system prompt,
    the judge and mechanical runs and the generator of the newly accepted
    norms take it. max_in_flight bounds the norms whose calls run at once
    (B164)."""
    judge_prompt = load_prompt(JUDGE_PROMPT_KIND, prompt_version)
    judge_prompt_sha256 = prompt_sha256(judge_prompt)
    validator = _alignments_validator()
    hleg_by_id = {node["id"]: node for node in hleg_nodes}

    accepted = [norm for norm in norms if norm.get("judge_verdict") == "accepted"]
    newly = [norm for norm in accepted if source_verdicts.get(norm["norm_id"]) != "accepted"]
    newly_ids = {norm["norm_id"] for norm in newly}
    carried = [norm for norm in accepted if norm["norm_id"] not in newly_ids]
    # the generator is called here only, for exactly the newly accepted norms
    fresh = (align_norms(newly, hleg_nodes, generator, judge, prompt_version=prompt_version, log_path=log_path,
                         build_id=build_id, max_in_flight=max_in_flight) if newly else None)

    def judge_carried(norm: dict[str, Any]) -> list[tuple[Any, ...]]:
        """A norm's stored candidates checked and judged again, each event with
        its candidate index; runs on a worker thread when max_in_flight > 1."""
        events: list[tuple[Any, ...]] = []
        for stored in source.assertions_by_norm.get(norm["norm_id"], []):
            candidate = alignment_candidate_of(stored)
            target = hleg_by_id.get(stored["target_id"])
            if target is None:  # source_index refuses this before any record; a guard
                raise ValueError(f"the source assertion {stored['id']} names {stored['target_id']!r}, "
                                 "which is not one of the seven HLEG requirements")
            judge_run_id = stored["judge_run_id"]
            checked = quote_check(norm, target, candidate, prompt_version=prompt_version, log_path=log_path,
                                  build_id=build_id, judge_run_id=judge_run_id)
            if checked is not None:
                events.append((_candidate_index(judge_run_id), "mechanical", *checked))
                continue
            judge_run = judge_alignment(norm, target, candidate, judge, judge_prompt, judge_prompt_sha256,
                                        prompt_version=prompt_version, log_path=log_path, build_id=build_id,
                                        judge_run_id=judge_run_id)
            assertion = assertion_of(norm, target, candidate, judge_run,
                                     index=int(stored["id"].rsplit(":", 1)[1]),
                                     mapping_run_id=stored["mapping_run_id"],
                                     target_span_id=(target.get("source_span") or {}).get("span_id"))
            events.append((_candidate_index(judge_run_id), "judged", assertion, judge_run))
        return events

    judged = dict(zip((norm["norm_id"] for norm in carried),
                      run_in_flight(carried, judge_carried, max_in_flight=max_in_flight), strict=True))

    assertions: list[dict[str, Any]] = []
    judge_runs: list[dict[str, Any]] = []
    stats = _empty_stats(hleg_nodes)
    for norm in norms:
        norm_id = norm["norm_id"]
        stats["norms_total"] += 1
        if norm.get("judge_verdict") != "accepted":
            stats["norms_skipped_not_accepted"] += 1
            stats["dropped_assertions"].extend(a["id"] for a in source.assertions_by_norm.get(norm_id, []))
            continue
        if norm_id in newly_ids:
            assert fresh is not None
            share = _of_norm(fresh, norm_id)
            stats["newly_aligned_norms"].append(norm_id)
            assertions.extend(share["assertions"])
            judge_runs.extend(share["judge_runs"])
            for key in ("mechanical_rejects", "invalid_candidates", "invalid_assertions", "norms_failed"):
                stats[key].extend(share[key])
            continue
        # accepted by both: the source's mechanical rejections carried, the
        # stored candidates judged again, in the candidates' order
        events = [(_candidate_index(run["id"]), "carried", run, reject)
                  for run, reject in source.mechanical_by_norm.get(norm_id, [])]
        events.extend(judged[norm_id])
        stats["carried_candidates"] += len(judged[norm_id])
        stats["norms_failed"].extend(source.failed_by_norm.get(norm_id, []))
        stats["invalid_candidates"].extend(source.invalid_by_norm.get(norm_id, []))
        if not (events or norm_id in source.failed_by_norm or norm_id in source.invalid_by_norm):
            stats["zero_alignment_norms"] += 1
        for event in sorted(events, key=lambda e: e[0]):
            kind = event[1]
            stats["candidates"] += 1
            if kind in ("carried", "mechanical"):
                judge_runs.append(event[2])
                stats["mechanical_rejects"].append(event[3])
                continue
            assertion, judge_run = event[2], event[3]
            judge_runs.append(judge_run)
            errors = sorted(validator.iter_errors(assertion), key=lambda e: list(e.path))
            if errors:
                # as align_norms: the judge decision is kept, the invalid
                # assertion never enters the output
                stats["invalid_assertions"].append({
                    "norm_id": assertion["source_norm_id"], "target_id": assertion["target_id"],
                    "assertion_id": assertion["id"], "errors": [err.message for err in errors[:5]],
                })
                continue
            stats["verdicts"][assertion["judge_verdict"]] += 1
            assertions.append(assertion)

    if fresh is not None:
        placed = sum(len(_of_norm(fresh, norm_id)["judge_runs"]) for norm_id in newly_ids)
        if placed != len(fresh["judge_runs"]):
            raise RuntimeError("a judge run of the newly accepted norms could not be placed at its norm")
        stats["zero_alignment_norms"] += fresh["stats"]["zero_alignment_norms"]
        stats["candidates"] += fresh["stats"]["candidates"]
        for verdict, count in fresh["stats"]["verdicts"].items():
            stats["verdicts"][verdict] = stats["verdicts"].get(verdict, 0) + count
    stats.update(spread_of(assertions, [node["id"] for node in hleg_nodes]))
    named = {a["mapping_run_id"] for a in assertions}
    mapping_runs = [run for run_id, run in source.mapping_runs_by_id.items() if run_id in named]
    if fresh is not None:
        mapping_runs.extend(fresh["mapping_runs"])
    return {"assertions": assertions, "mapping_runs": mapping_runs, "judge_runs": judge_runs, "stats": stats}


def merge_batches(partials: list[dict[str, Any]], source: SourceAlignments,
                  requirement_ids: list[str]) -> dict[str, Any]:
    """The batches merged as align_hleg merges them (lists joined, counts
    summed), the spread recounted from the merged assertions (spread_of), and
    the alignment runs deduplicated by id: the source runs in the source file's
    order, then the new runs in the batches' order."""
    # the merge of align_hleg/__main__.py (its batch loop's end), kept a copy so align_hleg is unchanged
    result: dict[str, Any] = {"assertions": [], "mapping_runs": [], "judge_runs": [], "stats": {}}
    runs: dict[str, dict[str, Any]] = {}
    for partial in partials:
        result["assertions"].extend(partial["assertions"])
        result["judge_runs"].extend(partial["judge_runs"])
        for run in partial["mapping_runs"]:
            runs.setdefault(run["id"], run)
        for key, value in partial["stats"].items():
            if isinstance(value, int):
                result["stats"][key] = result["stats"].get(key, 0) + value
            elif isinstance(value, list):
                result["stats"].setdefault(key, []).extend(value)
            elif isinstance(value, dict):
                bucket = result["stats"].setdefault(key, {})
                for k, v in value.items():
                    bucket[k] = bucket.get(k, 0) + v
    result["mapping_runs"] = ([run for run_id, run in source.mapping_runs_by_id.items() if run_id in runs]
                              + [run for run_id, run in runs.items() if run_id not in source.mapping_runs_by_id])
    result["stats"].update(spread_of(result["assertions"], requirement_ids))
    return result


def rejudged_alignment_build(norms_build: dict[str, Any], source_build: dict[str, Any], *,
                             public_models: dict[str, Any], judge_sampling: str | None, judge_effort: str,
                             usage: dict[str, Any], norms_sha256: str, hleg_text_sha256: str,
                             hleg_derivation_record_sha256: str, aligned_at: str, prompt_version: str,
                             rejudge: dict[str, Any]) -> dict[str, Any]:
    """The build block as align_hleg writes it over the re-judged norms file (its
    reference block kept under norms_reference), with the source's generator
    fields and the new judge's fields in alignment_models, alignment_sampling
    and alignment_effort, this run's usage, the judge's prompt version (B174
    R4; the source's is in alignment_rejudge), and the alignment_rejudge block
    last."""
    upstream = dict(norms_build)
    norms_reference = upstream.pop("reference", None)
    models = {**(source_build.get("alignment_models") or {}),
              **{key: public_models.get(key) for key in JUDGE_MODEL_KEYS}}
    return {
        **upstream,
        "norms_reference": norms_reference,
        "alignment_models": models,
        "alignment_sampling": {**(source_build.get("alignment_sampling") or {}), "judge": judge_sampling},
        "alignment_effort": {**(source_build.get("alignment_effort") or {}), "judge": judge_effort},
        "alignment_usage": usage,
        "alignment_input_sha256": norms_sha256,
        "hleg_text_sha256": hleg_text_sha256,
        "hleg_derivation_record_sha256": hleg_derivation_record_sha256,
        "aligned_at": aligned_at,
        "alignment_prompt_version": prompt_version,
        "alignment_rejudge": rejudge,
    }

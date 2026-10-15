"""Layer 2 re-judged: every stored candidate norm judged again, zero generator calls.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

Each stored norm is turned back into the candidate its judge read
(candidate_of_norm, B173 R4), on its source unit expanded from the same
Layer 1 dump, and judged with the message extract_norms builds today
(judge_message, judge_candidate): the shared functions of
extract_norms/pipeline.py, so a re-judged norm is judged by the same code.
The new norm is the stored one with only the judge's fields set again
(JUDGE_FIELDS) as extract_norms sets them; every id and the key order are
kept (R6). The checkpoint groups are the Article or Annex of each norm, in
the source file's order (R7). This module imports no generator client.

The judge runs at the code's default prompt version (B174 R4), which may be
newer than the source's: a source judged under an older version is accepted
when the candidate the judge receives has the same shape under both
(same_candidate_shape). The candidate and the judge's message are rebuilt
under the source's version, so the message is the one built at generation
time, and the judge's system prompt is the judge version's file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tere4ai.act_parties import slots_of
from tere4ai.extract_norms.model_clients import ModelClient
from tere4ai.extract_norms.pipeline import (
    DEFAULT_PROMPT_VERSION,
    _index_nodes,
    candidate_of_norm,
    judge_candidate,
    judge_message,
    judged_candidate_fields,
    load_prompt,
    prompt_sha256,
    unit_of_norm,
)
from tere4ai.extract_norms.requirement_type import types_for
from tere4ai.parallel_calls import run_in_flight
from tere4ai.review_queue.materialize import already_materialised

JUDGE_PROMPT_KIND = "judge_norms"
JUDGE_FIELDS = ("judge_verdict", "review_status", "confidence", "judge_type_agrees", "judge_requirement_type")
VERDICTS = ("accepted", "rejected", "needs_human_review")
MATERIALISED_REFUSAL = ("the source is a materialised reference file (human decisions applied); only a generator "
                        "build can be re-judged")


def materialised_refusal(payload: dict[str, Any]) -> str | None:
    """Why a source norms or alignments file cannot be re-judged because people's
    decisions were applied to it (its own reference block, or an item with a
    human_review entry; review_queue.materialize.already_materialised), or
    None (final review): the stored items are then no longer what the
    generator wrote, so no message the generation-time judge read can be
    rebuilt from them."""
    return MATERIALISED_REFUSAL if already_materialised(payload) else None


def group_of(norm: dict[str, Any]) -> str:
    """The Article or Annex of a norm: the first two segments of its source node
    id ("eu-ai-act:article-5")."""
    return ":".join(norm["source_node_id"].split(":")[:2])


def groups_in_order(norms: list[dict[str, Any]]) -> list[str]:
    """The groups in the order their first norm appears in the source file."""
    return list(dict.fromkeys(group_of(norm) for norm in norms))


def verdict_counts(norms: list[dict[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(VERDICTS, 0)
    for norm in norms:
        verdict = norm.get("judge_verdict")
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def rejudge_group(
    dump: dict[str, Any],
    norms: list[dict[str, Any]],
    judge: ModelClient,
    *,
    source_prompt_version: str,
    judge_prompt_version: str,
    log_path: Path,
    build_id: str,
    max_in_flight: int = 1,
) -> dict[str, Any]:
    """Judge each stored norm again. Returns {"norms", "judge_runs", "stats"} in
    the norms' order, the shape of an extract_norms group result; stats holds
    the candidates judged and the new verdicts. The candidate and the message
    are rebuilt under the source's prompt version, so the judge reads the
    message built at generation time; the system prompt is the judge
    version's file and the judge runs carry the judge version (B174 R4;
    norms_refusal has checked that the two versions give the candidate the
    same shape). max_in_flight bounds the judge calls running at once (B164)."""
    judge_prompt = load_prompt(JUDGE_PROMPT_KIND, judge_prompt_version)
    judge_prompt_sha256 = prompt_sha256(judge_prompt)
    nodes = _index_nodes(dump)
    typed = types_for(judge_prompt_version)

    def judge_one(norm: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        candidate = candidate_of_norm(norm, source_prompt_version)
        judge_user = judge_message(dump, nodes, unit_of_norm(dump, norm), candidate, source_prompt_version)
        judge_run, type_view = judge_candidate(
            judge, judge_prompt, judge_prompt_sha256, judge_user, candidate,
            node_id=norm["source_node_id"], prompt_version=judge_prompt_version, log_path=log_path,
            judge_run_id=norm["judge_run_id"], build_id=build_id,
        )
        verdict = judge_run["verdict"]
        new_norm = {**norm}
        new_norm["judge_verdict"] = verdict
        new_norm["review_status"] = "accepted" if verdict == "accepted" else "needs_review"
        new_norm["confidence"] = judge_run["scores"]["evidence_strength"]
        if typed:
            new_norm.update(type_view)
        return new_norm, judge_run

    judged = run_in_flight(norms, judge_one, max_in_flight=max_in_flight)
    new_norms = [norm for norm, _run in judged]
    return {"norms": new_norms, "judge_runs": [run for _norm, run in judged],
            "stats": {"candidates": len(new_norms), "verdicts": verdict_counts(new_norms)}}


def merge_in_source_order(source_norms: list[dict[str, Any]], results: list[dict[str, Any]]
                          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The re-judged norms and their judge runs in the source file's order,
    whatever order the groups were judged or inherited in."""
    norm_by_id = {n["norm_id"]: n for result in results for n in result["norms"]}
    run_by_id = {r["id"]: r for result in results for r in result["judge_runs"]}
    missing = [n["norm_id"] for n in source_norms if n["norm_id"] not in norm_by_id]
    if missing:
        raise ValueError(f"{len(missing)} source norm(s) were not re-judged, first {missing[0]}")
    norms = [norm_by_id[n["norm_id"]] for n in source_norms]
    return norms, [run_by_id[n["judge_run_id"]] for n in norms]


def recounted_stats(source_stats: dict[str, Any], norms: list[dict[str, Any]]) -> dict[str, Any]:
    """The source's stats in their key order with the candidates and verdicts
    counted again over the re-judged norms; the rest (source_units,
    nodes_failed, invalid_norms, without_target_system_category,
    untyped_in_scope: what the generator and the schema decided, which no judge
    changes) carried."""
    return {**source_stats, "candidates": len(norms), "verdicts": verdict_counts(norms)}


def changed_verdicts(source_norms: list[dict[str, Any]], norms: list[dict[str, Any]]) -> list[str]:
    """The ids of the norms whose verdict differs from the source's."""
    before = {n["norm_id"]: n["judge_verdict"] for n in source_norms}
    return [n["norm_id"] for n in norms if before.get(n["norm_id"]) != n["judge_verdict"]]


def rejudged_build_block(source_build: dict[str, Any], *, public_models: dict[str, Any], judge_sampling: str | None,
                         judge_effort: str, judge_temperature: str | None, judge_usage: dict[str, Any],
                         zero_usage: dict[str, int], prompt_version: str) -> dict[str, Any]:
    """The source's build block with the judge's fields from the new judge (the
    judge's model, effort, temperature and the parameters digest in
    extraction_models; the judge entries of extraction_sampling,
    extraction_effort and extraction_temperature), this run's usage and the
    judge's prompt version (B174 R4; the source's is in the rejudge block);
    the generator's fields and extracted_at carried."""
    block = {**source_build}
    block["prompt_version"] = prompt_version
    block["extraction_models"] = {
        **(source_build.get("extraction_models") or {}),
        **{key: public_models.get(key) for key in ("judge_model", "judge_effort", "judge_temperature",
                                                   "model_parameters_sha256")},
    }
    for key, value in (("extraction_sampling", judge_sampling), ("extraction_effort", judge_effort),
                       ("extraction_temperature", judge_temperature)):
        block[key] = {**(source_build.get(key) or {}), "judge": value}
    block["extraction_usage"] = {"generator": dict(zero_usage), "judge": dict(judge_usage)}
    return block


# R5: the judge of v1 and v2 read target_system_category, which a stored norm
# does not keep (DEC-21), so their candidates cannot be rebuilt.
UNREBUILDABLE_PROMPT_VERSIONS = ("v1", "v2")
# R5: Layer 3 aligns newly accepted norms with the generator in the
# environment, so it must be the generator that wrote the rest.
GENERATOR_KEYS = ("generator_model", "generator_effort", "generator_temperature", "generator_json_mode")


def same_candidate_shape(source_version: str, judge_version: str) -> bool:
    """True when the judge of judge_version receives a candidate of the same
    shape as the judge of source_version (B174 R4): the same keys in the same
    order and the same typing, so a norm judged under the source's version can
    be judged again under the judge's."""
    return (judged_candidate_fields(source_version) == judged_candidate_fields(judge_version)
            and types_for(source_version) == types_for(judge_version))


def norms_refusal(source_payload: dict[str, Any], public_models: dict[str, Any],
                  judge_version: str = DEFAULT_PROMPT_VERSION) -> str | None:
    """Why the source norms cannot be re-judged in this environment under the
    judge prompt version judge_version (R5, B174 R4), or None: a materialised
    reference file, a prompt version whose candidates cannot be rebuilt, a
    judge version missing from the checkout or whose candidate differs in
    shape from the source version's, a source version's judge prompt whose
    text today differs from the one the source's judge runs recorded (the
    proof that the source was judged with the file in the repository), a
    norm whose inferred addressee is null beside an inference source node
    (the generation-time judge read that node's text, which the stored norm
    cannot give back), or a generator that is not the source's."""
    materialised = materialised_refusal(source_payload)
    if materialised:
        return materialised
    build = source_payload.get("build") or {}
    version = build.get("prompt_version")
    if not isinstance(version, str) or not version:
        return "the source norms file names no prompt_version"
    if version in UNREBUILDABLE_PROMPT_VERSIONS:
        return (f"the source norms were judged under prompt version {version}, whose judge read "
                "target_system_category, which a norm does not keep (DEC-21); their candidates cannot be rebuilt")
    for needed_version in dict.fromkeys((judge_version, version)):
        try:
            load_prompt(JUDGE_PROMPT_KIND, needed_version)
        except FileNotFoundError:
            return f"there is no {JUDGE_PROMPT_KIND} prompt {needed_version} in this checkout"
    if not same_candidate_shape(version, judge_version):
        return (f"the source norms were judged under prompt version {version}, whose judge received a candidate "
                f"of another shape than the {JUDGE_PROMPT_KIND} {judge_version} judge receives (its fields "
                f"{', '.join(judged_candidate_fields(version))}, typed {types_for(version)}; under {judge_version} "
                f"{', '.join(judged_candidate_fields(judge_version))}, typed {types_for(judge_version)}); their "
                f"candidates cannot be judged under {judge_version}")
    today = prompt_sha256(load_prompt(JUDGE_PROMPT_KIND, version))
    judge_runs = source_payload.get("judge_runs") or []
    if not judge_runs:
        return "the source build holds no judge runs, nothing to re-judge"
    recorded = sorted({str(run.get("prompt_sha256")) for run in judge_runs})
    if recorded != [today]:
        return (f"the {JUDGE_PROMPT_KIND} {version} prompt has sha256 {today} today; the source's judge runs "
                f"recorded {', '.join(recorded) or 'none'}")
    # every field a re-judge reads or sets again, so the new norm keeps the
    # stored key order (a typed version's type view included)
    needed = ("norm_id", "source_node_id", "judge_run_id", "judge_verdict", "review_status", "confidence",
              *(("judge_type_agrees", "judge_requirement_type") if types_for(version) else ()))
    for norm in source_payload.get("norms") or []:
        lacking = [key for key in needed if key not in norm]
        if lacking:
            return (f"the source norm {norm.get('norm_id', '(no norm_id)')} lacks {', '.join(lacking)}, "
                    f"which a {version} norm carries")
        _explicit, inferred, source_node = slots_of(norm)
        if inferred is None and source_node is not None:
            return (f"the source norm {norm.get('norm_id', '(no norm_id)')} keeps the inference source node "
                    f"{source_node} beside no inferred addressee; the generation-time judge read the inference "
                    "text, which the stored norm cannot give back, so its message cannot be rebuilt")
    source_models = build.get("extraction_models") or {}
    differing = [key for key in GENERATOR_KEYS if source_models.get(key) != public_models.get(key)]
    if differing:
        return ("the generator in the environment differs from the source's in "
                + ", ".join(f"{key} ({public_models.get(key)!r}, the source {source_models.get(key)!r})"
                            for key in differing))
    return None

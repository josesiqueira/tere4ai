"""Presenter: a build record as the API serves it, and the legacy synthesis.

@implements: DEC-16
@grounded_by: REF-27, ADD-20

Spec G 3.1 and D-G25: every presented field carries a provenance,
recorded (written by the command that did the work), derived (computed
here or read from an artefact after the fact) or unavailable (null, with a
reason). A step is done only when its execution ended with success AND the
artefact it wrote still exists with the recorded digest. Liveness after the
heartbeat expiry is unknown, never failed. A count the record does not
hold is null, never zero.

Builds made before build records existed are synthesised from their
artefacts: one record per norms dump, executions carrying only what the
artefacts themselves state (no run id, no timing, no gate outcome), the
publication matched to the chain record whose inputs equal the FULL set
of artefacts present. Nothing is written: the synthesis opens the store
read-only and never creates it.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from tere4ai.graph_store.build_chain import chained_build_id, sha256_of_file
from tere4ai.graph_store.build_record import (
    SCHEMA_VERSION,
    STEP_IDS,
    BuildRecordStore,
    liveness,
    relative_to_dump_dir,
)
from tere4ai.graph_store.checkpoints import progress, read_checkpoint

DEPENDS_ON = {"L1.1": "L0.1", "L2.1": "L1.1", "L2.2": "L2.1", "L2.3": "L2.2", "L2.4": "L2.3", "L3.1": "L2.2",
              "L3.2": "L3.1", "L3.3": "L3.2", "L3.4": "L3.3", "L3.5": "L3.4", "P.1": "L3.3", "P.2": "P.1"}
RESULT_KEYS_OF = {"extract_norms": ("norms", "judge_runs", "stats"),
                  "align_hleg_altai": ("assertions", "mapping_runs", "judge_runs", "stats")}
KEY_FIELD_OF = {"extract_norms": "group", "align_hleg_altai": "batch"}
MODEL_COMMANDS = ("extract_norms", "align_hleg_altai")
PARSE_STEPS = ("L0.1", "L1.1")

NOT_RECORDED = "not recorded by the command"
NOT_RECORDED_LEGACY = "not recorded before DEC-16"
EXECUTION_DERIVED = {"liveness", "progress"}
RECORD_DERIVED = {"steps", "depends_on_state", "parse_record_id", "served", "observed_at", "synthesised"}
_LEGACY_EXCLUDED = (".reference", ".adjudicated", ".checkpoint", ".writing", ".building")

# Digest per (path, size, mtime) so presenting a list does not re-hash
# unchanged megabyte dumps on every request.
_DIGEST_CACHE: dict[tuple[str, int, int], str] = {}


def _digest(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _DIGEST_CACHE.get(key)
    if cached is None:
        cached = _DIGEST_CACHE[key] = sha256_of_file(path)
    return cached


def _default_state(record: dict[str, Any]) -> str:
    return "not_recorded" if record.get("synthesised") else "not_started"


def _artefact_problem(execution: dict[str, Any], dump_dir: Path) -> str | None:
    """Why a done execution's outputs no longer stand, or None when every one
    exists with its recorded digest."""
    for out in execution.get("outputs") or []:
        path = Path(dump_dir) / out["file"]
        if not path.is_file():
            return f"artefact {out['file']} missing"
        try:
            if _digest(path) != out["sha256"]:
                return f"artefact {out['file']} drifted from the recorded digest"
        except OSError:
            return f"artefact {out['file']} missing"
    return None


LEGACY_P1_REASON = ("a legacy chain record was written only after G1 to G6 passed; "
                    "per-gate outcomes were not recorded before DEC-16")
LEGACY_P2_REASON = ("the chain record predates the load; load and post-load gates "
                    "were not recorded before DEC-16")
PRODUCED_BEFORE_RECORDS = "produced before DEC-16"
# Steps a record can share with the records it builds on. Publication is
# never inherited: a build is published only by its own publish execution.
SHAREABLE_STEPS = tuple(s for s in STEP_IDS if not s.startswith("P."))
STEPS_OF_INPUT_ROLE = {"norms": ("L2.1", "L2.2"), "alignments": ("L3.1", "L3.2", "L3.3")}


def _own_states(record: dict[str, Any], dump_dir: Path, verify: bool) -> tuple[dict[str, str], dict[str, str]]:
    """(state per step, artefact problem per step) from the record's own
    executions: the newest covering execution decides; a done execution
    whose artefact is missing or drifted renders its steps failed."""
    steps: dict[str, str] = {}
    problems: dict[str, str] = {}
    for ex in record.get("executions", []):
        state = ex["status"]
        problem = None
        if state == "done" and verify:
            problem = _artefact_problem(ex, dump_dir)
            if problem:
                state = "failed"
        for step in ex.get("covers_steps", []):
            if step not in STEP_IDS:
                continue
            steps[step] = state
            if problem:
                problems[step] = problem
            else:
                problems.pop(step, None)
    return steps, problems


class _Lineage:
    """Resolve a step no execution of a record covers through the records it
    builds on (spec 3.1: done elsewhere is neither not started nor not
    recorded): the parse record of its Layer 1, the record that produced a
    norms or alignments input its earliest consuming execution read, then
    its parent record. Reads the store once per presentation."""

    def __init__(self, store: BuildRecordStore, dump_dir: Path) -> None:
        self.dump_dir = dump_dir
        self.records = store._valid_records_newest_first()
        self.by_id = {r["record_id"]: r for r in self.records}
        self._own: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

    def own(self, record: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
        rid = record["record_id"]
        if rid not in self._own:
            self._own[rid] = _own_states(record, self.dump_dir, verify=True)
        return self._own[rid]

    def producer(self, digest: str) -> str | None:
        for record in self.records:
            for ex in record["executions"]:
                if any(o.get("sha256") == digest for o in ex.get("outputs", [])):
                    return record["record_id"]
        return None

    def parse_producer(self, layer1_digest: str) -> str | None:
        for record in self.records:
            for ex in record["executions"]:
                if ex.get("command") == "parse_legal_structure" and any(
                    o.get("role") == "layer1_dump" and o.get("sha256") == layer1_digest for o in ex.get("outputs", [])
                ):
                    return record["record_id"]
        return None

    def sources(self, record: dict[str, Any]) -> tuple[list[tuple[str, tuple[str, ...] | None]], dict[str, str]]:
        """([(record id, steps it may answer or None for any)], not-recorded
        markers per step for inputs with a digest but no producing record)."""
        rid = record.get("record_id")
        out: list[tuple[str, tuple[str, ...] | None]] = []
        markers: dict[str, str] = {}
        if record.get("layer1_digest"):
            found = self.parse_producer(record["layer1_digest"])
            if found is None:
                for step in PARSE_STEPS:
                    markers[step] = PRODUCED_BEFORE_RECORDS
            elif found != rid:
                out.append((found, PARSE_STEPS))
        consuming = next((ex for ex in record.get("executions", [])
                          if any(i.get("role") in STEPS_OF_INPUT_ROLE and i.get("sha256") for i in ex.get("inputs", []))),
                         None)
        for inp in (consuming or {}).get("inputs", []):
            if inp.get("role") not in STEPS_OF_INPUT_ROLE or not inp.get("sha256"):
                continue
            found = self.producer(inp["sha256"])
            if found is None:
                for step in STEPS_OF_INPUT_ROLE[inp["role"]]:
                    markers.setdefault(step, PRODUCED_BEFORE_RECORDS)
            elif found != rid:
                out.append((found, None))
        if record.get("parent_record_id"):
            out.append((record["parent_record_id"], None))
        return out, markers

    def resolve(self, record: dict[str, Any], step: str, seen: frozenset[str]) -> tuple[str, str] | None:
        """(state, reason) for a step the record does not cover itself, or None."""
        sources, markers = self.sources(record)
        for source_id, only in sources:
            if source_id in seen or (only is not None and step not in only):
                continue
            source = self.by_id.get(source_id)
            if source is None:
                continue
            states, problems = self.own(source)
            if step in states:
                state = states[step]
                if step in problems:
                    return "failed", problems[step]
                if state == "done":
                    return "done_shared", f"done in record {source_id}"
                return state, f"{state} in record {source_id}"
            deeper = self.resolve(source, step, seen | {source_id})
            if deeper is not None:
                return deeper
        if step in markers:
            return "not_recorded", markers[step]
        return None


def step_states(record: dict[str, Any], store: BuildRecordStore | None, dump_dir: Path,
                reasons: dict[str, str] | None = None) -> tuple[dict, dict, str | None]:
    """(steps, depends_on_state, parse_record_id). The newest execution
    covering a step decides it; a done execution whose artefact is missing or
    drifted renders its steps failed, with the cause written into reasons
    (when given). A step the record does not cover is resolved through its
    lineage (_Lineage): done_shared naming the covering record only while
    that record's artefact stands, not_recorded when its input was produced
    before build records existed. Synthesised records read their digests
    from the artefacts themselves and are not re-verified."""
    synthesised = bool(record.get("synthesised"))
    steps, problems = _own_states(record, Path(dump_dir), verify=not synthesised)

    parse_record_id = None
    if store is not None:
        lineage = _Lineage(store, Path(dump_dir))
        if record.get("layer1_digest") and any(s not in steps for s in PARSE_STEPS):
            found = lineage.parse_producer(record["layer1_digest"])
            if found and found != record.get("record_id"):
                parse_record_id = found
        seen = frozenset({record.get("record_id")})
        for step in SHAREABLE_STEPS:
            if step in steps:
                continue
            resolved = lineage.resolve(record, step, seen)
            if resolved is None:
                continue
            state, why = resolved
            if synthesised and state == "not_recorded":
                continue  # the synthesis states its own reasons for what it could not read
            steps[step] = state
            problems[step] = why

    # A legacy chain record was written after the critical gates and BEFORE
    # the load (the defect D-G21 names): it proves neither the per-gate
    # outcomes nor the load, so both P steps stay not recorded, with why.
    if synthesised and record.get("publication") is not None:
        problems.setdefault("P.1", LEGACY_P1_REASON)
        problems.setdefault("P.2", LEGACY_P2_REASON)
    default = _default_state(record)
    for step in STEP_IDS:
        steps.setdefault(step, default)
    ordered = {step: steps[step] for step in STEP_IDS}

    materialised = any(ex.get("command") == "materialize_reference" and "L2.4" in ex.get("covers_steps", [])
                       for ex in record.get("executions", []))
    depends = dict(DEPENDS_ON)
    if materialised:
        depends["L3.1"] = "L2.4"
    depends_on_state = {step: ordered[depends[step]] for step in STEP_IDS
                        if ordered[step] == "not_started" and step in depends}
    if reasons is not None:
        reasons.update(problems)
    return ordered, depends_on_state, parse_record_id


def provenance_of(mapping: dict[str, Any], *, derived_keys: set[str], synthesised: bool, reason_null: str,
                  null_reasons: dict[str, str] | None = None,
                  unavailable_when_empty: frozenset[str] = frozenset()) -> tuple[dict, dict]:
    """One provenance per key. A null is unavailable with a reason (the
    specific one from null_reasons when given); so is an empty collection in a
    synthesised mapping, or under a key of unavailable_when_empty, which
    states only that nothing was recorded. A presenter-computed key is
    derived; in a synthesised mapping every value read from an artefact is
    derived; anything else was recorded."""
    null_reasons = null_reasons or {}
    provenance: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for key, value in mapping.items():
        if key in ("provenance", "reasons"):
            continue
        empty = isinstance(value, (list, dict)) and not value
        if value is None or (empty and (key in unavailable_when_empty or (synthesised and key not in derived_keys))):
            provenance[key] = "unavailable"
            reasons[key] = null_reasons.get(key, reason_null)
        elif key in derived_keys or synthesised:
            provenance[key] = "derived"
        else:
            provenance[key] = "recorded"
    return provenance, reasons


def _progress_of(execution: dict[str, Any], dump_dir: Path) -> dict[str, Any] | None:
    command = execution.get("command")
    if command not in KEY_FIELD_OF or not execution.get("checkpoint_file"):
        return None
    # A legacy execution (no run id) holds legacy lines: counted by key, never
    # validated against the result shape.
    result_keys = () if execution.get("run_id") is None else RESULT_KEYS_OF[command]
    return progress(execution, Path(dump_dir) / execution["checkpoint_file"], KEY_FIELD_OF[command], result_keys)


def _execution_null_reasons(execution: dict[str, Any]) -> dict[str, str]:
    command = execution.get("command")
    running = execution.get("status") == "running"
    reasons: dict[str, str] = {
        "resumes_run_id": "the execution is not a resume",
        "inherited_from": "the execution inherited no work",
    }
    reasons["counts"] = "the execution recorded no counts"
    if running:
        for key in ("ended_at", "error", "work_failures", "usage", "counts"):
            reasons[key] = "the execution has not ended"
    elif execution.get("status") == "done":
        reasons["error"] = "the execution ended without error"
    if command not in MODEL_COMMANDS:
        for key in ("models", "prompt_sha256", "sampling", "usage"):
            reasons[key] = "the command calls no model"
    if command not in KEY_FIELD_OF:
        for key in ("checkpoint_file", "work_unit", "expected_total", "progress"):
            reasons[key] = "the command has no work units"
    elif not execution.get("checkpoint_file"):
        reasons["progress"] = "no checkpoint file recorded"
    return reasons


def _record_null_reasons(record: dict[str, Any], steps_covered_here: bool) -> dict[str, str]:
    reasons = {"parent_record_id": "the record has no parent record", "publication": "the record is not published"}
    if steps_covered_here:
        reasons["parse_record_id"] = "the record holds its own parse execution"
    elif not record.get("layer1_digest"):
        reasons["parse_record_id"] = "the record names no layer1 digest"
    else:
        reasons["parse_record_id"] = "no parse record in this store produced the record's layer1 digest"
    return reasons


def present_record(record: dict[str, Any], dump_dir: Path, now: datetime, served_chain_id: str | None,
                   store: BuildRecordStore | None) -> dict[str, Any]:
    """The presented record (schema presented_record): the stored or
    synthesised record plus liveness, progress and provenance per execution,
    and steps, served, observed_at and provenance at the top level."""
    dump_dir = Path(dump_dir)
    presented = copy.deepcopy(record)
    synthesised = bool(presented.pop("synthesised", False))
    own_reasons = dict(presented.pop("reasons", None) or {})
    presented.pop("provenance", None)
    reason_null = NOT_RECORDED_LEGACY if synthesised else NOT_RECORDED

    for ex in presented["executions"]:
        ex.pop("provenance", None)
        ex.pop("reasons", None)
        ex["liveness"] = liveness(ex, now)
        ex["progress"] = _progress_of(ex, dump_dir)
        ex["provenance"], ex["reasons"] = provenance_of(
            ex, derived_keys=EXECUTION_DERIVED, synthesised=synthesised, reason_null=reason_null,
            null_reasons=None if synthesised else _execution_null_reasons(ex),
            unavailable_when_empty=frozenset({"counts"}),
        )

    step_reasons: dict[str, str] = {}
    steps, depends_on_state, parse_record_id = step_states(record, store, dump_dir, step_reasons)
    publication = presented.get("publication")
    presented.update({
        "steps": steps,
        "depends_on_state": depends_on_state,
        "parse_record_id": parse_record_id,
        "served": bool(publication) and served_chain_id is not None and publication.get("chain_id") == served_chain_id,
        "observed_at": now.isoformat(),
        "synthesised": synthesised,
    })
    derived_keys = set(RECORD_DERIVED) | ({"publication"} if synthesised else set())
    covered_here = any(set(PARSE_STEPS) & set(ex.get("covers_steps", [])) for ex in presented["executions"])
    null_reasons = {} if synthesised else _record_null_reasons(presented, covered_here)
    null_reasons.update(own_reasons)
    provenance, reasons = provenance_of(presented, derived_keys=derived_keys, synthesised=synthesised,
                                        reason_null=reason_null, null_reasons=null_reasons)
    presented["provenance"] = provenance
    presented["reasons"] = {**reasons, **own_reasons, **step_reasons}
    return presented


_PATH_RE = re.compile(r"(?:[A-Za-z]:)?(?:[^\\/\s'\"]*[\\/])+([^\\/\s'\"]+)")


def exception_reason(exc: BaseException) -> str:
    """The exception as a one-line reason with every path reduced to its file
    name: the builds list names what could not be read, never where."""
    return _PATH_RE.sub(r"\1", f"{type(exc).__name__}: {exc}")


def unreadable(record_id: str, reason: str, aliases: list[str] | None = None) -> dict[str, Any]:
    """The marker list_records uses for a record that cannot be presented."""
    return {"record_id": record_id, "aliases": list(aliases or []), "unreadable": True, "reason": reason}


def summary_of(presented: dict[str, Any]) -> dict[str, Any]:
    """One row of the builds list (schema summary). An unreadable record
    (store.list_records marks it) keeps its id and reason and nothing else."""
    if presented.get("unreadable"):
        return {"record_id": presented["record_id"], "aliases": [], "base_build_id": None, "created_at": None,
                "synthesised": False, "steps": None, "publication": None, "served": False, "unreadable": True,
                "reason": presented.get("reason")}
    pub = presented.get("publication")
    return {
        "record_id": presented["record_id"],
        "aliases": list(presented.get("aliases", [])),
        "base_build_id": presented.get("base_build_id"),
        "created_at": presented.get("created_at"),
        "synthesised": bool(presented.get("synthesised")),
        "steps": presented.get("steps"),
        "publication": ({"chain_id": pub["chain_id"], "label": pub.get("label"), "published_at": pub.get("published_at")}
                        if pub else None),
        "served": bool(presented.get("served")),
        "unreadable": False,
        "reason": None,
    }


# ---- legacy synthesis

def _read_json_or_none(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _derived_execution(command: str, steps: list[str], **fields: Any) -> dict[str, Any]:
    """A synthesised execution: every schema key present, nothing invented.
    Run id, argv and timings were never recorded before DEC-16."""
    execution = {
        "run_id": None, "command": command, "covers_steps": list(steps), "status": "done", "started_at": None,
        "ended_at": None, "heartbeat_at": None, "argv": None, "resumes_run_id": None, "inputs": [], "outputs": [],
        "config": {}, "models": None, "prompt_sha256": None, "sampling": None, "usage": None,
        "checkpoint_file": None, "work_unit": None, "expected_total": None, "inherited_keys": [],
        "inherited_from": None, "completed_keys": [], "counts": {}, "gates": [], "work_failures": None,
        "error": None,
    }
    execution.update(fields)
    return execution


def _build_block(payload: dict[str, Any]) -> dict[str, Any]:
    build = payload.get("build")
    return build if isinstance(build, dict) else {}


def _stats(payload: dict[str, Any]) -> dict[str, Any]:
    stats = payload.get("stats")
    return stats if isinstance(stats, dict) else {}


def _first_judge_prompt(payload: dict[str, Any]) -> str | None:
    runs = payload.get("judge_runs")
    if isinstance(runs, list) and runs and isinstance(runs[0], dict):
        return runs[0].get("prompt_sha256")
    return None


def _parse_execution(payload: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for node in payload["nodes"]:
        kind = node.get("type") if isinstance(node, dict) else None
        if kind is not None:
            by_type[kind] = by_type.get(kind, 0) + 1
    edges = payload.get("edges")
    queue = payload.get("review_queue")
    counts = {"nodes": len(payload["nodes"]), "edges": len(edges) if isinstance(edges, list) else None,
              "nodes_by_type": by_type, "review_queue": len(queue) if isinstance(queue, list) else None}
    return _derived_execution("parse_legal_structure", list(PARSE_STEPS), counts=counts,
                              outputs=[{"role": "layer1_dump", "file": name, "sha256": digest}])


def _extract_execution(payload: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    build, stats = _build_block(payload), _stats(payload)
    return _derived_execution(
        "extract_norms", ["L2.1", "L2.2"],
        models=build.get("extraction_models"), sampling=build.get("extraction_sampling"),
        usage=build.get("extraction_usage"),
        prompt_sha256={"generator": None, "judge": _first_judge_prompt(payload)},
        config={"prompt_version": build["prompt_version"]} if build.get("prompt_version") else {},
        counts={k: stats.get(k) for k in ("source_units", "candidates", "verdicts")},
        outputs=[{"role": "norms", "file": name, "sha256": digest}],
    )


def _align_execution(payload: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    build, stats = _build_block(payload), _stats(payload)
    rejects = stats.get("mechanical_rejects")
    if isinstance(rejects, list):
        rejects = len(rejects)
    elif not isinstance(rejects, int):
        rejects = None
    version = build.get("alignment_prompt_version")
    return _derived_execution(
        "align_hleg_altai", ["L3.1", "L3.2", "L3.3"],
        models=build.get("alignment_models"), sampling=build.get("alignment_sampling"),
        usage=build.get("alignment_usage"),
        prompt_sha256={"generator": None, "judge": _first_judge_prompt(payload)},
        config={"prompt_version": version} if version else {},
        counts={"norms_total": stats.get("norms_total"), "candidates": stats.get("candidates"),
                "verdicts": stats.get("verdicts"), "mechanical_rejects_count": rejects},
        outputs=[{"role": "alignments", "file": name, "sha256": digest}],
    )


def _chain_records(dump_dir: Path) -> list[dict[str, Any]]:
    out = []
    for path in sorted(dump_dir.glob("build_chain_*.json")):
        chain = _read_json_or_none(path)
        if not isinstance(chain, dict) or not isinstance(chain.get("chain_id"), str):
            continue
        inputs = chain.get("inputs")
        if not isinstance(inputs, list) or not all(isinstance(i, dict) and "role" in i and "sha256" in i for i in inputs):
            continue
        out.append(chain)
    return out


_ARTEFACT_ROLES = ("layer1_dump", "norms", "alignments")


def _matching_chain(chains: list[dict[str, Any]], present: dict[str, str], dump_dir: Path) -> dict[str, Any] | None:
    """The chain record whose inputs are exactly the present artefacts: equal
    digest on every present role, and no artefact role the dump directory
    lacks. Any other input it names (decisions, freeze manifests) must exist
    in the dump directory with its recorded digest."""
    for chain in chains:
        roles = {i["role"]: i["sha256"] for i in chain["inputs"] if i["role"] in _ARTEFACT_ROLES}
        if roles != present:
            continue
        others = [i for i in chain["inputs"] if i["role"] not in _ARTEFACT_ROLES]
        if all((dump_dir / str(i.get("file", ""))).is_file() and _digest(dump_dir / str(i["file"])) == i["sha256"]
               for i in others):
            return chain
    return None


def _legacy_publication(chain: dict[str, Any], base_build_id: str | None, has_alignments: bool) -> dict[str, Any] | None:
    build_id = chain.get("build_id")
    if not isinstance(build_id, str):
        if base_build_id is None:
            return None
        build_id = chained_build_id(base_build_id, chain)
    roles = {i["role"] for i in chain["inputs"]}
    gating = chain.get("gating") or {"layer2": "human" if "decisions" in roles else "llm",
                                     "layer3": "llm" if has_alignments else "absent"}
    return {"chain_id": chain["chain_id"], "build_id": build_id, "published_at": chain.get("published_at"),
            "gating": gating, "label": chain.get("label"), "gates": None, "postload_gates": None, "manifests": []}


def _synthesise_one(dump_dir: Path, slug: str, norms_path: Path, layer1_path: Path, layer1_digest: str | None,
                    layer1_payload: Any, chains: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: dict[str, str] = {}
    executions: list[dict[str, Any]] = []

    if layer1_digest is not None:
        if isinstance(layer1_payload, dict) and isinstance(layer1_payload.get("nodes"), list):
            executions.append(_parse_execution(layer1_payload, layer1_path.name, layer1_digest))
        else:
            for step in PARSE_STEPS:
                reasons[step] = f"artefact unreadable: {layer1_path.name}"

    norms_digest = _digest(norms_path)
    norms_payload = _read_json_or_none(norms_path)
    if isinstance(norms_payload, dict) and isinstance(norms_payload.get("norms"), list):
        executions.append(_extract_execution(norms_payload, norms_path.name, norms_digest))
    else:
        problem = "malformed" if isinstance(norms_payload, dict) else "unreadable"
        for step in ("L2.1", "L2.2"):
            reasons[step] = f"artefact {problem}: {norms_path.name}"

    align_path = dump_dir / f"alignments_{slug}.json"
    checkpoint_path = dump_dir / f"alignments_{slug}.checkpoint.jsonl"
    has_alignments = align_path.is_file() and align_path.stat().st_size > 0
    align_steps = ("L3.1", "L3.2", "L3.3")
    if has_alignments:
        payload = _read_json_or_none(align_path)
        if isinstance(payload, dict) and isinstance(payload.get("assertions"), list):
            executions.append(_align_execution(payload, align_path.name, _digest(align_path)))
        else:
            problem = "malformed" if isinstance(payload, dict) else "unreadable"
            for step in align_steps:
                reasons[step] = f"artefact {problem}: {align_path.name}"
    elif checkpoint_path.is_file():
        try:
            read = read_checkpoint(checkpoint_path, "batch", ())
        except (OSError, UnicodeDecodeError):
            for step in align_steps:
                reasons[step] = f"artefact unreadable: {checkpoint_path.name}"
        else:
            keys = list(dict.fromkeys(e["batch"] for e in read.entries))
            executions.append(_derived_execution(
                "align_hleg_altai", list(align_steps), status="running",
                checkpoint_file=relative_to_dump_dir(checkpoint_path, dump_dir), work_unit="batches",
                expected_total=None, inherited_keys=keys, inherited_from="legacy",
            ))
            reasons["L3.1"] = "legacy checkpoint: results not validated" + (
                "; corrupt lines in the middle were skipped" if read.corrupt_middle else "")
    elif align_path.is_file():
        for step in align_steps:
            reasons[step] = f"artefact unreadable: {align_path.name} is empty"

    base_build_id = _build_block(norms_payload).get("build_id") if isinstance(norms_payload, dict) else None
    if base_build_id is None and isinstance(layer1_payload, dict):
        base_build_id = _build_block(layer1_payload).get("build_id")

    present = {"norms": norms_digest}
    if layer1_digest is not None:
        present["layer1_dump"] = layer1_digest
    if has_alignments:
        present["alignments"] = _digest(align_path)
    chain = _matching_chain(chains, present, dump_dir)
    publication = _legacy_publication(chain, base_build_id, has_alignments) if chain else None
    if publication is None:
        reasons["publication"] = "no chain record matches the current artefacts"
    else:
        reasons["publication.gates"] = NOT_RECORDED_LEGACY
        for key in ("published_at", "label"):
            if publication[key] is None:
                reasons[f"publication.{key}"] = NOT_RECORDED_LEGACY
        reasons["publication.postload_gates"] = NOT_RECORDED_LEGACY

    return {
        "schema_version": SCHEMA_VERSION, "record_id": f"legacy-{slug}", "aliases": [slug],
        "parent_record_id": None, "base_build_id": base_build_id, "created_at": None,
        "layer1_digest": layer1_digest, "executions": executions, "publication": publication,
        "synthesised": True, "reasons": reasons,
    }


def synthesise_legacy_records(dump_dir: Path) -> list[dict[str, Any]]:
    """One synthesised record per norms_<slug>.json that no stored record
    carries as an alias. Read-only: never creates build_records/."""
    dump_dir = Path(dump_dir)
    store = BuildRecordStore(dump_dir, create=False)
    taken = {alias for r in store.list_records() if not r.get("unreadable") for alias in r.get("aliases", [])}
    layer1_path = dump_dir / "layer1.json"
    layer1_error = None
    try:
        layer1_digest = _digest(layer1_path) if layer1_path.is_file() else None
    except OSError:
        layer1_digest, layer1_error = None, f"artefact unreadable: {layer1_path.name}"
    layer1_payload = _read_json_or_none(layer1_path) if layer1_digest is not None else None
    chains = _chain_records(dump_dir)
    records = []
    for norms_path in sorted(dump_dir.glob("norms_*.json")):
        name = norms_path.name
        if any(marker in name for marker in _LEGACY_EXCLUDED):
            continue
        slug = name[len("norms_"):-len(".json")]
        if slug in taken:
            continue
        # One unreadable artefact never fails the list (spec 7(b)): the slug
        # is reported unreadable, with the reason, and the others stand.
        try:
            record = _synthesise_one(dump_dir, slug, norms_path, layer1_path, layer1_digest, layer1_payload, chains)
        except Exception as exc:  # noqa: BLE001 - reported per slug, never raised out of the list
            records.append(unreadable(f"legacy-{slug}", exception_reason(exc), [slug]))
            continue
        if layer1_error:
            record["reasons"].update({step: layer1_error for step in PARSE_STEPS})
        records.append(record)
    return records

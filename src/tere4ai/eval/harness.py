"""MILESTONE4 evaluation harness: run the ablation ladder over gold/benchmark items.

@implements: DEC-11, DEC-17
@implements: DEC-20
@implements: DEC-23
@grounded_by: REF-15, REF-16, REF-17

Runs the five Section 12 ablation conditions (strategies.py) over evaluation
items and writes one results artifact per run. Hard rules enforced here:

- NO live model call happens by default. The live path requires BOTH the
  explicit live=True argument (--live on the CLI) AND the environment gate
  TERE4AI_LIVE_TESTS=1. Offline runs use injected fake or stub clients that
  are clearly labelled and never produce content that could be mistaken for
  a model answer.
- Config of record (DEC-07): a live run refuses to start unless the loaded
  model configuration (tere4ai.judge.config.load_model_config) matches
  eval/config_evaluated.yaml on generator model and judge model. Results
  produced under any other configuration would not be the configuration of
  record, so they are never written.
- The results artifact name is deterministic: derived from the graph build
  id and the strategy set, never from a timestamp, so re-running the same
  configuration overwrites the same file instead of accumulating
  near-duplicates.

Item sources:
- eval/gold/gold_seed.json: the hand-authored seed gold set (load_gold_items).
- eval/gold/benchmark_sample.json: a frozen sample of the REF-15 benchmark
  (load_benchmark_items); see eval/README.md for provenance and coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tere4ai.eval.evaluation_record import (
    EvaluationRecordError,
    EvaluationRecordStore,
    code_version,
    end_failed,
    input_ref,
    observe_publication,
    served_input_paths,
)
from tere4ai.eval.metrics import METRICS_VERSION, current_level  # noqa: F401
from tere4ai.eval.strategies import STRATEGY_NAMES, build_strategy, uses_runtime_judge
from tere4ai.extract_norms.model_clients import ModelClient, declared_sampling
from tere4ai.graph_store.build_record import atomic_write_json
from tere4ai.graph_store.present import exception_reason
from tere4ai.judge.config import ConfigurationError, ModelConfig, load_model_config
from tere4ai.validate_graph.gates import deleted_unit_citations


def _repo_root() -> Path:
    """Repo root for eval assets, correct via parents[3] only under an
    editable install. eval/ is not shipped inside the wheel, so a wheel
    install must point TERE4AI_REPO_ROOT at a repository checkout."""
    override = os.environ.get("TERE4AI_REPO_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()
EVAL_CONFIG_PATH = REPO_ROOT / "eval" / "config_evaluated.yaml"
RESULTS_DIR = REPO_ROOT / "eval" / "results"
GOLD_SEED_PATH = REPO_ROOT / "eval" / "gold" / "gold_seed.json"
BENCHMARK_SAMPLE_PATH = REPO_ROOT / "eval" / "gold" / "benchmark_sample.json"
LAYER1_DUMP_PATH = REPO_ROOT / "data" / "graph_dumps" / "layer1.json"
NORMS_PATH = REPO_ROOT / "data" / "graph_dumps" / "norms_core.json"

LIVE_ENV_GATE = "TERE4AI_LIVE_TESTS"

ITEM_KINDS = ("classification", "retrieval", "qa")

# REF-15 benchmark risk levels -> our closed risk-category vocabulary.
# "limited" in the benchmark is the Article 50 transparency regime.
# B118: the benchmark's "limited" is its own overall label, grounded by REF-15
# in Articles 50 and 10; it maps here to the pyramid's limited_risk.
BENCHMARK_RISK_MAP = {
    "prohibited": "unacceptable_risk",
    "high-risk": "high_risk",
    "limited": "limited_risk",
    "minimal": "minimal_risk",
}


class EvalConfigMismatch(RuntimeError):
    """Loaded model config does not match eval/config_evaluated.yaml."""


class LiveGateError(RuntimeError):
    """A live run was requested without the TERE4AI_LIVE_TESTS=1 env gate."""


class EvalAssetMissingError(FileNotFoundError):
    """An eval asset is absent, usually a wheel install without TERE4AI_REPO_ROOT."""


def read_config_of_record(config_path: Path = EVAL_CONFIG_PATH) -> dict[str, str]:
    """Generator and judge model ids from eval/config_evaluated.yaml.

    The file is the config of record for evaluated builds (DEC-07 verify
    target). Parsed with a minimal purpose-built reader instead of a YAML
    dependency: only the two-level "section: / key: value" layout used by
    that file is supported, which keeps the guard dependency-free and makes
    an unexpected file shape fail loudly.
    """
    if not config_path.is_file():
        raise EvalAssetMissingError(
            f"eval config of record not found: {config_path}. eval/ ships "
            "with the repository, not the wheel; under a non-editable "
            "install set TERE4AI_REPO_ROOT to a repository checkout."
        )
    section = None
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            section = line.split(":", 1)[0].strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        if section in ("generator", "judges") and key.strip() == "model":
            values[f"{section}_model"] = value.strip()
    missing = [k for k in ("generator_model", "judges_model") if k not in values]
    if missing:
        raise EvalConfigMismatch(
            f"config of record {config_path} is missing {', '.join(missing)}; "
            "cannot guard a live run without it"
        )
    return {
        "generator_model": values["generator_model"],
        "judge_model": values["judges_model"],
    }


def guard_live_config(
    cfg: ModelConfig | None = None,
    config_path: Path = EVAL_CONFIG_PATH,
) -> ModelConfig:
    """Refuse a live run whose loaded config differs from the config of record.

    cfg defaults to load_model_config() (env / .env). Raises
    EvalConfigMismatch listing every differing field. Returns the validated
    config so the caller can construct clients from it.
    """
    if cfg is None:
        cfg = load_model_config()
    record = read_config_of_record(config_path)
    mismatches = []
    if cfg.generator_model != record["generator_model"]:
        mismatches.append(
            f"generator model: loaded {cfg.generator_model!r}, "
            f"config of record {record['generator_model']!r}"
        )
    if cfg.judge_model != record["judge_model"]:
        mismatches.append(
            f"judge model: loaded {cfg.judge_model!r}, "
            f"config of record {record['judge_model']!r}"
        )
    if mismatches:
        raise EvalConfigMismatch(
            "live eval refused, loaded model config does not match "
            f"{config_path}: " + "; ".join(mismatches)
        )
    return cfg


def _require_live_gate(env: dict[str, str] | None = None) -> None:
    env = os.environ if env is None else env
    if env.get(LIVE_ENV_GATE) != "1":
        raise LiveGateError(
            f"live eval requires the environment gate {LIVE_ENV_GATE}=1 in "
            "addition to the explicit live flag; refusing to call models"
        )


def load_gold_items(path: Path = GOLD_SEED_PATH) -> list[dict[str, Any]]:
    """Load and structurally validate the hand-authored gold items."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    return [_validated_item(item, path) for item in items]


def _validated_item(item: dict[str, Any], origin: Path) -> dict[str, Any]:
    for field in ("id", "kind", "gold", "gold_citations"):
        if field not in item:
            raise ValueError(f"gold item in {origin} is missing {field!r}: {item}")
    if item["kind"] not in ITEM_KINDS:
        raise ValueError(f"gold item {item['id']!r} has unknown kind {item['kind']!r}")
    if item["kind"] == "classification" and "system_features" not in item:
        raise ValueError(f"classification item {item['id']!r} needs system_features")
    if item["kind"] in ("retrieval", "qa") and not item.get("question"):
        raise ValueError(f"{item['kind']} item {item['id']!r} needs a question")
    return item


def load_benchmark_items(path: Path = BENCHMARK_SAMPLE_PATH) -> list[dict[str, Any]]:
    """REF-15 benchmark sample -> the harness item shape.

    Loads eval/gold/benchmark_sample.json (a frozen, provenance-stamped
    sample of https://github.com/davidath/ai-act-evaluation-benchmark).
    Scenarios become classification items; their free-text description is
    kept verbatim under system_text and system_features stays None, because
    mapping free text into the structured feature schema is annotation work,
    not something a loader may invent (see eval/README.md). Gold citations
    are the article-level node ids for the benchmark's related_articles,
    since the benchmark cites at article granularity only.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = []
    for scenario in payload.get("scenarios", []):
        risk = BENCHMARK_RISK_MAP[scenario["risk_level"]]
        items.append(
            {
                "id": f"bench:scenario:{scenario['benchmark_index']}",
                "kind": "classification",
                "system_features": None,
                "system_text": (
                    f"Role: {scenario['role']}. Intended use: {scenario['intended_use']}. "
                    f"System type: {scenario['system_type']}. "
                    f"Input data: {scenario['input_data']}. Domain: {scenario['domain']}."
                ),
                "gold": {
                    "risk_category": risk,
                    "related_articles": scenario["related_articles"],
                    "obligations": scenario["obligations"],
                },
                "gold_citations": [
                    f"eu-ai-act:article-{n}" for n in scenario["related_articles"]
                ],
                "source": "REF-15 benchmark",
            }
        )
    for pair in payload.get("qa_pairs", []):
        items.append(
            {
                "id": f"bench:qa:{pair['benchmark_index']}",
                "kind": "qa",
                "question": pair["question"],
                "gold": {"answer_text": pair["answer"]},
                "gold_citations": [f"eu-ai-act:article-{pair['relevant_article']}"],
                "source": "REF-15 benchmark",
            }
        )
    return items


def results_artifact_name(build_id: str, strategy_names: list[str]) -> str:
    """Deterministic artifact name: build id plus a strategy-set digest.

    No timestamp and no randomness: the same build and strategy set always
    map to the same file name.
    """
    digest = hashlib.sha256(",".join(sorted(strategy_names)).encode("utf-8")).hexdigest()[:8]
    return f"eval_{build_id}_{digest}.json"


def runtime_judge_prompt_sha256(models_by_strategy: dict[str, dict[str, Any]]) -> dict[str, str] | None:
    """The runtime grounding judge's prompt hash per prompt version, for every
    condition that calls the runtime judge (graph_full and, since B126,
    graph_runtime_judge; strategies.uses_runtime_judge) whose models report
    judge_prompt_version, else None (no runtime judge was called). Such a
    strategy reports it when a runtime judge is set; the name alone is no
    evidence (B81 item 23).

    Hashed the way tere4ai.judge.runtime_grounding does (load_prompt, then
    prompt_sha256), never reimplemented; the key is "runtime_grounding" for
    the v1 prompt and "runtime_grounding@<version>" for a variant."""
    from tere4ai.judge.runtime_grounding import load_prompt, prompt_sha256

    hashes: dict[str, str] = {}
    for name, models in models_by_strategy.items():
        version = (models or {}).get("judge_prompt_version")
        if not uses_runtime_judge(name) or not version:
            continue
        key = "runtime_grounding" if version == "v1" else f"runtime_grounding@{version}"
        hashes[key] = prompt_sha256(load_prompt("runtime_grounding", version))
    return hashes or None


def strategy_models(strategies: dict[str, Any], strategy_names: list[str]) -> dict[str, dict[str, Any]]:
    """Each strategy's models as its clients report them, read once after the
    items ran (a failed run included) so the artifact and the record agree
    (docs/architecture.md DEC-17: the record names the models with prompt
    versions and hashes, the sampling and usage); since B99 the reported
    effort and temperature are the declared ones (spec F D-F29)."""
    return {name: dict(getattr(strategies[name], "models", {})) for name in strategy_names}


def _own_usage(generator: Any, judge: Any) -> dict[str, Any] | None:
    """The clients' own usage for this run, or None when the strategies were
    prebuilt (no client was built here)."""
    if generator is None:
        return None
    usage = {"generator": getattr(generator, "usage", None),
             "judge": getattr(judge, "usage", None) if judge is not None else None}
    return None if usage["generator"] is None and usage["judge"] is None else usage


def _declared_sampling_or_none(generator: Any, judge: Any) -> dict[str, str | None] | None:
    """The declared sampling the record stores, as run_ablations stores it
    (spec F D-F29), the judge keys null when no judge was built; None
    when no client was built here or an offline stub reports none of the
    values, as before B99."""
    if generator is None:
        return None
    sampling = declared_sampling(generator, judge)
    return None if set(sampling.values()) <= {"unknown", None} else sampling


def _refuse_deleted_unit_items(dump: dict[str, Any], items: list[dict[str, Any]]) -> None:
    """B132 (D-G68 (3)): a test-set item citing a unit the Omnibus deleted is
    refused (ValueError naming each) before any strategy runs or any client
    is built; the answer key is corrected instead."""
    refused = deleted_unit_citations(dump, items)
    if refused:
        raise ValueError("; ".join(refused))


def run_eval(
    items: list[dict[str, Any]],
    strategies: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] | list[str],
    generator_factory: Callable[[], ModelClient] | None = None,
    judge_factory: Callable[[], ModelClient] | None = None,
    live: bool = False,
    dump: dict[str, Any] | None = None,
    norms_payload: dict[str, Any] | None = None,
    results_dir: Path | None = None,
    judge_log_path: Path | None = None,
    config_path: Path = EVAL_CONFIG_PATH,
    record_store: EvaluationRecordStore | None = None,
    argv: list[str] | None = None,
    input_paths: dict[str, Path] | None = None,
    dump_dir: Path | None = None,
    repeat_of: str | None = None,
) -> dict[str, Any]:
    """Run every strategy over every item; write and return the results dict.

    strategies is either a mapping name -> already constructed callable, or
    a list of names from STRATEGY_NAMES, in which case generator_factory
    (and judge_factory for a condition that calls the runtime judge, see
    strategies.uses_runtime_judge) are called once each and the
    strategies are built over dump and norms_payload (defaulting to the
    published graph dumps on disk).

    live=False (the default) never touches a network: callers must inject
    fake or stub clients. live=True additionally requires TERE4AI_LIVE_TESTS=1
    and a loaded model config matching eval/config_evaluated.yaml (DEC-07),
    otherwise the run refuses to start.

    When record_store is given, one E6 "run" evaluation record (DEC-17) is
    written per call, covering the inputs actually read from disk, the
    models, usage and sampling the harness built, and the outcome
    (completed or partial by per-item errors). record_store=None (the
    default) records nothing and behaves exactly as before.

    repeat_of: the record id of the run this one repeats, recorded as
    relations.repeat_of.
    """
    config_public: dict[str, str]
    if live:
        _require_live_gate()
        config_public = guard_live_config(config_path=config_path).as_public_dict()
    else:
        config_public = {"mode": "offline", "note": "no live model was called"}

    read_paths: dict[str, Path] = {}
    generator = judge = None
    if not isinstance(strategies, dict):
        if generator_factory is None:
            raise ValueError("strategy names were given but no generator_factory")
        served = served_input_paths(dump_dir or LAYER1_DUMP_PATH.parent)
        for kind, preloaded in (("layer1_dump", dump), ("norms", norms_payload)):
            if preloaded is None and kind not in served:
                raise EvalAssetMissingError(f"the active publication names no {kind} file")
        if dump is None:
            dump = json.loads(served["layer1_dump"].read_text(encoding="utf-8"))
            read_paths["layer1_dump"] = served["layer1_dump"]
        # Refused before generator_factory() or judge_factory() builds a client.
        _refuse_deleted_unit_items(dump, items)
        if norms_payload is None:
            norms_payload = json.loads(served["norms"].read_text(encoding="utf-8"))
            read_paths["norms"] = served["norms"]
        generator = generator_factory()
        judge = None
        judged = [name for name in strategies if uses_runtime_judge(name)]
        if judged:
            if judge_factory is None:
                raise ValueError(f"{', '.join(judged)} was requested but no judge_factory")
            judge = judge_factory()
        strategies = {
            name: build_strategy(
                name, generator, dump, norms_payload,
                judge=judge, judge_log_path=judge_log_path,
            )
            for name in strategies
        }
    elif dump is not None:
        # Prebuilt strategies: refused before any of them runs.
        _refuse_deleted_unit_items(dump, items)

    build_id = str((dump or {}).get("build", {}).get("build_id", "unknown-build"))
    strategy_names = sorted(strategies)

    record_id = None
    notes: list[str] = []
    if record_store is not None:
        inputs = [input_ref(kind, path) for kind, path in read_paths.items()]
        if not read_paths:
            notes.append("the strategies were passed prebuilt; the harness did not read their inputs")
        inputs.append(input_ref("gold_seed", (input_paths or {}).get("gold_seed", GOLD_SEED_PATH)))
        if input_paths and "benchmark" in input_paths:
            inputs.append(input_ref("benchmark", input_paths["benchmark"]))
        models = None
        if live:
            models = strategy_models(strategies, strategy_names)
        # bind to a publication only when both served input kinds were read here (F4)
        if {"layer1_dump", "norms"} <= set(read_paths):
            publication, publication_reason = observe_publication(dump_dir or LAYER1_DUMP_PATH.parent)
        else:
            publication, publication_reason = None, "the harness did not read the served files"
        record_id = record_store.begin(
            kind="run", step="E6", command="eval_harness", argv=list(argv or []), inputs=inputs,
            build={"base_build_id": build_id if build_id != "unknown-build" else None,
                   "publication": publication, "publication_reason": publication_reason},
            models=models, config={**config_public, "strategies": strategy_names,
                                   "metrics_version": METRICS_VERSION, "code_version": code_version(REPO_ROOT)},
            item_selection=[item["id"] for item in items], intended_items=[item["id"] for item in items],
            relations={"repeat_of": repeat_of},
        )

    # the failure path covers everything from begin to finish (F3): a raise
    # or a KeyboardInterrupt in the loop finishes the record failed
    results: dict[str, dict[str, Any]] = {}
    try:
        for name in strategy_names:
            strategy = strategies[name]
            per_item: dict[str, Any] = {}
            # registered before the item loop, so a failure mid-strategy still
            # sees the items that finished (B81 item 4)
            results[name] = {
                "models": dict(getattr(strategy, "models", {})),
                "items": per_item,
            }
            for item in items:
                started = time.perf_counter()
                try:
                    outcome = strategy(item)
                except ConfigurationError:
                    raise  # spec F D-F29: a refused declared parameter stops the run, never an item's error
                except Exception as exc:  # noqa: BLE001 (one bad item never kills the run)
                    outcome = {
                        "answer_text": "",
                        "citations": [],
                        "risk_category": None,
                        "error": exception_reason(exc),
                    }
                outcome["latency_s"] = round(time.perf_counter() - started, 6)
                per_item[item["id"]] = outcome

        # read again, once, after every strategy ran, so the artifact and the
        # record hold the same models (Codex review of 73b8baa..782f26a,
        # docs/architecture.md DEC-17); since B99 the clients report their
        # declared values from the start (spec F D-F29)
        models_now = strategy_models(strategies, strategy_names)
        for name in strategy_names:
            results[name]["models"] = models_now[name]

        artifact = {
            "build_id": build_id,
            "live": live,
            "config": config_public,
            "strategies": strategy_names,
            "n_items": len(items),
            "item_ids": [item["id"] for item in items],
            "results": results,
        }

        out_dir = results_dir or RESULTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / results_artifact_name(build_id, strategy_names)
        ref = None
        if record_store is not None and record_id is not None:
            # the record copies this run's own bytes from a run-private temp
            # file, never the shared deterministic path another run of the
            # same build and strategies may be replacing (G3)
            fd, tmp = tempfile.mkstemp(prefix="tmp", suffix=".json", dir=str(out_dir))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(artifact, ensure_ascii=False, indent=1) + "\n")
            except BaseException:
                # only a failed temp write drops the temp file
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            try:
                ref = record_store.keep_output(record_id, "artifact", tmp, name=out_path.name)
            finally:
                # never lose paid bytes (G3b): the run's results land at the
                # compatibility path whether or not the record's copy succeeded;
                # a failed copy re-raises and the record ends failed (F3)
                try:
                    os.replace(tmp, out_path)
                except OSError as exc:
                    # the temp file is kept: it may be the only copy of the results (B81 item 35); the
                    # operator's terminal gets its full path, the record its file name (exception_reason)
                    raise OSError(f"{out_path.name} was not written ({exception_reason(exc)}): the results stay in "
                                  f"{tmp}; move it to {out_path.name}") from exc
        else:
            atomic_write_json(out_path, artifact)
        artifact["artifact_path"] = str(out_path)
        artifact["record_id"] = record_id
        if record_store is not None and record_id is not None:
            errored = sorted({item_id for block in results.values() for item_id, r in block["items"].items()
                              if r.get("error")})
            intended = [item["id"] for item in items]
            completed = [i for i in intended if i not in set(errored)]

            usage = _own_usage(generator, judge)
            sampling = _declared_sampling_or_none(generator, judge)
            prompt_hashes = runtime_judge_prompt_sha256(models_now)
            record_store.finish(record_id, status="completed" if not errored else "partial", completed_items=completed,
                                outputs=[ref], usage=usage, sampling=sampling, notes=notes,
                                prompt_sha256=prompt_hashes, models=models_now if live else None,
                                counts={"items_total": len(items), "items_with_errors": len(errored)})
    except BaseException as exc:
        if record_store is not None and record_id is not None:
            # completed: every strategy holds a result for the item without an error
            done = [item["id"] for item in items
                    if all(n in results and item["id"] in results[n]["items"]
                           and not results[n]["items"][item["id"]].get("error") for n in strategy_names)]
            end_failed(record_store, record_id, exception_reason(exc), notes=notes, completed_items=done,
                       usage=_own_usage(generator, judge), sampling=_declared_sampling_or_none(generator, judge),
                       models=strategy_models(strategies, strategy_names) if live else None)
        raise
    return artifact


class OfflineStubClient:
    """Offline stand-in for the CLI's default (non-live) smoke run.

    Returns a fixed, clearly labelled JSON body: never model output, never
    mistakable for a result. Its judge verdict is needs_human_review so a
    stub run can never look like an accepted, judged answer.
    """

    model = "offline-stub-no-model"

    def complete(self, system: str, user: str) -> str:  # noqa: ARG002
        return json.dumps(
            {
                "answer_text": (
                    "[offline stub: no model was called; run with --live and "
                    "TERE4AI_LIVE_TESTS=1 for real answers]"
                ),
                "citations": [],
                "risk_category": None,
                "verdict": "needs_human_review",
                "rationale": "offline stub, no model was called",
            }
        )


def main(argv: list[str] | None = None) -> int:
    """CLI: offline smoke run by default; live only behind --live plus the gate."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strategies", default=",".join(STRATEGY_NAMES),
        help="comma-separated subset of: " + ", ".join(STRATEGY_NAMES),
    )
    parser.add_argument("--gold", type=Path, default=GOLD_SEED_PATH)
    parser.add_argument(
        "--benchmark-sample", action="store_true",
        help="also load eval/gold/benchmark_sample.json items",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="call the configured real models; ALSO requires TERE4AI_LIVE_TESTS=1 "
             "and a model config matching eval/config_evaluated.yaml (costs money)",
    )
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument("--dump-dir", type=Path, default=REPO_ROOT / "data" / "graph_dumps",
                        help="where layer1.json, norms_core.json and evaluation_records/ live "
                             "(default: the checkout's data/graph_dumps)")
    parser.add_argument("--no-record", action="store_true", help="do not write an evaluation record (D-G33)")
    parser.add_argument("--repeat-of", default=None, help="record id of the run this run repeats")
    args = parser.parse_args(argv)

    if args.repeat_of is not None and args.no_record:
        print("--repeat-of: a --no-record run records no relation; drop one of the two flags")
        return 2
    if args.repeat_of is not None:
        # resolved through a read-only store first: a refusal leaves no evaluation_records/ behind (B81 item 10)
        try:
            EvaluationRecordStore(args.dump_dir, create=False).read(args.repeat_of)
        except EvaluationRecordError as exc:
            print(f"--repeat-of: {exc}")
            return 2
    record_store = None if args.no_record else EvaluationRecordStore(args.dump_dir)

    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    items = load_gold_items(args.gold)
    if args.benchmark_sample:
        items += load_benchmark_items()

    if args.live:
        cfg = guard_live_config()  # refuse before any client is constructed
        _require_live_gate()
        from tere4ai.extract_norms.model_clients import AnthropicJudge, OpenAIGenerator

        generator_factory: Callable[[], ModelClient] = lambda: OpenAIGenerator(cfg)  # noqa: E731
        judge_factory: Callable[[], ModelClient] = lambda: AnthropicJudge(cfg)  # noqa: E731
    else:
        generator_factory = OfflineStubClient
        judge_factory = OfflineStubClient

    artifact = run_eval(
        items,
        names,
        generator_factory=generator_factory,
        judge_factory=judge_factory,
        live=args.live,
        results_dir=args.results_dir,
        record_store=record_store,
        argv=list(argv) if argv is not None else sys.argv[1:],
        input_paths={"gold_seed": args.gold,
                     **({"benchmark": BENCHMARK_SAMPLE_PATH} if args.benchmark_sample else {})},
        dump_dir=args.dump_dir,
        repeat_of=args.repeat_of,
    )
    print(
        f"wrote {artifact['artifact_path']} "
        f"({artifact['n_items']} items x {len(artifact['strategies'])} strategies, "
        f"live={artifact['live']})"
    )
    if artifact.get("record_id"):
        print(f"evaluation record {artifact['record_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

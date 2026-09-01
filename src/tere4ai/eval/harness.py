"""M4 evaluation harness: run the ablation ladder over gold/benchmark items.

@implements: DEC-11
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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tere4ai.eval.strategies import STRATEGY_NAMES, build_strategy
from tere4ai.extract_norms.model_clients import ModelClient
from tere4ai.judge.config import ModelConfig, load_model_config


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
BENCHMARK_RISK_MAP = {
    "prohibited": "prohibited",
    "high-risk": "high_risk",
    "limited": "transparency_only",
    "minimal": "minimal_or_none",
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
) -> dict[str, Any]:
    """Run every strategy over every item; write and return the results dict.

    strategies is either a mapping name -> already constructed callable, or
    a list of names from STRATEGY_NAMES, in which case generator_factory
    (and judge_factory for graph_full) are called once each and the
    strategies are built over dump and norms_payload (defaulting to the
    published graph dumps on disk).

    live=False (the default) never touches a network: callers must inject
    fake or stub clients. live=True additionally requires TERE4AI_LIVE_TESTS=1
    and a loaded model config matching eval/config_evaluated.yaml (DEC-07),
    otherwise the run refuses to start.
    """
    config_public: dict[str, str]
    if live:
        _require_live_gate()
        config_public = guard_live_config(config_path=config_path).as_public_dict()
    else:
        config_public = {"mode": "offline", "note": "no live model was called"}

    if not isinstance(strategies, dict):
        if generator_factory is None:
            raise ValueError("strategy names were given but no generator_factory")
        if dump is None:
            dump = json.loads(LAYER1_DUMP_PATH.read_text(encoding="utf-8"))
        if norms_payload is None:
            norms_payload = json.loads(NORMS_PATH.read_text(encoding="utf-8"))
        generator = generator_factory()
        judge = None
        if "graph_full" in strategies:
            if judge_factory is None:
                raise ValueError("graph_full was requested but no judge_factory")
            judge = judge_factory()
        strategies = {
            name: build_strategy(
                name, generator, dump, norms_payload,
                judge=judge, judge_log_path=judge_log_path,
            )
            for name in strategies
        }

    build_id = str((dump or {}).get("build", {}).get("build_id", "unknown-build"))
    strategy_names = sorted(strategies)

    results: dict[str, dict[str, Any]] = {}
    for name in strategy_names:
        strategy = strategies[name]
        per_item: dict[str, Any] = {}
        for item in items:
            started = time.perf_counter()
            try:
                outcome = strategy(item)
            except Exception as exc:  # noqa: BLE001 (one bad item never kills the run)
                outcome = {
                    "answer_text": "",
                    "citations": [],
                    "risk_category": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            outcome["latency_s"] = round(time.perf_counter() - started, 6)
            per_item[item["id"]] = outcome
        results[name] = {
            "models": dict(getattr(strategy, "models", {})),
            "items": per_item,
        }

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
    out_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    artifact["artifact_path"] = str(out_path)
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
    args = parser.parse_args(argv)

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
    )
    print(
        f"wrote {artifact['artifact_path']} "
        f"({artifact['n_items']} items x {len(artifact['strategies'])} strategies, "
        f"live={artifact['live']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

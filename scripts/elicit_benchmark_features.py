"""Elicit system_features for the benchmark's free-text scenarios (paid).

@implements: DEC-13
@grounded_by: REF-17

Checkpointed per item; resume by re-running. A provider overload is waited
out under the terminal policy; a stop or a provider refusal keeps the
checkpoint and prints the command that resumes it (spec F D-F30). Every
checkpoint entry and the output name the model declaration they were
elicited under (`models`, spec F D-F29), and a rerun over entries of another
declaration is refused. Writes eval/gold/benchmark_features.json with
provenance llm_elicited so ablation summaries can separate authored from
elicited features.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.elicit_features import elicit_features  # noqa: E402
from tere4ai.eval import harness  # noqa: E402
from tere4ai.extract_norms.model_clients import (  # noqa: E402
    TERMINAL_POLICY,
    OpenAIGenerator,
    ProviderRefused,
    ProviderUnavailable,
)
from tere4ai.judge.config import ConfigurationError, load_model_config  # noqa: E402

DEFAULT_OUT = ROOT / "eval" / "gold" / "benchmark_features.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--benchmark", type=Path, default=harness.BENCHMARK_SAMPLE_PATH,
        help="benchmark payload (default: the frozen 32+15 sample)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--prompt-version", default="v2",
        help="elicitor prompt version, recorded in the output",
    )
    args = parser.parse_args(argv)
    run_argv = list(sys.argv[1:] if argv is None else argv)
    OUT = args.out
    CKPT = OUT.with_suffix(".checkpoint.jsonl")

    items = [
        i
        for i in harness.load_benchmark_items(args.benchmark)
        if i.get("kind") == "classification" and not i.get("system_features")
    ]
    print(f"scenarios needing elicitation: {len(items)}")

    done: dict[str, dict] = {}
    if CKPT.exists():
        for line in CKPT.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            done[e["item_id"]] = e
        print(f"resume: {len(done)} already elicited")

    cfg = load_model_config()
    # spec F D-F29: the entries and the output name the declaration, so the
    # cache never mixes items elicited under two (a missing one differs too)
    models = cfg.as_public_dict()
    if any((e.get("models") or {}).get("model_parameters_sha256") != models["model_parameters_sha256"]
           for e in done.values()):
        print(f"refusing to resume {CKPT.name}: an elicited item was run under different models: "
              "model_parameters_sha256; restore the row in config/model_parameters.json to resume it, or move "
              "the checkpoint away to start again")
        return 2
    generator = OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)  # spec F D-F30: a terminal run with a checkpoint waits out an overload

    try:
        with CKPT.open("a", encoding="utf-8") as ckpt:
            for item in items:
                if item["id"] in done:
                    continue
                description = item.get("system_text") or ""
                if len(description) < 10:
                    entry = {
                        "item_id": item["id"],
                        "features": None,
                        "notes": ["no usable system_text; skipped without a model call"],
                        "provenance": "llm_elicited",
                        "elicitor_model": cfg.generator_model,
                        "models": models,
                    }
                    ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    ckpt.flush()
                    done[item["id"]] = entry
                    print(f"  {item['id']}: SKIPPED (no text)", flush=True)
                    continue
                try:
                    features, notes = elicit_features(
                        description, generator, prompt_version=args.prompt_version
                    )
                except ProviderRefused as exc:
                    # spec F D-F30, B101 ruling S5: the reason names the item, which is
                    # fixed before the rerun, never skipped
                    raise ProviderRefused(f"{exc.cause} (item {item['id']})") from exc
                entry = {
                    "item_id": item["id"],
                    "features": features,
                    "notes": notes,
                    "provenance": "llm_elicited",
                    "elicitor_model": cfg.generator_model,
                    "models": models,
                }
                ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                ckpt.flush()
                done[item["id"]] = entry
                status = "ok" if features else "FAILED"
                print(f"  {item['id']}: {status}", flush=True)
    except (ProviderUnavailable, ProviderRefused) as exc:
        # spec F D-F30: the checkpoint stays; re-running the same command resumes
        print(f"stopped: {exc}", file=sys.stderr)
        print(f"the checkpoint {CKPT.name} is kept ({sum(i['id'] in done for i in items)} of {len(items)} "
              "items done); continue with:", file=sys.stderr)
        print("  " + shlex.join([".venv/bin/python", "scripts/elicit_benchmark_features.py", *run_argv]),
              file=sys.stderr)
        return 3 if isinstance(exc, ProviderUnavailable) else 5
    except ConfigurationError as exc:
        # spec F D-F29: a declared parameter the provider refused stops the run
        print(f"stopped: {exc}", file=sys.stderr)
        return 4

    payload = {
        "provenance": "llm_elicited",
        "elicitor_model": cfg.generator_model,
        "models": models,
        "prompt_version": args.prompt_version,
        "note": (
            "Machine-elicited features for benchmark free-text scenarios. The "
            "deterministic classifier still decides; elicitation only supplies "
            "facts, and omitted flags surface as missing_facts. Human-verified "
            "features per the annotation protocol supersede these."
        ),
        "features_by_item": {k: v["features"] for k, v in done.items()},
    }
    tmp = OUT.with_suffix(".writing.json")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    CKPT.unlink(missing_ok=True)
    failed = sum(1 for v in done.values() if not v["features"])
    print(f"wrote {OUT} ({len(done)} items, {failed} failed elicitations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

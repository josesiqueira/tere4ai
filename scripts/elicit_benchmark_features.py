"""Elicit system_features for the benchmark's free-text scenarios (paid).

@implements: DEC-13, DEC-18
@grounded_by: REF-17

Checkpointed per item; resume by re-running. An inference backend overload is
waited out under the terminal policy; a stop or an inference backend refusal keeps the
checkpoint and prints the command that resumes it (spec F D-F30). Every
checkpoint entry and the output name the model declaration they were
elicited under (`models`, spec F D-F29), and a rerun over entries of another
declaration is refused. Writes eval/gold/benchmark_features.json with
provenance llm_elicited so ablation summaries can separate authored from
elicited features.

B10: the run serves the build load_active reads from data/graph_dumps and
renders the prompt over it once before the first item (render_prompt; a
provision that does not resolve refuses the run before any model call).
Each item is elicited with elicit(); every checkpoint entry carries its
quotes, dropped facts and prompt record, and the output names the prompt
once (the run is on one build) beside quotes_by_item, dropped_by_item and
the unchanged features_by_item. A rerun over entries of another prompt
version, template or build is refused, as one under other models is.

B164 (spec F D-F30 as amended 2026-10-12): --max-in-flight (default 8)
scenarios are elicited at once; the checkpoint lines are written and the items
printed in the benchmark's order, and the output lists the items in that order
(ruling R16), so a run at 8 writes the files a run at 1 writes; the output names
the setting (max_in_flight).

--max-usd (required) is the ceiling of this run's spend, at the list prices of
config/model_prices.json over the usage the inference backend reports: before
a scenario's call starts, the run stops when the spend so far plus a reserve
for the calls in flight (the dearest finished call times --max-in-flight)
would pass the ceiling; the checkpoint is kept and the exit code is 6. The
spend of an earlier, stopped run is not in a rerun's count. --dry-run prints
the priced plan and makes no model call.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai import parallel_calls  # noqa: E402
from tere4ai.elicit_features import elicit, render_prompt  # noqa: E402
from tere4ai.elicit_features.elicitor import (  # noqa: E402
    DEFAULT_PROMPT_VERSION,
    DUMP_DIR,
    SNAPSHOTS_DIR,
)
from tere4ai.elicit_features.provisions import ProvisionUnresolved  # noqa: E402
from tere4ai.eval import harness  # noqa: E402
from tere4ai.extract_norms.model_clients import (  # noqa: E402
    TERMINAL_POLICY,
    InferenceBackendRefused,
    InferenceBackendUnavailable,
    OpenAIGenerator,
    usage_snapshot,
)
from tere4ai.graph_store.publication import load_active  # noqa: E402
from tere4ai.judge.config import (  # noqa: E402
    ConfigurationError,
    load_model_config,
    load_model_prices,
)
from tere4ai.parallel_calls import run_in_flight  # noqa: E402
from tere4ai.rejudge.cost import CostStop, usage_cost, usd  # noqa: E402

DEFAULT_OUT = ROOT / "eval" / "gold" / "benchmark_features.json"
# B10: the prompt record's fields a resumed entry must share with the run:
# the version and template (the instrument) and the build it was rendered
# over (graph_version, rendered_sha256), so the output's one record is true
# of every item
PROMPT_RESUME_KEYS = ("version", "template_sha256", "rendered_sha256", "graph_version")
# --dry-run: characters per token of the plan's input count, and the reply
# size (reasoning included) it assumes per call; docs/benchmark_cost_estimate.md
# holds the measured ratio and the band
DRY_RUN_CHARS_PER_TOKEN = 4.0
DRY_RUN_OUTPUT_TOKENS_PER_CALL = 1100


def _max_usd(text: str) -> float:
    """The argparse type of --max-usd: a positive amount in USD."""
    try:
        value = float(text)
    except ValueError:
        value = 0.0
    if not value > 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive amount in USD")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--benchmark", type=Path, default=harness.BENCHMARK_SAMPLE_PATH,
        help="benchmark payload (default: the frozen 32+15 sample)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--prompt-version", default=DEFAULT_PROMPT_VERSION,
        help="elicitor prompt version, recorded in the output (default: the elicitor's own)",
    )
    parser.add_argument("--max-usd", type=_max_usd, required=True,
                        help="ceiling of this run's spend in USD at list price; the run stops before passing it")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the priced plan and make no model call")
    parallel_calls.add_max_in_flight_argument(parser)
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
    # B10: the build is loaded and the prompt rendered before any client is
    # built, so a build or a provision that does not resolve costs nothing
    loaded = load_active(DUMP_DIR)
    if loaded.dump is None:
        print(f"refusing to elicit: no build is served: {loaded.error}")
        return 2
    dump = loaded.dump
    prices = load_model_prices()
    if cfg.generator_model not in prices:
        print(f"refusing to elicit: config/model_prices.json has no price row for the generator model "
              f"{cfg.generator_model!r}, so the spend cannot be known; no model call made")
        return 2
    price = prices[cfg.generator_model]
    try:
        system, prompt = render_prompt(dump, SNAPSHOTS_DIR, args.prompt_version)
    except ProvisionUnresolved as exc:
        print(f"refusing to elicit: definition {exc.node_id} does not resolve in {exc.build}: {exc.reason}; "
              "no model call made")
        return 2
    differing = sorted({k for e in done.values() for k in PROMPT_RESUME_KEYS
                        if (e.get("prompt") or {}).get(k) != prompt[k]})
    if differing:
        print(f"refusing to resume {CKPT.name}: an elicited item was run under a different prompt: "
              f"{', '.join(differing)}; rerun with the prompt version and the build the checkpoint names to "
              "resume it, or move the checkpoint away to start again")
        return 2
    if args.dry_run:
        texts = [i.get("system_text") or "" for i in items if i["id"] not in done]
        texts = [t for t in texts if len(t) >= 10]
        tokens_in = int(round(sum(len(system) + len(t) for t in texts) / DRY_RUN_CHARS_PER_TOKEN))
        tokens_out = DRY_RUN_OUTPUT_TOKENS_PER_CALL * len(texts)
        cost = usage_cost({"input_tokens": tokens_in, "output_tokens": tokens_out}, price)
        print(f"dry run, no model call made: {len(texts)} calls to {cfg.generator_model} (prompt "
              f"{args.prompt_version}, build {prompt['graph_version']}); about {tokens_in} input tokens "
              f"({DRY_RUN_CHARS_PER_TOKEN} characters per token) at {price['input']} USD per million and "
              f"{tokens_out} output tokens ({DRY_RUN_OUTPUT_TOKENS_PER_CALL} per call, reasoning included, "
              f"assumed) at {price['output']} USD per million: about {usd(cost)} USD; ceiling {usd(args.max_usd)} USD")
        return 0
    generator = OpenAIGenerator(cfg, retry_policy=TERMINAL_POLICY)  # spec F D-F30: a terminal run with a checkpoint waits out an overload
    print(f"calls in flight: at most {args.max_in_flight} (--max-in-flight)", flush=True)

    def spent() -> float:
        return usage_cost(usage_snapshot(generator), price)

    dearest = [0.0]  # the dearest finished call so far, the reserve per call in flight

    def entry_for(item: dict) -> tuple[dict, str]:
        """One scenario's entry and the word printed for it (B164: on a worker thread when
        --max-in-flight > 1; it writes nothing)."""
        description = item.get("system_text") or ""
        so_far = spent()
        if len(description) >= 10 and so_far + dearest[0] * args.max_in_flight >= args.max_usd:
            raise CostStop(so_far, args.max_usd)
        if len(description) < 10:
            return {
                "item_id": item["id"],
                "features": None,
                "quotes": {},
                "dropped": [],
                "notes": ["no usable system_text; skipped without a model call"],
                "prompt": prompt,
                "provenance": "llm_elicited",
                "elicitor_model": cfg.generator_model,
                "models": models,
            }, "SKIPPED (no text)"
        try:
            result = elicit(description, generator, dump=dump, snapshots_dir=SNAPSHOTS_DIR,
                            prompt_version=args.prompt_version)
        except InferenceBackendRefused as exc:
            # spec F D-F30, B101 ruling S5: the reason names the item, which is
            # fixed before the rerun, never skipped
            raise InferenceBackendRefused(f"{exc.cause} (item {item['id']})") from exc
        features = result.features
        return {
            "item_id": item["id"],
            "features": features,
            "quotes": result.quotes,
            "dropped": result.dropped,
            "notes": result.notes,
            "prompt": result.prompt,
            "provenance": "llm_elicited",
            "elicitor_model": cfg.generator_model,
            "models": models,
        }, ("ok" if features else "FAILED")

    try:
        with CKPT.open("a", encoding="utf-8") as ckpt:
            def keep(_index: int, outcome: tuple[dict, str]) -> None:
                entry, word = outcome
                ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
                ckpt.flush()
                done[entry["item_id"]] = entry
                now = spent()
                dearest[0] = max(dearest[0], now - keep.last)
                keep.last = now
                print(f"  {entry['item_id']}: {word}", flush=True)

            keep.last = 0.0
            run_in_flight([item for item in items if item["id"] not in done], entry_for,
                          max_in_flight=args.max_in_flight, on_result=keep)
    except (InferenceBackendUnavailable, InferenceBackendRefused) as exc:
        # spec F D-F30: the checkpoint stays; re-running the same command resumes
        print(f"stopped: {exc}", file=sys.stderr)
        print(f"the checkpoint {CKPT.name} is kept ({sum(i['id'] in done for i in items)} of {len(items)} "
              "items done); continue with:", file=sys.stderr)
        print("  " + shlex.join([".venv/bin/python", "scripts/elicit_benchmark_features.py", *run_argv]),
              file=sys.stderr)
        return 3 if isinstance(exc, InferenceBackendUnavailable) else 5
    except CostStop as exc:
        print(f"stopped: {exc}, with the reserve for the calls in flight counted", file=sys.stderr)
        print(f"the checkpoint {CKPT.name} is kept ({sum(i['id'] in done for i in items)} of {len(items)} "
              f"items done); this run spent {usd(spent())} USD at list price", file=sys.stderr)
        return 6
    except ConfigurationError as exc:
        # spec F D-F29: a declared parameter the inference backend refused stops the run
        print(f"stopped: {exc}", file=sys.stderr)
        return 4

    # B164 (R16): the items in the benchmark's order, then any checkpoint entry for an
    # item the benchmark no longer lists, in the file's order; a run with one call at a
    # time, whose checkpoint is always a prefix, writes the order it always wrote
    listed = [i["id"] for i in items if i["id"] in done]
    seen = set(listed)
    order = listed + [k for k in done if k not in seen]
    payload = {
        "provenance": "llm_elicited",
        "elicitor_model": cfg.generator_model,
        "models": models,
        "prompt_version": args.prompt_version,
        "prompt": prompt,
        "max_in_flight": args.max_in_flight,
        "note": (
            "Machine-elicited features for benchmark free-text scenarios. The "
            "deterministic classifier still decides; elicitation only supplies "
            "facts, and omitted flags surface as missing_facts. Human-verified "
            "features per the annotation protocol supersede these."
        ),
        "features_by_item": {k: done[k]["features"] for k in order},
        "quotes_by_item": {k: done[k]["quotes"] for k in order},
        "dropped_by_item": {k: done[k]["dropped"] for k in order},
    }
    tmp = OUT.with_suffix(".writing.json")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)
    CKPT.unlink(missing_ok=True)
    failed = sum(1 for v in done.values() if not v["features"])
    print(f"wrote {OUT} ({len(done)} items, {failed} failed elicitations)")
    print(f"spent {usd(spent())} USD at list price of {usd(args.max_usd)} USD; usage {usage_snapshot(generator)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

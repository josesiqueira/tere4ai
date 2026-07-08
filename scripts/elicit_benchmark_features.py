"""Elicit system_features for the benchmark's free-text scenarios (paid).

@implements: DEC-08 (partial: elicitation front-end)
@grounded_by: REF-17

Checkpointed per item; resume by re-running. Writes
eval/gold/benchmark_features.json with provenance llm_elicited so ablation
summaries can separate authored from elicited features.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tere4ai.elicit_features import elicit_features  # noqa: E402
from tere4ai.eval import harness  # noqa: E402
from tere4ai.extract_norms.model_clients import OpenAIGenerator  # noqa: E402
from tere4ai.judge.config import load_model_config  # noqa: E402

OUT = ROOT / "eval" / "gold" / "benchmark_features.json"
CKPT = OUT.with_suffix(".checkpoint.jsonl")


def main() -> int:
    items = [
        i
        for i in harness.load_benchmark_items()
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
    generator = OpenAIGenerator(cfg)

    with CKPT.open("a", encoding="utf-8") as ckpt:
        for item in items:
            if item["id"] in done:
                continue
            description = item.get("question") or item.get("description") or ""
            features, notes = elicit_features(description, generator)
            entry = {
                "item_id": item["id"],
                "features": features,
                "notes": notes,
                "provenance": "llm_elicited",
                "elicitor_model": cfg.generator_model,
            }
            ckpt.write(json.dumps(entry, ensure_ascii=False) + "\n")
            ckpt.flush()
            done[item["id"]] = entry
            status = "ok" if features else "FAILED"
            print(f"  {item['id']}: {status}", flush=True)

    payload = {
        "provenance": "llm_elicited",
        "elicitor_model": load_model_config().generator_model,
        "prompt_version": "v1",
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

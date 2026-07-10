"""Cost estimator tests (#73): counting client, benchmark integrity, report."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "estimate_benchmark_cost", ROOT / "scripts" / "estimate_benchmark_cost.py"
)
est = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(est)

FULL_FILES_PRESENT = (est.BENCH_DIR / "scenarios.json").exists() and (
    est.BENCH_DIR / "qa_pairs.json"
).exists()


def test_counting_client_records_and_replies():
    client = est.CountingClient("gpt-5.2", {"answer_text": "x", "citations": []})
    reply = client.complete("system prompt", "user text")
    assert json.loads(reply)["answer_text"] == "x"
    assert client.calls == 1
    assert client.prompt_chars == len("system prompt") + len("user text")


def test_tokens_uses_chars_per_token():
    assert est.tokens(400) == int(round(400 / est.CHARS_PER_TOKEN))


def test_judge_price_matches_documented_source():
    # Anthropic published pricing for claude-opus-4-8 (cached 2026-06).
    assert (est.JUDGE_PRICE_IN, est.JUDGE_PRICE_OUT) == (5.00, 25.00)


@pytest.mark.skipif(not FULL_FILES_PRESENT, reason="full benchmark files not downloaded")
def test_full_benchmark_verifies_and_loads_all_items():
    from tere4ai.eval.harness import load_benchmark_items

    payload_path = est.verify_full_benchmark()
    try:
        items = load_benchmark_items(payload_path)
    finally:
        payload_path.unlink(missing_ok=True)
    kinds = [i["kind"] for i in items]
    assert kinds.count("classification") == 339
    assert kinds.count("qa") == 137


@pytest.mark.skipif(not FULL_FILES_PRESENT, reason="full benchmark files not downloaded")
def test_checksum_mismatch_is_fatal(tmp_path, monkeypatch):
    bad_dir = tmp_path / "benchmark"
    bad_dir.mkdir()
    for name in ("scenarios.json", "qa_pairs.json"):
        bad_dir.joinpath(name).write_text('{"data": []}', encoding="utf-8")
    monkeypatch.setattr(est, "BENCH_DIR", bad_dir)
    with pytest.raises(SystemExit, match="sha256"):
        est.verify_full_benchmark()


def test_observed_output_chars_reads_run2_checkpoint():
    out = est.observed_output_chars()
    assert "plain_llm" in out
    assert out["plain_llm"]["classification"] > 0

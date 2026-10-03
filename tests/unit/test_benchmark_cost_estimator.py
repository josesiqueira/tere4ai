"""Cost estimator tests (#73): counting client, benchmark integrity, report."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tere4ai.elicit_features.elicitor import DEFAULT_PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "estimate_benchmark_cost", ROOT / "scripts" / "estimate_benchmark_cost.py"
)
est = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(est)

FULL_FILES_PRESENT = (est.BENCH_DIR / "scenarios.json").exists() and (
    est.BENCH_DIR / "qa_pairs.json"
).exists()


def test_elicitation_prompt_path_follows_the_default_prompt_version():
    assert est.ELICIT_PROMPT.name == f"{DEFAULT_PROMPT_VERSION}.md"
    assert est.ELICIT_PROMPT.exists()


@pytest.mark.skipif(not est.ELICIT_DUMP.is_file(), reason="layer1.json dump not built")
def test_the_elicitation_prompt_counted_is_the_rendered_one():
    """B10: v6 carries provision placeholders; the estimator counts the
    prompt rendered over the repository's dump (no model call), the size a
    live call sends, not the template's."""
    from tere4ai.elicit_features import render_prompt

    dump = json.loads(est.ELICIT_DUMP.read_text(encoding="utf-8"))
    system, _ = render_prompt(dump, ROOT / "data" / "snapshots")
    counted = est.elicit_system_prompt()
    assert counted == system
    assert "{{provision:" not in counted
    assert len(counted) > len(est.ELICIT_PROMPT.read_text(encoding="utf-8"))


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


def test_elicitation_output_counts_features_and_quotes_when_the_file_has_quotes():
    """B10 final review: a v6 reply carries quotes beside the features, so
    the output size per item is the two together, each quote counted as the
    reply sends it (path to text; the offsets are added by the code)."""
    feats = {"a": {"flags": {"x": True}}, "b": {"domain": "banking"}}
    quotes = {"a": {"flags.x": {"text": "one two three", "start": 0, "end": 13}},
              "b": {"domain": {"text": "our bank site", "start": 4, "end": 17}}}
    mean, note = est.elicitation_output_chars({"features_by_item": feats, "quotes_by_item": quotes})
    sent = {"a": {"flags.x": "one two three"}, "b": {"domain": "our bank site"}}
    expected = [len(json.dumps(feats[k])) + len(json.dumps(sent[k])) for k in feats]
    assert mean == sum(expected) / 2
    assert note is None


def test_elicitation_output_counts_features_only_and_says_so_without_quotes():
    feats = {"a": {"flags": {"x": True}}, "b": {"domain": "banking"}}
    mean, note = est.elicitation_output_chars({"features_by_item": feats})
    assert mean == sum(len(json.dumps(v)) for v in feats.values()) / 2
    assert note is not None and "features only" in note and "no quotes" in note


def test_a_condition_the_july_checkpoint_lacks_takes_its_proxy_output_size():
    # B126: graph_runtime_judge was not run in July; its generator sees the
    # prompt of graph_no_judge, so it takes that condition's observed sizes
    # instead of a silent 0
    out = {"graph_no_judge": {"qa": 120.0, "classification": 80.0}}
    assert est.output_chars_for(out, "graph_runtime_judge") == (out["graph_no_judge"], "graph_no_judge")
    assert est.output_chars_for(out, "graph_no_judge") == (out["graph_no_judge"], None)
    assert est.output_chars_for(out, "plain_llm") == ({}, None)

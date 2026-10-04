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


def test_main_charges_the_sixth_condition_the_proxy_output_size(tmp_path, monkeypatch):
    # B126 final review M2: the estimate itself, not only the helper, gives
    # graph_runtime_judge graph_no_judge's observed answer size
    def fake_run_eval(subset, names, generator_factory, judge_factory, **_kwargs):
        gen = generator_factory()
        for _item in subset:
            gen.complete("system", "user")

    monkeypatch.setenv("TERE4AI_GENERATOR_MODEL", "gpt-6-astra")
    monkeypatch.setenv("TERE4AI_JUDGE_MODEL", "claude-opus-5-5")
    monkeypatch.setattr(est, "load_dotenv_once", lambda: None)
    monkeypatch.setattr(est, "ROOT", tmp_path)
    monkeypatch.setattr(est, "OUT_PATH", tmp_path / "estimate.md")
    monkeypatch.setattr(est, "verify_full_benchmark", lambda: tmp_path / "bench.json")
    monkeypatch.setattr(est, "load_benchmark_items",
                        lambda _p: [{"id": "bench:qa:1", "kind": "qa", "question": "q"}])
    monkeypatch.setattr(est, "observed_output_chars", lambda: {"graph_no_judge": {"qa": 4000.0}})
    monkeypatch.setattr(est, "observed_judge_reply_chars", lambda: 700.0)
    monkeypatch.setattr(est, "elicitation_output_chars", lambda _facts: (100.0, None))
    monkeypatch.setattr(est, "STRATEGY_NAMES", ("graph_no_judge", "graph_runtime_judge"))
    monkeypatch.setattr(est, "run_eval", fake_run_eval)
    assert est.main() == 0
    rows = {line.split("|")[1].strip(): [c.strip() for c in line.split("|")[2:-1]]
            for line in (tmp_path / "estimate.md").read_text(encoding="utf-8").splitlines()
            if line.startswith("| graph_")}
    assert rows["graph_runtime_judge"][2] == rows["graph_no_judge"][2] != "0"


# ---------------------------------------------------------------- B120 task 1
# the price table and the declared models (spec F D-F29 discipline)

PRICES_PATH = ROOT / "config" / "model_prices.json"


def _price_row(**over):
    row = {
        "provider": "openai", "currency": "USD",
        "input": "1.00", "output": "2.00", "batch_input": "0.50", "batch_output": "1.00",
        "pricing": {"url": "https://example.com/pricing", "read_on": "2026-10-04"},
        "quote": "mock line",
    }
    row.update(over)
    return row


def _write_prices(tmp_path, models):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"schema_version": 1, "models": models}), encoding="utf-8")
    return path


@pytest.mark.parametrize("pricing", [
    {"read_on": "2026-10-04"},
    {"url": "https://example.com/p"},
    {"url": "http://example.com/p", "read_on": "2026-10-04"},
    {"url": "https://example.com/p", "read_on": "2026-W40-1"},
    {"url": "https://example.com/p", "read_on": "2026-13-45"},
])
def test_a_price_row_without_a_page_or_a_day_is_refused_by_name(tmp_path, pricing):
    path = _write_prices(tmp_path, {"mock-model": _price_row(pricing=pricing)})
    with pytest.raises(est.ConfigurationError, match="mock-model"):
        est.load_model_prices(path)


def test_a_price_row_missing_a_price_is_refused_by_name(tmp_path):
    row = _price_row()
    del row["batch_output"]
    path = _write_prices(tmp_path, {"mock-model": row})
    with pytest.raises(est.ConfigurationError, match="mock-model"):
        est.load_model_prices(path)


def test_a_valid_price_row_loads_as_decimals(tmp_path):
    prices = est.load_model_prices(_write_prices(tmp_path, {"mock-model": _price_row()}))
    assert prices["mock-model"]["input"] == 1.0 and prices["mock-model"]["batch_output"] == 1.0
    assert prices["mock-model"]["pricing"]["read_on"] == "2026-10-04"


def test_a_model_the_environment_names_without_a_price_row_is_refused(tmp_path):
    prices = est.load_model_prices(_write_prices(tmp_path, {"mock-model": _price_row()}))
    env = {"TERE4AI_GENERATOR_MODEL": "gpt-6-astra", "TERE4AI_JUDGE_MODEL": "claude-opus-5-5"}
    declared = est.declared_models(env)
    with pytest.raises(est.ConfigurationError, match="gpt-6-astra"):
        est.price_rows(prices, declared)


def test_declared_models_reads_the_two_ids_with_their_declared_rows():
    declared = est.declared_models(
        {"TERE4AI_GENERATOR_MODEL": "gpt-6-astra", "TERE4AI_JUDGE_MODEL": "claude-opus-5-5"})
    assert declared["generator"].model_id == "gpt-6-astra"
    assert declared["generator"].provider == "openai" and declared["generator"].effort == "xhigh"
    assert declared["judge"].model_id == "claude-opus-5-5"
    assert declared["judge"].provider == "anthropic" and declared["judge"].effort == "xhigh"


@pytest.mark.parametrize("missing", ["TERE4AI_GENERATOR_MODEL", "TERE4AI_JUDGE_MODEL"])
def test_declared_models_refuses_an_unset_model(missing):
    env = {"TERE4AI_GENERATOR_MODEL": "gpt-6-astra", "TERE4AI_JUDGE_MODEL": "claude-opus-5-5"}
    del env[missing]
    with pytest.raises(est.ConfigurationError, match=missing):
        est.declared_models(env)


def test_declared_models_refuses_a_model_without_a_declaration_row():
    with pytest.raises(est.ConfigurationError, match="no-such-model"):
        est.declared_models({"TERE4AI_GENERATOR_MODEL": "no-such-model",
                             "TERE4AI_JUDGE_MODEL": "claude-opus-5-5"})


def test_the_script_names_no_model():
    source = (ROOT / "scripts" / "estimate_benchmark_cost.py").read_text(encoding="utf-8")
    assert "gpt-" not in source and "claude-" not in source


def test_the_repository_price_file_loads_and_both_rows_read_2026_10_04():
    prices = est.load_model_prices(PRICES_PATH)
    assert set(prices) == {"claude-opus-5-5", "gpt-6-astra"}
    for row in prices.values():
        assert row["pricing"]["read_on"] == "2026-10-04"
        assert row["pricing"]["url"].startswith("https://")
    assert (prices["claude-opus-5-5"]["input"], prices["claude-opus-5-5"]["output"]) == (4.0, 20.0)
    assert (prices["gpt-6-astra"]["input"], prices["gpt-6-astra"]["output"]) == (10.0, 50.0)

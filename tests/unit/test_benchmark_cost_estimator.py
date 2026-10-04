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


# ---------------------------------------------------------------- B120 task 2
# dry runs of the build steps: counting clients, the real pipelines, mock data

from tere4ai.extract_norms import pipeline as extract_pipeline  # noqa: E402

DUMPS = ROOT / "data" / "graph_dumps"
B74_NORMS = DUMPS / "norms_core.b74.json"


def _unit_node(node_id, text, span):
    return {"id": node_id, "layer": 1, "type": "Paragraph", "text": text, "amendment": "unchanged",
            "source_span": {"span_id": span}}


def _mock_dump():
    """Mock data: one Article holding two paragraphs."""
    return {
        "build": {"build_id": "build-mock"},
        "nodes": [
            {"id": "eu-ai-act:article-9", "layer": 1, "type": "Article", "number": "9",
             "title": "Mock article"},
            _unit_node("eu-ai-act:article-9:paragraph-1",
                       "1. A risk management system shall be established.", "span:009.001"),
            _unit_node("eu-ai-act:article-9:paragraph-2",
                       "2. The risk management system shall be documented.", "span:009.002"),
        ],
        "edges": [],
    }


def _mock_norm(node_id, n=1, verdict="accepted"):
    return {
        "norm_id": f"norm:{node_id}:n{n}", "layer": 2, "type": "NormativeStatement",
        "source_node_id": node_id, "source_span_id": "span:009.001",
        "deontic_type": "obligation", "modal": "shall", "actor_explicit": None,
        "actor_inferred": "provider", "actor_inference_source_node_id": node_id,
        "action": "establish", "object": "a risk management system",
        "target_system_category": None, "conditions": [], "exceptions": [],
        "lifecycle_phase_ids": [], "judge_verdict": verdict,
        "source_text": "1. A risk management system shall be established.",
    }


def _mock_judge_run(norm):
    return {"id": norm["judge_run_id"], "verdict": "accepted",
            "scores": {"semantic_similarity": 0.9}, "rationale": "mock rationale"}


def test_every_ratio_has_a_value_and_a_source():
    assert est.RATIOS
    for name, ratio in est.RATIOS.items():
        assert isinstance(ratio["value"], float) and ratio["value"] > 0, name
        assert isinstance(ratio["source"], str) and ratio["source"].strip(), name


def test_the_counting_client_scripts_a_reply_per_call_and_counts_its_characters():
    client = est.CountingClient("mock", lambda system, user: {"echo": user})
    client.complete("s", "abc")
    client.complete("s", "defg")
    assert client.calls == 2 and client.last_user == "defg"
    assert client.out_chars == len(json.dumps({"echo": "abc"})) + len(json.dumps({"echo": "defg"}))


def test_the_extraction_dry_run_calls_the_generator_once_per_unit_with_the_real_prompt(tmp_path):
    dump = _mock_dump()
    ids = ["eu-ai-act:article-9"]
    norm = _mock_norm("eu-ai-act:article-9:paragraph-1")
    lines, candidates = est.extraction_lines(dump, ids, [norm], [], tmp_path)
    units = extract_pipeline.expand_source_units(dump, ids)
    system = extract_pipeline.load_prompt("extract_norms", extract_pipeline.DEFAULT_PROMPT_VERSION)
    gen = lines["generator"]
    assert gen["calls"] == len(units) == 2
    assert gen["in_chars"] == sum(
        len(system) + len(extract_pipeline._generator_user_message(u)) for u in units)
    # the scripted July reply for the unit with a norm, an empty list for the other
    assert gen["out_chars"] > 2 * len('{"norms": []}')


def test_the_extraction_dry_run_counts_judge_input_from_the_pipelines_own_message(tmp_path):
    dump = _mock_dump()
    ids = ["eu-ai-act:article-9"]
    norm = _mock_norm("eu-ai-act:article-9:paragraph-1")
    lines, candidates = est.extraction_lines(dump, ids, [norm], [], tmp_path)
    judge_system = extract_pipeline.load_prompt("judge_norms", extract_pipeline.DEFAULT_PROMPT_VERSION)
    unit = extract_pipeline.expand_source_units(dump, ids)[0]
    nodes = extract_pipeline._index_nodes(dump)
    candidate = {k: norm[k] for k in ("deontic_type", "modal", "actor_explicit", "actor_inferred",
                                      "actor_inference_source_node_id", "action", "object",
                                      "conditions", "exceptions") if k in norm}
    candidate["requirement_type"] = None
    one = len(judge_system) + len(extract_pipeline._judge_user_message(
        unit, candidate, extract_pipeline._inference_source_block(dump, nodes, unit, candidate)))
    judge = lines["judge"]
    # one candidate in the mock: judge calls = units x candidates per unit, at the mean input
    assert candidates == pytest.approx(2 * est.RATIOS["candidates_per_unit"]["value"])
    assert judge["calls"] == round(candidates)
    assert judge["in_chars"] == pytest.approx(judge["calls"] * one, rel=0.02)


def test_the_alignment_dry_run_calls_the_generator_once_per_accepted_norm(tmp_path):
    accepted = [_mock_norm("eu-ai-act:article-9:paragraph-1"),
                _mock_norm("eu-ai-act:article-9:paragraph-2")]
    rejected = _mock_norm("eu-ai-act:article-9:paragraph-2", n=2, verdict="rejected")
    hleg = [{"id": "hleg:transparency", "name": "Transparency",
             "description": "Mock description of transparency.",
             "source_span": {"span_id": "span:hleg:req4"}}]
    assertions = [{"source_norm_id": accepted[0]["norm_id"], "target_id": "hleg:transparency",
                   "relation_type": "supports", "source_quote": "risk management system",
                   "target_quote": "transparency", "rationale": "mock", "judge_run_id": "j1"}]
    judge_runs = [{"id": "j1", "judge_kind": "mapping", "verdict": "accepted",
                   "scores": {"semantic_similarity": 0.9}, "rationale": "mock rationale",
                   "corrected_relation_type": None}]
    lines = est.alignment_lines(accepted + [rejected], hleg, assertions, judge_runs,
                                accepted_norms=10, tmp_dir=tmp_path)
    gen = lines["generator"]
    assert gen["calls"] == 10  # scaled from the dry run's 2 accepted norms
    assert lines["dry_generator_calls"] == 2
    assert gen["out_chars"] > 0
    assert lines["judge"]["calls"] == round(10 * est.RATIOS["align_judge_per_accepted"]["value"])
    assert lines["judge"]["in_chars"] > 0 and lines["judge"]["out_chars"] > 0


def test_the_backlog_dry_run_makes_one_call_per_role(tmp_path):
    norms = [_mock_norm("eu-ai-act:article-25:paragraph-1")]
    norms[0]["norm_id"] = "norm:eu-ai-act:article-25:paragraph-1:n1"
    lines = est.backlog_lines(norms, "Mock system description.", tmp_path)
    assert lines["generator"]["calls"] == 1 and lines["judge"]["calls"] == 1
    assert lines["generator"]["in_chars"] > 0 and lines["judge"]["in_chars"] > 0


@pytest.mark.skipif(not est.ELICIT_DUMP.is_file(), reason="layer1.json dump not built")
def test_the_extraction_dry_run_expands_core_nodes_to_424_units():
    dump = json.loads(est.ELICIT_DUMP.read_text(encoding="utf-8"))
    ids = est.core_node_ids()
    assert len(ids) == 30
    assert len(extract_pipeline.expand_source_units(dump, ids)) == 424


@pytest.mark.skipif(not (B74_NORMS.is_file() and est.ELICIT_DUMP.is_file()),
                    reason="the aborted extraction's dump is not on disk")
def test_the_characters_per_token_ratios_recompute_from_the_aborted_run():
    measured = est.recompute_chars_per_token()
    for provider in ("openai", "anthropic"):
        assert measured[provider] == pytest.approx(est.RATIOS[f"chars_per_token_{provider}"]["value"],
                                                   rel=0.01)


def test_the_default_reasoning_share_is_billed_output_against_the_visible_reply():
    gen_norms = [{"source_node_id": f"u{i}", "deontic_type": "obligation"} for i in range(2)]
    payload = {
        "build": {"extraction_usage": {"generator": {"calls": 4, "output_tokens": 4 * 100},
                                       "judge": {"calls": 2, "output_tokens": 2 * 200}},
                  "prompt_version": "v1"},
        "stats": {"source_units": 4},
        "norms": gen_norms,
        "judge_runs": [{"verdict": "accepted", "scores": {}, "rationale": "r" * 100},
                       {"verdict": "accepted", "scores": {}, "rationale": "r" * 100}],
    }
    shares = est.default_reasoning_shares(payload)
    assert 0 < shares["generator"] < 1 and 0 < shares["judge"] < 1
    visible = sum(len(json.dumps({"norms": [{"deontic_type": "obligation"}]})) for _ in range(2))
    visible += 2 * len(json.dumps({"norms": []}))
    expected = 1 - (visible / 4 / est.RATIOS["chars_per_token_openai"]["value"]) / 100
    assert shares["generator"] == pytest.approx(expected)
